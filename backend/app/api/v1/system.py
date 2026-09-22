from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ...core.database import get_db
from ...models.system import DataQualityLog, TaskLog, SystemConfig

router = APIRouter(prefix="/system", tags=["System Maintenance"])

@router.get("/data-quality")
async def list_data_quality_logs(limit: int = 50, db: AsyncSession = Depends(get_db)):
    stmt = select(DataQualityLog).order_by(DataQualityLog.created_at.desc()).limit(limit)
    logs = (await db.execute(stmt)).scalars().all()
    return {"code": 200, "data": logs}

@router.get("/tasks")
async def list_task_logs(limit: int = 50, db: AsyncSession = Depends(get_db)):
    stmt = select(TaskLog).order_by(TaskLog.created_at.desc()).limit(limit)
    logs = (await db.execute(stmt)).scalars().all()
    return {"code": 200, "data": logs}
