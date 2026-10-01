"""
Phase 2A Step 5 Contract Test: Narrowed AST Assertion Evaluator
上位依据:
- 《开发文档/45-Phase-2A-Step5-收窄AST解释执行器与事后证伪闭环实施规划.md》
- C-03: 白名单受限 AST 与单层结构化过滤
- Missing != False: 严防假零填充
- IEEE-754 临界精度安全
"""

import pytest
from typing import List, Optional

from app.cognition.hypothesis.contracts import (
    MetricAssertion,
    MetricType,
    UniverseType,
    OperatorType,
    AggregationType,
    MissingDataPolicy,
    AssertionOutcome,
    FilterCondition,
    StructuredFilter,
)
from app.cognition.hypothesis.evaluator import (
    AssertionEvaluator,
    AssertionSyntaxError,
    AssertionEvaluationResult,
)


def _build_test_assertion(
    assertion_id: str = "test_a_01",
    universe: UniverseType = UniverseType.ALL_A,
    conditions: Optional[List[FilterCondition]] = None,
    logical_op: str = "AND",
    metric: MetricType = MetricType.OPEN_PCT_CHANGE,
    aggregation: AggregationType = AggregationType.MEAN,
    operator: OperatorType = OperatorType.GT,
    target_value: Optional[float] = 0.0,
    target_range: Optional[List[float]] = None,
    missing_data_policy: MissingDataPolicy = MissingDataPolicy.INCONCLUSIVE,
) -> MetricAssertion:
    selector = StructuredFilter(
        universe_type=universe,
        conditions=conditions or [],
        logical_op=logical_op,
    )
    return MetricAssertion(
        assertion_id=assertion_id,
        selector=selector,
        metric=metric.value,
        aggregation=aggregation,
        operator=operator,
        target_value=target_value,
        target_range=target_range,
        missing_data_policy=missing_data_policy,
    )


def test_01_ast_syntax_and_whitelist_enforcement():
    """验证 1: AST 静态语法与白名单校验，越权字段或非法操作符强制抛错"""
    # 1. 尝试注入未知指标字段 (不在 MetricType 白名单)
    with pytest.raises(AssertionSyntaxError, match="Metric 'unauthorized_alpha' 不在白名单中"):
        selector = StructuredFilter(universe_type=UniverseType.ALL_A)
        bad_assertion = MetricAssertion(
            assertion_id="bad_01",
            selector=selector,
            metric="unauthorized_alpha",
            aggregation=AggregationType.MEAN,
            operator=OperatorType.GT,
            target_value=0.0,
        )
        AssertionEvaluator.evaluate(bad_assertion, {"stocks": []})

    # 2. 尝试在 Filter 中使用非法字段注入 (不在 WHITELIST_FILTER_FIELDS)
    with pytest.raises(AssertionSyntaxError, match="过滤字段 'select_password_from_users' 不在白名单中"):
        bad_cond = FilterCondition(field="select_password_from_users", op=OperatorType.EQ, val=1)
        selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[bad_cond])
        bad_assertion = MetricAssertion(
            assertion_id="bad_02",
            selector=selector,
            metric=MetricType.OPEN_PCT_CHANGE.value,
            aggregation=AggregationType.MEAN,
            operator=OperatorType.GT,
            target_value=0.0,
        )
        AssertionEvaluator.evaluate(bad_assertion, {"stocks": []})

    # 3. BETWEEN 操作符未提供合法的 target_range
    with pytest.raises(AssertionSyntaxError, match="Operator 'BETWEEN' 必须提供包含2个元素的 target_range"):
        bad_assertion = _build_test_assertion(operator=OperatorType.BETWEEN, target_value=None, target_range=None)
        AssertionEvaluator.evaluate(bad_assertion, {"stocks": []})


