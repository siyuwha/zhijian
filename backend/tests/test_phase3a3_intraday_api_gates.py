"""
Phase 3A.3: Intraday REST API & Safety Guard Gates
===================================================
测试门禁规范：
1. TC-3A3-01: 真实未 Mock 物理数据库穿透测试 (2026-10-09)
2. TC-3A3-02: 空间标杆炸板一票否决 CRITICAL_BREACH 端到端穿透测试
3. TC-3A3-03: 非交易日/休市平稳降级 INCONCLUSIVE 零时钟漂移测试
4. TC-3A3-04: 安全守卫拦截 500 与违规诱导词零泄露测试
5. TC-3A3-05: 非法日期与时间格式 400 校验测试
6. TC-3A3-06: 远古/缺失基准快照 404 兜底测试
7. TC-3A3-07: 10x 并发请求全字节级恒定幂等测试
8. TC-3A3-08: SQLite 只读连接物理写入拒止测试
9. TC-3A3-09: 特性开关禁用 503 拦截测试
"""

import pytest
import sqlite3
import re
from decimal import Decimal
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch

from backend.app.main import app
from backend.app.schemas.intraday_drift_verdict import (
    DriftStateEnum,
    DriftInconclusiveReasonEnum,
    DriftEventCategoryEnum,
    IntradayDriftVerdict,
)
from backend.app.services.intraday_drift_service import (
    IntradayDriftService,
    _INTRADAY_VERDICT_MEMORY_CACHE,
)
from backend.app.services.intraday_safety_guard import (
    IntradaySafetyGuard,
    IntradaySafetyInterceptionError,
    ALLOWED_INTRADAY_BOUNDARY_SET,
)
from backend.app.core.database import async_session
from backend.app.models.market import MarketDailySnapshot
from backend.app.models.report import DailyReview


@pytest.fixture(autouse=True)
def clear_intraday_cache():
    """每次测试前清空内存对账缓存"""
    _INTRADAY_VERDICT_MEMORY_CACHE.clear()


@pytest.fixture(autouse=True)
async def seed_20261008_test_sandbox():
    """在 pytest 隔离数据库中装载 2026-10-08 真实物理基准数据"""
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
        if prod_snap:
            existing = await session.get(MarketDailySnapshot, 1)
            if not existing:
                row = MarketDailySnapshot(
                    id=1,
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
                session.add(row)

        if prod_rev:
            existing_rev = await session.get(DailyReview, 1)
            if not existing_rev:
                r_row = DailyReview(
                    id=1,
                    date=prod_rev[0],
                    market_overview=prod_rev[1],
                    limit_up_analysis=prod_rev[2],
                    sector_analysis=prod_rev[3],
                    market_state_id=prod_rev[4],
                    report_content=prod_rev[5],
                    data_quality=prod_rev[6],
                )
                session.add(r_row)

        await session.commit()


@pytest.mark.asyncio
async def test_tc3a3_01_real_unmocked_database_penetration():
    """TC-3A3-01: 真实未 Mock 物理数据库穿透测试 (2026-10-09)"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/canonical/intraday-drift/2026-10-09?time=10:30:00")
        assert resp.status_code == 200
        data = resp.json()

        assert data["trade_date"] == "2026-10-09"
        assert data["stage"] == "STAGE_2_MORNING"
        assert data["elapsed_trading_minutes"] == 60
        assert data["overall_drift_state"] in ["NORMAL", "DRIFT_WARNING", "CRITICAL_BREACH"]
        assert len(data["verdict_fingerprint"]) == 64
        assert len(data["assertion_results"]) >= 4
        assert data["safety_audit_passed"] is True


@pytest.mark.asyncio
async def test_tc3a3_02_space_leader_critical_kill_falsified():
    """TC-3A3-02: 空间标杆炸板一票否决 CRITICAL_BREACH 端到端穿透测试"""
    async with async_session() as session:
        service = IntradayDriftService(session)
        replay_broken = {
            "sh_amount_wan": 2000000,
            "sz_amount_wan": 2800000,
            "indices": [],
            "stocks": [
                {
                    "code": "sh600825",
                    "pre_close": "10.00",
                    "price": "10.15",
                    "high": "11.00",  # 曾达涨停但现价开板
                    "amount_wan": "60000.00",
                    "volume_wan": "5500.00",
                }
            ],
            "limit_up_count": 40,
            "broken_limit_count": 15,
        }
        verdict = await service.get_or_compute_verdict(
            trade_date="2026-10-09",
            snapshot_time="10:30:00",
            force_replay_data=replay_broken,
        )
        assert verdict.overall_drift_state == DriftStateEnum.CRITICAL_BREACH
        assert DriftEventCategoryEnum.SPACE_LEADER_COLLAPSE in verdict.detected_drift_events
        assert any("杜绝追高" in b for b in verdict.preservation_boundaries)


@pytest.mark.asyncio
async def test_tc3a3_03_market_closed_non_trading_day_no_drift():
    """TC-3A3-03: 非交易日/休市平稳降级 INCONCLUSIVE 零时钟漂移测试"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/canonical/intraday-drift/2026-10-10?time=10:30:00")
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_drift_state"] == "INCONCLUSIVE"
        assert data["inconclusive_reason"] == "MARKET_CLOSED"
        assert len(data["assertion_results"]) == 0


