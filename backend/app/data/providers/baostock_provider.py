import asyncio
import logging
import sqlite3
import os
from typing import Optional, Dict, Any
from .base import BaseProvider
from ..capabilities import (
    DataQuality,
    DataResult,
    DataStatus,
    Freshness,
    ProviderErrorCode,
    SettlementCapability,
)
from ...config import settings

logger = logging.getLogger(__name__)

class BaostockProvider(BaseProvider, SettlementCapability):
    """
    Baostock 日线结算数据适配器 (P1-1 生产就绪强化版)
    具备：
    1. 3.0秒硬超时控制 (asyncio.wait_for)
    2. 本地持久化缓存兜底 (SQLite market_settlement_cache)
    3. 数据新鲜度判断 (Freshness.EOD_COMPENSATED vs Freshness.STALE)
    4. 明确状态语义 (AVAILABLE / STALE / TIMEOUT / ERROR)
    """

    def __init__(self):
        super().__init__(
            name="baostock",
            implementation_status="已接入",
            connectivity_verified="已验证",
            schema_verified="已验证",
            semantic_verified="已验证",
            production_eligible="准入",
        )
        self._mem_cache: Dict[str, dict] = {}
        self._db_path = settings.DATABASE_URL.split("///")[-1]
        self._ensure_cache_table()

    def _ensure_cache_table(self):
        """确保本地 SQLite 结算价缓存表存在"""
        try:
            os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
            with sqlite3.connect(self._db_path, timeout=5.0) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS market_settlement_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code TEXT NOT NULL,
                        date TEXT NOT NULL,
                        open REAL,
                        high REAL,
                        low REAL,
                        close REAL,
                        prev_close REAL,
                        volume REAL,
                        amount REAL,
                        pct_change REAL,
                        source TEXT DEFAULT 'baostock',
                        status TEXT DEFAULT 'AVAILABLE',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(code, date)
                    );
                """)
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to ensure settlement cache table: {e}")

    def _get_local_cache(self, code: str, date: str) -> Optional[dict]:
        cache_key = f"{code}:{date}"
        if cache_key in self._mem_cache:
            return self._mem_cache[cache_key]

        try:
            with sqlite3.connect(self._db_path, timeout=3.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT date, code, open, high, low, close, prev_close, volume, amount, pct_change, source FROM market_settlement_cache WHERE code = ? AND date = ?",
                    (code, date)
                )
                row = cursor.fetchone()
                if row:
                    res = dict(row)
                    self._mem_cache[cache_key] = res
                    return res
        except Exception as e:
            logger.warning(f"Local settlement cache lookup failed: {e}")
        return None

    def _save_local_cache(self, code: str, date: str, data: dict):
        cache_key = f"{code}:{date}"
        self._mem_cache[cache_key] = data
        try:
            with sqlite3.connect(self._db_path, timeout=3.0) as conn:
                conn.execute("""
                    INSERT INTO market_settlement_cache
                    (code, date, open, high, low, close, prev_close, volume, amount, pct_change, source, status, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'baostock', 'AVAILABLE', CURRENT_TIMESTAMP)
                    ON CONFLICT(code, date) DO UPDATE SET
                    open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
                    prev_close=excluded.prev_close, volume=excluded.volume, amount=excluded.amount,
                    pct_change=excluded.pct_change, updated_at=CURRENT_TIMESTAMP
                """, (
                    code, date,
                    data.get("open"), data.get("high"), data.get("low"), data.get("close"),
                    data.get("prev_close"), data.get("volume"), data.get("amount"), data.get("pct_change")
                ))
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to persist settlement cache: {e}")

    async def is_available(self) -> bool:
        return True

    def _sync_fetch_settlement(self, code: str, date: str) -> Optional[dict]:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != '0':
            logger.warning(f"baostock login error: {lg.error_msg}")
            return None

        try:
            bs_code = code
            if not ("." in code):
                if code.startswith("sh") or code.startswith("sz"):
                    bs_code = f"{code[:2]}.{code[2:]}"
                elif code.startswith("60") or code.startswith("68"):
                    bs_code = f"sh.{code}"
                elif code.startswith("00") or code.startswith("30"):
                    bs_code = f"sz.{code}"

            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,code,open,high,low,close,preclose,volume,amount,pctChg",
                start_date=date,
                end_date=date,
                frequency="d",
                adjustflag="3"
            )

            data_list = []
            while (rs.error_code == '0') and rs.next():
                data_list.append(rs.get_row_data())

            if data_list:
                row = data_list[0]
                return {
                    "date": row[0],
                    "code": row[1],
                    "open": float(row[2]) if row[2] else 0.0,
                    "high": float(row[3]) if row[3] else 0.0,
                    "low": float(row[4]) if row[4] else 0.0,
                    "close": float(row[5]) if row[5] else 0.0,
                    "prev_close": float(row[6]) if row[6] else 0.0,
                    "volume": float(row[7]) if row[7] else 0.0,
                    "amount": float(row[8]) if row[8] else 0.0,
                    "pct_change": float(row[9]) if row[9] else 0.0,
                }
            return None
        finally:
            try:
                bs.logout()
            except Exception:
                pass

    async def get_daily_settlement(self, code: str, date: str) -> DataResult:
        """
        获取日线结算 OHLCV 数据
        硬约束：
        - 3.0 秒硬超时限制
        - 超时或远端失败自动降级读取本地缓存并标记 STALE
        - 无本地缓存时显式返回 UNAVAILABLE 并记录状态 (TIMEOUT/ERROR)
        """
        is_timeout = False
        fetch_error = None
        data = None

        try:
            # 3.0s 硬超时控制
            data = await asyncio.wait_for(
                asyncio.to_thread(self._sync_fetch_settlement, code, date),
                timeout=3.0
            )
            if data:
                # 远端物理获取成功：持久化写入本地缓存
                self._save_local_cache(code, date, data)
                return DataResult(
                    data=data,
                    quality=DataQuality.FULL,
                    status=DataStatus.AVAILABLE,
                    freshness=Freshness.EOD_COMPENSATED,
                    provider=self.name
                )
        except asyncio.TimeoutError:
            is_timeout = True
            fetch_error = "Baostock physical request timed out (>3.0s)"
            logger.warning(f"{fetch_error} for {code} on {date}")
        except Exception as e:
            fetch_error = str(e)
            logger.warning(f"Baostock physical request failed: {e}")

        # 降级尝试：查找本地日线结算缓存
        cached_data = self._get_local_cache(code, date)
        if cached_data:
            logger.info(f"Serving STALE settlement cache for {code} on {date}")
            return DataResult(
                data=cached_data,
                quality=DataQuality.DEGRADED,
                status=DataStatus.STALE,
                freshness=Freshness.STALE,
                fallback_used=True,
                provider="baostock_local_cache",
                error_message=f"Baostock failed ({fetch_error}). Served from local settlement cache."
            )

        # 彻底不可得
        status = DataStatus.TIMEOUT if is_timeout else DataStatus.ERROR
        error_code = ProviderErrorCode.TIMEOUT if is_timeout else ProviderErrorCode.CONNECTION_ERROR
        return DataResult(
            data=None,
            quality=DataQuality.UNAVAILABLE,
            status=status,
            freshness=Freshness.UNAVAILABLE,
            error_code=error_code,
            fallback_used=True,
            provider=self.name,
            error_message=f"Baostock unavailable ({fetch_error or 'no data'}) and no local cache."
        )
