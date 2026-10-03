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


class M5IntradayFactAdapter(BaseFactAdapter):
    """M5 盘中宏观分时时序与异动事件事实抽取适配器"""

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
        source_name = "intraday_monitor"
        raw_snapshots: List[Any] = []
        raw_events: List[Any] = []

        if isinstance(raw_data, dict):
            date_str = date_str or raw_data.get("date")
            rec_id = str(raw_data.get("id", "dict_intraday"))
            source_name = raw_data.get("source", "intraday_monitor")
            raw_snapshots = raw_data.get("snapshots") or raw_data.get("intraday_snapshots") or []
            raw_events = raw_data.get("events") or raw_data.get("anomaly_events") or []
        elif isinstance(raw_data, list):
            date_str = date_str or clock.now_iso()[:10]
            if raw_data:
                first = raw_data[0]
                if hasattr(first, "event_category") or (isinstance(first, dict) and "event_category" in first):
                    raw_events = raw_data
                else:
                    raw_snapshots = raw_data
        elif hasattr(raw_data, "__table__"):
            date_str = date_str or getattr(raw_data, "date", None)
            rec_id = str(getattr(raw_data, "id", "db_row"))
            if hasattr(raw_data, "event_category"):
                raw_events = [raw_data]
            else:
                raw_snapshots = [raw_data]

        date_str = date_str or clock.now_iso()[:10]

        # 1. 抽取 5分钟宏观时序切片事实 (intraday.series)
        norm_snapshots = []
        latest_time = "09:30:00"
        for snap in raw_snapshots:
            if hasattr(snap, "__table__"):
                ts = str(getattr(snap, "timestamp", ""))
                mi = int(getattr(snap, "minute_index", 0))
                sh_p = getattr(snap, "sh_index_price", None)
                sh_pct = getattr(snap, "sh_index_pct", None)
                sz_p = getattr(snap, "sz_index_price", None)
                sz_pct = getattr(snap, "sz_index_pct", None)
                cy_pct = getattr(snap, "cy_index_pct", None)
                amt = getattr(snap, "total_amount_yi", None)
                vol_proj = getattr(snap, "volume_proj_yi", None)
                is_est = getattr(snap, "is_proj_estimated", False)
                up_cnt = getattr(snap, "up_count", None)
                down_cnt = getattr(snap, "down_count", None)
                lu_cnt = getattr(snap, "limit_up_count", None)
                ld_cnt = getattr(snap, "limit_down_count", None)
                broken_cnt = getattr(snap, "broken_limit_count", None)
                max_h = getattr(snap, "max_height", None)
                leader = getattr(snap, "leader_stock", None)
            elif isinstance(snap, dict):
                ts = str(snap.get("timestamp", ""))
                mi = int(snap.get("minute_index", 0))
                sh_p = snap.get("sh_index_price")
                sh_pct = snap.get("sh_index_pct")
                sz_p = snap.get("sz_index_price")
                sz_pct = snap.get("sz_index_pct")
                cy_pct = snap.get("cy_index_pct")
                amt = snap.get("total_amount_yi")
                vol_proj = snap.get("volume_proj_yi")
                is_est = snap.get("is_proj_estimated", False)
                up_cnt = snap.get("up_count")
                down_cnt = snap.get("down_count")
                lu_cnt = snap.get("limit_up_count")
                ld_cnt = snap.get("limit_down_count")
                broken_cnt = snap.get("broken_limit_count")
                max_h = snap.get("max_height")
                leader = snap.get("leader_stock")
            else:
                continue

            if ts > latest_time:
                latest_time = ts

            norm_snapshots.append({
                "timestamp": ts,
                "minute_index": mi,
                "sh_index_price": sh_p,
                "sh_index_pct": sh_pct,
                "sz_index_price": sz_p,
                "sz_index_pct": sz_pct,
                "cy_index_pct": cy_pct,
                "total_amount_yi": amt,
                "volume_proj_yi": vol_proj,
                "is_proj_estimated": is_est,
                "up_count": up_cnt,
                "down_count": down_cnt,
                "limit_up_count": lu_cnt,
                "limit_down_count": ld_cnt,
                "broken_limit_count": broken_cnt,
                "max_height": max_h,
                "leader_stock": leader,
            })

        t_ctx_series = FourDimensionalTime(
            event_time=f"{date_str}T{latest_time}.000+08:00" if len(latest_time) == 8 else f"{date_str}T15:00:00.000+08:00",
            observed_time=clock.now_iso(),
            ingestion_time=clock.now_iso(),
            effective_time=f"{date_str}T{latest_time}.000+08:00" if len(latest_time) == 8 else f"{date_str}T15:00:00.000+08:00",
        )
        prov_series = Provenance(
            primary_source=source_name,
            trace_id=trace_id,
        )

        status_series = FactStatus.AVAILABLE if len(norm_snapshots) > 0 else FactStatus.EMPTY
        payload_series = {
            "count": len(norm_snapshots),
            "snapshots": norm_snapshots,
        } if len(norm_snapshots) > 0 else {"count": 0, "snapshots": []}

        facts.append(
            self.create_fact_item(
                fact_key="intraday.series",
                fact_type=FactType.INTRADAY_SERIES,
                time_context=t_ctx_series,
                status=status_series,
                freshness=Freshness.REALTIME,
                source=source_name,
                source_record_id=rec_id,
                payload=payload_series,
                provenance=prov_series,
                clock=clock,
            )
        )

        # 2. 抽取盘中异动与相变事件事实 (intraday.anomaly)
        norm_events = []
        latest_event_time = "09:30:00"
        for evt in raw_events:
            if hasattr(evt, "__table__"):
                ts = str(getattr(evt, "timestamp", ""))
                mi = int(getattr(evt, "minute_index", 0))
                cat = getattr(evt, "event_category", "UNKNOWN")
                sev = getattr(evt, "severity_level", "INFO")
                sym = getattr(evt, "symbol", None)
                nm = getattr(evt, "name", None)
                prc = getattr(evt, "price", None)
                pct = getattr(evt, "pct_change", None)
                w_pct = getattr(evt, "window_delta_pct", None)
                w_amt = getattr(evt, "window_amount_wan", None)
                surge = getattr(evt, "surge_ratio", None)
                det = getattr(evt, "details", None)
            elif isinstance(evt, dict):
                ts = str(evt.get("timestamp", ""))
                mi = int(evt.get("minute_index", 0))
                cat = evt.get("event_category", "UNKNOWN")
                sev = evt.get("severity_level", "INFO")
                sym = evt.get("symbol")
                nm = evt.get("name")
                prc = evt.get("price")
                pct = evt.get("pct_change")
                w_pct = evt.get("window_delta_pct")
                w_amt = evt.get("window_amount_wan")
                surge = evt.get("surge_ratio")
                det = evt.get("details")
            else:
                continue

            if ts > latest_event_time:
                latest_event_time = ts

            norm_events.append({
                "timestamp": ts,
                "minute_index": mi,
                "event_category": cat,
                "severity_level": sev,
                "symbol": sym,
                "name": nm,
                "price": prc,
                "pct_change": pct,
                "window_delta_pct": w_pct,
                "window_amount_wan": w_amt,
                "surge_ratio": surge,
                "details": det,
            })

        t_ctx_anomaly = FourDimensionalTime(
            event_time=f"{date_str}T{latest_event_time}.000+08:00" if len(latest_event_time) == 8 else f"{date_str}T15:00:00.000+08:00",
            observed_time=clock.now_iso(),
            ingestion_time=clock.now_iso(),
            effective_time=f"{date_str}T{latest_event_time}.000+08:00" if len(latest_event_time) == 8 else f"{date_str}T15:00:00.000+08:00",
        )
        prov_anomaly = Provenance(
            primary_source=source_name,
            trace_id=trace_id,
        )

        status_anomaly = FactStatus.AVAILABLE if len(norm_events) > 0 else FactStatus.EMPTY
        payload_anomaly = {
            "count": len(norm_events),
            "events": norm_events,
        } if len(norm_events) > 0 else {"count": 0, "events": []}

        facts.append(
            self.create_fact_item(
                fact_key="intraday.anomaly",
                fact_type=FactType.INTRADAY_ANOMALY,
                time_context=t_ctx_anomaly,
                status=status_anomaly,
                freshness=Freshness.REALTIME,
                source=source_name,
                source_record_id=rec_id,
                payload=payload_anomaly,
                provenance=prov_anomaly,
                clock=clock,
            )
        )

        return facts
