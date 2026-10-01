"""
Phase 2A Step 5 Contract Test: Falsification-First Adjudication Engine
上位依据:
- 《开发文档/45-Phase-2A-Step5-收窄AST解释执行器与事后证伪闭环实施规划.md》
- C-01: Falsification-First 原则与证伪短路
- Missing != False: 严防假零填充
"""

import pytest
from typing import List

from app.cognition.hypothesis.contracts import (
    MarketHypothesisDefinition,
    MetricAssertion,
    MetricType,
    UniverseType,
    OperatorType,
    AggregationType,
    MissingDataPolicy,
    HypothesisOutcome,
    FilterCondition,
    StructuredFilter,
)
from app.cognition.hypothesis.falsification import (
    FalsificationEngine,
    HypothesisAdjudicationResult,
)


def _create_assertion(
    assertion_id: str,
    metric: MetricType,
    op: OperatorType,
    target_val: float,
    agg: AggregationType = AggregationType.MEAN,
    height_filter: int = 2,
) -> MetricAssertion:
    c = FilterCondition(field="board_height", op=OperatorType.GTE, val=height_filter)
    selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[c])
    return MetricAssertion(
        assertion_id=assertion_id,
        selector=selector,
        metric=metric.value,
        aggregation=agg,
        operator=op,
        target_value=target_val,
    )


def test_01_falsification_first_priority():
    """验证 1: C-01 证伪优先原则，预期断言即使全过，只要证伪断言触发，立即短路为 FALSIFIED"""
    # 假说设定：预期 2板以上高标开盘均值 > 2.0；若出现 2板以上高标跌幅 < -4.0 则视为被反向证伪
    exp_a = _create_assertion("exp_01", MetricType.OPEN_PCT_CHANGE, OperatorType.GT, 2.0)
    inv_a = _create_assertion("inv_01", MetricType.OPEN_PCT_CHANGE, OperatorType.LT, -4.0, agg=AggregationType.MIN)

    hypo = MarketHypothesisDefinition(
        hypothesis_id="h_test_01",
        cognition_id="cog_01",
        proposition="高标维持强势，且无极端恐慌低开",
        premise_evidence=["昨日连板梯队完整"],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[exp_a],
        invalidation_assertions=[inv_a],
        hypothesis_hash="dummy_hash_01",
    )

    # 实际观测：虽然高标均值达到了 3.0 (> 2.0 符合预期)，但存在单只个股开在 -5.0 (< -4.0 触发证伪条件！)
    real_data = {
        "stocks": [
            {"code": "001", "board_height": 2, "open_pct_change": 11.0},
            {"code": "002", "board_height": 2, "open_pct_change": -5.0},
        ]
    }

    res = FalsificationEngine.adjudicate(hypo, real_data)
    # 严格检验：必须判定为 FALSIFIED，且 falsification_triggered 必须为 True
    assert res.outcome == HypothesisOutcome.FALSIFIED
    assert res.falsification_triggered is True
    assert "证伪断言 'inv_01' 触发" in res.details


def test_02_all_expected_passed_and_invalidation_untriggered():
    """验证 2: 预期断言全部满足且证伪断言未触发 -> 判定 CONFIRMED"""
    exp_a = _create_assertion("exp_01", MetricType.OPEN_PCT_CHANGE, OperatorType.GT, 2.0)
    inv_a = _create_assertion("inv_01", MetricType.OPEN_PCT_CHANGE, OperatorType.LT, -4.0, agg=AggregationType.MIN)

    hypo = MarketHypothesisDefinition(
        hypothesis_id="h_test_02",
        cognition_id="cog_01",
        proposition="高标整体高开",
        premise_evidence=["情绪高涨"],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[exp_a],
        invalidation_assertions=[inv_a],
        hypothesis_hash="dummy_hash_02",
    )

    # 实际观测：高标开盘均值为 4.0 (> 2.0)，最低为 1.0 (未达到 < -4.0 证伪条件)
    real_data = {
        "stocks": [
            {"code": "001", "board_height": 2, "open_pct_change": 7.0},
            {"code": "002", "board_height": 2, "open_pct_change": 1.0},
        ]
    }

    res = FalsificationEngine.adjudicate(hypo, real_data)
    assert res.outcome == HypothesisOutcome.CONFIRMED
    assert res.falsification_triggered is False
    assert len(res.expected_results) == 1
    assert res.expected_results[0].outcome.value == "PASSED"


