"""
Phase 2A Step 5 Assembly & Extreme Scenario Test Suite
涵盖 7 大极限场景 (CS-H01 ~ CS-H07) 与全链路双时点对撞闭环
上位依据:
- 《开发文档/45-Phase-2A-Step5-收窄AST解释执行器与事后证伪闭环实施规划.md》
- 《开发文档/43-Phase-2A-Step4与Step5职责边界澄清与架构裁决方案.md》
"""

import pytest
from typing import List

from app.cognition.hypothesis.contracts import (
    MarketHypothesisDefinition,
    HypothesisSetProjection,
    MetricAssertion,
    MetricType,
    UniverseType,
    OperatorType,
    AggregationType,
    HypothesisOutcome,
    FilterCondition,
    StructuredFilter,
)
from app.cognition.hypothesis.fingerprint import (
    compute_hypothesis_hash,
    compute_hypothesis_set_hash,
)
from app.cognition.hypothesis.evaluator import (
    AssertionEvaluator,
    AssertionSyntaxError,
)
from app.cognition.hypothesis.pipeline import (
    DualTimestampValidationPipeline,
    TimeContinuityViolationError,
    HypothesisTamperError,
)
from app.cognition.hypothesis.ledger import (
    AppendOnlyValidationLedger,
    CognitionValidationRecord,
    ValidationLedgerError,
)


def _build_helper_hypothesis(
    hypo_id: str,
    cognition_id: str,
    exp_assertions: List[MetricAssertion],
    inv_assertions: List[MetricAssertion],
    logic: str = "AND",
) -> MarketHypothesisDefinition:
    dummy = MarketHypothesisDefinition(
        hypothesis_id=hypo_id,
        cognition_id=cognition_id,
        proposition="测试假说命题",
        premise_evidence=["证据1", "证据2"],
        time_binding="auction_0925",
        assertion_logic=logic,
        expected_assertions=exp_assertions,
        invalidation_assertions=inv_assertions,
        hypothesis_hash="",
    )
    h_hash = compute_hypothesis_hash(dummy)
    return MarketHypothesisDefinition(
        hypothesis_id=hypo_id,
        cognition_id=cognition_id,
        proposition="测试假说命题",
        premise_evidence=["证据1", "证据2"],
        time_binding="auction_0925",
        assertion_logic=logic,
        expected_assertions=exp_assertions,
        invalidation_assertions=inv_assertions,
        hypothesis_hash=h_hash,
    )


def _build_helper_set(
    set_id: str,
    cognition_id: str,
    hypotheses: List[MarketHypothesisDefinition],
) -> HypothesisSetProjection:
    dummy_set = HypothesisSetProjection(
        set_id=set_id,
        cognition_id=cognition_id,
        hypotheses=hypotheses,
        hypothesis_set_hash="",
    )
    set_hash = compute_hypothesis_set_hash(dummy_set)
    return HypothesisSetProjection(
        set_id=set_id,
        cognition_id=cognition_id,
        hypotheses=hypotheses,
        hypothesis_set_hash=set_hash,
    )


def test_cs_h01_all_expected_met_confirmed():
    """CS-H01: 全量符合预期，证伪未触发 -> CONFIRMED 且入账成功"""
    c = FilterCondition(field="board_height", op=OperatorType.GTE, val=2)
    selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[c])
    exp_a = MetricAssertion(
        assertion_id="exp_01",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        aggregation=AggregationType.MEAN,
        operator=OperatorType.GT,
        target_value=2.0,
    )
    inv_a = MetricAssertion(
        assertion_id="inv_01",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        aggregation=AggregationType.MIN,
        operator=OperatorType.LT,
        target_value=-4.0,
    )

    hypo = _build_helper_hypothesis("hypo_01", "cog_1001", [exp_a], [inv_a])
    hypo_set = _build_helper_set("set_01", "cog_1001", [hypo])

    # 09:25 到达真实快照：均值 3.5 (> 2.0)，最低 0.0 (未达到 < -4.0)
    real_snapshot = {
        "status": "AVAILABLE",
        "stocks": [
            {"code": "001", "board_height": 3, "open_pct_change": 5.0},
            {"code": "002", "board_height": 2, "open_pct_change": 2.0},
        ],
    }

    records = DualTimestampValidationPipeline.validate_hypothesis_set(
        hypothesis_set=hypo_set,
        realization_snapshot=real_snapshot,
        realization_snapshot_id="snap_0925_001",
        decision_time="2026-10-01T09:15:00+08:00",
        realization_time="2026-10-01T09:25:00+08:00",
    )

    assert len(records) == 1
    rec = records[0]
    assert rec.outcome == HypothesisOutcome.CONFIRMED
    assert rec.falsification_triggered is False
    assert rec.validation_id == "val_hypo_01_snap_0925_001"
    assert rec.actual_metrics_summary["exp_01"] == 3.5

    # 验证只追加账本入账
    ledger = AppendOnlyValidationLedger()
    ledger.append(rec)
    assert ledger.count() == 1
    assert ledger.get(rec.validation_id) == rec


