import asyncio
import logging
from typing import Any, Dict, List, Optional
import httpx

from ..capabilities import (
    DataQuality,
    DataResult,
    DataStatus,
    Freshness,
    IndexQuoteCapability,
    StockQuoteCapability,
)
from .base import BaseProvider

logger = logging.getLogger(__name__)


class TencentProvider(BaseProvider, StockQuoteCapability, IndexQuoteCapability):
    """
    腾讯实时行情提供者 (Tencent Market Quote Provider)
    上位依据：《开发文档/26-P2数据源接入与弹性容灾多级降级设计文档.md》
    数据协议：http://qt.gtimg.cn/q=...
    特性：
    1. 相比 TDX，原生提供毫秒/秒级真实撮合日期与时间戳 (YYYYMMDDHHMMSS 格式)；
    2. 相比 Sina，支持高并发轻量五档撮合与指数快照，作为最高级容灾备用源 (Secondary Backup)。
    3. 支持北京证券交易所 (92/43/83/87) 与沪深两市代码映射及单标的异常隔离解析。
    """

    BASE_URL = "http://qt.gtimg.cn/q="
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "http://gu.qq.com/",
    }

    def __init__(self):
        super().__init__(
            name="tencent",
            implementation_status="已接入",
            connectivity_verified="待验证",
            schema_verified="待验证",
            semantic_verified="待验证",
            production_eligible="仅作备用",
        )

    async def is_available(self) -> bool:
        return True

    @staticmethod
    def _format_symbol(code: str) -> str:
        """标准化代码格式为腾讯接口前缀 (例如 600519 -> sh600519, 000001 -> sz000001, 920001 -> bj920001)"""
        c = str(code).strip().lower()
        if c.startswith(("sh", "sz", "bj")):
            return c
        if "." in c:
            parts = c.split(".")
            market = parts[1].lower() if parts[0].isdigit() else parts[0].lower()
            num = parts[0] if parts[0].isdigit() else parts[1]
            return f"{market}{num}"
        # 北交所: 92 前缀 (新上市代码), 43/83/87 (精选层平移/创新层), 82/88
        if c.startswith(("4", "8", "92")):
            return f"bj{c}"
        if c.startswith(("6", "900", "688")):
            return f"sh{c}"
        if c.startswith(("0", "200", "300")):
            return f"sz{c}"
        return f"sh{c}"

    async def get_stock_quotes(self, codes: List[str]) -> DataResult:
        """批量获取个股实时五档行情快照 (具备单标的异常隔离与缺失标记)"""
        if not codes:
            return DataResult(
                data=[],
                quality=DataQuality.FULL,
                status=DataStatus.EMPTY,
                freshness=Freshness.REALTIME,
                provider=self.name,
            )

        formatted_codes = [self._format_symbol(c) for c in codes if str(c).strip()]
        url = f"{self.BASE_URL}{','.join(formatted_codes)}"

        results = []
        parsed_codes = set()
        try:
            async with httpx.AsyncClient(timeout=6.0, trust_env=False) as client:
                resp = await client.get(url, headers=self.HEADERS)
                if resp.status_code != 200:
                    return DataResult(
                        data=[],
                        quality=DataQuality.FAILED,
                        status=DataStatus.ERROR,
                        freshness=Freshness.UNAVAILABLE,
                        provider=self.name,
                        error_message=f"Tencent HTTP {resp.status_code}",
                        missing_codes=list(codes),
                    )
                content = resp.content.decode("gbk", errors="ignore")

            for line in content.strip().split(";"):
                line = line.strip()
                if not line or "=" not in line:
                    continue
                try:
                    var_part, val_part = line.split("=", 1)
                    full_code = var_part.split("_")[-1].replace('"', "").strip()
                    val_str = val_part.strip().strip('"')
                    parts = val_str.split("~")
                    if len(parts) > 30:
                        name = parts[1].strip()
                        symbol = parts[2].strip()
                        price = float(parts[3]) if parts[3] else None
                        prev_close = float(parts[4]) if parts[4] else None
                        open_price = float(parts[5]) if parts[5] else None
                        vol_hand = float(parts[6]) if parts[6] else None
                        vol_shares = vol_hand * 100.0 if vol_hand is not None else None

                        # 五档买一 / 卖一
                        bid1_price = float(parts[9]) if len(parts) > 9 and parts[9] else 0.0
                        bid1_vol_hand = float(parts[10]) if len(parts) > 10 and parts[10] else 0.0
                        ask1_price = float(parts[19]) if len(parts) > 19 and parts[19] else 0.0
                        ask1_vol_hand = float(parts[20]) if len(parts) > 20 and parts[20] else 0.0
                        bid1_amount = round(bid1_vol_hand * 100 * bid1_price, 2)
                        bid1_amount_wan = round(bid1_amount / 10000.0, 2)

                        # 核心时态戳字段: 第 30 位为 YYYYMMDDHHMMSS 格式 (例如 20261029161457)
                        dt_raw = parts[30].strip() if len(parts) > 30 else ""
                        trade_date = None
                        trade_time = None
                        if len(dt_raw) >= 14 and dt_raw.isdigit():
                            trade_date = f"{dt_raw[:4]}-{dt_raw[4:6]}-{dt_raw[6:8]}"
                            trade_time = f"{dt_raw[8:10]}:{dt_raw[10:12]}:{dt_raw[12:14]}"
                        time_str = f"{trade_date} {trade_time}" if (trade_date and trade_time) else None

                        pct_change = float(parts[32]) if len(parts) > 32 and parts[32] else None
                        high_price = float(parts[33]) if len(parts) > 33 and parts[33] else None
                        low_price = float(parts[34]) if len(parts) > 34 and parts[34] else None

                        # 成交额 (万元)
                        amount_wan = float(parts[37]) if len(parts) > 37 and parts[37] else 0.0
                        amount_yuan = round(amount_wan * 10000.0, 2)

                        open_pct = None
                        if open_price is not None and prev_close is not None and prev_close > 0:
                            open_pct = round((open_price - prev_close) / prev_close * 100, 2)

                        threshold = 19.8 if (symbol.startswith("30") or symbol.startswith("68")) else 9.8
                        is_one_word_up = False
                        is_one_word_down = False
                        if open_price is not None and high_price is not None and low_price is not None and open_pct is not None:
                            if open_price == high_price == low_price and open_pct >= threshold:
                                is_one_word_up = True
                            elif open_price == high_price == low_price and open_pct <= -threshold:
                                is_one_word_down = True

                        is_limit_up = False
                        is_sealed = False
                        if pct_change is not None and pct_change >= threshold - 0.2:
                            is_limit_up = True
                            if (ask1_vol_hand == 0 or ask1_price == 0) and (bid1_amount >= 10000000.0 or is_one_word_up):
                                is_sealed = True

                        if price is not None and price > 0:
                            results.append({
                                "code": full_code,
                                "symbol": symbol,
                                "name": name,
                                "open": open_price,
                                "prev_close": prev_close,
                                "price": round(price, 3),
                                "high": high_price,
                                "low": low_price,
                                "volume": vol_shares,
                                "amount": amount_yuan,
                                "amount_wan": amount_wan,
                                "open_pct": open_pct,
                                "pct_change": pct_change,
                                "bid1_vol": bid1_vol_hand * 100,
                                "bid1_price": bid1_price,
                                "bid1_amount": bid1_amount,
                                "bid1_amount_wan": bid1_amount_wan,
                                "ask1_vol": ask1_vol_hand * 100,
                                "ask1_price": ask1_price,
                                "is_limit_up": is_limit_up,
                                "is_sealed": is_sealed,
                                "is_one_word_up": is_one_word_up,
                                "is_one_word_down": is_one_word_down,
                                "date": trade_date,
                                "trade_date": trade_date,
                                "time": time_str,
                            })
                            parsed_codes.add(full_code.lower())
                            parsed_codes.add(symbol.lower())
                except Exception as line_err:
                    logger.warning(f"Tencent parse error for single line '{line[:50]}': {line_err}")
                    continue

            # 统计缺失标的
            missing_codes = []
            for c in codes:
                c_str = str(c).strip().lower()
                clean_c = c_str.replace("sh", "").replace("sz", "").replace("bj", "")
                fmt_c = self._format_symbol(c_str)
                if c_str not in parsed_codes and clean_c not in parsed_codes and fmt_c not in parsed_codes:
                    missing_codes.append(str(c))

            if len(results) >= len(codes):
                quality = DataQuality.FULL
            elif results:
                quality = DataQuality.PARTIAL
            else:
                quality = DataQuality.UNAVAILABLE

            status = DataStatus.AVAILABLE if results else DataStatus.EMPTY
            freshness = Freshness.REALTIME if results else Freshness.UNAVAILABLE

            return DataResult(
                data=results,
                quality=quality,
                status=status,
                freshness=freshness,
                missing_codes=missing_codes if missing_codes else None,
                provider=self.name,
            )
        except Exception as e:
            logger.error(f"Tencent get_stock_quotes failed: {e}")
            return DataResult(
                data=[],
                quality=DataQuality.FAILED,
                status=DataStatus.ERROR,
                freshness=Freshness.UNAVAILABLE,
                provider=self.name,
                error_message=str(e),
                missing_codes=list(codes),
            )

    async def get_index_quotes(self, codes: List[str]) -> DataResult:
        """获取大盘核心基准指数行情 (具备单标的异常隔离与缺失标记)"""
        if not codes:
            return DataResult(
                data=[],
                quality=DataQuality.FULL,
                status=DataStatus.EMPTY,
                freshness=Freshness.REALTIME,
                provider=self.name,
            )

        formatted_codes = [self._format_symbol(c) for c in codes if str(c).strip()]
        url = f"{self.BASE_URL}{','.join(formatted_codes)}"

        quotes = []
        parsed_codes = set()
        try:
            async with httpx.AsyncClient(timeout=6.0, trust_env=False) as client:
                resp = await client.get(url, headers=self.HEADERS)
                if resp.status_code != 200:
                    return DataResult(
                        data=[],
                        quality=DataQuality.FAILED,
                        status=DataStatus.ERROR,
                        freshness=Freshness.UNAVAILABLE,
                        provider=self.name,
                        error_message=f"Tencent Index HTTP {resp.status_code}",
                        missing_codes=list(codes),
                    )
                content = resp.content.decode("gbk", errors="ignore")

            for line in content.strip().split(";"):
                line = line.strip()
                if not line or "=" not in line:
                    continue
                try:
                    var_part, val_part = line.split("=", 1)
                    full_code = var_part.split("_")[-1].replace('"', "").strip()
                    val_str = val_part.strip().strip('"')
                    parts = val_str.split("~")
                    if len(parts) > 30:
                        name = parts[1].strip()
                        code = parts[2].strip()
                        price = float(parts[3]) if parts[3] else None
                        prev_close = float(parts[4]) if parts[4] else None
                        open_price = float(parts[5]) if parts[5] else None

                        dt_raw = parts[30].strip() if len(parts) > 30 else ""
                        trade_date = None
                        trade_time = None
                        if len(dt_raw) >= 14 and dt_raw.isdigit():
                            trade_date = f"{dt_raw[:4]}-{dt_raw[4:6]}-{dt_raw[6:8]}"
                            trade_time = f"{dt_raw[8:10]}:{dt_raw[10:12]}:{dt_raw[12:14]}"
                        time_str = f"{trade_date} {trade_time}" if (trade_date and trade_time) else None

                        change = float(parts[31]) if len(parts) > 31 and parts[31] else None
                        pct_change = float(parts[32]) if len(parts) > 32 and parts[32] else None
                        high_price = float(parts[33]) if len(parts) > 33 and parts[33] else None
                        low_price = float(parts[34]) if len(parts) > 34 and parts[34] else None
                        amount_wan = float(parts[37]) if len(parts) > 37 and parts[37] else None

                        low_pct = round(((low_price - prev_close) / prev_close) * 100, 2) if (low_price and prev_close and prev_close > 0) else None
                        high_pct = round(((high_price - prev_close) / prev_close) * 100, 2) if (high_price and prev_close and prev_close > 0) else None
                        rebound_pct = round(((price - low_price) / prev_close) * 100, 2) if (price and low_price and prev_close and prev_close > 0) else None
                        amplitude = round(((high_price - low_price) / prev_close) * 100, 2) if (high_price and low_price and prev_close and prev_close > 0) else None

                        if price is not None and price > 0:
                            quotes.append({
                                "code": full_code,
                                "symbol": full_code,
                                "name": name,
                                "price": round(price, 2),
                                "pre_close": round(prev_close, 2) if prev_close is not None else None,
                                "open": round(open_price, 2) if open_price is not None else None,
                                "high": round(high_price, 2) if high_price is not None else None,
                                "low": round(low_price, 2) if low_price is not None else None,
                                "change": round(change, 2) if change is not None else None,
                                "pct_change": round(pct_change, 2) if pct_change is not None else None,
                                "low_pct": low_pct,
                                "high_pct": high_pct,
                                "rebound_pct": rebound_pct,
                                "amplitude": amplitude,
                                "amount_wan": round(amount_wan, 2) if amount_wan is not None else None,
                                "date": trade_date,
                                "trade_date": trade_date,
                                "time": time_str,
                            })
                            parsed_codes.add(full_code.lower())
                            parsed_codes.add(code.lower())
                except Exception as line_err:
                    logger.warning(f"Tencent parse error for single index line '{line[:50]}': {line_err}")
                    continue

            missing_codes = []
            for c in codes:
                c_str = str(c).strip().lower()
                clean_c = c_str.replace("sh", "").replace("sz", "").replace("bj", "")
                fmt_c = self._format_symbol(c_str)
                if c_str not in parsed_codes and clean_c not in parsed_codes and fmt_c not in parsed_codes:
                    missing_codes.append(str(c))

            if len(quotes) >= len(codes):
                quality = DataQuality.FULL
            elif quotes:
                quality = DataQuality.PARTIAL
            else:
                quality = DataQuality.UNAVAILABLE

            status = DataStatus.AVAILABLE if quotes else DataStatus.EMPTY
            freshness = Freshness.REALTIME if quotes else Freshness.UNAVAILABLE

            return DataResult(
                data=quotes,
                quality=quality,
                status=status,
                freshness=freshness,
                missing_codes=missing_codes if missing_codes else None,
                provider=self.name,
            )
        except Exception as e:
            logger.error(f"Tencent get_index_quotes failed: {e}")
            return DataResult(
                data=[],
                quality=DataQuality.FAILED,
                status=DataStatus.ERROR,
                freshness=Freshness.UNAVAILABLE,
                provider=self.name,
                error_message=str(e),
                missing_codes=list(codes),
            )
