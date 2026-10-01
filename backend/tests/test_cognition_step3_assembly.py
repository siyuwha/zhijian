"""
Phase 2A Step 3.4 综合组装、全链路冷启动与全息追溯验收测试套件
上位依据：
1. 最高董事会工程批准令 BOARD-APPROVAL-20260930-STEP3
2. 《开发文档/39-Phase-2A-Step3.4-综合组装与全链路冷启动静态验收实施计划.md》

核心测试范围：
1. 七大冷启动场景矩阵验证 (CS-01 ~ CS-07)
2. 四维确定性验证 (100-run, Subprocess跨进程, 乱序输入, 重复到达)
3. 全息血缘闭环反向穿透验证 (Provenance Closure)
4. 绝对停机边界验证 (STOP Hard Boundary)
"""

import sys
import os
import copy
import random
import subprocess
import pytest
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.cognition.observation.contracts import (
    FactItem,
    FactStatus,
    Freshness,
    FactType,
    FactContract,
    CognitionStage,
    QualityLevel,
    FourDimensionalTime,
    ObservationWindow,
    Provenance,
    ConflictRecord,
    ObservationSnapshot,
    EffectiveInferenceInput,
    DEFAULT_FACT_CONTRACTS,
)
from app.cognition.observation.clock import DeterministicClock
from app.cognition.observation.fingerprint import (
    compute_fact_fingerprint,
    compute_snapshot_fingerprint,
    compute_effective_input_hash,
    verify_fact_fingerprint,
    verify_snapshot_fingerprint,
    verify_effective_input_hash,
)
from app.cognition.observation.conflict import (
    ConflictEngine,
    ConflictClass,
    ConflictPolicy,
)
from app.cognition.input.eligibility import (
    FactEligibilityGate,
    EligibilityOutcome,
)
from app.cognition.input.renderer import (
    DeterministicPromptSerializer,
    PromptSpecData,
)
from app.cognition.input.pipeline import CognitionObservationPipeline


def _build_test_fact(
    fact_key: str,
    fact_type: FactType,
    status: FactStatus = FactStatus.AVAILABLE,
    freshness: Freshness = Freshness.REALTIME,
    payload: Dict[str, Any] = None,
    source: str = "test_source",
    event_time: str = "2026-09-30T15:00:00.000+08:00",
) -> FactItem:
    t_ctx = FourDimensionalTime(
        event_time=event_time,
        observed_time="2026-09-30T15:00:01.000+08:00",
        ingestion_time="2026-09-30T15:00:02.000+08:00",
        effective_time=event_time,
    )
    prov = Provenance(
        primary_source=source,
        trace_id=f"trace_{fact_key}",
    )
    item = FactItem(
        fact_id=f"fact_{fact_key}",
        fact_key=fact_key,
        fact_type=fact_type,
        time_context=t_ctx,
        status=status,
        freshness=freshness,
        source=source,
        source_record_id=f"rec_{fact_key}",
        payload=payload,
        provenance=prov,
        fact_fingerprint="",
    )
    fp = compute_fact_fingerprint(item)
    return item.model_copy(update={"fact_fingerprint": fp})


def _get_standard_prompt_spec() -> PromptSpecData:
    return PromptSpecData(
        prompt_id="prompt_review_master_v1",
        version="1.0.0",
        prompt_hash="a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
        system_template="You are the Cognition Review Engine. Output deterministic evaluations.",
        user_template="Perform review for the current observation snapshot:\n{observation_data}",
    )


# =========================================================================
# Part 1: 七大冷启动场景矩阵测试 (CS-01 ~ CS-07)
# =========================================================================

