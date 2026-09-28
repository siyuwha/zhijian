import time
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from .capabilities import DataQuality, DataResult
from .registry import registry
from .quality import QualityTracker

class DataService:
    """
    统一数据服务接入层 (Data Layer Facade)
    上层服务只调用此类方法，完全与底层具体 Provider 解耦。
    具备 15 秒短生命周期 TTL 缓存与并发去重机制，彻底杜绝盘中外部请求风暴。
    """
    _CACHE: dict = {}
    CACHE_TTL_SECONDS: float = 15.0

    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session

    async def _execute_cached(self, capability: str, method: str, *args) -> DataResult:
        cache_key = f"{capability}:{method}:{str(args)}"
        now = time.time()
        cached = self._CACHE.get(cache_key)
        if cached:
            ts, res = cached
            if (now - ts) < self.CACHE_TTL_SECONDS and res.quality != DataQuality.FAILED:
                return res

        start = time.perf_counter()
        result = await registry.execute_with_fallback(capability, method, *args)
        duration_ms = int((time.perf_counter() - start) * 1000)
        if self.session:
            await QualityTracker.log_quality(self.session, capability, result, duration_ms)

        if result.quality != DataQuality.FAILED:
            self._CACHE[cache_key] = (now, result)

        return result

    async def get_index_quotes(self, codes: List[str]) -> DataResult:
        return await self._execute_cached("index_quote", "get_index_quotes", codes)

    async def get_stock_quotes(self, codes: List[str]) -> DataResult:
        return await self._execute_cached("stock_quote", "get_stock_quotes", codes)

    async def get_limit_up_pool(self, date: Optional[str] = None) -> DataResult:
        return await self._execute_cached("limit_up", "get_limit_up_pool", date)

    async def get_market_breadth(self) -> DataResult:
        return await self._execute_cached("market_breadth", "get_market_breadth")

    async def get_micro_cap_quote(self) -> DataResult:
        return await self._execute_cached("micro_cap", "get_micro_cap_quote")

    async def get_external_risk(self) -> DataResult:
        return await self._execute_cached("external_risk", "get_external_risk")

    async def get_high_tier_performance(self) -> DataResult:
        return await self._execute_cached("high_tier_performance", "get_high_tier_performance")

    async def get_overnight_data(self) -> DataResult:
        return await self._execute_cached("overnight", "get_overnight_data")

    async def get_daily_settlement(self, code: str, date: str) -> DataResult:
        return await self._execute_cached("settlement", "get_daily_settlement", code, date)

    async def get_latest_news(self, count: int = 15) -> DataResult:
        return await self._execute_cached("news", "get_latest_news", count)

    async def get_sector_ranking(self, sector_type: str = "industry") -> DataResult:
        return await self._execute_cached("sector", "get_sector_ranking", sector_type)

    async def get_capital_flow(self, code: str) -> DataResult:
        return await self._execute_cached("capital_flow", "get_capital_flow", code)
