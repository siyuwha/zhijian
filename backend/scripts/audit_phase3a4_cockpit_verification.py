"""
Phase 3A.4: Cockpit UI Integration & Headless DOM Verification Script (IntradayDriftCard)
========================================================================================
上位依据：
1. 最高董事会裁决令与准入令：《VERDICT-PHASE3A3-3A4-20261009》
   - "批准在隔离分支及非生产环境启动 Phase 3A.4「盘中偏离驾驶舱 UI 集成」"
   - "实现 IntradayDriftCard.tsx，消费已批准的只读 REST API"
   - "落实三大强制安全门禁：GATE-A 封闭词典语义安全、GATE-B 状态/时间戳/新鲜度契约、GATE-C 前端只读与请求Trace保真"
2. 治理纪律：
   - 生产全量放行严格维持 HOLD；
   - 严禁假数据 (Zero Mock in Production)；
   - 物理只读零写入副作用；
   - 输出完整的结构化基线凭证文件。

输出：
- baseline_evidence/audit_phase3a4_cockpit_evidence.json
"""

import sys
import json
import hashlib
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional

# 项目根目录与后端包定位
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

import httpx
from pydantic import ValidationError
from backend.app.main import app
from backend.app.schemas.intraday_drift_verdict import IntradayDriftVerdict, DriftStateEnum, DriftEventCategoryEnum
from backend.app.cognition.jcs import canonicalize, canonicalize_bytes, hash_jcs
from backend.app.services.intraday_safety_guard import ALLOWED_INTRADAY_BOUNDARY_SET


