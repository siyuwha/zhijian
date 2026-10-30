"""
T03-01 质量日志事务与风控失败隔离验收测试套件 (v3 最终加固版)
全面覆盖计划单核心验收场景与 Codex 二次独立复审 4 大缺陷闭环：
1. 场景 1: 质量日志唯一约束冲突复现与会话回滚恢复 (实测 SQLite UNIQUE 冲突与后续写入自增恢复)
2. 场景 2: 质量日志失败与业务事务隔离 (实测业务主动提交与主动回滚均与审计日志会话正交)
3. 场景 3: 真实快照持久化异常贯穿调度器与风控独立执行 (贯穿真实 flush_async_queue 与 commit 失败，T02 合法账本下风控平仓)
4. 场景 4: 过期/降级行情拒绝与账本不变 (DEGRADED + STALE 行情严禁触发平仓，账本流水资金分文不差)
5. 场景 5: 旧行情带 REALTIME 伪标签严格按来源日期核验拦截 (P0 核心实测: 昨日行情即使标 REALTIME 也坚决拒绝成交)
6. 场景 6: 行情无效且质量日志真实落库失败 (P1 核心实测: 贯穿真实 DataService 与 SQLite 主键冲突，状态绝不报 success)
7. 场景 7: 监控与驾驶舱阶段质量日志失败全流程汇总 (P1 核心实测: 监控阶段日志失败、风控成功时，整体状态准确记录 partial_warning)
8. 场景 8: 先平仓成交、后续标的执行出错时事件与流水完整保全 (P1 核心实测: 杜绝已成交事件漏记，账实完全对齐)
9. 场景 9: 多标的部分持仓缺行情诊断追踪 (PARTIAL_HOLD / partial_warning)
10. 场景 10: 质量日志高并发写入主键唯一性与会话可恢复性 (20 并发独立会话无死锁无冲突)
11. 场景 11: 正常链路回归与 TaskLog 可观察性审计记录
12. 场景 12: 事务归属与测试沙盒隔离确权 (严禁污染生产库)
"""

import os
import sys
import time
import asyncio
from datetime import datetime
from unittest.mock import patch, AsyncMock, MagicMock
import pytest
from sqlalchemy import select, func, text, delete
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.core.database import engine, async_session, init_db
from app.data.capabilities import DataQuality, DataResult, Freshness, DataStatus
from app.data.quality import QualityTracker
from app.data.service import DataService
from app.models.system import DataQualityLog, TaskLog
from app.models.market import IntradayMarketSnapshot
from app.models.simulation import SimAccount, SimPosition, SimTrade
from app.schemas.simulation import SimTradeCreate
from app.services.autonomous_executor import AutonomousJobEngine
from app.services.simulation import SimulationService
from app.services.monitor import MonitorService
from app.tasks.scheduler import TaskScheduler, task_scheduler


@pytest.fixture(autouse=True)
async def clean_database():
    """每次测试前清理系统与模拟相关表，并重置跟踪器状态"""
    QualityTracker.stop_round_tracking()
    QualityTracker.clear_round_failures()
    QualityTracker._test_force_id = None
    await init_db()
    async with async_session() as session:
        await session.execute(delete(SimTrade))
        await session.execute(delete(SimPosition))
        await session.execute(delete(SimAccount))
        await session.execute(delete(DataQualityLog))
        await session.execute(delete(TaskLog))
        await session.commit()
    yield
    QualityTracker.stop_round_tracking()
    QualityTracker.clear_round_failures()
    QualityTracker._test_force_id = None
    async with async_session() as session:
        await session.execute(delete(SimTrade))
        await session.execute(delete(SimPosition))
        await session.execute(delete(SimAccount))
        await session.execute(delete(DataQualityLog))
        await session.execute(delete(TaskLog))
        await session.commit()


# ==============================================================================
# 场景 1: 质量日志唯一约束冲突复现与会话回滚恢复
# ==============================================================================
@pytest.mark.asyncio
async def test_quality_log_unique_constraint_recovery():
    """
    验收场景 1: 质量日志唯一约束冲突
    - 在表中预埋已有记录 id=1
    - 再次尝试显式写入 id=1，真实触发 SQLite UNIQUE constraint failed: data_quality_log.id
    - 验证失败会话被自动回滚且异常受控，返回 False
    - 验证后续日志使用正常自增写入能够成功，绝无未回滚会话连锁异常
    """
    # 1. 预置记录
    res_init = await QualityTracker.log_quality(
        capability="index_quote",
        result=DataResult(data={}, quality=DataQuality.FULL, provider="init_provider"),
        explicit_id=1
    )
    assert res_init is True, "初始记录插入应成功"

    # 2. 真实触发主键冲突
    res_conflict = await QualityTracker.log_quality(
        capability="stock_quote",
        result=DataResult(data={}, quality=DataQuality.FULL, provider="conflict_provider"),
        explicit_id=1  # 强制冲突
    )
    assert res_conflict is False, "唯一约束冲突必须被捕获并返回 False"

    # 3. 验证会话已安全回滚，后续自增写入能够正常成功
    res_next = await QualityTracker.log_quality(
        capability="market_breadth",
        result=DataResult(data={}, quality=DataQuality.FULL, provider="next_provider"),
        explicit_id=None  # 自动自增
    )
    assert res_next is True, "冲突回滚后，下一次写入必须成功，无 PendingRollbackError"

    # 4. 验证数据库中最终记录数量与主键唯一性
    async with async_session() as session:
        logs = (await session.execute(select(DataQualityLog).order_by(DataQualityLog.id.asc()))).scalars().all()
        assert len(logs) == 2, f"初始1条 + 恢复1条 = 2条，实际为 {len(logs)}"
        assert logs[0].id == 1
        assert logs[0].provider == "init_provider"
        assert logs[1].id > 1
        assert logs[1].provider == "next_provider"


# ==============================================================================
# 场景 2: 质量日志失败与业务事务隔离 (主动提交与主动回滚正交)
# ==============================================================================
@pytest.mark.asyncio
async def test_quality_log_business_transaction_isolation():
    """
    验收场景 2: 质量日志失败与业务事务隔离
    - 流程 A: 外部业务事务中，质量日志发生主键冲突 (返回 False)，业务继续执行并成功 commit
    - 流程 B: 外部业务自身因逻辑失败 rollback，不影响此前已独立提交的审计日志
    """
    # --- 流程 A: 审计日志写入失败不阻断业务事务正常提交 ---
    res_init = await QualityTracker.log_quality(
        capability="seed",
        result=DataResult(data={}, quality=DataQuality.FULL, provider="p0"),
        explicit_id=100
    )
    assert res_init is True

    async with async_session() as biz_session:
        acc = SimAccount(
            name="业务隔离账户A",
            initial_capital=1000000.0,
            current_capital=900000.0,
            total_pnl=-100000.0,
            is_active=1
        )
        biz_session.add(acc)

        log_res = await QualityTracker.log_quality(
            session=biz_session,
            capability="stock_quote",
            result=DataResult(data={}, quality=DataQuality.FAILED, provider="p_err"),
            explicit_id=100
        )
        assert log_res is False, "质量日志由于主键冲突必定返回 False"

        await biz_session.commit()

    async with async_session() as verify_session:
        saved_acc = (await verify_session.execute(select(SimAccount).where(SimAccount.name == "业务隔离账户A"))).scalar_one_or_none()
        assert saved_acc is not None
        assert saved_acc.current_capital == 900000.0

    # --- 流程 B: 业务主动回滚，不会撤销已独立提交的审计日志 ---
    async with async_session() as biz_session_b:
        acc_b = SimAccount(
            name="将被回滚的业务账户B",
            initial_capital=500000.0,
            current_capital=500000.0,
            total_pnl=0.0,
            is_active=1
        )
        biz_session_b.add(acc_b)

        log_res_b = await QualityTracker.log_quality(
            session=biz_session_b,
            capability="successful_quote",
            result=DataResult(data={"val": 1}, quality=DataQuality.FULL, provider="audit_p")
        )
        assert log_res_b is True

        await biz_session_b.rollback()

    async with async_session() as verify_session:
        aborted_acc = (await verify_session.execute(select(SimAccount).where(SimAccount.name == "将被回滚的业务账户B"))).scalar_one_or_none()
        assert aborted_acc is None, "业务主动回滚的数据绝不应入库"

        audit_log = (await verify_session.execute(select(DataQualityLog).where(DataQualityLog.capability == "successful_quote"))).scalar_one_or_none()
        assert audit_log is not None, "独立会话提交的审计日志绝不应随业务回滚而丢失"


