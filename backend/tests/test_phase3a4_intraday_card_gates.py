"""
Phase 3A.4 Frontend Cockpit & IntradayDriftCard Verification Gates
==================================================================
上位依据：
1. 最高董事会裁决令：《VERDICT-PHASE3A3-3A4-20261009》
2. 《DOC-92 · Phase 3A 盘中 4 阶段动态跟踪与认知偏离实时告警系统技术设计单》

测试门禁标准：
- GATE-3A4-01: 真实 API 直穿与 Headless DOM 字符保真度门禁 (Zero Delta)
- GATE-3A4-02: 四大偏离定调状态徽章与色彩映射门禁 (MECE 完备性)
- GATE-3A4-03: 突发异动事件标签与严重度映射门禁 (Event Severity Mapping)
- GATE-3A4-04: 非交易日休市渲染与日期零漂移门禁 (MARKET_CLOSED)
- GATE-3A4-05: 安全守卫拦截 500 与安全盾牌视图脱敏门禁 (Zero Leak)
- GATE-3A4-06: 404 缺失与空状态平稳容错门禁 (Graceful Degradation)
- GATE-3A4-07: 篡改攻击与 JCS 数字指纹雪崩防御门禁 (Tamper Resistance)
- GATE-3A4-08: GATE-A 七大封闭防守词典严格白名单门禁 (Defensive Boundaries)
- GATE-3A4-09: 五位一体防伪水印对齐与审计溯源门禁 (Provenance Alignment)
"""

import sqlite3
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from backend.app.main import app
from backend.app.cognition.jcs import hash_jcs
from backend.app.core.database import async_session
from backend.app.models.market import MarketDailySnapshot
from backend.app.models.report import DailyReview
from backend.app.schemas.intraday_drift_verdict import IntradayDriftVerdict
from backend.app.services.intraday_safety_guard import ALLOWED_INTRADAY_BOUNDARY_SET
from backend.scripts.audit_phase3a4_cockpit_verification import HeadlessIntradayDriftCardDOM


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
# GATE-3A4-01: 真实 API 直穿与 Headless DOM 字符保真度门禁
# =============================================================================
@pytest.mark.asyncio
async def test_gate_3a4_01_real_api_to_dom_rendering_fidelity():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/canonical/intraday-drift/2026-10-09?time_str=10:30:00")
        assert res.status_code == 200
        data = res.json()

        # 1. 结构与指纹核验
        validated = IntradayDriftVerdict.model_validate(data)
        raw_dict = dict(data)
        reported_fp = raw_dict.pop("verdict_fingerprint")
        assert hash_jcs(raw_dict) == reported_fp

        # 2. Headless DOM 渲染核验
        dom = HeadlessIntradayDriftCardDOM(data)
        assert dom.nodes["type"] == "CARD_VIEW"
        assert dom.nodes["header"]["trade_date_badge"] == "2026-10-09"
        assert dom.nodes["header"]["stage_label"] == "10:00-11:30 主线定型期"
        assert dom.nodes["header"]["elapsed_trading_minutes"] == 60
        assert dom.nodes["header"]["outcome_badge"]["state"] == "NORMAL"
        assert len(dom.nodes["assertions"]) == 4
        assert len(dom.nodes["preservation_boundaries"]) >= 1


