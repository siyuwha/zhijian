"""
Cognition Effective Input Package (Phase 2A Step 3.4 Sandbox)
上位依据：最高董事会工程授权令 BOARD-APPROVAL-20260930-STEP3
"""

from .eligibility import FactEligibilityGate, EligibilityDecision, EligibilityOutcome
from .renderer import DeterministicPromptSerializer, PromptSpecData
from .pipeline import CognitionObservationPipeline

__all__ = [
    "FactEligibilityGate",
    "EligibilityDecision",
    "EligibilityOutcome",
    "DeterministicPromptSerializer",
    "PromptSpecData",
    "CognitionObservationPipeline",
]
