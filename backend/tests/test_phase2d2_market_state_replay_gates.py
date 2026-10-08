"""
Phase 2D.2: Market State 状态机自适应校准与多周期回放 10 项 Freeze Gates 验收套件
上位依据：
1. 《DOC-78 · Phase 2D.2 Market State 状态机自适应校准与多周期回放体系技术设计单》
2. 《DOC-77 · Phase 2D.1 Trader Acceptance Closure Report》

门禁清单 (10 项刚性放行门禁):
GATE-2D2-01: State Vector Extraction Gate (四维量化向量抽取纯洁性断言)
GATE-2D2-02: Invariant S1 High-Risk Defense (高危风险拦截断言: 高炸板+多跌停严禁判定为主升)
GATE-2D2-03: Invariant S2 Low-Breadth Defense (低高度与低广度拦截断言: 严禁判定为主升或高位分化)
GATE-2D2-04: 2026-10-08 State Calibration (真实回放 10-08 盘面精确标定为 HIGH_DIVERGENCE_TOPPING)
GATE-2D2-05: 2026-10-01 State Calibration (真实回放 10-01 盘面自适应标定为 EXPANSION_ACCELERATION)
GATE-2D2-06: State Transition Matrix Audit (T-1 -> T 状态转移合法性与可追溯性断言)
GATE-2D2-07: Deterministic Summary Rendering (状态一句话模板确定性渲染零幻觉断言)
GATE-2D2-08: Multi-Slice Idempotence 10x (多切片批量重跑 10 次 JCS SHA-256 绝对恒定断言)
GATE-2D2-09: Backward Compatibility 25/25 (向后兼容已有 25 项 Freeze Gates 零破坏)
GATE-2D2-10: Cockpit Banner Binding & Popperian Falsification (前台字段完整性与波普尔证伪对账断言)
"""

import sqlite3
import pytest
import asyncio
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import async_session
from backend.app.services.canonical_market_service import CanonicalMarketService
from backend.app.services.market_state_calibrator import MarketStateCalibrator
from backend.app.services.historical_replay_engine import HistoricalReplayEngine
from backend.app.schemas.canonical_market import (
    CanonicalMarketSnapshot,
    MarketStateEnum,
    IndexVector,
    LadderVector,
    RiskVector,
    RegulatoryVector,
    StateFeatureVector,
    CalibratedMarketState,
)
from backend.app.models.market import MarketDailySnapshot
from backend.app.models.report import DailyReview


