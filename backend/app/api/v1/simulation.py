from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from ...core.database import get_db
from ...services.simulation import SimulationService
from ...schemas.simulation import (
    SimTradeCreate,
    SimAccountResponse,
    SimPositionResponse,
    SimTradeResponse,
    SimStatsResponse,
)

router = APIRouter(prefix="/simulation", tags=["Forward Simulation"])

@router.get("/account")
async def get_simulation_account(db: AsyncSession = Depends(get_db)):
    """获取策略实盘模拟账户资产总览"""
    service = SimulationService(db)
    res = await service.get_account_summary()
    return {"code": 200, "data": res}

@router.get("/positions")
async def list_simulation_positions(
    refresh_quote: bool = Query(True, description="是否刷新实时行情"),
    db: AsyncSession = Depends(get_db)
):
    """获取策略实盘模拟持仓列表（物理隔离真实券商账户）"""
    service = SimulationService(db)
    positions = await service.get_positions(refresh_quote=refresh_quote)
    return {"code": 200, "data": positions}

@router.get("/records")
async def list_simulation_records(
    limit: int = Query(50, ge=1, le=200, description="返回数量"),
    db: AsyncSession = Depends(get_db)
):
    """获取策略实盘模拟交易执行流水"""
    service = SimulationService(db)
    records = await service.get_records(limit=limit)
    return {"code": 200, "data": {"items": records, "total": len(records)}}

@router.post("/trades")
async def execute_simulation_trade(
    payload: SimTradeCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    执行策略实盘模拟买入/卖出委托。
    正式模拟交易入口严格由服务端控制执行时间与 A 股 T+1 刚性规则。
    客户端禁止指定 trade_time（杜绝倒填买入时间绕过 T+1 漏洞）。
    """
    if payload.trade_time is not None:
        raise HTTPException(
            status_code=400,
            detail="正式模拟交易入口禁止客户端指定成交时间 (trade_time)，成交时间严格由服务端当前时钟受控决定"
        )
    service = SimulationService(db, enforce_t1=True)
    result = await service.execute_trade(payload, check_t1=True, allow_future=False)
    return {"code": 200, "data": result}

@router.get("/stats")
async def get_simulation_stats(db: AsyncSession = Depends(get_db)):
    """获取策略实盘模拟胜率与资金收益统计"""
    service = SimulationService(db)
    stats = await service.get_stats()
    return {"code": 200, "data": stats}

@router.post("/reset")
async def reset_simulation_account(db: AsyncSession = Depends(get_db)):
    """重置模拟沙盒账户 (恢复 100 万虚拟本金并清空持仓与流水)"""
    service = SimulationService(db)
    res = await service.reset_account()
    return {"code": 200, "data": res}
