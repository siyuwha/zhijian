"""
Cognition Hypothesis Package (Phase 2A Step 4 Sandbox)
上位依据：最高董事会工程令 PLAN-PHASE2A-STEP4-20261001
"""

from .contracts import (
    MetricType,
    UniverseType,
    OperatorType,
    AggregationType,
    MissingDataPolicy,
    AssertionOutcome,
    HypothesisOutcome,
    WHITELIST_FILTER_FIELDS,
    FilterCondition,
    StructuredFilter,
    MetricAssertion,
    MarketHypothesisDefinition,
    HypothesisSetProjection,
    HypothesisRuntimeState,
)
from .fingerprint import (
    compute_hypothesis_hash,
    compute_hypothesis_set_hash,
    verify_hypothesis_hash,
    verify_hypothesis_set_hash,
)
from .evaluator import (
    AssertionEvaluator,
    AssertionSyntaxError,
    AssertionEvaluationResult,
)
from .falsification import (
    FalsificationEngine,
    HypothesisAdjudicationResult,
)
from .ledger import (
    CognitionValidationRecord,
    AppendOnlyValidationLedger,
    ValidationLedgerError,
)
from .pipeline import (
    DualTimestampValidationPipeline,
    TimeContinuityViolationError,
    HypothesisTamperError,
)

__all__ = [
    "MetricType",
    "UniverseType",
    "OperatorType",
    "AggregationType",
    "MissingDataPolicy",
    "AssertionOutcome",
    "HypothesisOutcome",
    "WHITELIST_FILTER_FIELDS",
    "FilterCondition",
    "StructuredFilter",
    "MetricAssertion",
    "MarketHypothesisDefinition",
    "HypothesisSetProjection",
    "HypothesisRuntimeState",
    "compute_hypothesis_hash",
    "compute_hypothesis_set_hash",
    "verify_hypothesis_hash",
    "verify_hypothesis_set_hash",
    "AssertionEvaluator",
    "AssertionSyntaxError",
    "AssertionEvaluationResult",
    "FalsificationEngine",
    "HypothesisAdjudicationResult",
    "CognitionValidationRecord",
    "AppendOnlyValidationLedger",
    "ValidationLedgerError",
    "DualTimestampValidationPipeline",
    "TimeContinuityViolationError",
    "HypothesisTamperError",
]
