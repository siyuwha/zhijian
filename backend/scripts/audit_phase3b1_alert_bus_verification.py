"""
Phase 3B.1: In-Memory Alert Bus Core & Offline Replay Verification Script
========================================================================
上位依据：
- 最高董事会授权令：《VERDICT-PHASE3A-CLOSE-PHASE3B1-GATE-20261009》
- DOC-98 / DOC-99 规范要求
- 审计基线证据包生成器：输出 baseline_evidence/audit_phase3b1_alert_bus_evidence.json
"""

import sys
import os
import json
import sqlite3
import hashlib
from decimal import Decimal
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from backend.app.schemas.canonical_intraday import IntradayStageEnum
from backend.app.schemas.popper_verdict import AssertionItemVerdict, AssertionSeverityEnum
from backend.app.schemas.intraday_drift_verdict import (
    DriftStateEnum,
    DriftInconclusiveReasonEnum,
    DriftEventCategoryEnum,
    IntradayDriftVerdict,
)
from backend.app.schemas.canonical_alert_event import (
    CanonicalDriftAlertEvent,
    AlertSeverityEnum,
    AlertCategoryEnum,
    DEDUP_KEY_REGEX,
)
from backend.app.services.alert_bus_ring_buffer import (
    AlertRingBuffer,
    AlertDeadLetterQueue,
)
from backend.app.services.alert_evaluator import (
    AlertEvaluator,
    AlertLifecycleStateEnum,
)
from backend.app.services.alert_audit_logger import AlertAuditLogger


def build_test_verdict(
    time_str: str = "10:00:00",
    trade_date: str = "2026-10-09",
    state: DriftStateEnum = DriftStateEnum.CRITICAL_BREACH,
    events: list = None,
) -> IntradayDriftVerdict:
    if events is None:
        events = [DriftEventCategoryEnum.SPACE_LEADER_COLLAPSE]
    return IntradayDriftVerdict(
        verdict_id=f"VERDICT-{trade_date}-INTRADAY-12345678",
        trade_date=trade_date,
        evaluated_at=f"{trade_date}T{time_str}+08:00",
        stage=IntradayStageEnum.STAGE_2_MORNING,
        elapsed_trading_minutes=30,
        trace_id=f"TRACE-{trade_date}-001",
        hypothesis_id="HYPO-2026-10-08-001",
        hypothesis_fingerprint="a" * 64,
        intraday_snapshot_fingerprint="b" * 64,
        rule_version="3A.2-V1",
        threshold_config_hash="c" * 64,
        overall_drift_state=state,
        inconclusive_reason=None,
        verdict_headline="空间标杆破位炸板，触发客观风险防御",
        detected_drift_events=events,
        assertion_results=[
            AssertionItemVerdict(
                rule_id="RULE-SPACE-LEADER-STATUS",
                rule_name="空间标杆存续性",
                severity=AssertionSeverityEnum.CRITICAL_KILL,
                target_entity="000001",
                expected_condition="连板封死",
                actual_observation="炸板跌停",
                is_violated=True,
                deviation_analysis="盘中炸板破位，偏离度 100.0%",
            )
        ],
        preservation_boundaries=["空间龙炸板，杜绝追高盲目博弈"],
        safety_audit_passed=True,
        verdict_fingerprint="d" * 64,
    )


