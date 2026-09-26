from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
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
    """创建跨日推演假说 Payload"""
    target_date: str = Field(..., description="目标验证日期 YYYY-MM-DD")
    hypothesis_type: Literal["INDEX_TREND", "SECTOR_LEADER", "SENTIMENT_CYCLE"] = Field("SECTOR_LEADER", description="假说类别")
    target_asset: str = Field(..., description="推演标的名称或代码")
    expected_scenario: Literal["ACCELERATION", "DIVERGENCE", "REBOUND", "ROTATION"] = Field("DIVERGENCE", description="预期演绎形态")
    premise_logic: str = Field(..., description="前置支撑逻辑 (基于M1~M5)")
    expected_phenomenon: str = Field(..., description="预期可观测到的客观现象")
    invalidation_condition: str = Field(..., description="刚性证伪失效条件")
    assertion_metrics: Optional[Dict[str, Any]] = Field(None, description="可选指标阈值 JSON，如 {'sh_open_pct_min': -0.5}")

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
