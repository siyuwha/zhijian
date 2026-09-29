import asyncio
import collections
import logging
import time
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class Singleflight:
    """
    协程请求单飞合并器 (Request Coalescing)
    多个并发任务请求相同 Key 时，仅放行首个协程执行物理 I/O，其余协程共享相同 Future 返回结果。
    """

    def __init__(self):
        self._in_flight: Dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()
        self.coalesced_count: int = 0

    async def execute(
        self,
        key: str,
        fn: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Tuple[Any, bool]:
        """
        执行单飞合并
        返回值: (result, is_leader)
        - is_leader 为 True: 表示当前协程作为 Leader 执行了物理任务
        - is_leader 为 False: 表示当前协程通过单飞等待复用了 Leader 的结果
        """
        async with self._lock:
            if key in self._in_flight:
                # 已有任务在进行中，当前协程作为 Follower 等待
                self.coalesced_count += 1
                fut = self._in_flight[key]
                is_leader = False
            else:
                # 首个协程，成为 Leader 并创建 Future
                loop = asyncio.get_running_loop()
                fut = loop.create_future()
                self._in_flight[key] = fut
                is_leader = True

        if not is_leader:
            # 挂起等待 Leader 广播完成
            result = await fut
            return result, False

        # Leader 执行实际物理函数
        try:
            result = await fn()
            if not fut.done():
                fut.set_result(result)
            return result, True
        except Exception as e:
            if not fut.done():
                fut.set_exception(e)
            raise e
        finally:
            async with self._lock:
                self._in_flight.pop(key, None)


class RequestBudget:
    """
    分钟物理请求预算控制器 (Minute Request Budget)
    严格限制单个域名在 60 秒滑动窗口内的最大物理网络调用次数 (B_max)。
    """

    def __init__(self, default_budget_per_min: int = 60):
        self.default_budget_per_min = default_budget_per_min
        # domain -> deque of timestamps
        self._requests: Dict[str, collections.deque] = collections.defaultdict(collections.deque)
        self._custom_budgets: Dict[str, int] = {
            "sina": 60,
            "eastmoney": 60,
            "baostock": 30,
            "cls": 30,
        }
        self._lock = asyncio.Lock()
        self.rejected_count: int = 0

    def get_budget(self, domain_or_provider: str) -> int:
        return self._custom_budgets.get(domain_or_provider.lower(), self.default_budget_per_min)

    async def acquire(self, domain_or_provider: str) -> bool:
        """
        尝试扣减分钟预算
        - 返回 True: 预算充裕，允许发起物理请求
        - 返回 False: 预算耗尽，强制拦截并触发降级兜底
        """
        key = domain_or_provider.lower()
        b_max = self.get_budget(key)
        now = time.time()
        cutoff = now - 60.0

        async with self._lock:
            q = self._requests[key]
            while q and q[0] < cutoff:
                q.popleft()

            if len(q) >= b_max:
                self.rejected_count += 1
                logger.warning(
                    f"RequestBudget [{key}]: Minute budget exhausted ({len(q)} >= {b_max} req/min)! "
                    f"Blocking physical network request and triggering fallback."
                )
                return False

            q.append(now)
            return True

    async def get_current_usage(self, domain_or_provider: str) -> int:
        key = domain_or_provider.lower()
        now = time.time()
        cutoff = now - 60.0
        async with self._lock:
            q = self._requests[key]
            while q and q[0] < cutoff:
                q.popleft()
            return len(q)


class RateLimiter:
    """
    滑动令牌平滑限流器 (Rate Limiter)
    限制单秒最大请求速率 (如 5 req/s)，通过异步微休眠平滑削峰。
    """

    def __init__(self, default_rate_per_sec: float = 5.0):
        self.default_rate_per_sec = default_rate_per_sec
        self._last_request_time: Dict[str, float] = collections.defaultdict(float)
        self._lock = asyncio.Lock()

    async def acquire(self, domain_or_provider: str, max_wait_sec: float = 1.0) -> bool:
        key = domain_or_provider.lower()
        min_interval = 1.0 / self.default_rate_per_sec
        now = time.time()

        async with self._lock:
            last = self._last_request_time[key]
            elapsed = now - last
            if elapsed < min_interval:
                wait_needed = min_interval - elapsed
                if wait_needed > max_wait_sec:
                    return False
                self._last_request_time[key] = now + wait_needed
            else:
                wait_needed = 0.0
                self._last_request_time[key] = now

        if wait_needed > 0:
            await asyncio.sleep(wait_needed)

        return True


class DomainSemaphore:
    """
    域名并发信号量管理器 (Per-Domain Concurrency Semaphore)
    控制对单一外部数据源的最大物理并发 TCP/HTTP 连接数。
    """

    def __init__(self):
        self._semaphores: Dict[str, asyncio.Semaphore] = {
            "sina": asyncio.Semaphore(2),
            "eastmoney": asyncio.Semaphore(3),
            "baostock": asyncio.Semaphore(1),  # Baostock 本地进程严格单并发
            "cls": asyncio.Semaphore(2),
            "default": asyncio.Semaphore(2),
        }

    def get_semaphore(self, domain_or_provider: str) -> asyncio.Semaphore:
        key = domain_or_provider.lower()
        if key not in self._semaphores:
            self._semaphores[key] = asyncio.Semaphore(2)
        return self._semaphores[key]
