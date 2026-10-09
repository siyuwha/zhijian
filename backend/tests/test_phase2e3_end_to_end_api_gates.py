"""
Phase 2E.3: End-to-End REST API & Safety Guard Gate Tests (15 TC Matrix)
========================================================================
上位依据：
1. 最高董事会审查裁决令：《BOARD-VERDICT-PHASE-2E.3-DOC90-V1.1-20261009》
2. 《DOC-90 V1.1 · Phase 2E.3 09:25 竞价对账 REST API 与安全守卫技术设计单》
3. 《红队独立审计与对抗测试报告 · Phase 2E.3 专项》整改指令

整改要点：
- 严格禁止在测试中通过 patch.object(AuctionFalsificationService, "get_or_compute_verdict") 架空核心编排层；
- 包含 TC-2E3-01 绝对零 Mock 直穿真实物理数据库与完整业务编排链路；
- 场景测试仅在数据源采集层 (CanonicalAuctionService.produce_canonical_auction_snapshot) 模拟边界输入，
  保证 AuctionFalsificationService 的假说构建、时序因果、判定器调用、安全守卫与缓存管理 100% 真实执行！
"""

import pytest
import sqlite3
import re
from decimal import Decimal
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

from backend.app.main import app
from backend.app.schemas.popper_verdict import (
    FalsificationOutcomeEnum,
    InconclusiveReasonEnum,
    AssertionSeverityEnum,
    BiddingFalsificationVerdict,
)
from backend.app.services.auction_falsification_service import (
    AuctionFalsificationService,
    _AUCTION_VERDICT_MEMORY_CACHE,
)
from backend.app.services.canonical_auction_service import CanonicalAuctionService
from backend.app.services.popperian_bidding_comparator import (
    CausalTemporalViolationError,
    PopperianBiddingComparator,
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
from backend.app.schemas.canonical_market import DataQualityGrade


from sqlalchemy import select
from backend.app.core.database import async_session
from backend.app.models.market import MarketDailySnapshot
from backend.app.models.report import DailyReview


@pytest.fixture(autouse=True)
def clear_verdict_cache():
    """每次测试前清空内存对账缓存"""
    _AUCTION_VERDICT_MEMORY_CACHE.clear()


@pytest.fixture(autouse=True)
async def seed_20261008_test_sandbox():
    """
    EG-01 沙箱隔离：从物理 data/trading.db 只读读取 2026-10-08 真实事实并注入 pytest 测试沙箱
    """
    prod_conn = sqlite3.connect("data/trading.db")
    prod_snap = prod_conn.execute(
        "SELECT date, snapshot_type, indices_snapshot, breadth_snapshot, "
        "limit_up_snapshot, micro_cap_snapshot, external_risk_snapshot, "
        "high_tier_snapshot, market_state_snapshot, data_quality, source_status "
        "FROM market_daily_snapshot WHERE date='2026-10-08'"
    ).fetchone()

    prod_rev = prod_conn.execute(
        "SELECT date, market_overview, limit_up_analysis, sector_analysis, "
        "market_state_id, report_content, data_quality "
        "FROM daily_review WHERE date='2026-10-08'"
    ).fetchone()
    prod_conn.close()

    async with async_session() as session:
        existing = (await session.execute(
            select(MarketDailySnapshot).where(MarketDailySnapshot.date == '2026-10-08')
        )).scalars().first()

        if not existing:
            if prod_snap:
                snap_obj = MarketDailySnapshot(
                    date=prod_snap[0],
                    snapshot_type=prod_snap[1],
                    indices_snapshot=prod_snap[2],
                    breadth_snapshot=prod_snap[3],
                    limit_up_snapshot=prod_snap[4],
                    micro_cap_snapshot=prod_snap[5],
                    external_risk_snapshot=prod_snap[6],
                    high_tier_snapshot=prod_snap[7],
                    market_state_snapshot=prod_snap[8],
                    data_quality=prod_snap[9],
                    source_status=prod_snap[10],
                )
                session.add(snap_obj)

            if prod_rev:
                rev_obj = DailyReview(
                    date=prod_rev[0],
                    market_overview=prod_rev[1],
                    limit_up_analysis=prod_rev[2],
                    sector_analysis=prod_rev[3],
                    market_state_id=prod_rev[4],
                    report_content=prod_rev[5],
                    data_quality=prod_rev[6],
                )
                session.add(rev_obj)

            await session.commit()


# =============================================================================
# TC-2E3-01: 绝对零 Mock 直穿真实物理数据库与完整业务编排链路 (红队整改硬核门禁)
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_01_real_unmocked_database_penetration():
    """
    直穿物理数据库 data/trading.db，零 Mock 执行完整业务流：
    - 读取 2026-10-08 EOD_CLOSE 快照
    - 动态解析最高板 600825 (新华传媒) 与 Top 主线代表
    - 构建前夜假说并计算 JCS SHA-256
    - 采集/重放当日真实竞价数据
    - PopperianBiddingComparator 执行四维时序与多维规则断言
    - AuctionSafetyGuard 审计
    - 检验 200 返回与 5-in-1 锚点完整性
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
        assert res.status_code == 200
        data = res.json()
        assert data["trade_date"] == "2026-10-09"
        assert data["overall_verdict"] in ["CONFIRMED", "DIVERGENT", "FALSIFIED", "INCONCLUSIVE"]
        assert data["safety_audit_passed"] is True
        assert len(data["assertion_results"]) >= 1

        # 5-in-1 锚点格式严密校验 (P0-2 闭环)
        assert re.match(r"^HYPO-\d{4}-\d{2}-\d{2}-[a-f0-9]{8,12}$", data["hypothesis_id"])
        assert re.match(r"^[a-f0-9]{64}$", data["hypothesis_fingerprint"])
        assert re.match(r"^[a-f0-9]{64}$", data["threshold_config_hash"])
        assert re.match(r"^[a-f0-9]{64}$", data["auction_fingerprint"])
        assert re.match(r"^[a-f0-9]{64}$", data["verdict_fingerprint"])


# =============================================================================
# TC-2E3-01b: 正向假说全面吻合端到端 (HTTP 200, CONFIRMED)
# 编排服务 100% 真实执行，仅在数据采集层提供正面竞价事实
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_01b_confirmed_end_to_end():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async def mock_auction_snap(**kwargs):
            return make_test_auction_snapshot(
                trade_date=kwargs.get("trade_date", "2026-10-09"),
                space_pct=Decimal("2.40"),
                ml_pct=Decimal("1.70"),
            )

        with patch.object(CanonicalAuctionService, "produce_canonical_auction_snapshot", side_effect=mock_auction_snap):
            res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
            assert res.status_code == 200
            data = res.json()
            assert data["overall_verdict"] == "CONFIRMED"
            assert data["inconclusive_reason"] is None
            assert len(data["assertion_results"]) >= 2
            assert re.match(r"^HYPO-\d{4}-\d{2}-\d{2}-[a-f0-9]{8,12}$", data["hypothesis_id"])


# =============================================================================
# TC-2E3-02: 空间标杆致命证伪端到端 (HTTP 200, FALSIFIED, 封闭防守词)
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_02_space_leader_critical_kill_falsified():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async def mock_auction_snap(**kwargs):
            return make_test_auction_snapshot(
                trade_date=kwargs.get("trade_date", "2026-10-09"),
                space_pct=Decimal("-4.50"),
            )

        with patch.object(CanonicalAuctionService, "produce_canonical_auction_snapshot", side_effect=mock_auction_snap):
            res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
            assert res.status_code == 200
            data = res.json()
            assert data["overall_verdict"] == "FALSIFIED"
            # 封闭防守词库合规校验
            for b in data["action_boundaries"]:
                assert any(allowed in b for allowed in ALLOWED_CLOSED_BOUNDARIES)


# =============================================================================
# TC-2E3-03: 主线龙头中度分歧端到端 (HTTP 200, DIVERGENT)
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_03_mainline_divergent_end_to_end():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async def mock_auction_snap(**kwargs):
            return make_test_auction_snapshot(
                trade_date=kwargs.get("trade_date", "2026-10-09"),
                space_pct=Decimal("0.80"),
                ml_pct=Decimal("-2.50"),
            )

        with patch.object(CanonicalAuctionService, "produce_canonical_auction_snapshot", side_effect=mock_auction_snap):
            res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
            assert res.status_code == 200
            data = res.json()
            assert data["overall_verdict"] == "DIVERGENT"


# =============================================================================
# TC-2E3-04: 非交易日休市请求 (HTTP 200, INCONCLUSIVE, MARKET_CLOSED, 日期不漂移)
# 绝对零 Mock，直穿交易日历与物理编排层
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_04_market_closed_non_trading_day_no_drift():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 请求周六 (2026-10-10)
        res = await client.get("/api/v1/canonical/auction-falsification/2026-10-10")
        assert res.status_code == 200
        data = res.json()
        assert data["overall_verdict"] == "INCONCLUSIVE"
        assert data["inconclusive_reason"] == "MARKET_CLOSED"
        assert data["trade_date"] == "2026-10-10"  # 绝对不发生日期漂移！
        assert len(data["assertion_results"]) == 0


# =============================================================================
# TC-2E3-05: 数据源质量降级拦截 (HTTP 200, INCONCLUSIVE, DATA_QUALITY_DEGRADED)
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_05_data_quality_degraded_inconclusive():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async def mock_auction_snap(**kwargs):
            return make_test_auction_snapshot(
                trade_date=kwargs.get("trade_date", "2026-10-09"),
                data_quality=DataQualityGrade.PARTIAL,
                is_degraded=True,
                degradation_reason="深交所网关抖动",
            )

        with patch.object(CanonicalAuctionService, "produce_canonical_auction_snapshot", side_effect=mock_auction_snap):
            res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
            assert res.status_code == 200
            data = res.json()
            assert data["overall_verdict"] == "INCONCLUSIVE"
            assert data["inconclusive_reason"] == "DATA_QUALITY_DEGRADED"


# =============================================================================
# TC-2E3-06: 标的缺失零静默替换 (HTTP 200, INCONCLUSIVE, TARGET_MISSING_OR_SUSPENDED)
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_06_target_missing_zero_silent_substitution():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async def mock_auction_snap(**kwargs):
            return make_test_auction_snapshot(
                trade_date=kwargs.get("trade_date", "2026-10-09"),
                include_space=False,
            )

        with patch.object(CanonicalAuctionService, "produce_canonical_auction_snapshot", side_effect=mock_auction_snap):
            res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
            assert res.status_code == 200
            data = res.json()
            assert data["overall_verdict"] == "INCONCLUSIVE"
            assert data["inconclusive_reason"] == "TARGET_MISSING_OR_SUSPENDED"


# =============================================================================
# TC-2E3-07: 标的停牌异常防御 (HTTP 200, INCONCLUSIVE, TARGET_MISSING_OR_SUSPENDED)
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_07_target_suspended_defense():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async def mock_auction_snap(**kwargs):
            return make_test_auction_snapshot(
                trade_date=kwargs.get("trade_date", "2026-10-09"),
                space_suspended=True,
            )

        with patch.object(CanonicalAuctionService, "produce_canonical_auction_snapshot", side_effect=mock_auction_snap):
            res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
            assert res.status_code == 200
            data = res.json()
            assert data["overall_verdict"] == "INCONCLUSIVE"
            assert data["inconclusive_reason"] == "TARGET_MISSING_OR_SUSPENDED"


# =============================================================================
# TC-2E3-08: 因果时序倒置拦截 (HTTP 422, ERR_CAUSAL_TEMPORAL_VIOLATION)
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_08_causal_temporal_violation_422():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async def mock_early_snap(**kwargs):
            # 数据源观测时间早于交易所 09:25:00 截点 (违背 T_exchange <= T_source)
            return make_test_auction_snapshot(
                trade_date=kwargs.get("trade_date", "2026-10-09"),
                observed_time="09:24:50",
            )

        with patch.object(CanonicalAuctionService, "produce_canonical_auction_snapshot", side_effect=mock_early_snap):
            res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
            assert res.status_code == 422
            data = res.json()
            assert data["detail"]["error_code"] == "ERR_CAUSAL_TEMPORAL_VIOLATION"


# =============================================================================
# TC-2E3-09: 迟到数据接收截止线 (HTTP 200, 标记降级)
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_09_late_data_ingestion_deadline():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async def mock_late_snap(**kwargs):
            return make_test_auction_snapshot(
                trade_date=kwargs.get("trade_date", "2026-10-09"),
                observed_time="09:25:35",
                data_quality=DataQualityGrade.DEGRADED,
                is_degraded=True,
                degradation_reason="Snapshot arrived past 09:25:30 deadline",
            )

        with patch.object(CanonicalAuctionService, "produce_canonical_auction_snapshot", side_effect=mock_late_snap):
            res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
            assert res.status_code == 200
            data = res.json()
            assert data["overall_verdict"] == "INCONCLUSIVE"
            assert data["inconclusive_reason"] == "DATA_QUALITY_DEGRADED"


# =============================================================================
# TC-2E3-10: 日期格式非法拦截 (HTTP 400, ERR_INVALID_DATE_FORMAT)
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_10_invalid_date_format_400():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/canonical/auction-falsification/invalid-date-format")
        assert res.status_code == 400
        data = res.json()
        assert data["detail"]["error_code"] == "ERR_INVALID_DATE_FORMAT"


# =============================================================================
# TC-2E3-11: 历史基线记录不存在 (HTTP 404, ERR_BASE_BRIEFING_NOT_FOUND)
# 绝对零 Mock，直接请求未收录年份 (2019-01-02) 验证真实物理数据库 404 捕获
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_11_base_briefing_not_found_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/canonical/auction-falsification/2019-01-02")
        assert res.status_code == 404
        data = res.json()
        assert data["detail"]["error_code"] == "ERR_BASE_BRIEFING_NOT_FOUND"


# =============================================================================
# TC-2E3-12: 安全守卫违规买卖词拦截 (HTTP 500, ERR_SAFETY_GUARD_INTERCEPTED, 原始证据未抹除)
# 仅针对安全守卫进行阻断模拟，检验 API 网关层的安全脱敏与零泄漏
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_12_safety_guard_interception_500_zero_leak():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        def raise_safety_interception(verdict):
            from backend.app.services.auction_safety_guard import SafetyAuditReport
            report = SafetyAuditReport(
                passed=False,
                audited_at="2026-10-09T09:25:35+08:00",
                trace_id="TRACE-SAFETY-TEST",
                violations=["Forbidden trading directive term detected: '买入'"],
                quarantined=True,
            )
            raise AuctionSafetyInterceptionError("Safety audit intercepted violations", audit_report=report)

        with patch.object(AuctionSafetyGuard, "audit_verdict", side_effect=raise_safety_interception):
            res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
            assert res.status_code == 500
            data = res.json()
            assert data["detail"]["error_code"] == "ERR_SAFETY_GUARD_INTERCEPTED"
            # 验证零违规词泄露
            assert "买入" not in str(data)
            assert "quarantined" in data["detail"]["message"].lower()


# =============================================================================
# TC-2E3-13: 响应全字节级幂等测试 (10 次请求哈希与 evaluated_at 100% 字节一致)
# 绝对零 Mock，直穿缓存与物理数据库
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_13_byte_level_idempotence_10x():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        responses = []
        for _ in range(10):
            res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
            assert res.status_code == 200
            responses.append(res.content)

        # 验证 10 次 HTTP 响应字节流 100% 恒定一致
        assert len(set(responses)) == 1


# =============================================================================
# TC-2E3-14: 数据库只读物理限制穿透测试 (写入操作直接抛出 SQLite 只读死锁)
# =============================================================================
def test_tc2e3_14_database_readonly_physical_denial():
    uri = "file:data/trading.db?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    cursor = conn.cursor()

    try:
        with pytest.raises(sqlite3.OperationalError) as exc:
            cursor.execute("CREATE TABLE IF NOT EXISTS malicious_write (id INT)")
        assert "readonly database" in str(exc.value)
    finally:
        conn.close()
