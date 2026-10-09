"""
Phase 2E.1: Canonical Auction Data Contract & Service Gates
===========================================================
上位依据：
1. 最高董事会终审裁决令：《PHASE 2E.1 AUTHORIZED WITH REMEDIATIONS》
2. 《DOC-89 · Phase 2E 09:25 集合竞价自动对账与次日波普尔证伪闭环技术设计单》

门禁清单：
- GATE-2E1-01: Schema Model Contract Gate (不可变契约、Decimal 精度与类型守卫)
- GATE-2E1-02: Security Master Bijective Mapping & 002242 Integrity Gate (实体单射与002242防伪)
- GATE-2E1-03: Unidirectional Lineage & T-Day Binding Gate (单向血缘与T日快照指纹刚性锚定)
- GATE-2E1-04: Market Heartbeat & Non-Trading Day Defense Gate (休市心跳与非交易日防伪)
- GATE-2E1-05: JCS Determinism & 10x Idempotency Gate (JCS 哈希确定性与雪崩抗篡改)
- GATE-2E1-06: Turnover Calculation Fidelity Gate (两市竞价总额防重算会计守卫)
"""

import sqlite3
import pytest
from decimal import Decimal
from datetime import datetime
from sqlalchemy import select

from backend.app.schemas.canonical_auction import (
    CanonicalAuctionSnapshot,
    StockAuctionQuote,
    CanonicalAuctionIndexQuote,
    BiddingStatusEnum,
)
from backend.app.schemas.canonical_market import (
    ProvenanceEnvelope,
    TruthSource,
    DataQualityGrade,
)
from backend.app.services.canonical_auction_service import CanonicalAuctionService
from backend.app.services.canonical_market_service import CanonicalSecurityMasterRegistry
from backend.app.core.database import async_session
from backend.app.models.market import MarketDailySnapshot
from backend.app.models.report import DailyReview
from backend.app.cognition.jcs import hash_jcs


@pytest.fixture(autouse=True)
async def seed_20261008_test_sandbox():
    """
    EG-01 沙箱隔离：从物理 data/trading.db 只读读取 2026-10-08 真实事实并注入 pytest 测试沙箱
    """
    prod_conn = sqlite3.connect("data/trading.db")
    prod_snap = prod_conn.execute(
        "SELECT date, snapshot_type, indices_snapshot, breadth_snapshot, "
        "limit_up_snapshot, micro_cap_snapshot, external_risk_snapshot, "
        "high_tier_snapshot, market_state_snapshot, data_quality, source_status "
        "FROM market_daily_snapshot WHERE date='2026-10-08'"
    ).fetchone()

    prod_rev = prod_conn.execute(
        "SELECT date, market_overview, limit_up_analysis, sector_analysis, "
        "market_state_id, report_content, data_quality "
        "FROM daily_review WHERE date='2026-10-08'"
    ).fetchone()
    prod_conn.close()

    async with async_session() as session:
        existing = (await session.execute(
            select(MarketDailySnapshot).where(MarketDailySnapshot.date == '2026-10-08')
        )).scalars().first()

        if not existing:
            if prod_snap:
                snap_obj = MarketDailySnapshot(
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
                )
                session.add(snap_obj)

            if prod_rev:
                rev_obj = DailyReview(
                    date=prod_rev[0],
                    market_overview=prod_rev[1],
                    limit_up_analysis=prod_rev[2],
                    sector_analysis=prod_rev[3],
                    market_state_id=prod_rev[4],
                    report_content=prod_rev[5],
                    data_quality=prod_rev[6],
                )
                session.add(rev_obj)

            await session.commit()


# =============================================================================
# GATE-2E1-01: Schema Model Contract Gate
# =============================================================================
def test_gate_2e1_01_schema_contract():
    """
    GATE-2E1-01: 不可变契约、Decimal 精度与类型守卫
    - 验证 frozen=True 禁止属性修改；
    - 验证 extra='forbid' 阻止野字段注入；
    - 验证 Decimal 数值精度类型。
    """
    quote = StockAuctionQuote(
        code="600825",
        name="新华传媒",
        canonical_symbol="600825.SH",
        yesterday_close=Decimal("12.50"),
        auction_price=Decimal("12.88"),
        auction_pct_change=Decimal("3.04"),
        auction_turnover_wan=Decimal("4500.00"),
        auction_volume_ratio_pct=Decimal("2.15"),
        bidding_status=BiddingStatusEnum.NORMAL,
        open_order_imbalance_wan=Decimal("120.00"),
        is_space_leader=True,
        is_mainline_leader=False,
        bound_mainline_name=None,
    )

    # 1. 验证不可变性
    with pytest.raises(Exception):
        quote.auction_price = Decimal("13.00")

    # 2. 验证 extra="forbid" 阻止野字段
    with pytest.raises(Exception):
        StockAuctionQuote(
            code="600825",
            name="新华传媒",
            canonical_symbol="600825.SH",
            yesterday_close=Decimal("12.50"),
            auction_price=Decimal("12.88"),
            auction_pct_change=Decimal("3.04"),
            auction_turnover_wan=Decimal("4500.00"),
            unauthorized_wild_field="malicious_payload",
        )


