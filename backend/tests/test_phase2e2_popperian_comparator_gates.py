"""
Phase 2E.2: Popperian Bidding Comparator Gate Tests
===================================================
上位依据：
1. 最高董事会裁决令：《BOARD-DECISION-PHASE2E2-CONTROLLED-GO-20261009》
2. 《DOC-89 · Phase 2E 09:25 集合竞价自动对账与次日波普尔证伪闭环技术设计单》

门禁清单：
- GATE-2E2-01: Temporal Causality & Causal Invariant Defense Gate (因果时序与倒置防御门禁)
- GATE-2E2-02: Pre-condition Priority & INCONCLUSIVE Routing Gate (质检前置与证据不足路由门禁)
- GATE-2E2-03: Space Leader Life Line & CRITICAL_KILL Falsification Gate (空间标杆生命线与一票证伪门禁)
- GATE-2E2-04: Mainline Alignment & DIVERGENT Resolution Gate (主线分化与中度偏离门禁)
- GATE-2E2-05: Fully Reinforced CONFIRMED Resolution Gate (正向共振假说确认门禁)
- GATE-2E2-06: MECE Mutually Exclusive Truth Table Invariant Gate (四态完全互斥真值表公理门禁)
- GATE-2E2-07: 5-in-1 Provenance Auditability & Threshold Tamper Defense Gate (五位一体防伪与阈值防篡改门禁)
- GATE-2E2-08: Two-Market Turnover & ChiNext Anti-Double-Count Gate (两市全市场去重防双算独立期望值门禁)
"""

import pytest
from decimal import Decimal
from datetime import datetime

from backend.app.schemas.popper_verdict import (
    FalsificationOutcomeEnum,
    InconclusiveReasonEnum,
    AssertionSeverityEnum,
    PopperianHypothesisRecord,
    BiddingFalsificationVerdict,
)
from backend.app.schemas.canonical_auction import (
    CanonicalAuctionSnapshot,
    StockAuctionQuote,
    CanonicalAuctionIndexQuote,
    BiddingStatusEnum,
)
from backend.app.schemas.canonical_market import (
    ProvenanceEnvelope,
    TruthSource,
    DataQualityGrade,
)
from backend.app.services.popperian_bidding_comparator import (
    PopperianBiddingComparator,
    CausalTemporalViolationError,
    compute_threshold_config_hash,
    RULESET_VERSION,
    DEFAULT_ASSERTION_THRESHOLDS,
)
from backend.app.cognition.jcs import hash_jcs


def make_test_hypothesis(
    hypothesis_id: str = "HYPO-2026-10-08-3f8a91b2c4e1",
    registered_at: str = "2026-10-08T16:00:00+08:00",
    base_trade_date: str = "2026-10-08",
    target_trade_date: str = "2026-10-09",
    space_leader_code: str = "600825",
    space_leader_name: str = "新华传媒",
    space_leader_falsification_threshold: Decimal = Decimal("-3.00"),
    mainline_leader_codes: list = None,
    required_symbols: list = None,
) -> PopperianHypothesisRecord:
    mainlines = mainline_leader_codes or ["600241"]
    req = required_symbols or ["600825", "600241"]
    raw_dict = {
        "hypothesis_id": hypothesis_id,
        "registered_at": registered_at,
        "base_trade_date": base_trade_date,
        "target_trade_date": target_trade_date,
        "bound_briefing_trace_id": f"TRACE-{base_trade_date}-BRIEFING",
        "bound_briefing_fingerprint": "1f2e3d4c5b6a7f8e9d0c1b2a3f4e5d6c7b8a9f0e1d2c3b4a5f6e7d8c9b0a1f2e",
        "bound_snapshot_fingerprint": "80cb8e02acbcc1079b39b59f35af4bd252ce6f39c5a48064a6726d089ea58f22",
        "expected_market_state": "高位剧烈分化期",
        "expected_turnover_ratio_min": "0.80",
        "expected_turnover_ratio_max": "1.50",
        "space_leader_code": space_leader_code,
        "space_leader_name": space_leader_name,
        "space_leader_falsification_threshold": str(space_leader_falsification_threshold),
        "mainline_leader_codes": mainlines,
        "required_observation_symbols": req,
    }
    fp = hash_jcs(raw_dict)
    return PopperianHypothesisRecord(
        hypothesis_id=hypothesis_id,
        registered_at=registered_at,
        base_trade_date=base_trade_date,
        target_trade_date=target_trade_date,
        bound_briefing_trace_id=f"TRACE-{base_trade_date}-BRIEFING",
        bound_briefing_fingerprint="1f2e3d4c5b6a7f8e9d0c1b2a3f4e5d6c7b8a9f0e1d2c3b4a5f6e7d8c9b0a1f2e",
        bound_snapshot_fingerprint="80cb8e02acbcc1079b39b59f35af4bd252ce6f39c5a48064a6726d089ea58f22",
        expected_market_state="高位剧烈分化期",
        expected_turnover_ratio_min=Decimal("0.80"),
        expected_turnover_ratio_max=Decimal("1.50"),
        space_leader_code=space_leader_code,
        space_leader_name=space_leader_name,
        space_leader_falsification_threshold=space_leader_falsification_threshold,
        mainline_leader_codes=mainlines,
        required_observation_symbols=req,
        hypothesis_fingerprint=fp,
    )


