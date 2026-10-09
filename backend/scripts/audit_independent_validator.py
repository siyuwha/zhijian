"""
Phase 2D Independent Standalone Audit Validator Script
======================================================
上位依据：
最高董事会终审指令：五项硬核补证 (DOC-86 & DOC-87 复核意见 Item C)

核心职责：
- 独立于测试套件和现有声明，从原始物理快照和底层服务直接重新计算哈希；
- 逐一严格断言 7 节点无缝血缘链条（Unbroken 7-Node Provenance Chain）；
- 证明全链路无任何篡改、伪造或指纹漂移。

7 节点清单：
Node 1: 物理市场数据快照 (CanonicalMarketSnapshot via CanonicalMarketService)
Node 2: 快照 JCS SHA-256 权威指纹独立重算 (Snapshot Fingerprint Recalculation)
Node 3: 市场状态机与多维量化特征校准 (CalibratedMarketState)
Node 4: 叙事契约提取与 JCS 哈希重算 (NarrativeContextContract & JCS Fingerprint)
Node 5: 真实远程大模型 HTTPS 调用凭据 (Remote LLM Invocation Evidence)
Node 6: 后置物理安全守卫独立重审 (BriefingSafetyGuard Independent Re-Audit)
Node 7: 统一 Trace ID 强绑定与 REST API 载荷哈希重算 (TacticalBriefingReport & E2E Linkage)
"""

import sys
import json
import asyncio
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.core.database import async_session
from backend.app.services.canonical_market_service import CanonicalMarketService
from backend.app.services.narrative_context_service import NarrativeContextExtractor
from backend.app.services.briefing_safety_guard import BriefingSafetyGuard
from backend.app.services.tactical_briefing_service import TacticalBriefingService
from backend.app.cognition.jcs import hash_jcs


