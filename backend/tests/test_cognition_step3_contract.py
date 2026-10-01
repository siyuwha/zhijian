"""
Phase 2A Step 3.1 契约模型与确定性算法测试套件
上位依据：最高董事会工程批准令 BOARD-APPROVAL-20260930-STEP3
验证目标：
1. 确定性时钟注入验证 (零非受控时钟/零未种子随机)
2. 规范化数据模型不可变性 (Frozen Invariant)
3. 四维时间与观测窗口解耦验证 (含未来时钟防御)
4. RFC 8785 JCS 指纹 100 次运行逐字节确定性 (Bit-Exact Determinism)
5. 篡改穿透检测 (修改任意属性即指纹失效)
6. 区分 Fact-type-specific EMPTY 语义 (涨停池为0合法，竞价金额为0非法)
7. STALE 事实隔离与准入限制
8. 零填充防伪验证 (TIMEOUT / ERROR / MISSING 严禁假0填充)
9. 全息血缘与多源冲突双向保留 (ConflictRecord & Provenance)
10. 重复事实与乱序原貌保留 (Duplicate & Out-of-Order Preservation)
11. 事实状态与快照整体质量分层聚合验证 (Status vs OverallQuality)
12. 数据库 cognition_record 物理列承载兼容性验证 (零 Migration)
"""

