from sqlalchemy import Column, Integer, Float, String, Text, DateTime, UniqueConstraint, Boolean, func
from ..core.database import Base

class MarketIndexDaily(Base):
    """指数日线数据"""
    __tablename__ = "market_index_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, index=True)
    code = Column(String, nullable=False, index=True)
    name = Column(String)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    pct_change = Column(Float)
    prev_close = Column(Float)
    data_quality = Column(String, default="full")
    provider = Column(String)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("date", "code", name="uix_market_index_date_code"),
    )

class MarketLimitUpDaily(Base):
    """涨停池日明细"""
    __tablename__ = "market_limit_up_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, index=True)
    code = Column(String, nullable=False, index=True)
    name = Column(String)
    reason_type = Column(String)
    change_tag = Column(String)
    high_days = Column(String)
    limit_up_type = Column(String)
    sector = Column(String)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("date", "code", name="uix_market_limit_up_date_code"),
    )

class MarketLimitUpSummary(Base):
    """每日涨停与情绪统计汇总"""
    __tablename__ = "market_limit_up_summary"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, unique=True, index=True)
    limit_up_count = Column(Integer, default=0)
    limit_down_count = Column(Integer, default=0)
    first_limit_count = Column(Integer, default=0)
    continued_count = Column(Integer, default=0)
    one_word_count = Column(Integer, default=0)
    open_limit_count = Column(Integer, default=0)
    history_continued = Column(Integer, default=0)
    max_height = Column(Integer, default=0)
    top_reasons = Column(Text)  # JSON 字符串
    data_quality = Column(String, default="full")
    provider = Column(String)
    created_at = Column(DateTime, server_default=func.now())

class MarketNews(Base):
    """快讯与新闻聚合"""
    __tablename__ = "market_news"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String, nullable=False)
    title = Column(String, nullable=False)
    brief = Column(Text)
    publish_time = Column(String)
    collected_at = Column(DateTime, server_default=func.now())

class IntradayMarketSnapshot(Base):
    """盘中市场宏观时序快照表 (每5分钟采样一条，单日48条)"""
    __tablename__ = "intraday_market_snapshot"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, index=True)        # 交易日 YYYY-MM-DD
    timestamp = Column(String, nullable=False, index=True)   # 精确时间 HH:MM:SS
    minute_index = Column(Integer, nullable=False)           # 盘中有效分钟 1~240

    # 宏观指数与量能切片 (统一 nullable=True, default=None 贯彻 None 防伪)
    sh_index_price = Column(Float, nullable=True, default=None)
    sh_index_pct = Column(Float, nullable=True, default=None)
    sz_index_price = Column(Float, nullable=True, default=None)
    sz_index_pct = Column(Float, nullable=True, default=None)
    cy_index_pct = Column(Float, nullable=True, default=None)
    total_amount_yi = Column(Float, nullable=True, default=None)
    volume_proj_yi = Column(Float, nullable=True, default=None)  # 09:30~09:45 强制为 None
    is_proj_estimated = Column(Boolean, nullable=True, default=False)  # 量能投影是否处于估算状态

    # 市场多空广度 (统一 nullable=True, default=None 杜绝 0 伪造)
    up_count = Column(Integer, nullable=True, default=None)
    down_count = Column(Integer, nullable=True, default=None)
    limit_up_count = Column(Integer, nullable=True, default=None)
    limit_down_count = Column(Integer, nullable=True, default=None)
    broken_limit_count = Column(Integer, nullable=True, default=None)

    # 核心高标结构 (统一 nullable=True, default=None)
    max_height = Column(Integer, nullable=True, default=None)
    leader_stock = Column(String, nullable=True, default=None)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("date", "timestamp", name="uix_intraday_snapshot_date_time"),
    )

class IntradayAnomalyEvent(Base):
    """盘中显著物理异动与相变事件表 (边沿触发，单日约20~80条)"""
    __tablename__ = "intraday_anomaly_event"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, index=True)        # 交易日 YYYY-MM-DD
    timestamp = Column(String, nullable=False, index=True)   # 事件精确时间 HH:MM:SS
    minute_index = Column(Integer, nullable=False)           # 发生分钟 1~240

    # 事件分类与标的
    event_category = Column(String, nullable=False)          # LIMIT_UP_LOCK / LIMIT_UP_BREAK / VELOCITY_SPIKE / VOLUME_SURGE / LEADER_SHIFT / BREADTH_PULSE
    severity_level = Column(String, nullable=False)          # CRITICAL / TRANSITION / INFO
    symbol = Column(String, nullable=True, index=True)       # 涉及股票代码 (如 000001)
    name = Column(String, nullable=True)                     # 股票名称

    # 量化事实度量 (统一 nullable=True, default=None)
    price = Column(Float, nullable=True, default=None)
    pct_change = Column(Float, nullable=True, default=None)
    window_delta_pct = Column(Float, nullable=True, default=None)
    window_amount_wan = Column(Float, nullable=True, default=None)
    surge_ratio = Column(Float, nullable=True, default=None) # 09:30~10:00 强制为 None
    details = Column(Text, nullable=True, default=None)      # 结构化明细 JSON

    created_at = Column(DateTime, server_default=func.now())
