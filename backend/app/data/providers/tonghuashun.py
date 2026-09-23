import logging
from datetime import datetime
from typing import Optional
import httpx
from .base import BaseProvider
from ..capabilities import DataQuality, DataResult, LimitUpCapability

logger = logging.getLogger(__name__)

class TongHuaShunProvider(BaseProvider, LimitUpCapability):
    """
    同花顺 / 东方财富涨停池适配器
    提取短线连板与情绪数据：
    - 涨停池明细与题材归因 (reason_type)
    - 连板高度 (max_height)
    - 跌停池统计 (limit_down_count)
    - 炸板池统计与真实炸板率 (broken_limit_ratio)
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
        """获取指定交易日或最新涨停、跌停与炸板综合情绪数据"""
        try:
            # 格式化日期为 YYYYMMDD，接口强制要求该参数
            if date:
                date_param = date.replace("-", "")
            else:
                date_param = datetime.now().strftime("%Y%m%d")

            ut_token = "7eea3edcaed734bea9cbfc24409ed989"
            base_params = {
                "ut": ut_token,
                "dpt": "wz.ztzt",
                "Pageindex": "0",
                "pagesize": "200",
                "date": date_param
            }

            async with httpx.AsyncClient(timeout=10.0, trust_env=False, follow_redirects=True) as client:
                # 1. 抓取涨停池
                zt_url = "https://push2ex.eastmoney.com/getTopicZTPool"
                zt_params = {**base_params, "sort": "fbt:asc"}
                resp_zt = await client.get(zt_url, params=zt_params, headers=self.HEADERS)
                res_zt = resp_zt.json()

                # 2. 抓取跌停池
                dt_url = "https://push2ex.eastmoney.com/getTopicDTPool"
                dt_params = {**base_params, "sort": "fund:asc"}
                resp_dt = await client.get(dt_url, params=dt_params, headers=self.HEADERS)
                res_dt = resp_dt.json()

                # 3. 抓取炸板池
                zb_url = "https://push2ex.eastmoney.com/getTopicZBPool"
                zb_params = {**base_params, "sort": "fbt:asc"}
                resp_zb = await client.get(zb_url, params=zb_params, headers=self.HEADERS)
                res_zb = resp_zb.json()

            # 解析涨停池
            pool_list = res_zt.get("data", {}).get("pool", []) if res_zt.get("data") else []
            total_zt_count = res_zt.get("data", {}).get("tc", len(pool_list)) if res_zt.get("data") else 0

            # 解析跌停池
            total_dt_count = res_dt.get("data", {}).get("tc", 0) if res_dt.get("data") else 0

            # 解析炸板池
            total_zb_count = res_zb.get("data", {}).get("tc", 0) if res_zb.get("data") else 0

            # 真实炸板率计算：炸板数 / (封板数 + 炸板数)
            broken_ratio: Optional[float] = None
            if (total_zt_count + total_zb_count) > 0:
                broken_ratio = round(total_zb_count / (total_zt_count + total_zb_count), 4)

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

            first_limit_count = sum(1 for i in items if i["lbc"] == 1)
            continued_count = sum(1 for i in items if i["lbc"] > 1)

            summary = {
                "total_count": total_zt_count,
                "max_height": max_height,
                "first_limit_count": first_limit_count,
                "continued_count": continued_count,
                "limit_down_count": total_dt_count,
                "broken_limit_count": total_zb_count,
                "broken_limit_ratio": broken_ratio,
                "top_reasons": sorted(reasons_counter.items(), key=lambda x: x[1], reverse=True)[:5],
                "items": items
            }

            quality = DataQuality.FULL if (res_zt.get("data") is not None) else DataQuality.PARTIAL

            return DataResult(
                data=summary,
                quality=quality,
                provider=self.name
            )
        except Exception as e:
            logger.error(f"LimitUp get_limit_up_pool failed: {e}")
            return DataResult(data=None, quality=DataQuality.FAILED, provider=self.name, error_message=str(e))
