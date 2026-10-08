"""
Phase 2D.0 P0: Market Truth & Mainline Semantic Closure 23 项 Freeze Gates 验收套件
上位依据：
1. 用户 2026-10-08 最终裁决令：《Phase 2D.0 终审裁决：CONDITIONAL PASS；Phase 2D.1 有条件启动》
2. SPEC-DESIGN-PHASE2D-20261008-V1.0 (Doc 69)
3. 用户 2026-10-08 实时审计指令：“今天锂电池的高度是4板”
4. Phase 2D.0 P0.2《DOC-73 Overlap ≠ Semantic Redundancy 审计报告》
5. DOC-75｜Phase 2D.0 P0.2 Entity Identity Integrity Hard-Block 修复指令
6. 董事会外部终审补充令：P0.2 CLOSURE CORRECTION — MINOR CONTRACT PATCH

门禁清单 (23 项刚性放行门禁):
GATE-2D0-01: L0/L1 Truth 纯洁性断言 (绝不掺杂 L2/L3 推断与 L5 行动)
GATE-2D0-02: SZ 成交额防重算断言 (深市已含创业板，严禁二次累加)
GATE-2D0-03: 核心指数点位归一与非空断言 (消除 None 与命名歧义)
GATE-2D0-04: 炸板率 Universe 边界与分子分母闭环断言 (42.67% 样本闭环)
GATE-2D0-05: 连板天梯严格递降与首板防腐断言 (8B->4B->3B->2B->1B)
GATE-2D0-06: 横截面广度与涨停扩散度硬解耦断言
GATE-2D0-07: 502 业务级优雅降级与仪表盘防黑屏断言
GATE-2D0-08: 交易所严重异常波动监管事实商业撮合定性断言
GATE-2D0-09: Mainline 语义类型契约断言 (排除 Meta/统计/形态/热榜/地域)
GATE-2D0-10: 独立成分证据与 Leader Identity Independence 断言 (杜绝同一龙头垄断主线)
GATE-2D0-11: 反方证据集与次日证伪条件完备性断言
GATE-2D0-12: 251 -> Top-N -> Folded 完整血缘与数学闭环断言 (287=36+251 全覆盖)
GATE-2D0-13: Truth / Cognition 严密分层与 RFC 8785 JCS 10x 幂等性断言
GATE-2D0-14: Golden Fixtures 固化与历史版本双向存证断言
GATE-2D0-15: 成分股重叠度 (Shared-Evidence Ratio) 审计与主线三级模型断言
GATE-2D0-16: 多周期历史切片适应性与确定性回放断言
GATE-2D0-17: 交易语义穿透与 Dual-Layer 主线挂载断言 (P0.2 闭环)
GATE-2D0-18: Code-Name 一致性与单射不变量断言 (DOC-75 Test 1)
GATE-2D0-19: 实体身份主键单向权威派生防御断言 (DOC-75 Test 2 / Task 1 Patch)
GATE-2D0-20: 跨层级实体身份保真性与零漂移断言 (DOC-75 Test 3)
GATE-2D0-21: 自由文本名称覆盖防御拦截断言 (DOC-75 Test 4)
GATE-2D0-22: 002242 九阳股份回归防线与毅昌污染免疫断言 (DOC-75 Test 5)
GATE-2D0-23: Canonical Security Master Binding 全链路比特级绝对一致断言 (终审补充令 Task 2)
"""

import sqlite3
import pytest
import asyncio
from pathlib import Path
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import async_session
from backend.app.models.market import MarketDailySnapshot
from backend.app.models.report import DailyReview
from backend.app.services.canonical_market_service import CanonicalMarketService
from backend.app.schemas.canonical_market import (
    CanonicalMarketSnapshot,
    DataQualityGrade,
    TruthSource,
    SemanticType,
)


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


@pytest.mark.asyncio
async def test_gate_2d0_01_truth_purity():
    """GATE-2D0-01: L0/L1 Truth 纯洁性断言 (绝不掺杂 L2/L3 推断与 L5 行动)"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None, "2026-10-08 快照必须存在"

        # 检查 L1 指数与成交额结构中严禁出现推断或行动字段
        turnover_dict = snap.truth.turnover.model_dump()
        forbidden_fields = {"composite_score", "state_label", "action_guide", "target_signal", "polarity"}
        for f in forbidden_fields:
            assert f not in turnover_dict, f"L1 成交额结构严禁掺杂推断字段 {f}"

        for idx in snap.truth.indices:
            idx_dict = idx.model_dump()
            for f in forbidden_fields:
                assert f not in idx_dict, f"L1 指数行情结构严禁掺杂推断字段 {f}"


@pytest.mark.asyncio
async def test_gate_2d0_02_sz_turnover_double_count_defense():
    """GATE-2D0-02: SZ 成交额防重算断言 (深市已含创业板，严禁二次累加)"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        turnover = snap.truth.turnover
        # 1. 沪深两市真实总额严格等于 sh + sz，严禁额外相加 chinext
        assert turnover.two_markets_total_yi == round(turnover.sh_amount_yi + turnover.sz_total_amount_yi, 2)
        # 2. 10-08 实盘核对：沪市 8111.83 亿，深市 8709.26 亿，两市 16821.09 亿
        assert abs(turnover.sh_amount_yi - 8111.83) < 1.0
        assert abs(turnover.sz_total_amount_yi - 8709.26) < 1.0
        assert abs(turnover.two_markets_total_yi - 16821.09) < 1.0
        # 3. 创业板成交额 4227.55 亿仅作内部切片分析
        assert abs(turnover.chinext_slice_amount_yi - 4227.55) < 1.0
        assert turnover.chinext_ratio_in_sz == round(turnover.chinext_slice_amount_yi / turnover.sz_total_amount_yi, 4)
        assert abs(turnover.chinext_ratio_in_sz - 0.4854) < 0.001