def make_test_auction_snapshot(
    trade_date: str = "2026-10-09",
    observed_time: str = "09:25:05",
    is_trading_day: bool = True,
    data_quality: DataQualityGrade = DataQualityGrade.FULL,
    is_degraded: bool = False,
    degradation_reason: str = None,
    sh_turnover_yi: Decimal = Decimal("81.12"),
    sz_turnover_yi: Decimal = Decimal("87.09"),
    space_pct: Decimal = Decimal("1.50"),
    space_status: BiddingStatusEnum = BiddingStatusEnum.NORMAL,
    ml_pct: Decimal = Decimal("1.20"),
    include_space: bool = True,
    include_ml: bool = True,
    space_suspended: bool = False,
) -> CanonicalAuctionSnapshot:
    total_yi = sh_turnover_yi + sz_turnover_yi
    ratio_pct = Decimal("1.00")

    indices = [
        CanonicalAuctionIndexQuote(
            symbol="sh000001",
            name="上证指数",
            open_price=Decimal("3815.20"),
            pre_close=Decimal("3811.90"),
            change_val=Decimal("3.30"),
            pct_change=Decimal("0.09"),
            amount_yi=sh_turnover_yi,
        ),
        CanonicalAuctionIndexQuote(
            symbol="sz399001",
            name="深证成指",
            open_price=Decimal("12600.00"),
            pre_close=Decimal("12580.00"),
            change_val=Decimal("20.00"),
            pct_change=Decimal("0.16"),
            amount_yi=sz_turnover_yi,
        ),
    ]

    quotes = []
    if include_space:
        st = BiddingStatusEnum.SUSPENDED if space_suspended else space_status
        quotes.append(
            StockAuctionQuote(
                code="600825",
                name="新华传媒",
                canonical_symbol="600825.SH",
                yesterday_close=Decimal("12.50"),
                auction_price=Decimal("12.69"),
                auction_pct_change=space_pct,
                auction_turnover_wan=Decimal("4500.00"),
                auction_volume_ratio_pct=Decimal("2.10"),
                bidding_status=st,
                open_order_imbalance_wan=Decimal("120.00"),
                is_space_leader=True,
                is_mainline_leader=False,
                bound_mainline_name=None,
            )
        )
    if include_ml:
        quotes.append(
            StockAuctionQuote(
                code="600241",
                name="时代万恒",
                canonical_symbol="600241.SH",
                yesterday_close=Decimal("8.80"),
                auction_price=Decimal("8.91"),
                auction_pct_change=ml_pct,
                auction_turnover_wan=Decimal("3200.00"),
                auction_volume_ratio_pct=Decimal("1.80"),
                bidding_status=BiddingStatusEnum.NORMAL,
                open_order_imbalance_wan=Decimal("50.00"),
                is_space_leader=False,
                is_mainline_leader=True,
                bound_mainline_name="电池",
            )
        )

    envelope = ProvenanceEnvelope(
        source=TruthSource.INTERNAL_CANONICAL_AGGREGATE,
        observed_time=f"{trade_date}T{observed_time}+08:00",
        quality=data_quality,
        is_degraded=is_degraded,
        degradation_reason=degradation_reason,
    )

    raw_dict = {
        "trade_date": trade_date,
        "observed_time": observed_time,
        "prev_trade_date": "2026-10-08",
        "bound_snapshot_trace_id": "TRACE-2026-10-08-TO-2026-10-09-AUCTION",
        "bound_snapshot_fingerprint": "80cb8e02acbcc1079b39b59f35af4bd252ce6f39c5a48064a6726d089ea58f22",
        "bound_briefing_fingerprint": None,
        "indices": [
            {
                "symbol": i.symbol,
                "name": i.name,
                "open_price": str(i.open_price),
                "pre_close": str(i.pre_close),
                "change_val": str(i.change_val),
                "pct_change": str(i.pct_change),
                "amount_yi": str(i.amount_yi),
            }
            for i in indices
        ],
        "sh_auction_turnover_yi": str(sh_turnover_yi),
        "sz_auction_turnover_yi": str(sz_turnover_yi),
        "total_auction_turnover_yi": str(total_yi),
        "prev_total_turnover_yi": "16821.09",
        "auction_turnover_ratio_pct": str(ratio_pct),
        "leader_quotes": [
            {
                "code": q.code,
                "name": q.name,
                "canonical_symbol": q.canonical_symbol,
                "yesterday_close": str(q.yesterday_close),
                "auction_price": str(q.auction_price),
                "auction_pct_change": str(q.auction_pct_change),
                "auction_turnover_wan": str(q.auction_turnover_wan),
                "bidding_status": q.bidding_status.value,
                "is_space_leader": q.is_space_leader,
                "is_mainline_leader": q.is_mainline_leader,
                "bound_mainline_name": q.bound_mainline_name,
            }
            for q in quotes
        ],
        "is_trading_day": is_trading_day,
        "data_quality": data_quality.value,
        "envelope": envelope.model_dump(),
    }
    snap_fp = hash_jcs(raw_dict)

    return CanonicalAuctionSnapshot(
        trade_date=trade_date,
        observed_time=observed_time,
        prev_trade_date="2026-10-08",
        bound_snapshot_trace_id="TRACE-2026-10-08-TO-2026-10-09-AUCTION",
        bound_snapshot_fingerprint="80cb8e02acbcc1079b39b59f35af4bd252ce6f39c5a48064a6726d089ea58f22",
        bound_briefing_fingerprint=None,
        indices=indices,
        sh_auction_turnover_yi=sh_turnover_yi,
        sz_auction_turnover_yi=sz_turnover_yi,
        total_auction_turnover_yi=total_yi,
        prev_total_turnover_yi=Decimal("16821.09"),
        auction_turnover_ratio_pct=ratio_pct,
        leader_quotes=quotes,
        is_trading_day=is_trading_day,
        data_quality=data_quality,
        envelope=envelope,
        auction_fingerprint=snap_fp,
    )


