"""
事实资格准入网与法定六维矩阵求值器（Fact Eligibility Gate & Matrix Evaluator）
上位依据：
1. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》
2. 《开发文档/37-Phase-2A-Step3.3.1-Eligibility-Contract与Conflict-Policy冻结单.md》
核心铁律：
- 严格执行准入矩阵，禁止“有值就用”
- STALE 事实严格隔离，绝不在 admitted_facts 中出现
- TIMEOUT / MISSING / ERROR 严禁零填充
- MISSING ≠ FALSE，INCONCLUSIVE ≠ FALSE
"""

from enum import Enum
from typing import Dict, List, Any, Optional, Tuple
from pydantic import BaseModel, ConfigDict
from ..observation.contracts import (
    FactItem,
    FactStatus,
    Freshness,
    FactType,
    FactContract,
    ObservationSnapshot,
    DEFAULT_FACT_CONTRACTS,
)


class EligibilityOutcome(str, Enum):
    """事实资格审查结果枚举"""
    ADMITTED = "ADMITTED"                        # 审查通过，准入有效推理事实集 (admitted_facts)
    STALE_RESTRICTED = "STALE_RESTRICTED"        # 陈旧数据，严格隔离至警示专区 (stale_facts)
    SUPPRESSED_DEFECTIVE = "SUPPRESSED_DEFECTIVE"# 故障或破损数据，强制排除 (suppressed_facts)
    SUPPRESSED_CONFLICT = "SUPPRESSED_CONFLICT"  # 多源冲突未决，强制排除 (suppressed_facts)
    INCONCLUSIVE_MISSING = "INCONCLUSIVE_MISSING"# 关键事实缺失，强制判定为证据不足 (suppressed_facts)


