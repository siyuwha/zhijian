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
    clean_code = stock_code.strip().upper()
    if "." in clean_code:
        code_part, mkt_part = clean_code.split(".", 1)
        if mkt_part in ("SH", "SS"):
            return TDXParams.MARKET_SH, code_part
        elif mkt_part in ("SZ",):
            return TDXParams.MARKET_SZ, code_part
        clean_code = code_part

    if clean_code.startswith(("6", "99", "68")):
        return TDXParams.MARKET_SH, clean_code
    elif clean_code.startswith(("0", "3")):
        return TDXParams.MARKET_SZ, clean_code
    elif clean_code.startswith(("4", "8")):
        # 北交所通常挂在深圳或者单独市场，主板行情优先匹配深圳
        return TDXParams.MARKET_SZ, clean_code
    return TDXParams.MARKET_SH, clean_code


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
            price = q.get("price", 0.0)
            last_close = q.get("last_close", 0.0)
            pct_chg = round(((price - last_close) / last_close) * 100, 2) if last_close else 0.0
            
            results.append({
                "code": code,
                "market": q.get("market"),
                "price": price,
                "last_close": last_close,
                "pct_chg": pct_chg,
                "open": q.get("open"),
                "high": q.get("high"),
                "low": q.get("low"),
                "vol": q.get("vol"),             # 手数
                "amount": q.get("amount"),       # 元
                "amount_yi": round(q.get("amount", 0) / 1e8, 2),
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

    def get_minute_trend(self, code: str) -> List[Dict[str, Any]]:
        """获取 241 点全天分时走势"""
        if not self.connect_best_server():
            return []
        market, clean_code = parse_code_market(code)
        raw_minutes = self.api.get_minute_time_data(market, clean_code)
        if not raw_minutes:
            return []
        
        points = []
        for i, item in enumerate(raw_minutes):
            points.append({
                "minute_idx": i,
                "price": item.get("price"),
                "vol": item.get("vol")
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
