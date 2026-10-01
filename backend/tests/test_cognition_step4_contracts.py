"""
Phase 2A Step 4.1 假说实体契约与 JCS 指纹测试套件
上位依据：
1. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》v1.2.1-FINAL (第4节)
2. 《开发文档/42-Phase-2A-Step4-假说定义投影与收窄AST断言执行器实施规划.md》

核心验证目标：
1. 假说模型与收窄 AST 节点不可变性（Frozen Invariant）
2. RFC 8785 JCS 假说定义指纹（hypothesis_hash）确定性与雪崩效应
3. 假说集合聚合哈希（hypothesis_set_hash）字典序排布与验真
4. 【C-02 Invariant 核心测试】：后验运行态发生跃迁时，原始假说定义哈希 100% 保持不变（单向物理隔离）
"""

import sys
import os
import copy
import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.cognition.hypothesis.contracts import (
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
from app.cognition.hypothesis.fingerprint import (
    compute_hypothesis_hash,
    compute_hypothesis_set_hash,
    verify_hypothesis_hash,
    verify_hypothesis_set_hash,
)


def _create_sample_hypothesis() -> MarketHypothesisDefinition:
    """辅助工厂：构造标准测试假说"""
    # 构造收窄 AST 条件
    cond = FilterCondition(field="board_height", op=OperatorType.GTE, val=4)
    selector = StructuredFilter(
        universe_type=UniverseType.LADDER_HIGH_SPEC,
        conditions=[cond],
        logical_op="AND",
    )
    # 预期断言：连板梯队开盘低开均值 <= -3.0%
    expected = MetricAssertion(
        assertion_id="assert_exp_01",
        metric="open_pct_change",
        selector=selector,
        aggregation=AggregationType.MEAN,
        operator=OperatorType.LTE,
        target_value=-3.0,
        unit="PERCENT",
        time_binding="auction_0925",
        missing_data_policy=MissingDataPolicy.INCONCLUSIVE,
    )
    # 证伪断言：最高板个股开盘 >= 0.0%
    cond_inv = FilterCondition(field="is_highest_board", op=OperatorType.EQ, val=True)
    selector_inv = StructuredFilter(
        universe_type=UniverseType.LADDER_HIGH_SPEC,
        conditions=[cond_inv],
        logical_op="AND",
    )
    invalidation = MetricAssertion(
        assertion_id="assert_inv_01",
        metric="open_pct_change",
        selector=selector_inv,
        aggregation=AggregationType.MAX,
        operator=OperatorType.GTE,
        target_value=0.0,
        unit="PERCENT",
        time_binding="auction_0925",
        missing_data_policy=MissingDataPolicy.INCONCLUSIVE,
    )

    hypo = MarketHypothesisDefinition(
        hypothesis_id="hypo_20260930_01",
        cognition_id="cog_20260930_1530",
        proposition="2026-09-30 集合竞价阶段高位连板梯队整体低开杀跌",
        premise_evidence=["D3 极端生态跌停扩散", "缩量严重无法承接高位换手"],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[expected],
        invalidation_assertions=[invalidation],
        hypothesis_hash="",
    )
    h_hash = compute_hypothesis_hash(hypo)
    return hypo.model_copy(update={"hypothesis_hash": h_hash})


def test_01_hypothesis_model_immutability():
    """验证 1: 假说与 AST 模型的强不可变性 (Frozen Invariant)"""
    hypo = _create_sample_hypothesis()

    # 禁止就地修改属性
    with pytest.raises(ValidationError):
        hypo.proposition = "篡改命题"

    with pytest.raises(ValidationError):
        hypo.expected_assertions[0].target_value = 99.0

    # 禁止写入未定义字段 (extra='forbid')
    with pytest.raises(ValidationError):
        FilterCondition(field="board_height", op=OperatorType.EQ, val=2, invalid_extra=123)


def test_02_hypothesis_hash_determinism_and_verification():
    """验证 2: 假说定义指纹 JCS 计算确定性与验真防伪"""
    hypo1 = _create_sample_hypothesis()
    hypo2 = _create_sample_hypothesis()

    # 两次生成相同假说，哈希必须完全一致
    assert hypo1.hypothesis_hash == hypo2.hypothesis_hash
    assert verify_hypothesis_hash(hypo1) is True
    assert len(hypo1.hypothesis_hash) == 64

    # 篡改任意字符，验真立即失败
    tampered = hypo1.model_copy(update={"proposition": hypo1.proposition + "！"})
    assert verify_hypothesis_hash(tampered) is False
    assert compute_hypothesis_hash(tampered) != hypo1.hypothesis_hash


def test_03_hypothesis_set_hash_aggregation():
    """验证 3: 假说集合哈希聚合与字典序稳定性"""
    hypo1 = _create_sample_hypothesis()
    # 构造第二个假说
    hypo2 = hypo1.model_copy(update={"hypothesis_id": "hypo_20260930_02", "proposition": "命题2"})
    hypo2 = hypo2.model_copy(update={"hypothesis_hash": compute_hypothesis_hash(hypo2)})

    hypo_set = HypothesisSetProjection(
        set_id="set_20260930_01",
        cognition_id="cog_20260930_1530",
        hypotheses=[hypo1, hypo2],
        hypothesis_set_hash="",
    )
    s_hash = compute_hypothesis_set_hash(hypo_set)
    hypo_set = hypo_set.model_copy(update={"hypothesis_set_hash": s_hash})

    assert verify_hypothesis_set_hash(hypo_set) is True

    # 即使输入列表颠倒顺序，由于 JCS 内部按 hypothesis_id 字典序排列，聚合哈希依然保持恒等
    hypo_set_reversed = hypo_set.model_copy(update={"hypotheses": [hypo2, hypo1]})
    assert compute_hypothesis_set_hash(hypo_set_reversed) == s_hash


def test_04_c02_invariant_runtime_state_does_not_pollute_definition_hash():
    """
    验证 4: 【C-02 Invariant 核心闭环验证】
    后验运行态（status 跃迁为 CONFIRMED、对撞事实切片写入）绝不污染假说定义哈希！
    """
    hypo = _create_sample_hypothesis()
    original_def_hash = hypo.hypothesis_hash

    # 模拟在验证执行时刻，后验运行态发生流转
    runtime_state = HypothesisRuntimeState(
        hypothesis_id=hypo.hypothesis_id,
        status="CLOSED",
        actual_data_snapshot={"actual_open_pct": -4.5, "target": -3.0},
        verification_outcome=HypothesisOutcome.CONFIRMED,
        verification_execute_time="2026-09-30T09:25:05.000+08:00",
        gap_summary="连板梯队实际低开 -4.5%，符合预期低开断言，假说确证",
    )

    # 验证运行时状态对象已正确生成
    assert runtime_state.verification_outcome == HypothesisOutcome.CONFIRMED
    assert runtime_state.status == "CLOSED"

    # 重新提取假说定义并验真哈希：100% 保持恒等，未受后验状态丝毫污染！
    assert verify_hypothesis_hash(hypo) is True
    assert hypo.hypothesis_hash == original_def_hash
    assert compute_hypothesis_hash(hypo) == original_def_hash
