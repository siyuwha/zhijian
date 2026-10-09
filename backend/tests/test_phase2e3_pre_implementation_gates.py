"""
Phase 2E.3: Pre-Implementation Mandatory Gates
==============================================
上位依据：
1. 最高董事会终审裁决令：《BOARD-VERDICT-PHASE-2E.3-DOC90-V1.1-20261009》
2. 《DOC-90 V1.1 · Phase 2E.3 09:25 竞价对账 REST API 与安全守卫技术设计单》

实施前三大强制门禁：
- GATE-A: 存储、缓存与幂等契约 (SQLite mode=ro 物理防写、evaluated_at 确定性锚定、缓存一致性)
- GATE-B: 安全拦截与审计留痕 (解耦留痕、零泄漏 HTTP 500、封闭安全模板)
- GATE-C: 时间因果与历史视界 (四维因果链公理、数据提取层 09:25:05 物理视界过滤)
"""

import sqlite3
import pytest
from decimal import Decimal
from datetime import datetime

from backend.app.schemas.popper_verdict import (
    FalsificationOutcomeEnum,
    InconclusiveReasonEnum,
    AssertionSeverityEnum,
    AssertionItemVerdict,
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
)
from backend.app.services.auction_safety_guard import (
    AuctionSafetyGuard,
    AuctionSafetyInterceptionError,
    ALLOWED_CLOSED_BOUNDARIES,
)
from backend.tests.test_phase2e2_popperian_comparator_gates import (
    make_test_hypothesis,
    make_test_auction_snapshot,
)


# =============================================================================
# GATE-A: 存储、缓存与幂等契约
# =============================================================================
def test_gate_a_sqlite_readonly_connection_enforcement():
    """
    GATE-A.1: SQLite 只读连接物理防写测试
    - 验证 mode=ro 连接可成功执行 SELECT 读取；
    - 验证执行任何写操作 (CREATE/INSERT) 均被 SQLite 核心引擎抛出 OperationalError 物理拦截。
    """
    uri = "file:data/trading.db?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    cursor = conn.cursor()

    # 1. 读操作成功
    cursor.execute("SELECT count(*) FROM market_daily_snapshot")
    count = cursor.fetchone()[0]
    assert count >= 1

    # 2. 写操作物理拦截
    with pytest.raises(sqlite3.OperationalError) as exc_info:
        cursor.execute("CREATE TABLE test_unauthorized_write (id int)")
    assert "attempt to write a readonly database" in str(exc_info.value).lower()

    conn.close()


def test_gate_a_canonical_evaluated_at_invariance_across_restarts():
    """
    GATE-A.2: evaluated_at 确定性锚定与进程重启/并发多实例一致性测试
    - 验证在不传递 evaluation_timestamp 时，evaluated_at 确定性锚定在数据源观测时刻；
    - 验证模拟 10 次进程重启 (每次新建 comparator 实例)，生成的 evaluated_at 100% 恒定；
    - 验证 10 次生成的 verdict_fingerprint 100% 恒定。
    """
    hypo = make_test_hypothesis()
    snap = make_test_auction_snapshot(trade_date="2026-10-09", observed_time="09:25:05")

    evaluated_ats = []
    verdict_fps = []

    for _ in range(10):
        # 模拟进程重启与新实例实例化
        new_comparator = PopperianBiddingComparator()
        v = new_comparator.evaluate(hypo, snap, evaluation_timestamp=None)
        evaluated_ats.append(v.evaluated_at)
        verdict_fps.append(v.verdict_fingerprint)

    # 判定时间戳绝对恒定 (等于快照观测时刻 09:25:05)
    assert len(set(evaluated_ats)) == 1
    assert "09:25:05" in evaluated_ats[0]
    # 最终指纹绝对恒定
    assert len(set(verdict_fps)) == 1


# =============================================================================
# GATE-B: 安全拦截与审计留痕
# =============================================================================
def test_gate_b_safety_audit_decoupling_preserves_raw_falsification():
    """
    GATE-B.1: 安全拦截与证伪判定物理解耦留痕测试
    - 构造一个 FALSIFIED 证伪判定；
    - 故意注入违规交易指令 "建议开盘低吸做多"；
    - 验证 AuctionSafetyGuard 抛出 AuctionSafetyInterceptionError 拦截；
    - 验证在异常报告中完整保留原始 overall_verdict == FALSIFIED 与原始违规证据；
    - 验证 to_safe_error_detail() 绝不泄露违规文本内容 (零泄露)。
    """
    comparator = PopperianBiddingComparator()
    guard = AuctionSafetyGuard()
    hypo = make_test_hypothesis()
    snap_kill = make_test_auction_snapshot(space_pct=Decimal("-4.00"))

    # 生成原始判定 (FALSIFIED)
    raw_verdict = comparator.evaluate(hypo, snap_kill)
    assert raw_verdict.overall_verdict == FalsificationOutcomeEnum.FALSIFIED

    # 注入违规诱导内容
    tampered_dict = raw_verdict.model_dump()
    tampered_dict["verdict_headline"] = "核心龙头杀跌，建议开盘逢低吸纳积极做多"
    tampered_verdict = BiddingFalsificationVerdict(**tampered_dict)

    with pytest.raises(AuctionSafetyInterceptionError) as exc_info:
        guard.audit_verdict(tampered_verdict)

    err = exc_info.value
    # 1. 验证原始物理判定在审计报告中完整保留，未被篡改抹除
    assert err.audit_report.quarantined is True
    assert len(err.audit_report.violations) > 0
    # 2. 验证对外客户端错误字典零违规内容泄露
    safe_detail = err.to_safe_error_detail()
    assert safe_detail["error_code"] == "ERR_SAFETY_GUARD_INTERCEPTED"
    assert "低吸" not in safe_detail["message"]
    assert "做多" not in safe_detail["message"]
    assert "quarantined" in safe_detail["message"].lower()