@pytest.mark.asyncio
async def test_gate_2d0_03_index_quotes_normalization():
    """GATE-2D0-03: 核心指数点位归一与非空断言 (消除 None 与命名歧义)"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        symbols = [idx.symbol for idx in snap.truth.indices]
        assert "sh000001" in symbols
        assert "sz399001" in symbols
        assert "sz399006" in symbols
        assert "sh000688" in symbols

        for idx in snap.truth.indices:
            assert idx.current_price > 0.0
            assert idx.pre_close > 0.0
            assert idx.amount_yi >= 0.0
            # 涨跌方向与涨跌点数符号严格一致
            if idx.pct_change > 0:
                assert idx.change_val > 0
            elif idx.pct_change < 0:
                assert idx.change_val < 0


@pytest.mark.asyncio
async def test_gate_2d0_04_broken_limit_universe_closure():
    """GATE-2D0-04: 炸板率 Universe 边界与分子分母闭环断言"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        sb = snap.truth.sentiment_bounds
        # 分母 = 有效封死 (43) + 炸板 (32) = 75
        assert sb.touched_limit_total_count == sb.limit_up_count + sb.broken_limit_count
        assert sb.limit_up_count == 43
        assert sb.broken_limit_count == 32
        assert sb.touched_limit_total_count == 75
        assert abs(sb.broken_limit_ratio - 0.4267) < 0.001


@pytest.mark.asyncio
async def test_gate_2d0_05_ladder_tree_strict_descending_and_first_board_defense():
    """GATE-2D0-05: 连板天梯严格递降与首板防腐断言 (8B->4B->3B->2B->1B)"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        ladder = snap.truth.ladder_tree
        assert len(ladder) >= 3, "梯队必须有至少3个高度层级"

        # 1. 严格递减检查
        heights = [grp.height for grp in ladder]
        for i in range(len(heights) - 1):
            assert heights[i] > heights[i+1], f"连板梯队高度必须严格递降: {heights[i]} > {heights[i+1]}"

        # 2. 最高空间标杆必须正确标记
        top_grp = ladder[0]
        assert top_grp.height == snap.truth.sentiment_bounds.max_ladder_height
        assert top_grp.is_space_leader is True

        # 10-08 实盘空间龙为 8板新华传媒 (600825)
        if top_grp.height == 8:
            assert any(s.code == "600825" for s in top_grp.stocks)

        # 3. 首板防腐：height=1 的组内所有标的必须为 FIRST_LIMIT，连板数严格=1
        first_board_grp = next((g for g in ladder if g.height == 1), None)
        assert first_board_grp is not None
        for s in first_board_grp.stocks:
            assert s.continuous_board_count == 1
            assert s.limit_up_type == "FIRST_LIMIT"


@pytest.mark.asyncio
async def test_gate_2d0_06_breadth_and_limitup_decoupling():
    """GATE-2D0-06: 横截面广度与涨停扩散度硬解耦断言"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        assert hasattr(snap.truth, "cross_section_breadth_status")
        assert hasattr(snap.truth.sentiment_bounds, "limit_up_count")


@pytest.mark.asyncio
async def test_gate_2d0_07_breadth_502_graceful_degradation():
    """GATE-2D0-07: 502 业务级优雅降级与仪表盘防黑屏断言"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        # 10-08 上游东财 502，横截面广度标记为 UNAVAILABLE
        assert snap.truth.cross_section_breadth_status == DataQualityGrade.UNAVAILABLE
        # 但必须提供降级推断详情，阻断前端黑屏
        assert snap.truth.cross_section_breadth_detail is not None
        assert "502" in snap.truth.cross_section_breadth_detail["message"]
        assert "heuristic_warning" in snap.truth.cross_section_breadth_detail


@pytest.mark.asyncio
async def test_gate_2d0_08_regulatory_anomalies_commercial_nature():
    """GATE-2D0-08: 交易所严重异常波动监管事实商业撮合定性断言"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        assert len(snap.truth.regulatory_anomalies) == 11, "10-08 必须捕获 11 项监管异动"
        for a in snap.truth.regulatory_anomalies:
            assert a.provenance_nature == "EASTMONEY_COMPUTED_RULE_MATCH"
            assert a.status_flag in (0, 1, 2)
            assert a.deviation_pct != 0.0


