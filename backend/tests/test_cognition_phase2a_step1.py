"""
Unit tests for Cognition Phase 2A Step 1: Storage & WORM Foundation
依据：《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》(v1.2.1-FINAL-CLOSURE)
     《开发文档/29-Cognition-Phase2A架构与数据契约冻结决议与实施约束单.md》

测试目标：
1. 验证 cognition_record, cognition_chain_state, cognition_prompt_spec, cognition_diff_report 表结构创建；
2. 验证 cognition_chain_state 单行创世控制记录初始化与幂等性；
3. 验证 CognitionRecord 的全字段合规持久化；
4. 验证 WORM (Write-Once-Read-Many) 防篡改守卫（拦截 UPDATE / DELETE）；
5. 验证 PromptSpec 的 WORM 防篡改守卫；
6. 验证 ChainState 的更新许可与防删除守卫；
7. 验证 sequence_id 与 record_hash 唯一性约束。
"""

import pytest
import pytest_asyncio
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError

from app.core.database import Base
from app.models.cognition_v2 import (
    CognitionRecord,
    CognitionChainState,
    CognitionPromptSpec,
    CognitionDiffReport,
)
from app.cognition.chain_state import (
    ensure_genesis_chain_state,
    get_current_chain_state,
    DEFAULT_CHAIN_ID,
    GENESIS_PREVIOUS_HASH,
)


@pytest_asyncio.fixture
async def test_session():
    # 使用独立内存 SQLite 数据库进行严密隔离测试
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_step1_schema_creation(test_session: AsyncSession):
    """AC-01 基础：验证 Phase 2A 四大核心存储表成功注册与创建"""
    table_names = [table.name for table in Base.metadata.sorted_tables]
    assert "cognition_record" in table_names
    assert "cognition_chain_state" in table_names
    assert "cognition_prompt_spec" in table_names
    assert "cognition_diff_report" in table_names


@pytest.mark.asyncio
async def test_step1_genesis_chain_state_initialization(test_session: AsyncSession):
    """AC-06 基础：验证 chain_state 创世控制记录单行就绪与幂等性 (C-04)"""
    # 1. 首次初始化
    genesis = await ensure_genesis_chain_state(test_session)
    assert genesis.chain_id == DEFAULT_CHAIN_ID
    assert genesis.tail_sequence_id == 0
    assert genesis.tail_record_hash == GENESIS_PREVIOUS_HASH
    assert len(genesis.tail_record_hash) == 64

    # 2. 幂等性验证 (再次调用不会创建第二行，且不会破坏现有状态)
    genesis_again = await ensure_genesis_chain_state(test_session)
    assert genesis_again.tail_sequence_id == 0
    assert genesis_again.tail_record_hash == GENESIS_PREVIOUS_HASH

    # 3. 确认表中仅有唯一的单行
    stmt = select(CognitionChainState)
    rows = (await test_session.execute(stmt)).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_step1_cognition_record_persistence(test_session: AsyncSession):
    """验证 CognitionRecord 全要素与四维时间字段完整落盘"""
    record = CognitionRecord(
        id="cog_20260930_153000_0001",
        date="2026-09-30",
        stage="POST_CLOSE",
        timestamp=datetime(2026, 9, 30, 15, 30, 0),
        market_event_time="15:00:00",
        observation_window="09:15:00-15:00:00",
        data_snapshot_time=datetime(2026, 9, 30, 15, 5, 0),
        verification_execute_time=None,
        observation_snapshot='{"indices": [{"code": "sh000001", "close": 3000.0}]}',
        market_state_snapshot='{"composite_score": 65.5, "state_label": "强势"}',
        prompt_id="prompt_daily_review",
        prompt_version="v1.0.0",
        prompt_hash="a" * 64,
        model_provider="anthropic",
        model_name="claude-3-5-sonnet",
        model_version="20241022",
        inference_config='{"temperature": 0.0, "seed": 42}',
        effective_input_hash="b" * 64,
        rendered_system_prompt="You are an audited cognition engine.",
        rendered_user_prompt="Input market facts...",
        raw_response="Market thesis: liquidity expansion.",
        response_tokens=150,
        latency_ms=1200,
        structured_cognition='{"core_thesis": "liquidity expansion", "confidence": 0.85}',
        hypothesis_set_hash="c" * 64,
        sequence_id=1,
        previous_record_hash="0" * 64,
        payload_hash="d" * 64,
        record_hash="e" * 64,
        replay_type="ORIGINAL",
        deterministic_level="BIT_EXACT",
    )
    test_session.add(record)
    await test_session.commit()

    # 查询回读验证
    stmt = select(CognitionRecord).where(CognitionRecord.id == "cog_20260930_153000_0001")
    saved = (await test_session.execute(stmt)).scalars().first()
    assert saved is not None
    assert saved.sequence_id == 1
    assert saved.previous_record_hash == "0" * 64
    assert saved.market_event_time == "15:00:00"
    assert saved.replay_type == "ORIGINAL"


