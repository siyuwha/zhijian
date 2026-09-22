from sqlalchemy import Column, Integer, Float, String, Text, DateTime, ForeignKey, func
from ..core.database import Base

class Strategy(Base):
    """策略定义（AI自主驱动 + 用户自定义双模式）"""
    __tablename__ = "strategy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    mode = Column(String, nullable=False)          # ai_driven / user_defined
    description = Column(Text)
    conditions = Column(Text)                      # 筛选条件 JSON
    universe_config = Column(Text)                 # 选股范围配置 JSON
    created_by = Column(String, default="user")    # ai / user
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class SelectionResult(Base):
    """选股批次结果"""
    __tablename__ = "selection_result"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("strategy.id"), nullable=False)
    date = Column(String, nullable=False, index=True)
    candidate_count = Column(Integer, default=0)
    market_state_id = Column(Integer, ForeignKey("cognition_market_state.id"), nullable=True)
    execution_log = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

class SelectionCandidate(Base):
    """候选池股票明细"""
    __tablename__ = "selection_candidate"

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_id = Column(Integer, ForeignKey("selection_result.id"), nullable=False)
    code = Column(String, nullable=False, index=True)
    name = Column(String)
    score = Column(Float)
    tier = Column(String)                          # A / B / C
    reasons = Column(Text)                         # 选入理由 JSON
    data_snapshot = Column(Text)                   # 选入时数据快照 JSON
