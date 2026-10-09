"""
Phase 3A.2: Intraday Drift Verdict Contract (盘中认知偏离判定与证伪契约)
=======================================================================
上位依据：
1. 最高董事会终审裁决令：《DOC-92 APPROVED WITH REMEDIATIONS & PHASE 3A.1 AUTHORIZED》
2. 《DOC-92 · Phase 3A 盘中 4 阶段动态跟踪与认知偏离实时告警系统技术设计单》

刚性工程准则：
- 严格先质检再断言原则：数据不全或休市强制路由至 INCONCLUSIVE；
- 空间标杆炸板/跌破关键位具备 CRITICAL_KILL 一票否决权；
- 严格封闭安全行动边界词典，坚决阻断任何交易诱导指令；
- 继承 RFC 8785 JCS 不可变数字指纹与单向因果链。
"""

from typing import List, Optional, Dict, Any
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

from backend.app.schemas.canonical_intraday import IntradayStageEnum
from backend.app.schemas.popper_verdict import AssertionItemVerdict, AssertionSeverityEnum


class DriftStateEnum(str, Enum):
    """
    盘中认知偏离判定状态（MECE 互斥状态枚举）
    """
    NORMAL = "NORMAL"                     # 盘面演进吻合假说预设，处于正常容差区间
    DRIFT_WARNING = "DRIFT_WARNING"       # 中度偏离预警 (主线分歧或量能轻度不及预期)
    CRITICAL_BREACH = "CRITICAL_BREACH"   # 严重破位证伪 (空间板炸板翻绿或主线全面倒戈，一票否决)
    INCONCLUSIVE = "INCONCLUSIVE"         # 证据不足/休市/质量降级，无法进行科学裁判


class DriftInconclusiveReasonEnum(str, Enum):
    """
    INCONCLUSIVE 状态的细分根因
    """
    MARKET_CLOSED = "MARKET_CLOSED"                             # 物理休市 / 盘前盘后 / 非交易日
    DATA_QUALITY_DEGRADED = "DATA_QUALITY_DEGRADED"             # 上游数据质量降级
    TARGET_MISSING_OR_SUSPENDED = "TARGET_MISSING_OR_SUSPENDED" # 核心观测标的缺失或停牌
    CAUSAL_TEMPORAL_VIOLATION = "CAUSAL_TEMPORAL_VIOLATION"     # 因果时间戳倒置异常


class DriftEventCategoryEnum(str, Enum):
    """
    盘中突发异动偏离事件类型
    """
    SPACE_LEADER_COLLAPSE = "SPACE_LEADER_COLLAPSE"       # 空间标杆炸板或深水走弱 (一票否决)
    MAINLINE_TOTAL_REVERSAL = "MAINLINE_TOTAL_REVERSAL"   # 核心主线龙头集体由涨转跌破位
    LIQUIDITY_FLASH_DRY = "LIQUIDITY_FLASH_DRY"           # 量能断崖式衰减超容忍下限
    BREADTH_PANIC_DIVERGENCE = "BREADTH_PANIC_DIVERGENCE" # 炸板率畸高或跌停潮涌现


class IntradayDriftVerdict(BaseModel):
    """
    盘中动态认知偏离判定结果权威契约 (Phase 3A.2 核心交付物)
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict_id: str = Field(..., description="对账单全局唯一标识 VERDICT-YYYY-MM-DD-INTRADAY-<hash8>")
    trade_date: str = Field(..., description="对账评估交易日 YYYY-MM-DD")
    evaluated_at: str = Field(..., description="评估执行时间 ISO-8601 (YYYY-MM-DDTHH:MM:SS+08:00)")
    stage: IntradayStageEnum = Field(..., description="评估时所处盘中 4 阶段时间窗口")
    elapsed_trading_minutes: int = Field(..., ge=0, le=240, description="已交易分钟数")
    trace_id: str = Field(..., description="贯穿式单请求 Trace ID")

    # 五位一体防伪锚点
    hypothesis_id: str = Field(..., description="绑定的原始不可变假说 ID")
    hypothesis_fingerprint: str = Field(..., description="原始假说 JCS SHA-256 指纹")
    intraday_snapshot_fingerprint: str = Field(..., description="消费的盘中微观快照 JCS SHA-256 指纹")
    rule_version: str = Field(..., description="断言规则集静态版本号")
    threshold_config_hash: str = Field(..., description="阈值配置参数 JCS SHA-256 指纹")

    # 裁决结论与偏离事件
    overall_drift_state: DriftStateEnum = Field(..., description="综合认知偏离判定结论")
    inconclusive_reason: Optional[DriftInconclusiveReasonEnum] = Field(
        None, description="当且仅当 overall_drift_state 为 INCONCLUSIVE 时的具体原因"
    )
    verdict_headline: str = Field(..., description="受约束的客观事实一句话全貌")
    detected_drift_events: List[DriftEventCategoryEnum] = Field(
        default_factory=list, description="检测到的突发异动偏离事件列表"
    )

    # 微观客观断言证据链
    assertion_results: List[AssertionItemVerdict] = Field(
        default_factory=list, description="各项微观客观断言逐项判定证据链"
    )

    # 封闭安全防守边界 (严禁买卖诱导)
    preservation_boundaries: List[str] = Field(
        default_factory=list, description="机器推导的客观防守行动边界条件"
    )

    safety_audit_passed: bool = Field(True, description="是否通过安全审查")
    verdict_fingerprint: str = Field(..., description="对账单全字段 (除自身外) RFC 8785 JCS SHA-256 防伪指纹")
