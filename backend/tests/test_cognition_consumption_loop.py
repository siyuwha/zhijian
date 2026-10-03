"""
Cognition 物理事实数据消费闭环与全要素准入验收测试套件
(Cognition Fact Data Consumption Loop & Integration Tests)

上位依据：
1. 用户裁决：M4 + M5 + Stock-Sector Relation：PASS；Cognition Data Consumption：准予放行；
2. 目标：检查当前 Cognition 是否已经能够正确消费这些新输入，并把它接入真实复盘交易系统的每日运行闭环。
"""

import json
import pytest
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cognition.observation.clock import DeterministicClock
from app.cognition.observation.contracts import (
    FactStatus,
    Freshness,
    QualityLevel,
    FactType,
    CognitionStage,
    ObservationWindow,
    SourceCredential,
)
from app.cognition.observation.builder import ObservationSnapshotBuilder
from app.cognition.guard import CognitionAdmissionGuard
from app.cognition.input.pipeline import CognitionObservationPipeline
from app.cognition.input.renderer import PromptSpecData
from app.cognition.observation.fingerprint import verify_effective_input_hash
from app.cognition.bridge import CognitionBridge
from app.cognition.hypothesis.service_adapter import HypothesisServiceAdapter
from app.cognition.hypothesis.contracts import (
    UniverseType,
    OperatorType,
    AggregationType,
    FilterCondition,
    StructuredFilter,
    MetricAssertion,
    HypothesisOutcome,
)
from app.cognition.hypothesis.evaluator import AssertionEvaluator
from app.models.market import MarketDailySnapshot, IntradayMarketSnapshot, IntradayAnomalyEvent
from app.models.report import DailyReview, AuctionReport
from app.models.cognition_v2 import CognitionRecord
from app.core.database import Base
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


@pytest_asyncio.fixture
async def test_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_cognition_bridge_consumes_all_physical_fact_sources(test_session: AsyncSession):
    """
    验证 CognitionBridge 在日终复盘时，能够自动同时消费并聚合：
    - M1 盘后全天指数与涨停池明细
    - M4 早盘集合竞价高标溢价与竞价量比
    - M5 盘中 5 分钟宏观分时切片与异动相变事件
    - 股票与板块题材双向映射事实
    并全部通过 CognitionAdmissionGuard 准入网，生成链式入账记录。
    """
    market_date = "2026-10-02"
    clock = DeterministicClock(f"{market_date}T15:05:00.000+08:00")

    # 1. 准备 M1 物理复盘与快照数据 (含 2 只涨停股)
    sample_items = [
        {"code": "002058", "name": "紫竹高科", "lbc": 2, "sector": "电池", "reason_type": "固态电池"},
        {"code": "600825", "name": "新华传媒", "lbc": 7, "sector": "文化传媒", "reason_type": "知识产权"},
    ]
    snapshot = MarketDailySnapshot(
        date=market_date,
        snapshot_type="EOD_CLOSE",
        indices_snapshot=json.dumps([
            {"code": "sh000001", "name": "上证指数", "price": 3860.0, "pct_change": 0.45},
            {"code": "sz399001", "name": "深证成指", "price": 11600.0, "pct_change": 0.80},
            {"code": "sz399006", "name": "创业板指", "price": 2400.0, "pct_change": 0.20},
            {"code": "sh000688", "name": "科创50", "price": 1050.0, "pct_change": 1.10},
        ]),
        breadth_snapshot=json.dumps({"total_amount_yi": 17000.0, "up_count": 2900, "down_count": 2100, "flat_count": 100}),
        limit_up_snapshot=json.dumps({"total_count": 2, "max_height": 7, "items": sample_items}),
    )
    test_session.add(snapshot)

    review = DailyReview(
        date=market_date,
        market_overview=snapshot.indices_snapshot,
        limit_up_analysis=snapshot.limit_up_snapshot,
        sector_analysis=json.dumps([["电池", 1], ["文化传媒", 1]]),
        report_content=json.dumps({"market_state": {"label": "偏强震荡", "composite_score": 65.0}}),
    )
    test_session.add(review)

    # 2. 准备 M4 早盘竞价报告
    auc_report = AuctionReport(
        date=market_date,
        index_open_data=json.dumps({
            "indices": [{"code": "sh000001", "price": 3850.0, "pct_change": 0.20}],
            "total_bidding_amount_yi": 75.0,
            "bidding_volume_ratio": 0.45,
        }),
        high_open_stats=json.dumps({
            "tested_count": 2,
            "high_open_ratio": 100.0,
            "avg_premium_pct": 3.5,
            "max_board_str": "7进8高开 +5.2%",
        }),
        one_word_count=1,
    )
    test_session.add(auc_report)

    # 3. 准备 M5 盘中时序与异动事件
    intraday_snap = IntradayMarketSnapshot(
        date=market_date,
        timestamp="10:00:00",
        minute_index=30,
        sh_index_price=3855.0,
        sh_index_pct=0.32,
        total_amount_yi=3500.0,
        up_count=2700,
        down_count=2300,
        limit_up_count=2,
    )
    anomaly_evt = IntradayAnomalyEvent(
        date=market_date,
        timestamp="09:45:00",
        minute_index=15,
        event_category="VOLUME_SURGE",
        severity_level="CRITICAL",
        symbol="002058",
        name="紫竹高科",
        price=18.5,
        pct_change=9.98,
    )
    test_session.add(intraday_snap)
    test_session.add(anomaly_evt)
    await test_session.commit()

    # 4. 触发 CognitionBridge 记录
    bridge = CognitionBridge(test_session)
    record = await bridge.record_daily_review(market_date, snapshot, review, clock=clock)

    assert record is not None
    assert record.date == market_date
    assert record.stage == "POST_CLOSE"

    # 5. 反序列化生成的 ObservationSnapshot 验证全要素已进入认知底盘
    obs_dict = json.loads(record.observation_snapshot)
    fact_keys = [f["fact_key"] for f in obs_dict["fact_items"]]

    # 验证 M1 事实项
    assert "indices.sh000001" in fact_keys
    assert "breadth.summary" in fact_keys
    assert "limit_up.pool" in fact_keys

    # 验证 M4 早盘竞价事实项已成功消费
    assert "auction.indices" in fact_keys
    assert "auction.volume_ratio" in fact_keys
    assert "auction.high_open_stats" in fact_keys
    assert "auction.one_word_count" in fact_keys

    # 验证 M5 盘中时序与异动事实项已成功消费
    assert "intraday.series" in fact_keys
    assert "intraday.anomaly" in fact_keys

    # 验证 股票/板块题材关系事实项已成功消费
    assert "relation.stock_sector_map" in fact_keys

    # 6. 验证数据凭证完整记录
    manifest_sources = [s["source_name"] for s in obs_dict["source_manifest"]]
    assert "market_daily_snapshot:EOD_CLOSE" in manifest_sources
    assert "auction_report" in manifest_sources
    assert "intraday_monitor" in manifest_sources
    assert "stock_sector_mapper" in manifest_sources