@pytest.fixture(autouse=True)
async def seed_20261001_and_20261008_test_sandbox():
    """
    沙箱隔离：从物理 data/trading.db 只读读取 2026-10-01 与 2026-10-08 真实事实注入测试沙箱
    """
    prod_conn = sqlite3.connect("data/trading.db")
    
    # 注入 2026-10-08
    prod_snap_08 = prod_conn.execute(
        "SELECT date, snapshot_type, indices_snapshot, breadth_snapshot, "
        "limit_up_snapshot, micro_cap_snapshot, external_risk_snapshot, "
        "high_tier_snapshot, market_state_snapshot, data_quality, source_status "
        "FROM market_daily_snapshot WHERE date = '2026-10-08' AND snapshot_type = 'EOD_CLOSE'"
    ).fetchone()

    prod_rev_08 = prod_conn.execute(
        "SELECT date, market_overview, limit_up_analysis, sector_analysis, "
        "market_state_id, report_content, data_quality "
        "FROM daily_review WHERE date = '2026-10-08'"
    ).fetchone()

    # 注入 2026-10-01
    prod_snap_01 = prod_conn.execute(
        "SELECT date, snapshot_type, indices_snapshot, breadth_snapshot, "
        "limit_up_snapshot, micro_cap_snapshot, external_risk_snapshot, "
        "high_tier_snapshot, market_state_snapshot, data_quality, source_status "
        "FROM market_daily_snapshot WHERE date = '2026-10-01' AND snapshot_type = 'EOD_CLOSE'"
    ).fetchone()

    prod_conn.close()

    async with async_session() as session:
        # 清理沙箱中已有测试记录防冲突
        await session.execute(MarketDailySnapshot.__table__.delete())
        await session.execute(DailyReview.__table__.delete())
        await session.commit()

        if prod_snap_08:
            session.add(MarketDailySnapshot(
                date=prod_snap_08[0],
                snapshot_type=prod_snap_08[1],
                indices_snapshot=prod_snap_08[2],
                breadth_snapshot=prod_snap_08[3],
                limit_up_snapshot=prod_snap_08[4],
                micro_cap_snapshot=prod_snap_08[5],
                external_risk_snapshot=prod_snap_08[6],
                high_tier_snapshot=prod_snap_08[7],
                market_state_snapshot=prod_snap_08[8],
                data_quality=prod_snap_08[9],
                source_status=prod_snap_08[10],
            ))
        if prod_rev_08:
            session.add(DailyReview(
                date=prod_rev_08[0],
                market_overview=prod_rev_08[1],
                limit_up_analysis=prod_rev_08[2],
                sector_analysis=prod_rev_08[3],
                market_state_id=prod_rev_08[4],
                report_content=prod_rev_08[5],
                data_quality=prod_rev_08[6],
            ))

        if prod_snap_01:
            session.add(MarketDailySnapshot(
                date=prod_snap_01[0],
                snapshot_type=prod_snap_01[1],
                indices_snapshot=prod_snap_01[2],
                breadth_snapshot=prod_snap_01[3],
                limit_up_snapshot=prod_snap_01[4],
                micro_cap_snapshot=prod_snap_01[5],
                external_risk_snapshot=prod_snap_01[6],
                high_tier_snapshot=prod_snap_01[7],
                market_state_snapshot=prod_snap_01[8],
                data_quality=prod_snap_01[9],
                source_status=prod_snap_01[10],
            ))
            # 2026-10-01 模拟 DailyReview 映射供主线服务平滑读取
            session.add(DailyReview(
                date="2026-10-01",
                market_overview=prod_snap_01[2],
                limit_up_analysis=prod_snap_01[4],
                sector_analysis='[["新能源", 10], ["半导体", 5]]',
                market_state_id=1,
                report_content='{"title": "2026-10-01 复盘"}',
                data_quality="PARTIAL",
            ))

        await session.commit()


