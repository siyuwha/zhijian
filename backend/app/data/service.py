import time
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from .capabilities import DataResult
from .registry import registry
from .quality import QualityTracker

class DataService:
    """
    统一数据服务接入层 (Data Layer Facade)
    上层服务只调用此类方法，完全与底层具体 Provider 解耦。
    每次调用自动接入质量追踪与审计。
    """

    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session

    async def get_index_quotes(self, codes: List[str]) -> DataResult:
        start = time.perf_counter()
        result = await registry.execute_with_fallback("index_quote", "get_index_quotes", codes)
        duration_ms = int((time.perf_counter() - start) * 1000)
        if self.session:
            await QualityTracker.log_quality(self.session, "index_quote", result, duration_ms)
        return result

    async def get_stock_quotes(self, codes: List[str]) -> DataResult:
        start = time.perf_counter()
        result = await registry.execute_with_fallback("stock_quote", "get_stock_quotes", codes)
        duration_ms = int((time.perf_counter() - start) * 1000)
        if self.session:
            await QualityTracker.log_quality(self.session, "stock_quote", result, duration_ms)
        return result

    async def get_limit_up_pool(self, date: Optional[str] = None) -> DataResult:
        start = time.perf_counter()
        result = await registry.execute_with_fallback("limit_up", "get_limit_up_pool", date)
        duration_ms = int((time.perf_counter() - start) * 1000)
        if self.session:
            await QualityTracker.log_quality(self.session, "limit_up", result, duration_ms)
        return result

    async def get_market_breadth(self) -> DataResult:
        start = time.perf_counter()
        result = await registry.execute_with_fallback("market_breadth", "get_market_breadth")
        duration_ms = int((time.perf_counter() - start) * 1000)
        if self.session:
            await QualityTracker.log_quality(self.session, "market_breadth", result, duration_ms)
        return result

    async def get_micro_cap_quote(self) -> DataResult:
        start = time.perf_counter()
        result = await registry.execute_with_fallback("micro_cap", "get_micro_cap_quote")
        duration_ms = int((time.perf_counter() - start) * 1000)
        if self.session:
            await QualityTracker.log_quality(self.session, "micro_cap", result, duration_ms)
        return result

    async def get_external_risk(self) -> DataResult:
        start = time.perf_counter()
        result = await registry.execute_with_fallback("external_risk", "get_external_risk")
        duration_ms = int((time.perf_counter() - start) * 1000)
        if self.session:
            await QualityTracker.log_quality(self.session, "external_risk", result, duration_ms)
        return result

    async def get_high_tier_performance(self) -> DataResult:
        start = time.perf_counter()
        result = await registry.execute_with_fallback("high_tier_performance", "get_high_tier_performance")
        duration_ms = int((time.perf_counter() - start) * 1000)
        if self.session:
            await QualityTracker.log_quality(self.session, "high_tier_performance", result, duration_ms)
        return result

    async def get_overnight_data(self) -> DataResult:
        start = time.perf_counter()
        result = await registry.execute_with_fallback("overnight", "get_overnight_data")
        duration_ms = int((time.perf_counter() - start) * 1000)
        if self.session:
            await QualityTracker.log_quality(self.session, "overnight", result, duration_ms)
        return result

    async def get_daily_settlement(self, code: str, date: str) -> DataResult:
        start = time.perf_counter()
        result = await registry.execute_with_fallback("settlement", "get_daily_settlement", code, date)
        duration_ms = int((time.perf_counter() - start) * 1000)
        if self.session:
            await QualityTracker.log_quality(self.session, "settlement", result, duration_ms)
        return result

    async def get_latest_news(self, count: int = 15) -> DataResult:
        start = time.perf_counter()
        result = await registry.execute_with_fallback("news", "get_latest_news", count)
        duration_ms = int((time.perf_counter() - start) * 1000)
        if self.session:
            await QualityTracker.log_quality(self.session, "news", result, duration_ms)
        return result

    async def get_sector_ranking(self, sector_type: str = "industry") -> DataResult:
        start = time.perf_counter()
        result = await registry.execute_with_fallback("sector", "get_sector_ranking", sector_type)
        duration_ms = int((time.perf_counter() - start) * 1000)
        if self.session:
            await QualityTracker.log_quality(self.session, "sector", result, duration_ms)
        return result

    async def get_capital_flow(self, code: str) -> DataResult:
        start = time.perf_counter()
        result = await registry.execute_with_fallback("capital_flow", "get_capital_flow", code)
        duration_ms = int((time.perf_counter() - start) * 1000)
        if self.session:
            await QualityTracker.log_quality(self.session, "capital_flow", result, duration_ms)
        return result
