"""
M2 盘前事实抽取适配器（M2 Premarket Fact Adapter）
上位依据：BOARD-APPROVAL-20260930-STEP3（第五条：M2 事实规范化）
核心铁律：只能抽取外部事实与原始指标文本，严禁将新闻或宏观材料加工成市场观点或买卖倾向！
"""

import json
from typing import List, Dict, Any, Optional
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


class M2PremarketFactAdapter(BaseFactAdapter):
    """M2 盘前宏观事实适配器"""

    def extract_facts(
        self,
        raw_data: Any,
        clock: DeterministicClock,
        trace_id: str,
        market_date: Optional[str] = None,
        **kwargs: Any,
    ) -> List[FactItem]:
        facts: List[FactItem] = []

        date_str = market_date
        rec_id = "unknown"
        ingestion_time_str = clock.now_iso()
        overnight_raw = None
        news_digest_raw = None
        today_focus_raw = None
        source_name = "premarket_briefing"

        if hasattr(raw_data, "__table__"):
            rec_id = str(getattr(raw_data, "id", "db_row"))
            date_str = date_str or getattr(raw_data, "date", None)
            created_at = getattr(raw_data, "generated_at", None)
            if created_at:
                ingestion_time_str = created_at.strftime("%Y-%m-%dT%H:%M:%S.000+08:00")
            overnight_raw = getattr(raw_data, "overnight_summary", None)
            news_digest_raw = getattr(raw_data, "news_digest", None)
            today_focus_raw = getattr(raw_data, "today_focus", None)
        elif isinstance(raw_data, dict):
            date_str = date_str or raw_data.get("date")
            rec_id = str(raw_data.get("id", "dict_m2"))
            overnight_raw = raw_data.get("overnight_summary")
            news_digest_raw = raw_data.get("news_digest")
            today_focus_raw = raw_data.get("today_focus")
            source_name = raw_data.get("source", "premarket_briefing")

        date_str = date_str or clock.now_iso()[:10]
        event_time_str = f"{date_str}T08:30:00.000+08:00"
        observed_time_str = clock.now_iso()
        effective_time_str = event_time_str

        t_ctx = FourDimensionalTime(
            event_time=event_time_str,
            observed_time=observed_time_str,
            ingestion_time=ingestion_time_str,
            effective_time=effective_time_str,
        )
        prov = Provenance(
            primary_source=source_name,
            trace_id=trace_id,
        )

        # 1. 抽取隔夜外盘事实 (macro.overnight)
        overnight_list = []
        if isinstance(overnight_raw, str):
            try:
                overnight_list = json.loads(overnight_raw)
            except Exception:
                overnight_list = []
        elif isinstance(overnight_raw, list):
            overnight_list = overnight_raw

        status_overnight = FactStatus.AVAILABLE if overnight_list else FactStatus.MISSING
        facts.append(
            self.create_fact_item(
                fact_key="macro.overnight",
                fact_type=FactType.OVERNIGHT_MACRO,
                time_context=t_ctx,
                status=status_overnight,
                freshness=Freshness.REALTIME if overnight_list else Freshness.UNKNOWN,
                source=source_name,
                source_record_id=rec_id,
                payload={"symbols": overnight_list} if overnight_list else None,
                provenance=prov,
                clock=clock,
            )
        )

        # 2. 抽取宏观要闻摘要 (macro.news_digest) - 保持纯文本事实
        news_list = []
        if isinstance(news_digest_raw, str):
            try:
                parsed_news = json.loads(news_digest_raw)
                news_list = parsed_news if isinstance(parsed_news, list) else [parsed_news]
            except Exception:
                news_list = [{"raw_text": news_digest_raw}] if news_digest_raw else []
        elif isinstance(news_digest_raw, list):
            news_list = news_digest_raw

        status_news = FactStatus.AVAILABLE if news_list else FactStatus.EMPTY
        facts.append(
            self.create_fact_item(
                fact_key="macro.news_digest",
                fact_type=FactType.NEWS_BULLETIN,
                time_context=t_ctx,
                status=status_news,
                freshness=Freshness.REALTIME,
                source=source_name,
                source_record_id=rec_id,
                payload={"items": news_list},
                provenance=prov,
                clock=clock,
            )
        )

        # 3. 抽取盘前今日关注客观观察点 (macro.today_focus)
        focus_list = []
        if isinstance(today_focus_raw, str):
            try:
                parsed_focus = json.loads(today_focus_raw)
                focus_list = parsed_focus if isinstance(parsed_focus, list) else [parsed_focus]
            except Exception:
                focus_list = []
        elif isinstance(today_focus_raw, list):
            focus_list = today_focus_raw

        status_focus = FactStatus.AVAILABLE if focus_list else FactStatus.MISSING
        facts.append(
            self.create_fact_item(
                fact_key="macro.today_focus",
                fact_type=FactType.OVERNIGHT_MACRO,
                time_context=t_ctx,
                status=status_focus,
                freshness=Freshness.REALTIME if focus_list else Freshness.UNKNOWN,
                source=source_name,
                source_record_id=rec_id,
                payload={"focus_points": focus_list} if focus_list else None,
                provenance=prov,
                clock=clock,
            )
        )

        return facts