@pytest.mark.asyncio
async def test_step1_worm_guard_blocks_record_update(test_session: AsyncSession):
    """WORM 铁律验证：尝试 UPDATE CognitionRecord 必须被物理拦截并报错"""
    record = CognitionRecord(
        id="cog_20260930_153000_0002",
        date="2026-09-30",
        stage="POST_CLOSE",
        timestamp=datetime.now(),
        market_event_time="15:00:00",
        observation_window="09:15:00-15:00:00",
        data_snapshot_time=datetime.now(),
        observation_snapshot="{}",
        market_state_snapshot="{}",
        prompt_id="p1",
        prompt_version="v1",
        prompt_hash="1" * 64,
        model_provider="p",
        model_name="m",
        model_version="v",
        inference_config="{}",
        effective_input_hash="2" * 64,
        rendered_system_prompt="sys",
        rendered_user_prompt="user",
        raw_response="resp",
        structured_cognition="{}",
        hypothesis_set_hash="3" * 64,
        sequence_id=2,
        previous_record_hash="e" * 64,
        payload_hash="4" * 64,
        record_hash="5" * 64,
    )
    test_session.add(record)
    await test_session.commit()

    # 尝试修改记录（例如篡改 raw_response 或 stage）
    record.raw_response = "TAMPERED RESPONSE"
    with pytest.raises(RuntimeError, match="WORM Violation: CognitionRecord is immutable"):
        await test_session.commit()

    await test_session.rollback()


@pytest.mark.asyncio
async def test_step1_worm_guard_blocks_record_delete(test_session: AsyncSession):
    """WORM 铁律验证：尝试 DELETE CognitionRecord 必须被物理拦截并报错"""
    record = CognitionRecord(
        id="cog_20260930_153000_0003",
        date="2026-09-30",
        stage="POST_CLOSE",
        timestamp=datetime.now(),
        market_event_time="15:00:00",
        observation_window="09:15:00-15:00:00",
        data_snapshot_time=datetime.now(),
        observation_snapshot="{}",
        market_state_snapshot="{}",
        prompt_id="p1",
        prompt_version="v1",
        prompt_hash="1" * 64,
        model_provider="p",
        model_name="m",
        model_version="v",
        inference_config="{}",
        effective_input_hash="2" * 64,
        rendered_system_prompt="sys",
        rendered_user_prompt="user",
        raw_response="resp",
        structured_cognition="{}",
        hypothesis_set_hash="3" * 64,
        sequence_id=3,
        previous_record_hash="5" * 64,
        payload_hash="6" * 64,
        record_hash="7" * 64,
    )
    test_session.add(record)
    await test_session.commit()

    # 尝试删除该记录
    await test_session.delete(record)
    with pytest.raises(RuntimeError, match="WORM Violation: CognitionRecord is immutable"):
        await test_session.commit()

    await test_session.rollback()


