"""
M4 高标竞价 + M5 Intraday Adapter + 股票/板块关系契约验收测试套件
(M4 High-Tier Auction + M5 Intraday Adapter + Stock-Sector Relation Contract Tests)

上位依据：
1. 用户指令：直接进入 M4 高标竞价 + M5 Intraday Adapter + 股票/板块关系三件事。
2. 董事会工程纪律：零 LLM 依赖、严禁伪造数据、严格 RFC 8785 JCS 指纹防篡改、全库零污染。
"""

import json
import pytest
from datetime import datetime

from app.cognition.observation.clock import DeterministicClock
from app.cognition.observation.contracts import (
    FactStatus,
    Freshness,
    QualityLevel,
    FactType,
    CognitionStage,
)
from app.cognition.observation.adapters.m4_adapter import M4AuctionFactAdapter
from app.cognition.observation.adapters.m5_adapter import M5IntradayFactAdapter, M5SettlementFactAdapter
from app.cognition.observation.adapters.relation_adapter import StockSectorRelationAdapter
from app.cognition.observation.fingerprint import verify_fact_fingerprint


# ==============================================================================
# 1. M4 早盘高标竞价事实契约测试
# ==============================================================================

def test_m4_auction_high_tier_tracking_continuity():
    """验证 M4 早盘竞价高标跟踪接通：富集高标溢价、最高板、极值异动股与 JCS 指纹"""
    clock = DeterministicClock("2026-10-01T09:26:00.000+08:00")
    adapter = M4AuctionFactAdapter()

    raw_m4_with_high_tier = {
        "date": "2026-10-01",
        "id": "m4_auction_001",
        "index_open_data": {
            "indices": [
                {"code": "sh000001", "name": "上证指数", "price": 3850.0, "amount_wan": 3500000.0},
                {"code": "sz399001", "name": "深证成指", "price": 11550.0, "amount_wan": 4500000.0},
            ],
            "total_bidding_amount_yi": 80.0,
            "yesterday_total_amount_yi": 16477.0,
            "bidding_volume_ratio": 0.49,
        },
        "high_open_stats": {
            "tested_count": 10,
            "high_open_count": 7,
            "low_open_count": 3,
            "high_open_ratio": 70.0,
            "avg_premium_pct": 2.35,
            "one_word_up_count": 2,
            "one_word_down_count": 0,
            "max_board_str": "7进8高开 +5.20%",
            "max_board_info": {
                "symbol": "600825",
                "name": "新华传媒",
                "board_height": 7,
                "open_pct": 5.20,
                "is_one_word": False,
            },
            "extreme_stocks": [
                {"symbol": "600825", "name": "新华传媒", "open_pct": 5.20, "tag": "竞价大幅高开抢筹"},
                {"symbol": "002058", "name": "紫竹高科", "open_pct": 4.10, "tag": "竞价大幅高开抢筹"},
            ],
        },
        "one_word_count": 2,
    }

    facts = adapter.extract_facts(raw_m4_with_high_tier, clock=clock, trace_id="trace_m4_continuity")
    assert len(facts) >= 3

    # 1. 验证 auction.high_open_stats 事实
    ht_fact = next(f for f in facts if f.fact_key == "auction.high_open_stats")
    assert ht_fact.status == FactStatus.AVAILABLE
    assert ht_fact.payload["tested_count"] == 10
    assert ht_fact.payload["high_open_ratio"] == 70.0
    assert ht_fact.payload["avg_premium"] == 2.35
    assert ht_fact.payload["max_board_info"]["symbol"] == "600825"
    assert len(ht_fact.payload["extreme_stocks"]) == 2

    # 2. 验证时间锁定在 09:25:00
    assert ht_fact.time_context.event_time == "2026-10-01T09:25:00.000+08:00"

    # 3. 验证 JCS 指纹
    assert verify_fact_fingerprint(ht_fact) is True


