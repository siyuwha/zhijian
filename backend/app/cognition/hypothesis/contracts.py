"""
Hypothesis Domain Contracts & Narrowed AST Nodes (Phase 2A Step 4 Sandbox)
上位依据：
1. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》v1.2.1-FINAL
2. 《开发文档/42-Phase-2A-Step4-假说定义投影与收窄AST断言执行器实施规划.md》

核心铁律：
- 【C-02 闭环】：假说定义投影（HypothesisDefinitionProjection）与后验验证运行态严格物理隔离
- 【C-03 闭环】：收窄断言 DSL 为有限类型安全的白名单 AST，严禁类 SQL 子查询与任意字符串注入
- 不可变值对象设计（frozen=True, extra="forbid"）
- 严禁假零填充（Missing != False, Missing != 0）
"""

from enum import Enum
from typing import Dict, List, Any, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class MetricType(str, Enum):
    """白名单指标类型枚举"""
    OPEN_PCT_CHANGE = "open_pct_change"       # 集合竞价开盘涨跌幅 (%)
    PCT_CHANGE = "pct_change"                 # 盘中/收盘涨跌幅 (%)
    TURNOVER_RATIO = "turnover_ratio"         # 换手率 (%)
    VOLUME_RATIO = "volume_ratio"             # 量比
    LIMIT_UP_COUNT = "limit_up_count"         # 涨停家数 (COUNT)
    LIMIT_DOWN_COUNT = "limit_down_count"     # 跌停家数 (COUNT)
    SEAL_AMOUNT_RATIO = "seal_amount_ratio"   # 封单金额占成交比
    PRICE = "price"                           # 价格
    BOARD_HEIGHT = "board_height"             # 连板高度
    LEADER_OPEN_PCT = "leader_open_pct"       # 龙头次日开盘溢价 (%)
    SECTOR_CHANGE_PCT = "sector_change_pct"   # 板块涨跌幅 (%)



class UniverseType(str, Enum):
    """标的范围类型枚举"""
    ALL_A = "ALL_A"                           # 全A股
    SECTOR = "SECTOR"                         # 行业板块
    LADDER_HIGH_SPEC = "LADDER_HIGH_SPEC"     # 高位连板梯队
    CUSTOM_LIST = "CUSTOM_LIST"               # 自定义标的列表


class OperatorType(str, Enum):
    """操作符类型枚举"""
    GT = "GT"                                 # >
    GTE = "GTE"                               # >=
    LT = "LT"                                 # <
    LTE = "LTE"                               # <=
    EQ = "EQ"                                 # ==
    NE = "NE"                                 # !=
    BETWEEN = "BETWEEN"                       # [min, max] 闭区间
    IN = "IN"                                 # 集合包含


class AggregationType(str, Enum):
    """聚合函数类型枚举"""
    NONE = "NONE"                             # 不聚合（单标的）
    MEAN = "MEAN"                             # 算术平均
    MEDIAN = "MEDIAN"                         # 中位数
    COUNT = "COUNT"                           # 计数
    MAX = "MAX"                               # 最大值
    MIN = "MIN"                               # 最小值
    SUM = "SUM"                               # 求和


class MissingDataPolicy(str, Enum):
    """数据缺失应对策略枚举"""
    INCONCLUSIVE = "INCONCLUSIVE"             # 默认：判定为证据不足/无法判定（严禁假0）
    FAIL_FALSIFIED = "FAIL_FALSIFIED"         # 严格模式：缺数视为证伪
    SKIP = "SKIP"                             # 忽略该断言


class AssertionOutcome(str, Enum):
    """单项断言求值结果枚举"""
    PASSED = "PASSED"                         # 断言成立
    FAILED = "FAILED"                         # 断言失败
    INCONCLUSIVE = "INCONCLUSIVE"             # 证据缺失，无法判定
    SKIPPED = "SKIPPED"                       # 跳过


class HypothesisOutcome(str, Enum):
    """假说最终裁决状态枚举"""
    CONFIRMED = "CONFIRMED"                   # 假说确证（预期满足且未触发证伪）
    FALSIFIED = "FALSIFIED"                   # 假说证伪（证伪断言触发）
    UNCONFIRMED = "UNCONFIRMED"               # 未能确证（未触发证伪但预期未达标）
    INCONCLUSIVE = "INCONCLUSIVE"             # 证据不足无法裁决（关键指标缺失）
    PENDING = "PENDING"                       # 待验证（尚未到验证时点）


class HypothesisType(str, Enum):
    """
    假说类型枚举（Phase 2C 条件解封白名单）
    上位依据：SPEC-COGNITION-PHASE2C-20261005-V1.1 (第4节)
    """
    MACRO_BROAD_INDEX = "MACRO_BROAD_INDEX"       # 宏观宽基假说
    ALL_A_AGGREGATE = "ALL_A_AGGREGATE"           # 全A情绪假说
    INITIAL_OUTBREAK = "INITIAL_OUTBREAK"         # 题材首发/脉冲爆发 (Pillar 1+2+3)
    SECTOR_ROTATION = "SECTOR_ROTATION"           # 板块主线轮动 (Pillar 1+2+3+4)



# 白名单过滤字段定义（严禁非法字段）
WHITELIST_FILTER_FIELDS = {
    "board_height",       # 连板高度 (int)
    "sector_code",        # 板块代码 (str)
    "is_highest_board",   # 事实层预计算最高板布尔标记 (bool)
    "is_st",              # 是否ST股 (bool)
    "market_cap",         # 市值 (float)
    "code",               # 股票代码 (str)
    "name",               # 股票名称 (str)
}


