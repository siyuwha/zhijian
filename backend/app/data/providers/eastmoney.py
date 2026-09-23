import logging
from typing import Optional
import httpx
from .base import BaseProvider
from ..capabilities import (
    DataQuality,
    DataResult,
    MarketBreadthCapability,
    MicroCapCapability,
    HighTierPerformanceCapability,
)

logger = logging.getLogger(__name__)

class EastmoneyProvider(BaseProvider, MarketBreadthCapability, MicroCapCapability, HighTierPerformanceCapability):
    """
    东方财富全市场广度、风格及高标数据适配器
    实现：
    - MarketBreadthCapability (全市场上涨/下跌/平盘家数，覆盖沪深北全市场)
    - MicroCapCapability (微盘股板块 90.BK1158 真实行情)
    - HighTierPerformanceCapability (昨日连板板块承接表现)
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://quote.eastmoney.com/"
    }

    def __init__(self):
        super().__init__(name="eastmoney")

    async def is_available(self) -> bool:
        return True

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

            async with httpx.AsyncClient(timeout=10.0, trust_env=False, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                res_data = resp.json()

            diff_list = res_data.get("data", {}).get("diff", [])
            if not diff_list:
                return DataResult(
                    data=None,
                    quality=DataQuality.INVALID,
                    provider=self.name,
                    error_message="Eastmoney market breadth returned empty data"
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
                provider=self.name
            )
        except Exception as e:
            logger.error(f"Eastmoney get_market_breadth failed: {e}")
            return DataResult(data=None, quality=DataQuality.FAILED, provider=self.name, error_message=str(e))

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
            async with httpx.AsyncClient(timeout=10.0, trust_env=False, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                if resp.status_code == 200:
                    d = resp.json().get("data")
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
                            provider=self.name
                        )

            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                provider=self.name,
                error_message="Micro cap quote not available"
            )
        except Exception as e:
            logger.error(f"Eastmoney get_micro_cap_quote failed: {e}")
            return DataResult(data=None, quality=DataQuality.FAILED, provider=self.name, error_message=str(e))

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
            async with httpx.AsyncClient(timeout=10.0, trust_env=False, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                if resp.status_code == 200 and "data" in resp.text:
                    try:
                        d = resp.json().get("data")
                        if d and d.get("f170") is not None:
                            pct_change = round(float(d.get("f170")) / 100.0, 2)
                            return DataResult(
                                data={
                                    "symbol": "BK0816",
                                    "name": d.get("f58", "昨日连板"),
                                    "pct_change": pct_change
                                },
                                quality=DataQuality.FULL,
                                provider=self.name
                            )
                    except Exception:
                        pass

            # 若不可得，返回 UNAVAILABLE (D3 中该指标为 OPTIONAL，将正常重归一化，绝不捏造假数据)
            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                provider=self.name,
                error_message="High tier performance not available from provider"
            )
        except Exception as e:
            logger.error(f"Eastmoney get_high_tier_performance failed: {e}")
            return DataResult(data=None, quality=DataQuality.FAILED, provider=self.name, error_message=str(e))
