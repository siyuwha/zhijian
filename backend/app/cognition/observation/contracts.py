"""
Cognition 物理事实数据契约模型 (Phase 2A Step 3 Sandbox)
上位依据：
1. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》
2. 董事会工程裁决与批准令：BOARD-APPROVAL-20260930-STEP3
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, timezone, timedelta

BEIJING_TZ = timezone(timedelta(hours=8))


class FactStatus(str, Enum):
    """物理事实观测状态枚举（七大约束语义，严禁用默认值抹平）"""
    AVAILABLE = "AVAILABLE"          # 正常响应，数据完整合法
    EMPTY = "EMPTY"                  # 通信正常但客观事实集为空（如市场零涨停）
    STALE = "STALE"                  # 超时或故障回退读取本地历史快照/缓存
    TIMEOUT = "TIMEOUT"              # 外部数据源网络请求物理超时（严禁伪造为0）
    ERROR = "ERROR"                  # 通道异常、HTTP报错或数据结构损坏
    MISSING = "MISSING"              # 预期指标物理缺失（断言强行输出 INCONCLUSIVE）
    INCONCLUSIVE = "INCONCLUSIVE"    # 多源冲突不可调和或时序倒挂，无法确定


class Freshness(str, Enum):
    """数据新鲜度枚举"""
    REALTIME = "REALTIME"            # 实时数据 (毫秒~秒级)
    DELAYED = "DELAYED"              # 行情延迟 (如15分钟延迟行情)
    STALE = "STALE"                  # 历史缓存或非当日回放
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"  # 离线重放事实
    UNKNOWN = "UNKNOWN"              # 新鲜度未知


class QualityLevel(str, Enum):
    """快照整体质量评定枚举（与单个 FactItem.status 严格物理分层）"""
    FULL = "FULL"                    # 全量事实可用，无严重缺失
    PARTIAL = "PARTIAL"              # 基础事实完备，部分辅助事实缺失但非关键
    DEGRADED = "DEGRADED"            # 存在陈旧事实降级或关键指标次级可用
    INVALID = "INVALID"              # 关键核心事实严重损坏或缺失，不可作为有效推演基准


class FactType(str, Enum):
    """事实业务类型枚举"""
    INDEX_QUOTE = "INDEX_QUOTE"              # 指数行情
    MARKET_BREADTH = "MARKET_BREADTH"        # 市场量能与涨跌家数
    LIMIT_UP_POOL = "LIMIT_UP_POOL"          # 涨停梯队池
    HIGH_TIER_STAT = "HIGH_TIER_STAT"        # 昨日高标早盘开盘溢价
    NEWS_BULLETIN = "NEWS_BULLETIN"          # 财经滚动快讯
    OVERNIGHT_MACRO = "OVERNIGHT_MACRO"      # 隔夜外盘与宏观
    SETTLEMENT_PRICE = "SETTLEMENT_PRICE"    # 个股历史结算收盘价
    INTRADAY_SERIES = "INTRADAY_SERIES"      # 盘中5分钟宏观时序
    INTRADAY_ANOMALY = "INTRADAY_ANOMALY"    # 盘中异动相变事件
    STOCK_SECTOR_MAP = "STOCK_SECTOR_MAP"    # 股票与板块题材映射


class CognitionStage(str, Enum):
    """推演业务阶段枚举"""
    PRE_MARKET = "PRE_MARKET"                # 盘前推演
    MORNING_AUCTION = "MORNING_AUCTION"      # 早盘竞价 (09:15-09:30)
    INTRADAY = "INTRADAY"                    # 盘中连续监控 (09:30-15:00)
    MIDDAY = "MIDDAY"                        # 午间复盘
    POST_CLOSE = "POST_CLOSE"                # 盘后复盘 (15:00)
    NIGHT_REVIEW = "NIGHT_REVIEW"            # 夜盘总评


class WindowType(str, Enum):
    """观测窗口类型"""
    POINT_IN_TIME = "POINT_IN_TIME"          # 时点采样 (如 09:25:00 竞价开盘)
    ACCUMULATIVE_RANGE = "ACCUMULATIVE_RANGE"# 时间区间累计 (如 09:15:00-09:25:00)


class ObservationWindow(BaseModel):
    """观测窗口模型（与 effective_time 严格解耦）"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    window_start: str = Field(description="窗口起始时点 (ISO-8601 或 HH:MM:SS)")
    window_end: str = Field(description="窗口截止时点 (ISO-8601 或 HH:MM:SS)")
    window_type: WindowType = Field(default=WindowType.ACCUMULATIVE_RANGE)

    def is_within(self, event_time_str: str) -> bool:
        """判定某事件时间是否落在本窗口内（支持 HH:MM:SS 或 ISO 时间比较）"""
        t = event_time_str[-8:] if "T" in event_time_str else event_time_str
        s = self.window_start[-8:] if "T" in self.window_start else self.window_start
        e = self.window_end[-8:] if "T" in self.window_end else self.window_end
        return s <= t <= e


