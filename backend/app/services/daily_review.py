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
from ..data.capabilities import DataQuality
from ..core.market_heartbeat import MarketHeartbeatDetector, MarketHeartbeatResult
from ..models.report import DailyReview
from ..models.cognition import CognitionMarketState
from ..models.market import MarketDailySnapshot

logger = logging.getLogger(__name__)

class DailyReviewService:
    """收盘复盘报告业务编排服务 (M1)"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.data_service = DataService(session)
        self.last_heartbeat: Optional[MarketHeartbeatResult] = None

    async def generate_review(self, date_str: Optional[str] = None, force: bool = False) -> Optional[DailyReview]:
        today = date_str or datetime.now().strftime("%Y-%m-%d")

        # 检查是否已存在历史离线物理快照 (用于离线重放与自愈)
        snap_stmt = select(MarketDailySnapshot).where(
            MarketDailySnapshot.date == today,
            MarketDailySnapshot.snapshot_type == "EOD_CLOSE"
        )
        existing_snapshot = (await self.session.execute(snap_stmt)).scalars().first()

        # 1. 采集主要指数数据 (D1 / D6)
        indices = ["s_sh000001", "s_sz399001", "s_sz399006", "s_sh000688"]
        index_res = await self.data_service.get_index_quotes(indices)

        # 严肃真实错误守卫：绝不掩盖网络/上游服务真实故障！
        if index_res.quality == DataQuality.FAILED and not existing_snapshot:
            logger.error(f"行情数据源通信异常: {index_res.error_message}")
            raise HTTPException(
                status_code=502,
                detail=f"行情数据源通信异常: {index_res.error_message or '无法获取核心大盘指数行情'}"
            )

        is_today = (datetime.now().strftime("%Y-%m-%d") == today)
        if not is_today and existing_snapshot and existing_snapshot.indices_snapshot:
            try:
                index_data = json.loads(existing_snapshot.indices_snapshot)
                logger.info(f"Loaded index observation from MarketDailySnapshot for replay/historical date {today}")
            except Exception:
                index_data = index_res.data or []
        else:
            index_data = index_res.data or []
            if not index_data and existing_snapshot and existing_snapshot.indices_snapshot:
                try:
                    index_data = json.loads(existing_snapshot.indices_snapshot)
                    logger.info(f"Self-healed index observation from MarketDailySnapshot for {today}")
                except Exception:
                    pass

        # 2. 采集涨停池与情绪数据 (D2 / D3)
        limit_up_res = await self.data_service.get_limit_up_pool(today)
        if not is_today and existing_snapshot and existing_snapshot.limit_up_snapshot:
            try:
                limit_up_summary = json.loads(existing_snapshot.limit_up_snapshot)
            except Exception:
                limit_up_summary = limit_up_res.data or {}
        else:
            limit_up_summary = limit_up_res.data or {}
            if not limit_up_summary and existing_snapshot and existing_snapshot.limit_up_snapshot:
                try:
                    limit_up_summary = json.loads(existing_snapshot.limit_up_snapshot)
                    logger.info(f"Self-healed limit up observation from MarketDailySnapshot for {today}")
                except Exception:
                    pass

        # 3. 采集全市场广度 (D2)
        breadth_res = await self.data_service.get_market_breadth()
        if not is_today and existing_snapshot and existing_snapshot.breadth_snapshot:
            try:
                breadth_data = json.loads(existing_snapshot.breadth_snapshot)
            except Exception:
                breadth_data = breadth_res.data or {}
        else:
            breadth_data = breadth_res.data or {}
            if not breadth_data and existing_snapshot and existing_snapshot.breadth_snapshot:
                try:
                    breadth_data = json.loads(existing_snapshot.breadth_snapshot)
                    logger.info(f"Self-healed market breadth observation from MarketDailySnapshot for {today}")
                except Exception:
                    pass

        # 4. 获取数据库中最近一个有效交易日的归档收盘快照（作为前日镜像比对基准）
        prev_stmt = (
            select(DailyReview)
            .where(DailyReview.date < today)
            .order_by(DailyReview.date.desc())
            .limit(5)
        )
        prev_candidates = (await self.session.execute(prev_stmt)).scalars().all()
        prev_review = next((r for r in prev_candidates if calendar.is_trading_day(r.date)), None)
        prev_indices = []
        prev_date = None
        if prev_review:
            prev_date = prev_review.date
            if prev_review.market_overview:
                try:
                    prev_indices = json.loads(prev_review.market_overview)
                except Exception:
                    pass

        # 5. 物理事实心跳动态确权 (Market Heartbeat Dynamic Detection)
        # 场景二优先（前日收盘绝对镜像），场景一兜底（量能与极端博弈归零）
        heartbeat = MarketHeartbeatDetector.detect(
            indices=index_data,
            limit_up=limit_up_summary,
            breadth=breadth_data,
            prev_indices=prev_indices,
            prev_date=prev_date,
            target_date=today,
        )
        self.last_heartbeat = heartbeat

        # 若未开启强制模式且物理确权为休市状态：不报错误警报，正常返回 None（不污染历史数据库）
        if not force and not heartbeat.is_active_trading_day:
            reason_str = "；".join(heartbeat.reasons)
            logger.info(
                f"Market heartbeat confirmed non-trading day/closed for {today}: {reason_str}"
            )
            return None

        # 6. 若物理确权为真实交易日，继续采集微盘股、外部风险与高标表现
        # 6.1 采集微盘股风格代理数据 (D4)
        micro_res = await self.data_service.get_micro_cap_quote()
        micro_data = micro_res.data or {}
        if not micro_data and existing_snapshot and existing_snapshot.micro_cap_snapshot:
            try:
                micro_data = json.loads(existing_snapshot.micro_cap_snapshot)
            except Exception:
                pass

        # 6.2 采集外部风险与A50 (D5)
        ext_res = await self.data_service.get_external_risk()
        ext_data = ext_res.data or {}
        if not ext_data and existing_snapshot and existing_snapshot.external_risk_snapshot:
            try:
                ext_data = json.loads(existing_snapshot.external_risk_snapshot)
            except Exception:
                pass

        # 6.3 采集高位股/连板承接表现 (D3)
        high_tier_res = await self.data_service.get_high_tier_performance()
        high_tier_data = high_tier_res.data or {}
        if not high_tier_data and existing_snapshot and existing_snapshot.high_tier_snapshot:
            try:
                high_tier_data = json.loads(existing_snapshot.high_tier_snapshot)
            except Exception:
                pass

        # 7. 查找前一交易日复盘记录（提取昨日成交额与昨日涨停数，用于环比量能与连板晋级率）
        # 严格通过交易日历追溯前一有效交易日，杜绝非交易日（周末/假期）历史扰动
        prev_trade_date = calendar.prev_trading_day(today).strftime("%Y-%m-%d")
        prev_stmt = (
            select(DailyReview)
            .where(DailyReview.date <= prev_trade_date)
            .order_by(DailyReview.date.desc())
            .limit(10)
        )
        prev_candidates = (await self.session.execute(prev_stmt)).scalars().all()
        prev_review = next((r for r in prev_candidates if calendar.is_trading_day(r.date)), None)
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
