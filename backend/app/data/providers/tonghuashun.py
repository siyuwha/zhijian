import asyncio
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Referer": "https://data.eastmoney.com/",
        "Connection": "close",
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    def __init__(self):
        super().__init__(
            name="tonghuashun_eastmoney",
            implementation_status="部分接入",
            connectivity_verified="待验证",
            schema_verified="待验证",
            semantic_verified="待验证",
            production_eligible="暂不准入",
        )

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
                zt_url = "https://push2ex.eastmoney.com/getTopicZTPool"
                dt_url = "https://push2ex.eastmoney.com/getTopicDTPool"
                zb_url = "https://push2ex.eastmoney.com/getTopicZBPool"

                # 并发抓取涨停、跌停、炸板 3 个微观情绪池，耗时从 5.3s 降至 1.8s
                zt_task = client.get(zt_url, params={**base_params, "sort": "fbt:asc"}, headers=self.HEADERS)
                dt_task = client.get(dt_url, params={**base_params, "sort": "fund:asc"}, headers=self.HEADERS)
                zb_task = client.get(zb_url, params={**base_params, "sort": "fbt:asc"}, headers=self.HEADERS)

                resp_zt, resp_dt, resp_zb = await asyncio.gather(zt_task, dt_task, zb_task)
                res_zt = resp_zt.json() if resp_zt.status_code == 200 else {}
                res_dt = resp_dt.json() if resp_dt.status_code == 200 else {}
                res_zb = resp_zb.json() if resp_zb.status_code == 200 else {}

            # 解析涨停池
            pool_list = res_zt.get("data", {}).get("pool", []) if res_zt.get("data") else []
            total_zt_count = res_zt.get("data", {}).get("tc", len(pool_list)) if res_zt.get("data") else 0

            # 解析跌停池
            dt_pool = res_dt.get("data", {}).get("pool", []) if res_dt.get("data") else []
            total_dt_count = res_dt.get("data", {}).get("tc", len(dt_pool)) if res_dt.get("data") else 0

            # 解析炸板池
            zb_pool = res_zb.get("data", {}).get("pool", []) if res_zb.get("data") else []
            total_zb_count = res_zb.get("data", {}).get("tc", len(zb_pool)) if res_zb.get("data") else 0

            # 真实炸板率计算：炸板数 / (封板数 + 炸板数)
            broken_ratio: Optional[float] = None
            if (total_zt_count + total_zb_count) > 0:
                broken_ratio = round(total_zb_count / (total_zt_count + total_zb_count), 4)

            def _fmt_time(val) -> Optional[str]:
                if val is None or val == "":
                    return None
                s = str(val).strip().zfill(6)
                if len(s) == 6 and s.isdigit():
                    return f"{s[:2]}:{s[2:4]}:{s[4:6]}"
                return str(val)

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

                fund_raw = float(entry.get("fund", 0) or 0)
                amount_raw = float(entry.get("amount", 0) or 0)
                ltsz_raw = float(entry.get("ltsz", 0) or 0)
                fbt_val = entry.get("fbt")
                lbt_val = entry.get("lbt")
                zbc_val = int(entry.get("zbc", 0) or 0)
                hs_val = float(entry.get("hs", 0) or 0)

                items.append({
                    "code": code,
                    "name": name,
                    "reason_type": raw_reason,
                    "reasons": reasons,
                    "high_days": f"{lbc}天{lbc}板" if lbc > 1 else "首板",
                    "lbc": lbc,
                    "fbt": fbt_val,
                    "fbt_str": _fmt_time(fbt_val),
                    "lbt": lbt_val,
                    "lbt_str": _fmt_time(lbt_val),
                    "limit_up_type": "FIRST_LIMIT" if lbc == 1 else "CONTINUED",
                    "sector": entry.get("hybk", ""),
                    "fund": fund_raw,
                    "fund_wan": round(fund_raw / 1e4, 2),
                    "fund_yi": round(fund_raw / 1e8, 4),
                    "amount": amount_raw,
                    "amount_yi": round(amount_raw / 1e8, 4),
                    "turnover_ratio": round(hs_val, 2),
                    "open_count": zbc_val,
                    "ltsz_yi": round(ltsz_raw / 1e8, 2) if ltsz_raw else None,
                })

            first_limit_count = sum(1 for i in items if i["lbc"] == 1)
            continued_count = sum(1 for i in items if i["lbc"] > 1)

            # 解析跌停池标的 (大跌/核按钮风险榜)
            limit_down_items = []
            for entry in dt_pool:
                c = str(entry.get("c", ""))
                n = str(entry.get("n", ""))
                if not c:
                    continue
                p_raw = float(entry.get("p", 0) or 0)
                fund_raw = float(entry.get("fund", 0) or 0)
                amount_raw = float(entry.get("amount", 0) or 0)
                hs_raw = float(entry.get("hs", 0) or 0)
                zdp_raw = float(entry.get("zdp", 0) or 0)
                lbt_val = entry.get("lbt")
                days_val = int(entry.get("days", 1) or 1)

                limit_down_items.append({
                    "code": c,
                    "name": n,
                    "price": round(p_raw / 1000.0, 2) if p_raw else 0.0,
                    "pct_change": round(zdp_raw, 2),
                    "amount_yi": round(amount_raw / 1e8, 4),
                    "fund_wan": round(fund_raw / 1e4, 2),
                    "fund_yi": round(fund_raw / 1e8, 4),
                    "turnover_ratio": round(hs_raw, 2),
                    "lbt": lbt_val,
                    "lbt_str": _fmt_time(lbt_val),
                    "days": days_val,
                    "sector": str(entry.get("hybk", "") or ""),
                })

            # 解析炸板池标的 (日内大面榜)
            broken_limit_items = []
            for entry in zb_pool:
                c = str(entry.get("c", ""))
                n = str(entry.get("n", ""))
                if not c:
                    continue
                p_raw = float(entry.get("p", 0) or 0)
                ztp_raw = float(entry.get("ztp", 0) or 0)
                zdp_raw = float(entry.get("zdp", 0) or 0)
                amount_raw = float(entry.get("amount", 0) or 0)
                hs_raw = float(entry.get("hs", 0) or 0)
                zf_raw = float(entry.get("zf", 0) or 0)
                zbc_val = int(entry.get("zbc", 1) or 1)
                fbt_val = entry.get("fbt")

                # 回落幅度估算 (振幅与当前涨幅之差即为自高点回落幅度)
                fall_back_pct = round(zf_raw - zdp_raw, 2) if zf_raw else round(10.0 - zdp_raw, 2)

                broken_limit_items.append({
                    "code": c,
                    "name": n,
                    "price": round(p_raw / 1000.0, 2) if p_raw else 0.0,
                    "limit_up_price": round(ztp_raw / 1000.0, 2) if ztp_raw else 0.0,
                    "pct_change": round(zdp_raw, 2),
                    "fall_back_pct": fall_back_pct,
                    "amount_yi": round(amount_raw / 1e8, 4),
                    "turnover_ratio": round(hs_raw, 2),
                    "open_count": zbc_val,
                    "fbt": fbt_val,
                    "fbt_str": _fmt_time(fbt_val),
                    "amplitude": round(zf_raw, 2),
                    "sector": str(entry.get("hybk", "") or ""),
                })

            summary = {
                "total_count": total_zt_count,
                "max_height": max_height,
                "first_limit_count": first_limit_count,
                "continued_count": continued_count,
                "limit_down_count": total_dt_count,
                "broken_limit_count": total_zb_count,
                "broken_limit_ratio": broken_ratio,
                "top_reasons": sorted(reasons_counter.items(), key=lambda x: x[1], reverse=True)[:5],
                "items": items,
                "limit_down_items": limit_down_items,
                "broken_limit_items": broken_limit_items,
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
