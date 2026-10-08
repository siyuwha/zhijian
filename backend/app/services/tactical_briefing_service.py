"""
Phase 2D.3-B: Tactical Briefing Service (Dual-Track Architecture)
================================================================
上位依据：
1. 最高董事会 2026-10-09 裁决令：《Phase 2D.3-B 授权与安全防线规范》
2. 《DOC-80 · Phase 2D.3 受约束 LLM 实战战报生成器技术设计单》

核心架构：
- 双轨制保底机制 (Dual-Track Guardrail & Fallback)；
- 接收待发布候选战报（来自 LLM 或模拟源）；
- 通过 BriefingSafetyGuard 刚性拦截审查；
- 审查通过则签署发布；若审查失败或无候选文本，50ms 内无感降级为 DeterministicBriefingFallbackEngine 模板战报。
"""

from typing import Optional, List
from datetime import datetime

from backend.app.schemas.narrative_context import NarrativeContextContract
from backend.app.schemas.tactical_briefing import (
    TacticalBriefingReport,
    SafetyAuditResult,
)
from backend.app.services.briefing_safety_guard import BriefingSafetyGuard
from backend.app.services.briefing_fallback_engine import DeterministicBriefingFallbackEngine
from backend.app.cognition.jcs import hash_jcs


class TacticalBriefingService:
    """
    操盘手内参战报综合服务 (双轨制安全防线)
    """

    def __init__(
        self,
        safety_guard: Optional[BriefingSafetyGuard] = None,
        fallback_engine: Optional[DeterministicBriefingFallbackEngine] = None,
    ):
        self.safety_guard = safety_guard or BriefingSafetyGuard()
        self.fallback_engine = fallback_engine or DeterministicBriefingFallbackEngine(
            safety_guard=self.safety_guard
        )

    def produce_briefing(
        self,
        context: NarrativeContextContract,
        candidate_text: Optional[str] = None,
        key_battlegrounds: Optional[List[str]] = None,
        risk_warnings: Optional[List[str]] = None,
        next_day_observation_posts: Optional[List[str]] = None,
        generated_at: str = "2026-10-09T03:00:00Z",
    ) -> TacticalBriefingReport:
        """
        生产并发布符合审计门禁的 TacticalBriefingReport
        1. 若无候选文本，直接调用确定性保底引擎；
        2. 若有候选文本，经 BriefingSafetyGuard 严格审查；
        3. 审查通过则封装发布；审查未通过则无感降级并记录违规原因。
        """
        # 情况 A: 无外部输入候选文本，直接由确定性保底引擎生成
        if not candidate_text:
            return self.fallback_engine.generate_fallback_briefing(
                context=context,
                fallback_reason="No external candidate provided; default deterministic engine activated",
                generated_at=generated_at,
            )

        state_label = context.cognition_layer.market_state.state_display_name
        top_ml = context.cognition_layer.candidate_mainlines[0] if context.cognition_layer.candidate_mainlines else None
        battlegrounds = key_battlegrounds or (
            [
                f"{m.sector_name} (龙头【{m.leader_identity.canonical_name}】{m.leader_height}B)"
                for m in context.cognition_layer.candidate_mainlines[:3]
            ]
            if context.cognition_layer.candidate_mainlines
            else [f"全市场高位梯队 (空间标杆【{context.fact_layer.ladder.space_leader.canonical_name}】{context.fact_layer.ladder.max_height}B)"]
        )
        risks = risk_warnings or [
            f"日内真实炸板率高达 {context.derived_layer.broken_limit_ratio * 100:.2f}%",
            f"收盘跌停 {context.fact_layer.sentiment_counts.limit_down_count} 家",
            f"严重异常波动监控 {context.fact_layer.regulatory.total_anomaly_count} 家",
        ]
        falsification_str = (
            top_ml.falsification_condition.invalidation_rules[0]
            if top_ml and top_ml.falsification_condition and top_ml.falsification_condition.invalidation_rules
            else f"空间标杆【{context.fact_layer.ladder.space_leader.canonical_name}】次日竞价大幅低开或走弱"
        )
        observations = next_day_observation_posts or [
            f"空间标杆【{context.fact_layer.ladder.space_leader.canonical_name}】竞价承接力",
            f"证伪观察：{falsification_str}",
        ]

        audit_res: SafetyAuditResult = self.safety_guard.audit(
            report_or_text=candidate_text,
            context=context,
            key_battlegrounds=battlegrounds,
            risk_warnings=risks,
            next_day_observation_posts=observations,
        )

        if audit_res.passed:
            # 审查通过，构建主干战报

            payload = {
                "schema_version": "2D.3-TACTICAL-BRIEFING-V1",
                "producer_version": "CANONICAL_TACTICAL_BRIEFING_ENGINE-V1",
                "trade_date": context.trade_date,
                "generated_at": generated_at,
                "market_state_label": state_label,
                "tactical_briefing_text": candidate_text.strip(),
                "key_battlegrounds": battlegrounds,
                "risk_warnings": risks,
                "next_day_observation_posts": observations,
                "is_fallback_mode": False,
                "fallback_reason": None,
                "safety_audit_passed": True,
                "source_context_fingerprint": context.context_fingerprint,
            }
            payload["briefing_fingerprint"] = hash_jcs(payload)
            return TacticalBriefingReport(**payload)

        # 情况 C: 审查失败，记录违规并无感降级
        violation_reason = f"Candidate intercepted by Safety Guard: {'; '.join(audit_res.violations)}"
        return self.fallback_engine.generate_fallback_briefing(
            context=context,
            fallback_reason=violation_reason,
            generated_at=generated_at,
        )
