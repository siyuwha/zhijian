import json
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..data.service import DataService
from ..cognition.market_state import market_state_computer
from ..cognition.interfaces import CognitionInput
from ..models.report import DailyReview
from ..models.cognition import CognitionMarketState

logger = logging.getLogger(__name__)

class DailyReviewService:
    """收盘复盘报告业务编排服务 (M1)"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.data_service = DataService(session)

    async def generate_review(self, date_str: Optional[str] = None) -> DailyReview:
        today = date_str or datetime.now().strftime("%Y-%m-%d")

        # 1. 采集主要指数数据 (D1 / D6)
        indices = ["s_sh000001", "s_sz399001", "s_sz399006", "s_sh000688"]
        index_res = await self.data_service.get_index_quotes(indices)
        index_data = index_res.data or []

        # 2. 采集涨停池与情绪数据 (D2 / D3)
        limit_up_res = await self.data_service.get_limit_up_pool(today)
        limit_up_summary = limit_up_res.data or {}

        # 3. 采集全市场广度 (D2)
        breadth_res = await self.data_service.get_market_breadth()
        breadth_data = breadth_res.data or {}

        # 4. 采集微盘股风格代理数据 (D4)
        micro_res = await self.data_service.get_micro_cap_quote()
        micro_data = micro_res.data or {}

        # 5. 采集外部风险与A50 (D5)
        ext_res = await self.data_service.get_external_risk()
        ext_data = ext_res.data or {}

        # 6. 组织多维度原始快照数据
        raw_market_snapshot = {
            "indices": index_data,
            "limit_up": limit_up_summary,
            "breadth": breadth_data,
            "micro_cap": micro_data,
            "external_risk": ext_data,
        }

        # 7. 调用 Cognition Layer 接口计算结构化分层 Market State (M1.4 V1)
        cog_input = CognitionInput(market_data=raw_market_snapshot)
        market_state = await market_state_computer.compute_market_state(cog_input)

        dimensions_dump = {
            dim_id: dim_state.model_dump()
            for dim_id, dim_state in market_state.dimensions.items()
        }

        # 8. 持久化 CognitionMarketState 快照
        cog_record = CognitionMarketState(
            date=today,
            timestamp=datetime.now().isoformat(),
            indicators=json.dumps(dimensions_dump, ensure_ascii=False),
            composite_score=market_state.composite_score,
            state_label=market_state.state_label,
            config_snapshot=json.dumps(market_state_computer.config.model_dump(), ensure_ascii=False),
            data_quality=market_state.data_quality.value
        )
        self.session.add(cog_record)
        await self.session.flush()

        # 9. 生成并持久化 DailyReview 报告
        review_data = {
            "title": f"{today} A股收盘认知复盘",
            "indices": index_data,
            "limit_up": limit_up_summary,
            "market_state": {
                "composite_score": market_state.composite_score,
                "state_label": market_state.state_label,
                "data_quality": market_state.data_quality.value,
                "dimensions": dimensions_dump,
                "missing_metrics": market_state.missing_metrics
            }
        }

        # 检查是否已存在当日复盘
        stmt = select(DailyReview).where(DailyReview.date == today)
        existing = (await self.session.execute(stmt)).scalars().first()

        if existing:
            existing.market_overview = json.dumps(index_data, ensure_ascii=False)
            existing.limit_up_analysis = json.dumps(limit_up_summary, ensure_ascii=False)
            existing.market_state_id = cog_record.id
            existing.report_content = json.dumps(review_data, ensure_ascii=False)
            existing.data_quality = market_state.data_quality.value
            review_record = existing
        else:
            review_record = DailyReview(
                date=today,
                market_overview=json.dumps(index_data, ensure_ascii=False),
                limit_up_analysis=json.dumps(limit_up_summary, ensure_ascii=False),
                market_state_id=cog_record.id,
                report_content=json.dumps(review_data, ensure_ascii=False),
                data_quality=market_state.data_quality.value
            )
            self.session.add(review_record)

        await self.session.commit()
        await self.session.refresh(review_record)
        return review_record

    async def get_review_by_date(self, date_str: str) -> Optional[DailyReview]:
        stmt = select(DailyReview).where(DailyReview.date == date_str)
        return (await self.session.execute(stmt)).scalars().first()
