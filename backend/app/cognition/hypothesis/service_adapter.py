"""
Hypothesis Service Adapter (Phase 2B.1 Minimal Hypothesis & Falsification Loop)
上位依据：
1. 《开发文档/52-Phase-2B.1-Minimal-Hypothesis-Falsification-Contract.md》
2. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》

职责：
- 将 ORM 存储层 MarketHypothesis 编译/反序列化为收窄 AST 模型 MarketHypothesisDefinition
- 从 M1 日终复盘 (DailyReview) 与物理快照 (MarketDailySnapshot) 抽取客观事实切片
- 驱动 FalsificationEngine 进行波普尔“证伪优先”仲裁
- 绝不引入任何个股买卖推荐与交易预测 (严格遵守铁律 2)
"""

import json
import hashlib
from typing import Dict, List, Any, Optional

from .contracts import (
    MarketHypothesisDefinition,
    MetricAssertion,
    StructuredFilter,
    FilterCondition,
    UniverseType,
    OperatorType,
    AggregationType,
    MissingDataPolicy,
    MetricType,
)
from .falsification import FalsificationEngine, HypothesisAdjudicationResult
from ...models.report import DailyReview
from ...models.market import MarketDailySnapshot
from ...models.cognition import MarketHypothesis


class HypothesisServiceAdapter:
    """假说服务适配器：连接 ORM 业务层与 AST 证伪引擎内核"""

    @classmethod
    def compile_hypothesis_definition(cls, hypo: MarketHypothesis) -> MarketHypothesisDefinition:
        """
        将 MarketHypothesis 转换为不可变结构化 MarketHypothesisDefinition
        支持标准收窄 AST 语法与轻量规则无缝自适应编译
        """
        raw_metrics = {}
        if hypo.assertion_metrics:
            try:
                raw_metrics = json.loads(hypo.assertion_metrics) if isinstance(hypo.assertion_metrics, str) else hypo.assertion_metrics
            except Exception:
                raw_metrics = {}

        expected_assertions: List[MetricAssertion] = []
        invalidation_assertions: List[MetricAssertion] = []

        # 1. 尝试直接解析标准 AST 列表
        if "expected_assertions" in raw_metrics or "invalidation_assertions" in raw_metrics:
            for exp_raw in raw_metrics.get("expected_assertions", []):
                expected_assertions.append(cls._parse_or_compile_assertion(exp_raw, default_id="exp"))
            for inv_raw in raw_metrics.get("invalidation_assertions", []):
                invalidation_assertions.append(cls._parse_or_compile_assertion(inv_raw, default_id="inv"))
        else:
            # 2. 轻量格式自适应编译为收窄 AST
            # A. 预期跌停/涨停断言
            if "close_limit_up_min" in raw_metrics:
                expected_assertions.append(
                    MetricAssertion(
                        assertion_id="exp_lu_min",
                        metric=MetricType.LIMIT_UP_COUNT.value,
                        selector=StructuredFilter(
                            universe_type=UniverseType.ALL_A,
                            conditions=[FilterCondition(field="code", op=OperatorType.EQ, val="ALL_A")]
                        ),
                        operator=OperatorType.GTE,
                        target_value=float(raw_metrics["close_limit_up_min"]),
                    )
                )
            if "auction_limit_down_max" in raw_metrics:
                expected_assertions.append(
                    MetricAssertion(
                        assertion_id="exp_ld_max",
                        metric=MetricType.LIMIT_DOWN_COUNT.value,
                        selector=StructuredFilter(
                            universe_type=UniverseType.ALL_A,
                            conditions=[FilterCondition(field="code", op=OperatorType.EQ, val="ALL_A")]
                        ),
                        operator=OperatorType.LTE,
                        target_value=float(raw_metrics["auction_limit_down_max"]),
                    )
                )
            if "sh_pct_change_min" in raw_metrics:
                expected_assertions.append(
                    MetricAssertion(
                        assertion_id="exp_sh_pct_min",
                        metric=MetricType.PCT_CHANGE.value,
                        selector=StructuredFilter(
                            universe_type=UniverseType.ALL_A,
                            conditions=[FilterCondition(field="code", op=OperatorType.EQ, val="sh000001")]
                        ),
                        operator=OperatorType.GTE,
                        target_value=float(raw_metrics["sh_pct_change_min"]),
                    )
                )

            # B. 证伪断言编译
            if "sh_invalidation_max" in raw_metrics:
                invalidation_assertions.append(
                    MetricAssertion(
                        assertion_id="inv_sh_surge",
                        metric=MetricType.PCT_CHANGE.value,
                        selector=StructuredFilter(
                            universe_type=UniverseType.ALL_A,
                            conditions=[FilterCondition(field="code", op=OperatorType.EQ, val="sh000001")]
                        ),
                        operator=OperatorType.GT,
                        target_value=float(raw_metrics["sh_invalidation_max"]),
                    )
                )
            if "sh_invalidation_min" in raw_metrics:
                invalidation_assertions.append(
                    MetricAssertion(
                        assertion_id="inv_sh_drop",
                        metric=MetricType.PCT_CHANGE.value,
                        selector=StructuredFilter(
                            universe_type=UniverseType.ALL_A,
                            conditions=[FilterCondition(field="code", op=OperatorType.EQ, val="sh000001")]
                        ),
                        operator=OperatorType.LT,
                        target_value=float(raw_metrics["sh_invalidation_min"]),
                    )
                )
            if "limit_up_invalidation_max" in raw_metrics:
                invalidation_assertions.append(
                    MetricAssertion(
                        assertion_id="inv_lu_surge",
                        metric=MetricType.LIMIT_UP_COUNT.value,
                        selector=StructuredFilter(
                            universe_type=UniverseType.ALL_A,
                            conditions=[FilterCondition(field="code", op=OperatorType.EQ, val="ALL_A")]
                        ),
                        operator=OperatorType.GT,
                        target_value=float(raw_metrics["limit_up_invalidation_max"]),
                    )
                )
            if "limit_down_invalidation_max" in raw_metrics:
                invalidation_assertions.append(
                    MetricAssertion(
                        assertion_id="inv_ld_surge",
                        metric=MetricType.LIMIT_DOWN_COUNT.value,
                        selector=StructuredFilter(
                            universe_type=UniverseType.ALL_A,
                            conditions=[FilterCondition(field="code", op=OperatorType.EQ, val="ALL_A")]
                        ),
                        operator=OperatorType.GT,
                        target_value=float(raw_metrics["limit_down_invalidation_max"]),
                    )
                )

        # 确保至少有基础防御断言，杜绝空指针
        if not expected_assertions and not invalidation_assertions:
            # 默认建立宽基涨跌幅防御断言
            expected_assertions.append(
                MetricAssertion(
                    assertion_id="def_sh_active",
                    metric=MetricType.PCT_CHANGE.value,
                    selector=StructuredFilter(
                        universe_type=UniverseType.ALL_A,
                        conditions=[FilterCondition(field="code", op=OperatorType.EQ, val="sh000001")]
                    ),
                    operator=OperatorType.GTE,
                    target_value=-10.0, # 基础存活断言
                )
            )

        hypo_id_str = f"hypo_{hypo.id}"
        hash_seed = f"{hypo.id}_{hypo.created_date}_{hypo.target_date}_{hypo.hypothesis_type}_{hypo.expected_scenario}"
        hypo_hash = hashlib.sha256(hash_seed.encode("utf-8")).hexdigest()

        return MarketHypothesisDefinition(
            hypothesis_id=hypo_id_str,
            cognition_id=f"cog_{hypo.created_date}",
            proposition=hypo.premise_logic or "未指定命题阐述",
            premise_evidence=[str(hypo.target_asset or "ALL_A"), str(hypo.expected_scenario or "GENERAL")],
            time_binding=hypo.target_date,
            assertion_logic="AND",
            expected_assertions=expected_assertions,
            invalidation_assertions=invalidation_assertions,
            hypothesis_hash=hypo_hash,
        )

    @classmethod
    def _parse_or_compile_assertion(cls, raw: Dict[str, Any], default_id: str) -> MetricAssertion:
        """从字典构建 MetricAssertion AST 节点"""
        # 兼容 selector 既有格式或直接构建
        sel_raw = raw.get("selector")
        if isinstance(sel_raw, dict):
            selector = StructuredFilter(**sel_raw)
        else:
            # 自动基于 target_code 构建 StructuredFilter
            target_code = raw.get("target_code", "ALL_A")
            conds = [FilterCondition(field="code", op=OperatorType.EQ, val=target_code)]
            selector = StructuredFilter(
                universe_type=UniverseType.ALL_A,
                conditions=conds,
            )

        op_str = str(raw.get("operator", "GTE")).upper()
        op_enum = OperatorType(op_str) if op_str in OperatorType.__members__ else OperatorType.GTE

        agg_str = str(raw.get("aggregation", "NONE")).upper()
        agg_enum = AggregationType(agg_str) if agg_str in AggregationType.__members__ else AggregationType.NONE

        pol_str = str(raw.get("missing_data_policy", "INCONCLUSIVE")).upper()
        pol_enum = MissingDataPolicy(pol_str) if pol_str in MissingDataPolicy.__members__ else MissingDataPolicy.INCONCLUSIVE

        return MetricAssertion(
            assertion_id=raw.get("assertion_id") or f"{default_id}_{raw.get('metric_type', 'pct')}",
            metric=raw.get("metric_type") or raw.get("metric") or MetricType.PCT_CHANGE.value,
            selector=selector,
            aggregation=agg_enum,
            operator=op_enum,
            target_value=raw.get("target_value") if raw.get("target_value") is not None else (raw.get("threshold") if isinstance(raw.get("threshold"), (int, float)) else None),
            target_range=raw.get("target_range") or (raw.get("threshold") if isinstance(raw.get("threshold"), list) else None),
            missing_data_policy=pol_enum,
        )

    @classmethod
    def extract_observation_data(
        cls,
        target_date: str,
        review: Optional[DailyReview] = None,
        snapshot: Optional[MarketDailySnapshot] = None,
    ) -> Dict[str, Any]:
        """
        从收盘复盘与快照中提取纯认知宏观观测事实，构建求值事实切片
        严格限制为指数、全市场广度与投机统计事实，绝不包含任何个股交易预测
        """
        if not review and not snapshot:
            return {"date": target_date, "status": "MISSING", "stocks": []}

        stocks: List[Dict[str, Any]] = []

        # 1. 提取四大宽基指数事实
        quotes_raw = []
        if review and review.market_overview:
            try:
                quotes_raw = json.loads(review.market_overview)
            except Exception:
                quotes_raw = []
        elif snapshot and snapshot.indices_snapshot:
            try:
                quotes_raw = json.loads(snapshot.indices_snapshot)
            except Exception:
                quotes_raw = []

        sh_pct = 0.0
        for q in quotes_raw:
            if not isinstance(q, dict):
                continue
            code = str(q.get("symbol") or q.get("code") or "").lower().replace("s_", "")
            pct = q.get("pct_change") if q.get("pct_change") is not None else q.get("change_pct")
            close = q.get("close") if q.get("close") is not None else q.get("price")
            pct_float = float(pct) if pct is not None else 0.0
            close_float = float(close) if close is not None else 0.0
            if code == "sh000001":
                sh_pct = pct_float

            stocks.append({
                "code": code,
                "name": q.get("name") or q.get("index_name") or code,
                "pct_change": pct_float,
                "open_pct_change": float(q.get("open_pct_change", 0.0) or 0.0),
                "price": close_float,
                "board_height": 0,
            })

        # 2. 提取涨停池与全市场生态事实
        lu_dict = {}
        if review and review.limit_up_analysis:
            try:
                lu_dict = json.loads(review.limit_up_analysis)
            except Exception:
                lu_dict = {}
        elif snapshot and snapshot.limit_up_snapshot:
            try:
                lu_dict = json.loads(snapshot.limit_up_snapshot)
            except Exception:
                lu_dict = {}

        limit_up_count = float(lu_dict.get("total_count", 0) or 0)
        limit_down_count = float(lu_dict.get("limit_down_count", 0) or 0)
        max_height = float(lu_dict.get("max_height", 0) or lu_dict.get("max_board_height", 0) or 0)

        # 3. 提取市场广度事实
        breadth_dict = {}
        if snapshot and snapshot.breadth_snapshot:
            try:
                breadth_dict = json.loads(snapshot.breadth_snapshot)
            except Exception:
                breadth_dict = {}

        up_count = float(breadth_dict.get("up_count", 0) or 0)
        down_count = float(breadth_dict.get("down_count", 0) or 0)

        # 4. 构建全市场宏观虚拟标的 (ALL_A)
        stocks.append({
            "code": "ALL_A",
            "name": "全市场宏观聚合",
            "pct_change": sh_pct,
            "open_pct_change": 0.0,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "up_count": up_count,
            "down_count": down_count,
            "board_height": max_height,
        })

        # 5. 提取真实涨停个股、连板高标与板块映射事实
        ladder_stocks = []
        sector_stocks = []
        raw_items = lu_dict.get("items") if lu_dict.get("items") is not None else lu_dict.get("pool", [])
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            c = str(item.get("code") or item.get("symbol") or "").replace("s_", "")
            if not c:
                continue
            n = str(item.get("name") or c)
            h = int(item.get("lbc") or item.get("height") or item.get("board_count", 1))
            sec = str(item.get("sector") or item.get("hybk") or "")
            reasons = item.get("reasons") or ([item["reason_type"]] if item.get("reason_type") else [])
            is_highest = (h == int(max_height) and max_height > 0)
            st_dict = {
                "code": c,
                "symbol": c,
                "name": n,
                "pct_change": 10.0 if not (c.startswith("30") or c.startswith("68")) else 20.0,
                "open_pct_change": 0.0,
                "board_height": h,
                "sector": sec,
                "sector_code": sec,
                "reasons": reasons,
                "is_highest_board": is_highest,
            }
            stocks.append(st_dict)
            sector_stocks.append(st_dict)
            if h >= 2 or is_highest:
                ladder_stocks.append(st_dict)

        return {
            "date": target_date,
            "status": "AVAILABLE",
            "stocks": stocks,
            "all_stocks": stocks,
            "ladder_stocks": ladder_stocks,
            "sector_stocks": sector_stocks,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "max_board_height": max_height,
        }

    @classmethod
    def adjudicate(
        cls,
        hypo: MarketHypothesis,
        review: Optional[DailyReview] = None,
        snapshot: Optional[MarketDailySnapshot] = None,
    ) -> HypothesisAdjudicationResult:
        """对单项假说执行基于 AST 与真实复盘事实的权威证伪仲裁"""
        hypo_def = cls.compile_hypothesis_definition(hypo)
        obs_data = cls.extract_observation_data(hypo.target_date, review, snapshot)
        return FalsificationEngine.adjudicate(hypo_def, obs_data)
