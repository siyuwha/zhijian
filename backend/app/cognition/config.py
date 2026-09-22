from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class MetricQualityRule(str, Enum):
    CRITICAL = "critical"      # 关键指标：缺失则子维度判定 INVALID
    IMPORTANT = "important"    # 重要指标：缺失则子维度降级为 PARTIAL 并重归一化权重
    OPTIONAL = "optional"      # 可选/参考指标：缺失不影响维度质量，仅供参考

class MetricConfig(BaseModel):
    name: str                  # 指标唯一标识 (如 sh_pct_change)
    display_name: str          # 中文名称
    capability_ref: str        # 关联的数据能力 (如 index_quote, limit_up)
    weight_in_dimension: float # 在子维度内部的相对权重
    quality_rule: MetricQualityRule = MetricQualityRule.IMPORTANT
    thresholds: Dict[str, float] = Field(default_factory=dict)
    normalization_method: str = "linear_clamp" # 归一化方法名 (linear_clamp / inverse / zscore)

class SubDimensionConfig(BaseModel):
    dimension_id: str          # D1, D2, D3, D4, D5, D6
    name: str                  # 市场整体 / 市场广度 / 短线情绪...
    enabled: bool = True
    is_critical_dimension: bool = False # 是否关键维度 (可配置：为 True 时若维度 INVALID 则整体验证失败)
    dimension_weight: float    # 在全局综合评价中的权重
    metrics: List[MetricConfig]
    thresholds: Dict[str, float] = Field(default_factory=dict)

class MarketStateV1Config(BaseModel):
    """
    M1.4 V1 分层市场状态配置模型
    - 关键维度/关键指标由配置定义，非永久硬编码；
    - 权重、阈值、标准化算法均支持外部热配置与动态调整。
    """
    version: str = "v1"
    dimensions: List[SubDimensionConfig]
    state_classification_rules: Dict[str, float] = Field(
        default_factory=lambda: {
            "freezing": 25.0,  # 冰点
            "weak": 45.0,      # 偏弱
            "neutral": 55.0,   # 平衡
            "strong": 75.0,    # 偏强
            "overheated": 100.0 # 过热
        }
    )

