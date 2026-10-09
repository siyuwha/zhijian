"""
Phase 3B.1: Canonical Drift Alert Event Schema Contract
========================================================
上位依据：
1. 最高董事会裁决令：《VERDICT-PHASE3A-CLOSE-PHASE3B1-GATE-20261009》
2. 《DOC-98 · Phase 3B 盘中多源告警通知总线与受控防御编排技术设计单》

刚性工程准则：
- 严格区分内容哈希 (RFC 8785 JCS SHA-256) 与源端数字签名 (HMAC-SHA256)；
- 继承 Merkle Hash Chain 链式防篡改指针 (prev_event_hash)；
- 刚性校验 deduplication_key 字符白名单，防止去重作用域注入穿透；
- 严格携带四维时间戳与物理数据年龄 (data_age_seconds)。
"""

import re
import hmac
import hashlib
from typing import Optional, List, Dict, Any
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, field_validator

from backend.app.schemas.canonical_intraday import IntradayStageEnum
from backend.app.cognition.jcs import hash_jcs


class AlertSeverityEnum(str, Enum):
    """告警严重度等级"""
    INFO = "INFO"          # 提示级：正常对齐演进，或时间窗口状态切换
    WARNING = "WARNING"    # 预警级：中度偏离、量能偏离 10%~20%、主线轻度分歧
    CRITICAL = "CRITICAL"  # 严重级：空间龙炸板核按钮、主线全面倒戈、流动性断崖衰竭


class AlertCategoryEnum(str, Enum):
    """告警事件分类枚举"""
    SPACE_LEADER_COLLAPSE = "SPACE_LEADER_COLLAPSE"       # 空间标杆破位 (一票否决)
    MAINLINE_TOTAL_REVERSAL = "MAINLINE_TOTAL_REVERSAL"   # 主线龙头反转
    LIQUIDITY_FLASH_DRY = "LIQUIDITY_FLASH_DRY"           # 量能断崖萎缩
    BREADTH_PANIC_DIVERGENCE = "BREADTH_PANIC_DIVERGENCE" # 炸板率与恐慌分歧
    STAGE_TRANSITION = "STAGE_TRANSITION"                 # 4 阶段时间窗口迁移
    SAFETY_INTERCEPTION = "SAFETY_INTERCEPTION"           # 安全守卫违规拦截


# 严格白名单：去重键仅允许英文字母、数字、下划线、中划线和英文点
DEDUP_KEY_REGEX = re.compile(r"^[A-Za-z0-9_.:-]+$")


class CanonicalDriftAlertEvent(BaseModel):
    """
    Phase 3B 规范盘中多源告警事件契约 (不可变数据载荷)
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    # 事件全局唯一标识与血缘追溯
    alert_id: str = Field(..., description="事件全局唯一主键 ALERT-YYYY-MM-DD-<stage>-<hash8>")
    trade_date: str = Field(..., description="归属交易日 YYYY-MM-DD")
    observed_at: str = Field(..., description="物理微观事实快照采样时戳 (ISO-8601)")
    requested_at: str = Field(..., description="查询/处理请求发起物理时戳 (ISO-8601)")
    evaluated_at: str = Field(..., description="引擎评估执行时戳 (ISO-8601)")
    generated_at: str = Field(..., description="告警事件实例化时戳 (ISO-8601)")
    expires_at: str = Field(..., description="告警事件有效期截止时戳 (过期自动作废)")
    data_age_seconds: float = Field(..., ge=0.0, description="物理数据年龄: T_requested - T_observed (秒)")
    trace_id: str = Field(..., description="单请求贯穿式 Trace ID")
    version: str = Field("1.0.0", description="事件契约版本号")

    # 去重与抑制键 (正则强制白名单约束)
    deduplication_key: str = Field(..., description="去重键: <date>:<stage>:<category>:<symbol>")

    # 告警语义与分级
    severity: AlertSeverityEnum = Field(..., description="告警严重度等级")
    category: AlertCategoryEnum = Field(..., description="告警事件分类")
    stage: IntradayStageEnum = Field(..., description="触发时所处盘中 4 阶段时间窗口")
    headline: str = Field(..., description="纯客观描述性标题 (绝对禁止包含买卖诱导)")
    detail_facts: Dict[str, Any] = Field(..., description="微观客观事实键值对 (数值/比率/阈值)")

    # 封闭防守行动边界条件 (纯负向防守限制)
    preservation_boundaries: List[str] = Field(
        default_factory=list, description="系统推导的负向防守保留边界"
    )

    # 时效与状态标记
    is_out_of_order: bool = Field(False, description="是否为乱序/迟到事件")
    is_stale: bool = Field(False, description="数据是否已超出新鲜度阈值 (Data Age > 180s)")

    # 防伪签名与证据绑定 (严格区分内容哈希与源端签名)
    verdict_fingerprint: str = Field(..., description="绑定的 IntradayDriftVerdict JCS SHA-256 指纹")
    prev_event_hash: Optional[str] = Field(None, description="前序事件哈希指针 (Merkle 链式绑定)")
    content_hash: str = Field(..., description="事件不可变载荷 RFC 8785 JCS SHA-256 内容哈希")
    origin_signature: str = Field(..., description="源端私钥 HMAC-SHA256 身份认证数字签名")

    @field_validator("deduplication_key")
    @classmethod
    def validate_dedup_key(cls, v: str) -> str:
        if not DEDUP_KEY_REGEX.match(v):
            raise ValueError(f"Deduplication key '{v}' contains forbidden characters. Must match {DEDUP_KEY_REGEX.pattern}")
        return v

    @classmethod
    def compute_content_hash(cls, payload: Dict[str, Any]) -> str:
        """计算 RFC 8785 JCS 规范内容哈希 (排除 content_hash 和 origin_signature 本身)"""
        clean = {k: v for k, v in payload.items() if k not in ("content_hash", "origin_signature")}
        return hash_jcs(clean)

    @classmethod
    def compute_origin_signature(cls, content_hash: str, secret_key: str = "INTRADAY_ALERT_BUS_SECRET_20261009") -> str:
        """基于可信源端密钥生成 HMAC-SHA256 数字签名"""
        return hmac.new(secret_key.encode("utf-8"), content_hash.encode("utf-8"), hashlib.sha256).hexdigest()

    def verify_signatures(self, secret_key: str = "INTRADAY_ALERT_BUS_SECRET_20261009") -> bool:
        """双重校验内容防伪哈希与数字签名"""
        expected_hash = self.compute_content_hash(self.model_dump())
        if self.content_hash != expected_hash:
            return False
        expected_sig = self.compute_origin_signature(self.content_hash, secret_key)
        return hmac.compare_digest(self.origin_signature, expected_sig)
