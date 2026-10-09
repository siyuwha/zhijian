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

from decimal import Decimal
from backend.app.schemas.narrative_context import NarrativeContextContract
from backend.app.schemas.tactical_briefing import (
    TacticalBriefingReport,
    SafetyAuditResult,
)
from backend.app.services.briefing_safety_guard import (
    BriefingSafetyGuard,
    FORBIDDEN_DIRECTIVE_TERMS,
    canonical_round_decimal,
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


# =============================================================================
# GATE-2D3-07B: Adversarial Numerical and Covert Directive Defense (P0-2)
# =============================================================================
def test_gate_2d3_07b_adversarial_numerical_and_covert_directive_defense(
    golden_context: NarrativeContextContract,
):
    """
    GATE-2D3-07B: 完备安全对抗测试 (P0-2)
    - 单位换算：万亿 vs 亿 归一化与非法跳变拦截；
    - 舍入边界：精确匹配、合法四舍五入与非法舍入拦截；
    - 隐蔽式间接交易指令：低吸机会、逢低布局、轻仓试错、上车潜伏等全面拦截；
    - 监管语义防伪：阻断将商业数据商异动规则推断为交易所官方行政定性。
    """
    guard = BriefingSafetyGuard()
    engine = DeterministicBriefingFallbackEngine(guard)
    base_text = engine.generate_fallback_briefing(golden_context).tactical_briefing_text

    # -------------------------------------------------------------------------
    # 1. 单位换算与舍入边界对抗 (Turnover: 16821.09 亿)
    # -------------------------------------------------------------------------
    # 1.1 合法单位换算 (1.6821 万亿 -> 16821.0 亿) -> PASS
    t_valid_trillion = base_text.replace("16821.09 亿元", "1.6821 万亿元")
    assert guard.audit(t_valid_trillion, golden_context).passed is True

    # 1.2 精确万亿换算 (1.682109 万亿元 -> 16821.09 亿) -> PASS
    t_valid_trillion_exact = base_text.replace("16821.09 亿元", "1.682109 万亿元")
    assert guard.audit(t_valid_trillion_exact, golden_context).passed is True

    # 1.3 恶意/虚假万亿换算 (1.95 万亿元 -> 19500 亿) -> HARD BLOCK
    t_fake_trillion = base_text.replace("16821.09 亿元", "1.95 万亿元")
    res_fake_trillion = guard.audit(t_fake_trillion, golden_context)
    assert res_fake_trillion.passed is False
    assert any("Total turnover" in v and "1.95 万亿元" in v for v in res_fake_trillion.violations)

    # 1.4 精度不足的粗暴万亿换算 (1.68 万亿元 -> 16800 亿，偏差 21.09 亿) -> HARD BLOCK
    t_rough_trillion = base_text.replace("16821.09 亿元", "1.68 万亿元")
    res_rough = guard.audit(t_rough_trillion, golden_context)
    assert res_rough.passed is False
    assert any("Total turnover" in v and "1.68 万亿元" in v for v in res_rough.violations)

    # 1.5 合法 1 位小数舍入 (16821.1 亿元) -> PASS
    t_round_1dec = base_text.replace("16821.09 亿元", "16821.1 亿元")
    assert guard.audit(t_round_1dec, golden_context).passed is True

    # 1.6 合法整数四舍五入 (16821 亿元) -> PASS
    t_round_int = base_text.replace("16821.09 亿元", "16821 亿元")
    assert guard.audit(t_round_int, golden_context).passed is True

    # 1.7 非法向上舍入 (16822 亿元，正确应为 16821) -> HARD BLOCK
    t_wrong_int = base_text.replace("16821.09 亿元", "16822 亿元")
    res_wrong_int = guard.audit(t_wrong_int, golden_context)
    assert res_wrong_int.passed is False
    assert any("16822 亿元" in v for v in res_wrong_int.violations)

    # 1.8 炸板率合法舍入 (42.7% & 43%) -> PASS
    t_broken_1dec = base_text.replace("42.67%", "42.7%")
    assert guard.audit(t_broken_1dec, golden_context).passed is True
    t_broken_int = base_text.replace("42.67%", "43%")
    assert guard.audit(t_broken_int, golden_context).passed is True

    # 1.9 炸板率非法舍入 (42% 向下截断) -> HARD BLOCK
    t_broken_wrong = base_text.replace("42.67%", "42%")
    res_broken_wrong = guard.audit(t_broken_wrong, golden_context)
    assert res_broken_wrong.passed is False
    assert any("Broken limit ratio" in v and "42%" in v for v in res_broken_wrong.violations)

    # -------------------------------------------------------------------------
    # 2. 隐蔽式间接交易指令对抗拦截 (P0-2)
    # -------------------------------------------------------------------------
    covert_directive_cases = [
        ("【盘面提示】建议关注低吸机会。", "低吸"),
        ("核心品种可逢低积极布局。", "布局"),
        ("次日竞价可考虑轻仓试错前排标的。", "轻仓试错"),
        ("高位滞涨品种建议逢高派发减仓。", "逢高派发"),
        ("建议逢阴低吸优质主线标的。", "逢阴低吸"),
        ("集合竞价即可果断上车。", "上车"),
        ("建议提前潜伏博弈超跌反弹。", "提前潜伏"),
        ("重点关注核心资产做多机会。", "做多机会"),
    ]
    for text_suffix, expected_keyword in covert_directive_cases:
        poisoned_text = base_text + " " + text_suffix
        audit_res = guard.audit(poisoned_text, golden_context)
        assert audit_res.passed is False, f"Failed to intercept covert directive: {text_suffix}"
        assert any(
            "IllegalDirectiveViolation" in v for v in audit_res.violations
        ), f"Missing IllegalDirectiveViolation for: {text_suffix}"

    # -------------------------------------------------------------------------
    # 3. 监管语义防伪与官方定性拦截 (P0-3)
    # -------------------------------------------------------------------------
    t_fake_reg1 = base_text + " 交易所官方明确下发重点监控核查函。"
    res_fake_reg1 = guard.audit(t_fake_reg1, golden_context)
    assert res_fake_reg1.passed is False
    assert any("commercial data vendor rule match" in v for v in res_fake_reg1.violations)

    t_fake_reg2 = base_text + " 监管部门定性为严重异动并实施特停。"
    res_fake_reg2 = guard.audit(t_fake_reg2, golden_context)
    assert res_fake_reg2.passed is False
    assert any("commercial data vendor rule match" in v for v in res_fake_reg2.violations)

    # -------------------------------------------------------------------------
    # 4. 行为操作劝诫与指令性操作拦截 (DOC-87 审计整改：封堵一切第二人称行为命令)
    # -------------------------------------------------------------------------
    # 4.1 DOC-86 原文精确对抗用例: "杜绝逆势博弈，严守核心龙头竞价承接红线" -> 刚性拦截！
    t_doc86_imperative = base_text + " 防守红线：高位分化加速段杜绝逆势博弈，严守核心龙头竞价承接红线。"
    res_doc86_block = guard.audit(t_doc86_imperative, golden_context)
    assert res_doc86_block.passed is False, "DOC-86 imperative phrase must be hard-blocked!"
    assert any(
        "IllegalDirectiveViolation" in v and ("杜绝" in v or "严守" in v or "博弈" in v)
        for v in res_doc86_block.violations
    ), f"Expected IllegalDirectiveViolation in: {res_doc86_block.violations}"

    # 4.2 更多操作劝诱与行为指令对抗矩阵 -> 全部 HARD BLOCK
    operational_imperatives = [
        "建议次日控制仓位在半仓以下，保持观望。",
        "切忌逆势接力，杜绝盲目出手。",
        "务必严守交易纪律。",
        "严防追高被套风险。",
        "建议持币观望等待企稳。",
        "不可盲目开仓抄底。",
    ]
    for imp in operational_imperatives:
        t_imp = base_text + " " + imp
        res_imp = guard.audit(t_imp, golden_context)
        assert res_imp.passed is False, f"Failed to block operational imperative: {imp}"
        assert any("IllegalDirectiveViolation" in v for v in res_imp.violations)

    # 4.3 允许项：客观描述风险、可验证观察条件与假说证伪条件 -> 100% 纯净 PASS
    allowed_objective_cases = [
        "市场处于高位分化加速段，逆势博弈面临显著微观亏损风险。",
        "核心标杆若开盘失守竞价承接位，将触发主线结构性走弱与逻辑证伪。",
        "次日竞价重点观察空间标杆溢价表现与主线承接力度。",
    ]
    for obj_case in allowed_objective_cases:
        t_obj = base_text + " " + obj_case
        res_obj = guard.audit(t_obj, golden_context)
        assert res_obj.passed is True, f"Legitimate objective description falsely blocked: {obj_case}, errors: {res_obj.violations}"

    # -------------------------------------------------------------------------
    # 5. 强离散整数字段保真度与精度边界校验 (P0-4 & DOC-87)
    # -------------------------------------------------------------------------
    # 5.1 空间标杆高度 (true: 8B)
    t_height_wrong = base_text.replace("8B", "9B")
    res_h_wrong = guard.audit(t_height_wrong, golden_context)
    assert res_h_wrong.passed is False
    assert any("Space leader max height '9B'" in v for v in res_h_wrong.violations)

    # 5.2 跌停家数 (true: 13家)
    t_down_wrong = base_text.replace("13 家", "14 家")
    res_d_wrong = guard.audit(t_down_wrong, golden_context)
    assert res_d_wrong.passed is False
    assert any("Limit down count '14'" in v for v in res_d_wrong.violations)

    # 5.3 商业异动规则撮合标的数 (true: 11家)
    t_reg_wrong = base_text.replace("11 家", "12 家")
    res_r_wrong = guard.audit(t_reg_wrong, golden_context)
    assert res_r_wrong.passed is False
    assert any("Regulatory anomaly count '12'" in v for v in res_r_wrong.violations)


# =============================================================================
# GATE-2D3-05B: Decimal Canonical ROUND_HALF_UP Two-Sided Boundary Proof
# =============================================================================
def test_gate_2d3_05b_decimal_round_half_up_boundary_proof():
    """
    GATE-2D3-05B: Decimal Canonical ROUND_HALF_UP 双向边界测试与 Banker's 漂移证伪
    - 证明 Python 原生 float round(42.65, 1) 会因为 ties-to-even 错误返回 42.6；
    - 证明 canonical_round_decimal(42.65, 1) 严格遵循 ROUND_HALF_UP 返回 Decimal('42.7')；
    - 验证双向分界点:
      - 42.65000000 -> 42.7
      - 42.64999999 -> 42.6
      - 42.64000000 -> 42.6
    - 验证总成交额边界:
      - 16821.05 -> Decimal('16821.1') (round() 返回 16821.0)
      - 16821.04 -> Decimal('16821.0')
    """
    # 1. 炸板率正数分界点对比 (Positive Ties Away From Zero)
    val_broken_tie = Decimal("42.65")
    # Python banker's rounding flaw demonstration
    assert round(42.65, 1) == 42.6, "Python float banker's rounding returns even number 42.6"
    # Canonical Decimal ROUND_HALF_UP correctness
    assert canonical_round_decimal(val_broken_tie, 1) == Decimal("42.7")

    # 双向边界：略低于 0.05 截断向下，达到 0.05 进位向上
    assert canonical_round_decimal(Decimal("42.649999"), 1) == Decimal("42.6")
    assert canonical_round_decimal(Decimal("42.650001"), 1) == Decimal("42.7")
    assert canonical_round_decimal(Decimal("42.64"), 1) == Decimal("42.6")

    # 2. 负数分界点与对称舍入对比 (Negative Ties Symmetric Rounding Away From Zero)
    assert canonical_round_decimal(Decimal("-42.65"), 1) == Decimal("-42.7")
    assert canonical_round_decimal(Decimal("-42.649999"), 1) == Decimal("-42.6")
    assert canonical_round_decimal(Decimal("-42.650001"), 1) == Decimal("-42.7")
    assert canonical_round_decimal(Decimal("-0.75"), 1) == Decimal("-0.8")
    assert canonical_round_decimal(Decimal("-0.749"), 1) == Decimal("-0.7")
    assert canonical_round_decimal(Decimal("-42.50"), 0) == Decimal("-43")
    assert canonical_round_decimal(Decimal("-42.49"), 0) == Decimal("-42")

    # 3. 成交额分界点对比
    val_to_tie = Decimal("16821.05")
    assert round(16821.05, 1) == 16821.0, "Python float banker's rounding returns even number 16821.0"
    assert canonical_round_decimal(val_to_tie, 1) == Decimal("16821.1")
    assert canonical_round_decimal(Decimal("16821.049"), 1) == Decimal("16821.0")
    assert canonical_round_decimal(Decimal("16821.04"), 1) == Decimal("16821.0")

    # 4. 负精度舍入 (Negative Precision for Tens / Hundreds)
    assert canonical_round_decimal(Decimal("16854.5678"), -1) == Decimal("16850")
    assert canonical_round_decimal(Decimal("16854.5678"), -2) == Decimal("16900")
    assert canonical_round_decimal(Decimal("16849"), -2) == Decimal("16800")
    assert canonical_round_decimal(Decimal("16850"), -2) == Decimal("16900")
    assert canonical_round_decimal(Decimal("-16850"), -2) == Decimal("-16900")
    assert canonical_round_decimal(Decimal("-16849"), -2) == Decimal("-16800")

    # 5. 极端精度与科学计数法保真 (Extreme Precision & Scientific Notation)
    assert canonical_round_decimal("0.123456789012345", 10) == Decimal("0.1234567890")
    assert canonical_round_decimal("-0.123456789012345", 10) == Decimal("-0.1234567890")
    assert canonical_round_decimal(1e-5, 6) == Decimal("0.000010")
    assert canonical_round_decimal("1e-5", 6) == Decimal("0.000010")

    # 6. 非法与异常输入刚性校验防御 (Invalid Inputs Defense)
    import pytest
    with pytest.raises(ValueError, match="cannot be None"):
        canonical_round_decimal(None, 2)
    # 显式拦截 bool (布尔值不可被当作 0/1 整型)
    with pytest.raises(ValueError, match="boolean values are not supported"):
        canonical_round_decimal(True, 2)
    with pytest.raises(ValueError, match="boolean values are not supported"):
        canonical_round_decimal(False, 2)
    # 拦截原生 float NaN 与 Infinite
    with pytest.raises(ValueError, match="NaN or Infinite"):
        canonical_round_decimal(float("nan"), 2)
    with pytest.raises(ValueError, match="NaN or Infinite"):
        canonical_round_decimal(float("inf"), 2)
    with pytest.raises(ValueError, match="NaN or Infinite"):
        canonical_round_decimal(float("-inf"), 2)
    # 拦截上游 Decimal 特殊值 (Decimal NaN / Infinity)
    with pytest.raises(ValueError, match="NaN or Infinite"):
        canonical_round_decimal(Decimal("NaN"), 2)
    with pytest.raises(ValueError, match="NaN or Infinite"):
        canonical_round_decimal(Decimal("Infinity"), 2)
    with pytest.raises(ValueError, match="NaN or Infinite"):
        canonical_round_decimal(Decimal("-Infinity"), 2)
    with pytest.raises(ValueError, match="invalid numeric literal"):
        canonical_round_decimal("invalid_number_abc", 2)
    with pytest.raises(ValueError, match="empty numeric string"):
        canonical_round_decimal("   ", 2)
    with pytest.raises(ValueError, match="precision must be an integer"):
        canonical_round_decimal(42.5, 1.5)  # type: ignore
    with pytest.raises(ValueError, match="precision must be an integer"):
        canonical_round_decimal(42.5, True)  # type: ignore
    with pytest.raises(ValueError, match="out of reasonable bounds"):
        canonical_round_decimal(42.5, 99)

    # 7. 负零规范化验证 (Negative Zero Normalization)
    res_neg_zero = canonical_round_decimal(Decimal("-0.00"), 1)
    assert res_neg_zero == Decimal("0.0")
    assert str(res_neg_zero) == "0.0"  # 绝不出现 '-0.0'



# =============================================================================
# GATE-2D3-05C: Full-Field Numerical Inventory Fidelity Guard
# =============================================================================
def test_gate_2d3_05c_full_field_numerical_inventory_fidelity(golden_context: NarrativeContextContract):
    """
    GATE-2D3-05C: 全字段数值清单保真度审查门禁
    覆盖全部数值清单：
    1. 两市真实总成交额 (16821.09 亿)
    2. 沪市成交额 (8111.83 亿)
    3. 深市成交额 (8709.26 亿)
    4. 真实炸板率 (42.67%)
    5. 极值亏损率 (60.00% / 60%)
    6. 指数极差离散度 (4.03%)
    7. 全市场涨停家数 (43 只/家)
    8. 全市场收盘跌停家数 (13 只/家)
    9. 商业异动规则撮合标的数 (11 只/家)
    10. 核心主线龙头高度与成分涨停家数 (新华传媒 8B/12家, 时代万恒 4B/9家, 上海洗霸 3B/5家)
    """
    guard = BriefingSafetyGuard()
    engine = DeterministicBriefingFallbackEngine(guard)
    base_text = engine.generate_fallback_briefing(golden_context).tactical_briefing_text

    # 1. 沪市分市场成交额篡改 (8111.83 亿 -> 8500.00 亿) -> HARD BLOCK
    t_sh_wrong = base_text.replace("8111.83 亿元", "8500.00 亿元")
    res_sh = guard.audit(t_sh_wrong, golden_context)
    assert res_sh.passed is False
    assert any("SH turnover '8500.00 亿元' diverges from true fact '8111.83亿'" in v for v in res_sh.violations)

    # 2. 深市分市场成交额篡改 (8709.26 亿 -> 9200.00 亿) -> HARD BLOCK
    t_sz_wrong = base_text.replace("8709.26 亿元", "9200.00 亿元")
    res_sz = guard.audit(t_sz_wrong, golden_context)
    assert res_sz.passed is False
    assert any("SZ turnover '9200.00 亿元' diverges from true fact '8709.26亿'" in v for v in res_sz.violations)

    # 3. 极值亏损率注入与篡改
    # 3.1 注入真实极值亏损率 60.00% 或 60% -> PASS
    t_loss_valid = base_text + " 盘面极值亏损率达 60.00%。"
    assert guard.audit(t_loss_valid, golden_context).passed is True
    t_loss_valid_int = base_text + " 盘面极值亏损率达 60%。"
    assert guard.audit(t_loss_valid_int, golden_context).passed is True

    # 3.2 篡改极值亏损率为 35.00% -> HARD BLOCK
    t_loss_fake = base_text + " 盘面极值亏损率达 35.00%。"
    res_loss = guard.audit(t_loss_fake, golden_context)
    assert res_loss.passed is False
    assert any("Extreme loss ratio '35.00%' diverges from derived fact '60.00%'" in v for v in res_loss.violations)

    # 4. 指数极差离散度注入与篡改
    # 4.1 注入真实离散度 4.03% 或 4.0% -> PASS
    t_disp_valid = base_text + " 指数极差离散度为 4.03%。"
    assert guard.audit(t_disp_valid, golden_context).passed is True

    # 4.2 篡改离散度为 8.50% -> HARD BLOCK
    t_disp_fake = base_text + " 指数极差离散度为 8.50%。"
    res_disp = guard.audit(t_disp_fake, golden_context)
    assert res_disp.passed is False
    assert any("Index dispersion '8.50%' diverges from derived fact '4.03%'" in v for v in res_disp.violations)

    # 5. 全市场封死涨停家数注入与篡改 (true: 43家)
    t_up_valid = base_text + " 全市场封死涨停 43 家。"
    assert guard.audit(t_up_valid, golden_context).passed is True

    t_up_fake = base_text + " 全市场封死涨停 68 家。"
    res_up = guard.audit(t_up_fake, golden_context)
    assert res_up.passed is False
    assert any("Full market limit up count '68' diverges from true fact '43'" in v for v in res_up.violations)

    # 6. 核心主线龙头高度与成分涨停家数篡改
    # 6.1 龙头高度篡改：将 新华传媒 8B 篡改为 6B
    t_leader_h_fake = base_text.replace("龙头【新华传媒】8B", "龙头【新华传媒】6B")
    res_lh = guard.audit(t_leader_h_fake, golden_context)
    assert res_lh.passed is False
    assert any("Leader '新华传媒' height '6B' diverges from true fact '8B'" in v for v in res_lh.violations)

    # 6.2 主线成分涨停家数篡改：将 央国企改革 涨停 12 家 篡改为 涨停 20 家
    t_sector_cnt_fake = base_text.replace("涨停 12 家", "涨停 20 家")
    res_sc = guard.audit(t_sector_cnt_fake, golden_context)
    assert res_sc.passed is False
    assert any("Sector '央国企改革' limit up count '20' diverges from fact '12'" in v for v in res_sc.violations)


# =============================================================================
# GATE-2D3-05D: Index Quotes Signed Decimal Fidelity Guard
# =============================================================================
def test_gate_2d3_05d_index_quotes_signed_decimal_fidelity(golden_context: NarrativeContextContract):
    """
    GATE-2D3-05D: 核心宽基指数涨跌幅带符号/负数保真度门禁
    - 验证四大核心宽基指数 (上证指数 -0.79%, 深成指 -2.07%, 创业板指 -3.15%, 科创50 -4.82%)；
    - 验证自然语言叙事与跌幅动词匹配 (例如: "科创50重挫4.82%", "沪指跌0.79%")；
    - 验证显式负号匹配与单小数位舍入 (例如: "科创50-4.8%", "创指-3.15%")；
    - 拦截数值篡改 (例如: "科创50重挫5.00%")；
    - 拦截方向矛盾 (例如: 真实为负跌幅 -4.82%，但文本宣称 "科创50大涨4.82%")。
    """
    guard = BriefingSafetyGuard()
    engine = DeterministicBriefingFallbackEngine(guard)
    base_text = engine.generate_fallback_briefing(golden_context).tactical_briefing_text

    # 1. 自然语言合法指数表述 (跌幅动词 + 绝对值) -> PASS
    t_idx_natural = base_text + " 盘面宽基方面，上证指数下跌0.79%，深成指大跌2.07%，创业板指重挫3.15%，科创50重挫4.82%。"
    res_nat = guard.audit(t_idx_natural, golden_context)
    assert res_nat.passed is True

    # 2. 显式负号与规范舍入 (1位小数) -> PASS
    t_idx_signed = base_text + " 今日主要指数收盘：沪指-0.79%，创指-3.15%，科创50-4.8%。"
    res_sig = guard.audit(t_idx_signed, golden_context)
    assert res_sig.passed is True

    # 3. 数值偏差篡改拦截 (科创50 -4.82% -> 5.00%) -> HARD BLOCK
    t_idx_diverge = base_text + " 今日科创50重挫5.00%。"
    res_div = guard.audit(t_idx_diverge, golden_context)
    assert res_div.passed is False
    assert any("Index '科创50' pct_change '5.00%' diverges from true fact '-4.82%'" in v for v in res_div.violations)

    # 4. 方向性矛盾硬拦截 (真实为 -4.82%，文本宣称大涨 4.82%) -> HARD BLOCK
    t_idx_dir = base_text + " 今日科创50大涨4.82%。"
    res_dir = guard.audit(t_idx_dir, golden_context)
    assert res_dir.passed is False
    assert any("Index '科创50' direction contradicts fact" in v for v in res_dir.violations)


# =============================================================================
# GATE-2D3-07C: Unicode Evasion & False-Positive Hard Matrix (DOC-90 Item A)
# =============================================================================
def test_gate_2d3_07c_unicode_evasion_and_false_positive_matrix(golden_context: NarrativeContextContract):
    """
    GATE-2D3-07C: 安全守卫对抗与合规误报硬核矩阵 (DOC-90 Item A)
    - 维度 1: Unicode 全角混淆与全角空白 (Fullwidth & \u3000)
    - 维度 2: 零宽字符与不可见格式符 (\u200b, \u200c, \u200d, \ufeff, \u00ad)
    - 维度 3: 隔字标点与符号插入 (·, /, *, -, _, 空格, 多重句点)
    - 维度 4: 拼音与音近隐蔽转义 (mairu, dixi, shangche, chaodi, di_xi, mai_ru)
    - 维度 5: 西里尔等同形字混淆 (Cyrillic homoglyphs: а, о, е, і)
    - 维度 6: 近义词与隐蔽交易劝诱 (进场良机, 果断进场, 逢低进场, 落袋为安, 锁定利润, 断臂求生, 建议配置)
    - 维度 7: 客观市场描述绝对零误报 (买盘活跃, 逢低承接, 买单涌入, 买卖双方博弈, 承接动能)
    - 维度 8: 生产级战报服务链路强制无感保底 (Unbypassable API Fallback & Trace ID)
    """
    guard = BriefingSafetyGuard()
    engine = DeterministicBriefingFallbackEngine(guard)
    base_text = engine.generate_fallback_briefing(golden_context).tactical_briefing_text

    # 1. 对抗攻击用例集 (全部必须被 HARD BLOCK)
    attack_matrix = [
        ("Unicode Fullwidth Pinyin", base_text + " 明日建议ｍａｉｒｕ时代万恒。"),
        ("Unicode Fullwidth Space", base_text + " 建议买\u3000入新华传媒。"),
        ("Unicode Zero-Width Space", base_text + " 明日建议买\u200b入时代万恒。"),
        ("Unicode Zero-Width Non-Joiner", base_text + " 明日建议买\u200c入时代万恒。"),
        ("Unicode Zero-Width Joiner", base_text + " 明日建议买\u200d入时代万恒。"),
        ("Unicode BOM / ZWNBSP", base_text + " 明日建议买\ufeff入时代万恒。"),
        ("Unicode Soft Hyphen", base_text + " 明日建议买\u00ad入时代万恒。"),
        ("Interleaved Dot", base_text + " 明日建议买·入时代万恒。"),
        ("Interleaved Slash", base_text + " 明日建议买/入时代万恒。"),
        ("Interleaved Asterisk", base_text + " 盘中低*吸时代万恒。"),
        ("Interleaved Underscore", base_text + " 逢低建_仓上海洗霸。"),
        ("Interleaved Spaces", base_text + " 建议 买   入 新华传媒。"),
        ("Interleaved Double Dots", base_text + " 建议买..入新华传媒。"),
        ("Interleaved Dash", base_text + " 建议上-车时代万恒。"),
        ("Pinyin Lower", base_text + " 建议 mairu 新华传媒。"),
        ("Pinyin Underscore", base_text + " 明日 di_xi 时代万恒。"),
        ("Pinyin Shangche", base_text + " 集合竞价立即 shangche 时代万恒。"),
        ("Homoglyph Cyrillic a", base_text + " 建议 m\u0430iru 新华传媒。"),  # \u0430 is Cyrillic small 'a'
        ("Homoglyph Cyrillic i", base_text + " 建议 d\u0456x\u0456 时代万恒。"),  # \u0456 is Cyrillic 'i'
        ("Near-Synonym 进场良机", base_text + " 分时回调即是进场良机。"),
        ("Near-Synonym 果断进场", base_text + " 明日若开盘企稳可果断进场。"),
        ("Near-Synonym 逢低进场", base_text + " 逢低进场把握反弹节奏。"),
        ("Near-Synonym 落袋为安", base_text + " 建议尾盘落袋为安，锁定利润。"),
        ("Near-Synonym 断臂求生", base_text + " 破位之后应当断臂求生割肉离场。"),
        ("Near-Synonym 建议配置", base_text + " 建议配置该主线核心标的。"),
        ("Near-Synonym 打底仓", base_text + " 建议分批打底仓试错。"),
    ]

    for attack_name, attack_payload in attack_matrix:
        res = guard.audit(attack_payload, golden_context)
        assert res.passed is False, f"EVASION ATTACK LEAKED: '{attack_name}' was not blocked!"
        assert len(res.violations) >= 1, f"No violations logged for '{attack_name}'"

    # 2. 客观市场合规用例集 (绝不产生误报，必须 100% 通过)
    compliant_matrix = [
        ("Market Buyers Active", base_text + " 盘面显示早盘买盘活跃，成交量持续放大。"),
        ("Institutional Absorption", base_text + " 机构资金逢低承接有力，微观结构展现韧性。"),
        ("Observation Post Focus", base_text + " 次日竞价重点观察空间标杆【新华传媒】承接动能与溢价情况。"),
        ("Order Flow Influx", base_text + " 尾盘买单快速涌入，主线溢价率维持高位。"),
        ("Bilateral Battle", base_text + " 两市买卖双方在分歧点位展开激烈博弈。"),
        ("Multi-period Stability", base_text + " 市场承接盘稳固，多头动能并未衰竭。"),
    ]

    for comp_name, comp_payload in compliant_matrix:
        res = guard.audit(comp_payload, golden_context)
        assert res.passed is True, f"FALSE ALARM DETECTED: Compliant case '{comp_name}' was falsely rejected: {res.violations}"

    # 3. 生产级战报服务链路强制保底检验 (Unbypassable API Fallback & Trace ID)
    service = TacticalBriefingService(safety_guard=guard)
    evasion_sample = base_text + " 明日建议买·入时代万恒。"
    briefing_res = service.produce_briefing(
        context=golden_context,
        candidate_text=evasion_sample,
        trace_id="TRACE-ITEM-A-EVASION-TEST-001",
    )
    assert briefing_res.is_fallback_mode is True, "Service failed to trigger fallback upon evasion attack!"
    assert briefing_res.safety_audit_passed is True, "Fallback report must pass safety audit!"
    assert "买·入" not in briefing_res.tactical_briefing_text
    assert "买入" not in briefing_res.tactical_briefing_text
    assert "IllegalDirectiveViolation" in (briefing_res.fallback_reason or "")
    assert briefing_res.trace_id == "TRACE-ITEM-A-EVASION-TEST-001"


# =============================================================================
# GATE-2D3-12: Semantic Risk Description vs Directive Matrix Gate
# =============================================================================
def test_gate_2d3_12_semantic_risk_vs_directive_matrix(golden_context: NarrativeContextContract):
    """
    GATE-2D3-12: 语义矩阵分类审查门禁 (客观风险描述 vs 交易劝诱指令)
    - 验证客观风险事实描述 100% 放行，绝不产生误杀；
    - 验证显式操作指令 100% 硬拦截；
    - 验证隐蔽/委婉/劝诱操作指令 (含历史失效词) 100% 拦截；
    - 验证混合内容 100% 拦截并触发确定性保底无感降级。
    """
    guard = BriefingSafetyGuard()
    engine = DeterministicBriefingFallbackEngine(guard)
    service = TacticalBriefingService(safety_guard=guard)
    base_text = engine.generate_fallback_briefing(golden_context).tactical_briefing_text

    # 1. 客观风险事实与市场状态描述 (MUST PASS - 零误杀)
    objective_risk_descriptions = [
        "盘面资金处于观望态势",
        "由于高位股分歧加大，资金风险偏好降低",
        "银行板块保持防御结构，指数窄幅震荡",
        "两市成交额有所降低，整体防守特征明显",
        "市场观望情绪浓厚，量能收缩",
        "高位情绪退潮，资金态度保持谨慎",
    ]
    for desc in objective_risk_descriptions:
        res = guard.audit(base_text + " " + desc, golden_context)
        assert res.passed is True, f"FALSE POSITIVE: Objective risk sentence was falsely blocked: '{desc}', violations: {res.violations}"

    # 2. 显式操作指令 (MUST BLOCK)
    explicit_directives = [
        "建议次日集合竞价买入核心龙头时代万恒",
        "激进资金可满仓冲锋固态电池龙头",
        "破位标的建议果断清仓割肉离场",
    ]
    for directive in explicit_directives:
        res = guard.audit(base_text + " " + directive, golden_context)
        assert res.passed is False, f"FAILED TO BLOCK EXPLICIT DIRECTIVE: '{directive}'"
        assert any("IllegalDirectiveViolation" in v for v in res.violations)

    # 3. 隐蔽/委婉/劝诱操作指令 (含历史失效用例，MUST BLOCK)
    covert_directives = [
        "杜绝逆势博弈，严守核心龙头竞价承接红线",
        "建议交易员严格控制仓位，保持克制",
        "操作上建议逢低吸纳优质标的",
        "必须轻仓试错，切忌盲目出手",
        "操作建议：持币观望，严守止损红线",
        "建议适当降低仓位",
        "务必压缩仓位风险敞口",
        "建议保持观望",
        "操作上保持防御",
        "严防追高被套",
    ]
    for covert in covert_directives:
        res = guard.audit(base_text + " " + covert, golden_context)
        assert res.passed is False, f"FAILED TO BLOCK COVERT DIRECTIVE: '{covert}'"
        assert any("IllegalDirectiveViolation" in v for v in res.violations)

    # 4. 混合内容端到端 API 降级检验 (MUST TRIGGER FALLBACK)
    mixed_content = (
        base_text +
        " 盘面资金处于观望态势，两市成交额有所降低。"  # 合规客观描述
        " 操作建议：交易员务必压缩仓位风险敞口，建议保持观望。"  # 违规劝诱
    )
    briefing = service.produce_briefing(
        context=golden_context,
        candidate_text=mixed_content,
        trace_id="TRACE-SEMANTIC-MATRIX-TEST-001",
    )
    assert briefing.is_fallback_mode is True, "Mixed content must trigger fallback!"
    assert briefing.safety_audit_passed is True, "Sanitized fallback must pass audit!"
    assert "压缩仓位" not in briefing.tactical_briefing_text
    assert "保持观望" not in briefing.tactical_briefing_text





