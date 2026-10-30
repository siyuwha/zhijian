# -*- coding: utf-8 -*-
"""
TDX 直连通用客户端核心模块 (高可用主站池与断线自动重试)
专为 NAS Linux Docker 与无头服务器环境设计，100% 纯 Python 实现
"""

import time
from typing import List, Tuple, Optional, Dict, Any
from pytdx.hq import TdxHq_API
from pytdx.params import TDXParams

# 全国验证可用的通达信高速券商主站集群
DEFAULT_HQ_SERVERS = [
    {"name": "华泰证券南京电信4", "ip": "117.34.114.18", "port": 7709},
    {"name": "华泰证券南京电信2", "ip": "117.34.114.15", "port": 7709},
    {"name": "华泰证券南京电信1", "ip": "117.34.114.14", "port": 7709},
    {"name": "华泰证券南京电信3", "ip": "117.34.114.16", "port": 7709},
    {"name": "国联证券北京", "ip": "123.125.108.14", "port": 7709},
    {"name": "上海双线主站80端口", "ip": "180.153.18.172", "port": 80},
    {"name": "杭州主站J2", "ip": "115.238.56.198", "port": 7709},
]

def parse_code_market(stock_code: str) -> Tuple[int, str]:
    """
    智能将股票代码转换为 pytdx 规范 (market, clean_code)
    0: 深圳 (00, 30)
    1: 上海 (60, 68, 99, 000001指数)
    """
    raw = str(stock_code).strip().upper()
    mkt = None
    clean = raw

    # 1. 优先处理带点格式: "002724.SZ", "600519.SH", "SZ.002724"
    if "." in raw:
        p0, p1 = raw.split(".", 1)
        if p1 in ("SH", "SS"):
            mkt = TDXParams.MARKET_SH
            clean = p0
        elif p1 in ("SZ", "BJ"):
            mkt = TDXParams.MARKET_SZ
            clean = p0
        elif p0 in ("SH", "SS"):
            mkt = TDXParams.MARKET_SH
            clean = p1
        elif p0 in ("SZ", "BJ"):
            mkt = TDXParams.MARKET_SZ
            clean = p1
        else:
            clean = p0 if p0.isdigit() else p1

    # 2. 处理无点前缀格式: "SZ002724", "SH600519", "BJ832000"
    if clean.startswith("SZ"):
        mkt = TDXParams.MARKET_SZ
        clean = clean[2:].lstrip(".")
    elif clean.startswith("SH"):
        mkt = TDXParams.MARKET_SH
        clean = clean[2:].lstrip(".")
    elif clean.startswith("BJ"):
        mkt = TDXParams.MARKET_SZ
        clean = clean[2:].lstrip(".")

    clean = clean.strip()
    if mkt is not None:
        return mkt, clean

    # 3. 按代码特征推导
    if clean.startswith(("6", "99", "68")):
        return TDXParams.MARKET_SH, clean
    elif clean.startswith(("0", "3", "4", "8")):
        return TDXParams.MARKET_SZ, clean
    return TDXParams.MARKET_SH, clean