class EligibilityDecision(BaseModel):
    """单项事实准入决策"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_key: str
    outcome: EligibilityOutcome
    target_partition: str                       # "admitted", "stale", "suppressed"
    payload_to_inject: Optional[Dict[str, Any]] = None
    quality_warning: Optional[str] = None
    reason: str


class FactEligibilityGate:
    """法定事实准入网"""

    @classmethod
    def evaluate_fact(
        cls,
        fact: FactItem,
        contract: Optional[FactContract] = None,
    ) -> EligibilityDecision:
        """
        根据六维准入矩阵，对单项事实进行确定性资格审查
        """
        ct = contract or DEFAULT_FACT_CONTRACTS.get(
            fact.fact_type,
            FactContract(fact_type=fact.fact_type, is_critical=False, allow_empty=False),
        )

        # 1. 冲突未决事实 (INCONCLUSIVE)
        if fact.status == FactStatus.INCONCLUSIVE:
            return EligibilityDecision(
                fact_key=fact.fact_key,
                outcome=EligibilityOutcome.SUPPRESSED_CONFLICT,
                target_partition="suppressed",
                payload_to_inject=None,
                quality_warning=f"[CONFLICT UNRESOLVED: {fact.fact_key} 多源分歧超阈值，双向证据已永久存证，强制判定证据不足]",
                reason="MULTI_SOURCE_CONFLICT_INCONCLUSIVE",
            )

        # 2. 网络硬超时事实 (TIMEOUT -> 零填充防伪)
        if fact.status == FactStatus.TIMEOUT:
            return EligibilityDecision(
                fact_key=fact.fact_key,
                outcome=EligibilityOutcome.SUPPRESSED_DEFECTIVE,
                target_partition="suppressed",
                payload_to_inject=None, # TIMEOUT != 0，强制为 None
                quality_warning=f"[DATA TIMEOUT: {fact.fact_key} 网络物理超时，已强行剥离，payload 为 null]",
                reason="PHYSICAL_TIMEOUT",
            )

        # 3. 通道错误与数据解析损坏 (ERROR)
        if fact.status == FactStatus.ERROR:
            return EligibilityDecision(
                fact_key=fact.fact_key,
                outcome=EligibilityOutcome.SUPPRESSED_DEFECTIVE,
                target_partition="suppressed",
                payload_to_inject=None,
                quality_warning=f"[SOURCE ERROR: {fact.fact_key} 数据源通道报错或数据格式损坏]",
                reason="SOURCE_MALFORMED_OR_ERROR",
            )

        # 4. 关键事实缺失 (MISSING -> Missing != False, Missing != 0)
        if fact.status == FactStatus.MISSING:
            return EligibilityDecision(
                fact_key=fact.fact_key,
                outcome=EligibilityOutcome.INCONCLUSIVE_MISSING,
                target_partition="suppressed",
                payload_to_inject=None,
                quality_warning=f"[DATA DEFICIENCY: {fact.fact_key} 核心事实缺失，严禁进行方向性推断]",
                reason="FACT_MISSING_PREVENTS_ASSUMPTION",
            )

        # 5. 空事实 (EMPTY -> Fact-type-specific semantics)
        if fact.status == FactStatus.EMPTY:
            if ct.allow_empty and ct.empty_semantic in ("COUNT_ZERO", "EMPTY_SET"):
                # 契约允许的空事实（如零涨停）
                return EligibilityDecision(
                    fact_key=fact.fact_key,
                    outcome=EligibilityOutcome.ADMITTED,
                    target_partition="admitted",
                    payload_to_inject=fact.payload or {},
                    quality_warning=None,
                    reason=f"LEGITIMATE_EMPTY_{ct.empty_semantic}",
                )
            else:
                return EligibilityDecision(
                    fact_key=fact.fact_key,
                    outcome=EligibilityOutcome.SUPPRESSED_DEFECTIVE,
                    target_partition="suppressed",
                    payload_to_inject=None,
                    quality_warning=f"[EMPTY DISALLOWED: {fact.fact_key} 属于非空数值指标，无数据不具备准入资格]",
                    reason="EMPTY_DISALLOWED_FOR_FACT_TYPE",
                )

        # 6. 陈旧事实 (STALE -> STALE != admitted_facts)
        if fact.status == FactStatus.STALE or fact.freshness == Freshness.STALE:
            if ct.allow_stale_reference:
                # 仅在显式声明允许陈旧参考时，进入独立的 stale_facts 专区
                return EligibilityDecision(
                    fact_key=fact.fact_key,
                    outcome=EligibilityOutcome.STALE_RESTRICTED,
                    target_partition="stale",
                    payload_to_inject=fact.payload,
                    quality_warning=f"[STALE FACT: {fact.fact_key} 来源为本地历史缓存/非当时数据，仅供基准参考]",
                    reason="STALE_REFERENCE_ADMITTED_TO_RESTRICTED_ZONE",
                )
            else:
                return EligibilityDecision(
                    fact_key=fact.fact_key,
                    outcome=EligibilityOutcome.SUPPRESSED_DEFECTIVE,
                    target_partition="suppressed",
                    payload_to_inject=None,
                    quality_warning=f"[EXCLUDED STALE: {fact.fact_key} 契约禁止陈旧参考，已强行剥离]",
                    reason="STALE_NOT_ALLOWED_BY_CONTRACT",
                )

        # 7. 正常可用事实 (AVAILABLE)
        if fact.status == FactStatus.AVAILABLE:
            if fact.freshness in (Freshness.REALTIME, Freshness.DELAYED):
                return EligibilityDecision(
                    fact_key=fact.fact_key,
                    outcome=EligibilityOutcome.ADMITTED,
                    target_partition="admitted",
                    payload_to_inject=fact.payload,
                    quality_warning=None,
                    reason="AVAILABLE_AND_FRESH",
                )

        # 8. 默认兜底：凡未通过上述显式资格审查的，一律排除
        return EligibilityDecision(
            fact_key=fact.fact_key,
            outcome=EligibilityOutcome.SUPPRESSED_DEFECTIVE,
            target_partition="suppressed",
            payload_to_inject=None,
            quality_warning=f"[UNQUALIFIED: {fact.fact_key} 未满足任何准入准则]",
            reason="UNMET_ELIGIBILITY_CRITERIA",
        )

    @classmethod
    def filter_snapshot(
        cls,
        snapshot: ObservationSnapshot,
        contracts: Optional[Dict[FactType, FactContract]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]], List[str]]:
        """
        全量审查 ObservationSnapshot，精确分流至：
        - admitted_facts: 准入事实字典 (按 UTF-16 字典序排列)
        - stale_facts: 陈旧参考事实专区
        - suppressed_facts: 被排除的事实项及其排除原因
        - data_quality_warnings: 质量警示清单
        """
        active_contracts = contracts or DEFAULT_FACT_CONTRACTS
        admitted: Dict[str, Any] = {}
        stale: Dict[str, Any] = {}
        suppressed: List[Dict[str, Any]] = []
        warnings: List[str] = []

        # 严格按 fact_key 的 UTF-16 字节序遍历
        sorted_facts = sorted(snapshot.fact_items, key=lambda f: f.fact_key.encode("utf-16-be"))

        for f in sorted_facts:
            decision = cls.evaluate_fact(f, active_contracts.get(f.fact_type))

            if decision.quality_warning:
                warnings.append(decision.quality_warning)

            if decision.target_partition == "admitted":
                admitted[f.fact_key] = decision.payload_to_inject
            elif decision.target_partition == "stale":
                stale[f.fact_key] = decision.payload_to_inject
            else:
                suppressed.append({
                    "fact_key": f.fact_key,
                    "status": f.status.value,
                    "rejection_rule": decision.reason,
                    "outcome": decision.outcome.value,
                })

        return admitted, stale, suppressed, sorted(warnings)
