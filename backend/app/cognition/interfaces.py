from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from ..data.capabilities import DataQuality

class IndicatorValue(BaseModel):
    """单个指标的计算结果"""
    name: str = Field(description="指标名称")
    value: Any = Field(description="指标计算值")
    score: Optional[float] = Field(default=None, description="归一化得分(0-100)")
    weight: float = Field(default=1.0, description="当前维度内权重")
    contribution: Optional[float] = Field(default=None, description="加权贡献")
    raw_data: Optional[dict] = Field(default=None, description="原始支撑数据(可审计)")

class SubDimensionState(BaseModel):
    """子维度状态快照 (D1~D6)"""
    dimension_id: str = Field(description="D1, D2, D3, D4, D5, D6")
    name: str = Field(description="子维度名称")
    score: Optional[float] = Field(default=None, description="子维度核心标量分值(0-100)。注：多子域维度(如D3)核心输出为sub_domains，其score必须为None以杜绝标量塌缩")
    reference_score: Optional[float] = Field(default=None, description="仅供历史诊断与对照的参考分(reference_only)，严禁作为下游决策依据")
    quality: DataQuality = Field(default=DataQuality.FULL, description="维度数据质量")
    state_label: Optional[str] = Field(default=None, description="维度状态标签")
    metric_polarity: Optional[str] = Field(default=None, description="物理语义极性元数据(仅描述测量属性，严禁作为买卖信号)")
    semantics_desc: Optional[str] = Field(default=None, description="物理含义客观描述契约")
    sub_domains: Optional[Dict[str, Any]] = Field(default=None, description="多子域正交事实输出(如D3包含speculative_structure与tail_extremes)")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="各指标原始或提取值")
    indicators_detail: List[IndicatorValue] = Field(default_factory=list, description="指标计算明细")
    context: Optional[dict] = Field(default=None, description="非评分背景语境 (如外部市场)")

class MarketState(BaseModel):
    """
    结构化市场状态快照 (M1.4 核心产物: Market State Snapshot / Artifact)
    严格遵守 G4-B 裁决：
    - composite_score: 当且仅当全局非 INVALID 时输出分值，INVALID 时强制为 null；
    - dimensions: 六大子维度的独立评估与特征向量；
    - 绝不用默认值伪造数据。
    """
    timestamp: datetime = Field(default_factory=datetime.now)
    composite_score: Optional[float] = Field(default=None, description="综合得分(0-100)，INVALID 时必须为 null")
    state_label: str = Field(default="neutral", description="全局状态标签")
    data_quality: DataQuality = Field(default=DataQuality.FULL, description="FULL / PARTIAL / INVALID")
    dimensions: Dict[str, SubDimensionState] = Field(default_factory=dict, description="六大子维度状态字典")
    missing_metrics: List[str] = Field(default_factory=list, description="缺失指标标识清单")
    available_weight: Optional[float] = Field(default=None, description="综合分计算时有效维度的权重总和(0.0-1.0)")
    composite_score_method: Optional[str] = Field(default=None, description="综合得分计算方法(如 FULL_WEIGHTED / RENORMALIZED_VALID_DIMENSIONS / NONE_DUE_TO_INSUFFICIENT_DATA)")
    quality_level: Optional[str] = Field(default=None, description="质量级别详细描述")
    config_snapshot_version: str = Field(default="v1", description="对应配置版本")

class CognitionInput(BaseModel):
    """Cognition Layer 统一输入契约"""
    market_data: dict = Field(description="市场即时/日线快照数据")
    historical_context: Optional[dict] = Field(default=None, description="历史状态上下文")
    # G3/G4 预留扩展点：cognition_memory, human_feedback 等

class CognitionOutput(BaseModel):
    """Cognition Layer 统一输出契约"""
    market_state: MarketState = Field(description="结构化市场状态快照")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="判断置信度")
    reasoning: str = Field(default="", description="可审计的认知判断推导链")

class CognitionLayerInterface(ABC):
    """
    Cognition Layer 独立对外抽象契约
    Phase 1: 建立计算边界与对外接口
    """
    @abstractmethod
    async def compute_market_state(self, input_data: CognitionInput) -> MarketState:
        """根据输入数据分层计算市场状态快照 (M1.4)"""
        pass
