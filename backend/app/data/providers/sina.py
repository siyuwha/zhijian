import asyncio
import logging
from typing import List, Optional
import httpx
from .base import BaseProvider
from ..capabilities import (
    DataQuality,
    DataResult,
    IndexQuoteCapability,
    NewsCapability,
    OvernightCapability,
    StockQuoteCapability,
    ExternalRiskCapability,
)

logger = logging.getLogger(__name__)

class SinaProvider(BaseProvider, IndexQuoteCapability, StockQuoteCapability, OvernightCapability, NewsCapability, ExternalRiskCapability):
    """
    新浪财经数据适配器
    遵守 G1 避坑规则：
    1. 必须携带 Referer header: https://finance.sina.com.cn
    2. 批量请求每次最多10只，间隔 sleep(0.3) 避免被封
    3. 响应编码采用 GBK 解码
    4. 铁律：实时数据消费必须 price > 0
    """

    HEADERS = {
        "Referer": "https://finance.sina.com.cn",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    def __init__(self):
        super().__init__(name="sina")

    async def is_available(self) -> bool:
        return True

    async def get_index_quotes(self, codes: List[str]) -> DataResult:
        """
        获取指数行情 (如 s_sh000001, s_sz399001, s_sz399006, s_sh000688)
        """
        try:
            # 确保代码以 s_ 为前缀（简版行情）
            formatted_codes = [c if c.startswith("s_") else f"s_{c}" for c in codes]
            url = f"https://hq.sinajs.cn/list={','.join(formatted_codes)}"

            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.get(url, headers=self.HEADERS)
                content = resp.content.decode("gbk", errors="ignore")

            quotes = []
            for line in content.strip().split("\n"):
                if not line or "=" not in line:
                    continue
                var_name, val = line.split("=", 1)
                code = var_name.split("_")[-1].replace('"', '')
                val_str = val.strip().strip('";')
                if not val_str:
                    continue
                parts = val_str.split(",")
                if len(parts) >= 6:
                    # 指数名, 现价, 涨跌额, 涨跌幅, 成交量(手), 成交额(万元)
                    name = parts[0]
                    price = float(parts[1]) if len(parts) > 1 and parts[1] != "" else None
                    change = float(parts[2]) if len(parts) > 2 and parts[2] != "" else None
                    pct_change = float(parts[3]) if len(parts) > 3 and parts[3] != "" else None
                    amount = float(parts[5]) if len(parts) > 5 and parts[5] != "" else None # 万元

                    if price is not None and price > 0:
                        quotes.append({
                            "code": code,
                            "symbol": code,
                            "name": name,
                            "price": round(price, 2),
                            "change": round(change, 2) if change is not None else None,
                            "pct_change": round(pct_change, 2) if pct_change is not None else None,
                            "amount_wan": round(amount, 2) if amount is not None else None,
                        })

            return DataResult(
                data=quotes,
                quality=DataQuality.FULL if len(quotes) == len(codes) else DataQuality.PARTIAL,
                provider=self.name
            )
        except Exception as e:
            logger.error(f"Sina get_index_quotes failed: {e}")
            return DataResult(data=None, quality=DataQuality.FAILED, provider=self.name, error_message=str(e))

    async def get_stock_quotes(self, codes: List[str]) -> DataResult:
        """分批获取个股行情（每批10只，间隔0.3s）"""
        results = []
        chunk_size = 10
        chunks = [codes[i:i + chunk_size] for i in range(0, len(codes), chunk_size)]

        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                for idx, chunk in enumerate(chunks):
                    if idx > 0:
                        await asyncio.sleep(0.3)

                    url = f"https://hq.sinajs.cn/list={','.join(chunk)}"
                    resp = await client.get(url, headers=self.HEADERS)
                    content = resp.content.decode("gbk", errors="ignore")

                    for line in content.strip().split("\n"):
                        if not line or '="' in line and line.endswith('";'):
                            var_name, val = line.split("=", 1)
                            code = var_name.split("_")[-1].replace('"', '')
                            val_str = val.strip().strip('";')
                            parts = val_str.split(",")
                            if len(parts) >= 32:
                                name = parts[0]
                                open_price = float(parts[1]) if parts[1] else None
                                prev_close = float(parts[2]) if parts[2] else None
                                price = float(parts[3]) if parts[3] else None
                                high = float(parts[4]) if parts[4] else None
                                low = float(parts[5]) if parts[5] else None
                                volume = float(parts[8]) if parts[8] else None
                                amount = float(parts[9]) if parts[9] else None
                                trade_date = parts[30] if len(parts) > 30 and parts[30] else None
                                trade_time = parts[31] if len(parts) > 31 and parts[31] else None

                                open_pct = None
                                if open_price is not None and prev_close is not None and prev_close > 0:
                                    open_pct = round((open_price - prev_close) / prev_close * 100, 2)

                                is_one_word_up = False
                                is_one_word_down = False
                                if open_price is not None and high is not None and low is not None and open_pct is not None:
                                    threshold = 19.8 if (code.startswith("30") or code.startswith("68")) else 9.8
                                    if open_price == high == low and open_pct >= threshold:
                                        is_one_word_up = True
                                    elif open_price == high == low and open_pct <= -threshold:
                                        is_one_word_down = True

                                if price is not None and price > 0:
                                    results.append({
                                        "code": code,
                                        "symbol": code,
                                        "name": name,
                                        "open": open_price,
                                        "prev_close": prev_close,
                                        "price": price,
                                        "high": high,
                                        "low": low,
                                        "volume": volume,
                                        "amount": amount,
                                        "open_pct": open_pct,
                                        "is_one_word_up": is_one_word_up,
                                        "is_one_word_down": is_one_word_down,
                                        "date": trade_date,
                                        "time": trade_time,
                                    })

            return DataResult(
                data=results,
                quality=DataQuality.FULL if len(results) == len(codes) else DataQuality.PARTIAL,
                provider=self.name
            )
        except Exception as e:
            logger.error(f"Sina get_stock_quotes failed: {e}")
            return DataResult(data=None, quality=DataQuality.FAILED, provider=self.name, error_message=str(e))

    async def get_overnight_data(self) -> DataResult:
        """获取美股/亚太/外盘商品隔夜数据"""
        try:
            # 纳斯达克, 道琼斯, 标普500, 富时A50, 恒生
            overnight_codes = ["gb_ixic", "gb_dji", "gb_inx", "hf_CHA50CFD", "int_hangseng"]
            url = f"https://hq.sinajs.cn/list={','.join(overnight_codes)}"

            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.get(url, headers=self.HEADERS)
                content = resp.content.decode("gbk", errors="ignore")

            items = []
            for line in content.strip().split("\n"):
                if not line or "=" not in line:
                    continue
                var_name, val = line.split("=", 1)
                val_str = val.strip().strip('";')
                if not val_str:
                    continue
                parts = val_str.split(",")
                if len(parts) < 2:
                    continue

                code = var_name.split("_")[-1].replace('"', '')
                name = parts[0]
                price = None
                pct_change = None
                change_val = None
                time_str = None

                # 美股指数 (gb_ixic, gb_dji, gb_inx)
                if "gb_" in var_name:
                    try:
                        price = round(float(parts[1]), 2)
                        pct_change = round(float(parts[2]), 2)
                        time_str = parts[3] if len(parts) > 3 else None
                        change_val = round(float(parts[4]), 2) if len(parts) > 4 else None
                    except (ValueError, IndexError):
                        pass

                # 外盘期货 (hf_CHA50CFD 等)
                elif "hf_" in var_name:
                    try:
                        price = round(float(parts[0]), 2)
                        pre_close = float(parts[7]) if len(parts) > 7 and parts[7] else None
                        if price is not None and pre_close and pre_close > 0:
                            change_val = round(price - pre_close, 2)
                            pct_change = round((change_val / pre_close) * 100, 2)
                        time_str = f"{parts[12]} {parts[6]}" if len(parts) > 12 else None
                        name = "富时中国A50期货"
                    except (ValueError, IndexError):
                        pass

                # 亚太指数 (int_hangseng 等)
                elif "int_" in var_name:
                    try:
                        price = round(float(parts[1]), 2) if len(parts) > 1 else None
                        change_val = round(float(parts[2]), 2) if len(parts) > 2 else None
                        pct_change = round(float(parts[3]), 2) if len(parts) > 3 else None
                        time_str = parts[4] if len(parts) > 4 else None
                    except (ValueError, IndexError):
                        pass

                items.append({
                    "code": code,
                    "symbol": code,
                    "name": name,
                    "price": price,
                    "pct_change": pct_change,
                    "change_pct": pct_change,
                    "change_val": change_val,
                    "time": time_str
                })

            return DataResult(data=items, quality=DataQuality.FULL if items else DataQuality.PARTIAL, provider=self.name)
        except Exception as e:
            logger.error(f"Sina get_overnight_data failed: {e}")
            return DataResult(data=None, quality=DataQuality.FAILED, provider=self.name, error_message=str(e))

    async def get_latest_news(self, count: int = 15) -> DataResult:
        """新浪财经新闻 feed 备用方案"""
        try:
            # 简版财经要闻
            url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=15&page=1"
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.get(url, headers=self.HEADERS)
                data = resp.json()

            items = []
            for entry in data.get("result", {}).get("data", [])[:count]:
                items.append({
                    "title": entry.get("title"),
                    "brief": entry.get("intro"),
                    "publish_time": entry.get("ctime"),
                    "source": "sina"
                })

            return DataResult(data=items, quality=DataQuality.FULL, provider=self.name)
        except Exception as e:
            logger.error(f"Sina get_latest_news failed: {e}")
            return DataResult(data=None, quality=DataQuality.FAILED, provider=self.name, error_message=str(e))

    async def get_external_risk(self) -> DataResult:
        """获取 A50 变动及标准化多空指标 (若不可靠则返回 PARTIAL/UNAVAILABLE，严禁臆测字段)"""
        try:
            url = "https://hq.sinajs.cn/list=hf_CHA50CFD"
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.get(url, headers=self.HEADERS)
                content = resp.content.decode("gbk", errors="ignore")

            a50_pct = None
            if "=" in content:
                _, val = content.split("=", 1)
                val_str = val.strip().strip('";')
                parts = val_str.split(",")
                if len(parts) >= 8 and parts[0]:
                    price = float(parts[0]) if parts[0] else 0.0
                    prev = float(parts[7]) if parts[7] else 0.0
                    if price > 0 and prev > 0:
                        a50_pct = round((price - prev) / prev * 100, 2)

            quality = DataQuality.PARTIAL if a50_pct is not None else DataQuality.UNAVAILABLE

            return DataResult(
                data={
                    "a50_pct_change": a50_pct,
                    "a50_long_short_indicator": None  # G4-B: 不可得时允许为 None，严禁臆测字段
                },
                quality=quality,
                provider=self.name
            )
        except Exception as e:
            logger.error(f"Sina get_external_risk failed: {e}")
            return DataResult(data=None, quality=DataQuality.FAILED, provider=self.name, error_message=str(e))

