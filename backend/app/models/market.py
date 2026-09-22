from sqlalchemy import Column, Integer, Float, String, Text, DateTime, UniqueConstraint, func
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
