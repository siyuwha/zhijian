import os
import sys
import tempfile
from pathlib import Path
import pytest

# Ensure backend directory is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Configure an isolated temporary database path for test runs to prevent polluting data/trading.db
test_db_file = Path(tempfile.gettempdir()) / f"trading_test_sandbox_{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{test_db_file.as_posix()}"

@pytest.fixture(scope="session", autouse=True)
async def hermetic_test_database_sandbox():
    """
    EG-01 Test Isolation:
    Session-scoped fixture ensuring test runs operate on an isolated sandbox database,
    strictly preventing any writes or mutations to physical data/trading.db instances.
    """
    if test_db_file.exists():
        try:
            test_db_file.unlink()
        except Exception:
            pass

    # Physical schema & WORM triggers initialization on the isolated sandbox
    import sqlalchemy as sa
    from app.core.database import Base, engine
    import app.models
    from app.models.cognition_v2 import DATABASE_WORM_TRIGGERS_SQL
    from app.cognition.chain_state import DEFAULT_CHAIN_ID, GENESIS_PREVIOUS_HASH

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for trigger_sql in DATABASE_WORM_TRIGGERS_SQL:
            await conn.execute(sa.text(trigger_sql))
        has_genesis = (await conn.execute(sa.text(f"SELECT count(*) FROM cognition_chain_state WHERE chain_id = '{DEFAULT_CHAIN_ID}'"))).scalar()
        if not has_genesis:
            await conn.execute(sa.text(f"""
                INSERT INTO cognition_chain_state (chain_id, tail_sequence_id, tail_record_hash)
                VALUES ('{DEFAULT_CHAIN_ID}', 0, '{GENESIS_PREVIOUS_HASH}')
            """))

    yield

    await engine.dispose()

    if test_db_file.exists():
        try:
            test_db_file.unlink()
        except Exception:
            pass
