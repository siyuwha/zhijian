from sqlalchemy import Column, Integer, Float, String, Text, DateTime, ForeignKey, UniqueConstraint, func
from ..core.database import Base

class SimAccount(Base):
    """前向模拟账户"""
    __tablename__ = "sim_account"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    initial_capital = Column(Float, nullable=False)
    current_capital = Column(Float, nullable=False)
    total_pnl = Column(Float, default=0.0)
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())

class SimTrade(Base):
    """前向模拟交易执行与决策追踪"""
    __tablename__ = "sim_trade"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("sim_account.id"), nullable=False)
    code = Column(String, nullable=False, index=True)
    name = Column(String)
    direction = Column(String, nullable=False)   # buy / sell
    price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    trade_time = Column(String, nullable=False)
    strategy_id = Column(Integer, ForeignKey("strategy.id"), nullable=True)
    decision_summary = Column(Text)              # 简要决策说明（Phase 1 基础追踪）
    actual_outcome = Column(Text)                # 实际市场结果对比与复盘
    created_at = Column(DateTime, server_default=func.now())

class SimPosition(Base):
    """前向模拟持仓"""
    __tablename__ = "sim_position"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("sim_account.id"), nullable=False)
    code = Column(String, nullable=False, index=True)
    name = Column(String)
    quantity = Column(Integer, nullable=False)
    avg_cost = Column(Float, nullable=False)
    current_price = Column(Float)
    floating_pnl = Column(Float)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("account_id", "code", name="uix_sim_pos_account_code"),
    )
