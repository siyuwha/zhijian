from sqlalchemy import Column, Integer, Float, String, Text, DateTime, ForeignKey, UniqueConstraint, func
from ..core.database import Base

class CognitionMarketState(Base):
    """
    市场状态快照 / Market State Artifact (M1.4 输出)
    明确定位：这是 Market State Snapshot，不等同于完整 Cognition Model。
    """
    __tablename__ = "cognition_market_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, index=True)
    timestamp = Column(String, nullable=False)
    indicators = Column(Text, nullable=False)        # 各指标计算结果 JSON
    composite_score = Column(Float)                  # 综合得分
    state_label = Column(String)                     # 状态标签（如“强势/震荡/冰点”）
    config_snapshot = Column(Text)                   # 当时使用的指标配置快照 JSON
    data_quality = Column(String, default="full")
    created_at = Column(DateTime, server_default=func.now())


class CognitiveTradeDiagnosis(Base):
    """单笔交易认知行为诊断 (与 trade_record 1:1 纯派生绑定)"""
    __tablename__ = "cognitive_trade_diagnosis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(Integer, ForeignKey("trade_record.id"), nullable=False, unique=True, index=True)
    date = Column(String(10), nullable=False, index=True)          # 交易日期 YYYY-MM-DD

    # ---------------- 事实层 (Fact Layer - 客观不可推翻) ----------------
    trade_price = Column(Float, nullable=False)                    # 成交单价
    trade_quantity = Column(Integer, nullable=False)               # 成交股数
    trade_amount = Column(Float, nullable=False)                   # 成交金额
    trade_direction = Column(String(10), nullable=False)           # buy / sell
    market_d1_d6_snapshot = Column(Text, nullable=False)           # 当日 D1~D6 完整快照 (JSON)
    post_trade_mdd = Column(Float, nullable=True)                  # 买入后至清仓前最大回撤 %
    post_trade_max_profit = Column(Float, nullable=True)           # 买入后持有期最大浮盈 %

    # ------------ 认知解释层 (Interpretation Layer - 待人工确认) ----------
    env_match_type = Column(String(30), nullable=False)           # HIGH_MATCH(高度顺势), LOW_MATCH(逆势博弈), EMO_DRIVEN(情绪驱动), AMBIGUOUS(环境模糊)
    env_match_score = Column(Float, nullable=True, default=None)  # 留白或预留，一期严禁输出伪精确分数
    logic_realization = Column(String(30), nullable=False)        # REALIZED(预案兑现), UNREALIZED(预案落空), ACCIDENTAL(偏离预案但意外)
    cognitive_gap_analysis = Column(Text, nullable=False)         # 认知 Gap 剖析 (AI 诊断草案)

    # 人工审定状态 (HITL) - 隔离铁律载体
    human_status = Column(String(20), default="UNCONFIRMED")      # UNCONFIRMED(待确认), CONFIRMED(已确认), MODIFIED(人工修正)
    human_comment = Column(Text, nullable=True)                   # 用户修正意见或补充反思

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class MarketHypothesis(Base):
    """跨交易日市场推演假说"""
    __tablename__ = "market_hypothesis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_date = Column(String(10), nullable=False, index=True) # 假说生成日期 YYYY-MM-DD
    target_date = Column(String(10), nullable=False, index=True)  # 目标验证日期 YYYY-MM-DD (如周一)

    # 假说分类与标的
    hypothesis_type = Column(String(30), nullable=False)          # INDEX_TREND(大盘), SECTOR_LEADER(板块核心), SENTIMENT_CYCLE(情绪周期)
    target_asset = Column(String(50), nullable=False)             # 标的名称/代码 (如"全市场/连板梯队/半导体/000001")
    expected_scenario = Column(String(30), nullable=False)        # ACCELERATION(加速), DIVERGENCE(分歧), REBOUND(修复), ROTATION(轮动)

    # 双轨核对支撑结构
    premise_logic = Column(Text, nullable=False)                  # 前置支撑事实 (基于 M1~M5 既有数据)
    expected_phenomenon = Column(Text, nullable=False)            # 自然语言预期客观现象
    invalidation_condition = Column(Text, nullable=False)         # 刚性证伪失效条件 (自然语言)
    assertion_metrics = Column(Text, nullable=True)               # 可选确定性指标阈值 JSON (如 {"sh_open_pct_min": -0.5, "max_height_min": 4})

    # 生命周期状态 (落实修正项 2)
    status = Column(String(20), default="PENDING", nullable=False)# PENDING(待锁) / LOCKED(已锁) / VERIFYING(核对中) / CLOSED(已结案)
    created_at = Column(DateTime, server_default=func.now())


class HypothesisVerification(Base):
    """推演假说客观事实验证记录 (联合唯一键支持早盘与收盘双独立快照)"""
    __tablename__ = "hypothesis_verification"
    __table_args__ = (
        UniqueConstraint("hypothesis_id", "verification_stage", name="uq_hypo_verify_stage"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    hypothesis_id = Column(Integer, ForeignKey("market_hypothesis.id"), nullable=False, index=True)

    verification_stage = Column(String(20), nullable=False)       # AUCTION_0925(竞价核对), CLOSE_1530(收盘全景核对)
    actual_data_snapshot = Column(Text, nullable=False)           # 真实抓取的数据快照 JSON (不可覆盖)

    # 客观裁决枚举 (落实修正项 2: 新增 INCONCLUSIVE)
    outcome = Column(String(20), nullable=False)                  # CONFIRMED / FALSIFIED / PARTIAL / INVALID / INCONCLUSIVE
    accuracy_score = Column(Float, nullable=True, default=None)   # 一期留白，拒绝伪精确打分

    deviation_analysis = Column(Text, nullable=False)             # 偏差剖析 (为什么偏离预期？)
    gap_summary = Column(String(200), nullable=False)             # 一句话 Gap 总结
    verified_at = Column(DateTime, server_default=func.now())
