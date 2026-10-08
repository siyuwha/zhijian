"""
Phase 2D.3-B: Briefing Safety Guard & Fallback Engine Gates
===========================================================
门禁清单：
- GATE-2D3-05: Numerical Fidelity Guard Gate (数字保真度审查)
- GATE-2D3-06: Security Master & 002242 Integrity Guard Gate (实体身份与 002242 防御)
- GATE-2D3-07: Illegal Trading Directive Interception Gate (交易指令与禁区拦截)
- GATE-2D3-08: Deterministic Fallback Engine Gate (保底引擎时延与 10x 幂等性)
- GATE-2D3-09: End-to-End Fallback Activation Gate (双轨制无感降级全链路集成)
"""

import json
import time
import pytest
from pathlib import Path

from backend.app.schemas.narrative_context import NarrativeContextContract
from backend.app.schemas.tactical_briefing import (
    TacticalBriefingReport,
    SafetyAuditResult,
)
from backend.app.services.briefing_safety_guard import (
    BriefingSafetyGuard,
    FORBIDDEN_DIRECTIVE_TERMS,
)
from backend.app.services.briefing_fallback_engine import DeterministicBriefingFallbackEngine
from backend.app.services.tactical_briefing_service import TacticalBriefingService
from backend.app.cognition.jcs import hash_jcs


GOLDEN_CONTEXT_PATH = Path("baseline_evidence/golden_narrative_context_20261008.json")


