import asyncio
import logging
import random
from typing import List, Optional
import httpx
from .base import BaseProvider
from ..capabilities import (
    DataQuality,
    DataResult,
    DataStatus,
    Freshness,
    ProviderErrorCode,
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
        super().__init__(
            name="sina",
            implementation_status="已接入",
            connectivity_verified="已验证",
            schema_verified="已验证",
            semantic_verified="已验证",
            production_eligible="准入",
        )

    async def is_available(self) -> bool:
        return True

    async def get_index_quotes(self, codes: List[str]) -> DataResult:
        """
        获取指数行情 (如 sh000001, sz399001, sz399006, sh000688)
        优先使用完整行情解析真实撮合日期 trade_date 与昨收价 pre_close
        """
        try:
            # 统一转为标准代码 (如 sh000001)
            raw_codes = [c.replace("s_", "") for c in codes]
            url = f"http://hq.sinajs.cn/list={','.join(raw_codes)}"

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
                if len(parts) >= 30:
                    # 完整指数格式: name(0), open(1), pre_close(2), price(3), high(4), low(5), ..., volume(8), amount(9), ..., date(30), time(31)
                    name = parts[0]
                    open_price = float(parts[1]) if len(parts) > 1 and parts[1] != "" else None
                    pre_close = float(parts[2]) if len(parts) > 2 and parts[2] != "" else None
                    price = float(parts[3]) if len(parts) > 3 and parts[3] != "" else None
                    high_price = float(parts[4]) if len(parts) > 4 and parts[4] != "" else None
                    low_price = float(parts[5]) if len(parts) > 5 and parts[5] != "" else None
                    amount_yuan = float(parts[9]) if len(parts) > 9 and parts[9] != "" else None
                    trade_date = parts[30].strip() if len(parts) > 30 else None
                    change = (price - pre_close) if (price is not None and pre_close is not None) else None
                    pct_change = ((change / pre_close) * 100) if (change is not None and pre_close and pre_close > 0) else None
                    amount_wan = (amount_yuan / 10000.0) if amount_yuan is not None else None

                    # 计算日内动态极值与探底回升特征 (深V分时路径还原)
                    low_pct = round(((low_price - pre_close) / pre_close) * 100, 2) if (low_price is not None and pre_close and pre_close > 0) else None
                    high_pct = round(((high_price - pre_close) / pre_close) * 100, 2) if (high_price is not None and pre_close and pre_close > 0) else None
                    rebound_pct = round(((price - low_price) / pre_close) * 100, 2) if (price is not None and low_price is not None and pre_close and pre_close > 0) else None
                    amplitude = round(((high_price - low_price) / pre_close) * 100, 2) if (high_price is not None and low_price is not None and pre_close and pre_close > 0) else None

                    if price is not None and price > 0:
                        quotes.append({
                            "code": code,
                            "symbol": code,
                            "name": name,
                            "price": round(price, 2),
                            "pre_close": round(pre_close, 2) if pre_close is not None else None,
                            "open": round(open_price, 2) if open_price is not None else None,
                            "high": round(high_price, 2) if high_price is not None else None,
                            "low": round(low_price, 2) if low_price is not None else None,
                            "change": round(change, 2) if change is not None else None,
                            "pct_change": round(pct_change, 2) if pct_change is not None else None,
                            "low_pct": low_pct,
                            "high_pct": high_pct,
                            "rebound_pct": rebound_pct,
                            "amplitude": amplitude,
                            "amount_wan": round(amount_wan, 2) if amount_wan is not None else None,
                            "trade_date": trade_date,
                        })
                elif len(parts) >= 6:
                    # 兼容简版格式 s_sh000001: name(0), price(1), change(2), pct_change(3), volume(4), amount(5)
                    name = parts[0]
                    price = float(parts[1]) if len(parts) > 1 and parts[1] != "" else None
                    change = float(parts[2]) if len(parts) > 2 and parts[2] != "" else None
                    pct_change = float(parts[3]) if len(parts) > 3 and parts[3] != "" else None
                    amount = float(parts[5]) if len(parts) > 5 and parts[5] != "" else None
                    pre_close = (price - change) if (price is not None and change is not None) else None

                    if price is not None and price > 0:
                        quotes.append({
                            "code": code,
                            "symbol": code,
                            "name": name,
                            "price": round(price, 2),
                            "pre_close": round(pre_close, 2) if pre_close is not None else None,
                            "change": round(change, 2) if change is not None else None,
                            "pct_change": round(pct_change, 2) if pct_change is not None else None,
                            "amount_wan": round(amount, 2) if amount is not None else None,
                        })

            return DataResult(
                data=quotes,
                quality=DataQuality.FULL if len(quotes) >= len(codes) else DataQuality.PARTIAL,
                provider=self.name
            )
        except Exception as e:
            logger.error(f"Sina get_index_quotes failed: {e}")
            return DataResult(data=None, quality=DataQuality.FAILED, provider=self.name, error_message=str(e))

    @staticmethod
    def _format_stock_code(c: str) -> str:
        """为股票代码自动补齐 sh/sz/bj 市场前缀"""
        c_clean = str(c).strip().lower()
        if c_clean.startswith(("sh", "sz", "bj")):
            return c_clean
        if c_clean.startswith(("60", "68", "90")):
            return f"sh{c_clean}"
        elif c_clean.startswith(("00", "30", "20")):
            return f"sz{c_clean}"
        elif c_clean.startswith(("8", "4", "92")):
            return f"bj{c_clean}"
        return c_clean

    async def get_stock_quotes(self, codes: List[str]) -> DataResult:
        """分批获取个股行情（自动补齐市场前缀，每批15只，带Jitter与指数退避）"""
        results = []
        chunk_size = 15
        formatted_codes = [self._format_stock_code(c) for c in codes if c]
        chunks = [formatted_codes[i:i + chunk_size] for i in range(0, len(formatted_codes), chunk_size)]

        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                for idx, chunk in enumerate(chunks):
                    if idx > 0:
                        # 批次之间增加 150ms ~ 300ms 随机 Jitter 间隔
                        await asyncio.sleep(random.uniform(0.15, 0.30))

                    url = f"http://hq.sinajs.cn/list={','.join(chunk)}"
                    content = ""
                    max_retries = 3
                    for retry in range(max_retries):
                        try:
                            resp = await client.get(url, headers=self.HEADERS)
                            if resp.status_code == 200:
                                content = resp.content.decode("gbk", errors="ignore")
                                break
                            elif resp.status_code in (403, 429, 502):
                                delay = (2 ** retry) * 1.0 + random.uniform(0, 0.5)
                                logger.warning(f"Sina HTTP {resp.status_code}, backing off {delay:.2f}s (retry {retry+1}/{max_retries})")
                                await asyncio.sleep(delay)
                        except (httpx.TimeoutException, httpx.NetworkError) as e:
                            delay = (2 ** retry) * 1.0 + random.uniform(0, 0.5)
                            if retry < max_retries - 1:
                                await asyncio.sleep(delay)
                            else:
                                logger.warning(f"Sina chunk {chunk} network error after {max_retries} retries: {e}")

                    if not content:
                        continue

                    for line in content.strip().split("\n"):
                        line = line.strip()
                        if not line or "=" not in line:
                            continue
                        var_name, val = line.split("=", 1)
                        full_code = var_name.split("_")[-1].replace('"', '').strip()
                        symbol = full_code[-6:] if len(full_code) >= 6 else full_code
                        val_str = val.strip().strip('";')
                        parts = val_str.split(",")
                        if len(parts) >= 32:
                            name = parts[0].strip()
                            open_price = float(parts[1]) if parts[1] else None
                            prev_close = float(parts[2]) if parts[2] else None
                            price = float(parts[3]) if parts[3] else None
                            high = float(parts[4]) if parts[4] else None
                            low = float(parts[5]) if parts[5] else None
                            volume = float(parts[8]) if parts[8] else None
                            amount = float(parts[9]) if parts[9] else None

                            # 盘口档位提取 (买一/卖一)
                            bid1_vol = float(parts[10]) if len(parts) > 10 and parts[10] else 0.0
                            bid1_price = float(parts[11]) if len(parts) > 11 and parts[11] else 0.0
                            ask1_vol = float(parts[20]) if len(parts) > 20 and parts[20] else 0.0
                            ask1_price = float(parts[21]) if len(parts) > 21 and parts[21] else 0.0
                            bid1_amount = round(bid1_vol * bid1_price, 2)
                            bid1_amount_wan = round(bid1_amount / 10000.0, 2)

                            trade_date = parts[30] if len(parts) > 30 and parts[30] else None
                            trade_time = parts[31] if len(parts) > 31 and parts[31] else None

                            open_pct = None
                            if open_price is not None and prev_close is not None and prev_close > 0:
                                open_pct = round((open_price - prev_close) / prev_close * 100, 2)

                            pct_change = None
                            if price is not None and prev_close is not None and prev_close > 0:
                                pct_change = round((price - prev_close) / prev_close * 100, 2)

                            threshold = 19.8 if (symbol.startswith("30") or symbol.startswith("68")) else 9.8

                            is_one_word_up = False
                            is_one_word_down = False
                            if open_price is not None and high is not None and low is not None and open_pct is not None:
                                if open_price == high == low and open_pct >= threshold:
                                    is_one_word_up = True
                                elif open_price == high == low and open_pct <= -threshold:
                                    is_one_word_down = True

                            # 盘中涨停与封死判定 (卖一挂单量为 0 且价格达到涨停阈值，且买一封单金额 >= 1000 万元)
                            is_limit_up = False
                            is_sealed = False
                            if pct_change is not None and pct_change >= threshold - 0.2:
                                is_limit_up = True
                                # 卖一空单且买一封单达标 (实盘 >= 1000万元，或一字涨停)
                                if (ask1_vol == 0 or ask1_price == 0) and (bid1_amount >= 10000000.0 or is_one_word_up):
                                    is_sealed = True

                            if price is not None and price > 0:
                                results.append({
                                    "code": full_code,
                                    "symbol": symbol,
                                    "name": name,
                                    "open": open_price,
                                    "prev_close": prev_close,
                                    "price": round(price, 3),
                                    "high": high,
                                    "low": low,
                                    "volume": volume,
                                    "amount": amount,
                                    "amount_wan": round(amount / 10000.0, 2) if amount else 0.0,
                                    "open_pct": open_pct,
                                    "pct_change": pct_change,
                                    "bid1_vol": bid1_vol,
                                    "bid1_price": bid1_price,
                                    "bid1_amount": bid1_amount,
                                    "bid1_amount_wan": bid1_amount_wan,
                                    "ask1_vol": ask1_vol,
                                    "ask1_price": ask1_price,
                                    "is_limit_up": is_limit_up,
                                    "is_sealed": is_sealed,
                                    "is_one_word_up": is_one_word_up,
                                    "is_one_word_down": is_one_word_down,
                                    "date": trade_date,
                                    "time": f"{trade_date} {trade_time}" if (trade_date and trade_time) else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
            url = f"http://hq.sinajs.cn/list={','.join(overnight_codes)}"

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
        """新浪财经新闻 feed 备用方案（双源容灾）"""
        try:
            # 简版财经要闻
            url = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2509&k=&num=15&page=1"
            async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
                resp = await client.get(url, headers=self.HEADERS)
                if resp.status_code != 200:
                    return DataResult(
                        data=None,
                        quality=DataQuality.UNAVAILABLE,
                        status=DataStatus.ERROR,
                        error_code=ProviderErrorCode.HTTP_ERROR,
                        provider=self.name,
                        error_message=f"Sina news HTTP {resp.status_code}"
                    )
                text = resp.text.strip()
                if not text:
                    return DataResult(
                        data=None,
                        quality=DataQuality.UNAVAILABLE,
                        status=DataStatus.EMPTY,
                        error_code=ProviderErrorCode.EMPTY_PAYLOAD,
                        provider=self.name,
                        error_message="Sina news returned empty payload"
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
                        error_message=f"Sina news JSON decode error: {e}"
                    )

            items = []
            for entry in data.get("result", {}).get("data", [])[:count]:
                items.append({
                    "title": entry.get("title"),
                    "brief": entry.get("intro"),
                    "publish_time": str(entry.get("ctime")),
                    "source": "sina"
                })

            if not items:
                return DataResult(
                    data=[],
                    quality=DataQuality.PARTIAL,
                    status=DataStatus.EMPTY,
                    provider=self.name,
                    error_message="Sina news returned 0 items"
                )

            return DataResult(
                data=items,
                quality=DataQuality.FULL,
                status=DataStatus.AVAILABLE,
                freshness=Freshness.REALTIME,
                provider=self.name
            )
        except httpx.TimeoutException as te:
            logger.warning(f"Sina get_latest_news timeout: {te}")
            return DataResult(
                data=None,
                quality=DataQuality.UNAVAILABLE,
                status=DataStatus.TIMEOUT,
                error_code=ProviderErrorCode.TIMEOUT,
                provider=self.name,
                error_message=f"Sina news timeout (>8s): {te}"
            )
        except Exception as e:
            logger.error(f"Sina get_latest_news failed: {e}")
            return DataResult(
                data=None,
                quality=DataQuality.FAILED,
                status=DataStatus.ERROR,
                error_code=ProviderErrorCode.CONNECTION_ERROR,
                provider=self.name,
                error_message=str(e)
            )

    async def get_external_risk(self) -> DataResult:
        """获取 A50 变动及标准化多空指标 (融合盘口委买卖深度与价格日内位置区间)"""
        try:
            url = "http://hq.sinajs.cn/list=hf_CHA50CFD"
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.get(url, headers=self.HEADERS)
                content = resp.content.decode("gbk", errors="ignore")

            a50_pct = None
            long_short_ind = None
            if "=" in content:
                _, val = content.split("=", 1)
                val_str = val.strip().strip('";')
                parts = val_str.split(",")
                if len(parts) >= 8 and parts[0]:
                    price = float(parts[0]) if parts[0] else 0.0
                    prev = float(parts[7]) if parts[7] else 0.0
                    high = float(parts[4]) if len(parts) > 4 and parts[4] else price
                    low = float(parts[5]) if len(parts) > 5 and parts[5] else price
                    bid_vol = float(parts[10]) if len(parts) > 10 and parts[10] else 0.0
                    ask_vol = float(parts[11]) if len(parts) > 11 and parts[11] else 0.0

                    if price > 0 and prev > 0:
                        a50_pct = round((price - prev) / prev * 100, 2)

                        # 标准化 A50 多空强弱指标 (0~100 刻度，50为多空中性，>60偏多，<40偏空)
                        order_book_score = 50.0
                        if (bid_vol + ask_vol) > 0:
                            order_book_score = (bid_vol / (bid_vol + ask_vol)) * 100.0

                        price_range_score = 50.0
                        if high > low:
                            price_range_score = ((price - low) / (high - low)) * 100.0
                        else:
                            clamped_pct = max(min(a50_pct, 2.0), -2.0)
                            price_range_score = 50.0 + (clamped_pct / 2.0) * 25.0

                        long_short_ind = round(price_range_score * 0.6 + order_book_score * 0.4, 2)

            quality = DataQuality.FULL if (a50_pct is not None and long_short_ind is not None) else (
                DataQuality.PARTIAL if a50_pct is not None else DataQuality.UNAVAILABLE
            )

            return DataResult(
                data={
                    "a50_pct_change": a50_pct,
                    "a50_long_short_indicator": long_short_ind
                },
                quality=quality,
                provider=self.name
            )
        except Exception as e:
            logger.error(f"Sina get_external_risk failed: {e}")
            return DataResult(data=None, quality=DataQuality.FAILED, provider=self.name, error_message=str(e))

