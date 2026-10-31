import asyncio
from datetime import datetime
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession

from .capabilities import DataQuality, DataResult, Freshness, ProviderErrorCode, DataStatus
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

    # 缓存展示容忍期限 (秒)
    CAPABILITY_STALE_TOLERANCE: Dict[str, float] = {
        "stock_trends": 300.0,
        "sector": 600.0,
        "concept_blocks": 86400.0,
        "default": 300.0,
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
        self.last_quality_log_success: bool = True
        self.current_now: Optional[datetime] = None
        self.current_date: Optional[str] = None

    @staticmethod
    def _is_cache_temporally_valid(
        cached: Optional[DataResult],
        req_trade_date: Optional[str],
        max_age_sec: float,
        reference_now: Optional[datetime] = None,
    ) -> bool:
        """
        统一时态与日期门禁校验：
        1. 显式指定 trade_date 时，缓存必须存在且严格等于目标日期；
        2. 未指定 trade_date (实时行情) 时，缓存若有 trade_date 必须等于当日；
        3. 缓存时间戳禁止大于未来 60 秒 (防时钟漂移/伪造)；
        4. 实时行情禁止跨越午夜复用前日缓存；
        5. 年龄必须在 max_age_sec 容忍期内；
        6. 无时间戳且未显式指定目标日的缓存一律拒绝。
        """
        if not cached or cached.data is None:
            return False
        quality_val = cached.quality.value if hasattr(cached.quality, "value") else str(cached.quality)
        if quality_val not in ("FULL", "PARTIAL", "DEGRADED"):
            return False

        raw_now = reference_now or datetime.now()
        now_dt = raw_now.astimezone().replace(tzinfo=None) if raw_now.tzinfo is not None else raw_now
        today_str = now_dt.strftime("%Y-%m-%d")

        cached_trade_date = getattr(cached, "trade_date", None)
        if req_trade_date:
            if not cached_trade_date or str(cached_trade_date) != str(req_trade_date):
                return False
        else:
            # 未指定日期时必须具备当日交易日 (未知日期缓存拒用)
            if not cached_trade_date or str(cached_trade_date) != today_str:
                return False

        # 未知来源时点坚决拒用，严禁回退接收时间
        raw_src_ts = getattr(cached, "source_timestamp", None)
        if raw_src_ts is None:
            return False
        cached_src_ts = raw_src_ts.astimezone().replace(tzinfo=None) if raw_src_ts.tzinfo is not None else raw_src_ts

        if (cached_src_ts - now_dt).total_seconds() > 60:
            return False
        if not req_trade_date and cached_src_ts.date() != now_dt.date():
            return False
        if (now_dt - cached_src_ts).total_seconds() > max_age_sec:
            return False

        return True

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
        cache_kwargs = {k: v for k, v in kwargs.items() if k not in ("reference_now", "validate_freshness")}
        kwargs_part = f":{sorted(cache_kwargs.items())}" if cache_kwargs else ""
        cache_key = f"{capability}:{method}:{str(args)}{kwargs_part}"
        now = time.time()
        ttl = self.CAPABILITY_TTL.get(capability, 15.0)

        # -------------------------------------------------------------
        # 阶段 1: Cache (本地短 TTL 内存缓存，严苛时态与日期门禁)
        # -------------------------------------------------------------
        cached = self._CACHE.get(cache_key)
        if cached:
            ts, res = cached
            req_trade_date = kwargs.get("trade_date")
            is_valid = True
            if capability in ("sector", "concept_blocks", "stock_trends"):
                if not self._is_cache_temporally_valid(res, req_trade_date, max_age_sec=ttl):
                    is_valid = False

            quality_val = res.quality.value if hasattr(res.quality, "value") else str(res.quality)
            if is_valid and (now - ts) < ttl and quality_val in ("FULL", "PARTIAL", "DEGRADED"):
                # 针对行情报价类能力，缓存命中时必须重新校验当前时态与新鲜度 (防止缓存期内超过 300 秒或跨日)
                validate_freshness = kwargs.get("validate_freshness", True)
                if capability in ("stock_quote", "index_quote") and validate_freshness and res.data:
                    from .quote_validator import validate_quote_batch
                    reference_now = kwargs.get("reference_now") or getattr(self, "current_now", None)
                    is_fresh, freshness_err = validate_quote_batch(res.data, now=reference_now)
                    if not is_fresh:
                        logger.info(f"Cache invalidated for {capability} due to quote aging or date mismatch: {freshness_err}")
                        self._CACHE.pop(cache_key, None)
                        cached = None

                if cached:
                    self._metrics["cache_hits"] += 1
                    if getattr(res, "quality_log_success", None) is False:
                        QualityTracker.record_failure(
                            capability=capability,
                            provider=res.provider or "cache",
                            error=f"Reused cached result with failed quality log: {capability}"
                        )
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
                tolerance_sec = self.CAPABILITY_STALE_TOLERANCE.get(capability, self.CAPABILITY_STALE_TOLERANCE["default"])
                req_trade_date = kwargs.get("trade_date")
                ref_now = kwargs.get("reference_now") or getattr(self, "current_now", None)
                is_valid_cache = self._is_cache_temporally_valid(last_good, req_trade_date, tolerance_sec, reference_now=ref_now)
                cache_src_ts = getattr(last_good, "source_timestamp", None)

                if is_valid_cache and last_good:
                    return DataResult(
                        data=last_good.data,
                        quality=DataQuality.DEGRADED,
                        freshness=Freshness.STALE,
                        status=DataStatus.STALE,
                        provider=last_good.provider,
                        source_timestamp=cache_src_ts,
                        timestamp=datetime.now(),
                        trade_date=getattr(last_good, "trade_date", None),
                        error_message="Minute budget exhausted, served from STALE cache",
                        degradation_reason="Minute budget exhausted, served from STALE cache",
                        fallback_used=True,
                        missing_codes=getattr(last_good, "missing_codes", None),
                    )
                else:
                    return DataResult(
                        data=None,
                        quality=DataQuality.UNAVAILABLE,
                        freshness=Freshness.UNAVAILABLE,
                        status=DataStatus.ERROR,
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
                call_kwargs = dict(kwargs)
                ref_now = call_kwargs.get("reference_now") or getattr(self, "current_now", None)
                if ref_now is not None:
                    call_kwargs["reference_now"] = ref_now
                tolerance_sec = self.CAPABILITY_STALE_TOLERANCE.get(capability, self.CAPABILITY_STALE_TOLERANCE["default"])
                call_kwargs["stale_tolerance_sec"] = tolerance_sec
                result = await registry.execute_with_fallback(
                    capability,
                    method,
                    *args,
                    last_good_cache=last_good,
                    timeout_ms=timeout_ms,
                    **call_kwargs,
                )
                if result.quality in (DataQuality.INVALID, DataQuality.UNAVAILABLE, DataQuality.FAILED) or result.data is None:
                    last_good = self._LAST_GOOD_CACHE.get(cache_key)
                    req_trade_date = kwargs.get("trade_date")
                    ref_now = kwargs.get("reference_now") or getattr(self, "current_now", None)
                    is_valid_cache = self._is_cache_temporally_valid(last_good, req_trade_date, tolerance_sec, reference_now=ref_now)
                    cache_src_ts = getattr(last_good, "source_timestamp", None)

                    if is_valid_cache and last_good:
                        result = DataResult(
                            data=last_good.data,
                            quality=DataQuality.DEGRADED,
                            freshness=Freshness.STALE,
                            status=DataStatus.STALE,
                            provider=last_good.provider,
                            source_timestamp=cache_src_ts,
                            timestamp=datetime.now(),
                            trade_date=getattr(last_good, "trade_date", None),
                            error_message=f"All providers failed. Served from STALE snapshot. Last error: {result.error_message}",
                            degradation_reason=f"Served from STALE snapshot. Last error: {result.error_message}",
                            fallback_used=True,
                            missing_codes=getattr(last_good, "missing_codes", None),
                        )

                duration_ms = int((time.perf_counter() - t_start) * 1000)

                # 记录审计日志 (独立事务隔离落库，不占用或污染外部会话)
                log_success = await QualityTracker.log_quality(self.session, capability, result, duration_ms)
                result.quality_log_success = log_success
                self.last_quality_log_success = log_success

                # 写入缓存与最后有效快照 (仅当新物理获取的数据才写入/刷新 _CACHE 与 _LAST_GOOD_CACHE，严禁读取旧缓存刷新其时间)
                if result.quality not in (DataQuality.INVALID, DataQuality.UNAVAILABLE, DataQuality.FAILED) and result.data is not None:
                    if result.freshness != Freshness.STALE:
                        self._CACHE[cache_key] = (time.time(), result)
                        self._LAST_GOOD_CACHE[cache_key] = result

                return result

        result, is_leader = await self._singleflight.execute(cache_key, _execute_stages_3_to_7)
        if not is_leader and getattr(result, "quality_log_success", None) is False:
            QualityTracker.record_failure(
                capability=capability,
                provider=result.provider or "singleflight",
                error=f"Reused singleflight result with failed quality log: {capability}"
            )
        return result

    # 业务接口方法封装
    async def get_index_quotes(self, codes: List[str], **kwargs) -> DataResult:
        return await self._execute_pipeline("index_quote", "get_index_quotes", codes, **kwargs)

    async def get_stock_quotes(self, codes: List[str], **kwargs) -> DataResult:
        return await self._execute_pipeline("stock_quote", "get_stock_quotes", codes, **kwargs)

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

    @staticmethod
    def _normalize_code(code: Any) -> str:
        if not code:
            return ""
        c = str(code).strip().lower()
        if c.startswith(("sh", "sz", "bj")):
            c = c[2:]
        elif "." in c:
            parts = c.split(".")
            c = parts[1] if parts[0] in ("sh", "sz", "bj", "0", "1") else parts[0]
        return c

    async def _execute_provider_direct(
        self,
        capability: str,
        provider_name: str,
        method_name: str,
        *args,
        **kwargs,
    ) -> DataResult:
        """
        统一七重抗压管线对指定 Secondary Provider 的受控物理调度 (具备预算、限速、并发信号量、断路器全面治理)
        """
        budget_ok = await self._budget.acquire(provider_name)
        if not budget_ok:
            self._metrics["budget_rejections"] += 1
            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                freshness=Freshness.UNAVAILABLE,
                status=DataStatus.ERROR,
                provider=provider_name,
                error_code=ProviderErrorCode.RATE_LIMITED,
                error_message=f"Budget exhausted for secondary provider [{provider_name}]",
                degradation_reason=f"Budget exhausted for secondary provider [{provider_name}]",
                fallback_used=True,
            )

        await self._rate_limiter.acquire(provider_name)
        sem = self._semaphores.get_semaphore(provider_name)
        async with sem:
            cb = registry.get_circuit_breaker(provider_name)
            ht = registry.get_health_tracker(provider_name)
            can_exec, _ = await cb.can_execute()
            if not can_exec:
                return DataResult(
                    data=None,
                    quality=DataQuality.UNAVAILABLE,
                    freshness=Freshness.UNAVAILABLE,
                    status=DataStatus.ERROR,
                    provider=provider_name,
                    error_code=ProviderErrorCode.RATE_LIMITED,
                    error_message=f"Circuit breaker {cb.state.value} is OPEN for [{provider_name}]",
                    degradation_reason=f"Circuit breaker {cb.state.value} is OPEN for [{provider_name}]",
                    fallback_used=True,
                )

            providers = registry._registry.get(capability, [])
            provider_inst = None
            for p_name, p_inst in providers:
                if p_name == provider_name:
                    provider_inst = p_inst
                    break
            if not provider_inst:
                return DataResult(
                    data=None,
                    quality=DataQuality.UNAVAILABLE,
                    freshness=Freshness.UNAVAILABLE,
                    status=DataStatus.EMPTY,
                    provider=provider_name,
                    error_message=f"Provider [{provider_name}] not registered for [{capability}]",
                    fallback_used=True,
                )

            method = getattr(provider_inst, method_name, None)
            if not method:
                return DataResult(
                    data=None,
                    quality=DataQuality.UNAVAILABLE,
                    freshness=Freshness.UNAVAILABLE,
                    status=DataStatus.EMPTY,
                    provider=provider_name,
                    error_message=f"Method [{method_name}] not found on [{provider_name}]",
                    fallback_used=True,
                )

            t_start = time.perf_counter()
            timeout_ms = self.CAPABILITY_TIMEOUTS.get(capability, 5000)
            hard_timeout_sec = max(1.0, timeout_ms / 1000.0)
            try:
                res: DataResult = await asyncio.wait_for(method(*args, **kwargs), timeout=hard_timeout_sec)
                dur_ms = int((time.perf_counter() - t_start) * 1000)
                if res and res.quality not in (DataQuality.INVALID, DataQuality.UNAVAILABLE, DataQuality.FAILED) and res.data is not None:
                    await cb.record_success()
                    ht.record_sample(is_success=True, latency_ms=dur_ms)
                else:
                    err = res.error_message if res else "Empty or invalid response"
                    await cb.record_failure(err)
                    ht.record_sample(is_success=False, latency_ms=dur_ms, is_malformed=True)
                return res
            except asyncio.TimeoutError:
                dur_ms = int((time.perf_counter() - t_start) * 1000)
                await cb.record_failure("TIMEOUT")
                ht.record_sample(is_success=False, latency_ms=dur_ms, is_timeout=True)
                return DataResult(
                    data=None,
                    quality=DataQuality.UNAVAILABLE,
                    freshness=Freshness.UNAVAILABLE,
                    status=DataStatus.TIMEOUT,
                    provider=provider_name,
                    error_code=ProviderErrorCode.TIMEOUT,
                    error_message=f"Timeout executing {provider_name}.{method_name}",
                    fallback_used=True,
                )
            except Exception as e:
                dur_ms = int((time.perf_counter() - t_start) * 1000)
                await cb.record_failure(str(e))
                ht.record_sample(is_success=False, latency_ms=dur_ms)
                return DataResult(
                    data=None,
                    quality=DataQuality.UNAVAILABLE,
                    freshness=Freshness.UNAVAILABLE,
                    status=DataStatus.ERROR,
                    provider=provider_name,
                    error_code=ProviderErrorCode.CONNECTION_ERROR,
                    error_message=str(e),
                    fallback_used=True,
                )

    async def get_stock_trends(self, codes: list[str], trade_date: Optional[str] = None) -> DataResult:
        if not codes:
            return DataResult(
                data=[],
                quality=DataQuality.FULL,
                freshness=Freshness.REALTIME,
                status=DataStatus.AVAILABLE,
                provider="none",
                trade_date=trade_date,
            )

        res = await self._execute_pipeline("stock_trends", "get_stock_trends", codes, trade_date=trade_date)
        def valid_state(quality, freshness, status):
            try:
                return (DataQuality(quality) in (DataQuality.FULL, DataQuality.PARTIAL, DataQuality.DEGRADED)
                        and Freshness(freshness) in (Freshness.REALTIME, Freshness.DELAYED, Freshness.STALE, Freshness.EOD_COMPENSATED)
                        and DataStatus(status) in (DataStatus.AVAILABLE, DataStatus.STALE))
            except (ValueError, TypeError):
                return False

        raw_items = list(res.data) if (res and isinstance(res.data, list)
                    and valid_state(res.quality, res.freshness, res.status)) else []

        # 逐项对齐主源基础元数据
        for item in raw_items:
            if isinstance(item, dict):
                item.setdefault("provider", res.provider or "tdx_direct")
                item.setdefault("fallback_used", getattr(res, "fallback_used", False))
                tr = item.get("trends", [])
                item.setdefault("quality", res.quality if tr else DataQuality.UNAVAILABLE.value)
                item.setdefault("status", res.status if tr else DataStatus.EMPTY.value)
                item.setdefault("is_real", True if (tr and len(tr) >= 5) else False)
                if res.source_timestamp and not item.get("source_timestamp"):
                    item["source_timestamp"] = res.source_timestamp
                if res.trade_date and not item.get("trade_date"):
                    item["trade_date"] = res.trade_date

        existing_codes = {
            self._normalize_code(item.get("code"))
            for item in raw_items
            if isinstance(item, dict)
            and item.get("code")
            and valid_state(item.get("quality", res.quality), item.get("freshness", res.freshness), item.get("status", res.status))
            and len(item.get("trends", [])) > 0
        }
        existing_items = [
            item for item in raw_items
            if isinstance(item, dict) and self._normalize_code(item.get("code")) in existing_codes
            and valid_state(item.get("quality", res.quality), item.get("freshness", res.freshness), item.get("status", res.status))
        ]
        missing = [c for c in codes if self._normalize_code(c) not in existing_codes]
        fallback_item_count = 0

        # 如果主源未完全覆盖或主源完全失败，通过统一管线调度备用源 (eastmoney) 补全缺失代码
        backup_res = None
        if missing:
            registered_providers = registry._registry.get("stock_trends", [])
            has_secondary = any(p[0] == "eastmoney" for p in registered_providers)
            if has_secondary:
                backup_res = await self._execute_provider_direct(
                    "stock_trends", "eastmoney", "get_stock_trends", missing, trade_date=trade_date
                )
                if (
                    backup_res
                    and backup_res.quality not in (DataQuality.UNAVAILABLE, DataQuality.FAILED, DataQuality.INVALID)
                    and backup_res.freshness not in (Freshness.EXPIRED, Freshness.UNAVAILABLE)
                    and valid_state(backup_res.quality, backup_res.freshness, backup_res.status)
                    and isinstance(backup_res.data, list)
                    and backup_res.data
                ):
                    for b_item in backup_res.data:
                        if isinstance(b_item, dict):
                            norm_b = self._normalize_code(b_item.get("code"))
                            b_trends = b_item.get("trends", [])
                            b_qual = b_item.get("quality")
                            b_fresh = b_item.get("freshness")

                            # 解析备用单项的时效
                            if b_fresh is not None:
                                try:
                                    eff_b_fresh = Freshness(b_fresh)
                                except ValueError:
                                    eff_b_fresh = Freshness.UNAVAILABLE
                            else:
                                try:
                                    eff_b_fresh = Freshness(backup_res.freshness)
                                except (ValueError, TypeError):
                                    eff_b_fresh = Freshness.UNAVAILABLE

                            # 过滤不可用、失败、畸变或严重过期失效项
                            if (
                                norm_b in [self._normalize_code(c) for c in missing]
                                and norm_b not in existing_codes
                                and isinstance(b_trends, list)
                                and len(b_trends) > 0
                                and valid_state(b_qual if b_qual is not None else backup_res.quality, eff_b_fresh, b_item.get("status", backup_res.status))
                                and eff_b_fresh not in (Freshness.EXPIRED, Freshness.UNAVAILABLE)
                            ):
                                eff_b_status = DataStatus.STALE.value if (eff_b_fresh == Freshness.STALE or backup_res.status == DataStatus.STALE) else DataStatus.AVAILABLE.value
                                b_item["provider"] = "eastmoney"
                                b_item["quality"] = DataQuality.DEGRADED.value
                                b_item["status"] = eff_b_status
                                b_item["freshness"] = eff_b_fresh.value
                                b_item["is_real"] = True if len(b_trends) >= 5 else False
                                b_item["fallback_used"] = True
                                if backup_res.source_timestamp and not b_item.get("source_timestamp"):
                                    b_item["source_timestamp"] = backup_res.source_timestamp
                                if backup_res.trade_date and not b_item.get("trade_date"):
                                    b_item["trade_date"] = backup_res.trade_date
                                existing_items.append(b_item)
                                existing_codes.add(norm_b)
                                fallback_item_count += 1

                    missing = [c for c in codes if self._normalize_code(c) not in existing_codes]

        # 终局一致性质量合成
        has_primary_items = any(
            isinstance(it, dict) and it.get("provider") != "eastmoney" and it.get("quality") != DataQuality.UNAVAILABLE.value
            for it in existing_items
        )

        valid_items = [
            it for it in existing_items
            if isinstance(it, dict) and it.get("quality") != DataQuality.UNAVAILABLE.value and it.get("trends")
        ]

        # 收集所有参与有效响应的来源时效状态
        participating_freshnesses = set()
        if has_primary_items and res.freshness:
            try:
                participating_freshnesses.add(res.freshness if isinstance(res.freshness, Freshness) else Freshness(res.freshness))
            except ValueError:
                pass
        if fallback_item_count > 0 and backup_res and backup_res.freshness:
            try:
                participating_freshnesses.add(backup_res.freshness if isinstance(backup_res.freshness, Freshness) else Freshness(backup_res.freshness))
            except ValueError:
                pass

        for it in valid_items:
            f_val = it.get("freshness")
            if f_val:
                try:
                    participating_freshnesses.add(Freshness(f_val))
                except ValueError:
                    pass

        # 保守时态等级合成 (EXPIRED -> STALE -> DELAYED -> EOD_COMPENSATED -> REALTIME)
        if Freshness.EXPIRED in participating_freshnesses:
            synthesized_freshness = Freshness.EXPIRED
            synthesized_status = DataStatus.STALE
        elif Freshness.STALE in participating_freshnesses or res.status == DataStatus.STALE or (backup_res and backup_res.status == DataStatus.STALE and fallback_item_count > 0):
            synthesized_freshness = Freshness.STALE
            synthesized_status = DataStatus.STALE
        elif Freshness.DELAYED in participating_freshnesses:
            synthesized_freshness = Freshness.DELAYED
            synthesized_status = DataStatus.AVAILABLE
        elif Freshness.EOD_COMPENSATED in participating_freshnesses:
            synthesized_freshness = Freshness.EOD_COMPENSATED
            synthesized_status = DataStatus.AVAILABLE
        elif Freshness.REALTIME in participating_freshnesses:
            synthesized_freshness = Freshness.REALTIME
            synthesized_status = DataStatus.AVAILABLE
        else:
            synthesized_freshness = Freshness.UNAVAILABLE
            synthesized_status = DataStatus.EMPTY

        # 批次来源时点保守合成：
        # 若任何一个有效标的缺失来源时点 (例如主源 TDX 未传 source_timestamp)，
        # 绝不以备源东财时点冒充整批截止时点，严格保留 None (时态未知)
        has_item_without_ts = any(it.get("source_timestamp") is None for it in valid_items)
        if valid_items and not has_item_without_ts:
            valid_src_timestamps = [
                it["source_timestamp"] for it in valid_items
                if isinstance(it.get("source_timestamp"), datetime)
            ]
            res.source_timestamp = min(valid_src_timestamps) if valid_src_timestamps else None
        else:
            res.source_timestamp = None

        if fallback_item_count > 0:
            res.fallback_used = True
            if has_primary_items:
                res.provider = f"{res.provider}+eastmoney" if res.provider and res.provider != "all_failed" else "eastmoney"
            else:
                res.provider = "eastmoney"
                if backup_res:
                    res.trade_date = backup_res.trade_date

        res.freshness = synthesized_freshness
        res.status = synthesized_status

        # 对于最终仍无法获取的分时代码，构造标准空序列结构，附带明确的 UNAVAILABLE 质量元数据
        for c in codes:
            norm_c = self._normalize_code(c)
            if norm_c not in existing_codes:
                existing_items.append({
                    "code": c,
                    "name": c,
                    "pre_close": None,
                    "trends": [],
                    "quality": DataQuality.UNAVAILABLE.value,
                    "status": DataStatus.EMPTY.value,
                    "is_real": False,
                    "trade_date": trade_date,
                    "provider": None,
                    "fallback_used": False,
                })
                if c not in missing and norm_c not in missing:
                    missing.append(c)

        res.data = existing_items
        res.missing_codes = missing

        if len(missing) == len(codes):
            res.quality = DataQuality.UNAVAILABLE
            res.freshness = Freshness.UNAVAILABLE
            res.status = DataStatus.ERROR if res.error_message else DataStatus.EMPTY
        elif len(missing) > 0:
            res.quality = DataQuality.PARTIAL
            res.status = synthesized_status
            res.freshness = synthesized_freshness
            res.error_code = ProviderErrorCode.NONE
            res.error_message = None
            res.degradation_reason = f"Missing {len(missing)} of {len(codes)} symbols"
            if synthesized_freshness == Freshness.STALE:
                res.degradation_reason += "; contains STALE snapshot data"
            elif synthesized_freshness == Freshness.DELAYED:
                res.degradation_reason += "; contains DELAYED market data"
        else:
            # 全部代码成功获取
            if fallback_item_count > 0 or getattr(res, "fallback_used", False) or synthesized_freshness != Freshness.REALTIME or res.quality == DataQuality.DEGRADED:
                res.quality = DataQuality.DEGRADED
                res.fallback_used = True
                res.status = synthesized_status
                res.freshness = synthesized_freshness
                if synthesized_freshness == Freshness.STALE and fallback_item_count > 0:
                    res.degradation_reason = "Completed missing codes via STALE fallback provider"
                elif synthesized_freshness == Freshness.STALE:
                    res.degradation_reason = "Served from STALE snapshot"
                elif synthesized_freshness == Freshness.DELAYED and fallback_item_count > 0:
                    res.degradation_reason = "Completed missing codes via DELAYED fallback provider"
                elif synthesized_freshness == Freshness.DELAYED:
                    res.degradation_reason = "Contains DELAYED market data"
                elif fallback_item_count > 0:
                    res.degradation_reason = "Completed missing codes via fallback provider"
                else:
                    res.degradation_reason = getattr(res, "degradation_reason", None) or "Degraded data"
            else:
                res.quality = DataQuality.FULL
                res.fallback_used = False
                res.status = DataStatus.AVAILABLE
                res.freshness = Freshness.REALTIME
                res.degradation_reason = None
            res.error_code = ProviderErrorCode.NONE
            res.error_message = None

        return res

    async def get_market_index_trend(self, index_code: str = "sh000001") -> Optional[Dict[str, Any]]:
        """获取大盘基准指数分时走势 (上证指数等)"""
        try:
            from backend.app.data.providers.eastmoney import EastmoneyProvider
            em = EastmoneyProvider()
            return await em.get_market_index_trend(index_code)
        except Exception as e:
            logger.warning(f"Failed to fetch market index trend in DataService: {e}")
            return None