@pytest.fixture(scope="module")
def golden_context() -> NarrativeContextContract:
    assert GOLDEN_CONTEXT_PATH.exists(), f"Golden context missing: {GOLDEN_CONTEXT_PATH}"
    with open(GOLDEN_CONTEXT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return NarrativeContextContract(**data)


# =============================================================================
# GATE-2D3-05: Numerical Fidelity Guard Gate
# =============================================================================
def test_gate_2d3_05_numerical_fidelity_guard(golden_context: NarrativeContextContract):
    """
    GATE-2D3-05: 数字保真度审查门禁
    - 验证真实数据生成的文本通过审查；
    - 针对成交额、炸板率、最高板高度、跌停数、严重异动数的篡改，必须 100% 拦截并抛出违规。
    """
    guard = BriefingSafetyGuard()
    engine = DeterministicBriefingFallbackEngine(guard)

    # 1. 真实保底战报文本必须 100% 通过数字保真度检查
    valid_report = engine.generate_fallback_briefing(golden_context)
    res_valid = guard.audit(valid_report, golden_context)
    assert res_valid.passed is True
    assert len(res_valid.violations) == 0

    base_text = valid_report.tactical_briefing_text

    # 2. 模拟篡改成交额：将 16821.09 亿元 篡改为 19500.00 亿元
    fake_text_turnover = base_text.replace("16821.09 亿元", "19500.00 亿元")
    res_fake_to = guard.audit(fake_text_turnover, golden_context)
    assert res_fake_to.passed is False
    assert any("Total turnover" in v and "diverges from true fact" in v for v in res_fake_to.violations)

    # 3. 模拟篡改炸板率：将 42.67% 篡改为 18.50%
    fake_text_broken = base_text.replace("42.67%", "18.50%")
    res_fake_broken = guard.audit(fake_text_broken, golden_context)
    assert res_fake_broken.passed is False
    assert any("Broken limit ratio" in v and "diverges from derived fact" in v for v in res_fake_broken.violations)

    # 4. 模拟篡改最高连板高度：将 8B 篡改为 10B
    fake_text_height = base_text.replace("8B【新华传媒】", "10B【新华传媒】")
    res_fake_height = guard.audit(fake_text_height, golden_context)
    assert res_fake_height.passed is False
    assert any("Space leader max height" in v and "diverges from true fact" in v for v in res_fake_height.violations)

    # 5. 模拟篡改跌停家数：将 跌停 13 家 篡改为 跌停 35 家
    fake_text_down = base_text.replace("跌停 13 家", "跌停 35 家")
    res_fake_down = guard.audit(fake_text_down, golden_context)
    assert res_fake_down.passed is False
    assert any("Limit down count" in v and "diverges from true fact" in v for v in res_fake_down.violations)

    # 6. 模拟篡改严重异动家数：将 11 家 篡改为 28 家
    fake_text_reg = base_text.replace("11 家", "28 家")
    res_fake_reg = guard.audit(fake_text_reg, golden_context)
    assert res_fake_reg.passed is False
    assert any("Regulatory anomaly count" in v and "diverges from true fact" in v for v in res_fake_reg.violations)


# =============================================================================
# GATE-2D3-06: Security Master & 002242 Integrity Guard Gate
# =============================================================================
def test_gate_2d3_06_security_master_and_002242_defense(golden_context: NarrativeContextContract):
    """
    GATE-2D3-06: 实体身份单射与 002242 防御门禁
    - 任何出现 '毅昌科技' 的文本必须立即硬拦截；
    - 任何出现未在 Security Master 认证的野码 (如 688999) 必须立即硬拦截；
    - 允许合法的 002242 (九阳股份) 通过。
    """
    guard = BriefingSafetyGuard()
    engine = DeterministicBriefingFallbackEngine(guard)
    valid_report = engine.generate_fallback_briefing(golden_context)
    base_text = valid_report.tactical_briefing_text

    # 1. 注入 '毅昌科技' -> 必须硬拦截
    poisoned_text_yichang = base_text + " 观察 002242 毅昌科技 后续企稳。"
    res_yichang = guard.audit(poisoned_text_yichang, golden_context)
    assert res_yichang.passed is False
    assert any("毅昌科技" in v for v in res_yichang.violations)

    # 2. 注入未经认证的虚假代码 '688999' -> 必须拦截
    poisoned_text_fake_code = base_text + " 关注标的 688999 走势。"
    res_fake_code = guard.audit(poisoned_text_fake_code, golden_context)
    assert res_fake_code.passed is False
    assert any("Unregistered security code" in v and "688999" in v for v in res_fake_code.violations)

    # 3. 正常出现已认证个股代码 (如 002242 九阳股份) -> 允许通过
    # 将合法的 002242 放入文本
    valid_with_code = base_text.replace("【新华传媒】", "【新华传媒】(家电梯队含002242九阳股份)")
    res_valid_code = guard.audit(valid_with_code, golden_context)
    # 不得报 EntityIdentityViolation
    assert not any("EntityIdentityViolation" in v for v in res_valid_code.violations)


# =============================================================================
# GATE-2D3-07: Illegal Trading Directive Interception Gate
# =============================================================================
def test_gate_2d3_07_illegal_trading_directive_interception(golden_context: NarrativeContextContract):
    """
    GATE-2D3-07: 交易指令与发言禁区拦截门禁
    - 拦截一切 L5 操作指令 ('买入', '满仓', '建仓', '抄底', '割肉', '追高', '梭哈')；
    - 拦截预测具体买卖点位/目标价；
    - 拦截重复累加创业板成交额。
    """
    guard = BriefingSafetyGuard()
    engine = DeterministicBriefingFallbackEngine(guard)
    valid_report = engine.generate_fallback_briefing(golden_context)
    base_text = valid_report.tactical_briefing_text

    # 1. 测试常用交易指令词拦截
    dangerous_phrases = [
        "建议次日集合竞价买入核心龙头时代万恒",
        "激进资金可满仓冲锋固态电池龙头",
        "破位标的建议果断清仓割肉离场",
        "可于分时低点抄底低吸做T",
        "不可盲目追高打板买入",
    ]
    for phrase in dangerous_phrases:
        test_text = base_text + f" 【操作提示】{phrase}。"
        res = guard.audit(test_text, golden_context)
        assert res.passed is False, f"Failed to intercept dangerous phrase: {phrase}"
        assert any("IllegalDirectiveViolation" in v for v in res.violations)

    # 2. 预测具体目标价拦截
    target_price_text = base_text + " 新华传媒目标价 25.50 元。"
    res_tp = guard.audit(target_price_text, golden_context)
    assert res_tp.passed is False
    assert any("Unverified price target" in v for v in res_tp.violations)

    # 3. 创业板重复累加会计违规拦截
    double_count_text = base_text + " 两市总成交额加上创业板突破两万亿元。"
    res_dc = guard.audit(double_count_text, golden_context)
    assert res_dc.passed is False
    assert any("Redundant double-count" in v for v in res_dc.violations)


# =============================================================================
# GATE-2D3-08: Deterministic Fallback Engine Gate
# =============================================================================
def test_gate_2d3_08_deterministic_fallback_engine(golden_context: NarrativeContextContract):
    """
    GATE-2D3-08: 确定性保底引擎时延与 10x 幂等性门禁
    - 单次执行时间严格 <= 50ms；
    - 连续 10 次执行 JCS 哈希签名绝对一致 (SHA-256 不变量)；
    - 生成结果 100% 通过 BriefingSafetyGuard 审查；
    - 字符数在 150 ~ 600 区间，结构化字段齐备。
    """
    guard = BriefingSafetyGuard()
    engine = DeterministicBriefingFallbackEngine(guard)

    # 1. 验证极速生成性能 (< 50ms)
    t0 = time.time()
    first_report = engine.generate_fallback_briefing(golden_context)
    dt_ms = (time.time() - t0) * 1000
    assert dt_ms < 50.0, f"Fallback generation latency too high: {dt_ms:.2f}ms >= 50ms"

    # 2. 验证文本规格
    text_len = len(first_report.tactical_briefing_text)
    assert 150 <= text_len <= 600, f"Text length out of bounds: {text_len}"
    assert len(first_report.key_battlegrounds) >= 1
    assert len(first_report.risk_warnings) >= 1
    assert len(first_report.next_day_observation_posts) >= 1
    assert first_report.is_fallback_mode is True
    assert first_report.safety_audit_passed is True

    # 3. 验证 10x JCS 哈希幂等性
    hashes = []
    for _ in range(10):
        rep = engine.generate_fallback_briefing(golden_context)
        hashes.append(rep.briefing_fingerprint)

    assert len(set(hashes)) == 1, f"JCS fingerprint drift detected in fallback engine: {set(hashes)}"
    assert hashes[0] == first_report.briefing_fingerprint


# =============================================================================
# GATE-2D3-09: End-to-End Fallback Activation Gate
# =============================================================================
def test_gate_2d3_09_end_to_end_fallback_activation(golden_context: NarrativeContextContract):
    """
    GATE-2D3-09: 双轨制战报服务无感降级全链路门禁
    - 场景 A: 候选文本通过审查 -> 正式发布 (is_fallback_mode=False)；
    - 场景 B: 候选文本包含指令/幻觉 -> 审查拦截 -> 自动触发保底引擎 (is_fallback_mode=True, 记录原因)；
    - 场景 C: 无候选文本输入 -> 直接输出确定性战报；
    - 无论何种场景，最终对外发布的战报均 100% 具备 safety_audit_passed=True。
    """
    service = TacticalBriefingService()

    # 场景 A: 合法候选文本
    # 先生成一份合法文本作为模拟的合规 LLM 输出
    valid_base = service.produce_briefing(golden_context)
    res_a = service.produce_briefing(
        context=golden_context,
        candidate_text=valid_base.tactical_briefing_text,
    )
    assert res_a.is_fallback_mode is False
    assert res_a.fallback_reason is None
    assert res_a.safety_audit_passed is True

    # 场景 B1: 候选文本含违规买入指令
    poisoned_candidate_directive = valid_base.tactical_briefing_text + " 明日建议买入时代万恒。"
    res_b1 = service.produce_briefing(
        context=golden_context,
        candidate_text=poisoned_candidate_directive,
    )
    assert res_b1.is_fallback_mode is True
    assert "IllegalDirectiveViolation" in (res_b1.fallback_reason or "")
    assert res_b1.safety_audit_passed is True
    # 确认降级后正文中绝无污染词
    assert "买入" not in res_b1.tactical_briefing_text

    # 场景 B2: 候选文本含 002242 毅昌科技 混淆
    poisoned_candidate_entity = valid_base.tactical_briefing_text + " 观察毅昌科技。"
    res_b2 = service.produce_briefing(
        context=golden_context,
        candidate_text=poisoned_candidate_entity,
    )
    assert res_b2.is_fallback_mode is True
    assert "EntityIdentityViolation" in (res_b2.fallback_reason or "")
    assert res_b2.safety_audit_passed is True
    assert "毅昌科技" not in res_b2.tactical_briefing_text

    # 场景 B3: 候选文本含虚假虚高成交额 (19000 亿)
    poisoned_candidate_turnover = valid_base.tactical_briefing_text.replace("16821.09 亿元", "19000.00 亿元")
    res_b3 = service.produce_briefing(
        context=golden_context,
        candidate_text=poisoned_candidate_turnover,
    )
    assert res_b3.is_fallback_mode is True
    assert "NumericalFidelityViolation" in (res_b3.fallback_reason or "")
    assert res_b3.safety_audit_passed is True

    # 场景 C: 无输入文本 (例如 LLM 超时或降级)
    res_c = service.produce_briefing(context=golden_context, candidate_text=None)
    assert res_c.is_fallback_mode is True
    assert res_c.safety_audit_passed is True