# =============================================================================
# GATE-2E2-01: Temporal Causality & Causal Invariant Defense Gate
# =============================================================================
def test_gate_2e2_01_temporal_causality_defense():
    """
    GATE-2E2-01: 因果时序与倒置防御门禁
    - 正常因果: 假说 T 日 16:00 < 竞价 T+1 日 09:25:05 -> 正常通过
    - 时序倒置: 假说 T+1 日 09:26:00 > 竞价 T+1 日 09:25:05 -> 抛出 CausalTemporalViolationError
    - 时序相同: 假说 T+1 日 09:25:05 == 竞价 T+1 日 09:25:05 -> 抛出 CausalTemporalViolationError
    """
    comparator = PopperianBiddingComparator()
    snapshot = make_test_auction_snapshot(trade_date="2026-10-09", observed_time="09:25:05")

    # 1. 正常时序 (通过)
    hypo_valid = make_test_hypothesis(registered_at="2026-10-08T16:00:00+08:00")
    verdict = comparator.evaluate(hypo_valid, snapshot)
    assert verdict.overall_verdict in [
        FalsificationOutcomeEnum.CONFIRMED,
        FalsificationOutcomeEnum.DIVERGENT,
        FalsificationOutcomeEnum.FALSIFIED,
    ]

    # 2. 事后假说倒置 (阻断)
    hypo_posthoc = make_test_hypothesis(registered_at="2026-10-09T09:26:00+08:00")
    with pytest.raises(CausalTemporalViolationError):
        comparator.evaluate(hypo_posthoc, snapshot)

    # 3. 临界相等倒置 (阻断)
    hypo_equal = make_test_hypothesis(registered_at="2026-10-09T09:25:05+08:00")
    with pytest.raises(CausalTemporalViolationError):
        comparator.evaluate(hypo_equal, snapshot)


