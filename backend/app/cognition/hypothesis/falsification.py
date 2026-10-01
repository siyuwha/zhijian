"""
Falsification-First Adjudication Engine (Phase 2A Step 5 Runtime)
上位依据：
1. 《开发文档/45-Phase-2A-Step5-收窄AST解释执行器与事后证伪闭环实施规划.md》
2. 【C-01 Invariant】Falsification-First 原则：证伪断言具有最高优先级
3. Missing != False 铁律：缺数时严禁假零填充，默认裁决 INCONCLUSIVE
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from .contracts import (
    MarketHypothesisDefinition,
    HypothesisOutcome,
    AssertionOutcome,
)
from .evaluator import (
    AssertionEvaluator,
    AssertionEvaluationResult,
)


class HypothesisAdjudicationResult(BaseModel):
    """假说仲裁结果不可变值对象"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothesis_id: str
    hypothesis_hash: str
    outcome: HypothesisOutcome
    falsification_triggered: bool = False
    invalidation_results: List[AssertionEvaluationResult] = Field(default_factory=list)
    expected_results: List[AssertionEvaluationResult] = Field(default_factory=list)
    actual_metrics_summary: Dict[str, Any] = Field(default_factory=dict)
    details: str = ""


class FalsificationEngine:
    """证伪优先仲裁引擎"""

    @classmethod
    def adjudicate(
        cls,
        hypothesis: MarketHypothesisDefinition,
        observation_data: Dict[str, Any],
    ) -> HypothesisAdjudicationResult:
        """
        对单项假说执行严格的“证伪优先”裁决：
        Step A: 优先求值 invalidation_assertions。只要任一证伪断言成立，立即判定 FALSIFIED！
        Step B: 缺数防御。若数据异常或关键断言为 INCONCLUSIVE，输出 INCONCLUSIVE，绝不冒充成功或失败。
        Step C: 求值 expected_assertions。依据 assertion_logic (AND/OR) 裁决 CONFIRMED 或 UNCONFIRMED。
        """
        invalidation_results: List[AssertionEvaluationResult] = []
        expected_results: List[AssertionEvaluationResult] = []
        actual_metrics: Dict[str, Any] = {}

        # ---------------------------------------------------------------------
        # Step A: 证伪断言先行求值 (Falsification-First Priority)
        # ---------------------------------------------------------------------
        any_falsified = False
        falsified_assertion_id = ""

        for inv_assertion in hypothesis.invalidation_assertions:
            res = AssertionEvaluator.evaluate(inv_assertion, observation_data)
            invalidation_results.append(res)
            if res.actual_value is not None:
                actual_metrics[inv_assertion.assertion_id] = res.actual_value

            # 当证伪断言 PASSED 时，表示反向证伪条件被真实市场触发！
            if res.outcome == AssertionOutcome.PASSED:
                any_falsified = True
                falsified_assertion_id = inv_assertion.assertion_id
                # 依据证伪优先原则，只要有一项证伪条件被击中，假说已被证伪，不再等待预期验证

        if any_falsified:
            return HypothesisAdjudicationResult(
                hypothesis_id=hypothesis.hypothesis_id,
                hypothesis_hash=hypothesis.hypothesis_hash,
                outcome=HypothesisOutcome.FALSIFIED,
                falsification_triggered=True,
                invalidation_results=invalidation_results,
                expected_results=[],
                actual_metrics_summary=actual_metrics,
                details=f"[FALSIFIED]: 证伪断言 '{falsified_assertion_id}' 触发，假说被直接证伪短路",
            )

        # ---------------------------------------------------------------------
        # Step B: 预期断言求值 (Expected Assertions Evaluation)
        # ---------------------------------------------------------------------
        has_inconclusive = False
        inconclusive_reasons = []

        # 检查证伪断言中是否有因缺数导致的 INCONCLUSIVE
        for inv_res in invalidation_results:
            if inv_res.outcome == AssertionOutcome.INCONCLUSIVE:
                has_inconclusive = True
                inconclusive_reasons.append(f"证伪断言 {inv_res.assertion_id} 缺数")

        for exp_assertion in hypothesis.expected_assertions:
            res = AssertionEvaluator.evaluate(exp_assertion, observation_data)
            expected_results.append(res)
            if res.actual_value is not None:
                actual_metrics[exp_assertion.assertion_id] = res.actual_value

            if res.outcome == AssertionOutcome.INCONCLUSIVE:
                has_inconclusive = True
                inconclusive_reasons.append(f"预期断言 {exp_assertion.assertion_id} 缺数")

        # ---------------------------------------------------------------------
        # Step C: 综合逻辑仲裁与缺数保护 (Synthesis Adjudication)
        # ---------------------------------------------------------------------
        # 1. 缺数保护：如果关键断言缺数，严禁给出 CONFIRMED 判定
        if has_inconclusive:
            return HypothesisAdjudicationResult(
                hypothesis_id=hypothesis.hypothesis_id,
                hypothesis_hash=hypothesis.hypothesis_hash,
                outcome=HypothesisOutcome.INCONCLUSIVE,
                falsification_triggered=False,
                invalidation_results=invalidation_results,
                expected_results=expected_results,
                actual_metrics_summary=actual_metrics,
                details=f"[INCONCLUSIVE]: 数据缺失或断言未决: {'; '.join(inconclusive_reasons)}",
            )

        # 若无预期断言，且未被证伪
        if not hypothesis.expected_assertions:
            return HypothesisAdjudicationResult(
                hypothesis_id=hypothesis.hypothesis_id,
                hypothesis_hash=hypothesis.hypothesis_hash,
                outcome=HypothesisOutcome.CONFIRMED,
                falsification_triggered=False,
                invalidation_results=invalidation_results,
                expected_results=expected_results,
                actual_metrics_summary=actual_metrics,
                details="[CONFIRMED]: 无预期断言约束，且证伪断言未触发",
            )

        is_or = hypothesis.assertion_logic.upper() == "OR"
        passed_list = [r.outcome == AssertionOutcome.PASSED for r in expected_results]

        if is_or:
            confirmed = any(passed_list)
        else:
            confirmed = all(passed_list)

        outcome = HypothesisOutcome.CONFIRMED if confirmed else HypothesisOutcome.UNCONFIRMED
        detail_msg = (
            f"[{outcome.value}]: 预期断言符合度 {sum(passed_list)}/{len(expected_results)} "
            f"(逻辑={hypothesis.assertion_logic.upper()}), 证伪断言均未触发"
        )

        return HypothesisAdjudicationResult(
            hypothesis_id=hypothesis.hypothesis_id,
            hypothesis_hash=hypothesis.hypothesis_hash,
            outcome=outcome,
            falsification_triggered=False,
            invalidation_results=invalidation_results,
            expected_results=expected_results,
            actual_metrics_summary=actual_metrics,
            details=detail_msg,
        )
