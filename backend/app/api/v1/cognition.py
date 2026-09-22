import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ...core.database import get_db
from ...models.cognition import CognitionMarketState
from ...cognition.market_state import market_state_computer
from ...cognition.config import MarketStateV1Config

router = APIRouter(prefix="/cognition", tags=["Cognition"])

@router.get("/market-state/{date}")
async def get_market_state(date: str, db: AsyncSession = Depends(get_db)):
    stmt = select(CognitionMarketState).where(CognitionMarketState.date == date).order_by(CognitionMarketState.id.desc())
    record = (await db.execute(stmt)).scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="Cognition market state not found")

    return {
        "code": 200,
        "data": {
            "date": record.date,
            "timestamp": record.timestamp,
            "composite_score": record.composite_score,
            "state_label": record.state_label,
            "indicators": json.loads(record.indicators) if record.indicators else [],
            "data_quality": record.data_quality
        }
    }

@router.get("/config/indicators")
async def get_indicators_config():
    """获取当前可配置的指标体系与权重"""
    return {
        "code": 200,
        "data": market_state_computer.config.model_dump()
    }

@router.put("/config/indicators")
async def update_indicators_config(config: MarketStateV1Config):
    """更新指标体系与权重设置"""
    market_state_computer.update_config(config)
    return {
        "code": 200,
        "message": "Indicators config updated successfully",
        "data": market_state_computer.config.model_dump()
    }