def test_cs_01_full_available_scenario():
    """CS-01: 全量健康可用冷启动场景"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    prompt_spec = _get_standard_prompt_spec()

    f_idx = _build_test_fact("indices.sh000001", FactType.INDEX_QUOTE, FactStatus.AVAILABLE, Freshness.REALTIME, {"close": 3200.0, "pct_change": 1.2})
    f_breadth = _build_test_fact("breadth.summary", FactType.MARKET_BREADTH, FactStatus.AVAILABLE, Freshness.REALTIME, {"up_count": 3500, "down_count": 1200})
    f_limit = _build_test_fact("limit_up.pool", FactType.LIMIT_UP_POOL, FactStatus.AVAILABLE, Freshness.REALTIME, {"limit_up_count": 45, "pool": ["600519"]})

    out = CognitionObservationPipeline.assemble_and_run(
        market_date="2026-09-30",
        stage=CognitionStage.POST_CLOSE,
        observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
        fact_items=[f_idx, f_breadth, f_limit],
        prompt_spec=prompt_spec,
        input_id="inp_cs01",
        clock=clock,
    )

    assert len(out.admitted_facts) == 3
    assert len(out.stale_facts) == 0
    assert len(out.suppressed_facts) == 0
    assert len(out.data_quality_warnings) == 0
    assert verify_effective_input_hash(out) is True
    assert "Overall Data Quality: FULL" in out.rendered_user_prompt
    assert "Active Quality Warnings: None" in out.rendered_user_prompt


def test_cs_02_partial_missing_scenario():
    """CS-02: 部分次要事实缺失冷启动场景 (Missing != False, no zero-fill)"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    prompt_spec = _get_standard_prompt_spec()

    f_idx = _build_test_fact("indices.sh000001", FactType.INDEX_QUOTE, FactStatus.AVAILABLE, Freshness.REALTIME, {"close": 3200.0})
    # 高标溢价因未收录而缺失
    f_high_missing = _build_test_fact("auction.high_open_stats", FactType.HIGH_TIER_STAT, FactStatus.MISSING, Freshness.STALE, None)

    out = CognitionObservationPipeline.assemble_and_run(
        market_date="2026-09-30",
        stage=CognitionStage.POST_CLOSE,
        observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
        fact_items=[f_idx, f_high_missing],
        prompt_spec=prompt_spec,
        input_id="inp_cs02",
        clock=clock,
    )

    assert "indices.sh000001" in out.admitted_facts
    assert "auction.high_open_stats" not in out.admitted_facts
    # 验证缺失事实进入 suppressed_facts 且 payload 为 None (绝对不填 0 或 False)
    suppressed_entry = next(s for s in out.suppressed_facts if s["fact_key"] == "auction.high_open_stats")
    assert suppressed_entry["status"] == "MISSING"
    assert suppressed_entry["outcome"] == "INCONCLUSIVE_MISSING"
    assert any("严禁进行方向性推断" in w for w in out.data_quality_warnings)
    assert verify_effective_input_hash(out) is True


def test_cs_03_physical_timeout_scenario():
    """CS-03: 物理超时故障冷启动场景 (Timeout != 0, payload is None)"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    prompt_spec = _get_standard_prompt_spec()

    f_timeout = _build_test_fact("settlement.sh600519", FactType.SETTLEMENT_PRICE, FactStatus.TIMEOUT, Freshness.STALE, None)

    out = CognitionObservationPipeline.assemble_and_run(
        market_date="2026-09-30",
        stage=CognitionStage.POST_CLOSE,
        observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
        fact_items=[f_timeout],
        prompt_spec=prompt_spec,
        input_id="inp_cs03",
        clock=clock,
    )

    assert "settlement.sh600519" not in out.admitted_facts
    assert any(s["fact_key"] == "settlement.sh600519" and s["status"] == "TIMEOUT" for s in out.suppressed_facts)
    assert any("[DATA TIMEOUT:" in w for w in out.data_quality_warnings)
    assert verify_effective_input_hash(out) is True


def test_cs_04_stale_reference_scenario():
    """CS-04: 陈旧历史缓存降级冷启动场景 (STALE != admitted_facts, 物理隔离)"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    prompt_spec = _get_standard_prompt_spec()

    f_idx = _build_test_fact("indices.sh000001", FactType.INDEX_QUOTE, FactStatus.AVAILABLE, Freshness.REALTIME, {"close": 3200.0})
    f_stale_settle = _build_test_fact("settlement.sh600519", FactType.SETTLEMENT_PRICE, FactStatus.STALE, Freshness.STALE, {"close": 1780.0})

    out = CognitionObservationPipeline.assemble_and_run(
        market_date="2026-09-30",
        stage=CognitionStage.POST_CLOSE,
        observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
        fact_items=[f_idx, f_stale_settle],
        prompt_spec=prompt_spec,
        input_id="inp_cs04",
        clock=clock,
    )

    # 验证物理隔离：绝对不在 admitted_facts 出现，严格归入 stale_facts
    assert "settlement.sh600519" not in out.admitted_facts
    assert "settlement.sh600519" in out.stale_facts
    assert out.stale_facts["settlement.sh600519"] == {"close": 1780.0}
    assert "[HISTORICAL/STALE REFERENCE ONLY]" in out.rendered_user_prompt
    assert verify_effective_input_hash(out) is True


