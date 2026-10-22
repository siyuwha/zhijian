from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from ...core.database import get_db
from ...services.selection import SelectionService
from ...services.backtest_engine import BacktestService

router = APIRouter(prefix="/strategy", tags=["Strategy & Selection"])

class StrategyCreate(BaseModel):
    name: str
    mode: str = "user_defined"
    description: Optional[str] = None
    conditions: Optional[str] = "{}"
    universe_config: Optional[str] = "{}"

class BacktestRunRequest(BaseModel):
    start_date: str = "2024-01-01"
    end_date: str = "2026-10-22"
    strategy_id: str = "weak_to_strong"
    initial_capital: float = 1000000.0
    min_open_pct: float = 1.5
    max_open_pct: float = 5.5
    stop_loss_pct: float = -5.0
    max_positions: int = 5
    holding_days: int = 2
    market_filter: bool = True

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

@router.get("/backtest/status")
async def get_backtest_status():
    """获取底层全量历史回测底座就绪状态与覆盖交易日区间"""
    service = BacktestService()
    res = service.get_status()
    return {"code": 200, "data": res}

@router.post("/backtest/run")
async def run_strategy_backtest(payload: BacktestRunRequest):
    """
    执行真实事件驱动的历史量化回测 (毫秒级吞吐，全市场 700+ 交易日模拟撮合)
    """
    service = BacktestService()
    res = service.run_backtest(
        start_date=payload.start_date,
        end_date=payload.end_date,
        strategy_id=payload.strategy_id,
        initial_capital=payload.initial_capital,
        min_open_pct=payload.min_open_pct,
        max_open_pct=payload.max_open_pct,
        stop_loss_pct=payload.stop_loss_pct,
        max_positions=payload.max_positions,
        holding_days=payload.holding_days,
        market_filter=payload.market_filter,
    )
    return res
