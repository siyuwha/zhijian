"""
Phase 2E.1: Canonical Auction Data Contract (09:25 竞价物理快照契约)
===================================================================
上位依据：
1. 最高董事会终审裁决令：《PHASE 2E.1 AUTHORIZED WITH REMEDIATIONS》
2. 《DOC-89 · Phase 2E 09:25 集合竞价自动对账与次日波普尔证伪闭环技术设计单》

刚性工程准则：
- 严格遵循单向依赖：只能消费已冻结的 CanonicalMarketSnapshot 与 SecurityMasterRegistry；
- 贯彻 Decimal 高保真与防重算会计准则；
- 继承 RFC 8785 JCS 不可变数字指纹与血缘元数据信封。
"""

from typing import Optional, List, Dict, Any, Literal
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

from backend.app.schemas.canonical_market import (
    ProvenanceEnvelope,
    TruthSource,
    DataQualityGrade,
    CanonicalSecurityIdentity,
)


class BiddingStatusEnum(str, Enum):
    NORMAL = "NORMAL"
    LIMIT_UP_BIDDING = "LIMIT_UP_BIDDING"      # 一字涨停竞价封死
    LIMIT_DOWN_BIDDING = "LIMIT_DOWN_BIDDING"  # 一字跌停竞价封死
    SUSPENDED = "SUSPENDED"                    # 停牌


class StockAuctionQuote(BaseModel):
    """
    单个核心标的 09:25 撮合开盘物理行情契约
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(..., description="6位数字规范股票代码 (如 '600825')")
    name: str = Field(..., description="规范证券简称 (如 '新华传媒')")
    canonical_symbol: str = Field(..., description="规范证券全局主键 (如 '600825.SH')")
    
    yesterday_close: Decimal = Field(..., gt=0, description="前一交易日收盘价 (元)")
    auction_price: Decimal = Field(..., ge=0, description="09:25 撮合开盘价 (元，停牌可为0)")
    auction_pct_change: Decimal = Field(..., description="竞价开盘涨跌幅 (%)，精确到2位小数")
    auction_turnover_wan: Decimal = Field(..., ge=0, description="09:25 竞价撮合成交额 (万元)")
    
    auction_volume_ratio_pct: Optional[Decimal] = Field(
        None, ge=0, description="竞价成交额占前日全天总成交比值 (%)"
    )
    bidding_status: BiddingStatusEnum = Field(
        default=BiddingStatusEnum.NORMAL, description="竞价封死或特殊状态"
    )
    open_order_imbalance_wan: Optional[Decimal] = Field(
        None, description="09:25 未匹配封单买卖差额 (万元，正为买盘，负为卖盘)"
    )
    
    # 认知角色标记 (由前夜战报血缘继承)
    is_space_leader: bool = Field(False, description="是否为前日全市场空间标杆")
    is_mainline_leader: bool = Field(False, description="是否为前日 Top 3 主线领军标的")
    bound_mainline_name: Optional[str] = Field(None, description="所属前日主线板块名称")


class CanonicalAuctionIndexQuote(BaseModel):
    """
    宽基指数 09:25 竞价开盘切片
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(..., description="标准指数代码 (如 'sh000001')")
    name: str = Field(..., description="指数名称 (如 '上证指数')")
    open_price: Decimal = Field(..., gt=0, description="09:25 开盘点位")
    pre_close: Decimal = Field(..., gt=0, description="昨收盘点位")
    change_val: Decimal = Field(..., description="开盘涨跌点数")
    pct_change: Decimal = Field(..., description="开盘涨跌幅 (%)")
    amount_yi: Decimal = Field(..., ge=0, description="竞价成交额 (亿元)")


class CanonicalAuctionSnapshot(BaseModel):
    """
    全市场 09:25 集合竞价物理事实快照契约 (Phase 2E.1 核心数据底盘)
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    trade_date: str = Field(..., description="T+1 交易日 YYYY-MM-DD")
    observed_time: str = Field(..., description="物理采样时间 HH:MM:SS，如 '09:25:05'")
    prev_trade_date: str = Field(..., description="T 交易日 (所绑定的基准复盘日期)")
    
    # 单向血缘绑定 (严格指向 T 日 Canonical 快照与战报)
    bound_snapshot_trace_id: str = Field(..., description="绑定的前日快照 Trace ID")
    bound_snapshot_fingerprint: str = Field(..., description="绑定的前日快照 JCS SHA-256 指纹")
    bound_briefing_fingerprint: Optional[str] = Field(None, description="绑定的前日战报 JCS SHA-256 指纹")

    # 宽基与流动性事实
    indices: List[CanonicalAuctionIndexQuote] = Field(..., description="核心宽基指数竞价列表")
    sh_auction_turnover_yi: Decimal = Field(..., ge=0, description="上交所竞价成交额 (亿元)")
    sz_auction_turnover_yi: Decimal = Field(..., ge=0, description="深交所竞价成交额 (亿元，已含创业板)")
    total_auction_turnover_yi: Decimal = Field(
        ..., ge=0, description="沪深两市竞价总额 (亿元，严格 sh + sz，严禁重复累加创业板)"
    )
    prev_total_turnover_yi: Decimal = Field(..., gt=0, description="前日沪深真实总成交额 (亿元)")
    auction_turnover_ratio_pct: Decimal = Field(
        ..., ge=0, description="两市竞价总额占前日全天比值 (%)"
    )

    # 重点观测标的竞价阵列 (空间标杆 + Top 3 主线领军)
    leader_quotes: List[StockAuctionQuote] = Field(..., description="核心观测标的竞价行情")

    # 系统物理状态与品质
    is_trading_day: bool = Field(True, description="是否为真实开盘交易日")
    data_quality: DataQualityGrade = Field(default=DataQualityGrade.FULL, description="数据质量等级")
    envelope: ProvenanceEnvelope = Field(..., description="数据来源与观测信封")

    # 不可变 RFC 8785 JCS 防伪指纹
    auction_fingerprint: str = Field(..., description="本竞价快照的 JCS SHA-256 数字指纹")