def test_m4_auction_empty_when_no_prev_limit_up():
    """验证前日无涨停股时，合法输出 FactStatus.EMPTY 语义与零填充防伪"""
    clock = DeterministicClock("2026-10-01T09:26:00.000+08:00")
    adapter = M4AuctionFactAdapter()

    raw_m4_empty = {
        "date": "2026-10-01",
        "id": "m4_auction_empty",
        "index_open_data": {
            "indices": [],
            "total_bidding_amount_yi": None,
        },
        "high_open_stats": {
            "tested_count": 0,
            "high_open_ratio": None,
            "avg_premium_pct": None,
            "max_board_str": "无连板高标",
        },
    }

    facts = adapter.extract_facts(raw_m4_empty, clock=clock, trace_id="trace_m4_empty")
    ht_fact = next(f for f in facts if f.fact_key == "auction.high_open_stats")
    assert ht_fact.status == FactStatus.EMPTY
    assert ht_fact.payload["tested_count"] == 0
    assert ht_fact.payload["extreme_stocks"] == []
    assert verify_fact_fingerprint(ht_fact) is True


# ==============================================================================
# 2. M5 盘中时序与异动事实契约测试
# ==============================================================================

def test_m5_intraday_series_and_anomaly_facts():
    """验证 M5 盘中5分钟分时切片与异动相变事件规范化事实抽取"""
    clock = DeterministicClock("2026-09-30T10:05:00.000+08:00")
    adapter = M5IntradayFactAdapter()

    raw_intraday = {
        "date": "2026-09-30",
        "id": "m5_intraday_001",
        "snapshots": [
            {
                "timestamp": "09:35:00",
                "minute_index": 5,
                "sh_index_price": 3840.1,
                "sh_index_pct": 0.25,
                "sz_index_price": 11480.0,
                "sz_index_pct": 0.40,
                "cy_index_pct": -0.15,
                "total_amount_yi": 1200.5,
                "volume_proj_yi": None,  # 09:30~09:45 强制保持 None 防伪
                "is_proj_estimated": False,
                "up_count": 2500,
                "down_count": 2200,
                "limit_up_count": 18,
                "limit_down_count": 1,
                "broken_limit_count": 2,
                "max_height": 7,
                "leader_stock": "600825",
            },
            {
                "timestamp": "10:00:00",
                "minute_index": 30,
                "sh_index_price": 3855.3,
                "sh_index_pct": 0.65,
                "sz_index_price": 11530.0,
                "sz_index_pct": 0.82,
                "cy_index_pct": 0.35,
                "total_amount_yi": 4500.0,
                "volume_proj_yi": 16800.0,  # 10:00 已具备稳定量能投影
                "is_proj_estimated": True,
                "up_count": 3100,
                "down_count": 1600,
                "limit_up_count": 32,
                "limit_down_count": 1,
                "broken_limit_count": 4,
                "max_height": 7,
                "leader_stock": "600825",
            },
        ],
        "events": [
            {
                "timestamp": "09:42:15",
                "minute_index": 12,
                "event_category": "VOLUME_SURGE",
                "severity_level": "CRITICAL",
                "symbol": "002058",
                "name": "紫竹高科",
                "price": 18.50,
                "pct_change": 9.98,
                "window_delta_pct": 4.5,
                "window_amount_wan": 15000.0,
                "surge_ratio": None,
                "details": {"reason": "电池板块放量上攻"},
            }
        ],
    }

    facts = adapter.extract_facts(raw_intraday, clock=clock, trace_id="trace_m5_intraday")
    assert len(facts) == 2

    # 1. 验证 intraday.series 事实
    series_fact = next(f for f in facts if f.fact_key == "intraday.series")
    assert series_fact.status == FactStatus.AVAILABLE
    assert series_fact.payload["count"] == 2
    assert series_fact.payload["snapshots"][0]["volume_proj_yi"] is None  # 验证严防0伪造
    assert series_fact.payload["snapshots"][1]["volume_proj_yi"] == 16800.0
    assert verify_fact_fingerprint(series_fact) is True

    # 2. 验证 intraday.anomaly 事实
    anomaly_fact = next(f for f in facts if f.fact_key == "intraday.anomaly")
    assert anomaly_fact.status == FactStatus.AVAILABLE
    assert anomaly_fact.payload["count"] == 1
    assert anomaly_fact.payload["events"][0]["symbol"] == "002058"
    assert anomaly_fact.payload["events"][0]["event_category"] == "VOLUME_SURGE"
    assert verify_fact_fingerprint(anomaly_fact) is True


