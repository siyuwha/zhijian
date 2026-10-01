"""
M5 历史结算价事实抽取适配器（M5 Settlement Price Fact Adapter）
上位依据：BOARD-APPROVAL-20260930-STEP3（第五条：M5 事实规范化）
核心铁律：
- 严格保全 Baostock 超时与缓存降级的真实状态（TIMEOUT / STALE）
- 超时或错误时严禁进行 0 填充
- 准确记录本地缓存来源与回退事实血缘
"""

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


class M5SettlementFactAdapter(BaseFactAdapter):
    """M5 标的结算价事实适配器"""

    def extract_facts(
        self,
        raw_data: Any,
        clock: DeterministicClock,
        trace_id: str,
        market_date: Optional[str] = None,
        symbol: Optional[str] = None,
        **kwargs: Any,
    ) -> List[FactItem]:
        facts: List[FactItem] = []

        code = symbol or "unknown_symbol"
        date_str = market_date
        rec_id = "unknown"
        ingestion_time_str = clock.now_iso()
        status_str = "AVAILABLE"
        source_name = "baostock"
        close_price = None
        prev_close = None
        volume = None
        amount = None
        pct_change = None

        if hasattr(raw_data, "__table__"):
            # MarketSettlementCache ORM 实例
            rec_id = str(getattr(raw_data, "id", "db_row"))
            code = getattr(raw_data, "code", code)
            date_str = getattr(raw_data, "date", date_str)
            close_price = getattr(raw_data, "close", None)
            prev_close = getattr(raw_data, "prev_close", None)
            volume = getattr(raw_data, "volume", None)
            amount = getattr(raw_data, "amount", None)
            pct_change = getattr(raw_data, "pct_change", None)
            source_name = getattr(raw_data, "source", "baostock_local_cache")
            status_str = getattr(raw_data, "status", "AVAILABLE")
            created_at = getattr(raw_data, "created_at", None)
            if created_at:
                ingestion_time_str = created_at.strftime("%Y-%m-%dT%H:%M:%S.000+08:00")
        elif isinstance(raw_data, dict):
            rec_id = str(raw_data.get("id", "dict_m5"))
            code = raw_data.get("code", code)
            date_str = raw_data.get("date", date_str)
            close_price = raw_data.get("close")
            prev_close = raw_data.get("prev_close")
            volume = raw_data.get("volume")
            amount = raw_data.get("amount")
            pct_change = raw_data.get("pct_change")
            source_name = raw_data.get("source", "baostock")
            status_str = raw_data.get("status", "AVAILABLE")

        clean_code = str(code).lower().replace("sh", "").replace("sz", "")
        fact_key = f"settlement.{clean_code}"
        date_str = date_str or clock.now_iso()[:10]
        event_time_str = f"{date_str}T15:00:00.000+08:00"
        observed_time_str = clock.now_iso()
        effective_time_str = event_time_str

        t_ctx = FourDimensionalTime(
            event_time=event_time_str,
            observed_time=observed_time_str,
            ingestion_time=ingestion_time_str,
            effective_time=effective_time_str,
        )

        fallback_used = "cache" in source_name or status_str == "STALE"
        prov = Provenance(
            primary_source="baostock",
            fallback_occurred=fallback_used,
            fallback_source=source_name if fallback_used else None,
            fallback_reason="TIMEOUT_FALLBACK_TO_LOCAL_CACHE" if fallback_used else None,
            trace_id=trace_id,
        )

        # 状态判定与零填充防御
        if status_str in ("TIMEOUT", FactStatus.TIMEOUT.value):
            final_status = FactStatus.TIMEOUT
            final_freshness = Freshness.UNKNOWN
            final_payload = None  # 零填充防伪：超时绝不补 0.0
        elif status_str in ("ERROR", FactStatus.ERROR.value):
            final_status = FactStatus.ERROR
            final_freshness = Freshness.UNKNOWN
            final_payload = None
        elif status_str in ("STALE", FactStatus.STALE.value) or fallback_used:
            final_status = FactStatus.STALE
            final_freshness = Freshness.STALE
            final_payload = {
                "code": clean_code,
                "date": date_str,
                "close": close_price,
                "prev_close": prev_close,
                "volume": volume,
                "amount": amount,
                "pct_change": pct_change,
            }
        else:
            final_status = FactStatus.AVAILABLE
            final_freshness = Freshness.REALTIME
            final_payload = {
                "code": clean_code,
                "date": date_str,
                "close": close_price,
                "prev_close": prev_close,
                "volume": volume,
                "amount": amount,
                "pct_change": pct_change,
            }

        facts.append(
            self.create_fact_item(
                fact_key=fact_key,
                fact_type=FactType.SETTLEMENT_PRICE,
                time_context=t_ctx,
                status=final_status,
                freshness=final_freshness,
                source=source_name,
                source_record_id=rec_id,
                payload=final_payload,
                provenance=prov,
                clock=clock,
            )
        )

        return facts