def test_cs_h02_falsification_first_priority():
    """CS-H02: 证伪断言触发 -> 绝对优先短路为 FALSIFIED"""
    c = FilterCondition(field="board_height", op=OperatorType.GTE, val=2)
    selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[c])
    exp_a = MetricAssertion(
        assertion_id="exp_01",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        aggregation=AggregationType.MEAN,
        operator=OperatorType.GT,
        target_value=1.0,
    )
    inv_a = MetricAssertion(
        assertion_id="inv_01",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        aggregation=AggregationType.MIN,
        operator=OperatorType.LT,
        target_value=-3.0,
    )

    hypo = _build_helper_hypothesis("hypo_02", "cog_1002", [exp_a], [inv_a])
    hypo_set = _build_helper_set("set_02", "cog_1002", [hypo])

    # 实际快照：均值 4.0 (> 1.0 满足预期)，但出现极端跌停 -5.0 (< -3.0 触发证伪！)
    real_snapshot = {
        "status": "AVAILABLE",
        "stocks": [
            {"code": "001", "board_height": 2, "open_pct_change": 13.0},
            {"code": "002", "board_height": 2, "open_pct_change": -5.0},
        ],
    }

    records = DualTimestampValidationPipeline.validate_hypothesis_set(
        hypothesis_set=hypo_set,
        realization_snapshot=real_snapshot,
        realization_snapshot_id="snap_0925_002",
        decision_time="2026-10-01T09:15:00+08:00",
        realization_time="2026-10-01T09:25:00+08:00",
    )

    assert len(records) == 1
    assert records[0].outcome == HypothesisOutcome.FALSIFIED
    assert records[0].falsification_triggered is True


def test_cs_h03_missing_data_defense_inconclusive():
    """CS-H03: 关键数据超时或缺失 -> INCONCLUSIVE，防假零填充"""
    c = FilterCondition(field="board_height", op=OperatorType.GTE, val=2)
    selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[c])
    exp_a = MetricAssertion(
        assertion_id="exp_01",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        aggregation=AggregationType.MEAN,
        operator=OperatorType.GT,
        target_value=0.0,
    )

    hypo = _build_helper_hypothesis("hypo_03", "cog_1003", [exp_a], [])
    hypo_set = _build_helper_set("set_03", "cog_1003", [hypo])

    # 数据源整体标记为 TIMEOUT
    real_snapshot = {"status": "TIMEOUT", "stocks": []}

    records = DualTimestampValidationPipeline.validate_hypothesis_set(
        hypothesis_set=hypo_set,
        realization_snapshot=real_snapshot,
        realization_snapshot_id="snap_0925_003",
        decision_time="2026-10-01T09:15:00+08:00",
        realization_time="2026-10-01T09:25:00+08:00",
    )

    assert len(records) == 1
    assert records[0].outcome == HypothesisOutcome.INCONCLUSIVE
    assert records[0].falsification_triggered is False


def test_cs_h04_empty_universe_handling():
    """CS-H04: 标的池过滤后为空 -> COUNT 为 0.0 vs 均值等指标判定为 INCONCLUSIVE"""
    c = FilterCondition(field="board_height", op=OperatorType.GTE, val=5)
    selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[c])

    # 1. 计数断言
    a_count = MetricAssertion(
        assertion_id="a_cnt",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        aggregation=AggregationType.COUNT,
        operator=OperatorType.EQ,
        target_value=0.0,
    )
    res_cnt = AssertionEvaluator.evaluate(a_count, {"stocks": []})
    assert res_cnt.outcome.value == "PASSED"
    assert res_cnt.actual_value == 0.0

    # 2. 均值断言
    a_mean = MetricAssertion(
        assertion_id="a_mean",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        aggregation=AggregationType.MEAN,
        operator=OperatorType.GT,
        target_value=0.0,
    )
    res_mean = AssertionEvaluator.evaluate(a_mean, {"stocks": []})
    assert res_mean.outcome.value == "INCONCLUSIVE"
    assert res_mean.is_missing is True


