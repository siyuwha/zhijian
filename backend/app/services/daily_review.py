import json
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from ..core.calendar import calendar
from ..data.service import DataService
from ..cognition.market_state import market_state_computer
from ..cognition.interfaces import CognitionInput
from ..models.report import DailyReview
from ..models.cognition import CognitionMarketState
from ..models.market import MarketDailySnapshot

logger = logging.getLogger(__name__)

class DailyReviewService:
    """收盘复盘报告业务编排服务 (M1)"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.data_service = DataService(session)

    async def generate_review(self, date_str: Optional[str] = None, force: bool = False) -> DailyReview:
        today = date_str or datetime.now().strftime("%Y-%m-%d")

        if not force and not calendar.is_trading_day(today):
            logger.warning(f"Attempted to generate daily review on non-trading day: {today}")
            raise HTTPException(
                status_code=400,
                detail=f"{today} 为非交易日（周末/法定节假日休市），系统禁止生成收盘复盘。"
            )

        # 检查是否已存在历史离线物理快照 (用于离线重放与自愈)
        snap_stmt = select(MarketDailySnapshot).where(
            MarketDailySnapshot.date == today,
            MarketDailySnapshot.snapshot_type == "EOD_CLOSE"
        )
        existing_snapshot = (await self.session.execute(snap_stmt)).scalars().first()

        # 1. 采集主要指数数据 (D1 / D6)
        indices = ["s_sh000001", "s_sz399001", "s_sz399006", "s_sh000688"]
        index_res = await self.data_service.get_index_quotes(indices)
        index_data = index_res.data or []

        # 离线自愈判定：若外部数据源返回空且本地存在历史快照，则自愈加载物理事实
        if not index_data and existing_snapshot and existing_snapshot.indices_snapshot:
            try:
                index_data = json.loads(existing_snapshot.indices_snapshot)
                logger.info(f"Self-healed index observation from MarketDailySnapshot for {today}")
            except Exception:
                pass

        # 2. 采集涨停池与情绪数据 (D2 / D3)
        limit_up_res = await self.data_service.get_limit_up_pool(today)
        limit_up_summary = limit_up_res.data or {}
        if not limit_up_summary and existing_snapshot and existing_snapshot.limit_up_snapshot:
            try:
                limit_up_summary = json.loads(existing_snapshot.limit_up_snapshot)
                logger.info(f"Self-healed limit up observation from MarketDailySnapshot for {today}")
            except Exception:
                pass

        # 3. 采集全市场广度 (D2)
        breadth_res = await self.data_service.get_market_breadth()
        breadth_data = breadth_res.data or {}
        if not breadth_data and existing_snapshot and existing_snapshot.breadth_snapshot:
            try:
                breadth_data = json.loads(existing_snapshot.breadth_snapshot)
                logger.info(f"Self-healed market breadth observation from MarketDailySnapshot for {today}")
            except Exception:
                pass

        # 4. 采集微盘股风格代理数据 (D4)
        micro_res = await self.data_service.get_micro_cap_quote()
        micro_data = micro_res.data or {}
        if not micro_data and existing_snapshot and existing_snapshot.micro_cap_snapshot:
            try:
                micro_data = json.loads(existing_snapshot.micro_cap_snapshot)
            except Exception:
                pass

        # 5. 采集外部风险与A50 (D5)
        ext_res = await self.data_service.get_external_risk()
        ext_data = ext_res.data or {}
        if not ext_data and existing_snapshot and existing_snapshot.external_risk_snapshot:
            try:
                ext_data = json.loads(existing_snapshot.external_risk_snapshot)
            except Exception:
                pass

        # 6. 采集高位股/连板承接表现 (D3)
        high_tier_res = await self.data_service.get_high_tier_performance()
        high_tier_data = high_tier_res.data or {}
        if not high_tier_data and existing_snapshot and existing_snapshot.high_tier_snapshot:
            try:
                high_tier_data = json.loads(existing_snapshot.high_tier_snapshot)
            except Exception:
                pass

        # 7. 查找前一交易日复盘记录（提取昨日成交额与昨日涨停数，用于环比量能与连板晋级率）
        prev_stmt = select(DailyReview).where(DailyReview.date < today).order_by(DailyReview.date.desc()).limit(1)
        prev_review = (await self.session.execute(prev_stmt)).scalars().first()
        prev_total_amount = None
        prev_limit_up_count = None
        if prev_review and prev_review.market_overview:
            try:
                prev_indices = json.loads(prev_review.market_overview)
                prev_total_amount = sum(float(idx.get("amount_wan", 0)) for idx in prev_indices) / 10000.0
            except Exception:
                pass
        if prev_review and prev_review.limit_up_analysis:
            try:
                prev_lu = json.loads(prev_review.limit_up_analysis)
                prev_limit_up_count = prev_lu.get("total_count")
            except Exception:
                pass

        # 8. 组织多维度原始快照数据
        raw_market_snapshot = {
            "indices": index_data,
            "limit_up": limit_up_summary,
            "breadth": breadth_data,
            "micro_cap": micro_data,
            "external_risk": ext_data,
            "high_tier": high_tier_data,
            "prev_total_amount": prev_total_amount,
            "prev_limit_up_count": prev_limit_up_count,
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

        # 9. 持久化底层物理快照表 MarketDailySnapshot (P1-3 盘后离线快照与自愈机制)
        snap_stmt = select(MarketDailySnapshot).where(
            MarketDailySnapshot.date == today,
            MarketDailySnapshot.snapshot_type == "EOD_CLOSE"
        )
        existing_snapshot = (await self.session.execute(snap_stmt)).scalars().first()

        source_status_dict = {
            "indices": str(getattr(index_res, "status", "UNKNOWN")),
            "limit_up": str(getattr(limit_up_res, "status", "UNKNOWN")),
            "breadth": str(getattr(breadth_res, "status", "UNKNOWN")),
            "micro_cap": str(getattr(micro_res, "status", "UNKNOWN")),
            "external_risk": str(getattr(ext_res, "status", "UNKNOWN")),
            "high_tier": str(getattr(high_tier_res, "status", "UNKNOWN")),
        }

        if existing_snapshot:
            existing_snapshot.indices_snapshot = json.dumps(index_data, ensure_ascii=False)
            existing_snapshot.breadth_snapshot = json.dumps(breadth_data, ensure_ascii=False)
            existing_snapshot.limit_up_snapshot = json.dumps(limit_up_summary, ensure_ascii=False)
            existing_snapshot.micro_cap_snapshot = json.dumps(micro_data, ensure_ascii=False)
            existing_snapshot.external_risk_snapshot = json.dumps(ext_data, ensure_ascii=False)
            existing_snapshot.high_tier_snapshot = json.dumps(high_tier_data, ensure_ascii=False)
            existing_snapshot.market_state_snapshot = json.dumps(dimensions_dump, ensure_ascii=False)
            existing_snapshot.data_quality = market_state.data_quality.value
            existing_snapshot.source_status = json.dumps(source_status_dict, ensure_ascii=False)
        else:
            daily_snapshot = MarketDailySnapshot(
                date=today,
                snapshot_type="EOD_CLOSE",
                indices_snapshot=json.dumps(index_data, ensure_ascii=False),
                breadth_snapshot=json.dumps(breadth_data, ensure_ascii=False),
                limit_up_snapshot=json.dumps(limit_up_summary, ensure_ascii=False),
                micro_cap_snapshot=json.dumps(micro_data, ensure_ascii=False),
                external_risk_snapshot=json.dumps(ext_data, ensure_ascii=False),
                high_tier_snapshot=json.dumps(high_tier_data, ensure_ascii=False),
                market_state_snapshot=json.dumps(dimensions_dump, ensure_ascii=False),
                data_quality=market_state.data_quality.value,
                source_status=json.dumps(source_status_dict, ensure_ascii=False),
            )
            self.session.add(daily_snapshot)

        # 10. 生成并持久化 DailyReview 报告
        review_data = {
            "title": f"{today} A股收盘认知复盘",
            "indices": index_data,
            "limit_up": limit_up_summary,
            "breadth": breadth_data,
            "micro_cap": micro_data,
            "external_risk": ext_data,
            "high_tier": high_tier_data,
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

        sector_summary = json.dumps(limit_up_summary.get("top_reasons", []), ensure_ascii=False) if isinstance(limit_up_summary, dict) else None

        if existing:
            existing.market_overview = json.dumps(index_data, ensure_ascii=False)
            existing.limit_up_analysis = json.dumps(limit_up_summary, ensure_ascii=False)
            existing.sector_analysis = sector_summary
            existing.market_state_id = cog_record.id
            existing.report_content = json.dumps(review_data, ensure_ascii=False)
            existing.data_quality = market_state.data_quality.value
            review_record = existing
        else:
            review_record = DailyReview(
                date=today,
                market_overview=json.dumps(index_data, ensure_ascii=False),
                limit_up_analysis=json.dumps(limit_up_summary, ensure_ascii=False),
                sector_analysis=sector_summary,
                market_state_id=cog_record.id,
                report_content=json.dumps(review_data, ensure_ascii=False),
                data_quality=market_state.data_quality.value
            )
            self.session.add(review_record)

        await self.session.commit()
        await self.session.refresh(review_record)

        # 11. 最小认知桥梁 (Minimal Cognition Bridge): 自动接入 Phase 2A 不可变认知账本
        try:
            from ..cognition.bridge import CognitionBridge
            target_snapshot = existing_snapshot if existing_snapshot else daily_snapshot
            bridge = CognitionBridge(self.session)
            await bridge.record_daily_review(today, target_snapshot, review_record)
        except Exception as e:
            logger.error(f"Minimal Cognition Bridge recording error for {today}: {e}")

        return review_record

    async def get_review_by_date(self, date_str: str) -> Optional[DailyReview]:
        stmt = select(DailyReview).where(DailyReview.date == date_str)
        return (await self.session.execute(stmt)).scalars().first()

    async def get_reviews(self, limit: int = 30, offset: int = 0):
        """获取历史复盘列表（分页与概览元数据）"""
        count_stmt = select(func.count(DailyReview.id))
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = select(DailyReview).order_by(DailyReview.date.desc()).offset(offset).limit(limit)
        records = (await self.session.execute(stmt)).scalars().all()

        items = []
        for r in records:
            state_label = None
            composite_score = None
            if r.report_content:
                try:
                    c = json.loads(r.report_content)
                    ms = c.get("market_state", {})
                    state_label = ms.get("state_label")
                    composite_score = ms.get("composite_score")
                except Exception:
                    pass

            items.append({
                "id": r.id,
                "date": r.date,
                "state_label": state_label or "未定义",
                "composite_score": composite_score,
                "data_quality": r.data_quality or "unknown",
                "generated_at": r.generated_at.isoformat() if r.generated_at else None
            })

        return items, total
