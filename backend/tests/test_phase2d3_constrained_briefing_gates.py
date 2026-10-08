"""
Phase 2D.3-C: Constrained Briefing Generation & Multi-Period Adaptation Gates
=============================================================================
门禁清单：
- GATE-2D3-10: Tactical Briefing Generation Gate (2026-10-08 分化期战报与 10x 幂等性)
- GATE-2D3-11: Multi-Period Adaptation Gate (2026-10-01 主升共振期文风与盘面自适应)
- GATE-2D3-12: Prompt Speech Boundary Adherence Gate (提示词发言边界与红线禁区完整性)
- GATE-2D3-13: Downstream Exception & Fallback Resilience Gate (LLM 异常与毒化降级容灾)
"""

import json
import sqlite3
import pytest
from pathlib import Path

from backend.app.core.database import async_session
from backend.app.models.report import DailyReview
from backend.app.models.market import MarketDailySnapshot
from backend.app.schemas.narrative_context import NarrativeContextContract
from backend.app.schemas.tactical_briefing import TacticalBriefingReport
from backend.app.services.canonical_market_service import CanonicalMarketService
from backend.app.services.narrative_context_service import NarrativeContextExtractor
from backend.app.services.constrained_briefing_generator import (
    ConstrainedBriefingGenerator,
    BriefingPromptBuilder,
)
from backend.app.cognition.jcs import hash_jcs


GOLDEN_CONTEXT_PATH = Path("baseline_evidence/golden_narrative_context_20261008.json")