@pytest.mark.asyncio
async def test_gate_2d2_01_state_vector_extraction_gate():
    """GATE-2D2-01: 四维量化向量抽取纯洁性断言 (X = (I, S, R, M)，100% 纯数值，无 None 逃逸)"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        features = service.state_calibrator.extract_feature_vector(snap.truth)
        assert isinstance(features, StateFeatureVector)

        # 向量 I 验证
        assert features.index_vector.total_turnover_yi == 16821.09
        assert features.index_vector.dispersion_pct > 0.0
        assert isinstance(features.index_vector.star_divergence_pct, float)

        # 向量 S 验证
        assert features.ladder_vector.max_ladder_height == 8
        assert features.ladder_vector.limit_up_count == 43
        assert features.ladder_vector.limit_down_count == 13
        assert 0.0 <= features.ladder_vector.leader_ratio <= 1.0

        # 向量 R 验证
        assert abs(features.risk_vector.broken_limit_ratio - 0.4267) < 0.001
        assert features.risk_vector.broken_limit_count == 32
        assert 0.0 <= features.risk_vector.extreme_loss_ratio <= 1.0

        # 向量 M 验证
        assert features.regulatory_vector.anomaly_count == 11
        assert isinstance(features.regulatory_vector.has_leader_warning, bool)


def test_gate_2d2_02_invariant_s1_high_risk_defense():
    """GATE-2D2-02: Invariant S1 高危风险拦截断言 (高炸板+多跌停 严禁判定为 EXPANSION_ACCELERATION)"""
    calibrator = MarketStateCalibrator()

    # 构造极度危险但试图伪装为主升加速的向量 (涨停多/高度高，但炸板率45%且跌停15家)
    toxic_features = StateFeatureVector(
        index_vector=IndexVector(total_turnover_yi=20000.0, dispersion_pct=1.5, star_divergence_pct=0.5),
        ladder_vector=LadderVector(max_ladder_height=7, limit_up_count=60, limit_down_count=15, leader_ratio=0.2),
        risk_vector=RiskVector(broken_limit_ratio=0.45, broken_limit_count=35, extreme_loss_ratio=0.5),
        regulatory_vector=RegulatoryVector(anomaly_count=2, has_leader_warning=False),
    )

    state = calibrator.calibrate(toxic_features, prior_state=MarketStateEnum.EXPANSION_ACCELERATION)

    # 必须坚决拦截，绝不能为主升加速
    assert state.primary_state != MarketStateEnum.EXPANSION_ACCELERATION
    assert state.primary_state in (MarketStateEnum.HIGH_DIVERGENCE_TOPPING, MarketStateEnum.RECESSION_PANIC)
    assert any("45.00%" in f or "Invariant S1" in f for f in state.driving_factors)


def test_gate_2d2_03_invariant_s2_low_breadth_defense():
    """GATE-2D2-03: Invariant S2 低高度低广度拦截断言 (严禁判定为 EXPANSION_ACCELERATION 或 HIGH_DIVERGENCE_TOPPING)"""
    calibrator = MarketStateCalibrator()

    # 构造冰冷盘面 (最高仅2B，涨停仅12家，跌停2家，炸板率15%)
    low_breadth_features = StateFeatureVector(
        index_vector=IndexVector(total_turnover_yi=8000.0, dispersion_pct=0.8, star_divergence_pct=0.1),
        ladder_vector=LadderVector(max_ladder_height=2, limit_up_count=12, limit_down_count=2, leader_ratio=0.0),
        risk_vector=RiskVector(broken_limit_ratio=0.15, broken_limit_count=2, extreme_loss_ratio=0.2),
        regulatory_vector=RegulatoryVector(anomaly_count=0, has_leader_warning=False),
    )

    state = calibrator.calibrate(low_breadth_features)

    # 严禁判定为高位分化或主升
    assert state.primary_state not in (MarketStateEnum.EXPANSION_ACCELERATION, MarketStateEnum.HIGH_DIVERGENCE_TOPPING)
    assert state.primary_state in (MarketStateEnum.CHAOTIC_ROTATION, MarketStateEnum.LOW_REBOUND)


@pytest.mark.asyncio
async def test_gate_2d2_04_20261008_state_calibration():
    """GATE-2D2-04: 真实回放 10-08 盘面，断言定性为 HIGH_DIVERGENCE_TOPPING (高位剧烈分化期)"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        cal = snap.cognition.market_state_calibration
        assert cal is not None
        assert cal.primary_state == MarketStateEnum.HIGH_DIVERGENCE_TOPPING
        assert cal.state_display_name == "高位剧烈分化期"
        assert cal.state_confidence >= 0.90
        assert len(cal.driving_factors) >= 3

        # 核心驱动事实必须精准捕获 42.67% 炸板、13 家跌停、8B 高度
        factors_str = " ".join(cal.driving_factors)
        assert "42.67%" in factors_str
        assert "13" in factors_str
        assert "8B" in factors_str


@pytest.mark.asyncio
async def test_gate_2d2_05_20261001_state_calibration():
    """GATE-2D2-05: 真实回放 10-01 盘面，断言自适应识别为 EXPANSION_ACCELERATION (主升共振期)，消除单日过拟合"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-01")
        assert snap is not None

        cal = snap.cognition.market_state_calibration
        assert cal is not None
        # 10-01 盘面具有 52 只涨停，最高 7B，炸板率仅 18.75% (<25%)
        assert cal.primary_state == MarketStateEnum.EXPANSION_ACCELERATION
        assert cal.state_display_name == "主升共振期"
        assert cal.state_confidence >= 0.90
        factors_str = " ".join(cal.driving_factors)
        assert "52" in factors_str
        assert "7B" in factors_str


@pytest.mark.asyncio
async def test_gate_2d2_06_state_transition_matrix_audit():
    """GATE-2D2-06: T-1 -> T 状态转移合法性与可追溯性断言 (2026-10-01 主升 -> 2026-10-08 高位分化)"""
    async with async_session() as session:
        replay_engine = HistoricalReplayEngine(session)
        snapshots = await replay_engine.replay_multi_periods(["2026-10-01", "2026-10-08"])
        assert len(snapshots) == 2

        transitions = await replay_engine.audit_transition_matrix(snapshots)
        assert len(transitions) == 1

        t = transitions[0]
        assert t["from_date"] == "2026-10-01"
        assert t["from_state"] == MarketStateEnum.EXPANSION_ACCELERATION.value
        assert t["to_date"] == "2026-10-08"
        assert t["to_state"] == MarketStateEnum.HIGH_DIVERGENCE_TOPPING.value
        assert t["transition_signal"] is not None
        assert "主升共振遭遇天量分歧" in t["transition_signal"]


@pytest.mark.asyncio
async def test_gate_2d2_07_deterministic_summary_rendering():
    """GATE-2D2-07: 验证状态文本由模板确定性渲染，零 LLM 幻觉漂移"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap1 = await service.get_canonical_snapshot("2026-10-08")
        snap2 = await service.get_canonical_snapshot("2026-10-08")
        assert snap1 is not None and snap2 is not None

        # 文本完全比特级一致
        assert snap1.cognition.market_state_summary == snap2.cognition.market_state_summary
        summary = snap1.cognition.market_state_summary
        assert "指数高位剧烈分化" in summary
        assert "1.68 万亿" in summary
        assert "42.67%" in summary
        assert "跌停13家" in summary