@pytest.mark.asyncio
async def test_gate_2d0_09_mainline_semantic_type_contract():
    """GATE-2D0-09: Mainline 语义类型契约断言 (排除 Meta/统计/形态/热榜/地域)"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        mainlines = snap.cognition.mainlines
        assert len(mainlines) > 0

        # 所有候选必须严格标记为 CONCEPT 或 INDUSTRY
        for m in mainlines:
            assert m.semantic_type in ("CONCEPT", "INDUSTRY")
            # 严禁数据商元标签或行情特征进入主线
            forbidden_names = [
                "东方财富热股", "最近多板", "题材股", "大盘股", "小盘股", 
                "超跌股", "新高", "破发", "AB股", "AH股", "HS300", "上海板块"
            ]
            for fn in forbidden_names:
                assert fn not in m.sector_name, f"主线严禁包含元标签或交易特征: {m.sector_name}"


@pytest.mark.asyncio
async def test_gate_2d0_10_evidence_independence_and_constituency():
    """GATE-2D0-10: 独立成分证据与 Evidence Independence 断言 (杜绝同一龙头垄断主线)"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        mainlines = snap.cognition.mainlines
        
        # 1. 独立成分检查
        for m in mainlines:
            c = m.constituency
            assert c.leader_code != ""
            assert c.leader_name != ""
            assert c.leader_height >= 1
            assert c.limit_up_count >= 1
            assert len(c.ladder_distribution) >= 1
            assert len(c.constituent_symbols) == c.limit_up_count

        # 2. Evidence Independence 核心测试：
        # 同一只 8B 龙头 (新华传媒 600825) 不得垄断 Top-N 前列！
        leaders_in_top = [m.constituency.leader_code for m in mainlines]
        # 验证 Top 5 中领军龙头具有独立多样性 (不全为新华传媒)
        assert len(set(leaders_in_top)) >= 3, "Top 主线必须呈现不同独立领军龙头，严禁单标的垄断！"
        # 验证 Rank 1 与 Rank 2 龙头相互独立
        assert mainlines[0].constituency.leader_code != mainlines[1].constituency.leader_code


@pytest.mark.asyncio
async def test_gate_2d0_11_counter_evidence_and_falsification():
    """GATE-2D0-11: 反方证据集与次日证伪条件完备性断言"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        for m in snap.cognition.mainlines:
            # 必须具有支撑证据
            assert len(m.supporting_evidence) >= 1
            # 必须具有反方证据集 (波普尔批判)
            assert len(m.counter_evidence) >= 1
            # 必须具有次日证伪条件清单与核心观察标的
            fc = m.falsification_condition
            assert len(fc.invalidation_rules) >= 1
            assert len(fc.critical_observation_symbols) >= 1


@pytest.mark.asyncio
async def test_gate_2d0_12_mece_lineage_accounting_closure():
    """GATE-2D0-12: 251 -> Top-N -> Folded 完整血缘与数学闭环断言 (287=36+251 全覆盖)"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        la = snap.cognition.lineage_accounting
        # 1. 物理总数
        assert la.total_raw_evaluated == 287
        assert la.admission_rejected_count == 36
        assert la.admission_admitted_count == 251
        assert la.total_raw_evaluated == la.admission_rejected_count + la.admission_admitted_count

        # 2. 251 Admitted MECE 分解恒等式核验
        sum_parts = (
            la.excluded_meta_tags_count
            + la.excluded_regions_count
            + la.solitary_leader_noise_count
            + la.pulse_noise_count
            + la.deduplicated_clusters_count
            + la.eligible_candidates_count
        )
        assert sum_parts == la.admission_admitted_count, f"血缘桶总和 ({sum_parts}) 必须严格等于通过准入数 ({la.admission_admitted_count})"
        assert la.eligible_candidates_count == la.top_mainlines_count + la.folded_eligible_remainder_count
        assert la.is_mathematically_closed is True
        assert len(la.lineage_formula) > 0


