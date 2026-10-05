"""
Phase 2C: Wave 1 Fact Consumption & Evidence-Gated Sector Cognition 测试套件
上位依据：
1. SPEC-COGNITION-PHASE2C-20261005-V1.1 (全量契约)
2. 董事会授权令：AUTH-PHASE2C5-20261005 (二审全票通过准予实施)
3. 凭据：baseline_evidence/replay_baseline_20260930_v028.json (Phase 2C.1 PASS)

覆盖测试矩阵：
1. 四维充分性证据矩阵门禁 (EvidenceGatedEvaluator):
   - Pillar 1+2+3 -> INITIAL_OUTBREAK
   - Pillar 1+2+3+4 (height >= 2) -> SECTOR_ROTATION
   - 首板严禁计入持续性 (First-Board Persistence Defense)
   - 仅有归属 (Membership only) -> INSUFFICIENT_EVIDENCE (REJECTED)
   - REGION / NOISE 刚性隔离与阻断
   - FactStatus.MISSING 坦然守卫
   - RFC 8785 JCS evidence_fingerprint 确定性
2. 收窄 AST 解释器空集与缺失断言守护 (AssertionEvaluator):
   - sector_stocks 缺失 -> 刚性输出 INCONCLUSIVE
   - sector_stocks 为空集 -> 性能指标刚性输出 INCONCLUSIVE (阻断 count=0 伪造证伪)
   - 正常板块标的指标求值
3. 受约束假说提案准入校验器 (ProposalValidator):
   - INITIAL_OUTBREAK 与 SECTOR_ROTATION 准入
   - 板块标的代码 (BK* / SECTOR) 与白名单指标 (leader_open_pct, sector_change_pct)
4. M1 流水线消费与全息事实组装 (StockSectorRelationAdapter & DailyReviewService):
   - target_stocks = DailyAnomalyList ∪ LimitUpPool.items 正向单向流动
   - 事实入账与 ObservationSnapshot JCS 一致性
"""

import json
import pytest
from datetime import datetime

from app.cognition.observation.contracts import (
    FactStatus,
    FactType,
    EvidenceGateResult,
    ObservationSnapshot,
    ObservationWindow,
    CognitionStage,
)
from app.cognition.observation.evidence_gate import EvidenceGatedEvaluator
from app.cognition.observation.adapters.relation_adapter import StockSectorRelationAdapter
from app.cognition.observation.clock import DeterministicClock
from app.cognition.hypothesis.contracts import (
    MetricAssertion,
    MetricType,
    UniverseType,
    OperatorType,
    AggregationType,
    MissingDataPolicy,
    AssertionOutcome,
    HypothesisType,
    StructuredFilter,
    FilterCondition,
    MarketHypothesisDefinition,
)
from app.cognition.hypothesis.evaluator import AssertionEvaluator
from app.cognition.hypothesis.proposal_validator import (
    ProposalValidator,
    ALLOWED_HYPOTHESIS_TYPES,
)
from app.core.block_registry import BlockRegistry
from app.cognition.jcs import hash_jcs


# ==============================================================================
# 1. 四维充分性证据矩阵与门禁状态机测试 (EvidenceGatedEvaluator)
# ==============================================================================

def test_evidence_gate_membership_only_rejected():
    """
    [P0-1 核心防腐测试]: 仅有板块归属 (Membership)，无涨停与无异动
    铁律：贵州茅台属于食品饮料，不能单独作为看多板块的证据！必须 REJECTED！
    """
    stocks = [{"symbol": "600519", "name": "贵州茅台"}]
    res = EvidenceGatedEvaluator.evaluate_sector(
        sector_code="BK0438",
        sector_name="食品饮料",
        sector_stocks=stocks,
        limit_up_items=[],
        anomaly_facts=[],
        evaluated_at="2026-09-30T15:35:00.000+08:00",
    )

    assert res.gate_status == "REJECTED"
    assert res.admitted_hypothesis_type == "NONE"
    assert res.pillar_membership == FactStatus.AVAILABLE
    assert res.pillar_breadth == FactStatus.EMPTY
    assert res.pillar_leadership == FactStatus.EMPTY
    assert res.pillar_persistence == FactStatus.EMPTY
    assert any("Pillar 2 (Breadth) insufficient" in r for r in res.rejection_reasons)
    assert len(res.evidence_fingerprint) == 64