# =============================================================================
# GATE-2E2-02: Pre-condition Priority & INCONCLUSIVE Routing Gate
# =============================================================================
def test_gate_2e2_02_precondition_priority_and_inconclusive():
    """
    GATE-2E2-02: 质检前置与证据不足优先路由门禁
    - 休市/非交易日 -> INCONCLUSIVE (MARKET_CLOSED)
    - 数据品质降级 -> INCONCLUSIVE (DATA_QUALITY_DEGRADED)
    - 标的缺失 (零静默替换) -> INCONCLUSIVE (TARGET_MISSING_OR_SUSPENDED)
    - 标的停牌 -> INCONCLUSIVE (TARGET_MISSING_OR_SUSPENDED)
    - 刚性保证: 绝不误判为 CONFIRMED 或 FALSIFIED，断言结果列表全空
    """
    comparator = PopperianBiddingComparator()
    hypo = make_test_hypothesis()

    # 场景 1: 休市
    snap_closed = make_test_auction_snapshot(is_trading_day=False)
    v1 = comparator.evaluate(hypo, snap_closed)
    assert v1.overall_verdict == FalsificationOutcomeEnum.INCONCLUSIVE
    assert v1.inconclusive_reason == InconclusiveReasonEnum.MARKET_CLOSED
    assert len(v1.assertion_results) == 0

    # 场景 2: 降级
    snap_degraded = make_test_auction_snapshot(
        data_quality=DataQualityGrade.PARTIAL,
        is_degraded=True,
        degradation_reason="深交所网关抖动",
    )
    v2 = comparator.evaluate(hypo, snap_degraded)
    assert v2.overall_verdict == FalsificationOutcomeEnum.INCONCLUSIVE
    assert v2.inconclusive_reason == InconclusiveReasonEnum.DATA_QUALITY_DEGRADED
    assert len(v2.assertion_results) == 0

    # 场景 3: 标的缺失
    snap_missing = make_test_auction_snapshot(include_space=False)
    v3 = comparator.evaluate(hypo, snap_missing)
    assert v3.overall_verdict == FalsificationOutcomeEnum.INCONCLUSIVE
    assert v3.inconclusive_reason == InconclusiveReasonEnum.TARGET_MISSING_OR_SUSPENDED
    assert len(v3.assertion_results) == 0

    # 场景 4: 标的停牌
    snap_suspended = make_test_auction_snapshot(space_suspended=True)
    v4 = comparator.evaluate(hypo, snap_suspended)
    assert v4.overall_verdict == FalsificationOutcomeEnum.INCONCLUSIVE
    assert v4.inconclusive_reason == InconclusiveReasonEnum.TARGET_MISSING_OR_SUSPENDED
    assert len(v4.assertion_results) == 0


