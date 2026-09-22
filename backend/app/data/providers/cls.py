import hashlib
import logging
import time
from typing import Optional
import httpx
from .base import BaseProvider
from ..capabilities import DataQuality, DataResult, NewsCapability

logger = logging.getLogger(__name__)

class CLSProvider(BaseProvider, NewsCapability):
    """
    财联社 (CLS) 盘前快讯与电报适配器
    参考 TRADING_DATA_SOURCES.md:
    sign 签名算法: md5(sha1(sorted_query_string))
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.cls.cn/"
    }

    def __init__(self):
        super().__init__(name="cls")

    async def is_available(self) -> bool:
        return True

    def _generate_sign(self, params: dict) -> str:
        """计算财联社查询签名"""
        sorted_keys = sorted(params.keys())
        query_str = "&".join(f"{k}={params[k]}" for k in sorted_keys)
        sha1_str = hashlib.sha1(query_str.encode("utf-8")).hexdigest()
        md5_sign = hashlib.md5(sha1_str.encode("utf-8")).hexdigest()
        return md5_sign

    async def get_latest_news(self, count: int = 15) -> DataResult:
        try:
            params = {
                "app": "CxhWeb",
                "category": "watch",
                "os": "web",
                "rn": str(count),
                "sv": "7.7.5"
            }
            params["sign"] = self._generate_sign(params)

            url = "https://www.cls.cn/api/v1/roll/get_roll_list"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                data = resp.json()

            roll_data = data.get("data", {}).get("roll_data", [])
            items = []
            for entry in roll_data[:count]:
                items.append({
                    "title": entry.get("title") or entry.get("content", "")[:30],
                    "brief": entry.get("content"),
                    "publish_time": str(entry.get("ctime")),
                    "source": "cls"
                })

            return DataResult(
                data=items,
                quality=DataQuality.FULL if items else DataQuality.PARTIAL,
                provider=self.name
            )
        except Exception as e:
            logger.error(f"CLS get_latest_news failed: {e}")
            return DataResult(data=None, quality=DataQuality.FAILED, provider=self.name, error_message=str(e))