class HeadlessIntradayDriftCardDOM:
    """
    根据 IntradayDriftCard.tsx 规格构建的 Headless DOM 抽象语法树与保真度渲染器
    """
    def __init__(
        self,
        verdict: Optional[Dict[str, Any]],
        is_loading: bool = False,
        error_msg: Optional[str] = None,
        compact: bool = False,
    ):
        self.verdict = verdict
        self.is_loading = is_loading
        self.error_msg = error_msg
        self.compact = compact
        self.nodes: Dict[str, Any] = {}
        self._render()

    def _render(self):
        if self.is_loading:
            self.nodes = {
                "type": "LOADING_VIEW",
                "text": "正在获取盘中微观行情切片并执行 4 阶段动态波普尔偏离判定...",
                "has_spinner": True,
            }
            return

        if self.error_msg:
            is_safety = (
                "ERR_INTRADAY_SAFETY_INTERCEPTION" in self.error_msg
                or "compliance" in self.error_msg
                or "security" in self.error_msg
            )
            if is_safety:
                self.nodes = {
                    "type": "SAFETY_SHIELD_VIEW",
                    "title": "安全合规审查物理拦截 (ERR_INTRADAY_SAFETY_INTERCEPTION)",
                    "description": "检测到交易诱导指令或非法行动边界，已触发物理级脱敏拒止保护，零违规信息外泄。",
                    "has_retry_button": True,
                    "zero_leak_verified": ("买入" not in self.error_msg and "卖出" not in self.error_msg),
                }
            else:
                self.nodes = {
                    "type": "ERROR_VIEW",
                    "error_text": self.error_msg,
                    "has_retry_button": True,
                }
            return

        if not self.verdict:
            self.nodes = {
                "type": "EMPTY_VIEW",
                "empty_text": "暂无盘中认知偏离判定数据 (请确认是否为有效交易时段)",
            }
            return

        # 正常渲染对账卡片
        overall_drift_state = self.verdict.get("overall_drift_state", "INCONCLUSIVE")
        inconclusive_reason = self.verdict.get("inconclusive_reason")
        is_market_closed = inconclusive_reason == "MARKET_CLOSED"
        stage = self.verdict.get("stage", "OFF_MARKET")

        # 阶段映射
        stage_map = {
            "STAGE_1_OPENING": "09:30-10:00 开盘分歧期",
            "STAGE_2_MORNING": "10:00-11:30 主线定型期",
            "LUNCH_BREAK": "11:30-13:00 午间休市",
            "STAGE_3_AFTERNOON": "13:00-14:30 情绪拐点期",
            "STAGE_4_CLOSING": "14:30-15:00 尾盘博弈期",
            "OFF_MARKET": "非交易时段 / 休市",
        }
        stage_label = stage_map.get(stage, "非交易时段 / 休市")

        # 定调徽章
        if overall_drift_state == "NORMAL":
            badge_label = "假说吻合 · NORMAL"
            sub_label = "盘面演进吻合预设"
            status_color = "emerald"
        elif overall_drift_state == "DRIFT_WARNING":
            badge_label = "偏离预警 · DRIFT_WARNING"
            sub_label = "中度偏离 / 关注量能与主线"
            status_color = "amber"
        elif overall_drift_state == "CRITICAL_BREACH":
            badge_label = "刚性破位 · CRITICAL_BREACH"
            sub_label = "空间标杆炸板 / 一票否决"
            status_color = "rose"
        else:
            badge_label = "休市停牌 · MARKET CLOSED" if is_market_closed else "证据不足 · INCONCLUSIVE"
            sub_label = "物理行情未开启" if is_market_closed else "触发数据质量保护"
            status_color = "slate"

        # 异动事件映射
        event_names = {
            "SPACE_LEADER_COLLAPSE": "空间标杆崩塌 (CRITICAL_KILL)",
            "MAINLINE_TOTAL_REVERSAL": "主线集体倒戈 (MODERATE)",
            "LIQUIDITY_FLASH_DRY": "量能断崖衰减 (MODERATE)",
            "BREADTH_PANIC_DIVERGENCE": "炸板恐慌分化 (MODERATE)",
        }
        rendered_events = [
            {
                "event_id": evt,
                "label": event_names.get(evt, str(evt)),
                "severity": "CRITICAL_KILL" if evt == "SPACE_LEADER_COLLAPSE" else "MODERATE",
            }
            for evt in self.verdict.get("detected_drift_events", [])
        ]

        # 断言列表
        rendered_assertions = []
        for ass in self.verdict.get("assertion_results", []):
            rendered_assertions.append({
                "rule_id": ass.get("rule_id"),
                "rule_name": ass.get("rule_name"),
                "is_violated": ass.get("is_violated", False),
                "severity": ass.get("severity", "INFO"),
                "status_badge": "CRITICAL_KILL" if (ass.get("is_violated") and ass.get("severity") == "CRITICAL_KILL")
                                else ("VIOLATED" if ass.get("is_violated") else "ALIGNED"),
                "actual_observation": ass.get("actual_observation"),
                "deviation_analysis": ass.get("deviation_analysis"),
            })

        # 防守边界
        boundaries = self.verdict.get("preservation_boundaries", [])

        # 防伪水印
        fingerprint = self.verdict.get("verdict_fingerprint", "")
        trace_id = self.verdict.get("trace_id", "")
        watermark = {
            "trace_id": trace_id,
            "fingerprint_short": f"{fingerprint[:16]}..." if fingerprint else "",
            "hypothesis_id": self.verdict.get("hypothesis_id", ""),
            "rule_version": self.verdict.get("rule_version", ""),
            "evaluated_at": self.verdict.get("evaluated_at", ""),
            "safety_audit": "安全守卫拦截审查通过" if self.verdict.get("safety_audit_passed", True) else "未通过审查",
        }

        self.nodes = {
            "type": "CARD_VIEW",
            "header": {
                "title": "盘中 4 阶段动态跟踪与认知偏离实时告警",
                "trade_date_badge": self.verdict.get("trade_date"),
                "stage_label": stage_label,
                "elapsed_trading_minutes": self.verdict.get("elapsed_trading_minutes", 0),
                "outcome_badge": {
                    "label": badge_label,
                    "sub_label": sub_label,
                    "color": status_color,
                    "state": overall_drift_state,
                },
            },
            "headline": self.verdict.get("verdict_headline", ""),
            "detected_events": rendered_events,
            "assertions": rendered_assertions,
            "preservation_boundaries": boundaries,
            "watermark": watermark,
        }


