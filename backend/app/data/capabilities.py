from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

class DataQuality(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    INVALID = "invalid"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"

@dataclass
class DataResult:
    """统一数据返回结构"""
    data: Any
    quality: DataQuality
    provider: str                      # 实际提供数据的 Provider 名称
    timestamp: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    fallback_used: bool = False

class IndexQuoteCapability(ABC):
    """A股指数行情能力 (D1 / D6)"""
    @abstractmethod
    async def get_index_quotes(self, codes: list[str]) -> DataResult:
        """获取主要指数行情（如 sh000001, sz399001, sz399006, sh000688 等）"""
        pass

class StockQuoteCapability(ABC):
    """A股个股行情能力"""
    @abstractmethod
    async def get_stock_quotes(self, codes: list[str]) -> DataResult:
        """批量获取个股行情"""
        pass

class LimitUpCapability(ABC):
    """涨跌停与连板情绪能力 (D2 / D3)"""
    @abstractmethod
    async def get_limit_up_pool(self, date: Optional[str] = None) -> DataResult:
        """获取涨停池明细、连板梯队、跌停数及炸板数据"""
        pass

class MarketBreadthCapability(ABC):
    """全市场涨跌广度能力 (D2)"""
    @abstractmethod
    async def get_market_breadth(self) -> DataResult:
        """获取全市场上涨家数、下跌家数、平盘家数"""
        pass

class MicroCapCapability(ABC):
    """微盘股/风格偏好能力 (D4 - 抽象接口，不绑定具体代码与Provider)"""
    @abstractmethod
    async def get_micro_cap_quote(self) -> DataResult:
        """获取微盘股指数或代理标的的行情变动"""
        pass

class ExternalRiskCapability(ABC):
    """外部衍生品与风险指标能力 (D5)"""
    @abstractmethod
    async def get_external_risk(self) -> DataResult:
        """获取 A50 变动及标准化多空指标（若不可靠则返回 UNAVAILABLE/PARTIAL）"""
        pass

class HighTierPerformanceCapability(ABC):
    """高位股表现扩展能力接口 (D3 扩展槽位，不固化具体股票池)"""
    @abstractmethod
    async def get_high_tier_performance(self) -> DataResult:
        """评估高位核心标的次日承接表现"""
        pass

class OvernightCapability(ABC):
    """隔夜外盘数据能力 (D5 外部背景)"""
    @abstractmethod
    async def get_overnight_data(self) -> DataResult:
        """获取美股/亚太隔夜数据"""
        pass

class SettlementCapability(ABC):
    """指数/股票日线结算数据能力"""
    @abstractmethod
    async def get_daily_settlement(self, code: str, date: str) -> DataResult:
        """获取日线结算 OHLCV 数据"""
        pass

class NewsCapability(ABC):
    """财经快讯与新闻聚合能力"""
    @abstractmethod
    async def get_latest_news(self, count: int = 15) -> DataResult:
        """获取最新财经快讯"""
        pass

class SectorCapability(ABC):
    """板块排行能力"""
    @abstractmethod
    async def get_sector_ranking(self, sector_type: str = "industry") -> DataResult:
        pass

class CapitalFlowCapability(ABC):
    """资金流向能力"""
    @abstractmethod
    async def get_capital_flow(self, code: str) -> DataResult:
        pass

class SecuritySearchCapability(ABC):
    """证券主数据与代码/名称/拼音模糊搜索能力"""
    @abstractmethod
    async def search_security(self, query: str, limit: int = 10) -> DataResult:
        """根据代码、中文简称或拼音首字母模糊搜索证券"""
        pass