class FilterCondition(BaseModel):
    """单项过滤条件（白名单、类型安全）"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: str
    op: OperatorType
    val: Any

    def to_canonical_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "op": self.op.value,
            "val": self.val,
        }


class StructuredFilter(BaseModel):
    """结构化单层过滤解释器节点（严禁深层递归与嵌套子查询）"""
    model_config = ConfigDict(frozen=True, extra="forbid")

    universe_type: UniverseType
    conditions: List[FilterCondition] = Field(default_factory=list)
    logical_op: str = "AND"                   # 仅支持 "AND" 或 "OR"

    def to_canonical_dict(self) -> Dict[str, Any]:
        sorted_conds = sorted(
            [c.to_canonical_dict() for c in self.conditions],
            key=lambda x: str(x.get("field", "")),
        )
        return {
            "conditions": sorted_conds,
            "logical_op": self.logical_op,
            "universe_type": self.universe_type.value,
        }


class MetricAssertion(BaseModel):
    """
    收窄白名单指标断言 AST 节点 (Metric Assertion Node)
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    assertion_id: str
    metric: str                               # 必须在 MetricType 白名单内
    selector: StructuredFilter
    aggregation: AggregationType = AggregationType.NONE
    operator: OperatorType
    target_value: Optional[float] = None
    target_range: Optional[List[float]] = None # [min, max] 当 operator == BETWEEN 时使用
    unit: str = "PERCENT"
    time_binding: str = "auction_0925"        # 绑定生效时点
    missing_data_policy: MissingDataPolicy = MissingDataPolicy.INCONCLUSIVE

    def to_canonical_dict(self) -> Dict[str, Any]:
        """按 JCS 规范序列化（排除动态运行态字段）"""
        return {
            "aggregation": self.aggregation.value,
            "assertion_id": self.assertion_id,
            "metric": self.metric,
            "missing_data_policy": self.missing_data_policy.value,
            "operator": self.operator.value,
            "selector": self.selector.to_canonical_dict(),
            "target_range": self.target_range,
            "target_value": self.target_value,
            "time_binding": self.time_binding,
            "unit": self.unit,
        }


class MarketHypothesisDefinition(BaseModel):
    """
    不可变假说定义投影模型 (Hypothesis Definition Projection)
    上位依据：【C-02 Invariant】假说定义与后验状态物理隔离。
    本对象在推演生成时刻固化，永久不可变，绝不包含任何后验运行态字段。
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothesis_id: str
    cognition_id: str
    proposition: str                          # 自然语言命题客观阐述
    premise_evidence: List[str]               # 支撑该假说的前提事实证据清单
    time_binding: str                         # 验证时点
    assertion_logic: str = "AND"              # 多断言合成逻辑 (AND / OR)
    expected_assertions: List[MetricAssertion]# 预期发生的断言清单
    invalidation_assertions: List[MetricAssertion] # 证伪断言清单（证伪优先）
    hypothesis_type: Optional[str] = None     # 假说分类（INITIAL_OUTBREAK / SECTOR_ROTATION 等）
    observation_time: Optional[str] = None    # 物理事实快照观察时间
    hypothesis_generated_time: Optional[str] = None # 假说生成时点
    hypothesis_hash: str = ""

    def to_canonical_dict(self) -> Dict[str, Any]:
        """构建 JCS SHA-256 规范化载荷（排除自身哈希字段）"""
        sorted_expected = sorted(
            [a.to_canonical_dict() for a in self.expected_assertions],
            key=lambda x: str(x.get("assertion_id", "")),
        )
        sorted_invalidation = sorted(
            [a.to_canonical_dict() for a in self.invalidation_assertions],
            key=lambda x: str(x.get("assertion_id", "")),
        )
        d = {
            "assertion_logic": self.assertion_logic,
            "cognition_id": self.cognition_id,
            "expected_assertions": sorted_expected,
            "hypothesis_id": self.hypothesis_id,
            "invalidation_assertions": sorted_invalidation,
            "premise_evidence": sorted(self.premise_evidence),
            "proposition": self.proposition,
            "time_binding": self.time_binding,
        }
        if self.hypothesis_type is not None:
            d["hypothesis_type"] = self.hypothesis_type
        if self.observation_time is not None:
            d["observation_time"] = self.observation_time
        if self.hypothesis_generated_time is not None:
            d["hypothesis_generated_time"] = self.hypothesis_generated_time
        return d


class HypothesisSetProjection(BaseModel):
    """
    不可变假说集合定义投影 (Hypothesis Set Projection)
    对应 CognitionRecord.hypothesis_set_hash
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    set_id: str
    cognition_id: str
    hypotheses: List[MarketHypothesisDefinition]
    hypothesis_set_hash: str = ""

    def to_canonical_dict(self) -> Dict[str, Any]:
        sorted_hypos = sorted(
            [h.to_canonical_dict() for h in self.hypotheses],
            key=lambda x: str(x.get("hypothesis_id", "")).encode("utf-16-be"),
        )
        return {
            "cognition_id": self.cognition_id,
            "hypotheses": sorted_hypos,
            "set_id": self.set_id,
        }


class HypothesisRuntimeState(BaseModel):
    """
    验证运行态域模型 (Verification Runtime Domain)
    与 MarketHypothesisDefinition 严格物理隔离，后验变更绝不污染原始定义哈希！
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothesis_id: str
    status: str = "PENDING"                   # PENDING / LOCKED / VERIFYING / CLOSED
    actual_data_snapshot: Optional[Dict[str, Any]] = None
    verification_outcome: Optional[HypothesisOutcome] = None
    verification_execute_time: Optional[str] = None
    evaluation_time: Optional[str] = None     # 事后反事实求值时间戳 (锁定次日 15:05:00)
    gap_summary: Optional[str] = None

