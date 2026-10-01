"""
多源冲突检测、分类与确定性裁决策略引擎（Conflict Detection, Classification, and Policy Engine）
上位依据：
1. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》
2. 《开发文档/37-Phase-2A-Step3.3.1-Eligibility-Contract与Conflict-Policy冻结单.md》
核心铁律：
- 严禁按 source priority 静默挑选一个事实并删除另一个事实
- 完整双向保留双方原始源、数值、时间戳与差异度量
- 判定无客观权威依据时，强制裁决为 INCONCLUSIVE
"""

from enum import Enum
from typing import Optional, Dict, Any, Tuple
from pydantic import BaseModel, ConfigDict
from .contracts import (
    FactItem,
    FactStatus,
    ConflictRecord,
)


class ConflictClass(str, Enum):
    """冲突分类标准枚举"""
    NUMERIC_DIVERGENCE = "NUMERIC_DIVERGENCE"        # 数值分歧超阈值
    STATE_CONTRADICTION = "STATE_CONTRADICTION"      # 状态客观矛盾 (如一报正常一报停牌)
    TEMPORAL_INVERSION = "TEMPORAL_INVERSION"        # 时序倒挂异常


class ConflictPolicy(str, Enum):
    """冻结裁决策略枚举"""
    ACCEPT_A = "ACCEPT_A"                            # 采信 Source A
    ACCEPT_B = "ACCEPT_B"                            # 采信 Source B
    ACCEPT_BOTH = "ACCEPT_BOTH"                      # 两方并存互补 (如快讯)
    INCONCLUSIVE = "INCONCLUSIVE"                    # 无法裁决，强制判定为证据不足


