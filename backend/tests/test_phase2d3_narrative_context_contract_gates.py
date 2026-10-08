"""
Phase 2D.3-A: Narrative Context Contract Freeze Gates 验收套件
上位依据：
1. 最高董事会 2026-10-09 裁决令：《有条件批准 Phase 2D.3-A，锁死 7 条刚性红线》
2. 《DOC-80 · Phase 2D.3 受约束 LLM 实战战报生成器技术设计单》

门禁清单:
GATE-2D3-00: Narrative Context Contract Freeze Gate (十项刚性属性核验)
GATE-2D3-01: Context 10x JCS Idempotence & Fingerprint Invariant Gate (确定性防漂移核验)
GATE-2D3-02: Security Master Binding & Identity Non-Corruption Gate (002242 九阳股份强绑定)
GATE-2D3-03: No Secondary Mainline Reranking Gate (严格保持上游主线排名与数量)
GATE-2D3-04: No Trader-Action Field Isolation Gate (绝对零交易指令字段)
"""

import sqlite3
import pytest
import asyncio
from typing import Dict, Any

from backend.app.core.database import async_session
from backend.app.services.canonical_market_service import CanonicalMarketService
from backend.app.services.narrative_context_service import NarrativeContextExtractor
from backend.app.schemas.narrative_context import (
    NarrativeContextContract,
    SpeechBoundaryContract,
)
from backend.app.models.market import MarketDailySnapshot
from backend.app.models.report import DailyReview


@pytest.fixture(autouse=True)
async def seed_20261008_test_sandbox():
    """沙箱环境数据注入"""
    prod_conn = sqlite3.connect("data/trading.db")
    prod_snap = prod_conn.execute(
        "SELECT date, snapshot_type, indices_snapshot, breadth_snapshot, "
        "limit_up_snapshot, micro_cap_snapshot, external_risk_snapshot, "
        "high_tier_snapshot, market_state_snapshot, data_quality, source_status "
        "FROM market_daily_snapshot WHERE date = '2026-10-08' AND snapshot_type = 'EOD_CLOSE'"
    ).fetchone()

    prod_rev = prod_conn.execute(
        "SELECT date, market_overview, limit_up_analysis, sector_analysis, "
        "market_state_id, report_content, data_quality "
        "FROM daily_review WHERE date = '2026-10-08'"
    ).fetchone()
    prod_conn.close()

    async with async_session() as session:
        await session.execute(MarketDailySnapshot.__table__.delete())
        await session.execute(DailyReview.__table__.delete())
        await session.commit()

        if prod_snap:
            session.add(MarketDailySnapshot(
                date=prod_snap[0],
                snapshot_type=prod_snap[1],
                indices_snapshot=prod_snap[2],
                breadth_snapshot=prod_snap[3],
                limit_up_snapshot=prod_snap[4],
                micro_cap_snapshot=prod_snap[5],
                external_risk_snapshot=prod_snap[6],
                high_tier_snapshot=prod_snap[7],
                market_state_snapshot=prod_snap[8],
                data_quality=prod_snap[9],
                source_status=prod_snap[10],
            ))
        if prod_rev:
            session.add(DailyReview(
                date=prod_rev[0],
                market_overview=prod_rev[1],
                limit_up_analysis=prod_rev[2],
                sector_analysis=prod_rev[3],
                market_state_id=prod_rev[4],
                report_content=prod_rev[5],
                data_quality=prod_rev[6],
            ))
        await session.commit()