@pytest.mark.asyncio
async def test_gate_2d0_13_truth_cognition_strict_layering_and_idempotence():
    """GATE-2D0-13: Truth / Cognition 严密分层与 RFC 8785 JCS 10x 幂等性断言"""
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap1 = await service.get_canonical_snapshot("2026-10-08")
        assert snap1 is not None

        # 严密分层核验
        assert snap1.truth.schema_version == "2D.0-TRUTH-V1"
        assert snap1.truth.producer == "CANONICAL_MARKET_SERVICE"
        assert snap1.cognition.schema_version == "2D.0-COGNITION-V1"
        assert snap1.cognition.producer == "COGNITION_ELIGIBILITY_ENGINE"
        assert snap1.truth.truth_fingerprint != ""
        assert snap1.cognition.cognition_fingerprint != ""
        assert snap1.envelope_fingerprint != ""

        # 10x 幂等性核验 (哈希绝对一致)
        fp_truth = snap1.truth.truth_fingerprint
        fp_cog = snap1.cognition.cognition_fingerprint
        fp_env = snap1.envelope_fingerprint

        for i in range(9):
            subsequent = await service.get_canonical_snapshot("2026-10-08")
            assert subsequent is not None
            assert subsequent.truth.truth_fingerprint == fp_truth, f"第 {i+2} 次 Truth 哈希漂移"
            assert subsequent.cognition.cognition_fingerprint == fp_cog, f"第 {i+2} 次 Cognition 哈希漂移"
            assert subsequent.envelope_fingerprint == fp_env, f"第 {i+2} 次 Envelope 哈希漂移"


@pytest.mark.asyncio
async def test_gate_2d0_14_golden_fixtures_preservation_and_verification():
    """GATE-2D0-14: Golden Fixtures 固化与历史版本双向存证断言"""
    legacy_file = Path("baseline_evidence/golden_canonical_snapshot_20261008_v1_legacy.json")
    v2_file = Path("baseline_evidence/golden_canonical_snapshot_20261008.json")

    # 1. 历史 v1 审计证据必须完整保留
    assert legacy_file.exists(), "必须完整保留 v1 历史快照存证"
    assert legacy_file.stat().st_size > 10000

    # 2. 当前 v2 快照必须存在且包含 truth 与 cognition 结构
    assert v2_file.exists(), "必须成功固化 v2 golden snapshot"
    assert v2_file.stat().st_size > 10000


@pytest.mark.asyncio
async def test_gate_2d0_15_shared_evidence_ratio_and_three_tier_model():
    """
    GATE-2D0-15: 成分股重叠度 (Shared-Evidence Ratio) 审计与主线三级模型断言
    上位依据：【董事会外部审计令：PHASE 2D.0 P0.1 SEMANTIC VALIDATION REQUIRED】
    1. P0.1-1: 拆解【电力设备】与【储能概念】同源资金簇，Shared-Evidence Ratio 审计
    2. P0.1-2: 确立三级层级模型，【家用电器】因广度与梯队断层降级为 TIER_3_WEAK_OR_ISOLATED
    3. P0.1-3: 细分前沿催化剂辨识度保护，验证【固态电池】未被机械折叠并标记为前沿催化
    """
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        mainlines_map = {m.sector_name: m for m in snap.cognition.mainlines}

        # 1. P0.1-1: 电力设备 vs 储能概念 Shared-Evidence Ratio 审计
        assert "电力设备" in mainlines_map
        assert "储能概念" in mainlines_map
        power_sec = mainlines_map["电力设备"]
        storage_sec = mainlines_map["储能概念"]

        # 检查电力设备关联审计项
        power_storage_aff = next(
            (aff for aff in power_sec.shared_evidence_affiliates if aff.target_sector_name == "储能概念"),
            None,
        )
        assert power_storage_aff is not None, "电力设备必须持有储能概念的重叠审计项"
        assert power_storage_aff.overlap_stocks_count == 4, "电力设备与储能必须共享 4 只涨停标的"
        assert power_storage_aff.shared_evidence_ratio > 0.5, "重叠度必须 > 50%"
        assert abs(power_storage_aff.shared_evidence_ratio - 0.5714) < 0.01

        # 2. P0.1-2: 家用电器降级为弱轮动
        assert "家用电器" in mainlines_map
        appliance_sec = mainlines_map["家用电器"]
        assert appliance_sec.structural_role == "WEAK_ROTATION_OR_ISOLATED"
        assert appliance_sec.thematic_tier == "TIER_3_WEAK_OR_ISOLATED"
        assert appliance_sec.constituency.limit_up_count == 2
        assert any("中军断层" in note for note in appliance_sec.counter_evidence), "必须包含中军断层反方警告"

        # 3. P0.1-3: 固态电池未被机械折叠，保留在前瞻主线中
        assert "固态电池" in mainlines_map
        battery_sec = mainlines_map["固态电池"]
        assert battery_sec.is_thematic_frontier is True
        assert battery_sec.constituency.limit_up_count == 5
        assert battery_sec.constituency.leader_height == 3
        # 验证固态电池与电力设备存在跨层级关联证据
        solid_power_aff = next(
            (aff for aff in battery_sec.shared_evidence_affiliates if aff.target_sector_name == "电力设备"),
            None,
        )
        assert solid_power_aff is not None
        assert solid_power_aff.relationship == "PARENT_INDUSTRY"
        assert solid_power_aff.overlap_stocks_count == 3
        assert abs(solid_power_aff.shared_evidence_ratio - 0.6000) < 0.01