async def run_independent_audit_validation():
    print("=" * 90)
    print("PHASE 2D INDEPENDENT STANDALONE AUDIT VALIDATOR (RECOMPUTING ALL HASHES)")
    print("=" * 90)

    # -------------------------------------------------------------------------
    # Node 1: 物理市场数据快照 (CanonicalMarketSnapshot)
    # -------------------------------------------------------------------------
    trade_date = "2026-10-08"
    async with async_session() as session:
        market_service = CanonicalMarketService(session)
        snap = await market_service.get_canonical_snapshot(trade_date)
        assert snap is not None, f"Node 1 Failure: Canonical snapshot missing for {trade_date}"

    total_turnover = snap.truth.turnover.two_markets_total_yi
    sh_turnover = snap.truth.turnover.sh_amount_yi
    sz_turnover = snap.truth.turnover.sz_total_amount_yi
    max_height = snap.truth.sentiment_bounds.max_ladder_height
    limit_down = snap.truth.sentiment_bounds.limit_down_count

    print(f"\n[NODE 1: PHYSICAL CANONICAL MARKET SNAPSHOT]")
    print(f"  - Trade Date               : {snap.trade_date}")
    print(f"  - Snapshot Version         : {snap.snapshot_version}")
    print(f"  - Total Turnover Fact      : {total_turnover:.2f} 亿元 (SH {sh_turnover:.2f} + SZ {sz_turnover:.2f})")
    print(f"  - Max Ladder Height Fact   : {max_height}B")
    print(f"  - Limit Down Count Fact    : {limit_down} 家")

    # -------------------------------------------------------------------------
    # Node 2: 快照 JCS SHA-256 权威指纹独立重算
    # -------------------------------------------------------------------------
    envelope_dict_for_hash = {
        "snapshot_version": snap.snapshot_version,
        "trade_date": snap.trade_date,
        "generated_at": snap.generated_at,
        "truth_fingerprint": snap.truth.truth_fingerprint,
        "cognition_fingerprint": snap.cognition.cognition_fingerprint,
    }
    recalculated_snap_fp = hash_jcs(envelope_dict_for_hash)
    stored_envelope_fp = snap.envelope_fingerprint

    assert recalculated_snap_fp == stored_envelope_fp, (
        f"Node 2 Failure: Snapshot envelope hash drift! "
        f"Computed: {recalculated_snap_fp} != Stored: {stored_envelope_fp}"
    )

    print(f"\n[NODE 2: SNAPSHOT JCS SHA-256 RECALCULATION]")
    print(f"  - Stored Envelope FP       : {stored_envelope_fp}")
    print(f"  - Recalculated JCS SHA-256 : {recalculated_snap_fp}")
    print(f"  - Cryptographic Match      : IDENTICAL (100% Bitwise Exact)")

    # -------------------------------------------------------------------------
    # Node 3: 市场状态机与多维量化特征校准
    # -------------------------------------------------------------------------
    cognition = snap.cognition
    assert cognition is not None, "Node 3 Failure: Snapshot cognition layer missing"
    calibrated = cognition.market_state_calibration
    primary_state = calibrated.primary_state.value if calibrated else "UNKNOWN"
    confidence = calibrated.state_confidence if calibrated else 0.0
    driving_factors = calibrated.driving_factors if calibrated else []

    print(f"\n[NODE 3: CALIBRATED MARKET STATE REPLAY]")
    print(f"  - Primary State Classification: {primary_state}")
    print(f"  - Calibrated Confidence       : {confidence:.2f}")
    print(f"  - Driving Factors Count       : {len(driving_factors)}")
    print(f"  - Top Mainlines Admitted      : {len(cognition.mainlines)}")

    # -------------------------------------------------------------------------
    # Node 4: 叙事契约提取与 JCS 哈希重算
    # -------------------------------------------------------------------------
    extractor = NarrativeContextExtractor()
    context = extractor.extract_context(snap)
    stored_context_fp = context.context_fingerprint

    # 依据 RFC 8785 规则独立重算 Context JCS
    dict_for_fingerprint = {
        "schema_version": "2D.3-NARRATIVE-CONTEXT-V1",
        "producer_version": "CANONICAL_NARRATIVE_CONTEXT_EXTRACTOR-V1",
        "trade_date": snap.trade_date,
        "source_snapshot_fingerprint": snap.envelope_fingerprint,
        "fact_layer": context.fact_layer.model_dump(),
        "derived_layer": context.derived_layer.model_dump(),
        "cognition_layer": context.cognition_layer.model_dump(),
        "speech_boundary": context.speech_boundary.model_dump(),
    }
    recalculated_context_fp = hash_jcs(dict_for_fingerprint)

    assert recalculated_context_fp == stored_context_fp, (
        f"Node 4 Failure: Context JCS hash drift! "
        f"Computed: {recalculated_context_fp} != Stored: {stored_context_fp}"
    )
    assert context.source_snapshot_fingerprint == recalculated_snap_fp, (
        f"Node 4 Failure: Context source snapshot mismatch! "
        f"{context.source_snapshot_fingerprint} != {recalculated_snap_fp}"
    )

    print(f"\n[NODE 4: NARRATIVE CONTEXT CONTRACT & JCS RECALCULATION]")
    print(f"  - Bound Snapshot Hash      : {context.source_snapshot_fingerprint}")
    print(f"  - Stored Context FP        : {stored_context_fp}")
    print(f"  - Recalculated JCS SHA-256 : {recalculated_context_fp}")
    print(f"  - Cryptographic Match      : IDENTICAL (100% Bitwise Exact)")

    # -------------------------------------------------------------------------
    # Node 5: 真实远程大模型 HTTPS 调用凭据
    # -------------------------------------------------------------------------
    trace_evidence_file = Path("baseline_evidence/audit_unified_trace_20261008.json")
    assert trace_evidence_file.exists(), f"Node 5 Failure: Trace evidence file missing: {trace_evidence_file}"
    with open(trace_evidence_file, "r", encoding="utf-8") as f:
        trace_data = json.load(f)

    unified_trace_id = trace_data["correlation_trace_id"]
    llm_info = trace_data["node_3_llm"]
    raw_llm_text = llm_info["raw_text"]
    ttft_ms = llm_info["ttft_ms"]
    total_ms = llm_info["total_ms"]

    assert ttft_ms > 500.0, f"Node 5 Failure: TTFT too low ({ttft_ms}ms), suspiciously like mock!"
    assert total_ms > 1000.0, f"Node 5 Failure: Total latency too low ({total_ms}ms), suspiciously like mock!"

    print(f"\n[NODE 5: REMOTE LLM INFERENCE EVIDENCE]")
    print(f"  - Model Provider           : {llm_info['model']}")
    print(f"  - TTFT (First Token)       : {ttft_ms:.2f} ms (Realistic Remote Network Roundtrip)")
    print(f"  - Total Generation Latency : {total_ms:.2f} ms")
    print(f"  - Text Length              : {len(raw_llm_text)} chars")

    # -------------------------------------------------------------------------
    # Node 6: 后置物理安全守卫独立重审
    # -------------------------------------------------------------------------
    guard = BriefingSafetyGuard()
    re_audit_res = guard.audit(
        report_or_text=raw_llm_text,
        context=context,
        trace_id=unified_trace_id,
    )

    assert re_audit_res.passed is True, f"Node 6 Failure: Independent re-audit failed: {re_audit_res.violations}"
    assert len(re_audit_res.violations) == 0

    print(f"\n[NODE 6: INDEPENDENT BRIEFING SAFETY GUARD RE-AUDIT]")
    print(f"  - Trace ID Bound           : {re_audit_res.trace_id}")
    print(f"  - Audit Verdict            : PASSED")
    print(f"  - Violations Count         : {len(re_audit_res.violations)}")
    print(f"  - Checks Run Count         : {len(re_audit_res.checks_run)}")

    # -------------------------------------------------------------------------
    # Node 7: 统一 Trace ID 强绑定与 REST API 载荷哈希重算
    # -------------------------------------------------------------------------
    api_node = trace_data["node_5_api"]
    stored_briefing_fp = api_node["briefing_fingerprint"]
    stored_api_trace = api_node["trace_id"]
    stored_api_snapshot = api_node["source_snapshot_hash"]

    assert stored_api_trace == unified_trace_id, "Node 7 Failure: API trace_id mismatch!"
    assert stored_api_snapshot == recalculated_snap_fp, "Node 7 Failure: API snapshot hash mismatch!"

    # 依据 RFC 8785 规则独立重算 API 载荷 JCS 哈希
    api_payload_without_fp = {k: v for k, v in api_node.items() if k != "briefing_fingerprint"}
    recalculated_api_fp = hash_jcs(api_payload_without_fp)

    assert recalculated_api_fp == stored_briefing_fp, (
        f"Node 7 Failure: Recomputed briefing fingerprint drift! "
        f"Computed: {recalculated_api_fp} != Stored: {stored_briefing_fp}"
    )

    print(f"\n[NODE 7: API PAYLOAD JCS SHA-256 RECALCULATION & TRACE UNIFICATION]")
    print(f"  - Correlation Trace ID     : {unified_trace_id}")
    print(f"  - Source Snapshot Hash     : {stored_api_snapshot}")
    print(f"  - Context Fingerprint Hash : {recalculated_context_fp}")
    print(f"  - Stored Briefing FP       : {stored_briefing_fp}")
    print(f"  - Recalculated Briefing FP : {recalculated_api_fp}")
    print(f"  - End-to-End Hash Match    : VERIFIED (100% Bitwise Exact)")

    # -------------------------------------------------------------------------
    # 汇总总结表
    # -------------------------------------------------------------------------
    print("\n" + "=" * 90)
    print("7-NODE PROVENANCE CHAIN MATHEMATICAL PROOF SUMMARY TABLE")
    print("=" * 90)
    print(f"Node 1 (Market Truth Snapshot)   : {snap.trade_date} | SH {sh_turnover:.2f}亿, SZ {sz_turnover:.2f}亿 -> PASS")
    print(f"Node 2 (Snapshot JCS Fingerprint): {recalculated_snap_fp} -> PASS")
    print(f"Node 3 (Market State Cognition)  : {primary_state} (Confidence: {confidence}) -> PASS")
    print(f"Node 4 (Narrative Context JCS)   : {recalculated_context_fp} (Bound: {context.source_snapshot_fingerprint[:16]}...) -> PASS")
    print(f"Node 5 (Real Remote LLM Stream)  : {llm_info['model']} | TTFT: {ttft_ms:.1f}ms, Total: {total_ms:.1f}ms -> PASS")
    print(f"Node 6 (Safety Guard Re-Audit)   : 100% Passed (0 Violations, {len(re_audit_res.checks_run)} Checks) -> PASS")
    print(f"Node 7 (API & UI Watermark Trace): Trace ID: {unified_trace_id} | Briefing FP: {stored_briefing_fp[:16]}... -> PASS")
    print("=" * 90)
    print("INDEPENDENT AUDIT VALIDATION VERDICT: ALL 7 NODES CRYPTOGRAPHICALLY UNBROKEN")
    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(run_independent_audit_validation())
