import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from .interfaces import (
    CognitionInput,
    CognitionLayerInterface,
    IndicatorValue,
    MarketState,
    SubDimensionState,
)
from .config import (
    MarketStateV1Config,
    MetricConfig,
    MetricQualityRule,
    SubDimensionConfig,
    get_default_market_state_v1_config,
)
from ..data.capabilities import DataQuality

logger = logging.getLogger(__name__)

class MarketStateComputer(CognitionLayerInterface):
    """
    分层市场状态计算引擎 (M1.4 V1.1 核心实现)
    严格执行 G5-Phase 1A.2 终审裁决与红队审计规范：
    1. 分层架构：Raw Data -> D1~D6 子维度评估 -> Market State Snapshot；
    2. D2 纯广度彻底解耦，不含涨跌停与炸板率等极端尾部事实；
    3. D3 独立正交输出 Sub-A (投机高标) 与 Sub-B (尾部极端)，彻底杜绝标量塌缩；
    4. 严格质量防伪：不可得时留白，关键缺失时 composite_score = None，绝不填补默认值；
    5. 六大维度挂载物理语义极性元数据 (metric_polarity)，严禁作为买卖交易信号。
    """

    def __init__(self, config: Optional[MarketStateV1Config] = None):
        self.config = config or get_default_market_state_v1_config()

    def update_config(self, new_config: MarketStateV1Config):
        """动态更新配置（热配置）"""
        self.config = new_config

    async def compute_market_state(self, input_data: CognitionInput) -> MarketState:
        raw_market = input_data.market_data
        missing_metrics_global: List[str] = []

        sub_dimension_states: Dict[str, SubDimensionState] = {}
        extracted_metric_values: Dict[str, Any] = self._extract_raw_metrics(raw_market)

        # 1. 逐个子维度计算 (Level 1 -> Level 2)
        for dim_cfg in self.config.dimensions:
            if not dim_cfg.enabled:
                continue

            dim_state, missing = self._evaluate_sub_dimension(dim_cfg, extracted_metric_values, sub_dimension_states)
            sub_dimension_states[dim_cfg.dimension_id] = dim_state
            missing_metrics_global.extend(missing)

        # 2. 全局数据质量判定与综合分计算 (Level 2 -> Level 3)
        (
            global_quality,
            composite_score,
            global_label,
            available_weight,
            composite_score_method,
            quality_level,
        ) = self._synthesize_global_state(sub_dimension_states)

        return MarketState(
            timestamp=datetime.now(),
            composite_score=composite_score,
            state_label=global_label,
            data_quality=global_quality,
            dimensions=sub_dimension_states,
            missing_metrics=missing_metrics_global,
            available_weight=available_weight,
            composite_score_method=composite_score_method,
            quality_level=quality_level,
            config_snapshot_version=self.config.version
        )

    def _extract_raw_metrics(self, raw: dict) -> Dict[str, Any]:
        """从上游原始数据包中平铺提取指标原生值"""
        metrics: Dict[str, Any] = {}

        # D1 & D6: 指数行情与两市成交额
        indices = raw.get("indices", [])
        total_amount = 0.0
        sh_pct = None
        for idx in indices:
            code = str(idx.get("code", ""))
            pct = idx.get("pct_change")
            amount = float(idx.get("amount_wan", 0.0) or 0.0) / 10000.0  # 亿元
            # 严格去重仅统计沪深两市核心基准 (上证+深证)
            if "000001" in code or "399001" in code:
                total_amount += amount

            if "sh000001" in code or "000001" in code:
                metrics["sh_pct_change"] = pct
                sh_pct = pct
            elif "sz399001" in code or "399001" in code:
                metrics["sz_pct_change"] = pct
            elif "sz399006" in code or "399006" in code:
                metrics["cyb_pct_change"] = pct
            elif "sh000688" in code or "000688" in code:
                metrics["kc50_pct_change"] = pct

        if total_amount > 0:
            metrics["total_amount"] = round(total_amount, 2)
            prev_amount = raw.get("prev_total_amount")
            if prev_amount and prev_amount > 0:
                metrics["amount_change_ratio"] = round((total_amount - prev_amount) / prev_amount, 4)

        # D2 & D3: 涨跌停、连板及广度数据
        limit_up = raw.get("limit_up", {})
        if limit_up:
            metrics["limit_up_count"] = limit_up.get("total_count")
            metrics["limit_down_count"] = limit_up.get("limit_down_count")
            metrics["max_board_height"] = limit_up.get("max_height")
            if metrics["limit_up_count"] is not None and metrics["limit_down_count"] is not None:
                metrics["limit_diff"] = metrics["limit_up_count"] - metrics["limit_down_count"]

            if "broken_limit_ratio" in limit_up and limit_up.get("broken_limit_ratio") is not None:
                metrics["broken_limit_ratio"] = limit_up.get("broken_limit_ratio")
            prev_limit_up = raw.get("prev_limit_up_count")
            continued_count = limit_up.get("continued_count")
            if prev_limit_up and prev_limit_up > 0 and continued_count is not None:
                metrics["promotion_rate"] = round(continued_count / prev_limit_up, 4)

        # D3: 高位股/连板生态承接表现
        high_tier = raw.get("high_tier")
        if isinstance(high_tier, dict):
            metrics["high_tier_performance"] = high_tier.get("pct_change")
        elif isinstance(high_tier, (int, float)):
            metrics["high_tier_performance"] = float(high_tier)

        breadth = raw.get("breadth", {})
        if breadth:
            metrics["up_count"] = breadth.get("up_count")
            metrics["down_count"] = breadth.get("down_count")
            if "flat_count" in breadth:
                metrics["flat_count"] = breadth.get("flat_count")
            if metrics["up_count"] is not None and metrics["down_count"] is not None:
                down = max(1, metrics["down_count"])
                metrics["up_down_ratio"] = round(metrics["up_count"] / down, 3)

        # D4: 微盘股及风格
        micro = raw.get("micro_cap", {})
        if micro:
            micro_pct = micro.get("pct_change")
            metrics["micro_cap_pct_change"] = micro_pct
            if micro_pct is not None and sh_pct is not None:
                metrics["micro_vs_macro_ratio"] = round(micro_pct - sh_pct, 2)

        # D5: 外部环境与A50
        ext = raw.get("external_risk", {})
        if ext:
            metrics["a50_pct_change"] = ext.get("a50_pct_change")
            metrics["a50_long_short_indicator"] = ext.get("a50_long_short_indicator")

        return metrics

    def _evaluate_sub_dimension(
        self,
        dim_cfg: SubDimensionConfig,
        metrics_pool: Dict[str, Any],
        calculated_dims: Dict[str, SubDimensionState]
    ) -> tuple[SubDimensionState, List[str]]:
        """计算单个子维度的状态、质量与得分 (支持多子域独立并行计算)"""
        missing_in_dim: List[str] = []
        indicators_detail: List[IndicatorValue] = []
        valid_metrics_map: Dict[str, Any] = {}

        # 检查是否包含子域划分 (如 D3 的 speculative_structure 与 tail_extremes)
        has_sub_domains = any(m.sub_domain is not None for m in dim_cfg.metrics)
        sub_domains_result: Optional[Dict[str, Any]] = None

        if has_sub_domains:
            # 按 sub_domain 分组独立计算
            sub_domains_result = {}
            sub_domain_groups: Dict[str, List[MetricConfig]] = {}
            for m_cfg in dim_cfg.metrics:
                s_id = m_cfg.sub_domain or "default"
                if s_id not in sub_domain_groups:
                    sub_domain_groups[s_id] = []
                sub_domain_groups[s_id].append(m_cfg)

            overall_critical_missing = False
            overall_important_missing = False
            total_valid_weight = 0.0
            weighted_score_sum = 0.0

            for s_id, s_metrics in sub_domain_groups.items():
                s_critical_missing = False
                s_important_missing = False
                s_total_weight = 0.0
                s_weighted_sum = 0.0
                s_metrics_map: Dict[str, Any] = {}

                for m_cfg in s_metrics:
                    raw_val = metrics_pool.get(m_cfg.name)

                    if raw_val is None:
                        missing_in_dim.append(m_cfg.name)
                        if m_cfg.quality_rule == MetricQualityRule.CRITICAL:
                            s_critical_missing = True
                            overall_critical_missing = True
                        elif m_cfg.quality_rule == MetricQualityRule.IMPORTANT:
                            s_important_missing = True
                            overall_important_missing = True
                        continue

                    score = self._normalize_metric(raw_val, m_cfg)
                    contribution = score * m_cfg.weight_in_dimension

                    valid_metrics_map[m_cfg.name] = raw_val
                    s_metrics_map[m_cfg.name] = {"raw": raw_val, "score": score, "weight": m_cfg.weight_in_dimension}
                    s_total_weight += m_cfg.weight_in_dimension
                    s_weighted_sum += contribution

                    total_valid_weight += m_cfg.weight_in_dimension
                    weighted_score_sum += contribution

                    indicators_detail.append(
                        IndicatorValue(
                            name=m_cfg.name,
                            value=raw_val,
                            score=score,
                            weight=m_cfg.weight_in_dimension,
                            contribution=contribution,
                            raw_data={"display_name": m_cfg.display_name, "sub_domain": s_id}
                        )
                    )

                # 子域内部质量与得分计算
                if s_critical_missing or s_total_weight == 0.0:
                    s_quality = DataQuality.INVALID
                    s_score = None
                elif s_important_missing:
                    s_quality = DataQuality.PARTIAL
                    s_score = round(s_weighted_sum / s_total_weight, 2)
                else:
                    s_quality = DataQuality.FULL
                    s_score = round(s_weighted_sum / s_total_weight, 2)

                s_name = "投机高标结构事实" if s_id == "speculative_structure" else ("尾部极端博弈事实" if s_id == "tail_extremes" else s_id)
                sub_domains_result[s_id] = {
                    "subdomain_id": s_id,
                    "name": s_name,
                    "score": s_score,
                    "quality": s_quality.value,
                    "metrics": s_metrics_map
                }

            # 维度整体质量判定与抗标量塌缩铁律
            # 核心铁律：D3 核心事实由 sub_domains 正交承载，核心 dim_score 强制为 None！
            # 严禁将两子域 50/50 融合为单一核心分，彻底杜绝维度内标量塌缩与反向污染全局综合分
            dim_score = None
            reference_score = round(weighted_score_sum / total_valid_weight, 2) if total_valid_weight > 0 else None

            if overall_critical_missing or total_valid_weight == 0.0:
                dim_quality = DataQuality.INVALID
                state_label = "INVALID"
            elif overall_important_missing:
                dim_quality = DataQuality.PARTIAL
                state_label = "部分缺失 (双子域独立)"
            else:
                dim_quality = DataQuality.FULL
                state_label = "正交双子域 (无标量塌缩)"

        else:
            # 常规单层子维度 (D1, D2, D4, D5, D6)
            has_critical_missing = False
            has_important_missing = False
            total_valid_weight = 0.0
            weighted_score_sum = 0.0
            reference_score = None

            for m_cfg in dim_cfg.metrics:
                raw_val = metrics_pool.get(m_cfg.name)

                if raw_val is None:
                    missing_in_dim.append(m_cfg.name)
                    if m_cfg.quality_rule == MetricQualityRule.CRITICAL:
                        has_critical_missing = True
                    elif m_cfg.quality_rule == MetricQualityRule.IMPORTANT:
                        has_important_missing = True
                    continue

                score = self._normalize_metric(raw_val, m_cfg)
                contribution = score * m_cfg.weight_in_dimension

                valid_metrics_map[m_cfg.name] = raw_val
                total_valid_weight += m_cfg.weight_in_dimension
                weighted_score_sum += contribution

                indicators_detail.append(
                    IndicatorValue(
                        name=m_cfg.name,
                        value=raw_val,
                        score=score,
                        weight=m_cfg.weight_in_dimension,
                        contribution=contribution,
                        raw_data={"display_name": m_cfg.display_name}
                    )
                )

            if has_critical_missing or total_valid_weight == 0.0:
                dim_quality = DataQuality.INVALID
                dim_score = None
                state_label = "INVALID"
            elif has_important_missing:
                dim_quality = DataQuality.PARTIAL
                dim_score = round(weighted_score_sum / total_valid_weight, 2)
                state_label = self._classify_score(dim_score)
            else:
                dim_quality = DataQuality.FULL
                dim_score = round(weighted_score_sum / total_valid_weight, 2)
                state_label = self._classify_score(dim_score)

        return SubDimensionState(
            dimension_id=dim_cfg.dimension_id,
            name=dim_cfg.name,
            score=dim_score,
            reference_score=reference_score,
            quality=dim_quality,
            state_label=state_label,
            metric_polarity=dim_cfg.metric_polarity,
            semantics_desc=dim_cfg.semantics_desc,
            sub_domains=sub_domains_result,
            metrics=valid_metrics_map,
            indicators_detail=indicators_detail
        ), missing_in_dim

    def _synthesize_global_state(
        self,
        sub_dims: Dict[str, SubDimensionState]
    ) -> tuple[DataQuality, Optional[float], str, Optional[float], str, str]:
        """
        综合全局状态与数据质量判定 (落实 P0 硬约束 2)
        - 坚决废除“单一核心维度缺失直接整天判死刑”机制
        - 哪个指标缺失 -> 哪个指标 INVALID -> 整体质量评分真实反映缺失程度
        - 当有效加权维度总和 >= 0.30 (且至少 2 个有效维度) 时，判定为 PARTIAL，按有效维度重归一化加权
        - 输出元数据：available_weight, composite_score_method, quality_level
        """
        has_any_invalid_dim = False
        has_any_partial_dim = False

        total_valid_dim_weight = 0.0
        dim_weighted_sum = 0.0
        valid_dim_count = 0

        for dim_cfg in self.config.dimensions:
            if not dim_cfg.enabled:
                continue

            state = sub_dims.get(dim_cfg.dimension_id)
            if not state:
                continue

            if state.quality == DataQuality.INVALID:
                has_any_invalid_dim = True
            elif state.quality == DataQuality.PARTIAL:
                has_any_partial_dim = True
                valid_dim_count += 1
                if state.score is not None:
                    total_valid_dim_weight += dim_cfg.dimension_weight
                    dim_weighted_sum += state.score * dim_cfg.dimension_weight
            elif state.quality == DataQuality.FULL:
                valid_dim_count += 1
                if state.score is not None:
                    total_valid_dim_weight += dim_cfg.dimension_weight
                    dim_weighted_sum += state.score * dim_cfg.dimension_weight

        # 检查是否全部有效
        if not has_any_invalid_dim and not has_any_partial_dim and total_valid_dim_weight > 0:
            composite_score = round(dim_weighted_sum / total_valid_dim_weight, 2)
            global_label = self._classify_score(composite_score)
            return (
                DataQuality.FULL,
                composite_score,
                global_label,
                round(total_valid_dim_weight, 4),
                "FULL_WEIGHTED",
                "full_coverage",
            )

        # 降级分支：存在部分维度缺失或无效
        # 只要有效加权维度总和 >= 0.30 且至少有有效维度支撑，则保留真实事实并标记 PARTIAL
        if total_valid_dim_weight >= 0.30 and valid_dim_count >= 2:
            composite_score = round(dim_weighted_sum / total_valid_dim_weight, 2)
            base_label = self._classify_score(composite_score)
            global_label = f"{base_label} (部分降级)"
            return (
                DataQuality.PARTIAL,
                composite_score,
                global_label,
                round(total_valid_dim_weight, 4),
                "RENORMALIZED_VALID_DIMENSIONS",
                f"partial_available_weight_{round(total_valid_dim_weight, 2)}",
            )

        # 有效数据极度匮乏 (权重不足 0.30 或有效维度极少) -> INVALID
        return (
            DataQuality.INVALID,
            None,
            "UNAVAILABLE_DUE_TO_DATA_QUALITY",
            round(total_valid_dim_weight, 4) if total_valid_dim_weight > 0 else 0.0,
            "NONE_DUE_TO_INSUFFICIENT_DATA",
            "insufficient_weight_invalid",
        )

    def _normalize_metric(self, value: float, config: MetricConfig) -> float:
        """根据指标配置的阈值进行 0~100 归一化映射"""
        th = config.thresholds
        low = th.get("low", 0.0)
        high = th.get("high", 100.0)

        if high == low:
            return 50.0

        if config.normalization_method == "inverse":
            norm = (high - value) / (high - low)
        else:
            norm = (value - low) / (high - low)

        clamped = max(0.0, min(1.0, norm))
        return round(clamped * 100.0, 2)

    def _classify_score(self, score: float) -> str:
        """状态分级标签 (客观物理刻度描述，严禁带有交易多空或周期主观定论)"""
        rules = self.config.state_classification_rules
        if score <= rules.get("freezing", 25.0):
            return "极弱收缩"
        elif score <= rules.get("weak", 45.0):
            return "偏弱整理"
        elif score <= rules.get("neutral", 55.0):
            return "平稳中性"
        elif score <= rules.get("strong", 75.0):
            return "偏强扩散"
        else:
            return "极度亢奋"

market_state_computer = MarketStateComputer()