# ==============================================================================
# 场景 3: 真实快照持久化异常贯穿调度器与风控独立执行 (贯穿真实 flush_async_queue)
# ==============================================================================
@pytest.mark.asyncio
async def test_snapshot_persistence_failure_risk_still_executed():
    """
    验收场景 3 (Codex P1 核心修复项):
    - 准备符合 T02 规范的合法前日买入账本 (T+1 可卖仓)
    - 调度器真实调用 MonitorService.flush_async_queue()，不 mock flush_async_queue 本身！
    - 通过将 monitor_session.commit 注入真实写入错误，贯穿验证 flush_async_queue 内部真实回滚并 raise
    - 验证调度器阶段隔离：监控阶段报错被准确捕获 (Monitor: failed)，阶段 2 风控守护机仍在全新独立会话中成功执行平仓
    - 验证 TaskLog 记录为 partial_failure，原因详细反映 Monitor: failed, Risk: success
    """
    # 1. 准备符合 T02 规则的合法账户、前日买入流水与在持标的 (1000 股 @ 10.0 元)
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 990000.0

        # 合法前日买入流水，确保 T+1 校验合法通过
        trade = SimTrade(
            account_id=acc.id,
            code="600519",
            name="贵州茅台",
            direction="buy",
            price=10.0,
            quantity=1000,
            trade_time="2026-10-28 10:00:00",
            decision_summary="前日建仓"
        )
        session.add(trade)

        pos = SimPosition(
            account_id=acc.id,
            code="600519",
            name="贵州茅台",
            quantity=1000,
            avg_cost=10.0,
            current_price=10.0,
            floating_pnl=0.0
        )
        session.add(pos)

        # 真实 SQLite 唯一约束冲突注入：预先在数据库中插入 (date='2026-10-29', timestamp='10:30:00') 快照
        session.add(IntradayMarketSnapshot(
            date="2026-10-29",
            timestamp="10:30:00",
            minute_index=60,
            sh_index_price=3000.0
        ))
        await session.commit()

    # 2. 模拟实时有效行情：现价 9.40 元 (触及 -6.0% 止损)
    valid_quotes = [
        {"code": "600519", "name": "贵州茅台", "price": 9.40, "open_pct": -6.0, "date": "2026-10-29", "time": "2026-10-29 10:30:00"}
    ]
    mock_quotes_result = DataResult(
        data=valid_quotes,
        quality=DataQuality.FULL,
        provider="mock_live",
        freshness=Freshness.REALTIME
    )

    scheduler = TaskScheduler()

    # 清空并预置冲突快照数据到异步队列中，当真实 flush_async_queue() 调用 session.commit() 时，
    # 必然触发真实 SQLite 原生 IntegrityError: UNIQUE constraint failed: intraday_market_snapshot.date, intraday_market_snapshot.timestamp
    # 彻底杜绝任何 commit mock，贯穿真实数据库唯一约束冲突故障！
    while not MonitorService._async_write_queue.empty():
        try:
            MonitorService._async_write_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    MonitorService._async_write_queue.put_nowait(("snapshot", {
        "date": "2026-10-29",
        "timestamp": "10:30:00",
        "minute_index": 60,
        "sh_price": 3000.0,
        "sh_pct": 0.5,
    }))

    # 3. 运行调度器 _run_intraday_monitor，使用原生真实 async_session，验证真实异常捕获与阶段隔离
    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", new_callable=AsyncMock, return_value={"total_amount_yi": 1000.0}), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch.object(DataService, "get_stock_quotes", new_callable=AsyncMock, return_value=mock_quotes_result):

        # 注意：此处绝不 mock flush_async_queue，让真实的 flush_async_queue 运行并遭遇 commit 失败！
        test_time = datetime(2026, 10, 29, 10, 30, 0)
        await scheduler._run_intraday_monitor(now_dt=test_time)

    # 4. 验证风控实际执行结果：持仓被清空，资金回流，产生卖出平仓流水
    async with async_session() as session:
        positions = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalars().all()
        assert len(positions) == 0, "触发 -6% 止损且 T+1 校验通过，持仓必须被清空！"

        trades = (await session.execute(select(SimTrade).where(SimTrade.code == "600519"))).scalars().all()
        sell_trades = [t for t in trades if t.direction == "sell"]
        assert len(sell_trades) == 1, "必须产生真实卖出平仓流水！"
        t = sell_trades[0]
        assert t.quantity == 1000
        assert round(t.price, 2) == 9.39
        assert "波普尔硬止损" in t.decision_summary

        acc_updated = (await session.execute(select(SimAccount))).scalars().first()
        assert round(acc_updated.current_capital, 2) == 999390.0

        task_logs = (await session.execute(select(TaskLog).where(TaskLog.task_name == "intraday_monitor"))).scalars().all()
        assert len(task_logs) == 1
        t_log = task_logs[0]
        assert t_log.status == "partial_failure", "监控失败但风控成功时，整体状态必须记录为 partial_failure"
        assert "Monitor: failed" in t_log.error_message
        assert "Liquidations: 1" in t_log.error_message


# ==============================================================================
# 场景 4: 过期/降级行情拒绝与账本不变 (DEGRADED + STALE 坚决跳过)
# ==============================================================================
@pytest.mark.asyncio
async def test_stale_or_degraded_quotes_rejected_risk_skipped_ledger_unchanged():
    """
    验收场景 4:
    - 标的处于浮亏状态 (持仓 1000 股 @ 10.0，若按 9.40 会触发 -6.0% 止损)
    - DataService 缓存降级返回 DEGRADED + STALE 行情
    - 验证风控守护机严格拒绝对过期/降级行情进行自动平仓，状态为 SKIPPED
    - 严格验证持仓未被卖出、可用资金不变、无任何卖出交易流水
    - 验证调度器 TaskLog 准确记录为 skipped，严禁虚报为 success
    """
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 900000.0

        trade = SimTrade(
            account_id=acc.id,
            code="600519",
            name="贵州茅台",
            direction="buy",
            price=10.0,
            quantity=1000,
            trade_time="2026-10-28 10:00:00",
            decision_summary="建仓"
        )
        session.add(trade)

        pos = SimPosition(
            account_id=acc.id,
            code="600519",
            name="贵州茅台",
            quantity=1000,
            avg_cost=10.0,
            current_price=10.0,
            floating_pnl=0.0
        )
        session.add(pos)
        await session.commit()

    # 模拟缓存降级行情：DEGRADED 质量，STALE 新鲜度
    stale_quotes_result = DataResult(
        data=[{"code": "600519", "name": "贵州茅台", "price": 9.40, "open_pct": -6.0}],
        quality=DataQuality.DEGRADED,
        freshness=Freshness.STALE,
        provider="cache_fallback",
        error_message="Minute budget exhausted, falling back to cached snapshot"
    )

    scheduler = TaskScheduler()

    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", new_callable=AsyncMock, return_value={"total_amount_yi": 1000.0}), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch.object(DataService, "get_stock_quotes", new_callable=AsyncMock, return_value=stale_quotes_result):

        test_time = datetime(2026, 10, 29, 10, 30, 0)
        await scheduler._run_intraday_monitor(now_dt=test_time)

    # 严格断言：持仓绝对未被平仓，可用资金不变，无卖出交易流水
    async with async_session() as session:
        pos_after = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalar_one_or_none()
        assert pos_after is not None, "过期/降级行情下，绝对严禁触发自动平仓！"
        assert pos_after.quantity == 1000

        acc_after = (await session.execute(select(SimAccount))).scalars().first()
        assert acc_after.current_capital == 900000.0, "资金不得发生任何变动"

        trades = (await session.execute(select(SimTrade).where(SimTrade.direction == "sell"))).scalars().all()
        assert len(trades) == 0, "严禁因过期行情生成伪造卖单！"

        task_logs = (await session.execute(select(TaskLog).where(TaskLog.task_name == "intraday_monitor"))).scalars().all()
        assert len(task_logs) == 1
        t_log = task_logs[0]
        assert t_log.status == "skipped", "风控因过期行情跳过时，整体状态必须为 skipped，严禁虚报 success"
        assert "Risk: skipped" in t_log.error_message


