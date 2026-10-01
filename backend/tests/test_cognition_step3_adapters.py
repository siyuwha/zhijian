"""
Phase 2A Step 3.2 事实抽取适配器测试套件
上位依据：最高董事会工程授权令 BOARD-APPROVAL-20260930-STEP3
覆盖测试项目：
1. M1 盘后复盘适配器契约 (收盘指数、量能广度、涨停池与零涨停 EMPTY 语义)
2. M2 盘前宏观事实适配器契约 (客观事实提取，零观点加工)
3. M4 早盘竞价 09:25 时间契约 (时点严格锁定 09:25:00，竞价额缺失 MISSING 零填充防伪)
4. M5 结算价超时与缓存契约 (TIMEOUT / STALE 真实保留，零填充防伪)
5. S4 资讯双源与 Fallback Provenance (主备切换全息血缘双向保留)
6. 重复到达与乱序到达原貌保留 (Duplicate & Out-of-order Preservation)
7. 嵌套不可变防篡改网 (Nested Immutability Gate: 外部源对象变更对已生成事实零污染)
8. 快照构建器装配集成 (ObservationSnapshotBuilder 整体聚合与 JCS 验真)
"""

import sys
import os
import pytest
from datetime import datetime

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
    SourceCredential,
)
from app.cognition.observation.adapters import (
    M1ReviewFactAdapter,
    M2PremarketFactAdapter,
    M4AuctionFactAdapter,
    M5SettlementFactAdapter,
    S4NewsFactAdapter,
)
from app.cognition.observation.builder import ObservationSnapshotBuilder
from app.cognition.observation.fingerprint import (
    verify_fact_fingerprint,
    verify_snapshot_fingerprint,
)


