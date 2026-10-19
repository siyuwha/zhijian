# -*- coding: utf-8 -*-
"""
驾驶舱全局极速快照服务 (Cockpit Snapshot Service)
专为解决“前端打开白屏/卡顿/重复请求”与“后端脱离前端独立后台维持全景热快照”设计：
1. 09:10 - 15:00 交易窗口内，后端在后台自主维护常驻内存热快照 (In-Memory Hot Snapshot)
2. 提供统一的秒开单端点 /api/v1/canonical/instant-snapshot，前端 0.05 秒直出全屏数据
3. 盘后或非交易日，无缝读取最近交易日真实快照与复盘，杜绝一切伪造数据
"""

import asyncio
import logging
import time
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.calendar import calendar
from ..data.service import DataService
from ..data.providers.tdx_session_manager import tdx_session_manager
from ..services.canonical_market_service import CanonicalMarketService
from ..services.canonical_intraday_service import CanonicalIntradayService
from ..services.canonical_auction_service import CanonicalAuctionService
from ..services.intraday_briefing_service import IntradayBriefingService
from ..services.narrative_context_service import NarrativeContextExtractor
from ..services.constrained_briefing_generator import ConstrainedBriefingGenerator
from ..models.market import MarketDailySnapshot

logger = logging.getLogger(__name__)

class CockpitSnapshotService:
    """驾驶舱内存热快照中心 (单例缓存)"""

    _CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
    _BUILDING_LOCK = asyncio.Lock()

    def __init__(self, db: AsyncSession):
        self.db = db
        self.data_service = DataService(db)

    @classmethod
    def get_cached_snapshot(cls, trade_date: str) -> Optional[Dict[str, Any]]:
        """从内存中快速读取快照 (0 延迟)"""
        cached = cls._CACHE.get(trade_date)
        if not cached:
            return None
        cached_time, payload = cached
        now = time.time()
        # 交易窗口内 15 秒 TTL，非交易窗口时段 1 小时 TTL
        ttl = 15.0 if tdx_session_manager.is_trading_window() else 3600.0
        if now - cached_time < ttl:
            return payload
        return None

    async def get_instant_snapshot(
        self,
        trade_date: Optional[str] = None,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        获取驾驶舱即时全景快照 (首屏秒开核心端点)
        - 若内存有有效缓存：直接 1ms 返回
        - 若无缓存或已过期：并发聚合各个领域快照，入缓存后返回
        """
        target_date = trade_date
        if not target_date:
            target_date = await self._resolve_latest_trading_date()

        if not force_refresh:
            cached_data = self.get_cached_snapshot(target_date)
            if cached_data:
                cached_data["cached"] = True
                return cached_data

        async with self._BUILDING_LOCK:
            # 双重检查
            if not force_refresh:
                cached_data = self.get_cached_snapshot(target_date)
                if cached_data:
                    cached_data["cached"] = True
                    return cached_data

            t0 = time.time()
            prev_date = self._get_prev_trading_day(target_date)

            canonical_market = CanonicalMarketService(self.db)
            canonical_intraday = CanonicalIntradayService(self.db)
            canonical_auction = CanonicalAuctionService(self.db)
            intraday_briefing = IntradayBriefingService(self.db)

            # 1. 首先拉取标准市场物理与认知快照
            snap_res = None
            snap_obj = None
            try:
                snap_obj = await canonical_market.get_canonical_snapshot(target_date)
                if snap_obj:
                    snap_res = snap_obj.model_dump()
            except Exception as e:
                logger.debug(f"Failed to fetch canonical market snapshot: {e}")

            # 2. 从快照衍生出受约束操盘手内参战报
            tactical_res = None
            if snap_obj:
                try:
                    raw_snapshot_json = snap_obj.model_dump_json()
                    snapshot_hash = hashlib.sha256(raw_snapshot_json.encode("utf-8")).hexdigest()
                    trace_id = f"TRACE-{target_date}-INSTANT"
                    extractor = NarrativeContextExtractor()
                    context = extractor.extract_context(snap_obj)
                    generator = ConstrainedBriefingGenerator()
                    briefing = generator.generate_briefing(
                        contract=context,
                        trace_id=trace_id,
                        source_snapshot_hash=snapshot_hash,
                    )
                    if briefing:
                        tactical_res = briefing.model_dump()
                except Exception as e:
                    logger.debug(f"Failed to generate tactical briefing for snapshot: {e}")

            from ..services.auction_falsification_service import AuctionFalsificationService
            from ..services.intraday_drift_service import IntradayDriftService

            auction_svc = AuctionFalsificationService(self.db)
            drift_svc = IntradayDriftService(self.db)

            # 3. 并发打捞其他核心维度
            tasks = [
                self.data_service.get_limit_up_pool(target_date),
                self.data_service.get_limit_up_pool(prev_date),
                auction_svc.get_or_compute_verdict(trade_date=target_date),
                drift_svc.get_or_compute_verdict(trade_date=target_date),
                intraday_briefing.get_or_compute_timeline(trade_date=target_date),
                intraday_briefing.get_top_sectors_trend(trade_date=target_date),
                self.data_service.get_sector_ranking("concept"),
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            def _safe_res(res):
                if isinstance(res, Exception):
                    logger.debug(f"Snapshot sub-task returned exception: {res}")
                    return None
                if hasattr(res, "model_dump"):
                    return res.model_dump()
                if hasattr(res, "dict"):
                    return res.dict()
                if hasattr(res, "data"):
                    return res.data
                return res

            (
                lu_res,
                prev_lu_res,
                auction_res,
                drift_res,
                timeline_res,
                top_sectors_res,
                sectors_res
            ) = [_safe_res(r) for r in results]

            tdx_stat = tdx_session_manager.get_status()

            payload = {
                "code": 200,
                "trade_date": target_date,
                "prev_trade_date": prev_date,
                "cached": False,
                "latency_build_ms": round((time.time() - t0) * 1000, 1),
                "generated_at": datetime.now().isoformat(),
                "tdx_status": tdx_stat,
                "canonical_snapshot": snap_res,
                "limit_up_pool": lu_res,
                "yesterday_limit_up_pool": prev_lu_res,
                "tactical_briefing": tactical_res,
                "auction_verdict": auction_res,
                "intraday_drift": drift_res,
                "intraday_timeline": timeline_res,
                "top_sectors_trend": top_sectors_res,
                "sectors": sectors_res or [],
            }

            self._CACHE[target_date] = (time.time(), payload)
            logger.info(f"Cockpit 即时快照已刷新入内存: {target_date}, 耗时: {payload['latency_build_ms']}ms")
            return payload

    async def _resolve_latest_trading_date(self) -> str:
        """解析系统最新的基准交易日期"""
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        if calendar.is_trading_day(now.date()) and (now.hour > 8 or (now.hour == 8 and now.minute >= 30)):
            return today_str

        stmt = (
            select(MarketDailySnapshot.date)
            .where(MarketDailySnapshot.snapshot_type == "EOD_CLOSE")
            .order_by(MarketDailySnapshot.date.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        latest = result.scalar_one_or_none()
        return latest or today_str

    @staticmethod
    def _get_prev_trading_day(cur_date_str: str) -> str:
        """获取前一有效交易日字符串"""
        try:
            cur_dt = datetime.strptime(cur_date_str, "%Y-%m-%d").date()
            prev = calendar.get_previous_trading_day(cur_dt)
            return prev.strftime("%Y-%m-%d") if prev else cur_date_str
        except Exception:
            return cur_date_str
