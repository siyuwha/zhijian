"""
Phase 3A.2: Intraday Drift Comparator Gates (盘中动态波普尔证伪判定器门禁)
========================================================================
测试门禁规范：
1. GATE-3A2-01: 空间标杆炸板(Broken Limit)一票否决 CRITICAL_KILL 门禁
2. GATE-3A2-02: 空间标杆深水走弱一票否决门禁
3. GATE-3A2-03: 量能断崖萎缩与中度偏离预警门禁
4. GATE-3A2-04: 主线龙头集体翻绿倒戈门禁
5. GATE-3A2-05: 市场广度恶化与高炸板率预警门禁
6. GATE-3A2-06: 假说完全吻合 NORMAL 状态与防守边界门禁
7. GATE-3A2-07: 先质检再断言 INCONCLUSIVE 绝对优先级门禁
8. GATE-3A2-08: 四维时间因果时序倒置硬性拒止门禁
9. GATE-3A2-09: JCS 数字指纹 10x 恒等性与雪崩抗篡改门禁
"""

import pytest
from decimal import Decimal

from backend.app.schemas.canonical_intraday import (
    IntradayStageEnum,
    CanonicalIntradaySnapshot,
    StockIntradayQuote,
    CanonicalIntradayIndexQuote,
)
from backend.app.schemas.popper_verdict import (
    PopperianHypothesisRecord,
    AssertionItemVerdict,
    AssertionSeverityEnum,
)
from backend.app.schemas.intraday_drift_verdict import (
    DriftStateEnum,
    DriftInconclusiveReasonEnum,
    DriftEventCategoryEnum,
    IntradayDriftVerdict,
)
from backend.app.services.intraday_drift_comparator import (
    IntradayDriftComparator,
    CausalTemporalViolationError,
    DEFAULT_INTRADAY_THRESHOLDS,
)
from backend.app.schemas.canonical_market import (
    ProvenanceEnvelope,
    TruthSource,
    DataQualityGrade,
)
from backend.app.cognition.jcs import hash_jcs


def hamming_distance(hex1: str, hex2: str) -> int:
    val1 = int(hex1, 16)
    val2 = int(hex2, 16)
    xor_val = val1 ^ val2
    return bin(xor_val).count("1")


def make_test_hypothesis() -> PopperianHypothesisRecord:
    raw_dict = {
        "hypothesis_id": "HYPO-2026-10-08-TEST-001",
        "registered_at": "2026-10-08T18:00:00+08:00",
        "base_trade_date": "2026-10-08",
        "target_trade_date": "2026-10-09",
        "bound_briefing_trace_id": "TRACE-BRIEFING-1008",
        "bound_briefing_fingerprint": "a" * 64,
        "bound_snapshot_fingerprint": "b" * 64,
        "expected_market_state": "主升加速期",
        "expected_turnover_ratio_min": Decimal("8.00"),
        "expected_turnover_ratio_max": Decimal("15.00"),
        "space_leader_code": "600825",
        "space_leader_name": "新华传媒",
        "space_leader_falsification_threshold": Decimal("-3.00"),
        "mainline_leader_codes": ["600241", "603200"],
        "required_observation_symbols": ["600825", "600241", "603200"],
    }
    fp = hash_jcs({k: str(v) if isinstance(v, Decimal) else v for k, v in raw_dict.items()})
    return PopperianHypothesisRecord(**raw_dict, hypothesis_fingerprint=fp)