def test_cs_h05_boundary_precision_float_safety():
    """CS-H05: 浮点临界边界 1e-9 精度防抖动"""
    c = FilterCondition(field="board_height", op=OperatorType.EQ, val=2)
    selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[c])

    # 目标值 = -3.0，实际值 = -3.00000000001 (差值 1e-11 < 1e-9，浮点等价)
    mock_data = {"stocks": [{"code": "001", "board_height": 2, "open_pct_change": -3.00000000001}]}
    a_eq = MetricAssertion(
        assertion_id="a_eq",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        aggregation=AggregationType.MEAN,
        operator=OperatorType.EQ,
        target_value=-3.0,
    )
    res = AssertionEvaluator.evaluate(a_eq, mock_data)
    assert res.outcome.value == "PASSED"


def test_cs_h06_syntax_violation_and_injection_blocked():
    """CS-H06: 非法 SQL 或未授权字段注入被 AST 白名单彻底阻断"""
    with pytest.raises(AssertionSyntaxError, match="不在白名单中"):
        bad_cond = FilterCondition(field="drop_table_users", op=OperatorType.EQ, val=1)
        selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[bad_cond])
        bad_a = MetricAssertion(
            assertion_id="bad",
            selector=selector,
            metric=MetricType.OPEN_PCT_CHANGE.value,
            operator=OperatorType.GT,
            target_value=0.0,
        )
        AssertionEvaluator.evaluate(bad_a, {"stocks": []})


def test_cs_h07_c02_isolation_worm_and_reverse_audit():
    """CS-H07: C-02 不变量证明、WORM 覆写阻断、时序倒流拦截与全血缘反向审计"""
    c = FilterCondition(field="board_height", op=OperatorType.GTE, val=2)
    selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[c])
    exp_a = MetricAssertion(
        assertion_id="exp_01",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        operator=OperatorType.GT,
        target_value=1.0,
    )

    hypo = _build_helper_hypothesis("hypo_07", "cog_1007", [exp_a], [])
    hypo_set = _build_helper_set("set_07", "cog_1007", [hypo])
    original_set_hash = hypo_set.hypothesis_set_hash
    original_hypo_hash = hypo.hypothesis_hash

    real_snapshot = {
        "status": "AVAILABLE",
        "stocks": [{"code": "001", "board_height": 2, "open_pct_change": 3.0}],
    }

    # 1. 尝试四维时间倒流 (T_realization < T_decision) -> 必须被拦截抛出 TimeContinuityViolationError
    with pytest.raises(TimeContinuityViolationError, match="时序倒流违规"):
        DualTimestampValidationPipeline.validate_hypothesis_set(
            hypothesis_set=hypo_set,
            realization_snapshot=real_snapshot,
            realization_snapshot_id="snap_bad_time",
            decision_time="2026-10-01T09:30:00+08:00",
            realization_time="2026-10-01T09:15:00+08:00",
        )

    # 2. 尝试篡改假说定义哈希 -> 必须被拦截抛出 HypothesisTamperError
    tampered_set = HypothesisSetProjection(
        set_id="set_07",
        cognition_id="cog_1007",
        hypotheses=hypo_set.hypotheses,
        hypothesis_set_hash="fake_hash_attack",
    )
    with pytest.raises(HypothesisTamperError, match="HypothesisSet hash mismatch"):
        DualTimestampValidationPipeline.validate_hypothesis_set(
            hypothesis_set=tampered_set,
            realization_snapshot=real_snapshot,
            realization_snapshot_id="snap_tamper",
            decision_time="2026-10-01T09:15:00+08:00",
            realization_time="2026-10-01T09:25:00+08:00",
        )

    # 3. 正常执行验证
    records = DualTimestampValidationPipeline.validate_hypothesis_set(
        hypothesis_set=hypo_set,
        realization_snapshot=real_snapshot,
        realization_snapshot_id="snap_0925_007",
        decision_time="2026-10-01T09:15:00+08:00",
        realization_time="2026-10-01T09:25:00+08:00",
    )
    rec = records[0]

    # C-02 隔离证明：原假说定义哈希未发生任何改变
    assert hypo_set.hypothesis_set_hash == original_set_hash
    assert hypo.hypothesis_hash == original_hypo_hash

    # 全血缘反向审计：从验证记录可 100% 穿透回 parent cognition_record_id 与 hypothesis_hash
    assert rec.cognition_record_id == "cog_1007"
    assert rec.hypothesis_hash == original_hypo_hash
    assert rec.hypothesis_set_hash == original_set_hash
    assert rec.verification_snapshot_id == "snap_0925_007"

    # WORM 账本保护：首次写入成功，二次追加相同 validation_id 必须抛出 ValidationLedgerError
    ledger = AppendOnlyValidationLedger()
    ledger.append(rec)
    with pytest.raises(ValidationLedgerError, match="WORM Violation"):
        ledger.append(rec)
