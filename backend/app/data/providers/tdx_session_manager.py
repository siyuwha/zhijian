# -*- coding: utf-8 -*-
"""
通达信原生券商行情直连会话管理器 (TDX Session Manager)
严格遵守用户铁律红线：
1. 仅在每个交易日 09:10:00 - 15:00:05 运行连接池与长连接感知
2. 盘后 15:00:05 准时自动挂断释放连接，非交易日坚决不连接，零网络与主站资源空耗
3. 提供毫秒级探活、断线自动重试与状态自检
"""

import logging
from datetime import datetime, time as dtime
from typing import Optional, Dict, Any

from ...core.calendar import calendar
from .tdx_client import TdxDirectClient, DEFAULT_HQ_SERVERS

logger = logging.getLogger(__name__)

class TdxSessionManager:
    """通达信长连接时钟与会话窗口管理器 (单例模式)"""

    _instance: Optional["TdxSessionManager"] = None

    START_TIME = dtime(9, 10, 0)
    STOP_TIME = dtime(15, 0, 5)

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(TdxSessionManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._client: Optional[TdxDirectClient] = None
        self._last_heartbeat: Optional[datetime] = None
        self._last_latency_ms: Optional[float] = None
        self._initialized = True

    @classmethod
    def is_trading_window(cls, now_dt: Optional[datetime] = None) -> bool:
        """
        判断当前是否处于交易日连接窗口：
        1. 必须是 A 股交易日；
        2. 当前时间在 09:10:00 ~ 15:00:05 之间。
        """
        if now_dt is None:
            now_dt = datetime.now()

        # 检查是否为交易日
        if not calendar.is_trading_day(now_dt.date()):
            return False

        cur_t = now_dt.time()
        return cls.START_TIME <= cur_t <= cls.STOP_TIME

    def ensure_connected(self) -> bool:
        """
        状态机驱动：
        - 若在交易窗口内：确保长连接通畅；
        - 若超出交易窗口：自动断开物理连接并释放资源。
        """
        now = datetime.now()
        in_window = self.is_trading_window(now)

        if not in_window:
            # 盘后或非交易日，执行自动断开
            if self._client and self._client.connected_server:
                logger.info("非交易窗口时段 (09:10-15:00 之外)，自动断开 TDX 长连接，释放网络端口")
                self.disconnect()
            return False

        # 在交易窗口内，确保连接
        if self._client is None:
            self._client = TdxDirectClient(servers=DEFAULT_HQ_SERVERS, timeout=3.0)

        if not self._client.connected_server:
            t0 = datetime.now()
            ok = self._client.connect_best_server()
            if ok:
                self._last_latency_ms = round((datetime.now() - t0).total_seconds() * 1000, 1)
                self._last_heartbeat = datetime.now()
                logger.info(
                    f"TDX 交易时段长连接已激活: {self._client.connected_server.get('name')} "
                    f"({self._client.connected_server.get('ip')}), 延迟: {self._last_latency_ms}ms"
                )
                return True
            else:
                logger.warning("TDX 尝试建立交易时段长连接失败，将等待下次重试")
                return False
        return True

    def get_client(self) -> Optional[TdxDirectClient]:
        """获取当前活跃的 TDX 客户端 (仅在交易窗口有效)"""
        if self.ensure_connected():
            return self._client
        return None

    def disconnect(self):
        """强制断开连接"""
        if self._client:
            try:
                self._client.close()
            except Exception as e:
                logger.debug(f"TDX 关闭连接微异常: {e}")
            finally:
                self._client = None
                self._last_latency_ms = None

    def get_status(self) -> Dict[str, Any]:
        """获取当前会话管理器的全景健康状态"""
        now = datetime.now()
        in_window = self.is_trading_window(now)
        is_trade_day = calendar.is_trading_day(now.date())

        connected = False
        server_info = None
        if self._client and self._client.connected_server:
            connected = True
            server_info = {
                "name": self._client.connected_server.get("name"),
                "ip": self._client.connected_server.get("ip"),
                "port": self._client.connected_server.get("port"),
            }

        return {
            "window_rule": "每个交易日当天 09:10:00 - 15:00:05",
            "is_trading_day": is_trade_day,
            "in_trading_window": in_window,
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "connected": connected,
            "latency_ms": self._last_latency_ms,
            "server": server_info,
            "mode": "ACTIVE_STREAM" if in_window else "HIBERNATING",
            "last_heartbeat": self._last_heartbeat.strftime("%H:%M:%S") if self._last_heartbeat else None,
        }

tdx_session_manager = TdxSessionManager()