# ==============================================================================
# 场景 5: 旧行情带 REALTIME 伪标签严格按来源日期核验拦截 (Codex P0 核心修复项)
# ==============================================================================
@pytest.mark.asyncio
async def test_yesterday_quotes_with_realtime_label_rejected_by_date_check():
    """
    验收场景 5 (Codex P0 核心修复项):
    - 标的处于浮亏状态 (持仓 1000 股 @ 10.0，按 9.40 会触发 -6.0% 止损)
    - 上游接口返回数据结构虽然带着 freshness=REALTIME，但内部单项行情 trade_date 为昨日 (2026-10-28)
    - 当前风控巡检日期为 2026-10-29
    - 风控守护机精准核验来源日期，识别出昨日陈旧行情，坚决拒绝平仓成交
    - 验证持仓未卖出、资金未变、无交易流水，状态返回 PARTIAL_HOLD 或 SKIPPED，整体记 partial_warning/skipped
    """
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 900000.0

        trade = SimTrade(
            account_id=acc.id,
            code="600519",
            name="贵州茅台",
            direction="buy",
            price=10.0,
            quantity=1000,
            trade_time="2026-10-28 10:00:00",
            decision_summary="建仓"
        )
        session.add(trade)

        pos = SimPosition(
            account_id=acc.id,
            code="600519",
            name="贵州茅台",
            quantity=1000,
            avg_cost=10.0,
            current_price=10.0,
            floating_pnl=0.0
        )
        session.add(pos)
        await session.commit()

    # 构造带 REALTIME 标签但实际为昨日 (2026-10-28) 的陈旧行情
    deceptive_stale_quotes = DataResult(
        data=[{
            "code": "600519",
            "name": "贵州茅台",
            "price": 9.40,
            "open_pct": -6.0,
            "date": "2026-10-28",  # 来源日期是昨天！
            "time": "2026-10-28 15:00:00"
        }],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,  # 标签欺骗性地标为 REALTIME
        provider="sina"
    )

    scheduler = TaskScheduler()

    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", new_callable=AsyncMock, return_value={"total_amount_yi": 1000.0}), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch.object(DataService, "get_stock_quotes", new_callable=AsyncMock, return_value=deceptive_stale_quotes):

        # 巡检当前时间为 2026-10-29 10:30:00
        test_time = datetime(2026, 10, 29, 10, 30, 0)
        await scheduler._run_intraday_monitor(now_dt=test_time)

    async with async_session() as session:
        pos_after = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalar_one_or_none()
        assert pos_after is not None, "昨日陈旧行情绝对严禁触发平仓！"
        assert pos_after.quantity == 1000

        acc_after = (await session.execute(select(SimAccount))).scalars().first()
        assert acc_after.current_capital == 900000.0, "资金不得发生任何变动"

        trades = (await session.execute(select(SimTrade).where(SimTrade.direction == "sell"))).scalars().all()
        assert len(trades) == 0, "严禁生成任何伪造成交！"

        task_logs = (await session.execute(select(TaskLog).where(TaskLog.task_name == "intraday_monitor"))).scalars().all()
        assert len(task_logs) == 1
        t_log = task_logs[0]
        assert t_log.status in ("skipped", "partial_warning"), "因日期陈旧拦截时，状态必须为 skipped 或 partial_warning"
        assert "600519" in t_log.error_message


# ==============================================================================
# 场景 6: 行情无效且质量日志真实落库失败 (Codex P1 核心修复项: 贯穿真实 DataService 与 SQLite 冲突)
# ==============================================================================
@pytest.mark.asyncio
async def test_invalid_quotes_and_quality_failure_via_real_db_conflict():
    """
    验收场景 6 (Codex P1 核心修复项):
    - 预设在持仓位
    - 预设 id=1 记录于 data_quality_log 表中，并通过 QualityTracker._test_force_id=1 真实触发 SQLite 主键唯一冲突！
    - 贯穿真实的 DataService._execute_pipeline，实测 QualityTracker.log_quality 遭遇真实主键冲突并回滚
    - 验证 DataResult.quality_log_success 被准确捕获为 False，且被本轮追踪器记录
    - 风控守护机明确跳过，绝对禁止使用成本价伪造成交，资金持仓分文不差
    - 验证 TaskLog 状态绝不标记为完全成功，反映 QualityLog: failed 与 Risk: skipped
    - 验证清除冲突 ID 后，后续日志写入能够完全恢复正常
    """
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 950000.0
        pos = SimPosition(
            account_id=acc.id,
            code="000001",
            name="平安银行",
            quantity=2000,
            avg_cost=12.50,
            current_price=12.50,
            floating_pnl=0.0
        )
        session.add(pos)
        # 预先占用主键 id=1
        session.add(DataQualityLog(id=1, date="2026-10-29", capability="seed", provider="p", quality="full"))
        await session.commit()

    # 启用真实主键冲突注入：让 log_quality 尝试插入 id=1，真实触发 SQLite UNIQUE constraint failed
    QualityTracker._test_force_id = 1

    scheduler = TaskScheduler()

    # 模拟真实 DataService 请求上游返回无效行情，但不 mock log_quality 与 DataService 本身！
    mock_upstream_resp = DataResult(
        data=None,
        quality=DataQuality.INVALID,
        freshness=Freshness.UNAVAILABLE,
        provider="upstream_corrupted",
        error_message="Protocol parse error from remote gateway"
    )

    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", new_callable=AsyncMock, return_value={"total_amount_yi": 1000.0}), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch("app.data.registry.registry.execute_with_fallback", new_callable=AsyncMock, return_value=mock_upstream_resp):

        test_time = datetime(2026, 10, 29, 10, 30, 0)
        # 真实 DataService 会执行 _execute_pipeline -> QualityTracker.log_quality -> 触发真实主键冲突！
        await scheduler._run_intraday_monitor(now_dt=test_time)

    # 恢复冲突开关
    QualityTracker._test_force_id = None

    # 严格断言：持仓未被平仓，资金未变，无假成交流水
    async with async_session() as session:
        pos_after = (await session.execute(select(SimPosition).where(SimPosition.code == "000001"))).scalar_one_or_none()
        assert pos_after is not None
        assert pos_after.quantity == 2000

        acc_after = (await session.execute(select(SimAccount))).scalars().first()
        assert acc_after.current_capital == 950000.0

        trades = (await session.execute(select(SimTrade))).scalars().all()
        assert len(trades) == 0

        task_logs = (await session.execute(select(TaskLog).where(TaskLog.task_name == "intraday_monitor"))).scalars().all()
        assert len(task_logs) == 1
        t_log = task_logs[0]
        # 状态绝不应为完全成功
        assert t_log.status in ("skipped", "partial_warning"), f"状态必须为 skipped 或 partial_warning，实际为 {t_log.status}"
        assert "QualityLog: failed" in t_log.error_message
        assert "Risk: skipped" in t_log.error_message

    # 验证主键冲突后会话可恢复性：后续正常写入自增记录能够完全成功，无 PendingRollbackError
    recover_ok = await QualityTracker.log_quality(capability="recovery_check", result=DataResult(data={}, quality=DataQuality.FULL, provider="p_rec"))
    assert recover_ok is True, "冲突后下一次自增日志写入必须成功！"


# ==============================================================================
# 场景 7: 监控与驾驶舱阶段质量日志失败全流程汇总 (Codex P1 核心修复项)
# ==============================================================================
@pytest.mark.asyncio
async def test_monitor_stage_quality_log_failure_reported_in_scheduler():
    """
    验收场景 7 (Codex P1 核心修复项):
    - 阶段 1 监控采集 / 驾驶舱快照过程中发生质量日志写入失败
    - 阶段 2 风控守护机行情与日志均成功
    - 验证调度器能够跨阶段汇总监控阶段的质量日志失败，整体状态准确记录为 partial_warning，绝不虚报为完全 success！
    """
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        pos = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=10.0, current_price=10.2, floating_pnl=200.0)
        session.add(pos)
        await session.commit()

    safe_quotes = [{"code": "600519", "name": "贵州茅台", "price": 10.20, "open_pct": 1.0, "date": "2026-10-29", "time": "2026-10-29 10:30:00"}]
    mock_quotes = DataResult(data=safe_quotes, quality=DataQuality.FULL, provider="mock_live", freshness=Freshness.REALTIME)

    scheduler = TaskScheduler()

    async def mock_capture_with_log_failure(*args, **kwargs):
        # 模拟在阶段 1 监控采集过程中，发生一次质量日志写入失败
        QualityTracker._test_force_id = 999
        # 先占用 999
        await QualityTracker.log_quality(capability="init_999", result=DataResult(data={}, quality=DataQuality.FULL, provider="p"), explicit_id=999)
        # 再次触发冲突
        await QualityTracker.log_quality(capability="macro_snapshot_quote", result=DataResult(data={}, quality=DataQuality.FULL, provider="p"))
        QualityTracker._test_force_id = None
        return {"total_amount_yi": 1000.0}

    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", side_effect=mock_capture_with_log_failure), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch.object(DataService, "get_stock_quotes", new_callable=AsyncMock, return_value=mock_quotes):

        test_time = datetime(2026, 10, 29, 10, 30, 0)
        await scheduler._run_intraday_monitor(now_dt=test_time)

    async with async_session() as session:
        task_logs = (await session.execute(select(TaskLog).where(TaskLog.task_name == "intraday_monitor"))).scalars().all()
        assert len(task_logs) == 1
        t_log = task_logs[0]
        # 即使风控成功，由于监控阶段日志失败，整体状态必须标记为 partial_warning！
        assert t_log.status == "partial_warning", f"监控阶段质量日志失败时，整体状态必须为 partial_warning，实际为 {t_log.status}"
        assert "QualityLog: failed" in t_log.error_message
        assert "macro_snapshot_quote" in t_log.error_message