# =============================================================================
# GATE-3A4-02: 四大偏离定调状态徽章与色彩映射门禁 (MECE 完备性)
# =============================================================================
@pytest.mark.asyncio
async def test_gate_3a4_02_drift_states_badge_mapping():
    base_payload = {
        "verdict_id": "VERDICT-TEST",
        "trade_date": "2026-10-09",
        "evaluated_at": "2026-10-09T10:30:00+08:00",
        "stage": "STAGE_2_MORNING",
        "elapsed_trading_minutes": 60,
        "trace_id": "TRACE-TEST",
        "hypothesis_id": "HYPO-TEST",
        "hypothesis_fingerprint": "a" * 64,
        "intraday_snapshot_fingerprint": "b" * 64,
        "rule_version": "2026.10.3A2.V1",
        "threshold_config_hash": "c" * 64,
        "verdict_headline": "测试客观全貌描述",
        "detected_drift_events": [],
        "assertion_results": [],
        "preservation_boundaries": ["严格执行防守纪律，保持空仓或锁定现有仓位观察"],
        "safety_audit_passed": True,
        "verdict_fingerprint": "d" * 64,
    }

    # 1. NORMAL
    p1 = {**base_payload, "overall_drift_state": "NORMAL"}
    d1 = HeadlessIntradayDriftCardDOM(p1)
    assert d1.nodes["header"]["outcome_badge"]["color"] == "emerald"
    assert "NORMAL" in d1.nodes["header"]["outcome_badge"]["label"]

    # 2. DRIFT_WARNING
    p2 = {**base_payload, "overall_drift_state": "DRIFT_WARNING"}
    d2 = HeadlessIntradayDriftCardDOM(p2)
    assert d2.nodes["header"]["outcome_badge"]["color"] == "amber"
    assert "DRIFT_WARNING" in d2.nodes["header"]["outcome_badge"]["label"]

    # 3. CRITICAL_BREACH
    p3 = {**base_payload, "overall_drift_state": "CRITICAL_BREACH"}
    d3 = HeadlessIntradayDriftCardDOM(p3)
    assert d3.nodes["header"]["outcome_badge"]["color"] == "rose"
    assert "CRITICAL_BREACH" in d3.nodes["header"]["outcome_badge"]["label"]

    # 4. INCONCLUSIVE (休市)
    p4 = {**base_payload, "overall_drift_state": "INCONCLUSIVE", "inconclusive_reason": "MARKET_CLOSED"}
    d4 = HeadlessIntradayDriftCardDOM(p4)
    assert d4.nodes["header"]["outcome_badge"]["color"] == "slate"
    assert "MARKET CLOSED" in d4.nodes["header"]["outcome_badge"]["label"]


# =============================================================================
# GATE-3A4-03: 突发异动事件标签与严重度映射门禁
# =============================================================================
@pytest.mark.asyncio
async def test_gate_3a4_03_detected_events_severity_mapping():
    payload = {
        "verdict_id": "VERDICT-TEST",
        "trade_date": "2026-10-09",
        "evaluated_at": "2026-10-09T10:30:00+08:00",
        "stage": "STAGE_2_MORNING",
        "elapsed_trading_minutes": 60,
        "trace_id": "TRACE-TEST",
        "hypothesis_id": "HYPO-TEST",
        "hypothesis_fingerprint": "a" * 64,
        "intraday_snapshot_fingerprint": "b" * 64,
        "rule_version": "2026.10.3A2.V1",
        "threshold_config_hash": "c" * 64,
        "overall_drift_state": "CRITICAL_BREACH",
        "verdict_headline": "测试多异动并发",
        "detected_drift_events": [
            "SPACE_LEADER_COLLAPSE",
            "MAINLINE_TOTAL_REVERSAL",
            "LIQUIDITY_FLASH_DRY",
            "BREADTH_PANIC_DIVERGENCE",
        ],
        "assertion_results": [],
        "preservation_boundaries": ["严格执行防守纪律，保持空仓或锁定现有仓位观察"],
        "safety_audit_passed": True,
        "verdict_fingerprint": "d" * 64,
    }

    dom = HeadlessIntradayDriftCardDOM(payload)
    events = dom.nodes["detected_events"]
    assert len(events) == 4

    assert events[0]["label"] == "空间标杆崩塌 (CRITICAL_KILL)"
    assert events[0]["severity"] == "CRITICAL_KILL"

    assert events[1]["label"] == "主线集体倒戈 (MODERATE)"
    assert events[1]["severity"] == "MODERATE"

    assert events[2]["label"] == "量能断崖衰减 (MODERATE)"
    assert events[2]["severity"] == "MODERATE"

    assert events[3]["label"] == "炸板恐慌分化 (MODERATE)"
    assert events[3]["severity"] == "MODERATE"