def test_cognition_observation_pipeline_renders_all_admitted_facts():
    """
    验证 CognitionObservationPipeline 与 DeterministicPromptSerializer：
    将 M1、M4、M5 与股票板块关系事实完整准入为 admitted_facts，并序列化为不可变生效输入。
    """
    market_date = "2026-10-02"
    clock = DeterministicClock(f"{market_date}T15:05:00.000+08:00")

    # 构建包含全要素事实的快照
    adapter_facts = []
    from app.cognition.observation.adapters import (
        M1ReviewFactAdapter,
        M4AuctionFactAdapter,
        M5IntradayFactAdapter,
        StockSectorRelationAdapter,
    )

    m1_raw = {
        "date": market_date,
        "indices": [{"code": "sh000001", "name": "上证指数", "price": 3860.0, "pct_change": 0.45}],
        "breadth": {"total_amount_yi": 17000.0, "up_count": 2900, "down_count": 2100},
        "limit_up": {"total_count": 1, "items": [{"code": "002058", "name": "紫竹高科", "lbc": 2, "sector": "电池"}]},
    }
    adapter_facts.extend(M1ReviewFactAdapter().extract_facts(m1_raw, clock=clock, trace_id="pipe_m1"))

    m4_raw = {
        "date": market_date,
        "index_open_data": {"indices": [{"code": "sh000001", "price": 3850.0}], "total_bidding_amount_yi": 80.0},
        "high_open_stats": {"tested_count": 1, "high_open_ratio": 100.0, "avg_premium_pct": 2.5},
        "one_word_count": 1,
    }
    adapter_facts.extend(M4AuctionFactAdapter().extract_facts(m4_raw, clock=clock, trace_id="pipe_m4"))

    m5_raw = {
        "date": market_date,
        "snapshots": [{"timestamp": "10:00:00", "minute_index": 30, "sh_index_price": 3855.0, "total_amount_yi": 3500.0}],
        "events": [{"timestamp": "09:45:00", "minute_index": 15, "event_category": "VOLUME_SURGE", "symbol": "002058"}],
    }
    adapter_facts.extend(M5IntradayFactAdapter().extract_facts(m5_raw, clock=clock, trace_id="pipe_m5"))

    rel_raw = {
        "date": market_date,
        "items": [{"code": "002058", "name": "紫竹高科", "sector": "电池", "lbc": 2}],
    }
    adapter_facts.extend(StockSectorRelationAdapter().extract_facts(rel_raw, clock=clock, trace_id="pipe_rel"))

    obs_window = ObservationWindow(window_start=f"{market_date}T09:15:00.000+08:00", window_end=f"{market_date}T15:00:00.000+08:00")
    snapshot = ObservationSnapshotBuilder.build(
        market_date=market_date,
        stage=CognitionStage.POST_CLOSE,
        observation_window=obs_window,
        fact_items=adapter_facts,
        source_manifest=[],
        clock=clock,
    )

    prompt_spec = PromptSpecData(
        prompt_id="SPEC_TEST",
        version="v1.0.0",
        prompt_hash="h" * 64,
        system_template="System spec test",
        user_template="[USER PROMPT] Observation data: {observation_data}",
    )

    effective_input = CognitionObservationPipeline.process_snapshot(
        snapshot=snapshot,
        prompt_spec=prompt_spec,
        input_id="input_test_001",
    )

    # 验证准入事实字典包含了所有关键事实
    admitted = effective_input.admitted_facts
    assert "indices.sh000001" in admitted
    assert "auction.high_open_stats" in admitted
    assert "intraday.series" in admitted
    assert "intraday.anomaly" in admitted
    assert "relation.stock_sector_map" in admitted

    # 验证渲染文本中包含了 Section 2 准入数据
    user_prompt = effective_input.rendered_user_prompt
    assert "auction.high_open_stats" in user_prompt
    assert "intraday.series" in user_prompt
    assert "relation.stock_sector_map" in user_prompt

    # 验证 JCS 散列防篡改通过
    assert verify_effective_input_hash(effective_input) is True


