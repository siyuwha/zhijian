from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, List, Optional
from pydantic import BaseModel, Field
from ..cognition.interfaces import MarketState

class StrategyMode(str, Enum):
    AI_DRIVEN = "ai_driven"        # 模式 A: AI 自主驱动提出策略假设
    USER_DEFINED = "user_defined"  # 模式 B: 用户自定义交易思路与规则

class UniverseConfig(BaseModel):
    """
    选股范围配置
    G1 明确规则：
    选股 Universe: 沪深主板 + 创业板 (排除 688 和北交所)
    注意：不参与交易，不等于不参与认知。
    """
    include_main_board: bool = Field(default=True, description="主板")
    include_gem: bool = Field(default=True, description="创业板 300")
    include_star: bool = Field(default=False, description="科创板 688 (本期排除实盘交易)")
    include_bse: bool = Field(default=False, description="北交所 (本期排除实盘交易)")
    exclude_st: bool = Field(default=True, description="排除 ST/退市整理")
    exclude_codes: List[str] = Field(default_factory=list, description="自定义黑名单代码")

class Candidate(BaseModel):
    """候选池股票 (核心边界：候选池 != 买入建议)"""
    code: str
    name: str
    score: float
    tier: str = Field(description="分层: A (>=75) / B (50-74) / C (<50)")
    reasons: List[str] = Field(default_factory=list, description="选入逻辑与支撑依据")
    data_snapshot: dict = Field(default_factory=dict, description="选入时行情与因子快照")

class SelectionResult(BaseModel):
    """策略选股结果批次"""
    strategy_id: str
    date: str
    candidates: List[Candidate]
    market_state_snapshot: Optional[MarketState] = None
    created_at: datetime = Field(default_factory=datetime.now)

class StrategyDefinition(BaseModel):
    """策略定义模型"""
    id: Optional[int] = None
    name: str
    mode: StrategyMode
    description: Optional[str] = None
    conditions: dict = Field(default_factory=dict, description="策略规则树/条件配置")
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    created_by: str = Field(default="user", description="ai 或 user")
    is_active: bool = True

class StrategyEngine(ABC):
    """策略与选股引擎抽象契约"""

    @abstractmethod
    async def execute(
        self,
        strategy: StrategyDefinition,
        market_state: MarketState,
        market_data: dict
    ) -> SelectionResult:
        """执行策略选股筛选并生成分层候选池"""
        pass
