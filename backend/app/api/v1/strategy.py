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

class VetoOrderRequest(BaseModel):
    code: str
    reason: Optional[str] = "Manual Trader Veto"

class ReplayRunRequest(BaseModel):
    date: str = "2024-03-05"

class SyncRunRequest(BaseModel):
    date: Optional[str] = None
    force: bool = False

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

# =============================================================================
# 无人值守交易时钟、双轨一票否决与单日全真回放 API
# =============================================================================
@router.get("/autonomous/status")
async def get_autonomous_status():
    """获取当前无人值守交易时钟、双轨否决缓冲窗口与待撮合指令状态"""
    from ...tasks.scheduler import task_scheduler
    status = task_scheduler.get_autonomous_state()
    return {"code": 200, "data": status}

@router.post("/autonomous/veto")
async def execute_order_veto(payload: VetoOrderRequest):
    """
    在 09:25:00 ~ 09:29:50 双轨缓冲窗口内行使交易员一票否决权
    """
    from ...tasks.scheduler import task_scheduler
    ok = task_scheduler.veto_order(payload.code, payload.reason or "Manual Trader Veto")
    if ok:
        return {"code": 200, "message": f"标的 {payload.code} 已被成功否决废弃，不会在 09:30 撮合成交", "data": {"code": payload.code, "vetoed": True}}
    else:
        return {"code": 400, "message": f"否决失败：标的 {payload.code} 不在缓冲队列中或当前不在 09:25~09:29:50 缓冲窗口", "data": {"code": payload.code, "vetoed": False}}

@router.post("/autonomous/replay")
async def run_single_day_replay(payload: ReplayRunRequest, db: AsyncSession = Depends(get_db)):
    """
    单交易日全时钟全真倍速闭环回放测试：
    09:26 策略计算 ➔ 09:28 预埋队列 ➔ 09:30 开盘撮合 ➔ 盘中风控守护 ➔ 15:05 收盘结算
    """
    from ...services.autonomous_executor import AutonomousJobEngine
    engine = AutonomousJobEngine(db)
    res = await engine.replay_single_day(test_date=payload.date)
    return {"code": 200, "data": res}

@router.post("/autonomous/sync")
async def run_incremental_data_sync(payload: SyncRunRequest):
    """
    手动/定时触发 方案 A 增量行情自给同步 (无头直接补齐本地 Parquet)
    """
    from ...services.incremental_sync import incremental_sync_pipeline
    res = await incremental_sync_pipeline(target_date=payload.date, force=payload.force)
    return {"code": 200, "data": res}

