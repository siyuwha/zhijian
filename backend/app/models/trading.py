from sqlalchemy import Column, Integer, Float, String, Text, DateTime, ForeignKey, CheckConstraint, func
from ..core.database import Base

class TradeRecord(Base):
    """交易事实账本（Truth Ledger，只追加、禁止物理删除与就地修改）"""
    __tablename__ = "trade_record"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, nullable=False, index=True)
    name = Column(String)
    direction = Column(String, nullable=False)   # buy / sell
    price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)       # 服务端强制派生计算 round(price * quantity, 2)
    trade_time = Column(String, nullable=False)  # YYYY-MM-DD HH:MM:SS
    trade_reason = Column(Text)
    source = Column(String, default="manual")    # manual / agent_api
    record_type = Column(String, default="TRADE") # TRADE / REVERSAL
    reversed_record_id = Column(Integer, ForeignKey("trade_record.id"), nullable=True) # 仅冲正记录非空
    idempotency_key = Column(String, nullable=True, index=True) # 客户端幂等防重键
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        CheckConstraint("amount > 0 AND abs(amount - round(price * quantity, 2)) < 0.01", name="check_amount_matches_price_qty"),
    )

class Position(Base):
    """当前持仓派生快照（Materialized View / Cache）"""
    __tablename__ = "position"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String, nullable=False, unique=True, index=True)
    name = Column(String)
    quantity = Column(Integer, nullable=False)   # >= 0
    avg_cost = Column(Float, nullable=False)     # 加权成本均价
    total_cost = Column(Float, nullable=False)   # 总成本
    current_price = Column(Float, nullable=True) # 最新市价
    price_type = Column(String, default="UNAVAILABLE") # REALTIME / PREV_CLOSE / UNAVAILABLE
    quote_time = Column(String, nullable=True)   # 行情时间戳
    floating_pnl = Column(Float, nullable=True)  # 浮动盈亏
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class TradeNote(Base):
    """交易认知复盘反思笔记（与单笔交易 1:1 强绑定，支持增量追加）"""
    __tablename__ = "trade_note"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(Integer, ForeignKey("trade_record.id"), nullable=False, unique=True, index=True)
    date = Column(String, nullable=False, index=True)
    mental_state = Column(Text)       # 交易时心理状态
    decision_logic = Column(Text)     # 决策逻辑
    reflection = Column(Text)         # 事后反思（支持带时间戳增量追加 [HH:MM 追加]）
    lessons = Column(Text)            # 经验教训与规则固化
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