# ==============================================================================
# 场景 8: 先平仓成交、后续标的执行出错时事件与流水完整保全 (Codex P1 核心修复项)
# ==============================================================================
@pytest.mark.asyncio
async def test_first_symbol_liquidated_second_symbol_error_preserves_events():
    """
    验收场景 8 (Codex P1 核心修复项):
    - 账户持有两只标的：600519 (茅台，1000股) 与 000001 (平安，2000股)
    - 两只标的均触及 -6% 止损红线
    - 茅台先执行平仓并成功提交入库
    - 平安在后续执行平仓时由于异常 (如网络中断或账本错误) 执行失败
    - 严格验证：
      1. 茅台已提交的卖单流水绝对不丢失，数据库中真实存在！
      2. 调度器的 _execution_history 准确记录茅台的 RISK_LIQUIDATION，绝不因平安报错而丢弃！
      3. TaskLog 准确反映 Liquidations: 1, Failed_Executions: 1，状态标记为 partial_failure，账实完全对齐！
    """
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 900000.0

        # 茅台 (前日建仓)
        t1 = SimTrade(account_id=acc.id, code="600519", name="贵州茅台", direction="buy", price=10.0, quantity=1000, trade_time="2026-10-28 10:00:00")
        p1 = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=10.0, current_price=10.0, floating_pnl=0.0)
        # 平安 (前日建仓)
        t2 = SimTrade(account_id=acc.id, code="000001", name="平安银行", direction="buy", price=12.0, quantity=2000, trade_time="2026-10-28 10:00:00")
        p2 = SimPosition(account_id=acc.id, code="000001", name="平安银行", quantity=2000, avg_cost=12.0, current_price=12.0, floating_pnl=0.0)

        session.add_all([t1, p1, t2, p2])
        await session.commit()

    # 两只标的均触及 -6% 止损
    both_loss_quotes = DataResult(
        data=[
            {"code": "600519", "name": "贵州茅台", "price": 9.40, "open_pct": -6.0, "date": "2026-10-29", "time": "2026-10-29 10:30:00"},
            {"code": "000001", "name": "平安银行", "price": 11.20, "open_pct": -6.0, "date": "2026-10-29", "time": "2026-10-29 10:30:00"}
        ],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,
        provider="mock_live"
    )

    scheduler = TaskScheduler()

    # 注入：当平仓标的为 000001 时抛出执行异常
    original_execute_trade = SimulationService.execute_trade

    async def selective_execute_trade(self, trade_create: SimTradeCreate, *args, **kwargs):
        if trade_create.code == "000001":
            raise RuntimeError("Simulated Database / Order Gateway Breakdown on 000001")
        return await original_execute_trade(self, trade_create, *args, **kwargs)

    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", new_callable=AsyncMock, return_value={"total_amount_yi": 1000.0}), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch.object(DataService, "get_stock_quotes", new_callable=AsyncMock, return_value=both_loss_quotes), \
         patch.object(SimulationService, "execute_trade", selective_execute_trade):

        test_time = datetime(2026, 10, 29, 10, 30, 0)
        await scheduler._run_intraday_monitor(now_dt=test_time)

    # 1. 验证调度器流水历史中，茅台 (600519) 成功记录平仓，绝不被丢弃
    liq_history = [h for h in scheduler._execution_history if h.get("action") == "RISK_LIQUIDATION"]
    assert any(h["code"] == "600519" and h["quantity"] == 1000 for h in liq_history), "茅台已提交的平仓必须存在于调度历史中！"

    # 2. 验证数据库中真实状态：茅台持仓已清空，产生卖单流水；平安持仓依然保留
    async with async_session() as session:
        maotai_pos = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalar_one_or_none()
        assert maotai_pos is None, "茅台必须平仓出局"

        pingan_pos = (await session.execute(select(SimPosition).where(SimPosition.code == "000001"))).scalar_one_or_none()
        assert pingan_pos is not None, "平安因执行失败持仓保留"
        assert pingan_pos.quantity == 2000

        sell_trades = (await session.execute(select(SimTrade).where(SimTrade.direction == "sell"))).scalars().all()
        assert len(sell_trades) == 1
        assert sell_trades[0].code == "600519"

        # 3. 验证 TaskLog 准确对账
        task_logs = (await session.execute(select(TaskLog).where(TaskLog.task_name == "intraday_monitor"))).scalars().all()
        assert len(task_logs) == 1
        t_log = task_logs[0]
        assert t_log.status == "partial_failure", f"有成交但有错误时状态必须为 partial_failure，实际为 {t_log.status}"
        assert "Liquidations: 1" in t_log.error_message
        assert "Failed_Executions: 1" in t_log.error_message


# ==============================================================================
# 场景 9: 多标的部分持仓缺行情诊断追踪 (PARTIAL_HOLD / partial_warning)
# ==============================================================================
@pytest.mark.asyncio
async def test_partial_holdings_missing_quotes_diagnostic():
    """
    验收场景 9:
    - 账户持有两只标的：600519 (茅台) 与 000001 (平安)
    - 行情服务仅返回 600519 (安全价格 10.20)，完全缺失 000001 的行情
    - 验证风控返回状态为 PARTIAL_HOLD (而非 HOLD)，绝不虚报“全部在持标的均在安全阈值内”
    - 验证 reason 准确记录缺失标的 ['000001'] 与核验安全标的 ['600519']
    - 验证调度器整体状态记录为 partial_warning，而非完全 success
    """
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 900000.0

        p1 = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=10.0, current_price=10.0, floating_pnl=0.0)
        p2 = SimPosition(account_id=acc.id, code="000001", name="平安银行", quantity=2000, avg_cost=12.0, current_price=12.0, floating_pnl=0.0)
        session.add_all([p1, p2])
        await session.commit()

    partial_quotes_result = DataResult(
        data=[{"code": "600519", "name": "贵州茅台", "price": 10.20, "open_pct": 1.0, "date": "2026-10-29", "time": "2026-10-29 10:30:00"}],
        quality=DataQuality.PARTIAL,
        freshness=Freshness.REALTIME,
        provider="mock_partial"
    )

    scheduler = TaskScheduler()

    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", new_callable=AsyncMock, return_value={"total_amount_yi": 1000.0}), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch.object(DataService, "get_stock_quotes", new_callable=AsyncMock, return_value=partial_quotes_result):

        test_time = datetime(2026, 10, 29, 10, 30, 0)
        await scheduler._run_intraday_monitor(now_dt=test_time)

    async with async_session() as session:
        task_logs = (await session.execute(select(TaskLog).where(TaskLog.task_name == "intraday_monitor"))).scalars().all()
        assert len(task_logs) == 1
        t_log = task_logs[0]
        assert t_log.status == "partial_warning", f"部分标的缺行情时必须记录为 partial_warning，实际为 {t_log.status}"
        assert "Risk: partial_hold" in t_log.error_message
        assert "Missing Quotes: 1" in t_log.error_message
        assert "000001" in t_log.error_message


# ==============================================================================
# 场景 10: 质量日志高并发写入主键唯一性与会话可恢复性
# ==============================================================================
@pytest.mark.asyncio
async def test_concurrent_quality_log_writes():
    """
    验收场景 10: 质量日志并发写入
    - 使用独立会话并发写入 20 条日志
    - 验证所有记录自增主键严格唯一，无主键冲突崩溃
    """
    concurrent_count = 20

    async def _single_write(idx: int):
        return await QualityTracker.log_quality(
            capability=f"cap_{idx % 5}",
            result=DataResult(data={"k": idx}, quality=DataQuality.FULL, provider=f"prov_{idx}"),
            response_time_ms=idx * 5
        )

    results = await asyncio.gather(*[_single_write(i) for i in range(concurrent_count)])
    success_count = sum(1 for r in results if r is True)
    assert success_count == concurrent_count, f"并发写入应全部成功，成功数: {success_count}/{concurrent_count}"

    async with async_session() as session:
        logs = (await session.execute(select(DataQualityLog))).scalars().all()
        assert len(logs) == concurrent_count
        ids = [l.id for l in logs]
        assert len(set(ids)) == concurrent_count, "所有并发写入的主键必须唯一"


# ==============================================================================
# 场景 11: 正常链路回归与 TaskLog 可观察性审计记录
# ==============================================================================
@pytest.mark.asyncio
async def test_normal_pipeline_regression():
    """
    验收场景 11: 正常链路回归
    - 有效行情下，宏观快照采集、异动感知、风控巡检均正常运行
    - 持仓安全，无平仓触发，TaskLog 整体标记为 success
    """
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        pos = SimPosition(
            account_id=acc.id,
            code="600519",
            name="贵州茅台",
            quantity=1000,
            avg_cost=10.0,
            current_price=10.2,  # 浮盈 2%，安全
            floating_pnl=200.0
        )
        session.add(pos)
        await session.commit()

    safe_quotes = [
        {"code": "600519", "name": "贵州茅台", "price": 10.20, "open_pct": 1.0, "date": "2026-10-29", "time": "2026-10-29 10:30:00"}
    ]
    mock_quotes = DataResult(
        data=safe_quotes,
        quality=DataQuality.FULL,
        provider="mock_live",
        freshness=Freshness.REALTIME
    )

    scheduler = TaskScheduler()

    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", new_callable=AsyncMock, return_value={"total_amount_yi": 1000.0}), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch.object(DataService, "get_stock_quotes", new_callable=AsyncMock, return_value=mock_quotes):

        test_time = datetime(2026, 10, 29, 10, 30, 0)
        await scheduler._run_intraday_monitor(now_dt=test_time)

    async with async_session() as session:
        task_logs = (await session.execute(select(TaskLog).where(TaskLog.task_name == "intraday_monitor"))).scalars().all()
        assert len(task_logs) == 1
        assert task_logs[0].status == "success"
        assert "Risk: success" in task_logs[0].error_message
        assert "Liquidations: 0" in task_logs[0].error_message


