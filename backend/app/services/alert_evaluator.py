"""
Phase 3B.1: Alert Evaluator, Deduplicator & Lifecycle State Machine
===================================================================
上位依据：
1. 最高董事会裁决令：《VERDICT-PHASE3A-CLOSE-PHASE3B1-GATE-20261009》
2. 《DOC-98 · Phase 3B 盘中多源告警通知总线与受控防御编排技术设计单》

核心设计：
- 严格生命周期状态机: PENDING -> EVALUATING -> ACTIVE -> COOLDOWN / EXPIRED / DROPPED;
- 滑动时间窗口 LRU 去重器 (180s 冷却抑制期)；
- 乱序与迟到物理时戳检测 (Out-of-Order / Delayed Data Flagging)；
- 物理数据年龄精确计算 (Data Age = T_requested - T_observed)；
- 链式防篡改指针绑定 (prev_event_hash 级联)。
"""

import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta
from enum import Enum
from threading import Lock

from backend.app.schemas.canonical_intraday import IntradayStageEnum
from backend.app.schemas.intraday_drift_verdict import (
    DriftStateEnum,
    DriftEventCategoryEnum,
    IntradayDriftVerdict,
)
from backend.app.schemas.canonical_alert_event import (
    CanonicalDriftAlertEvent,
    AlertSeverityEnum,
    AlertCategoryEnum,
    DEDUP_KEY_REGEX,
)
from backend.app.services.alert_bus_ring_buffer import (
    AlertRingBuffer,
    AlertDeadLetterQueue,
)

logger = logging.getLogger(__name__)


class AlertLifecycleStateEnum(str, Enum):
    """告警生命周期状态机枚举"""
    PENDING = "PENDING"          # 待求值
    EVALUATING = "EVALUATING"    # 求值中
    ACTIVE = "ACTIVE"            # 激活生效，已进入 RingBuffer
    COOLDOWN = "COOLDOWN"        # 冷却抑制中 (重复事件被静默)
    EXPIRED = "EXPIRED"          # 已超过有效时限失效
    DROPPED = "DROPPED"          # 格式非法或安全拒止丢弃
    DEAD_LETTER = "DEAD_LETTER"  # 进入死信队列


class AlertDeduplicator:
    """
    滑动窗口告警去重与冷却抑制器
    """
    def __init__(self, cooldown_seconds: float = 180.0, max_keys: int = 10000):
        self.cooldown_seconds = cooldown_seconds
        self.max_keys = max_keys
        # key -> (last_emitted_datetime, emit_count)
        self._history: Dict[str, Tuple[datetime, int]] = {}
        self._lock = Lock()

    def check_and_record(self, dedup_key: str, current_time: datetime) -> Tuple[bool, int]:
        """
        检查指定去重键是否处于冷却期：
        - 返回 (is_suppressed, occurrence_count)
        - 若处于冷却期内：返回 (True, count)
        - 若已过冷却期或新键：记录当前时戳并返回 (False, count)
        """
        with self._lock:
            # 淘汰超量键
            if len(self._history) > self.max_keys:
                oldest_key = min(self._history.keys(), key=lambda k: self._history[k][0])
                del self._history[oldest_key]

            if dedup_key in self._history:
                last_time, count = self._history[dedup_key]
                elapsed = (current_time - last_time).total_seconds()
                if elapsed < self.cooldown_seconds:
                    # 处于冷却抑制期
                    self._history[dedup_key] = (last_time, count + 1)
                    return True, count + 1
                else:
                    # 冷却期已过，重新激活
                    self._history[dedup_key] = (current_time, count + 1)
                    return False, count + 1
            else:
                self._history[dedup_key] = (current_time, 1)
                return False, 1

    def clear(self) -> None:
        with self._lock:
            self._history.clear()