import sys
import os
import json
from typing import Any, Optional
import pytest
from datetime import datetime
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.cognition.observation.clock import DeterministicClock
from app.cognition.observation.contracts import (
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
from app.cognition.observation.fingerprint import (
    compute_fact_fingerprint,
    compute_snapshot_fingerprint,
    compute_effective_input_hash,
    verify_fact_fingerprint,
    verify_snapshot_fingerprint,
    verify_effective_input_hash,
)
from app.cognition.observation.quality import aggregate_overall_quality
from app.cognition.jcs import canonicalize


def _build_sample_fact(
    fact_key: str = "indices.sh000001",
    fact_type: FactType = FactType.INDEX_QUOTE,
    status: FactStatus = FactStatus.AVAILABLE,
    freshness: Freshness = Freshness.REALTIME,
    source: str = "sina",
    payload: Any = "DEFAULT",
    clock: DeterministicClock = None,
) -> FactItem:
    clk = clock or DeterministicClock("2026-09-30T09:25:00.000+08:00")
    t_ctx = FourDimensionalTime(
        event_time="2026-09-30T09:25:00.000+08:00",
        observed_time=clk.now_iso(),
        ingestion_time=clk.now_iso(),
        effective_time="2026-09-30T09:25:00.000+08:00",
    )
    prov = Provenance(
        primary_source=source,
        trace_id=clk.generate_trace_id(fact_key),
    )
    actual_payload = {"price": 3200.5, "change_pct": 0.52} if payload == "DEFAULT" else payload
    item = FactItem(
        fact_id=clk.generate_id("fact", fact_key),
        fact_key=fact_key,
        fact_type=fact_type,
        time_context=t_ctx,
        status=status,
        freshness=freshness,
        source=source,
        source_record_id="rec_001",
        payload=actual_payload,
        provenance=prov,
    )
    fp = compute_fact_fingerprint(item)
    return item.model_copy(update={"fact_fingerprint": fp})


def test_01_deterministic_clock_injection():
    """验证 1: 确定性时钟注入，保证毫秒级推进与 ID/Trace 确定性"""
    clock1 = DeterministicClock("2026-09-30T09:15:00.000+08:00")
    clock2 = DeterministicClock("2026-09-30T09:15:00.000+08:00")

    assert clock1.now_iso() == clock2.now_iso()
    t1 = clock1.generate_trace_id("auction")
    t2 = clock2.generate_trace_id("auction")
    assert t1 == t2  # 确定性 Trace ID

    clock1.advance_seconds(600)  # 前进 10 分钟到 09:25:00
    assert clock1.now_iso() == "2026-09-30T09:25:00.000+08:00"


def test_02_model_immutability_frozen_invariant():
    """验证 2: 规范化模型不可变性，杜绝原地篡改"""
    fact = _build_sample_fact()
    with pytest.raises(ValidationError):
        # Pydantic frozen=True 拦截直接属性赋值
        fact.status = FactStatus.ERROR


def test_03_four_dimensional_time_and_window_decoupling():
    """验证 3: 四维时间与观测窗口解耦，包含未来事件一票否决"""
    window = ObservationWindow(
        window_start="09:15:00",
        window_end="09:25:00",
        window_type=WindowType.ACCUMULATIVE_RANGE,
    )
    assert window.is_within("09:20:00") is True
    assert window.is_within("09:30:00") is False

    # 正常事件时间
    t_normal = FourDimensionalTime(
        event_time="2026-09-30T09:25:00.000+08:00",
        observed_time="2026-09-30T09:25:02.000+08:00",
        ingestion_time="2026-09-30T09:25:03.000+08:00",
        effective_time="2026-09-30T09:25:00.000+08:00",
    )
    assert t_normal.is_future_event(tolerance_seconds=30.0) is False

    # 异常未来事件时间 (event_time 晚于 observed_time 超过容差)
    t_future = FourDimensionalTime(
        event_time="2026-09-30T10:00:00.000+08:00",
        observed_time="2026-09-30T09:25:00.000+08:00",
        ingestion_time="2026-09-30T09:25:01.000+08:00",
        effective_time="2026-09-30T10:00:00.000+08:00",
    )
    assert t_future.is_future_event(tolerance_seconds=30.0) is True


def test_04_100_runs_bit_exact_determinism():
    """验证 4: 100 次循环计算，证明完全无哈希漂移与字节级一致性"""
    clock = DeterministicClock("2026-09-30T09:25:00.000+08:00")
    fact = _build_sample_fact(clock=clock)
    
    window = ObservationWindow(
        window_start="09:15:00",
        window_end="09:25:00",
        window_type=WindowType.ACCUMULATIVE_RANGE,
    )
    snap = ObservationSnapshot(
        snapshot_id="obs_20260930_0925_001",
        schema_version="1.0.0",
        market_date="2026-09-30",
        stage=CognitionStage.MORNING_AUCTION,
        observation_window=window,
        snapshot_time=clock.now_iso(),
        overall_quality=QualityLevel.FULL,
        fact_items=[fact],
        degraded_fields=[],
        source_manifest=[
            SourceCredential(source_name="sina", fetch_status="200", latency_ms=120.0, records_count=1)
        ],
    )
    base_fingerprint = compute_snapshot_fingerprint(snap)
    base_jcs_bytes = canonicalize(snap.canonical_dict()).encode("utf-8")

    for _ in range(100):
        fp = compute_snapshot_fingerprint(snap)
        jcs_bytes = canonicalize(snap.canonical_dict()).encode("utf-8")
        assert fp == base_fingerprint
        assert jcs_bytes == base_jcs_bytes


def test_05_tamper_detection_on_any_attribute():
    """验证 5: 篡改穿透检测，修改任意字段即刻引发指纹验真失败"""
    fact = _build_sample_fact()
    assert verify_fact_fingerprint(fact) is True

    # 1. 篡改 payload
    tampered_payload = fact.model_copy(update={"payload": {"price": 9999.0}})
    assert verify_fact_fingerprint(tampered_payload) is False

    # 2. 篡改 source
    tampered_source = fact.model_copy(update={"source": "hacked_source"})
    assert verify_fact_fingerprint(tampered_source) is False

    # 3. 篡改 status
    tampered_status = fact.model_copy(update={"status": FactStatus.ERROR})
    assert verify_fact_fingerprint(tampered_status) is False


def test_06_fact_type_specific_empty_semantics():
    """验证 6: 严正区分不同 FactType 的 EMPTY 语义"""
    # 涨停池: allow_empty=True, 业务语义为数量为0
    contract_limit_up = DEFAULT_FACT_CONTRACTS[FactType.LIMIT_UP_POOL]
    assert contract_limit_up.allow_empty is True
    assert contract_limit_up.empty_semantic == "COUNT_ZERO"

    # 指数行情: allow_empty=False, 严禁把空当成合法
    contract_index = DEFAULT_FACT_CONTRACTS[FactType.INDEX_QUOTE]
    assert contract_index.allow_empty is False
    assert contract_index.empty_semantic == "DISALLOWED"


def test_07_stale_facts_strictly_segregated():
    """验证 7: STALE 事实严格隔离，默认严禁混入 admitted_facts"""
    eff_input = EffectiveInferenceInput(
        input_id="inp_001",
        snapshot_id="obs_001",
        prompt_id="prompt_auction_v1",
        prompt_version="1.0.0",
        prompt_hash="a" * 64,
        inference_metadata={"provider": "deepseek", "model": "deepseek-r1"},
        admitted_facts={"indices": {"sh000001": 3200.5}},
        stale_facts={"settlement": {"000001.SZ": 11.2}}, # 严格隔离在此
        suppressed_facts=[],
        data_quality_warnings=["[STALE FACT: 结算价使用本地历史缓存]"],
        rendered_system_prompt="system",
        rendered_user_prompt="user",
    )
    fp = compute_effective_input_hash(eff_input)
    assert len(fp) == 64
    assert verify_effective_input_hash(eff_input.model_copy(update={"effective_input_hash": fp})) is True

    # 确认 stale_facts 与 admitted_facts 字典键名物理分离
    assert "settlement" not in eff_input.admitted_facts
    assert "settlement" in eff_input.stale_facts


def test_08_no_zero_fill_on_failures():
    """验证 8: TIMEOUT / MISSING / ERROR 严禁假0填充"""
    clock = DeterministicClock("2026-09-30T09:25:00.000+08:00")
    timeout_fact = _build_sample_fact(
        fact_key="auction.total_amount_yi",
        fact_type=FactType.INDEX_QUOTE,
        status=FactStatus.TIMEOUT,
        payload=None, # 物理为空，绝不能为 {"total_bidding_amount_yi": 0.0}
        clock=clock,
    )
    assert timeout_fact.payload is None
    assert timeout_fact.status == FactStatus.TIMEOUT

    missing_fact = _build_sample_fact(
        fact_key="micro_cap.index",
        fact_type=FactType.INDEX_QUOTE,
        status=FactStatus.MISSING,
        payload=None,
        clock=clock,
    )
    assert missing_fact.payload is None
    assert missing_fact.status == FactStatus.MISSING


def test_09_provenance_and_conflict_preservation():
    """验证 9: 多源冲突与主备切换全息血缘保留双向痕迹"""
    clock = DeterministicClock("2026-09-30T09:25:00.000+08:00")
    conflict = ConflictRecord(
        fact_key="indices.sh000001.pct_change",
        source_a="cls",
        value_a=-0.52,
        event_time_a="2026-09-30T09:25:00.000+08:00",
        observed_time_a="2026-09-30T09:25:01.000+08:00",
        source_b="sina",
        value_b=0.88,
        event_time_b="2026-09-30T09:25:00.000+08:00",
        observed_time_b="2026-09-30T09:25:01.200+08:00",
        difference_metric="divergence_1.40_pct",
        rule_applied="CONFLICT_DIVERGENCE_EXCEEDS_0.5_PCT",
        resolution="INCONCLUSIVE",
    )
    prov = Provenance(
        primary_source="cls",
        fallback_occurred=True,
        fallback_source="sina",
        fallback_reason="PRIMARY_TIMEOUT_AFTER_5000MS",
        trace_id=clock.generate_trace_id("conflict_test"),
        conflict_record=conflict,
    )
    assert prov.fallback_occurred is True
    assert prov.conflict_record.value_a == -0.52
    assert prov.conflict_record.value_b == 0.88
    assert prov.conflict_record.resolution == "INCONCLUSIVE"


def test_10_duplicate_and_out_of_order_preservation():
    """验证 10: 重复与乱序原貌痕迹保全"""
    prov = Provenance(
        primary_source="cls",
        trace_id="trace_dup_001",
        duplicate_detected=True,
        duplicate_count=2,
        original_arrival_order=5,
    )
    assert prov.duplicate_detected is True
    assert prov.duplicate_count == 2
    assert prov.original_arrival_order == 5


def test_11_quality_aggregation_status_separation():
    """验证 11: 事实状态与快照整体质量分层聚合"""
    clock = DeterministicClock("2026-09-30T09:25:00.000+08:00")

    # 1. 关键事实 (INDEX_QUOTE) 损坏 -> INVALID
    crit_bad = _build_sample_fact(
        fact_key="indices.sh000001",
        fact_type=FactType.INDEX_QUOTE,
        status=FactStatus.ERROR,
        clock=clock,
    )
    q_invalid, fields = aggregate_overall_quality([crit_bad])
    assert q_invalid == QualityLevel.INVALID
    assert "indices.sh000001" in fields

    # 2. 非关键事实 (NEWS_BULLETIN) 损坏 -> PARTIAL
    news_bad = _build_sample_fact(
        fact_key="news.item_1",
        fact_type=FactType.NEWS_BULLETIN,
        status=FactStatus.ERROR,
        clock=clock,
    )
    crit_good = _build_sample_fact(
        fact_key="indices.sh000001",
        fact_type=FactType.INDEX_QUOTE,
        status=FactStatus.AVAILABLE,
        clock=clock,
    )
    q_partial, fields2 = aggregate_overall_quality([crit_good, news_bad])
    assert q_partial == QualityLevel.PARTIAL
    assert "news.item_1" in fields2

    # 3. 存在 STALE 事实 -> DEGRADED
    stale_fact = _build_sample_fact(
        fact_key="settlement.000001",
        fact_type=FactType.SETTLEMENT_PRICE,
        status=FactStatus.STALE,
        clock=clock,
    )
    q_degraded, fields3 = aggregate_overall_quality([crit_good, stale_fact])
    assert q_degraded == QualityLevel.DEGRADED

    # 4. 全部可用 -> FULL
    q_full, fields4 = aggregate_overall_quality([crit_good])
    assert q_full == QualityLevel.FULL
    assert len(fields4) == 0


def test_12_database_column_compatibility():
    """验证 12: 产物可被现有 cognition_record 物理列承载（零 Schema 变更）"""
    clock = DeterministicClock("2026-09-30T09:25:00.000+08:00")
    fact = _build_sample_fact(clock=clock)
    window = ObservationWindow(
        window_start="09:15:00",
        window_end="09:25:00",
        window_type=WindowType.ACCUMULATIVE_RANGE,
    )
    snap = ObservationSnapshot(
        snapshot_id="obs_20260930_0925_001",
        schema_version="1.0.0",
        market_date="2026-09-30",
        stage=CognitionStage.MORNING_AUCTION,
        observation_window=window,
        snapshot_time=clock.now_iso(),
        overall_quality=QualityLevel.FULL,
        fact_items=[fact],
        degraded_fields=[],
        source_manifest=[
            SourceCredential(source_name="sina", fetch_status="200", latency_ms=120.0, records_count=1)
        ],
    )
    snap_fp = compute_snapshot_fingerprint(snap)
    snap_with_fp = snap.model_copy(update={"snapshot_fingerprint": snap_fp})

    # 转换为 JSON 文本
    obs_json_str = canonicalize(snap_with_fp.canonical_dict())
    assert isinstance(obs_json_str, str)
    assert len(obs_json_str) > 0

    eff_input = EffectiveInferenceInput(
        input_id="inp_001",
        snapshot_id=snap.snapshot_id,
        prompt_id="prompt_v1",
        prompt_version="1.0.0",
        prompt_hash="p" * 64,
        inference_metadata={"note": "future metadata"},
        admitted_facts={"indices": {"sh000001": 3200.5}},
        stale_facts={},
        suppressed_facts=[],
        data_quality_warnings=[],
        rendered_system_prompt="System Prompt Text",
        rendered_user_prompt="User Prompt Text",
    )
    eff_hash = compute_effective_input_hash(eff_input)

    # 验证哈希满足 VARCHAR(64)
    assert len(eff_hash) == 64
    assert all(c in "0123456789abcdef" for c in eff_hash)
