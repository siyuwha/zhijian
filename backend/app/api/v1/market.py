from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from ...core.database import get_db
from ...data.service import DataService

router = APIRouter(prefix="/market", tags=["Market Data"])

@router.get("/indices")
async def get_index_quotes(
    codes: Optional[str] = Query(default="sh000001,sz399001,sz399006,sh000688"),
    db: AsyncSession = Depends(get_db)
):
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    service = DataService(db)
    res = await service.get_index_quotes(code_list)
    return {"code": 200, "data": res.data, "quality": res.quality.value, "provider": res.provider}

@router.get("/limit-up")
async def get_limit_up_pool(
    date: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    service = DataService(db)
    res = await service.get_limit_up_pool(date)
    return {"code": 200, "data": res.data, "quality": res.quality.value, "provider": res.provider}

@router.get("/news")
async def get_latest_news(
    count: int = 15,
    db: AsyncSession = Depends(get_db)
):
    service = DataService(db)
    res = await service.get_latest_news(count)
    return {"code": 200, "data": res.data, "quality": res.quality.value, "provider": res.provider}

@router.get("/sectors")
async def get_sectors(
    sector_type: str = Query(default="industry", description="industry (行业) or concept (概念)"),
    limit: int = Query(default=15, ge=1, le=50, description="返回数量"),
    db: AsyncSession = Depends(get_db)
):
    service = DataService(db)
    res = await service.get_sector_ranking(sector_type=sector_type)
    src_ts = getattr(res, "source_timestamp", None)
    recv_ts = getattr(res, "received_timestamp", None) or getattr(res, "timestamp", None)
    err_code = getattr(res, "error_code", None)
    err_code_val = err_code.value if hasattr(err_code, "value") else (str(err_code) if err_code else None)
    return {
        "code": 200,
        "data": res.data if res.data is not None else [],
        "quality": res.quality.value if hasattr(res, "quality") and hasattr(res.quality, "value") else str(getattr(res, "quality", "UNKNOWN")),
        "freshness": getattr(res.freshness, "value", str(getattr(res, "freshness", "REALTIME"))),
        "status": getattr(res.status, "value", str(getattr(res, "status", "AVAILABLE"))),
        "error_code": err_code_val,
        "trade_date": getattr(res, "trade_date", None),
        "provider": res.provider,
        "fallback_used": getattr(res, "fallback_used", False),
        "degradation_reason": getattr(res, "degradation_reason", None) or getattr(res, "error_message", None),
        "source_timestamp": src_ts.isoformat() if hasattr(src_ts, "isoformat") else (str(src_ts) if src_ts else None),
        "received_timestamp": recv_ts.isoformat() if hasattr(recv_ts, "isoformat") else (str(recv_ts) if recv_ts else None),
    }

@router.get("/stock-trends")
async def get_stock_trends(
    codes: str = Query(..., description="逗号分隔的股票/板块代码列表，例如 002696,002343,BK0480"),
    trade_date: Optional[str] = Query(None, description="交易日期，格式 YYYY-MM-DD 或 YYYYMMDD"),
    date: Optional[str] = Query(None, description="别名兼容：交易日期"),
    db: AsyncSession = Depends(get_db)
):
    actual_date = trade_date or date
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    service = DataService(db)
    res = await service.get_stock_trends(code_list, trade_date=actual_date)
    src_ts = getattr(res, "source_timestamp", None)
    recv_ts = getattr(res, "received_timestamp", None) or getattr(res, "timestamp", None)
    err_code = getattr(res, "error_code", None)
    err_code_val = err_code.value if hasattr(err_code, "value") else (str(err_code) if err_code else None)
    resp = {
        "code": 200,
        "data": res.data if res.data is not None else [],
        "quality": res.quality.value if hasattr(res, "quality") and hasattr(res.quality, "value") else str(getattr(res, "quality", "UNKNOWN")),
        "freshness": getattr(res.freshness, "value", str(getattr(res, "freshness", "REALTIME"))),
        "status": getattr(res.status, "value", str(getattr(res, "status", "AVAILABLE"))),
        "error_code": err_code_val,
        "trade_date": getattr(res, "trade_date", None) or actual_date,
        "provider": res.provider,
        "fallback_used": getattr(res, "fallback_used", False),
        "degradation_reason": getattr(res, "degradation_reason", None) or getattr(res, "error_message", None),
        "source_timestamp": src_ts.isoformat() if hasattr(src_ts, "isoformat") else (str(src_ts) if src_ts else None),
        "received_timestamp": recv_ts.isoformat() if hasattr(recv_ts, "isoformat") else (str(recv_ts) if recv_ts else None),
    }
    if getattr(res, "missing_codes", None) is not None:
        resp["missing_codes"] = res.missing_codes
    return resp