# =============================================================================
# GATE-3A4-04: 非交易日休市渲染与日期零漂移门禁
# =============================================================================
@pytest.mark.asyncio
async def test_gate_3a4_04_market_closed_graceful_degradation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/canonical/intraday-drift/2026-10-11?time_str=10:30:00")
        assert res.status_code == 200
        data = res.json()

        assert data["overall_drift_state"] == "INCONCLUSIVE"
        assert data["inconclusive_reason"] == "MARKET_CLOSED"
        assert data["evaluated_at"] == "2026-10-11T10:30:00+08:00"

        dom = HeadlessIntradayDriftCardDOM(data)
        assert dom.nodes["type"] == "CARD_VIEW"
        assert dom.nodes["header"]["outcome_badge"]["state"] == "INCONCLUSIVE"
        assert dom.nodes["header"]["outcome_badge"]["label"] == "休市停牌 · MARKET CLOSED"
        assert len(dom.nodes["detected_events"]) == 0


# =============================================================================
# GATE-3A4-05: 安全守卫拦截 500 与安全盾牌视图脱敏门禁
# =============================================================================
@pytest.mark.asyncio
async def test_gate_3a4_05_safety_shield_error_view_zero_leak():
    safety_err = "ERR_INTRADAY_SAFETY_INTERCEPTION: Intraday verdict failed security & compliance guard."
    dom = HeadlessIntradayDriftCardDOM(verdict=None, error_msg=safety_err)

    assert dom.nodes["type"] == "SAFETY_SHIELD_VIEW"
    assert "ERR_INTRADAY_SAFETY_INTERCEPTION" in dom.nodes["title"]
    assert dom.nodes["zero_leak_verified"] is True
    assert dom.nodes["has_retry_button"] is True


# =============================================================================
# GATE-3A4-06: 404 缺失与空状态平稳容错门禁
# =============================================================================
@pytest.mark.asyncio
async def test_gate_3a4_06_not_found_empty_state_fallback():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/canonical/intraday-drift/9999-12-31")
        assert res.status_code == 404

        dom = HeadlessIntradayDriftCardDOM(verdict=None, is_loading=False, error_msg=None)
        assert dom.nodes["type"] == "EMPTY_VIEW"
        assert "暂无盘中认知偏离判定数据" in dom.nodes["empty_text"]


# =============================================================================
# GATE-3A4-07: 篡改攻击与 JCS 数字指纹雪崩防御门禁
# =============================================================================
@pytest.mark.asyncio
async def test_gate_3a4_07_tamper_resistance_jcs_fingerprint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/canonical/intraday-drift/2026-10-09?time_str=10:30:00")
        assert res.status_code == 200
        payload = res.json()

        # 注入 1 字符微篡改
        tampered = dict(payload)
        tampered["verdict_headline"] = tampered["verdict_headline"] + "!"
        expected_fp = tampered.pop("verdict_fingerprint")
        recomputed_fp = hash_jcs(tampered)

        assert recomputed_fp != expected_fp, "Tampered payload should have mismatched fingerprint!"


# =============================================================================
# GATE-3A4-08: GATE-A 七大封闭防守词典严格白名单门禁
# =============================================================================
def test_gate_3a4_08_gate_a_boundaries_strict_whitelist():
    assert len(ALLOWED_INTRADAY_BOUNDARY_SET) == 7
    prohibited_affirmative = ["立即买入", "建议买入", "市价买入", "逢低买入", "建议加仓", "立即卖出", "建议卖出", "全仓"]
    for b in ALLOWED_INTRADAY_BOUNDARY_SET:
        for act in prohibited_affirmative:
            assert act not in b, f"Forbidden affirmative action in boundary: {b}"


# =============================================================================
# GATE-3A4-09: 五位一体防伪水印对齐与审计溯源门禁
# =============================================================================
@pytest.mark.asyncio
async def test_gate_3a4_09_watermark_provenance_binding():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/canonical/intraday-drift/2026-10-09?time_str=10:30:00")
        assert res.status_code == 200
        data = res.json()

        dom = HeadlessIntradayDriftCardDOM(data)
        wm = dom.nodes["watermark"]

        assert wm["trace_id"] == data["trace_id"]
        assert wm["fingerprint_short"] == f"{data['verdict_fingerprint'][:16]}..."
        assert wm["hypothesis_id"] == data["hypothesis_id"]
        assert wm["rule_version"] == data["rule_version"]
        assert wm["safety_audit"] == "安全守卫拦截审查通过"
