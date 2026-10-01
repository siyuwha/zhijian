"""
Narrowed AST Assertion Evaluator (Phase 2A Step 5 Runtime)
上位依据：
1. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》v1.2.1-FINAL (第4.2节)
2. 《开发文档/45-Phase-2A-Step5-收窄AST解释执行器与事后证伪闭环实施规划.md》

核心铁律：
- 【C-03 闭环】：严格执行有限白名单 AST 解释求值，严禁任意 SQL 注入与动态解析
- Missing-Data 语义求值：缺数时强制输出 INCONCLUSIVE，严禁假零填充 (Missing != False, Missing != 0)
- IEEE-754 临界精度安全：采用 math.isclose(rel_tol=1e-9, abs_tol=1e-9) 防范浮点抖动
- 纯沙箱、类型安全、内存级确定性求值
"""

import math
import statistics
from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, ConfigDict

from .contracts import (
    MetricAssertion,
    MetricType,
    UniverseType,
    OperatorType,
    AggregationType,
    MissingDataPolicy,
    AssertionOutcome,
    WHITELIST_FILTER_FIELDS,
)


class AssertionSyntaxError(ValueError):
    """断言语法或白名单违规异常"""
    pass


class AssertionEvaluationResult(BaseModel):
    """单项断言求值结果不可变值对象"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    assertion_id: str
    outcome: AssertionOutcome
    actual_value: Optional[float] = None
    target_value: Optional[float] = None
    target_range: Optional[List[float]] = None
    matched_count: int = 0
    is_missing: bool = False
    details: str = ""


class AssertionEvaluator:
    """收窄 AST 指标断言解释执行器"""

    @classmethod
    def evaluate(
        cls,
        assertion: MetricAssertion,
        observation_data: Dict[str, Any],
    ) -> AssertionEvaluationResult:
        """
        对单项 MetricAssertion 在给定的观测事实切片上进行确定性求值
        """
        # 1. 语法与白名单校验 (AST Syntax Validation)
        cls._validate_assertion_syntax(assertion)

        # 2. 检查整体数据源是否标记为 MISSING / TIMEOUT / ERROR
        if observation_data.get("status") in ("MISSING", "TIMEOUT", "ERROR") or observation_data.get("is_missing") is True:
            return cls._handle_missing_data(
                assertion,
                details=f"数据源状态异常或缺失: status={observation_data.get('status')}",
            )

        # 3. 提取候选标的池 (Universe Selection)
        raw_items = cls._extract_universe(assertion.selector.universe_type, observation_data)

        # 4. 执行单层平铺条件过滤 (StructuredFilter Evaluation)
        filtered_items = cls._apply_filter(assertion.selector, raw_items)
        matched_count = len(filtered_items)

        # 5. 针对标的集合为空时的空语义处理 (Empty Set Handling)
        if matched_count == 0:
            if assertion.aggregation == AggregationType.COUNT:
                # 计数函数聚合空集合输出合法 0.0
                actual_val = 0.0
            else:
                # 数值指标（如 MEAN/MAX/MIN）在空集合上无法计算均值或极值
                return cls._handle_missing_data(
                    assertion,
                    details=f"过滤后目标标的集合为空 (matched_count=0)，无法计算 {assertion.aggregation.value}",
                )
        else:
            # 6. 提取指标值并检查数值缺失
            metric_values: List[float] = []
            has_missing_metric = False

            for it in filtered_items:
                v = it.get(assertion.metric)
                if v is None:
                    has_missing_metric = True
                else:
                    try:
                        metric_values.append(float(v))
                    except (ValueError, TypeError):
                        has_missing_metric = True

            # 若关键指标存在缺失，执行缺失策略
            if has_missing_metric or len(metric_values) == 0:
                return cls._handle_missing_data(
                    assertion,
                    details=f"标的池中存在指标缺失或空值: metric={assertion.metric}",
                )

            # 7. 执行聚合计算 (Aggregation Processing)
            actual_val = cls._compute_aggregation(assertion.aggregation, metric_values)

        # 8. 操作符比较求值 (Operator Evaluation)
        passed = cls._compare(
            actual_val=actual_val,
            operator=assertion.operator,
            target_value=assertion.target_value,
            target_range=assertion.target_range,
        )

        outcome = AssertionOutcome.PASSED if passed else AssertionOutcome.FAILED
        detail_msg = (
            f"断言求值: {assertion.metric} {assertion.aggregation.value} "
            f"实际值={actual_val:.4f} {assertion.operator.value} "
            f"目标值={assertion.target_value or assertion.target_range}, 判定={outcome.value}"
        )

        return AssertionEvaluationResult(
            assertion_id=assertion.assertion_id,
            outcome=outcome,
            actual_value=round(actual_val, 6),
            target_value=assertion.target_value,
            target_range=assertion.target_range,
            matched_count=matched_count,
            is_missing=False,
            details=detail_msg,
        )

    @classmethod
    def _validate_assertion_syntax(cls, assertion: MetricAssertion) -> None:
        """白名单强类型静态校验，严禁未知字段注入"""
        # 1. 检查 metric 白名单
        valid_metrics = {m.value for m in MetricType}
        if assertion.metric not in valid_metrics:
            raise AssertionSyntaxError(
                f"Metric '{assertion.metric}' 不在白名单中: {sorted(valid_metrics)}"
            )

        # 2. 检查 filter field 白名单
        for cond in assertion.selector.conditions:
            if cond.field not in WHITELIST_FILTER_FIELDS:
                raise AssertionSyntaxError(
                    f"过滤字段 '{cond.field}' 不在白名单中: {sorted(WHITELIST_FILTER_FIELDS)}"
                )

        # 3. 检查 BETWEEN 操作符必须提供 target_range
        if assertion.operator == OperatorType.BETWEEN:
            if not assertion.target_range or len(assertion.target_range) != 2:
                raise AssertionSyntaxError("Operator 'BETWEEN' 必须提供包含2个元素的 target_range [min, max]")

        # 4. 检查常规操作符必须提供 target_value
        if assertion.operator in (OperatorType.GT, OperatorType.GTE, OperatorType.LT, OperatorType.LTE, OperatorType.EQ, OperatorType.NE):
            if assertion.target_value is None:
                raise AssertionSyntaxError(f"Operator '{assertion.operator.value}' 必须提供有效的 target_value")

    @classmethod
    def _extract_universe(cls, universe: UniverseType, observation_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """从事实切片中提取对应标的范围的原始记录列表"""
        # 支持多种常见的事实字典组织格式
        if universe == UniverseType.ALL_A:
            return observation_data.get("stocks", observation_data.get("all_stocks", []))
        elif universe == UniverseType.LADDER_HIGH_SPEC:
            # 优先从高标专用列表提取，若无则从 stocks 筛选连板股
            ladder = observation_data.get("ladder_stocks", observation_data.get("high_open_stats", []))
            if ladder:
                return ladder
            all_s = observation_data.get("stocks", [])
            return [s for s in all_s if s.get("board_height", 0) >= 2 or s.get("is_highest_board") is True]
        elif universe == UniverseType.SECTOR:
            return observation_data.get("sector_stocks", observation_data.get("stocks", []))
        elif universe == UniverseType.CUSTOM_LIST:
            return observation_data.get("custom_stocks", observation_data.get("stocks", []))
        return []

    @classmethod
    def _apply_filter(cls, selector: Any, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """对列表项执行单层平铺条件过滤 (支持 AND / OR 逻辑)"""
        if not selector.conditions:
            return items

        filtered = []
        is_or = selector.logical_op.upper() == "OR"

        for item in items:
            condition_matches = []
            for cond in selector.conditions:
                field_val = item.get(cond.field)
                match = cls._match_condition(field_val, cond.op, cond.val)
                condition_matches.append(match)

            if is_or:
                if any(condition_matches):
                    filtered.append(item)
            else:
                if all(condition_matches):
                    filtered.append(item)

        return filtered

    @classmethod
    def _match_condition(cls, actual: Any, op: OperatorType, target: Any) -> bool:
        """单字段条件判定"""
        if actual is None:
            return False

        try:
            if op == OperatorType.EQ:
                return actual == target
            elif op == OperatorType.NE:
                return actual != target
            elif op == OperatorType.GT:
                return float(actual) > float(target)
            elif op == OperatorType.GTE:
                return float(actual) >= float(target)
            elif op == OperatorType.LT:
                return float(actual) < float(target)
            elif op == OperatorType.LTE:
                return float(actual) <= float(target)
            elif op == OperatorType.IN:
                return actual in target
        except (ValueError, TypeError):
            return False
        return False

    @classmethod
    def _compute_aggregation(cls, agg: AggregationType, values: List[float]) -> float:
        """执行聚合运算"""
        if agg == AggregationType.COUNT:
            return float(len(values))
        elif agg == AggregationType.MEAN:
            return statistics.fmean(values)
        elif agg == AggregationType.MEDIAN:
            return statistics.median(values)
        elif agg == AggregationType.MAX:
            return max(values)
        elif agg == AggregationType.MIN:
            return min(values)
        elif agg == AggregationType.SUM:
            return sum(values)
        elif agg == AggregationType.NONE:
            return values[0] if values else 0.0
        return values[0]

    @classmethod
    def _compare(
        cls,
        actual_val: float,
        operator: OperatorType,
        target_value: Optional[float],
        target_range: Optional[List[float]],
    ) -> bool:
        """比较求值 (采用 1e-9 容差与 math.isclose 防范 IEEE-754 临界精度抖动)"""
        rel_tol = 1e-9
        abs_tol = 1e-9

        if operator == OperatorType.GT:
            return actual_val > target_value and not math.isclose(actual_val, target_value, rel_tol=rel_tol, abs_tol=abs_tol)
        elif operator == OperatorType.GTE:
            return actual_val >= target_value or math.isclose(actual_val, target_value, rel_tol=rel_tol, abs_tol=abs_tol)
        elif operator == OperatorType.LT:
            return actual_val < target_value and not math.isclose(actual_val, target_value, rel_tol=rel_tol, abs_tol=abs_tol)
        elif operator == OperatorType.LTE:
            return actual_val <= target_value or math.isclose(actual_val, target_value, rel_tol=rel_tol, abs_tol=abs_tol)
        elif operator == OperatorType.EQ:
            return math.isclose(actual_val, target_value, rel_tol=rel_tol, abs_tol=abs_tol)
        elif operator == OperatorType.NE:
            return not math.isclose(actual_val, target_value, rel_tol=rel_tol, abs_tol=abs_tol)
        elif operator == OperatorType.BETWEEN:
            if target_range and len(target_range) == 2:
                low, high = min(target_range), max(target_range)
                low_ok = actual_val >= low or math.isclose(actual_val, low, rel_tol=rel_tol, abs_tol=abs_tol)
                high_ok = actual_val <= high or math.isclose(actual_val, high, rel_tol=rel_tol, abs_tol=abs_tol)
                return low_ok and high_ok
            return False
        return False

    @classmethod
    def _handle_missing_data(
        cls,
        assertion: MetricAssertion,
        details: str,
    ) -> AssertionEvaluationResult:
        """依策略处理缺失数据（严守 Missing != False 铁律）"""
        if assertion.missing_data_policy == MissingDataPolicy.FAIL_FALSIFIED:
            outcome = AssertionOutcome.FAILED
        elif assertion.missing_data_policy == MissingDataPolicy.SKIP:
            outcome = AssertionOutcome.SKIPPED
        else:
            outcome = AssertionOutcome.INCONCLUSIVE

        return AssertionEvaluationResult(
            assertion_id=assertion.assertion_id,
            outcome=outcome,
            actual_value=None,
            target_value=assertion.target_value,
            target_range=assertion.target_range,
            matched_count=0,
            is_missing=True,
            details=f"[DATA DEFICIENCY]: {details}, outcome={outcome.value}",
        )
