import asyncio
import logging
import time
from enum import Enum
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class CircuitState(str, Enum):
    """断路器三态"""
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreaker:
    """
    P2 工业级确定性硬断路器 (Deterministic Circuit Breaker)
    
    硬规则：
    1. 触发跳闸只由确定性硬失败驱动 (连续失败 CF >= failure_threshold)
    2. 绝不与 Health Score 耦合，调优健康分不影响硬跳闸行为
    3. HALF_OPEN 状态强制单并发探针 (Probe Concurrency Lock)
    4. 探针失败执行指数退避 (60s -> 120s -> 240s -> 600s)
    """

    def __init__(
        self,
        provider_name: str,
        failure_threshold: int = 5,
        base_cooldown_seconds: float = 60.0,
        max_cooldown_seconds: float = 600.0,
    ):
        self.provider_name = provider_name
        self.failure_threshold = failure_threshold
        self.base_cooldown_seconds = base_cooldown_seconds
        self.max_cooldown_seconds = max_cooldown_seconds

        self.state: CircuitState = CircuitState.CLOSED
        self.consecutive_failures: int = 0
        self.current_cooldown: float = base_cooldown_seconds
        self.opened_at: Optional[float] = None
        self.last_probe_time: Optional[float] = None
        self._probe_lock = asyncio.Lock()
        self._lock = asyncio.Lock()

    async def can_execute(self) -> Tuple[bool, bool]:
        """
        检查当前断路器是否允许执行物理请求。
        返回值: (allow_execution, is_probe_request)
        - 若处于 CLOSED: (True, False)
        - 若处于 OPEN:
          - 若冷却时间到期: 尝试晋升为 HALF_OPEN 并获取探针锁 -> (True, True) 或 (False, False)
          - 若冷却时间未到: 本地短路拦截 Fast-Fail -> (False, False)
        - 若处于 HALF_OPEN:
          - 若能获取探针锁: (True, True)
          - 探针已有协程在执行: (False, False) (其他流量继续走备用源)
        """
        now = time.time()
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True, False

            if self.state == CircuitState.OPEN:
                if self.opened_at and (now - self.opened_at) >= self.current_cooldown:
                    # 冷却到期，跃迁为 HALF_OPEN
                    self.state = CircuitState.HALF_OPEN
                    logger.info(
                        f"CircuitBreaker [{self.provider_name}]: Cooldown expired ({self.current_cooldown}s), "
                        f"transitioning OPEN -> HALF_OPEN"
                    )
                else:
                    # 处于熔断冷却期，直接 Fast-Fail 拦截 (0 网络 I/O)
                    return False, False

            if self.state == CircuitState.HALF_OPEN:
                # 仅允许 1 个并发探针
                if not self._probe_lock.locked():
                    await self._probe_lock.acquire()
                    self.last_probe_time = now
                    logger.info(f"CircuitBreaker [{self.provider_name}]: Acquired probe lock in HALF_OPEN")
                    return True, True
                else:
                    return False, False

        return False, False

    async def record_success(self):
        """记录硬成功，重置计数器并合闸"""
        async with self._lock:
            prev_state = self.state
            self.consecutive_failures = 0
            self.current_cooldown = self.base_cooldown_seconds
            self.opened_at = None
            self.state = CircuitState.CLOSED

            if self._probe_lock.locked():
                self._probe_lock.release()

            if prev_state != CircuitState.CLOSED:
                logger.info(
                    f"CircuitBreaker [{self.provider_name}]: Probed successfully! Transitioning {prev_state} -> CLOSED"
                )

    async def record_failure(self, error_message: str = ""):
        """记录确定性硬失败"""
        now = time.time()
        async with self._lock:
            self.consecutive_failures += 1

            if self.state == CircuitState.HALF_OPEN:
                # 探针探测失败，指数退避翻倍后重新跳开
                self.current_cooldown = min(self.max_cooldown_seconds, self.current_cooldown * 2.0)
                self.state = CircuitState.OPEN
                self.opened_at = now
                if self._probe_lock.locked():
                    self._probe_lock.release()
                logger.warning(
                    f"CircuitBreaker [{self.provider_name}]: Probe failed! Transitioning HALF_OPEN -> OPEN "
                    f"(new cooldown: {self.current_cooldown}s). Reason: {error_message}"
                )
            elif self.state == CircuitState.CLOSED:
                if self.consecutive_failures >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    self.opened_at = now
                    self.current_cooldown = self.base_cooldown_seconds
                    logger.warning(
                        f"CircuitBreaker [{self.provider_name}]: Consecutive hard failures ({self.consecutive_failures} >= {self.failure_threshold})! "
                        f"Transitioning CLOSED -> OPEN (cooldown: {self.current_cooldown}s). Reason: {error_message}"
                    )
            elif self.state == CircuitState.OPEN:
                # 保持 OPEN，如果探针锁未释放则释放
                if self._probe_lock.locked():
                    self._probe_lock.release()

    def get_status(self) -> dict:
        """获取断路器当前状态快照"""
        return {
            "provider": self.provider_name,
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "current_cooldown": self.current_cooldown,
            "opened_at": self.opened_at,
        }
