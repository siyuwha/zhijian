import contextvars
from contextvars import ContextVar
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from .capabilities import DataQuality, DataResult
from ..models.system import DataQualityLog
from ..core.database import async_session

logger = logging.getLogger(__name__)

# 上下文隔离变量：按 async Task / 协程隔离，杜绝并发请求与不同调度轮次之间的状态串扰
_round_failures_ctx: ContextVar[Optional[List[Dict[str, Any]]]] = ContextVar("round_failures_ctx", default=None)
_tracking_active_ctx: ContextVar[bool] = ContextVar("tracking_active_ctx", default=False)
_test_force_id_ctx: ContextVar[Optional[int]] = ContextVar("test_force_id_ctx", default=None)


class _QualityTrackerMeta(type):
    """元类支持通过 QualityTracker._test_force_id = X 进行上下文感知读写"""
    @property
    def _test_force_id(cls) -> Optional[int]:
        return _test_force_id_ctx.get()

    @_test_force_id.setter
    def _test_force_id(cls, value: Optional[int]):
        _test_force_id_ctx.set(value)


class QualityTracker(metaclass=_QualityTrackerMeta):
    """数据质量跟踪与审计日志记录器 (具备独立事务隔离生命周期与协程上下文聚合能力)"""

    @classmethod
    def start_round_tracking(cls):
        """启动当前上下文调度各阶段的质量日志失败聚合追踪"""
        _round_failures_ctx.set([])
        _tracking_active_ctx.set(True)

    @classmethod
    def stop_round_tracking(cls):
        """停止追踪并清理开关"""
        _tracking_active_ctx.set(False)

    @classmethod
    def get_round_failures(cls) -> List[Dict[str, Any]]:
        """获取当前上下文汇总的所有质量日志失败项"""
        failures = _round_failures_ctx.get()
        return list(failures) if failures is not None else []

    @classmethod
    def clear_round_failures(cls):
        """清空当前上下文追踪项"""
        failures = _round_failures_ctx.get()
        if failures is not None:
            failures.clear()

    @classmethod
    def record_failure(cls, capability: str = "", provider: str = "UNKNOWN", error: str = ""):
        """显式向当前上下文轮次追踪器登记质量日志失败 (支持缓存复用与跨上下文传递)"""
        if _tracking_active_ctx.get():
            failures = _round_failures_ctx.get()
            if failures is not None:
                failures.append({
                    "capability": capability,
                    "provider": provider,
                    "error": error,
                    "timestamp": datetime.now().isoformat()
                })

    @classmethod
    def set_test_force_id(cls, force_id: Optional[int]):
        """显式设置当前上下文测试强制 ID (隔离测试，杜绝并发污染)"""
        _test_force_id_ctx.set(force_id)

    @classmethod
    async def log_quality(
        cls,
        session: Optional[AsyncSession] = None,
        capability: str = "",
        result: Optional[DataResult] = None,
        response_time_ms: int = 0,
        session_factory = None,
        explicit_id: Optional[int] = None,
    ) -> bool:
        """
        持久化数据质量日志：
        严格遵循事务所有权隔离铁律：
        无论调用方是否传入业务 session，质量审计日志均由独立的会话与事务闭环管理 (创建、提交、回滚、关闭)，
        绝对禁止在调用方的业务 session 上调用 commit() 或 add()，杜绝事务劫持、未回滚污染与连锁崩溃。
        """
        factory = session_factory or async_session
        prov = "UNKNOWN"
        is_tracking = _tracking_active_ctx.get()
        try:
            async with factory() as local_session:
                try:
                    q_val = "UNKNOWN"
                    err_msg = None
                    if result:
                        prov = result.provider or "UNKNOWN"
                        q_val = result.quality.value if isinstance(result.quality, DataQuality) else str(result.quality)
                        err_msg = result.error_message

                    effective_id = explicit_id if explicit_id is not None else _test_force_id_ctx.get()

                    log_entry = DataQualityLog(
                        id=effective_id,
                        date=datetime.now().strftime("%Y-%m-%d"),
                        capability=capability,
                        provider=prov,
                        quality=q_val,
                        error_message=err_msg,
                        response_time_ms=response_time_ms
                    )
                    local_session.add(log_entry)
                    await local_session.commit()
                    return True
                except Exception as e:
                    await local_session.rollback()
                    logger.error(f"Failed to record data quality log (rolled back): {e}")
                    if is_tracking:
                        failures = _round_failures_ctx.get()
                        if failures is not None:
                            failures.append({
                                "capability": capability,
                                "provider": prov,
                                "error": str(e),
                                "timestamp": datetime.now().isoformat()
                            })
                    return False
        except Exception as outer_e:
            logger.error(f"Failed to open session for quality log: {outer_e}")
            if is_tracking:
                failures = _round_failures_ctx.get()
                if failures is not None:
                    failures.append({
                        "capability": capability,
                        "provider": prov,
                        "error": str(outer_e),
                        "timestamp": datetime.now().isoformat()
                    })
            return False