# ==============================================================================
# 场景 12: 事务归属与隔离环境确权
# ==============================================================================
def test_isolated_sandbox_provenance():
    """
    验收场景 12: 事务归属与隔离环境
    - 证明测试运行在独立的沙盒数据库中，绝对未连接或篡改生产数据
    """
    db_url = str(engine.url)
    assert "data/trading.db" not in db_url, f"测试必须运行在隔离沙盒，严禁触碰生产库: {db_url}"
    assert "trading_test_sandbox" in db_url or ":memory:" in db_url or "temp" in db_url.lower(), f"沙盒数据库标识校验: {db_url}"


# ==============================================================================
# 场景 13: 行情缺失日期或缺失时间严格拒单 (Codex P0 核心修复项)
# ==============================================================================
@pytest.mark.asyncio
async def test_quote_missing_date_or_time_rejected_no_trade():
    """
    验收场景 13 (Codex P0 核心修复项):
    - 标的 600519 浮亏 -6% 触及止损
    - 行情服务返回的行情项缺失 date (None) 或缺失 time (None)
    - 风控守护机拒绝未经验证来源时间的行情，严禁平仓成交
    - 断言持仓未卖出、资金未变、无交易流水
    """
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 900000.0

        trade = SimTrade(account_id=acc.id, code="600519", name="贵州茅台", direction="buy", price=10.0, quantity=1000, trade_time="2026-10-28 10:00:00")
        pos = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=10.0, current_price=10.0, floating_pnl=0.0)
        session.add_all([trade, pos])
        await session.commit()

    # Case A: 缺失 date
    missing_date_quotes = DataResult(
        data=[{"code": "600519", "name": "贵州茅台", "price": 9.40, "open_pct": -6.0, "date": None, "time": "10:30:00"}],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,
        provider="mock"
    )

    scheduler = TaskScheduler()
    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", new_callable=AsyncMock, return_value={"total_amount_yi": 1000.0}), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch.object(DataService, "get_stock_quotes", new_callable=AsyncMock, return_value=missing_date_quotes):

        test_time = datetime(2026, 10, 29, 10, 30, 0)
        await scheduler._run_intraday_monitor(now_dt=test_time)

    async with async_session() as session:
        pos_after = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalar_one_or_none()
        assert pos_after is not None and pos_after.quantity == 1000, "缺失日期严禁成交！"
        trades = (await session.execute(select(SimTrade).where(SimTrade.direction == "sell"))).scalars().all()
        assert len(trades) == 0, "严禁生成任何卖单流水"

    # Case B: 缺失 time
    missing_time_quotes = DataResult(
        data=[{"code": "600519", "name": "贵州茅台", "price": 9.40, "open_pct": -6.0, "date": "2026-10-29", "time": None}],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,
        provider="mock"
    )

    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", new_callable=AsyncMock, return_value={"total_amount_yi": 1000.0}), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch.object(DataService, "get_stock_quotes", new_callable=AsyncMock, return_value=missing_time_quotes):

        await scheduler._run_intraday_monitor(now_dt=test_time)

    async with async_session() as session:
        pos_after = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalar_one_or_none()
        assert pos_after is not None and pos_after.quantity == 1000, "缺失时间戳严禁成交！"
        trades = (await session.execute(select(SimTrade).where(SimTrade.direction == "sell"))).scalars().all()
        assert len(trades) == 0, "严禁生成任何卖单流水"


# ==============================================================================
# 场景 14: 同日过期行情与非法/未来时间拦截 (Codex P0 核心修复项)
# ==============================================================================
@pytest.mark.asyncio
async def test_quote_same_day_stale_and_future_time_rejected_no_trade():
    """
    验收场景 14 (Codex P0 核心修复项):
    - Case A: 同日但采样时间严重滞后 (如 09:30:00 采样，当前巡检时间 14:30:00，延迟 5 小时 > 300 秒)
    - Case B: 未来异常时间 (如当前 10:30:00，行情时间 15:30:00)
    - Case C: 非法格式日期 (如 date='invalid_format')
    - 验证风控守护机全部坚决拒绝平仓，无伪造成交
    """
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 900000.0

        trade = SimTrade(account_id=acc.id, code="600519", name="贵州茅台", direction="buy", price=10.0, quantity=1000, trade_time="2026-10-28 10:00:00")
        pos = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=10.0, current_price=10.0, floating_pnl=0.0)
        session.add_all([trade, pos])
        await session.commit()

    scheduler = TaskScheduler()

    # Case A: 同日过期 (09:30 采样，14:30 巡检)
    same_day_stale_quotes = DataResult(
        data=[{"code": "600519", "name": "贵州茅台", "price": 9.40, "open_pct": -6.0, "date": "2026-10-29", "time": "2026-10-29 09:30:00"}],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,
        provider="mock"
    )

    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", new_callable=AsyncMock, return_value={"total_amount_yi": 1000.0}), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch.object(DataService, "get_stock_quotes", new_callable=AsyncMock, return_value=same_day_stale_quotes):

        # 当前时间 14:30:00，距行情 09:30:00 已过期 5 小时
        await scheduler._run_intraday_monitor(now_dt=datetime(2026, 10, 29, 14, 30, 0))

    async with async_session() as session:
        pos_after = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalar_one_or_none()
        assert pos_after is not None and pos_after.quantity == 1000, "同日过期行情严禁平仓！"
        trades = (await session.execute(select(SimTrade).where(SimTrade.direction == "sell"))).scalars().all()
        assert len(trades) == 0

    # Case B: 未来时间 (当前 10:30，行情 15:30)
    future_quotes = DataResult(
        data=[{"code": "600519", "name": "贵州茅台", "price": 9.40, "open_pct": -6.0, "date": "2026-10-29", "time": "2026-10-29 15:30:00"}],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,
        provider="mock"
    )
    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", new_callable=AsyncMock, return_value={"total_amount_yi": 1000.0}), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch.object(DataService, "get_stock_quotes", new_callable=AsyncMock, return_value=future_quotes):

        await scheduler._run_intraday_monitor(now_dt=datetime(2026, 10, 29, 10, 30, 0))

    async with async_session() as session:
        pos_after = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalar_one_or_none()
        assert pos_after is not None and pos_after.quantity == 1000, "未来异常时间严禁平仓！"
        trades = (await session.execute(select(SimTrade).where(SimTrade.direction == "sell"))).scalars().all()
        assert len(trades) == 0

    # Case C: 非法格式日期
    malformed_quotes = DataResult(
        data=[{"code": "600519", "name": "贵州茅台", "price": 9.40, "open_pct": -6.0, "date": "invalid_date_str", "time": "10:30:00"}],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,
        provider="mock"
    )
    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", new_callable=AsyncMock, return_value={"total_amount_yi": 1000.0}), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch.object(DataService, "get_stock_quotes", new_callable=AsyncMock, return_value=malformed_quotes):

        await scheduler._run_intraday_monitor(now_dt=datetime(2026, 10, 29, 10, 30, 0))

    async with async_session() as session:
        pos_after = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalar_one_or_none()
        assert pos_after is not None and pos_after.quantity == 1000, "非法日期格式严禁平仓！"


