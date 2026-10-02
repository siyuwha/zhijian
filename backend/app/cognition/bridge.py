"""
Minimal Cognition Bridge (最小认知桥梁服务)
核心职责：
- 将 M1 收盘复盘生成的物理事实 (MarketDailySnapshot / DailyReview) 适配并构建为不可变 ObservationSnapshot
- 驱动 Phase 2A 核心链式账本，生成具备全要素自包含与抗雪崩哈希链的 CognitionRecord
- 更新 cognition_chain_state 链条锚点 (单调连续 Sequence，前驱哈希链式闭合)
- 严守 Zero External LLM 铁律 (采用确定性规则引擎与启发式 Prompt 规范)
- 严守 WORM 铁律 (只允许单调追加 INSERT，零 UPDATE/DELETE)
"""

import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Union
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.cognition_v2 import CognitionRecord, CognitionChainState
from ..models.report import DailyReview
from ..models.market import MarketDailySnapshot
from .chain_state import DEFAULT_CHAIN_ID, GENESIS_PREVIOUS_HASH, ensure_genesis_chain_state
from .hash_chain import compute_payload_hash, compute_record_hash
from .jcs import hash_jcs
from .clock import DeterministicClock
from .observation.contracts import (
    ObservationSnapshot,
    ObservationWindow,
    CognitionStage,
    SourceCredential,
)
from .observation.adapters.m1_adapter import M1ReviewFactAdapter
from .observation.builder import ObservationSnapshotBuilder

logger = logging.getLogger(__name__)

# 预设的确定性复盘 Prompt 规范指纹 (Zero External LLM 模式)
BRIDGE_PROMPT_ID = "M1_EOD_SYNTHESIS"
BRIDGE_PROMPT_VERSION = "v1.0.0"
BRIDGE_PROMPT_SYSTEM = "Deterministic market state synthesis engine based on multi-dimensional facts."
BRIDGE_PROMPT_HASH = hash_jcs({"id": BRIDGE_PROMPT_ID, "v": BRIDGE_PROMPT_VERSION, "sys": BRIDGE_PROMPT_SYSTEM})
EMPTY_HYPOTHESIS_HASH = "0" * 64


