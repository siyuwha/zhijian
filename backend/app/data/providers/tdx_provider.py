import asyncio
import logging
import math
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
from datetime import date, datetime

from ..capabilities import (
    DataQuality,
    DataResult,
    DataStatus,
    Freshness,
    StockTrendsCapability,
    StockQuoteCapability,
    ConceptBlocksCapability,
)
from ...core.calendar import calendar
from .base import BaseProvider

logger = logging.getLogger(__name__)

try:
    from .tdx_client import TdxDirectClient, parse_code_market
    TDX_AVAILABLE = True
except Exception as e:
    logger.warning(f"TDX Direct Client import failed in TdxProvider: {e}")
    TDX_AVAILABLE = False


class TdxProvider(BaseProvider, StockTrendsCapability, StockQuoteCapability, ConceptBlocksCapability):
    """
    基于通达信原生券商行情主站直连协议的数据提供者 (TDX Direct Provider)
    优势：
    1. 毫秒级原生 TCP 直连券商主站，无反爬限制，无需任何第三方 Token；
    2. 提供物理真实的 241 分钟连续分时价格点阵，坚决杜绝平滑贝塞尔拟合；
    3. 原生支持无头 Linux Docker 与 Windows 环境。
    """

    def __init__(self, client: Optional[Any] = None):
        super().__init__(
            name="tdx_direct",
            implementation_status="已接入",
            connectivity_verified="已验证",
            schema_verified="已验证",
            semantic_verified="已验证",
            production_eligible="准入",
        )
        self._client = client

    async def is_available(self) -> bool:
        """检查通达信直连是否可用"""
        return TDX_AVAILABLE

    def _get_client(self):
        if not TDX_AVAILABLE:
            return None
        if self._client is None:
            try:
                self._client = TdxDirectClient()
            except Exception as e:
                logger.warning(f"Failed to initialize TdxDirectClient: {e}")
        return self._client

    @staticmethod
    def _parse_trade_date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = str(value or "").strip()
        if len(text) >= 10 and text[4:5] == "-":
            text = text[:10]
        for date_format in ("%Y-%m-%d", "%Y%m%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _normalize_code(value: Any) -> str:
        code = str(value or "").strip().upper()
        if code.startswith("BK"):
            return code
        if "." in code:
            code = next((part for part in code.split(".") if part.isdigit()), code)
        if code.startswith(("SH", "SZ", "BJ")):
            code = code[2:].lstrip(".")
        digits = "".join(ch for ch in code if ch.isdigit())
        return digits or code

    @staticmethod
    def _positive_price(value: Any) -> Optional[float]:
        try:
            price = float(value)
        except (TypeError, ValueError):
            return None
        return price if math.isfinite(price) and price > 0 else None

    def _get_daily_context(self, client: Any, code: str, session_date: date) -> Tuple[Optional[float], Optional[float]]:
        """Return the prior session close and requested session open from real daily bars."""
        try:
            bars = client.get_kline(code, period="1d", count=800)
        except Exception as exc:
            logger.info("Unable to load daily bars for %s on %s: %s", code, session_date, exc)
            return None, None

        if not isinstance(bars, (list, tuple)):
            return None, None

        prior_bars: List[Tuple[date, float]] = []
        session_open: Optional[float] = None
        for bar in bars:
            if not isinstance(bar, dict):
                continue
            bar_date = self._parse_trade_date(bar.get("datetime"))
            if bar_date is None:
                continue
            close = self._positive_price(bar.get("close"))
            if close is None:
                continue
            if bar_date < session_date:
                prior_bars.append((bar_date, close))
            elif bar_date == session_date:
                session_open = self._positive_price(bar.get("open"))

        previous_close = max(prior_bars, key=lambda item: item[0])[1] if prior_bars else None
        return previous_close, session_open

    async def get_stock_trends(self, codes: list[str], trade_date: Optional[str] = None) -> DataResult:
        """
        获取指定股票代码的真实 241 分钟全天分时走势 (支持显式交易日期历史拉取)
        """
        requested_codes = list(dict.fromkeys(
            self._normalize_code(code) for code in codes if str(code or "").strip()
        ))
        if not requested_codes:
            return DataResult(
                data=[],
                quality=DataQuality.FULL,
                status=DataStatus.AVAILABLE,
                provider=self.name,
            )

        requested_date = self._parse_trade_date(trade_date) if trade_date is not None else date.today()
        today = date.today()
        if requested_date is None or requested_date > today:
            return DataResult(
                data=[],
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.EMPTY,
                provider=self.name,
                error_message="Invalid or future trade_date",
                missing_codes=requested_codes,
            )

        client = self._get_client()
        if not client:
            return DataResult(
                data=[],
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.EMPTY,
                provider=self.name,
                error_message="TDX client not available",
                missing_codes=requested_codes,
            )

        loop = asyncio.get_event_loop()
        stock_codes = [code for code in requested_codes if not code.startswith("BK")]

        def _fetch_all_sync() -> List[Dict[str, Any]]:
            results = []
            if not stock_codes or not client.connect_best_server():
                return []

            clean_codes = stock_codes
            quotes = client.get_quotes(clean_codes)
            quote_map = {q["code"]: q for q in quotes if q.get("code")}

            # 2. 生成标准 241 分钟交易时间刻度表 (09:30~11:30 121分 + 13:01~15:00 120分)
            morning_times = [f"{m // 60:02d}:{m % 60:02d}" for m in range(570, 691)]
            afternoon_times = [f"{m // 60:02d}:{m % 60:02d}" for m in range(781, 901)]
            timeline = morning_times + afternoon_times

            for code in clean_codes:
                q = quote_map.get(code, {})
                name = q.get("name") or code

                quote_pre_close = self._positive_price(q.get("last_close") or q.get("pre_close"))
                is_requested_today = requested_date == today
                minute_pre_close = quote_pre_close if is_requested_today else None
                raw_minutes = client.get_minute_trend(code, date=trade_date, pre_close=minute_pre_close)
                if not raw_minutes:
                    continue

                point_date = self._parse_trade_date(raw_minutes[0].get("trade_date")) if isinstance(raw_minutes[0], dict) else None
                session_date = point_date or (requested_date if trade_date is not None else today)
                if trade_date is not None and session_date != requested_date:
                    logger.warning("TDX returned %s trend for requested date %s", session_date, requested_date)
                    continue

                quote_open = self._positive_price(q.get("open"))
                if session_date == today and quote_pre_close is not None and quote_open is not None:
                    daily_pre_close, daily_open = None, None
                else:
                    daily_pre_close, daily_open = self._get_daily_context(client, code, session_date)
                pre_close = quote_pre_close if session_date == today else daily_pre_close
                if pre_close is None:
                    pre_close = daily_pre_close
                if pre_close is None:
                    logger.info("Missing reliable previous close for %s on %s", code, session_date)
                    continue

                session_open = quote_open if session_date == today else daily_open
                if session_open is None:
                    session_open = daily_open

                # TDX minute-time data omits the independently sampled 09:30
                # open anchor. Add it only when the actual session open exists;
                # otherwise leave a visible gap before the first physical point.
                timeline_offset = 0
                if 0 < len(raw_minutes) <= 240:
                    if session_open is not None:
                        raw_minutes = [{"price": session_open, "vol": 0}] + raw_minutes
                    else:
                        timeline_offset = 1

                trend_points = []
                cum_amount = 0.0
                cum_vol = 0
                invalid_series = False
                for i, pt in enumerate(raw_minutes):
                    if not isinstance(pt, dict):
                        invalid_series = True
                        break
                    timeline_index = i + timeline_offset
                    if timeline_index >= len(timeline):
                        invalid_series = True
                        break
                    t_str = timeline[timeline_index]
                    price = self._positive_price(pt.get("price"))
                    try:
                        vol = int(pt.get("vol") or 0)
                    except (TypeError, ValueError):
                        invalid_series = True
                        break
                    if price is None or vol < 0:
                        invalid_series = True
                        break
                    cum_vol += vol
                    # 估算成交额 (元)
                    cum_amount += price * vol * 100
                    pct = round((price - pre_close) / pre_close * 100.0, 2)

                    trend_points.append({
                        "time": t_str,
                        "price": price,
                        "pct_change": pct,
                        "avg_price": round(price, 2),
                        "volume": vol,
                        "amount": cum_amount,
                    })

                if invalid_series or not trend_points:
                    continue

                results.append({
                    "code": code,
                    "name": name,
                    "pre_close": pre_close,
                    "trends": trend_points,
                    "is_real": True,
                    "trade_date": session_date.isoformat(),
                })

            return results

        try:
            items = await loop.run_in_executor(None, _fetch_all_sync)
            fetched_codes = {self._normalize_code(item.get("code")) for item in items if isinstance(item, dict)}
            missing_codes = [code for code in requested_codes if code not in fetched_codes]

            # TDX has no BK-sector protocol. Fill only missing rows from the
            # registered secondary source while preserving successful TDX rows.
            backup_provider_name = None
            if items and missing_codes:
                from .eastmoney import EastmoneyProvider

                try:
                    backup = await EastmoneyProvider().get_stock_trends(missing_codes, trade_date=trade_date)
                    backup_items = [item for item in (backup.data or []) if isinstance(item, dict)]
                    existing = {self._normalize_code(item.get("code")) for item in items}
                    backup_added = False
                    for item in backup_items:
                        normalized = self._normalize_code(item.get("code"))
                        if normalized in missing_codes and normalized not in existing:
                            items.append(item)
                            existing.add(normalized)
                            backup_added = True
                    backup_provider_name = backup.provider if backup_added else None
                except Exception as backup_error:
                    logger.warning("Eastmoney stock-trend fallback failed: %s", backup_error)

            fetched_codes = {self._normalize_code(item.get("code")) for item in items if isinstance(item, dict)}
            missing_codes = [code for code in requested_codes if code not in fetched_codes]
            if not items:
                return DataResult(
                    data=[],
                    quality=DataQuality.UNAVAILABLE,
                    status=DataStatus.EMPTY,
                    provider=self.name,
                    missing_codes=missing_codes,
                )
            quality = DataQuality.FULL if not missing_codes else DataQuality.PARTIAL
            return DataResult(
                data=items,
                quality=quality,
                status=DataStatus.AVAILABLE,
                provider=f"{self.name}+{backup_provider_name}" if backup_provider_name else self.name,
                fallback_used=bool(backup_provider_name),
                missing_codes=missing_codes,
            )
        except Exception as e:
            logger.error(f"TdxProvider get_stock_trends failed: {e}")

        return DataResult(
            data=[],
            quality=DataQuality.UNAVAILABLE,
            status=DataStatus.EMPTY,
            provider=self.name,
            missing_codes=requested_codes,
        )

    async def get_stock_quotes(self, codes: List[str]) -> DataResult:
        """获取个股批量五档实时快照"""
        client = self._get_client()
        if not client:
            return DataResult(data=[], quality=DataQuality.UNAVAILABLE, freshness=Freshness.UNAVAILABLE, provider=self.name)

        loop = asyncio.get_event_loop()
        try:
            quotes = await loop.run_in_executor(None, lambda: client.get_quotes(codes))
            now = datetime.now()
            is_trading = calendar.is_trading_day(now.date())

            # 严格核查返回行情的日期和时间信息
            # 如果不是交易日，或者行情项缺失真实日期和时间，或日期非当日，绝对不得标为 REALTIME
            all_have_datetime = bool(quotes) and all(
                (q.get("date") or q.get("trade_date")) and (q.get("time") or q.get("servertime"))
                for q in quotes
            )
            today_str = now.date().isoformat()
            all_are_today = bool(quotes) and all(
                (q.get("date") or q.get("trade_date")) == today_str
                for q in quotes
            )
            if not is_trading:
                freshness = Freshness.STALE
            elif not all_have_datetime:
                freshness = Freshness.UNAVAILABLE
            elif not all_are_today:
                freshness = Freshness.STALE
            else:
                freshness = Freshness.REALTIME

            return DataResult(
                data=quotes,
                quality=DataQuality.FULL if quotes else DataQuality.UNAVAILABLE,
                freshness=freshness,
                status=DataStatus.AVAILABLE if (quotes and freshness == Freshness.REALTIME) else (DataStatus.STALE if freshness == Freshness.STALE else DataStatus.EMPTY),
                provider=self.name,
            )
        except Exception as e:
            return DataResult(data=[], quality=DataQuality.FAILED, freshness=Freshness.UNAVAILABLE, provider=self.name, error_message=str(e))

    async def get_concept_blocks(self, code: str) -> DataResult:
        """获取标的归属的三维板块映射集 (TDX 直连备用降级通道)"""
        if not code or not str(code).strip():
            return DataResult(data=[], quality=DataQuality.FULL, status=DataStatus.AVAILABLE, provider=self.name)

        clean_code = str(code).strip().lower()
        if clean_code.startswith(("sh", "sz", "bj")):
            clean_code = clean_code[2:]
        elif "." in clean_code:
            parts = clean_code.split(".")
            clean_code = parts[1] if parts[0] in ("sh", "sz", "bj") else parts[0]

        client = self._get_client()
        if not client:
            return DataResult(data=[], quality=DataQuality.UNAVAILABLE, status=DataStatus.EMPTY, provider=self.name)

        loop = asyncio.get_event_loop()

        def _fetch_tdx_blocks():
            if not client.connect_best_server():
                return []
            try:
                market, ccode = parse_code_market(clean_code)
                fin = client.api.get_finance_info(market, ccode)
                if fin and isinstance(fin, dict):
                    ind_id = fin.get("industry")
                    if ind_id is not None:
                        from ...core.canonical_fact import BlockMappingFact
                        from ...core.block_registry import BlockRegistry
                        block_name = f"TDX行业_{ind_id}"
                        fact = BlockMappingFact.create(
                            symbol=clean_code,
                            block_code=f"TDX_{ind_id}",
                            block_name=block_name,
                            category="INDUSTRY",
                            block_change_pct=None,
                            leader_name=None,
                            leader_symbol=None,
                        )
                        return [fact.to_dict()]
            except Exception as e:
                logger.warning(f"TDX get_concept_blocks fallback error: {e}")
            return []

        try:
            facts = await loop.run_in_executor(None, _fetch_tdx_blocks)
            if facts:
                return DataResult(
                    data=facts,
                    quality=DataQuality.DEGRADED,
                    status=DataStatus.AVAILABLE,
                    provider=self.name,
                    fallback_used=True,
                )
        except Exception as e:
            logger.warning(f"TDX get_concept_blocks failed: {e}")

        return DataResult(
            data=[],
            quality=DataQuality.DEGRADED,
            status=DataStatus.EMPTY,
            provider=self.name,
            error_message="TDX concept blocks fallback empty",
        )