def run_verification() -> Dict[str, Any]:
    print("=== [PHASE 3B.1] IN-MEMORY ALERT BUS CORE AUDIT START ===")
    evidence: Dict[str, Any] = {
        "audit_phase": "Phase 3B.1",
        "description": "离线回放与纯内存总线核心基准核验",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scenarios": {},
    }

    # DB baseline pre-check
    db_path = ROOT / "data" / "trading.db"
    assert db_path.exists(), "trading.db does not exist"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    tables = [row[0] for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    pre_counts = {tbl: cur.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0] for tbl in tables}
    conn.close()

    # 1. Dual Signatures & RFC 8785 JCS
    print("\n[Scenario 1] Dual Signatures & RFC 8785 JCS Verification...")
    evaluator = AlertEvaluator(cooldown_seconds=0.0)
    v1 = build_test_verdict("10:00:00")
    t_req = datetime.fromisoformat("2026-10-09T10:01:00+08:00")
    state1, ev1, _ = evaluator.evaluate_and_publish(v1, request_timestamp=t_req)
    assert state1 == AlertLifecycleStateEnum.ACTIVE
    assert ev1 is not None
    assert ev1.verify_signatures() is True
    evidence["scenarios"]["scenario_1_dual_signatures"] = {
        "status": "PASS",
        "content_hash": ev1.content_hash,
        "origin_signature": ev1.origin_signature,
        "data_age_seconds": ev1.data_age_seconds,
        "signature_verified": True,
    }

    # 2. LRU Cooldown Deduplication
    print("\n[Scenario 2] LRU Cooldown Deduplication Verification...")
    dedup_eval = AlertEvaluator(cooldown_seconds=180.0)
    s_first, ev_first, _ = dedup_eval.evaluate_and_publish(v1, request_timestamp=t_req)
    assert s_first == AlertLifecycleStateEnum.ACTIVE
    s_suppressed, ev_sup, msg_sup = dedup_eval.evaluate_and_publish(v1, request_timestamp=t_req + timedelta(seconds=10))
    assert s_suppressed == AlertLifecycleStateEnum.COOLDOWN
    assert ev_sup is None
    evidence["scenarios"]["scenario_2_deduplication"] = {
        "status": "PASS",
        "first_state": s_first.value,
        "second_state": s_suppressed.value,
        "suppression_message": msg_sup,
    }

    # 3. Out-of-Order & Staleness Detection
    print("\n[Scenario 3] Out-of-Order & Staleness Detection...")
    temporal_eval = AlertEvaluator(cooldown_seconds=0.0)
    v_norm = build_test_verdict("10:30:00")
    _, ev_norm, _ = temporal_eval.evaluate_and_publish(v_norm, request_timestamp=datetime.fromisoformat("2026-10-09T10:31:00+08:00"))
    assert ev_norm.is_out_of_order is False
    assert ev_norm.is_stale is False

    v_reverted = build_test_verdict("09:45:00")
    _, ev_rev, _ = temporal_eval.evaluate_and_publish(v_reverted, request_timestamp=datetime.fromisoformat("2026-10-09T10:32:00+08:00"))
    assert ev_rev.is_out_of_order is True
    assert ev_rev.is_stale is True
    assert ev_rev.data_age_seconds == 2820.0
    evidence["scenarios"]["scenario_3_temporal"] = {
        "status": "PASS",
        "forward_is_out_of_order": ev_norm.is_out_of_order,
        "reverted_is_out_of_order": ev_rev.is_out_of_order,
        "reverted_data_age_seconds": ev_rev.data_age_seconds,
        "reverted_is_stale": ev_rev.is_stale,
    }

    # 4. RingBuffer Capacity & CRITICAL Reservation
    print("\n[Scenario 4] RingBuffer Capacity & CRITICAL Reservation...")
    ring = AlertRingBuffer(capacity=10, critical_reservation_quota=3)
    eval_c = AlertEvaluator(ring_buffer=ring, cooldown_seconds=0.0)
    v_c = build_test_verdict("10:00:00", state=DriftStateEnum.CRITICAL_BREACH)
    eval_c.evaluate_and_publish(v_c)
    for i in range(1, 10):
        v_i = build_test_verdict(f"10:{i:02d}:00", state=DriftStateEnum.NORMAL)
        eval_c.evaluate_and_publish(v_i)
    assert ring.size() == 10

    # Overwrite with another event
    v_extra = build_test_verdict("10:15:00", state=DriftStateEnum.DRIFT_WARNING)
    eval_c.evaluate_and_publish(v_extra)
    assert ring.size() == 10
    assert ring.total_overflow_drops == 1
    # Check that CRITICAL is still present
    crit_count = sum(1 for e in ring.get_events() if e.severity == AlertSeverityEnum.CRITICAL)
    assert crit_count >= 1
    evidence["scenarios"]["scenario_4_ring_buffer"] = {
        "status": "PASS",
        "capacity": ring.capacity,
        "final_size": ring.size(),
        "total_overflow_drops": ring.total_overflow_drops,
        "critical_preserved_count": crit_count,
    }

    # 5. DLQ & Snapshot Recovery
    print("\n[Scenario 5] DLQ & Snapshot Recovery...")
    dlq = AlertDeadLetterQueue(capacity=10)
    dlq.push({"test": "poison_pill"}, "Tampered payload")
    assert dlq.size() == 1
    snap = ring.export_snapshot()
    ring2 = AlertRingBuffer(capacity=10)
    restored_count = ring2.restore_from_snapshot(snap)
    assert restored_count == len(snap)
    evidence["scenarios"]["scenario_5_dlq_snapshot"] = {
        "status": "PASS",
        "dlq_items": dlq.size(),
        "snapshot_exported_events": len(snap),
        "snapshot_restored_events": restored_count,
    }

    # 6. Merkle Hash-Chain Tamper-Evident Logger
    print("\n[Scenario 6] Merkle Hash-Chain Logger...")
    log_dir = ROOT / "logs" / "alert_bus_test"
    if log_dir.exists():
        import shutil
        shutil.rmtree(log_dir)
    logger = AlertAuditLogger(str(log_dir))
    line_hash = logger.append_event(ev1)
    log_file = os.path.join(str(log_dir), f"alert_audit_{ev1.trade_date}.jsonl")
    ok, count, err = AlertAuditLogger.verify_audit_log_integrity(log_file)
    assert ok is True, f"Integrity check failed: {err}"
    assert count == 1
    evidence["scenarios"]["scenario_6_merkle_logger"] = {
        "status": "PASS",
        "log_path": str(Path(log_file).relative_to(ROOT)).replace("\\", "/"),
        "verified_lines": count,
        "line_hash": line_hash,
        "integrity_verified": True,
    }
    if log_dir.exists():
        import shutil
        shutil.rmtree(log_dir, ignore_errors=True)

    # 7. Physical DB Read-Only Check
    print("\n[Scenario 7] Physical DB Zero-Write Check...")
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    post_counts = {tbl: cur.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0] for tbl in tables}
    conn.close()
    mutations = {tbl: (post_counts[tbl] - pre_counts[tbl]) for tbl in tables if post_counts[tbl] != pre_counts[tbl]}
    assert len(mutations) == 0, f"Detected DB mutations: {mutations}"
    evidence["scenarios"]["scenario_7_database_immutability"] = {
        "status": "PASS",
        "monitored_tables": len(tables),
        "mutations_count": 0,
        "zero_write_verified": True,
    }

    out_file = ROOT / "baseline_evidence" / "audit_phase3b1_alert_bus_evidence.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2, ensure_ascii=False)

    print(f"\n[DONE] Baseline evidence persisted to: {out_file}")
    with open(out_file, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    print(f"Evidence SHA-256: {sha}")
    return evidence


if __name__ == "__main__":
    run_verification()