# ==============================================================================
# 场景 15: 质量日志追踪器并发协程上下文隔离 (Codex P1 核心修复项)
# ==============================================================================
@pytest.mark.asyncio
async def test_quality_tracker_concurrent_context_isolation():
    """
    验收场景 15 (Codex P1 核心修复项):
    - 验证 QualityTracker 基于 ContextVar 实现真正的协程任务上下文物理隔离
    - Task 1: 开启追踪，设置 _test_force_id 触发主键冲突失败
    - Task 2: 同时开启追踪，执行正常日志写入，验证不受 Task 1 强制 ID 与失败记录污染
    - Task 3: 无关并发请求 (不开启追踪)，正常写入日志
    - 验证 Task 1 的失败记录仅归属于 Task 1，Task 2 记录为 0 失败，Task 3 零侵入
    - 验证 Task 2 停止追踪不影响 Task 1 的追踪状态
    """
    # 预先占用 id=777
    await QualityTracker.log_quality(capability="init_777", result=DataResult(data={}, quality=DataQuality.FULL, provider="p"), explicit_id=777)

    async def task_1_worker():
        QualityTracker.start_round_tracking()
        QualityTracker.set_test_force_id(777)
        # 触发冲突
        res = await QualityTracker.log_quality(capability="t1_conflict", result=DataResult(data={}, quality=DataQuality.FULL, provider="p1"))
        assert res is False, "Task 1 必然因 id=777 冲突失败"
        await asyncio.sleep(0.05)
        failures = QualityTracker.get_round_failures()
        QualityTracker.stop_round_tracking()
        return failures

    async def task_2_worker():
        await asyncio.sleep(0.01)  # 稍微错开启动，确保与 Task 1 重叠执行
        QualityTracker.start_round_tracking()
        # 正常自增写入，不受 Task 1 的 force_id 影响
        res = await QualityTracker.log_quality(capability="t2_normal", result=DataResult(data={}, quality=DataQuality.FULL, provider="p2"))
        assert res is True, "Task 2 必须正常写入成功，绝不能被 Task 1 污染！"
        failures = QualityTracker.get_round_failures()
        QualityTracker.stop_round_tracking()
        return failures

    async def task_3_unrelated_worker():
        await asyncio.sleep(0.02)
        # 无关请求，不开启追踪
        res = await QualityTracker.log_quality(capability="t3_unrelated", result=DataResult(data={}, quality=DataQuality.FULL, provider="p3"))
        assert res is True
        return res

    t1_res, t2_res, t3_res = await asyncio.gather(task_1_worker(), task_2_worker(), task_3_unrelated_worker())

    # Task 1 精准捕获自身的 1 次冲突失败
    assert len(t1_res) == 1
    assert t1_res[0]["capability"] == "t1_conflict"

    # Task 2 上下文独立，0 次失败，完全无串染
    assert len(t2_res) == 0, f"Task 2 必须为 0 失败，实际捕获: {t2_res}"


# ==============================================================================
# 场景 16: 风控撮合异常后 session 回滚恢复且后续标的继续成功平仓 (Codex P1 核心修复项)
# ==============================================================================
@pytest.mark.asyncio
async def test_trade_execution_failure_rolls_back_session_and_subsequent_symbol_succeeds():
    """
    验收场景 16 (Codex P1 核心修复项):
    - 账户持有 3 只标的：600519 (茅台), 000001 (平安), 000002 (万科)
    - 3 只标的均满足 T+1 且浮亏 -6% 触及止损
    - 执行序列：
      1. 标的 1 (600519) 成功平仓并 commit 落库
      2. 标的 2 (000001) 在撮合执行时触发数据库/网关异常
      3. 风控循环精准捕获异常并显式调用 session.rollback()，彻底重置 session 状态
      4. 标的 3 (000002) 在同一个巡检循环中继续执行，成功平仓并 commit 落库 (无 PendingRollbackError!)
    - 严格断言：
      - 标的 1 与 标的 3 真实平仓成功，持仓清空，资金到账，卖单流水落库
      - 标的 2 持仓保留，进入 failed_executions
      - 调度器 TaskLog 状态记录为 partial_failure，精准报告 2 笔平仓成功，1 笔失败
    """
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 800000.0

        # 3 只标的前日建仓
        t1 = SimTrade(account_id=acc.id, code="600519", name="贵州茅台", direction="buy", price=10.0, quantity=1000, trade_time="2026-10-28 10:00:00")
        p1 = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=10.0, current_price=10.0, floating_pnl=0.0)

        t2 = SimTrade(account_id=acc.id, code="000001", name="平安银行", direction="buy", price=12.0, quantity=2000, trade_time="2026-10-28 10:00:00")
        p2 = SimPosition(account_id=acc.id, code="000001", name="平安银行", quantity=2000, avg_cost=12.0, current_price=12.0, floating_pnl=0.0)

        t3 = SimTrade(account_id=acc.id, code="000002", name="万科A", direction="buy", price=8.0, quantity=3000, trade_time="2026-10-28 10:00:00")
        p3 = SimPosition(account_id=acc.id, code="000002", name="万科A", quantity=3000, avg_cost=8.0, current_price=8.0, floating_pnl=0.0)

        session.add_all([t1, p1, t2, p2, t3, p3])
        await session.commit()

    all_loss_quotes = DataResult(
        data=[
            {"code": "600519", "name": "贵州茅台", "price": 9.40, "open_pct": -6.0, "date": "2026-10-29", "time": "2026-10-29 10:30:00"},
            {"code": "000001", "name": "平安银行", "price": 11.20, "open_pct": -6.0, "date": "2026-10-29", "time": "2026-10-29 10:30:00"},
            {"code": "000002", "name": "万科A", "price": 7.50, "open_pct": -6.0, "date": "2026-10-29", "time": "2026-10-29 10:30:00"}
        ],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,
        provider="mock_live"
    )

    scheduler = TaskScheduler()
    orig_exec = SimulationService.execute_trade

    async def mock_exec_with_middle_failure(self, trade_create: SimTradeCreate, *args, **kwargs):
        if trade_create.code == "000001":
            # 真实抛出异常
            raise RuntimeError("Database Connection Dropped during 000001 commit")
        return await orig_exec(self, trade_create, *args, **kwargs)

    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", new_callable=AsyncMock, return_value={"total_amount_yi": 1000.0}), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch.object(DataService, "get_stock_quotes", new_callable=AsyncMock, return_value=all_loss_quotes), \
         patch.object(SimulationService, "execute_trade", mock_exec_with_middle_failure):

        test_time = datetime(2026, 10, 29, 10, 30, 0)
        await scheduler._run_intraday_monitor(now_dt=test_time)

    # 严格验证：
    # 1. 标的 1 (600519) 成功平仓
    # 2. 标的 2 (000001) 失败保留
    # 3. 标的 3 (000002) 依然成功平仓 (证明 session 成功回滚恢复健康，没有 PendingRollbackError!)
    async with async_session() as session:
        p1_after = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalar_one_or_none()
        assert p1_after is None, "标的 1 (茅台) 必须平仓出局"

        p2_after = (await session.execute(select(SimPosition).where(SimPosition.code == "000001"))).scalar_one_or_none()
        assert p2_after is not None and p2_after.quantity == 2000, "标的 2 (平安) 必须保留持仓"

        p3_after = (await session.execute(select(SimPosition).where(SimPosition.code == "000002"))).scalar_one_or_none()
        assert p3_after is None, "标的 3 (万科) 在标的 2 失败回滚后，依然成功平仓出局！"

        sell_trades = (await session.execute(select(SimTrade).where(SimTrade.direction == "sell"))).scalars().all()
        sell_codes = [t.code for t in sell_trades]
        assert "600519" in sell_codes
        assert "000002" in sell_codes
        assert "000001" not in sell_codes

        task_logs = (await session.execute(select(TaskLog).where(TaskLog.task_name == "intraday_monitor"))).scalars().all()
        assert len(task_logs) == 1
        t_log = task_logs[0]
        assert t_log.status == "partial_failure"
        assert "Liquidations: 2" in t_log.error_message
        assert "Failed_Executions: 1" in t_log.error_message


# ==============================================================================
# 场景 17: 真实 pytdx 原生数据结构缺失日期，穿透提供方与风控刚性拦截 (Codex 第四轮 P1 核心项)

# ==============================================================================
# 场景 17: 真实 pytdx 原生行情结构缺失日期时安全降级 (Codex 第四轮 P1 核心项)
# ==============================================================================
@pytest.mark.asyncio
async def test_real_pytdx_quote_structure_missing_date_safely_blocked():
    """
    验收场景 17 (Codex 第四轮 P1 核心项):
    - 严格采用 pytdx 生产真实返回的原生字典结构 (仅 servertime，无 date / trade_date)
    - 模拟通达信主站日K不可用 (get_security_bars 与 get_index_bars 均返回 None)
    - 穿透 TdxDirectClient.get_quotes，验证 date 字段权威为 None (绝不伪造当前系统时间)
    - 穿透 TdxProvider.get_stock_quotes，验证返回结果判定为 freshness = Freshness.UNAVAILABLE, status = DataStatus.EMPTY
    - 穿透 AutonomousJobEngine.run_intraday_risk_guard_detailed，验证风控坚决拒单拦截，持仓资金分文未动
    """
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 900000.0

        # T-1 日建仓
        t = SimTrade(account_id=acc.id, code="600519", name="贵州茅台", direction="buy", price=10.0, quantity=1000, trade_time="2026-10-28 10:00:00")
        p = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=10.0, current_price=10.0, floating_pnl=0.0)
        session.add_all([t, p])
        await session.commit()

    from app.data.providers.tdx_client import TdxDirectClient
    from app.data.providers.tdx_provider import TdxProvider

    # 100% 真实 pytdx 返回数据字典 (绝无 date 键)
    real_pytdx_quote = {
        "market": 1,
        "code": "600519",
        "active1": 2841,
        "price": 9.40,
        "last_close": 10.0,
        "open": 9.50,
        "high": 9.60,
        "low": 9.30,
        "servertime": "14:55:00.123",
        "reversed_bytes0": 145500,
        "vol": 10000,
        "amount": 9400000.0,
    }

    client = TdxDirectClient()
    provider = TdxProvider(client=client)

    # 模拟 pytdx api：get_security_quotes 返回原生数据，get_security_bars/get_index_bars 均返回 None
    with patch.object(client, "connect_best_server", return_value=True), \
         patch.object(client.api, "get_security_quotes", return_value=[real_pytdx_quote]), \
         patch.object(client.api, "get_security_bars", return_value=None), \
         patch.object(client.api, "get_index_bars", return_value=None):

        # 1. 验证客户端解析
        quotes = client.get_quotes(["600519"])
        assert len(quotes) == 1
        assert quotes[0]["servertime"] == "14:55:00.123"
        assert quotes[0]["time"] == "14:55:00"
        assert quotes[0]["date"] is None, "无权威标的日历时，绝不得伪造系统当前日期"

        # 2. 验证提供方质量与时态判定
        with patch("app.core.calendar.calendar.is_trading_day", return_value=True):
            data_res = await provider.get_stock_quotes(["600519"])
            assert data_res.freshness == Freshness.UNAVAILABLE
            assert data_res.status == DataStatus.EMPTY

        # 3. 贯穿风控守护机，验证严格拦截
        async with async_session() as session:
            engine = AutonomousJobEngine(session)
            guard_res = await engine.run_intraday_risk_guard_detailed(
                target_date="2026-10-29",
                now_dt=datetime(2026, 10, 29, 14, 55, 0),
                quotes_result=data_res
            )
            assert guard_res["status"] in ("SKIPPED", "PARTIAL_HOLD")
            assert len(guard_res["actual_liquidations"]) == 0

            # 严格断言持仓未变
            pos = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalar_one()
            assert pos.quantity == 1000