@pytest.fixture(scope="module")
def golden_context_1008() -> NarrativeContextContract:
    assert GOLDEN_CONTEXT_PATH.exists(), f"Golden context missing: {GOLDEN_CONTEXT_PATH}"
    with open(GOLDEN_CONTEXT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return NarrativeContextContract(**data)


@pytest.fixture(autouse=True)
async def seed_multi_period_db():
    """沙箱环境数据注入 (同时注入 2026-10-08 与 2026-10-01)"""
    prod_conn = sqlite3.connect("data/trading.db")
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

    prod_snap_01 = prod_conn.execute(
        "SELECT date, snapshot_type, indices_snapshot, breadth_snapshot, "
        "limit_up_snapshot, micro_cap_snapshot, external_risk_snapshot, "
        "high_tier_snapshot, market_state_snapshot, data_quality, source_status "
        "FROM market_daily_snapshot WHERE date = '2026-10-01' AND snapshot_type = 'EOD_CLOSE'"
    ).fetchone()

    prod_conn.close()

    async with async_session() as session:
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


# =============================================================================
# GATE-2D3-10: Tactical Briefing Generation Gate (2026-10-08)
# =============================================================================
def test_gate_2d3_10_tactical_briefing_generation_1008(golden_context_1008: NarrativeContextContract):
    """
    GATE-2D3-10: 2026-10-08 分化期战报生成与 10x 幂等性门禁
    - 针对 10-08 数据成功生成战报；
    - 100% 通过 BriefingSafetyGuard (safety_audit_passed=True, is_fallback_mode=False)；
    - 准确体现 16821.09 亿, 42.67% 炸板率, 8B 空间板, 13 跌停, 11 异动；
    - 连续 10 次生成 JCS SHA-256 签名完全恒定。
    """
    generator = ConstrainedBriefingGenerator()
    rep = generator.generate_briefing(golden_context_1008)

    assert rep.trade_date == "2026-10-08"
    assert rep.market_state_label == "高位剧烈分化期"
    assert rep.safety_audit_passed is True
    assert rep.is_fallback_mode is False
    assert 200 <= len(rep.tactical_briefing_text) <= 450

    # 验证关键量化事实全部体现在战报中
    text = rep.tactical_briefing_text
    assert "16821.09" in text
    assert "42.67%" in text
    assert "8B" in text
    assert "新华传媒" in text
    assert "13" in text
    assert "11" in text
    assert "毅昌科技" not in text
    assert "高位兑现" in text or "高位剧烈分化期" in text

    # 验证 10x JCS 哈希恒定
    hashes = []
    for _ in range(10):
        r = generator.generate_briefing(golden_context_1008)
        hashes.append(r.briefing_fingerprint)
    assert len(set(hashes)) == 1
    assert hashes[0] == rep.briefing_fingerprint


# =============================================================================
# GATE-2D3-11: Multi-Period Adaptation Gate (2026-10-01)
# =============================================================================
@pytest.mark.asyncio
async def test_gate_2d3_11_multi_period_adaptation_1001():
    """
    GATE-2D3-11: 多周期回放自适应门禁 (2026-10-01 主升加速日)
    - 验证流水线在主升加速日环境下能正确映射主升共振期；
    - 文风自适应呈现良性、进攻、做多通道定调；
    - 100% 通过安全审查。
    """
    async with async_session() as session:
        cms = CanonicalMarketService(session)
        snap = await cms.get_canonical_snapshot("2026-10-01")
        assert snap is not None

        extractor = NarrativeContextExtractor()
        ctx = extractor.extract_context(snap)
        assert ctx.cognition_layer.market_state.primary_state.value == "EXPANSION_ACCELERATION"

        generator = ConstrainedBriefingGenerator()
        rep = generator.generate_briefing(ctx)

        assert rep.trade_date == "2026-10-01"
        assert rep.market_state_label == "主升共振期"
        assert rep.safety_audit_passed is True
        assert rep.is_fallback_mode is False

        text = rep.tactical_briefing_text
        assert "主升共振期" in text
        assert "14379.89" in text
        assert "18.75%" in text
        assert "7B" in text
        assert "良性" in text or "多头动能" in text


# =============================================================================
# GATE-2D3-12: Prompt Speech Boundary Adherence Gate
# =============================================================================
def test_gate_2d3_12_prompt_speech_boundary_adherence(golden_context_1008: NarrativeContextContract):
    """
    GATE-2D3-12: 提示词发言边界与红线禁区完整性门禁
    - 验证 System Prompt 严格包含所有允许声明类型与禁止声明类型；
    - 验证包含 002242 -> 九阳股份 实体单射约束与毅昌科技严禁警示；
    - 验证包含禁止一切买入/卖出/满仓/抄底等 L5 指令警示；
    - 验证 User Prompt 纯洁呈现 FACT, DERIVED, COGNITION 三层结构。
    """
    sys_prompt = BriefingPromptBuilder.build_system_prompt(golden_context_1008)
    usr_prompt = BriefingPromptBuilder.build_user_prompt(golden_context_1008)

    # 1. 验证允许声明类型枚举
    for claim in golden_context_1008.speech_boundary.allowed_claim_types:
        assert claim in sys_prompt

    # 2. 验证禁止声明类型枚举
    for claim in golden_context_1008.speech_boundary.forbidden_claim_types:
        assert claim in sys_prompt

    # 3. 验证 002242 与毅昌科技强防御条款
    assert "002242" in sys_prompt
    assert "九阳股份" in sys_prompt
    assert "毅昌科技" in sys_prompt

    # 4. 验证 L5 指令与价格预测禁区
    assert "买入" in sys_prompt
    assert "满仓" in sys_prompt
    assert "目标价" in sys_prompt

    # 5. 验证 User Prompt 呈现三层物理事实
    assert "【L0/L1 事实层 (FACT)】" in usr_prompt
    assert "【L2 衍生结构层 (DERIVED)】" in usr_prompt
    assert "【L3 顶层认知假说层 (COGNITION)】" in usr_prompt
    assert "16821.09" in usr_prompt
    assert "42.67%" in usr_prompt
    assert "8B" in usr_prompt


# =============================================================================
# GATE-2D3-13: Downstream Exception & Fallback Resilience Gate
# =============================================================================
def test_gate_2d3_13_downstream_exception_and_fallback_resilience(golden_context_1008: NarrativeContextContract):
    """
    GATE-2D3-13: LLM 故障与毒化降级容灾门禁
    - 场景 1: LLM 客户端抛出 Timeout / ConnectionError 异常 -> 优雅捕获并触发保底；
    - 场景 2: LLM 返回毒化文本 (含买入指令与目标价) -> BriefingSafetyGuard 硬拦截并触发保底；
    - 两种异常场景下均确保返回合规 TacticalBriefingReport (is_fallback_mode=True, safety_audit_passed=True)。
    """
    # 场景 1: LLM 超时模拟
    def mock_timeout_llm(sys: str, usr: str) -> str:
        raise TimeoutError("LLM Gateway Timeout: Upstream LLM failed to respond in 5000ms")

    generator_timeout = ConstrainedBriefingGenerator(llm_client=mock_timeout_llm)
    rep_timeout = generator_timeout.generate_briefing(golden_context_1008)

    assert rep_timeout.is_fallback_mode is True
    assert "LLM Client Exception" in (rep_timeout.fallback_reason or "")
    assert "TimeoutError" in (rep_timeout.fallback_reason or "")
    assert rep_timeout.safety_audit_passed is True

    # 场景 2: LLM 返回违规指令毒化文本
    def mock_poisoned_llm(sys: str, usr: str) -> str:
        return (
            "【大势定调】两市总成交额达 16821.09 亿元。全市场高位剧烈分化。"
            "【主线与梯队】核心战场为央国企改革。龙头新华传媒8B。"
            "【风险与负反馈】真实炸板率高达 42.67%，收盘跌停 13 家，严重异动 11 家。"
            "【明日推演与防守红线】建议次日集合竞价满仓买入核心龙头时代万恒，目标价 35 元。"
        )

    generator_poison = ConstrainedBriefingGenerator(llm_client=mock_poisoned_llm)
    rep_poison = generator_poison.generate_briefing(golden_context_1008)

    assert rep_poison.is_fallback_mode is True
    assert "IllegalDirectiveViolation" in (rep_poison.fallback_reason or "")
    assert rep_poison.safety_audit_passed is True
    # 确认最终发布的战报中彻底清除了“满仓买入”与“目标价”
    assert "满仓" not in rep_poison.tactical_briefing_text
    assert "目标价" not in rep_poison.tactical_briefing_text
