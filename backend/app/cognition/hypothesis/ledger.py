"""
Append-Only Validation Ledger & State Machine (Phase 2A Step 5 Runtime)
上位依据：
1. 《开发文档/45-Phase-2A-Step5-收窄AST解释执行器与事后证伪闭环实施规划.md》
2. 《开发文档/43-Phase-2A-Step4与Step5职责边界澄清与架构裁决方案.md》
3. WORM 存储不变量：绝对禁止对 cognition_record 执行 UPDATE，验证记录只追加写入独立账本
"""

import hashlib
import json
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from .contracts import (
    HypothesisOutcome,
)


class CognitionValidationRecord(BaseModel):
    """事后验证只追加账本记录不可变值对象 (Append-Only Validation Record)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    validation_id: str
    cognition_record_id: str                   # FK -> 指向父级 CognitionRecord
    hypothesis_set_hash: str                   # 校验时刻事前冻结的集合根指纹
    hypothesis_hash: str                       # FK -> 指向具体的假说指纹
    hypothesis_id: str
    verification_snapshot_id: str              # 关联的真实市场截面快照 ID
    decision_time: str                         # 事前决策时点 (T_decision)
    realization_time: str                      # 事后到达时点 (T_realization)
    outcome: HypothesisOutcome
    falsification_triggered: bool = False
    actual_metrics_summary: Dict[str, Any] = Field(default_factory=dict)
    assertion_results: List[Dict[str, Any]] = Field(default_factory=list)
    provenance_trace: Dict[str, Any] = Field(default_factory=dict)
    verified_at: str                           # 验证执行时间戳
    validation_record_hash: str = ""           # 本验证记录自身的 JCS SHA-256 防篡改指纹

    def to_canonical_dict(self) -> Dict[str, Any]:
        """构建 RFC 8785 JCS 规范载荷（排除自身哈希字段）"""
        return {
            "actual_metrics_summary": self.actual_metrics_summary,
            "assertion_results": self.assertion_results,
            "cognition_record_id": self.cognition_record_id,
            "decision_time": self.decision_time,
            "falsification_triggered": self.falsification_triggered,
            "hypothesis_hash": self.hypothesis_hash,
            "hypothesis_id": self.hypothesis_id,
            "hypothesis_set_hash": self.hypothesis_set_hash,
            "outcome": self.outcome.value,
            "provenance_trace": self.provenance_trace,
            "realization_time": self.realization_time,
            "validation_id": self.validation_id,
            "verification_snapshot_id": self.verification_snapshot_id,
            "verified_at": self.verified_at,
        }

    @classmethod
    def compute_record_hash(cls, payload_dict: Dict[str, Any]) -> str:
        """基于 RFC 8785 规则计算验证记录的 SHA-256 指纹"""
        canonical_bytes = json.dumps(
            payload_dict,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical_bytes).hexdigest()


class ValidationLedgerError(ValueError):
    """只追加验证账本异常"""
    pass


class AppendOnlyValidationLedger:
    """
    只追加验证账本内存实体 (Append-Only Validation Ledger)
    严守 WORM 原则：仅支持 append 与 read，严禁 update 与 delete
    """

    def __init__(self):
        self._records: Dict[str, CognitionValidationRecord] = {}
        self._by_cognition_id: Dict[str, List[str]] = {}
        self._by_hypothesis_hash: Dict[str, List[str]] = {}

    def append(self, record: CognitionValidationRecord) -> None:
        """只追加记录，若记录已存在则抛出防篡改异常"""
        if record.validation_id in self._records:
            raise ValidationLedgerError(
                f"WORM Violation: validation_id '{record.validation_id}' 已存在，严禁原地覆写或修改！"
            )

        # 验算自身哈希一致性
        expected_hash = CognitionValidationRecord.compute_record_hash(record.to_canonical_dict())
        if record.validation_record_hash and record.validation_record_hash != expected_hash:
            raise ValidationLedgerError(
                f"Validation record hash mismatch! Given: {record.validation_record_hash}, Computed: {expected_hash}"
            )

        self._records[record.validation_id] = record
        self._by_cognition_id.setdefault(record.cognition_record_id, []).append(record.validation_id)
        self._by_hypothesis_hash.setdefault(record.hypothesis_hash, []).append(record.validation_id)

    def get(self, validation_id: str) -> Optional[CognitionValidationRecord]:
        return self._records.get(validation_id)

    def list_by_cognition_id(self, cognition_record_id: str) -> List[CognitionValidationRecord]:
        val_ids = self._by_cognition_id.get(cognition_record_id, [])
        return [self._records[vid] for vid in val_ids]

    def list_by_hypothesis_hash(self, hypothesis_hash: str) -> List[CognitionValidationRecord]:
        val_ids = self._by_hypothesis_hash.get(hypothesis_hash, [])
        return [self._records[vid] for vid in val_ids]

    def count(self) -> int:
        return len(self._records)
