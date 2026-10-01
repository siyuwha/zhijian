from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from ..config import settings
import os
db_file = settings.DATABASE_URL.split("///")[-1]
if db_file and not db_file.startswith(":memory:"):
    db_dir = os.path.dirname(db_file)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
async_session = async_sessionmaker(engine, expire_on_commit=False)
async_session_factory = async_session

Base = declarative_base()

async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session

async def init_db():
    from ..models.cognition_v2 import install_database_worm_triggers_async
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await install_database_worm_triggers_async(conn)
