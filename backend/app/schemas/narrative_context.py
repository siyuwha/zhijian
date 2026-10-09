"""
Phase 2D.3-A: Narrative Context Contract (COGNITION-TO-NARRATIVE CONTRACT)
==========================================================================
上位依据：
1. 最高董事会 2026-10-09 裁决令：《有条件批准 Phase 2D.3-A，锁死 7 条刚性红线》
2. 《DOC-80 · Phase 2D.3 受约束 LLM 实战战报生成器技术设计单》

核心设计哲学：
- 机器决定事实 (FACT)。
- 机器决定衍生结构 (DERIVED)。
- 机器决定状态与主线认知 (COGNITION)。
- 机器决定叙事发言边界 (SPEECH BOUNDARY)。
- LLM 只能“表达”，严禁提升证据等级 (严禁 COGNITION -> FACT)，严禁携带交易指令。
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field
from backend.app.schemas.canonical_market import (
    CanonicalSecurityIdentity,
    CanonicalIndexQuote,
    MarketStateEnum,
    StateFeatureVector,
    DataQualityGrade,
    FalsificationCondition,
)


class NarrativeTurnoverFact(BaseModel):
    """L0/L1 成交额事实 (防重算冻结口径)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    total_turnover_yi: float = Field(..., description="沪深两市真实总成交额(亿元)")
    sh_amount_yi: float = Field(..., description="沪市成交额(亿元)")
    sz_total_amount_yi: float = Field(..., description="深市成交额(亿元，已含创业板)")
    chinext_slice_yi: float = Field(..., description="创业板成交额(亿元，结构切片)")
    chinext_ratio_in_sz: float = Field(..., description="创业板占深市比例")
    accounting_rule: str = Field(
        "深市成交额在统计范畴内已包含创业板，沪深两市总成交额 = SH + SZ，严禁将创业板再次累加！",
        description="防重算刚性会计核算准则"
    )


class NarrativeLadderTier(BaseModel):
    """天梯层级事实"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    height: int = Field(..., ge=1, description="连板高度 (板)")
    count: int = Field(..., ge=1, description="该高度标的家数")
    is_space_leader: bool = Field(False, description="是否为全市场最高空间标杆")
    stocks: List[CanonicalSecurityIdentity] = Field(..., description="标的规范身份列表")


class NarrativeLadderFact(BaseModel):
    """L1 连板天梯事实"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_height: int = Field(..., ge=1, description="最高连板高度")
    space_leader: CanonicalSecurityIdentity = Field(..., description="最高空间标杆规范身份")
    tiers: List[NarrativeLadderTier] = Field(..., description="按高度严格递降排列的天梯层级")


class NarrativeSentimentCountsFact(BaseModel):
    """L1 涨跌停与炸板数量事实"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    limit_up_count: int = Field(..., ge=0, description="有效收盘封死涨停数")
    limit_down_count: int = Field(..., ge=0, description="收盘跌停数")
    touched_limit_total_count: int = Field(..., ge=0, description="日内曾触及涨停总家数")
    broken_limit_count: int = Field(..., ge=0, description="日内曾触板但收盘未封死家数")


class NarrativeRegulatoryFact(BaseModel):
    """L1 商业数据商异动规则撮合事实 (基于公开异动规则的第三方算法撮合，非交易所官方行政定性)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    total_anomaly_count: int = Field(..., ge=0, description="商业数据商异动规则撮合标的总数")
    anomaly_stocks: List[CanonicalSecurityIdentity] = Field(..., description="触碰规则标的规范身份列表")
    space_leader_has_warning: bool = Field(False, description="最高板标的是否触碰异动或特停预警")


# =========================================================================
# FACT LAYER: 客观物理事实层 (L0/L1)
# =========================================================================

