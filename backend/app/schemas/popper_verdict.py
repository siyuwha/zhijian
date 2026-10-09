"""
Phase 2E.2: Popperian Bidding Comparator & Verdict Contract
============================================================
上位依据：
1. 最高董事会裁决令：《BOARD-DECISION-PHASE2E2-CONTROLLED-GO-20261009》
2. 《DOC-89 · Phase 2E 09:25 集合竞价自动对账与次日波普尔证伪闭环技术设计单》

四大刚性设计准则（董事会授权令第 3 条刚性约束）：
------------------------------------------------------------
A. 先质检再断言原则：
   - 必须优先检查输入数据的完整性、交易日状态与质量信封；
   - 若证据不足或物理休市，严格路由至 INCONCLUSIVE，绝对禁止默认 CONFIRMED，亦绝对禁止将数据缺失误判为 FALSIFIED。

B. 不可变与抗篡改边界准则（严禁夸大 WORM）：
   1. Pydantic 模型 (frozen=True, extra="forbid")：仅提供应用进程内存生命周期内的只读对象守卫，防止运行时属性篡改与野字段注入；
   2. SQLite 文件写入保护：仅提供单机关系数据库层面的 SQL 事务与触发器防护，防止代码误写；
   3. 真正的不可伪造与抗篡改：依赖 RFC 8785 JCS (JSON Canonicalization Scheme) 与 SHA-256 数字指纹，任何比特级篡改均导致指纹雪崩失配并被下游拒绝；
   *本系统不宣称具备物理光盘级硬件 WORM 或分布式区块链不可撤销写入特性，防篡改由密码学指纹链路提供数学保障*。

C. 市场成交额与指数成交额口径区分：
   - 必须严格区分【宽基指数成分股成交额】与【交易所全市场总成交额】；
   - 上交所全市场成交额与深交所全市场成交额（已包含创业板全市场成交额）相加构成两市全市场总成交额；
   - 严禁将创业板指数（399006）成交额在两市总额上重复累加（防双重记账会计铁律）。

D. 五位一体相互复核：
   - 对账单必须同时封装：原始假说身份、规则版本、阈值配置指纹、竞价事实指纹及全链路 Trace ID，实现跨周期穿透核验。
"""

from typing import List, Optional, Dict, Any
from decimal import Decimal
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class FalsificationOutcomeEnum(str, Enum):
    """
    波普尔证伪三态 + 独立证据不足状态（MECE 互斥状态枚举）
    """
    CONFIRMED = "CONFIRMED"       # 假说得到验证与强化 (全部断言落入预期容差区间)
    DIVERGENT = "DIVERGENT"       # 假说呈现温和分歧 (无致命证伪，但存在次级或量能预期偏离)
    FALSIFIED = "FALSIFIED"       # 刚性证伪 (空间标杆深水崩塌或核心主线彻底破位，一票否决)
    INCONCLUSIVE = "INCONCLUSIVE" # 独立状态：证据不足/休市/质量降级/标的停牌，无法进行科学裁判


class InconclusiveReasonEnum(str, Enum):
    """
    INCONCLUSIVE 独立状态的具体根因分类
    """
    MARKET_CLOSED = "MARKET_CLOSED"                             # 物理休市 / 非交易日
    DATA_QUALITY_DEGRADED = "DATA_QUALITY_DEGRADED"             # 上游行情质量降级 (PARTIAL/DEGRADED/UNAVAILABLE)
    TARGET_MISSING_OR_SUSPENDED = "TARGET_MISSING_OR_SUSPENDED" # 核心观测标的在竞价中缺失或处于停牌状态
    CAUSAL_TEMPORAL_VIOLATION = "CAUSAL_TEMPORAL_VIOLATION"     # 假说登记时间与竞价事实时间存在因果时序倒置


class AssertionSeverityEnum(str, Enum):
    """
    断言规则的严重性级别
    """
    CRITICAL_KILL = "CRITICAL_KILL" # 核心生命线 (触发即触发 FALSIFIED 一票否决)
    MODERATE = "MODERATE"           # 中度分歧 (触发则将结论降级为 DIVERGENT)
    INFORMATIONAL = "INFORMATIONAL" # 观察性参考 (不改变综合三态结论)


