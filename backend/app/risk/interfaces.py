from abc import ABC, abstractmethod
from typing import List
from pydantic import BaseModel, Field
from ..cognition.interfaces import MarketState
from ..strategy.interfaces import Candidate

class RiskCheckResult(BaseModel):
    """风控检查结果"""
    passed: bool = Field(default=True, description="是否通过风控约束")
    violations: List[str] = Field(default_factory=list, description="阻断性违规项列表")
    warnings: List[str] = Field(default_factory=list, description="非阻断风险警示列表")

class RiskChecker(ABC):
    """
    独立风控层契约
    铁律：任何策略计划或交易模拟必须经过 Risk 评估，不可绕过
    """

    @abstractmethod
    async def check(
        self,
        candidates: List[Candidate],
        current_positions: list,
        market_state: MarketState
    ) -> RiskCheckResult:
        """执行风控合规检查"""
        pass
