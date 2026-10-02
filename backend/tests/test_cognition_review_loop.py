"""
Phase 2B.3: 认知闭环三卡片聚合服务单元测试 (test_cognition_review_loop.py)
上位依据：《开发文档/59-Phase-2B.3-认知闭环前端可视化契约设计单.md》

测试覆盖：
1. 缺数日期安全回退与空状态测试 (Missing != Error)；
2. 今日事实与今日假说组装测试 (Fact vs Derived 分层)；
3. 昨日假说事后裁决与对比矩阵测试 (CONFIRMED / FALSIFIED 状态机)；
4. API 端点 /api/v1/cognition/review-loop/{date} 契约一致性。
"""

import os
import json
import tempfile
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.report import DailyReview
from app.models.market import MarketDailySnapshot
from app.models.cognition import MarketHypothesis, CognitionMarketState, HypothesisVerification
from app.services.cognition_review import CognitionReviewService
from app.schemas.cognition import MarketHypothesisCreate


@pytest_asyncio.fixture
async def async_session():
    temp_dir = tempfile.gettempdir()
    db_file = os.path.join(temp_dir, f"test_review_loop_{os.getpid()}.db")
    if os.path.exists(db_file):
        os.unlink(db_file)

    db_url = f"sqlite+aiosqlite:///{db_file}"
    engine = create_async_engine(db_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
    if os.path.exists(db_file):
        os.unlink(db_file)


@pytest.mark.asyncio
async def test_review_loop_empty_date(async_session: AsyncSession):
    """测试完全无数据的日期，安全返回空结构，无异常崩溃"""
    service = CognitionReviewService(async_session)
    data = await service.get_review_loop_data("2099-01-01")

    assert data.market_date == "2099-01-01"
    assert data.today_facts is not None
    assert len(data.today_facts.fact_layer.indices) == 0
    assert data.today_facts.fact_layer.sentiment.limit_up_count is None
    assert data.today_hypothesis is None
    assert data.yesterday_adjudication is None


@pytest.mark.asyncio
async def test_review_loop_with_today_facts_and_hypothesis(async_session: AsyncSession):
    """测试包含今日复盘事实与今日假说的组装契约"""
    service = CognitionReviewService(async_session)

    # 1. 注入 2026-09-28 收盘复盘事实
    mock_indices = [
        {"code": "sh000001", "name": "上证指数", "price": 3823.62, "pct_change": -1.67},
        {"code": "sz399001", "name": "深证成指", "price": 12858.75, "pct_change": -3.44},
    ]
    mock_lu = {
        "total_count": 33,
        "limit_down_count": 56,
        "max_height": 5,
        "broken_limit_count": 11,
        "broken_limit_ratio": 0.25,
    }
    rev = DailyReview(
        date="2026-09-28",
        market_overview=json.dumps(mock_indices),
        limit_up_analysis=json.dumps(mock_lu),
        data_quality="FULL",
    )
    async_session.add(rev)

    snap = MarketDailySnapshot(
        date="2026-09-28",
        snapshot_type="EOD_CLOSE",
        indices_snapshot=json.dumps(mock_indices),
        limit_up_snapshot=json.dumps(mock_lu),
        breadth_snapshot="{}",
        data_quality="FULL",
    )
    async_session.add(snap)

    # 注入市场状态
    ms = CognitionMarketState(
        date="2026-09-28",
        timestamp="2026-09-28T15:00:00",
        indicators="[]",
        composite_score=15.0,
        state_label="恐慌出清",
        config_snapshot="{}",
    )
    async_session.add(ms)

    # 2. 注入 2026-09-28 建立的假说 (针对 2026-09-29)
    hypo_create = MarketHypothesisCreate(
        created_date="2026-09-28",
        target_date="2026-09-29",
        hypothesis_type="SENTIMENT_CYCLE",
        target_asset="全市场短线投机生态",
        expected_scenario="REBOUND",
        premise_logic="连板5板有韧性，预期次日修复",
        expected_phenomenon="涨停家数重回40家以上",
        invalidation_condition="若跌停依然大于50家则证伪",
        assertion_metrics={
            "expected_assertions": [
                {
                    "assertion_id": "exp_lu_min",
                    "metric_type": "limit_up_count",
                    "target_code": "ALL_A",
                    "operator": "GTE",
                    "threshold": 40.0,
                    "description": "全A涨停>=40",
                }
            ],
            "invalidation_assertions": [
                {
                    "assertion_id": "inv_ld_max",
                    "metric_type": "limit_down_count",
                    "target_code": "ALL_A",
                    "operator": "GT",
                    "threshold": 50.0,
                    "description": "全A跌停>50",
                }
            ],
            "meta": {
                "model_name": "deepseek-flash",
                "prompt_spec_version": "1.1.0",
                "hypothesis_hash": "mock_hash_0928",
            },
        },
    )
    await service.create_hypothesis(hypo_create)

    # 3. 查询聚合闭环数据
    data = await service.get_review_loop_data("2026-09-28")

    # 验证今日事实卡
    assert len(data.today_facts.fact_layer.indices) == 2
    assert data.today_facts.fact_layer.indices[0].code == "sh000001"
    assert data.today_facts.fact_layer.indices[0].pct_change == -1.67
    assert data.today_facts.fact_layer.sentiment.limit_up_count == 33
    assert data.today_facts.derived_state.state_label == "恐慌出清"
    assert data.today_facts.fact_snapshot_hash is not None
    assert data.today_facts.fact_snapshot_hash.startswith("obs-")
    assert data.today_facts.observation_timestamp is not None
    assert data.today_facts.data_quality == "GOOD"

    # 验证今日 AI 假说卡
    assert data.today_hypothesis is not None
    assert data.today_hypothesis.created_date == "2026-09-28"
    assert data.today_hypothesis.target_date == "2026-09-29"
    assert data.today_hypothesis.status == "PENDING"
    assert len(data.today_hypothesis.expected_assertions) == 1
    assert data.today_hypothesis.expected_assertions[0].operator == "GTE"
    assert data.today_hypothesis.expected_assertions[0].threshold == 40.0
    assert len(data.today_hypothesis.invalidation_assertions) == 1
    assert data.today_hypothesis.invalidation_assertions[0].operator == "GT"
    assert data.today_hypothesis.invalidation_assertions[0].threshold == 50.0
    assert data.today_hypothesis.meta.model_name == "deepseek-flash"
    assert data.today_hypothesis.meta.prompt_spec_version == "1.1.0"


@pytest.mark.asyncio
async def test_review_loop_with_yesterday_falsification(async_session: AsyncSession):
    """测试昨日假说针对今日的自动客观裁决与对比矩阵 (FALSIFIED 打脸场景)"""
    service = CognitionReviewService(async_session)

    # 1. 注入昨日 (2026-09-26) 提出的假说：预期 09-28 弱修复，跌停不能超过 30 家
    hypo_0926 = MarketHypothesisCreate(
        created_date="2026-09-26",
        target_date="2026-09-28",
        hypothesis_type="SENTIMENT_CYCLE",
        target_asset="全市场短线投机生态",
        expected_scenario="WEAK_REBOUND",
        premise_logic="急跌后预期弱修复",
        expected_phenomenon="跌停家数受控在20家以内",
        invalidation_condition="跌停大于30家则证伪",
        assertion_metrics={
            "expected_assertions": [
                {
                    "assertion_id": "exp_ld_ok",
                    "metric_type": "limit_down_count",
                    "target_code": "ALL_A",
                    "operator": "LTE",
                    "threshold": 20.0,
                    "description": "跌停<=20",
                }
            ],
            "invalidation_assertions": [
                {
                    "assertion_id": "inv_ld_bad",
                    "metric_type": "limit_down_count",
                    "target_code": "ALL_A",
                    "operator": "GT",
                    "threshold": 30.0,
                    "description": "跌停>30",
                }
            ],
        },
    )
    await service.create_hypothesis(hypo_0926)

    # 2. 注入今日 (2026-09-28) 真实收盘事实：实际跌停 56 家
    mock_lu = {"total_count": 33, "limit_down_count": 56, "max_height": 5}
    rev_0928 = DailyReview(
        date="2026-09-28",
        market_overview="[]",
        limit_up_analysis=json.dumps(mock_lu),
        data_quality="FULL",
    )
    async_session.add(rev_0928)
    await async_session.commit()

    # 2.5 模拟收盘 15:30 产生的客观事后核验 (生成核验记账，保证 get_review_loop_data 严格只读)
    await service.verify_hypothesis(1, stage="CLOSE_1530")

    # 3. 查询今日 2026-09-28 的闭环数据 (严格只读查询)
    data = await service.get_review_loop_data("2026-09-28")

    # 验证昨日假说裁决卡
    adj = data.yesterday_adjudication
    assert adj is not None
    assert adj.created_date == "2026-09-26"
    assert adj.target_date == "2026-09-28"
    assert adj.outcome == "FALSIFIED"
    assert adj.falsification_triggered is True
    assert "证伪" in adj.details

    # 验证对比矩阵 (证伪优先短路原则：一旦触发证伪红线，立即短路，仅记录证伪断言)
    assert len(adj.comparison_matrix) == 1
    inv_item = adj.comparison_matrix[0]
    assert inv_item.kind == "INVALIDATION"
    assert inv_item.metric_type == "limit_down_count"
    assert inv_item.threshold == 30.0
    assert inv_item.actual_value == 56.0
    assert inv_item.is_satisfied is True  # 触碰了证伪红线！


@pytest.mark.asyncio
async def test_propose_today_temporal_causality_guard(async_session: AsyncSession):
    """测试 propose_today 服务端刚性时间因果防线：target_date <= market_date 必须抛出 400"""
    from fastapi import HTTPException
    service = CognitionReviewService(async_session)

    # 1. 注入当日事实
    rev_0928 = DailyReview(
        date="2026-09-28",
        market_overview="[]",
        limit_up_analysis="{}",
        data_quality="FULL",
    )
    async_session.add(rev_0928)
    await async_session.commit()

    # 2. 尝试传入过去的时间 (target_date < market_date)
    with pytest.raises(HTTPException) as exc_past:
        await service.propose_today_hypothesis(market_date="2026-09-28", target_date="2026-09-27")
    assert exc_past.value.status_code == 400
    assert "Temporal causality violation" in exc_past.value.detail

    # 3. 尝试传入当天的时间 (target_date == market_date)
    with pytest.raises(HTTPException) as exc_today:
        await service.propose_today_hypothesis(market_date="2026-09-28", target_date="2026-09-28")
    assert exc_today.value.status_code == 400
    assert "Temporal causality violation" in exc_today.value.detail


@pytest.mark.asyncio
async def test_fact_snapshot_hash_identity_regression(async_session: AsyncSession):
    """
    Phase 2B.3 Closure Patch 核心测试：Hash Identity 规范与敏感性断言
    1. 同快照同 hash (确定性与可复现)
    2. 事实变化 hash 变化 (敏感性)
    3. DTO/表现层变化不影响 hash (独立性)
    4. 无 Observation 快照时严格为 None，严禁以 Review Payload 冒充
    """
    service = CognitionReviewService(async_session)

    # 1. 注入基准快照 A (2026-09-28)
    snap_a = MarketDailySnapshot(
        date="2026-09-28",
        snapshot_type="EOD_CLOSE",
        indices_snapshot=json.dumps([{"code": "sh000001", "name": "上证指数", "price": 3800.0, "pct_change": 1.0}]),
        limit_up_snapshot=json.dumps({"total_count": 50}),
        breadth_snapshot=json.dumps({"up": 3000, "down": 1000}),
        data_quality="FULL",
    )
    async_session.add(snap_a)
    await async_session.commit()

    data_a1 = await service.get_review_loop_data("2026-09-28")
    data_a2 = await service.get_review_loop_data("2026-09-28")

    hash_a1 = data_a1.today_facts.fact_snapshot_hash
    hash_a2 = data_a2.today_facts.fact_snapshot_hash
    assert hash_a1 is not None
    assert hash_a1.startswith("obs-")
    # 断言 1: 同快照同 hash
    assert hash_a1 == hash_a2, "Determinism: identical snapshot must yield identical hash"

    # 断言 2: DTO 衍生字段/UI 状态变动绝对不影响底层物理快照 hash (独立性)
    data_a1.today_facts.derived_state.state_label = "完全不同的UI标签"
    data_a1.today_facts.derived_state.config_version = "v999.0"
    data_fresh = await service.get_review_loop_data("2026-09-28")
    assert data_fresh.today_facts.fact_snapshot_hash == hash_a1, "Independence: DTO mutation must not affect fact hash"

    # 2. 注入略微变动的快照 B (2026-09-29): 指数点位从 3800.0 变成 3800.1
    snap_b = MarketDailySnapshot(
        date="2026-09-29",
        snapshot_type="EOD_CLOSE",
        indices_snapshot=json.dumps([{"code": "sh000001", "name": "上证指数", "price": 3800.1, "pct_change": 1.0}]),
        limit_up_snapshot=json.dumps({"total_count": 50}),
        breadth_snapshot=json.dumps({"up": 3000, "down": 1000}),
        data_quality="FULL",
    )
    async_session.add(snap_b)
    await async_session.commit()

    data_b = await service.get_review_loop_data("2026-09-29")
    hash_b = data_b.today_facts.fact_snapshot_hash
    # 断言 3: 物理事实微小变化导致 hash 变化 (雪崩敏感性)
    assert hash_b != hash_a1, "Sensitivity: underlying fact mutation must cause hash mutation"

    # 3. 注入仅有 DailyReview 无 MarketDailySnapshot 的情况 (2026-09-30)
    rev_c = DailyReview(
        date="2026-09-30",
        market_overview=json.dumps([{"code": "sh000001", "name": "上证指数", "price": 3900.0}]),
        limit_up_analysis="{}",
        data_quality="FULL",
    )
    async_session.add(rev_c)
    await async_session.commit()

    data_c = await service.get_review_loop_data("2026-09-30")
    # 断言 4: 无 Observation 快照时严格为 None，严禁以 Review Payload 冒充
    assert data_c.today_facts.fact_snapshot_hash is None, "Missing semantic: absent ObservationSnapshot must strictly yield None"


@pytest.mark.asyncio
async def test_review_loop_strictly_read_only_idempotency(async_session: AsyncSession):
    """
    Phase 2B.3 Closure Patch 核心测试：get_review_loop_data 严格只读幂等，绝无写库副作用
    """
    from sqlalchemy import select, func
    service = CognitionReviewService(async_session)

    # 1. 注入昨日假说 (针对今日 2026-10-01)，但不执行核验
    hypo = MarketHypothesisCreate(
        created_date="2026-09-30",
        target_date="2026-10-01",
        hypothesis_type="SENTIMENT_CYCLE",
        target_asset="全市场",
        expected_scenario="REBOUND",
        premise_logic="预设逻辑",
        expected_phenomenon="预设现象",
        invalidation_condition="预设证伪",
        assertion_metrics={"expected_assertions": [], "invalidation_assertions": []},
    )
    await service.create_hypothesis(hypo)

    # 注入今日收盘复盘
    rev = DailyReview(date="2026-10-01", market_overview="[]", limit_up_analysis="{}")
    async_session.add(rev)
    await async_session.commit()

    # 查询前核验记录数应为 0
    cnt_stmt = select(func.count()).select_from(HypothesisVerification)
    before_cnt = (await async_session.execute(cnt_stmt)).scalar()
    assert before_cnt == 0

    # 2. 连续多次执行 get_review_loop_data
    loop1 = await service.get_review_loop_data("2026-10-01")
    loop2 = await service.get_review_loop_data("2026-10-01")

    # 断言：由于未显式核验，UI 聚合层不自动写库产生裁决
    assert loop1.yesterday_adjudication is None
    assert loop2.yesterday_adjudication is None

    # 查询后核验记录数依然严格为 0 (零写库副作用，零隐式提交)
    after_cnt = (await async_session.execute(cnt_stmt)).scalar()
    assert after_cnt == 0, "Idempotency: GET review-loop must be strictly read-only"
