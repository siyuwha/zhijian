"""
M1 盘后复盘事实适配器（M1 Post-Close Review Fact Adapter）
上位依据：
1. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》
2. BOARD-APPROVAL-20260930-STEP3（第五条：M1 事实规范化）
核心职责：
- 抽取收盘指数、市场广度量能、涨停梯队与连板高度、六维状态 D1~D6
- 严格绑定收盘事件时点 (15:00:00)
- 涨停池为空时输出合法 FactStatus.EMPTY（数量为0）
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


class M1ReviewFactAdapter(BaseFactAdapter):
    """M1 盘后复盘事实抽取适配器"""

    def extract_facts(
        self,
        raw_data: Any,
        clock: DeterministicClock,
        trace_id: str,
        market_date: Optional[str] = None,
        **kwargs: Any,
    ) -> List[FactItem]:
        facts: List[FactItem] = []

        # 统一转为字典视图处理，支持 ORM 对象或纯字典
        date_str = market_date
        rec_id = "unknown"
        ingestion_time_str = clock.now_iso()
        indices_raw = None
        breadth_raw = None
        limit_up_raw = None
        market_state_raw = None
        source_name = "m1_review"

        if hasattr(raw_data, "__table__"):
            # SQLAlchemy 模型 (MarketDailySnapshot 或 DailyReview)
            rec_id = str(getattr(raw_data, "id", "db_row"))
            date_str = date_str or getattr(raw_data, "date", None)
            created_at = getattr(raw_data, "created_at", None)
            if created_at:
                ingestion_time_str = created_at.strftime("%Y-%m-%dT%H:%M:%S.000+08:00")
            
            # 优先从 MarketDailySnapshot 属性读取
            if hasattr(raw_data, "indices_snapshot"):
                source_name = "market_daily_snapshot:EOD_CLOSE"
                indices_raw = getattr(raw_data, "indices_snapshot", None)
                breadth_raw = getattr(raw_data, "breadth_snapshot", None)
                limit_up_raw = getattr(raw_data, "limit_up_snapshot", None)
                market_state_raw = getattr(raw_data, "market_state_snapshot", None)
            elif hasattr(raw_data, "market_overview"):
                source_name = "daily_review"
                indices_raw = getattr(raw_data, "market_overview", None)
                limit_up_raw = getattr(raw_data, "limit_up_analysis", None)
                market_state_raw = getattr(raw_data, "report_content", None)
        elif isinstance(raw_data, dict):
            date_str = date_str or raw_data.get("date")
            rec_id = str(raw_data.get("id", "dict_001"))
            indices_raw = raw_data.get("indices") or raw_data.get("indices_snapshot")
            breadth_raw = raw_data.get("breadth") or raw_data.get("breadth_snapshot")
            limit_up_raw = raw_data.get("limit_up") or raw_data.get("limit_up_snapshot")
            market_state_raw = raw_data.get("market_state") or raw_data.get("market_state_snapshot")
            source_name = raw_data.get("source", "m1_review")

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
        prov = Provenance(
            primary_source=source_name,
            trace_id=trace_id,
        )

        # 1. 抽取收盘指数事实
        quotes: List[Dict[str, Any]] = []
        if isinstance(indices_raw, str):
            try:
                parsed = json.loads(indices_raw)
                quotes = parsed.get("indices", parsed) if isinstance(parsed, dict) else parsed
            except Exception:
                quotes = []
        elif isinstance(indices_raw, list):
            quotes = indices_raw
        elif isinstance(indices_raw, dict):
            quotes = indices_raw.get("indices", [indices_raw])

        target_indices = ["sh000001", "sz399001", "sz399006", "sh000688"]
        found_codes = set()
        for q in quotes:
            if not isinstance(q, dict):
                continue
            code = q.get("code") or q.get("symbol")
            if not code:
                continue
            clean_code = str(code).lower().replace("s_", "")
            found_codes.add(clean_code)
            facts.append(
                self.create_fact_item(
                    fact_key=f"indices.{clean_code}",
                    fact_type=FactType.INDEX_QUOTE,
                    time_context=t_ctx,
                    status=FactStatus.AVAILABLE,
                    freshness=Freshness.REALTIME,
                    source=source_name,
                    source_record_id=rec_id,
                    payload={
                        "code": clean_code,
                        "name": q.get("name", clean_code),
                        "close": q.get("price") or q.get("close"),
                        "pct_change": q.get("pct_change") or q.get("change_pct"),
                        "amount_wan": q.get("amount_wan") or q.get("amount"),
                    },
                    provenance=prov,
                    clock=clock,
                )
            )

        # 若核心指数未获取到，显式标记 MISSING (零填充防伪)
        for target in target_indices:
            if target not in found_codes:
                facts.append(
                    self.create_fact_item(
                        fact_key=f"indices.{target}",
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

        # 2. 抽取市场广度事实 (breadth.summary)
        breadth_dict = None
        if isinstance(breadth_raw, str):
            try:
                breadth_dict = json.loads(breadth_raw)
            except Exception:
                breadth_dict = None
        elif isinstance(breadth_raw, dict):
            breadth_dict = breadth_raw

        if breadth_dict:
            facts.append(
                self.create_fact_item(
                    fact_key="breadth.summary",
                    fact_type=FactType.MARKET_BREADTH,
                    time_context=t_ctx,
                    status=FactStatus.AVAILABLE,
                    freshness=Freshness.REALTIME,
                    source=source_name,
                    source_record_id=rec_id,
                    payload={
                        "total_amount_yi": breadth_dict.get("total_amount_yi"),
                        "up_count": breadth_dict.get("up_count"),
                        "down_count": breadth_dict.get("down_count"),
                        "flat_count": breadth_dict.get("flat_count"),
                    },
                    provenance=prov,
                    clock=clock,
                )
            )
        else:
            facts.append(
                self.create_fact_item(
                    fact_key="breadth.summary",
                    fact_type=FactType.MARKET_BREADTH,
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

        # 3. 抽取涨停梯队事实 (limit_up.pool)
        lu_dict = None
        if isinstance(limit_up_raw, str):
            try:
                lu_dict = json.loads(limit_up_raw)
            except Exception:
                lu_dict = None
        elif isinstance(limit_up_raw, dict):
            lu_dict = limit_up_raw

        if lu_dict:
            pool = lu_dict.get("pool", [])
            max_height = lu_dict.get("max_board_height") or lu_dict.get("max_height", 0)
            status = FactStatus.AVAILABLE if len(pool) > 0 else FactStatus.EMPTY
            facts.append(
                self.create_fact_item(
                    fact_key="limit_up.pool",
                    fact_type=FactType.LIMIT_UP_POOL,
                    time_context=t_ctx,
                    status=status,
                    freshness=Freshness.REALTIME,
                    source=source_name,
                    source_record_id=rec_id,
                    payload={
                        "limit_up_count": len(pool),
                        "max_board_height": max_height,
                        "pool": pool,
                    },
                    provenance=prov,
                    clock=clock,
                )
            )
        else:
            facts.append(
                self.create_fact_item(
                    fact_key="limit_up.pool",
                    fact_type=FactType.LIMIT_UP_POOL,
                    time_context=t_ctx,
                    status=FactStatus.EMPTY,
                    freshness=Freshness.REALTIME,
                    source=source_name,
                    source_record_id=rec_id,
                    payload={
                        "limit_up_count": 0,
                        "max_board_height": 0,
                        "pool": [],
                    },
                    provenance=prov,
                    clock=clock,
                )
            )

        return facts
