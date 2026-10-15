import sys
import types
from pathlib import Path
from contextlib import asynccontextmanager
import logging

# 双向路径与包别名兼容保护 (兼容 Docker 容器内缺少 backend 顶层目录问题)
_current_dir = Path(__file__).resolve().parent
_parent_dir = _current_dir.parent
for _p in [str(_current_dir), str(_parent_dir), "/app", "/"]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

if "backend" not in sys.modules:
    try:
        import app
        _backend_pkg = types.ModuleType("backend")
        _backend_pkg.app = app
        _backend_pkg.__path__ = []
        sys.modules["backend"] = _backend_pkg
        sys.modules["backend.app"] = app
    except Exception:
        pass

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

from .services.llm_config_service import LLMConfigService

setup_logging(debug=settings.DEBUG)
logger = logging.getLogger("trading_system")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing system...")
    await init_db()
    init_providers()
    LLMConfigService.load_and_apply_on_startup()
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

from .version import get_version_info, VERSION, get_git_commit

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "project": settings.PROJECT_NAME,
        "api_version": "v1",
        "app_version": f"v{VERSION}",
        "commit": get_git_commit()
    }

@app.get("/version")
async def version_info():
    return get_version_info()