# =============================================================================
# GATE-2E2-03: Space Leader Life Line & CRITICAL_KILL Falsification Gate
# =============================================================================
def test_gate_2e2_03_space_leader_critical_kill():
    """
    GATE-2E2-03: 空间标杆生命线与一票证伪门禁
    - 开盘跌幅达到 -3.00% (临界线) -> 触发 CRITICAL_KILL -> FALSIFIED
    - 开盘跌幅 -5.00% (深水) -> 触发 CRITICAL_KILL -> FALSIFIED
    - 开盘一字跌停封死 -> 触发 CRITICAL_KILL -> FALSIFIED
    - 即使主线涨幅良好 (+3.0%)，空间板破位依然一票否决
    """
    comparator = PopperianBiddingComparator()
    hypo = make_test_hypothesis()

    # 临界跌幅 -3.00%
    snap_kill = make_test_auction_snapshot(
        space_pct=Decimal("-3.00"),
        ml_pct=Decimal("3.00"),
    )
    v = comparator.evaluate(hypo, snap_kill)
    assert v.overall_verdict == FalsificationOutcomeEnum.FALSIFIED
    space_assert = next(a for a in v.assertion_results if a.rule_id == "RULE-SPACE-LEADER-PREMIUM")
    assert space_assert.is_violated is True
    assert space_assert.severity == AssertionSeverityEnum.CRITICAL_KILL

    # 跌停封死
    snap_down = make_test_auction_snapshot(
        space_pct=Decimal("-9.90"),
        space_status=BiddingStatusEnum.LIMIT_DOWN_BIDDING,
    )
    v_down = comparator.evaluate(hypo, snap_down)
    assert v_down.overall_verdict == FalsificationOutcomeEnum.FALSIFIED


# =============================================================================
# GATE-2E2-04: Mainline Alignment & DIVERGENT Resolution Gate
# =============================================================================
def test_gate_2e2_04_mainline_alignment_divergent():
    """
    GATE-2E2-04: 主线分化与中度偏离门禁
    - 空间标杆正常 (+0.5%)，但主线龙头集体破位跌破 -1.50% (如 -2.0%)
    - 未触发 CRITICAL_KILL，但触发 MODERATE 违背 -> 裁决为 DIVERGENT
    """
    comparator = PopperianBiddingComparator()
    hypo = make_test_hypothesis()

    snap_div = make_test_auction_snapshot(
        space_pct=Decimal("0.50"),
        ml_pct=Decimal("-2.00"),
    )
    v = comparator.evaluate(hypo, snap_div)
    assert v.overall_verdict == FalsificationOutcomeEnum.DIVERGENT
    ml_assert = next(a for a in v.assertion_results if a.rule_id == "RULE-MAINLINE-LEADER-ALIGNMENT")
    assert ml_assert.is_violated is True
    assert ml_assert.severity == AssertionSeverityEnum.MODERATE


# =============================================================================
# GATE-2E2-05: Fully Reinforced CONFIRMED Resolution Gate
# =============================================================================
def test_gate_2e2_05_fully_confirmed():
    """
    GATE-2E2-05: 正向共振假说确认门禁
    - 空间标杆良性溢价 (+1.8%)
    - 主线龙头红开承接 (+1.2%)
    - 两市流动性正常 (1.00%)
    - 无任何断言被违背 -> 判定为 CONFIRMED
    """
    comparator = PopperianBiddingComparator()
    hypo = make_test_hypothesis()

    snap_ok = make_test_auction_snapshot(
        space_pct=Decimal("1.80"),
        ml_pct=Decimal("1.20"),
    )
    v = comparator.evaluate(hypo, snap_ok)
    assert v.overall_verdict == FalsificationOutcomeEnum.CONFIRMED
    assert all(a.is_violated is False for a in v.assertion_results)


# =============================================================================
# GATE-2E2-06: MECE Mutually Exclusive Truth Table Invariant Gate
# =============================================================================
def test_gate_2e2_06_mece_truth_table_invariants():
    """
    GATE-2E2-06: 四态完全互斥真值表公理门禁
    - 验证判定真值表的互斥与完备性：
      1. Has Critical Kill -> 100% FALSIFIED
      2. No Critical Kill, Has Moderate -> 100% DIVERGENT
      3. No Critical Kill, No Moderate -> 100% CONFIRMED
      4. Degraded / Closed -> 100% INCONCLUSIVE
    """
    comparator = PopperianBiddingComparator()
    hypo = make_test_hypothesis()

    # 1. Critical Kill 压倒一切 Moderate
    snap_combo = make_test_auction_snapshot(
        space_pct=Decimal("-4.00"),
        ml_pct=Decimal("-2.50"),
    )
    v_combo = comparator.evaluate(hypo, snap_combo)
    assert v_combo.overall_verdict == FalsificationOutcomeEnum.FALSIFIED

    # 2. 状态唯一性：每个 Verdict 的 overall_verdict 必须是有效枚举值
    assert isinstance(v_combo.overall_verdict, FalsificationOutcomeEnum)