class AlertEvaluator:
    """
    盘中多源告警求值与事件构造器
    """
    def __init__(
        self,
        ring_buffer: Optional[AlertRingBuffer] = None,
        dead_letter_queue: Optional[AlertDeadLetterQueue] = None,
        cooldown_seconds: float = 180.0,
    ):
        self.ring_buffer = ring_buffer or AlertRingBuffer()
        self.dlq = dead_letter_queue or AlertDeadLetterQueue()
        self.deduplicator = AlertDeduplicator(cooldown_seconds=cooldown_seconds)
        self.last_observed_time: Optional[datetime] = None
        self.last_event_hash: Optional[str] = None
        self._lock = Lock()

    def evaluate_and_publish(
        self,
        verdict: IntradayDriftVerdict,
        request_timestamp: Optional[datetime] = None,
    ) -> Tuple[AlertLifecycleStateEnum, Optional[CanonicalDriftAlertEvent], Optional[str]]:
        """
        依据 IntradayDriftVerdict 求值并产出规范告警事件：
        - 检查时效与乱序；
        - 执行去重与抑制；
        - 构造防篡改不可变事件并推入 RingBuffer。
        """
        with self._lock:
            now_tz = datetime.now(timezone(timedelta(hours=8)))
            t_req = request_timestamp or now_tz

            # 1. 解析时戳与数据年龄
            t_obs = datetime.fromisoformat(f"{verdict.trade_date}T{verdict.evaluated_at.split('T')[1]}")
            data_age = max(0.0, (t_req - t_obs).total_seconds())
            is_stale = data_age > 180.0

            # 2. 乱序检测
            is_out_of_order = False
            if self.last_observed_time is not None and t_obs < self.last_observed_time:
                is_out_of_order = True
            elif not is_out_of_order:
                self.last_observed_time = t_obs

            # 3. 映射告警严重度与分类
            if verdict.overall_drift_state == DriftStateEnum.CRITICAL_BREACH:
                severity = AlertSeverityEnum.CRITICAL
                ttl_seconds = 60.0
            elif verdict.overall_drift_state == DriftStateEnum.DRIFT_WARNING:
                severity = AlertSeverityEnum.WARNING
                ttl_seconds = 180.0
            else:
                severity = AlertSeverityEnum.INFO
                ttl_seconds = 300.0

            category = AlertCategoryEnum.STAGE_TRANSITION
            target_symbol = "GLOBAL"
            if verdict.detected_drift_events:
                first_event = verdict.detected_drift_events[0]
                if first_event == DriftEventCategoryEnum.SPACE_LEADER_COLLAPSE:
                    category = AlertCategoryEnum.SPACE_LEADER_COLLAPSE
                elif first_event == DriftEventCategoryEnum.MAINLINE_TOTAL_REVERSAL:
                    category = AlertCategoryEnum.MAINLINE_TOTAL_REVERSAL
                elif first_event == DriftEventCategoryEnum.LIQUIDITY_FLASH_DRY:
                    category = AlertCategoryEnum.LIQUIDITY_FLASH_DRY
                elif first_event == DriftEventCategoryEnum.BREADTH_PANIC_DIVERGENCE:
                    category = AlertCategoryEnum.BREADTH_PANIC_DIVERGENCE

            # 4. 构建规范合法去重键
            dedup_key = f"{verdict.trade_date}:{verdict.stage.value}:{category.value}:{target_symbol}"
            if not DEDUP_KEY_REGEX.match(dedup_key):
                # 异常键注入防卫
                err_msg = f"[INJECTION PREVENTED] Invalid dedup key format: {dedup_key}"
                self.dlq.push(verdict.model_dump(), err_msg)
                return AlertLifecycleStateEnum.DEAD_LETTER, None, err_msg

            # 5. 去重与冷却抑制检查
            is_suppressed, count = self.deduplicator.check_and_record(dedup_key, t_req)
            if is_suppressed and count > 1:
                return AlertLifecycleStateEnum.COOLDOWN, None, f"Suppressed by cooldown ({count} occurrences)"

            # 6. 计算有效期
            t_expires = (now_tz + timedelta(seconds=ttl_seconds)).isoformat()
            alert_id = f"ALERT-{verdict.trade_date}-{verdict.stage.value}-{verdict.verdict_fingerprint[:8]}"

            # 7. 组装未签名事件字典
            raw_event_dict = {
                "alert_id": alert_id,
                "trade_date": verdict.trade_date,
                "observed_at": t_obs.isoformat(),
                "requested_at": t_req.isoformat(),
                "evaluated_at": verdict.evaluated_at,
                "generated_at": now_tz.isoformat(),
                "expires_at": t_expires,
                "data_age_seconds": round(data_age, 3),
                "trace_id": verdict.trace_id,
                "version": "1.0.0",
                "deduplication_key": dedup_key,
                "severity": severity,
                "category": category,
                "stage": verdict.stage,
                "headline": verdict.verdict_headline,
                "detail_facts": {
                    "overall_drift_state": verdict.overall_drift_state.value,
                    "elapsed_trading_minutes": verdict.elapsed_trading_minutes,
                    "assertion_count": len(verdict.assertion_results),
                    "occurrence_count": count,
                },
                "preservation_boundaries": verdict.preservation_boundaries,
                "is_out_of_order": is_out_of_order,
                "is_stale": is_stale,
                "verdict_fingerprint": verdict.verdict_fingerprint,
                "prev_event_hash": self.last_event_hash,
            }

            # 8. 双重计算内容哈希与源端 HMAC 签名
            content_hash = CanonicalDriftAlertEvent.compute_content_hash(raw_event_dict)
            origin_sig = CanonicalDriftAlertEvent.compute_origin_signature(content_hash)
            raw_event_dict["content_hash"] = content_hash
            raw_event_dict["origin_signature"] = origin_sig

            try:
                event = CanonicalDriftAlertEvent(**raw_event_dict)
            except Exception as e:
                err_msg = f"[SCHEMA VIOLATION] Failed to construct alert: {e}"
                self.dlq.push(raw_event_dict, err_msg)
                return AlertLifecycleStateEnum.DEAD_LETTER, None, err_msg

            # 9. 级联更新上一个哈希指针并推入 RingBuffer
            self.last_event_hash = content_hash
            ok, drop_msg = self.ring_buffer.append(event)

            return AlertLifecycleStateEnum.ACTIVE, event, drop_msg