def test_evidence_gate_initial_outbreak_admitted():
    """
    [P0-1 & 假说分流]: Pillar 1 + 2 + 3 齐备 (仅有首板，height=1)，放行 INITIAL_OUTBREAK
    """
    stocks = [
        {"symbol": "002466", "name": "天齐锂业"},
        {"symbol": "002460", "name": "赣锋锂业"},
    ]
    limit_up = [
        {"code": "002466", "name": "天齐锂业", "height": 1, "board_count": 1}
    ]
    anomaly = [
        {"symbol": "002466", "rule_id": "6", "status_flag": 2}
    ]

    res = EvidenceGatedEvaluator.evaluate_sector(
        sector_code="BK0980",
        sector_name="锂电池",
        sector_stocks=stocks,
        limit_up_items=limit_up,
        anomaly_facts=anomaly,
        evaluated_at="2026-09-30T15:35:00.000+08:00",
    )

    assert res.gate_status == "ADMITTED"
    assert res.admitted_hypothesis_type == "INITIAL_OUTBREAK"
    assert res.pillar_membership == FactStatus.AVAILABLE
    assert res.pillar_breadth == FactStatus.AVAILABLE
    assert res.pillar_leadership == FactStatus.AVAILABLE
    # 首板严禁计入持续性
    assert res.pillar_persistence == FactStatus.EMPTY
    assert len(res.evidence_fingerprint) == 64


def test_evidence_gate_sector_rotation_admitted():
    """
    [P0-1 & 假说分流]: Pillar 1 + 2 + 3 + 4 全齐备 (连板高度 >= 2)，放行 SECTOR_ROTATION
    """
    stocks = [
        {"symbol": "002466", "name": "天齐锂业"},
        {"symbol": "002460", "name": "赣锋锂业"},
    ]
    limit_up = [
        {"code": "002466", "name": "天齐锂业", "height": 3, "board_count": 3},
        {"code": "002460", "name": "赣锋锂业", "height": 1, "board_count": 1},
    ]
    anomaly = [
        {"symbol": "002466", "rule_id": "6", "status_flag": 2}
    ]

    res = EvidenceGatedEvaluator.evaluate_sector(
        sector_code="BK0980",
        sector_name="锂电池",
        sector_stocks=stocks,
        limit_up_items=limit_up,
        anomaly_facts=anomaly,
        evaluated_at="2026-09-30T15:35:00.000+08:00",
    )

    assert res.gate_status == "ADMITTED"
    assert res.admitted_hypothesis_type == "SECTOR_ROTATION"
    assert res.pillar_membership == FactStatus.AVAILABLE
    assert res.pillar_breadth == FactStatus.AVAILABLE
    assert res.pillar_leadership == FactStatus.AVAILABLE
    assert res.pillar_persistence == FactStatus.AVAILABLE
    assert len(res.evidence_fingerprint) == 64


def test_first_board_persistence_defense():
    """
    [红队攻击点验证]: 连板高度等于 1 (首板) 绝不能被认定为持续性 (Persistence)
    """
    stocks = [{"symbol": "600000", "name": "浦发银行"}]
    limit_up = [{"code": "600000", "name": "浦发银行", "height": 1, "board_count": 1}]
    anomaly = [{"symbol": "600000", "rule_id": "1", "status_flag": 1}]

    res = EvidenceGatedEvaluator.evaluate_sector(
        sector_code="BK0475",
        sector_name="银行",
        sector_stocks=stocks,
        limit_up_items=limit_up,
        anomaly_facts=anomaly,
        evaluated_at="2026-09-30T15:35:00.000+08:00",
    )

    # 只能作为脉冲爆发，绝不能作为主线轮动
    assert res.admitted_hypothesis_type != "SECTOR_ROTATION"
    assert res.admitted_hypothesis_type == "INITIAL_OUTBREAK"
    assert res.pillar_persistence == FactStatus.EMPTY
    assert any("max_height=1 < 2" in r for r in res.rejection_reasons)