def make_test_intraday_snapshot(
    space_price: Decimal = Decimal("11.00"),
    space_pct: Decimal = Decimal("10.00"),
    space_broken: bool = False,
    pace_ratio: Decimal = Decimal("100.00"),
    ml_pct1: Decimal = Decimal("5.00"),
    ml_pct2: Decimal = Decimal("3.00"),
    broken_ratio: Decimal = Decimal("15.00"),
    limit_down: int = 1,
    is_trading: bool = True,
    stage: IntradayStageEnum = IntradayStageEnum.STAGE_2_MORNING,
    data_quality: DataQualityGrade = DataQualityGrade.FULL,
    obs_time: str = "2026-10-09T10:30:00+08:00",
) -> CanonicalIntradaySnapshot:
    env = ProvenanceEnvelope(
        source=TruthSource.INTERNAL_CANONICAL_AGGREGATE,
        observed_time=obs_time,
        quality=data_quality,
        is_degraded=(data_quality != DataQualityGrade.FULL),
        degradation_reason=None,
    )
    quotes = [
        StockIntradayQuote(
            code="600241",
            name="时代万恒",
            canonical_symbol="600241.SH",
            yesterday_close=Decimal("10.00"),
            open_price=Decimal("10.50"),
            current_price=Decimal("10.50"),
            high_price=Decimal("10.80"),
            low_price=Decimal("10.20"),
            pct_change=ml_pct1,
            turnover_wan=Decimal("30000.00"),
            volume_wan=Decimal("2800.00"),
            is_limit_up=(ml_pct1 >= Decimal("9.80")),
            is_broken_limit=False,
            is_limit_down=False,
            is_space_leader=False,
            is_mainline_leader=True,
            bound_mainline_name="固态电池",
        ),
        StockIntradayQuote(
            code="600825",
            name="新华传媒",
            canonical_symbol="600825.SH",
            yesterday_close=Decimal("10.00"),
            open_price=Decimal("10.80"),
            current_price=space_price,
            high_price=Decimal("11.00"),
            low_price=Decimal("10.00"),
            pct_change=space_pct,
            turnover_wan=Decimal("50000.00"),
            volume_wan=Decimal("4500.00"),
            is_limit_up=(space_pct >= Decimal("9.80")),
            is_broken_limit=space_broken,
            is_limit_down=(space_pct <= Decimal("-9.80")),
            is_space_leader=True,
            is_mainline_leader=False,
            bound_mainline_name=None,
        ),
        StockIntradayQuote(
            code="603200",
            name="上海洗霸",
            canonical_symbol="603200.SH",
            yesterday_close=Decimal("20.00"),
            open_price=Decimal("20.50"),
            current_price=Decimal("20.60"),
            high_price=Decimal("21.00"),
            low_price=Decimal("20.10"),
            pct_change=ml_pct2,
            turnover_wan=Decimal("40000.00"),
            volume_wan=Decimal("1900.00"),
            is_limit_up=(ml_pct2 >= Decimal("9.80")),
            is_broken_limit=False,
            is_limit_down=False,
            is_space_leader=False,
            is_mainline_leader=True,
            bound_mainline_name="证券",
        ),
    ]
    raw_dict = {
        "trade_date": "2026-10-09",
        "snapshot_time": "10:30:00",
        "stage": stage.value,
        "elapsed_trading_minutes": 60,
        "sh_accumulated_turnover_yi": "2000.00",
        "sz_accumulated_turnover_yi": "2800.00",
        "total_accumulated_turnover_yi": "4800.00",
        "prev_total_turnover_yi": "10000.00",
        "projected_turnover_yi": "10000.00",
        "turnover_pace_ratio_pct": str(pace_ratio),
        "indices": [],
        "leader_quotes": [
            {
                "code": q.code,
                "name": q.name,
                "canonical_symbol": q.canonical_symbol,
                "yesterday_close": str(q.yesterday_close),
                "open_price": str(q.open_price),
                "current_price": str(q.current_price),
                "high_price": str(q.high_price),
                "low_price": str(q.low_price),
                "pct_change": str(q.pct_change),
                "turnover_wan": str(q.turnover_wan),
                "volume_wan": str(q.volume_wan),
                "is_limit_up": q.is_limit_up,
                "is_broken_limit": q.is_broken_limit,
                "is_limit_down": q.is_limit_down,
                "is_space_leader": q.is_space_leader,
                "is_mainline_leader": q.is_mainline_leader,
                "bound_mainline_name": q.bound_mainline_name,
            }
            for q in quotes
        ],
        "up_count": 3200,
        "down_count": 1500,
        "flat_count": 300,
        "limit_up_count": 50,
        "limit_down_count": limit_down,
        "broken_limit_count": 10,
        "broken_limit_ratio_pct": str(broken_ratio),
        "prev_trade_date": "2026-10-08",
        "bound_snapshot_trace_id": "TRACE-1008-1009-INTRADAY",
        "bound_snapshot_fingerprint": "c" * 64,
        "bound_auction_trace_id": "TRACE-1008-1009-AUCTION",
        "bound_auction_fingerprint": "d" * 64,
        "is_trading_day": is_trading,
        "data_quality": data_quality.value,
        "envelope": env.model_dump(mode="json"),
    }
    fp = hash_jcs(raw_dict)
    return CanonicalIntradaySnapshot(
        trade_date="2026-10-09",
        snapshot_time="10:30:00",
        stage=stage,
        elapsed_trading_minutes=60,
        sh_accumulated_turnover_yi=Decimal("2000.00"),
        sz_accumulated_turnover_yi=Decimal("2800.00"),
        total_accumulated_turnover_yi=Decimal("4800.00"),
        prev_total_turnover_yi=Decimal("10000.00"),
        projected_turnover_yi=Decimal("10000.00"),
        turnover_pace_ratio_pct=pace_ratio,
        indices=[],
        leader_quotes=quotes,
        up_count=3200,
        down_count=1500,
        flat_count=300,
        limit_up_count=50,
        limit_down_count=limit_down,
        broken_limit_count=10,
        broken_limit_ratio_pct=broken_ratio,
        prev_trade_date="2026-10-08",
        bound_snapshot_trace_id="TRACE-1008-1009-INTRADAY",
        bound_snapshot_fingerprint="c" * 64,
        bound_auction_trace_id="TRACE-1008-1009-AUCTION",
        bound_auction_fingerprint="d" * 64,
        is_trading_day=is_trading,
        data_quality=data_quality,
        envelope=env,
        snapshot_fingerprint=fp,
    )