def get_default_market_state_v1_config() -> MarketStateV1Config:
    """
    生成经 G4-B 审定的 M1.4 V1 初始标准配置
    六大维度，22 项指标，关键维度可按场景自由切换
    """
    return MarketStateV1Config(
        dimensions=[
            # D1 市场整体
            SubDimensionConfig(
                dimension_id="D1",
                name="市场整体",
                enabled=True,
                is_critical_dimension=True,
                dimension_weight=0.20,
                metrics=[
                    MetricConfig(name="sh_pct_change", display_name="上证指数涨跌幅", capability_ref="index_quote", weight_in_dimension=0.35, quality_rule=MetricQualityRule.CRITICAL, thresholds={"high": 1.5, "low": -1.5}),
                    MetricConfig(name="sz_pct_change", display_name="深证成指涨跌幅", capability_ref="index_quote", weight_in_dimension=0.25, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 1.5, "low": -1.5}),
                    MetricConfig(name="cyb_pct_change", display_name="创业板指涨跌幅", capability_ref="index_quote", weight_in_dimension=0.25, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 2.0, "low": -2.0}),
                    MetricConfig(name="kc50_pct_change", display_name="科创50涨跌幅", capability_ref="index_quote", weight_in_dimension=0.15, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 2.5, "low": -2.5}),
                ]
            ),
            # D2 市场广度 / 赚钱效应
            SubDimensionConfig(
                dimension_id="D2",
                name="市场广度与赚钱效应",
                enabled=True,
                is_critical_dimension=True,
                dimension_weight=0.25,
                metrics=[
                    MetricConfig(name="up_count", display_name="全市场上涨家数", capability_ref="market_breadth", weight_in_dimension=0.15, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 3500, "low": 1500}),
                    MetricConfig(name="down_count", display_name="全市场下跌家数", capability_ref="market_breadth", weight_in_dimension=0.15, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 3500, "low": 1500}, normalization_method="inverse"),
                    MetricConfig(name="up_down_ratio", display_name="涨跌家数比", capability_ref="derived", weight_in_dimension=0.15, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 2.5, "low": 0.5}),
                    MetricConfig(name="limit_up_count", display_name="涨停家数", capability_ref="limit_up", weight_in_dimension=0.20, quality_rule=MetricQualityRule.CRITICAL, thresholds={"high": 60, "low": 20}),
                    MetricConfig(name="limit_down_count", display_name="跌停家数", capability_ref="limit_up", weight_in_dimension=0.15, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 20, "low": 3}, normalization_method="inverse"),
                    MetricConfig(name="limit_diff", display_name="涨跌停差值", capability_ref="derived", weight_in_dimension=0.10, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 50, "low": 0}),
                    MetricConfig(name="broken_limit_ratio", display_name="炸板率", capability_ref="limit_up", weight_in_dimension=0.10, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 0.35, "low": 0.15}, normalization_method="inverse"),
                ]
            ),
            # D3 短线情绪
            SubDimensionConfig(
                dimension_id="D3",
                name="短线情绪",
                enabled=True,
                is_critical_dimension=True,
                dimension_weight=0.25,
                metrics=[
                    MetricConfig(name="max_board_height", display_name="连板最高空间", capability_ref="limit_up", weight_in_dimension=0.40, quality_rule=MetricQualityRule.CRITICAL, thresholds={"high": 6, "low": 2}),
                    MetricConfig(name="promotion_rate", display_name="连板晋级率", capability_ref="limit_up", weight_in_dimension=0.30, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 0.40, "low": 0.15}),
                    MetricConfig(name="high_tier_performance", display_name="高位股表现", capability_ref="high_tier_performance", weight_in_dimension=0.15, quality_rule=MetricQualityRule.OPTIONAL, thresholds={"high": 3.0, "low": -3.0}),
                    MetricConfig(name="ref_broken_limit_ratio", display_name="炸板率(引用)", capability_ref="ref_d2", weight_in_dimension=0.15, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 0.35, "low": 0.15}, normalization_method="inverse"),
                ]
            ),
            # D4 风格 / 风险偏好
            SubDimensionConfig(
                dimension_id="D4",
                name="风格与风险偏好",
                enabled=True,
                is_critical_dimension=False, # 可配置：非硬编码永久非关键
                dimension_weight=0.10,
                metrics=[
                    MetricConfig(name="micro_cap_pct_change", display_name="微盘股指数涨跌幅", capability_ref="micro_cap", weight_in_dimension=0.60, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 2.0, "low": -2.0}),
                    MetricConfig(name="micro_vs_macro_ratio", display_name="微盘相对强弱", capability_ref="derived", weight_in_dimension=0.40, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 1.5, "low": -1.5}),
                ]
            ),
            # D5 外部风险 / 预期
            SubDimensionConfig(
                dimension_id="D5",
                name="外部风险与预期",
                enabled=True,
                is_critical_dimension=False, # 可配置：支持特定场景下提升为关键维度
                dimension_weight=0.05,
                metrics=[
                    MetricConfig(name="a50_pct_change", display_name="A50变动", capability_ref="external_risk", weight_in_dimension=0.70, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 1.0, "low": -1.0}),
                    MetricConfig(name="a50_long_short_indicator", display_name="A50多空指标", capability_ref="external_risk", weight_in_dimension=0.30, quality_rule=MetricQualityRule.OPTIONAL, thresholds={"high": 60, "low": 40}),
                ]
            ),
            # D6 流动性
            SubDimensionConfig(
                dimension_id="D6",
                name="流动性",
                enabled=True,
                is_critical_dimension=True,
                dimension_weight=0.15,
                metrics=[
                    MetricConfig(name="total_amount", display_name="两市成交总额", capability_ref="index_quote", weight_in_dimension=0.60, quality_rule=MetricQualityRule.CRITICAL, thresholds={"high": 12000, "low": 6000}),
                    MetricConfig(name="amount_change_ratio", display_name="成交额环比变化", capability_ref="derived", weight_in_dimension=0.40, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 0.20, "low": -0.20}),
                ]
            ),
        ]
    )