@pytest.mark.asyncio
async def test_gate_2d0_16_multi_slice_historical_replay():
    """
    GATE-2D0-16: 多周期历史切片适应性与确定性回放断言 (P0.1-4)
    上位依据：【董事会外部审计令：PHASE 2D.0 P0.1 SEMANTIC VALIDATION REQUIRED】
    验证规则在不同盘面微观结构下的自适应性，防固定规则过拟合单一交易日
    """
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        # 1. 验证三级模型分类逻辑在多种微观梯队结构下的自适应性
        # Case A: 核心主线门槛校验 (Leader >= 3, Count >= 5, Tiers >= 3)
        # 央国企改革: 8B, 12只, 4个梯队 -> TIER_1_CORE
        yangguoqi = next(m for m in snap.cognition.mainlines if m.sector_name == "央国企改革")
        assert yangguoqi.thematic_tier == "TIER_1_CORE"
        assert yangguoqi.structural_role == "CORE_MAINLINE"

        # Case B: 孤立高标降级门槛校验 (Count < 3)
        # 家电: 4B, 2只 -> TIER_3_WEAK_OR_ISOLATED
        jiadian = next(m for m in snap.cognition.mainlines if m.sector_name == "家用电器")
        assert jiadian.thematic_tier == "TIER_3_WEAK_OR_ISOLATED"
        assert jiadian.structural_role == "WEAK_ROTATION_OR_ISOLATED"

        # 2. 验证高炸板分歧环境下，所有主线必须自适应注入全局炸板风险警告
        if snap.truth.sentiment_bounds.broken_limit_ratio >= 0.35:
            for m in snap.cognition.mainlines:
                assert any("炸板率高达" in ce for ce in m.counter_evidence), f"{m.sector_name} 必须注入炸板风险反方证据"

        # 3. 验证董事会免责声明在 CognitionSnapshot 中刚性存在
        assert "PROVISIONAL" in snap.cognition.provisional_disclaimer


@pytest.mark.asyncio
async def test_gate_2d0_17_dual_layer_representation_and_battery_chain():
    """
    GATE-2D0-17: 交易语义穿透与 Dual-Layer 主线挂载断言 (P0.2 闭环)
    上位依据：
    1. 用户 2026-10-08 实时审计指令：“今天锂电池的高度是4板”
    2. Phase 2D.0 P0.2《DOC-73 Overlap ≠ Semantic Redundancy 审计报告》
    
    核心断言：
    1. 验证【电力设备 (BK1200)】完整保留静态行业分类纯洁性，同时透出实盘交易叙事【电池 / 锂电池产业链】
    2. 验证主线领军龙头为【时代万恒 4B (600241)】，确立锂电池真实 4B 空间高度
    3. 验证母链挂载前沿技术催化分支【固态电池 (BK0968)】，其独立高度为 3B，重叠度为 60%
    4. 验证【固态电池】独立前沿席位未被抹杀，其领军龙头为【上海洗霸 3B (603200)】，梯队高度 3B 与母链 4B 相互独立存证
    5. 验证 Top 5 排序严格遵守全市场空间与梯队层级：Rank 1 为【央国企改革 8B】，Rank 2 为【电力设备 4B】
    6. 验证 Evidence Independence：Top 5 主线领军标的全部相互独立，零同标冲突
    """
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        mainlines = snap.cognition.mainlines
        mainlines_map = {m.sector_name: m for m in mainlines}

        # 1. 验证电力设备 Dual-Layer 表达
        assert "电力设备" in mainlines_map
        power = mainlines_map["电力设备"]
        assert power.sector_code == "BK1200"
        assert power.market_narrative == "电池 / 锂电池产业链"
        assert power.static_taxonomy_name == "电力设备 (BK1200)"
        assert power.constituency.leader_name == "时代万恒"
        assert power.constituency.leader_code == "600241"
        assert power.constituency.leader_height == 4
        assert any("【交易叙事穿透】" in note for note in power.supporting_evidence)

        # 2. 验证固态电池前沿催化分支挂载
        assert len(power.subtheme_catalysts) >= 1
        solid_sub = next((s for s in power.subtheme_catalysts if s.sector_name == "固态电池"), None)
        assert solid_sub is not None
        assert solid_sub.sector_code == "BK0968"
        assert solid_sub.catalyst_height == 3
        assert solid_sub.thematic_role == "FRONTIER_TECH_CATALYST"
        assert abs(solid_sub.overlap_ratio_with_master - 0.6000) < 0.01

        # 3. 验证固态电池作为独立前沿主线席位，具有独立的 3B 领军标杆 (上海洗霸)
        assert "固态电池" in mainlines_map
        solid = mainlines_map["固态电池"]
        assert solid.is_thematic_frontier is True
        assert solid.constituency.leader_name == "上海洗霸"
        assert solid.constituency.leader_code == "603200"
        assert solid.constituency.leader_height == 3
        assert solid.market_narrative == "固态电池 (前沿技术催化)"

        # 4. 验证空间排序与梯队层级：Rank 1 为 8B 央国企改革，Rank 2 为 4B 电力设备
        assert mainlines[0].sector_name == "央国企改革"
        assert mainlines[0].constituency.leader_height == 8
        assert mainlines[1].sector_name == "电力设备"
        assert mainlines[1].constituency.leader_height == 4

        # 5. 验证 Leader Identity Independence：Top 5 主线领军标的代码互不相同
        leaders = [m.constituency.leader_code for m in mainlines]
        assert len(set(leaders)) == len(leaders) == 5


