"""
Phase 2A.6 链健康可观察性模块 (Chain Health Observability)
铁律约束：仅提供链状态查询与全链完整性自验，禁止引入任何外部监控系统或中间件。
"""

import logging
from typing import Dict, Any, List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.cognition_v2 import CognitionRecord, CognitionChainState
from .chain_state import DEFAULT_CHAIN_ID, GENESIS_PREVIOUS_HASH
from .hash_chain import verify_chain_integrity

logger = logging.getLogger(__name__)


class ChainHealthService:
    """轻量链健康与可观察性服务 (只读自检)"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_chain_status(self, chain_id: str = DEFAULT_CHAIN_ID) -> Dict[str, Any]:
        """
        查询全局控制锚点状态与账本物理统计
        """
        # 1. 查找链锚点
        state_stmt = select(CognitionChainState).where(CognitionChainState.chain_id == chain_id)
        state = (await self.session.execute(state_stmt)).scalars().first()

        # 2. 统计已写入记录总数
        count_stmt = select(func.count(CognitionRecord.id))
        total_records = (await self.session.execute(count_stmt)).scalar_one()

        # 3. 统计首尾记录信息
        latest_rec_stmt = select(CognitionRecord).order_by(CognitionRecord.sequence_id.desc()).limit(1)
        latest_rec = (await self.session.execute(latest_rec_stmt)).scalars().first()

        if not state:
            return {
                "chain_id": chain_id,
                "is_initialized": False,
                "tail_sequence_id": None,
                "tail_record_hash": None,
                "total_records": total_records,
                "status": "UNINITIALIZED",
            }

        is_synced = True
        if latest_rec:
            is_synced = (
                latest_rec.sequence_id == state.tail_sequence_id and
                latest_rec.record_hash == state.tail_record_hash
            )
        elif state.tail_sequence_id != 0:
            is_synced = False

        return {
            "chain_id": state.chain_id,
            "is_initialized": True,
            "tail_sequence_id": state.tail_sequence_id,
            "tail_record_hash": state.tail_record_hash,
            "total_records": total_records,
            "is_state_synced": is_synced,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
            "status": "HEALTHY" if is_synced else "OUT_OF_SYNC",
        }

    async def audit_chain_health(self, chain_id: str = DEFAULT_CHAIN_ID) -> Dict[str, Any]:
        """
        执行全链自验审计：验证自增单调性、连续哈希闭合、首尾指针一致性
        """
        status = await self.get_chain_status(chain_id)
        if not status["is_initialized"]:
            return {
                "healthy": False,
                "error": "Chain state is uninitialized",
                "details": status,
            }

        # 加载全量记录（升序）
        stmt = select(CognitionRecord).order_by(CognitionRecord.sequence_id.asc())
        records = list((await self.session.execute(stmt)).scalars().all())

        if not records:
            genesis_valid = (
                status["tail_sequence_id"] == 0 and
                status["tail_record_hash"] == GENESIS_PREVIOUS_HASH
            )
            return {
                "healthy": genesis_valid,
                "total_records": 0,
                "error": None if genesis_valid else "Genesis state hash/seq mismatch with empty records",
                "status": status,
            }

        # 运行底层哈希链验真器
        chain_valid, chain_err = verify_chain_integrity(records)
        if not chain_valid:
            return {
                "healthy": False,
                "total_records": len(records),
                "error": f"Hash chain verification failed: {chain_err}",
                "status": status,
            }

        # 检查最新记录与 chain_state 是否完全闭合
        last_rec = records[-1]
        if last_rec.sequence_id != status["tail_sequence_id"] or last_rec.record_hash != status["tail_record_hash"]:
            return {
                "healthy": False,
                "total_records": len(records),
                "error": "Chain state tail pointer diverged from latest record on ledger",
                "status": status,
            }

        return {
            "healthy": True,
            "total_records": len(records),
            "head_sequence_id": records[0].sequence_id,
            "tail_sequence_id": last_rec.sequence_id,
            "tail_record_hash": last_rec.record_hash,
            "error": None,
            "status": status,
        }
