import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

from .capabilities import DataQuality, DataResult, Freshness, ProviderErrorCode, ProviderResponse
from .circuit_breaker import CircuitBreaker, CircuitState
from .health import HealthTracker
from .quote_validator import validate_quote_batch

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class FailoverAuditEvent:
    """数据源故障转移审计事件 (P2 标准契约)"""
    event_id: str
    capability: str
    original_provider: str
    target_provider: str
    failover_reason: str
    switch_timestamp: datetime
    latency_before_switch_ms: int
    observation_id: str = ""

class ProviderRegistry:
    """
    P2 高可用韧性 Provider 注册中心
    - 管理 Capability -> Provider 降级调用链 (Primary -> Secondary -> Tertiary)
    - 绑定确定性硬断路器 (CircuitBreaker) 与健康追踪器 (HealthTracker)
    - 落实多级故障转移 (Failover) 与全物理源断流兜底规则：
      1. 有可信快照缓存: quality=DEGRADED, freshness=STALE
      2. 无可信快照缓存: quality=UNAVAILABLE, freshness=UNAVAILABLE (坚决不填 0)
    - 审计全量记录 FailoverAuditEvent
    """

    def __init__(self):
        # capability -> list of (provider_name, provider_instance)
        self._registry: Dict[str, List[Tuple[str, Any]]] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._health_trackers: Dict[str, HealthTracker] = {}
        self._audit_logs: List[FailoverAuditEvent] = []
        self._lock = asyncio.Lock()

    def reset(self):
        """重置所有断路器状态与审计日志（常用于单元测试清理）"""
        for cb in self._circuit_breakers.values():
            cb.state = CircuitState.CLOSED
            cb.consecutive_failures = 0
            cb.current_cooldown = cb.base_cooldown_seconds
            cb.opened_at = None
        self._audit_logs.clear()

    def get_circuit_breaker(self, provider_name: str) -> CircuitBreaker:
        name = provider_name.lower()
        if name not in self._circuit_breakers:
            self._circuit_breakers[name] = CircuitBreaker(provider_name=name)
        return self._circuit_breakers[name]

    def get_health_tracker(self, provider_name: str) -> HealthTracker:
        name = provider_name.lower()
        if name not in self._health_trackers:
            self._health_trackers[name] = HealthTracker(provider_name=name)
        return self._health_trackers[name]

    def register(
        self,
        capability: str,
        provider_name: str,
        provider_instance: Any,
        is_primary: bool = False,
    ):
        if capability not in self._registry:
            self._registry[capability] = []

        entry = (provider_name, provider_instance)
        if is_primary:
            self._registry[capability].insert(0, entry)
        else:
            self._registry[capability].append(entry)

        # 确保断路器与健康追踪器完成初始化
        self.get_circuit_breaker(provider_name)
        self.get_health_tracker(provider_name)

        logger.info(
            f"Registered provider '{provider_name}' for capability '{capability}' (primary={is_primary})"
        )

    def record_failover_event(
        self,
        capability: str,
        original_provider: str,
        target_provider: str,
        reason: str,
        latency_ms: int,
    ) -> FailoverAuditEvent:
        event = FailoverAuditEvent(
            event_id=str(uuid.uuid4()),
            capability=capability,
            original_provider=original_provider,
            target_provider=target_provider,
            failover_reason=reason,
            switch_timestamp=datetime.now(),
            latency_before_switch_ms=latency_ms,
        )
        self._audit_logs.append(event)
        logger.warning(
            f"FAILOVER AUDIT: capability='{capability}', from='{original_provider}' -> to='{target_provider}', "
            f"reason='{reason}', latency={latency_ms}ms"
        )
        return event

    def get_audit_logs(self) -> List[FailoverAuditEvent]:
        return list(self._audit_logs)

    def get_all_health(self) -> List[dict]:
        """获取所有已注册提供商的综合健康大盘指标"""
        results = []
        for name, tracker in self._health_trackers.items():
            cb = self.get_circuit_breaker(name)
            h = tracker.calculate_health()
            h["circuit_state"] = cb.state.value
            results.append(h)
        return results

    async def execute_with_fallback(
        self,
        capability: str,
        func_name: str,
        *args,
        last_good_cache: Optional[DataResult] = None,
        timeout_ms: int = 5000,
        **kwargs,
    ) -> DataResult:
        """
        按注册的级联降级链尝试执行：
        Primary -> Secondary -> Tertiary -> (有快照: DEGRADED+STALE / 无快照: UNAVAILABLE+UNAVAILABLE)
        """
        providers = self._registry.get(capability, [])
        if not providers:
            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                freshness=Freshness.UNAVAILABLE,
                provider="none",
                error_message=f"No provider registered for capability: {capability}",
                fallback_used=True,
            )

        last_error = None
        for i, (provider_name, provider) in enumerate(providers):
            method = getattr(provider, func_name, None)
            if not method:
                continue

            cb = self.get_circuit_breaker(provider_name)
            ht = self.get_health_tracker(provider_name)

            # 1. 断路器判定 (0 网络 I/O 内存拦截)
            can_exec, is_probe = await cb.can_execute()
            if not can_exec:
                last_error = f"Circuit breaker {cb.state.value} is OPEN (fast fail)"
                next_target = providers[i + 1][0] if i < len(providers) - 1 else "CACHE"
                self.record_failover_event(
                    capability=capability,
                    original_provider=provider_name,
                    target_provider=next_target,
                    reason=f"CIRCUIT_{cb.state.value}_FAST_FAIL",
                    latency_ms=0,
                )
                continue

            # 2. 物理网络请求执行 (硬超时保护)
            t_start = time.perf_counter()
            is_timeout = False
            is_malformed = False

            call_kwargs = dict(kwargs)
            validate_freshness = call_kwargs.pop("validate_freshness", True)
            reference_now = call_kwargs.pop("reference_now", None)

            try:
                hard_timeout_sec = max(1.0, timeout_ms / 1000.0)
                result: DataResult = await asyncio.wait_for(
                    method(*args, **call_kwargs),
                    timeout=hard_timeout_sec,
                )
                duration_ms = int((time.perf_counter() - t_start) * 1000)

                # 校验返回值质量
                if result and result.data is not None:
                    # 保留上游提供方物理产出的原始质量，严防被随后的 fallback 降级统一改写所遮蔽
                    raw_quality = getattr(result, "original_quality", None) or result.quality
                    result.original_quality = raw_quality

                    # 针对行情报价类能力，要求物理返回质量必须确证合格为 FULL 或 PARTIAL (原生 DEGRADED 拒绝准入)
                    # 且强制执行 Asia/Shanghai 当日与 0 <= now - quote_time <= 300s 严格时态校验
                    if capability in ("stock_quote", "index_quote"):
                        # 检查原始质量：如果原生为 DEGRADED/INVALID/UNAVAILABLE/FAILED，不可作为合格行情
                        if raw_quality not in (DataQuality.FULL, DataQuality.PARTIAL):
                            is_malformed = True
                            last_error = f"ORIGINAL_QUALITY_INADEQUATE: Provider '{provider_name}' returned raw quality {raw_quality}"
                            logger.warning(
                                f"Provider '{provider_name}' raw quality for '{capability}' is {raw_quality} (not FULL/PARTIAL). "
                                f"Triggering failover to next provider..."
                            )
                            await cb.record_failure(last_error)
                            ht.record_sample(is_success=False, latency_ms=duration_ms, is_malformed=True)
                            if i < len(providers) - 1:
                                self.record_failover_event(
                                    capability=capability,
                                    original_provider=provider_name,
                                    target_provider=providers[i + 1][0],
                                    reason=last_error,
                                    latency_ms=duration_ms,
                                )
                            continue

                        if validate_freshness:
                            is_fresh, freshness_err = validate_quote_batch(result.data, now=reference_now)
                            if not is_fresh:
                                is_malformed = True
                                last_error = f"QUOTE_FRESHNESS_FAIL: {freshness_err}"
                                logger.warning(
                                    f"Provider '{provider_name}' failed quote freshness for '{capability}': {freshness_err}. "
                                    f"Triggering failover to backup provider..."
                                )
                                await cb.record_failure(last_error)
                                ht.record_sample(is_success=False, latency_ms=duration_ms, is_malformed=True)

                                if i < len(providers) - 1:
                                    self.record_failover_event(
                                        capability=capability,
                                        original_provider=provider_name,
                                        target_provider=providers[i + 1][0],
                                        reason=last_error,
                                        latency_ms=duration_ms,
                                    )
                                continue
                    else:
                        # 非行情通用能力保持原有的基本质量校验
                        if result.quality in (DataQuality.INVALID, DataQuality.UNAVAILABLE, DataQuality.FAILED):
                            is_malformed = True
                            last_error = result.error_message or f"Invalid quality {result.quality}"
                            await cb.record_failure(last_error)
                            ht.record_sample(is_success=False, latency_ms=duration_ms, is_malformed=True)
                            continue

                    # 硬成功：合闸并清零失败计数
                    await cb.record_success()
                    ht.record_sample(is_success=True, latency_ms=duration_ms)

                    if i > 0:
                        result.fallback_used = True
                        result.quality = DataQuality.DEGRADED
                    return result
                else:
                    # 返回空包或被判定为无效
                    is_malformed = True
                    last_error = result.error_message if result else "Empty or invalid payload"
                    duration_ms = int((time.perf_counter() - t_start) * 1000)
                    await cb.record_failure(f"MALFORMED_OR_EMPTY: {last_error}")
                    ht.record_sample(
                        is_success=False,
                        latency_ms=duration_ms,
                        is_malformed=True,
                    )
            except asyncio.TimeoutError:
                is_timeout = True
                duration_ms = int((time.perf_counter() - t_start) * 1000)
                last_error = f"Physical request timeout (>{hard_timeout_sec}s)"
                await cb.record_failure("TIMEOUT")
                ht.record_sample(is_success=False, latency_ms=duration_ms, is_timeout=True)
            except Exception as e:
                duration_ms = int((time.perf_counter() - t_start) * 1000)
                last_error = str(e)
                await cb.record_failure(f"EXCEPTION: {last_error}")
                ht.record_sample(is_success=False, latency_ms=duration_ms)

            # 当前源失败，触发级联审计并流向下一级
            if i < len(providers) - 1:
                self.record_failover_event(
                    capability=capability,
                    original_provider=provider_name,
                    target_provider=providers[i + 1][0],
                    reason=f"HARD_FAILURE_{last_error}",
                    latency_ms=duration_ms,
                )

        # 3. 所有外部 Provider 均告失败，终局降级收口规则
        logger.error(
            f"All registered providers failed for capability '{capability}'. Last error: {last_error}"
        )
        if last_good_cache is not None and last_good_cache.data is not None:
            logger.warning(f"Serving STALE cache snapshot for capability '{capability}'")
            return DataResult(
                data=last_good_cache.data,
                quality=DataQuality.DEGRADED,
                freshness=Freshness.STALE,
                provider=last_good_cache.provider,
                error_message=f"All providers failed. Served from STALE snapshot. Last error: {last_error}",
                fallback_used=True,
            )
        else:
            logger.error(f"No valid cache available for capability '{capability}'. Returning UNAVAILABLE.")
            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                freshness=Freshness.UNAVAILABLE,
                provider="all_failed",
                error_message=f"All providers failed and no cache available. Last error: {last_error}",
                fallback_used=True,
            )

registry = ProviderRegistry()
