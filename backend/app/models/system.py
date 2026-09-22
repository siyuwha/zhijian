from sqlalchemy import Column, Integer, String, Text, DateTime, func
from ..core.database import Base

class DataQualityLog(Base):
    """数据质量审计日志"""
    __tablename__ = "data_quality_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, index=True)
    capability = Column(String, nullable=False)   # 数据能力名称
    provider = Column(String, nullable=False)     # 实际提供数据的 Provider
    quality = Column(String, nullable=False)      # full / partial / failed
    error_message = Column(Text)
    response_time_ms = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())

class TaskLog(Base):
    """定时任务执行日志"""
    __tablename__ = "task_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_name = Column(String, nullable=False)
    trigger_time = Column(String, nullable=False)
    status = Column(String, nullable=False)       # success / failed / skipped
    duration_ms = Column(Integer)
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

class SystemConfig(Base):
    """系统配置与指标参数"""
    __tablename__ = "system_config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)          # JSON 字符串
    description = Column(String)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
