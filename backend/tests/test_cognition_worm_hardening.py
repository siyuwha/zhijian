"""
Step 1 Closure Follow-up / WORM Hardening 专项穿透测试
上位依据：最高董事会下一阶段工程裁决（第六条）
核心铁律：ORM Event Listener != Database-level WORM.
验证目标：
1. 验证 SQLite 数据库原生触发器 (Triggers) 真实存在于 sqlite_master
2. 验证绕过 ORM 直接执行原生 SQL UPDATE cognition_record 必被 DB 引擎触发器强行拒绝 (ABORT)
3. 验证绕过 ORM 直接执行原生 SQL DELETE cognition_record 必被 DB 引擎触发器强行拒绝
4. 验证绕过 ORM 直接执行原生 SQL UPDATE/DELETE cognition_prompt_spec 必被 DB 引擎拒绝
5. 验证绕过 ORM 直接执行原生 SQL DELETE cognition_chain_state 必被 DB 引擎拒绝
6. 验证 API 层 PUT / PATCH / DELETE 端点 100% 拒绝 (405 Method Not Allowed)
"""

import sys
import os
import pytest
import pytest_asyncio
from datetime import datetime
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, DatabaseError

from app.core.database import Base
from app.models.cognition_v2 import (
    CognitionRecord,
    CognitionPromptSpec,
    CognitionChainState,
    install_database_worm_triggers_async,
)
from app.cognition.chain_state import ensure_genesis_chain_state
from app.main import app


