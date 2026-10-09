"""
Phase 3B.1: In-Memory Alert Ring Buffer & Dead Letter Queue
===========================================================
上位依据：
1. 最高董事会裁决令：《VERDICT-PHASE3A-CLOSE-PHASE3B1-GATE-20261009》
2. 《DOC-98 · Phase 3B 盘中多源告警通知总线与受控防御编排技术设计单》

核心设计：
- 严格有界内存环形队列 (最大容量 1,000 条，杜绝无界增长防 OOM)；
- 关键告警优先保留策略 (CRITICAL Alert Reservation): 优先淘汰非关键告警，关键告警设有刚性保护槽；
- 溢出警告与淘汰计数器 (FIFO Overwrite Warning)；
- 内存死信队列 (Dead Letter Queue, 容量 500 条) 容纳投递失败或恶意毒丸载荷；
- 快照导出/导入能力，支持进程重启边界测试与状态重放。
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from collections import deque
from datetime import datetime, timezone, timedelta
from threading import Lock

from backend.app.schemas.canonical_alert_event import (
    CanonicalDriftAlertEvent,
    AlertSeverityEnum,
)

logger = logging.getLogger(__name__)


class DeadLetterItem:
    """死信队列条目包装器"""
    def __init__(self, event_data: Dict[str, Any], reason: str, timestamp: str):
        self.event_data = event_data
        self.reason = reason
        self.timestamp = timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_data": self.event_data,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class AlertDeadLetterQueue:
    """
    内存有界死信队列 (Dead Letter Queue)
    """
    def __init__(self, capacity: int = 500):
        self.capacity = capacity
        self._queue: deque[DeadLetterItem] = deque(maxlen=capacity)
        self._lock = Lock()
        self.total_dropped_count = 0

    def push(self, event_data: Dict[str, Any], reason: str) -> None:
        """压入死信条目"""
        with self._lock:
            now_iso = datetime.now(timezone(timedelta(hours=8))).isoformat()
            if len(self._queue) >= self.capacity:
                self.total_dropped_count += 1
                logger.warning(f"[DLQ OVERFLOW] Dead Letter Queue full ({self.capacity}). Oldest dead letter discarded.")
            item = DeadLetterItem(event_data=event_data, reason=reason, timestamp=now_iso)
            self._queue.append(item)

    def size(self) -> int:
        with self._lock:
            return len(self._queue)

    def get_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [item.to_dict() for item in self._queue]

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()
            self.total_dropped_count = 0


class AlertRingBuffer:
    """
    内存有界环形告警缓冲区 (Alert Ring Buffer)
    """
    def __init__(self, capacity: int = 1000, critical_reservation_quota: int = 200):
        self.capacity = capacity
        self.critical_reservation_quota = critical_reservation_quota
        self._buffer: List[CanonicalDriftAlertEvent] = []
        self._lock = Lock()
        self.total_overflow_drops = 0
        self.critical_protected_drops = 0

    def append(self, event: CanonicalDriftAlertEvent) -> Tuple[bool, Optional[str]]:
        """
        向环形缓冲区追加告警事件：
        - 若未达容量上限，直接追加；
        - 若已满载，启动关键告警保留策略：
          * 优先淘汰最旧的非 CRITICAL 告警；
          * 若缓冲区全部为 CRITICAL 且已满，淘汰最旧的 CRITICAL 告警。
        """
        with self._lock:
            if len(self._buffer) < self.capacity:
                self._buffer.append(event)
                return True, None

            # 缓冲区已满载，执行受控淘汰
            self.total_overflow_drops += 1
            evicted_index = -1

            # 1. 寻找最旧的非 CRITICAL 告警进行淘汰
            for i, existing in enumerate(self._buffer):
                if existing.severity != AlertSeverityEnum.CRITICAL:
                    evicted_index = i
                    break

            if evicted_index != -1:
                evicted_event = self._buffer.pop(evicted_index)
                self._buffer.append(event)
                msg = f"[RING_BUFFER FIFO] Evicted non-critical alert '{evicted_event.alert_id}' ({evicted_event.severity}) to preserve space."
                logger.info(msg)
                return True, msg
            else:
                # 2. 极端场景：全缓冲全为 CRITICAL 告警
                evicted_event = self._buffer.pop(0)
                self._buffer.append(event)
                self.critical_protected_drops += 1
                msg = f"[RING_BUFFER CRITICAL OVERFLOW] Buffer 100% saturated with CRITICAL alerts. Evicted oldest critical alert '{evicted_event.alert_id}'."
                logger.warning(msg)
                return True, msg

    def size(self) -> int:
        with self._lock:
            return len(self._buffer)

    def get_events(self, limit: Optional[int] = None) -> List[CanonicalDriftAlertEvent]:
        """获取缓冲区内的最新告警事件列表"""
        with self._lock:
            if limit is not None:
                return list(self._buffer[-limit:])
            return list(self._buffer)

    def get_by_id(self, alert_id: str) -> Optional[CanonicalDriftAlertEvent]:
        with self._lock:
            for event in self._buffer:
                if event.alert_id == alert_id:
                    return event
            return None

    def export_snapshot(self) -> List[Dict[str, Any]]:
        """导出当前缓冲区快照，支持无损重放与边界测试"""
        with self._lock:
            return [ev.model_dump() for ev in self._buffer]

    def restore_from_snapshot(self, snapshot: List[Dict[str, Any]]) -> int:
        """从快照恢复缓冲区，模拟进程重启边界"""
        with self._lock:
            self._buffer.clear()
            loaded = 0
            for item in snapshot:
                try:
                    ev = CanonicalDriftAlertEvent(**item)
                    self._buffer.append(ev)
                    loaded += 1
                except Exception as e:
                    logger.error(f"[RESTORE ERROR] Failed to parse item: {e}")
            return loaded

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
            self.total_overflow_drops = 0
            self.critical_protected_drops = 0