class FourDimensionalTime(BaseModel):
    """
    四维时间解耦契约
    event_time: 物理事件发生时点
    observed_time: 系统实际观察时点 (单调时钟)
    ingestion_time: 数据库持久化落盘时点
    effective_time: 业务规则生效起始时点
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_time: str = Field(description="物理世界事实发生时间")
    observed_time: str = Field(description="系统网络抓取到内存的时间")
    ingestion_time: str = Field(description="落库持久化时间")
    effective_time: str = Field(description="业务规则生效时间")

    def is_future_event(self, tolerance_seconds: float = 30.0) -> bool:
        """未来时钟防御：判定 event_time 是否异常大幅晚于 observed_time"""
        try:
            ev = datetime.fromisoformat(self.event_time)
            obs = datetime.fromisoformat(self.observed_time)
            return ev > (obs + timedelta(seconds=tolerance_seconds))
        except Exception:
            return False

    def to_dict(self) -> Dict[str, str]:
        return {
            "event_time": self.event_time,
            "observed_time": self.observed_time,
            "ingestion_time": self.ingestion_time,
            "effective_time": self.effective_time,
        }


class ConflictRecord(BaseModel):
    """多源冲突原始凭证记录（保全双向痕迹，严禁过早丢弃）"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_key: str
    source_a: str
    value_a: Any
    event_time_a: str
    observed_time_a: str
    source_b: str
    value_b: Any
    event_time_b: str
    observed_time_b: str
    difference_metric: str
    rule_applied: str
    resolution: str = "INCONCLUSIVE"


class Provenance(BaseModel):
    """全息血缘追踪模型"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    primary_source: str
    fallback_occurred: bool = False
    fallback_source: Optional[str] = None
    fallback_reason: Optional[str] = None
    primary_error_detail: Optional[str] = None
    trace_id: str = Field(description="全局确定性追踪链路ID")
    duplicate_detected: bool = False
    duplicate_count: int = 0
    original_arrival_order: Optional[int] = None
    conflict_record: Optional[ConflictRecord] = None


class FactContract(BaseModel):
    """
    事实契约定义（按 FactType 显式规定 EMPTY 语义、关键性与 STALE 准入规则）
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_type: FactType
    is_critical: bool = False                 # 关键事实如果失败，整体快照直接 INVALID
    allow_empty: bool = False                # 是否允许 EMPTY 作为合法业务事实进入 Context
    empty_semantic: str = "DISALLOWED"       # "COUNT_ZERO" / "EMPTY_SET" / "DISALLOWED"
    allow_stale_reference: bool = False      # 是否允许陈旧数据作为基准值准入 (默认严禁)


# 系统预设事实契约清单
DEFAULT_FACT_CONTRACTS: Dict[FactType, FactContract] = {
    FactType.INDEX_QUOTE: FactContract(
        fact_type=FactType.INDEX_QUOTE,
        is_critical=True,
        allow_empty=False,
        empty_semantic="DISALLOWED",
        allow_stale_reference=False,
    ),
    FactType.MARKET_BREADTH: FactContract(
        fact_type=FactType.MARKET_BREADTH,
        is_critical=True,
        allow_empty=False,
        empty_semantic="DISALLOWED",
        allow_stale_reference=False,
    ),
    FactType.LIMIT_UP_POOL: FactContract(
        fact_type=FactType.LIMIT_UP_POOL,
        is_critical=False,
        allow_empty=True,
        empty_semantic="COUNT_ZERO",          # 市场零涨停是合法的“数量为0”
        allow_stale_reference=False,
    ),
    FactType.HIGH_TIER_STAT: FactContract(
        fact_type=FactType.HIGH_TIER_STAT,
        is_critical=False,
        allow_empty=True,
        empty_semantic="EMPTY_SET",           # 昨日无连板股时为空集合
        allow_stale_reference=False,
    ),
    FactType.NEWS_BULLETIN: FactContract(
        fact_type=FactType.NEWS_BULLETIN,
        is_critical=False,
        allow_empty=True,
        empty_semantic="EMPTY_SET",           # 非交易时段无快讯为空集合
        allow_stale_reference=False,
    ),
    FactType.OVERNIGHT_MACRO: FactContract(
        fact_type=FactType.OVERNIGHT_MACRO,
        is_critical=False,
        allow_empty=False,
        empty_semantic="DISALLOWED",
        allow_stale_reference=False,
    ),
    FactType.SETTLEMENT_PRICE: FactContract(
        fact_type=FactType.SETTLEMENT_PRICE,
        is_critical=False,
        allow_empty=False,
        empty_semantic="DISALLOWED",
        allow_stale_reference=True,           # 结算价允许读取本地昨日历史缓存作为计算基准
    ),
    FactType.INTRADAY_SERIES: FactContract(
        fact_type=FactType.INTRADAY_SERIES,
        is_critical=False,
        allow_empty=True,
        empty_semantic="EMPTY_SET",           # 盘前或初始时刻无5分钟切片为空集合
        allow_stale_reference=False,
    ),
    FactType.INTRADAY_ANOMALY: FactContract(
        fact_type=FactType.INTRADAY_ANOMALY,
        is_critical=False,
        allow_empty=True,
        empty_semantic="EMPTY_SET",           # 盘中无异常事件时为空集合
        allow_stale_reference=False,
    ),
    FactType.STOCK_SECTOR_MAP: FactContract(
        fact_type=FactType.STOCK_SECTOR_MAP,
        is_critical=False,
        allow_empty=True,
        empty_semantic="EMPTY_SET",           # 样本池为空时为空集合
        allow_stale_reference=False,
    ),
}


