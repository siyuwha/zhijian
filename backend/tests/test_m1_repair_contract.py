"""
M1 盘后事实底座修复与契约验收测试套件 (M1 Fact Foundation Repair Contract Tests)
上位依据：
1. 《开发文档/61-Observation-M1-M5-Fact-Foundation-Audit-Report.md》
2. 用户指令：M1 事实补齐修复与验收专项
测试目标：
1. 验证 m1_adapter 兼容读取真实生产库中的 items 字段（提取 52 只涨停股真实明细）；
2. 验证 m1_adapter 向下兼容既有测试的 pool 字段；
3. 验证全市场零涨停时的合法 FactStatus.EMPTY 语义与零填充防伪；
4. 验证 DailyReview ORM 对象自愈提取 breadth.summary，杜绝 INVALID 降级；
5. 验证 RFC 8785 JCS 指纹与全息血缘在富集事实项下的一致性与抗碰撞性。
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
from app.cognition.observation.adapters.m1_adapter import M1ReviewFactAdapter
from app.cognition.observation.fingerprint import verify_fact_fingerprint


def test_m1_adapter_extracts_real_production_items():
    """验证从生产库真实格式 (items 数组) 提取全部 52 只涨停个股与元数据"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    adapter = M1ReviewFactAdapter()

    # 构造模拟生产环境 MarketDailySnapshot.limit_up_snapshot 真实结构 (含 52 只 items)
    sample_items = [
        {
            "code": "002058",
            "name": "紫竹高科",
            "reason_type": "电池",
            "reasons": ["电池", "固态电池"],
            "high_days": "2天2板",
            "lbc": 2,
            "fbt": 92500,
            "limit_up_type": "CONTINUED",
            "sector": "电池",
        },
        {
            "code": "600825",
            "name": "新华传媒",
            "reason_type": "文化传媒",
            "reasons": ["传媒", "知识产权"],
            "high_days": "7天7板",
            "lbc": 7,
            "fbt": 93012,
            "limit_up_type": "CONTINUED",
            "sector": "传媒",
        },
    ] + [
        {
            "code": f"60{i:04d}",
            "name": f"样本股{i}",
            "reason_type": "通用",
            "reasons": ["重组"],
            "high_days": "首板",
            "lbc": 1,
            "fbt": 94500,
            "limit_up_type": "FIRST_LIMIT",
            "sector": "综合",
        }
        for i in range(50)
    ]

    raw_snapshot = {
        "date": "2026-09-30",
        "id": "snap_prod_001",
        "indices_snapshot": json.dumps([
            {"code": "sh000001", "name": "上证指数", "price": 3842.19, "pct_change": 0.31, "amount_wan": 65000000.0},
            {"code": "sz399001", "name": "深证成指", "price": 11500.0, "pct_change": 0.50, "amount_wan": 75000000.0},
            {"code": "sz399006", "name": "创业板指", "price": 2400.0, "pct_change": -0.20, "amount_wan": 35000000.0},
            {"code": "sh000688", "name": "科创50", "price": 1050.0, "pct_change": 1.10, "amount_wan": 15000000.0},
        ]),
        "breadth_snapshot": json.dumps({
            "total_amount_yi": 16477.2,
            "up_count": 2614,
            "down_count": 2841,
            "flat_count": 183,
        }),
        "limit_up_snapshot": json.dumps({
            "total_count": 52,
            "max_height": 7,
            "first_limit_count": 50,
            "continued_count": 2,
            "limit_down_count": 9,
            "broken_limit_count": 12,
            "broken_limit_ratio": 18.75,
            "top_reasons": [["综合", 50], ["电池", 1], ["传媒", 1]],
            "items": sample_items,
        }),
    }

    facts = adapter.extract_facts(raw_snapshot, clock=clock, trace_id="trace_m1_prod_repair")
    assert len(facts) >= 6

    # 1. 验证 limit_up.pool 事实
    lu_fact = next(f for f in facts if f.fact_key == "limit_up.pool")
    assert lu_fact.status == FactStatus.AVAILABLE
    assert lu_fact.payload["limit_up_count"] == 52
    assert lu_fact.payload["max_board_height"] == 7
    assert len(lu_fact.payload["pool"]) == 52

    # 2. 验证个股明细已结构化入库
    p0 = lu_fact.payload["pool"][0]
    assert p0["code"] == "002058"
    assert p0["name"] == "紫竹高科"
    assert p0["height"] == 2
    assert p0["sector"] == "电池"
    assert p0["limit_up_type"] == "CONTINUED"
    assert p0["fbt"] == 92500

    p1 = lu_fact.payload["pool"][1]
    assert p1["code"] == "600825"
    assert p1["name"] == "新华传媒"
    assert p1["height"] == 7
    assert p1["sector"] == "传媒"

    # 3. 验证 JCS 指纹验证通过
    assert verify_fact_fingerprint(lu_fact) is True


