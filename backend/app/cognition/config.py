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
    sub_domain: Optional[str] = None # 所属子域标识 (例如 speculative_structure / tail_extremes)

class SubDimensionConfig(BaseModel):
    dimension_id: str          # D1, D2, D3, D4, D5, D6
    name: str                  # 市场整体 / 市场广度 / 短线情绪...
    enabled: bool = True
    is_critical_dimension: bool = False # 是否关键维度 (可配置：为 True 时若维度 INVALID 则整体验证失败)
    dimension_weight: float    # 在全局综合评价中的权重
    metric_polarity: Optional[str] = None # 物理语义极性元数据 (DIRECTIONAL / BREADTH_EXPANSION / HEAT_EXTREMITY / ...)
    semantics_desc: Optional[str] = None  # 物理含义客观描述契约
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
    生成经 G5-Phase 1A.2 审定的 M1.4 V1.1 校准配置
    六大维度，解耦 D2 纯广度，D3 划分为双子域正交事实
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
                metric_polarity="DIRECTIONAL",
                semantics_desc="核心宽基指数均值方向刻度（>50偏多，<50偏空）",
                metrics=[
                    MetricConfig(name="sh_pct_change", display_name="上证指数涨跌幅", capability_ref="index_quote", weight_in_dimension=0.35, quality_rule=MetricQualityRule.CRITICAL, thresholds={"high": 1.5, "low": -1.5}),
                    MetricConfig(name="sz_pct_change", display_name="深证成指涨跌幅", capability_ref="index_quote", weight_in_dimension=0.25, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 1.5, "low": -1.5}),
                    MetricConfig(name="cyb_pct_change", display_name="创业板指涨跌幅", capability_ref="index_quote", weight_in_dimension=0.25, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 2.0, "low": -2.0}),
                    MetricConfig(name="kc50_pct_change", display_name="科创50涨跌幅", capability_ref="index_quote", weight_in_dimension=0.15, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 2.5, "low": -2.5}),
                ]
            ),
            # D2 市场广度 (纯广度解耦：彻底剔除涨跌停与炸板率)
            SubDimensionConfig(
                dimension_id="D2",
                name="市场广度",
                enabled=True,
                is_critical_dimension=True,
                dimension_weight=0.25,
                metric_polarity="BREADTH_EXPANSION",
                semantics_desc="全市场有效个股普适覆盖度（>50普涨扩散，<50普跌收缩）",
                metrics=[
                    MetricConfig(name="up_count", display_name="全市场上涨家数", capability_ref="market_breadth", weight_in_dimension=0.35, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 3500, "low": 1500}),
                    MetricConfig(name="down_count", display_name="全市场下跌家数", capability_ref="market_breadth", weight_in_dimension=0.35, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 3500, "low": 1500}, normalization_method="inverse"),
                    MetricConfig(name="up_down_ratio", display_name="涨跌家数比", capability_ref="derived", weight_in_dimension=0.30, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 2.5, "low": 0.5}),
                ]
            ),
            # D3 短线情绪与极端生态 (双子域独立正交输出，彻底防止标量塌缩)
            SubDimensionConfig(
                dimension_id="D3",
                name="短线情绪与极端生态",
                enabled=True,
                is_critical_dimension=True,
                dimension_weight=0.25,
                metric_polarity="HEAT_EXTREMITY",
                semantics_desc="短线投机活跃与两极极端博弈热度（数值高代表极端分化活跃，非买入信号）",
                metrics=[
                    # Sub-Domain A: 投机高标结构事实 (Speculative Structure)
                    MetricConfig(name="max_board_height", display_name="连板最高空间", capability_ref="limit_up", sub_domain="speculative_structure", weight_in_dimension=0.45, quality_rule=MetricQualityRule.CRITICAL, thresholds={"high": 6, "low": 2}),
                    MetricConfig(name="promotion_rate", display_name="连板晋级率", capability_ref="limit_up", sub_domain="speculative_structure", weight_in_dimension=0.30, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 0.40, "low": 0.15}),
                    MetricConfig(name="high_tier_performance", display_name="高位股溢价表现", capability_ref="high_tier_performance", sub_domain="speculative_structure", weight_in_dimension=0.25, quality_rule=MetricQualityRule.OPTIONAL, thresholds={"high": 3.0, "low": -3.0}),
                    # Sub-Domain B: 尾部极端博弈事实 (Tail Extremes)
                    MetricConfig(name="limit_up_count", display_name="全市场涨停数", capability_ref="limit_up", sub_domain="tail_extremes", weight_in_dimension=0.35, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 60, "low": 20}),
                    MetricConfig(name="limit_down_count", display_name="全市场跌停数", capability_ref="limit_up", sub_domain="tail_extremes", weight_in_dimension=0.25, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 20, "low": 3}, normalization_method="inverse"),
                    MetricConfig(name="limit_diff", display_name="涨跌停绝对差", capability_ref="derived", sub_domain="tail_extremes", weight_in_dimension=0.20, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 50, "low": 0}),
                    MetricConfig(name="broken_limit_ratio", display_name="真实炸板率", capability_ref="limit_up", sub_domain="tail_extremes", weight_in_dimension=0.20, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 0.35, "low": 0.15}, normalization_method="inverse"),
                ]
            ),
            # D4 风格与风险偏好
            SubDimensionConfig(
                dimension_id="D4",
                name="风格与风险偏好",
                enabled=True,
                is_critical_dimension=False, # 可配置：非硬编码永久非关键
                dimension_weight=0.10,
                metric_polarity="STYLE_ELASTICITY",
                semantics_desc="微盘/小市值相对大盘弹性比（>50小票强，<50蓝筹强）",
                metrics=[
                    MetricConfig(name="micro_cap_pct_change", display_name="微盘股指数涨跌幅", capability_ref="micro_cap", weight_in_dimension=0.60, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 2.0, "low": -2.0}),
                    MetricConfig(name="micro_vs_macro_ratio", display_name="微盘相对强弱", capability_ref="derived", weight_in_dimension=0.40, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 1.5, "low": -1.5}),
                ]
            ),
            # D5 外部环境 (更名消除歧义，极性定性为平稳友好度)
            SubDimensionConfig(
                dimension_id="D5",
                name="外部环境",
                enabled=True,
                is_critical_dimension=False, # 可配置：支持特定场景下提升为关键维度
                dimension_weight=0.05,
                metric_polarity="EXTERNAL_BENIGNITY",
                semantics_desc="离岸衍生品与外盘扰动平稳度刻度（>50偏暖平稳，<50承压扰动）",
                metrics=[
                    MetricConfig(name="a50_pct_change", display_name="A50变动", capability_ref="external_risk", weight_in_dimension=0.70, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 1.0, "low": -1.0}),
                    MetricConfig(name="a50_long_short_indicator", display_name="A50多空指标", capability_ref="external_risk", weight_in_dimension=0.30, quality_rule=MetricQualityRule.OPTIONAL, thresholds={"high": 60, "low": 40}),
                ]
            ),
            # D6 流动性 (定性为交投活跃度与资金深度，消除单调多头假设)
            SubDimensionConfig(
                dimension_id="D6",
                name="流动性",
                enabled=True,
                is_critical_dimension=True,
                dimension_weight=0.15,
                metric_polarity="LIQUIDITY_ACTIVITY",
                semantics_desc="两市换手活跃度与资金深度（数值高代表巨量交投，非多头定论）",
                metrics=[
                    MetricConfig(name="total_amount", display_name="两市成交总额", capability_ref="index_quote", weight_in_dimension=0.60, quality_rule=MetricQualityRule.CRITICAL, thresholds={"high": 12000, "low": 6000}),
                    MetricConfig(name="amount_change_ratio", display_name="成交额环比变化", capability_ref="derived", weight_in_dimension=0.40, quality_rule=MetricQualityRule.IMPORTANT, thresholds={"high": 0.20, "low": -0.20}),
                ]
            ),
        ]
    )
