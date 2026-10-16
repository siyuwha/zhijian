"""
知见系统短线核心认知指标研究与审计设计数据契约
文件路径：backend/app/schemas/research_divergence_contract.py
上位依据：
1. DOSSIER-COGNITION-RESEARCH-20261016-V1.0
2. SPEC-DESIGN-PHASE2D-20261008-V1.0
3. RFC 8785 (JCS) 与波普尔证伪批判规范

硬隔离原则：
- 严格只读契约，extra="forbid", frozen=True
- 杜绝以推断冒充事实，明确区分 L1/L2/L3 置信等级
- 次日结果数据 (Y_t+1) 严格隔离于指标特征，仅用于事后验证标签
"""

from typing import Optional, List, Dict, Literal
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class LeaderRoleEnum(str, Enum):
    """核心股多标签角色枚举 (可并存拓扑)"""
    TREND_CORE = "TREND_CORE"                   # 趋势型核心
    LADDER_EMOTION_CORE = "LADDER_EMOTION_CORE" # 连板情绪核心
    SECTOR_CAPACITY_CORE = "SECTOR_CAPACITY_CORE" # 板块容量核心
    CATCHUP_RUNNER_CORE = "CATCHUP_RUNNER_CORE" # 补涨型核心
    INDEPENDENT_EVENT_CORE = "INDEPENDENT_EVENT_CORE" # 独立事件型


class ConfidenceGrade(str, Enum):
    """认知置信等级"""
    L1_DETERMINISTIC = "L1_DETERMINISTIC"   # 纯数学/物理事实确定
    L2_DERIVED = "L2_DERIVED"               # 统计推导与规则匹配确定
    L3_COGNITIVE = "L3_COGNITIVE"           # 启发式假说推断


# =========================================================================
# 1. 维度 A：后排负反馈指标契约 (Divergence Penalty Metrics)
# =========================================================================

class RearDivergenceMetrics(BaseModel):
    """后排负反馈与分化度量模型 (只读特征)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    sector_code: str = Field(..., description="板块代码")
    trade_date: str = Field(..., description="交易日期 YYYY-MM-DD")
    evaluation_time: str = Field(..., description="计算时间戳 ISO-8601")

    # 核心量化指标
    rear_stock_count: int = Field(..., ge=0, description="后排股票样本总数 |R|")
    rear_negative_ratio: Optional[float] = Field(None, ge=0.0, le=1.0, description="后排股票负收益比例 RNR (样本为0时为 None)")
    avg_spread_fade: float = Field(..., description="后排平均冲高回落价差 ΔGain 均值 (%)")
    avg_peak_pullback: float = Field(..., ge=0.0, le=1.0, description="后排平均最高价回撤比例 Pullback 均值")
    sector_broken_ratio: Optional[float] = Field(None, ge=0.0, le=1.0, description="板块炸板率 BLR_s (无触板时为 None)")
    core_rear_relative_strength: float = Field(..., description="核心与后排相对强度剪刀差 CRRS (%)")

    # 质量审计标记
    is_sample_sufficient: bool = Field(..., description="后排样本是否充足 (|R| >= 5)")
    confidence: ConfidenceGrade = Field(ConfidenceGrade.L2_DERIVED, description="置信度评级")


class NextDayPenaltyLabel(BaseModel):
    """次日负反馈与惩罚结果标签 (事后标签 Y_t+1，严禁渗入特征库)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    sector_code: str = Field(..., description="板块代码")
    next_trade_date: str = Field(..., description="次日交易日期 YYYY-MM-DD")
    labeled_at: str = Field(..., description="打标时间戳 (必须为次日开盘 09:25 或收盘后)")
    next_day_penalty_ratio: float = Field(..., ge=0.0, le=1.0, description="板块成分股次日极端负反馈率 NDPR")
    broken_stocks_next_open_loss_ratio: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="昨日炸板股次日低开幅度超过 -3% 比例 (无炸板股时为 None)"
    )
    leader_next_open_pct: Optional[float] = Field(None, description="领军龙头次日集合竞价开盘涨跌幅 (%)")
    leader_next_success: Optional[bool] = Field(None, description="领军龙头次日是否成功连板晋级")


