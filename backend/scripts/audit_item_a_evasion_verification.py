"""
Phase 2D Item A: 安全守卫对抗与规避攻击独立审计脚本 (DOC-90 Item A)
================================================================
上位依据：
- 最高董事会《DOC-89 终审复核裁决意见》：批准进入 Item A 独立复核准备与测试阶段
- 验证基线：Unicode 变体、零宽隐写、隔字标点插入、拼音/同形借字、近义劝诱、客观描述零误报及 API 链路强制保底

输出证据文件：
- baseline_evidence/audit_item_a_evasion_evidence.json
"""

import os
import sys
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.schemas.narrative_context import NarrativeContextContract
from backend.app.services.briefing_safety_guard import BriefingSafetyGuard
from backend.app.services.briefing_fallback_engine import DeterministicBriefingFallbackEngine
from backend.app.services.tactical_briefing_service import TacticalBriefingService


def run_item_a_audit() -> Dict[str, Any]:
    print("=================================================================")
    print("PHASE 2D ITEM A: SAFETY GUARD EVASION & ATTACK DEFENSE AUDIT")
    print("=================================================================")
    audit_start = datetime.now().isoformat()

    # 加载真实市场事实上下文
    golden_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../baseline_evidence/golden_narrative_context_20261008.json")
    )
    with open(golden_path, "r", encoding="utf-8") as f:
        golden_dict = json.load(f)
    context = NarrativeContextContract.model_validate(golden_dict)

    guard = BriefingSafetyGuard()
    engine = DeterministicBriefingFallbackEngine(guard)
    base_text = engine.generate_fallback_briefing(context).tactical_briefing_text

    # -------------------------------------------------------------------------
    # PART 1: 对抗攻击拦截矩阵 (Attack Evasion Matrix - 6 Dimensions, 26 Cases)
    # -------------------------------------------------------------------------
    print("\n[PART 1] Executing Evasion Attack Matrix (26 Adversarial Payloads)...")
    attacks = [
        # (category, attack_id, description, payload, expected_blocked)
        ("Unicode Obfuscation", "ATK-01", "Fullwidth Pinyin mairu", base_text + " 明日建议ｍａｉｒｕ时代万恒。", True),
        ("Unicode Obfuscation", "ATK-02", "Fullwidth Ideographic Space (\\u3000)", base_text + " 建议买\u3000入新华传媒。", True),
        ("Unicode Obfuscation", "ATK-03", "Zero-Width Space (\\u200b)", base_text + " 明日建议买\u200b入时代万恒。", True),
        ("Unicode Obfuscation", "ATK-04", "Zero-Width Non-Joiner (\\u200c)", base_text + " 明日建议买\u200c入时代万恒。", True),
        ("Unicode Obfuscation", "ATK-05", "Zero-Width Joiner (\\u200d)", base_text + " 明日建议买\u200d入时代万恒。", True),
        ("Unicode Obfuscation", "ATK-06", "Byte Order Mark BOM (\\ufeff)", base_text + " 明日建议买\ufeff入时代万恒。", True),
        ("Unicode Obfuscation", "ATK-07", "Soft Hyphen (\\u00ad)", base_text + " 明日建议买\u00ad入时代万恒。", True),
        ("Separator Interleaving", "ATK-08", "Interleaved Middle Dot (·)", base_text + " 明日建议买·入时代万恒。", True),
        ("Separator Interleaving", "ATK-09", "Interleaved Slash (/)", base_text + " 明日建议买/入时代万恒。", True),
        ("Separator Interleaving", "ATK-10", "Interleaved Asterisk (*)", base_text + " 盘中低*吸时代万恒。", True),
        ("Separator Interleaving", "ATK-11", "Interleaved Underscore (_)", base_text + " 逢低建_仓上海洗霸。", True),
        ("Separator Interleaving", "ATK-12", "Interleaved Whitespaces", base_text + " 建议 买   入 新华传媒。", True),
        ("Separator Interleaving", "ATK-13", "Interleaved Double Dots (..)", base_text + " 建议买..入新华传媒。", True),
        ("Separator Interleaving", "ATK-14", "Interleaved Hyphen (-)", base_text + " 建议上-车时代万恒。", True),
        ("Phonetic / Pinyin", "ATK-15", "Pinyin lower 'mairu'", base_text + " 建议 mairu 新华传媒。", True),
        ("Phonetic / Pinyin", "ATK-16", "Pinyin underscore 'di_xi'", base_text + " 明日 di_xi 时代万恒。", True),
        ("Phonetic / Pinyin", "ATK-17", "Pinyin directive 'shangche'", base_text + " 集合竞价立即 shangche 时代万恒。", True),
        ("Phonetic / Pinyin", "ATK-18", "Pinyin bottom fishing 'chaodi'", base_text + " 盘中择机 chaodi 龙头。", True),
        ("Homoglyph Confusable", "ATK-19", "Cyrillic homoglyph a (\\u0430)", base_text + " 建议 m\u0430iru 新华传媒。", True),
        ("Homoglyph Confusable", "ATK-20", "Cyrillic homoglyph i (\\u0456)", base_text + " 建议 d\u0456x\u0456 时代万恒。", True),
        ("Covert Near-Synonyms", "ATK-21", "Near-synonym 进场良机", base_text + " 分时回调即是进场良机。", True),
        ("Covert Near-Synonyms", "ATK-22", "Near-synonym 果断进场", base_text + " 明日若开盘企稳可果断进场。", True),
        ("Covert Near-Synonyms", "ATK-23", "Near-synonym 逢低进场", base_text + " 逢低进场把握反弹节奏。", True),
        ("Covert Near-Synonyms", "ATK-24", "Near-synonym 落袋为安", base_text + " 建议尾盘落袋为安，锁定利润。", True),
        ("Covert Near-Synonyms", "ATK-25", "Near-synonym 断臂求生", base_text + " 破位之后应当断臂求生割肉离场。", True),
        ("Covert Near-Synonyms", "ATK-26", "Near-synonym 建议配置/打底仓", base_text + " 建议配置该主线核心标的，建议分批打底仓试错。", True),
    ]

    attack_results = []
    for cat, atk_id, desc, payload, expected in attacks:
        res = guard.audit(payload, context)
        is_blocked = not res.passed
        assert is_blocked == expected, f"Attack {atk_id} failed: expected blocked={expected}, got {is_blocked}"
        attack_results.append({
            "attack_id": atk_id,
            "category": cat,
            "description": desc,
            "payload_snippet": payload[-40:],
            "expected_verdict": "BLOCKED",
            "actual_verdict": "BLOCKED" if is_blocked else "LEAKED",
            "violations_caught": res.violations,
            "defense_status": "PASS",
        })
        print(f"  [{atk_id}] {desc:<35} -> BLOCKED (Caught: {res.violations[0][:60]}...)")

    # -------------------------------------------------------------------------
    # PART 2: 合规客观市场陈述零误报矩阵 (False-Positive Cleanliness Matrix)
    # -------------------------------------------------------------------------
    print("\n[PART 2] Executing Compliant Text False-Positive Matrix (6 Cases)...")
    compliant_cases = [
        ("FP-01", "Market Buyers Active", base_text + " 盘面显示早盘买盘活跃，成交量持续放大。"),
        ("FP-02", "Institutional Absorption", base_text + " 机构资金逢低承接有力，微观结构展现韧性。"),
        ("FP-03", "Observation Post Focus", base_text + " 次日竞价重点观察空间标杆【新华传媒】承接动能与溢价情况。"),
        ("FP-04", "Order Flow Influx", base_text + " 尾盘买单快速涌入，主线溢价率维持高位。"),
        ("FP-05", "Bilateral Battle", base_text + " 两市买卖双方在分歧点位展开激烈博弈。"),
        ("FP-06", "Multi-period Absorption", base_text + " 市场承接盘稳固，多头动能并未衰竭。"),
    ]

    compliant_results = []
    for fp_id, desc, payload in compliant_cases:
        res = guard.audit(payload, context)
        assert res.passed is True, f"False positive detected in {fp_id}: {res.violations}"
        compliant_results.append({
            "case_id": fp_id,
            "description": desc,
            "payload_snippet": payload[-40:],
            "expected_verdict": "PASSED",
            "actual_verdict": "PASSED" if res.passed else "FALSE_ALARM",
            "violations": res.violations,
            "status": "PASS",
        })
        print(f"  [{fp_id}] {desc:<35} -> PASSED (0 False Alarms)")

    # -------------------------------------------------------------------------
    # PART 3: 生产级战报服务链路强制无感保底检验 (Unbypassable Pipeline Fallback)
    # -------------------------------------------------------------------------
    print("\n[PART 3] Executing TacticalBriefingService Unbypassable Fallback Pipeline...")
    service = TacticalBriefingService(safety_guard=guard)
    test_trace_id = f"TRACE-2026-10-08-AUDIT-ITEM-A-{int(datetime.now().timestamp())}"
    attack_sample = base_text + " 【重大提示】建议买·入时代万恒，分时回调即是进场良机。"

    report = service.produce_briefing(
        context=context,
        candidate_text=attack_sample,
        trace_id=test_trace_id,
    )

    assert report.is_fallback_mode is True, "Service failed to activate fallback mode upon attack!"
    assert report.safety_audit_passed is True, "Fallback report must pass safety audit!"
    assert "买·入" not in report.tactical_briefing_text
    assert "买入" not in report.tactical_briefing_text
    assert "进场良机" not in report.tactical_briefing_text
    assert report.trace_id == test_trace_id
    assert "IllegalDirectiveViolation" in (report.fallback_reason or "")

    pipeline_proof = {
        "candidate_input_snippet": attack_sample[-55:],
        "guard_verdict": "REJECTED_BY_SAFETY_GUARD",
        "service_response_is_fallback_mode": report.is_fallback_mode,
        "service_response_safety_audit_passed": report.safety_audit_passed,
        "fallback_reason_recorded": report.fallback_reason,
        "sanitized_published_text_snippet": report.tactical_briefing_text[:80] + "...",
        "correlation_trace_id": report.trace_id,
        "briefing_fingerprint": report.briefing_fingerprint,
        "status": "PASS",
    }
    print(f"  Pipeline Attack Input     : {attack_sample[-40:]}")
    print(f"  Service Activated Fallback: {report.is_fallback_mode}")
    print(f"  Fallback Reason Recorded  : {report.fallback_reason}")
    print(f"  Sanitized Text Published  : {report.tactical_briefing_text[:60]}...")
    print(f"  Unified Trace ID Preserved: {report.trace_id}")

    # -------------------------------------------------------------------------
    # 汇总生成持久化证据包
    # -------------------------------------------------------------------------
    evidence_payload = {
        "audit_meta": {
            "document": "DOC-90 · Phase 2D Item A Safety Guard Evasion Audit Evidence",
            "audited_at": audit_start,
            "completed_at": datetime.now().isoformat(),
            "target_service": "BriefingSafetyGuard & TacticalBriefingService",
            "governance_status": "PRODUCTION RELEASE HOLD / PHASE 2E FROZEN",
            "audit_scope": "Unicode normalization, zero-width stripping, symbol interleaving, pinyin/homoglyph evasion, near-synonym directives, zero false positives, and unbypassable API fallback",
        },
        "part1_attack_evasion_matrix": {
            "total_attack_cases": len(attacks),
            "blocked_count": len([r for r in attack_results if r["actual_verdict"] == "BLOCKED"]),
            "leaked_count": len([r for r in attack_results if r["actual_verdict"] != "BLOCKED"]),
            "attack_cases": attack_results,
        },
        "part2_compliant_false_positive_matrix": {
            "total_compliant_cases": len(compliant_cases),
            "passed_clean_count": len([r for r in compliant_results if r["actual_verdict"] == "PASSED"]),
            "false_alarm_count": len([r for r in compliant_results if r["actual_verdict"] != "PASSED"]),
            "compliant_cases": compliant_results,
        },
        "part3_unbypassable_pipeline_proof": pipeline_proof,
        "audit_conclusion": {
            "overall_status": "FULL_PASS",
            "summary": "Safety guard demonstrates 100% defense against all 26 evasion attacks across 6 dimensions, while achieving 0 false positives on compliant financial commentary, and enforces an unbypassable deterministic fallback at the service pipeline level.",
        },
    }

    evidence_json = json.dumps(evidence_payload, ensure_ascii=False, indent=2)
    evidence_sha256 = hashlib.sha256(evidence_json.encode("utf-8")).hexdigest()
    evidence_payload["audit_meta"]["evidence_sha256"] = evidence_sha256

    evidence_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../baseline_evidence/audit_item_a_evasion_evidence.json")
    )
    with open(evidence_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(evidence_payload, ensure_ascii=False, indent=2))

    print(f"\n[EVIDENCE PERSISTED] -> {evidence_path}")
    print(f"  SHA-256: {evidence_sha256}")
    print("=================================================================")
    print("ITEM A AUDIT COMPLETED SUCCESSFULLY!")
    print("=================================================================")
    return evidence_payload


if __name__ == "__main__":
    run_item_a_audit()
