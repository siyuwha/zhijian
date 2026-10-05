"""
Phase 2B.2: 受约束 LLM 认知假说提议器校验器 (ProposalValidator)
上位依据：《开发文档/56-Phase-2B.2-受约束LLM认知假说提议器契约设计单.md》

核心职责：
1. 校验来自 LLM 生成的原始 JSON 提案结构；
2. 严厉执行 VR-01 ~ VR-07 的 7 大准入防御规则（白名单、时序、刚性证伪红线、交易禁令）；
3. 将通过校验的合法提案编译为标准 MarketHypothesisCreate，供下游入库与 AST 解释执行；
4. 任何违规提案立即阻断抛出详细错误，绝不静默修正或假定默认值。
"""

import re
from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .contracts import (
    MetricType,
    OperatorType,
    UniverseType,
)
from ...schemas.cognition import MarketHypothesisCreate

# 允许的假说类型白名单 (Phase 2C 解封 INITIAL_OUTBREAK 与 SECTOR_ROTATION)
ALLOWED_HYPOTHESIS_TYPES = {
    "SENTIMENT_CYCLE",
    "INDEX_TREND",
    "MARKET_STATE",
    "BREADTH_TREND",
    "INITIAL_OUTBREAK",
    "SECTOR_ROTATION",
}

# 允许的标的代码白名单 (全A宏观聚合 + 四大核心宽基，严禁个股代码)
ALLOWED_TARGET_CODES = {
    "ALL_A",
    "sh000001",
    "sz399001",
    "sz399006",
    "sh000688",
}

# 允许的白名单指标
ALLOWED_METRIC_TYPES = {
    MetricType.LIMIT_UP_COUNT.value,
    MetricType.LIMIT_DOWN_COUNT.value,
    MetricType.PCT_CHANGE.value,
    MetricType.OPEN_PCT_CHANGE.value,
    MetricType.TURNOVER_RATIO.value,
    MetricType.BOARD_HEIGHT.value,
    "up_count",
    "down_count",
    "leader_open_pct",
    "sector_change_pct",
}

# 允许的操作符
ALLOWED_OPERATORS = {
    OperatorType.GT.value,
    OperatorType.GTE.value,
    OperatorType.LT.value,
    OperatorType.LTE.value,
    OperatorType.EQ.value,
    OperatorType.NE.value,
    OperatorType.BETWEEN.value,
}

# 交易禁令黑名单关键词 (严防大模型滑向交易建议与买卖预测)
PROHIBITED_TRADING_KEYWORDS = [
    "买入", "卖出", "建仓", "加仓", "减仓", "清仓", "做多", "做空",
    "目标价", "止盈价", "止损价", "现价买", "抄底", "逃顶", "开仓",
]


class ProposalAssertionNode(BaseModel):
    """提案中的单项指标断言节点"""
    model_config = ConfigDict(extra="forbid")

    assertion_id: str = Field(..., description="断言唯一标识")
    metric_type: str = Field(..., description="白名单指标类型")
    target_code: str = Field("ALL_A", description="宏观目标代码")
    operator: str = Field(..., description="操作符枚举")
    threshold: Union[float, int, List[Union[float, int]]] = Field(..., description="阈值或闭区间")
    description: Optional[str] = Field(None, description="可读描述")


class LLMProposalPayload(BaseModel):
    """LLM 输出的候选假说提案完整载荷"""
    model_config = ConfigDict(extra="forbid")

    target_date: str = Field(..., description="目标验证日期 YYYY-MM-DD")
    hypothesis_type: str = Field(..., description="假说类型枚举")
    target_asset: str = Field(..., description="推演标的宏观对象描述")
    expected_scenario: str = Field(..., description="预期演绎形态")
    premise_logic: str = Field(..., description="前置支撑逻辑")
    expected_phenomenon: str = Field(..., description="预期盘面现象")
    expected_assertions: List[ProposalAssertionNode] = Field(..., description="预期满足指标断言列表")
    invalidation_condition: str = Field(..., description="失效条件自然语言")
    invalidation_assertions: List[ProposalAssertionNode] = Field(..., description="刚性证伪红线断言列表")
    explanation: Optional[str] = Field(None, description="推理补充说明")


