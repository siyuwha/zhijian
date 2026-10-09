"""
Phase 3A.1: Canonical Intraday Gates (盘中微观事实快照与量能投影门禁)
===================================================================
测试门禁规范：
1. GATE-3A1-01: Schema 契约与 JCS RFC 8785 幂等及汉明距离雪崩门禁
2. GATE-3A1-02: 盘中 4 阶段时间窗口与午间休市状态机门禁
3. GATE-3A1-03: 交易分钟衰减量能投影模型精度与边界门禁
4. GATE-3A1-04: Security Master 标的绑定与空间标杆炸板(Broken Limit)检测门禁
5. GATE-3A1-05: 非交易日/周末休市硬性防御门禁 (零时钟漂移)
6. GATE-3A1-06: Decimal 会计准则与防重复累加门禁 (SH + SZ)
7. GATE-3A1-07: 单向时间血缘绑定门禁 (锚定 T 日收盘与今晨 09:25 竞价快照)
"""

import pytest
import sqlite3
from decimal import Decimal
from unittest.mock import patch

from backend.app.schemas.canonical_intraday import (
    IntradayStageEnum,
    StockIntradayQuote,
    CanonicalIntradayIndexQuote,
    CanonicalIntradaySnapshot,
)
from backend.app.services.canonical_intraday_service import (
    CanonicalIntradayService,
    calculate_intraday_stage,
    calculate_projected_turnover,
)
from backend.app.services.canonical_market_service import CanonicalSecurityMasterRegistry
from backend.app.schemas.canonical_market import DataQualityGrade
from backend.app.core.database import async_session
from backend.app.models.market import MarketDailySnapshot
from backend.app.models.report import DailyReview
from backend.app.cognition.jcs import hash_jcs


def hamming_distance(hex1: str, hex2: str) -> int:
    """计算两个十六进制字符串之间的二进制汉明距离 (比特差异数)"""
    val1 = int(hex1, 16)
    val2 = int(hex2, 16)
    xor_val = val1 ^ val2
    return bin(xor_val).count("1")


