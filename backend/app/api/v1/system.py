from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ...core.database import get_db
from ...models.system import DataQualityLog, TaskLog, SystemConfig
from ...schemas.system_llm import (
    LLMConfigResponse,
    LLMConfigUpdateRequest,
    LLMTestConnectionRequest,
    LLMTestConnectionResponse,
)
from ...services.llm_config_service import LLMConfigService

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


# =========================================================================
# 系统 LLM 与兼容 OpenAI 中转站 API 设置与连通性测试
# =========================================================================

@router.get("/llm-config", response_model=LLMConfigResponse)
async def get_system_llm_config():
    """获取当前系统生效的 LLM / OpenAI 中转站配置"""
    return LLMConfigService.get_active_config()


@router.post("/llm-config", response_model=LLMConfigResponse)
async def update_system_llm_config(payload: LLMConfigUpdateRequest):
    """保存并实时热加载系统 LLM / OpenAI 中转站配置"""
    return LLMConfigService.save_config(payload)


@router.post("/llm-config/test", response_model=LLMTestConnectionResponse)
async def test_system_llm_connection(payload: LLMTestConnectionRequest):
    """实际发起请求测试指定中转站端点与模型连通性"""
    return await LLMConfigService.test_connection(payload)


@router.post("/llm-config/reset", response_model=LLMConfigResponse)
async def reset_system_llm_config():
    """重置 LLM 配置为系统环境变量默认值"""
    return LLMConfigService.reset_config()