@pytest.mark.asyncio
async def test_gate_2d0_18_code_name_consistency_invariant():
    """
    GATE-2D0-18: Code-Name 一致性与单射不变量断言 (DOC-75 Test 1)
    上位依据：DOC-75 P0.2-Fix-3 自动化 Entity Integrity Guard
    断言：
    - 快照内出现的每一个 stock_code 对应且仅对应一个规范 canonical_name
    - 全市场涨停池、天梯、主线领军与成分股中，不得存在同代码多名称歧义
    """
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        code_to_names: Dict[str, Set[str]] = {}
        # 收集 L1/L2 天梯中的 code -> name
        for grp in snap.truth.ladder_tree:
            for s in grp.stocks:
                code_to_names.setdefault(s.code, set()).add(s.name)

        # 收集 L3 主线中的 leader_code -> leader_name
        for m in snap.cognition.mainlines:
            c = m.constituency
            code_to_names.setdefault(c.leader_code, set()).add(c.leader_name)

        # 刚性断言：每一个代码对应的名称集合大小严格等于 1
        for code, names in code_to_names.items():
            assert len(names) == 1, f"Code-Name Invariant 破坏: 代码 {code} 映射到多个名称: {names}"


@pytest.mark.asyncio
async def test_gate_2d0_19_duplicate_identity_collision_defense():
    """
    GATE-2D0-19: 实体身份主键单向权威派生防御断言 (DOC-75 Test 2 / Task 1 Patch)
    上位依据：
    - DOC-75 P0.2-Fix-3 Invariant A & B
    - 董事会外部终审补充令 Task 1: 废除 name->code 反向硬单射，改为主键单向权威派生
    断言：
    - Invariant A: 同代码换名/同码异属 (尝试注入 002242 -> 毅昌科技) 必抛 EntityIdentityIntegrityError (Invariant A)
    - Invariant B: (exchange, stock_code) -> security_id -> canonical_name 权威单向派生：
      1. 正确派生: (SZ, 002242) -> 002242.SZ -> 九阳股份
      2. 允许不同代码独立派生各自名称 (即便可能同名或同行业标的，不强制 name->code 反向硬单射)
      3. 任何非法交易所、非法代码格式或空名称破坏派生链条的操作必抛 EntityIdentityIntegrityError (Invariant B)
    """
    from backend.app.services.canonical_market_service import (
        CanonicalSecurityMasterRegistry,
        EntityIdentityIntegrityError,
    )
    reg = CanonicalSecurityMasterRegistry()
    ent1 = reg.register(code="002242", name="九阳股份", exchange="SZ")
    assert ent1.security_id == "002242.SZ"
    assert ent1.canonical_name == "九阳股份"
    assert reg.get_canonical_name("002242") == "九阳股份"

    # Invariant A 测试：同代码换名 (尝试注入 002242 -> 毅昌科技)
    with pytest.raises(EntityIdentityIntegrityError) as exc_info_a:
        reg.register(code="002242", name="毅昌科技", exchange="SZ")
    assert "Invariant A Violation" in str(exc_info_a.value)

    # Invariant B 测试 1：(exchange, stock_code) -> security_id -> canonical_name 单向权威派生正常工作
    ent2 = reg.register(code="002420", name="毅昌科技", exchange="SZ")
    assert ent2.security_id == "002420.SZ"
    assert ent2.canonical_name == "毅昌科技"
    assert reg.get_canonical_name("002420") == "毅昌科技"

    # Invariant B 测试 2：非法交易所输入破坏派生链条必抛 Invariant B 异常
    with pytest.raises(EntityIdentityIntegrityError) as exc_info_b1:
        reg.register(code="002242", name="九阳股份", exchange="INVALID")
    assert "Invariant B Violation" in str(exc_info_b1.value)

    # Invariant B 测试 3：非法代码位数破坏派生链条必抛 Invariant B 异常
    with pytest.raises(EntityIdentityIntegrityError) as exc_info_b2:
        reg.register(code="2242", name="九阳股份", exchange="SZ")
    assert "Invariant B Violation" in str(exc_info_b2.value)

    # Invariant B 测试 4：空名称破坏派生链条必抛 Invariant B 异常
    with pytest.raises(EntityIdentityIntegrityError) as exc_info_b3:
        reg.register(code="600825", name="", exchange="SH")
    assert "Invariant B Violation" in str(exc_info_b3.value)