def test_01_m1_adapter_contract():
    """验证 M1: 收盘指数、市场广度、涨停池及零涨停 EMPTY 语义"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    adapter = M1ReviewFactAdapter()

    # 1. 模拟包含指数与广度的完整复盘数据
    raw_m1 = {
        "date": "2026-09-30",
        "id": "m1_001",
        "indices": [
            {"code": "sh000001", "name": "上证指数", "price": 3250.0, "pct_change": 0.85, "amount_wan": 45000000.0},
            {"code": "sz399001", "name": "深证成指", "price": 10500.0, "pct_change": 1.20, "amount_wan": 55000000.0},
        ],
        "breadth": {
            "total_amount_yi": 10000.0,
            "up_count": 3500,
            "down_count": 1200,
            "flat_count": 300,
        },
        "limit_up": {
            "max_board_height": 5,
            "pool": [{"code": "000001", "name": "平安银行", "height": 1}],
        },
    }

    facts = adapter.extract_facts(raw_m1, clock=clock, trace_id="trace_m1_test")
    assert len(facts) >= 6  # 4 个指数(含 missing) + 1 个广度 + 1 个涨停池

    # 验证上证指数提取正确性
    sh_fact = next(f for f in facts if f.fact_key == "indices.sh000001")
    assert sh_fact.status == FactStatus.AVAILABLE
    assert sh_fact.payload["close"] == 3250.0
    assert sh_fact.time_context.event_time == "2026-09-30T15:00:00.000+08:00"
    assert verify_fact_fingerprint(sh_fact) is True

    # 验证未提供的指数 (如 sz399006) 显式置为 MISSING，且 payload 为 None (零填充防伪)
    cy_fact = next(f for f in facts if f.fact_key == "indices.sz399006")
    assert cy_fact.status == FactStatus.MISSING
    assert cy_fact.payload is None

    # 验证涨停池事实
    lu_fact = next(f for f in facts if f.fact_key == "limit_up.pool")
    assert lu_fact.status == FactStatus.AVAILABLE
    assert lu_fact.payload["limit_up_count"] == 1

    # 2. 验证零涨停时的合法 EMPTY 语义
    raw_m1_empty = {
        "date": "2026-09-30",
        "limit_up": {"max_board_height": 0, "pool": []},
    }
    empty_facts = adapter.extract_facts(raw_m1_empty, clock=clock, trace_id="trace_m1_empty")
    lu_empty_fact = next(f for f in empty_facts if f.fact_key == "limit_up.pool")
    assert lu_empty_fact.status == FactStatus.EMPTY
    assert lu_empty_fact.payload["limit_up_count"] == 0
    assert lu_empty_fact.payload["pool"] == []


def test_02_m2_adapter_contract():
    """验证 M2: 盘前宏观事实提取，零观点加工"""
    clock = DeterministicClock("2026-09-30T08:35:00.000+08:00")
    adapter = M2PremarketFactAdapter()

    raw_m2 = {
        "date": "2026-09-30",
        "id": "m2_001",
        "overnight_summary": [
            {"code": "ixic", "name": "纳斯达克", "price": 18000.0, "pct_change": 0.95},
            {"code": "a50", "name": "富时A50", "price": 13200.0, "pct_change": -0.15},
        ],
        "news_digest": [
            {"title": "外盘科技股普涨", "content": "美股三大指数集体收涨"},
        ],
        "today_focus": [
            {"dimension": "量能", "observation_point": "09:25 开盘量比"},
        ],
    }

    facts = adapter.extract_facts(raw_m2, clock=clock, trace_id="trace_m2_test")
    assert len(facts) == 3

    # 验证隔夜事实
    macro_fact = next(f for f in facts if f.fact_key == "macro.overnight")
    assert macro_fact.status == FactStatus.AVAILABLE
    assert len(macro_fact.payload["symbols"]) == 2
    assert macro_fact.time_context.event_time == "2026-09-30T08:30:00.000+08:00"

    # 验证新闻摘要纯文本事实
    news_fact = next(f for f in facts if f.fact_key == "macro.news_digest")
    assert news_fact.status == FactStatus.AVAILABLE
    assert news_fact.payload["items"][0]["title"] == "外盘科技股普涨"


def test_03_m4_0925_temporal_contract_and_no_zero_fill():
    """验证 M4: 09:25 时间契约，竞价额缺失时 MISSING 零填充防伪"""
    clock = DeterministicClock("2026-09-30T09:26:00.000+08:00")
    adapter = M4AuctionFactAdapter()

    # 1. 正常竞价数据
    raw_m4 = {
        "date": "2026-09-30",
        "id": "m4_001",
        "index_open_data": {
            "indices": [{"code": "sh000001", "price": 3210.0, "amount_wan": 25000.0}],
            "total_bidding_amount_yi": 45.2,
            "yesterday_total_amount_yi": 10000.0,
            "bidding_volume_ratio": 0.45,
        },
        "high_open_stats": {
            "high_open_ratio": 65.5,
            "avg_premium": 1.25,
            "max_board_str": "5进6高开",
        },
        "one_word_count": 8,
    }

    facts = adapter.extract_facts(raw_m4, clock=clock, trace_id="trace_m4_test")
    
    # 验证物理事件时间严格锁定 09:25:00
    idx_fact = next(f for f in facts if f.fact_key == "auction.indices")
    assert idx_fact.time_context.event_time == "2026-09-30T09:25:00.000+08:00"
    assert idx_fact.time_context.observed_time == "2026-09-30T09:26:00.000+08:00"
    assert idx_fact.time_context.event_time != idx_fact.time_context.observed_time

    # 2. 竞价总额缺失时的零填充防伪
    raw_m4_missing = {
        "date": "2026-09-30",
        "index_open_data": {"indices": [], "total_bidding_amount_yi": None},
    }
    missing_facts = adapter.extract_facts(raw_m4_missing, clock=clock, trace_id="trace_m4_missing")
    vol_fact = next(f for f in missing_facts if f.fact_key == "auction.volume_ratio")
    assert vol_fact.status == FactStatus.MISSING
    assert vol_fact.payload is None  # 严禁填 0 亿！


def test_04_m5_settlement_timeout_and_stale_contract():
    """验证 M5: 结算价超时与缓存降级保留真实状态"""
    clock = DeterministicClock("2026-09-30T16:00:00.000+08:00")
    adapter = M5SettlementFactAdapter()

    # 1. 模拟 Baostock 物理超时
    raw_timeout = {
        "code": "600519",
        "date": "2026-09-30",
        "status": "TIMEOUT",
    }
    t_facts = adapter.extract_facts(raw_timeout, clock=clock, trace_id="trace_m5_to", symbol="sh600519")
    t_fact = t_facts[0]
    assert t_fact.status == FactStatus.TIMEOUT
    assert t_fact.payload is None  # 零填充防伪

    # 2. 模拟超时后读取本地缓存（STALE）
    raw_stale = {
        "code": "600519",
        "date": "2026-09-30",
        "close": 1800.0,
        "prev_close": 1780.0,
        "source": "baostock_local_cache",
        "status": "STALE",
    }
    s_facts = adapter.extract_facts(raw_stale, clock=clock, trace_id="trace_m5_stale", symbol="sh600519")
    s_fact = s_facts[0]
    assert s_fact.status == FactStatus.STALE
    assert s_fact.freshness == Freshness.STALE
    assert s_fact.payload["close"] == 1800.0
    assert s_fact.provenance.fallback_occurred is True
    assert s_fact.provenance.fallback_reason == "TIMEOUT_FALLBACK_TO_LOCAL_CACHE"


def test_05_s4_fallback_provenance_and_duplicate_preservation():
    """验证 S4: 主备切换保留 Fallback Provenance 与重复原貌"""
    clock = DeterministicClock("2026-09-30T10:00:00.000+08:00")
    adapter = S4NewsFactAdapter()

    # 模拟 CLS 超时切换至 Sina
    fallback_meta = {
        "fallback_occurred": True,
        "primary_source": "cls",
        "fallback_source": "sina",
        "fallback_reason": "CLS_TIMEOUT_AFTER_5000MS",
        "primary_error_detail": "asyncio.TimeoutError",
    }

    # 包含重复快讯标题的原始列表
    raw_news = [
        {"title": "重磅政策出台", "brief": "摘要1", "publish_time": "09:35:00"},
        {"title": "重磅政策出台", "brief": "重复摘要", "publish_time": "09:36:00"}, # 重复新闻
    ]

    facts = adapter.extract_facts(
        raw_news,
        clock=clock,
        trace_id="trace_s4_test",
        fallback_meta=fallback_meta,
    )
    assert len(facts) == 2

    # 验证主备切换血缘完整保留
    f1 = facts[0]
    assert f1.source == "sina"
    assert f1.provenance.primary_source == "cls"
    assert f1.provenance.fallback_occurred is True
    assert f1.provenance.fallback_reason == "CLS_TIMEOUT_AFTER_5000MS"
    assert f1.provenance.primary_error_detail == "asyncio.TimeoutError"

    # 验证重复记录原貌保留（不静默丢弃）
    f2 = facts[1]
    assert f2.provenance.duplicate_detected is True
    assert f2.provenance.duplicate_count == 1
    assert f2.provenance.original_arrival_order == 1


def test_06_nested_immutability_gate():
    """验证 6: 强制 Nested Immutability Gate (外部原始对象修改对已生成事实零污染)"""
    clock = DeterministicClock("2026-09-30T15:00:00.000+08:00")
    adapter = M1ReviewFactAdapter()

    # 外部传入可变字典
    external_dict = {
        "date": "2026-09-30",
        "indices": [{"code": "sh000001", "name": "上证", "price": 3200.0}],
    }
    facts = adapter.extract_facts(external_dict, clock=clock, trace_id="trace_mut_test")
    sh_fact = next(f for f in facts if f.fact_key == "indices.sh000001")
    original_fp = sh_fact.fact_fingerprint

    # 外部恶意原地修改原始字典
    external_dict["indices"][0]["price"] = 99999.0
    external_dict["date"] = "2099-01-01"

    # 验证已生成的 FactItem 内部数值未受任何篡改
    assert sh_fact.payload["close"] == 3200.0
    assert sh_fact.fact_fingerprint == original_fp
    assert verify_fact_fingerprint(sh_fact) is True


def test_07_snapshot_builder_assembly_and_quality_aggregation():
    """验证 7: 快照构建器整体装配、整体质量聚合与 JCS 指纹固化"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    m1_adapter = M1ReviewFactAdapter()
    m5_adapter = M5SettlementFactAdapter()

    m1_raw = {
        "date": "2026-09-30",
        "indices": [
            {"code": "sh000001", "price": 3200.0},
            {"code": "sz399001", "price": 10500.0},
            {"code": "sz399006", "price": 2100.0},
            {"code": "sh000688", "price": 950.0},
        ],
        "breadth": {"total_amount_yi": 8000.0, "up_count": 3000, "down_count": 1500, "flat_count": 200},
        "limit_up": {"max_board_height": 2, "pool": [{"code": "000001"}]},
    }
    m1_facts = m1_adapter.extract_facts(m1_raw, clock=clock, trace_id="t1")

    # 注入一个 STALE 结算价事实
    m5_raw = {"code": "600519", "date": "2026-09-30", "close": 1800.0, "status": "STALE"}
    m5_facts = m5_adapter.extract_facts(m5_raw, clock=clock, trace_id="t2", symbol="sh600519")

    all_facts = m1_facts + m5_facts

    window = ObservationWindow(
        window_start="14:55:00",
        window_end="15:05:00",
        window_type=WindowType.ACCUMULATIVE_RANGE,
    )
    manifest = [
        SourceCredential(source_name="market_daily_snapshot", fetch_status="200", latency_ms=10.0, records_count=len(m1_facts)),
        SourceCredential(source_name="baostock_cache", fetch_status="STALE", latency_ms=1.0, records_count=len(m5_facts)),
    ]

    snapshot = ObservationSnapshotBuilder.build(
        market_date="2026-09-30",
        stage=CognitionStage.POST_CLOSE,
        observation_window=window,
        fact_items=all_facts,
        source_manifest=manifest,
        clock=clock,
    )

    # 1. 验证整体质量被正确聚合为 DEGRADED (因为包含 STALE 事实)
    assert snapshot.overall_quality == QualityLevel.DEGRADED
    assert "settlement.600519" in snapshot.degraded_fields

    # 2. 验证快照指纹合法且自洽
    assert len(snapshot.snapshot_fingerprint) == 64
    assert verify_snapshot_fingerprint(snapshot) is True

    # 3. 验证嵌套不可变性：修改 snapshot.fact_items 的外部引用不会改变内部快照
    all_facts[0] = None  # 外部修改列表
    assert snapshot.fact_items[0] is not None
    assert verify_snapshot_fingerprint(snapshot) is True