def test_ast_evaluator_evaluates_real_ladder_and_sector_facts():
    """
    验证 AST Evaluator 能够直接消费 extract_observation_data 提取的真实高标与板块事实，
    不再发生因标的范围为空导致的假说空转与 INCONCLUSIVE 假死！
    """
    target_date = "2026-10-02"

    sample_items = [
        {"code": "002058", "name": "紫竹高科", "lbc": 2, "sector": "电池", "reason_type": "固态电池"},
        {"code": "600825", "name": "新华传媒", "lbc": 7, "sector": "文化传媒", "reason_type": "知识产权"},
    ]
    snapshot = MarketDailySnapshot(
        date=target_date,
        snapshot_type="EOD_CLOSE",
        indices_snapshot=json.dumps([{"code": "sh000001", "name": "上证指数", "price": 3860.0, "pct_change": 0.45}]),
        breadth_snapshot=json.dumps({"up_count": 2900, "down_count": 2100}),
        limit_up_snapshot=json.dumps({"total_count": 2, "max_height": 7, "items": sample_items}),
    )

    obs_data = HypothesisServiceAdapter.extract_observation_data(target_date, snapshot=snapshot)

    # 验证真实高标与板块成员已沉淀入 AST 事实切片
    assert len(obs_data["ladder_stocks"]) == 2
    assert len(obs_data["sector_stocks"]) == 2

    # 构造针对 UniverseType.LADDER_HIGH_SPEC 的 AST 断言：验证最高板大于等于 5 板
    assertion_high = MetricAssertion(
        assertion_id="ast_check_ladder_height",
        metric="board_height",
        selector=StructuredFilter(universe_type=UniverseType.LADDER_HIGH_SPEC, conditions=[]),
        aggregation=AggregationType.MAX,
        operator=OperatorType.GTE,
        target_value=5.0,
    )

    res = AssertionEvaluator.evaluate(assertion_high, obs_data)
    # 真实最高板为 7 板，7 >= 5 -> PASSED
    assert res.outcome.value == "PASSED"
    assert res.actual_value == 7.0

    # 构造针对 UniverseType.SECTOR 的 AST 断言：验证电池板块包含 2 板股票
    assertion_sector = MetricAssertion(
        assertion_id="ast_check_battery_sector",
        metric="board_height",
        selector=StructuredFilter(
            universe_type=UniverseType.SECTOR,
            conditions=[FilterCondition(field="sector_code", op=OperatorType.EQ, val="电池")],
        ),
        aggregation=AggregationType.MAX,
        operator=OperatorType.EQ,
        target_value=2.0,
    )

    res_sec = AssertionEvaluator.evaluate(assertion_sector, obs_data)
    assert res_sec.outcome.value == "PASSED"
    assert res_sec.actual_value == 2.0
