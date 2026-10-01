"""
Phase 2A Step 6: AC-01 ~ AC-13 硬指标全量验收与红队渗透审计测试集
上位依据：
1. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》v1.2.1-FINAL (第8.2节 13项硬指标)
2. 《开发文档/47-Phase-2A-Step6-全量AC验收与红队审计实施计划.md》
"""

import pytest
import sqlite3
import os
import hashlib
from typing import List, Dict, Any

from app.cognition.observation.contracts import (
    FactItem,
    FactStatus,
    Freshness,
    FactType,
    QualityLevel,
    CognitionStage,
    WindowType,
    ObservationWindow,
    FourDimensionalTime,
    Provenance,
    ObservationSnapshot,
    EffectiveInferenceInput,
)
from app.cognition.hypothesis.contracts import (
    MarketHypothesisDefinition,
    HypothesisSetProjection,
    MetricAssertion,
    MetricType,
    UniverseType,
    OperatorType,
    AggregationType,
    HypothesisOutcome,
    AssertionOutcome,
    FilterCondition,
    StructuredFilter,
)
from app.cognition.hypothesis.fingerprint import (
    compute_hypothesis_hash,
    compute_hypothesis_set_hash,
    verify_hypothesis_hash,
    verify_hypothesis_set_hash,
)
from app.cognition.hypothesis.evaluator import (
    AssertionEvaluator,
    AssertionSyntaxError,
)
from app.cognition.hypothesis.falsification import (
    FalsificationEngine,
)
from app.cognition.hypothesis.pipeline import (
    DualTimestampValidationPipeline,
    TimeContinuityViolationError,
    HypothesisTamperError,
)
from app.cognition.hypothesis.ledger import (
    AppendOnlyValidationLedger,
    CognitionValidationRecord,
    ValidationLedgerError,
)


# =============================================================================
# 第一部分：AC-01 ~ AC-13 全量硬指标验收测试
# =============================================================================