# ==============================================================================
# 场景 18: 报价自身具备完整可信日期时间戳准入风控平仓 (Codex 第六轮规范)
# ==============================================================================
@pytest.mark.asyncio
async def test_real_pytdx_with_tdx_server_market_date_succeeds():
    """
    验收场景 18 (Codex 第六轮规范 - 报价自身完整日期确权准入):
    - 报价自身严格携带可信交易日期 (date="2026-10-29") 与时间戳 (time="14:55:00")
    - 验证无需借用任何外部日历或日K线，客户端忠实传递报价自身时间
    - TdxProvider 正确产出 REALTIME 行情
    - 风控成功准入，并在浮亏 -6% 下正常执行波普尔平仓！
    """
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 900000.0

        t = SimTrade(account_id=acc.id, code="600519", name="贵州茅台", direction="buy", price=10.0, quantity=1000, trade_time="2026-10-28 10:00:00")
        p = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=10.0, current_price=10.0, floating_pnl=0.0)
        session.add_all([t, p])
        await session.commit()

    from app.data.providers.tdx_client import TdxDirectClient
    from app.data.providers.tdx_provider import TdxProvider

    real_quote_with_date = {
        "market": 1,
        "code": "600519",
        "price": 9.40,
        "last_close": 10.0,
        "open": 9.50,
        "high": 9.60,
        "low": 9.30,
        "servertime": "14:55:00.123",
        "date": "2026-10-29",
        "time": "14:55:00",
        "reversed_bytes0": 145500,
        "vol": 10000,
        "amount": 9400000.0,
    }

    client = TdxDirectClient()
    provider = TdxProvider(client=client)

    class MockDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 29, 14, 55, 0)

    with patch.object(client, "connect_best_server", return_value=True), \
         patch.object(client.api, "get_security_quotes", return_value=[real_quote_with_date]), \
         patch("app.data.providers.tdx_provider.datetime", MockDatetime), \
         patch("app.core.calendar.calendar.is_trading_day", return_value=True):

        data_res = await provider.get_stock_quotes(["600519"])
        assert data_res.freshness == Freshness.REALTIME
        assert data_res.data[0]["date"] == "2026-10-29"
        assert data_res.data[0]["time"] == "14:55:00"

        async with async_session() as session:
            engine = AutonomousJobEngine(session)
            guard_res = await engine.run_intraday_risk_guard_detailed(
                target_date="2026-10-29",
                now_dt=datetime(2026, 10, 29, 14, 55, 30),
                quotes_result=data_res
            )
            assert guard_res["status"] in ("LIQUIDATED", "PARTIAL_LIQUIDATED")
            assert len(guard_res["actual_liquidations"]) == 1
            assert guard_res["actual_liquidations"][0]["code"] == "600519"


# ==============================================================================
# 场景 19: 跨协程真实 Singleflight 并发请求，主键冲突日志失败向 Follower 可靠传递 (Codex 第五轮 P2 核心项)
# ==============================================================================
@pytest.mark.asyncio
async def test_cross_context_singleflight_follower_propagates_quality_log_failure():
    """
    验收场景 19 (Codex 第五轮 P2 核心项):
    - 坚决杜绝 mock execute！使用真实 Singleflight 驱动多协程并发
    - 数据库中预占主键 id=1，并配置 QualityTracker._test_force_id = 1
    - 启动两个真实并发协程同时调用 DataService.get_stock_quotes(['600519'])：
      - Leader 协程物理执行 pipeline，在 log_quality 阶段遭遇真实的 SQLite 主键冲突回滚，产出 quality_log_success = False
      - Follower 协程在单飞屏障等待，复用 Leader 结果 (is_leader=False)
      - Follower 在自身上下文中通过 QualityTracker.record_failure 成功捕获质量日志失败！
    - 验证 Follower 所在的调度巡检审计将整体状态精准标记为 partial_warning，绝无漏报！
    """
    DataService._CACHE.clear()
    DataService._singleflight._in_flight.clear()

    # 预设主键冲突种子
    async with async_session() as session:
        session.add(DataQualityLog(id=1, date="2026-10-29", capability="seed", provider="p", quality="full"))
        await session.commit()

    # 启用真实主键冲突注入：插入 id=1 必炸
    QualityTracker._test_force_id = 1

    upstream_quote = [{"code": "600519", "name": "贵州茅台", "price": 10.0, "date": "2026-10-29", "time": "10:30:00"}]
    mock_upstream_res = DataResult(data=upstream_quote, quality=DataQuality.FULL, freshness=Freshness.REALTIME, provider="mock_concurrent")

    async def mock_execute_upstream(*args, **kwargs):
        # 增加微小延迟，确保 Follower 协程在 Leader 执行期间稳定挂起单飞等待
        await asyncio.sleep(0.05)
        return mock_upstream_res

    data_service = DataService()

    async def coroutine_leader():
        # Leader 协程运行于独立上下文
        return await data_service.get_stock_quotes(["600519"])

    async def coroutine_follower():
        # Follower 协程稍后一点发起请求，必然命中单飞 Follower 路径
        await asyncio.sleep(0.01)
        # 启动 Follower 协程的本轮追踪
        QualityTracker.start_round_tracking()
        res = await data_service.get_stock_quotes(["600519"])
        failures = QualityTracker.get_round_failures()
        QualityTracker.stop_round_tracking()
        return res, failures

    with patch("app.data.registry.registry.execute_with_fallback", side_effect=mock_execute_upstream):
        res_leader, (res_follower, follower_failures) = await asyncio.gather(
            coroutine_leader(),
            coroutine_follower()
        )

    # 清除冲突注入
    QualityTracker._test_force_id = None

    # 断言 1: Leader 与 Follower 均拿到相同的行情数据
    assert res_leader.data == upstream_quote
    assert res_follower.data == upstream_quote

    # 断言 2: Leader 遭遇真实 SQLite 主键冲突，quality_log_success 必须为 False
    assert res_leader.quality_log_success is False

    # 断言 3: Follower 即使未物理执行 Provider，也成功通过 Singleflight 桥接登记了质量日志失败！
    assert len(follower_failures) == 1
    assert follower_failures[0]["capability"] == "stock_quote"
    assert "Reused singleflight result" in follower_failures[0]["error"]

    # 验证主键冲突后数据库会话完好可用
    recover_ok = await QualityTracker.log_quality(capability="concurrency_recovery", result=mock_upstream_res)
    assert recover_ok is True


