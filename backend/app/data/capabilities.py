from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

class DataQuality(str, Enum):
    """
    数据完整度与质量等级 (Data Integrity & Quality)
    严格反映数据内容的完整性与可信程度，与时间时态完全正交。
    """
    FULL = "FULL"                # 全部核心指标与次要维度完备，数值完全自洽
    PARTIAL = "PARTIAL"          # 核心指标可用，但部分非关键次要指标缺失或未就绪
    DEGRADED = "DEGRADED"        # 核心指标通过降级途径提供 (如切换至备用源，或使用容忍期内的历史快照)
    INVALID = "INVALID"          # 数据协议畸变、校验失败或数值严重失真 (坚决丢弃，不提供给上层)
    UNAVAILABLE = "UNAVAILABLE"  # 所有物理数据源断流且无有效快照缓存 (显式报错，绝不填 0)
    FAILED = "FAILED"            # 兼容性别名，等同于 UNAVAILABLE / 失败

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            val_upper = value.upper()
            for member in cls:
                if member.value == val_upper or member.name == val_upper:
                    return member
        return super()._missing_(value)

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other.upper() or self.value == other
        return super().__eq__(other)

    def __hash__(self):
        return hash(self.value)

class Freshness(str, Enum):
    """
    数据新鲜度与时态语义 (Temporal Freshness & Price Semantics)
    严格反映数据所对应的物理时间窗口与价格语义，与数据质量完全正交。
    """
    REALTIME = "REALTIME"                # 盘中高频实时数据 (<15s 采样滞后)
    DELAYED = "DELAYED"                  # 延迟行情 (通常为 15 分钟以上延时，禁止用于突破信号)
    EOD_COMPENSATED = "EOD_COMPENSATED"  # 收盘日终结算补偿价 (盘后资产核算专用，严禁当作盘中最新跳动)
    STALE = "STALE"                      # 超过正常采样周期，使用可接受容忍窗口内的最后有效已知快照
    EXPIRED = "EXPIRED"                  # 严重过期失效，已丧失时效参考价值
    UNAVAILABLE = "UNAVAILABLE"          # 物理数据缺失，无时态信息

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            val_upper = value.upper()
            for member in cls:
                if member.value == val_upper or member.name == val_upper:
                    return member
        return super()._missing_(value)

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other.upper() or self.value == other
        return super().__eq__(other)

    def __hash__(self):
        return hash(self.value)

class DataStatus(str, Enum):
    """
    数据源物理状态与可用性语义 (Data Source Availability & Health Status)
    按最高裁决严格区分：
    - AVAILABLE: 正常有效获取
    - EMPTY: 接口正常响应但数据集为空（非异常，如非交易时段空响应或无新资讯）
    - STALE: 缓存过期或降级历史快照
    - TIMEOUT: 网络/服务端物理超时
    - ERROR: 接口异常/解析错误/网络阻断
    杜绝以“空字符串 + JSON Parse Error”表达缺失。
    """
    AVAILABLE = "AVAILABLE"
    EMPTY = "EMPTY"
    STALE = "STALE"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            val_upper = value.upper()
            for member in cls:
                if member.value == val_upper or member.name == val_upper:
                    return member
        return super()._missing_(value)

    def __eq__(self, other):
        if isinstance(other, str):
            return self.value == other.upper() or self.value == other
        return super().__eq__(other)

    def __hash__(self):
        return hash(self.value)

class ProviderErrorCode(str, Enum):
    """标准化提供者错误码"""
    NONE = "NONE"
    TIMEOUT = "TIMEOUT"                  # 网络/服务端物理超时 (>=5000ms)
    CONNECTION_ERROR = "CONNECTION_ERROR"# 网络连接失败 / TCP断开 / DNS解析失败
    HTTP_ERROR = "HTTP_ERROR"            # 4xx / 5xx HTTP 异常
    WAF_BLOCKED = "WAF_BLOCKED"          # 触发远端 WAF / 验证码 / IP 限制
    EMPTY_PAYLOAD = "EMPTY_PAYLOAD"      # 数据源返回空内容 / 零字节
    MALFORMED_PARSE = "MALFORMED_PARSE"  # JSON/文本协议解析崩溃 / 乱码
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"  # 核心业务字段缺失
    SEMANTIC_INVALID = "SEMANTIC_INVALID"# 数值逻辑异常 (如现价<=0，成交量为负)
    RATE_LIMITED = "RATE_LIMITED"        # 触达本地预算或远端限流