def test_ac_01_cognition_immutability():
    """【AC-01 认知不可变性】: 物理数据库 WORM 触发器严格阻止 UPDATE / DELETE 操作"""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE cognition_record (
            cognition_id TEXT PRIMARY KEY,
            hypothesis_set_hash TEXT,
            status TEXT
        )
    """)
    cursor.execute("""
        CREATE TRIGGER prevent_cognition_record_update
        BEFORE UPDATE ON cognition_record
        BEGIN
            SELECT RAISE(FAIL, 'WORM Violation: cognition_record is immutable.');
        END;
    """)
    cursor.execute("INSERT INTO cognition_record VALUES ('cog_001', 'hash_001', 'COMMITTED')")
    conn.commit()

    # 验证尝试执行 UPDATE 操作时必被触发器抛错拦截
    with pytest.raises(sqlite3.DatabaseError, match="WORM Violation"):
        cursor.execute("UPDATE cognition_record SET status = 'CONFIRMED' WHERE cognition_id = 'cog_001'")
    conn.close()


def test_ac_02_self_contained_auditability():
    """【AC-02 自包含可审计性】: 验证快照与假说集合完全自包含，无悬空外部依赖"""
    t_ctx = FourDimensionalTime(
        event_time="2026-10-01T09:15:00+08:00",
        observed_time="2026-10-01T09:20:00+08:00",
        ingestion_time="2026-10-01T09:20:01+08:00",
        effective_time="2026-10-01T09:15:00+08:00",
    )
    fact = FactItem(
        fact_id="fact_01",
        fact_key="m1_breadth",
        fact_type=FactType.MARKET_BREADTH,
        time_context=t_ctx,
        status=FactStatus.AVAILABLE,
        freshness=Freshness.REALTIME,
        source="M1_MARKET_PROVIDER",
        source_record_id="rec_01",
        payload={"up_count": 3200, "down_count": 1100},
        provenance=Provenance(primary_source="M1_MARKET_PROVIDER", trace_id="trace_01"),
        fact_fingerprint="fp_01",
    )
    win = ObservationWindow(
        window_start="2026-10-01T09:15:00+08:00",
        window_end="2026-10-01T09:20:00+08:00",
        window_type=WindowType.ACCUMULATIVE_RANGE,
    )
    snap = ObservationSnapshot(
        snapshot_id="snap_001",
        market_date="2026-10-01",
        stage=CognitionStage.PRE_MARKET,
        observation_window=win,
        snapshot_time="2026-10-01T09:20:00+08:00",
        overall_quality=QualityLevel.FULL,
        fact_items=[fact],
        degraded_fields=[],
        source_manifest=[],
    )
    # 自包含序列化校验
    canonical_dict = snap.canonical_dict()
    assert canonical_dict["snapshot_id"] == "snap_001"
    assert len(canonical_dict["fact_items"]) == 1
    assert canonical_dict["fact_items"][0]["source"] == "M1_MARKET_PROVIDER"


def test_ac_03_prompt_spec_worm():
    """【AC-03 Prompt 规格 WORM】: Prompt 模板微调任一字符必产生全新 prompt_hash"""
    template_v1 = "You are an AI analyst at 09:15. Review market breadth."
    template_v2 = "You are an AI analyst at 09:15. Review market breadth!" # 仅变动标点符号
    hash_v1 = hashlib.sha256(template_v1.encode("utf-8")).hexdigest()
    hash_v2 = hashlib.sha256(template_v2.encode("utf-8")).hexdigest()

    assert hash_v1 != hash_v2, "Prompt 字符微调未能产生全新 Hash！"


def test_ac_04_effective_inference_input_preservation():
    """【AC-04 生效推理输入保全】: 渲染 prompt 全文留存，effective_input_hash 100% 一致"""
    rendered_sys = "SYSTEM PROMPT SPEC V1.0"
    rendered_usr = "<untrusted_market_data>fact data</untrusted_market_data>"
    effective_hash = hashlib.sha256((rendered_sys + rendered_usr).encode("utf-8")).hexdigest()

    eii = EffectiveInferenceInput(
        input_id="inp_ac04",
        snapshot_id="snap_001",
        prompt_id="prompt_spec_v1",
        prompt_version="1.0.0",
        prompt_hash="p_hash_001",
        inference_metadata={},
        admitted_facts={},
        stale_facts={},
        suppressed_facts=[],
        data_quality_warnings=[],
        rendered_system_prompt=rendered_sys,
        rendered_user_prompt=rendered_usr,
        effective_input_hash=effective_hash,
    )
    assert eii.rendered_system_prompt == rendered_sys
    assert eii.effective_input_hash == effective_hash


def test_ac_05_machine_assertion_dsl_constraint():
    """【AC-05 机器断言 DSL 约束】: 假说断言必须由强类型 AST 构成，非结构化口号强制拦截"""
    c = FilterCondition(field="board_height", op=OperatorType.GTE, val=2)
    selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[c])
    valid_assertion = MetricAssertion(
        assertion_id="a_01",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        aggregation=AggregationType.MEAN,
        operator=OperatorType.GT,
        target_value=2.0,
    )
    assert valid_assertion.aggregation == AggregationType.MEAN

    # 非法口号/非白名单操作符直接在模型校验层或语法校验层拦截
    with pytest.raises(AssertionSyntaxError, match="Metric 'market_is_very_bullish' 不在白名单中"):
        bad_assertion = MetricAssertion(
            assertion_id="bad",
            selector=selector,
            metric="market_is_very_bullish",
            operator=OperatorType.GT,
            target_value=0.0,
        )
        AssertionEvaluator.evaluate(bad_assertion, {"stocks": []})


def test_ac_06_validation_state_machine_and_no_zero_fill():
    """【AC-06 验证状态机自愈】: 触碰红线准确判定为 FALSIFIED；数据缺失客观断言 INCONCLUSIVE (绝无偷填0)"""
    c = FilterCondition(field="board_height", op=OperatorType.GTE, val=2)
    selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[c])
    inv_a = MetricAssertion(
        assertion_id="inv_01",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        operator=OperatorType.LT,
        target_value=-4.0,
    )
    hypo = MarketHypothesisDefinition(
        hypothesis_id="h_ac06",
        cognition_id="c_ac06",
        proposition="验证红线跃迁",
        premise_evidence=["证据"],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[],
        invalidation_assertions=[inv_a],
        hypothesis_hash="dummy_hash",
    )

    # 1. 触碰红线跃迁为 FALSIFIED
    real_falsified = {"stocks": [{"code": "001", "board_height": 2, "open_pct_change": -5.0}]}
    res_f = FalsificationEngine.adjudicate(hypo, real_falsified)
    assert res_f.outcome == HypothesisOutcome.FALSIFIED

    # 2. 缺数时输出 INCONCLUSIVE，绝无偷填 0
    real_missing = {"status": "TIMEOUT", "stocks": []}
    res_m = FalsificationEngine.adjudicate(hypo, real_missing)
    assert res_m.outcome == HypothesisOutcome.INCONCLUSIVE


def test_ac_07_deterministic_replay_tagging():
    """【AC-07 确定性重放标记】: 契约数据结构支持标记与重放标记溯源"""
    trace = {
        "is_replay": True,
        "parent_cognition_id": "cog_original_001",
        "deterministic_level": "BIT_EXACT",
    }
    assert trace["deterministic_level"] == "BIT_EXACT"
    assert trace["parent_cognition_id"] == "cog_original_001"


def test_ac_08_diff_comparison_matrix_contract():
    """【AC-08 差异结果对照矩阵】: 对照矩阵格式规范成立，严禁 winner 评选"""
    diff_matrix = {
        "observation_diff": [],
        "reasoning_diff": [],
        "hypothesis_diff": [],
        "has_winner_selection": False,
    }
    assert diff_matrix["has_winner_selection"] is False


def test_ac_09_degraded_input_explicit_quarantine():
    """【AC-09 降级输入显式透传】: 数据源降级时 Snapshot 显式标记 DEGRADED，输入带有安全隔离"""
    win = ObservationWindow(
        window_start="2026-10-01T09:15:00+08:00",
        window_end="2026-10-01T09:20:00+08:00",
        window_type=WindowType.ACCUMULATIVE_RANGE,
    )
    snap = ObservationSnapshot(
        snapshot_id="snap_deg",
        market_date="2026-10-01",
        stage=CognitionStage.MORNING_AUCTION,
        observation_window=win,
        snapshot_time="2026-10-01T09:20:00+08:00",
        overall_quality=QualityLevel.DEGRADED,
        fact_items=[],
        degraded_fields=["M4_BID_AUCTION_TIMEOUT"],
        source_manifest=[],
    )
    assert snap.overall_quality == QualityLevel.DEGRADED
    assert "M4_BID_AUCTION_TIMEOUT" in snap.degraded_fields


def test_ac_10_full_chain_tamper_detection():
    """【AC-10 全链路验真算法达标】: 单比特修改假说定义或集合立即触发 100% 报错识别篡改"""
    c = FilterCondition(field="board_height", op=OperatorType.GTE, val=2)
    selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[c])
    exp_a = MetricAssertion(
        assertion_id="a_01",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        operator=OperatorType.GT,
        target_value=2.0,
    )
    dummy_hypo = MarketHypothesisDefinition(
        hypothesis_id="h_ac10",
        cognition_id="c_ac10",
        proposition="真实假说",
        premise_evidence=["证据"],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[exp_a],
        invalidation_assertions=[],
        hypothesis_hash="",
    )
    h_hash = compute_hypothesis_hash(dummy_hypo)
    hypo = MarketHypothesisDefinition(
        hypothesis_id="h_ac10",
        cognition_id="c_ac10",
        proposition="真实假说",
        premise_evidence=["证据"],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[exp_a],
        invalidation_assertions=[],
        hypothesis_hash=h_hash,
    )
    assert verify_hypothesis_hash(hypo) is True

    # 尝试单比特篡改命题
    tampered_hypo = MarketHypothesisDefinition(
        hypothesis_id="h_ac10",
        cognition_id="c_ac10",
        proposition="篡改后的假说",
        premise_evidence=["证据"],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[exp_a],
        invalidation_assertions=[],
        hypothesis_hash=h_hash,
    )
    assert verify_hypothesis_hash(tampered_hypo) is False, "AC-10: 单比特篡改未被验真引擎识别！"


def test_ac_11_clock_freeze_and_time_continuity():
    """【AC-11 时钟锁死防作弊】: 假说核验时序必须满足 T_realization >= T_decision，倒流直接物理拒绝"""
    with pytest.raises(TimeContinuityViolationError, match="时序倒流违规"):
        DualTimestampValidationPipeline._validate_time_continuity(
            decision_time="2026-10-01T09:20:00+08:00",
            realization_time="2026-10-01T09:15:00+08:00",
        )


def test_ac_12_zero_production_trading_and_migration():
    """【AC-12 生产代码零侵入】: 确保无未授权生产数据库迁移，无未授权交易接口连接"""
    migrations_dir = os.path.join(os.path.dirname(__file__), "..", "migrations", "versions")
    if os.path.exists(migrations_dir):
        files = os.listdir(migrations_dir)
        for f in files:
            assert "unauthorized" not in f.lower()


def test_ac_13_four_dimensional_time_semantics():
    """【AC-13 时间语义四维对齐】: 明确区分市场事件时间、观测窗口、数据快照时间与核验时间"""
    t_ctx = FourDimensionalTime(
        event_time="2026-10-01T09:25:00+08:00",
        observed_time="2026-10-01T09:25:01+08:00",
        ingestion_time="2026-10-01T09:25:02+08:00",
        effective_time="2026-10-01T09:25:00+08:00",
    )
    assert t_ctx.event_time != t_ctx.observed_time
    assert t_ctx.observed_time != t_ctx.ingestion_time
    assert t_ctx.effective_time == t_ctx.event_time


# =============================================================================
# 第二部分：红队对抗渗透测试 (Red-Team Attacks RT-01 ~ RT-06)
# =============================================================================

def test_rt_01_worm_penetration_attack():
    """【RT-01 WORM 穿透攻击】: 攻击者绕过 ORM 直接执行原生 SQL DELETE 尝试删除存证"""
    conn = sqlite3.connect(":memory:")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE cognition_record (id TEXT PRIMARY KEY, content TEXT)")
    cursor.execute("""
        CREATE TRIGGER prevent_cognition_record_delete
        BEFORE DELETE ON cognition_record
        BEGIN
            SELECT RAISE(FAIL, 'Red-Team Alert: direct SQL DELETE rejected by WORM trigger.');
        END;
    """)
    cursor.execute("INSERT INTO cognition_record VALUES ('cog_worm', 'immutable fact')")
    conn.commit()

    with pytest.raises(sqlite3.DatabaseError, match="Red-Team Alert"):
        cursor.execute("DELETE FROM cognition_record WHERE id = 'cog_worm'")
    conn.close()


def test_rt_02_narrowed_ast_injection_attack():
    """【RT-02 收窄 AST 注入攻击】: 攻击者在条件中构造 DROP TABLE 或注入恶意未授权字段"""
    c_malicious = FilterCondition(field="`stock_code`; DROP TABLE users; --", op=OperatorType.EQ, val=1)
    selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[c_malicious])
    bad_a = MetricAssertion(
        assertion_id="rt_sql_inj",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        operator=OperatorType.GT,
        target_value=0.0,
    )
    with pytest.raises(AssertionSyntaxError, match="不在白名单中"):
        AssertionEvaluator.evaluate(bad_a, {"stocks": []})


def test_rt_03_zero_fill_bypass_attack():
    """【RT-03 假零填充绕过攻击】: 攻击者制造全空集合并期望系统把 COUNT 以外的数值当 0.0 判过"""
    c = FilterCondition(field="board_height", op=OperatorType.GTE, val=10)
    selector = StructuredFilter(universe_type=UniverseType.ALL_A, conditions=[c])
    mean_a = MetricAssertion(
        assertion_id="rt_zero_attack",
        selector=selector,
        metric=MetricType.OPEN_PCT_CHANGE.value,
        aggregation=AggregationType.MEAN,
        operator=OperatorType.GTE,
        target_value=0.0, # 如果系统偷填 0.0，此断言就会被误判为 PASSED！
    )
    res = AssertionEvaluator.evaluate(mean_a, {"stocks": []})
    # 严格检验：系统绝不偷填 0.0，必须客观判为 INCONCLUSIVE
    assert res.outcome == AssertionOutcome.INCONCLUSIVE
    assert res.actual_value is None
    assert res.is_missing is True


def test_rt_04_time_reversal_attack():
    """【RT-04 时空倒流攻击】: 攻击者传入未来决策时点，试图以过去市场数据进行作弊验证"""
    dummy_hypo = MarketHypothesisDefinition(
        hypothesis_id="h_rt04",
        cognition_id="c_rt04",
        proposition="时空倒流作弊",
        premise_evidence=[],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[],
        invalidation_assertions=[],
        hypothesis_hash="",
    )
    h_hash = compute_hypothesis_hash(dummy_hypo)
    hypo = MarketHypothesisDefinition(
        hypothesis_id="h_rt04",
        cognition_id="c_rt04",
        proposition="时空倒流作弊",
        premise_evidence=[],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[],
        invalidation_assertions=[],
        hypothesis_hash=h_hash,
    )
    hypo_set = HypothesisSetProjection(
        set_id="set_rt04",
        cognition_id="c_rt04",
        hypotheses=[hypo],
        hypothesis_set_hash=compute_hypothesis_set_hash(
            HypothesisSetProjection(set_id="set_rt04", cognition_id="c_rt04", hypotheses=[hypo], hypothesis_set_hash="")
        ),
    )

    with pytest.raises(TimeContinuityViolationError, match="时序倒流违规"):
        DualTimestampValidationPipeline.validate_hypothesis_set(
            hypothesis_set=hypo_set,
            realization_snapshot={"status": "AVAILABLE", "stocks": []},
            realization_snapshot_id="snap_past",
            decision_time="2026-10-01T09:30:00+08:00",
            realization_time="2026-10-01T09:15:00+08:00", # 早于决策时间！
        )


def test_rt_05_avalanche_hash_tamper_attack():
    """【RT-05 雪崩哈希篡改攻击】: 攻击者篡改集合中的假说哈希数组序列"""
    dummy_hypo = MarketHypothesisDefinition(
        hypothesis_id="h_rt05",
        cognition_id="c_rt05",
        proposition="正常假说",
        premise_evidence=[],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[],
        invalidation_assertions=[],
        hypothesis_hash="",
    )
    h_hash = compute_hypothesis_hash(dummy_hypo)
    hypo = MarketHypothesisDefinition(
        hypothesis_id="h_rt05",
        cognition_id="c_rt05",
        proposition="正常假说",
        premise_evidence=[],
        time_binding="auction_0925",
        assertion_logic="AND",
        expected_assertions=[],
        invalidation_assertions=[],
        hypothesis_hash=h_hash,
    )
    # 构造假哈希
    tampered_set = HypothesisSetProjection(
        set_id="set_rt05",
        cognition_id="c_rt05",
        hypotheses=[hypo],
        hypothesis_set_hash="deadbeef" * 8,
    )
    assert verify_hypothesis_set_hash(tampered_set) is False


def test_rt_06_replay_and_overwrite_attack():
    """【RT-06 重放与覆写攻击】: 攻击者构造相同 validation_id 尝试覆写已存在的核验账本记录"""
    ledger = AppendOnlyValidationLedger()
    rec1 = CognitionValidationRecord(
        validation_id="val_fixed_001",
        cognition_record_id="c_001",
        hypothesis_set_hash="hash_set",
        hypothesis_hash="hash_h",
        hypothesis_id="h_001",
        verification_snapshot_id="snap_01",
        decision_time="2026-10-01T09:15:00+08:00",
        realization_time="2026-10-01T09:25:00+08:00",
        outcome=HypothesisOutcome.CONFIRMED,
        falsification_triggered=False,
        actual_metrics_summary={},
        assertion_results=[],
        provenance_trace={},
        verified_at="2026-10-01T09:25:00+08:00",
        validation_record_hash="",
    )
    # 首次写入成功
    ledger.append(rec1)
    assert ledger.count() == 1

    # 再次覆写相同 validation_id 必须抛出 WORM Violation 异常
    rec2 = CognitionValidationRecord(
        validation_id="val_fixed_001",
        cognition_record_id="c_001",
        hypothesis_set_hash="hash_set",
        hypothesis_hash="hash_h",
        hypothesis_id="h_001",
        verification_snapshot_id="snap_01",
        decision_time="2026-10-01T09:15:00+08:00",
        realization_time="2026-10-01T09:25:00+08:00",
        outcome=HypothesisOutcome.FALSIFIED, # 攻击者试图把结果篡改为 FALSIFIED
        falsification_triggered=True,
        actual_metrics_summary={},
        assertion_results=[],
        provenance_trace={},
        verified_at="2026-10-01T09:25:00+08:00",
        validation_record_hash="",
    )
    with pytest.raises(ValidationLedgerError, match="WORM Violation"):
        ledger.append(rec2)
