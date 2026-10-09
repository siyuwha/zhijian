"""
Phase 3A.3: Intraday REST API & Safety Guard Verification Script
================================================================
上位依据：
- 最高董事会授权令：《VERDICT-PHASE3A2-3A3-20261009》
- 审计基线证据包生成器：直穿真实 SQLite，0 Mock，输出 baseline_evidence/audit_phase3a3_api_evidence.json
"""

import asyncio
import json
import os
import sys
import sqlite3
from decimal import Decimal
from typing import Dict, Any
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.main import app
from backend.app.core.database import async_session
from backend.app.services.intraday_drift_service import (
    IntradayDriftService,
    _INTRADAY_VERDICT_MEMORY_CACHE,
)
from backend.app.services.intraday_safety_guard import (
    IntradaySafetyGuard,
    IntradaySafetyInterceptionError,
    ALLOWED_INTRADAY_BOUNDARY_SET,
)
from backend.app.schemas.intraday_drift_verdict import (
    DriftStateEnum,
    DriftInconclusiveReasonEnum,
    DriftEventCategoryEnum,
    IntradayDriftVerdict,
)
from backend.app.cognition.jcs import hash_jcs


def hamming_distance(hex1: str, hex2: str) -> int:
    val1 = int(hex1, 16)
    val2 = int(hex2, 16)
    xor_val = val1 ^ val2
    return bin(xor_val).count("1")


