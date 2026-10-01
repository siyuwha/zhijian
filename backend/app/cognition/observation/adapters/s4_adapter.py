"""
S4 快讯流事实抽取适配器（S4 News Fact Adapter）
上位依据：BOARD-APPROVAL-20260930-STEP3（第四条与第五条：S4 事实规范化与 Fallback Provenance）
核心铁律：
- 严格保留双源事实与主备切换全息血缘 (Fallback Provenance)
- CLS 超时切换 Sina 时，必须同时记录 CLS 超时详情与 Sina 接管痕迹
- 严禁将 source priority 偷渡为 conflict resolution 裁决
- 保留重复与乱序到达原貌，不得静默丢失证据
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from .base import BaseFactAdapter
from ..contracts import (
    FactItem,
    FactType,
    FactStatus,
    Freshness,
    FourDimensionalTime,
    Provenance,
)
from ..clock import DeterministicClock


class S4NewsFactAdapter(BaseFactAdapter):
    """S4 滚动资讯事实适配器"""

    def extract_facts(
        self,
        raw_news_items: List[Any],
        clock: DeterministicClock,
        trace_id: str,
        fallback_meta: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> List[FactItem]:
        facts: List[FactItem] = []
        observed_time_str = clock.now_iso()

        # 检查是否存在主备切换元数据
        fallback_occurred = False
        primary_source = "cls"
        fallback_source = None
        fallback_reason = None
        primary_error_detail = None

        if fallback_meta:
            fallback_occurred = fallback_meta.get("fallback_occurred", False)
            primary_source = fallback_meta.get("primary_source", "cls")
            fallback_source = fallback_meta.get("fallback_source", "sina")
            fallback_reason = fallback_meta.get("fallback_reason")
            primary_error_detail = fallback_meta.get("primary_error_detail")

        seen_titles = {}
        for idx, raw in enumerate(raw_news_items):
            title = ""
            brief = ""
            pub_time_raw = ""
            rec_id = f"news_{idx}"
            source = fallback_source or primary_source
            ingestion_time_str = clock.now_iso()

            if hasattr(raw, "__table__"):
                rec_id = str(getattr(raw, "id", rec_id))
                source = getattr(raw, "source", source)
                title = getattr(raw, "title", "")
                brief = getattr(raw, "brief", "")
                pub_time_raw = str(getattr(raw, "publish_time", ""))
                created_at = getattr(raw, "collected_at", None)
                if created_at:
                    ingestion_time_str = created_at.strftime("%Y-%m-%dT%H:%M:%S.000+08:00")
            elif isinstance(raw, dict):
                rec_id = str(raw.get("id", rec_id))
                source = raw.get("source", source)
                title = raw.get("title", "")
                brief = raw.get("brief", "")
                pub_time_raw = str(raw.get("publish_time", ""))

            # 规范化 publish_time 为 event_time (秒级时间戳或标准格式)
            if pub_time_raw.isdigit():
                # UNIX 时间戳
                ts = int(pub_time_raw)
                event_time_str = datetime.fromtimestamp(ts, tz=clock.current_time.tzinfo).strftime(
                    "%Y-%m-%dT%H:%M:%S.000+08:00"
                )
            elif "T" in pub_time_raw:
                event_time_str = pub_time_raw
            else:
                event_time_str = f"{clock.now_iso()[:10]}T{pub_time_raw or '09:00:00'}.000+08:00"

            effective_time_str = event_time_str
            t_ctx = FourDimensionalTime(
                event_time=event_time_str,
                observed_time=observed_time_str,
                ingestion_time=ingestion_time_str,
                effective_time=effective_time_str,
            )

            # 重复性检测（保全重复痕迹，严禁静默删除）
            duplicate_detected = False
            dup_count = 0
            if title in seen_titles:
                duplicate_detected = True
                seen_titles[title] += 1
                dup_count = seen_titles[title]
            else:
                seen_titles[title] = 0

            prov = Provenance(
                primary_source=primary_source,
                fallback_occurred=fallback_occurred,
                fallback_source=fallback_source,
                fallback_reason=fallback_reason,
                primary_error_detail=primary_error_detail,
                trace_id=trace_id,
                duplicate_detected=duplicate_detected,
                duplicate_count=dup_count,
                original_arrival_order=idx,
            )

            fact_key = f"news.item_{idx}"
            facts.append(
                self.create_fact_item(
                    fact_key=fact_key,
                    fact_type=FactType.NEWS_BULLETIN,
                    time_context=t_ctx,
                    status=FactStatus.AVAILABLE if title else FactStatus.EMPTY,
                    freshness=Freshness.REALTIME,
                    source=source,
                    source_record_id=rec_id,
                    payload={
                        "title": title,
                        "brief": brief,
                        "publish_time": pub_time_raw,
                    },
                    provenance=prov,
                    clock=clock,
                )
            )

        return facts
