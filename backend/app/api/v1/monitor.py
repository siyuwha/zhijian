from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...services.monitor import MonitorService

router = APIRouter(prefix="/monitor", tags=["Intraday Monitor"])

@router.get("/realtime")
async def get_monitor_realtime(
    date: Optional[str] = Query(default=None, description="交易日 YYYY-MM-DD，缺省为今日"),
    db: AsyncSession = Depends(get_db)
):
    """获取盘中实时综合宏观与重点池切片"""
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    service = MonitorService(db)
    data = await service.get_realtime_snapshot(target_date)
    return {"code": 200, "data": data}

@router.get("/series")
async def get_monitor_series(
    date: Optional[str] = Query(default=None, description="交易日 YYYY-MM-DD，缺省为今日"),
    db: AsyncSession = Depends(get_db)
):
    """获取盘中分时宏观走势时序数据"""
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    service = MonitorService(db)
    data = await service.get_series_data(target_date)
    return {"code": 200, "data": data}

@router.get("/events")
async def get_monitor_events(
    date: Optional[str] = Query(default=None, description="交易日 YYYY-MM-DD，缺省为今日"),
    severity: Optional[str] = Query(default=None, description="事件严重级别: CRITICAL / TRANSITION / INFO"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db)
):
    """获取盘中客观异动与相变事件流 (边沿触发)"""
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    service = MonitorService(db)
    data = await service.get_events_stream(target_date, severity=severity, limit=limit)
    return {"code": 200, "data": data}

@router.get("/watchlist")
async def get_monitor_watchlist(
    date: Optional[str] = Query(default=None, description="交易日 YYYY-MM-DD，缺省为今日"),
    db: AsyncSession = Depends(get_db)
):
    """获取重点监控池当前盘中状态"""
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    service = MonitorService(db)
    symbols = await service.build_watchlist_universe(target_date)
    return {"code": 200, "data": {"symbols": symbols, "count": len(symbols)}}

@router.post("/trigger-scan")
async def trigger_monitor_scan(
    date: Optional[str] = Query(default=None, description="交易日 YYYY-MM-DD，缺省为今日"),
    db: AsyncSession = Depends(get_db)
):
    """触发一次盘中宏观快照采集与异动扫描 (用于调度器与测试)"""
    target_date = date or datetime.now().strftime("%Y-%m-%d")
    service = MonitorService(db)
    snapshot = await service.capture_macro_snapshot(target_date)
    events = await service.detect_anomalies(target_date)
    await service.flush_async_queue()
    return {
        "code": 200,
        "data": {
            "snapshot": snapshot,
            "events_detected": len(events),
            "events": events
        }
    }