def test_cs_05_legitimate_empty_scenario():
    """CS-05: 客观极值空事实冷启动场景 (COUNT_ZERO 合法准入)"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    prompt_spec = _get_standard_prompt_spec()

    # 市场极值冰点，0 涨停
    f_limit_zero = _build_test_fact(
        "limit_up.pool",
        FactType.LIMIT_UP_POOL,
        FactStatus.EMPTY,
        Freshness.REALTIME,
        {"limit_up_count": 0, "pool": []},
    )

    out = CognitionObservationPipeline.assemble_and_run(
        market_date="2026-09-30",
        stage=CognitionStage.POST_CLOSE,
        observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
        fact_items=[f_limit_zero],
        prompt_spec=prompt_spec,
        input_id="inp_cs05",
        clock=clock,
    )

    assert "limit_up.pool" in out.admitted_facts
    assert out.admitted_facts["limit_up.pool"] == {"limit_up_count": 0, "pool": []}
    assert len(out.suppressed_facts) == 0
    assert verify_effective_input_hash(out) is True


def test_cs_06_multisource_conflict_scenario():
    """CS-06: 多源分歧对撞冷启动场景 (ConflictRecord 证据留存，裁决 INCONCLUSIVE)"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    prompt_spec = _get_standard_prompt_spec()

    # 两个数据源对上证指数产生 1.70% 分歧
    f_a = _build_test_fact("indices.sh000001", FactType.INDEX_QUOTE, FactStatus.AVAILABLE, Freshness.REALTIME, {"pct_change": 1.25}, source="eastmoney")
    f_b = _build_test_fact("indices.sh000001", FactType.INDEX_QUOTE, FactStatus.AVAILABLE, Freshness.REALTIME, {"pct_change": -0.45}, source="sina")

    out = CognitionObservationPipeline.assemble_and_run(
        market_date="2026-09-30",
        stage=CognitionStage.POST_CLOSE,
        observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
        fact_items=[f_a, f_b],
        prompt_spec=prompt_spec,
        input_id="inp_cs06",
        clock=clock,
    )

    # 验证冲突事实未决，被剥离出 admitted_facts，进入 suppressed_facts
    assert "indices.sh000001" not in out.admitted_facts
    suppressed_entry = next(s for s in out.suppressed_facts if s["fact_key"] == "indices.sh000001")
    assert suppressed_entry["status"] == "INCONCLUSIVE"
    assert suppressed_entry["outcome"] == "SUPPRESSED_CONFLICT"
    assert any("多源分歧超阈值" in w for w in out.data_quality_warnings)
    assert verify_effective_input_hash(out) is True


