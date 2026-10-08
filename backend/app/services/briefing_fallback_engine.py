"""
Phase 2D.3-B: Deterministic Briefing Fallback Engine
===================================================
上位依据：
1. 最高董事会 2026-10-09 裁决令：《Phase 2D.3-B 授权与安全防线规范》
2. 《DOC-80 · Phase 2D.3 受约束 LLM 实战战报生成器技术设计单》

核心职责：
- 当下游 LLM 发生超时、崩溃或被 BriefingSafetyGuard 拦截时，触发 100% 确定性保底模板生成；
- 50ms 极速响应（内存格式化耗时通常 < 5ms）；
- 绝对保真：所引用的所有数字、股票名称、主线层级、证伪红线全部 1:1 来自 NarrativeContextContract；
- 绝对合规：100% 通过 BriefingSafetyGuard 审查，零交易指令，零 002242 实体漂移；
- 10x JCS 哈希恒定（SHA-256 签名幂等）。
"""

from typing import List, Optional
from datetime import datetime

from backend.app.schemas.narrative_context import NarrativeContextContract
from backend.app.schemas.tactical_briefing import (
    TacticalBriefingReport,
    SafetyAuditResult,
)
from backend.app.services.briefing_safety_guard import BriefingSafetyGuard
from backend.app.cognition.jcs import hash_jcs


class DeterministicBriefingFallbackEngine:
    """
    确定性保底战报生成引擎 (Deterministic Briefing Fallback Engine)
    """

    def __init__(self, safety_guard: Optional[BriefingSafetyGuard] = None):
        self.safety_guard = safety_guard or BriefingSafetyGuard()

    def generate_fallback_briefing(
        self,
        context: NarrativeContextContract,
        fallback_reason: str = "Deterministic Fallback Activated (Safety Guard or Generator Fallback)",
        generated_at: str = "2026-10-09T03:00:00Z",
    ) -> TacticalBriefingReport:
        """
        基于 NarrativeContextContract 确定性生成操盘手内参实战战报
        """
        fact = context.fact_layer
        derived = context.derived_layer
        cog = context.cognition_layer

        # 1. 提取客观量化数据
        total_turnover = fact.turnover.total_turnover_yi
        sh_turnover = fact.turnover.sh_amount_yi
        sz_turnover = fact.turnover.sz_total_amount_yi
        state_label = cog.market_state.state_display_name
        confidence_pct = int(cog.market_state.state_confidence * 100)
        broken_pct = derived.broken_limit_ratio * 100
        limit_down = fact.sentiment_counts.limit_down_count
        anomaly_count = fact.regulatory.total_anomaly_count
        max_height = fact.ladder.max_height
        space_leader_name = fact.ladder.space_leader.canonical_name

        # 2. 提取核心主线与龙头
        mainlines = cog.candidate_mainlines
        top_ml = mainlines[0] if mainlines else None
        second_ml = mainlines[1] if len(mainlines) > 1 else None

        ml1_text = (
            f"第一主线为【{top_ml.sector_name}】（龙头【{top_ml.leader_identity.canonical_name}】{top_ml.leader_height}B，涨停 {top_ml.limit_up_count} 家）"
            if top_ml else "暂无单一明确主线"
        )
        ml2_text = (
            f"，第二主线为【{second_ml.sector_name}】（龙头【{second_ml.leader_identity.canonical_name}】{second_ml.leader_height}B）"
            if second_ml else ""
        )

        if top_ml and top_ml.falsification_condition and top_ml.falsification_condition.invalidation_rules:
            falsification_summary = top_ml.falsification_condition.invalidation_rules[0]
        else:
            falsification_summary = "核心龙头竞价承接力不足且出现大面积封单溃退"

        # 3. 模板化组装符合 250~350 字操盘手内参文风的正文
        part1 = (
            f"【大势定调】沪深两市真实总成交额为 {total_turnover:.2f} 亿元"
            f"（沪市 {sh_turnover:.2f} 亿元，深市含创业板 {sz_turnover:.2f} 亿元）。"
            f"全市场微观状态标定为【{state_label}】（判定置信度 {confidence_pct}%）。"
        )
        part2 = (
            f"【主线与梯队】核心做多战场呈现结构分化：{ml1_text}{ml2_text}。"
            f"全市场最高连板高度标杆为 {max_height}B【{space_leader_name}】。"
        )
        part3 = (
            f"【风险与负反馈】盘面微观亏钱效应显著：日内真实炸板率高达 {broken_pct:.2f}%，"
            f"收盘跌停 {limit_down} 家；交易所严重异常波动重点监控标的达 {anomaly_count} 家，"
            f"高位分化与监管降温压制明显。"
        )
        part4 = (
            f"【明日推演与防守红线】次日竞价重点观察空间标杆【{space_leader_name}】溢价承接力"
            f"与主线标杆【{top_ml.leader_identity.canonical_name if top_ml else space_leader_name}】竞价分歧度。"
            f"核心证伪红线：{falsification_summary}。"
        )

        tactical_text = f"{part1}{part2}{part3}{part4}"

        # 4. 组装结构化战场、风险警告与观察哨
        key_battlegrounds: List[str] = [
            f"{m.sector_name} (龙头【{m.leader_identity.canonical_name}】{m.leader_height}B, 涨停 {m.limit_up_count} 家)"
            for m in mainlines[:3]
        ]
        risk_warnings: List[str] = [
            f"日内真实炸板率高达 {broken_pct:.2f}%",
            f"全市场收盘跌停家数达 {limit_down} 家",
            f"交易所严重异常波动重点监控标的达 {anomaly_count} 家",
        ]
        next_day_observation_posts: List[str] = [
            f"最高空间标杆【{space_leader_name}】({max_height}B) 次日竞价承接力与溢价表现",
            f"主线核心标杆【{top_ml.leader_identity.canonical_name if top_ml else space_leader_name}】次日开盘流动性与分歧度",
            f"防守证伪红线：{falsification_summary}",
        ]

        # 5. 计算初步报告对象
        base_payload = {
            "schema_version": "2D.3-TACTICAL-BRIEFING-V1",
            "producer_version": "CANONICAL_TACTICAL_BRIEFING_ENGINE-V1",
            "trade_date": context.trade_date,
            "generated_at": generated_at,
            "market_state_label": state_label,
            "tactical_briefing_text": tactical_text,
            "key_battlegrounds": key_battlegrounds,
            "risk_warnings": risk_warnings,
            "next_day_observation_posts": next_day_observation_posts,
            "is_fallback_mode": True,
            "fallback_reason": fallback_reason,
            "safety_audit_passed": True,
            "source_context_fingerprint": context.context_fingerprint,
        }

        # 6. 计算 RFC 8785 JCS 数字签名指纹
        briefing_fingerprint = hash_jcs(base_payload)
        base_payload["briefing_fingerprint"] = briefing_fingerprint

        report = TacticalBriefingReport(**base_payload)

        # 7. 执行 BriefingSafetyGuard 严苛审查
        audit_res: SafetyAuditResult = self.safety_guard.audit(
            report_or_text=report,
            context=context,
        )
        if not audit_res.passed:
            raise RuntimeError(
                f"Deterministic fallback generation failed internal safety audit: {audit_res.violations}"
            )

        return report