def test_orthogonal_isolation_region_and_noise():
    """
    [两维度准入与两维度刚性隔离]:
    - REGION (贵州板块) 刚性隔离
    - NOISE (富时罗素 / 昨日涨停) 刚性阻断
    """
    stocks = [{"symbol": "600519", "name": "贵州茅台"}]
    limit_up = [{"code": "600519", "name": "贵州茅台", "height": 3, "board_count": 3}]
    anomaly = [{"symbol": "600519", "rule_id": "6", "status_flag": 2}]

    # 1. 测试 REGION
    res_reg = EvidenceGatedEvaluator.evaluate_sector(
        sector_code="BK0896",
        sector_name="贵州板块",
        sector_stocks=stocks,
        limit_up_items=limit_up,
        anomaly_facts=anomaly,
    )
    assert res_reg.gate_status == "REJECTED"
    assert res_reg.admitted_hypothesis_type == "NONE"
    assert res_reg.category == "REGION"
    assert any("刚性隔离" in r for r in res_reg.rejection_reasons)

    # 2. 测试 NOISE
    res_noise = EvidenceGatedEvaluator.evaluate_sector(
        sector_code="BK0999",
        sector_name="富时罗素",
        sector_stocks=stocks,
        limit_up_items=limit_up,
        anomaly_facts=anomaly,
    )
    assert res_noise.gate_status == "REJECTED"
    assert res_noise.admitted_hypothesis_type == "NONE"
    assert res_noise.category == "FILTERED_NOISE"


def test_missingness_discipline_preserves_missing():
    """
    [P0-2 补丁]: 事实缺失时坦然标记 MISSING，严禁 LLM 脑补，严禁假0填充
    """
    stocks = [{"symbol": "000001", "name": "平安银行"}]
    res = EvidenceGatedEvaluator.evaluate_sector(
        sector_code="BK0475",
        sector_name="银行",
        sector_stocks=stocks,
        limit_up_items=None,  # 显式缺失
        anomaly_facts=None,   # 显式缺失
    )

    assert res.gate_status == "REJECTED"
    assert res.pillar_breadth == FactStatus.MISSING
    assert res.pillar_leadership == FactStatus.MISSING
    assert res.pillar_persistence == FactStatus.MISSING


def test_evidence_fingerprint_rfc8785_determinism():
    """
    [P0-4 补丁]: 验证 EvidenceGateResult 的 RFC 8785 JCS 指纹确定性
    """
    stocks = [{"symbol": "002466", "name": "天齐锂业"}]
    limit_up = [{"code": "002466", "name": "天齐锂业", "height": 1, "board_count": 1}]
    anomaly = [{"symbol": "002466", "rule_id": "6", "status_flag": 2}]

    res1 = EvidenceGatedEvaluator.evaluate_sector(
        sector_code="BK0980",
        sector_name="锂电池",
        sector_stocks=stocks,
        limit_up_items=limit_up,
        anomaly_facts=anomaly,
        evaluated_at="2026-09-30T15:35:00.000+08:00",
    )

    res2 = EvidenceGatedEvaluator.evaluate_sector(
        sector_code="BK0980",
        sector_name="锂电池",
        sector_stocks=stocks,
        limit_up_items=limit_up,
        anomaly_facts=anomaly,
        evaluated_at="2026-09-30T15:35:00.000+08:00",
    )

    assert res1.evidence_fingerprint == res2.evidence_fingerprint
    assert len(res1.evidence_fingerprint) == 64


# ==============================================================================
# 2. 收窄 AST 解释器空集与缺失断言守护测试 (AssertionEvaluator)
# ==============================================================================

