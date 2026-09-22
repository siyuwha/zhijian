import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from .capabilities import DataQuality, DataResult
from ..models.system import DataQualityLog

logger = logging.getLogger(__name__)

class QualityTracker:
    """数据质量跟踪与审计日志记录器"""

    @staticmethod
    async def log_quality(
        session: AsyncSession,
        capability: str,
        result: DataResult,
        response_time_ms: int = 0
    ):
        try:
            log_entry = DataQualityLog(
                date=datetime.now().strftime("%Y-%m-%d"),
                capability=capability,
                provider=result.provider,
                quality=result.quality.value if isinstance(result.quality, DataQuality) else str(result.quality),
                error_message=result.error_message,
                response_time_ms=response_time_ms
            )
            session.add(log_entry)
            await session.commit()
        except Exception as e:
            logger.error(f"Failed to record data quality log: {e}")
