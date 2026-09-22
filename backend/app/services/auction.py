import json
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..data.service import DataService
from ..models.report import AuctionReport

class AuctionService:
    """竞价观察服务 (M4)"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.data_service = DataService(session)

    async def generate_auction_report(self, date_str: Optional[str] = None) -> AuctionReport:
        today = date_str or datetime.now().strftime("%Y-%m-%d")

        # 9:25 开盘指数数据
        indices = ["s_sh000001", "s_sz399001", "s_sz399006"]
        res = await self.data_service.get_index_quotes(indices)
        index_data = res.data or []

        stmt = select(AuctionReport).where(AuctionReport.date == today)
        existing = (await self.session.execute(stmt)).scalars().first()

        if existing:
            existing.index_open_data = json.dumps(index_data, ensure_ascii=False)
            existing.emotion_judgment = "竞价平开，符合预期"
            record = existing
        else:
            record = AuctionReport(
                date=today,
                index_open_data=json.dumps(index_data, ensure_ascii=False),
                one_word_count=0,
                high_open_stats=json.dumps({}, ensure_ascii=False),
                emotion_judgment="竞价平开，符合预期"
            )
            self.session.add(record)

        await self.session.commit()
        await self.session.refresh(record)
        return record
