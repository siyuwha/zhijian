import json
import logging
import urllib.parse
from typing import Optional, List, Dict, Any, Tuple
import asyncio
import httpx
from .base import BaseProvider
from ..capabilities import (
    DataQuality,
    DataResult,
    DataStatus,
    Freshness,
    ProviderErrorCode,
    MarketBreadthCapability,
    MicroCapCapability,
    HighTierPerformanceCapability,
    SecuritySearchCapability,
    PriceAnomalyCapability,
    ConceptBlocksCapability,
    SectorCapability,
    StockTrendsCapability,
)
from ...core.canonical_fact import MarketAnomalyFact, BlockMappingFact
from ...core.block_registry import BlockRegistry

logger = logging.getLogger(__name__)

class EastmoneyProvider(
    BaseProvider,
    MarketBreadthCapability,
    MicroCapCapability,
    HighTierPerformanceCapability,
    SecuritySearchCapability,
    PriceAnomalyCapability,
    ConceptBlocksCapability,
    SectorCapability,
    StockTrendsCapability,
):
    """
    东方财富全市场广度、风格及高标数据适配器
    满足 P0-2 生产级防爆与状态明确化要求：
    1. 空响应 ≠ JSON 错误 ≠ 有效事实
    2. 全链路防御非交易时段空字符串与 4xx/5xx 响应，杜绝 JSONDecodeError 抛出
    3. 返回结果严格区分 AVAILABLE / EMPTY / STALE / TIMEOUT / ERROR 状态
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/",
        "Connection": "close",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    def __init__(self):
        super().__init__(
            name="eastmoney",
            implementation_status="已接入",
            connectivity_verified="已验证",
            schema_verified="已验证",
            semantic_verified="已验证",
            production_eligible="准入",
        )

    async def is_available(self) -> bool:
        return True

    @staticmethod
    def _safe_parse_json(resp: httpx.Response) -> Tuple[Optional[Dict[str, Any]], DataStatus, Optional[str]]:
        """
        安全解析响应体，严格区分：
        - (dict, AVAILABLE, None): 正常解析出业务字典
        - (None, EMPTY, msg): HTTP 200 但响应体为空串/空白符/零长度（如非交易时段断流）
        - (None, ERROR, msg): HTTP 4xx/5xx 或 JSONDecodeError 格式损坏
        """
        if resp.status_code != 200:
            return None, DataStatus.ERROR, f"HTTP {resp.status_code}"
        text = resp.text.strip()
        if not text:
            return None, DataStatus.EMPTY, "Empty response body (non-trading window or upstream empty)"
        try:
            data = resp.json()
            return data, DataStatus.AVAILABLE, None
        except Exception as e:
            return None, DataStatus.ERROR, f"JSON decode error: {e}"

    async def get_market_breadth(self) -> DataResult:
        """
        获取全市场上涨、下跌、平盘统计
        通过上证指数(1.000001)、深证成指(0.399001)、北证50(0.899050)的 f104(涨), f105(跌), f106(平) 聚合累加
        多节点容灾机制：依次尝试 push2delay 与 push2，彻底防御单节点连接重置 (RST)
        """
        params = {
            "fltt": "2",
            "secids": "1.000001,0.399001,0.899050",
            "fields": "f12,f13,f14,f104,f105,f106"
        }
        candidate_urls = [
            "https://push2delay.eastmoney.com/api/qt/ulist.np/get",
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            "https://82.push2.eastmoney.com/api/qt/ulist.np/get",
        ]

        last_error = None
        for url in candidate_urls:
            try:
                async with httpx.AsyncClient(timeout=6.0, trust_env=False, follow_redirects=True) as client:
                    resp = await client.get(url, params=params, headers=self.HEADERS)
                    res_data, status, err_msg = self._safe_parse_json(resp)

                if status == DataStatus.AVAILABLE and res_data:
                    diff_list = res_data.get("data", {}).get("diff", [])
                    if diff_list:
                        up_count = sum(int(item.get("f104", 0)) for item in diff_list if item.get("f104") is not None)
                        down_count = sum(int(item.get("f105", 0)) for item in diff_list if item.get("f105") is not None)
                        flat_count = sum(int(item.get("f106", 0)) for item in diff_list if item.get("f106") is not None)
                        total_stocks = up_count + down_count + flat_count
                        quality = DataQuality.FULL if total_stocks > 3000 else DataQuality.PARTIAL
                        return DataResult(
                            data={
                                "up_count": up_count,
                                "down_count": down_count,
                                "flat_count": flat_count,
                                "total_stocks": total_stocks
                            },
                            quality=quality,
                            status=DataStatus.AVAILABLE,
                            provider=self.name
                        )
                last_error = err_msg or "Empty diff list"
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Eastmoney node {url} failed: {e}, trying next candidate node...")
                continue

        logger.error(f"All Eastmoney breadth candidate nodes failed, last error: {last_error}")
        return DataResult(
            data=None,
            quality=DataQuality.UNAVAILABLE,
            status=DataStatus.ERROR,
            error_code=ProviderErrorCode.CONNECTION_ERROR,
            provider=self.name,
            error_message=f"All Eastmoney breadth nodes failed: {last_error}"
        )

    async def get_micro_cap_quote(self) -> DataResult:
        """
        获取微盘股指数行情
        使用 Eastmoney 官方 stock/get 接口获取 90.BK1158 (微盘股板块)
        """
        try:
            url = "https://push2delay.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": "90.BK1158",
                "fields": "f57,f58,f43,f169,f170"
            }
            async with httpx.AsyncClient(timeout=8.0, trust_env=False, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                res_data, status, err_msg = self._safe_parse_json(resp)

            if status == DataStatus.EMPTY:
                return DataResult(
                    data=None,
                    quality=DataQuality.UNAVAILABLE,
                    status=DataStatus.EMPTY,
                    error_code=ProviderErrorCode.EMPTY_PAYLOAD,
                    provider=self.name,
                    error_message=err_msg
                )
            if status == DataStatus.ERROR or res_data is None:
                return DataResult(
                    data=None,
                    quality=DataQuality.INVALID,
                    status=DataStatus.ERROR,
                    error_code=ProviderErrorCode.MALFORMED_PARSE,
                    provider=self.name,
                    error_message=err_msg
                )

            d = res_data.get("data")
            if d and d.get("f170") is not None:
                pct_change = round(float(d.get("f170")) / 100.0, 2)
                price = round(float(d.get("f43", 0)) / 100.0, 2)
                return DataResult(
                    data={
                        "symbol": "BK1158",
                        "name": d.get("f58", "微盘股"),
                        "pct_change": pct_change,
                        "price": price
                    },
                    quality=DataQuality.FULL,
                    status=DataStatus.AVAILABLE,
                    provider=self.name
                )

            # 若东财 BK1158 不可用，自动切换至新浪中证2000/国证2000 宽基指数作为微盘风格替代
            try:
                from .sina import SinaProvider
                sina = SinaProvider()
                q_res = await sina.get_index_quotes(["s_sh563300", "s_sz399303"])
                if q_res.data:
                    first = q_res.data[0]
                    return DataResult(
                        data={
                            "symbol": first.get("symbol", "sh563300"),
                            "name": first.get("name", "中证2000ETF"),
                            "pct_change": float(first.get("pct_change", 0.0)),
                            "price": float(first.get("price", 0.0))
                        },
                        quality=DataQuality.FULL,
                        status=DataStatus.AVAILABLE,
                        provider="sina_failover"
                    )
            except Exception as fe:
                logger.warning(f"Sina failover for micro_cap failed: {fe}")

            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.EMPTY,
                error_code=ProviderErrorCode.EMPTY_PAYLOAD,
                provider=self.name,
                error_message="Micro cap quote not available"
            )
        except Exception as e:
            logger.warning(f"Eastmoney get_micro_cap_quote failed ({e}), attempting Sina fallback...")
            try:
                from .sina import SinaProvider
                sina = SinaProvider()
                q_res = await sina.get_index_quotes(["s_sh563300", "s_sz399303"])
                if q_res.data:
                    first = q_res.data[0]
                    return DataResult(
                        data={
                            "symbol": first.get("symbol", "sh563300"),
                            "name": first.get("name", "中证2000ETF"),
                            "pct_change": float(first.get("pct_change", 0.0)),
                            "price": float(first.get("price", 0.0))
                        },
                        quality=DataQuality.FULL,
                        status=DataStatus.AVAILABLE,
                        provider="sina_failover"
                    )
            except Exception as fe:
                pass

            return DataResult(
                data=None,
                quality=DataQuality.FAILED,
                status=DataStatus.ERROR,
                error_code=ProviderErrorCode.CONNECTION_ERROR,
                provider=self.name,
                error_message=str(e)
            )

    async def get_high_tier_performance(self) -> DataResult:
        """
        获取高位股/连板生态承接表现 (D3 扩展指标)
        """
        try:
            url = "https://push2delay.eastmoney.com/api/qt/stock/get"
            params = {
                "secid": "90.BK0816",
                "fields": "f57,f58,f43,f169,f170"
            }
            async with httpx.AsyncClient(timeout=8.0, trust_env=False, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                res_data, status, err_msg = self._safe_parse_json(resp)

            if status == DataStatus.EMPTY:
                return DataResult(
                    data=None,
                    quality=DataQuality.UNAVAILABLE,
                    status=DataStatus.EMPTY,
                    error_code=ProviderErrorCode.EMPTY_PAYLOAD,
                    provider=self.name,
                    error_message=err_msg
                )
            if status == DataStatus.ERROR or res_data is None:
                return DataResult(
                    data=None,
                    quality=DataQuality.UNAVAILABLE,
                    status=DataStatus.ERROR,
                    error_code=ProviderErrorCode.HTTP_ERROR,
                    provider=self.name,
                    error_message=err_msg
                )

            d = res_data.get("data")
            if d and d.get("f170") is not None:
                pct_change = round(float(d.get("f170")) / 100.0, 2)
                return DataResult(
                    data={
                        "symbol": "BK0816",
                        "name": d.get("f58", "昨日连板"),
                        "pct_change": pct_change
                    },
                    quality=DataQuality.FULL,
                    status=DataStatus.AVAILABLE,
                    provider=self.name
                )

            # 若东财 BK0816 不可用，自动通过 Sina 批量查询高标样本自主计算承接均值
            try:
                from .sina import SinaProvider
                sina = SinaProvider()
                q_res = await sina.get_stock_quotes(["sh600633", "sz002829", "sz000801", "sh600576", "sz000957"])
                if q_res.data:
                    valid_pcts = [float(s.get("pct_change", 0.0)) for s in q_res.data if s.get("pct_change") is not None]
                    if valid_pcts:
                        avg_pct = round(sum(valid_pcts) / len(valid_pcts), 2)
                        return DataResult(
                            data={
                                "symbol": "HIGH_TIER_COMPOSITE",
                                "name": "高位连板承接(自主计算)",
                                "pct_change": avg_pct
                            },
                            quality=DataQuality.FULL,
                            status=DataStatus.AVAILABLE,
                            provider="sina_composite_calc"
                        )
            except Exception as fe:
                logger.warning(f"High tier performance failover failed: {fe}")

            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.EMPTY,
                error_code=ProviderErrorCode.EMPTY_PAYLOAD,
                provider=self.name,
                error_message="High tier performance not available from provider"
            )
        except Exception as e:
            logger.warning(f"Eastmoney get_high_tier_performance failed ({e}), attempting Sina fallback...")
            try:
                from .sina import SinaProvider
                sina = SinaProvider()
                q_res = await sina.get_stock_quotes(["sh600633", "sz002829", "sz000801", "sh600576", "sz000957"])
                if q_res.data:
                    valid_pcts = [float(s.get("pct_change", 0.0)) for s in q_res.data if s.get("pct_change") is not None]
                    if valid_pcts:
                        avg_pct = round(sum(valid_pcts) / len(valid_pcts), 2)
                        return DataResult(
                            data={
                                "symbol": "HIGH_TIER_COMPOSITE",
                                "name": "高位连板承接(自主计算)",
                                "pct_change": avg_pct
                            },
                            quality=DataQuality.FULL,
                            status=DataStatus.AVAILABLE,
                            provider="sina_composite_calc"
                        )
            except Exception as fe:
                pass

            return DataResult(
                data=None,
                quality=DataQuality.FAILED,
                status=DataStatus.ERROR,
                error_code=ProviderErrorCode.CONNECTION_ERROR,
                provider=self.name,
                error_message=str(e)
            )

    async def get_top_sectors(self, limit: int = 15, sector_type: str = "industry") -> DataResult:
        """
        获取当日实时板块排行 (含成交额、主力资金净流向及领涨龙头)
        - sector_type: 'industry' (行业, fs=m:90+t:2) 或 'concept' (概念, fs=m:90+t:3)
        - 补充字段: f6 (成交额), f62 (主力净流入), f128 (领涨股名), f140 (领涨股代码), f136 (领涨股涨幅)
        """
        try:
            fs_val = "m:90+t:3+f:!50" if sector_type == "concept" else "m:90+t:2+f:!50"
            url = "https://push2delay.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": "1",
                "pz": str(limit),
                "po": "1",
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fid": "f3",
                "fs": fs_val,
                "fields": "f12,f14,f2,f3,f6,f62,f128,f140,f136"
            }
            async with httpx.AsyncClient(timeout=8.0, trust_env=False, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                res_data, status, err_msg = self._safe_parse_json(resp)

            if status == DataStatus.EMPTY:
                return DataResult(
                    data=None,
                    quality=DataQuality.UNAVAILABLE,
                    status=DataStatus.EMPTY,
                    error_code=ProviderErrorCode.EMPTY_PAYLOAD,
                    provider=self.name,
                    error_message=err_msg
                )
            if status == DataStatus.ERROR or res_data is None:
                return DataResult(
                    data=None,
                    quality=DataQuality.INVALID,
                    status=DataStatus.ERROR,
                    error_code=ProviderErrorCode.MALFORMED_PARSE,
                    provider=self.name,
                    error_message=err_msg
                )

            diff_list = res_data.get("data", {}).get("diff", [])
            sectors = []
            for item in diff_list:
                amount_raw = float(item.get("f6", 0) or 0)
                net_inflow_raw = float(item.get("f62", 0) or 0)
                leader_n = item.get("f128")
                leader_c = item.get("f140")
                leader_pct = item.get("f136")

                sectors.append({
                    "code": item.get("f12"),
                    "name": item.get("f14"),
                    "price": float(item.get("f2", 0.0) or 0.0),
                    "pct_change": float(item.get("f3", 0.0) or 0.0),
                    "amount_yi": round(amount_raw / 1e8, 2),
                    "net_inflow_yi": round(net_inflow_raw / 1e8, 2),
                    "leader_name": str(leader_n) if leader_n else None,
                    "leader_code": str(leader_c) if leader_c else None,
                    "leader_pct": float(leader_pct) if leader_pct is not None and leader_pct != "-" else None,
                })

            if not sectors:
                return DataResult(
                    data=[],
                    quality=DataQuality.PARTIAL,
                    status=DataStatus.EMPTY,
                    provider=self.name,
                    error_message="Eastmoney returned 0 sectors"
                )

            return DataResult(
                data=sectors,
                quality=DataQuality.FULL,
                status=DataStatus.AVAILABLE,
                provider=self.name
            )
        except httpx.TimeoutException as te:
            logger.warning(f"Eastmoney get_top_sectors timeout: {te}")
            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.TIMEOUT,
                error_code=ProviderErrorCode.TIMEOUT,
                provider=self.name,
                error_message=f"Eastmoney timeout (>8s): {te}"
            )
        except Exception as e:
            logger.error(f"Eastmoney get_top_sectors failed: {e}")
            return DataResult(
                data=None,
                quality=DataQuality.FAILED,
                status=DataStatus.ERROR,
                error_code=ProviderErrorCode.CONNECTION_ERROR,
                provider=self.name,
                error_message=str(e)
            )

    async def get_sector_ranking(self, sector_type: str = "industry") -> DataResult:
        """
        SectorCapability 协议标准实现：获取板块排行与主力资金流
        """
        return await self.get_top_sectors(limit=20, sector_type=sector_type)

    async def get_large_cap_turnover_cores(self, min_cap_yi: float = 1000.0, top_turnover: int = 20) -> DataResult:
        """
        获取核心容量中军 (总市值 >= min_cap_yi 且成交额排名前列，排除 ST/*ST/退市标的)
        """
        try:
            url = "https://push2delay.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": "1",
                "pz": "60",
                "po": "1",
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fid": "f6",  # 按成交额倒序
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f12,f14,f2,f3,f6,f20"
            }
            async with httpx.AsyncClient(timeout=8.0, trust_env=False, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                res_data, status, err_msg = self._safe_parse_json(resp)

            if status == DataStatus.EMPTY:
                return DataResult(
                    data=None,
                    quality=DataQuality.UNAVAILABLE,
                    status=DataStatus.EMPTY,
                    error_code=ProviderErrorCode.EMPTY_PAYLOAD,
                    provider=self.name,
                    error_message=err_msg
                )
            if status == DataStatus.ERROR or res_data is None:
                return DataResult(
                    data=None,
                    quality=DataQuality.INVALID,
                    status=DataStatus.ERROR,
                    error_code=ProviderErrorCode.MALFORMED_PARSE,
                    provider=self.name,
                    error_message=err_msg
                )

            diff_list = res_data.get("data", {}).get("diff", [])
            cores = []
            for item in diff_list:
                name = str(item.get("f14", "")).strip()
                upper_name = name.upper()
                if "ST" in upper_name or "退" in upper_name:
                    continue

                market_cap_yuan = float(item.get("f20") or 0.0)
                market_cap_yi = round(market_cap_yuan / 1e8, 2)
                amount_yuan = float(item.get("f6") or 0.0)
                amount_yi = round(amount_yuan / 1e8, 2)

                if market_cap_yi >= min_cap_yi:
                    cores.append({
                        "symbol": item.get("f12"),
                        "name": name,
                        "price": float(item.get("f2") or 0.0),
                        "pct_change": float(item.get("f3") or 0.0),
                        "amount_yi": amount_yi,
                        "market_cap_yi": market_cap_yi
                    })
                    if len(cores) >= top_turnover:
                        break

            return DataResult(
                data=cores,
                quality=DataQuality.FULL if cores else DataQuality.PARTIAL,
                status=DataStatus.AVAILABLE if cores else DataStatus.EMPTY,
                provider=self.name
            )
        except httpx.TimeoutException as te:
            logger.warning(f"Eastmoney get_large_cap_turnover_cores timeout: {te}")
            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.TIMEOUT,
                error_code=ProviderErrorCode.TIMEOUT,
                provider=self.name,
                error_message=f"Eastmoney timeout (>8s): {te}"
            )
        except Exception as e:
            logger.error(f"Eastmoney get_large_cap_turnover_cores failed: {e}")
            return DataResult(
                data=None,
                quality=DataQuality.FAILED,
                status=DataStatus.ERROR,
                error_code=ProviderErrorCode.CONNECTION_ERROR,
                provider=self.name,
                error_message=str(e)
            )

    async def search_security(self, query: str, limit: int = 10) -> DataResult:
        """
        A股证券代码/名称/拼音前缀模糊搜索 (支持6位代码、中文名称、首字母拼音)
        """
        if not query or not str(query).strip():
            return DataResult(data=[], quality=DataQuality.FULL, status=DataStatus.AVAILABLE, provider=self.name)

        q = str(query).strip()
        try:
            url = f"https://searchapi.eastmoney.com/api/suggest/get?type=14&token=D43BF722C8E33BDC906FB84D85E326E8&input={urllib.parse.quote(q)}"
            async with httpx.AsyncClient(timeout=5.0, trust_env=False, follow_redirects=True) as client:
                resp = await client.get(url, headers=self.HEADERS)
                data, status, err_msg = self._safe_parse_json(resp)

            if status != DataStatus.AVAILABLE or data is None:
                return DataResult(
                    data=[],
                    quality=DataQuality.UNAVAILABLE,
                    status=status,
                    error_code=ProviderErrorCode.EMPTY_PAYLOAD if status == DataStatus.EMPTY else ProviderErrorCode.HTTP_ERROR,
                    provider=self.name,
                    error_message=err_msg
                )

            raw_items = data.get("QuotationCodeTable", {}).get("Data", []) or []
            results = []
            for item in raw_items:
                classify = item.get("Classify", "")
                code = item.get("Code", "")
                name = item.get("Name", "")
                pinyin = item.get("PinYin", "")
                if classify in ("AStock", "BSEStock") or (len(code) == 6 and code.startswith(("60", "68", "00", "30", "8", "4", "92"))):
                    results.append({
                        "code": code,
                        "name": name,
                        "pinyin": pinyin,
                        "market": item.get("SecurityTypeName", "")
                    })
                    if len(results) >= limit:
                        break

            return DataResult(
                data=results,
                quality=DataQuality.FULL,
                status=DataStatus.AVAILABLE if results else DataStatus.EMPTY,
                provider=self.name
            )
        except httpx.TimeoutException as te:
            logger.warning(f"Eastmoney search_security timeout for '{q}': {te}")
            return DataResult(
                data=[],
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.TIMEOUT,
                error_code=ProviderErrorCode.TIMEOUT,
                provider=self.name,
                error_message=f"Eastmoney timeout (>5s): {te}"
            )
        except Exception as e:
            logger.warning(f"Eastmoney search_security failed for '{q}': {e}")
            return DataResult(
                data=[],
                quality=DataQuality.FAILED,
                status=DataStatus.ERROR,
                error_code=ProviderErrorCode.CONNECTION_ERROR,
                provider=self.name,
                error_message=str(e)
            )

    async def get_price_anomaly(self, page_size: int = 200, page_no: int = 1) -> DataResult:
        """
        获取交易所严重异常波动监管异动事实 (Wave 1: em_price_anomaly)
        数据源：Eastmoney dycalchis.eastmoney.com/price-anomaly/list
        返回：规范化 MarketAnomalyFact 列表字典
        特性：
        1. 幂等 Canonical Fact ID: ANOM:{trade_date}:{symbol}:R{rule_id}
        2. 显式 Provenance: EASTMONEY_COMPUTED_RULE_MATCH (DERIVED_COMMERCIAL_MATCH)
        3. 纠偏科创板 s=5 (STAR)
        4. 12 规则代码严密映射与未知规则优雅降级
        """
        try:
            url = "https://dycalchis.eastmoney.com/price-anomaly/list"
            params = {
                "team": "h5",
                "product": "EastMoney",
                "client": "WAP",
                "version": "9001",
                "name": "WAP",
                "user": "123",
                "pageSize": str(page_size),
                "pageNo": str(page_no),
            }
            headers = {
                **self.HEADERS,
                "Referer": "https://vipmoney.eastmoney.com/",
            }
            async with httpx.AsyncClient(timeout=8.0, trust_env=False, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=headers)
                raw_json, status, err_msg = self._safe_parse_json(resp)

            if status != DataStatus.AVAILABLE or raw_json is None:
                return DataResult(
                    data=[],
                    quality=DataQuality.UNAVAILABLE,
                    status=status,
                    error_code=ProviderErrorCode.EMPTY_PAYLOAD if status == DataStatus.EMPTY else ProviderErrorCode.HTTP_ERROR,
                    provider=self.name,
                    error_message=err_msg,
                )

            # 校验业务响应码 (0 为成功)
            if raw_json.get("result") != 0:
                msg = raw_json.get("message") or raw_json.get("msg") or f"Eastmoney error code: {raw_json.get('result')}"
                return DataResult(
                    data=[],
                    quality=DataQuality.UNAVAILABLE,
                    status=DataStatus.EMPTY,
                    error_code=ProviderErrorCode.EMPTY_PAYLOAD,
                    provider=self.name,
                    error_message=msg,
                )

            # 兼容 root.date 或 data.date
            trade_date_raw = raw_json.get("date")
            raw_data_field = raw_json.get("data")
            if isinstance(raw_data_field, list):
                raw_list = raw_data_field
            elif isinstance(raw_data_field, dict):
                raw_list = raw_data_field.get("list", []) or []
                if not trade_date_raw:
                    trade_date_raw = raw_data_field.get("date")
            else:
                raw_list = []

            trade_date = str(trade_date_raw or "")
            facts: List[Dict[str, Any]] = []
            for item in raw_list:
                symbol = str(item.get("c", "")).strip()
                name = str(item.get("n", "")).strip()
                if not symbol:
                    continue

                # 交易所判定: 1 -> SH, 0 -> SZ / BJ
                raw_m = item.get("m")
                if raw_m == 1 or symbol.startswith(("6", "9", "5")):
                    exchange = "SH"
                elif symbol.startswith(("8", "4", "92")):
                    exchange = "BJ"
                else:
                    exchange = "SZ"

                # 板块判定 (关键: 修复 s=5 为 STAR 科创板)
                raw_s = item.get("s")
                if raw_s == 5 or symbol.startswith("688"):
                    board_type = "STAR"
                elif raw_s == 4 or symbol.startswith("30"):
                    board_type = "GEM"
                elif raw_s == 8 or symbol.startswith(("8", "4", "92")):
                    board_type = "BSE"
                elif raw_s == 1:
                    board_type = "MAIN"
                else:
                    if symbol.startswith("688"):
                        board_type = "STAR"
                    elif symbol.startswith("30"):
                        board_type = "GEM"
                    elif symbol.startswith(("8", "4", "92")):
                        board_type = "BSE"
                    else:
                        board_type = "MAIN"

                rule_id = int(item.get("e", 0))
                dev_val = item.get("x")
                deviation_pct = float(dev_val) if dev_val is not None else None
                win_val = item.get("d")
                window_days = int(win_val) if win_val is not None else None
                day_chg = item.get("a")
                day_change_pct = float(day_chg) if day_chg is not None else None
                status_flag = int(item.get("o", 0))

                fact = MarketAnomalyFact.create(
                    trade_date=trade_date,
                    symbol=symbol,
                    name=name,
                    exchange=exchange,
                    board_type=board_type,
                    rule_id=rule_id,
                    deviation_pct=deviation_pct,
                    window_days=window_days,
                    day_change_pct=day_change_pct,
                    status_flag=status_flag,
                )
                facts.append(fact.to_dict())

            return DataResult(
                data=facts,
                quality=DataQuality.FULL if facts else DataQuality.FULL,
                status=DataStatus.AVAILABLE if facts else DataStatus.EMPTY,
                provider=self.name,
            )
        except httpx.TimeoutException as te:
            logger.warning(f"Eastmoney get_price_anomaly timeout: {te}")
            return DataResult(
                data=[],
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.TIMEOUT,
                error_code=ProviderErrorCode.TIMEOUT,
                provider=self.name,
                error_message=f"Eastmoney price anomaly timeout (>8s): {te}",
            )
        except Exception as e:
            logger.warning(f"Eastmoney get_price_anomaly failed: {e}")
            return DataResult(
                data=[],
                quality=DataQuality.FAILED,
                status=DataStatus.ERROR,
                error_code=ProviderErrorCode.CONNECTION_ERROR,
                provider=self.name,
                error_message=str(e),
            )

    async def get_concept_blocks(self, code: str) -> DataResult:
        """
        获取标的归属的三维板块映射集 (Wave 1: eastmoney_concept_blocks)
        数据源：Eastmoney push2.eastmoney.com/api/qt/slist/get
        执行：
        1. 代码规整与市场代码判定 (SH=1, SZ/BJ=0)
        2. BlockRegistry 三维分类打标 (INDUSTRY / CONCEPT / REGION)
        3. 机械统计噪音清洗 (过滤 昨日连板、富时罗素等)
        4. 幂等 Canonical Fact ID: BLOCK_MAP:{symbol}:{block_code}
        """
        if not code or not str(code).strip():
            return DataResult(data=[], quality=DataQuality.FULL, status=DataStatus.AVAILABLE, provider=self.name)

        clean_code = str(code).strip().lower()
        if clean_code.startswith(("sh", "sz", "bj")):
            prefix = clean_code[:2]
            clean_code = clean_code[2:]
            market_id = "1" if prefix == "sh" else "0"
        elif "." in clean_code:
            parts = clean_code.split(".", 1)
            if parts[0] in ("0", "1"):
                market_id = parts[0]
                clean_code = parts[1]
            else:
                clean_code = parts[0]
                market_id = "1" if clean_code.startswith(("6", "9", "5")) else "0"
        else:
            market_id = "1" if clean_code.startswith(("6", "9", "5")) else "0"

        secid = f"{market_id}.{clean_code}"

        for attempt in range(3):
            try:
                url = "https://push2.eastmoney.com/api/qt/slist/get"
                params = {
                    "fltt": "2",
                    "invt": "2",
                    "secid": secid,
                    "spt": "3",
                    "pi": "0",
                    "pz": "200",
                    "po": "1",
                    "fields": "f12,f14,f3,f128,f140,f141",
                }
                async with httpx.AsyncClient(timeout=12.0, trust_env=False, follow_redirects=True) as client:
                    resp = await client.get(url, params=params, headers=self.HEADERS)
                    raw_json, status, err_msg = self._safe_parse_json(resp)

                if status == DataStatus.AVAILABLE and raw_json is not None:
                    break
                if attempt == 2:
                    return DataResult(
                        data=[],
                        quality=DataQuality.UNAVAILABLE,
                        status=status,
                        error_code=ProviderErrorCode.EMPTY_PAYLOAD if status == DataStatus.EMPTY else ProviderErrorCode.HTTP_ERROR,
                        provider=self.name,
                        error_message=err_msg,
                    )
                await asyncio.sleep(0.3)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                if attempt == 2:
                    logger.warning(f"Eastmoney get_concept_blocks timeout for '{code}': {e}")
                    return DataResult(
                        data=[],
                        quality=DataQuality.UNAVAILABLE,
                        status=DataStatus.TIMEOUT,
                        error_code=ProviderErrorCode.TIMEOUT,
                        provider=self.name,
                        error_message=f"Eastmoney concept blocks timeout (>12s): {e}",
                    )
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"Eastmoney get_concept_blocks failed for '{code}': {e}")
                return DataResult(
                    data=[],
                    quality=DataQuality.FAILED,
                    status=DataStatus.ERROR,
                    error_code=ProviderErrorCode.CONNECTION_ERROR,
                    provider=self.name,
                    error_message=str(e),
                )

        if not raw_json:
            return DataResult(
                data=[],
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.EMPTY,
                error_code=ProviderErrorCode.EMPTY_PAYLOAD,
                provider=self.name,
                error_message="Empty raw json after retries",
            )

        data_obj = raw_json.get("data") or {}
        diff_obj = data_obj.get("diff", [])
        if isinstance(diff_obj, dict):
            raw_items = list(diff_obj.values())
        elif isinstance(diff_obj, list):
            raw_items = diff_obj
        else:
            raw_items = []

        facts: List[Dict[str, Any]] = []
        for item in raw_items:
            b_code = str(item.get("f12", "")).strip()
            b_name = str(item.get("f14", "")).strip()
            if not b_name:
                continue

            category = BlockRegistry.categorize(b_name, b_code)
            if category == "FILTERED_NOISE":
                continue

            f3_val = item.get("f3")
            chg_pct = float(f3_val) if f3_val is not None and f3_val != "-" else None
            leader_n = item.get("f128")
            leader_s = item.get("f140")

            fact = BlockMappingFact.create(
                symbol=clean_code,
                block_code=b_code,
                block_name=b_name,
                category=category,
                block_change_pct=chg_pct,
                leader_name=str(leader_n) if leader_n else None,
                leader_symbol=str(leader_s) if leader_s else None,
            )
            facts.append(fact.to_dict())

        return DataResult(
            data=facts,
            quality=DataQuality.FULL if facts else DataQuality.FULL,
            status=DataStatus.AVAILABLE if facts else DataStatus.EMPTY,
            provider=self.name,
        )

    async def get_stock_trends(self, codes: list[str]) -> DataResult:
        """
        获取指定股票/板块的分时走势分钟数据 (Intraday Minute Trends)
        支持个股 (002696, 600000) 与概念板块 (BK0480)
        """
        if not codes:
            return DataResult(
                data=[],
                quality=DataQuality.FULL,
                status=DataStatus.AVAILABLE,
                provider=self.name,
            )

        results: List[Dict[str, Any]] = []

        async def _fetch_single_trend(client: httpx.AsyncClient, code_str: str) -> Optional[Dict[str, Any]]:
            clean_code = str(code_str).strip()
            if not clean_code:
                return None

            if "." in clean_code:
                secid = clean_code
                pure_code = clean_code.split(".")[-1]
            elif clean_code.upper().startswith("BK"):
                secid = f"90.{clean_code.upper()}"
                pure_code = clean_code.upper()
            elif clean_code.startswith(("60", "68", "900")):
                secid = f"1.{clean_code}"
                pure_code = clean_code
            else:
                secid = f"0.{clean_code}"
                pure_code = clean_code

            url = "https://push2delay.eastmoney.com/api/qt/stock/trends2/get"
            params = {
                "secid": secid,
                "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
                "iscr": "0",
            }

            try:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                if resp.status_code != 200:
                    return None
                data_json = resp.json() or {}
                data = data_json.get("data")
                if not data:
                    return None

                pre_price = float(data.get("prePrice") or data.get("preClose") or 0.0)
                raw_trends = data.get("trends") or []
                name = str(data.get("name") or pure_code)

                trend_points: List[Dict[str, Any]] = []
                for row in raw_trends:
                    parts = row.split(",")
                    if len(parts) >= 8:
                        t_full = parts[0].strip()
                        t_hhmm = t_full.split(" ")[-1] if " " in t_full else t_full
                        c_price = float(parts[2])
                        pct = round((c_price - pre_price) / pre_price * 100.0, 2) if pre_price > 0 else 0.0
                        trend_points.append({
                            "time": t_hhmm,
                            "price": c_price,
                            "pct_change": pct,
                            "avg_price": float(parts[7]),
                            "volume": int(float(parts[5])),
                            "amount": float(parts[6]),
                        })

                return {
                    "code": pure_code,
                    "name": name,
                    "pre_close": pre_price,
                    "trends": trend_points,
                }
            except Exception as e:
                logger.warning(f"Failed to fetch stock trend for {code_str}: {e}")
                return None

        try:
            async with httpx.AsyncClient(
                limits=httpx.Limits(max_keepalive_connections=15, max_connections=20),
                timeout=6.0
            ) as client:
                tasks = [_fetch_single_trend(client, c) for c in codes]
                fetched = await asyncio.gather(*tasks, return_exceptions=True)
                for item in fetched:
                    if isinstance(item, dict) and item.get("trends"):
                        results.append(item)
        except Exception as e:
            logger.error(f"Eastmoney get_stock_trends batch failed: {e}")

        return DataResult(
            data=results,
            quality=DataQuality.FULL if results else DataQuality.UNAVAILABLE,
            status=DataStatus.AVAILABLE if results else DataStatus.EMPTY,
            provider=self.name,
        )


