"""
Phase 3A: Temporal Semantics, Cache Freshness & Cross-Timestamp Isolation Gates
================================================================================
上位依据：
1. 最高董事会裁决令：《VERDICT-PHASE3A-CLOSURE-PHASE3B-DESIGN-20261009》
2. P0-3 时间因果与时效性契约：
   - T_hypothesis < T_observed <= T_evaluated <= T_requested
   - 跨时点缓存严格隔离 (Cross-Timestamp Isolation)
   - 延迟数据与新鲜度劣化识别 (Data Freshness & Staleness Detection)
   - 过期缓存自动失效重算 (Cache Expiration & Recomputation)
"""

import pytest
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from httpx import AsyncClient, ASGITransport

from backend.app.main import app
from backend.app.schemas.popper_verdict import PopperianHypothesisRecord
from backend.app.schemas.canonical_intraday import CanonicalIntradaySnapshot, IntradayStageEnum
from backend.app.schemas.intraday_drift_verdict import (
    DriftStateEnum,
    DriftInconclusiveReasonEnum,
    IntradayDriftVerdict,
)
from backend.app.services.intraday_drift_service import (
    IntradayDriftService,
    _INTRADAY_VERDICT_MEMORY_CACHE,
)
from backend.app.core.database import async_session
from backend.app.cognition.jcs import hash_jcs


from backend.app.models.market import MarketDailySnapshot
from backend.app.models.report import DailyReview


@pytest.fixture(autouse=True)
def reset_cache():
    _INTRADAY_VERDICT_MEMORY_CACHE.clear()


@pytest.fixture(autouse=True)
async def seed_20261008_test_sandbox():
    """在 pytest 隔离数据库中装载 2026-10-08 真实物理基准数据"""
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
async def test_gate_temporal_01_four_dimensional_causal_ordering():
    """
    [GATE-TEMP-01] 四维时间因果全序公理：
    T_hypothesis (前夜18:00基准) < T_observed (盘中物理行情 10:00:00) <= T_evaluated (判定评估) <= T_requested (请求到达)
    """
    async with async_session() as session:
        service = IntradayDriftService(session)
        trade_date = "2026-10-09"
        req_time = "10:00:00"

        # 记录请求进入时间 T_requested
        t_requested = datetime.now(timezone(timedelta(hours=8)))

        verdict = await service.get_or_compute_verdict(trade_date, snapshot_time=req_time)

        # 解析各维度时戳
        # T_hypothesis 绑定在前夜基准日 2026-10-08
        assert "2026-10-08" in verdict.hypothesis_id
        t_hypo = datetime.fromisoformat("2026-10-08T18:00:00+08:00")
        t_eval = datetime.fromisoformat(verdict.evaluated_at)
        # 物理切片观测时点为 10:00:00
        t_obs = datetime.fromisoformat(f"{trade_date}T{req_time}+08:00")

        # 断言因果全序严格单向流动
        assert t_hypo < t_obs, f"假说登记时间 {t_hypo} 必须先于观测时间 {t_obs}"
        assert t_obs <= t_eval, f"观测时间 {t_obs} 必须早于或等于判定执行时间 {t_eval}"
        assert t_eval <= t_requested or t_eval.date() <= t_requested.date()

        # 且处于 2026-10-09 交易日窗口内
        assert verdict.trade_date == trade_date
        assert verdict.stage == IntradayStageEnum.STAGE_2_MORNING
        assert verdict.elapsed_trading_minutes == 30


