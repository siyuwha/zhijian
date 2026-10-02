"""
Phase 2B.1 Minimal Hypothesis & Falsification Loop Contract & Unit Tests
上位依据：《开发文档/52-Phase-2B.1-Minimal-Hypothesis-Falsification-Contract.md》
验证铁律：
1. 证伪优先 (Falsification-First)
2. 缺数防伪 (Missing != False, INCONCLUSIVE)
3. 严格认知验证，零交易预测
4. 联合唯一防重与不可篡改幂等
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
from app.models.cognition import MarketHypothesis, HypothesisVerification
from app.schemas.cognition import MarketHypothesisCreate
from app.services.cognition_review import CognitionReviewService
from app.cognition.hypothesis.service_adapter import HypothesisServiceAdapter
from app.cognition.hypothesis.contracts import (
    MetricType,
    OperatorType,
    UniverseType,
    HypothesisOutcome,
)


@pytest_asyncio.fixture
async def async_session():
    temp_dir = tempfile.gettempdir()
    db_file = os.path.join(temp_dir, f"test_phase2b1_{os.getpid()}.db")
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
async def test_hypothesis_service_adapter_compile_and_extract():
    """验证服务适配器编译收窄 AST 与提取真实观测事实"""
    hypo = MarketHypothesis(
        id=1,
        created_date="2026-09-28",
        target_date="2026-09-29",
        hypothesis_type="SENTIMENT_CYCLE",
        target_asset="全市场短线情绪",
        expected_scenario="WEAK_CONSOLIDATION",
        premise_logic="高位退潮预期惯性弱势",
        expected_phenomenon="大盘微涨跌且涨停受限",
        invalidation_condition="暴涨突破>1.5%",
        assertion_metrics=json.dumps({
            "expected_assertions": [
                {
                    "assertion_id": "exp_sh_pct",
                    "metric_type": "pct_change",
                    "target_code": "sh000001",
                    "operator": "BETWEEN",
                    "threshold": [-1.0, 1.0],
                }
            ],
            "invalidation_assertions": [
                {
                    "assertion_id": "inv_sh_surge",
                    "metric_type": "pct_change",
                    "target_code": "sh000001",
                    "operator": "GT",
                    "threshold": 1.5,
                }
            ]
        }),
    )

    # 1. 编译 AST
    hypo_def = HypothesisServiceAdapter.compile_hypothesis_definition(hypo)
    assert hypo_def.hypothesis_id == "hypo_1"
    assert len(hypo_def.expected_assertions) == 1
    assert len(hypo_def.invalidation_assertions) == 1
    assert hypo_def.expected_assertions[0].operator == OperatorType.BETWEEN
    assert hypo_def.invalidation_assertions[0].operator == OperatorType.GT

    # 2. 抽取真实观测切片
    mock_quotes = [
        {"code": "sh000001", "name": "上证指数", "pct_change": 0.18, "close": 3830.45},
        {"code": "sz399001", "name": "深证成指", "pct_change": 0.34, "close": 12901.95},
    ]
    mock_lu = {"total_count": 57, "broken_count": 8, "limit_down_count": 0}
    mock_breadth = {"up_count": 2800, "down_count": 2200}

    rev = DailyReview(
        date="2026-09-29",
        market_overview=json.dumps(mock_quotes),
        limit_up_analysis=json.dumps(mock_lu),
        data_quality="PARTIAL",
    )
    snap = MarketDailySnapshot(
        date="2026-09-29",
        snapshot_type="EOD_CLOSE",
        indices_snapshot=json.dumps(mock_quotes),
        breadth_snapshot=json.dumps(mock_breadth),
    )

    obs = HypothesisServiceAdapter.extract_observation_data("2026-09-29", rev, snap)
    assert obs["status"] == "AVAILABLE"
    assert len(obs["stocks"]) == 3  # 2 indices + 1 ALL_A macro proxy
    all_a_item = next(s for s in obs["stocks"] if s["code"] == "ALL_A")
    assert all_a_item["limit_up_count"] == 57.0
    assert all_a_item["up_count"] == 2800.0


@pytest.mark.asyncio
async def test_falsification_triggered_on_invalidating_market_move():
    """验证证伪优先：当反向证伪断言触发时，假说刚性判定 FALSIFIED"""
    hypo = MarketHypothesis(
        id=2,
        created_date="2026-09-28",
        target_date="2026-09-29",
        hypothesis_type="SENTIMENT_CYCLE",
        target_asset="全市场短线情绪",
        expected_scenario="WEAK_CONSOLIDATION",
        premise_logic="预期弱势防守",
        expected_phenomenon="指数低位",
        invalidation_condition="大盘微涨即触发空头证伪",
        assertion_metrics=json.dumps({
            "expected_assertions": [
                {
                    "assertion_id": "exp_sh_drop",
                    "metric_type": "pct_change",
                    "target_code": "sh000001",
                    "operator": "LT",
                    "threshold": 0.0,
                }
            ],
            "invalidation_assertions": [
                {
                    "assertion_id": "inv_sh_green_fail",
                    "metric_type": "pct_change",
                    "target_code": "sh000001",
                    "operator": "GT",
                    "threshold": 0.10,  # 只要 > +0.10% 即反向击溃空头假说
                }
            ]
        }),
    )

    # 真实事实：09-29 上证涨 +0.18%
    mock_quotes = [{"code": "sh000001", "name": "上证指数", "pct_change": 0.18, "close": 3830.45}]
    rev = DailyReview(date="2026-09-29", market_overview=json.dumps(mock_quotes), limit_up_analysis="{}")

    adj_res = HypothesisServiceAdapter.adjudicate(hypo, rev, None)
    assert adj_res.outcome == HypothesisOutcome.FALSIFIED
    assert adj_res.falsification_triggered is True
    assert "证伪断言 'inv_sh_green_fail' 触发" in adj_res.details


@pytest.mark.asyncio
async def test_confirmed_when_expected_conditions_met():
    """验证假说确证：当预期断言均满足且未触碰证伪时，判定 CONFIRMED"""
    hypo = MarketHypothesis(
        id=3,
        created_date="2026-09-29",
        target_date="2026-09-30",
        hypothesis_type="SENTIMENT_CYCLE",
        target_asset="全市场短线情绪",
        expected_scenario="ROTATION",
        premise_logic="超跌反弹后分化整理",
        expected_phenomenon="指数涨幅在 [-0.5, 0.5] 且涨停 >= 50 家",
        invalidation_condition="暴跌 <-1.5%",
        assertion_metrics=json.dumps({
            "expected_assertions": [
                {
                    "assertion_id": "exp_sh_range",
                    "metric_type": "pct_change",
                    "target_code": "sh000001",
                    "operator": "BETWEEN",
                    "threshold": [-0.5, 0.5],
                },
                {
                    "assertion_id": "exp_lu_count",
                    "metric_type": "limit_up_count",
                    "target_code": "ALL_A",
                    "operator": "GTE",
                    "threshold": 50,
                }
            ],
            "invalidation_assertions": [
                {
                    "assertion_id": "inv_crash",
                    "metric_type": "pct_change",
                    "target_code": "sh000001",
                    "operator": "LT",
                    "threshold": -1.5,
                }
            ]
        }),
    )

    # 09-30 真实事实：上证 +0.31%，涨停 52 家
    mock_quotes = [{"code": "sh000001", "name": "上证指数", "pct_change": 0.31, "close": 3842.19}]
    mock_lu = {"total_count": 52}
    rev = DailyReview(date="2026-09-30", market_overview=json.dumps(mock_quotes), limit_up_analysis=json.dumps(mock_lu))

    adj_res = HypothesisServiceAdapter.adjudicate(hypo, rev, None)
    assert adj_res.outcome == HypothesisOutcome.CONFIRMED
    assert adj_res.falsification_triggered is False


@pytest.mark.asyncio
async def test_inconclusive_when_data_missing():
    """验证缺数防伪：目标日期数据缺失时严禁假判，强制裁决 INCONCLUSIVE"""
    hypo = MarketHypothesis(
        id=4,
        created_date="2026-10-01",
        target_date="2026-10-02",
        hypothesis_type="SENTIMENT_CYCLE",
        target_asset="全市场短线情绪",
        expected_scenario="ROTATION",
        premise_logic="推演假期后行情",
        expected_phenomenon="指数平开",
        invalidation_condition="巨震",
        assertion_metrics=json.dumps({
            "expected_assertions": [
                {"assertion_id": "exp_1", "metric_type": "pct_change", "target_code": "sh000001", "operator": "GT", "threshold": 0.0}
            ]
        }),
    )

    # 传入空复盘数据 (例如未来交易日尚未收盘)
    adj_res = HypothesisServiceAdapter.adjudicate(hypo, None, None)
    assert adj_res.outcome == HypothesisOutcome.INCONCLUSIVE


@pytest.mark.asyncio
async def test_cognition_review_service_e2e_verify_flow(async_session: AsyncSession):
    """端到端验证：通过 CognitionReviewService 创建假说、收盘核对并验证物理幂等不可篡改性"""
    service = CognitionReviewService(async_session)

    # 1. 创建假说
    payload = MarketHypothesisCreate(
        target_date="2026-09-30",
        hypothesis_type="SENTIMENT_CYCLE",
        target_asset="全市场短线情绪",
        expected_scenario="ROTATION",
        premise_logic="09-29弱修复后预期09-30平稳轮动",
        expected_phenomenon="指数窄幅震荡",
        invalidation_condition="暴跌击溃",
        assertion_metrics={
            "expected_assertions": [
                {"assertion_id": "exp_sh", "metric_type": "pct_change", "target_code": "sh000001", "operator": "BETWEEN", "threshold": [-0.5, 0.5]},
                {"assertion_id": "exp_lu", "metric_type": "limit_up_count", "target_code": "ALL_A", "operator": "GTE", "threshold": 50}
            ],
            "invalidation_assertions": [
                {"assertion_id": "inv_crash", "metric_type": "pct_change", "target_code": "sh000001", "operator": "LT", "threshold": -1.5}
            ]
        }
    )
    hypo = await service.create_hypothesis(payload)
    assert hypo.id is not None
    assert hypo.status == "PENDING"

    # 2. 插入 09-30 真实收盘复盘
    mock_quotes = [{"code": "sh000001", "name": "上证指数", "pct_change": 0.31, "close": 3842.19}]
    mock_lu = {"total_count": 52}
    rev = DailyReview(
        date="2026-09-30",
        market_overview=json.dumps(mock_quotes),
        limit_up_analysis=json.dumps(mock_lu),
        data_quality="PARTIAL",
    )
    async_session.add(rev)
    await async_session.commit()

    # 3. 触发收盘终核 (CLOSE_1530)
    v1 = await service.verify_hypothesis(hypo.id, stage="CLOSE_1530")
    assert v1.outcome == "CONFIRMED"
    assert "假说证实" in v1.gap_summary

    # 4. 验证幂等性：重复调用必须返回已存在快照，严禁覆写
    v2 = await service.verify_hypothesis(hypo.id, stage="CLOSE_1530")
    assert v2.id == v1.id
    assert v2.verified_at == v1.verified_at

    # 5. 校验列表查询能一并拉出快照数据 (供前端 UI 消费)
    res = await service.get_hypotheses(target_date="2026-09-30")
    assert res["total"] == 1
    item = res["items"][0]
    assert len(item["verifications"]) == 1
    assert item["verifications"][0]["outcome"] == "CONFIRMED"
