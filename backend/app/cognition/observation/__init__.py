"""
Cognition Observation Package (Phase 2A Step 3 Sandbox)
上位依据：《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》
董事会令：BOARD-APPROVAL-20260930-STEP3
"""

from .contracts import (
    FactStatus,
    Freshness,
    QualityLevel,
    FactType,
    CognitionStage,
    WindowType,
    ObservationWindow,
    FourDimensionalTime,
    ConflictRecord,
    Provenance,
    FactContract,
    FactItem,
    SourceCredential,
    ObservationSnapshot,
    EffectiveInferenceInput,
    DEFAULT_FACT_CONTRACTS,
)
from .clock import DeterministicClock
from .fingerprint import (
    compute_fact_fingerprint,
    compute_snapshot_fingerprint,
    compute_effective_input_hash,
    verify_fact_fingerprint,
    verify_snapshot_fingerprint,
    verify_effective_input_hash,
)
from .quality import aggregate_overall_quality
from .builder import ObservationSnapshotBuilder
from .adapters import (
    BaseFactAdapter,
    M1ReviewFactAdapter,
    M2PremarketFactAdapter,
    M4AuctionFactAdapter,
    M5SettlementFactAdapter,
    S4NewsFactAdapter,
)

__all__ = [
    "FactStatus",
    "Freshness",
    "QualityLevel",
    "FactType",
    "CognitionStage",
    "WindowType",
    "ObservationWindow",
    "FourDimensionalTime",
    "ConflictRecord",
    "Provenance",
    "FactContract",
    "FactItem",
    "SourceCredential",
    "ObservationSnapshot",
    "EffectiveInferenceInput",
    "DEFAULT_FACT_CONTRACTS",
    "DeterministicClock",
    "compute_fact_fingerprint",
    "compute_snapshot_fingerprint",
    "compute_effective_input_hash",
    "verify_fact_fingerprint",
    "verify_snapshot_fingerprint",
    "verify_effective_input_hash",
    "aggregate_overall_quality",
    "ObservationSnapshotBuilder",
    "BaseFactAdapter",
    "M1ReviewFactAdapter",
    "M2PremarketFactAdapter",
    "M4AuctionFactAdapter",
    "M5SettlementFactAdapter",
    "S4NewsFactAdapter",
]
