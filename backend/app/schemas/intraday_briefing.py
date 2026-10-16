"""
Phase 3B: Intraday 4-Stage Briefing & Top 5 Sectors Trend Contracts
==================================================================
上位依据：
1. 用户战略裁决令：4大固定时段盘中内参（09:26 竞价定调、10:15 早盘初战、11:31 午盘综述、14:15 变盘前哨）
2. 科学证伪原则：推断有据，宏微观共振，明确给出成立与不成立的证伪判定硬指标，杜绝模棱两可
3. 历史不覆盖原则：所有时段内参按时间轴保存，供随时回溯
4. 题材战场 Top 5 分时资金多线图与领涨龙头联动看板
"""

from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class IntradayBriefingStageEnum(str, Enum):
    STAGE_1_AUCTION = "STAGE_1_AUCTION"        # 09:26:00 竞价定调
    STAGE_2_MORNING = "STAGE_2_MORNING"        # 10:15:00 早盘初战分歧定型
    STAGE_3_MIDDAY = "STAGE_3_MIDDAY"          # 11:30:30 午盘中继综述
    STAGE_4_AFTERNOON = "STAGE_4_AFTERNOON"    # 14:15:00 两点半变盘前哨


class IntradayQuantitativeIndicators(BaseModel):
    """盘中量化关键指标小黑板"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    projected_volume: str = Field(..., description="时间衰减全天预估总量及放缩比")
    breadth_divergence: str = Field(..., description="黄白剪刀差背离描述")
    broken_ratio: str = Field(..., description="动态炸板大面率及警戒线状态")
    space_height: str = Field(..., description="空间最高板标杆及状态")
    action_advice: str = Field(..., description="当前纪律红线与行动建议")


class IntradayBriefingRecord(BaseModel):
    """单个固定时段 500 字深度操盘内参模型"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: IntradayBriefingStageEnum = Field(..., description="时段标识枚举")
    stage_label: str = Field(..., description="时段标题，如 '① 09:26 竞价定调 · 开盘前5分钟决策'")
    status_badge: str = Field(..., description="微观状态标牌，如 '早盘冲高回落分歧期 · 权重吸血失真'")
    status_color: str = Field(..., description="状态标牌色系 class")
    timing: str = Field(..., description="物理采样时点，如 '采集判定时点: 10:15:00 · 100% 物理真实快照'")
    confidence: str = Field(..., description="置信度声明，如 '置信度 88% · 证据链已闭环'")
    
    # 四段式操盘内参核心字段
    strong_weak_judgment: str = Field(..., description="【强弱定调与宏微观证据】谁强谁弱明确裁决")
    resonance_attribution: str = Field(..., description="【多维共振与博弈归因】形态、资金、消息与监管共振")
    action_inference: str = Field(..., description="【后市明确推断与行动建议】明确方向与建议，拒绝模糊")
    falsification_criteria: str = Field(..., description="【证伪判定硬指标】成立与不成立的清晰边界")
    
    # 结构化渲染内容 (最大 500 字)
    content_html: str = Field(..., description="富文本 HTML 结构化内容")
    quantitative_indicators: IntradayQuantitativeIndicators = Field(..., description="右侧小黑板指标")
    
    evaluated_at: str = Field(..., description="物理生成时间戳")
    trade_date: str = Field(..., description="交易日 YYYY-MM-DD")
    trace_id: str = Field(..., description="端到端审计链路 Trace ID")
    fingerprint: str = Field(..., description="JCS SHA-256 防篡改指纹")


class IntradayBriefingTimelineResponse(BaseModel):
    """当天全天 4 时段内参时间轴信封 (绝不覆盖早先时段)"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    trade_date: str = Field(..., description="交易日期")
    current_active_stage: IntradayBriefingStageEnum = Field(..., description="当前最新激活时段")
    stages: List[IntradayBriefingRecord] = Field(..., description="当天已生成的时段记录列表 (按时间升序排列)")


# =========================================================================
# Top 5 题材分时资金曲线与领涨龙头契约
# =========================================================================

class SectorTrendPoint(BaseModel):
    """单个分钟时间点的数据"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    time: str = Field(..., description="时间 HH:MM")
    net_inflow_yi: float = Field(..., description="累计主力资金净流入 (亿元)")
    pct_change: float = Field(..., description="板块涨跌幅 (%)")


class TopSectorLeaderStock(BaseModel):
    """题材领涨龙头核心"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票简称")
    pct_change: float = Field(..., description="当前涨跌幅 (%)")
    status_desc: str = Field(..., description="龙头地位与盘中表现描述 (如 '领军', '触板', '炸板')")


class TopSectorTrendItem(BaseModel):
    """单个 Top 题材的分时资金与领涨标的"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(..., description="板块代码 (如 'BK0910')")
    name: str = Field(..., description="板块名称 (如 '半导体')")
    rank: int = Field(..., ge=1, le=5, description="排名 1~5")
    color: str = Field(..., description="分时曲线渲染专属发光色 (如 '#8B5CF6')")
    current_net_inflow_yi: float = Field(..., description="当前最新主力净流入 (亿元)")
    current_pct_change: float = Field(..., description="当前最新涨跌幅 (%)")
    leader: TopSectorLeaderStock = Field(..., description="领涨龙头核心")
    trends: List[SectorTrendPoint] = Field(..., description="分时分钟走势序列 (09:30 至当前)")

    # 认知微观体检扩展指标 (可为空/默认值)
    is_solitary_monopoly: Optional[bool] = Field(False, description="是否处于独苗高标状态")
    monopoly_turnover_ratio: Optional[float] = Field(None, description="独苗占板块成交比例 (0.0~1.0)")
    core_rear_relative_strength: Optional[float] = Field(None, description="核心与后排相对剪刀差 CRRS (%)")
    rear_negative_ratio: Optional[float] = Field(None, description="后排股票负收益比例 RNR (0.0~1.0)")
    sector_broken_ratio: Optional[float] = Field(None, description="板块炸板率 BLR (0.0~1.0)")


class TopSectorsTrendResponse(BaseModel):
    """Top 5 题材分时资金争夺多线数据信封"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    trade_date: str = Field(..., description="交易日 YYYY-MM-DD")
    snapshot_time: str = Field(..., description="采样时间 HH:MM:SS")
    sectors: List[TopSectorTrendItem] = Field(..., description="Top 5 题材列表")