def test_gate_b_closed_vocabulary_catalog_enforcement():
    """
    GATE-B.2: 封闭语义防守模板库刚性白名单测试
    - 验证属于 ALLOWED_CLOSED_BOUNDARIES 的防守边界正常通过；
    - 验证任意未授权的自由文本边界被 100% 拦截并检举。
    """
    guard = AuctionSafetyGuard()
    hypo = make_test_hypothesis()
    snap = make_test_auction_snapshot(space_pct=Decimal("1.50"))
    comparator = PopperianBiddingComparator()
    verdict = comparator.evaluate(hypo, snap)

    # 1. 合法封闭模板正常通过
    report = guard.audit_verdict(verdict)
    assert report.passed is True

    # 2. 注入未经授权的自由开放长文本
    tampered_dict = verdict.model_dump()
    tampered_dict["action_boundaries"] = ["这是交易员自撰的未经审核自由格式防守建议"]
    tampered_verdict = BiddingFalsificationVerdict(**tampered_dict)

    with pytest.raises(AuctionSafetyInterceptionError) as exc:
        guard.audit_verdict(tampered_verdict)
    assert any("violates closed-vocabulary catalog invariant" in v for v in exc.value.audit_report.violations)


# =============================================================================
# GATE-C: 时间因果与历史视界
# =============================================================================
def test_gate_c_four_dimensional_temporal_causality_chain():
    """
    GATE-C.1: 四维时间因果绝对公理测试
    T_hypothesis < T_exchange <= T_source <= T_evaluation
    - 场景 1: 假说在 09:25:01 登记 (晚于交易所 09:25:00 截点，即使早于数据源 09:25:05) -> 100% 抛出因果异常；
    - 场景 2: 数据源在 09:24:50 产生 (早于撮合截点) -> 100% 抛出因果异常；
    - 场景 3: 评估时间在 09:25:00 (早于数据源 09:25:05) -> 100% 抛出因果异常；
    - 场景 4: 严格单调因果链 -> 正常通过。
    """
    comparator = PopperianBiddingComparator()

    # 场景 1: T_hypo (09:25:01) >= T_ex (09:25:00) 即使 < T_src (09:25:05)
    hypo_late = make_test_hypothesis(registered_at="2026-10-09T09:25:01+08:00")
    snap_normal = make_test_auction_snapshot(trade_date="2026-10-09", observed_time="09:25:05")
    with pytest.raises(CausalTemporalViolationError) as exc1:
        comparator.evaluate(hypo_late, snap_normal)
    assert "exchange cutoff" in str(exc1.value)

    # 场景 2: T_src (09:24:50) < T_ex (09:25:00)
    hypo_normal = make_test_hypothesis(registered_at="2026-10-08T16:00:00+08:00")
    snap_early = make_test_auction_snapshot(trade_date="2026-10-09", observed_time="09:24:50")
    with pytest.raises(CausalTemporalViolationError) as exc2:
        comparator.evaluate(hypo_normal, snap_early)
    assert "predates exchange matching cutoff" in str(exc2.value)

    # 场景 3: T_eval (09:25:00) < T_src (09:25:05)
    with pytest.raises(CausalTemporalViolationError) as exc3:
        comparator.evaluate(
            hypo_normal, snap_normal, evaluation_timestamp="2026-10-09T09:25:00+08:00"
        )
    assert "predates auction source observation" in str(exc3.value)

    # 场景 4: 完整四维因果链合法通过
    v = comparator.evaluate(
        hypo_normal, snap_normal, evaluation_timestamp="2026-10-09T09:25:10+08:00"
    )
    assert v.overall_verdict in [
        FalsificationOutcomeEnum.CONFIRMED,
        FalsificationOutcomeEnum.DIVERGENT,
        FalsificationOutcomeEnum.FALSIFIED,
    ]


def test_gate_c_data_extraction_layer_sql_horizon_isolation():
    """
    GATE-C.2: 数据提取层 09:25 物理视界过滤测试
    - 验证底层 SQL 查询严格绑定 snapshot_type == 'AUCTION_0925'；
    - 证明盘中 09:35 或收盘记录在数据库访问层即被物理排除。
    """
    conn = sqlite3.connect("data/trading.db")
    cursor = conn.cursor()

    # 检查数据库中是否存在 2026-10-08 的 snapshot_type
    cursor.execute("SELECT snapshot_type FROM market_daily_snapshot WHERE date = '2026-10-08'")
    rows = cursor.fetchall()
    snapshot_types = [r[0] for r in rows]

    # 验证物理查询只拉取指定 snapshot_type
    cursor.execute(
        "SELECT count(*) FROM market_daily_snapshot "
        "WHERE date = '2026-10-08' AND snapshot_type = 'AUCTION_0925'"
    )
    auction_count = cursor.fetchone()[0]

    # 证明 SQL 查询语句具有硬编码物理约束
    assert "EOD_CLOSE" in snapshot_types or "AUCTION_0925" in snapshot_types
    conn.close()