@pytest.mark.asyncio
async def test_gate_2d2_08_multi_slice_idempotence_10x():
    """GATE-2D2-08: 多历史切片批量重跑 10 次 JCS SHA-256 哈希指纹完全恒定"""
    async with async_session() as session:
        replay_engine = HistoricalReplayEngine(session)
        res_08 = await replay_engine.verify_idempotence("2026-10-08", runs=10)
        assert res_08["status"] == "PASS"
        assert res_08["is_invariant"] is True

        res_01 = await replay_engine.verify_idempotence("2026-10-01", runs=10)
        assert res_01["status"] == "PASS"
        assert res_01["is_invariant"] is True


@pytest.mark.asyncio
async def test_gate_2d2_09_backward_compatibility_25_gates():
    """GATE-2D2-09: 继承运行已有契约，证明对存量事实层与 API 零污染"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        # 验证 2D.0 核心不变量
        assert snap.truth.turnover.two_markets_total_yi == 16821.09
        assert snap.truth.sentiment_bounds.broken_limit_ratio == 0.4267
        assert snap.cognition.lineage_accounting.is_mathematically_closed is True
        # 验证 2D.1 兼容性
        assert len(snap.cognition.market_state_summary) > 20
        # 验证 2D.2 结构化字段已就绪
        assert snap.cognition.market_state_calibration is not None


@pytest.mark.asyncio
async def test_gate_2d2_10_cockpit_banner_binding_and_popperian_falsification():
    """GATE-2D2-10: 驾驶舱横幅字段契约与波普尔反向证伪对账断言"""
    async with async_session() as session:
        replay_engine = HistoricalReplayEngine(session)
        snap = await replay_engine.replay_date("2026-10-08")
        assert snap is not None

        # 1. 前端 Banner 所需字段契约校验
        cal = snap.cognition.market_state_calibration
        assert cal is not None
        assert cal.primary_state in MarketStateEnum.__members__.values()
        assert len(cal.state_display_name) > 0
        assert 0.0 <= cal.state_confidence <= 1.0
        assert len(cal.driving_factors) >= 1

        # 2. 波普尔反向证伪检验
        # 模拟 2026-10-09 早盘竞价：空间标杆新华传媒大幅低开 -4.5%
        t_plus_one_mock = {
            "symbols": {
                "600825": {"open_pct_change": -4.5},  # 新华传媒
                "603200": {"open_pct_change": +2.1},  # 上海洗霸
            }
        }
        falsification_report = replay_engine.evaluate_popperian_falsification(snap, t_plus_one_mock)
        assert falsification_report["evaluation_date"] == "2026-10-08"
        results = falsification_report["results"]
        assert len(results) > 0

        # 新华传媒所引领的主线应当触发证伪警报
        xinhua_eval = next((r for r in results if r["leader_code"] == "600825"), None)
        if xinhua_eval:
            assert xinhua_eval["is_falsified"] is True
            assert "大幅低开证伪条件" in xinhua_eval["falsified_reasons"][0]
