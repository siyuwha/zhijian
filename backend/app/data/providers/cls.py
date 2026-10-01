import hashlib
import logging
import time
from typing import Optional
import httpx
from .base import BaseProvider
from ..capabilities import (
    DataQuality,
    DataResult,
    DataStatus,
    Freshness,
    NewsCapability,
    ProviderErrorCode,
)

logger = logging.getLogger(__name__)

class CLSProvider(BaseProvider, NewsCapability):
    """
    财联社 (CLS) 盘前快讯与电报适配器
    参考 TRADING_DATA_SOURCES.md:
    端点: https://www.cls.cn/v1/roll/get_roll_list
    sign 签名算法: md5(sha1(sorted_query_string))
    参数要求: app=CailianpressWeb, category='', refresh_type=1, last_time=当前时间戳
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.cls.cn/"
    }

    def __init__(self):
        super().__init__(
            name="cls",
            implementation_status="已接入",
            connectivity_verified="已验证",
            schema_verified="已验证",
            semantic_verified="已验证",
            production_eligible="准入",
        )

    async def is_available(self) -> bool:
        return True

    def _generate_sign(self, params: dict) -> str:
        """计算财联社查询签名: md5(sha1(sorted_query_string))"""
        sorted_keys = sorted(params.keys())
        query_str = "&".join(f"{k}={params[k]}" for k in sorted_keys)
        sha1_str = hashlib.sha1(query_str.encode("utf-8")).hexdigest()
        md5_sign = hashlib.md5(sha1_str.encode("utf-8")).hexdigest()
        return md5_sign

    async def get_latest_news(self, count: int = 15) -> DataResult:
        try:
            params = {
                "app": "CailianpressWeb",
                "category": "",
                "last_time": str(int(time.time())),
                "os": "web",
                "refresh_type": "1",
                "rn": str(count),
                "sv": "7.7.5"
            }
            params["sign"] = self._generate_sign(params)

            url = "https://www.cls.cn/v1/roll/get_roll_list"
            async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                if resp.status_code != 200:
                    return DataResult(
                        data=None,
                        quality=DataQuality.UNAVAILABLE,
                        status=DataStatus.ERROR,
                        error_code=ProviderErrorCode.HTTP_ERROR,
                        provider=self.name,
                        error_message=f"CLS HTTP {resp.status_code}"
                    )

                text = resp.text.strip()
                if not text:
                    return DataResult(
                        data=None,
                        quality=DataQuality.UNAVAILABLE,
                        status=DataStatus.EMPTY,
                        error_code=ProviderErrorCode.EMPTY_PAYLOAD,
                        provider=self.name,
                        error_message="CLS returned empty payload"
                    )

                try:
                    data = resp.json()
                except Exception as e:
                    return DataResult(
                        data=None,
                        quality=DataQuality.INVALID,
                        status=DataStatus.ERROR,
                        error_code=ProviderErrorCode.MALFORMED_PARSE,
                        provider=self.name,
                        error_message=f"CLS JSON parse error: {e}"
                    )

            if data.get("errno") != 0:
                err_msg = data.get("msg", "Unknown error")
                return DataResult(
                    data=None,
                    quality=DataQuality.UNAVAILABLE,
                    status=DataStatus.ERROR,
                    error_code=ProviderErrorCode.HTTP_ERROR,
                    provider=self.name,
                    error_message=f"CLS error code {data.get('errno')}: {err_msg}"
                )

            roll_data = data.get("data", {}).get("roll_data", [])
            items = []
            for entry in roll_data[:count]:
                content = entry.get("content", "")
                title = entry.get("title") or (content[:40] if content else "")
                items.append({
                    "title": title,
                    "brief": content,
                    "publish_time": str(entry.get("ctime")),
                    "source": "cls"
                })

            if not items:
                return DataResult(
                    data=[],
                    quality=DataQuality.PARTIAL,
                    status=DataStatus.EMPTY,
                    provider=self.name,
                    error_message="CLS returned 0 roll data items"
                )

            return DataResult(
                data=items,
                quality=DataQuality.FULL,
                status=DataStatus.AVAILABLE,
                freshness=Freshness.REALTIME,
                provider=self.name
            )
        except httpx.TimeoutException as te:
            logger.warning(f"CLS get_latest_news timeout: {te}")
            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.TIMEOUT,
                error_code=ProviderErrorCode.TIMEOUT,
                provider=self.name,
                error_message=f"CLS timeout (>8s): {te}"
            )
        except Exception as e:
            logger.error(f"CLS get_latest_news failed: {e}")
            return DataResult(
                data=None,
                quality=DataQuality.FAILED,
                status=DataStatus.ERROR,
                error_code=ProviderErrorCode.CONNECTION_ERROR,
                provider=self.name,
                error_message=str(e)
            )
