from sqlalchemy import Column, Integer, Float, String, Text, DateTime, func
from ..core.database import Base

class CognitionMarketState(Base):
    """
    市场状态快照 / Market State Artifact (M1.4 输出)
    明确定位：这是 Market State Snapshot，不等同于完整 Cognition Model。
    """
    __tablename__ = "cognition_market_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, index=True)
    timestamp = Column(String, nullable=False)
    indicators = Column(Text, nullable=False)        # 各指标计算结果 JSON
    composite_score = Column(Float)                  # 综合得分
    state_label = Column(String)                     # 状态标签（如“强势/震荡/冰点”）
    config_snapshot = Column(Text)                   # 当时使用的指标配置快照 JSON
    data_quality = Column(String, default="full")
    created_at = Column(DateTime, server_default=func.now())
