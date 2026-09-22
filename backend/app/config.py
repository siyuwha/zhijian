from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "AI认知复盘交易系统"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/trading.db"
    DEBUG: bool = True

    class Config:
        env_file = ".env"

settings = Settings()