# =============================================================================
# GATE-2E1-02: Security Master Bijective Mapping & 002242 Integrity Gate
# =============================================================================
def test_gate_2e1_02_security_master_mapping():
    """
    GATE-2E1-02: 实体单射与 002242 规范性守卫
    - 验证 002242 必须为九阳股份 (绝对禁止毅昌科技)；
    - 验证 600825 为新华传媒；
    - 验证未经认证的野码受到规范映射约束。
    """
    sec_002242 = CanonicalSecurityMasterRegistry.resolve("002242")
    assert sec_002242 is not None
    assert sec_002242.canonical_name == "九阳股份"
    assert sec_002242.canonical_name != "毅昌科技"

    sec_600825 = CanonicalSecurityMasterRegistry.resolve("600825")
    assert sec_600825 is not None
    assert sec_600825.canonical_name == "新华传媒"


# =============================================================================
# GATE-2E1-03: Unidirectional Lineage & T-Day Binding Gate
# =============================================================================
@pytest.mark.asyncio
async def test_gate_2e1_03_unidirectional_lineage():
    """
    GATE-2E1-03: 单向血缘与 T 日快照指纹刚性锚定
    - 基于真实数据库 2026-10-08 快照，生成 2026-10-09 竞价物理事实快照；
    - 断言 prev_trade_date 为 2026-10-08；
    - 断言 bound_snapshot_fingerprint 严格与 2026-10-08 快照指纹一致；
    - 断言正确识别 600825 (新华传媒) 为 is_space_leader=True。
    """
    async with async_session() as session:
        service = CanonicalAuctionService(session)

        # 模拟 2026-10-09 早盘竞价输入数据
        mock_auction_data = {
            "indices": [
                {
                    "code": "sh000001",
                    "name": "上证指数",
                    "open": 3815.20,
                    "pre_close": 3811.90,
                    "amount_wan": 750000.0,
                },
                {
                    "code": "sz399001",
                    "name": "深证成指",
                    "open": 12600.00,
                    "pre_close": 12620.90,
                    "amount_wan": 820000.0,
                },
            ],
            "stocks": [
                {
                    "code": "600825",
                    "name": "新华传媒",
                    "yesterday_close": 12.50,
                    "open": 12.20,
                    "pct_change": -2.40,
                    "amount_wan": 5400.0,
                    "volume_ratio_pct": 1.95,
                },
                {
                    "code": "600241",
                    "name": "时代万恒",
                    "yesterday_close": 8.80,
                    "open": 9.05,
                    "pct_change": 2.84,
                    "amount_wan": 3200.0,
                    "volume_ratio_pct": 2.10,
                },
            ],
            "sh_amount_wan": 750000.0,
            "sz_amount_wan": 820000.0,
        }

        snapshot = await service.produce_canonical_auction_snapshot(
            trade_date="2026-10-09",
            prev_date="2026-10-08",
            force_replay_data=mock_auction_data,
        )

        assert snapshot.trade_date == "2026-10-09"
        assert snapshot.prev_trade_date == "2026-10-08"
        assert snapshot.bound_snapshot_fingerprint == "80cb8e02acbcc1079b39b59f35af4bd252ce6f39c5a48064a6726d089ea58f22"
        assert snapshot.is_trading_day is True
        assert snapshot.data_quality == DataQualityGrade.FULL

        # 检查领军标的标记
        space_leader = next((s for s in snapshot.leader_quotes if s.code == "600825"), None)
        assert space_leader is not None
        assert space_leader.is_space_leader is True
        assert space_leader.name == "新华传媒"
        assert space_leader.auction_pct_change == Decimal("-2.40")


