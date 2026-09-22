from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field

class HumanDecision(BaseModel):
    """人的决策与反馈记录"""
    decision_id: str = Field(description="决策唯一ID")
    context_type: str = Field(description="场景类型：selection / trade / review")
    ai_suggestion: dict = Field(description="AI提供的建议或输入原型")
    human_action: str = Field(description="人的行为：approve / reject / modify")
    human_reason: Optional[str] = Field(default=None, description="人的主观理由或修正批注")
    timestamp: datetime = Field(default_factory=datetime.now)

class HumanLayerInterface(ABC):
    """
    Human-in-the-loop 接口契约
    架构铁律：
    1. AI输出绝不直接触发实盘自动执行
    2. 系统架构始终保留人的最终裁量与反馈通道
    """

    @abstractmethod
    async def submit_for_review(self, suggestion: dict) -> str:
        """提交 AI 建议供 Owner 审阅，返回 review_id"""
        pass

    @abstractmethod
    async def record_decision(self, decision: HumanDecision) -> None:
        """记录 Owner 的确认或修正裁定"""
        pass