async def run_audit():
    print("=== [PHASE 3A.3] INTRADAY REST API & SAFETY GUARD AUDIT START ===")
    evidence: Dict[str, Any] = {
        "audit_phase": "Phase 3A.3",
        "description": "盘中安全守卫与只读 REST API 基准核验",
        "scenarios": {},
    }

    _INTRADAY_VERDICT_MEMORY_CACHE.clear()

    # -------------------------------------------------------------------------
    # Scenario 1: 真实未 Mock 物理数据库穿透测试 (2026-10-09)
    # -------------------------------------------------------------------------
    print("\n[Scenario 1] Real physical database penetration...")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/canonical/intraday-drift/2026-10-09?time=10:30:00")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["trade_date"] == "2026-10-09"
        assert data["stage"] == "STAGE_2_MORNING"
        assert len(data["verdict_fingerprint"]) == 64
        assert data["safety_audit_passed"] is True

        evidence["scenarios"]["scenario_1_real_penetration"] = {
            "status_code": resp.status_code,
            "verdict_id": data["verdict_id"],
            "trade_date": data["trade_date"],
            "stage": data["stage"],
            "overall_drift_state": data["overall_drift_state"],
            "verdict_fingerprint": data["verdict_fingerprint"],
            "assertions_count": len(data["assertion_results"]),
            "boundaries_count": len(data["preservation_boundaries"]),
            "safety_audit_passed": data["safety_audit_passed"],
        }
    print(f"  -> Scenario 1 PASS: Verdict {data['verdict_id']}, State={data['overall_drift_state']}")

    # -------------------------------------------------------------------------
    # Scenario 2: 空间标杆炸板一票否决 CRITICAL_BREACH 端到端穿透测试
    # -------------------------------------------------------------------------
    print("\n[Scenario 2] Space leader broken limit critical kill...")
    _INTRADAY_VERDICT_MEMORY_CACHE.clear()
    async with async_session() as session:
        service = IntradayDriftService(session)
        replay_broken = {
            "sh_amount_wan": 2000000,
            "sz_amount_wan": 2800000,
            "indices": [],
            "stocks": [
                {
                    "code": "sh600825",
                    "pre_close": "10.00",
                    "price": "10.15",
                    "high": "11.00",
                    "amount_wan": "60000.00",
                    "volume_wan": "5500.00",
                }
            ],
            "limit_up_count": 40,
            "broken_limit_count": 15,
        }
        verdict = await service.get_or_compute_verdict(
            trade_date="2026-10-09",
            snapshot_time="10:30:00",
            force_replay_data=replay_broken,
        )
        assert verdict.overall_drift_state == DriftStateEnum.CRITICAL_BREACH
        assert DriftEventCategoryEnum.SPACE_LEADER_COLLAPSE in verdict.detected_drift_events
        assert verdict.safety_audit_passed is True

        evidence["scenarios"]["scenario_2_space_leader_critical_kill"] = {
            "verdict_id": verdict.verdict_id,
            "overall_drift_state": verdict.overall_drift_state.value,
            "detected_drift_events": [e.value for e in verdict.detected_drift_events],
            "verdict_fingerprint": verdict.verdict_fingerprint,
            "safety_audit_passed": verdict.safety_audit_passed,
        }
    print(f"  -> Scenario 2 PASS: Critical Breach identified correctly.")

    # -------------------------------------------------------------------------
    # Scenario 3: 安全守卫物理拦截 500 与违规词零泄露测试
    # -------------------------------------------------------------------------
    print("\n[Scenario 3] Safety guard interception 500 and zero leak...")
    guard = IntradaySafetyGuard()
    # 构造含交易诱导违规词的断言
    poisoned_verdict_dict = verdict.model_dump(mode="json")
    poisoned_verdict_dict["verdict_headline"] = "立即全仓买入，坚决抄底做多！"
    poisoned_fp = hash_jcs(poisoned_verdict_dict)
    poisoned_verdict_dict["verdict_fingerprint"] = poisoned_fp
    poisoned_verdict = IntradayDriftVerdict(**poisoned_verdict_dict)

    intercepted = False
    safe_error_payload = {}
    try:
        guard.audit_verdict(poisoned_verdict)
    except IntradaySafetyInterceptionError as e:
        intercepted = True
        safe_error_payload = e.to_safe_error_detail()
        assert "买入" not in json.dumps(safe_error_payload)
        assert "做多" not in json.dumps(safe_error_payload)
        assert safe_error_payload["error_code"] == "ERR_INTRADAY_SAFETY_INTERCEPTION"

    assert intercepted is True
    evidence["scenarios"]["scenario_3_safety_guard_interception"] = {
        "intercepted": True,
        "safe_error_payload": safe_error_payload,
        "zero_leak_verified": True,
    }
    print("  -> Scenario 3 PASS: Interception executed, zero leak confirmed.")

    # -------------------------------------------------------------------------
    # Scenario 4: 非交易日平稳降级 INCONCLUSIVE 零时钟漂移测试
    # -------------------------------------------------------------------------
    print("\n[Scenario 4] Non-trading day smooth degradation...")
    _INTRADAY_VERDICT_MEMORY_CACHE.clear()
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/v1/canonical/intraday-drift/2026-10-11?time=10:30:00")
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_drift_state"] == "INCONCLUSIVE"
        assert data["inconclusive_reason"] == "MARKET_CLOSED"
        assert data["evaluated_at"] == "2026-10-11T10:30:00+08:00"

        evidence["scenarios"]["scenario_4_non_trading_day"] = {
            "status_code": resp.status_code,
            "overall_drift_state": data["overall_drift_state"],
            "inconclusive_reason": data["inconclusive_reason"],
            "evaluated_at": data["evaluated_at"],
            "verdict_fingerprint": data["verdict_fingerprint"],
        }
    print("  -> Scenario 4 PASS: Non-trading day correctly degraded.")

    # -------------------------------------------------------------------------
    # Scenario 5: 10x 并发请求全字节级恒定幂等测试
    # -------------------------------------------------------------------------
    print("\n[Scenario 5] 10x concurrent requests byte-for-byte idempotence...")
    _INTRADAY_VERDICT_MEMORY_CACHE.clear()
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        tasks = [
            client.get("/api/v1/canonical/intraday-drift/2026-10-09?time=10:30:00")
            for _ in range(10)
        ]
        responses = await asyncio.gather(*tasks)
        body_hashes = set(hash_jcs(r.json()) for r in responses)
        assert len(body_hashes) == 1, "Concurrency returned differing bodies!"

        evidence["scenarios"]["scenario_5_concurrency_idempotence"] = {
            "concurrent_count": 10,
            "distinct_body_hashes": len(body_hashes),
            "common_body_hash": list(body_hashes)[0],
            "status_codes": [r.status_code for r in responses],
        }
    print(f"  -> Scenario 5 PASS: 10x concurrent requests identical: {list(body_hashes)[0]}")

    # -------------------------------------------------------------------------
    # Scenario 6: SQLite 物理只读连接拒止测试
    # -------------------------------------------------------------------------
    print("\n[Scenario 6] SQLite physical readonly denial...")
    db_path = os.path.abspath("data/trading.db")
    ro_uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(ro_uri, uri=True)
    write_denied = False
    try:
        cur = conn.cursor()
        cur.execute("INSERT INTO system_config (key, value) VALUES ('audit_3a3_hack', 'illegal')")
        conn.commit()
    except sqlite3.OperationalError as e:
        write_denied = True
        denial_msg = str(e)
    finally:
        conn.close()

    assert write_denied is True
    evidence["scenarios"]["scenario_6_physical_readonly"] = {
        "uri": ro_uri,
        "write_denied": True,
        "denial_error": denial_msg,
    }
    print(f"  -> Scenario 6 PASS: Write denied: {denial_msg}")

    # -------------------------------------------------------------------------
    # Scenario 7: RFC 8785 JCS 防篡改雪崩效应证明
    # -------------------------------------------------------------------------
    print("\n[Scenario 7] RFC 8785 JCS avalanche effect...")
    base_verdict_dict = verdict.model_dump(mode="json")
    fp_original = base_verdict_dict["verdict_fingerprint"]

    # 篡改成交额或标杆数据 0.01
    tampered_dict = json.loads(json.dumps(base_verdict_dict))
    tampered_dict["elapsed_trading_minutes"] = 61
    fp_tampered = hash_jcs(tampered_dict)
    distance = hamming_distance(fp_original, fp_tampered)

    assert fp_original != fp_tampered
    assert distance > 100, f"Avalanche distance too low: {distance} bits"
    evidence["scenarios"]["scenario_7_avalanche_effect"] = {
        "fp_original": fp_original,
        "fp_tampered": fp_tampered,
        "hamming_distance_bits": distance,
        "avalanche_ratio": f"{distance / 256.0:.2%}",
    }
    print(f"  -> Scenario 7 PASS: Hamming distance {distance}/256 bits ({distance / 256.0:.2%})")

    # 写入基线证据文件
    evidence_path = os.path.abspath("baseline_evidence/audit_phase3a3_api_evidence.json")
    os.makedirs(os.path.dirname(evidence_path), exist_ok=True)
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)

    print(f"\n=== [PHASE 3A.3] AUDIT COMPLETE -> {evidence_path} ===")
    return evidence


if __name__ == "__main__":
    asyncio.run(run_audit())