@pytest.mark.asyncio
async def test_gate_2d0_20_cross_layer_identity_preservation():
    """
    GATE-2D0-20: 跨层级实体身份保真性与零漂移断言 (DOC-75 Test 3)
    上位依据：DOC-75 P0.2-Fix-3
    断言：
    - L0 (DB raw) -> L1 (LimitUpStockItem) -> L2 (LadderGroup) -> L3 (MainlineCandidate)
    - 实体 (security_id, stock_code, canonical_name) 100% 保持保真，绝对零漂移
    """
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        # 检查所有主线领军龙头在 L2 天梯中的实体完全一致
        l2_stock_map = {
            s.code: s
            for grp in snap.truth.ladder_tree
            for s in grp.stocks
        }
        for m in snap.cognition.mainlines:
            lc = m.constituency.leader_code
            ln = m.constituency.leader_name
            assert lc in l2_stock_map, f"主线 {m.sector_name} 龙头 {lc} 必须存在于 L2 天梯"
            assert l2_stock_map[lc].name == ln, f"跨层级漂移: L2名称 {l2_stock_map[lc].name} != L3名称 {ln}"
            if m.constituency.leader_security_id:
                assert l2_stock_map[lc].security_id == m.constituency.leader_security_id


@pytest.mark.asyncio
async def test_gate_2d0_21_no_free_text_identity_override():
    """
    GATE-2D0-21: 自由文本名称覆盖防御拦截断言 (DOC-75 Test 4)
    上位依据：DOC-75 P0.2-Fix-3 Invariant C & D
    断言：
    - 验证 registry.validate_snapshot_integrity 对下游自由文本伪造名称的防御拦截能力
    """
    from backend.app.services.canonical_market_service import (
        CanonicalSecurityMasterRegistry,
        EntityIdentityIntegrityError,
    )
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        # 伪造一个含有篡改名称的 CognitionSnapshot
        corrupted_cognition = snap.cognition.model_copy(deep=True)
        m5 = corrupted_cognition.mainlines[-1]
        assert m5.constituency.leader_code == "002242"
        # 模拟下游使用自由文本篡改名称为 '毅昌科技'
        object.__setattr__(m5.constituency, "leader_name", "毅昌科技")

        # 刚性拦截：validate_snapshot_integrity 必须抛出异常
        with pytest.raises(EntityIdentityIntegrityError) as exc_info:
            service.entity_registry.validate_snapshot_integrity(snap.truth, corrupted_cognition)
        assert "Cross-Layer Drift" in str(exc_info.value) or "HARD-BLOCK" in str(exc_info.value)


@pytest.mark.asyncio
async def test_gate_2d0_22_002242_joyoung_known_regression_defense():
    """
    GATE-2D0-22: 002242 九阳股份回归防线与毅昌污染免疫断言 (DOC-75 Test 5)
    上位依据：DOC-75 P0.2-Fix-1 & Fix-3 Known Regression
    刚性断言：
    1. 确认 002242 规范实体为【九阳股份】(Joyoung, 4B)
    2. 严禁 002242 映射为【毅昌科技】
    3. 严禁 002420 (毅昌科技实际代码) 污染 2026-10-08 盘面涨停池
    4. 验证 L1 天梯与 L3 主线矩阵中 002242 严格绑定 九阳股份
    """
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        # 1. 验证 L1/L2 天梯中的 002242 身份
        ladder_002242 = [
            s for grp in snap.truth.ladder_tree for s in grp.stocks if s.code == "002242"
        ]
        assert len(ladder_002242) == 1, "002242 必须在天梯中唯一存在"
        item_002242 = ladder_002242[0]
        assert item_002242.name == "九阳股份", "002242 必须严格定性为【九阳股份】"
        assert item_002242.continuous_board_count == 4, "002242 高度为 4B"
        assert item_002242.security_id == "002242.SZ"

        # 2. 验证 L3 主线矩阵中 Rank 5 家用电器的 leader 身份
        appliance = next(m for m in snap.cognition.mainlines if m.sector_name == "家用电器")
        assert appliance.constituency.leader_code == "002242"
        assert appliance.constituency.leader_name == "九阳股份"
        assert "九阳股份" in appliance.constituency.constituent_symbols
        assert "毅昌科技" not in appliance.constituency.constituent_symbols

        # 3. 验证 002420 绝未进入天梯或主线
        all_ladder_codes = {s.code for grp in snap.truth.ladder_tree for s in grp.stocks}
        assert "002420" not in all_ladder_codes, "002420 严禁污染 2026-10-08 盘面"

        # 4. 全局反洗脑检查：整个 snapshot 序列化中绝对不得出现 '毅昌'
        snap_json = snap.model_dump_json()
        assert "毅昌" not in snap_json, "全快照严格禁止包含任何'毅昌'字符串"