class ConflictResolutionResult(BaseModel):
    """冲突裁决结果结构体"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    conflict_detected: bool
    conflict_class: Optional[ConflictClass] = None
    conflict_record: Optional[ConflictRecord] = None
    policy_applied: ConflictPolicy
    resolved_status: FactStatus
    resolved_payload: Optional[Dict[str, Any]] = None
    resolved_source: Optional[str] = None
    warning_message: Optional[str] = None


class ConflictEngine:
    """多源冲突检测、分类与确定性裁决引擎"""

    # 默认数值分歧阈值表
    DEFAULT_PCT_CHANGE_THRESHOLD = 0.30       # 指数或股票涨跌幅分歧 > 0.3%
    DEFAULT_AMOUNT_RATIO_THRESHOLD = 0.05      # 成交金额分歧 > 5%

    @classmethod
    def evaluate(
        cls,
        fact_a: FactItem,
        fact_b: FactItem,
        pct_threshold: float = DEFAULT_PCT_CHANGE_THRESHOLD,
    ) -> ConflictResolutionResult:
        """
        确定性比对来自不同数据源的两个同名事实项
        """
        if fact_a.fact_key != fact_b.fact_key:
            return ConflictResolutionResult(
                conflict_detected=False,
                policy_applied=ConflictPolicy.ACCEPT_BOTH,
                resolved_status=FactStatus.AVAILABLE,
                resolved_payload=fact_a.payload,
                resolved_source=fact_a.source,
            )

        # 1. 检查时序倒挂
        if fact_a.time_context.event_time != fact_b.time_context.event_time:
            # 事件时间不一致但属于同个切片
            record = ConflictRecord(
                fact_key=fact_a.fact_key,
                source_a=fact_a.source,
                value_a=fact_a.payload,
                event_time_a=fact_a.time_context.event_time,
                observed_time_a=fact_a.time_context.observed_time,
                source_b=fact_b.source,
                value_b=fact_b.payload,
                event_time_b=fact_b.time_context.event_time,
                observed_time_b=fact_b.time_context.observed_time,
                difference_metric="temporal_mismatch",
                rule_applied="RULE_CONFLICT_TEMPORAL_INVERSION",
                resolution="INCONCLUSIVE",
            )
            return ConflictResolutionResult(
                conflict_detected=True,
                conflict_class=ConflictClass.TEMPORAL_INVERSION,
                conflict_record=record,
                policy_applied=ConflictPolicy.INCONCLUSIVE,
                resolved_status=FactStatus.INCONCLUSIVE,
                resolved_payload=None,
                warning_message=f"[CONFLICT: {fact_a.fact_key} 多源事件时间倒挂不一致]",
            )

        # 2. 检查状态矛盾 (如一个 AVAILABLE，一个 ERROR/TIMEOUT)
        if fact_a.status != fact_b.status:
            if fact_a.status == FactStatus.AVAILABLE and fact_b.status in (FactStatus.ERROR, FactStatus.TIMEOUT):
                return ConflictResolutionResult(
                    conflict_detected=True,
                    conflict_class=ConflictClass.STATE_CONTRADICTION,
                    policy_applied=ConflictPolicy.ACCEPT_A,
                    resolved_status=FactStatus.AVAILABLE,
                    resolved_payload=fact_a.payload,
                    resolved_source=fact_a.source,
                    warning_message=f"[FAILOVER: {fact_a.fact_key} 源 {fact_b.source} 故障，采信健康源 {fact_a.source}]",
                )
            elif fact_b.status == FactStatus.AVAILABLE and fact_a.status in (FactStatus.ERROR, FactStatus.TIMEOUT):
                return ConflictResolutionResult(
                    conflict_detected=True,
                    conflict_class=ConflictClass.STATE_CONTRADICTION,
                    policy_applied=ConflictPolicy.ACCEPT_B,
                    resolved_status=FactStatus.AVAILABLE,
                    resolved_payload=fact_b.payload,
                    resolved_source=fact_b.source,
                    warning_message=f"[FAILOVER: {fact_a.fact_key} 源 {fact_a.source} 故障，采信健康备源 {fact_b.source}]",
                )

        # 3. 检查数值分歧 (双源均 AVAILABLE 时)
        if fact_a.status == FactStatus.AVAILABLE and fact_b.status == FactStatus.AVAILABLE:
            payload_a = fact_a.payload or {}
            payload_b = fact_b.payload or {}

            # 比较涨跌幅字段 (pct_change 或 change_pct)
            pct_a = payload_a.get("pct_change") if payload_a.get("pct_change") is not None else payload_a.get("change_pct")
            pct_b = payload_b.get("pct_change") if payload_b.get("pct_change") is not None else payload_b.get("change_pct")

            if pct_a is not None and pct_b is not None:
                delta = abs(float(pct_a) - float(pct_b))
                if delta > pct_threshold:
                    # 触发数值分歧冲突
                    diff_metric = f"divergence_{delta:.4f}_pct (exceeds {pct_threshold}%)"
                    record = ConflictRecord(
                        fact_key=fact_a.fact_key,
                        source_a=fact_a.source,
                        value_a=payload_a,
                        event_time_a=fact_a.time_context.event_time,
                        observed_time_a=fact_a.time_context.observed_time,
                        source_b=fact_b.source,
                        value_b=payload_b,
                        event_time_b=fact_b.time_context.event_time,
                        observed_time_b=fact_b.time_context.observed_time,
                        difference_metric=diff_metric,
                        rule_applied="RULE_CONFLICT_INDEX_DIVERGENCE_GT_THRESHOLD",
                        resolution="INCONCLUSIVE",
                    )
                    return ConflictResolutionResult(
                        conflict_detected=True,
                        conflict_class=ConflictClass.NUMERIC_DIVERGENCE,
                        conflict_record=record,
                        policy_applied=ConflictPolicy.INCONCLUSIVE,
                        resolved_status=FactStatus.INCONCLUSIVE,
                        resolved_payload=None, # 双向证据留存于 conflict_record，payload 置空
                        warning_message=f"[CONFLICT UNRESOLVED: {fact_a.fact_key} 数值分歧 {diff_metric}，双向证据已永久存证]",
                    )

        # 4. 无冲突，默认采信
        return ConflictResolutionResult(
            conflict_detected=False,
            policy_applied=ConflictPolicy.ACCEPT_A,
            resolved_status=fact_a.status,
            resolved_payload=fact_a.payload,
            resolved_source=fact_a.source,
        )