class FactItem(BaseModel):
    """单个物理事实项不可变快照对象"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    fact_id: str
    fact_key: str
    fact_type: FactType
    time_context: FourDimensionalTime
    status: FactStatus
    freshness: Freshness
    source: str
    source_record_id: str
    payload: Optional[Dict[str, Any]] = None  # JCS 规范化载荷，严禁假0填充
    provenance: Provenance
    fact_fingerprint: str = ""

    def canonical_dict(self) -> Dict[str, Any]:
        """构建参与 RFC 8785 JCS 规范化与指纹计算的字典（排除自身指纹字段）"""
        return {
            "event_time": self.time_context.event_time,
            "fact_id": self.fact_id,
            "fact_key": self.fact_key,
            "fact_type": self.fact_type.value,
            "freshness": self.freshness.value,
            "payload": self.payload,
            "provenance": self.provenance.model_dump(),
            "source": self.source,
            "source_record_id": self.source_record_id,
            "status": self.status.value,
        }


class SourceCredential(BaseModel):
    """数据源凭证"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_name: str
    fetch_status: str
    latency_ms: float
    records_count: int


class ObservationSnapshot(BaseModel):
    """
    客观物理事实快照（Immutable Value Object）
    记录物理世界真实观测切片，绝非观点或 AI 推论。
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: str
    schema_version: str = "1.0.0"
    market_date: str
    stage: CognitionStage
    observation_window: ObservationWindow
    snapshot_time: str
    overall_quality: QualityLevel
    fact_items: List[FactItem]
    degraded_fields: List[str]
    source_manifest: List[SourceCredential]
    snapshot_fingerprint: str = ""

    def canonical_dict(self) -> Dict[str, Any]:
        """构建快照整体规范化字典（按 fact_key 严格 UTF-16 字典序排列事实项）"""
        sorted_items = sorted(self.fact_items, key=lambda f: f.fact_key.encode("utf-16-be"))
        return {
            "degraded_fields": sorted(self.degraded_fields),
            "fact_items": [f.canonical_dict() for f in sorted_items],
            "market_date": self.market_date,
            "observation_window": self.observation_window.model_dump(),
            "overall_quality": self.overall_quality.value,
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "snapshot_time": self.snapshot_time,
            "source_manifest": [s.model_dump() for s in self.source_manifest],
            "stage": self.stage.value,
        }


class EffectiveInferenceInput(BaseModel):
    """
    法定生效推理输入（Immutable Value Object）
    经过资格网筛选后的合格事实集合与 Rendered Prompt 全文保全对象。
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    input_id: str
    snapshot_id: str
    prompt_id: str
    prompt_version: str
    prompt_hash: str
    inference_metadata: Dict[str, Any]       # 标记为未来运行时元数据，零 LLM 依赖
    admitted_facts: Dict[str, Any]           # 仅收纳合规准入事实 (UTF-16 字典序)
    stale_facts: Dict[str, Any]              # 严格与 admitted_facts 隔离的陈旧事实
    suppressed_facts: List[Dict[str, Any]]   # 违背准入规则被排除的事实清单及原因
    data_quality_warnings: List[str]         # 注入 Prompt 的强制性数据质量警示
    rendered_system_prompt: str
    rendered_user_prompt: str
    effective_input_hash: str = ""

    def canonical_dict(self) -> Dict[str, Any]:
        """构建生效输入参与哈希计算的规范化载荷"""
        return {
            "admitted_facts": self.admitted_facts,
            "data_quality_warnings": sorted(self.data_quality_warnings),
            "inference_metadata": self.inference_metadata,
            "input_id": self.input_id,
            "prompt_hash": self.prompt_hash,
            "prompt_id": self.prompt_id,
            "prompt_version": self.prompt_version,
            "rendered_system_prompt": self.rendered_system_prompt,
            "rendered_user_prompt": self.rendered_user_prompt,
            "snapshot_id": self.snapshot_id,
            "stale_facts": self.stale_facts,
            "suppressed_facts": self.suppressed_facts,
        }