def test_02_structured_filter_and_boolean_logic():
    """验证 2: 单层平铺过滤器条件求值与布尔组合 (AND / OR)"""
    mock_data = {
        "stocks": [
            {"code": "001", "board_height": 3, "sector_code": "BK001", "open_pct_change": 5.0},
            {"code": "002", "board_height": 2, "sector_code": "BK001", "open_pct_change": 2.0},
            {"code": "003", "board_height": 3, "sector_code": "BK002", "open_pct_change": -1.0},
            {"code": "004", "board_height": 1, "sector_code": "BK002", "open_pct_change": -3.0},
        ]
    }

    # 1. 单条件过滤: board_height == 3 -> [001, 003] -> MEAN = (5 + -1) / 2 = 2.0 > 1.0 (PASSED)
    c1 = FilterCondition(field="board_height", op=OperatorType.EQ, val=3)
    a1 = _build_test_assertion(universe=UniverseType.ALL_A, conditions=[c1], target_value=1.0)
    res1 = AssertionEvaluator.evaluate(a1, mock_data)
    assert res1.outcome == AssertionOutcome.PASSED
    assert res1.matched_count == 2
    assert res1.actual_value == 2.0

    # 2. 多条件 AND 过滤: board_height == 3 AND sector_code == "BK001" -> [001] -> MEAN = 5.0 > 4.0 (PASSED)
    c2 = FilterCondition(field="sector_code", op=OperatorType.EQ, val="BK001")
    a2 = _build_test_assertion(universe=UniverseType.ALL_A, conditions=[c1, c2], logical_op="AND", target_value=4.0)
    res2 = AssertionEvaluator.evaluate(a2, mock_data)
    assert res2.outcome == AssertionOutcome.PASSED
    assert res2.matched_count == 1
    assert res2.actual_value == 5.0

    # 3. 多条件 OR 过滤: board_height == 1 OR sector_code == "BK001" -> [001, 002, 004] -> matched_count = 3
    c3 = FilterCondition(field="board_height", op=OperatorType.EQ, val=1)
    a3 = _build_test_assertion(
        universe=UniverseType.ALL_A,
        conditions=[c3, c2],
        logical_op="OR",
        aggregation=AggregationType.COUNT,
        operator=OperatorType.EQ,
        target_value=3.0,
    )
    res3 = AssertionEvaluator.evaluate(a3, mock_data)
    assert res3.outcome == AssertionOutcome.PASSED
    assert res3.actual_value == 3.0


def test_03_aggregation_functions_evaluation():
    """验证 3: 核心统计聚合函数 (MEAN, MEDIAN, MAX, MIN, COUNT, SUM)"""
    mock_data = {
        "stocks": [
            {"code": "001", "board_height": 4, "open_pct_change": 1.0},
            {"code": "002", "board_height": 3, "open_pct_change": 2.0},
            {"code": "003", "board_height": 3, "open_pct_change": 9.0},
        ]
    }
    c = FilterCondition(field="board_height", op=OperatorType.GTE, val=3)

    # 1. MEAN: (1 + 2 + 9) / 3 = 4.0
    a_mean = _build_test_assertion(universe=UniverseType.ALL_A, conditions=[c], aggregation=AggregationType.MEAN, operator=OperatorType.EQ, target_value=4.0)
    assert AssertionEvaluator.evaluate(a_mean, mock_data).outcome == AssertionOutcome.PASSED

    # 2. MEDIAN: 中位数 [1, 2, 9] = 2.0
    a_med = _build_test_assertion(universe=UniverseType.ALL_A, conditions=[c], aggregation=AggregationType.MEDIAN, operator=OperatorType.EQ, target_value=2.0)
    assert AssertionEvaluator.evaluate(a_med, mock_data).outcome == AssertionOutcome.PASSED

    # 3. MAX: 9.0
    a_max = _build_test_assertion(universe=UniverseType.ALL_A, conditions=[c], aggregation=AggregationType.MAX, operator=OperatorType.EQ, target_value=9.0)
    assert AssertionEvaluator.evaluate(a_max, mock_data).outcome == AssertionOutcome.PASSED

    # 4. MIN: 1.0
    a_min = _build_test_assertion(universe=UniverseType.ALL_A, conditions=[c], aggregation=AggregationType.MIN, operator=OperatorType.EQ, target_value=1.0)
    assert AssertionEvaluator.evaluate(a_min, mock_data).outcome == AssertionOutcome.PASSED

    # 5. COUNT: 3.0
    a_count = _build_test_assertion(universe=UniverseType.ALL_A, conditions=[c], aggregation=AggregationType.COUNT, operator=OperatorType.EQ, target_value=3.0)
    assert AssertionEvaluator.evaluate(a_count, mock_data).outcome == AssertionOutcome.PASSED

    # 6. SUM: 12.0
    a_sum = _build_test_assertion(universe=UniverseType.ALL_A, conditions=[c], aggregation=AggregationType.SUM, operator=OperatorType.EQ, target_value=12.0)
    assert AssertionEvaluator.evaluate(a_sum, mock_data).outcome == AssertionOutcome.PASSED


