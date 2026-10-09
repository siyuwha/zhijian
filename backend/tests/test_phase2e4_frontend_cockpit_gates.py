"""
Phase 2E.4 Frontend Cockpit & Bidding Falsification Card Verification Gates
=============================================================================
测试门禁标准：
1. GATE-2E4-01: 真实 API 直穿与 Headless DOM 字符保真度门禁 (Zero Delta)
2. GATE-2E4-02: 非交易日休市渲染与日期零漂移门禁 (MARKET_CLOSED)
3. GATE-2E4-03: 篡改攻击与 JCS 数字指纹雪崩防御门禁 (Tamper Resistance)
4. GATE-2E4-04: 降级与空状态平稳容错门禁 (Graceful Degradation)
5. GATE-2E4-05: 五位一体防伪水印对齐与安全守卫全覆盖门禁
"""

import re
import sqlite3
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from backend.app.main import app
from backend.app.cognition.jcs import hash_jcs
from backend.app.core.database import async_session
from backend.app.models.market import MarketDailySnapshot
from backend.app.models.report import DailyReview
from backend.scripts.audit_phase2e4_api_dom_verification import HeadlessBiddingFalsificationDOM


@pytest.fixture(autouse=True)
async def seed_20261008_test_sandbox():
    """
    在隔离的 pytest SQLite 沙盒数据库中装载 2026-10-08 物理基准数据
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
# GATE-2E4-01: 真实 API 直穿与 Headless DOM 字符保真度门禁
# =============================================================================
@pytest.mark.asyncio
async def test_gate_2e4_01_real_api_to_dom_fidelity():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
        assert res.status_code == 200
        data = res.json()

        # 1. 真实字段结构完整性
        assert data["trade_date"] == "2026-10-09"
        assert data["overall_verdict"] in ["CONFIRMED", "DIVERGENT", "FALSIFIED", "INCONCLUSIVE"]
        assert len(data["verdict_headline"]) > 10

        # 2. Headless DOM 渲染
        dom = HeadlessBiddingFalsificationDOM(data)
        assert dom.nodes["type"] == "CARD_VIEW"
        assert dom.nodes["header"]["trade_date_badge"] == "2026-10-09"
        assert dom.nodes["header"]["headline_text"] == data["verdict_headline"]
        assert dom.nodes["assertions_count"] == len(data["assertion_results"])

        # 3. 字符保真度检验 (Rendered text contains headline & trace_id & fp)
        rendered = dom.get_rendered_text_content()
        assert data["verdict_headline"] in rendered
        assert data["trace_id"] in rendered
        assert data["hypothesis_id"] in rendered


# =============================================================================
# GATE-2E4-02: 非交易日休市渲染与日期零漂移门禁
# =============================================================================
@pytest.mark.asyncio
async def test_gate_2e4_02_market_closed_rendering_no_drift():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 请求周六 (2026-10-10)
        res = await client.get("/api/v1/canonical/auction-falsification/2026-10-10")
        assert res.status_code == 200
        data = res.json()

        assert data["overall_verdict"] == "INCONCLUSIVE"
        assert data["inconclusive_reason"] == "MARKET_CLOSED"
        assert data["trade_date"] == "2026-10-10"

        dom = HeadlessBiddingFalsificationDOM(data)
        assert dom.nodes["type"] == "CARD_VIEW"
        assert "MARKET CLOSED" in dom.nodes["header"]["outcome_badge"]["label"]
        assert dom.nodes["assertions_count"] == 0  # 休市日无断言展开
        assert len(dom.nodes["action_boundaries"]) >= 1


# =============================================================================
# GATE-2E4-03: 篡改攻击与 JCS 数字指纹雪崩防御门禁
# =============================================================================
@pytest.mark.asyncio
async def test_gate_2e4_03_tamper_avalanche_defense():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
        data = res.json()

        original_fp = data["verdict_fingerprint"]
        # 验证原始指纹正确性
        clone = dict(data)
        clone.pop("verdict_fingerprint", None)
        assert original_fp == hash_jcs(clone)

        # 篡改 1 标点字符
        tampered = dict(clone)
        tampered["verdict_headline"] = tampered["verdict_headline"] + "！"
        tampered_fp = hash_jcs(tampered)

        assert original_fp != tampered_fp, "Tampered text MUST alter fingerprint!"


# =============================================================================
# GATE-2E4-04: 降级与空状态平稳容错门禁
# =============================================================================
def test_gate_2e4_04_graceful_degradation():
    # 1. Loading State
    dom_load = HeadlessBiddingFalsificationDOM(None, is_loading=True)
    assert dom_load.nodes["type"] == "LOADING_VIEW"
    assert dom_load.nodes["has_spinner"] is True

    # 2. Error State
    dom_err = HeadlessBiddingFalsificationDOM(None, error_msg="服务内部异常 (500)")
    assert dom_err.nodes["type"] == "ERROR_VIEW"
    assert dom_err.nodes["has_retry_button"] is True

    # 3. Empty State
    dom_empty = HeadlessBiddingFalsificationDOM(None)
    assert dom_empty.nodes["type"] == "EMPTY_VIEW"


# =============================================================================
# GATE-2E4-05: 五位一体防伪水印对齐与安全守卫全覆盖门禁
# =============================================================================
@pytest.mark.asyncio
async def test_gate_2e4_05_watermark_anchors_and_safety_audit():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/canonical/auction-falsification/2026-10-09")
        data = res.json()

        # 5-in-1 锚点正则
        assert re.match(r"^HYPO-\d{4}-\d{2}-\d{2}-[a-f0-9]{8,12}$", data["hypothesis_id"])
        assert re.match(r"^VERDICT-\d{4}-\d{2}-\d{2}-[a-f0-9]{8,12}$", data["verdict_id"])
        assert re.match(r"^TRACE-\d{4}-\d{2}-\d{2}-TO-\d{4}-\d{2}-\d{2}-AUCTION-POPPER-.*$", data["trace_id"])
        assert re.match(r"^[a-f0-9]{64}$", data["verdict_fingerprint"])
        assert re.match(r"^[a-f0-9]{64}$", data["auction_fingerprint"])
        assert re.match(r"^[a-f0-9]{64}$", data["threshold_config_hash"])

        assert data["safety_audit_passed"] is True