def test_m5_intraday_empty_semantics():
    """验证 M5 盘中无数据时的合法 FactStatus.EMPTY 语义"""
    clock = DeterministicClock("2026-09-30T10:05:00.000+08:00")
    adapter = M5IntradayFactAdapter()

    facts = adapter.extract_facts({"date": "2026-09-30", "snapshots": [], "events": []}, clock=clock, trace_id="trace_m5_empty")
    assert len(facts) == 2
    for f in facts:
        assert f.status == FactStatus.EMPTY
        assert f.payload["count"] == 0
        assert verify_fact_fingerprint(f) is True


# ==============================================================================
# 3. 股票/板块关系映射事实契约测试
# ==============================================================================

def test_stock_sector_relation_adapter_bidirectional():
    """验证股票与板块双向客观归属映射、题材梯队排行与指纹防篡改"""
    clock = DeterministicClock("2026-09-30T15:35:00.000+08:00")
    adapter = StockSectorRelationAdapter()

    sample_items = [
        {"code": "002058", "name": "紫竹高科", "hybk": "电池", "reason_type": "固态电池", "lbc": 2},
        {"code": "600825", "name": "新华传媒", "sector": "文化传媒", "reasons": ["传媒", "知识产权"], "lbc": 7},
        {"code": "000001", "name": "平安银行", "sector": "银行", "reasons": ["金融"], "lbc": 1},
        {"code": "600036", "name": "招商银行", "sector": "银行", "reasons": ["金融"], "lbc": 1},
    ]

    raw_relation_data = {
        "date": "2026-09-30",
        "items": sample_items,
        "top_reasons": [["银行", 2], ["文化传媒", 1], ["电池", 1]],
    }

    facts = adapter.extract_facts(raw_relation_data, clock=clock, trace_id="trace_rel_test")
    assert len(facts) == 1

    rel_fact = facts[0]
    assert rel_fact.fact_key == "relation.stock_sector_map"
    assert rel_fact.fact_type == FactType.STOCK_SECTOR_MAP
    assert rel_fact.status == FactStatus.AVAILABLE

    payload = rel_fact.payload
    assert payload["total_stocks_mapped"] == 4
    assert payload["total_sectors_mapped"] == 3

    # 1. 验证股票 -> 板块正向索引
    s_002058 = payload["stock_to_sector"]["002058"]
    assert s_002058["name"] == "紫竹高科"
    assert s_002058["primary_sector"] == "电池"
    assert s_002058["height"] == 2

    # 2. 验证板块 -> 股票反向索引 (板块成员真实可查，杜绝幻觉)
    bank_stocks = payload["sector_to_stocks"]["银行"]
    assert len(bank_stocks) == 2
    bank_codes = [s["code"] for s in bank_stocks]
    assert "000001" in bank_codes
    assert "600036" in bank_codes

    # 3. 验证题材梯队榜按热度排序
    assert payload["sector_leaderboard"][0]["sector"] == "银行"
    assert payload["sector_leaderboard"][0]["count"] == 2

    # 4. 验证 RFC 8785 JCS 指纹
    assert verify_fact_fingerprint(rel_fact) is True


def test_stock_sector_relation_empty_semantic():
    """验证无股票数据时的 FactStatus.EMPTY 合法语义"""
    clock = DeterministicClock("2026-09-30T15:35:00.000+08:00")
    adapter = StockSectorRelationAdapter()

    facts = adapter.extract_facts({"date": "2026-09-30", "items": []}, clock=clock, trace_id="trace_rel_empty")
    assert len(facts) == 1
    rel_fact = facts[0]
    assert rel_fact.status == FactStatus.EMPTY
    assert rel_fact.payload["total_stocks_mapped"] == 0
    assert rel_fact.payload["total_sectors_mapped"] == 0
    assert verify_fact_fingerprint(rel_fact) is True