@dataclass(frozen=True)
class ProviderRequest:
    """标准化请求契约"""
    capability: str
    method: str
    symbols: List[str] = field(default_factory=list)
    date: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 5000
    trace_id: str = ""

@dataclass
class ProviderResponse:
    """标准化响应契约 (所有 Provider 产出的物理快照)"""
    data: Any
    provider: str
    capability: str
    quality: DataQuality
    freshness: Freshness
    latency_ms: int = 0
    source_timestamp: Optional[datetime] = None
    received_timestamp: datetime = field(default_factory=datetime.now)
    validity: bool = True
    error_code: ProviderErrorCode = ProviderErrorCode.NONE
    error_message: Optional[str] = None
    observation_id: str = ""
    fallback_used: bool = False
    status: Optional[DataStatus] = None

    def get_status(self) -> DataStatus:
        if self.status:
            return self.status
        if self.error_code == ProviderErrorCode.TIMEOUT:
            return DataStatus.TIMEOUT
        if self.freshness == Freshness.STALE:
            return DataStatus.STALE
        if self.error_code in (ProviderErrorCode.MALFORMED_PARSE, ProviderErrorCode.HTTP_ERROR, ProviderErrorCode.CONNECTION_ERROR) or (self.quality in (DataQuality.INVALID, DataQuality.FAILED) and self.error_code != ProviderErrorCode.NONE):
            return DataStatus.ERROR
        if self.error_code == ProviderErrorCode.EMPTY_PAYLOAD or (self.data is None and self.quality in (DataQuality.UNAVAILABLE, DataQuality.PARTIAL)):
            return DataStatus.EMPTY
        if self.quality in (DataQuality.FULL, DataQuality.PARTIAL) and self.data is not None:
            return DataStatus.AVAILABLE
        return DataStatus.AVAILABLE

    def to_data_result(self) -> "DataResult":
        return DataResult(
            data=self.data,
            quality=self.quality,
            provider=self.provider,
            timestamp=self.received_timestamp,
            error_message=self.error_message,
            fallback_used=self.fallback_used,
            freshness=self.freshness,
            latency_ms=self.latency_ms,
            error_code=self.error_code,
            observation_id=self.observation_id,
            status=self.get_status(),
        )

@dataclass
class DataResult:
    """统一数据返回结构 (兼顾既有业务消费与 P2 标准契约)"""
    data: Any
    quality: DataQuality
    provider: str                      # 实际提供数据的 Provider 名称
    timestamp: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    fallback_used: bool = False
    freshness: Freshness = Freshness.REALTIME
    latency_ms: int = 0
    error_code: ProviderErrorCode = ProviderErrorCode.NONE
    observation_id: str = ""
    status: Optional[DataStatus] = None

    def __post_init__(self):
        if self.status is None:
            if self.error_code == ProviderErrorCode.TIMEOUT:
                self.status = DataStatus.TIMEOUT
            elif self.freshness == Freshness.STALE:
                self.status = DataStatus.STALE
            elif self.error_code in (ProviderErrorCode.MALFORMED_PARSE, ProviderErrorCode.HTTP_ERROR, ProviderErrorCode.CONNECTION_ERROR):
                self.status = DataStatus.ERROR
            elif self.quality in (DataQuality.INVALID, DataQuality.FAILED) and self.error_code != ProviderErrorCode.NONE:
                self.status = DataStatus.ERROR
            elif self.error_code == ProviderErrorCode.EMPTY_PAYLOAD or (self.data is None and self.quality in (DataQuality.UNAVAILABLE, DataQuality.PARTIAL)):
                self.status = DataStatus.EMPTY
            elif self.quality in (DataQuality.FULL, DataQuality.PARTIAL) and self.data is not None:
                self.status = DataStatus.AVAILABLE
            else:
                self.status = DataStatus.AVAILABLE if self.data is not None else DataStatus.EMPTY

    def to_provider_response(self, capability: str = "unknown") -> ProviderResponse:
        return ProviderResponse(
            data=self.data,
            provider=self.provider,
            capability=capability,
            quality=self.quality,
            freshness=self.freshness,
            latency_ms=self.latency_ms,
            source_timestamp=self.timestamp,
            received_timestamp=self.timestamp,
            validity=self.quality not in (DataQuality.INVALID, DataQuality.UNAVAILABLE),
            error_code=self.error_code,
            error_message=self.error_message,
            observation_id=self.observation_id,
            fallback_used=self.fallback_used,
            status=self.status,
        )

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