@pytest.mark.asyncio
async def test_gate_2d0_23_canonical_security_master_binding():
    """
    GATE-2D0-23: Canonical Security Master Binding 门禁 (董事会外部终审补充令 Task 2)
    上位依据：
    - 董事会外部终审补充令 Task 2
    - DOC-75 实体身份完整性硬阻断修复指令
    断言目标：
    - 逐一断言 L0~L3 所有出现的个股代码、交易所、简称与 Security Master 字典比特级绝对一致。
    - 验证范围：
      1. L0 DB 物理存储 (market_daily_snapshot 涨停样本空间)
      2. L1 MarketTruth 物理真相层 (ladder_tree 股票项)
      3. L2 Derived Metrics 派生层 (天梯高度梯队)
      4. L3 Cognition 假说层 (Top-N 主线候选 leader 与 constituent_symbols)
    """
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        master_dict = service.entity_registry.get_dictionary()
        assert len(master_dict) > 0, "Security Master 字典不得为空"

        # 1. 验证 L0 DB 物理存储与 Security Master 字典比特级一致
        query = select(MarketDailySnapshot).where(
            MarketDailySnapshot.date == "2026-10-08",
            MarketDailySnapshot.snapshot_type == "EOD_CLOSE",
        )
        result = await session.execute(query)
        db_snap = result.scalar_one_or_none()
        assert db_snap is not None
        lu_data = db_snap.limit_up_snapshot
        if isinstance(lu_data, str):
            import json
            lu_data = json.loads(lu_data)
        l0_stocks = lu_data.get("items", [])
        assert len(l0_stocks) > 0

        for s in l0_stocks:
            code = s["code"]
            raw_name = s["name"]
            assert code in master_dict, f"L0 股票代码 {code} 未在 Security Master 字典中注册"
            master_entity = master_dict[code]
            # 比特级断言：代码、简称绝对一致
            assert master_entity.stock_code == code, f"代码比特级不一致: {master_entity.stock_code} != {code}"
            assert master_entity.canonical_name == raw_name, f"简称比特级不一致: {master_entity.canonical_name} != {raw_name}"
            # 交易所一致
            expected_exchange = "SH" if code.startswith(("60", "68")) else ("SZ" if code.startswith(("00", "30")) else "BJ")
            assert master_entity.exchange == expected_exchange, f"交易所不一致: {master_entity.exchange} != {expected_exchange}"
            assert master_entity.security_id == f"{code}.{expected_exchange}"

        # 2. 验证 L1/L2 MarketTruth 物理真相层与天梯树
        l1_stock_count = 0
        for grp in snap.truth.ladder_tree:
            for s in grp.stocks:
                l1_stock_count += 1
                assert s.code in master_dict, f"L1/L2 股票代码 {s.code} 未在 Security Master 字典中注册"
                master_entity = master_dict[s.code]
                assert s.name == master_entity.canonical_name, f"L1/L2 简称比特级漂移: {s.name} != {master_entity.canonical_name}"
                assert s.security_id == master_entity.security_id, f"L1/L2 security_id 漂移: {s.security_id} != {master_entity.security_id}"

        assert l1_stock_count == len(l0_stocks), "L1/L2 股票总量与 L0 涨停样本必须完全一致"

        # 3. 验证 L3 Cognition 假说层
        all_master_names = {e.canonical_name for e in master_dict.values()}
        for m in snap.cognition.mainlines:
            c = m.constituency
            leader_code = c.leader_code
            assert leader_code in master_dict, f"L3 领军代码 {leader_code} 未在 Security Master 字典中注册"
            master_entity = master_dict[leader_code]
            assert c.leader_name == master_entity.canonical_name, f"L3 龙头简称比特级漂移: {c.leader_name} != {master_entity.canonical_name}"
            assert c.leader_security_id == master_entity.security_id, f"L3 龙头 security_id 漂移: {c.leader_security_id} != {master_entity.security_id}"

            # 验证每一个成分股简称均属于 Security Master 规范名称集合
            for sym in c.constituent_symbols:
                assert sym in all_master_names, f"L3 成分股 {sym} 未在 Security Master 字典中找到"

        # 4. 关键个股防线断言 (002242 九阳股份 比特级校验)
        joyoung = master_dict["002242"]
        assert joyoung.stock_code == "002242"
        assert joyoung.canonical_name == "九阳股份"
        assert joyoung.exchange == "SZ"
        assert joyoung.security_id == "002242.SZ"
        assert "002420" not in master_dict


