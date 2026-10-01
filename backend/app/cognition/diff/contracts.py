"""
Cognition Diff Contracts (Phase 2B Runtime)
上位依据：
1. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》v1.2.1-FINAL (第6.2节)
2. 《开发文档/49-Phase-2B-实施规划与科学实验对撞引擎技术设计单.md》

核心铁律：
- 【INV-NO-WINNER】：彻底封杀 winner_cognition_id，认知对撞的本质是控制变量的科学对照实验，严禁粗暴评选胜负！
- 五维对撞结构化保全：Observation, Reasoning, Hypothesis, Confidence, Outcome Matrix
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class ObservationDiff(BaseModel):
    """事实摄入与关注点差异不可变值对象"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    record_a_quality: str
    record_b_quality: str
    is_quality_equal: bool
    admitted_facts_diff: Dict[str, List[str]] = Field(default_factory=dict)
    degraded_fields_diff: Dict[str, List[str]] = Field(default_factory=dict)
    summary: str = ""


class ReasoningDiff(BaseModel):
    """推演归因链条差异不可变值对象"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    text_similarity_ratio: float              # 文本字符相似度 [0.0, 1.0]
    proposition_comparison: List[Dict[str, str]] = Field(default_factory=list)
    summary: str = ""


class HypothesisDiff(BaseModel):
    """假说命题与断言宽严对比不可变值对象"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    count_a: int
    count_b: int
    strictness_comparison: List[Dict[str, Any]] = Field(default_factory=list)
    invalidation_redline_diff: List[Dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class ConfidenceDiff(BaseModel):
    """模型置信度差异与过度自信识别不可变值对象"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    confidence_a: Optional[float] = None
    confidence_b: Optional[float] = None
    delta: float = 0.0
    overconfidence_risk: bool = False
    details: str = ""


class OutcomeComparisonMatrix(BaseModel):
    """五维对撞结果矩阵不可变值对象 (无排行榜)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    record_a_metrics: Dict[str, int]          # {"total": 2, "confirmed": 1, "falsified": 1, ...}
    record_b_metrics: Dict[str, int]
    delta_metrics: Dict[str, int]             # 实验组相对于对照组的变化量
    significance_summary: str = ""            # 科学差异显著性客观陈述


class CognitionDiffReport(BaseModel):
    """
    五维科学差异对撞报告不可变值对象 (Cognition Diff Report)
    上位依据：【AC-08】格式完备，has_winner_selection 刚性恒为 False，严禁胜负榜
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    diff_id: str
    baseline_cognition_id: str                 # 对照组记录 ID (Record A)
    experiment_cognition_id: str               # 实验组记录 ID (Record B)
    observation_diff: ObservationDiff
    reasoning_diff: ReasoningDiff
    hypothesis_diff: HypothesisDiff
    confidence_diff: ConfidenceDiff
    outcome_matrix: OutcomeComparisonMatrix
    has_winner_selection: bool = False         # 刚性恒为 False，严禁 winner 评选！
    generated_at: str

    def to_canonical_dict(self) -> Dict[str, Any]:
        """构建标准化字典"""
        return {
            "baseline_cognition_id": self.baseline_cognition_id,
            "confidence_diff": self.confidence_diff.model_dump(),
            "diff_id": self.diff_id,
            "experiment_cognition_id": self.experiment_cognition_id,
            "generated_at": self.generated_at,
            "has_winner_selection": self.has_winner_selection,
            "hypothesis_diff": self.hypothesis_diff.model_dump(),
            "observation_diff": self.observation_diff.model_dump(),
            "outcome_matrix": self.outcome_matrix.model_dump(),
            "reasoning_diff": self.reasoning_diff.model_dump(),
        }
