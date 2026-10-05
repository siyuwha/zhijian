"""
股票与板块题材映射事实抽取适配器（Stock-Sector Relational Fact Adapter）
上位依据：
1. 《开发文档/61-Observation-M1-M5-Fact-Foundation-Audit-Report.md》
2. 用户指令：直接进入 M4 高标竞价 + M5 Intraday Adapter + 股票/板块关系三件事
核心铁律：
- 严格基于物理观测中的客观事实建立双向归属映射（Stock <-> Sector），严禁 AI 凭空幻觉板块成员
- 规范化股票代码（统一去除 s_ 前缀，保证 6 位纯数字无偏比对）
- 确定性聚合题材热度梯队（sector_leaderboard）
- 严格遵循 RFC 8785 JCS 指纹规范
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


class StockSectorRelationAdapter(BaseFactAdapter):
    """股票与板块题材客观映射事实适配器"""

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
        source_name = "stock_sector_mapper"
        items_raw = []
        top_reasons_raw = []

        anomaly_facts_raw = []
        block_facts_raw = []

        if hasattr(raw_data, "__table__"):
            # DailyReview 或 MarketDailySnapshot 模型
            rec_id = str(getattr(raw_data, "id", "db_row"))
            date_str = date_str or getattr(raw_data, "date", None)
            source_name = f"{getattr(raw_data, '__tablename__', 'model')}:relation"

            # 提取 market_state_snapshot 中的 Wave 1 物理事实
            mss_raw = getattr(raw_data, "market_state_snapshot", None)
            if mss_raw:
                try:
                    mss_dict = json.loads(mss_raw) if isinstance(mss_raw, str) else mss_raw
                    if isinstance(mss_dict, dict):
                        anomaly_facts_raw = mss_dict.get("anomaly_facts", [])
                        block_facts_raw = mss_dict.get("block_mapping_facts", [])
                except Exception:
                    pass

            # 优先从 limit_up_analysis 或 limit_up_snapshot 提取
            lu_raw = getattr(raw_data, "limit_up_analysis", None) or getattr(raw_data, "limit_up_snapshot", None)
            if lu_raw:
                try:
                    lu_dict = json.loads(lu_raw) if isinstance(lu_raw, str) else lu_raw
                    if isinstance(lu_dict, dict):
                        items_raw = lu_dict.get("items") or lu_dict.get("pool", [])
                        top_reasons_raw = lu_dict.get("top_reasons", [])
                except Exception:
                    pass

            # 兼容从 sector_analysis 提取题材排行
            sec_raw = getattr(raw_data, "sector_analysis", None)
            if sec_raw and not top_reasons_raw:
                try:
                    sec_parsed = json.loads(sec_raw) if isinstance(sec_raw, str) else sec_raw
                    if isinstance(sec_parsed, list):
                        top_reasons_raw = sec_parsed
                except Exception:
                    pass

        elif isinstance(raw_data, dict):
            date_str = date_str or raw_data.get("date")
            rec_id = str(raw_data.get("id", "dict_relation"))
            source_name = raw_data.get("source", "stock_sector_mapper")

            anomaly_facts_raw = raw_data.get("anomaly_facts", [])
            block_facts_raw = raw_data.get("block_mapping_facts", [])

            if "items" in raw_data:
                items_raw = raw_data["items"]
            elif "pool" in raw_data:
                items_raw = raw_data["pool"]
            elif "limit_up" in raw_data:
                lu_val = raw_data["limit_up"]
                if isinstance(lu_val, dict):
                    items_raw = lu_val.get("items") or lu_val.get("pool", [])
                    top_reasons_raw = lu_val.get("top_reasons", [])
            elif "limit_up_analysis" in raw_data:
                lu_val = raw_data["limit_up_analysis"]
                try:
                    lu_dict = json.loads(lu_val) if isinstance(lu_val, str) else lu_val
                    if isinstance(lu_dict, dict):
                        items_raw = lu_dict.get("items") or lu_dict.get("pool", [])
                        top_reasons_raw = lu_dict.get("top_reasons", [])
                except Exception:
                    pass

            if "top_reasons" in raw_data:
                top_reasons_raw = raw_data["top_reasons"]
            elif "sector_analysis" in raw_data and not top_reasons_raw:
                sec_val = raw_data["sector_analysis"]
                try:
                    sec_parsed = json.loads(sec_val) if isinstance(sec_val, str) else sec_val
                    if isinstance(sec_parsed, list):
                        top_reasons_raw = sec_parsed
                except Exception:
                    pass

        elif isinstance(raw_data, list):
            items_raw = raw_data

        date_str = date_str or clock.now_iso()[:10]
        event_time_str = f"{date_str}T15:00:00.000+08:00"
        observed_time_str = clock.now_iso()
        effective_time_str = event_time_str

        t_ctx = FourDimensionalTime(
            event_time=event_time_str,
            observed_time=observed_time_str,
            ingestion_time=clock.now_iso(),
            effective_time=effective_time_str,
        )
        prov = Provenance(
            primary_source=source_name,
            trace_id=trace_id,
        )

        stock_to_sector: Dict[str, Dict[str, Any]] = {}
        sector_to_stocks: Dict[str, List[Dict[str, Any]]] = {}

        for item in items_raw:
            if not isinstance(item, dict):
                continue

            raw_code = item.get("code") or item.get("symbol")
            if not raw_code:
                continue
            clean_code = str(raw_code).replace("s_", "")[-6:]
            name = str(item.get("name", clean_code))
            height = int(item.get("lbc") or item.get("height") or item.get("board_count", 1))

            # 题材提取 (兼容 sector 与 hybk)
            primary_sector = item.get("sector") or item.get("hybk") or ""
            reasons = item.get("reasons") or ([item["reason_type"]] if item.get("reason_type") else [])
            if not primary_sector and reasons:
                primary_sector = reasons[0]

            if not primary_sector:
                primary_sector = "其他"

            # 1. 股票到板块映射
            stock_to_sector[clean_code] = {
                "code": clean_code,
                "name": name,
                "primary_sector": primary_sector,
                "reasons": reasons,
                "height": height,
            }

            # 2. 板块到股票映射 (双向互联)
            if primary_sector not in sector_to_stocks:
                sector_to_stocks[primary_sector] = []
            sector_to_stocks[primary_sector].append({
                "code": clean_code,
                "name": name,
                "height": height,
            })

        # 题材排行榜 (按个股数量降序确定性排序)
        sector_leaderboard = []
        if top_reasons_raw:
            for tr in top_reasons_raw:
                if isinstance(tr, (list, tuple)) and len(tr) >= 2:
                    sector_leaderboard.append({"sector": str(tr[0]), "count": int(tr[1])})
                elif isinstance(tr, dict):
                    sector_leaderboard.append({
                        "sector": str(tr.get("sector") or tr.get("name", "")),
                        "count": int(tr.get("count", 0)),
                    })
        else:
            for sec, stocks in sorted(sector_to_stocks.items(), key=lambda kv: len(kv[1]), reverse=True):
                sector_leaderboard.append({"sector": sec, "count": len(stocks)})

        total_mapped = len(stock_to_sector)
        status = FactStatus.AVAILABLE if total_mapped > 0 else FactStatus.EMPTY

        facts.append(
            self.create_fact_item(
                fact_key="relation.stock_sector_map",
                fact_type=FactType.STOCK_SECTOR_MAP,
                time_context=t_ctx,
                status=status,
                freshness=Freshness.REALTIME,
                source=source_name,
                source_record_id=rec_id,
                payload={
                    "stock_to_sector": stock_to_sector,
                    "sector_to_stocks": sector_to_stocks,
                    "sector_leaderboard": sector_leaderboard,
                    "total_stocks_mapped": total_mapped,
                    "total_sectors_mapped": len(sector_to_stocks),
                },
                provenance=prov,
                clock=clock,
            )
        )

        # Wave 1 异动事实抽取 (ANOM:*)
        if anomaly_facts_raw:
            anom_dict = {}
            for af in anomaly_facts_raw:
                if isinstance(af, dict) and af.get("canonical_fact_id"):
                    cid = af["canonical_fact_id"]
                    if cid not in anom_dict or af.get("status_flag", 0) > anom_dict[cid].get("status_flag", 0):
                        anom_dict[cid] = af
            for af in anom_dict.values():
                sym = af.get("symbol", "")
                rid = af.get("rule_id", "0")
                facts.append(
                    self.create_fact_item(
                        fact_key=f"anomaly.{sym}.R{rid}",
                        fact_type=FactType.INTRADAY_ANOMALY,
                        time_context=t_ctx,
                        status=FactStatus.AVAILABLE,
                        freshness=Freshness.REALTIME,
                        source="eastmoney_price_anomaly",
                        source_record_id=af["canonical_fact_id"],
                        payload=af,
                        provenance=Provenance(
                            primary_source="EASTMONEY_COMPUTED_RULE_MATCH",
                            trace_id=trace_id,
                        ),
                        clock=clock,
                    )
                )

        # Wave 1 板块映射事实抽取 (BLOCK_MAP:*)
        if block_facts_raw:
            block_dict = {}
            for bf in block_facts_raw:
                if isinstance(bf, dict) and bf.get("canonical_fact_id"):
                    cid = bf["canonical_fact_id"]
                    block_dict[cid] = bf
            for bf in block_dict.values():
                sym = bf.get("symbol", "")
                bcode = bf.get("block_code", "")
                facts.append(
                    self.create_fact_item(
                        fact_key=f"block_map.{sym}.{bcode}",
                        fact_type=FactType.STOCK_SECTOR_MAP,
                        time_context=t_ctx,
                        status=FactStatus.AVAILABLE,
                        freshness=Freshness.REALTIME,
                        source="eastmoney_concept_blocks",
                        source_record_id=bf["canonical_fact_id"],
                        payload=bf,
                        provenance=Provenance(
                            primary_source="EASTMONEY_SLIST_MAPPING",
                            trace_id=trace_id,
                        ),
                        clock=clock,
                    )
                )

        return facts