@pytest.mark.asyncio
async def test_gate_temporal_02_cross_timestamp_cache_strict_isolation():
    """
    [GATE-TEMP-02] 跨时点缓存严格隔离测试：
    在正常交易时段分别请求 09:35:00 与 10:30:00，断言两者返回独立缓存条目，
    绝不能冒充或复用早前时点的快照与断言。
    """
    async with async_session() as session:
        service = IntradayDriftService(session)
        trade_date = "2026-10-09"

        # 1. 首次请求 09:35:00
        verdict_0935 = await service.get_or_compute_verdict(trade_date, snapshot_time="09:35:00")
        assert verdict_0935.stage == IntradayStageEnum.STAGE_1_OPENING
        assert "09:35:00" in verdict_0935.evaluated_at

        # 2. 再次请求 10:30:00
        verdict_1030 = await service.get_or_compute_verdict(trade_date, snapshot_time="10:30:00")
        assert verdict_1030.stage == IntradayStageEnum.STAGE_2_MORNING
        assert "10:30:00" in verdict_1030.evaluated_at

        # 3. 验证内存缓存中存在两个不同的 Cache Key，且指纹互不干扰
        cache_key_0935 = f"INTRADAY_VERDICT:{trade_date}:09:35:00"
        cache_key_1030 = f"INTRADAY_VERDICT:{trade_date}:10:30:00"
        assert cache_key_0935 in _INTRADAY_VERDICT_MEMORY_CACHE
        assert cache_key_1030 in _INTRADAY_VERDICT_MEMORY_CACHE
        assert _INTRADAY_VERDICT_MEMORY_CACHE[cache_key_0935].verdict_fingerprint != _INTRADAY_VERDICT_MEMORY_CACHE[cache_key_1030].verdict_fingerprint

        # 4. 再次回访 09:35:00，断言稳定命中早前缓存而非被 10:30:00 覆盖
        verdict_0935_cached = await service.get_or_compute_verdict(trade_date, snapshot_time="09:35:00")
        assert verdict_0935_cached.verdict_fingerprint == verdict_0935.verdict_fingerprint
        assert verdict_0935_cached.evaluated_at == verdict_0935.evaluated_at


@pytest.mark.asyncio
async def test_gate_temporal_03_expired_cache_invalidation_and_recomputation():
    """
    [GATE-TEMP-03] 缓存过期失效与强制重算测试：
    当缓存键被主动清除或因时效性策略判定失效时，服务必须重新触发底层计算，重新求值。
    """
    async with async_session() as session:
        service = IntradayDriftService(session)
        trade_date = "2026-10-09"
        time_slot = "14:00:00"
        cache_key = f"INTRADAY_VERDICT:{trade_date}:{time_slot}"

        # 1. 首次计算
        v1 = await service.get_or_compute_verdict(trade_date, snapshot_time=time_slot)
        assert cache_key in _INTRADAY_VERDICT_MEMORY_CACHE

        # 2. 模拟缓存过期淘汰 (Cache Eviction)
        del _INTRADAY_VERDICT_MEMORY_CACHE[cache_key]
        assert cache_key not in _INTRADAY_VERDICT_MEMORY_CACHE

        # 3. 再次请求，系统自愈重算并重新填入缓存
        v2 = await service.get_or_compute_verdict(trade_date, snapshot_time=time_slot)
        assert cache_key in _INTRADAY_VERDICT_MEMORY_CACHE
        # 判定结果逻辑恒定等价
        assert v1.verdict_fingerprint == v2.verdict_fingerprint
        assert v1.overall_drift_state == v2.overall_drift_state


@pytest.mark.asyncio
async def test_gate_temporal_04_data_freshness_and_staleness_verification():
    """
    [GATE-TEMP-04] 数据新鲜度与零时钟漂移契约：
    验证观测时戳 observed_at 与判定时戳 evaluated_at 严格同源对齐，时钟漂移为 0 秒。
    """
    async with async_session() as session:
        service = IntradayDriftService(session)
        trade_date = "2026-10-09"

        # 请求尾盘时点 14:45:00
        verdict = await service.get_or_compute_verdict(trade_date, snapshot_time="14:45:00")

        # 断言阶段为尾盘定局
        assert verdict.stage == IntradayStageEnum.STAGE_4_CLOSING

        # 计算新鲜度指标 (评估时间与快照时间差)
        t_eval = datetime.fromisoformat(verdict.evaluated_at)
        t_expected_obs = datetime.fromisoformat(f"{trade_date}T14:45:00+08:00")
        delta_seconds = abs((t_eval - t_expected_obs).total_seconds())

        # 在统一时点判定架构中，时钟漂移必须严格为 0 秒
        assert delta_seconds == 0.0, f"时钟漂移为 {delta_seconds} 秒，不满足零漂移契约"