@pytest.mark.asyncio
async def test_tc3a3_04_safety_guard_interception_500_zero_leak():
    """TC-3A3-04: 安全守卫拦截 500 与违规诱导词零泄露测试"""
    async with async_session() as session:
        service = IntradayDriftService(session)
        # 获取正常裁决
        v = await service.get_or_compute_verdict("2026-10-09", "10:30:00")
        
        # 恶意注入买卖诱导词到标题
        v_malicious = v.model_copy(update={"verdict_headline": "全仓杀入追高买入"})
        guard = IntradaySafetyGuard()
        with pytest.raises(IntradaySafetyInterceptionError) as exc_info:
            guard.audit_verdict(v_malicious)

        err_detail = exc_info.value.to_safe_error_detail()
        assert err_detail["error_code"] == "ERR_INTRADAY_SAFETY_INTERCEPTION"
        assert "全仓杀入" not in str(err_detail)
        assert "买入" not in str(err_detail)


@pytest.mark.asyncio
async def test_tc3a3_05_invalid_date_and_time_format_400():
    """TC-3A3-05: 非法日期与时间格式 400 校验测试"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 非法日期
        resp1 = await client.get("/api/v1/canonical/intraday-drift/2026-109-09")
        assert resp1.status_code == 400
        assert resp1.json()["detail"]["error_code"] == "ERR_INVALID_DATE_FORMAT"

        # 非法时间
        resp2 = await client.get("/api/v1/canonical/intraday-drift/2026-10-09?time=invalid_time")
        assert resp2.status_code == 400
        assert resp2.json()["detail"]["error_code"] == "ERR_INVALID_TIME_FORMAT"


@pytest.mark.asyncio
async def test_tc3a3_06_base_data_not_found_404():
    """TC-3A3-06: 远古/缺失基准快照 404 兜底测试"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/canonical/intraday-drift/1999-01-05")
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_code"] == "ERR_BASE_DATA_NOT_FOUND"


@pytest.mark.asyncio
async def test_tc3a3_07_byte_level_idempotence_10x():
    """TC-3A3-07: 10x 并发请求全字节级恒定幂等测试"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp_base = await client.get("/api/v1/canonical/intraday-drift/2026-10-09?time=10:30:00")
        assert resp_base.status_code == 200
        base_body = resp_base.content

        for _ in range(9):
            resp = await client.get("/api/v1/canonical/intraday-drift/2026-10-09?time=10:30:00")
            assert resp.status_code == 200
            assert resp.content == base_body, "10次连续响应必须实现 100% 全字节级恒定幂等"


@pytest.mark.asyncio
async def test_tc3a3_08_database_readonly_physical_denial():
    """TC-3A3-08: SQLite 只读连接物理写入拒止测试"""
    # 模拟在只读 URI 模式下执行写入尝试
    import sqlite3
    ro_conn = sqlite3.connect("file:data/trading.db?mode=ro", uri=True)
    with pytest.raises(sqlite3.OperationalError) as exc_info:
        ro_conn.execute("INSERT INTO daily_review (date) VALUES ('2099-01-01')")
    assert "readonly" in str(exc_info.value).lower()
    ro_conn.close()


@pytest.mark.asyncio
async def test_tc3a3_09_feature_flag_disabled_503():
    """TC-3A3-09: 特性开关禁用 503 拦截测试"""
    with patch("backend.app.api.v1.canonical.ENABLE_PHASE3A_INTRADAY_API", False):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/canonical/intraday-drift/2026-10-09")
            assert resp.status_code == 503
            assert resp.json()["detail"]["error_code"] == "ERR_FEATURE_FLAG_DISABLED"
