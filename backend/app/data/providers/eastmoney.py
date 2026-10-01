import json
import logging
import urllib.parse
from typing import Optional, List, Dict, Any, Tuple
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
)

logger = logging.getLogger(__name__)

class EastmoneyProvider(BaseProvider, MarketBreadthCapability, MicroCapCapability, HighTierPerformanceCapability, SecuritySearchCapability):
    """
    东方财富全市场广度、风格及高标数据适配器
    满足 P0-2 生产级防爆与状态明确化要求：
    1. 空响应 ≠ JSON 错误 ≠ 有效事实
    2. 全链路防御非交易时段空字符串与 4xx/5xx 响应，杜绝 JSONDecodeError 抛出
    3. 返回结果严格区分 AVAILABLE / EMPTY / STALE / TIMEOUT / ERROR 状态
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://quote.eastmoney.com/"
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
        """
        try:
            url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
            params = {
                "fltt": "2",
                "secids": "1.000001,0.399001,0.899050",
                "fields": "f12,f13,f14,f104,f105,f106"
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
            if not diff_list:
                return DataResult(
                    data=None,
                    quality=DataQuality.UNAVAILABLE,
                    status=DataStatus.EMPTY,
                    error_code=ProviderErrorCode.EMPTY_PAYLOAD,
                    provider=self.name,
                    error_message="Eastmoney market breadth returned empty diff list"
                )

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
        except httpx.TimeoutException as te:
            logger.warning(f"Eastmoney get_market_breadth timeout: {te}")
            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.TIMEOUT,
                error_code=ProviderErrorCode.TIMEOUT,
                provider=self.name,
                error_message=f"Eastmoney timeout (>8s): {te}"
            )
        except Exception as e:
            logger.error(f"Eastmoney get_market_breadth failed: {e}")
            return DataResult(
                data=None,
                quality=DataQuality.FAILED,
                status=DataStatus.ERROR,
                error_code=ProviderErrorCode.CONNECTION_ERROR,
                provider=self.name,
                error_message=str(e)
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

            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.EMPTY,
                error_code=ProviderErrorCode.EMPTY_PAYLOAD,
                provider=self.name,
                error_message="Micro cap quote not available"
            )
        except httpx.TimeoutException as te:
            logger.warning(f"Eastmoney get_micro_cap_quote timeout: {te}")
            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.TIMEOUT,
                error_code=ProviderErrorCode.TIMEOUT,
                provider=self.name,
                error_message=f"Eastmoney timeout (>8s): {te}"
            )
        except Exception as e:
            logger.error(f"Eastmoney get_micro_cap_quote failed: {e}")
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

            # 若不可得，返回 UNAVAILABLE (D3 中该指标为 OPTIONAL，将正常重归一化，绝不捏造假数据)
            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.EMPTY,
                error_code=ProviderErrorCode.EMPTY_PAYLOAD,
                provider=self.name,
                error_message="High tier performance not available from provider"
            )
        except httpx.TimeoutException as te:
            logger.warning(f"Eastmoney get_high_tier_performance timeout: {te}")
            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.TIMEOUT,
                error_code=ProviderErrorCode.TIMEOUT,
                provider=self.name,
                error_message=f"Eastmoney timeout (>8s): {te}"
            )
        except Exception as e:
            logger.error(f"Eastmoney get_high_tier_performance failed: {e}")
            return DataResult(
                data=None,
                quality=DataQuality.FAILED,
                status=DataStatus.ERROR,
                error_code=ProviderErrorCode.CONNECTION_ERROR,
                provider=self.name,
                error_message=str(e)
            )

    async def get_top_sectors(self, limit: int = 3) -> DataResult:
        """
        获取当日实时涨幅排名前 N 的行业板块
        """
        try:
            url = "https://push2delay.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": "1",
                "pz": str(limit),
                "po": "1",
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fid": "f3",
                "fs": "m:90+t:2+f:!50",
                "fields": "f12,f14,f2,f3"
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
                sectors.append({
                    "code": item.get("f12"),
                    "name": item.get("f14"),
                    "pct_change": float(item.get("f3", 0.0))
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
