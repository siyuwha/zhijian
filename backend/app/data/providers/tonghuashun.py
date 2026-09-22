import logging
from typing import Optional
import httpx
from .base import BaseProvider
from ..capabilities import DataQuality, DataResult, LimitUpCapability

logger = logging.getLogger(__name__)

class TongHuaShunProvider(BaseProvider, LimitUpCapability):
    """
    同花顺 / 东方财富涨停池适配器
    提取涨停数据，包含：
    - reason_type 题材归因（按 + 拆分）
    - high_days 连板高度 (如 2连板, 3连板)
    - change_tag / limit_up_type
    """

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://data.eastmoney.com/"
    }

    def __init__(self):
        super().__init__(name="tonghuashun_eastmoney")

    async def is_available(self) -> bool:
        return True

    async def get_limit_up_pool(self, date: Optional[str] = None) -> DataResult:
        """获取指定交易日或最新涨停池"""
        try:
            # 东方财富涨停池 API (稳定公共接口)
            # date format: YYYYMMDD
            date_param = date.replace("-", "") if date else ""
            url = "https://push2ex.eastmoney.com/getTopicZTPool"
            params = {
                "ut": "7eea3edcaed734bea9cbfc24409ed989",
                "dpt": "wz.ztzt",
                "Pageindex": "0",
                "pagesize": "200",
                "sort": "fbt:asc",
                "date": date_param
            }

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params, headers=self.HEADERS)
                res_data = resp.json()

            pool_list = res_data.get("data", {}).get("pool", [])
            items = []
            reasons_counter = {}
            max_height = 0

            for entry in pool_list:
                code = str(entry.get("c", ""))
                name = str(entry.get("n", ""))
                raw_reason = str(entry.get("hybk", "")) or str(entry.get("zttj", {}).get("ct", ""))
                # 按 + 拆分题材归因
                reasons = [r.strip() for r in raw_reason.split("+") if r.strip()]
                for r in reasons:
                    reasons_counter[r] = reasons_counter.get(r, 0) + 1

                lbc = int(entry.get("lbc", 1))
                if lbc > max_height:
                    max_height = lbc

                items.append({
                    "code": code,
                    "name": name,
                    "reason_type": raw_reason,
                    "reasons": reasons,
                    "high_days": f"{lbc}天{lbc}板" if lbc > 1 else "首板",
                    "lbc": lbc,
                    "fbt": entry.get("fbt"), # 封板时间
                    "limit_up_type": "FIRST_LIMIT" if lbc == 1 else "CONTINUED",
                    "sector": entry.get("hybk", "")
                })

            summary = {
                "total_count": len(items),
                "max_height": max_height,
                "first_limit_count": sum(1 for i in items if i["lbc"] == 1),
                "continued_count": sum(1 for i in items if i["lbc"] > 1),
                "top_reasons": sorted(reasons_counter.items(), key=lambda x: x[1], reverse=True)[:5],
                "items": items
            }

            return DataResult(
                data=summary,
                quality=DataQuality.FULL if items else DataQuality.PARTIAL,
                provider=self.name
            )
        except Exception as e:
            logger.error(f"LimitUp get_limit_up_pool failed: {e}")
            return DataResult(data=None, quality=DataQuality.FAILED, provider=self.name, error_message=str(e))