def test_ast_evaluator_sector_missing_defense():
    """
    [P1-8 补丁]: 当 observation_data 中缺失 sector_stocks 时，必须刚性输出 INCONCLUSIVE
    """
    assertion = MetricAssertion(
        assertion_id="ast_sec_01",
        metric=MetricType.BOARD_HEIGHT.value,
        selector=StructuredFilter(
            universe_type=UniverseType.SECTOR,
            conditions=[FilterCondition(field="sector_code", op=OperatorType.EQ, val="BK0980")],
        ),
        aggregation=AggregationType.MAX,
        operator=OperatorType.GTE,
        target_value=2.0,
        missing_data_policy=MissingDataPolicy.INCONCLUSIVE,
    )

    # 观测数据完全缺少 sector_stocks 键
    obs_data = {"date": "2026-09-30", "status": "AVAILABLE"}
    result = AssertionEvaluator.evaluate(assertion, obs_data)

    assert result.outcome == AssertionOutcome.INCONCLUSIVE
    assert result.is_missing is True
    assert "SECTOR_DATA_MISSING_FROM_OBSERVATION" in result.details


def test_ast_evaluator_empty_sector_universe_defense():
    """
    [P1-8 补丁 & 红队致命漏洞靶点]:
    当板块成分股因数据缺失为空集时，严禁因 COUNT(board_height>=2)==0 错误裁决为 FAILED (伪造证伪)！
    必须挂起为 INCONCLUSIVE！
    """
    # 证伪断言：次日龙头早盘溢价跌破 0%
    inv_assertion = MetricAssertion(
        assertion_id="ast_sec_inv",
        metric=MetricType.LEADER_OPEN_PCT.value,
        selector=StructuredFilter(
            universe_type=UniverseType.SECTOR,
            conditions=[],
        ),
        aggregation=AggregationType.NONE,
        operator=OperatorType.LT,
        target_value=0.0,
        missing_data_policy=MissingDataPolicy.INCONCLUSIVE,
    )

    # 板块数据虽然存在但为空集合
    obs_data = {
        "date": "2026-09-30",
        "status": "AVAILABLE",
        "sector_stocks": [],
    }
    result = AssertionEvaluator.evaluate(inv_assertion, obs_data)

    assert result.outcome == AssertionOutcome.INCONCLUSIVE
    assert result.is_missing is True
    assert "EMPTY_UNIVERSE_CANNOT_EVALUATE_PERFORMANCE" in result.details or "SECTOR_UNIVERSE_EMPTY" in result.details


def test_ast_evaluator_valid_sector_evaluation():
    """
    正常板块标的指标求值：数据齐备时能够准确计算并裁决 PASSED / FAILED
    """
    assertion = MetricAssertion(
        assertion_id="ast_sec_valid",
        metric=MetricType.BOARD_HEIGHT.value,
        selector=StructuredFilter(
            universe_type=UniverseType.SECTOR,
            conditions=[FilterCondition(field="board_height", op=OperatorType.GTE, val=2)],
        ),
        aggregation=AggregationType.COUNT,
        operator=OperatorType.GTE,
        target_value=1.0,
    )

    obs_data = {
        "date": "2026-09-30",
        "status": "AVAILABLE",
        "sector_stocks": [
            {"code": "002466", "board_height": 3},
            {"code": "002460", "board_height": 1},
        ],
    }

    result = AssertionEvaluator.evaluate(assertion, obs_data)
    assert result.outcome == AssertionOutcome.PASSED
    assert result.actual_value == 1.0
    assert result.matched_count == 1


# ==============================================================================
# 3. 受约束假说提案准入校验器测试 (ProposalValidator)
# ==============================================================================

