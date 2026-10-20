import logging
import time
from datetime import datetime
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from ..core.calendar import calendar
from ..core.database import async_session
from ..models.system import TaskLog
from ..services.daily_review import DailyReviewService
from ..services.premarket import PremarketService
from ..services.auction import AuctionService
from ..services.monitor import MonitorService

logger = logging.getLogger(__name__)

class TaskScheduler:
    """定时任务调度器 (APScheduler AsyncIO)"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()

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
        # 08:30 盘前简报
        self.scheduler.add_job(
            self._run_premarket,
            "cron",
            hour=8,
            minute=30,
            id="premarket_briefing",
            misfire_grace_time=300
        )
        # 09:26 竞价观察
        self.scheduler.add_job(
            self._run_auction,
            "cron",
            hour=9,
            minute=26,
            id="auction_observation",
            misfire_grace_time=60
        )
        # 16:30 知见·收盘全景深度复盘 (盘后 16:30 自动生成与落库)
        self.scheduler.add_job(
            self._run_daily_review,
            "cron",
            hour=16,
            minute=30,
            id="daily_review",
            misfire_grace_time=600
        )
        # 盘中动态监控与异动感知 (最佳防封安全区间：每 180 秒采样一次，防止上游接口被识别封禁)
        self.scheduler.add_job(
            self._run_intraday_monitor,
            "interval",
            seconds=180,
            id="intraday_monitor",
            max_instances=1,
            coalesce=True
        )
        logger.info("TaskScheduler jobs configured.")

    def start(self):
        if not self.scheduler.running:
            self.setup()
            self.scheduler.start()
            logger.info("TaskScheduler started.")

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("TaskScheduler stopped.")

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
                # 严格按照 09:10-15:00 交易时钟维护长连接生命周期 (盘后自动断开)
                tdx_session_manager.ensure_connected()

                service = MonitorService(session)
                await service.capture_macro_snapshot(today_str)
                events = await service.detect_anomalies(today_str)
                await service.flush_async_queue()

                # 后台自主维护驾驶舱内存全景热快照，供前端随时秒开
                snapshot_svc = CockpitSnapshotService(session)
                await snapshot_svc.get_instant_snapshot(trade_date=today_str, force_refresh=True)

                logger.debug("Scheduled intraday snapshot, TDX session & cockpit warm-up completed.")
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            ev_cnt = len(events) if 'events' in locals() and events else 0
            await self._record_task_log(
                "intraday_monitor",
                trigger_time,
                "success",
                duration_ms,
                f"Anomalies detected: {ev_cnt}"
            )
        except Exception as e:
            duration_ms = int((time.perf_counter() - t_start) * 1000)
            logger.error(f"Scheduled intraday monitor error: {e}")
            await self._record_task_log("intraday_monitor", trigger_time, "failed", duration_ms, str(e))

task_scheduler = TaskScheduler()
