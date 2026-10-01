"""
确定性时钟与标识生成器（Deterministic Clock & ID Provider）
上位依据：BOARD-APPROVAL-20260930-STEP3（第七条：时钟与标识支持确定性注入）
核心铁律：禁止在推演或快照计算中直接调用未受控的 datetime.now()、time.time() 或 uuid.uuid4()。
"""

from datetime import datetime, timezone, timedelta
import hashlib
from typing import Optional


# 统一时区为 Asia/Shanghai (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))


class DeterministicClock:
    """
    确定性时钟与 ID 生成器
    在测试和沙箱重放中，提供毫秒级完全可控的时间推进与散列 ID 生成，保证 100% Bit-Exact 确定性。
    """

    def __init__(self, fixed_iso_time: str = "2026-09-30T09:25:00.000+08:00"):
        self._current_time: datetime = datetime.fromisoformat(fixed_iso_time)
        if self._current_time.tzinfo is None:
            self._current_time = self._current_time.replace(tzinfo=BEIJING_TZ)
        self._seq_counter: int = 0

    @property
    def current_time(self) -> datetime:
        return self._current_time

    def now(self) -> datetime:
        return self._current_time

    def now_iso(self) -> str:
        """返回严格格式化的 ISO-8601 UTC+8 时间串 (带毫秒)"""
        return self._current_time.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+08:00"

    def advance_seconds(self, seconds: float) -> str:
        """时钟单调向前推进一步"""
        self._current_time += timedelta(seconds=seconds)
        return self.now_iso()

    def generate_trace_id(self, seed: Optional[str] = None) -> str:
        """根据确定性种子生成 Trace ID"""
        self._seq_counter += 1
        s = f"trace_{seed or 'default'}_{self.now_iso()}_{self._seq_counter}"
        h = hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
        return f"trace_{h}"

    def generate_id(self, prefix: str, seed: Optional[str] = None) -> str:
        """根据确定性前缀与种子生成对象唯一 ID"""
        self._seq_counter += 1
        s = f"{prefix}_{seed or 'id'}_{self.now_iso()}_{self._seq_counter}"
        h = hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]
        return f"{prefix}_{h}"