def test_04_operators_and_boundary_precision():
    """验证 4: 操作符比较与临界浮点精度 (GT / GTE / LT / LTE / BETWEEN)"""
    mock_data = {"stocks": [{"code": "001", "board_height": 2, "open_pct_change": -3.0000001}]}
    c = FilterCondition(field="board_height", op=OperatorType.EQ, val=2)

    # 实际值 -3.0000001 <= -3.0 -> PASSED
    a_lte = _build_test_assertion(universe=UniverseType.ALL_A, conditions=[c], operator=OperatorType.LTE, target_value=-3.0)
    assert AssertionEvaluator.evaluate(a_lte, mock_data).outcome == AssertionOutcome.PASSED

    # 实际值 -3.0000001 < -3.0 -> PASSED
    a_lt = _build_test_assertion(universe=UniverseType.ALL_A, conditions=[c], operator=OperatorType.LT, target_value=-3.0)
    assert AssertionEvaluator.evaluate(a_lt, mock_data).outcome == AssertionOutcome.PASSED

    # 实际值 -3.0000001 >= -3.0 -> FAILED
    a_gte = _build_test_assertion(universe=UniverseType.ALL_A, conditions=[c], operator=OperatorType.GTE, target_value=-3.0)
    assert AssertionEvaluator.evaluate(a_gte, mock_data).outcome == AssertionOutcome.FAILED

    # BETWEEN [-4.0, -3.0] -> PASSED
    a_between = _build_test_assertion(universe=UniverseType.ALL_A, conditions=[c], operator=OperatorType.BETWEEN, target_range=[-4.0, -3.0])
    assert AssertionEvaluator.evaluate(a_between, mock_data).outcome == AssertionOutcome.PASSED


def test_05_empty_set_semantics():
    """验证 5: 标的池为空时的确定性语义 (COUNT 为 0 vs 数值聚合为缺失)"""
    empty_data = {"stocks": []}
    c = FilterCondition(field="board_height", op=OperatorType.GTE, val=4)

    # 1. COUNT 聚合在空集合上：输出合法 0.0，断言 == 0.0 成立
    a_count = _build_test_assertion(
        universe=UniverseType.ALL_A,
        conditions=[c],
        aggregation=AggregationType.COUNT,
        operator=OperatorType.EQ,
        target_value=0.0,
    )
    res_count = AssertionEvaluator.evaluate(a_count, empty_data)
    assert res_count.outcome == AssertionOutcome.PASSED
    assert res_count.actual_value == 0.0

    # 2. MEAN 聚合在空集合上：无法计算均值，不能假零填充，输出 INCONCLUSIVE
    a_mean = _build_test_assertion(
        universe=UniverseType.ALL_A,
        conditions=[c],
        aggregation=AggregationType.MEAN,
        operator=OperatorType.GT,
        target_value=0.0,
    )
    res_mean = AssertionEvaluator.evaluate(a_mean, empty_data)
    assert res_mean.outcome == AssertionOutcome.INCONCLUSIVE
    assert res_mean.actual_value is None
    assert res_mean.is_missing is True


def test_06_missing_data_policy_and_no_zero_fill():
    """验证 6: 缺数语义与缺失策略 (Missing != False, 严禁假零填充)"""
    # 模拟数据源超时不可用
    timeout_data = {"status": "TIMEOUT", "stocks": []}
    c = FilterCondition(field="board_height", op=OperatorType.GTE, val=2)

    # 1. 默认策略: INCONCLUSIVE
    a_default = _build_test_assertion(
        universe=UniverseType.ALL_A,
        conditions=[c],
        missing_data_policy=MissingDataPolicy.INCONCLUSIVE,
    )
    res_def = AssertionEvaluator.evaluate(a_default, timeout_data)
    assert res_def.outcome == AssertionOutcome.INCONCLUSIVE
    assert res_def.is_missing is True
    assert res_def.actual_value is None

    # 2. FAIL_FALSIFIED 策略: FAILED (若配置了严厉策略)
    a_strict = _build_test_assertion(
        universe=UniverseType.ALL_A,
        conditions=[c],
        missing_data_policy=MissingDataPolicy.FAIL_FALSIFIED,
    )
    res_strict = AssertionEvaluator.evaluate(a_strict, timeout_data)
    assert res_strict.outcome == AssertionOutcome.FAILED
    assert res_strict.is_missing is True

    # 3. SKIP 策略: SKIPPED
    a_skip = _build_test_assertion(
        universe=UniverseType.ALL_A,
        conditions=[c],
        missing_data_policy=MissingDataPolicy.SKIP,
    )
    res_skip = AssertionEvaluator.evaluate(a_skip, timeout_data)
    assert res_skip.outcome == AssertionOutcome.SKIPPED
    assert res_skip.is_missing is True
