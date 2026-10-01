"""
Cognition Phase 2A 账本链控制状态与创世初始化服务
依据：《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》(v1.2.1-FINAL-CLOSURE)
     《开发文档/29-Cognition-Phase2A架构与数据契约冻结决议与实施约束单.md》

核心职责：
1. 确保 cognition_chain_state 创世控制记录单行就绪 (tail_sequence_id=0, tail_record_hash="0"*64)
2. 提供防 Genesis Race 的排他串行化控制依据
"""

import logging
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.cognition_v2 import CognitionChainState

logger = logging.getLogger(__name__)

DEFAULT_CHAIN_ID = "MAIN_LEDGER"
GENESIS_PREVIOUS_HASH = "0" * 64


async def ensure_genesis_chain_state(
    session: AsyncSession,
    chain_id: str = DEFAULT_CHAIN_ID
) -> CognitionChainState:
    """
    幂等初始化创世控制行：
    如果 chain_id 不存在，则初始化 sequence_id=0, tail_record_hash="0"*64。
    如果已存在，则保持现状不变。
    """
    stmt = select(CognitionChainState).where(CognitionChainState.chain_id == chain_id)
    res = await session.execute(stmt)
    state = res.scalars().first()

    if state is None:
        state = CognitionChainState(
            chain_id=chain_id,
            tail_sequence_id=0,
            tail_record_hash=GENESIS_PREVIOUS_HASH,
        )
        session.add(state)
        await session.commit()
        await session.refresh(state)
        logger.info(f"Cognition Phase 2A 创世控制记录已初始化: chain_id={chain_id}, seq=0, hash={'0'*16}...")
    return state


async def get_current_chain_state(
    session: AsyncSession,
    chain_id: str = DEFAULT_CHAIN_ID
) -> Optional[CognitionChainState]:
    """获取当前账本链尾状态"""
    stmt = select(CognitionChainState).where(CognitionChainState.chain_id == chain_id)
    res = await session.execute(stmt)
    return res.scalars().first()