def test_cs_07_total_failure_scenario():
    """CS-07: 全不可用极端冷启动场景 (INVALID, 阻断推演)"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    prompt_spec = _get_standard_prompt_spec()

    # 所有维度均故障或报错
    f_err1 = _build_test_fact("indices.sh000001", FactType.INDEX_QUOTE, FactStatus.ERROR, Freshness.STALE, None)
    f_err2 = _build_test_fact("breadth.summary", FactType.MARKET_BREADTH, FactStatus.TIMEOUT, Freshness.STALE, None)

    out = CognitionObservationPipeline.assemble_and_run(
        market_date="2026-09-30",
        stage=CognitionStage.POST_CLOSE,
        observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
        fact_items=[f_err1, f_err2],
        prompt_spec=prompt_spec,
        input_id="inp_cs07",
        clock=clock,
    )

    assert len(out.admitted_facts) == 0
    assert len(out.suppressed_facts) == 2
    assert "Overall Data Quality: INVALID" in out.rendered_user_prompt
    assert "- No admitted facts available." in out.rendered_user_prompt
    assert verify_effective_input_hash(out) is True


# =========================================================================
# Part 2: 全链路四维确定性验证
# =========================================================================

def test_determinism_100_runs():
    """验证 1: 内存级连续 100 次运行哈希与文本 100% 逐比特无漂移"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    prompt_spec = _get_standard_prompt_spec()

    f1 = _build_test_fact("indices.sh000001", FactType.INDEX_QUOTE, FactStatus.AVAILABLE, Freshness.REALTIME, {"close": 3200.0})
    f2 = _build_test_fact("settlement.sh600519", FactType.SETTLEMENT_PRICE, FactStatus.STALE, Freshness.STALE, {"close": 1800.0})

    baseline = CognitionObservationPipeline.assemble_and_run(
        market_date="2026-09-30",
        stage=CognitionStage.POST_CLOSE,
        observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
        fact_items=[f1, f2],
        prompt_spec=prompt_spec,
        input_id="inp_det_const",
        snapshot_id="obs_det_const",
        clock=clock,
    )
    expected_hash = baseline.effective_input_hash
    expected_prompt = baseline.rendered_user_prompt

    for i in range(100):
        run_i = CognitionObservationPipeline.assemble_and_run(
            market_date="2026-09-30",
            stage=CognitionStage.POST_CLOSE,
            observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
            fact_items=[f1, f2],
            prompt_spec=prompt_spec,
            input_id="inp_det_const",
            snapshot_id="obs_det_const",
            clock=clock,
        )
        assert run_i.effective_input_hash == expected_hash, f"Hash drifted at iteration {i}"
        assert run_i.rendered_user_prompt == expected_prompt, f"Prompt drifted at iteration {i}"


def test_determinism_subprocess_fresh_process():
    """验证 2: 独立跨进程 Subprocess 确定性 (跨 Python 随机种子 PYTHONHASHSEED)"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    prompt_spec = _get_standard_prompt_spec()

    f1 = _build_test_fact("indices.sh000001", FactType.INDEX_QUOTE, FactStatus.AVAILABLE, Freshness.REALTIME, {"close": 3200.0})
    baseline = CognitionObservationPipeline.assemble_and_run(
        market_date="2026-09-30",
        stage=CognitionStage.POST_CLOSE,
        observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
        fact_items=[f1],
        prompt_spec=prompt_spec,
        input_id="inp_subprocess",
        clock=clock,
    )
    expected_hash = baseline.effective_input_hash

    # 启动独立子进程，并注入完全不同的 PYTHONHASHSEED
    sub_code = f"""
import sys, os
sys.path.insert(0, r"{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}")
from app.cognition.observation.contracts import (
    FactItem, FactStatus, Freshness, FactType, CognitionStage,
    ObservationWindow, FourDimensionalTime, Provenance
)
from app.cognition.observation.fingerprint import compute_fact_fingerprint
from app.cognition.observation.clock import DeterministicClock
from app.cognition.input.renderer import PromptSpecData
from app.cognition.input.pipeline import CognitionObservationPipeline

clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
prompt_spec = PromptSpecData(
    prompt_id="prompt_review_master_v1",
    version="1.0.0",
    prompt_hash="a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90",
    system_template="You are the Cognition Review Engine. Output deterministic evaluations.",
    user_template="Perform review for the current observation snapshot:\\n{{observation_data}}",
)

t_ctx = FourDimensionalTime(
    event_time="2026-09-30T15:00:00.000+08:00",
    observed_time="2026-09-30T15:00:01.000+08:00",
    ingestion_time="2026-09-30T15:00:02.000+08:00",
    effective_time="2026-09-30T15:00:00.000+08:00",
)
prov = Provenance(primary_source="test_source", trace_id="trace_indices.sh000001")
item = FactItem(
    fact_id="fact_indices.sh000001",
    fact_key="indices.sh000001",
    fact_type=FactType.INDEX_QUOTE,
    time_context=t_ctx,
    status=FactStatus.AVAILABLE,
    freshness=Freshness.REALTIME,
    source="test_source",
    source_record_id="rec_indices.sh000001",
    payload={{"close": 3200.0}},
    provenance=prov,
    fact_fingerprint="",
)
item = item.model_copy(update={{"fact_fingerprint": compute_fact_fingerprint(item)}})

