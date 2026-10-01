"""
基础事实抽取适配器抽象（Base Fact Adapter）
上位依据：BOARD-APPROVAL-20260930-STEP3（第三条：Adapter 只转换、不决策）
核心铁律：
1. 强制深度剥离（Deep Detachment）：防止外部调用方后续修改原始 dict 时污染已经生成的不可变 FactItem。
2. 零填充防护（No Zero-Filling）：当上游数据为 None 或状态为 TIMEOUT/MISSING/ERROR 时，绝不用 0 填充。
"""

import copy
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from ..contracts import (
    FactItem,
    FactType,
    FactStatus,
    Freshness,
    FourDimensionalTime,
    Provenance,
)
from ..clock import DeterministicClock
from ..fingerprint import compute_fact_fingerprint


class BaseFactAdapter(ABC):
    """
    事实抽取适配器基类
    职责边界：
    - 数据清洗与提取、格式解包、时间戳对齐、字段映射、指纹计算
    - 绝不擅作 Eligibility 准入决策
    - 绝不擅作 Conflict Resolution 冲突裁决
    - 绝不伪造虚假默认值
    """

    @staticmethod
    def deep_detach(data: Any) -> Any:
        """
        深度解耦复制：彻底阻断外部引用对内部事实的二次篡改
        """
        if data is None:
            return None
        return copy.deepcopy(data)

    def create_fact_item(
        self,
        fact_key: str,
        fact_type: FactType,
        time_context: FourDimensionalTime,
        status: FactStatus,
        freshness: Freshness,
        source: str,
        source_record_id: str,
        payload: Optional[Dict[str, Any]],
        provenance: Provenance,
        clock: DeterministicClock,
    ) -> FactItem:
        """
        确定性构建不可变 FactItem 并自动绑定 RFC 8785 JCS 指纹
        """
        detached_payload = self.deep_detach(payload)
        detached_prov = copy.deepcopy(provenance)

        # 零填充防伪铁律：非可用状态下若无有效数据，强制为 None 或纯空结构，严禁假0注入
        if status in (FactStatus.TIMEOUT, FactStatus.ERROR, FactStatus.MISSING) and not detached_payload:
            detached_payload = None

        fact_id = clock.generate_id("fact", fact_key)
        item = FactItem(
            fact_id=fact_id,
            fact_key=fact_key,
            fact_type=fact_type,
            time_context=time_context,
            status=status,
            freshness=freshness,
            source=source,
            source_record_id=str(source_record_id),
            payload=detached_payload,
            provenance=detached_prov,
        )
        fp = compute_fact_fingerprint(item)
        return item.model_copy(update={"fact_fingerprint": fp})

    @abstractmethod
    def extract_facts(
        self,
        raw_data: Any,
        clock: DeterministicClock,
        trace_id: str,
        **kwargs: Any,
    ) -> List[FactItem]:
        """从原始数据源中抽取规范化事实项"""
        pass
