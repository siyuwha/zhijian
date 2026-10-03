from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

class DiagnosisConfirmPayload(BaseModel):
    """人工审定确认 Payload"""
    human_status: Literal["CONFIRMED", "MODIFIED"] = Field(..., description="审定状态：CONFIRMED 采纳, MODIFIED 修正")
    human_comment: Optional[str] = Field(None, description="人工修正意见或补充反思")

class CognitiveTradeDiagnosisResponse(BaseModel):
    """单笔交易双层诊断响应"""
    id: int
    trade_id: int
    date: str
    # 事实层
    trade_price: float
    trade_quantity: int
    trade_amount: float
    trade_direction: str
    market_d1_d6_snapshot: Dict[str, Any]
    post_trade_mdd: Optional[float] = None
    post_trade_max_profit: Optional[float] = None
    # 解释层
    env_match_type: str
    env_match_score: Optional[float] = None
    logic_realization: str
    cognitive_gap_analysis: str
    # 人机回环审定状态
    human_status: str
    human_comment: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class WeeklyAuditMetrics(BaseModel):
    """周复盘三维客观度量"""
    env_match_degree: Optional[float] = None       # 环境匹配度 % (None表示无样本)
    logic_realization_degree: Optional[float] = None # 逻辑兑现度 % (None表示无买入样本)
    outcome_deviation_degree: Optional[float] = None # 结果偏离度 % (None表示无预期目标样本)

class WeeklyAuditResponse(BaseModel):
    """周度认知复盘响应"""
    week_label: str
    total_trades: int
    confirmed_samples_count: int
    metrics: WeeklyAuditMetrics
    market_state_distribution: Dict[str, int]
    trade_sample_summary: Dict[str, int]
    empirical_observations: List[str]

class MarketHypothesisCreate(BaseModel):
    """创建跨日推演假说 Payload (严格遵循 Phase 2B.1 认知契约，不做交易预测)"""
    target_date: str = Field(..., description="目标验证日期 YYYY-MM-DD")
    created_date: Optional[str] = Field(None, description="假说创立日期 YYYY-MM-DD (缺省为当日，历史回放时支持显式设定)")
    hypothesis_type: str = Field("SENTIMENT_CYCLE", description="假说类别：SENTIMENT_CYCLE / INDEX_TREND / MARKET_STATE / BREADTH_TREND")
    target_asset: str = Field(..., description="推演标的宏观对象，如全市场短线情绪或主要宽基指数")
    expected_scenario: str = Field("WEAK_CONSOLIDATION", description="预期演绎形态")
    premise_logic: str = Field(..., description="前置支撑逻辑")
    expected_phenomenon: str = Field(..., description="预期可观测到的客观现象")
    invalidation_condition: str = Field(..., description="刚性证伪失效条件")
    assertion_metrics: Optional[Dict[str, Any]] = Field(None, description="收窄 AST 指标断言或阈值配置")

class HypothesisVerificationResponse(BaseModel):
    """假说客观核对记录响应"""
    id: int
    hypothesis_id: int
    verification_stage: str
    actual_data_snapshot: Dict[str, Any]
    outcome: str
    accuracy_score: Optional[float] = None
    deviation_analysis: str
    gap_summary: str
    verified_at: Optional[datetime] = None

class MarketHypothesisResponse(BaseModel):
    """推演假说详情响应 (含核对快照列表)"""
    id: int
    created_date: str
    target_date: str
    hypothesis_type: str
    target_asset: str
    expected_scenario: str
    premise_logic: str
    expected_phenomenon: str
    invalidation_condition: str
    assertion_metrics: Optional[Dict[str, Any]] = None
    status: str
    verifications: List[HypothesisVerificationResponse] = []
    created_at: Optional[datetime] = None


# =========================================================================
# Phase 2B.3: 认知闭环三卡片聚合 DTO (Cognition Review Loop DTOs)
# 上位依据：《开发文档/59-Phase-2B.3-认知闭环前端可视化契约设计单.md》
# =========================================================================

class FactIndexItem(BaseModel):
    code: str
    name: str
    price: Optional[float] = None
    pct_change: Optional[float] = None

class FactSentiment(BaseModel):
    limit_up_count: Optional[int] = None
    limit_down_count: Optional[int] = None
    max_board_height: Optional[int] = None
    broken_limit_count: Optional[int] = None
    broken_ratio: Optional[float] = None

class FactBreadth(BaseModel):
    up_count: Optional[int] = None
    down_count: Optional[int] = None
    flat_count: Optional[int] = None