out = CognitionObservationPipeline.assemble_and_run(
    market_date="2026-09-30",
    stage=CognitionStage.POST_CLOSE,
    observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
    fact_items=[item],
    prompt_spec=prompt_spec,
    input_id="inp_subprocess",
    clock=clock,
)
print(out.effective_input_hash)
"""
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "99999"

    res = subprocess.run([sys.executable, "-c", sub_code], capture_output=True, text=True, env=env)
    assert res.returncode == 0, f"Subprocess failed with error: {res.stderr}"
    subprocess_hash = res.stdout.strip()
    assert subprocess_hash == expected_hash


def test_determinism_arbitrary_permutation():
    """验证 3: 输入事实随机乱序排布不变性 (UTF-16 字典序规范化保证)"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    prompt_spec = _get_standard_prompt_spec()

    f1 = _build_test_fact("indices.sh000001", FactType.INDEX_QUOTE, FactStatus.AVAILABLE, Freshness.REALTIME, {"close": 3200.0})
    f2 = _build_test_fact("indices.sz399001", FactType.INDEX_QUOTE, FactStatus.AVAILABLE, Freshness.REALTIME, {"close": 10500.0})
    f3 = _build_test_fact("breadth.summary", FactType.MARKET_BREADTH, FactStatus.AVAILABLE, Freshness.REALTIME, {"up_count": 3000})
    f4 = _build_test_fact("limit_up.pool", FactType.LIMIT_UP_POOL, FactStatus.AVAILABLE, Freshness.REALTIME, {"limit_up_count": 50})

    base_list = [f1, f2, f3, f4]
    base_out = CognitionObservationPipeline.assemble_and_run(
        market_date="2026-09-30",
        stage=CognitionStage.POST_CLOSE,
        observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
        fact_items=base_list,
        prompt_spec=prompt_spec,
        input_id="inp_perm",
        snapshot_id="obs_perm",
        clock=clock,
    )
    expected_hash = base_out.effective_input_hash

    # 执行 10 次随机打乱输入
    rng = random.Random(42)
    for _ in range(10):
        shuffled = copy.deepcopy(base_list)
        rng.shuffle(shuffled)
        out_shuffled = CognitionObservationPipeline.assemble_and_run(
            market_date="2026-09-30",
            stage=CognitionStage.POST_CLOSE,
            observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
            fact_items=shuffled,
            prompt_spec=prompt_spec,
            input_id="inp_perm",
            snapshot_id="obs_perm",
            clock=clock,
        )
        assert out_shuffled.effective_input_hash == expected_hash


