from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from ..core.database import Base

class DailyReview(Base):
    """每日收盘复盘报告"""
    __tablename__ = "daily_review"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, unique=True, index=True)
    title = Column(String(200), nullable=True)  # 研报核心主标题
    market_overview = Column(Text)          # 大盘总览 JSON
    limit_up_analysis = Column(Text)        # 涨停分析 JSON
    sector_analysis = Column(Text)          # 板块/题材归因 JSON
    market_state_id = Column(Integer, ForeignKey("cognition_market_state.id"), nullable=True)
    report_content = Column(Text)           # 结构化报告完整内容 JSON
    data_quality = Column(String, default="full")
    generated_at = Column(DateTime, server_default=func.now())

class PremarketBriefing(Base):
    """每日盘前简报"""
    __tablename__ = "premarket_briefing"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, unique=True, index=True)
    overnight_summary = Column(Text)        # 隔夜外盘 JSON
    news_digest = Column(Text)              # 快讯摘要 JSON
    yesterday_review_summary = Column(Text) # 昨日复盘回顾
    today_focus = Column(Text)              # 今日关注方向 JSON
    generated_at = Column(DateTime, server_default=func.now())

class AuctionReport(Base):
    """竞价观察报告"""
    __tablename__ = "auction_report"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, unique=True, index=True)
    index_open_data = Column(Text)          # 指数开盘数据 JSON
    one_word_count = Column(Integer, default=0)
    high_open_stats = Column(Text)          # 高开统计 JSON
    emotion_judgment = Column(String)       # 开盘情绪判断
    generated_at = Column(DateTime, server_default=func.now())
