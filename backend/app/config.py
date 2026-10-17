import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

def _resolve_data_dir() -> Path:
    """
    智能解析持久化数据目录：
    1. 优先环境变量 DATA_DIR
    2. 若运行在 Docker 容器环境 (/app/data 存在)，精确锚定挂载卷 /app/data
    3. 否则根据代码层级寻找宿主机本地工程根目录下的 data 目录
    """
    if os.environ.get("DATA_DIR"):
        d = Path(os.environ["DATA_DIR"]).resolve()
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return d

    # Docker 容器标准挂载卷点
    app_data = Path("/app/data")
    if app_data.exists():
        return app_data

    # 本地开发环境：递归向上寻找包含 data 或 backend 的工程根目录
    curr = Path(__file__).resolve()
    for candidate in [curr.parent.parent.parent, curr.parent.parent, curr.parent]:
        if (candidate / "data").exists():
            return (candidate / "data").resolve()

    # 兜底创建
    fallback = curr.parent.parent.parent / "data"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return fallback.resolve()

DATA_DIR = _resolve_data_dir()
PROJECT_ROOT = DATA_DIR.parent if DATA_DIR.name == "data" else Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = (DATA_DIR / "trading.db").as_posix()

# 智能探查 .env 文件是否存在且为合法文件 (防御 Docker 卷挂载把缺失文件自动挂成目录导致的 IsADirectoryError 崩溃)
_env_candidates = [Path(".env"), Path("/app/.env"), PROJECT_ROOT / ".env"]
_valid_env_file = next((f.as_posix() for f in _env_candidates if f.exists() and f.is_file()), None)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_valid_env_file, extra="ignore")

    PROJECT_NAME: str = "AI认知复盘交易系统"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}"
    DEBUG: bool = True

    # 默认不再硬编码 DeepSeek，允许完全由用户在前端设置中自定义并持久化到 DATA_DIR
    LLM_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""

settings = Settings()


