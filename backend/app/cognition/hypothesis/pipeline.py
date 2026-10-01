"""
Dual-Timestamp Validation Pipeline (Phase 2A Step 5 Runtime)
上位依据：
1. 《开发文档/45-Phase-2A-Step5-收窄AST解释执行器与事后证伪闭环实施规划.md》
2. 四维时间契约：严格校验 T_realization >= T_decision，防范时空倒流与未来函数
3. 密码学全血缘溯源与 STOP 硬边界
"""

from typing import Dict, List, Any, Optional
from datetime import datetime

from .contracts import (
    HypothesisSetProjection,
    MarketHypothesisDefinition,
)
from .fingerprint import (
    verify_hypothesis_set_hash,
    verify_hypothesis_hash,
)
from .falsification import (
    FalsificationEngine,
    HypothesisAdjudicationResult,
)
from .ledger import (
    CognitionValidationRecord,
)


class TimeContinuityViolationError(ValueError):
    """四维时间时序倒流异常 (T_realization < T_decision)"""
    pass


class HypothesisTamperError(ValueError):
    """假说定义或哈希被篡改异常"""
    pass


class DualTimestampValidationPipeline:
    """双时点真实截面对撞与证伪闭环流水线"""

    @classmethod
    def validate_hypothesis_set(
        cls,
        hypothesis_set: HypothesisSetProjection,
        realization_snapshot: Dict[str, Any],
        realization_snapshot_id: str,
        decision_time: str,
        realization_time: str,
    ) -> List[CognitionValidationRecord]:
        """
        执行双时点假说验证全流程：
        1. 四维时间校验: T_realization >= T_decision，杜绝未来函数；
        2. 假说完整性校验: 验证 hypothesis_set_hash 与各项 hypothesis_hash 未被篡改；
        3. 证伪优先裁决: 针对各项假说执行 FalsificationEngine；
        4. 组装只追加验证记录: 注入密码学全血缘指纹；
        5. 执行 STOP 硬边界: 仅返回不可变值对象，绝无外部调用与副作用。
        """
        # 1. 四维时间时序校验 (Time-Continuity Validation)
        cls._validate_time_continuity(decision_time, realization_time)

        # 2. 假说定义防篡改校验 (Cryptographic Hash Integrity)
        if not verify_hypothesis_set_hash(hypothesis_set):
            raise HypothesisTamperError(
                f"HypothesisSet hash mismatch! Given: {hypothesis_set.hypothesis_set_hash}"
            )

        for hypo in hypothesis_set.hypotheses:
            if not verify_hypothesis_hash(hypo):
                raise HypothesisTamperError(
                    f"Hypothesis hash mismatch for '{hypo.hypothesis_id}'! Given: {hypo.hypothesis_hash}"
                )

        # 3. 逐项假说执行真实截面对撞 (Execution & Adjudication)
        validation_records: List[CognitionValidationRecord] = []

        for hypo in hypothesis_set.hypotheses:
            adjudication = FalsificationEngine.adjudicate(hypo, realization_snapshot)

            # 序列化断言明细用于存证
            assertion_results_serialized = []
            for r in adjudication.invalidation_results:
                assertion_results_serialized.append({
                    "assertion_id": r.assertion_id,
                    "type": "INVALIDATION",
                    "outcome": r.outcome.value,
                    "actual_value": r.actual_value,
                    "target_value": r.target_value,
                    "matched_count": r.matched_count,
                    "details": r.details,
                })
            for r in adjudication.expected_results:
                assertion_results_serialized.append({
                    "assertion_id": r.assertion_id,
                    "type": "EXPECTED",
                    "outcome": r.outcome.value,
                    "actual_value": r.actual_value,
                    "target_value": r.target_value,
                    "matched_count": r.matched_count,
                    "details": r.details,
                })

            # 溯源元数据
            provenance = {
                "snapshot_id": realization_snapshot_id,
                "snapshot_status": realization_snapshot.get("status", "AVAILABLE"),
                "adjudication_details": adjudication.details,
            }

            validation_id = f"val_{hypo.hypothesis_id}_{realization_snapshot_id}"
            partial_dict = {
                "actual_metrics_summary": adjudication.actual_metrics_summary,
                "assertion_results": assertion_results_serialized,
                "cognition_record_id": hypo.cognition_id,
                "decision_time": decision_time,
                "falsification_triggered": adjudication.falsification_triggered,
                "hypothesis_hash": hypo.hypothesis_hash,
                "hypothesis_id": hypo.hypothesis_id,
                "hypothesis_set_hash": hypothesis_set.hypothesis_set_hash,
                "outcome": adjudication.outcome.value,
                "provenance_trace": provenance,
                "realization_time": realization_time,
                "validation_id": validation_id,
                "verification_snapshot_id": realization_snapshot_id,
                "verified_at": realization_time,
            }

            rec_hash = CognitionValidationRecord.compute_record_hash(partial_dict)

            record = CognitionValidationRecord(
                validation_id=validation_id,
                cognition_record_id=hypo.cognition_id,
                hypothesis_set_hash=hypothesis_set.hypothesis_set_hash,
                hypothesis_hash=hypo.hypothesis_hash,
                hypothesis_id=hypo.hypothesis_id,
                verification_snapshot_id=realization_snapshot_id,
                decision_time=decision_time,
                realization_time=realization_time,
                outcome=adjudication.outcome,
                falsification_triggered=adjudication.falsification_triggered,
                actual_metrics_summary=adjudication.actual_metrics_summary,
                assertion_results=assertion_results_serialized,
                provenance_trace=provenance,
                verified_at=realization_time,
                validation_record_hash=rec_hash,
            )
            validation_records.append(record)

        # 4. STOP 边界保证：直接返回不可变实体清单
        return validation_records

    @classmethod
    def _validate_time_continuity(cls, decision_time: str, realization_time: str) -> None:
        """校验决策时点与到达时点的前后因果关系"""
        try:
            # 兼容 ISO 8601 或普通字符串比较
            dt_dec = datetime.fromisoformat(decision_time.replace("Z", "+00:00"))
            dt_real = datetime.fromisoformat(realization_time.replace("Z", "+00:00"))
            if dt_real < dt_dec:
                raise TimeContinuityViolationError(
                    f"时序倒流违规: realization_time ({realization_time}) 早于 decision_time ({decision_time})！"
                )
        except ValueError as e:
            # 若不是标准 ISO，则执行字符串比较
            if "时序倒流违规" in str(e):
                raise
            if realization_time < decision_time:
                raise TimeContinuityViolationError(
                    f"时序倒流违规: realization_time ({realization_time}) < decision_time ({decision_time})！"
                )
