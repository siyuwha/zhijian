"""
Phase 3A.1: Canonical Intraday Data Contract (盘中微观行情切片与量能投影契约)
=============================================================================
上位依据：
1. 最高董事会终审裁决令：《DOC-92 APPROVED WITH REMEDIATIONS & PHASE 3A.1 AUTHORIZED》
2. 《DOC-92 · Phase 3A 盘中 4 阶段动态跟踪与认知偏离实时告警系统技术设计单》

刚性工程准则：
- 严格单向血缘依赖：消费已冻结的 CanonicalMarketSnapshot 与 CanonicalAuctionSnapshot；
- 贯彻 Decimal 会计准则与防重算原则；
- 继承 RFC 8785 JCS 不可变数字指纹与血缘元数据信封。
"""

from typing import Optional, List, Dict, Any, Literal
from decimal import Decimal, ROUND_HALF_UP
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

from backend.app.schemas.canonical_market import (
    ProvenanceEnvelope,
    TruthSource,
    DataQualityGrade,
    CanonicalSecurityIdentity,
)


class IntradayStageEnum(str, Enum):
    """盘中 4 阶段时间窗口枚举"""
    STAGE_1_OPENING = "STAGE_1_OPENING"        # 09:30 - 10:00 龙头确认与分歧承接期
    STAGE_2_MORNING = "STAGE_2_MORNING"        # 10:00 - 11:30 主线定型与量能趋势期
    LUNCH_BREAK = "LUNCH_BREAK"                # 11:30 - 13:00 午间休市
    STAGE_3_AFTERNOON = "STAGE_3_AFTERNOON"    # 13:00 - 14:30 午后异动与情绪拐点期
    STAGE_4_CLOSING = "STAGE_4_CLOSING"        # 14:30 - 15:00 尾盘博弈与次日预设期
    OFF_MARKET = "OFF_MARKET"                  # 盘前、盘后或非交易日休市


class StockIntradayQuote(BaseModel):
    """
    重点观测标的盘中连续竞价切片契约
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(..., description="6位数字规范股票代码 (如 '600825')")
    name: str = Field(..., description="规范证券简称 (如 '新华传媒')")
    canonical_symbol: str = Field(..., description="规范证券全局主键 (如 '600825.SH')")
    
    yesterday_close: Decimal = Field(..., gt=0, description="前一交易日收盘价 (元)")
    open_price: Decimal = Field(..., ge=0, description="今日开盘价 (元)")
    current_price: Decimal = Field(..., ge=0, description="当前最新价 (元)")
    high_price: Decimal = Field(..., ge=0, description="今日最高价 (元)")
    low_price: Decimal = Field(..., ge=0, description="今日最低价 (元)")
    pct_change: Decimal = Field(..., description="当前涨跌幅 (%)")
    turnover_wan: Decimal = Field(..., ge=0, description="累计成交额 (万元)")
    volume_wan: Decimal = Field(..., ge=0, description="累计成交量 (万股)")
    
    # 盘中微观异动状态
    is_limit_up: bool = Field(False, description="当前是否封住涨停")
    is_broken_limit: bool = Field(False, description="今日是否曾触及涨停但当前开板/炸板")
    is_limit_down: bool = Field(False, description="当前是否封住跌停")
    
    # 认知血缘绑定 (由前夜战报与今晨竞价快照继承)
    is_space_leader: bool = Field(False, description="是否为全市场最高空间标杆")
    is_mainline_leader: bool = Field(False, description="是否为 Top 3 主线领军标的")
    bound_mainline_name: Optional[str] = Field(None, description="所属前日主线板块名称")


class CanonicalIntradayIndexQuote(BaseModel):
    """
    宽基指数盘中切片契约
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(..., description="标准指数代码 (如 'sh000001')")
    name: str = Field(..., description="指数名称 (如 '上证指数')")
    current_price: Decimal = Field(..., gt=0, description="当前指数点位")
    pre_close: Decimal = Field(..., gt=0, description="昨收盘点位")
    change_val: Decimal = Field(..., description="当前涨跌点数")
    pct_change: Decimal = Field(..., description="当前涨跌幅 (%)")
    amount_yi: Decimal = Field(..., ge=0, description="累计成交额 (亿元)")


class CanonicalIntradaySnapshot(BaseModel):
    """
    全市场盘中微观事实快照契约 (Phase 3A.1 核心数据底盘)
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    trade_date: str = Field(..., description="交易日 YYYY-MM-DD")
    snapshot_time: str = Field(..., description="物理采样时间 HH:MM:SS，如 '10:15:00'")
    stage: IntradayStageEnum = Field(..., description="当前盘中时间窗口")
    elapsed_trading_minutes: int = Field(..., ge=0, le=240, description="当日已开市连续交易分钟数 (0~240)")

    # 量能投影与累计成交额 (严格去重，防重复累加创业板)
    sh_accumulated_turnover_yi: Decimal = Field(..., ge=0, description="上交所累计成交额 (亿元)")
    sz_accumulated_turnover_yi: Decimal = Field(..., ge=0, description="深交所累计成交额 (亿元，已含创业板)")
    total_accumulated_turnover_yi: Decimal = Field(
        ..., ge=0, description="沪深两市累计成交总额 (亿元，严格 sh + sz)"
    )
    prev_total_turnover_yi: Decimal = Field(..., gt=0, description="前一交易日两市真实全天总成交 (亿元)")
    projected_turnover_yi: Decimal = Field(
        ..., ge=0, description="基于交易分钟时间衰减模型预估的全天成交总额 (亿元)"
    )
    turnover_pace_ratio_pct: Decimal = Field(
        ..., ge=0, description="预估全天成交与前日全天成交比率 (%)，100% 为平量"
    )

    # 宽基与核心观测标的
    indices: List[CanonicalIntradayIndexQuote] = Field(..., description="核心宽基指数实时切片")
    leader_quotes: List[StockIntradayQuote] = Field(..., description="核心观测标的实时切片")

    # 市场广度统计
    up_count: int = Field(..., ge=0, description="上涨家数")
    down_count: int = Field(..., ge=0, description="下跌家数")
    flat_count: int = Field(..., ge=0, description="平盘家数")
    limit_up_count: int = Field(..., ge=0, description="当前封死涨停家数")
    limit_down_count: int = Field(..., ge=0, description="当前封死跌停家数")
    broken_limit_count: int = Field(..., ge=0, description="曾涨停开板家数")
    broken_limit_ratio_pct: Decimal = Field(..., ge=0, le=100, description="炸板率 (%)")

    # 单向因果血缘锚点
    prev_trade_date: str = Field(..., description="基准前日交易日 YYYY-MM-DD")
    bound_snapshot_trace_id: str = Field(..., description="绑定的前日 EOD 收盘快照 Trace ID")
    bound_snapshot_fingerprint: str = Field(..., description="绑定的前日 EOD 收盘快照 JCS 指纹")
    bound_auction_trace_id: Optional[str] = Field(None, description="绑定的今晨 09:25 竞价快照 Trace ID")
    bound_auction_fingerprint: Optional[str] = Field(None, description="绑定的今晨 09:25 竞价快照 JCS 指纹")

    # 系统物理状态与品质
    is_trading_day: bool = Field(True, description="是否为真实交易日")
    data_quality: DataQualityGrade = Field(default=DataQualityGrade.FULL, description="数据质量等级")
    envelope: ProvenanceEnvelope = Field(..., description="数据来源与观测信封")

    # 不可变 RFC 8785 JCS 防伪指纹
    snapshot_fingerprint: str = Field(..., description="本盘中快照的 JCS SHA-256 数字指纹")
