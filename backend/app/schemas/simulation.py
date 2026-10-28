from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class SimTradeCreate(BaseModel):
    code: str
    name: Optional[str] = None
    direction: str = Field(..., description="buy or sell")
    price: float = Field(..., gt=0)
    quantity: int = Field(..., gt=0)
    trade_time: Optional[str] = None
    strategy_id: Optional[int] = None
    decision_summary: Optional[str] = None

class SimAccountResponse(BaseModel):
    id: int
    name: str
    initial_capital: float
    current_capital: float
    market_value: float
    total_asset: float
    total_pnl: float
    total_pnl_pct: float

class SimPositionResponse(BaseModel):
    id: int
    account_id: int
    code: str
    name: Optional[str] = None
    quantity: int
    avg_cost: float
    total_cost: float = 0.0
    current_price: Optional[float] = None
    market_value: float = 0.0
    floating_pnl: Optional[float] = None
    floating_pnl_pct: Optional[float] = None
    updated_at: Optional[datetime] = None

class SimTradeResponse(BaseModel):
    id: int
    account_id: int
    code: str
    name: Optional[str] = None
    direction: str
    price: float
    quantity: int
    amount: float
    trade_time: str
    strategy_id: Optional[int] = None
    decision_summary: Optional[str] = None
    actual_outcome: Optional[str] = None
    created_at: Optional[datetime] = None

class SimStatsResponse(BaseModel):
    total_trades: int
    win_trades: int
    loss_trades: int
    closed_trades: int = 0
    win_rate: Optional[float] = None
    closed_leg_win_rate: Optional[float] = None
    payoff_ratio: Optional[float] = None
    total_pnl: float
    total_realized_pnl: float = 0.0
    available_cash: float
    market_value: float
    total_asset: float