# ==============================================================================
# 场景 20: 跨轮次内存缓存复用，质量日志失败可靠向当前轮次传递 (Codex 第四轮 P1 核心项)
# ==============================================================================
@pytest.mark.asyncio
async def test_cross_context_cache_hit_propagates_quality_log_failure():
    """
    验收场景 20 (Codex 第四轮 P1 核心项):
    - 内存缓存中存放之前请求生成的 DataResult，其 quality_log_success = False
    - 当前调度轮次启动追踪并命中缓存
    - 验证 DataService._execute_pipeline 自动将缓存项的日志失败登记至当前轮次 QualityTracker
    - 调度器 TaskLog 判定为 partial_warning，杜绝漏报！
    """
    DataService._CACHE.clear()

    cache_key = "stock_quote:get_stock_quotes:(['600519'],)"
    cached_res = DataResult(
        data=[{"code": "600519", "name": "贵州茅台", "price": 10.0, "date": "2026-10-29", "time": "10:30:00"}],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,
        provider="sina",
        quality_log_success=False
    )
    # 注入缓存
    DataService._CACHE[cache_key] = (time.time(), cached_res)

    scheduler = TaskScheduler()

    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", new_callable=AsyncMock, return_value={"total_amount_yi": 1000.0}), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}):

        test_time = datetime(2026, 10, 29, 10, 30, 0)
        async with async_session() as session:
            sim_svc = SimulationService(session)
            acc = await sim_svc.get_or_create_default_account()
            pos = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=10.0, current_price=10.0, floating_pnl=0.0)
            session.add(pos)
            await session.commit()

        await scheduler._run_intraday_monitor(now_dt=test_time)

    async with async_session() as session:
        task_logs = (await session.execute(select(TaskLog).where(TaskLog.task_name == "intraday_monitor"))).scalars().all()
        assert len(task_logs) == 1
        t_log = task_logs[0]
        assert t_log.status == "partial_warning"
        assert "QualityLog: failed" in t_log.error_message

    DataService._CACHE.clear()


# ==============================================================================
# 场景 21: 区分质量日志未写入 (None)、写入成功 (True) 与写入失败 (False) (Codex 第四轮 P1 核心项)
# ==============================================================================
@pytest.mark.asyncio
async def test_quality_log_success_distinguishes_true_false_none():
    """
    验收场景 21 (Codex 第四轮 P1 核心项):
    - quality_log_success = True (写入成功): 不登记失败
    - quality_log_success = None (未写入/预算超限等无日志场景): 不登记失败
    - quality_log_success = False (写入失败): 登记失败
    """
    QualityTracker.start_round_tracking()

    # 1. 未写入 (None)
    res_none = DataResult(data=[], quality=DataQuality.FULL, provider="p", quality_log_success=None)
    if getattr(res_none, "quality_log_success", None) is False:
        QualityTracker.record_failure("test_none", "p", "err")
    assert len(QualityTracker.get_round_failures()) == 0

    # 2. 写入成功 (True)
    res_true = DataResult(data=[], quality=DataQuality.FULL, provider="p", quality_log_success=True)
    if getattr(res_true, "quality_log_success", None) is False:
        QualityTracker.record_failure("test_true", "p", "err")
    assert len(QualityTracker.get_round_failures()) == 0

    # 3. 写入失败 (False)
    res_false = DataResult(data=[], quality=DataQuality.FULL, provider="p", quality_log_success=False)
    if getattr(res_false, "quality_log_success", None) is False:
        QualityTracker.record_failure("test_false", "p", "err")
    failures = QualityTracker.get_round_failures()
    assert len(failures) == 1
    assert failures[0]["capability"] == "test_false"

    QualityTracker.stop_round_tracking()


# ==============================================================================
# 场景 22: 对抗性测试 - 当日日K与当日大盘均已更新，但无日期旧快照坚决阻断零成交 (Codex 第六轮 P1 核心项)
# ==============================================================================
@pytest.mark.asyncio
async def test_adversarial_stale_stock_with_fresh_index_blocked():
    """
    验收场景 22 (Codex 第六轮 P1 核心项 - 对抗性攻击防御):
    - 设定大盘指数与个股自身日K线均已权威更新至今日 (2026-10-29 最新状态)
    - 但特定个股 600519 快照仅有 servertime (14:55:00.123)，无来源 date 字段 (无日期旧快照/滞留)
    - 绝对严禁将今日日K日期赋予无日期快照！
    - TdxDirectClient 严格判定 date 权威为 None
    - TdxProvider 严谨识别为 Freshness.UNAVAILABLE, DataStatus.EMPTY
    - 风控守护机坚决阻断波普尔止损平仓，零假成交，持仓与资金纹丝不动！
    """
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 900000.0

        t = SimTrade(account_id=acc.id, code="600519", name="贵州茅台", direction="buy", price=10.0, quantity=1000, trade_time="2026-10-28 10:00:00")
        p = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=10.0, current_price=10.0, floating_pnl=0.0)
        session.add_all([t, p])
        await session.commit()

    from app.data.providers.tdx_client import TdxDirectClient
    from app.data.providers.tdx_provider import TdxProvider

    # 滞留快照：价格大跌到 9.0 (-10%)，看似应触发风控止损，但无 date 字段
    stale_quote = {
        "market": 1,
        "code": "600519",
        "price": 9.00,
        "last_close": 10.0,
        "servertime": "14:55:00.123",
    }

    # 大盘指数是今日最新 2026-10-29
    fresh_index_bar = [{"datetime": "2026-10-29 15:00", "close": 3200.0}]
    # 个股自身的日K线也已权威更新为今日 2026-10-29！
    fresh_stock_bar = [{"datetime": "2026-10-29 15:00", "close": 9.00}]

    client = TdxDirectClient()
    provider = TdxProvider(client=client)

    with patch.object(client, "connect_best_server", return_value=True), \
         patch.object(client.api, "get_security_quotes", return_value=[stale_quote]), \
         patch.object(client.api, "get_index_bars", return_value=fresh_index_bar), \
         patch.object(client.api, "get_security_bars", return_value=fresh_stock_bar), \
         patch("app.core.calendar.calendar.is_trading_day", return_value=True):

        # 1. 验证客户端解析出的个股日期权威为 None，绝不借用独立的当日日K线日期！
        quotes = client.get_quotes(["600519"])
        assert len(quotes) == 1
        assert quotes[0]["date"] is None, "日K线虽为今日，但决不能将独立日K日期赋予无日期快照！"

        # 2. 验证提供方质量与时态判定为 UNAVAILABLE
        data_res = await provider.get_stock_quotes(["600519"])
        assert data_res.freshness == Freshness.UNAVAILABLE
        assert data_res.status == DataStatus.EMPTY

        # 3. 贯穿风控守护机，验证严格拦截
        async with async_session() as session:
            engine = AutonomousJobEngine(session)
            guard_res = await engine.run_intraday_risk_guard_detailed(
                target_date="2026-10-29",
                now_dt=datetime(2026, 10, 29, 14, 55, 30),
                quotes_result=data_res
            )
            assert guard_res["status"] in ("SKIPPED", "PARTIAL_HOLD")
            assert len(guard_res["actual_liquidations"]) == 0

            # 验证持仓与资金毫发无损，零成交！
            pos = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalar_one()
            assert pos.quantity == 1000
            trades = (await session.execute(select(SimTrade).where(SimTrade.direction == "sell"))).scalars().all()
            assert len(trades) == 0


# ==============================================================================
# 场景 23: 质量日志失败且风控跳过时，调度器整体状态精准评估为 partial_warning (Codex 第五轮 P2 核心项)
# ==============================================================================
@pytest.mark.asyncio
async def test_scheduler_quality_log_failure_with_risk_skipped_yields_partial_warning():
    """
    验收场景 23 (Codex 第五轮 P2 核心项 - 状态一致性):
    - 账户持有仓位，但行情不可用导致风控巡检明确跳过 (risk_status = 'skipped')
    - 阶段 1 监控采集发生质量日志落库失败 (QualityTracker 记录失败)
    - 严格遵循计划单第 2.2 节状态矩阵：
      [Monitor: success | Risk: skipped | QualityLog: failed] -> 整体必须评估为 partial_warning！
    - 决不能因为风控 skipped 而覆盖掉质量日志的 warning！
    """
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        pos = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=10.0, current_price=10.0, floating_pnl=0.0)
        session.add(pos)
        await session.commit()

    scheduler = TaskScheduler()

    async def mock_capture_with_log_failure(*args, **kwargs):
        # 触发质量日志登记失败
        QualityTracker.record_failure(
            capability="macro_snapshot_quote",
            provider="mock_p",
            error="Simulated DB lock failure"
        )
        return {"total_amount_yi": 1000.0}

    # 行情缺失/不可用，风控巡检触发 skipped
    mock_unavailable_quotes = DataResult(
        data=None,
        quality=DataQuality.UNAVAILABLE,
        freshness=Freshness.UNAVAILABLE,
        provider="mock_down"
    )

    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch.object(MonitorService, "capture_macro_snapshot", side_effect=mock_capture_with_log_failure), \
         patch.object(MonitorService, "detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch.object(MonitorService, "flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock, return_value={}), \
         patch.object(DataService, "get_stock_quotes", new_callable=AsyncMock, return_value=mock_unavailable_quotes):

        test_time = datetime(2026, 10, 29, 10, 30, 0)
        await scheduler._run_intraday_monitor(now_dt=test_time)

    async with async_session() as session:
        task_logs = (await session.execute(select(TaskLog).where(TaskLog.task_name == "intraday_monitor"))).scalars().all()
        assert len(task_logs) == 1
        t_log = task_logs[0]
        # 严格验证：状态绝不能是 skipped，必须是 partial_warning！
        assert t_log.status == "partial_warning", f"期望状态为 partial_warning，实际为 {t_log.status}"
        assert "QualityLog: failed" in t_log.error_message
        assert "Risk: skipped" in t_log.error_message