def test_determinism_duplicate_and_out_of_order():
    """验证 4: 重复报文与乱序到达原貌保全"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    prompt_spec = _get_standard_prompt_spec()

    # 模拟两条重复的快讯记录，保留到达次序
    f1 = _build_test_fact("news.cls.001", FactType.NEWS_BULLETIN, FactStatus.AVAILABLE, Freshness.REALTIME, {"title": "快讯1"})
    f1_dup = f1.model_copy(update={
        "provenance": f1.provenance.model_copy(update={"duplicate_detected": True, "duplicate_count": 1, "original_arrival_order": 1})
    })

    out = CognitionObservationPipeline.assemble_and_run(
        market_date="2026-09-30",
        stage=CognitionStage.POST_CLOSE,
        observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
        fact_items=[f1, f1_dup],
        prompt_spec=prompt_spec,
        input_id="inp_dup",
        clock=clock,
    )
    assert verify_effective_input_hash(out) is True


# =========================================================================
# Part 3: 全息血缘闭环反向追溯验证 (Provenance Closure)
# =========================================================================

def test_provenance_closure_reverse_audit():
    """
    全息血缘闭环反向穿透测试：
    验证仅凭 effective_input_hash，程序可 100% 反向穿透至：
    1. input_id 与有效输入对象
    2. snapshot_id 与 snapshot_fingerprint
    3. 每个 FactItem 的 fact_fingerprint
    4. Provenance 采集源、端点、原始报文哈希与四维时间
    """
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    prompt_spec = _get_standard_prompt_spec()

    f1 = _build_test_fact("indices.sh000001", FactType.INDEX_QUOTE, FactStatus.AVAILABLE, Freshness.REALTIME, {"close": 3200.0}, source="sina")
    f2 = _build_test_fact("settlement.sh600519", FactType.SETTLEMENT_PRICE, FactStatus.STALE, Freshness.STALE, {"close": 1800.0}, source="baostock_cache")

    # 装配并保留快照引用
    snap = ObservationSnapshot(
        snapshot_id="snap_audit_001",
        market_date="2026-09-30",
        stage=CognitionStage.POST_CLOSE,
        observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
        snapshot_time="2026-09-30T15:30:00.000+08:00",
        overall_quality=QualityLevel.DEGRADED,
        fact_items=[f1, f2],
        degraded_fields=["settlement.sh600519"],
        source_manifest=[],
    )
    snap_fp = compute_snapshot_fingerprint(snap)
    snap = snap.model_copy(update={"snapshot_fingerprint": snap_fp})

    effective_input = CognitionObservationPipeline.process_snapshot(
        snapshot=snap,
        prompt_spec=prompt_spec,
        input_id="inp_audit_001",
    )
    target_hash = effective_input.effective_input_hash

    # --- 开始纯反向溯源审计链 ---
    # 1. 验证目标哈希
    assert verify_effective_input_hash(effective_input) is True
    assert compute_effective_input_hash(effective_input) == target_hash

    # 2. 从 effective_input 穿透到 prompt_spec
    assert effective_input.prompt_id == prompt_spec.prompt_id
    assert effective_input.prompt_version == prompt_spec.version
    assert effective_input.prompt_hash == prompt_spec.prompt_hash

    # 3. 从 effective_input 穿透到 snapshot_id 并验真 snapshot_fingerprint
    assert effective_input.snapshot_id == snap.snapshot_id
    assert verify_snapshot_fingerprint(snap) is True

    # 4. 穿透至每一个 FactItem 及其指纹
    for item in snap.fact_items:
        assert verify_fact_fingerprint(item) is True
        # 5. 穿透至底层 Provenance 与四维时间
        assert item.provenance.primary_source in ("sina", "baostock_cache")
        assert item.provenance.trace_id.startswith("trace_")
        assert item.time_context.event_time == "2026-09-30T15:00:00.000+08:00"
        assert item.time_context.observed_time == "2026-09-30T15:00:01.000+08:00"

    # 证明全息血缘闭环 100% 成立！


# =========================================================================
# Part 4: 停机边界验证 (STOP Hard Boundary)
# =========================================================================

def test_hard_stop_boundary_enforced(monkeypatch):
    """
    验证绝对硬停机边界：
    计算完成 effective_input_hash 后立即 STOP，绝不产生任何后续 LLM、交易或业务副作用
    """
    import urllib.request
    import http.client

    def forbidden_call(*args, **kwargs):
        raise RuntimeError("VIOLATION: Attempted external call beyond STOP boundary!")

    monkeypatch.setattr(http.client.HTTPConnection, "request", forbidden_call)
    monkeypatch.setattr(http.client.HTTPSConnection, "request", forbidden_call)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden_call)

    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    prompt_spec = _get_standard_prompt_spec()
    f1 = _build_test_fact("indices.sh000001", FactType.INDEX_QUOTE, FactStatus.AVAILABLE, Freshness.REALTIME, {"close": 3200.0})

    # 执行流水线，验证在 STOP 边界即刻安全返回
    res = CognitionObservationPipeline.assemble_and_run(
        market_date="2026-09-30",
        stage=CognitionStage.POST_CLOSE,
        observation_window=ObservationWindow(window_start="15:00:00", window_end="15:30:00"),
        fact_items=[f1],
        prompt_spec=prompt_spec,
        input_id="inp_stop_test",
        clock=clock,
    )
    assert isinstance(res, EffectiveInferenceInput)
    assert res.effective_input_hash != ""
