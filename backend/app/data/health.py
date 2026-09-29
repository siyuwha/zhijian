import collections
import logging
import time
from dataclasses import dataclass
from typing import Deque, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class HealthSample:
    timestamp: float
    is_success: bool
    latency_ms: int
    is_timeout: bool = False
    is_malformed: bool = False
    staleness_seconds: float = 0.0

class HealthTracker:
    """
    P2 Provider 健康度度量追踪器 (Observability & Soft Routing)
    
    职责边界铁律：
    1. 负责全链路可观测性大盘、监控告警等级判定与动态软路由流量配比
    2. 无论健康分如何波动，绝对禁止直接触发断路器 OPEN！
    """

    def __init__(
        self,
        provider_name: str,
        window_seconds: float = 300.0,
        max_samples: int = 100,
    ):
        self.provider_name = provider_name
        self.window_seconds = window_seconds
        self.max_samples = max_samples
        self.samples: Deque[HealthSample] = collections.deque(maxlen=max_samples)
        self.consecutive_failures: int = 0

    def record_sample(
        self,
        is_success: bool,
        latency_ms: int,
        is_timeout: bool = False,
        is_malformed: bool = False,
        staleness_seconds: float = 0.0,
    ):
        now = time.time()
        sample = HealthSample(
            timestamp=now,
            is_success=is_success,
            latency_ms=latency_ms,
            is_timeout=is_timeout,
            is_malformed=is_malformed,
            staleness_seconds=staleness_seconds,
        )
        self.samples.append(sample)

        if is_success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1

    def _clean_expired(self, now: float):
        cutoff = now - self.window_seconds
        while self.samples and self.samples[0].timestamp < cutoff:
            self.samples.popleft()

    def calculate_health(self) -> dict:
        now = time.time()
        self._clean_expired(now)

        total = len(self.samples)
        if total == 0:
            return {
                "provider": self.provider_name,
                "health_score": 100.0,
                "grade": "HEALTHY",
                "sample_count": 0,
                "success_rate": 1.0,
                "timeout_rate": 0.0,
                "malformed_rate": 0.0,
                "p90_latency_ms": 0,
                "consecutive_failures": self.consecutive_failures,
            }

        success_count = sum(1 for s in self.samples if s.is_success)
        timeout_count = sum(1 for s in self.samples if s.is_timeout)
        malformed_count = sum(1 for s in self.samples if s.is_malformed)

        sr = success_count / total
        tr = timeout_count / total
        mr = malformed_count / total

        latencies = sorted(s.latency_ms for s in self.samples)
        p50 = latencies[int(len(latencies) * 0.50)]
        p90 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.90))]
        p99 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.99))]

        max_staleness = max((s.staleness_seconds for s in self.samples), default=0.0)

        # 加权扣分惩罚因子计算
        penalty_error = (1.0 - sr) * 60.0
        penalty_latency = min(20.0, max(0.0, (p90 - 1000.0) / 200.0))
        penalty_consecutive = min(40.0, self.consecutive_failures * 10.0)
        penalty_stale = min(20.0, max(0.0, (max_staleness - 30.0) / 5.0))

        score = max(0.0, 100.0 - penalty_error - penalty_latency - penalty_consecutive - penalty_stale)
        score = round(score, 1)

        if score >= 80.0:
            grade = "HEALTHY"
        elif score >= 60.0:
            grade = "SUSPICIOUS"
        elif score >= 40.0:
            grade = "DEGRADED"
        else:
            grade = "CRITICAL"

        return {
            "provider": self.provider_name,
            "health_score": score,
            "grade": grade,
            "sample_count": total,
            "success_rate": round(sr, 3),
            "timeout_rate": round(tr, 3),
            "malformed_rate": round(mr, 3),
            "p50_latency_ms": p50,
            "p90_latency_ms": p90,
            "p99_latency_ms": p99,
            "consecutive_failures": self.consecutive_failures,
        }