class AssertionItemVerdict(BaseModel):
    """
    单个量化断言的微观裁判证据契约
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_id: str = Field(..., description="规则全局唯一编号 (如 'RULE-SPACE-LEADER-PREMIUM')")
    rule_name: str = Field(..., description="断言规则人类可读名称")
    severity: AssertionSeverityEnum = Field(..., description="严重性级别")
    target_entity: str = Field(..., description="观测标的或宏观指标 (如 '600825 新华传媒')")
    expected_condition: str = Field(..., description="假说预设的判定条件 (如 '竞价开盘涨幅 >= -1.00%')")
    actual_observation: str = Field(..., description="09:25 物理观测值 (如 '开盘 -2.40%，撮合成交 5400 万元')")
    is_violated: bool = Field(..., description="实际观测是否违背/突破了假说预设")
    deviation_analysis: str = Field(..., description="偏离度量化分析说明")


class PopperianHypothesisRecord(BaseModel):
    """
    不可变波普尔假说记录模型 (由 T 日闭市战报生成并在 T+1 日竞价前固化)
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothesis_id: str = Field(..., description="假说全局唯一标识 HYPO-YYYY-MM-DD-<hash12>")
    registered_at: str = Field(..., description="假说登记时间 ISO-8601 (必须严苛早于 T+1 09:25:00)")
    base_trade_date: str = Field(..., description="基准复盘交易日 T (YYYY-MM-DD)")
    target_trade_date: str = Field(..., description="目标对账交易日 T+1 (YYYY-MM-DD)")
    
    # 血缘防伪锚定
    bound_briefing_trace_id: str = Field(..., description="绑定的 T 日战报 Trace ID")
    bound_briefing_fingerprint: str = Field(..., description="绑定的 T 日战报 JCS SHA-256 指纹")
    bound_snapshot_fingerprint: str = Field(..., description="绑定的 T 日市场快照 JCS SHA-256 指纹")

    # 宏观与状态假说
    expected_market_state: str = Field(..., description="预期的次日延续或转移市场状态")
    expected_turnover_ratio_min: Decimal = Field(..., ge=0, description="预期竞价占前日成交额最低比值 (%)")
    expected_turnover_ratio_max: Decimal = Field(..., gt=0, description="预期竞价占前日成交额最高比值 (%)")

    # 重点观测标的绑定 (零静默替换铁律)
    space_leader_code: str = Field(..., description="空间标杆股票代码 (如 '600825')")
    space_leader_name: str = Field(..., description="空间标杆规范简称 (如 '新华传媒')")
    space_leader_falsification_threshold: Decimal = Field(
        Decimal("-3.00"), description="空间标杆致命证伪跌幅阈值 (%，默认 <= -3.00%)"
    )
    mainline_leader_codes: List[str] = Field(default_factory=list, description="Top 3 主线领军标的代码列表")
    required_observation_symbols: List[str] = Field(
        ..., min_length=1, description="必须参与本次对账的法定标的代码全集 (缺一即判定 INCONCLUSIVE)"
    )

    # 不可变数字指纹
    hypothesis_fingerprint: str = Field(..., description="本假说记录的 RFC 8785 JCS SHA-256 数字指纹")


class BiddingFalsificationVerdict(BaseModel):
    """
    09:25 集合竞价波普尔证伪自动对账单权威契约 (Phase 2E.2 核心交付物)
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict_id: str = Field(..., description="对账单全局唯一标识 VERDICT-YYYY-MM-DD-AUCTION-<hash8>")
    trade_date: str = Field(..., description="对账执行交易日 T+1 (YYYY-MM-DD)")
    evaluated_at: str = Field(..., description="对账评估物理执行时间 ISO-8601")
    trace_id: str = Field(..., description="跨日贯穿式追踪 ID (如 TRACE-2026-10-08-TO-2026-10-09-AUCTION-POPPER)")

    # 五位一体跨日相互复核指纹链 (Requirement D)
    hypothesis_id: str = Field(..., description="绑定的原始假说 ID")
    hypothesis_fingerprint: str = Field(..., description="绑定的原始假说 JCS SHA-256 指纹")
    bound_briefing_fingerprint: Optional[str] = Field(None, description="绑定的战报 JCS SHA-256 指纹")
    rule_version: str = Field(..., description="断言规则集静态版本号")
    threshold_config_hash: str = Field(..., description="阈值配置参数 JCS SHA-256 指纹")
    auction_fingerprint: str = Field(..., description="消费的 09:25 物理竞价快照 JCS SHA-256 指纹")

    # 裁决结论与证据
    overall_verdict: FalsificationOutcomeEnum = Field(..., description="最终三态结论或证据不足状态")
    inconclusive_reason: Optional[InconclusiveReasonEnum] = Field(
        None, description="当且仅当 overall_verdict 为 INCONCLUSIVE 时的具体原因"
    )
    verdict_headline: str = Field(..., description="受约束的客观事实一句话全貌")
    
    assertion_results: List[AssertionItemVerdict] = Field(
        default_factory=list, description="各项量化断言逐项判定证据链"
    )
    action_boundaries: List[str] = Field(
        default_factory=list, description="机器推导的客观防守行动边界条件 (严禁买卖劝诱)"
    )

    safety_audit_passed: bool = Field(True, description="是否通过安全审查")
    verdict_fingerprint: str = Field(..., description="对账单全字段 (除自身外) RFC 8785 JCS SHA-256 防伪指纹")