class NarrativeFactLayer(BaseModel):
    """
    FACT LAYER: 纯洁客观物理事实，零主观推断
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    layer_type: str = Field("FACT", description="层级标识")
    turnover: NarrativeTurnoverFact
    indices: List[CanonicalIndexQuote]
    ladder: NarrativeLadderFact
    sentiment_counts: NarrativeSentimentCountsFact
    regulatory: NarrativeRegulatoryFact


# =========================================================================
# DERIVED LAYER: 确定性衍生结构层 (L2)
# =========================================================================

class NarrativeDerivedLayer(BaseModel):
    """
    DERIVED LAYER: 基于事实通过确定性数学公式派生的微观结构
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    layer_type: str = Field("DERIVED", description="层级标识")
    broken_limit_ratio: float = Field(..., ge=0.0, le=1.0, description="真实炸板率 (42.67%)")
    extreme_loss_ratio: float = Field(..., ge=0.0, le=1.0, description="极值亏损率")
    turnover_change_ratio: Optional[float] = Field(None, description="成交额环比变动率")
    breadth_status: DataQualityGrade = Field(..., description="截面广度状态 (如 UNAVAILABLE 502)")
    breadth_message: Optional[str] = Field(None, description="广度降级详细说明")
    state_features: StateFeatureVector = Field(..., description="四维量化特征向量 X = (I, S, R, M)")


# =========================================================================
# COGNITION LAYER: 顶层认知假说层 (L3)
# 必须完全由上游 Phase 2D.0/2D.2 只读映射，严禁二次排序或重新筛选主线！
# =========================================================================

class NarrativeMainlineItem(BaseModel):
    """单条主线认知证据模型 (严格 1:1 映射自 Canonical MainlineCandidate)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    rank: int = Field(..., ge=1, description="主线排名 (只读透传，严禁二次重排)")
    sector_name: str = Field(..., description="板块名称")
    sector_code: str = Field(..., description="板块代码")
    structural_role: str = Field(..., description="结构角色: CORE_MAINLINE / BRANCH_ROTATION / WEAK_ROTATION_OR_ISOLATED")
    thematic_tier: str = Field(..., description="主线层级: TIER_1_CORE / TIER_2_BRANCH / TIER_3_WEAK_OR_ISOLATED")
    market_narrative: Optional[str] = Field(None, description="交易实盘叙事穿透标签 (如 '电池 / 锂电池产业链')")
    leader_identity: CanonicalSecurityIdentity = Field(..., description="代表龙头权威规范身份")
    leader_height: int = Field(..., ge=1, description="龙头连板高度")
    limit_up_count: int = Field(..., ge=1, description="成分涨停家数")
    ladder_distribution: Dict[str, int] = Field(..., description="梯队高度分布 (如 {'4B': 1, '3B': 1})")
    supporting_evidence: List[str] = Field(..., description="正向支撑证据链")
    counter_evidence: List[str] = Field(..., description="反方批判证据集 (亏钱效应/断层/异动)")
    falsification_condition: FalsificationCondition = Field(..., description="次日证伪条件与核心观察标的")
    shared_evidence_notes: List[str] = Field(default_factory=list, description="同源资金簇重叠度审计说明")


class NarrativeStateCognition(BaseModel):
    """市场状态认知模型 (来自 Phase 2D.2 CalibratedMarketState)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    primary_state: MarketStateEnum = Field(..., description="状态机分类枚举")
    state_display_name: str = Field(..., description="中文状态简称 (如 '高位剧烈分化期')")
    state_confidence: float = Field(..., ge=0.0, le=1.0, description="判定置信度")
    driving_factors: List[str] = Field(..., min_length=1, description="核心驱动量化事实列表")
    transition_signal: Optional[str] = Field(None, description="状态转移信号")
    deterministic_summary: str = Field(..., description="受约束确定性一句话全貌")