class CognitionBridge:
    """M1 收盘复盘 -> Phase 2A 认知账本桥接器"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.adapter = M1ReviewFactAdapter()

    async def record_daily_review(
        self,
        market_date: str,
        snapshot: MarketDailySnapshot,
        review: Optional[DailyReview] = None,
        clock: Optional[DeterministicClock] = None,
    ) -> CognitionRecord:
        """
        将单日收盘复盘物理事实接入 Phase 2A 不可变认知账本
        """
        # 1. 幂等性检查：同日 POST_CLOSE 阶段记录仅能生成一次，防止分叉或重复入账
        existing_stmt = select(CognitionRecord).where(
            CognitionRecord.date == market_date,
            CognitionRecord.stage == "POST_CLOSE",
            CognitionRecord.replay_type == "ORIGINAL"
        )
        existing_rec = (await self.session.execute(existing_stmt)).scalars().first()
        if existing_rec:
            logger.info(f"CognitionBridge: {market_date} POST_CLOSE 认知账本记录已存在 (id={existing_rec.id})，幂等跳过。")
            return existing_rec

        # 2. 准备确定性时钟
        now = datetime.now()
        clk = clock or DeterministicClock.frozen(now)

        # 3. 抽取事实并装配不可变 ObservationSnapshot
        trace_id = f"bridge_m1_{market_date.replace('-', '')}"
        facts = self.adapter.extract_facts(
            raw_data=snapshot,
            clock=clk,
            trace_id=trace_id,
            market_date=market_date
        )

        obs_window = ObservationWindow(
            window_start=f"{market_date}T09:15:00.000+08:00",
            window_end=f"{market_date}T15:00:00.000+08:00"
        )

        credentials = [
            SourceCredential(
                source_name="market_daily_snapshot:EOD_CLOSE",
                fetch_status="SUCCESS",
                latency_ms=0.0,
                records_count=len(facts)
            )
        ]

        obs_snapshot = ObservationSnapshotBuilder.build(
            market_date=market_date,
            stage=CognitionStage.POST_CLOSE,
            observation_window=obs_window,
            fact_items=facts,
            source_manifest=credentials,
            clock=clk
        )

        obs_json = obs_snapshot.model_dump_json()

        # 4. 抽取市场状态快照
        state_dict: Dict[str, Any] = {}
        if snapshot.market_state_snapshot:
            try:
                state_dict = json.loads(snapshot.market_state_snapshot)
            except Exception:
                state_dict = {"raw": snapshot.market_state_snapshot}
        elif review and review.report_content:
            try:
                rep_json = json.loads(review.report_content)
                state_dict = rep_json.get("market_state", {})
            except Exception:
                pass
        market_state_json = json.dumps(state_dict, ensure_ascii=False)

        # 5. 构建结构化认知与保全输入 (Zero LLM / 规则启发式输出)
        raw_text = (
            (review.report_content if review else None) or
            snapshot.market_state_snapshot or
            f"Market state synthesized for {market_date}"
        )

        structured_cog = {
            "thesis": f"Post-close synthesis for {market_date}",
            "market_state": state_dict.get("label", "BALANCED"),
            "composite_score": state_dict.get("composite_score", 50.0),
            "quality": obs_snapshot.overall_quality.value,
            "synthesized_by": "HEURISTIC_RULE_SYNTHESIZER",
        }

        user_prompt = f"Synthesize deterministic market review for date: {market_date}"
        effective_input_hash = hash_jcs({
            "sys": BRIDGE_PROMPT_SYSTEM,
            "usr": user_prompt,
            "obs_fp": obs_snapshot.snapshot_fingerprint
        })

        inference_cfg = {"mode": "deterministic_heuristic", "temperature": 0.0}

        # 6. 获取或初始化链状态 (排他串行单行控制)
        chain_state = await ensure_genesis_chain_state(self.session, DEFAULT_CHAIN_ID)
        
        # 读取链尾状态
        tail_stmt = select(CognitionChainState).where(
            CognitionChainState.chain_id == DEFAULT_CHAIN_ID
        ).with_for_update()
        curr_state = (await self.session.execute(tail_stmt)).scalar_one()

        new_sequence_id = curr_state.tail_sequence_id + 1
        previous_hash = curr_state.tail_record_hash

        # 7. 计算全要素 Payload Hash 与链式 Record Hash
        payload_hash = compute_payload_hash(
            date=market_date,
            stage="POST_CLOSE",
            market_event_time="15:00:00",
            observation_window="09:15:00-15:00:00",
            observation_snapshot=obs_json,
            market_state_snapshot=market_state_json,
            prompt_id=BRIDGE_PROMPT_ID,
            prompt_version=BRIDGE_PROMPT_VERSION,
            prompt_hash=BRIDGE_PROMPT_HASH,
            model_provider="HEURISTIC_RULE",
            model_name="RULE_BASED_D1_D6_ENGINE",
            model_version="v1.0.0",
            inference_config=inference_cfg,
            effective_input_hash=effective_input_hash,
            rendered_system_prompt=BRIDGE_PROMPT_SYSTEM,
            rendered_user_prompt=user_prompt,
            raw_response=raw_text,
            structured_cognition=structured_cog,
            hypothesis_set_hash=EMPTY_HYPOTHESIS_HASH,
        )

        record_hash = compute_record_hash(
            sequence_id=new_sequence_id,
            previous_record_hash=previous_hash,
            payload_hash=payload_hash,
        )

        # 8. 构造并单调追加物理 CognitionRecord 实体
        rec_id = f"cog_{market_date.replace('-', '')}_POST_CLOSE_{new_sequence_id:04d}"
        new_record = CognitionRecord(
            id=rec_id,
            date=market_date,
            stage="POST_CLOSE",
            timestamp=now,
            market_event_time="15:00:00",
            observation_window="09:15:00-15:00:00",
            data_snapshot_time=now,
            verification_execute_time=None,
            observation_snapshot=obs_json,
            market_state_snapshot=market_state_json,
            prompt_id=BRIDGE_PROMPT_ID,
            prompt_version=BRIDGE_PROMPT_VERSION,
            prompt_hash=BRIDGE_PROMPT_HASH,
            model_provider="HEURISTIC_RULE",
            model_name="RULE_BASED_D1_D6_ENGINE",
            model_version="v1.0.0",
            inference_config=json.dumps(inference_cfg),
            effective_input_hash=effective_input_hash,
            rendered_system_prompt=BRIDGE_PROMPT_SYSTEM,
            rendered_user_prompt=user_prompt,
            raw_response=raw_text,
            response_tokens=len(raw_text.split()),
            latency_ms=10,
            structured_cognition=json.dumps(structured_cog, ensure_ascii=False),
            hypothesis_set_hash=EMPTY_HYPOTHESIS_HASH,
            sequence_id=new_sequence_id,
            previous_record_hash=previous_hash,
            payload_hash=payload_hash,
            record_hash=record_hash,
            parent_cognition_id=None,
            replay_type="ORIGINAL",
            deterministic_level="BIT_EXACT"
        )

        self.session.add(new_record)

        # 9. 推进链状态全局控制指针
        curr_state.tail_sequence_id = new_sequence_id
        curr_state.tail_record_hash = record_hash
        curr_state.updated_at = now

        await self.session.commit()
        await self.session.refresh(new_record)

        logger.info(
            f"CognitionBridge: 成功写入收盘不可变认知账本! "
            f"id={rec_id}, seq={new_sequence_id}, hash={record_hash[:16]}..."
        )
        return new_record
