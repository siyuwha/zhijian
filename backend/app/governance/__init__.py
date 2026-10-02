"""
KA-06 基线差分与防退化门禁模块 (Baseline Diff & Anti-Regression Gate)
"""
from .baseline_gate import BaselineDiffEngine, BaselineDiffReport, MetricDelta

__all__ = ["BaselineDiffEngine", "BaselineDiffReport", "MetricDelta"]