@pytest.mark.asyncio
async def test_step1_worm_guard_blocks_prompt_spec_mutation(test_session: AsyncSession):
    """WORM 铁律验证：Prompt 模板工件一旦落盘禁止 UPDATE / DELETE"""
    spec = CognitionPromptSpec(
        id="prompt_daily_review@v1.0.0",
        prompt_id="prompt_daily_review",
        version="v1.0.0",
        prompt_hash="p" * 64,
        system_template="System prompt template content",
        user_template="User prompt template content",
    )
    test_session.add(spec)
    await test_session.commit()

    # 尝试原地修改模板内容
    spec.system_template = "Tampered template"
    with pytest.raises(RuntimeError, match="WORM Violation: CognitionPromptSpec is immutable"):
        await test_session.commit()
    await test_session.rollback()

    # 尝试删除模板
    spec_query = await test_session.get(CognitionPromptSpec, "prompt_daily_review@v1.0.0")
    await test_session.delete(spec_query)
    with pytest.raises(RuntimeError, match="WORM Violation: CognitionPromptSpec is immutable"):
        await test_session.commit()
    await test_session.rollback()


@pytest.mark.asyncio
async def test_step1_chain_state_update_allowed_but_delete_blocked(test_session: AsyncSession):
    """Chain State 行为验证：允许追加推进更新，但禁止 DELETE 销毁锚点"""
    state = await ensure_genesis_chain_state(test_session)

    # 允许合规更新 (入账后推进链尾)
    state.tail_sequence_id = 1
    state.tail_record_hash = "abc" * 21 + "a"
    await test_session.commit()

    reloaded = await get_current_chain_state(test_session)
    assert reloaded.tail_sequence_id == 1
    assert reloaded.tail_record_hash == "abc" * 21 + "a"

    # 严禁删除链状态记录
    await test_session.delete(reloaded)
    with pytest.raises(RuntimeError, match="WORM Violation: CognitionChainState is permanent"):
        await test_session.commit()
    await test_session.rollback()


@pytest.mark.asyncio
async def test_step1_sequence_id_and_record_hash_uniqueness(test_session: AsyncSession):
    """验证 sequence_id 与 record_hash 唯一性约束"""
    rec1 = CognitionRecord(
        id="cog_unique_01",
        date="2026-09-30",
        stage="POST_CLOSE",
        timestamp=datetime.now(),
        market_event_time="15:00:00",
        observation_window="09:15:00-15:00:00",
        data_snapshot_time=datetime.now(),
        observation_snapshot="{}",
        market_state_snapshot="{}",
        prompt_id="p",
        prompt_version="v",
        prompt_hash="h1",
        model_provider="p",
        model_name="m",
        model_version="v",
        inference_config="{}",
        effective_input_hash="e1",
        rendered_system_prompt="s",
        rendered_user_prompt="u",
        raw_response="r",
        structured_cognition="{}",
        hypothesis_set_hash="hypo1",
        sequence_id=100,
        previous_record_hash="0" * 64,
        payload_hash="pay1",
        record_hash="rec_hash_100",
    )
    test_session.add(rec1)
    await test_session.commit()

    # 尝试插入重复 sequence_id
    rec_dup_seq = CognitionRecord(
        id="cog_unique_02",
        date="2026-09-30",
        stage="POST_CLOSE",
        timestamp=datetime.now(),
        market_event_time="15:00:00",
        observation_window="09:15:00-15:00:00",
        data_snapshot_time=datetime.now(),
        observation_snapshot="{}",
        market_state_snapshot="{}",
        prompt_id="p",
        prompt_version="v",
        prompt_hash="h2",
        model_provider="p",
        model_name="m",
        model_version="v",
        inference_config="{}",
        effective_input_hash="e2",
        rendered_system_prompt="s",
        rendered_user_prompt="u",
        raw_response="r",
        structured_cognition="{}",
        hypothesis_set_hash="hypo2",
        sequence_id=100,  # 重复 sequence_id
        previous_record_hash="rec_hash_100",
        payload_hash="pay2",
        record_hash="rec_hash_101",
    )
    test_session.add(rec_dup_seq)
    with pytest.raises(IntegrityError):
        await test_session.commit()
    await test_session.rollback()
