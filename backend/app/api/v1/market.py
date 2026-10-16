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
    return {"code": 200, "data": res.data, "quality": res.quality.value, "provider": res.provider}

@router.get("/stock-trends")
async def get_stock_trends(
    codes: str = Query(..., description="逗号分隔的股票/板块代码列表，例如 002696,002343,BK0480"),
    db: AsyncSession = Depends(get_db)
):
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    service = DataService(db)
    res = await service.get_stock_trends(code_list)
    return {"code": 200, "data": res.data, "quality": res.quality.value, "provider": res.provider}