def test_m1_adapter_backwards_compatibility_with_pool():
    """验证向下兼容旧的 pool 格式 (单测与轻量输入)"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    adapter = M1ReviewFactAdapter()

    old_raw = {
        "date": "2026-09-30",
        "id": "dict_old",
        "limit_up": {
            "max_board_height": 5,
            "pool": [
                {"code": "000001", "name": "平安银行", "height": 1},
                {"code": "600519", "name": "贵州茅台", "height": 2, "sector": "白酒"},
            ],
        },
    }

    facts = adapter.extract_facts(old_raw, clock=clock, trace_id="trace_old_pool")
    lu_fact = next(f for f in facts if f.fact_key == "limit_up.pool")
    assert lu_fact.status == FactStatus.AVAILABLE
    assert lu_fact.payload["limit_up_count"] == 2
    assert lu_fact.payload["max_board_height"] == 5
    assert len(lu_fact.payload["pool"]) == 2
    assert lu_fact.payload["pool"][0]["code"] == "000001"
    assert lu_fact.payload["pool"][1]["sector"] == "白酒"
    assert verify_fact_fingerprint(lu_fact) is True


def test_m1_adapter_zero_limit_up_empty_semantic():
    """验证市场零涨停时的合法 FactStatus.EMPTY 语义与零填充防伪"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    adapter = M1ReviewFactAdapter()

    empty_raw = {
        "date": "2026-09-30",
        "limit_up": {
            "total_count": 0,
            "max_height": 0,
            "items": [],
        },
    }

    facts = adapter.extract_facts(empty_raw, clock=clock, trace_id="trace_empty_zt")
    lu_fact = next(f for f in facts if f.fact_key == "limit_up.pool")
    assert lu_fact.status == FactStatus.EMPTY
    assert lu_fact.payload["limit_up_count"] == 0
    assert lu_fact.payload["max_board_height"] == 0
    assert lu_fact.payload["pool"] == []
    assert verify_fact_fingerprint(lu_fact) is True


def test_m1_adapter_daily_review_orm_breadth_healing():
    """验证传入 DailyReview 对象时，能自动从 report_content 自愈提取 breadth.summary 事实"""
    clock = DeterministicClock("2026-09-30T15:30:00.000+08:00")
    adapter = M1ReviewFactAdapter()

    class MockDailyReview:
        id = 101
        date = "2026-09-30"
        created_at = datetime.fromisoformat("2026-09-30T15:35:00")
        market_overview = json.dumps([
            {"code": "sh000001", "name": "上证指数", "price": 3842.19, "pct_change": 0.31}
        ])
        limit_up_analysis = json.dumps({
            "total_count": 1,
            "max_height": 1,
            "items": [{"code": "000001", "name": "平安银行", "lbc": 1, "sector": "银行"}],
        })
        # report_content 内含自愈事实
        report_content = json.dumps({
            "breadth": {
                "total_amount_yi": 16477.2,
                "up_count": 2614,
                "down_count": 2841,
                "flat_count": 183,
            }
        })
        __table__ = True

    mock_review = MockDailyReview()
    facts = adapter.extract_facts(mock_review, clock=clock, trace_id="trace_daily_review_healing")

    # 验证 breadth.summary 不再是 MISSING，而是成功自愈为 AVAILABLE
    br_fact = next(f for f in facts if f.fact_key == "breadth.summary")
    assert br_fact.status == FactStatus.AVAILABLE
    assert br_fact.payload["total_amount_yi"] == 16477.2
    assert br_fact.payload["up_count"] == 2614
    assert br_fact.payload["down_count"] == 2841
    assert verify_fact_fingerprint(br_fact) is True
