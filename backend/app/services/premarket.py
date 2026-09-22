import json
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..data.service import DataService
from ..models.report import PremarketBriefing, DailyReview
from ..core.calendar import calendar

logger = logging.getLogger(__name__)

class PremarketService:
    """盘前简报业务编排服务 (M2)"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.data_service = DataService(session)

    async def generate_briefing(self, date_str: Optional[str] = None) -> PremarketBriefing:
        today = date_str or datetime.now().strftime("%Y-%m-%d")

        # 1. 获取隔夜外盘
        overnight_res = await self.data_service.get_overnight_data()
        overnight_data = overnight_res.data or []

        # 2. 获取盘前最新财经快讯
        news_res = await self.data_service.get_latest_news(count=10)
        news_data = news_res.data or []

        # 3. 关联上一交易日复盘摘要
        prev_day = calendar.prev_trading_day(today).strftime("%Y-%m-%d")
        stmt = select(DailyReview).where(DailyReview.date == prev_day)
        prev_review = (await self.session.execute(stmt)).scalars().first()
        prev_summary = "前一交易日复盘结论：市场结构轮动，主线持续观察中。"
        if prev_review and prev_review.report_content:
            try:
                prev_json = json.loads(prev_review.report_content)
                state = prev_json.get("market_state", {})
                prev_summary = f"前日市场状态：{state.get('state_label')} (情绪得分: {state.get('composite_score')})"
            except Exception:
                pass

        # 4. 今日关注重点
        today_focus = [
            "关注集合竞价开盘大盘指数与成交量能否放大",
            "观察昨日连板高标标的溢价情况",
            "留意隔夜外盘波动映射之题材分支",
        ]

        stmt = select(PremarketBriefing).where(PremarketBriefing.date == today)
        existing = (await self.session.execute(stmt)).scalars().first()

        if existing:
            existing.overnight_summary = json.dumps(overnight_data, ensure_ascii=False)
            existing.news_digest = json.dumps(news_data, ensure_ascii=False)
            existing.yesterday_review_summary = prev_summary
            existing.today_focus = json.dumps(today_focus, ensure_ascii=False)
            briefing_record = existing
        else:
            briefing_record = PremarketBriefing(
                date=today,
                overnight_summary=json.dumps(overnight_data, ensure_ascii=False),
                news_digest=json.dumps(news_data, ensure_ascii=False),
                yesterday_review_summary=prev_summary,
                today_focus=json.dumps(today_focus, ensure_ascii=False),
            )
            self.session.add(briefing_record)

        await self.session.commit()
        await self.session.refresh(briefing_record)
        return briefing_record

    async def get_briefing_by_date(self, date_str: str) -> Optional[PremarketBriefing]:
        stmt = select(PremarketBriefing).where(PremarketBriefing.date == date_str)
        return (await self.session.execute(stmt)).scalars().first()
