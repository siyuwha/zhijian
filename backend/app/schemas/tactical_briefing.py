"""
Phase 2D.3-B: Tactical Briefing Schema Contract
================================================
上位依据：
1. 最高董事会 2026-10-09 裁决令：《Phase 2D.3-B 授权与安全防线规范》
2. 《DOC-80 · Phase 2D.3 受约束 LLM 实战战报生成器技术设计单》

核心设计哲学：
- 操盘内参战报必须基于 NarrativeContextContract 单向只读生成；
- 战报必须包含结构化战场、风险警告与次日证伪防守线；
- 战报必须具备 RFC 8785 JCS 数字指纹，并与来源 NarrativeContextContract 指纹强绑定；
- 必须通过 BriefingSafetyGuard 双轨物理拦截审查。
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class SafetyAuditResult(BaseModel):
    """
    后置安全合规审查结果 (BriefingSafetyGuard Audit Result)
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool = Field(..., description="是否通过全量安全合规审查")
    trade_date: str = Field(..., description="业务交易日期 YYYY-MM-DD")
    trace_id: Optional[str] = Field(None, description="全链路调用追踪 ID")
    audited_at: str = Field(..., description="审查完成时间 ISO-8601")
    checks_run: List[str] = Field(..., description="已执行的合规检查项列表")
    violations: List[str] = Field(default_factory=list, description="违规项详情列表 (空表示无违规)")
    sanitized_text: Optional[str] = Field(None, description="若经过消毒处理的文本")


class TacticalBriefingReport(BaseModel):
    """
    操盘手内参实战战报权威契约 (Phase 2D.3)
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field("2D.3-TACTICAL-BRIEFING-V1", description="战报契约规范版本")
    producer_version: str = Field("CANONICAL_TACTICAL_BRIEFING_ENGINE-V1", description="生成引擎版本")
    trade_date: str = Field(..., description="业务交易日期 YYYY-MM-DD")
    trace_id: str = Field("TRACE-20261008-CANONICAL-DEFAULT", description="全链路唯一可复核调用追踪 ID")
    source_snapshot_hash: str = Field("926200c87eb19e07547d3e6ce5f780c44b2943313a499f69a68560880a49cc52", description="上游物理快照 SHA-256 哈希")
    llm_metrics: Optional[dict] = Field(None, description="真实 LLM 网络推理指标")
    generated_at: str = Field(..., description="战报生成时间 ISO-8601")
    market_state_label: str = Field(..., description="状态机标定中文名称 (如 '高位剧烈分化期')")
    tactical_briefing_text: str = Field(..., min_length=150, max_length=600, description="操盘内参正文 (250~350字)")
    key_battlegrounds: List[str] = Field(..., min_length=1, description="核心战场主线提炼")
    risk_warnings: List[str] = Field(..., min_length=1, description="主要亏钱效应与监管风险点")
    next_day_observation_posts: List[str] = Field(..., min_length=1, description="次日竞价核心观察哨与证伪条件")
    is_fallback_mode: bool = Field(False, description="是否处于确定性模板降级模式")
    fallback_reason: Optional[str] = Field(None, description="降级原因说明 (若处于降级模式)")
    safety_audit_passed: bool = Field(True, description="是否通过 BriefingSafetyGuard 合规审查")
    source_context_fingerprint: str = Field(..., description="来源 NarrativeContextContract JCS 指纹")
    briefing_fingerprint: str = Field(..., description="RFC 8785 JCS 内容数字签名 (SHA-256)")