# =========================================================================
# 2. 维度 B：板块宽度与独苗状态契约 (Breadth & Monopoly Metrics)
# =========================================================================

class SectorBreadthMetrics(BaseModel):
    """板块宽度与独苗状态契约"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    sector_code: str = Field(..., description="板块代码")
    sector_name: str = Field(..., description="板块名称")
    trade_date: str = Field(..., description="交易日期 YYYY-MM-DD")
    pit_constituents_count: int = Field(..., ge=1, description="历史 PIT 成分股总数")

    # 宽度与分布
    breadth_ratio: float = Field(..., ge=0.0, le=1.0, description="上涨家数占比")
    median_pct_change: float = Field(..., description="成分股涨跌幅中位数 (%)")
    limit_up_count: int = Field(..., ge=0, description="收盘涨停家数")
    limit_down_count: int = Field(..., ge=0, description="收盘跌停家数")
    ladder_distribution: Dict[str, int] = Field(default_factory=dict, description="连板梯队分布 {'1B': 3, '2B': 1}")

    # 独苗状态度量
    is_solitary_monopoly: bool = Field(..., description="是否处于涨停独苗状态 (唯1涨停且无首板助攻)")
    monopoly_leader_code: Optional[str] = Field(None, description="独苗领军股票代码")
    monopoly_turnover_ratio: Optional[float] = Field(None, ge=0.0, le=1.0, description="独苗占板块成交比例 (无独苗时为 None)")

    # 板块流动性
    sector_turnover_yi: float = Field(..., ge=0.0, description="板块总成交额 (亿元)")
    market_turnover_share: float = Field(..., ge=0.0, le=1.0, description="占沪深全市场真实总成交比重")


# =========================================================================
# 3. 维度 C：核心股多标签角色契约 (Leader Role Taxonomy Contract)
# =========================================================================

class LeaderRoleItem(BaseModel):
    """单项激活的角色标签 (包含依据、有效时点、置信度与失效条件)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    role: LeaderRoleEnum = Field(..., description="角色枚举")
    confidence: ConfidenceGrade = Field(..., description="置信等级")
    effective_time: str = Field(..., description="生效时间戳 ISO-8601")
    mathematical_evidence: Dict[str, float] = Field(..., description="计算佐证指标 (纯量化数据)")
    invalidation_condition: str = Field(..., description="刚性失效条件判定规则")


class StockRoleTaxonomySnapshot(BaseModel):
    """标的多标签角色聚合画像 (多标签并存拓扑)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    security_id: str = Field(..., description="规范实体主键，如 002242.SZ")
    stock_code: str = Field(..., description="6位股票代码")
    canonical_name: str = Field(..., description="权威证券简称")
    trade_date: str = Field(..., description="评定交易日")
    active_roles: List[LeaderRoleItem] = Field(default_factory=list, description="当前并存的有效角色列表")


# =========================================================================
# 顶层综合认知研究包 (Cognitive Research Packet)
# =========================================================================

class CognitiveResearchPacket(BaseModel):
    """短线核心认知综合研究包 (包含特征与只读溯源血缘)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field("2D.0-RESEARCH-V1", description="契约规范版本")
    trade_date: str = Field(..., description="交易日期 YYYY-MM-DD")
    generated_at: str = Field(..., description="生成时间戳 ISO-8601")
    rear_divergence: List[RearDivergenceMetrics] = Field(default_factory=list, description="各板块后排负反馈度量")
    sector_breadth: List[SectorBreadthMetrics] = Field(default_factory=list, description="各板块宽度与独苗度量")
    stock_roles: List[StockRoleTaxonomySnapshot] = Field(default_factory=list, description="核心股多标签角色拓扑")