def test_gate_3a2_01_space_leader_broken_limit_critical_kill():
    """GATE-3A2-01: 空间标杆炸板(Broken Limit)一票否决 CRITICAL_KILL 门禁"""
    comparator = IntradayDriftComparator()
    hypo = make_test_hypothesis()
    snap = make_test_intraday_snapshot(
        space_price=Decimal("10.20"),
        space_pct=Decimal("2.00"),
        space_broken=True,  # 空间板炸板
    )

    verdict = comparator.evaluate_drift(hypo, snap, "2026-10-09T10:30:05+08:00")
    assert verdict.overall_drift_state == DriftStateEnum.CRITICAL_BREACH
    assert DriftEventCategoryEnum.SPACE_LEADER_COLLAPSE in verdict.detected_drift_events
    assert any("杜绝追高" in b for b in verdict.preservation_boundaries)


def test_gate_3a2_02_space_leader_deep_drop_critical_kill():
    """GATE-3A2-02: 空间标杆深水走弱一票否决门禁"""
    comparator = IntradayDriftComparator()
    hypo = make_test_hypothesis()
    snap = make_test_intraday_snapshot(
        space_price=Decimal("9.60"),
        space_pct=Decimal("-4.00"),  # 跌破 -3.00%
        space_broken=False,
    )

    verdict = comparator.evaluate_drift(hypo, snap, "2026-10-09T10:30:05+08:00")
    assert verdict.overall_drift_state == DriftStateEnum.CRITICAL_BREACH
    assert DriftEventCategoryEnum.SPACE_LEADER_COLLAPSE in verdict.detected_drift_events


def test_gate_3a2_03_liquidity_flash_dry_and_warning():
    """GATE-3A2-03: 量能断崖萎缩与中度偏离预警门禁"""
    comparator = IntradayDriftComparator()
    hypo = make_test_hypothesis()

    # 1. 中度偏离预警 (pace_ratio = 75.00% < 80%)
    snap_warn = make_test_intraday_snapshot(pace_ratio=Decimal("75.00"))
    v_warn = comparator.evaluate_drift(hypo, snap_warn, "2026-10-09T10:30:05+08:00")
    assert v_warn.overall_drift_state == DriftStateEnum.DRIFT_WARNING

    # 2. 断崖萎缩 (pace_ratio = 55.00% < 60%)
    snap_dry = make_test_intraday_snapshot(pace_ratio=Decimal("55.00"))
    v_dry = comparator.evaluate_drift(hypo, snap_dry, "2026-10-09T10:30:05+08:00")
    assert v_dry.overall_drift_state == DriftStateEnum.DRIFT_WARNING
    assert DriftEventCategoryEnum.LIQUIDITY_FLASH_DRY in v_dry.detected_drift_events


def test_gate_3a2_04_mainline_total_reversal_divergence():
    """GATE-3A2-04: 主线龙头集体翻绿倒戈门禁"""
    comparator = IntradayDriftComparator()
    hypo = make_test_hypothesis()

    # 主线全部暴跌破位 (< -4.00%)
    snap_rev = make_test_intraday_snapshot(
        ml_pct1=Decimal("-4.50"),
        ml_pct2=Decimal("-5.20"),
    )
    v_rev = comparator.evaluate_drift(hypo, snap_rev, "2026-10-09T10:30:05+08:00")
    assert v_rev.overall_drift_state == DriftStateEnum.DRIFT_WARNING
    assert DriftEventCategoryEnum.MAINLINE_TOTAL_REVERSAL in v_rev.detected_drift_events


def test_gate_3a2_05_breadth_panic_broken_limit_ratio():
    """GATE-3A2-05: 市场广度恶化与高炸板率预警门禁"""
    comparator = IntradayDriftComparator()
    hypo = make_test_hypothesis()

    # 炸板率达 42% (超 35%)
    snap_panic = make_test_intraday_snapshot(broken_ratio=Decimal("42.00"))
    v_panic = comparator.evaluate_drift(hypo, snap_panic, "2026-10-09T10:30:05+08:00")
    assert v_panic.overall_drift_state == DriftStateEnum.DRIFT_WARNING
    assert DriftEventCategoryEnum.BREADTH_PANIC_DIVERGENCE in v_panic.detected_drift_events


