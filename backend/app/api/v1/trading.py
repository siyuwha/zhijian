from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional
from ...core.database import get_db
from ...services.trading import TradingService

router = APIRouter(prefix="/trading", tags=["Trading"])

class TradeRecordCreate(BaseModel):
    code: str
    name: str
    direction: str = Field(description="buy / sell")
    price: float
    quantity: int
    trade_time: str
    trade_reason: Optional[str] = None
    source: str = "manual"

class TradeNoteCreate(BaseModel):
    date: str
    mental_state: str
    decision_logic: str
    reflection: str
    lessons: str
    trade_id: Optional[int] = None

@router.get("/records")
async def list_records(limit: int = 50, db: AsyncSession = Depends(get_db)):
    service = TradingService(db)
    records = await service.get_records(limit)
    return {"code": 200, "data": records}

@router.post("/records")
async def add_record(payload: TradeRecordCreate, db: AsyncSession = Depends(get_db)):
    service = TradingService(db)
    record = await service.add_trade_record(
        code=payload.code,
        name=payload.name,
        direction=payload.direction,
        price=payload.price,
        quantity=payload.quantity,
        trade_time=payload.trade_time,
        trade_reason=payload.trade_reason,
        source=payload.source
    )
    return {"code": 200, "data": record}

@router.get("/positions")
async def list_positions(db: AsyncSession = Depends(get_db)):
    service = TradingService(db)
    positions = await service.get_positions()
    return {"code": 200, "data": positions}

@router.post("/notes")
async def add_note(payload: TradeNoteCreate, db: AsyncSession = Depends(get_db)):
    service = TradingService(db)
    note = await service.add_trade_note(
        date=payload.date,
        mental_state=payload.mental_state,
        decision_logic=payload.decision_logic,
        reflection=payload.reflection,
        lessons=payload.lessons,
        trade_id=payload.trade_id
    )
    return {"code": 200, "data": note}
