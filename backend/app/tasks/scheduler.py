import logging
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from ..core.calendar import calendar
from ..core.database import async_session
from ..models.system import TaskLog
from ..services.daily_review import DailyReviewService
from ..services.premarket import PremarketService
from ..services.auction import AuctionService
from ..services.monitor import MonitorService
from ..services.autonomous_executor import AutonomousJobEngine

logger = logging.getLogger(__name__)

class TaskScheduler:
    """
    全自动定时任务调度器 (APScheduler AsyncIO)
    严格执行全流程闭环交易时钟规范 (Spec 105)：
    - 08:30 盘前简报
    - 09:26 竞价观察 & 经典策略推演 (生成待撮合买单，进入 09:25~09:29:50 双轨否决缓冲窗口)
    - 09:30 开盘撮合成交 (真实滑点 0.1% 撮合未否决指令)
    - 09:30~15:00 盘中 180s 动态监控 & 波普尔刚性风控守护机 (-5% 止损、证伪离场)
    - 15:05 盘后净值对账与清算结算
    - 15:35 盘后无头原生增量数据同步 (方案 A: 自动补齐 Parquet 日线与涨停天梯底座)
    - 16:30 知见·收盘全景深度复盘
    """

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._pending_veto_orders: List[Dict[str, Any]] = []
        self._execution_history: List[Dict[str, Any]] = []

    @staticmethod
    async def _record_task_log(
        task_name: str,
        trigger_time: str,
        status: str,
        duration_ms: int = 0,
        error_message: Optional[str] = None
    ):
        """持久化定时任务执行状态到 TaskLog 审计表"""
        try:
            async with async_session() as session:
                log_entry = TaskLog(
                    task_name=task_name,
                    trigger_time=trigger_time,
                    status=status,
                    duration_ms=duration_ms,
                    error_message=error_message,
                )
                session.add(log_entry)
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to record TaskLog for {task_name}: {e}")

    def setup(self):
        # 1. 08:30 盘前简报
        self.scheduler.add_job(
            self._run_premarket,
            "cron",
            hour=8,
            minute=30,
            id="premarket_briefing",
            misfire_grace_time=300
        )
        # 2. 09:26 竞价观察
        self.scheduler.add_job(
            self._run_auction,
            "cron",
            hour=9,
            minute=26,
            id="auction_observation",
            misfire_grace_time=60
        )
        # 3. 09:26:05 早盘无人值守策略计算 (双轨否决预埋)
        self.scheduler.add_job(
            self._run_morning_strategy,
            "cron",
            hour=9,
            minute=26,
            second=5,
            id="autonomous_morning_strategy",
            misfire_grace_time=30
        )
        # 4. 09:30:00 开盘真实滑点撮合成交
        self.scheduler.add_job(
            self._run_market_open_execution,
            "cron",
            hour=9,
            minute=30,
            second=0,
            id="autonomous_market_open_execution",
            misfire_grace_time=30
        )
        # 5. 15:05:00 盘后净值对账与清算结算
        self.scheduler.add_job(
            self._run_post_market_settlement,
            "cron",
            hour=15,
            minute=5,
            second=0,
            id="autonomous_post_market_settlement",
            misfire_grace_time=300
        )
        # 6. 15:35:00 盘后原生增量行情同步 (方案 A)
        self.scheduler.add_job(
            self._run_incremental_sync,
            "cron",
            hour=15,
            minute=35,
            second=0,
            id="autonomous_incremental_sync",
            misfire_grace_time=600
        )
        # 7. 16:30 知见·收盘全景深度复盘
        self.scheduler.add_job(
            self._run_daily_review,
            "cron",
            hour=16,
            minute=30,
            id="daily_review",
            misfire_grace_time=600
        )
        # 8. 盘中动态监控与波普尔风控守护机 (每 180 秒一次)
        self.scheduler.add_job(
            self._run_intraday_monitor,
            "interval",
            seconds=180,
            id="intraday_monitor",
            max_instances=1,
            coalesce=True
        )
        logger.info("TaskScheduler jobs configured with autonomous quant closed loop.")

    def start(self):
        if not self.scheduler.running:
            self.setup()
            self.scheduler.start()
            logger.info("TaskScheduler started.")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("TaskScheduler stopped.")

    # =========================================================================
    # 双轨否决权限与状态查询
    # =========================================================================
    def get_autonomous_state(self) -> Dict[str, Any]:
        """获取当前无人值守调度器运行状态及待撮合指令列表"""
        now = datetime.now()
        cur_time_str = now.strftime("%H:%M:%S")
        is_veto_window = ("09:25:00" <= cur_time_str <= "09:29:50") and calendar.is_trading_day()

        return {
            "scheduler_running": self.scheduler.running if self.scheduler else False,
            "is_trading_day": calendar.is_trading_day(),
            "server_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "veto_window_active": is_veto_window,
            "veto_deadline": f"{now.strftime('%Y-%m-%d')} 09:29:50",
            "pending_orders": self._pending_veto_orders,
            "pending_orders_count": len(self._pending_veto_orders),
            "recent_executions": self._execution_history[-10:]
        }

    def veto_order(self, stock_code: str, reason: str = "Manual Trader Veto") -> bool:
        """
        在 09:25:00 ~ 09:29:50 双轨缓冲窗口内行使一票否决权
        """
        now = datetime.now()
        cur_time = now.time()
        # 严格校验是否在否决窗口内
        if cur_time.hour != 9 or cur_time.minute >= 30:
            logger.warning(f"一票否决失败：当前时间 {now.strftime('%H:%M:%S')} 已超出 09:29:50 缓冲窗口")
            return False

        clean_c = stock_code.strip()
        matched = False
        remaining = []
        for o in self._pending_veto_orders:
            if o.get("code") == clean_c:
                matched = True
                logger.info(f"🚫 [一票否决生效] 用户否决了标的买入: {o.get('name')} ({clean_c}) | 原因: {reason}")
                self._execution_history.append({
                    "action": "VETO",
                    "code": clean_c,
                    "name": o.get("name"),
                    "time": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "reason": reason
                })
            else:
                remaining.append(o)

        self._pending_veto_orders = remaining
        return matched

    # =========================================================================
    # 定时作业实现
    # =========================================================================
    async def _run_premarket(self):
        trigger_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not calendar.is_trading_day():
            logger.info("Non-trading day, skipping premarket briefing.")
            await self._record_task_log("premarket_briefing", trigger_time, "skipped", 0, "Non-trading day")
            return
        t_start = time.perf_counter()
        try:
            async with async_session() as session:
                service = PremarketService(session)
                await service.generate_briefing()
                logger.info("Scheduled premarket briefing completed.")
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            await self._record_task_log("premarket_briefing", trigger_time, "success", duration_ms)
        except Exception as e:
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            logger.error(f"Scheduled premarket briefing failed: {e}")
            await self._record_task_log("premarket_briefing", trigger_time, "failed", duration_ms, str(e))

    async def _run_auction(self):
        trigger_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not calendar.is_trading_day():
            await self._record_task_log("auction_observation", trigger_time, "skipped", 0, "Non-trading day")
            return
        t_start = time.perf_counter()
        try:
            async with async_session() as session:
                service = AuctionService(session)
                await service.generate_auction_report()
                logger.info("Scheduled auction observation completed.")
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            await self._record_task_log("auction_observation", trigger_time, "success", duration_ms)
        except Exception as e:
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            logger.error(f"Scheduled auction observation failed: {e}")
            await self._record_task_log("auction_observation", trigger_time, "failed", duration_ms, str(e))

    async def _run_morning_strategy(self):
        """09:26:05 触发竞价策略推演，生成待撮合订单并预埋进入缓冲队列"""
        trigger_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not calendar.is_trading_day():
            await self._record_task_log("morning_strategy", trigger_time, "skipped", 0, "Non-trading day")
            return
        t_start = time.perf_counter()
        try:
            async with async_session() as session:
                engine = AutonomousJobEngine(session)
                res = await engine.run_morning_strategy_pipeline()
                orders = res.get("orders", [])
                self._pending_veto_orders = orders
                logger.info(f"09:26 策略计算完成: 生成 {len(orders)} 笔预埋买单进入双轨缓冲队列")
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            await self._record_task_log("morning_strategy", trigger_time, "success", duration_ms, f"Generated {len(orders)} orders")
        except Exception as e:
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            logger.error(f"Scheduled morning strategy failed: {e}")
            await self._record_task_log("morning_strategy", trigger_time, "failed", duration_ms, str(e))

    async def _run_market_open_execution(self):
        """09:30:00 开盘撮合：对未被否决的订单以真实开盘价执行自动成交"""
        trigger_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not calendar.is_trading_day():
            await self._record_task_log("market_open_execution", trigger_time, "skipped", 0, "Non-trading day")
            return
        t_start = time.perf_counter()
        try:
            queued = list(self._pending_veto_orders)
            self._pending_veto_orders = [] # 撮合后立即清空缓冲
            async with async_session() as session:
                engine = AutonomousJobEngine(session)
                executed = await engine.execute_open_market_match(queued)
                for tr in executed:
                    self._execution_history.append({
                        "action": "BUY_FILLED",
                        "code": tr.get("code"),
                        "name": tr.get("name"),
                        "price": tr.get("match_price"),
                        "quantity": tr.get("quantity"),
                        "time": trigger_time
                    })
                logger.info(f"09:30 开盘撮合完成: 实际成交 {len(executed)} 笔")
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            await self._record_task_log("market_open_execution", trigger_time, "success", duration_ms, f"Executed {len(executed)} trades")
        except Exception as e:
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            logger.error(f"Scheduled open execution failed: {e}")
            await self._record_task_log("market_open_execution", trigger_time, "failed", duration_ms, str(e))

    async def _run_post_market_settlement(self):
        """15:05:00 收盘清算与资产核算"""
        trigger_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not calendar.is_trading_day():
            await self._record_task_log("post_market_settlement", trigger_time, "skipped", 0, "Non-trading day")
            return
        t_start = time.perf_counter()
        try:
            async with async_session() as session:
                engine = AutonomousJobEngine(session)
                res = await engine.run_post_market_settlement()
                logger.info(f"15:05 收盘结算完成: 资产规模 ￥{res.get('total_asset', 0):,.2f}")
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            await self._record_task_log("post_market_settlement", trigger_time, "success", duration_ms, f"Total Asset: {res.get('total_asset')}")
        except Exception as e:
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            logger.error(f"Scheduled settlement failed: {e}")
            await self._record_task_log("post_market_settlement", trigger_time, "failed", duration_ms, str(e))

    async def _run_incremental_sync(self):
        """15:35:00 方案 A 增量行情自给同步 (无头直接落盘 Parquet)"""
        trigger_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not calendar.is_trading_day():
            await self._record_task_log("incremental_sync", trigger_time, "skipped", 0, "Non-trading day")
            return
        t_start = time.perf_counter()
        try:
            from ..services.incremental_sync import incremental_sync_pipeline
            res = await incremental_sync_pipeline()
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            await self._record_task_log("incremental_sync", trigger_time, "success", duration_ms, f"Synced: {res.get('synced_count', 0)}")
            logger.info(f"15:35 增量数据自给同步完成: 记录数 {res.get('synced_count', 0)}")
        except Exception as e:
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            logger.error(f"Scheduled incremental sync failed: {e}")
            await self._record_task_log("incremental_sync", trigger_time, "failed", duration_ms, str(e))

    async def _run_daily_review(self):
        trigger_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not calendar.is_trading_day():
            logger.info("Non-trading day, skipping daily review.")
            await self._record_task_log("daily_review", trigger_time, "skipped", 0, "Non-trading day")
            return
        t_start = time.perf_counter()
        try:
            async with async_session() as session:
                service = DailyReviewService(session)
                await service.generate_review()
                logger.info("Scheduled daily review completed.")
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            await self._record_task_log("daily_review", trigger_time, "success", duration_ms)
        except Exception as e:
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            logger.error(f"Scheduled daily review failed: {e}")
            await self._record_task_log("daily_review", trigger_time, "failed", duration_ms, str(e))

    async def _run_intraday_monitor(self):
        trigger_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not calendar.is_trading_day():
            return
        state = MonitorService.get_trading_session_state()
        if state != "ACTIVE":
            return
        t_start = time.perf_counter()
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            async with async_session() as session:
                from ..data.providers.tdx_session_manager import tdx_session_manager
                from ..services.cockpit_snapshot_service import CockpitSnapshotService
                # 严格按照 09:10-15:00 交易时钟维护长连接生命周期
                tdx_session_manager.ensure_connected()

                service = MonitorService(session)
                await service.capture_macro_snapshot(today_str)
                events = await service.detect_anomalies(today_str)
                await service.flush_async_queue()

                # 后台自主维护驾驶舱内存全景热快照
                snapshot_svc = CockpitSnapshotService(session)
                await snapshot_svc.get_instant_snapshot(trade_date=today_str, force_refresh=True)

                # 嵌入波普尔刚性风控守护机 (-5% 止损、证伪离场巡检)
                auto_engine = AutonomousJobEngine(session)
                risk_liquidations = await auto_engine.run_intraday_risk_guard()
                for liq in risk_liquidations:
                    self._execution_history.append({
                        "action": "RISK_LIQUIDATION",
                        "code": liq.get("code"),
                        "name": liq.get("name"),
                        "price": liq.get("sell_price"),
                        "quantity": liq.get("quantity"),
                        "reason": liq.get("reason"),
                        "time": trigger_time
                    })

                logger.debug("Scheduled intraday snapshot & popper risk guard completed.")
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            ev_cnt = len(events) if 'events' in locals() and events else 0
            await self._record_task_log(
                "intraday_monitor",
                trigger_time,
                "success",
                duration_ms,
                f"Anomalies: {ev_cnt}, Liquidations: {len(risk_liquidations) if 'risk_liquidations' in locals() else 0}"
            )
        except Exception as e:
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            logger.error(f"Scheduled intraday monitor error: {e}")
            await self._record_task_log("intraday_monitor", trigger_time, "failed", duration_ms, str(e))

task_scheduler = TaskScheduler()
