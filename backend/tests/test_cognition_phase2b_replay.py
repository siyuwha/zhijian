"""
Phase 2B Contract Test: Parameterized Replay Runner & Deterministic Level Classifier
上位依据:
- 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》v1.2.1-FINAL (第6.1节)
- 《开发文档/49-Phase-2B-实施规划与科学实验对撞引擎技术设计单.md》
"""

import pytest
from typing import Dict, Any

from app.cognition.hypothesis.contracts import (
    MarketHypothesisDefinition,
    HypothesisSetProjection,
    MetricAssertion,
    MetricType,
    UniverseType,
    OperatorType,
    AggregationType,
    FilterCondition,
    StructuredFilter,
)
from app.cognition.hypothesis.fingerprint import (
    compute_hypothesis_hash,
    compute_hypothesis_set_hash,
)
from app.cognition.replay.contracts import (
    DeterministicLevel,
    ReplayType,
    InferenceConfig,
    ReplayRequest,
    DerivedCognitionRecord,
)
from app.cognition.replay.runner import (
    DeterministicClassifier,
    ReplayRunner,
)


def _build_test_hypo_set(set_id: str, cognition_id: str, target_val: float) -> HypothesisSetProjection:
    c = FilterCondition(field="board_height", op=OperatorType.GTE, val=2)
    selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[c])
    exp_a = MetricAssertion(
        assertion_id="exp_01",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        aggregation=AggregationType.MEAN,
        operator=OperatorType.GT,
        target_value=target_val,
    )
    dummy_hypo = MarketHypothesisDefinition(
        hypothesis_id=f"h_{set_id}",
        cognition_id=cognition_id,
        proposition="高标开盘走势",
        premise_evidence=["梯队健全"],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[exp_a],
        invalidation_assertions=[],
        hypothesis_hash="",
    )
    h_hash = compute_hypothesis_hash(dummy_hypo)
    hypo = MarketHypothesisDefinition(
        hypothesis_id=f"h_{set_id}",
        cognition_id=cognition_id,
        proposition="高标开盘走势",
        premise_evidence=["梯队健全"],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[exp_a],
        invalidation_assertions=[],
        hypothesis_hash=h_hash,
    )
    dummy_set = HypothesisSetProjection(
        set_id=set_id,
        cognition_id=cognition_id,
        hypotheses=[hypo],
        hypothesis_set_hash="",
    )
    set_hash = compute_hypothesis_set_hash(dummy_set)
    return HypothesisSetProjection(
        set_id=set_id,
        cognition_id=cognition_id,
        hypotheses=[hypo],
        hypothesis_set_hash=set_hash,
    )


def test_01_bit_exact_deterministic_replay():
    """验证 1: 原始文本二进制级 100% 吻合 -> 判定为 BIT_EXACT"""
    hypo_set = _build_test_hypo_set("set_01", "cog_parent_01", 2.0)
    parent_record = {
        "cognition_id": "cog_parent_01",
        "snapshot_id": "snap_historical_01",
        "raw_response": "Market analysis: bullish bias with mean open +2.5%",
        "hypothesis_set": hypo_set,
    }

    req = ReplayRequest(
        replay_id="rep_01",
        parent_cognition_id="cog_parent_01",
        replay_type=ReplayType.EXACT_REPLAY,
    )

    derived = ReplayRunner.execute_replay(
        parent_record=parent_record,
        request=req,
        simulated_raw_response="Market analysis: bullish bias with mean open +2.5%",
        simulated_hypothesis_set=hypo_set,
    )

    assert derived.deterministic_level == DeterministicLevel.BIT_EXACT
    assert derived.parent_cognition_id == "cog_parent_01"
    assert derived.snapshot_id == "snap_historical_01"
    assert derived.drift_details is None


def test_02_semantic_equal_deterministic_replay():
    """验证 2: 文本存在换行或微小格式变动，但假说集合哈希 100% 相同 -> 判定为 SEMANTIC_EQUAL"""
    hypo_set = _build_test_hypo_set("set_02", "cog_parent_02", 2.0)
    parent_record = {
        "cognition_id": "cog_parent_02",
        "snapshot_id": "snap_historical_02",
        "raw_response": "Conclusion: expect high open > 2.0%",
        "hypothesis_set": hypo_set,
    }

    req = ReplayRequest(
        replay_id="rep_02",
        parent_cognition_id="cog_parent_02",
        replay_type=ReplayType.EXACT_REPLAY,
    )

    # 模拟文本存在微调，但假说集合内容与哈希完全一致
    derived = ReplayRunner.execute_replay(
        parent_record=parent_record,
        request=req,
        simulated_raw_response="Conclusion: expect high open > 2.0%! (slightly formatted)",
        simulated_hypothesis_set=hypo_set,
    )

    assert derived.deterministic_level == DeterministicLevel.SEMANTIC_EQUAL
    assert derived.hypothesis_set_hash == hypo_set.hypothesis_set_hash


