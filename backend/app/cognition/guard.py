"""
Cognition Admission Guard (Phase 2A.6 轻量准入防守网)
上位依据：最高董事会 Phase 2A.6 准入决议
铁律约束：
1. 仅包含三项硬阻断规则：
   - Rule 1: INVALID 数据拒绝 (Reject if overall_quality == INVALID)
   - Rule 2: 关键事实缺失拒绝 (Reject if critical fact types INDEX_QUOTE or MARKET_BREADTH missing or have fatal status)
   - Rule 3: 时间倒挂拒绝 (Reject if event_time > observed_time + tolerance)
2. 禁止引入评分模型、LLM判断或业务策略逻辑。
"""

import logging
from typing import List, Set
from .observation.contracts import (
    ObservationSnapshot,
    QualityLevel,
    FactType,
    FactStatus,
)

logger = logging.getLogger(__name__)


class CognitionAdmissionError(Exception):
    """认知准入硬阻断违规异常"""
    def __init__(self, rule_name: str, reason: str):
        super().__init__(f"Cognition Admission Violation [{rule_name}]: {reason}")
        self.rule_name = rule_name
        self.reason = reason


class CognitionAdmissionGuard:
    """
    轻量认知准入守卫：入账前前置拦截，防止不可变账本被残损、缺失或倒挂数据永久污染。
    """

    CRITICAL_FACT_TYPES: Set[FactType] = {
        FactType.INDEX_QUOTE,
        FactType.MARKET_BREADTH,
    }
    FATAL_STATUSES: Set[FactStatus] = {
        FactStatus.MISSING,
        FactStatus.TIMEOUT,
        FactStatus.ERROR,
        FactStatus.INCONCLUSIVE,
    }

    @classmethod
    def validate_snapshot(cls, snapshot: ObservationSnapshot) -> None:
        """
        对已装配好的 ObservationSnapshot 执行三项硬阻断校验，不符合直接抛出 CognitionAdmissionError
        """
        # Rule 1: INVALID 数据拒绝
        if snapshot.overall_quality == QualityLevel.INVALID:
            raise CognitionAdmissionError(
                rule_name="REJECT_INVALID_QUALITY",
                reason=f"快照整体质量评定为 INVALID (snapshot_id={snapshot.snapshot_id})，禁止入账污染主账本。"
            )

        # Rule 2: 关键事实缺失拒绝 (指数行情与全市场广度不可或缺)
        present_types = {fact.fact_type for fact in snapshot.fact_items}
        for critical_type in cls.CRITICAL_FACT_TYPES:
            if critical_type not in present_types:
                raise CognitionAdmissionError(
                    rule_name="REJECT_MISSING_CRITICAL_FACT",
                    reason=f"缺失核心关键事实类型 '{critical_type.value}'，禁止入账。"
                )

        # 检查关键事实的状态是否为致命异常 (MISSING / TIMEOUT / ERROR / INCONCLUSIVE)
        for fact in snapshot.fact_items:
            if fact.fact_type in cls.CRITICAL_FACT_TYPES:
                if fact.status in cls.FATAL_STATUSES:
                    raise CognitionAdmissionError(
                        rule_name="REJECT_FATAL_CRITICAL_FACT_STATUS",
                        reason=f"关键事实 '{fact.fact_key}' 状态为 '{fact.status.value}'，不可作为可信推演基准。"
                    )

        # Rule 3: 时间倒挂/未来时钟拒绝
        for fact in snapshot.fact_items:
            if fact.time_context.is_future_event(tolerance_seconds=30.0):
                raise CognitionAdmissionError(
                    rule_name="REJECT_TIME_INVERSION",
                    reason=(
                        f"事实 '{fact.fact_key}' 发生时间倒挂异常：物理事件时间 "
                        f"'{fact.time_context.event_time}' 晚于观测时间 '{fact.time_context.observed_time}'。"
                    )
                )

        logger.debug(
            f"CognitionAdmissionGuard: 快照 {snapshot.snapshot_id} 通过 3 项准入硬规则核验。"
        )
