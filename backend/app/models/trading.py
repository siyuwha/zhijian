from sqlalchemy import Column, Integer, Float, String, Text, DateTime, ForeignKey, func
from ..core.database import Base

class TradeRecord(Base):
    """交易记录（手工录入或外部Agent标准接口写入）"""
    __tablename__ = "trade_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, nullable=False, index=True)
    name = Column(String)
    direction = Column(String, nullable=False)   # buy / sell
    price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    amount = Column(Float)
    trade_time = Column(String, nullable=False)  # YYYY-MM-DD HH:MM:SS
    trade_reason = Column(Text)
    source = Column(String, default="manual")    # manual / agent_api
    created_at = Column(DateTime, server_default=func.now())

class Position(Base):
    """当前持仓"""
    __tablename__ = "position"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, nullable=False, unique=True, index=True)
    name = Column(String)
    quantity = Column(Integer, nullable=False)
    avg_cost = Column(Float, nullable=False)
    total_cost = Column(Float)
    current_price = Column(Float)
    floating_pnl = Column(Float)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class TradeNote(Base):
    """交易复盘笔记与反思"""
    __tablename__ = "trade_note"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(Integer, ForeignKey("trade_record.id"), nullable=True)
    date = Column(String, nullable=False, index=True)
    mental_state = Column(Text)       # 交易时心理状态
    decision_logic = Column(Text)     # 决策逻辑
    reflection = Column(Text)         # 事后反思
    lessons = Column(Text)            # 经验教训
    created_at = Column(DateTime, server_default=func.now())