class TdxDirectClient:
    """通达信行情直连高可用客户端"""

    def __init__(self, servers: Optional[List[Dict[str, Any]]] = None, timeout: float = 3.5):
        self.servers = servers or DEFAULT_HQ_SERVERS
        self.timeout = timeout
        self.api = TdxHq_API(auto_retry=True)
        self.connected_server: Optional[Dict[str, Any]] = None

    def connect_best_server(self) -> bool:
        """从主站池中自动探测并连接低延迟主站"""
        if self.connected_server:
            try:
                # 探活心跳
                if self.api.get_security_count(TDXParams.MARKET_SH) > 0:
                    return True
            except Exception:
                self.api.disconnect()
                self.connected_server = None

        for srv in self.servers:
            try:
                ok = self.api.connect(srv["ip"], srv["port"], time_out=self.timeout)
                if ok:
                    self.connected_server = srv
                    return True
            except Exception:
                continue
        return False

    def close(self):
        """断开连接"""
        try:
            if self.connected_server:
                self.api.disconnect()
        except Exception:
            pass
        finally:
            self.connected_server = None

    def __enter__(self):
        self.connect_best_server()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_market_date(self) -> Optional[str]:
        """
        从通达信主站查询市场最新基准交易日 (基于上证指数最新日K线，杜绝伪造系统当前日期)
        """
        now = time.time()
        if hasattr(self, "_cached_market_date"):
            ts, cached_date = self._cached_market_date
            if now - ts < 60.0 and cached_date:
                return cached_date

        if not self.connect_best_server():
            return None
        try:
            bars = self.api.get_index_bars(
                category=TDXParams.KLINE_TYPE_DAILY,
                market=TDXParams.MARKET_SH,
                code="000001",
                start=0,
                count=1
            )
            if bars:
                dt_str = bars[-1].get("datetime")
                if dt_str and len(dt_str) >= 10:
                    trade_date = dt_str[:10]
                    self._cached_market_date = (now, trade_date)
                    return trade_date
        except Exception as e:
            pass
        return None

    def get_stock_trade_date(self, market: int, code: str) -> Optional[str]:
        """
        从通达信主站查询单个标的自身的最权威交易日 (基于该个股自身最新日K线，绝不借用大盘指数日期)
        """
        if not self.connect_best_server():
            return None
        try:
            bars = self.api.get_security_bars(
                category=TDXParams.KLINE_TYPE_DAILY,
                market=market,
                code=code,
                start=0,
                count=1
            )
            if bars:
                dt_str = bars[-1].get("datetime")
                if dt_str and len(dt_str) >= 10:
                    return dt_str[:10]
        except Exception:
            pass
        return None

    def get_quote(self, code: str) -> Optional[Dict[str, Any]]:
        """获取单只个股实时五档快照"""
        market, clean_code = parse_code_market(code)
        quotes = self.get_quotes([code])
        return quotes[0] if quotes else None

    def get_quotes(self, codes: List[str]) -> List[Dict[str, Any]]:
        """批量获取多只个股实时五档快照"""
        if not self.connect_best_server():
            return []

        param_list = [parse_code_market(c) for c in codes]
        raw_quotes = self.api.get_security_quotes(param_list)
        if not raw_quotes:
            return []

        results = []
        for q in raw_quotes:
            code = q.get("code")
            mkt = q.get("market")
            price = q.get("price", 0.0)
            last_close = q.get("last_close", 0.0)
            pct_chg = round(((price - last_close) / last_close) * 100, 2) if last_close else 0.0

            server_time = q.get("servertime")
            # 严格安全边界 (SSOT 来源确权防线):
            # 报价必须提供属于其快照自身的完整可信日期 (如上游原生 date/trade_date)。
            # 绝对严禁借用上证指数日期或独立的个股日K线日期！
            # 因为日K线与报价是两次独立网络请求，若日K已更新至今日而报价滞留，借用日K日期会使陈旧报价通过新鲜度检查导致误平仓。
            # 无法证明日期属于该条报价自身时，权威标记为 None，交由提供方标记为 UNAVAILABLE 并由风控刚性阻断。
            quote_date = q.get("date") or q.get("trade_date")

            clean_time = server_time[:8] if (server_time and len(server_time) >= 8) else (q.get("time") or server_time)
            results.append({
                "code": code,
                "symbol": code,
                "market": mkt,
                "price": price,
                "last_close": last_close,
                "prev_close": last_close,
                "pct_chg": pct_chg,
                "pct_change": pct_chg,
                "open": q.get("open"),
                "high": q.get("high"),
                "low": q.get("low"),
                "vol": q.get("vol"),             # 手数
                "volume": q.get("vol"),
                "amount": q.get("amount"),       # 元
                "amount_yi": round(q.get("amount", 0) / 1e8, 2),
                "amount_wan": round(q.get("amount", 0) / 10000.0, 2),
                "servertime": server_time,
                "date": quote_date,
                "trade_date": quote_date,
                "time": clean_time,
                "bid1": q.get("bid1"), "bid_vol1": q.get("bid_vol1"),
                "bid2": q.get("bid2"), "bid_vol2": q.get("bid_vol2"),
                "bid3": q.get("bid3"), "bid_vol3": q.get("bid_vol3"),
                "bid4": q.get("bid4"), "bid_vol4": q.get("bid_vol4"),
                "bid5": q.get("bid5"), "bid_vol5": q.get("bid_vol5"),
                "ask1": q.get("ask1"), "ask_vol1": q.get("ask_vol1"),
                "ask2": q.get("ask2"), "ask_vol2": q.get("ask_vol2"),
                "ask3": q.get("ask3"), "ask_vol3": q.get("ask_vol3"),
                "ask4": q.get("ask4"), "ask_vol4": q.get("ask_vol4"),
                "ask5": q.get("ask5"), "ask_vol5": q.get("ask_vol5"),
            })
        return results

    def get_minute_trend(
        self,
        code: str,
        date: Optional[Any] = None,
        pre_close: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        获取 240~241 点全天分时走势
        - 盘中实时时段严格校验数据真实性 (防 pytdx 6 字节对齐漂移与 0.0/800+ 荒谬数据)
        - 盘后闭市时段或校验不通过时自动无缝回退至交易日历史分时
        """
        from datetime import datetime, time as dt_time
        from ...core.calendar import calendar

        requested_date = None
        if date is not None:
            date_text = str(date).strip()
            try:
                if len(date_text) == 8 and date_text.isdigit():
                    requested_date = datetime.strptime(date_text, "%Y%m%d").date()
                else:
                    requested_date = datetime.strptime(date_text, "%Y-%m-%d").date()
            except (TypeError, ValueError):
                # A malformed explicit date is a bad request, not permission to
                # silently switch back to the live/latest session.
                return []

            if requested_date > datetime.now().date():
                return []

        if not self.connect_best_server():
            return []
        market, clean_code = parse_code_market(code)

        now = datetime.now()
        is_trading_day = calendar.is_trading_day(now.date())
        today_int = int(now.strftime("%Y%m%d"))
        req_date_int = int(requested_date.strftime("%Y%m%d")) if requested_date else None

        raw_minutes = None
        resolved_date = requested_date

        # 1. 若显式指定了交易日期 (严格防穿透：不得回退到其他交易日)
        if req_date_int is not None:
            if req_date_int > today_int:
                return []

            if req_date_int < today_int:
                # 严格历史日期：只能拉取该日历史分时
                try:
                    raw_minutes = self.api.get_history_minute_time_data(market, clean_code, req_date_int)
                except Exception:
                    pass
                # Historical pytdx minute records carry no timestamps. A short
                # or overlong result cannot be mapped to the trading clock
                # without guessing, so reject it instead of shifting the curve.
                if not raw_minutes or len(raw_minutes) != 240:
                    return []
            else:
                # 显式指定今天：尝试历史归档或当日实时分时，但绝不可回退到昨天
                try:
                    raw_minutes = self.api.get_history_minute_time_data(market, clean_code, req_date_int)
                except Exception:
                    pass
                if not raw_minutes or len(raw_minutes) == 0:
                    try:
                        raw_minutes = self.api.get_minute_time_data(market, clean_code)
                    except Exception:
                        pass
                if not raw_minutes or len(raw_minutes) == 0:
                    return []
                resolved_date = requested_date

        # 2. 未指定日期 (date is None)：按盘中活跃时段拉取实时分时并做严格物理校验
        if req_date_int is None:
            # A 股交易时段窗口：09:25 ~ 15:05
            is_intraday_active = is_trading_day and (
                dt_time(9, 25) <= now.time() <= dt_time(15, 5)
            )
            if is_intraday_active:
                try:
                    real_data = self.api.get_minute_time_data(market, clean_code)
                    if real_data and len(real_data) > 0:
                        first_p = float(real_data[0].get("price") or 0.0)
                        last_p = float(real_data[-1].get("price") or 0.0)

                        # 校验价格有效性：A股不可能小于等于 0.05 元
                        is_valid = (first_p > 0.05 and last_p > 0.05)
                        if pre_close and pre_close > 0.0:
                            # 涨跌幅偏离不能超过 30% (允许 20% 涨跌停缓冲)
                            dev_first = abs(first_p - pre_close) / pre_close
                            dev_last = abs(last_p - pre_close) / pre_close
                            if dev_first > 0.30 or dev_last > 0.30:
                                is_valid = False

                        if is_valid:
                            raw_minutes = real_data
                            resolved_date = now.date()
                except Exception:
                    pass

            # 3. 仅在未指定日期且（非交易时段、实时分时无效、或出现漂移）时，使用日历向前回溯拉取有效历史分时
            if not raw_minutes or len(raw_minutes) == 0:
                chk_dt = now.date()
                if not is_trading_day or now.time() < dt_time(9, 30):
                    chk_dt = calendar.prev_trading_day(chk_dt)

                for _ in range(5):
                    chk_date_int = int(chk_dt.strftime("%Y%m%d"))
                    try:
                        hist_data = self.api.get_history_minute_time_data(market, clean_code, chk_date_int)
                        if hist_data and len(hist_data) >= 120:
                            chk_p0 = float(hist_data[0].get("price") or 0.0)
                            chk_plast = float(hist_data[-1].get("price") or 0.0)
                            if chk_p0 > 0.05 and chk_plast > 0.05:
                                if pre_close and pre_close > 0.0:
                                    if abs(chk_plast - pre_close) / pre_close <= 0.30:
                                        raw_minutes = hist_data
                                        resolved_date = chk_dt
                                        break
                                else:
                                    raw_minutes = hist_data
                                    resolved_date = chk_dt
                                    break
                    except Exception:
                        pass
                    chk_dt = calendar.prev_trading_day(chk_dt)

        if not raw_minutes:
            return []

        points = []
        resolved_date_text = resolved_date.isoformat() if resolved_date else None
        for i, item in enumerate(raw_minutes):
            p = float(item.get("price") or 0.0)
            v = int(item.get("vol") or 0)
            points.append({
                "minute_idx": i,
                "price": p,
                "vol": v,
                "trade_date": resolved_date_text,
            })
        return points

    def get_kline(self, code: str, period: str = "1d", count: int = 100) -> List[Dict[str, Any]]:
        """
        获取多周期 K 线历史
        period: '1d' (日线), '5m' (5分钟), '1m' (1分钟), '15m', '30m', '60m'
        """
        if not self.connect_best_server():
            return []
        market, clean_code = parse_code_market(code)

        category_map = {
            "5m": 0, "15m": 1, "30m": 2, "60m": 3, "1h": 3,
            "1d": 4, "day": 4, "daily": 4,
            "1w": 5, "week": 5, "1mon": 6, "month": 6,
            "1m": 8
        }
        cat = category_map.get(period.lower(), 4)
        bars = self.api.get_security_bars(category=cat, market=market, code=clean_code, start=0, count=count)
        if not bars:
            return []

        results = []
        for b in bars:
            results.append({
                "datetime": b.get("datetime"),
                "open": b.get("open"),
                "high": b.get("high"),
                "low": b.get("low"),
                "close": b.get("close"),
                "vol": b.get("vol"),
                "amount": b.get("amount"),
                "amount_yi": round(b.get("amount", 0) / 1e8, 2)
            })
        return results

    def get_ticks(self, code: str, count: int = 30) -> List[Dict[str, Any]]:
        """获取逐笔成交明细"""
        if not self.connect_best_server():
            return []
        market, clean_code = parse_code_market(code)
        raw_ticks = self.api.get_transaction_data(market, clean_code, start=0, count=count)
        if not raw_ticks:
            return []

        results = []
        for t in raw_ticks:
            bs = t.get("buyorsell")
            direction = "买盘" if bs == 0 else ("卖盘" if bs == 1 else "中性盘")
            results.append({
                "time": t.get("time"),
                "price": t.get("price"),
                "vol": t.get("vol"),
                "buyorsell": bs,
                "direction": direction
            })
        return results

    def get_index_quotes(self) -> List[Dict[str, Any]]:
        """获取大盘核心指数 (上证、深证、创业板、科创50)"""
        if not self.connect_best_server():
            return []

        index_targets = [
            ("上证指数", TDXParams.MARKET_SH, "000001"),
            ("深证成指", TDXParams.MARKET_SZ, "399001"),
            ("创业板指", TDXParams.MARKET_SZ, "399006"),
            ("科创50", TDXParams.MARKET_SH, "000688"),
        ]

        indices = []
        for name, mkt, code in index_targets:
            bars = self.api.get_index_bars(category=4, market=mkt, code=code, start=0, count=1)
            if bars:
                latest = bars[-1]
                indices.append({
                    "name": name,
                    "code": code,
                    "datetime": latest.get("datetime"),
                    "close": latest.get("close"),
                    "open": latest.get("open"),
                    "high": latest.get("high"),
                    "low": latest.get("low"),
                    "amount_yi": round(latest.get("amount", 0) / 1e8, 2)
                })
        return indices
