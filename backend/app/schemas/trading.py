from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any
from datetime import datetime
import re

class TradeRecordCreate(BaseModel):
    code: str = Field(..., description="6位A股纯数字代码，如 600519 或 000001")
    name: Optional[str] = Field(None, description="股票名称")
    direction: str = Field(..., description="交易方向：buy 或 sell")
    price: float = Field(..., gt=0, description="成交单价，必须大于0")
    quantity: int = Field(..., gt=0, description="成交股数，必须为正整数")
    trade_time: str = Field(..., description="成交时间，格式 YYYY-MM-DD HH:MM:SS")
    trade_reason: Optional[str] = Field(None, max_length=500, description="交易理由简述")
    source: str = Field("manual", description="来源渠道：manual 或 agent_api")
    idempotency_key: Optional[str] = Field(None, max_length=64, description="客户端幂等唯一键")

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        code_str = v.strip()
        if not re.match(r"^\d{6}$", code_str):
            raise ValueError("股票代码必须为6位纯数字")
        return code_str

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        d = v.lower().strip()
        if d not in ("buy", "sell"):
            raise ValueError("交易方向只能为 buy 或 sell")
        return d

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: int) -> int:
        if v < 100 or v % 100 != 0:
            raise ValueError("交易数量必须为 100 股或 100 的整数倍 (一手起报)")
        return v

class ReversalTradeCreate(BaseModel):
    target_record_id: int = Field(..., description="待红字冲正的原始交易流水ID")
    reason: str = Field(..., min_length=2, max_length=200, description="冲正原因说明")
    idempotency_key: Optional[str] = Field(None, max_length=64, description="客户端幂等唯一键")

class CorrectTradeRecordRequest(BaseModel):
    target_record_id: int = Field(..., description="待纠错的原始交易流水ID")
    reason: str = Field(..., min_length=2, max_length=200, description="纠错/修改原因说明")
    corrected_data: TradeRecordCreate = Field(..., description="修正后的有效交易内容")

class TradeNoteCreate(BaseModel):
    trade_id: int = Field(..., description="关联的具体交易ID（1:1唯一对应）")
    date: str = Field(..., description="记录日期 YYYY-MM-DD")
    mental_state: Optional[str] = Field(None, max_length=200, description="心理状态")
    decision_logic: Optional[str] = Field(None, max_length=1000, description="决策逻辑")
    reflection: Optional[str] = Field(None, max_length=2000, description="事后反思")
    lessons: Optional[str] = Field(None, max_length=1000, description="经验教训")
    append_mode: bool = Field(True, description="是否为增量时间戳追加模式")

class TradeNoteResponse(BaseModel):
    id: int
    trade_id: int
    date: str
    mental_state: Optional[str] = None
    decision_logic: Optional[str] = None
    reflection: Optional[str] = None
    lessons: Optional[str] = None
    created_at: Optional[Any] = None
    updated_at: Optional[Any] = None

    class Config:
        from_attributes = True

class TradeRecordResponse(BaseModel):
    id: int
    code: str
    name: Optional[str] = None
    direction: str
    price: float
    quantity: int
    amount: float
    trade_time: str
    trade_reason: Optional[str] = None
    source: str
    record_type: str
    reversed_record_id: Optional[int] = None
    idempotency_key: Optional[str] = None
    created_at: Optional[Any] = None
    realized_pnl: Optional[float] = None
    note: Optional[TradeNoteResponse] = None

    class Config:
        from_attributes = True

class PositionResponse(BaseModel):
    id: int
    code: str
    name: Optional[str] = None
    quantity: int
    avg_cost: float
    total_cost: float
    current_price: Optional[float] = None
    price_type: str
    quote_time: Optional[str] = None
    floating_pnl: Optional[float] = None
    floating_pnl_pct: Optional[float] = None
    market_value: Optional[float] = None
    updated_at: Optional[Any] = None

    class Config:
        from_attributes = True

class TradeStatsResponse(BaseModel):
    total_trades: int
    closed_trades: int
    win_trades: int
    loss_trades: int
    closed_leg_win_rate: Optional[float] = None
    payoff_ratio: Optional[float] = None
    total_realized_pnl: float
    total_floating_pnl: Optional[float] = None
    total_market_value: Optional[float] = None
    total_pnl: Optional[float] = None
    quote_status: str = "FULL"
