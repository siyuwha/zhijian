"""
Phase 2D.1: Canonical Market Snapshot API 端点测试
测试目标：
1. GET /api/v1/canonical/market-snapshot/2026-10-08 正常返回 200 与统一数据信封
2. 信封中严格包含 MarketTruthSnapshot (FACT+DERIVED) 与 CognitionSnapshot (COGNITION)
3. 验证深市防重算口径 (16821.09 亿)、炸板率 Universe (42.67%)、三级层级模型 (央国企/电设/固态/储能/家电)
4. 验证 SharedEvidenceAffiliate 重叠度审计、前沿科技题材保护与中军断层警告
5. 验证非交易日或未收录日期返回 404
"""

import pytest
import sqlite3
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from backend.app.main import app
from backend.app.core.database import init_db, async_session
from backend.app.models.market import MarketDailySnapshot
from backend.app.models.report import DailyReview


@pytest.fixture(autouse=True)
async def seed_20261008_for_api():
    """沙箱数据注入"""
    await init_db()
    prod_conn = sqlite3.connect("data/trading.db")
    prod_snap = prod_conn.execute(
        "SELECT date, snapshot_type, indices_snapshot, breadth_snapshot, "
        "limit_up_snapshot, micro_cap_snapshot, external_risk_snapshot, "
        "high_tier_snapshot, market_state_snapshot, data_quality, source_status "
        "FROM market_daily_snapshot WHERE date='2026-10-08' AND snapshot_type='EOD_CLOSE'"
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
                session.add(MarketDailySnapshot(
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
                ))
            if prod_rev:
                session.add(DailyReview(
                    date=prod_rev[0],
                    market_overview=prod_rev[1],
                    limit_up_analysis=prod_rev[2],
                    sector_analysis=prod_rev[3],
                    market_state_id=prod_rev[4],
                    report_content=prod_rev[5],
                    data_quality=prod_rev[6],
                ))
            await session.commit()


@pytest.mark.asyncio
async def test_get_canonical_market_snapshot_success():
    """测试获取 2026-10-08 标准市场真相与认知快照成功"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/canonical/market-snapshot/2026-10-08")
        assert resp.status_code == 200
        data = resp.json()

        # 1. 顶层统一信封校验
        assert data["snapshot_version"] == "2D.0-CANONICAL-V2"
        assert data["trade_date"] == "2026-10-08"
        assert "truth" in data
        assert "cognition" in data
        assert len(data["envelope_fingerprint"]) == 64

        # 2. L1 真实成交额防重算校验
        turnover = data["truth"]["turnover"]
        assert turnover["two_markets_total_yi"] == 16821.09
        assert abs(turnover["sh_amount_yi"] - 8111.83) < 1.0
        assert abs(turnover["sz_total_amount_yi"] - 8709.26) < 1.0
        assert abs(turnover["chinext_slice_amount_yi"] - 4227.55) < 1.0
        assert turnover["two_markets_total_yi"] == round(
            turnover["sh_amount_yi"] + turnover["sz_total_amount_yi"], 2
        )

        # 3. L1 炸板率 Universe 边界校验
        sb = data["truth"]["sentiment_bounds"]
        assert sb["limit_up_count"] == 43
        assert sb["broken_limit_count"] == 32
        assert sb["touched_limit_total_count"] == 75
        assert abs(sb["broken_limit_ratio"] - 0.4267) < 0.001

        # 4. L2 连板天梯与最高空间标杆
        ladder = data["truth"]["ladder_tree"]
        assert len(ladder) >= 3
        top_tier = ladder[0]
        assert top_tier["height"] == 8
        assert top_tier["is_space_leader"] is True
        assert any(s["code"] == "600825" for s in top_tier["stocks"])

        # 5. L3 认知主线矩阵与 P0.1 闭环契约
        cognition = data["cognition"]
        assert "PROVISIONAL" in cognition["provisional_disclaimer"]
        mainlines = cognition["mainlines"]
        assert len(mainlines) == 5

        # 5.1 验证央国企改革 (Tier 1 核心主线)
        ygq = next(m for m in mainlines if m["sector_name"] == "央国企改革")
        assert ygq["thematic_tier"] == "TIER_1_CORE"
        assert ygq["structural_role"] == "CORE_MAINLINE"
        assert ygq["constituency"]["limit_up_count"] == 12

        # 5.2 验证电力设备与储能的 Shared-Evidence Ratio 审计
        power = next(m for m in mainlines if m["sector_name"] == "电力设备")
        assert power["thematic_tier"] == "TIER_1_CORE"
        power_affs = {a["target_sector_name"]: a for a in power["shared_evidence_affiliates"]}
        assert "储能概念" in power_affs
        assert power_affs["储能概念"]["overlap_stocks_count"] == 4
        assert abs(power_affs["储能概念"]["shared_evidence_ratio"] - 0.5714) < 0.01

        # 5.3 验证固态电池前沿科技题材保护
        battery = next(m for m in mainlines if m["sector_name"] == "固态电池")
        assert battery["is_thematic_frontier"] is True
        assert battery["constituency"]["limit_up_count"] == 5

        # 5.4 验证家电降级为 Tier 3 并附加中军断层警告
        appliance = next(m for m in mainlines if m["sector_name"] == "家用电器")
        assert appliance["thematic_tier"] == "TIER_3_WEAK_OR_ISOLATED"
        assert appliance["structural_role"] == "WEAK_ROTATION_OR_ISOLATED"
        assert appliance["constituency"]["limit_up_count"] == 2
        assert any("中军断层" in ce for ce in appliance["counter_evidence"])

        # 6. L3 血缘闭环报告恒等式核验
        la = cognition["lineage_accounting"]
        assert la["total_raw_evaluated"] == 287
        assert la["admission_rejected_count"] == 36
        assert la["admission_admitted_count"] == 251
        assert la["is_mathematically_closed"] is True


@pytest.mark.asyncio
async def test_get_canonical_market_snapshot_not_found():
    """测试请求不存在的日期返回 404"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/canonical/market-snapshot/1990-01-01")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_tactical_briefing_success():
    """测试获取 2026-10-08 操盘手内参实战战报接口 (Phase 2D.3)"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/canonical/tactical-briefing/2026-10-08")
        assert resp.status_code == 200
        data = resp.json()
        assert data["trade_date"] == "2026-10-08"
        assert data["market_state_label"] == "高位剧烈分化期"
        assert data["safety_audit_passed"] is True
        assert 200 <= len(data["tactical_briefing_text"]) <= 450
        assert "16821.09" in data["tactical_briefing_text"]
        assert "42.67%" in data["tactical_briefing_text"]
        assert len(data["key_battlegrounds"]) >= 1
        assert len(data["risk_warnings"]) >= 1
        assert len(data["next_day_observation_posts"]) >= 1
        assert len(data["briefing_fingerprint"]) == 64


@pytest.mark.asyncio
async def test_get_tactical_briefing_not_found():
    """测试不存在日期获取战报返回 404"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/canonical/tactical-briefing/1990-01-01")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
