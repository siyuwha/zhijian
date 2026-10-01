"""
客观事实快照确定性构建器（Observation Snapshot Builder）
上位依据：BOARD-APPROVAL-20260930-STEP3（第六条：强制 Nested Immutability Gate）
核心职责：
- 聚合各 Adapter 产出的原子 FactItem
- 执行强制深度剥离（Deep Detachment），彻底杜绝外部原对象后续篡改引发隐式变异
- 确定性聚合 overall_quality 与 degraded_fields
- 自动计算并固化 JCS snapshot_fingerprint
"""

import copy
from typing import List, Optional
from .contracts import (
    ObservationSnapshot,
    FactItem,
    ObservationWindow,
    CognitionStage,
    SourceCredential,
)
from .clock import DeterministicClock
from .quality import aggregate_overall_quality
from .fingerprint import compute_snapshot_fingerprint


class ObservationSnapshotBuilder:
    """快照装配构建器"""

    @classmethod
    def build(
        cls,
        market_date: str,
        stage: CognitionStage,
        observation_window: ObservationWindow,
        fact_items: List[FactItem],
        source_manifest: List[SourceCredential],
        clock: DeterministicClock,
        snapshot_id: Optional[str] = None,
        schema_version: str = "1.0.0",
    ) -> ObservationSnapshot:
        """
        确定性组装 ObservationSnapshot 并执行嵌套不可变封包
        """
        # 1. 深度复制列表元素并按 UTF-16 字节字典序排序，阻断外部引用污染与乱序漂移
        detached_facts = sorted(
            [copy.deepcopy(f) for f in fact_items],
            key=lambda f: f.fact_key.encode("utf-16-be"),
        )
        detached_manifest = [copy.deepcopy(s) for s in source_manifest]

        # 2. 确定性计算快照质量与降级字段清单
        quality, degraded_fields = aggregate_overall_quality(detached_facts)

        # 3. 构造快照基础对象
        snap_id = snapshot_id or clock.generate_id("obs", f"{market_date}_{stage.value}")
        snapshot = ObservationSnapshot(
            snapshot_id=snap_id,
            schema_version=schema_version,
            market_date=market_date,
            stage=stage,
            observation_window=copy.deepcopy(observation_window),
            snapshot_time=clock.now_iso(),
            overall_quality=quality,
            fact_items=detached_facts,
            degraded_fields=degraded_fields,
            source_manifest=detached_manifest,
        )

        # 4. 计算 RFC 8785 JCS 确定性指纹并固化
        fp = compute_snapshot_fingerprint(snapshot)
        return snapshot.model_copy(update={"snapshot_fingerprint": fp})
