import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
from .core.database import init_db, async_session
from .core.logging import setup_logging
from . import models  # 注册所有ORM模型到Base.metadata
from .api.v1 import router as api_router
from .tasks.scheduler import task_scheduler
from .services.monitor import MonitorService
from .data.providers import init_providers

setup_logging(debug=settings.DEBUG)
logger = logging.getLogger("trading_system")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing system...")
    await init_db()
    init_providers()
    task_scheduler.start()
    MonitorService.start_background_daemon(async_session)
    logger.info(f"{settings.PROJECT_NAME} backend started successfully.")
    yield
    # Shutdown
    logger.info("Shutting down...")
    await MonitorService.stop_background_daemon(async_session)
    task_scheduler.shutdown()
    logger.info("Scheduler stopped.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
    debug=settings.DEBUG
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "project": settings.PROJECT_NAME,
        "api_version": "v1"
    }

@app.get("/version")
async def version_info():
    return {
        "status": "ok",
        "commit": "add942d",
        "sina_protocol": "http"
    }