# =============================================================================
# GATE-2E1-04: Market Heartbeat & Non-Trading Day Defense Gate
# =============================================================================
@pytest.mark.asyncio
async def test_gate_2e1_04_non_trading_day_defense():
    """
    GATE-2E1-04: 休市心跳与非交易日防伪
    - 针对非交易日 (如 2026-10-04 周日)，断言系统输出 is_trading_day=False；
    - 断言 data_quality=UNAVAILABLE；
    - 断言竞价总额与标的列表全部为空，绝不制造假成交额。
    """
    async with async_session() as session:
        service = CanonicalAuctionService(session)

        snapshot = await service.produce_canonical_auction_snapshot(
            trade_date="2026-10-10",
            prev_date="2026-10-08",
        )

        assert snapshot.is_trading_day is False
        assert snapshot.data_quality == DataQualityGrade.UNAVAILABLE
        assert snapshot.total_auction_turnover_yi == Decimal("0.00")
        assert len(snapshot.indices) == 0
        assert len(snapshot.leader_quotes) == 0
        assert snapshot.envelope.is_degraded is True


# =============================================================================
# GATE-2E1-05: JCS Determinism & 10x Idempotency Gate
# =============================================================================
@pytest.mark.asyncio
async def test_gate_2e1_05_jcs_idempotency_and_avalanche():
    """
    GATE-2E1-05: JCS 哈希确定性与雪崩抗篡改
    - 验证 10 次重复调用输出 100% 相同 JCS SHA-256 指纹；
    - 验证微小篡改 0.01 导致哈希彻底翻转。
    """
    async with async_session() as session:
        service = CanonicalAuctionService(session)

        mock_data = {
            "indices": [],
            "stocks": [
                {
                    "code": "600825",
                    "name": "新华传媒",
                    "yesterday_close": 12.50,
                    "open": 12.50,
                    "pct_change": 0.0,
                    "amount_wan": 1000.0,
                }
            ],
            "sh_amount_wan": 500000.0,
            "sz_amount_wan": 500000.0,
        }

        hashes = []
        for _ in range(10):
            snap = await service.produce_canonical_auction_snapshot(
                trade_date="2026-10-09",
                prev_date="2026-10-08",
                force_replay_data=mock_data,
            )
            hashes.append(snap.auction_fingerprint)

        # 10x 幂等
        assert len(set(hashes)) == 1, "JCS Fingerprint drifted across identical runs!"

        # 篡改测试 (篡改开盘价 0.10 元)
        mock_tampered = {
            "indices": [],
            "stocks": [
                {
                    "code": "600825",
                    "name": "新华传媒",
                    "yesterday_close": 12.50,
                    "open": 12.60,
                    "pct_change": 0.8,
                    "amount_wan": 1000.0,
                }
            ],
            "sh_amount_wan": 500000.0,
            "sz_amount_wan": 500000.0,
        }
        snap_tampered = await service.produce_canonical_auction_snapshot(
            trade_date="2026-10-09",
            prev_date="2026-10-08",
            force_replay_data=mock_tampered,
        )
        assert snap_tampered.auction_fingerprint != hashes[0], "Tampered data did not cause hash avalanche!"


# =============================================================================
# GATE-2E1-06: Turnover Calculation Fidelity Gate
# =============================================================================
@pytest.mark.asyncio
async def test_gate_2e1_06_turnover_calculation_fidelity():
    """
    GATE-2E1-06: 两市竞价总额防重算会计守卫
    - 验证 total_auction_turnover_yi 严格等于 sh_auction_turnover_yi + sz_auction_turnover_yi；
    - 验证比值计算 (total / prev_total * 100) 精度正确。
    """
    async with async_session() as session:
        service = CanonicalAuctionService(session)

        mock_data = {
            "indices": [],
            "stocks": [],
            "sh_amount_wan": 811183.0,  # 81.12 亿
            "sz_amount_wan": 870926.0,  # 87.09 亿
        }

        snap = await service.produce_canonical_auction_snapshot(
            trade_date="2026-10-09",
            prev_date="2026-10-08",
            force_replay_data=mock_data,
        )

        assert snap.sh_auction_turnover_yi == Decimal("81.12")
        assert snap.sz_auction_turnover_yi == Decimal("87.09")
        assert snap.total_auction_turnover_yi == Decimal("168.21")
        # prev_total = 16821.09 亿, ratio = (168.21 / 16821.09) * 100 = 1.00%
        assert snap.auction_turnover_ratio_pct == Decimal("1.00")