@pytest.mark.asyncio
async def test_gate_2d3_00_narrative_context_contract_freeze():
    """
    GATE-2D3-00: Narrative Context Contract Freeze Gate
    董事会裁决十项刚性核验要求：
    1. Source Snapshot identity
    2. schema_version & producer_version
    3. Security Identity (Security Master binding)
    4. FACT / DERIVED / COGNITION strict separation
    5. Evidence lineage
    6. Falsification lineage
    7. Deterministic serialization
    8. No raw-data leakage
    9. No trader-action field
    10. Speech boundary complete definition
    """
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        extractor = NarrativeContextExtractor()
        contract = extractor.extract_context(snap)
        assert isinstance(contract, NarrativeContextContract)

        # 1. Source Snapshot identity
        assert contract.source_snapshot_fingerprint == snap.envelope_fingerprint
        assert len(contract.source_snapshot_fingerprint) == 64

        # 2. schema_version & producer_version
        assert contract.schema_version == "2D.3-NARRATIVE-CONTEXT-V1"
        assert contract.producer_version == "CANONICAL_NARRATIVE_CONTEXT_EXTRACTOR-V1"
        assert contract.trade_date == "2026-10-08"

        # 3. Security Identity binding
        leader = contract.fact_layer.ladder.space_leader
        assert leader.stock_code == "600825"
        assert leader.canonical_name == "新华传媒"
        assert leader.security_id == "600825.SH"
        assert leader.exchange == "SH"

        # 4. FACT / DERIVED / COGNITION strict separation
        assert contract.fact_layer.layer_type == "FACT"
        assert contract.derived_layer.layer_type == "DERIVED"
        assert contract.cognition_layer.layer_type == "COGNITION"

        # FACT 校验
        assert contract.fact_layer.turnover.total_turnover_yi == 16821.09
        assert contract.fact_layer.turnover.sh_amount_yi == 8111.83
        assert contract.fact_layer.turnover.sz_total_amount_yi == 8709.26
        assert contract.fact_layer.turnover.chinext_slice_yi == 4227.55
        assert "严禁将创业板再次累加" in contract.fact_layer.turnover.accounting_rule

        # DERIVED 校验
        assert abs(contract.derived_layer.broken_limit_ratio - 0.4267) < 0.001
        assert contract.derived_layer.state_features.ladder_vector.max_ladder_height == 8

        # COGNITION 校验
        assert contract.cognition_layer.market_state.primary_state.value == "HIGH_DIVERGENCE_TOPPING"
        assert "PROVISIONAL" in contract.cognition_layer.provisional_disclaimer

        # 5. Evidence lineage
        anchors = contract.speech_boundary.required_evidence_anchors
        assert any("16821.09" in a for a in anchors)
        assert any("42.67%" in a for a in anchors)
        assert any("8B" in a for a in anchors)
        assert any("600825:新华传媒" in a for a in anchors)

        # 6. Falsification lineage
        fals = contract.speech_boundary.falsification_rules_to_monitor
        assert len(fals) >= 3
        assert any("大幅低开" in f or "破位" in f for f in fals)

        # 7. Deterministic serialization (SHA-256 fingerprint)
        assert len(contract.context_fingerprint) == 64

        # 8. No raw-data leakage
        # Extractor 只接受 CanonicalMarketSnapshot，无 session 或 db 连接
        assert not hasattr(extractor, "session")
        assert not hasattr(extractor, "db")

        # 9. No trader-action field
        # 遍历所有字段名，绝对无 buy/sell/order/action 字段
        model_dict = contract.model_dump()
        forbidden_keys = {"buy", "sell", "order", "action", "position", "target_price"}
        
        def check_no_forbidden_keys(d: Any, path=""):
            if isinstance(d, dict):
                for k, v in d.items():
                    assert k.lower() not in forbidden_keys, f"违规交易指令字段发现: {path}.{k}"
                    check_no_forbidden_keys(v, f"{path}.{k}")
            elif isinstance(d, list):
                for idx, item in enumerate(d):
                    check_no_forbidden_keys(item, f"{path}[{idx}]")
        
        check_no_forbidden_keys(model_dict)

        # 10. Speech boundary complete definition
        sb = contract.speech_boundary
        assert "MACRO_TURNOVER_DIVERGENCE" in sb.allowed_claim_types
        assert "DIRECT_TRADING_DIRECTIVE" in sb.forbidden_claim_types
        assert "COGNITION_TO_FACT_PROMOTION" in sb.forbidden_claim_types