class ProposalValidationResult(BaseModel):
    """提案校验与编译结果不可变对象"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    is_valid: bool
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    compiled_hypothesis: Optional[MarketHypothesisCreate] = None


class ProposalValidator:
    """受约束假说提案准入校验器"""

    @classmethod
    def validate_and_compile(
        cls,
        raw_proposal: Dict[str, Any],
        market_date: str,
    ) -> ProposalValidationResult:
        """
        对单项原始 JSON 提案执行 VR-01 ~ VR-07 的逐条强校验。
        若全部通过，编译输出符合现有 Phase 2B.1 契约的 MarketHypothesisCreate。
        """
        # ---------------------------------------------------------------------
        # VR-01: Schema 结构完备性与必填项校验
        # ---------------------------------------------------------------------
        try:
            proposal = LLMProposalPayload.model_validate(raw_proposal)
        except ValidationError as ve:
            return ProposalValidationResult(
                is_valid=False,
                error_code="VR-01_SCHEMA_INVALID",
                error_detail=f"提案数据结构不合法: {ve.errors()}",
            )
        except Exception as e:
            return ProposalValidationResult(
                is_valid=False,
                error_code="VR-01_PARSE_ERROR",
                error_detail=f"原始提案解析异常: {str(e)}",
            )

        # ---------------------------------------------------------------------
        # VR-06: 时序因果硬约束 (target_date 严格晚于 market_date)
        # ---------------------------------------------------------------------
        if proposal.target_date <= market_date:
            return ProposalValidationResult(
                is_valid=False,
                error_code="VR-06_TIME_CAUSALITY_VIOLATION",
                error_detail=f"目标验证日期 ({proposal.target_date}) 必须严格晚于当前基准事实日期 ({market_date})，严禁时间倒挂与当天自证",
            )

        # ---------------------------------------------------------------------
        # VR-02: 假说类型与宏观标的白名单
        # ---------------------------------------------------------------------
        if proposal.hypothesis_type not in ALLOWED_HYPOTHESIS_TYPES:
            return ProposalValidationResult(
                is_valid=False,
                error_code="VR-02_ILLEGAL_HYPOTHESIS_TYPE",
                error_detail=f"假说类型 '{proposal.hypothesis_type}' 不在白名单中: {sorted(ALLOWED_HYPOTHESIS_TYPES)}",
            )

        all_nodes = proposal.expected_assertions + proposal.invalidation_assertions
        for node in all_nodes:
            if proposal.hypothesis_type in ("INITIAL_OUTBREAK", "SECTOR_ROTATION"):
                # 板块假说允许合规板块代码 (以 BK 开头或 SECTOR) 或宏观白名单
                is_sector_code = node.target_code.startswith("BK") or node.target_code in ("SECTOR", "ALL_A")
                if not is_sector_code and node.target_code not in ALLOWED_TARGET_CODES:
                    return ProposalValidationResult(
                        is_valid=False,
                        error_code="VR-02_ILLEGAL_TARGET_CODE",
                        error_detail=f"板块假说标的代码 '{node.target_code}' 不合法 (必须为 BK*、SECTOR 或宏观白名单)",
                    )
            else:
                if node.target_code not in ALLOWED_TARGET_CODES:
                    return ProposalValidationResult(
                        is_valid=False,
                        error_code="VR-02_ILLEGAL_TARGET_CODE",
                        error_detail=f"断言标的代码 '{node.target_code}' 不在宏观白名单中 (严禁个股): {sorted(ALLOWED_TARGET_CODES)}",
                    )

        # ---------------------------------------------------------------------
        # VR-03: 指标白名单校验
        # ---------------------------------------------------------------------
        for node in all_nodes:
            if node.metric_type not in ALLOWED_METRIC_TYPES:
                return ProposalValidationResult(
                    is_valid=False,
                    error_code="VR-03_UNAPPROVED_METRIC",
                    error_detail=f"断言指标 '{node.metric_type}' 不在白名单中: {sorted(ALLOWED_METRIC_TYPES)}",
                )

        # ---------------------------------------------------------------------
        # VR-04: 操作符与阈值合理性校验
        # ---------------------------------------------------------------------
        for node in all_nodes:
            if node.operator not in ALLOWED_OPERATORS:
                return ProposalValidationResult(
                    is_valid=False,
                    error_code="VR-04_ILLEGAL_OPERATOR",
                    error_detail=f"操作符 '{node.operator}' 不在白名单中: {sorted(ALLOWED_OPERATORS)}",
                )
            if node.operator == OperatorType.BETWEEN.value:
                if not isinstance(node.threshold, list) or len(node.threshold) != 2:
                    return ProposalValidationResult(
                        is_valid=False,
                        error_code="VR-04_INVALID_BETWEEN_THRESHOLD",
                        error_detail=f"BETWEEN 操作符要求 threshold 为含2个元素的列表，收到: {node.threshold}",
                    )
                if node.threshold[0] > node.threshold[1]:
                    return ProposalValidationResult(
                        is_valid=False,
                        error_code="VR-04_INVALID_RANGE_ORDER",
                        error_detail=f"闭区间必须 min <= max: {node.threshold}",
                    )
            else:
                if not isinstance(node.threshold, (int, float)):
                    return ProposalValidationResult(
                        is_valid=False,
                        error_code="VR-04_SCALAR_THRESHOLD_REQUIRED",
                        error_detail=f"操作符 '{node.operator}' 要求标量数值阈值，收到: {type(node.threshold)}",
                    )

        # ---------------------------------------------------------------------
        # VR-05: 刚性证伪断言必须非空 (强制落实波普尔原则)
        # ---------------------------------------------------------------------
        if not proposal.invalidation_assertions or len(proposal.invalidation_assertions) == 0:
            return ProposalValidationResult(
                is_valid=False,
                error_code="VR-05_MISSING_FALSIFICATION_REDLINE",
                error_detail="提案必须包含至少一项刚性证伪红线断言 (invalidation_assertions 严禁为空)",
            )

        # ---------------------------------------------------------------------
        # VR-07: 交易禁令黑名单过滤 (严防大模型掺杂买卖建议)
        # ---------------------------------------------------------------------
        text_corpus = f"{proposal.premise_logic} {proposal.expected_phenomenon} {proposal.invalidation_condition} {proposal.explanation or ''}"
        for kw in PROHIBITED_TRADING_KEYWORDS:
            if kw in text_corpus:
                return ProposalValidationResult(
                    is_valid=False,
                    error_code="VR-07_PROHIBITED_TRADING_ADVICE",
                    error_detail=f"提案包含违规交易建议关键词 '{kw}'，系统严禁个股买卖与预测指令",
                )

        # ---------------------------------------------------------------------
        # 全部校验通过：编译为下游标准的 MarketHypothesisCreate
        # ---------------------------------------------------------------------
        compiled_assertions = {
            "expected_assertions": [
                {
                    "assertion_id": a.assertion_id,
                    "metric_type": a.metric_type,
                    "target_code": a.target_code,
                    "operator": a.operator,
                    "threshold": a.threshold,
                    "description": a.description,
                }
                for a in proposal.expected_assertions
            ],
            "invalidation_assertions": [
                {
                    "assertion_id": a.assertion_id,
                    "metric_type": a.metric_type,
                    "target_code": a.target_code,
                    "operator": a.operator,
                    "threshold": a.threshold,
                    "description": a.description,
                }
                for a in proposal.invalidation_assertions
            ],
        }

        compiled_create = MarketHypothesisCreate(
            created_date=market_date,
            target_date=proposal.target_date,
            hypothesis_type=proposal.hypothesis_type,
            target_asset=proposal.target_asset,
            expected_scenario=proposal.expected_scenario,
            premise_logic=proposal.premise_logic,
            expected_phenomenon=proposal.expected_phenomenon,
            invalidation_condition=proposal.invalidation_condition,
            assertion_metrics=compiled_assertions,
        )

        return ProposalValidationResult(
            is_valid=True,
            compiled_hypothesis=compiled_create,
        )