def test_gate_3a2_06_fully_normal_scenario():
    """GATE-3A2-06: 假说完全吻合 NORMAL 状态与防守边界门禁"""
    comparator = IntradayDriftComparator()
    hypo = make_test_hypothesis()
    snap_norm = make_test_intraday_snapshot()  # 默认空间板封死，量能100%，主线大涨

    v_norm = comparator.evaluate_drift(hypo, snap_norm, "2026-10-09T10:30:05+08:00")
    assert v_norm.overall_drift_state == DriftStateEnum.NORMAL
    assert len(v_norm.detected_drift_events) == 0
    assert any("吻合假说" in b for b in v_norm.preservation_boundaries)


def test_gate_3a2_07_precondition_inconclusive_priority():
    """GATE-3A2-07: 先质检再断言 INCONCLUSIVE 绝对优先级门禁"""
    comparator = IntradayDriftComparator()
    hypo = make_test_hypothesis()

    # 1. 非交易日
    snap_closed = make_test_intraday_snapshot(is_trading=False)
    v_closed = comparator.evaluate_drift(hypo, snap_closed, "2026-10-09T10:30:05+08:00")
    assert v_closed.overall_drift_state == DriftStateEnum.INCONCLUSIVE
    assert v_closed.inconclusive_reason == DriftInconclusiveReasonEnum.MARKET_CLOSED

    # 2. 数据品质降级
    snap_deg = make_test_intraday_snapshot(data_quality=DataQualityGrade.DEGRADED)
    v_deg = comparator.evaluate_drift(hypo, snap_deg, "2026-10-09T10:30:05+08:00")
    assert v_deg.overall_drift_state == DriftStateEnum.INCONCLUSIVE
    assert v_deg.inconclusive_reason == DriftInconclusiveReasonEnum.DATA_QUALITY_DEGRADED


def test_gate_3a2_08_temporal_causality_defense_422():
    """GATE-3A2-08: 四维时间因果时序倒置硬性拒止门禁"""
    comparator = IntradayDriftComparator()
    hypo = make_test_hypothesis()  # 登记时间 2026-10-08T18:00:00

    # 构造时序倒置快照：观测时间 2026-10-08T15:00:00 早于假说登记时间
    snap_invalid = make_test_intraday_snapshot(obs_time="2026-10-08T15:00:00+08:00")
    with pytest.raises(CausalTemporalViolationError):
        comparator.evaluate_drift(hypo, snap_invalid, "2026-10-09T10:30:05+08:00")


def test_gate_3a2_09_jcs_fingerprint_idempotence_and_tamper_avalanche():
    """GATE-3A2-09: JCS 数字指纹 10x 恒等性与雪崩抗篡改门禁"""
    comparator = IntradayDriftComparator()
    hypo = make_test_hypothesis()
    snap = make_test_intraday_snapshot()

    # 1. 10 次重复评估幂等性
    v1 = comparator.evaluate_drift(hypo, snap, "2026-10-09T10:30:05+08:00")
    for _ in range(9):
        v_rep = comparator.evaluate_drift(hypo, snap, "2026-10-09T10:30:05+08:00")
        assert v_rep.verdict_fingerprint == v1.verdict_fingerprint

    # 2. 篡改测试 (修改 1 字符标题)
    raw_tampered = {
        "verdict_id": v1.verdict_id,
        "trade_date": v1.trade_date,
        "evaluated_at": v1.evaluated_at,
        "stage": v1.stage.value,
        "elapsed_trading_minutes": v1.elapsed_trading_minutes,
        "trace_id": v1.trace_id,
        "hypothesis_id": v1.hypothesis_id,
        "hypothesis_fingerprint": v1.hypothesis_fingerprint,
        "intraday_snapshot_fingerprint": v1.intraday_snapshot_fingerprint,
        "rule_version": v1.rule_version,
        "threshold_config_hash": v1.threshold_config_hash,
        "overall_drift_state": v1.overall_drift_state.value,
        "inconclusive_reason": None,
        "verdict_headline": v1.verdict_headline + "!",  # 注入 1 字符
        "detected_drift_events": [e.value for e in v1.detected_drift_events],
        "assertion_results": [
            {
                "rule_id": a.rule_id,
                "rule_name": a.rule_name,
                "severity": a.severity.value,
                "target_entity": a.target_entity,
                "expected_condition": a.expected_condition,
                "actual_observation": a.actual_observation,
                "is_violated": a.is_violated,
                "deviation_analysis": a.deviation_analysis,
            }
            for a in v1.assertion_results
        ],
        "preservation_boundaries": v1.preservation_boundaries,
        "safety_audit_passed": True,
    }
    tampered_fp = hash_jcs(raw_tampered)
    h_dist = hamming_distance(v1.verdict_fingerprint, tampered_fp)
    flip_rate = h_dist / 256.0
    assert flip_rate >= 0.40, f"单字符篡改雪崩率不足: {flip_rate:.2%}"
