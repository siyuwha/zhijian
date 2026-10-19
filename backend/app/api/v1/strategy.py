from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from ...core.database import get_db
from ...services.selection import SelectionService

router = APIRouter(prefix="/strategy", tags=["Strategy & Selection"])

class StrategyCreate(BaseModel):
    name: str
    mode: str = "user_defined"
    description: Optional[str] = None
    conditions: Optional[str] = "{}"
    universe_config: Optional[str] = "{}"

@router.get("/strategies")
async def list_strategies(db: AsyncSession = Depends(get_db)):
    service = SelectionService(db)
    strategies = await service.get_strategies()
    return {"code": 200, "data": strategies}

@router.post("/strategies")
async def create_strategy(payload: StrategyCreate, db: AsyncSession = Depends(get_db)):
    service = SelectionService(db)
    strat = await service.create_strategy(
        name=payload.name,
        mode=payload.mode,
        description=payload.description,
        conditions=payload.conditions,
        universe_config=payload.universe_config
    )
    return {"code": 200, "data": strat}


@router.get("/classic-evaluation")
async def get_classic_strategy_evaluation(
    date: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    三大经典工业级策略 (弱转强竞价抢筹、连板分歧低吸、首板龙回头) 实盘/历史推演端点
    """
    service = SelectionService(db)
    res = await service.evaluate_classic_strategies(date=date)
    return res
