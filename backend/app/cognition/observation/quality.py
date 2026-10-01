"""
确定性快照整体质量聚合器（Deterministic Snapshot Quality Aggregator）
上位依据：
BOARD-APPROVAL-20260930-STEP3（第十条：FactItem.status 与 overall_quality 严格物理分层）
"""

from typing import List, Tuple, Dict, Optional
from .contracts import (
    FactItem,
    FactStatus,
    QualityLevel,
    FactType,
    FactContract,
    DEFAULT_FACT_CONTRACTS,
)


def aggregate_overall_quality(
    fact_items: List[FactItem],
    contracts: Optional[Dict[FactType, FactContract]] = None,
) -> Tuple[QualityLevel, List[str]]:
    """
    根据事实清单与业务契约，确定性计算快照整体质量等级与退化字段列表。
    
    规则：
    1. Critical Fact 阻断：若任何 is_critical=True 的事实项状态为 TIMEOUT / ERROR / MISSING / INCONCLUSIVE，
       整体快照直接判定为 INVALID（一票否决）。
    2. 全量健康：若所有事实项均为 AVAILABLE，或处于契约明确允许的 EMPTY 状态，整体判定为 FULL。
    3. 降级：若存在 STALE 事实项，或主备切换降级，整体判定为 DEGRADED。
    4. 部分可用：无关键事实阻断且无 STALE，但存在非关键事实缺失或非致命异常，整体判定为 PARTIAL。
    """
    active_contracts = contracts or DEFAULT_FACT_CONTRACTS
    degraded_fields: List[str] = []
    
    has_critical_failure = False
    has_stale = False
    has_non_critical_defect = False

    for item in fact_items:
        contract = active_contracts.get(
            item.fact_type,
            FactContract(fact_type=item.fact_type, is_critical=False, allow_empty=False),
        )

        is_defective = False
        if item.status == FactStatus.AVAILABLE:
            pass
        elif item.status == FactStatus.EMPTY:
            if not contract.allow_empty:
                is_defective = True
                has_non_critical_defect = True
        elif item.status == FactStatus.STALE:
            is_defective = True
            has_stale = True
        elif item.status in (FactStatus.TIMEOUT, FactStatus.ERROR, FactStatus.MISSING, FactStatus.INCONCLUSIVE):
            is_defective = True
            if contract.is_critical:
                has_critical_failure = True
            else:
                has_non_critical_defect = True

        if is_defective:
            degraded_fields.append(item.fact_key)

    if has_critical_failure:
        return QualityLevel.INVALID, sorted(degraded_fields)
    elif has_stale:
        return QualityLevel.DEGRADED, sorted(degraded_fields)
    elif has_non_critical_defect:
        return QualityLevel.PARTIAL, sorted(degraded_fields)
    else:
        return QualityLevel.FULL, sorted(degraded_fields)