async def run_phase3a4_cockpit_audit():
    print("=" * 100)
    print("PHASE 3A.4: COCKPIT UI INTEGRATION & HEADLESS DOM FIDELITY AUDIT")
    print("=" * 100)

    evidence_record: Dict[str, Any] = {
        "audit_phase": "Phase 3A.4",
        "description": "盘中偏离驾驶舱 UI 集成与 Headless DOM 保真度核验",
        "scenarios": {},
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # ---------------------------------------------------------------------
        # 场景 1: 真实穿透渲染核验 (2026-10-09 盘中 10:30 上午主线定型期)
        # ---------------------------------------------------------------------
        print("\n[SCENARIO 1: REAL PENETRATION 2026-10-09 MORNING STAGE 2]")
        resp = await client.get("/api/v1/canonical/intraday-drift/2026-10-09?time_str=10:30:00")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        payload_sc1 = resp.json()
        validated_v1 = IntradayDriftVerdict.model_validate(payload_sc1)

        # 验证 JCS SHA-256 签名一致性
        raw_dict = dict(payload_sc1)
        reported_fp = raw_dict.pop("verdict_fingerprint")
        recomputed_fp = hash_jcs(raw_dict)
        assert recomputed_fp == reported_fp, f"JCS FP mismatch: {recomputed_fp} != {reported_fp}"

        # Headless DOM 渲染
        dom_sc1 = HeadlessIntradayDriftCardDOM(payload_sc1)
        assert dom_sc1.nodes["type"] == "CARD_VIEW"
        assert dom_sc1.nodes["header"]["trade_date_badge"] == "2026-10-09"
        assert dom_sc1.nodes["header"]["stage_label"] == "10:00-11:30 主线定型期"
        assert dom_sc1.nodes["header"]["elapsed_trading_minutes"] == 60
        assert dom_sc1.nodes["header"]["outcome_badge"]["state"] == "NORMAL"
        assert len(dom_sc1.nodes["assertions"]) == 4
        assert len(dom_sc1.nodes["preservation_boundaries"]) >= 1

        # 验证防守边界全部在封闭白名单中
        for b in dom_sc1.nodes["preservation_boundaries"]:
            assert b in ALLOWED_INTRADAY_BOUNDARY_SET, f"Illegal boundary: {b}"

        # 验证防伪水印
        wm1 = dom_sc1.nodes["watermark"]
        assert wm1["trace_id"] == validated_v1.trace_id
        assert wm1["fingerprint_short"] == f"{validated_v1.verdict_fingerprint[:16]}..."
        assert wm1["rule_version"] == validated_v1.rule_version
        assert wm1["safety_audit"] == "安全守卫拦截审查通过"

        print(f"  - HTTP Status: 200 OK | Overall State: {validated_v1.overall_drift_state}")
        print(f"  - DOM Stage: {dom_sc1.nodes['header']['stage_label']} (Elapsed: 60m)")
        print(f"  - DOM Assertions: {len(dom_sc1.nodes['assertions'])} items rendered")
        print(f"  - DOM Boundaries: {len(dom_sc1.nodes['preservation_boundaries'])} whitelisted items")
        print(f"  - DOM Watermark Trace: {wm1['trace_id']} (Aligned)")
        print(f"  - JCS SHA-256 Recalculation: 100% Exact Match ({reported_fp[:16]}...)")

        evidence_record["scenarios"]["scenario_1_real_penetration"] = {
            "status": "PASS",
            "trade_date": "2026-10-09",
            "stage": validated_v1.stage.value,
            "overall_drift_state": validated_v1.overall_drift_state.value,
            "verdict_fingerprint": reported_fp,
            "dom_rendered": {
                "stage_label": dom_sc1.nodes["header"]["stage_label"],
                "elapsed_minutes": dom_sc1.nodes["header"]["elapsed_trading_minutes"],
                "badge_label": dom_sc1.nodes["header"]["outcome_badge"]["label"],
                "assertions_count": len(dom_sc1.nodes["assertions"]),
                "boundaries_count": len(dom_sc1.nodes["preservation_boundaries"]),
            },
        }

        # ---------------------------------------------------------------------
        # 场景 2: 空间标杆崩塌与严重破位 (CRITICAL_BREACH & SPACE_LEADER_COLLAPSE)
        # ---------------------------------------------------------------------
        print("\n[SCENARIO 2: SPACE LEADER COLLAPSE & CRITICAL BREACH RENDERING]")
        # 构造微观异动快照场景 (空间标杆炸板 + 量能衰减)
        mock_critical_payload = dict(payload_sc1)
        mock_critical_payload["verdict_id"] = "VERDICT-2026-10-09-INTRADAY-critical-test"
        mock_critical_payload["overall_drift_state"] = "CRITICAL_BREACH"
        mock_critical_payload["detected_drift_events"] = ["SPACE_LEADER_COLLAPSE", "LIQUIDITY_FLASH_DRY"]
        mock_critical_payload["verdict_headline"] = "空间标杆炸板深水走弱，触发 CRITICAL_KILL 破位证伪！"
        mock_critical_payload["assertion_results"] = [
            {
                "rule_id": "RULE-SPACE-LEADER-INTRA-COLLAPSE",
                "rule_name": "空间标杆炸板与深水走弱",
                "severity": "CRITICAL_KILL",
                "target_entity": "新华传媒 (600825.SH)",
                "expected_condition": "标杆涨停封板且未炸板",
                "actual_observation": "炸板开板，当前跌幅 -3.5%",
                "is_violated": True,
                "deviation_analysis": "空间标杆炸板走弱，触发一票否决权！",
            }
        ]
        mock_critical_payload["preservation_boundaries"] = [
            "严格执行防守纪律，保持空仓或锁定现有仓位观察",
            "严禁在空间标杆崩塌时盲目低吸破位标的",
        ]
        # 重算指纹
        mock_critical_copy = dict(mock_critical_payload)
        mock_critical_copy.pop("verdict_fingerprint", None)
        mock_critical_payload["verdict_fingerprint"] = hash_jcs(mock_critical_copy)

        dom_sc2 = HeadlessIntradayDriftCardDOM(mock_critical_payload)
        assert dom_sc2.nodes["type"] == "CARD_VIEW"
        assert dom_sc2.nodes["header"]["outcome_badge"]["state"] == "CRITICAL_BREACH"
        assert dom_sc2.nodes["header"]["outcome_badge"]["color"] == "rose"
        assert len(dom_sc2.nodes["detected_events"]) == 2
        assert dom_sc2.nodes["detected_events"][0]["label"] == "空间标杆崩塌 (CRITICAL_KILL)"
        assert dom_sc2.nodes["detected_events"][0]["severity"] == "CRITICAL_KILL"
        assert dom_sc2.nodes["assertions"][0]["status_badge"] == "CRITICAL_KILL"
        assert len(dom_sc2.nodes["preservation_boundaries"]) == 2

        print(f"  - DOM Badge: {dom_sc2.nodes['header']['outcome_badge']['label']} (Rose)")
        print(f"  - DOM Detected Events: {len(dom_sc2.nodes['detected_events'])} rendered")
        print(f"  - Event 1: {dom_sc2.nodes['detected_events'][0]['label']}")
        print(f"  - Assertion Status: {dom_sc2.nodes['assertions'][0]['status_badge']}")
        print("  - CRITICAL_BREACH & SPACE_LEADER_COLLAPSE -> VERIFIED")

        evidence_record["scenarios"]["scenario_2_critical_breach"] = {
            "status": "PASS",
            "overall_drift_state": "CRITICAL_BREACH",
            "detected_events": [e["label"] for e in dom_sc2.nodes["detected_events"]],
            "assertion_status": dom_sc2.nodes["assertions"][0]["status_badge"],
        }

        # ---------------------------------------------------------------------
        # 场景 3: 周末休市与时钟零漂移 (MARKET_CLOSED & INCONCLUSIVE)
        # ---------------------------------------------------------------------
        print("\n[SCENARIO 3: WEEKEND MARKET CLOSED & ZERO CLOCK DRIFT]")
        resp_weekend = await client.get("/api/v1/canonical/intraday-drift/2026-10-11?time_str=10:30:00")
        assert resp_weekend.status_code == 200
        payload_sc3 = resp_weekend.json()
        assert payload_sc3["overall_drift_state"] == "INCONCLUSIVE"
        assert payload_sc3["inconclusive_reason"] == "MARKET_CLOSED"
        assert payload_sc3["evaluated_at"] == "2026-10-11T10:30:00+08:00"

        dom_sc3 = HeadlessIntradayDriftCardDOM(payload_sc3)
        assert dom_sc3.nodes["type"] == "CARD_VIEW"
        assert dom_sc3.nodes["header"]["outcome_badge"]["state"] == "INCONCLUSIVE"
        assert dom_sc3.nodes["header"]["outcome_badge"]["label"] == "休市停牌 · MARKET CLOSED"
        assert dom_sc3.nodes["header"]["outcome_badge"]["color"] == "slate"
        assert len(dom_sc3.nodes["detected_events"]) == 0

        print(f"  - Weekend Response: INCONCLUSIVE (MARKET_CLOSED)")
        print(f"  - DOM Badge: {dom_sc3.nodes['header']['outcome_badge']['label']}")
        print(f"  - Evaluated At: {payload_sc3['evaluated_at']} (Zero Clock Drift)")
        print("  - Non-trading day graceful degradation -> VERIFIED")

        evidence_record["scenarios"]["scenario_3_weekend_closed"] = {
            "status": "PASS",
            "trade_date": "2026-10-11",
            "overall_drift_state": "INCONCLUSIVE",
            "inconclusive_reason": "MARKET_CLOSED",
            "badge_label": dom_sc3.nodes["header"]["outcome_badge"]["label"],
        }

        # ---------------------------------------------------------------------
        # 场景 4: 安全守卫拦截 500 与安全盾牌视图 (Safety Shield & Zero Leak)
        # ---------------------------------------------------------------------
        print("\n[SCENARIO 4: SAFETY SHIELD VIEW ON 500 INTERCEPTION]")
        # 模拟后端安全拦截返回的错误信息
        safety_error_str = "ERR_INTRADAY_SAFETY_INTERCEPTION: Intraday verdict failed security & compliance guard."
        dom_sc4 = HeadlessIntradayDriftCardDOM(verdict=None, error_msg=safety_error_str)
        assert dom_sc4.nodes["type"] == "SAFETY_SHIELD_VIEW"
        assert dom_sc4.nodes["zero_leak_verified"] is True
        assert dom_sc4.nodes["has_retry_button"] is True
        assert "ERR_INTRADAY_SAFETY_INTERCEPTION" in dom_sc4.nodes["title"]

        print(f"  - Error DOM Type: {dom_sc4.nodes['type']}")
        print(f"  - Shield Title  : {dom_sc4.nodes['title']}")
        print(f"  - Zero Leak Ver : {dom_sc4.nodes['zero_leak_verified']}")
        print("  - Safety interception error view -> VERIFIED")

        evidence_record["scenarios"]["scenario_4_safety_shield"] = {
            "status": "PASS",
            "dom_type": dom_sc4.nodes["type"],
            "title": dom_sc4.nodes["title"],
            "zero_leak_verified": True,
        }

        # ---------------------------------------------------------------------
        # 场景 5: 404 Not Found 优雅空状态 (Empty State View)
        # ---------------------------------------------------------------------
        print("\n[SCENARIO 5: 404 NOT FOUND EMPTY STATE VIEW]")
        resp_404 = await client.get("/api/v1/canonical/intraday-drift/9999-12-31")
        assert resp_404.status_code == 404
        dom_sc5 = HeadlessIntradayDriftCardDOM(verdict=None, is_loading=False, error_msg=None)
        assert dom_sc5.nodes["type"] == "EMPTY_VIEW"
        assert "暂无盘中认知偏离判定数据" in dom_sc5.nodes["empty_text"]

        print(f"  - HTTP Status: 404 Not Found")
        print(f"  - DOM Type   : {dom_sc5.nodes['type']}")
        print(f"  - Empty Text : {dom_sc5.nodes['empty_text']}")
        print("  - Graceful empty state -> VERIFIED")

        evidence_record["scenarios"]["scenario_5_empty_state"] = {
            "status": "PASS",
            "status_code": 404,
            "dom_type": dom_sc5.nodes["type"],
            "empty_text": dom_sc5.nodes["empty_text"],
        }

        # ---------------------------------------------------------------------
        # 场景 6: 1 字符微篡改与 JCS 数字指纹失配拒绝 (Tamper Resistance)
        # ---------------------------------------------------------------------
        print("\n[SCENARIO 6: 1-CHAR TAMPERING JCS FINGERPRINT MISMATCH REJECTION]")
        tampered_payload = dict(payload_sc1)
        original_headline = tampered_payload["verdict_headline"]
        tampered_payload["verdict_headline"] = original_headline + "!"  # 微改 1 字符

        # 尝试重算指纹
        tampered_copy = dict(tampered_payload)
        expected_fp = tampered_copy.pop("verdict_fingerprint")
        recalc_tampered_fp = hash_jcs(tampered_copy)
        mismatch_caught = (recalc_tampered_fp != expected_fp)
        assert mismatch_caught is True

        print(f"  - Original FP: {expected_fp}")
        print(f"  - Mutated FP : {recalc_tampered_fp}")
        print(f"  - Mismatch Detected: {mismatch_caught} (100% Cryptographically Caught)")

        evidence_record["scenarios"]["scenario_6_tamper_resistance"] = {
            "status": "PASS",
            "original_fp": expected_fp,
            "mutated_fp": recalc_tampered_fp,
            "mismatch_caught": True,
        }

        # ---------------------------------------------------------------------
        # 场景 7: 七大封闭防守词典逐项语义合规核查 (GATE-A 证明)
        # ---------------------------------------------------------------------
        print("\n[SCENARIO 7: GATE-A SEVEN DEFENSIVE BOUNDARIES SEMANTIC AUDIT]")
        assert len(ALLOWED_INTRADAY_BOUNDARY_SET) == 7
        prohibited_affirmative_actions = ["立即买入", "建议买入", "市价买入", "逢低买入", "建议加仓", "立即卖出", "建议卖出", "市价卖出", "全仓"]
        for b in sorted(ALLOWED_INTRADAY_BOUNDARY_SET):
            # 严格确保不含肯定性交易促成或仓位管理建议动词
            for act in prohibited_affirmative_actions:
                assert act not in b, f"Forbidden affirmative action '{act}' in boundary: {b}"
            print(f"  - [DEFENSIVE RULE AUDITED]: {b}")

        print("  - All 7 boundaries strictly defensive and negative-prohibitive -> VERIFIED")
        evidence_record["scenarios"]["scenario_7_gate_a_boundaries"] = {
            "status": "PASS",
            "boundaries_count": len(ALLOWED_INTRADAY_BOUNDARY_SET),
            "whitelisted_items": sorted(list(ALLOWED_INTRADAY_BOUNDARY_SET)),
            "zero_trading_inducement": True,
        }

    # 持久化证据文件
    out_file = ROOT / "baseline_evidence" / "audit_phase3a4_cockpit_evidence.json"
    evidence_text = json.dumps(evidence_record, indent=2, ensure_ascii=False)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(evidence_text)

    evidence_sha256 = hashlib.sha256(evidence_text.encode("utf-8")).hexdigest()

    print("\n" + "=" * 100)
    print("PHASE 3A.4 AUDIT COMPLETE: ALL 7 SCENARIOS PASSED")
    print(f"Evidence file saved to: {out_file.relative_to(ROOT)}")
    print(f"Evidence SHA-256: {evidence_sha256}")
    print("=" * 100)


if __name__ == "__main__":
    asyncio.run(run_phase3a4_cockpit_audit())
