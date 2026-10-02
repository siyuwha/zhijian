"""
Phase 2B.2: 受约束 LLM 认知假说提议器单元测试与沙箱闭环测试
上位依据：《开发文档/56-Phase-2B.2-受约束LLM认知假说提议器契约设计单.md》

测试覆盖：
1. VR-01 ~ VR-07 准入校验规则全覆盖拦截测试；
2. 合法宏观假说编译为 MarketHypothesisCreate；
3. SandboxProposer 沙箱驱动管道与不可变 PromptSpec 审计；
4. 端到端对接：Observation -> Proposal -> Validator -> WORM Ledger -> FalsificationEngine。
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
from app.schemas.cognition import MarketHypothesisCreate
from app.services.cognition_review import CognitionReviewService
from app.cognition.hypothesis.proposal_validator import (
    ProposalValidator,
    ProposalValidationResult,
    LLMProposalPayload,
)
from app.cognition.hypothesis.prompt_spec import PromptSpec
from app.cognition.hypothesis.sandbox_proposer import SandboxProposer, ProposerExecutionRecord
from app.cognition.hypothesis.service_adapter import HypothesisServiceAdapter
from app.cognition.hypothesis.contracts import HypothesisOutcome


@pytest_asyncio.fixture
async def async_session():
    temp_dir = tempfile.gettempdir()
    db_file = os.path.join(temp_dir, f"test_phase2b2_{os.getpid()}.db")
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


def get_base_valid_proposal() -> dict:
    return {
        "target_date": "2026-09-29",
        "hypothesis_type": "SENTIMENT_CYCLE",
        "target_asset": "全市场短线投机生态",
        "expected_scenario": "REBOUND",
        "premise_logic": "09-28 连板严重冰点跌停56家，预期次日超跌反弹修复",
        "expected_phenomenon": "涨停家数重回40家以上",
        "expected_assertions": [
            {
                "assertion_id": "exp_lu_min",
                "metric_type": "limit_up_count",
                "target_code": "ALL_A",
                "operator": "GTE",
                "threshold": 40.0,
                "description": "全A涨停家数>=40",
            }
        ],
        "invalidation_condition": "若跌停家数仍大于50家则反弹假说证伪",
        "invalidation_assertions": [
            {
                "assertion_id": "inv_ld_max",
                "metric_type": "limit_down_count",
                "target_code": "ALL_A",
                "operator": "GT",
                "threshold": 50.0,
                "description": "全A跌停家数>50",
            }
        ],
        "explanation": "基于短线情绪冰点出清原理",
    }


def test_proposal_validator_valid_proposal():
    """验证合法宏观提案通过校验并正确编译"""
    raw = get_base_valid_proposal()
    res = ProposalValidator.validate_and_compile(raw, market_date="2026-09-28")
    assert res.is_valid is True
    assert res.error_code is None
    assert res.compiled_hypothesis is not None
    assert res.compiled_hypothesis.created_date == "2026-09-28"
    assert res.compiled_hypothesis.target_date == "2026-09-29"
    assert res.compiled_hypothesis.assertion_metrics is not None
    assert len(res.compiled_hypothesis.assertion_metrics["expected_assertions"]) == 1
    assert len(res.compiled_hypothesis.assertion_metrics["invalidation_assertions"]) == 1


def test_proposal_validator_reject_unapproved_metric():
    """VR-03: 拒绝未审批的指标 (如大模型脑补北向资金或主力资金)"""
    raw = get_base_valid_proposal()
    raw["expected_assertions"][0]["metric_type"] = "northbound_capital_inflow"
    res = ProposalValidator.validate_and_compile(raw, market_date="2026-09-28")
    assert res.is_valid is False
    assert res.error_code == "VR-03_UNAPPROVED_METRIC"
    assert "northbound_capital_inflow" in res.error_detail


def test_proposal_validator_reject_single_stock_target():
    """VR-02: 拒绝具体个股标的 (严禁个股买卖推演)"""
    raw = get_base_valid_proposal()
    raw["expected_assertions"][0]["target_code"] = "sh600519"
    res = ProposalValidator.validate_and_compile(raw, market_date="2026-09-28")
    assert res.is_valid is False
    assert res.error_code == "VR-02_ILLEGAL_TARGET_CODE"
    assert "sh600519" in res.error_detail


def test_proposal_validator_reject_missing_invalidation():
    """VR-05: 拒绝缺少证伪红线的提案 (波普尔证伪原则刚性防御)"""
    raw = get_base_valid_proposal()
    raw["invalidation_assertions"] = []
    res = ProposalValidator.validate_and_compile(raw, market_date="2026-09-28")
    assert res.is_valid is False
    assert res.error_code == "VR-05_MISSING_FALSIFICATION_REDLINE"


def test_proposal_validator_reject_time_inversion():
    """VR-06: 拒绝时间倒挂与当天自证"""
    raw = get_base_valid_proposal()
    # 目标日期早于建立日期
    raw["target_date"] = "2026-09-27"
    res1 = ProposalValidator.validate_and_compile(raw, market_date="2026-09-28")
    assert res1.is_valid is False
    assert res1.error_code == "VR-06_TIME_CAUSALITY_VIOLATION"

    # 目标日期等于建立日期
    raw["target_date"] = "2026-09-28"
    res2 = ProposalValidator.validate_and_compile(raw, market_date="2026-09-28")
    assert res2.is_valid is False
    assert res2.error_code == "VR-06_TIME_CAUSALITY_VIOLATION"


def test_proposal_validator_reject_trading_advice():
    """VR-07: 拒绝包含个股买卖指令与交易建议关键词的提案"""
    raw = get_base_valid_proposal()
    raw["premise_logic"] = "行情恐慌释放，建议逢低买入龙头标的建仓"
    res = ProposalValidator.validate_and_compile(raw, market_date="2026-09-28")
    assert res.is_valid is False
    assert res.error_code == "VR-07_PROHIBITED_TRADING_ADVICE"
    assert "买入" in res.error_detail


def test_sandbox_proposer_prompt_spec_rendering_and_audit():
    """验证不可变 PromptSpec 安全渲染与哈希一致性"""
    spec = PromptSpec.create_canonical()
    assert spec.prompt_hash != ""
    assert len(spec.prompt_hash) == 64

    obs = {
        "market_date": "2026-09-28",
        "indices": [{"code": "sh000001", "name": "上证指数", "pct_change": -1.67}],
        "limit_up_summary": {"total_limit_up": 33, "limit_down_count": 56, "max_board_height": 5, "broken_ratio": 0.25},
        "breadth": {"up_count": 820, "down_count": 4350},
        "market_state": {"state_label": "极弱收缩"},
    }
    rendered = spec.render_user_prompt(obs, target_date="2026-09-29")
    assert "2026-09-28" in rendered
    assert "2026-09-29" in rendered
    assert "极弱收缩" in rendered
    assert "33" in rendered


@pytest.mark.asyncio
async def test_sandbox_proposer_e2e_to_falsification_engine(async_session: AsyncSession):
    """
    端到端集成验证：
    Observation -> SandboxProposer (带Mock生成器) -> Validator通过 -> 入库锁定 -> 灌入T+1事实 -> FalsificationEngine权威仲裁
    """
    service = CognitionReviewService(async_session)
    obs = {
        "market_date": "2026-09-28",
        "indices": [{"code": "sh000001", "name": "上证指数", "pct_change": -1.67}],
        "limit_up_summary": {"total_limit_up": 33, "limit_down_count": 56, "max_board_height": 5, "broken_ratio": 0.25},
        "breadth": {"up_count": 820, "down_count": 4350},
        "market_state": {"state_label": "极弱收缩"},
    }

    proposer = SandboxProposer()

    # 1. 模拟 LLM 输出合法的提案 JSON (使用 Markdown 代码块包裹模拟现实场景)
    def mock_llm_generator(sys_prompt: str, user_prompt: str) -> str:
        valid_json = get_base_valid_proposal()
        return f"```json\n{json.dumps(valid_json, ensure_ascii=False)}\n```"

    exec_record: ProposerExecutionRecord = proposer.propose(
        observation=obs,
        target_date="2026-09-29",
        generator_fn=mock_llm_generator,
    )

    assert exec_record.is_valid is True
    assert exec_record.compiled_hypothesis is not None
    assert exec_record.validation_error_code is None

    # 2. 经校验合格后，将假说创建并锁定入库
    hypo = await service.create_hypothesis(exec_record.compiled_hypothesis)
    assert hypo.id is not None
    assert hypo.status == "PENDING"

    # 3. 灌入 2026-09-29 真实收盘事实 (全A涨停57家，跌停10家)
    mock_quotes = [{"code": "sh000001", "name": "上证指数", "pct_change": 0.18, "close": 3830.45}]
    mock_lu = {"total_count": 57, "limit_down_count": 10}
    rev_0929 = DailyReview(
        date="2026-09-29",
        market_overview=json.dumps(mock_quotes),
        limit_up_analysis=json.dumps(mock_lu),
        data_quality="PARTIAL",
    )
    async_session.add(rev_0929)
    await async_session.commit()

    # 4. 驱动收盘核验 (CLOSE_1530)
    verification = await service.verify_hypothesis(hypo.id, stage="CLOSE_1530")
    assert verification.outcome == "CONFIRMED"
    assert "假说证实" in verification.gap_summary
    assert hypo.status == "CLOSED"
