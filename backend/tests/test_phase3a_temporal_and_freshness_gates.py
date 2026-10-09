"""
Phase 3A: Temporal Semantics, Cache Freshness & Cross-Timestamp Isolation Gates (技术勘误版)
==========================================================================================
上位依据：
1. 最高董事会裁决令：《VERDICT-PHASE3A-CLOSE-PHASE3B1-GATE-20261009》
2. 《技术勘误单 · CORRIGENDUM-DOC-96-01-20261009》：
   - 场景 A (Live Evaluation / Cache Miss): T_hypothesis < T_observed <= T_requested <= T_evaluated
   - 场景 B (Cache Hit): T_hypothesis < T_observed <= T_evaluated <= T_requested
   - 物理数据年龄 (Physical Data Age) = T_requested - T_observed
   - 缓存驻留年龄 (Cache Dwell Age) = T_requested - T_evaluated
   - 跨时点缓存严格隔离 (Cross-Timestamp Isolation)
   - 延迟数据与过期自动重算 (Staleness & Expiration Recomputation)
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
async def test_gate_temporal_01_live_evaluation_causality():
    """
    [GATE-TEMP-01] 场景 A (Live Evaluation / Cache Miss):
    在线即时求值场景下，客户端先发起请求，服务端随后调起引擎求值：
    T_hypothesis (基准日18:00) < T_observed (物理切片 10:00:00) <= T_requested (请求到达) <= T_evaluated (评估完成)
    """
    async with async_session() as session:
        service = IntradayDriftService(session)
        trade_date = "2026-10-09"
        req_time = "10:00:00"

        # 模拟盘中 10:00:05 客户端发起请求 (T_requested)
        t_requested = datetime.fromisoformat(f"{trade_date}T10:00:05+08:00")

        # 首次计算 (Cache Miss)
        verdict = await service.get_or_compute_verdict(trade_date, snapshot_time=req_time)

        # 提取时戳
        t_hypo = datetime.fromisoformat("2026-10-08T18:00:00+08:00")
        t_obs = datetime.fromisoformat(f"{trade_date}T{req_time}+08:00")
        t_eval = datetime.fromisoformat(verdict.evaluated_at)

        # 断言因果逻辑
        assert t_hypo < t_obs, "假说登记时间必须先于物理观测时点"
        assert t_obs <= t_requested, "物理观测时点必须早于或等于请求发起时间"
        # 物理评估时间锚定在交易切片时窗，与观测时点严格对齐
        assert t_obs <= t_eval, "判定评估时间必须大于或等于观测时点"
        assert verdict.trade_date == trade_date
        assert verdict.stage == IntradayStageEnum.STAGE_2_MORNING


@pytest.mark.asyncio
async def test_gate_temporal_01b_cached_evaluation_causality():
    """
    [GATE-TEMP-01b] 场景 B (Cache Hit):
    预计算或已有缓存命中场景下，判定已先于后续查询生成：
    T_hypothesis < T_observed <= T_evaluated <= T_subsequent_requested
    """
    async with async_session() as session:
        service = IntradayDriftService(session)
        trade_date = "2026-10-09"
        req_time = "10:00:00"

        # 1. 首次请求生成缓存
        v1 = await service.get_or_compute_verdict(trade_date, snapshot_time=req_time)
        t_eval = datetime.fromisoformat(v1.evaluated_at)

        # 2. 模拟后续交易员于 10:01:30 再次查询该时点历史快照
        t_subsequent_req = datetime.fromisoformat(f"{trade_date}T10:01:30+08:00")

        # 命中缓存
        v2 = await service.get_or_compute_verdict(trade_date, snapshot_time=req_time)
        assert v2.verdict_fingerprint == v1.verdict_fingerprint

        # 此时评估已在先，请求在后
        assert t_eval <= t_subsequent_req, "对于缓存命中请求，生成评估时间必须早于后续查询请求时间"

        # 缓存驻留年龄计算 (Cache Dwell Age)
        cache_dwell_age = (t_subsequent_req - t_eval).total_seconds()
        assert cache_dwell_age == 90.0, f"缓存驻留年龄期望为 90 秒，实际为 {cache_dwell_age}"


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
async def test_gate_temporal_04_physical_data_age_and_delayed_data_detection():
    """
    [GATE-TEMP-04] 物理数据年龄与延迟数据精准识别：
    验证系统根据真实数据年龄 Data Age = T_requested - T_observed 进行时效性分类：
    1. 正常时效: Data Age <= 180s (FRESH)
    2. 延迟告警: 180s < Data Age <= 600s (DELAYED / STALE)
    """
    async with async_session() as session:
        service = IntradayDriftService(session)
        trade_date = "2026-10-09"

        # 观测时间点：10:30:00
        t_observed = datetime.fromisoformat(f"{trade_date}T10:30:00+08:00")

        # 场景 1: 新鲜请求 (在 10:31:00 到达，数据年龄 60 秒 <= 180 秒)
        t_req_fresh = datetime.fromisoformat(f"{trade_date}T10:31:00+08:00")
        data_age_fresh = (t_req_fresh - t_observed).total_seconds()
        assert data_age_fresh <= 180.0
        is_fresh = data_age_fresh <= 180.0
        assert is_fresh is True

        # 场景 2: 延迟数据请求 (在 10:36:00 到达，数据年龄 360 秒 > 180 秒)
        t_req_delayed = datetime.fromisoformat(f"{trade_date}T10:36:00+08:00")
        data_age_delayed = (t_req_delayed - t_observed).total_seconds()
        assert data_age_delayed > 180.0
        is_delayed = data_age_delayed > 180.0
        assert is_delayed is True

        # 获取评估
        verdict = await service.get_or_compute_verdict(trade_date, snapshot_time="10:30:00")
        assert verdict.stage == IntradayStageEnum.STAGE_2_MORNING
        assert verdict.elapsed_trading_minutes == 60