class NarrativeCognitionLayer(BaseModel):
    """
    COGNITION LAYER: 顶层认知假说，只读映射自 Phase 2D.0/2D.2
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    layer_type: str = Field("COGNITION", description="层级标识")
    market_state: NarrativeStateCognition
    candidate_mainlines: List[NarrativeMainlineItem] = Field(
        default_factory=list, max_length=5, description="受约束主线候选列表 (严格保持上游排序)"
    )
    provisional_disclaimer: str = Field(
        "PROVISIONAL / 实验性认知绑定：L3 认知推断仅供交易员复盘交叉核验，非确定性物理事实",
        description="董事会审计令强制免责声明"
    )


# =========================================================================
# SPEECH BOUNDARY CONTRACT: 叙事发言边界契约 (红线 5 & 6)
# 明确“LLM 可以说什么”与“绝对不能说什么”
# =========================================================================

class SpeechBoundaryContract(BaseModel):
    """
    叙事发言边界契约：刚性约束 LLM 语义边界
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed_claim_types: List[str] = Field(
        default=[
            "MACRO_TURNOVER_DIVERGENCE",       # 可陈述宏观成交额与指数离散背离
            "LADDER_STRUCTURE_AND_SPACE",      # 可陈述连板天梯高度与梯队纵深
            "CORE_MAINLINE_EVIDENCE",          # 可陈述 Top 3~5 核心主线与代表标杆
            "BLEEDING_AND_NEGATIVE_FEEDBACK",  # 可陈述炸板率、跌停家数与高位派发
            "REGULATORY_ANOMALY_WARNING",      # 可陈述商业数据商异动规则撮合风险 (非交易所官方内参)
            "NEXT_DAY_FALSIFICATION_BOUNDARY", # 可陈述次日竞价核心观察哨与证伪条件
        ],
        description="允许 LLM 叙述的客观事实与假说声明类型"
    )

    forbidden_claim_types: List[str] = Field(
        default=[
            "DIRECT_TRADING_DIRECTIVE",        # 严禁买入、卖出、加仓、减仓、建仓、冲、梭哈、抄底、追高等交易指令
            "UNVERIFIED_PRICE_TARGET",         # 严禁预测具体买卖点位或目标价
            "UNAUTHENTICATED_SECURITY_IDENTITY", # 严禁使用非 Security Master 认证的个股简称 (杜绝 002242 漂移)
            "COGNITION_TO_FACT_PROMOTION",     # 严禁将 L3 认知假说伪造为 L0 确定性物理事实
            "REDUNDANT_DOUBLE_COUNT_CLAIMS",   # 严禁将创业板成交额与深市再次累加
            "SECONDARY_MAINLINE_RERANKING",    # 严禁 LLM 自行重新排序主线强弱
        ],
        description="绝对禁止 LLM 输出的违规语义声明类型 (L5 隔离)"
    )

    required_evidence_anchors: List[str] = Field(
        ..., min_length=3, description="战报必须引用的确定性锚点事实标识列表"
    )

    falsification_rules_to_monitor: List[str] = Field(
        ..., min_length=1, description="战报必须在结尾强调的次日证伪防守红线列表"
    )


# =========================================================================
# TOP-LEVEL CONTRACT: NarrativeContextContract
# 唯一的合法只读 LLM 输入上下文信封
# =========================================================================

class NarrativeContextContract(BaseModel):
    """
    只读、确定性、可审计的 Cognition-to-Narrative 上下文契约
    上位依据：Phase 2D.3-A 裁决令
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field("2D.3-NARRATIVE-CONTEXT-V1", description="叙事上下文契约版本")
    producer_version: str = Field("CANONICAL_NARRATIVE_CONTEXT_EXTRACTOR-V1", description="生成器版本")
    trade_date: str = Field(..., description="业务交易日期 YYYY-MM-DD")
    extracted_at: str = Field(..., description="上下文提取时间 ISO-8601")
    source_snapshot_fingerprint: str = Field(..., description="源 CanonicalMarketSnapshot 指纹 (防篡改源头锚定)")

    # 严格三层分层结构 (红线 3)
    fact_layer: NarrativeFactLayer = Field(..., description="L0/L1 客观物理事实层")
    derived_layer: NarrativeDerivedLayer = Field(..., description="L2 确定性衍生结构层")
    cognition_layer: NarrativeCognitionLayer = Field(..., description="L3 顶层认知假说层")

    # 发言边界契约 (红线 5 & 6)
    speech_boundary: SpeechBoundaryContract = Field(..., description="叙事发言边界契约")

    context_fingerprint: str = Field(..., description="RFC 8785 JCS 确定性内容数字指纹 (SHA-256)")