def test_03_stochastic_drift_detection():
    """验证 3: 相同配置下结论发生离散漂移（假说阈值变动） -> 判定为 STOCHASTIC_DRIFT"""
    hypo_set_parent = _build_test_hypo_set("set_p03", "cog_parent_03", 2.0)
    # 重放时假说阈值漂移为 3.0，导致集合哈希不匹配
    hypo_set_drifted = _build_test_hypo_set("set_d03", "cog_parent_03", 3.0)

    parent_record = {
        "cognition_id": "cog_parent_03",
        "snapshot_id": "snap_historical_03",
        "raw_response": "Parent prediction: mean > 2.0%",
        "hypothesis_set": hypo_set_parent,
    }

    req = ReplayRequest(
        replay_id="rep_03",
        parent_cognition_id="cog_parent_03",
        replay_type=ReplayType.EXACT_REPLAY,
    )

    derived = ReplayRunner.execute_replay(
        parent_record=parent_record,
        request=req,
        simulated_raw_response="Drifted prediction: mean > 3.0%",
        simulated_hypothesis_set=hypo_set_drifted,
    )

    assert derived.deterministic_level == DeterministicLevel.STOCHASTIC_DRIFT
    assert "推演结论发生离散漂移" in derived.drift_details


def test_04_offline_fallback_level():
    """验证 4: 当标记历史模型下线采用替代模型 -> 判定为 OFFLINE_FALLBACK"""
    hypo_set = _build_test_hypo_set("set_04", "cog_parent_04", 2.0)
    parent_record = {
        "cognition_id": "cog_parent_04",
        "snapshot_id": "snap_historical_04",
        "raw_response": "Historical original text",
        "hypothesis_set": hypo_set,
    }

    req = ReplayRequest(
        replay_id="rep_04",
        parent_cognition_id="cog_parent_04",
        replay_type=ReplayType.EXACT_REPLAY,
        is_offline_fallback=True,
    )

    derived = ReplayRunner.execute_replay(
        parent_record=parent_record,
        request=req,
        simulated_raw_response="Fallback model text",
        simulated_hypothesis_set=hypo_set,
    )

    assert derived.deterministic_level == DeterministicLevel.OFFLINE_FALLBACK
    assert "离线近似替代模型" in derived.drift_details


def test_05_worm_parent_preservation_and_fact_isolation():
    """验证 5: WORM 不变量：父记录绝对不被原地修改，事实快照严格沿用"""
    hypo_set = _build_test_hypo_set("set_05", "cog_parent_05", 2.0)
    parent_record = {
        "cognition_id": "cog_parent_05",
        "snapshot_id": "snap_historical_05",
        "raw_response": "Original text",
        "hypothesis_set": hypo_set,
    }
    original_copy = dict(parent_record)

    req = ReplayRequest(
        replay_id="rep_05",
        parent_cognition_id="cog_parent_05",
        replay_type=ReplayType.EXACT_REPLAY,
    )

    derived = ReplayRunner.execute_replay(
        parent_record=parent_record,
        request=req,
    )

    # 1. 父记录字典保持原貌，未被覆写
    assert parent_record == original_copy
    # 2. 衍生记录 snapshot_id 严格一致
    assert derived.snapshot_id == "snap_historical_05"
    assert derived.parent_cognition_id == "cog_parent_05"


def test_06_diff_shadow_replay_type():
    """验证 6: 控制变量反事实重放 (DIFF_SHADOW)，成功绑定 parent_cognition_id 与新假说"""
    hypo_set_parent = _build_test_hypo_set("set_p06", "cog_parent_06", 1.0)
    hypo_set_upgraded = _build_test_hypo_set("set_u06", "cog_parent_06", 2.5)

    parent_record = {
        "cognition_id": "cog_parent_06",
        "snapshot_id": "snap_historical_06",
        "raw_response": "Baseline prompt reasoning",
        "hypothesis_set": hypo_set_parent,
    }

    req = ReplayRequest(
        replay_id="rep_shadow_06",
        parent_cognition_id="cog_parent_06",
        replay_type=ReplayType.DIFF_SHADOW,
        target_prompt_id="prompt_v2_falsification_heavy",
    )

    derived = ReplayRunner.execute_replay(
        parent_record=parent_record,
        request=req,
        simulated_raw_response="Upgraded prompt reasoning with higher threshold",
        simulated_hypothesis_set=hypo_set_upgraded,
    )

    assert derived.replay_type == ReplayType.DIFF_SHADOW
    assert derived.parent_cognition_id == "cog_parent_06"
    assert derived.hypothesis_set_hash == hypo_set_upgraded.hypothesis_set_hash
