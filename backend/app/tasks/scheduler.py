import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from ..core.calendar import calendar
from ..core.database import async_session
from ..services.daily_review import DailyReviewService
from ..services.premarket import PremarketService
from ..services.auction import AuctionService

logger = logging.getLogger(__name__)

class TaskScheduler:
    """定时任务调度器 (APScheduler AsyncIO)"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()

    def setup(self):
        # 08:00 盘前简报
        self.scheduler.add_job(
            self._run_premarket,
            "cron",
            hour=8,
            minute=0,
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
        # 15:35 收盘复盘
        self.scheduler.add_job(
            self._run_daily_review,
            "cron",
            hour=15,
            minute=35,
            id="daily_review",
            misfire_grace_time=300
        )
        logger.info("TaskScheduler jobs configured.")

    def start(self):
        self.setup()
        self.scheduler.start()
        logger.info("TaskScheduler started.")

    def shutdown(self):
        self.scheduler.shutdown()
        logger.info("TaskScheduler stopped.")

    async def _run_premarket(self):
        if not calendar.is_trading_day():
            logger.info("Non-trading day, skipping premarket briefing.")
            return
        async with async_session() as session:
            service = PremarketService(session)
            await service.generate_briefing()
            logger.info("Scheduled premarket briefing completed.")

    async def _run_auction(self):
        if not calendar.is_trading_day():
            return
        async with async_session() as session:
            service = AuctionService(session)
            await service.generate_auction_report()
            logger.info("Scheduled auction observation completed.")

    async def _run_daily_review(self):
        if not calendar.is_trading_day():
            logger.info("Non-trading day, skipping daily review.")
            return
        async with async_session() as session:
            service = DailyReviewService(session)
            await service.generate_review()
            logger.info("Scheduled daily review completed.")

task_scheduler = TaskScheduler()
