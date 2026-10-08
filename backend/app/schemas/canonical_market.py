"""
Phase 2D.0 P0: Canonical Market Truth & Cognition 契约模型
上位依据：
1. 用户 2026-10-08 最终裁决令：《Phase 2D.0 终审裁决：CONDITIONAL PASS；Phase 2D.1 有条件启动》
2. SPEC-DESIGN-PHASE2D-20261008-V1.0 (Doc 69)

架构硬隔离规约：
- FACT / DERIVED 属于 MarketTruthSnapshot，绝不掺杂 COGNITION 假说推断；
- COGNITION 属于 CognitionSnapshot，严格执行 Mainline Eligibility Contract，杜绝 Provider Meta-Tag 污染；
- 双方各自持有独立的 schema_version, producer, provenance, fingerprint；
- 顶层统一信封 CanonicalMarketSnapshot 聚合两者，供前端只读单向消费。
"""

from typing import Optional, List, Dict, Any, Literal, Set
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


# =========================================================================
# L0 / L1: 元数据血缘信封 (Provenance Envelope)
# =========================================================================

class TruthSource(str, Enum):
    SINA_HQ_STREAM = "SINA_HQ_STREAM"
    EASTMONEY_PUSH = "EASTMONEY_PUSH"
    EASTMONEY_PRICE_ANOMALY = "EASTMONEY_PRICE_ANOMALY"
    EASTMONEY_CONCEPT_BLOCKS = "EASTMONEY_CONCEPT_BLOCKS"
    TONGHUASHUN_LIMIT_UP = "TONGHUASHUN_LIMIT_UP"
    DERIVED_COMMERCIAL_MATCH = "DERIVED_COMMERCIAL_MATCH"
    INTERNAL_CANONICAL_AGGREGATE = "INTERNAL_CANONICAL_AGGREGATE"
    COGNITION_ELIGIBILITY_ENGINE = "COGNITION_ELIGIBILITY_ENGINE"
    UNKNOWN = "UNKNOWN"


