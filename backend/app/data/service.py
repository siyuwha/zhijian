import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from .capabilities import DataQuality, DataResult, Freshness, ProviderErrorCode
from .pipeline import DomainSemaphore, RateLimiter, RequestBudget, Singleflight
from .quality import QualityTracker
from .registry import registry
from .providers import init_providers

logger = logging.getLogger(__name__)

class DataService:
    """
    P2 统一数据服务接入层 (Data Layer Facade)
    上层服务只调用此类方法，完全与底层具体 Provider 解耦。
    严格执行七重抗压防御管线：
    Cache → Singleflight → CircuitBreaker → RequestBudget → RateLimiter → Semaphore → Physical Provider
    """

    # 业务能力短生命周期 TTL 字典 (秒)
    CAPABILITY_TTL: Dict[str, float] = {
        "index_quote": 15.0,
        "stock_quote": 10.0,
        "limit_up": 30.0,
        "market_breadth": 45.0,
        "micro_cap": 60.0,
        "external_risk": 60.0,
        "high_tier_performance": 30.0,
        "overnight": 120.0,
        "settlement": 300.0,
        "news": 60.0,
        "sector": 60.0,
        "capital_flow": 30.0,
        "security_search": 300.0,
        "price_anomaly": 60.0,
        "concept_blocks": 300.0,
        "stock_trends": 15.0,
    }

    # 业务能力硬超时配置 (毫秒)
    CAPABILITY_TIMEOUTS: Dict[str, int] = {
        "concept_blocks": 15000,
        "price_anomaly": 15000,
        "settlement": 10000,
        "limit_up": 15000,
        "high_tier_performance": 15000,
        "market_breadth": 10000,
        "stock_trends": 10000,
    }

    # 全局内存快照缓存与最后已知有效快照 (Last Known Good Snapshot)
    _CACHE: Dict[str, Tuple[float, DataResult]] = {}
    _LAST_GOOD_CACHE: Dict[str, DataResult] = {}

    # 七重抗压组件单例
    _singleflight = Singleflight()
    _budget = RequestBudget()
    _rate_limiter = RateLimiter()
    _semaphores = DomainSemaphore()

    # 管道度量计数器
    _metrics = {
        "cache_hits": 0,
        "cache_misses": 0,
        "budget_rejections": 0,
    }

    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session

    @classmethod
    def get_pipeline_metrics(cls) -> dict:
        return {
            "cache_hits": cls._metrics["cache_hits"],
            "cache_misses": cls._metrics["cache_misses"],
            "coalesced_requests": cls._singleflight.coalesced_count,
            "budget_rejections": cls._budget.rejected_count,
        }

    async def _execute_pipeline(
        self,
        capability: str,
        method: str,
        *args,
        **kwargs,
    ) -> DataResult:
        """
        七重抗压管线核心驱动器
        """
        cache_key = f"{capability}:{method}:{str(args)}"
        now = time.time()
        ttl = self.CAPABILITY_TTL.get(capability, 15.0)

        # -------------------------------------------------------------
        # 阶段 1: Cache (本地短 TTL 内存缓存)
        # -------------------------------------------------------------
        cached = self._CACHE.get(cache_key)
        if cached:
            ts, res = cached
            if (now - ts) < ttl and res.quality not in (DataQuality.INVALID, DataQuality.UNAVAILABLE, DataQuality.FAILED):
                self._metrics["cache_hits"] += 1
                return res

        self._metrics["cache_misses"] += 1

        # -------------------------------------------------------------
        # 阶段 2: Singleflight (协程请求单飞合并)
        # -------------------------------------------------------------
        async def _execute_stages_3_to_7() -> DataResult:
            # 获取该能力注册的主力 Provider 标识 (用于预算、限速和信号量控制)
            providers = registry._registry.get(capability, [])
            primary_name = providers[0][0] if providers else "default"

            # ---------------------------------------------------------
            # 阶段 4: RequestBudget (分钟物理请求预算控制)
            # ---------------------------------------------------------
            budget_ok = await self._budget.acquire(primary_name)
            if not budget_ok:
                self._metrics["budget_rejections"] += 1
                logger.warning(
                    f"Pipeline Stage 4: Budget exhausted for [{primary_name}]. "
                    f"Fast-failing to STALE snapshot."
                )
                last_good = self._LAST_GOOD_CACHE.get(cache_key)
                if last_good and last_good.data is not None:
                    return DataResult(
                        data=last_good.data,
                        quality=DataQuality.DEGRADED,
                        freshness=Freshness.STALE,
                        provider=last_good.provider,
                        error_message="Minute budget exhausted, served from STALE cache",
                        fallback_used=True,
                    )
                else:
                    return DataResult(
                        data=None,
                        quality=DataQuality.UNAVAILABLE,
                        freshness=Freshness.UNAVAILABLE,
                        provider="budget_exhausted",
                        error_message="Minute budget exhausted and no cache available",
                        fallback_used=True,
                    )

            # ---------------------------------------------------------
            # 阶段 5: RateLimiter (滑动令牌平滑限速)
            # ---------------------------------------------------------
            await self._rate_limiter.acquire(primary_name)

            # ---------------------------------------------------------
            # 阶段 6: Semaphore (物理并发连接信号量配额)
            # ---------------------------------------------------------
            sem = self._semaphores.get_semaphore(primary_name)
            async with sem:
                # -----------------------------------------------------
                # 阶段 3 & 7: CircuitBreaker & Physical Provider
                # (由 registry.execute_with_fallback 执行断路器判定与多级故障转移)
                # -----------------------------------------------------
                t_start = time.perf_counter()
                last_good = self._LAST_GOOD_CACHE.get(cache_key)
                timeout_ms = self.CAPABILITY_TIMEOUTS.get(capability, 5000)
                result = await registry.execute_with_fallback(
                    capability,
                    method,
                    *args,
                    last_good_cache=last_good,
                    timeout_ms=timeout_ms,
                    **kwargs,
                )
                duration_ms = int((time.perf_counter() - t_start) * 1000)

                # 记录审计日志
                if self.session:
                    await QualityTracker.log_quality(self.session, capability, result, duration_ms)

                # 写入缓存与最后有效快照
                if result.quality not in (DataQuality.INVALID, DataQuality.UNAVAILABLE, DataQuality.FAILED) and result.data is not None:
                    self._CACHE[cache_key] = (time.time(), result)
                    self._LAST_GOOD_CACHE[cache_key] = result

                return result

        result, is_leader = await self._singleflight.execute(cache_key, _execute_stages_3_to_7)
        return result

    # 业务接口方法封装
    async def get_index_quotes(self, codes: List[str]) -> DataResult:
        return await self._execute_pipeline("index_quote", "get_index_quotes", codes)

    async def get_stock_quotes(self, codes: List[str]) -> DataResult:
        return await self._execute_pipeline("stock_quote", "get_stock_quotes", codes)

    async def get_limit_up_pool(self, date: Optional[str] = None) -> DataResult:
        return await self._execute_pipeline("limit_up", "get_limit_up_pool", date)

    async def get_market_breadth(self) -> DataResult:
        return await self._execute_pipeline("market_breadth", "get_market_breadth")

    async def get_micro_cap_quote(self) -> DataResult:
        return await self._execute_pipeline("micro_cap", "get_micro_cap_quote")

    async def get_external_risk(self) -> DataResult:
        return await self._execute_pipeline("external_risk", "get_external_risk")

    async def get_high_tier_performance(self) -> DataResult:
        return await self._execute_pipeline("high_tier_performance", "get_high_tier_performance")

    async def get_overnight_data(self) -> DataResult:
        return await self._execute_pipeline("overnight", "get_overnight_data")

    async def get_daily_settlement(self, code: str, date: str) -> DataResult:
        return await self._execute_pipeline("settlement", "get_daily_settlement", code, date)

    async def get_latest_news(self, count: int = 15) -> DataResult:
        return await self._execute_pipeline("news", "get_latest_news", count)

    async def get_sector_ranking(self, sector_type: str = "industry", limit: int = 60) -> DataResult:
        return await self._execute_pipeline("sector", "get_sector_ranking", sector_type, limit=limit)

    async def get_capital_flow(self, code: str) -> DataResult:
        return await self._execute_pipeline("capital_flow", "get_capital_flow", code)

    async def search_securities(self, query: str, limit: int = 10) -> DataResult:
        return await self._execute_pipeline("security_search", "search_security", query, limit)

    async def get_price_anomaly(self, page_size: int = 200, page_no: int = 1) -> DataResult:
        return await self._execute_pipeline("price_anomaly", "get_price_anomaly", page_size, page_no)

    async def get_concept_blocks(self, code: str) -> DataResult:
        return await self._execute_pipeline("concept_blocks", "get_concept_blocks", code)

    async def get_stock_trends(self, codes: list[str]) -> DataResult:
        return await self._execute_pipeline("stock_trends", "get_stock_trends", codes)