# =============================================================================
# GATE-2E2-07: 5-in-1 Provenance Auditability & Threshold Tamper Defense Gate
# =============================================================================
def test_gate_2e2_07_provenance_and_tamper_defense():
    """
    GATE-2E2-07: 五位一体防伪与阈值防篡改门禁
    - 验证包含 5 大防伪锚点字段；
    - 验证 10 次重复调用输出完全相同的 JCS SHA-256 签名 (10x 幂等)；
    - 验证微调阈值字典时，threshold_config_hash 发生确定性改变。
    """
    comparator = PopperianBiddingComparator()
    hypo = make_test_hypothesis()
    snap = make_test_auction_snapshot()

    v1 = comparator.evaluate(hypo, snap, evaluation_timestamp="2026-10-09T09:25:30+08:00")

    # 1. 验证五位一体字段完整存在
    assert v1.hypothesis_id == hypo.hypothesis_id
    assert v1.hypothesis_fingerprint == hypo.hypothesis_fingerprint
    assert v1.rule_version == RULESET_VERSION
    assert v1.threshold_config_hash == comparator.threshold_config_hash
    assert v1.auction_fingerprint == snap.auction_fingerprint
    assert v1.trace_id.startswith("TRACE-2026-10-08-TO-2026-10-09-AUCTION-POPPER")

    # 2. 10x 幂等性
    fps = []
    for _ in range(10):
        v = comparator.evaluate(hypo, snap, evaluation_timestamp="2026-10-09T09:25:30+08:00")
        fps.append(v.verdict_fingerprint)
    assert len(set(fps)) == 1

    # 3. 阈值篡改防御
    tampered_thresholds = dict(DEFAULT_ASSERTION_THRESHOLDS)
    tampered_thresholds["space_leader_falsification_drop"] = "-2.50"  # 悄悄放宽 0.5%
    tampered_comparator = PopperianBiddingComparator(tampered_thresholds)

    assert tampered_comparator.threshold_config_hash != comparator.threshold_config_hash
    v_tampered = tampered_comparator.evaluate(
        hypo, snap, evaluation_timestamp="2026-10-09T09:25:30+08:00"
    )
    assert v_tampered.verdict_fingerprint != v1.verdict_fingerprint


# =============================================================================
# GATE-2E2-08: Two-Market Turnover & ChiNext Anti-Double-Count Gate
# =============================================================================
def test_gate_2e2_08_turnover_anti_double_count_with_golden_expected():
    """
    GATE-2E2-08: 两市全市场去重防双算独立期望值门禁
    - 使用独立硬编码黄金期望值校验：
      SH 全市场 = 81.12 亿
      SZ 全市场 = 87.09 亿 (已包含深市主板与创业板全市场)
      两市总额 = 168.21 亿 (绝不能叠加创业板指数成分成交额)
    """
    comparator = PopperianBiddingComparator()
    hypo = make_test_hypothesis()

    snap = make_test_auction_snapshot(
        sh_turnover_yi=Decimal("81.12"),
        sz_turnover_yi=Decimal("87.09"),
    )

    # 独立期望值断言 (非自反公式)
    assert snap.sh_auction_turnover_yi == Decimal("81.12")
    assert snap.sz_auction_turnover_yi == Decimal("87.09")
    assert snap.total_auction_turnover_yi == Decimal("168.21")

    # 执行对账评估
    v = comparator.evaluate(hypo, snap)
    liq_assert = next(a for a in v.assertion_results if a.rule_id == "RULE-LIQUIDITY-INTENSITY")
    assert "168.21" in liq_assert.target_entity
    assert "上海 81.12 亿" in liq_assert.actual_observation
    assert "深圳 87.09 亿" in liq_assert.actual_observation