class DataQualityGrade(str, Enum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class ProvenanceEnvelope(BaseModel):
    """事实与认知血缘包装信封 (防篡改溯源)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: TruthSource = Field(..., description="物理数据来源或生成引擎端点")
    observed_time: str = Field(..., description="系统网络观察或生成时间戳 ISO-8601")
    quality: DataQualityGrade = Field(..., description="数据质量等级")
    is_degraded: bool = Field(False, description="是否处于单源故障或降级状态")
    degradation_reason: Optional[str] = Field(None, description="降级原因描述 (如 HTTP 502)")


# =========================================================================
# L1: 核心大盘指数与真实成交额规范 (防重算标准口径)
# =========================================================================

class CanonicalIndexQuote(BaseModel):
    """规范化指数行情 (L1 客观事实，消除 None 缺陷)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(..., description="标准指数代码，如 sh000001, sz399001")
    name: str = Field(..., description="指数中文标准名称")
    current_price: float = Field(..., gt=0, description="当前点位 / 收盘点位")
    pre_close: float = Field(..., gt=0, description="昨收盘点位")
    change_val: float = Field(..., description="涨跌绝对点数 (current_price - pre_close)")
    pct_change: float = Field(..., description="涨跌幅百分比 (精确到2位小数)")
    amount_yi: float = Field(..., ge=0, description="成交金额 (严格以亿元为单位)")
    trade_date: str = Field(..., description="撮合日期 YYYY-MM-DD")
    envelope: ProvenanceEnvelope


class CanonicalTurnoverBreakdown(BaseModel):
    """
    全市场成交额防重算标准口径 (GATE-2D0-02 核心防线)
    深交所官方公布的深市总额已包含创业板！严禁重复相加！
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    trade_date: str
    sh_amount_yi: float = Field(..., ge=0, description="上交所总成交额 (亿元)")
    sz_total_amount_yi: float = Field(..., ge=0, description="深交所总成交额 (亿元，已含主板与创业板！)")
    chinext_slice_amount_yi: float = Field(..., ge=0, description="创业板成交额 (深市内部结构切片，仅作占比分析，严禁相加！)")
    chinext_ratio_in_sz: float = Field(..., ge=0, le=1.0, description="创业板占深市总成交比例")
    bse_amount_yi: Optional[float] = Field(0.0, ge=0, description="北交所成交额 (亿元)")
    
    # 真实全市场成交额 = 沪市 + 深市(含创) + 北证
    two_markets_total_yi: float = Field(..., ge=0, description="沪深两市真实总成交额 = sh + sz (绝不额外加 chinext)")
    all_markets_total_yi: float = Field(..., ge=0, description="全市场真实总成交额 = sh + sz + bse")
    
    envelope: ProvenanceEnvelope


# =========================================================================
# L0/L1: 规范证券实体唯一身份契约 (DOC-75 P0.2-Fix-2)
# =========================================================================

class CanonicalSecurityIdentity(BaseModel):
    """
    规范证券实体唯一身份契约 (DOC-75 P0.2-Fix-2)
    不可变量：
    Invariant A: (exchange, stock_code) -> 唯一 canonical security entity
    Invariant B: canonical security entity -> 唯一 normalized stock code
    Invariant C: L2/L3 严格引用该 identity，禁止使用自由文本名称作为主键
    Invariant D: canonical_name 为只读展示属性，禁止自由文本覆盖
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    security_id: str = Field(..., description="规范证券全局主键 (如 '002242.SZ')")
    stock_code: str = Field(..., description="6位数字规范股票代码 (如 '002242')")
    canonical_name: str = Field(..., description="规范官方证券简称 (如 '九阳股份')")
    exchange: str = Field(..., description="交易所标识: SH, SZ, BJ")


# =========================================================================
# L1: 涨跌停与炸板率 Universe 边界规范 (GATE-2D0-04 核心防线)
# =========================================================================

class LimitUpStockItem(BaseModel):
    """涨停标的事实模型"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(..., description="6位数字代码")
    name: str = Field(..., description="标的简称")
    security_id: Optional[str] = Field(None, description="规范证券主键 (如 '002242.SZ')")
    board_type: str = Field(..., description="板块类型: MAIN, GEM, STAR, BSE")
    continuous_board_count: int = Field(..., ge=1, description="连板高度 (自然交易日连板数 >= 1)")
    limit_up_type: str = Field(..., description="FIRST_LIMIT (首板) / CONTINUED (连板)")
    first_limit_time: Optional[str] = Field(None, description="首次封板时间 HH:MM:SS")
    last_limit_time: Optional[str] = Field(None, description="最终封板时间 HH:MM:SS")
    reason_type: str = Field(..., description="涨停主因归属")
    order_amount_wan: Optional[float] = Field(None, description="收盘封单金额 (万元)")


class BrokenLimitStockItem(BaseModel):
    """炸板标的事实模型 (日内曾触及涨停但收盘未封死)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    name: str
    board_type: str
    close_pct_change: float = Field(..., description="收盘实际涨跌幅 %")
    max_pct_change: float = Field(..., description="日内最高涨幅 % (曾触及涨停)")
    open_times: int = Field(1, ge=1, description="日内打开涨停次数")
    reason_type: Optional[str] = None


class BrokenLimitUniverseContract(BaseModel):
    """
    炸板率与极端情绪 Universe 边界契约
    明确界定分子与分母样本边界 (严格剔除退市整理期，明确 ST 规则)
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    trade_date: str
    limit_up_count: int = Field(..., ge=0, description="收盘有效封死涨停家数")
    broken_limit_count: int = Field(..., ge=0, description="日内曾触及涨停但收盘未封死家数 (分子)")
    touched_limit_total_count: int = Field(..., ge=0, description="日内曾触及涨停总家数 (分母 = 封死 + 炸板)")
    broken_limit_ratio: float = Field(..., ge=0.0, le=1.0, description="真实炸板率 = broken / touched_total")
    limit_down_count: int = Field(0, ge=0, description="收盘跌停家数")
    max_ladder_height: int = Field(1, ge=1, description="当日全市场最高连板高度")
    universe_criteria: Dict[str, bool] = Field(
        default_factory=lambda: {
            "include_st_stocks": True,
            "include_chinext_star": True,
            "include_bse_30cm": True,
            "exclude_ipo_unlimited": True,
        },
        description="全市场样本统计规则边界"
    )
    envelope: ProvenanceEnvelope


# =========================================================================
# L1: 交易所严重异常波动监管事实 (GATE-2D0-08)
# =========================================================================

class RegulatoryAnomalyItem(BaseModel):
    """交易所监管异动事实项 (严谨定性为商业匹配规则事实)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    name: str
    rule_id: int
    rule_name: str
    deviation_pct: float = Field(..., description="累计偏离度百分比")
    status_flag: int = Field(..., description="0=监控中, 1=已触发预警, 2=正式达标严重异动")
    provenance_nature: str = Field(
        default="EASTMONEY_COMPUTED_RULE_MATCH",
        description="定性属性：第三方金融数据算法依交易所规则撮合匹配，非交易所官方内参红头文件"
    )


# =========================================================================
# L2: 连板天梯树 (Ladder Tree) 与微观结构 (DERIVED)
# =========================================================================

class LadderGroup(BaseModel):
    """连板高度层级组 (从高到低严密排序，首板防腐)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    height: int = Field(..., ge=1, description="连板高度阶梯 (如 8, 4, 3, 2, 1)")
    stocks_count: int = Field(..., ge=1)
    stocks: List[LimitUpStockItem]
    is_space_leader: bool = Field(False, description="是否为全市场最高空间标杆")


# =========================================================================
# L1/L2 顶层事实信封: MarketTruthSnapshot (FACT + DERIVED)
# =========================================================================

class MarketTruthSnapshot(BaseModel):
    """
    市场客观事实与派生快照 (FACT + DERIVED)
    硬铁律：本模型绝不包含任何主线评级、假说推断或行动建议！
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field("2D.0-TRUTH-V1", description="事实契约版本")
    producer: str = Field("CANONICAL_MARKET_SERVICE", description="事实生成器标识")
    trade_date: str = Field(..., description="业务交易日期 YYYY-MM-DD")
    generated_at: str = Field(..., description="快照生成时间 ISO-8601")
    
    # L1: 核心大盘指数
    indices: List[CanonicalIndexQuote]
    
    # L1: 真实成交额结构 (绝无创业板重复相加)
    turnover: CanonicalTurnoverBreakdown
    
    # L1: 涨跌停与炸板率边界
    sentiment_bounds: BrokenLimitUniverseContract
    
    # L1: 交易所严重异常波动监管雷达
    regulatory_anomalies: List[RegulatoryAnomalyItem]
    
    # L2: 连板天梯树 (DERIVED)
    ladder_tree: List[LadderGroup]
    
    # L1: 全市场横截面广度状态 (解耦单源 502)
    cross_section_breadth_status: DataQualityGrade
    cross_section_breadth_detail: Optional[Dict[str, Any]] = None
    
    # 溯源与不可变哈希
    provenance: ProvenanceEnvelope
    truth_fingerprint: str = Field(..., description="RFC 8785 JCS 确定性内容哈希 (SHA-256)")


# =========================================================================
# P0 Closure: Mainline Eligibility Contract (主线准入语义契约)
# =========================================================================

class SemanticType(str, Enum):
    """板块语义类型分类"""
    CONCEPT = "CONCEPT"                     # 真实投资主题/概念 (准入候选)
    INDUSTRY = "INDUSTRY"                   # 真实产业/行业 (准入候选)
    STATISTICAL_TAG = "STATISTICAL_TAG"     # 统计/规模/财务标签 (禁止准入: 大盘股, 预增等)
    TRADING_FEATURE = "TRADING_FEATURE"     # 交易形态/行情特征标签 (禁止准入: 最近多板, 新高等)
    RANKING_TAG = "RANKING_TAG"             # 热榜/关注度标签 (禁止准入: 东财热股, 题材股等)
    PROVIDER_META_TAG = "PROVIDER_META_TAG" # 数据商元标签/宽基指数 (禁止准入: AB股, HS300等)
    REGION = "REGION"                       # 地域标签 (禁止准入: 深圳特区, 上海板块等)


class ConstituencyEvidence(BaseModel):
    """主线独立成分证据 (Constituency Evidence)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    leader_code: str = Field(..., description="核心辨识度龙头代码")
    leader_name: str = Field(..., description="核心辨识度龙头名称")
    leader_security_id: Optional[str] = Field(None, description="核心辨识度龙头规范全局主键 (如 '002242.SZ')")
    leader_height: int = Field(..., ge=1, description="龙头连板高度")
    limit_up_count: int = Field(..., ge=1, description="板块内涨停标的数量 (广度)")
    ladder_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="梯队分布，例如 {'8B': 1, '2B': 1, '1B': 10}"
    )
    first_board_diffusion_count: int = Field(0, ge=0, description="首板扩散标的数")
    constituent_symbols: List[str] = Field(default_factory=list, description="板块内涨停成分标的简称列表")


class FalsificationCondition(BaseModel):
    """次日证伪条件契约 (波普尔证伪批判硬要求)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    invalidation_rules: List[str] = Field(..., description="主线结构次日被证伪/失效的判定条件")
    critical_observation_symbols: List[str] = Field(..., description="次日早盘集合竞价核心观察标的")


class SharedEvidenceAffiliate(BaseModel):
    """成分股重叠度与共享证据审计模型 (GATE-2D0-15 核心防线)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    target_sector_name: str = Field(..., description="关联审计目标板块名称")
    target_sector_code: str = Field(..., description="关联审计目标板块代码")
    overlap_stocks_count: int = Field(..., ge=1, description="重叠涨停标的数量")
    shared_evidence_ratio: float = Field(..., ge=0.0, le=1.0, description="共享证据率 (|A∩B| / min(|A|, |B|))")
    relationship: Literal["PARENT_INDUSTRY", "SUBTHEME_CATALYST", "CO_DRIVER_AFFILIATE"] = Field(
        ..., description="关联定性：母板块 / 细分催化题材 / 协同衍生资金簇"
    )
    audit_note: str = Field(..., description="审计解耦结论陈述")


class SubthemeCatalyst(BaseModel):
    """前沿技术细分催化分支模型 (Parent/Child 树状挂载)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    sector_name: str = Field(..., description="细分题材名称 (如 固态电池)")
    sector_code: str = Field(..., description="细分题材代码 (如 BK0968)")
    catalyst_leader: str = Field(..., description="细分题材自身领军龙头 (如 传艺科技)")
    catalyst_height: int = Field(..., ge=1, description="细分题材独立高度 (如 3B)")
    stocks_count: int = Field(..., ge=1, description="细分题材涨停标的数")
    thematic_role: str = Field("FRONTIER_TECH_CATALYST", description="细分角色定性")
    overlap_ratio_with_master: float = Field(..., ge=0.0, le=1.0, description="与母产业链成分重合度")


class MainlineCandidate(BaseModel):
    """
    经过语义准入契约、独立成分校验、三级层级模型与反方批判的主线候选 (COGNITION)
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    rank: int = Field(..., ge=1, description="显著性排序位次 (Top 1~5)")
    sector_code: str = Field(..., description="板块代码")
    sector_name: str = Field(..., description="板块名称")
    semantic_type: Literal["CONCEPT", "INDUSTRY"] = Field(..., description="必须为 CONCEPT 或 INDUSTRY")
    constituency: ConstituencyEvidence = Field(..., description="独立成分证据")
    supporting_evidence: List[str] = Field(..., description="正向支撑证据 (梯队/广度/龙头)")
    counter_evidence: List[str] = Field(..., description="反方证据集 (监管/炸板/分化风险)")
    falsification_condition: FalsificationCondition = Field(..., description="次日证伪观察条件")
    structural_role: Literal["CORE_MAINLINE", "BRANCH_ROTATION", "WEAK_ROTATION_OR_ISOLATED"] = Field(
        ..., description="主线三级模型定性：核心主线 / 分支轮动 / 弱轮动孤立高标"
    )
    thematic_tier: Literal["TIER_1_CORE", "TIER_2_BRANCH", "TIER_3_WEAK_OR_ISOLATED"] = Field(
        ..., description="主线刚性阶梯分类"
    )
    is_thematic_frontier: bool = Field(False, description="是否属于核心前沿细分题材 (如固态电池)")
    shared_evidence_affiliates: List[SharedEvidenceAffiliate] = Field(
        default_factory=list, description="成分股重叠度与共享证据审计清单"
    )
    conviction_summary: str = Field(..., description="非线性证据综合裁决综述")
    market_narrative: Optional[str] = Field(None, description="交易叙事映射名称 (如 '电池 / 锂电池产业链')")
    static_taxonomy_name: Optional[str] = Field(None, description="底层数据商静态行业/概念分类 (如 '电力设备 (BK1200)')")
    subtheme_catalysts: List[SubthemeCatalyst] = Field(
        default_factory=list, description="挂载的前沿技术催化分支 (如 固态电池 3B)"
    )


# =========================================================================
# P0 Closure: 完整血缘解释与数学闭环 (Lineage Accounting Report)
# =========================================================================

class LineageAccountingReport(BaseModel):
    """
    287 -> 251 -> Top-N -> Folded 完整血缘与数学闭环报告
    所有原始板块必须落入明确且互斥的 Bucket 中，绝无遗漏！
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    total_raw_evaluated: int = Field(287, description="物理评估板块总数")
    admission_rejected_count: int = Field(36, description="准入保护器直接拒绝板块数")
    admission_admitted_count: int = Field(251, description="通过准入的候选假说数")
    
    # 251 Admitted 内部 MECE 分解:
    excluded_meta_tags_count: int = Field(..., description="排除的数据商元标签/统计/特征/热榜数 (6+12+10+2=30)")
    excluded_regions_count: int = Field(..., description="排除的纯地域标签数 (8)")
    solitary_leader_noise_count: int = Field(..., description="排除的单票孤立寄生标签数 (如只有新华传媒1只8B的出版/语料)")
    pulse_noise_count: int = Field(..., description="排除的无梯队日内脉冲杂音数 (首板<=2且无梯队)")
    deduplicated_clusters_count: int = Field(..., description="成分高度重合被去重聚类的分支题材数")
    eligible_candidates_count: int = Field(..., description="符合准入且具备独立成分的主线候选池总数")
    
    # Eligible Candidates 内部去向:
    top_mainlines_count: int = Field(..., description="推送到首页交易员驾驶舱的顶级主线数 (Top N)")
    folded_eligible_remainder_count: int = Field(..., description="折叠供展开查看的其余合规主线数")
    
    is_mathematically_closed: bool = Field(True, description="数学恒等式闭环核验状态")
    lineage_formula: str = Field(
        ...,
        description="闭环校验公式表达: 287 = 36(Rejected) + 251(Admitted); 251 = Meta(30) + Region(8) + Solitary(32) + Pulse(147) + Dedup(15) + Eligible(19); 19 = Top(5) + Folded(14)"
    )


# =========================================================================
# L3: 市场状态多维量化输入向量与状态机契约 (DOC-78 Phase 2D.2)
# =========================================================================

class MarketStateEnum(str, Enum):
    """市场状态枚举 (MECE 完全穷尽 6 态)"""
    EXPANSION_ACCELERATION = "EXPANSION_ACCELERATION"   # 主升共振期
    HIGH_DIVERGENCE_TOPPING = "HIGH_DIVERGENCE_TOPPING" # 高位剧烈分化期
    RECESSION_PANIC = "RECESSION_PANIC"                 # 退潮恐慌期
    FREEZING_REVERSAL = "FREEZING_REVERSAL"             # 极值冰点反转期
    CHAOTIC_ROTATION = "CHAOTIC_ROTATION"               # 混沌轮动期
    LOW_REBOUND = "LOW_REBOUND"                         # 低位超跌反弹期


class IndexVector(BaseModel):
    """指数与流动性量化特征向量 I"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    total_turnover_yi: float = Field(..., description="沪深两市真实总成交额(亿元)")
    turnover_change_ratio: Optional[float] = Field(None, description="较前一交易日成交额环比变动率")
    dispersion_pct: float = Field(..., description="各大指数极差离散度 (max - min) %")
    star_divergence_pct: float = Field(..., description="科创50与主板指数背离差值 %")


class LadderVector(BaseModel):
    """天梯情绪与做多广度特征向量 S"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_ladder_height: int = Field(..., ge=1, description="全市场最高连板高度 (板)")
    limit_up_count: int = Field(..., ge=0, description="有效封死涨停家数")
    limit_down_count: int = Field(..., ge=0, description="收盘跌停家数")
    leader_ratio: float = Field(..., ge=0.0, le=1.0, description="高位连板(>=3B)占涨停比率")


class RiskVector(BaseModel):
    """亏钱效应与负反馈特征向量 R"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    broken_limit_ratio: float = Field(..., ge=0.0, le=1.0, description="真实炸板率")
    broken_limit_count: int = Field(..., ge=0, description="日内炸板家数")
    extreme_loss_ratio: float = Field(..., ge=0.0, le=1.0, description="极值亏损率 (跌停+炸板占触板总数比)")


class RegulatoryVector(BaseModel):
    """监管压力与异常波动特征向量 M"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    anomaly_count: int = Field(..., ge=0, description="触发严重异常波动规则标的总数")
    has_leader_warning: bool = Field(False, description="空间标杆是否触发特停或异动预警")


class StateFeatureVector(BaseModel):
    """四维输入量化特征向量 X = (I, S, R, M)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    index_vector: IndexVector
    ladder_vector: LadderVector
    risk_vector: RiskVector
    regulatory_vector: RegulatoryVector


class CalibratedMarketState(BaseModel):
    """经过多维量化向量校准的确定性市场状态模型 (L3 COGNITION)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    primary_state: MarketStateEnum = Field(..., description="主市场状态分类")
    state_display_name: str = Field(..., description="中文交易状态简称 (如 '高位剧烈分化期')")
    state_confidence: float = Field(..., ge=0.0, le=1.0, description="状态判定确定性置信度")
    driving_factors: List[str] = Field(..., min_length=1, description="支撑该状态的核心驱动量化事实列表")
    transition_signal: Optional[str] = Field(None, description="前序状态转移信号定性")
    feature_vector: Optional[StateFeatureVector] = Field(None, description="四维底层量化输入特征向量")


# =========================================================================
# L3 顶层认知信封: CognitionSnapshot (COGNITION)
# =========================================================================

class CognitionSnapshot(BaseModel):
    """
    市场认知与主线裁决快照 (COGNITION)
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field("2D.0-COGNITION-V1", description="认知契约版本")
    producer: str = Field("COGNITION_ELIGIBILITY_ENGINE", description="认知生成器标识")
    trade_date: str = Field(..., description="业务交易日期 YYYY-MM-DD")
    generated_at: str = Field(..., description="认知生成时间 ISO-8601")
    
    # 受约束的主线候选 (Top 3~5)
    mainlines: List[MainlineCandidate]
    
    # 完整血缘闭环解释报告
    lineage_accounting: LineageAccountingReport
    
    # 市场状态整体结构化定性一句话 (推断属性，向后兼容)
    market_state_summary: str = Field(..., description="受约束的一句话全貌定性")
    
    # Phase 2D.2: 结构化状态校准对象
    market_state_calibration: Optional[CalibratedMarketState] = Field(
        default=None, description="经过 Phase 2D.2 有限状态机校准的结构化市场状态对象"
    )
    
    # 董事会审计令强制免责声明
    provisional_disclaimer: str = Field(
        default="PROVISIONAL / 实验性认知绑定：L3 认知推断仅供交易员复盘交叉核验，非确定性物理事实",
        description="董事会审计令强制免责与认知状态声明"
    )
    
    provenance: ProvenanceEnvelope
    cognition_fingerprint: str = Field(..., description="RFC 8785 JCS 确定性内容哈希 (SHA-256)")


# =========================================================================
# 顶层统一信封 API 响应模型: CanonicalMarketSnapshot
# =========================================================================

class CanonicalMarketSnapshot(BaseModel):
    """
    GET /api/v1/canonical/market-snapshot/{date} 顶层统一数据信封
    严格区分并包含 MarketTruthSnapshot (FACT+DERIVED) 与 CognitionSnapshot (COGNITION)！
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_version: str = Field("2D.0-CANONICAL-V2", description="契约规范版本")
    trade_date: str = Field(..., description="业务交易日期 YYYY-MM-DD")
    generated_at: str = Field(..., description="信封打包时间 ISO-8601")
    
    # 严格分层两大核心子系统
    truth: MarketTruthSnapshot = Field(..., description="L0~L2 客观市场真相 (事实与派生)")
    cognition: CognitionSnapshot = Field(..., description="L3 认知分析 (受约束主线与血缘闭环)")
    
    envelope_fingerprint: str = Field(..., description="RFC 8785 JCS 顶层信封防篡改数字指纹 (SHA-256)")