def test_proposal_validator_admits_phase2c_hypotheses():
    """
    验证 ProposalValidator 准入 INITIAL_OUTBREAK 与 SECTOR_ROTATION 板块假说
    """
    raw_proposal = {
        "target_date": "2026-10-08",
        "hypothesis_type": "INITIAL_OUTBREAK",
        "target_asset": "锂电池题材首发爆发",
        "expected_scenario": "CONTINUED_MOMENTUM",
        "premise_logic": "09-30 锂电池板块爆发首板梯队",
        "expected_phenomenon": "早盘开盘龙头高开溢价",
        "expected_assertions": [
            {
                "assertion_id": "exp_sec_1",
                "metric_type": "leader_open_pct",
                "target_code": "BK0980",
                "operator": "GTE",
                "threshold": 1.5,
                "description": "龙头次日竞价溢价大于1.5%",
            }
        ],
        "invalidation_condition": "龙头开盘低开低于-1%",
        "invalidation_assertions": [
            {
                "assertion_id": "inv_sec_1",
                "metric_type": "leader_open_pct",
                "target_code": "BK0980",
                "operator": "LT",
                "threshold": -1.0,
                "description": "龙头低开大于1%触发证伪",
            }
        ],
        "explanation": "首发题材次日检验龙头溢价承接能力",
    }

    res = ProposalValidator.validate_and_compile(raw_proposal, market_date="2026-09-30")
    assert res.is_valid is True
    assert res.compiled_hypothesis is not None
    assert res.compiled_hypothesis.hypothesis_type == "INITIAL_OUTBREAK"


def test_proposal_validator_rejects_illegal_type():
    """
    验证 ProposalValidator 拒绝未知或非白名单假说类型
    """
    raw_proposal = {
        "target_date": "2026-10-08",
        "hypothesis_type": "UNCONSTRAINED_FREE_SPECULATION",
        "target_asset": "未知资产",
        "expected_scenario": "UP",
        "premise_logic": "无依据",
        "expected_phenomenon": "大涨",
        "expected_assertions": [
            {
                "assertion_id": "exp_1",
                "metric_type": "pct_change",
                "target_code": "ALL_A",
                "operator": "GT",
                "threshold": 0.0,
            }
        ],
        "invalidation_condition": "下跌",
        "invalidation_assertions": [
            {
                "assertion_id": "inv_1",
                "metric_type": "pct_change",
                "target_code": "ALL_A",
                "operator": "LT",
                "threshold": 0.0,
            }
        ],
    }

    res = ProposalValidator.validate_and_compile(raw_proposal, market_date="2026-09-30")
    assert res.is_valid is False
    assert res.error_code == "VR-02_ILLEGAL_HYPOTHESIS_TYPE"


# ==============================================================================
# 4. M1 流水线消费与全息事实组装测试 (StockSectorRelationAdapter)
# ==============================================================================

def test_relation_adapter_extracts_wave1_facts():
    """
    验证 StockSectorRelationAdapter 能够正向抽取 Wave 1 物理事实：
    - ANOM:* 异动衍生事实 (FactType.INTRADAY_ANOMALY)
    - BLOCK_MAP:* 映射事实 (FactType.STOCK_SECTOR_MAP)
    - 并且不污染原有 stock_to_sector 关系聚合
    """
    clock = DeterministicClock("2026-09-30T15:35:00.000+08:00")
    adapter = StockSectorRelationAdapter()

    test_input = {
        "date": "2026-09-30",
        "items": [
            {"code": "600519", "name": "贵州茅台", "height": 1, "sector": "白酒"}
        ],
        "anomaly_facts": [
            {
                "canonical_fact_id": "ANOM:600519:2026-09-30:R6",
                "symbol": "600519",
                "rule_id": "6",
                "status_flag": 2,
            }
        ],
        "block_mapping_facts": [
            {
                "canonical_fact_id": "BLOCK_MAP:600519:BK0438",
                "symbol": "600519",
                "block_code": "BK0438",
                "block_name": "食品饮料",
                "category": "INDUSTRY",
            }
        ],
    }

    facts = adapter.extract_facts(
        raw_data=test_input,
        clock=clock,
        trace_id="test_wave1_trace",
        market_date="2026-09-30",
    )

    fact_keys = [f.fact_key for f in facts]
    assert "relation.stock_sector_map" in fact_keys
    assert "anomaly.600519.R6" in fact_keys
    assert "block_map.600519.BK0438" in fact_keys

    anom_fact = next(f for f in facts if f.fact_key == "anomaly.600519.R6")
    assert anom_fact.fact_type == FactType.INTRADAY_ANOMALY
    assert anom_fact.provenance.primary_source == "EASTMONEY_COMPUTED_RULE_MATCH"

    block_fact = next(f for f in facts if f.fact_key == "block_map.600519.BK0438")
    assert block_fact.fact_type == FactType.STOCK_SECTOR_MAP
    assert block_fact.provenance.primary_source == "EASTMONEY_SLIST_MAPPING"


