"""
Phase 2D.3 Dual-Scenario Independent Audit Verification Script
=============================================================
执行两种对抗与合规场景的端到端真实审计核验：
- 场景 1 (违规注入场景): 注入 DOC-86 原始失效措辞（“杜绝逆势博弈，严守核心龙头竞价承接红线”），
  证明 BriefingSafetyGuard 物理硬拦截，API 触发确定性保底降级 (is_fallback_mode=True)，
  降级原因精确记录 IllegalDirectiveViolation，最终对外交付文本 100% 纯净零污染。
- 场景 2 (合规客观场景): 客观描述微观风险与证伪条件（“市场处于高位分化加速段，逆势博弈面临显著微观亏损风险；核心标杆若开盘失守竞价承接位，将触发主线结构性走弱与逻辑证伪”），
  证明 Guard 纯净放行 (is_fallback_mode=False, fallback_reason=None)，零误杀。
"""

import json
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.schemas.narrative_context import NarrativeContextContract
from backend.app.services.briefing_safety_guard import BriefingSafetyGuard
from backend.app.services.tactical_briefing_service import TacticalBriefingService
from backend.app.services.briefing_fallback_engine import DeterministicBriefingFallbackEngine

GOLDEN_CONTEXT_PATH = Path("baseline_evidence/golden_narrative_context_20261008.json")


def run_dual_scenario_audit():
    with open(GOLDEN_CONTEXT_PATH, "r", encoding="utf-8") as f:
        context_data = json.load(f)
    context = NarrativeContextContract(**context_data)

    guard = BriefingSafetyGuard()
    fallback_engine = DeterministicBriefingFallbackEngine(guard)
    service = TacticalBriefingService(
        safety_guard=guard,
        fallback_engine=fallback_engine,
    )

    base_fallback = fallback_engine.generate_fallback_briefing(context)
    clean_base_text = base_fallback.tactical_briefing_text

    results = {}

    # =========================================================================
    # 场景 1: DOC-86 原始违规行为劝诫指令注入
    # =========================================================================
    offending_phrase = "防守红线：高位分化加速段杜绝逆势博弈，严守核心龙头竞价承接红线。"
    poisoned_candidate_text = clean_base_text + " " + offending_phrase
    trace_id_scene1 = "TRACE-20261008-AUDIT-SCENE-1-OFFENDING"

    # 1. 独立执行 Guard 审查
    guard_res_1 = guard.audit(poisoned_candidate_text, context, trace_id=trace_id_scene1)
    # 2. 端到端服务生产调用
    report_scene1 = service.produce_briefing(
        context=context,
        candidate_text=poisoned_candidate_text,
        trace_id=trace_id_scene1,
    )

    # 断言场景 1
    assert guard_res_1.passed is False, "Scenario 1 Guard must block offending phrase!"
    assert any("IllegalDirectiveViolation" in v for v in guard_res_1.violations)
    assert report_scene1.is_fallback_mode is True, "Scenario 1 must activate fallback mode!"
    assert report_scene1.fallback_reason is not None
    assert "IllegalDirectiveViolation" in report_scene1.fallback_reason
    assert "杜绝" not in report_scene1.tactical_briefing_text
    assert "严守" not in report_scene1.tactical_briefing_text
    assert report_scene1.safety_audit_passed is True

    results["scenario_1_offending"] = {
        "candidate_input_text": poisoned_candidate_text,
        "injected_violation_phrase": offending_phrase,
        "guard_audit_result": {
            "passed": guard_res_1.passed,
            "violations": guard_res_1.violations,
        },
        "api_output_report": {
            "trace_id": report_scene1.trace_id,
            "is_fallback_mode": report_scene1.is_fallback_mode,
            "fallback_reason": report_scene1.fallback_reason,
            "safety_audit_passed": report_scene1.safety_audit_passed,
            "briefing_fingerprint": report_scene1.briefing_fingerprint,
            "final_delivered_text": report_scene1.tactical_briefing_text,
        },
        "audit_verdict": "HARD_BLOCKED_AND_SAFELY_DEGRADED_PASS",
    }

    # =========================================================================
    # 场景 2: 合规客观物理风险与波普尔证伪条件叙述
    # =========================================================================
    compliant_phrase = "防守红线：市场处于高位分化加速段，逆势博弈面临显著微观亏损风险；核心标杆若开盘失守竞价承接位，将触发主线结构性走弱与逻辑证伪。"
    compliant_candidate_text = clean_base_text + " " + compliant_phrase
    trace_id_scene2 = "TRACE-20261008-AUDIT-SCENE-2-COMPLIANT"

    # 1. 独立执行 Guard 审查
    guard_res_2 = guard.audit(compliant_candidate_text, context, trace_id=trace_id_scene2)
    # 2. 端到端服务生产调用
    report_scene2 = service.produce_briefing(
        context=context,
        candidate_text=compliant_candidate_text,
        trace_id=trace_id_scene2,
    )

    # 断言场景 2
    assert guard_res_2.passed is True, f"Scenario 2 must pass Guard cleanly! Violations: {guard_res_2.violations}"
    assert report_scene2.is_fallback_mode is False, "Scenario 2 must NOT degrade to fallback!"
    assert report_scene2.fallback_reason is None
    assert report_scene2.safety_audit_passed is True
    assert compliant_phrase in report_scene2.tactical_briefing_text

    results["scenario_2_compliant"] = {
        "candidate_input_text": compliant_candidate_text,
        "compliant_phrase": compliant_phrase,
        "guard_audit_result": {
            "passed": guard_res_2.passed,
            "violations": guard_res_2.violations,
        },
        "api_output_report": {
            "trace_id": report_scene2.trace_id,
            "is_fallback_mode": report_scene2.is_fallback_mode,
            "fallback_reason": report_scene2.fallback_reason,
            "safety_audit_passed": report_scene2.safety_audit_passed,
            "briefing_fingerprint": report_scene2.briefing_fingerprint,
            "final_delivered_text": report_scene2.tactical_briefing_text,
        },
        "audit_verdict": "CLEAN_PASS_WITHOUT_FALSE_POSITIVE",
    }

    output_path = Path("baseline_evidence/audit_dual_scenario_verification_20261008.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("=" * 80)
    print("DUAL SCENARIO VERIFICATION COMPLETED SUCCESSFULLY")
    print(f"Output saved to: {output_path}")
    print(f"Scenario 1 Verdict: {results['scenario_1_offending']['audit_verdict']}")
    print(f"Scenario 2 Verdict: {results['scenario_2_compliant']['audit_verdict']}")
    print("=" * 80)


if __name__ == "__main__":
    run_dual_scenario_audit()