def test_03_expected_assertion_failed_and_invalidation_untriggered():
    """验证 3: 证伪断言未触发，但预期断言未达到 -> 判定 UNCONFIRMED"""
    exp_a = _create_assertion("exp_01", MetricType.OPEN_PCT_CHANGE, OperatorType.GT, 3.0)
    inv_a = _create_assertion("inv_01", MetricType.OPEN_PCT_CHANGE, OperatorType.LT, -5.0, agg=AggregationType.MIN)

    hypo = MarketHypothesisDefinition(
        hypothesis_id="h_test_03",
        cognition_id="cog_01",
        proposition="预期大幅高开",
        premise_evidence=["超预期高开预判"],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[exp_a],
        invalidation_assertions=[inv_a],
        hypothesis_hash="dummy_hash_03",
    )

    # 实际观测：开盘均值仅为 1.0 (未达到 > 3.0)，但最低为 0.0 (未跌破 -5.0)
    real_data = {
        "stocks": [
            {"code": "001", "board_height": 2, "open_pct_change": 2.0},
            {"code": "002", "board_height": 2, "open_pct_change": 0.0},
        ]
    }

    res = FalsificationEngine.adjudicate(hypo, real_data)
    assert res.outcome == HypothesisOutcome.UNCONFIRMED
    assert res.falsification_triggered is False


def test_04_or_logic_in_expected_assertions():
    """验证 4: OR 逻辑组合：多个预期断言只要命中一个即 CONFIRMED"""
    exp_a1 = _create_assertion("exp_01", MetricType.OPEN_PCT_CHANGE, OperatorType.GT, 5.0)
    exp_a2 = _create_assertion("exp_02", MetricType.OPEN_PCT_CHANGE, OperatorType.GT, 1.0)

    hypo = MarketHypothesisDefinition(
        hypothesis_id="h_test_04",
        cognition_id="cog_01",
        proposition="多预期弹性支撑",
        premise_evidence=["题材轮动"],
        time_binding="auction_0925",
        assertion_logic="OR",
        expected_assertions=[exp_a1, exp_a2],
        invalidation_assertions=[],
        hypothesis_hash="dummy_hash_04",
    )

    # 实际均值为 2.0 (未达到 > 5.0，但达到了 > 1.0)
    real_data = {
        "stocks": [
            {"code": "001", "board_height": 2, "open_pct_change": 2.0},
        ]
    }

    res = FalsificationEngine.adjudicate(hypo, real_data)
    assert res.outcome == HypothesisOutcome.CONFIRMED


def test_05_missing_data_defense_inconclusive():
    """验证 5: 真实数据切片异常或缺失时，严禁假零填充，判定 INCONCLUSIVE"""
    exp_a = _create_assertion("exp_01", MetricType.OPEN_PCT_CHANGE, OperatorType.GT, 0.0)

    hypo = MarketHypothesisDefinition(
        hypothesis_id="h_test_05",
        cognition_id="cog_01",
        proposition="缺数防御验证",
        premise_evidence=["证据"],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[exp_a],
        invalidation_assertions=[],
        hypothesis_hash="dummy_hash_05",
    )

    # 观测数据标记为 TIMEOUT
    timeout_data = {"status": "TIMEOUT", "stocks": []}
    res = FalsificationEngine.adjudicate(hypo, timeout_data)

    assert res.outcome == HypothesisOutcome.INCONCLUSIVE
    assert "[INCONCLUSIVE]" in res.details


def test_06_invalidation_inconclusive_prevents_false_confirmation():
    """验证 6: 若证伪断言因缺数导致未决，即使预期断言满足，也绝对不能冒然判定 CONFIRMED"""
    # 证伪断言：针对 4板及以上高标最低开盘 < -2.0
    # 但实际数据中没有任何 4板标的，导致数值聚合无法计算 (INCONCLUSIVE)
    inv_a = _create_assertion("inv_high", MetricType.OPEN_PCT_CHANGE, OperatorType.LT, -2.0, height_filter=4)
    exp_a = _create_assertion("exp_low", MetricType.OPEN_PCT_CHANGE, OperatorType.GT, 1.0, height_filter=2)

    hypo = MarketHypothesisDefinition(
        hypothesis_id="h_test_06",
        cognition_id="cog_01",
        proposition="高标安全防线",
        premise_evidence=["梯队"],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[exp_a],
        invalidation_assertions=[inv_a],
        hypothesis_hash="dummy_hash_06",
    )

    # 仅包含 2 板股票，无 4 板股票
    real_data = {
        "stocks": [
            {"code": "001", "board_height": 2, "open_pct_change": 3.0},
        ]
    }

    res = FalsificationEngine.adjudicate(hypo, real_data)
    # 因为证伪条件无法被有效检验（缺数/空集），不能给出完全确认
    assert res.outcome == HypothesisOutcome.INCONCLUSIVE
    assert "证伪断言 inv_high 缺数" in res.details