class FactLayer(BaseModel):
    indices: List[FactIndexItem] = []
    sentiment: FactSentiment = Field(default_factory=FactSentiment)
    breadth: FactBreadth = Field(default_factory=FactBreadth)

class DerivedStateLayer(BaseModel):
    state_label: str = "平稳中性"
    config_version: str = "v1.0"

class TodayFactsDTO(BaseModel):
    fact_layer: FactLayer = Field(default_factory=FactLayer)
    derived_state: DerivedStateLayer = Field(default_factory=DerivedStateLayer)
    observation_timestamp: Optional[str] = None
    fact_snapshot_hash: Optional[str] = None
    data_quality: Optional[str] = "GOOD"
    completeness: Optional[float] = 1.0

class AssertionDTO(BaseModel):
    assertion_id: str
    metric_type: str
    target_code: str = "ALL_A"
    operator: str
    threshold: Any
    description: Optional[str] = None

class HypothesisMetaDTO(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model_name: str = "deepseek-flash"
    prompt_spec_version: str = "1.1.0"
    hypothesis_hash: Optional[str] = None

class TodayHypothesisDTO(BaseModel):
    id: int
    status: str = "PENDING"
    created_date: str
    target_date: str
    hypothesis_type: str
    target_asset: str
    expected_scenario: str
    premise_logic: str
    expected_phenomenon: str
    expected_assertions: List[AssertionDTO] = []
    invalidation_condition: str
    invalidation_assertions: List[AssertionDTO] = []
    meta: HypothesisMetaDTO = Field(default_factory=HypothesisMetaDTO)

class AdjudicationComparisonItem(BaseModel):
    assertion_id: str
    kind: str  # EXPECTED / INVALIDATION
    metric_type: str
    operator: str
    threshold: Any
    actual_value: Optional[float] = None
    is_satisfied: bool

class YesterdayAdjudicationDTO(BaseModel):
    hypothesis_id: int
    created_date: str
    target_date: str
    hypothesis_type: str
    premise_logic: str
    outcome: Literal["CONFIRMED", "FALSIFIED", "INCONCLUSIVE"]
    falsification_triggered: bool = False
    details: str = ""
    comparison_matrix: List[AdjudicationComparisonItem] = []

from enum import Enum

class SimulationIntentType(str, Enum):
    OBSERVE_ONLY = "OBSERVE_ONLY"
    SECTOR_FOCUS = "SECTOR_FOCUS"
    POSITION_DEFENSE = "POSITION_DEFENSE"
    LADDER_TRACKING = "LADDER_TRACKING"

class SimulationIntentStatus(str, Enum):
    PENDING_CONSUMPTION = "PENDING_CONSUMPTION"
    CONSUMED = "CONSUMED"
    REJECTED_BY_RISK = "REJECTED_BY_RISK"
    EXPIRED = "EXPIRED"

class SimulationIntent(BaseModel):
    intent_id: str = Field(..., description="确定性指纹 ID (如 intent_20260930_001)")
    market_date: str = Field(..., description="交易日 YYYY-MM-DD")
    source_hypothesis_id: Optional[int] = Field(None, description="关联的认知假说 ID")
    source_record_hash: Optional[str] = Field(None, description="关联的认知账本 Record Hash (可溯源防伪)")
    intent_type: SimulationIntentType = Field(SimulationIntentType.OBSERVE_ONLY, description="意图类型")
    target_entities: List[str] = Field(default_factory=list, description="标的或板块代码列表")
    confidence: float = Field(0.5, description="置信度")
    rationale: str = Field("", description="意图依据与扣手逻辑")
    risk_boundary: Dict[str, Any] = Field(default_factory=dict, description="风控红线与容忍阈值")
    status: SimulationIntentStatus = Field(SimulationIntentStatus.PENDING_CONSUMPTION, description="消费状态")
    created_at: str = Field(..., description="生成时间 ISO-8601")

class CognitionReviewLoopData(BaseModel):
    market_date: str
    today_facts: TodayFactsDTO
    today_hypothesis: Optional[TodayHypothesisDTO] = None
    yesterday_adjudication: Optional[YesterdayAdjudicationDTO] = None
    simulation_intent: Optional[SimulationIntent] = None

class CognitionReviewLoopResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: CognitionReviewLoopData

class ProposeTodayHypothesisPayload(BaseModel):
    market_date: str
    target_date: Optional[str] = None


