"""
M4 早盘竞价事实抽取适配器（M4 Morning Auction Fact Adapter）
上位依据：BOARD-APPROVAL-20260930-STEP3（第五条：M4 事实规范化）
核心铁律：
- 严格将 event_time 锁定为物理集合竞价撮合时点 (09:25:00)
- 严格区分 event_time、observed_time 与 ingestion_time
- 严禁用盘中连续交易事实冒充 AUCTION_0925
- 竞价额缺失时标记为 MISSING，严禁填 0 亿伪造
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


class M4AuctionFactAdapter(BaseFactAdapter):
    """M4 早盘竞价事实抽取适配器"""

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
        index_open_raw = None
        high_open_raw = None
        one_word_count = 0
        source_name = "auction_report"

        if hasattr(raw_data, "__table__"):
            # SQLAlchemy 模型 (AuctionReport 或 MarketDailySnapshot)
            rec_id = str(getattr(raw_data, "id", "db_row"))
            date_str = date_str or getattr(raw_data, "date", None)
            created_at = getattr(raw_data, "created_at", None) or getattr(raw_data, "generated_at", None)
            if created_at:
                ingestion_time_str = created_at.strftime("%Y-%m-%dT%H:%M:%S.000+08:00")

            if hasattr(raw_data, "snapshot_type") and getattr(raw_data, "snapshot_type") == "AUCTION_0925":
                source_name = "market_daily_snapshot:AUCTION_0925"
                index_open_raw = getattr(raw_data, "indices_snapshot", None)
                high_open_raw = getattr(raw_data, "high_tier_snapshot", None)
            else:
                source_name = "auction_report"
                index_open_raw = getattr(raw_data, "index_open_data", None)
                high_open_raw = getattr(raw_data, "high_open_stats", None)
                one_word_count = getattr(raw_data, "one_word_count", 0)
        elif isinstance(raw_data, dict):
            date_str = date_str or raw_data.get("date")
            rec_id = str(raw_data.get("id", "dict_m4"))
            index_open_raw = raw_data.get("index_open_data") or raw_data.get("indices_snapshot")
            high_open_raw = raw_data.get("high_open_stats") or raw_data.get("high_tier_snapshot")
            one_word_count = raw_data.get("one_word_count", 0)
            source_name = raw_data.get("source", "auction_report")

        date_str = date_str or clock.now_iso()[:10]
        # 严格锁定 09:25:00 物理撮合时点
        event_time_str = f"{date_str}T09:25:00.000+08:00"
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

        # 1. 抽取 09:25 开盘指数与两市竞价总额
        parsed_open = None
        if isinstance(index_open_raw, str):
            try:
                parsed_open = json.loads(index_open_raw)
            except Exception:
                parsed_open = None
        elif isinstance(index_open_raw, dict):
            parsed_open = index_open_raw

        quotes_list = []
        total_bidding_yi = None
        bidding_ratio = None
        yesterday_total_yi = None

        if parsed_open:
            quotes_list = parsed_open.get("indices", [])
            total_bidding_yi = parsed_open.get("total_bidding_amount_yi")
            bidding_ratio = parsed_open.get("bidding_volume_ratio")
            yesterday_total_yi = parsed_open.get("yesterday_total_amount_yi")

        # 1.1 开盘指数事实项
        if quotes_list:
            facts.append(
                self.create_fact_item(
                    fact_key="auction.indices",
                    fact_type=FactType.INDEX_QUOTE,
                    time_context=t_ctx,
                    status=FactStatus.AVAILABLE,
                    freshness=Freshness.REALTIME,
                    source=source_name,
                    source_record_id=rec_id,
                    payload={"indices": quotes_list},
                    provenance=prov,
                    clock=clock,
                )
            )
        else:
            facts.append(
                self.create_fact_item(
                    fact_key="auction.indices",
                    fact_type=FactType.INDEX_QUOTE,
                    time_context=t_ctx,
                    status=FactStatus.MISSING,
                    freshness=Freshness.UNKNOWN,
                    source=source_name,
                    source_record_id=rec_id,
                    payload=None,
                    provenance=prov,
                    clock=clock,
                )
            )

        # 1.2 竞价量能比值事实项 (零填充防伪：缺失时严禁补0)
        if total_bidding_yi is not None:
            facts.append(
                self.create_fact_item(
                    fact_key="auction.volume_ratio",
                    fact_type=FactType.MARKET_BREADTH,
                    time_context=t_ctx,
                    status=FactStatus.AVAILABLE,
                    freshness=Freshness.REALTIME,
                    source=source_name,
                    source_record_id=rec_id,
                    payload={
                        "total_bidding_amount_yi": total_bidding_yi,
                        "yesterday_total_amount_yi": yesterday_total_yi,
                        "bidding_volume_ratio": bidding_ratio,
                    },
                    provenance=prov,
                    clock=clock,
                )
            )
        else:
            facts.append(
                self.create_fact_item(
                    fact_key="auction.volume_ratio",
                    fact_type=FactType.MARKET_BREADTH,
                    time_context=t_ctx,
                    status=FactStatus.MISSING,
                    freshness=Freshness.UNKNOWN,
                    source=source_name,
                    source_record_id=rec_id,
                    payload=None, # 强制为 None
                    provenance=prov,
                    clock=clock,
                )
            )

        # 2. 抽取高标开盘溢价事实 (auction.high_open_stats)
        parsed_high = None
        if isinstance(high_open_raw, str):
            try:
                parsed_high = json.loads(high_open_raw)
            except Exception:
                parsed_high = None
        elif isinstance(high_open_raw, dict):
            parsed_high = high_open_raw

        if parsed_high:
            tested_count = int(parsed_high.get("tested_count", 0)) if parsed_high.get("tested_count") is not None else 0
            ratio = parsed_high.get("high_open_ratio")
            avg_prem = parsed_high.get("avg_premium_pct") if parsed_high.get("avg_premium_pct") is not None else parsed_high.get("avg_premium")
            max_board_str = parsed_high.get("max_board_str")
            high_open_cnt = int(parsed_high.get("high_open_count", 0)) if parsed_high.get("high_open_count") is not None else 0
            low_open_cnt = int(parsed_high.get("low_open_count", 0)) if parsed_high.get("low_open_count") is not None else 0
            one_word_up = int(parsed_high.get("one_word_up_count", 0)) if parsed_high.get("one_word_up_count") is not None else 0
            one_word_down = int(parsed_high.get("one_word_down_count", 0)) if parsed_high.get("one_word_down_count") is not None else 0
            max_board_info = parsed_high.get("max_board_info")
            extreme_stocks = parsed_high.get("extreme_stocks", [])

            # 区分空状态与可用状态
            if tested_count > 0 or (ratio is not None and ratio > 0) or (avg_prem is not None and avg_prem != 0):
                status = FactStatus.AVAILABLE
            elif tested_count == 0 and ratio is None and avg_prem is None:
                status = FactStatus.EMPTY
            else:
                status = FactStatus.AVAILABLE

            facts.append(
                self.create_fact_item(
                    fact_key="auction.high_open_stats",
                    fact_type=FactType.HIGH_TIER_STAT,
                    time_context=t_ctx,
                    status=status,
                    freshness=Freshness.REALTIME,
                    source=source_name,
                    source_record_id=rec_id,
                    payload={
                        "high_open_ratio": ratio,
                        "avg_premium": avg_prem,
                        "max_board_str": max_board_str or ("无昨日连板标的" if tested_count == 0 else ""),
                        "tested_count": tested_count,
                        "high_open_count": high_open_cnt,
                        "low_open_count": low_open_cnt,
                        "one_word_up_count": one_word_up,
                        "one_word_down_count": one_word_down,
                        "max_board_info": max_board_info,
                        "extreme_stocks": extreme_stocks,
                    },
                    provenance=prov,
                    clock=clock,
                )
            )
        else:
            facts.append(
                self.create_fact_item(
                    fact_key="auction.high_open_stats",
                    fact_type=FactType.HIGH_TIER_STAT,
                    time_context=t_ctx,
                    status=FactStatus.EMPTY,
                    freshness=Freshness.REALTIME,
                    source=source_name,
                    source_record_id=rec_id,
                    payload={
                        "high_open_ratio": 0.0,
                        "avg_premium": 0.0,
                        "max_board_str": "无昨日连板标的",
                        "tested_count": 0,
                        "high_open_count": 0,
                        "low_open_count": 0,
                        "one_word_up_count": 0,
                        "one_word_down_count": 0,
                        "max_board_info": None,
                        "extreme_stocks": [],
                    },
                    provenance=prov,
                    clock=clock,
                )
            )

        # 3. 抽取一字板家数事实 (auction.one_word_count)
        facts.append(
            self.create_fact_item(
                fact_key="auction.one_word_count",
                fact_type=FactType.MARKET_BREADTH,
                time_context=t_ctx,
                status=FactStatus.AVAILABLE,
                freshness=Freshness.REALTIME,
                source=source_name,
                source_record_id=rec_id,
                payload={"one_word_up_count": one_word_count},
                provenance=prov,
                clock=clock,
            )
        )

        return facts