@pytest_asyncio.fixture
async def hardened_db():
    """提供带有完整原生触发器的隔离内存 SQLite 数据库"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await install_database_worm_triggers_async(conn)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session, engine

    await engine.dispose()


@pytest.mark.asyncio
async def test_worm_triggers_exist_in_sqlite_master(hardened_db):
    """验证 Trigger 真实存在于 sqlite_master 系统元数据表中"""
    session, engine = hardened_db
    
    result = await session.execute(text("SELECT name, tbl_name FROM sqlite_master WHERE type = 'trigger'"))
    triggers = {row[0]: row[1] for row in result.fetchall()}
    
    assert "trg_cognition_record_no_update" in triggers
    assert triggers["trg_cognition_record_no_update"] == "cognition_record"
    
    assert "trg_cognition_record_no_delete" in triggers
    assert triggers["trg_cognition_record_no_delete"] == "cognition_record"
    
    assert "trg_cognition_prompt_spec_no_update" in triggers
    assert triggers["trg_cognition_prompt_spec_no_update"] == "cognition_prompt_spec"
    
    assert "trg_cognition_prompt_spec_no_delete" in triggers
    assert triggers["trg_cognition_prompt_spec_no_delete"] == "cognition_prompt_spec"
    
    assert "trg_cognition_chain_state_no_delete" in triggers
    assert triggers["trg_cognition_chain_state_no_delete"] == "cognition_chain_state"


@pytest.mark.asyncio
async def test_direct_sql_update_cognition_record_rejected_by_db_trigger(hardened_db):
    """绕过 ORM 直接执行原生 SQL UPDATE cognition_record 必须被 DB 引擎拒绝"""
    session, engine = hardened_db
    
    # 1. 插入一条初始合法记录
    insert_sql = """
    INSERT INTO cognition_record (
        id, date, stage, timestamp, market_event_time, observation_window,
        data_snapshot_time, observation_snapshot, market_state_snapshot,
        prompt_id, prompt_version, prompt_hash, model_provider, model_name,
        model_version, inference_config, effective_input_hash,
        rendered_system_prompt, rendered_user_prompt, raw_response,
        structured_cognition, hypothesis_set_hash, sequence_id,
        previous_record_hash, payload_hash, record_hash, replay_type
    ) VALUES (
        'cog_test_001', '2026-09-30', 'POST_CLOSE', CURRENT_TIMESTAMP,
        '15:00:00', '15:00:00', CURRENT_TIMESTAMP, '{}', '{}',
        'prompt_v1', '1.0.0', 'hash_p1', 'deepseek', 'deepseek-r1',
        'v1', '{}', 'eff_hash_1', 'sys', 'user', 'resp',
        '{}', 'hypo_hash_1', 1, '0'*64, 'payload_hash_1', 'rec_hash_1', 'ORIGINAL'
    )
    """
    await session.execute(text(insert_sql))
    await session.commit()
    
    # 2. 绕过 SQLAlchemy ORM，使用直接原生 SQL UPDATE 企图篡改字段
    with pytest.raises((OperationalError, DatabaseError)) as exc_info:
        await session.execute(text("UPDATE cognition_record SET stage = 'MALICIOUS_TAMPER' WHERE id = 'cog_test_001'"))
        await session.commit()
        
    error_msg = str(exc_info.value)
    assert "DATABASE WORM VIOLATION" in error_msg
    assert "cognition_record is immutable" in error_msg


@pytest.mark.asyncio
async def test_direct_sql_delete_cognition_record_rejected_by_db_trigger(hardened_db):
    """绕过 ORM 直接执行原生 SQL DELETE cognition_record 必须被 DB 引擎拒绝"""
    session, engine = hardened_db
    
    # 1. 插入一条真实记录
    insert_sql = """
    INSERT INTO cognition_record (
        id, date, stage, timestamp, market_event_time, observation_window,
        data_snapshot_time, observation_snapshot, market_state_snapshot,
        prompt_id, prompt_version, prompt_hash, model_provider, model_name,
        model_version, inference_config, effective_input_hash,
        rendered_system_prompt, rendered_user_prompt, raw_response,
        structured_cognition, hypothesis_set_hash, sequence_id,
        previous_record_hash, payload_hash, record_hash, replay_type
    ) VALUES (
        'cog_del_001', '2026-09-30', 'POST_CLOSE', CURRENT_TIMESTAMP,
        '15:00:00', '15:00:00', CURRENT_TIMESTAMP, '{}', '{}',
        'prompt_v1', '1.0.0', 'hash_p1', 'deepseek', 'deepseek-r1',
        'v1', '{}', 'eff_hash_1', 'sys', 'user', 'resp',
        '{}', 'hypo_hash_1', 10, '0'*64, 'payload_hash_del', 'rec_hash_del', 'ORIGINAL'
    )
    """
    await session.execute(text(insert_sql))
    await session.commit()

    # 2. 绕过 SQLAlchemy ORM，使用直接原生 SQL DELETE 企图物理删除账本
    with pytest.raises((OperationalError, DatabaseError)) as exc_info:
        await session.execute(text("DELETE FROM cognition_record WHERE id = 'cog_del_001'"))
        await session.commit()
        
    error_msg = str(exc_info.value)
    assert "DATABASE WORM VIOLATION" in error_msg
    assert "cognition_record is immutable" in error_msg


@pytest.mark.asyncio
async def test_direct_sql_prompt_spec_mutation_rejected_by_db_trigger(hardened_db):
    """绕过 ORM 直接执行原生 SQL UPDATE/DELETE cognition_prompt_spec 必须被 DB 引擎拒绝"""
    session, engine = hardened_db
    
    # 1. 插入 Prompt 工件
    insert_sql = """
    INSERT INTO cognition_prompt_spec (id, prompt_id, version, prompt_hash, system_template, user_template)
    VALUES ('p1@1.0', 'p1', '1.0', 'phash_1', 'system text', 'user text')
    """
    await session.execute(text(insert_sql))
    await session.commit()
    
    # 2. 直接 SQL UPDATE 尝试篡改 Prompt
    with pytest.raises((OperationalError, DatabaseError)) as exc_info_update:
        await session.execute(text("UPDATE cognition_prompt_spec SET system_template = 'hacked' WHERE id = 'p1@1.0'"))
        await session.commit()
    assert "DATABASE WORM VIOLATION" in str(exc_info_update.value)
    assert "cognition_prompt_spec is immutable" in str(exc_info_update.value)
    
    # 3. 直接 SQL DELETE 尝试删除 Prompt
    with pytest.raises((OperationalError, DatabaseError)) as exc_info_delete:
        await session.execute(text("DELETE FROM cognition_prompt_spec WHERE id = 'p1@1.0'"))
        await session.commit()
    assert "DATABASE WORM VIOLATION" in str(exc_info_delete.value)


@pytest.mark.asyncio
async def test_direct_sql_chain_state_delete_rejected_by_db_trigger(hardened_db):
    """绕过 ORM 直接执行原生 SQL DELETE cognition_chain_state 必须被 DB 引擎拒绝"""
    session, engine = hardened_db
    await ensure_genesis_chain_state(session)
    
    # 直接 SQL DELETE 尝试删除控制行
    with pytest.raises((OperationalError, DatabaseError)) as exc_info:
        await session.execute(text("DELETE FROM cognition_chain_state WHERE chain_id = 'MAIN_LEDGER'"))
        await session.commit()
    assert "DATABASE WORM VIOLATION" in str(exc_info.value)
    assert "cognition_chain_state is permanent ledger anchor" in str(exc_info.value)


@pytest.mark.asyncio
async def test_api_level_worm_rejection():
    """验证 API 层对 UPDATE/DELETE 请求统一拦截并返回 405 Method Not Allowed"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. 认知记录 UPDATE
        put_rec = await client.put("/api/v1/cognition/records/cog_123", json={"stage": "TAMPER"})
        assert put_rec.status_code == 405
        assert "WORM Violation" in put_rec.text
        
        patch_rec = await client.patch("/api/v1/cognition/records/cog_123", json={"stage": "TAMPER"})
        assert patch_rec.status_code == 405
        
        # 2. 认知记录 DELETE
        del_rec = await client.delete("/api/v1/cognition/records/cog_123")
        assert del_rec.status_code == 405
        assert "WORM Violation" in del_rec.text

        # 3. PromptSpec UPDATE / DELETE
        put_spec = await client.put("/api/v1/cognition/prompt-specs/spec_1", json={"template": "TAMPER"})
        assert put_spec.status_code == 405
        
        del_spec = await client.delete("/api/v1/cognition/prompt-specs/spec_1")
        assert del_spec.status_code == 405

        # 4. ChainState DELETE
        del_chain = await client.delete("/api/v1/cognition/chain-state/MAIN_LEDGER")
        assert del_chain.status_code == 405
        assert "permanent ledger anchor" in del_chain.text
