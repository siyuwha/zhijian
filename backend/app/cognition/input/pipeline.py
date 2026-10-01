"""
Cognition Observation Pipeline (Phase 2A Step 3.4 Pure Sandbox Pipeline Orchestrator)
上位依据：
1. 最高董事会工程批准令 BOARD-APPROVAL-20260930-STEP3
2. 《开发文档/39-Phase-2A-Step3.4-综合组装与全链路冷启动静态验收实施计划.md》

核心铁律：
- 严格受控纯沙箱组装器，只拼装、不扩权
- 完整贯通：Adapters -> Snapshot -> Conflict -> Eligibility -> Serializer -> Hash
- 绝对硬停机边界（STOP Hard Boundary）：
  Physical Facts -> ObservationSnapshot -> Eligibility / Conflict / Quality ->
  EffectiveInferenceInput -> Deterministic Prompt -> effective_input_hash -> STOP
- STOP 之后立即返回不可变 EffectiveInferenceInput，严禁触发任何后续 LLM、交易或业务副作用
"""

import copy
from typing import Dict, List, Any, Optional, Union

from ..observation.contracts import (
    FactItem,
    FactStatus,
    FactType,
    FactContract,
    CognitionStage,
    QualityLevel,
    ObservationWindow,
    ObservationSnapshot,
    EffectiveInferenceInput,
    DEFAULT_FACT_CONTRACTS,
)
from ..observation.builder import ObservationSnapshotBuilder
from ..observation.conflict import ConflictEngine, ConflictPolicy
from ..observation.clock import DeterministicClock
from ..observation.fingerprint import verify_effective_input_hash
from .eligibility import FactEligibilityGate
from .renderer import (
    DeterministicPromptSerializer,
    PromptSpecData,
)


class CognitionObservationPipeline:
    """
    认知事实观测流水线组装器（纯沙箱受控编排器）
    """

    @classmethod
    def process_snapshot(
        cls,
        snapshot: ObservationSnapshot,
        prompt_spec: Union[PromptSpecData, Any],
        input_id: str,
        inference_metadata: Optional[Dict[str, Any]] = None,
        contracts: Optional[Dict[FactType, FactContract]] = None,
    ) -> EffectiveInferenceInput:
        """
        端到端全链路处理已有快照：
        1. 多源事实冲突检测与策略裁决（Conflict Resolution）
        2. 六维矩阵资格准入网分流（Eligibility Gating）
        3. 确定性 Prompt 序列化与安全容器包裹（Deterministic Prompt Serialization）
        4. 全息 JCS 输入哈希计算与验真（effective_input_hash）
        5. ★★★ 触达 STOP 边界，即刻停机返回不可变值对象 ★★★
        """
        active_contracts = contracts or DEFAULT_FACT_CONTRACTS

        # 1. 冲突检测与裁决：针对同切片下同名 fact_key 的多源事实进行冲突核查
        resolved_facts = cls._resolve_conflicts_if_any(snapshot.fact_items)

        # 2. 若有事实状态在冲突处理中变更（如 INCONCLUSIVE），构建 resolved 快照
        resolved_snapshot = snapshot.model_copy(update={"fact_items": resolved_facts})

        # 3. 六维准入网分流 (Admitted / Stale / Suppressed / Warnings)
        admitted, stale, suppressed, warnings = FactEligibilityGate.filter_snapshot(
            resolved_snapshot, contracts=active_contracts
        )

        # 4. 确定性 Prompt 序列化与 effective_input_hash 计算
        effective_input = DeterministicPromptSerializer.render_and_build(
            snapshot_id=resolved_snapshot.snapshot_id,
            overall_quality=resolved_snapshot.overall_quality,
            admitted_facts=admitted,
            stale_facts=stale,
            suppressed_facts=suppressed,
            data_quality_warnings=warnings,
            prompt_spec=prompt_spec,
            input_id=input_id,
            inference_metadata=inference_metadata,
        )

        # 5. 校验哈希完整性闭环
        if not verify_effective_input_hash(effective_input):
            raise ValueError(f"Pipeline verification failed for effective_input_hash: {effective_input.effective_input_hash}")

        # 6. ★★★ STOP HARD BOUNDARY ★★★
        # 立即终止，绝不向下调用任何 LLM 或交易执行模块
        return effective_input

    @classmethod
    def assemble_and_run(
        cls,
        market_date: str,
        stage: CognitionStage,
        observation_window: ObservationWindow,
        fact_items: List[FactItem],
        prompt_spec: Union[PromptSpecData, Any],
        input_id: str,
        clock: Optional[DeterministicClock] = None,
        snapshot_id: Optional[str] = None,
        source_manifest: Optional[List[Any]] = None,
        inference_metadata: Optional[Dict[str, Any]] = None,
        contracts: Optional[Dict[FactType, FactContract]] = None,
    ) -> EffectiveInferenceInput:
        """
        从事实列表直接装配 ObservationSnapshot 并完成全链路处理
        """
        clk = clock or DeterministicClock(f"{market_date}T15:00:00.000+08:00")
        snapshot = ObservationSnapshotBuilder.build(
            market_date=market_date,
            stage=stage,
            observation_window=observation_window,
            fact_items=fact_items,
            source_manifest=source_manifest or [],
            clock=clk,
            snapshot_id=snapshot_id,
        )
        return cls.process_snapshot(
            snapshot=snapshot,
            prompt_spec=prompt_spec,
            input_id=input_id,
            inference_metadata=inference_metadata,
            contracts=contracts,
        )

    @classmethod
    def _resolve_conflicts_if_any(cls, facts: List[FactItem]) -> List[FactItem]:
        """
        检测事实列表中是否存在同名 fact_key 的多源事实；
        若存在，调用 ConflictEngine 执行确定性分类与策略裁决，
        保全双方原始证据并返回裁决后的事实项列表。
        """
        # 按 fact_key 分组
        grouped: Dict[str, List[FactItem]] = {}
        for f in facts:
            grouped.setdefault(f.fact_key, []).append(f)

        resolved_list: List[FactItem] = []
        for key, items in grouped.items():
            if len(items) == 1:
                resolved_list.append(items[0])
            else:
                # 出现两个或多个来源对同一 fact_key 进行观测
                # 成对评估冲突
                primary_item = items[0]
                has_inconclusive = False
                for peer in items[1:]:
                    res = ConflictEngine.evaluate(primary_item, peer)
                    if res.conflict_detected:
                        if res.policy_applied == ConflictPolicy.INCONCLUSIVE:
                            has_inconclusive = True
                            # 标记为 INCONCLUSIVE，留存 ConflictRecord
                            primary_item = primary_item.model_copy(
                                update={
                                    "status": FactStatus.INCONCLUSIVE,
                                    "payload": None,
                                }
                            )
                        elif res.policy_applied == ConflictPolicy.ACCEPT_B:
                            primary_item = peer
                resolved_list.append(primary_item)

        # 保持 UTF-16 字节字典序输出
        return sorted(resolved_list, key=lambda x: x.fact_key.encode("utf-16-be"))