@pytest.mark.asyncio
async def test_gate_2d3_01_context_10x_jcs_idempotence():
    """
    GATE-2D3-01: 确定性与 10x JCS 幂等性断言 (红线 2)
    同一快照连续提取 10 次，指纹比特级绝对恒定
    """
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        extractor = NarrativeContextExtractor()
        first_contract = extractor.extract_context(snap)
        expected_fp = first_contract.context_fingerprint

        for i in range(9):
            subsequent = extractor.extract_context(snap)
            assert subsequent.context_fingerprint == expected_fp, f"第 {i+2} 次 Narrative Context 哈希漂移"


@pytest.mark.asyncio
async def test_gate_2d3_02_security_master_binding_and_002242_defense():
    """
    GATE-2D3-02: Security Master 强绑定与 002242 防腐断言 (红线 4)
    断言上下文内所有涉及 002242 的身份严格为九阳股份，严禁毅昌科技
    """
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        extractor = NarrativeContextExtractor()
        contract = extractor.extract_context(snap)

        # 检查所有出现股票代码的实体
        all_identities = []
        for tier in contract.fact_layer.ladder.tiers:
            all_identities.extend(tier.stocks)
        all_identities.append(contract.fact_layer.ladder.space_leader)
        all_identities.extend(contract.fact_layer.regulatory.anomaly_stocks)
        for m in contract.cognition_layer.candidate_mainlines:
            all_identities.append(m.leader_identity)

        for ident in all_identities:
            assert ident.security_id.endswith(f".{ident.exchange}")
            if ident.stock_code == "002242":
                assert ident.canonical_name == "九阳股份"
                assert "毅昌" not in ident.canonical_name
            if ident.stock_code == "002420":
                assert ident.canonical_name == "毅昌科技"


@pytest.mark.asyncio
async def test_gate_2d3_03_no_secondary_mainline_reranking():
    """
    GATE-2D3-03: 主线排名只读透传与二次推断拦截断言 (红线 7)
    断言 Context 内主线候选与上游 CognitionSnapshot 排名、名称、角色 1:1 比特级一致
    """
    async with async_session() as session:
        service = CanonicalMarketService(session)
        snap = await service.get_canonical_snapshot("2026-10-08")
        assert snap is not None

        extractor = NarrativeContextExtractor()
        contract = extractor.extract_context(snap)

        upstream_mainlines = snap.cognition.mainlines
        context_mainlines = contract.cognition_layer.candidate_mainlines

        assert len(context_mainlines) == len(upstream_mainlines)
        for i in range(len(upstream_mainlines)):
            u = upstream_mainlines[i]
            c = context_mainlines[i]
            assert c.rank == u.rank
            assert c.sector_name == u.sector_name
            assert c.sector_code == u.sector_code
            assert c.structural_role == u.structural_role
            assert c.thematic_tier == u.thematic_tier
            assert c.leader_identity.stock_code == u.constituency.leader_code


def test_gate_2d3_04_forbidden_claim_types_and_no_l5_action():
    """
    GATE-2D3-04: 发言边界刚性约束与 L5 隔离断言 (红线 5 & 6)
    """
    contract_class_fields = NarrativeContextContract.model_fields
    assert "action" not in contract_class_fields
    assert "directive" not in contract_class_fields
    assert "recommendation" not in contract_class_fields

    # 发言边界枚举断言
    sb = SpeechBoundaryContract(
        required_evidence_anchors=["EVID:1", "EVID:2", "EVID:3"],
        falsification_rules_to_monitor=["RULE:1"],
    )
    assert "DIRECT_TRADING_DIRECTIVE" in sb.forbidden_claim_types
    assert "COGNITION_TO_FACT_PROMOTION" in sb.forbidden_claim_types
    assert "MACRO_TURNOVER_DIVERGENCE" in sb.allowed_claim_types
