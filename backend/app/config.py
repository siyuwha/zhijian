import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Canonical project root: directory containing 'backend' and 'data'
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = (PROJECT_ROOT / "data" / "trading.db").as_posix()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "AI认知复盘交易系统"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}"
    DEBUG: bool = True

    LLM_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.deepseek.com/v1"
    LLM_MODEL: str = "deepseek-chat"

settings = Settings()