@pytest.fixture(autouse=True)
async def seed_20261008_test_sandbox():
    """在 pytest 隔离数据库中装载 2026-10-08 真实收盘物理快照"""
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
        if prod_snap:
            existing = await session.get(MarketDailySnapshot, 1)
            if not existing:
                row = MarketDailySnapshot(
                    id=1,
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
                session.add(row)

        if prod_rev:
            existing_rev = await session.get(DailyReview, 1)
            if not existing_rev:
                r_row = DailyReview(
                    id=1,
                    date=prod_rev[0],
                    market_overview=prod_rev[1],
                    limit_up_analysis=prod_rev[2],
                    sector_analysis=prod_rev[3],
                    market_state_id=prod_rev[4],
                    report_content=prod_rev[5],
                    data_quality=prod_rev[6],
                )
                session.add(r_row)

        await session.commit()


@pytest.mark.asyncio
async def test_gate_3a1_01_schema_contract_and_jcs_avalanche():
    """GATE-3A1-01: Schema 契约与 JCS RFC 8785 幂等及汉明距离雪崩门禁"""
    async with async_session() as session:
        service = CanonicalIntradayService(session)

        # 1. 10x 幂等性测试
        snap1 = await service.produce_canonical_intraday_snapshot(
            trade_date="2026-10-09", snapshot_time="10:15:00"
        )
        for _ in range(9):
            snap_rep = await service.produce_canonical_intraday_snapshot(
                trade_date="2026-10-09", snapshot_time="10:15:00"
            )
            assert snap_rep.snapshot_fingerprint == snap1.snapshot_fingerprint, "10x JCS 哈希必须字节级绝对恒等"

        # 2. 字段只读与不可变性 (Pydantic frozen=True)
        with pytest.raises(Exception):
            snap1.projected_turnover_yi = Decimal("9999.00")  # type: ignore

        # 3. 密码学汉明距离雪崩效应测试 (修改 0.01 亿成交额，断言翻转率接近 50%)
        tampered_replay = {
            "sh_amount_wan": 1000000,
            "sz_amount_wan": 1500001,  # 微篡改 1 万元 (0.0001 亿)
            "indices": [],
            "stocks": [],
        }
        snap_tampered = await service.produce_canonical_intraday_snapshot(
            trade_date="2026-10-09",
            snapshot_time="10:15:00",
            force_replay_data=tampered_replay,
        )
        h_dist = hamming_distance(snap1.snapshot_fingerprint, snap_tampered.snapshot_fingerprint)
        bit_flip_ratio = h_dist / 256.0
        assert bit_flip_ratio >= 0.40, f"微篡改未引发充分雪崩: {bit_flip_ratio:.2%}"


def test_gate_3a1_02_four_stage_intraday_horizons_and_lunch_break():
    """GATE-3A1-02: 盘中 4 阶段时间窗口与午间休市状态机门禁"""
    # 盘前
    st, m = calculate_intraday_stage("09:15:00")
    assert st == IntradayStageEnum.OFF_MARKET and m == 0

    # STAGE 1: 09:30 - 10:00 (龙头确认期)
    st, m = calculate_intraday_stage("09:45:00")
    assert st == IntradayStageEnum.STAGE_1_OPENING and m == 15

    # STAGE 2: 10:00 - 11:30 (主线定型期)
    st, m = calculate_intraday_stage("10:30:00")
    assert st == IntradayStageEnum.STAGE_2_MORNING and m == 60

    # LUNCH BREAK: 11:30 - 13:00 (午间休市，分钟数锁定在 120)
    st, m = calculate_intraday_stage("12:15:00")
    assert st == IntradayStageEnum.LUNCH_BREAK and m == 120

    # STAGE 3: 13:00 - 14:30 (午后异动期)
    st, m = calculate_intraday_stage("13:45:00")
    assert st == IntradayStageEnum.STAGE_3_AFTERNOON and m == 165

    # STAGE 4: 14:30 - 15:00 (尾盘博弈期)
    st, m = calculate_intraday_stage("14:45:00")
    assert st == IntradayStageEnum.STAGE_4_CLOSING and m == 225

    # 收盘后
    st, m = calculate_intraday_stage("15:05:00")
    assert st == IntradayStageEnum.OFF_MARKET and m == 240


def test_gate_3a1_03_minute_decay_volume_projection_accuracy():
    """GATE-3A1-03: 交易分钟衰减量能投影模型精度与边界门禁"""
    prev_total = Decimal("10000.00")

    # 1. 0 分钟边界
    proj, pace = calculate_projected_turnover(Decimal("0.00"), 0, prev_total)
    assert proj == Decimal("0.00") and pace == Decimal("0.00")

    # 2. 10:00 (30 分钟，累计 28%): 累计 2800.00 亿，预估全天应精准为 10000.00 亿 (100.00%)
    proj_30, pace_30 = calculate_projected_turnover(Decimal("2800.00"), 30, prev_total)
    assert proj_30 == Decimal("10000.00")
    assert pace_30 == Decimal("100.00")

    # 3. 11:30 (120 分钟，累计 63%): 累计 6300.00 亿，预估全天应精准为 10000.00 亿
    proj_120, pace_120 = calculate_projected_turnover(Decimal("6300.00"), 120, prev_total)
    assert proj_120 == Decimal("10000.00")
    assert pace_120 == Decimal("100.00")

    # 4. 14:30 (210 分钟，累计 86%): 累计 8600.00 亿，预估全天应精准为 10000.00 亿
    proj_210, pace_210 = calculate_projected_turnover(Decimal("8600.00"), 210, prev_total)
    assert proj_210 == Decimal("10000.00")
    assert pace_210 == Decimal("100.00")

    # 5. 15:00 (240 分钟收盘): 累计 10000.00 亿，预估全天应直接等于实际值
    proj_240, pace_240 = calculate_projected_turnover(Decimal("10000.00"), 240, prev_total)
    assert proj_240 == Decimal("10000.00")
    assert pace_240 == Decimal("100.00")

    # 6. 放量场景：10:00 已经成交 4200 亿，预估量能应为 15000.00 亿 (150.00%)
    proj_surge, pace_surge = calculate_projected_turnover(Decimal("4200.00"), 30, prev_total)
    assert proj_surge == Decimal("15000.00")
    assert pace_surge == Decimal("150.00")


@pytest.mark.asyncio
async def test_gate_3a1_04_security_master_binding_and_broken_limit_detection():
    """GATE-3A1-04: Security Master 标的绑定与空间标杆炸板(Broken Limit)检测门禁"""
    async with async_session() as session:
        service = CanonicalIntradayService(session)

        # 模拟盘中标的切片：
        # 标的 1 (600825 新华传媒，最高空间标杆)：昨收 10.00，最高 11.00 (曾涨停)，现价 10.20 (炸板回落)
        # 标的 2 (600241 时代万恒，主线龙头)：昨收 10.00，最高 11.00，现价 11.00 (封死涨停)
        replay_data = {
            "sh_amount_wan": 1000000,
            "sz_amount_wan": 1500000,
            "indices": [],
            "stocks": [
                {
                    "code": "sh600825",
                    "pre_close": "10.00",
                    "open": "10.50",
                    "price": "10.20",
                    "high": "11.00",
                    "low": "10.10",
                    "amount_wan": "50000.00",
                    "volume_wan": "4800.00",
                },
                {
                    "code": "sh600241",
                    "pre_close": "10.00",
                    "open": "10.80",
                    "price": "11.00",
                    "high": "11.00",
                    "low": "10.70",
                    "amount_wan": "80000.00",
                    "volume_wan": "7200.00",
                },
            ],
            "up_count": 2800,
            "down_count": 1900,
            "limit_up_count": 45,
            "broken_limit_count": 15,
        }

        snap = await service.produce_canonical_intraday_snapshot(
            trade_date="2026-10-09",
            snapshot_time="10:15:00",
            force_replay_data=replay_data,
        )

        assert len(snap.leader_quotes) == 2
        # 标的按代码确定性排序: 600241, 600825
        q_600241 = next(q for q in snap.leader_quotes if q.code == "600241")
        q_600825 = next(q for q in snap.leader_quotes if q.code == "600825")

        # 600825 (空间板) 必须精准识别为 炸板 (is_broken_limit == True, is_limit_up == False)
        assert q_600825.is_broken_limit is True, "空间板最高价达涨停且现价回落必须识别为炸板"
        assert q_600825.is_limit_up is False
        assert q_600825.is_space_leader is True

        # 600241 必须精准识别为 封死涨停
        assert q_600241.is_limit_up is True
        assert q_600241.is_broken_limit is False

        # 炸板率校验: 15 / (45 + 15) = 25.00%
        assert snap.broken_limit_ratio_pct == Decimal("25.00")


@pytest.mark.asyncio
async def test_gate_3a1_05_non_trading_day_weekend_defense():
    """GATE-3A1-05: 非交易日/周末休市硬性防御门禁 (零时钟漂移)"""
    async with async_session() as session:
        service = CanonicalIntradayService(session)

        # 2026-10-10 是周六
        snap = await service.produce_canonical_intraday_snapshot(
            trade_date="2026-10-10", snapshot_time="10:15:00"
        )
        assert snap.is_trading_day is False
        assert snap.stage == IntradayStageEnum.OFF_MARKET
        assert snap.data_quality == DataQualityGrade.UNAVAILABLE
        assert snap.elapsed_trading_minutes == 0
        assert snap.projected_turnover_yi == Decimal("0.00")
        assert len(snap.leader_quotes) == 0


@pytest.mark.asyncio
async def test_gate_3a1_06_decimal_accounting_and_anti_double_count():
    """GATE-3A1-06: Decimal 会计准则与防重复累加门禁 (SH + SZ)"""
    async with async_session() as session:
        service = CanonicalIntradayService(session)

        replay_data = {
            "sh_amount_wan": 4500000,  # 450.00 亿
            "sz_amount_wan": 5500000,  # 550.00 亿 (含创业板)
            "indices": [],
            "stocks": [],
        }
        snap = await service.produce_canonical_intraday_snapshot(
            trade_date="2026-10-09",
            snapshot_time="10:00:00",
            force_replay_data=replay_data,
        )

        assert snap.sh_accumulated_turnover_yi == Decimal("450.00")
        assert snap.sz_accumulated_turnover_yi == Decimal("550.00")
        assert snap.total_accumulated_turnover_yi == Decimal("1000.00")
        assert isinstance(snap.total_accumulated_turnover_yi, Decimal)
        assert isinstance(snap.projected_turnover_yi, Decimal)


@pytest.mark.asyncio
async def test_gate_3a1_07_unidirectional_lineage_to_t_and_auction():
    """GATE-3A1-07: 单向时间血缘绑定门禁 (锚定 T 日收盘与今晨 09:25 竞价快照)"""
    async with async_session() as session:
        service = CanonicalIntradayService(session)

        snap = await service.produce_canonical_intraday_snapshot(
            trade_date="2026-10-09", snapshot_time="10:15:00"
        )

        # 必须绑定 2026-10-08 作为前日
        assert snap.prev_trade_date == "2026-10-08"
        assert snap.bound_snapshot_trace_id == "TRACE-2026-10-08-TO-2026-10-09-INTRADAY"
        assert len(snap.bound_snapshot_fingerprint) == 64
        # 必须绑定 09:25 竞价快照指纹
        assert snap.bound_auction_trace_id is not None
        assert snap.bound_auction_fingerprint is not None
        assert len(snap.bound_auction_fingerprint) == 64