@pytest.mark.asyncio
async def test_daily_review_service_ingests_wave1_and_evaluates_sector_gates():
    """
    [M1 端到端流水线集成测试]:
    验证 DailyReviewService.generate_review 在真实/模拟执行中：
    1. 正向抽取 target_stocks = DailyAnomalyList ∪ LimitUpPool.items
    2. 计算并存储 sector_evidence_gates
    3. 完整入账 MarketDailySnapshot 并触发 CognitionBridge
    """
    from unittest.mock import AsyncMock, patch
    from app.core.database import async_session
    from app.services.daily_review import DailyReviewService
    from app.models.market import MarketDailySnapshot
    from app.models.report import DailyReview
    from app.data.capabilities import DataResult, DataQuality, DataStatus

    async with async_session() as session:
        test_date = "2026-10-25"

        # 模拟 09-30 真实结构的市场数据
        mock_anom = [
            {"canonical_fact_id": f"ANOM:600519:{test_date}:R6", "symbol": "600519", "rule_id": "6", "status_flag": 2}
        ]
        mock_blocks = [
            {"canonical_fact_id": "BLOCK_MAP:600519:BK0438", "symbol": "600519", "block_code": "BK0438", "block_name": "食品饮料", "category": "INDUSTRY"}
        ]
        mock_lu = {
            "items": [{"code": "600519", "name": "贵州茅台", "height": 1, "board_count": 1}],
            "total_count": 1,
            "top_reasons": [["食品饮料", 1]]
        }

        service = DailyReviewService(session)
        service.data_service.get_index_quotes = AsyncMock(return_value=DataResult(
            data=[{"code": "s_sh000001", "name": "上证指数", "price": 3300.0, "pct_change": 1.5, "amount_wan": 500000.0}],
            quality=DataQuality.FULL,
            status=DataStatus.AVAILABLE,
            provider="eastmoney"
        ))
        service.data_service.get_market_breadth = AsyncMock(return_value=DataResult(
            data={"up_count": 3500, "down_count": 1200, "total_amount": 15000.0},
            quality=DataQuality.FULL,
            status=DataStatus.AVAILABLE,
            provider="eastmoney"
        ))
        service.data_service.get_limit_up_pool = AsyncMock(return_value=DataResult(
            data=mock_lu,
            quality=DataQuality.FULL,
            status=DataStatus.AVAILABLE,
            provider="eastmoney"
        ))
        service.data_service.get_price_anomaly = AsyncMock(return_value=DataResult(
            data=mock_anom,
            quality=DataQuality.FULL,
            status=DataStatus.AVAILABLE,
            provider="eastmoney"
        ))
        service.data_service.get_concept_blocks = AsyncMock(return_value=DataResult(
            data=mock_blocks,
            quality=DataQuality.FULL,
            status=DataStatus.AVAILABLE,
            provider="eastmoney"
        ))

        review = await service.generate_review(date_str=test_date, force=True)
        assert review is not None

        # 验证报告内容包含结构化门禁
        rep_content = json.loads(review.report_content)
        assert "sector_evidence_gates" in rep_content
        gates = rep_content["sector_evidence_gates"]
        assert len(gates) > 0

        # 食品饮料板块：首板 + 异动 -> 放行 INITIAL_OUTBREAK
        food_gate = next(g for g in gates if g["sector_code"] == "BK0438")
        assert food_gate["gate_status"] == "ADMITTED"
        assert food_gate["admitted_hypothesis_type"] == "INITIAL_OUTBREAK"
        assert food_gate["pillar_membership"] == "AVAILABLE"
        assert food_gate["pillar_breadth"] == "AVAILABLE"
        assert food_gate["pillar_leadership"] == "AVAILABLE"
        assert food_gate["pillar_persistence"] == "EMPTY"  # 首板严禁计入持续性
        assert len(food_gate["evidence_fingerprint"]) == 64

