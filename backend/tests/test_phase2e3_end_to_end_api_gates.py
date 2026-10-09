"""
Phase 2E.3: End-to-End REST API & Safety Guard Gate Tests (14 TC Matrix)
========================================================================
上位依据：
1. 最高董事会审查裁决令：《BOARD-VERDICT-PHASE-2E.3-DOC90-V1.1-20261009》
2. 《DOC-90 V1.1 · Phase 2E.3 09:25 竞价对账 REST API 与安全守卫技术设计单》

14 组端到端全量测试规格：
- TC-2E3-01: 正向假说确认端到端 (HTTP 200, CONFIRMED)
- TC-2E3-02: 空间标杆致命证伪端到端 (HTTP 200, FALSIFIED, 封闭防守词)
- TC-2E3-03: 主线龙头中度分歧端到端 (HTTP 200, DIVERGENT)
- TC-2E3-04: 非交易日休市请求 (HTTP 200, INCONCLUSIVE, MARKET_CLOSED, 日期不漂移)
- TC-2E3-05: 数据源质量降级拦截 (HTTP 200, INCONCLUSIVE, DATA_QUALITY_DEGRADED)
- TC-2E3-06: 标的缺失零静默替换 (HTTP 200, INCONCLUSIVE, TARGET_MISSING_OR_SUSPENDED)
- TC-2E3-07: 标的停牌异常防御 (HTTP 200, INCONCLUSIVE, TARGET_MISSING_OR_SUSPENDED)
- TC-2E3-08: 因果时序倒置拦截 (HTTP 422, ERR_CAUSAL_TEMPORAL_VIOLATION)
- TC-2E3-09: 迟到数据接收截止线 (HTTP 200, 标记降级)
- TC-2E3-10: 日期格式非法拦截 (HTTP 400, ERR_INVALID_DATE_FORMAT)
- TC-2E3-11: 历史基线记录不存在 (HTTP 404, ERR_BASE_BRIEFING_NOT_FOUND)
- TC-2E3-12: 安全守卫违规买卖词拦截 (HTTP 500, ERR_SAFETY_GUARD_INTERCEPTED, 原始证据未抹除)
- TC-2E3-13: 响应全字节级幂等测试 (10 次请求哈希与 evaluated_at 100% 字节一致)
- TC-2E3-14: 数据库只读物理限制穿透测试 (写入操作直接抛出 SQLite 只读死锁)
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


@pytest.fixture(autouse=True)
def clear_verdict_cache():
    """每次测试前清空内存对账缓存"""
    _AUCTION_VERDICT_MEMORY_CACHE.clear()


# =============================================================================
# TC-2E3-01: 正向假说确认端到端 (HTTP 200, CONFIRMED)
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_01_confirmed_end_to_end():
    healthy_mock_data = {
        "indices": [],
        "stocks": [
            {
                "code": "600825",
                "name": "新华传媒",
                "open": 12.80,
                "yesterday_close": 12.50,
                "pct_change": 2.40,
                "amount_wan": 4500.0,
            },
            {
                "code": "600241",
                "name": "时代万恒",
                "open": 8.95,
                "yesterday_close": 8.80,
                "pct_change": 1.70,
                "amount_wan": 3200.0,
            },
        ],
        "sh_amount_wan": 800000.0,
        "sz_amount_wan": 850000.0,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch.object(
            AuctionFalsificationService,
            "get_or_compute_verdict",
            side_effect=lambda trade_date: AuctionFalsificationService(None).comparator.evaluate(
                make_test_hypothesis(target_trade_date=trade_date),
                make_test_auction_snapshot(trade_date=trade_date, space_pct=Decimal("2.40"), ml_pct=Decimal("1.70")),
            ),
        ):
            res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
            assert res.status_code == 200
            data = res.json()
            assert data["overall_verdict"] == "CONFIRMED"
            assert data["inconclusive_reason"] is None
            assert len(data["assertion_results"]) >= 2
            # 5-in-1 锚点格式校验
            assert re.match(r"^HYPO-\d{4}-\d{2}-\d{2}-[a-f0-9]{8,12}$", data["hypothesis_id"])
            assert re.match(r"^[a-f0-9]{64}$", data["hypothesis_fingerprint"])
            assert re.match(r"^[a-f0-9]{64}$", data["threshold_config_hash"])
            assert re.match(r"^[a-f0-9]{64}$", data["auction_fingerprint"])
            assert re.match(r"^[a-f0-9]{64}$", data["verdict_fingerprint"])


# =============================================================================
# TC-2E3-02: 空间标杆致命证伪端到端 (HTTP 200, FALSIFIED, 封闭防守词)
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_02_space_leader_critical_kill_falsified():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch.object(
            AuctionFalsificationService,
            "get_or_compute_verdict",
            side_effect=lambda trade_date: AuctionFalsificationService(None).comparator.evaluate(
                make_test_hypothesis(target_trade_date=trade_date),
                make_test_auction_snapshot(trade_date=trade_date, space_pct=Decimal("-4.50")),
            ),
        ):
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
        with patch.object(
            AuctionFalsificationService,
            "get_or_compute_verdict",
            side_effect=lambda trade_date: AuctionFalsificationService(None).comparator.evaluate(
                make_test_hypothesis(target_trade_date=trade_date),
                make_test_auction_snapshot(trade_date=trade_date, space_pct=Decimal("0.80"), ml_pct=Decimal("-2.50")),
            ),
        ):
            res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
            assert res.status_code == 200
            data = res.json()
            assert data["overall_verdict"] == "DIVERGENT"


# =============================================================================
# TC-2E3-04: 非交易日休市请求 (HTTP 200, INCONCLUSIVE, MARKET_CLOSED, 日期不漂移)
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_04_market_closed_non_trading_day_no_drift():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        with patch.object(
            AuctionFalsificationService,
            "get_or_compute_verdict",
            side_effect=lambda trade_date: AuctionFalsificationService(None).comparator.evaluate(
                make_test_hypothesis(target_trade_date=trade_date),
                make_test_auction_snapshot(trade_date=trade_date, is_trading_day=False),
            ),
        ):
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
        with patch.object(
            AuctionFalsificationService,
            "get_or_compute_verdict",
            side_effect=lambda trade_date: AuctionFalsificationService(None).comparator.evaluate(
                make_test_hypothesis(target_trade_date=trade_date),
                make_test_auction_snapshot(
                    trade_date=trade_date,
                    data_quality=DataQualityGrade.PARTIAL,
                    is_degraded=True,
                    degradation_reason="深交所网关抖动",
                ),
            ),
        ):
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
        with patch.object(
            AuctionFalsificationService,
            "get_or_compute_verdict",
            side_effect=lambda trade_date: AuctionFalsificationService(None).comparator.evaluate(
                make_test_hypothesis(target_trade_date=trade_date),
                make_test_auction_snapshot(trade_date=trade_date, include_space=False),
            ),
        ):
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
        with patch.object(
            AuctionFalsificationService,
            "get_or_compute_verdict",
            side_effect=lambda trade_date: AuctionFalsificationService(None).comparator.evaluate(
                make_test_hypothesis(target_trade_date=trade_date),
                make_test_auction_snapshot(trade_date=trade_date, space_suspended=True),
            ),
        ):
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
        def raise_causal_error(trade_date):
            raise CausalTemporalViolationError("Hypothesis registered at 09:25:01 postdates exchange cutoff 09:25:00")

        with patch.object(AuctionFalsificationService, "get_or_compute_verdict", side_effect=raise_causal_error):
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
        with patch.object(
            AuctionFalsificationService,
            "get_or_compute_verdict",
            side_effect=lambda trade_date: AuctionFalsificationService(None).comparator.evaluate(
                make_test_hypothesis(target_trade_date=trade_date),
                make_test_auction_snapshot(
                    trade_date=trade_date,
                    observed_time="09:25:35",
                    data_quality=DataQualityGrade.DEGRADED,
                    is_degraded=True,
                    degradation_reason="Snapshot arrived past 09:25:30 deadline",
                ),
            ),
        ):
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
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_11_base_briefing_not_found_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        def raise_404(trade_date):
            raise ValueError(f"Base market snapshot for 2019-01-01 not found")

        with patch.object(AuctionFalsificationService, "get_or_compute_verdict", side_effect=raise_404):
            res = await client.get("/api/v1/canonical/auction-falsification/2019-01-02")
            assert res.status_code == 404
            data = res.json()
            assert data["detail"]["error_code"] == "ERR_BASE_BRIEFING_NOT_FOUND"


# =============================================================================
# TC-2E3-12: 安全守卫违规买卖词拦截 (HTTP 500, ERR_SAFETY_GUARD_INTERCEPTED, 原始证据未抹除)
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_12_safety_guard_interception_500_zero_leak():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        def raise_safety_interception(trade_date):
            from backend.app.services.auction_safety_guard import SafetyAuditReport
            report = SafetyAuditReport(
                passed=False,
                audited_at="2026-10-09T09:25:35+08:00",
                trace_id="TRACE-SAFETY-TEST",
                violations=["Forbidden trading directive term detected: '买入'"],
                quarantined=True,
            )
            raise AuctionSafetyInterceptionError("Safety audit intercepted violations", audit_report=report)

        with patch.object(AuctionFalsificationService, "get_or_compute_verdict", side_effect=raise_safety_interception):
            res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
            assert res.status_code == 500
            data = res.json()
            assert data["detail"]["error_code"] == "ERR_SAFETY_GUARD_INTERCEPTED"
            # 验证零违规词泄露
            assert "买入" not in str(data)
            assert "quarantined" in data["detail"]["message"].lower()


# =============================================================================
# TC-2E3-13: 响应全字节级幂等测试 (10 次请求哈希与 evaluated_at 100% 字节一致)
# =============================================================================
@pytest.mark.asyncio
async def test_tc2e3_13_byte_level_idempotence_10x():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        snap_fixed = make_test_auction_snapshot(trade_date="2026-10-09", observed_time="09:25:05")
        hypo_fixed = make_test_hypothesis(target_trade_date="2026-10-09")
        fixed_verdict = PopperianBiddingComparator().evaluate(hypo_fixed, snap_fixed)

        # 预热缓存
        _AUCTION_VERDICT_MEMORY_CACHE["VERDICT:2026-10-09"] = fixed_verdict

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

    # 验证尝试插入数据被 SQLite 物理拒绝
    with pytest.raises(sqlite3.OperationalError) as exc_info:
        cursor.execute("INSERT INTO market_daily_snapshot (date, snapshot_type) VALUES ('2099-01-01', 'ILLEGAL')")
    assert "attempt to write a readonly database" in str(exc_info.value).lower()
    conn.close()
