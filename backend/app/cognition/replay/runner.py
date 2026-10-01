"""
Parameterized History Replay Runner (Phase 2B Runtime)
上位依据：
1. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》v1.2.1-FINAL (第6.1节)
2. 《开发文档/49-Phase-2B-实施规划与科学实验对撞引擎技术设计单.md》
"""

import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.cognition.hypothesis.contracts import (
    HypothesisSetProjection,
)
from .contracts import (
    DeterministicLevel,
    ReplayType,
    ReplayRequest,
    DerivedCognitionRecord,
)


class DeterministicClassifier:
    """确定性等级仲裁分类器"""

    @classmethod
    def classify(
        cls,
        parent_raw_response: str,
        parent_hypo_set: Optional[HypothesisSetProjection],
        new_raw_response: str,
        new_hypo_set: HypothesisSetProjection,
        is_offline_fallback: bool = False,
    ) -> DeterministicLevel:
        """
        按照四级刚性标准判定确定性：
        1. OFFLINE_FALLBACK: 显式标记替代模型介入
        2. BIT_EXACT: 原始文本二进制级 SHA-256 100% 相同
        3. SEMANTIC_EQUAL: 文本虽有微小变化，但结构化假说集合哈希 100% 相同
        4. STOCHASTIC_DRIFT: 结构化假说结论发生实质性漂移
        """
        if is_offline_fallback:
            return DeterministicLevel.OFFLINE_FALLBACK

        parent_hash = hashlib.sha256(parent_raw_response.strip().encode("utf-8")).hexdigest()
        new_hash = hashlib.sha256(new_raw_response.strip().encode("utf-8")).hexdigest()

        if parent_hash == new_hash:
            return DeterministicLevel.BIT_EXACT

        if parent_hypo_set and parent_hypo_set.hypothesis_set_hash == new_hypo_set.hypothesis_set_hash:
            return DeterministicLevel.SEMANTIC_EQUAL

        return DeterministicLevel.STOCHASTIC_DRIFT


class ReplayRunner:
    """参数化历史认知重放执行器 (Pure Sandbox)"""

    @classmethod
    def execute_replay(
        cls,
        parent_record: Dict[str, Any],
        request: ReplayRequest,
        simulated_raw_response: Optional[str] = None,
        simulated_hypothesis_set: Optional[HypothesisSetProjection] = None,
    ) -> DerivedCognitionRecord:
        """
        执行历史切片重放推演：
        - 强制保持事实切片控制变量恒定 (直接沿用 parent_record.snapshot_id)
        - 挂载父级血缘 (parent_cognition_id)
        - 严格执行确定性分类
        - 杜绝任何原地覆写与副作用 (WORM 保护)
        """
        parent_cog_id = parent_record.get("cognition_id", "")
        if parent_cog_id != request.parent_cognition_id:
            raise ValueError(
                f"Parent ID mismatch! Given in request: {request.parent_cognition_id}, but record is: {parent_cog_id}"
            )

        snapshot_id = parent_record.get("snapshot_id", "snap_unknown")
        parent_raw_response = parent_record.get("raw_response", "")
        parent_hypo_set: Optional[HypothesisSetProjection] = parent_record.get("hypothesis_set")

        # 若未提供模拟响应（例如在 EXACT_REPLAY 且处于确定性沙箱下），默认取父级数据进行验证
        if simulated_raw_response is None:
            if request.replay_type == ReplayType.EXACT_REPLAY:
                simulated_raw_response = parent_raw_response
            else:
                simulated_raw_response = f"[SHADOW REPLAY RESPONSE with prompt {request.target_prompt_id}]"

        if simulated_hypothesis_set is None:
            if parent_hypo_set is not None:
                simulated_hypothesis_set = parent_hypo_set
            else:
                raise ValueError("No hypothesis set provided for replay derivation!")

        # 判定确定性等级
        det_level = DeterministicClassifier.classify(
            parent_raw_response=parent_raw_response,
            parent_hypo_set=parent_hypo_set,
            new_raw_response=simulated_raw_response,
            new_hypo_set=simulated_hypothesis_set,
            is_offline_fallback=request.is_offline_fallback,
        )

        response_hash = hashlib.sha256(simulated_raw_response.strip().encode("utf-8")).hexdigest()
        derived_cognition_id = f"cog_derived_{request.replay_id}"

        drift_msg = None
        if det_level == DeterministicLevel.STOCHASTIC_DRIFT:
            drift_msg = "推演结论发生离散漂移，结构化假说哈希不匹配"
        elif det_level == DeterministicLevel.OFFLINE_FALLBACK:
            drift_msg = "因历史模型下线，启用离线近似替代模型"

        now_str = datetime.now(timezone.utc).isoformat()

        return DerivedCognitionRecord(
            cognition_id=derived_cognition_id,
            parent_cognition_id=parent_cog_id,
            replay_id=request.replay_id,
            replay_type=request.replay_type,
            deterministic_level=det_level,
            snapshot_id=snapshot_id,
            raw_response=simulated_raw_response,
            response_hash=response_hash,
            hypothesis_set=simulated_hypothesis_set,
            hypothesis_set_hash=simulated_hypothesis_set.hypothesis_set_hash,
            replayed_at=now_str,
            drift_details=drift_msg,
        )
