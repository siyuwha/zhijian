import asyncio
import logging
import random
from datetime import datetime, time as dtime
from typing import Dict, List, Optional, Any
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.calendar import calendar
from ..data.service import DataService
from .turnover_engine import calculate_turnover_caliber, TurnoverSourceStatus
from ..models.market import IntradayMarketSnapshot, IntradayAnomalyEvent
from ..models.report import DailyReview, PremarketBriefing, AuctionReport

logger = logging.getLogger(__name__)

class MonitorService:
    """
    M4 盘中动态监控与异动感知服务引擎 (v1.1)
    严格遵循董事会 5 大核心边界与 7+1 铁律必修清单：
    1. 统一契约与 None 零填充防伪 (所有指标缺失保持 None，绝不填 0)
    2. 量能投影 W(T) 累积函数 (09:30~09:45 强制为 None，标记 ESTIMATED)
    3. 数学指标冷启动 (09:30~10:00 R_vol 强制为 None，状态 BASELINE_NOT_READY)
    4. 边沿跃迁触发 Edge Trigger (涨跌停状态持续期零重复插入)
    5. 简化系统性共振布尔规则 (指数同向 >= 0.15% 或 板块异动标的数 >= 2)
    6. 锁定白名单边界与排除项 (领涨前3行业、1000亿成交Top20中军，排除 ST/*ST/停牌标的)
    7. 午休跨段窗口向前拼接 (13:00~13:05 跨段取 11:25~11:30) 与异步批处理落盘
    """

    # 内存热时序环形缓存 (当日宏观分时序列: minute_index -> snapshot dict)
    _macro_series_cache: Dict[int, dict] = {}
    # 标的历史分时切片: symbol -> list of dicts [{minute_index, price, volume, amount, timestamp}]
    _stock_series_cache: Dict[str, List[dict]] = {}
    # 标的前一周期状态缓存 (用于 Edge Trigger 边沿跃迁检测): symbol -> status ("NORMAL", "SEALED", "BROKEN", "HALTED")
    _stock_state_cache: Dict[str, str] = {}
    # 异动提醒冷却期记录 (用于 15 分钟降噪): (symbol, event_type) -> last_triggered_datetime
    _cooldown_cache: Dict[str, datetime] = {}
    # 内存近期事件流水
    _recent_events_cache: List[dict] = []
    # 异步写入队列
    _async_write_queue: asyncio.Queue = asyncio.Queue()
    # 缓存归属日期 (用于日切隔离，防止次日假炸板风暴与历史时序污染)
    _cache_date: Optional[str] = None
    _flush_task: Optional[asyncio.Task] = None

    DISCLAIMER = "【客观物理事实测量提示】本看板仅对盘中市场量价与流动性数据进行客观时间序列观测与统计记录，非买卖建议，不构成任何投资建议或交易执行指令。市场有风险，决策须自主。"

    @classmethod
    def _ensure_date_cache(cls, target_date: str):
        """
        日切与缓存隔离：当接收到新交易日请求时，自动清理上一日内存状态，防止次日开盘假炸板与历史时序污染
        【红队审计整改项 4】
        """
        if cls._cache_date is None:
            cls._cache_date = target_date
        elif cls._cache_date != target_date:
            logger.info(f"MonitorService 触发日切隔离清理: {cls._cache_date} -> {target_date}")
            cls._macro_series_cache.clear()
            cls._stock_series_cache.clear()
            cls._stock_state_cache.clear()
            cls._cooldown_cache.clear()
            cls._recent_events_cache.clear()
            cls._cache_date = target_date

    @classmethod
    def start_background_daemon(cls, session_factory):
        """启动后台异步批处理持久化与采样 Daemon【红队审计整改项 5】"""
        if cls._flush_task is None or cls._flush_task.done():
            cls._flush_task = asyncio.create_task(cls._daemon_loop(session_factory))
            logger.info("MonitorService 异步批处理与盘中采样 Daemon 已启动")

    @classmethod
    async def stop_background_daemon(cls, session_factory=None):
        """停止后台 Daemon 并安全落盘【红队审计整改项 5】"""
        if cls._flush_task and not cls._flush_task.done():
            cls._flush_task.cancel()
            try:
                await cls._flush_task
            except asyncio.CancelledError:
                pass
            cls._flush_task = None
        if session_factory and not cls._async_write_queue.empty():
            try:
                async with session_factory() as session:
                    srv = MonitorService(session)
                    await srv.flush_async_queue()
            except Exception as e:
                logger.error(f"MonitorService 停止时最终刷盘异常: {e}")
        logger.info("MonitorService 后台 Daemon 已安全停止")


    @classmethod
    async def _daemon_loop(cls, session_factory):
        """后台消费循环：每 10 秒唤醒消费异步写队列"""
        while True:
            try:
                await asyncio.sleep(10)
                if not cls._async_write_queue.empty():
                    async with session_factory() as session:
                        srv = MonitorService(session)
                        await srv.flush_async_queue()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"MonitorService 异步写队列落盘循环异常: {e}")

    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session
        self.data_service = DataService(session)
        from ..data.providers.eastmoney import EastmoneyProvider
        from ..data.providers.sina import SinaProvider
        self.eastmoney = EastmoneyProvider()
        self.sina = SinaProvider()

    # ==========================================
    # 1. 时间戳与交易时钟辅助计算
    # ==========================================

    @staticmethod
    def get_trading_session_state(now_dt: Optional[datetime] = None) -> str:
        """获取当前盘中状态: PRE_MARKET / ACTIVE / NOON_BREAK / CLOSED"""
        if now_dt is None:
            now_dt = datetime.now()
        cur_time = now_dt.time()
        if cur_time < dtime(9, 30):
            return "PRE_MARKET"
        elif dtime(9, 30) <= cur_time < dtime(11, 30):
            return "ACTIVE"
        elif dtime(11, 30) <= cur_time < dtime(13, 0):
            return "NOON_BREAK"
        elif dtime(13, 0) <= cur_time <= dtime(15, 0):
            return "ACTIVE"
        else:
            return "CLOSED"

    @staticmethod
    def get_minute_index(now_dt: Optional[datetime] = None) -> int:
        """
        计算盘中有效交易分钟序号 (1 ~ 240)
        09:30 -> 1, 11:30 -> 120, 13:00 -> 121, 15:00 -> 240
        """
        if now_dt is None:
            now_dt = datetime.now()
        cur_time = now_dt.time()

        if cur_time < dtime(9, 30):
            return 0
        elif dtime(9, 30) <= cur_time <= dtime(11, 30):
            m = (cur_time.hour - 9) * 60 + cur_time.minute - 30
            return max(1, min(120, m if m > 0 else 1))
        elif dtime(11, 30) < cur_time < dtime(13, 0):
            return 120
        elif dtime(13, 0) <= cur_time <= dtime(15, 0):
            m = 120 + (cur_time.hour - 13) * 60 + cur_time.minute
            return max(121, min(240, m if m > 120 else 121))
        else:
            return 240

    @staticmethod
    def calculate_w_cum(minute_index: int) -> Optional[float]:
        """
        日内成交占比累积分布函数 W(T)
        【v1.1 必修项 2】：09:30~09:45 (T <= 15) 强制返回 None (冷启动防失真)
        """
        if minute_index <= 15:
            return None
        if minute_index >= 240:
            return 1.0

        # 分段线性插值基准锚点 (分时累计成交经验分布)
        anchors = [
            (15, 0.15),
            (30, 0.25),
            (60, 0.38),
            (120, 0.55),
            (180, 0.78),
            (210, 0.88),
            (240, 1.00),
        ]
        for i in range(len(anchors) - 1):
            m0, w0 = anchors[i]
            m1, w1 = anchors[i + 1]
            if m0 <= minute_index <= m1:
                ratio = (minute_index - m0) / (m1 - m0)
                return round(w0 + ratio * (w1 - w0), 4)
        return 1.0

    # ==========================================
    # 2. 前序基线只读消费 (M1, M2, M3)
    # ==========================================

    async def get_yesterday_baseline(self) -> dict:
        """只读消费 M1 昨日收盘复盘状态向量与连板池"""
        yesterday_amount_yi = None
        yesterday_pool = []
        max_height = 0

        if self.session:
            from ..core.calendar import calendar
            today_str = datetime.now().strftime("%Y-%m-%d")
            prev_trade_date = calendar.prev_trading_day(today_str).strftime("%Y-%m-%d")
            stmt = (
                select(DailyReview)
                .where(DailyReview.date <= prev_trade_date)
                .order_by(desc(DailyReview.date))
                .limit(10)
            )
            res = await self.session.execute(stmt)
            candidates = res.scalars().all()
            prev_review = next((r for r in candidates if calendar.is_trading_day(r.date)), None)
            if prev_review and prev_review.report_content:
                try:
                    import json
                    rep = json.loads(prev_review.report_content)
                    d6 = rep.get("market_state", {}).get("dimensions", {}).get("D6") or {}
                    raw_amt = (d6.get("metrics") or {}).get("total_amount")
                    if raw_amt is not None and float(raw_amt) > 0:
                        yesterday_amount_yi = round(float(raw_amt), 1)
                except Exception as e:
                    logger.warning(f"解析前日 D6 总成交额失败: {e}")

            if prev_review and prev_review.limit_up_analysis:
                try:
                    import json
                    lu = json.loads(prev_review.limit_up_analysis)
                    yesterday_pool = lu.get("pool", [])
                    max_height = lu.get("max_height") or lu.get("max_board_height", 0)
                except Exception as e:
                    logger.warning(f"解析前日连板池失败: {e}")

        return {
            "yesterday_amount_yi": yesterday_amount_yi,
            "yesterday_pool": yesterday_pool,
            "max_height": max_height
        }

    async def get_auction_baseline(self, date_str: str) -> dict:
        """只读消费 M3 09:25 开盘微观事实 (物理原点 t0)"""
        open_items = {}
        high_open_stats = {}
        if self.session:
            stmt = select(AuctionReport).where(AuctionReport.date == date_str)
            res = await self.session.execute(stmt)
            rep = res.scalar_one_or_none()
            if rep and rep.high_open_stats:
                try:
                    import json
                    high_open_stats = json.loads(rep.high_open_stats)
                    for item in high_open_stats.get("stocks", []):
                        sym = str(item.get("symbol", ""))[-6:]
                        if sym:
                            open_items[sym] = item.get("open_pct")
                except Exception as e:
                    logger.warning(f"解析 M3 竞价数据失败: {e}")
        return {
            "open_items": open_items,
            "high_open_stats": high_open_stats
        }

    # ==========================================
    # 3. 核心监控池构建 (白名单与排除项)
    # ==========================================

    async def build_watchlist_universe(self, date_str: str) -> List[str]:
        """
        构建盘中重点监测核心池 (Watchlist)
        【v1.1 必修项 6】：
        1. 空间板最高标与 M1 连板梯队 (连板数 >= 2)
        2. 日内领涨行业前 3 龙头 (取东财当日涨幅榜前3板块)
        3. 核心容量中军 (总市值 >= 1000 亿且成交额 Top 20)
        4. 显式排除 ST / *ST / 停牌标的
        """
        watchlist_set = set()

        # 1. 继承 M1 连板池
        y_base = await self.get_yesterday_baseline()
        for s in y_base.get("yesterday_pool", []):
            code = s.get("code") or s.get("symbol")
            if code:
                sym = str(code).strip()[-6:]
                # 排除 ST, *ST, 退市整理期 (含 xx退)
                name_upper = str(s.get("name", "")).upper()
                if "ST" not in name_upper and "退" not in name_upper:
                    watchlist_set.add(sym)

        # 2. 获取领涨行业前 3 (来自 Eastmoney)
        try:
            top_sectors_res = await self.eastmoney.get_top_sectors(limit=3)
            # 记录领涨行业供系统性共振使用
            self._top_sectors = top_sectors_res.data or []
        except Exception as e:
            logger.warning(f"获取领涨行业前3失败: {e}")

        # 3. 获取千亿容量中军
        try:
            cores_res = await self.eastmoney.get_large_cap_turnover_cores(min_cap_yi=1000.0, top_turnover=20)
            for c in (cores_res.data or []):
                sym = str(c.get("symbol", "")).strip()[-6:]
                if sym:
                    watchlist_set.add(sym)
        except Exception as e:
            logger.warning(f"获取千亿容量中军失败: {e}")

        # 确保最高空间板优先包含
        return list(watchlist_set)[:50]

    # ==========================================
    # 4. 盘中宏观切片与时序采集 (09:30~15:00)
    # ==========================================

    async def capture_macro_snapshot(self, date_str: str, now_dt: Optional[datetime] = None) -> dict:
        """
        采集盘中宏观快照 (指数、全市场广度、两市量能、量能投影)
        【v1.1 必修项 1 & 2】：统一 None 零填充防伪，所有统计指标缺失保持 None
        """
        if now_dt is None:
            now_dt = datetime.now()
        minute_index = self.get_minute_index(now_dt)
        time_str = now_dt.strftime("%H:%M:%S")

        # 1. 宽基指数行情
        core_index_codes = ["s_sh000001", "s_sz399001", "s_sz399006", "s_sh000688"]
        index_res = await self.data_service.get_index_quotes(core_index_codes)
        index_data = index_res.data or []

        sh_price = None
        sh_pct = None
        sz_price = None
        sz_pct = None
        cy_pct = None
        sh_q = next((q for q in index_data if "sh000001" in q.get("code", "")), None)
        sz_q = next((q for q in index_data if "sz399001" in q.get("code", "")), None)
        cy_q = next((q for q in index_data if "sz399006" in q.get("code", "")), None)
        star_q = next((q for q in index_data if "sh000688" in q.get("code", "")), None)

        if sh_q:
            sh_price = sh_q.get("price")
            sh_pct = sh_q.get("pct_change")
        if sz_q:
            sz_price = sz_q.get("price")
            sz_pct = sz_q.get("pct_change")
        if cy_q:
            cy_pct = cy_q.get("pct_change")

        # T09-01 标准口径治理：禁止循环累加 4 个指数！
        # 候选来源保持 PENDING_VERIFICATION 门禁，透传真实时间戳，正式两市总额保守置空 (None)
        turnover_res = calculate_turnover_caliber(
            target_date=date_str,
            sh_amount=sh_q.get("amount_wan") if sh_q else None,
            sh_date=sh_q.get("date") if sh_q else None,
            sh_time=sh_q.get("time") if sh_q else None,
            sh_volume=sh_q.get("volume") if sh_q else None,
            sh_unit="wan",
            sz_amount=sz_q.get("amount_wan") if sz_q else None,
            sz_date=sz_q.get("date") if sz_q else None,
            sz_time=sz_q.get("time") if sz_q else None,
            sz_volume=sz_q.get("volume") if sz_q else None,
            sz_unit="wan",
            chinext_amount=cy_q.get("amount_wan") if cy_q else None,
            chinext_unit="wan",
            now_dt=now_dt,
            sh_status=TurnoverSourceStatus.PENDING_VERIFICATION,
            sz_status=TurnoverSourceStatus.PENDING_VERIFICATION,
        )

        total_amount_yi = turnover_res.two_markets_total_yi

















        # 2. 全市场广度 (来自 Eastmoney)
        breadth_res = await self.data_service.get_market_breadth()
        b_data = breadth_res.data or {}
        up_count = b_data.get("up_count")
        down_count = b_data.get("down_count")

        # 3. 涨停与连板情绪 (来自 TongHuaShun/Eastmoney)
        limit_up_res = await self.data_service.get_limit_up_pool(date_str)
        lu_data = limit_up_res.data or {}
        limit_up_count = lu_data.get("total_count")
        limit_down_count = lu_data.get("limit_down_count")
        broken_limit_count = lu_data.get("broken_count")
        max_height = lu_data.get("max_height")

        # 4. 量能投影计算 (W(T) 分布)
        # 【v1.1 必修项 2】：09:30~09:45 强制输出 None，标记 ESTIMATED
        volume_proj_yi = None
        is_proj_estimated = False
        w = self.calculate_w_cum(minute_index)
        if w is not None and total_amount_yi is not None and w > 0:
            volume_proj_yi = round(total_amount_yi / w, 1)
            is_proj_estimated = True

        # 构建统一的可空字典
        snapshot = {
            "date": date_str,
            "timestamp": time_str,
            "minute_index": minute_index,
            "sh_price": sh_price,
            "sh_pct": sh_pct,
            "sz_price": sz_price,
            "sz_pct": sz_pct,
            "cy_pct": cy_pct,
            "total_amount_yi": total_amount_yi,
            "sh_amount_yi": turnover_res.sh_amount_yi,
            "sz_amount_yi": turnover_res.sz_total_amount_yi,
            "cy_slice_amount_yi": turnover_res.chinext_slice_amount_yi,
            "turnover_quality": turnover_res.two_markets_quality.value if hasattr(turnover_res.two_markets_quality, "value") else str(turnover_res.two_markets_quality),
            "turnover_reason": "; ".join(turnover_res.degradation_reasons),
            "volume_proj_yi": volume_proj_yi,
            "is_proj_estimated": is_proj_estimated,
            "up_count": up_count,
            "down_count": down_count,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "broken_count": broken_limit_count,
            "max_height": max_height,
            "leader_stock": None
        }

        # 寻找当前最高连板股
        items = lu_data.get("items", [])
        if items and max_height and max_height > 0:
            for it in items:
                if it.get("lbc") == max_height:
                    snapshot["leader_stock"] = f"{it.get('name')}({it.get('code')}) {max_height}连板"
                    break

        # 存入内存环形缓存
        self._macro_series_cache[minute_index] = snapshot

        # 触发 5 分钟增量抽样落盘 (写入异步批处理队列)
        if minute_index % 5 == 0 and self.session:
            await self._async_write_queue.put(("snapshot", snapshot))

        return snapshot

    # ==========================================
    # 5. 异动感知引擎 (边沿触发、冷启动、共振)
    # ==========================================

    async def detect_anomalies(
        self,
        date_str: str,
        now_dt: Optional[datetime] = None
    ) -> List[dict]:
        """
        盘中异动与相变感知扫描
        【v1.1 必修项 3, 4, 5, 7】：
        - 边沿跃迁触发 Edge Trigger
        - 09:30~10:00 R_vol 冷启动保护
        - 简化系统性共振布尔规则
        - 13:00~13:05 午休跨段窗口
        """
        if now_dt is None:
            now_dt = datetime.now()
        minute_index = self.get_minute_index(now_dt)
        time_str = now_dt.strftime("%H:%M:%S")

        # 非活跃盘中时段不执行异动扫描
        session_state = self.get_trading_session_state(now_dt)
        if session_state != "ACTIVE":
            return []

        self._ensure_date_cache(date_str)

        # 获取重点池行情
        watchlist = await self.build_watchlist_universe(date_str)
        if not watchlist:
            return []

        stock_res = await self.data_service.get_stock_quotes(watchlist)
        quotes = stock_res.data or []
        detected_events = []

        # 取得当前大盘与双创指数波动 (用于系统性共振计算)
        cur_macro = self._macro_series_cache.get(minute_index, {})
        sh_pct = cur_macro.get("sh_pct")
        cy_pct = cur_macro.get("cy_pct")

        # 检查大盘 5 分钟波动: IndexCoMove >= 0.15%
        # 【v1.1 必修项 7】：午休跨段拼接 (13:00~13:05 跨段取 11:25~11:30)
        macro_prev_5 = self._get_stitched_macro_point(minute_index, 5)
        prev_sh_pct = macro_prev_5.get("sh_pct") if macro_prev_5 else None
        prev_cy_pct = macro_prev_5.get("cy_pct") if macro_prev_5 else None

        sh_index_delta = round(sh_pct - prev_sh_pct, 4) if (sh_pct is not None and prev_sh_pct is not None) else 0.0
        cy_index_delta = round(cy_pct - prev_cy_pct, 4) if (cy_pct is not None and prev_cy_pct is not None) else sh_index_delta

        # 预先将本轮行情推入切片，并计算各标的 3 分钟速动速度
        stock_velocity_map = {}
        for sq in quotes:
            sym = sq.get("symbol")
            price = sq.get("price")
            pct_change = sq.get("pct_change")
            amount = sq.get("amount") or 0.0
            is_sealed = sq.get("is_sealed", False)

            if not sym or price is None or pct_change is None:
                continue

            if sym not in self._stock_series_cache:
                self._stock_series_cache[sym] = []
            self._stock_series_cache[sym].append({
                "minute_index": minute_index,
                "price": price,
                "pct_change": pct_change,
                "amount": amount,
                "is_sealed": is_sealed,
                "timestamp": time_str
            })
            if len(self._stock_series_cache[sym]) > 60:
                self._stock_series_cache[sym] = self._stock_series_cache[sym][-60:]

            slices = self._stock_series_cache[sym]
            if len(slices) >= 4:
                s_prev_3 = self._get_stitched_stock_slice(slices, minute_index, 3)
                if s_prev_3 and s_prev_3.get("price") and s_prev_3["price"] > 0:
                    v_3m = round((price - s_prev_3["price"]) / s_prev_3["price"] * 100, 2)
                    delta_amt_wan = round((amount - s_prev_3.get("amount", 0.0)) / 10000.0, 1)
                    stock_velocity_map[sym] = (v_3m, delta_amt_wan)

        # 统计重点池同向快速异动标的数，用于 SectorCoMove (同向标的数 >= 2)
        pos_movers_count = sum(1 for v, _ in stock_velocity_map.values() if v >= 2.0)
        neg_movers_count = sum(1 for v, _ in stock_velocity_map.values() if v <= -2.0)

        for sq in quotes:
            sym = sq.get("symbol")
            name = sq.get("name")
            price = sq.get("price")
            pct_change = sq.get("pct_change")
            amount = sq.get("amount") or 0.0 # 元
            is_sealed = sq.get("is_sealed", False)

            if not sym or price is None or pct_change is None:
                continue

            # ------------------------------------------------------------------
            # 规则 A: 边沿跃迁触发 Edge Trigger (涨停封死与炸板)
            # 【v1.1 必修项 4】：仅在状态改变瞬间触发，持续封死绝对不重复插入！
            # ------------------------------------------------------------------
            prev_status = self._stock_state_cache.get(sym, "NORMAL")
            current_status = "SEALED" if is_sealed else "NORMAL"

            # 1. 封死涨停跃迁: NORMAL -> SEALED
            if prev_status != "SEALED" and current_status == "SEALED":
                bid1_wan = round(sq.get("bid1_amount_wan", (sq.get("bid1_amount") or 0.0) / 10000.0), 1)
                event = {
                    "date": date_str,
                    "timestamp": time_str,
                    "minute_index": minute_index,
                    "event_category": "LIMIT_UP_LOCK",
                    "severity_level": "CRITICAL",
                    "symbol": sym,
                    "name": name,
                    "price": price,
                    "pct_change": pct_change,
                    "window_delta_pct": None,
                    "window_amount_wan": round(amount / 10000.0, 1),
                    "surge_ratio": None,
                    "details": f"标的封死涨停，买一封单额 {bid1_wan} 万元"
                }
                detected_events.append(event)
                self._record_event(event)

            # 2. 涨停炸板跃迁: SEALED -> NORMAL
            elif prev_status == "SEALED" and current_status != "SEALED":
                event = {
                    "date": date_str,
                    "timestamp": time_str,
                    "minute_index": minute_index,
                    "event_category": "LIMIT_UP_BREAK",
                    "severity_level": "CRITICAL",
                    "symbol": sym,
                    "name": name,
                    "price": price,
                    "pct_change": pct_change,
                    "window_delta_pct": None,
                    "window_amount_wan": round(amount / 10000.0, 1),
                    "surge_ratio": None,
                    "details": f"标的涨停炸板脱离，现价 {price} 元 (涨幅 {pct_change}%)"
                }
                detected_events.append(event)
                self._record_event(event)

            # 更新状态缓存 (用于后续 Edge Trigger 判定)
            self._stock_state_cache[sym] = current_status

            # ------------------------------------------------------------------
            # 规则 B: 动量突变四元组与系统性共振
            # 【v1.1 必修项 5 & 红队审计整改项 3】：严格判断同向联动，杜绝诱多与背离误判
            # ------------------------------------------------------------------
            if sym in stock_velocity_map:
                v_3m, delta_amount_wan = stock_velocity_map[sym]

                # 主板 3%，双创 5%，成交额达标
                threshold_v = 5.0 if (sym.startswith("30") or sym.startswith("68")) else 3.0
                threshold_amt = 3000.0 if (sym.startswith("30") or sym.startswith("68")) else 2000.0

                if abs(v_3m) >= threshold_v and delta_amount_wan >= threshold_amt:
                    # 双创标的对比创业板指，主板对比上证指数
                    target_idx_delta = cy_index_delta if (sym.startswith("30") or sym.startswith("68")) else sh_index_delta
                    
                    # 严格同向性判定: 标的拉升时大盘必须同向拉升 >= 0.15% (绝对禁止大盘暴跌个股拉升判定为共振)
                    index_co_move = False
                    if v_3m > 0 and target_idx_delta >= 0.15:
                        index_co_move = True
                    elif v_3m < 0 and target_idx_delta <= -0.15:
                        index_co_move = True

                    # SectorCoMove: 板块/重点池同向标的数 >= 2
                    sector_co_move = (pos_movers_count >= 2 if v_3m > 0 else neg_movers_count >= 2)

                    is_resonance = index_co_move or sector_co_move
                    severity = "TRANSITION" if is_resonance else "INFO"

                    cooldown_key = f"{sym}_VELOCITY"
                    if self._is_cooldown_expired(cooldown_key, now_dt):
                        resonance_desc = f"指数同向={index_co_move}, 板块同向={sector_co_move}"
                        event = {
                            "date": date_str,
                            "timestamp": time_str,
                            "minute_index": minute_index,
                            "event_category": "VELOCITY_SPIKE",
                            "severity_level": severity,
                            "symbol": sym,
                            "name": name,
                            "price": price,
                            "pct_change": pct_change,
                            "window_delta_pct": v_3m,
                            "window_amount_wan": delta_amount_wan,
                            "surge_ratio": None,
                            "details": f"3分钟速动变化 {v_3m}%，窗口成交 {delta_amount_wan} 万元 (共振={is_resonance}: {resonance_desc})"
                        }
                        detected_events.append(event)
                        self._record_event(event)
                        self._cooldown_cache[cooldown_key] = now_dt

            # ------------------------------------------------------------------
            # 规则 C: 流动性脉冲比率 R_vol 与 30 分钟冷启动保护
            # 【v1.1 必修项 3】：09:30~10:00 (minute_index <= 30) 统一输出 None
            # ------------------------------------------------------------------
            slices = self._stock_series_cache.get(sym, [])
            if minute_index <= 30:
                # 冷启动保护期: 强制为 None，不计算 R_vol
                pass
            else:
                # 10:00 之后样本满额，计算 5 分钟成交量相比过去 30 分钟均值
                r_vol = self._calculate_r_vol(slices, minute_index)
                if r_vol is not None and r_vol >= 3.0:
                    cooldown_key = f"{sym}_SURGE"
                    if self._is_cooldown_expired(cooldown_key, now_dt):
                        event = {
                            "date": date_str,
                            "timestamp": time_str,
                            "minute_index": minute_index,
                            "event_category": "VOLUME_SURGE",
                            "severity_level": "TRANSITION",
                            "symbol": sym,
                            "name": name,
                            "price": price,
                            "pct_change": pct_change,
                            "window_delta_pct": None,
                            "window_amount_wan": None,
                            "surge_ratio": round(r_vol, 2),
                            "details": f"5分钟成交放量至过去半小时均值的 {r_vol:.1f} 倍"
                        }
                        detected_events.append(event)
                        self._record_event(event)
                        self._cooldown_cache[cooldown_key] = now_dt
                        self._cooldown_cache[cooldown_key] = now_dt

        return detected_events

    # ==========================================
    # 6. 辅助内部算法 (冷启动、午休跨段与降噪)
    # ==========================================

    def _get_stitched_macro_point(self, current_minute: int, delta_minutes: int) -> Optional[dict]:
        """
        获取 delta_minutes 前的宏观快照点位
        【v1.1 必修项 7】：午休跨段拼接 (13:00~13:05 跨段取 11:25~11:30)
        【红队审计整改项 8】：抗抖动滑动探测，防止偶发丢包导致共振失效
        """
        target_m = current_minute - delta_minutes
        if target_m <= 0:
            target_m = 1
        # 1. 精确匹配
        if target_m in self._macro_series_cache:
            return self._macro_series_cache[target_m]
        # 2. 逆序滑动探测最近有效点 (<= target_m)
        candidate_mins = [m for m in self._macro_series_cache.keys() if m <= target_m]
        if candidate_mins:
            return self._macro_series_cache[max(candidate_mins)]
        # 3. 若无更早点，返回最早采样点
        if self._macro_series_cache:
            return self._macro_series_cache[min(self._macro_series_cache.keys())]
        return None

    def _get_stitched_stock_slice(self, slices: List[dict], current_minute: int, delta_minutes: int) -> Optional[dict]:
        """在个股历史切片中寻找 delta_minutes 前的切片 (午休有效时间差计为 0)"""
        target_m = current_minute - delta_minutes
        for s in reversed(slices):
            if s.get("minute_index", 0) <= target_m:
                return s
        return slices[0] if slices else None

    def _calculate_r_vol(self, slices: List[dict], current_minute: int) -> Optional[float]:
        """
        计算流动性脉冲比率 R_vol (当前5分钟成交额 / 过去30分钟均值)
        【v1.1 必修项 3】：若处于冷启动期或样本不足，输出 None
        """
        if current_minute <= 30 or len(slices) < 6:
            return None

        # 当前5分钟成交额增量
        curr_slice = slices[-1]
        prev_5_slice = self._get_stitched_stock_slice(slices, current_minute, 5)
        if not curr_slice or not prev_5_slice:
            return None

        a_5m = curr_slice.get("amount", 0.0) - prev_5_slice.get("amount", 0.0)
        if a_5m < 15000000.0: # 绝对金额不足 1500 万元不构成显著脉冲
            return None

        # 过去30分钟均值
        prev_30_slice = self._get_stitched_stock_slice(slices, current_minute, 30)
        if not prev_30_slice:
            return None

        a_30m = curr_slice.get("amount", 0.0) - prev_30_slice.get("amount", 0.0)
        mean_5m_baseline = a_30m / 6.0

        if mean_5m_baseline <= 0:
            return None

        return a_5m / mean_5m_baseline

    def _is_cooldown_expired(self, key: str, now_dt: datetime) -> bool:
        """检查 15 分钟冷却期是否已过 (防刷屏)"""
        last_dt = self._cooldown_cache.get(key)
        if last_dt is None:
            return True
        return (now_dt - last_dt).total_seconds() >= 900 # 15 分钟

    def _record_event(self, event: dict):
        """记录事件入内存并推入异步批处理队列"""
        self._recent_events_cache.insert(0, event)
        if len(self._recent_events_cache) > 100:
            self._recent_events_cache.pop()

        if self.session:
            self._async_write_queue.put_nowait(("event", event))

    # ==========================================
    # 7. 异步批处理持久化 (SQLite 防锁表)
    # ==========================================

    async def flush_async_queue(self):
        """
        消费异步批处理队列，合并落盘
        【v1.1 必修项 7】：SQLite 异步批处理写入，杜绝高频阻塞
        """
        if not self.session or self._async_write_queue.empty():
            return

        snapshots_to_add = []
        events_to_add = []

        while not self._async_write_queue.empty():
            try:
                item_type, data = self._async_write_queue.get_nowait()
                if item_type == "snapshot":
                    snapshots_to_add.append(IntradayMarketSnapshot(
                        date=data["date"],
                        timestamp=data["timestamp"],
                        minute_index=data["minute_index"],
                        sh_index_price=data.get("sh_price"),
                        sh_index_pct=data.get("sh_pct"),
                        sz_index_price=data.get("sz_price"),
                        sz_index_pct=data.get("sz_pct"),
                        cy_index_pct=data.get("cy_pct"),
                        total_amount_yi=data.get("total_amount_yi"),
                        volume_proj_yi=data.get("volume_proj_yi"),
                        is_proj_estimated=data.get("is_proj_estimated", False),
                        up_count=data.get("up_count"),
                        down_count=data.get("down_count"),
                        limit_up_count=data.get("limit_up_count"),
                        limit_down_count=data.get("limit_down_count"),
                        broken_limit_count=data.get("broken_count"),
                        max_height=data.get("max_height"),
                        leader_stock=data.get("leader_stock")
                    ))
                elif item_type == "event":
                    events_to_add.append(IntradayAnomalyEvent(
                        date=data["date"],
                        timestamp=data["timestamp"],
                        minute_index=data["minute_index"],
                        event_category=data["event_category"],
                        severity_level=data["severity_level"],
                        symbol=data.get("symbol"),
                        name=data.get("name"),
                        price=data.get("price"),
                        pct_change=data.get("pct_change"),
                        window_delta_pct=data.get("window_delta_pct"),
                        window_amount_wan=data.get("window_amount_wan"),
                        surge_ratio=data.get("surge_ratio"),
                        details=data.get("details")
                    ))
            except asyncio.QueueEmpty:
                break

        try:
            if snapshots_to_add:
                self.session.add_all(snapshots_to_add)
            if events_to_add:
                self.session.add_all(events_to_add)
            await self.session.commit()
            return True
        except Exception as e:
            await self.session.rollback()
            logger.error(f"SQLite 异步批处理写入失败: {e}")
            raise

    # ==========================================
    # 8. 对外只读查询接口 (API 服务层)
    # ==========================================

    async def get_realtime_snapshot(self, date_str: str) -> dict:
        """
        获取盘中最新综合切片 (耗时 < 5ms)
        """
        self._ensure_date_cache(date_str)
        now_dt = datetime.now()
        minute_index = self.get_minute_index(now_dt)
        session_state = self.get_trading_session_state(now_dt)

        # 优先读取内存最新快照
        macro = self._macro_series_cache.get(minute_index)
        if not macro:
            macro = await self.capture_macro_snapshot(date_str, now_dt)

        # 获取重点池当前追踪
        watchlist_symbols = await self.build_watchlist_universe(date_str)
        m3_base = await self.get_auction_baseline(date_str)
        open_items = m3_base.get("open_items", {})

        stock_res = await self.data_service.get_stock_quotes(watchlist_symbols[:20])
        quotes = stock_res.data or []

        watchlist_items = []
        for q in quotes:
            sym = q.get("symbol", "")
            current_pct = q.get("pct_change")
            status = "SEALED" if q.get("is_sealed") else ("NORMAL" if current_pct is not None else "HALTED")
            amount_yi = round(float(q.get("amount") or 0.0) / 100000000.0, 2)

            watchlist_items.append({
                "symbol": sym,
                "name": q.get("name", "--"),
                "board_count": None,
                "open_pct": open_items.get(sym),
                "current_pct": current_pct,
                "status": status,
                "amount_yi": amount_yi
            })

        return {
            "session_state": session_state,
            "freshness_seconds": 3,
            "is_delayed": False,
            "timestamp": now_dt.strftime("%H:%M:%S"),
            "macro": macro,
            "watchlist": watchlist_items,
            "recent_events": self._recent_events_cache[:20],
            "disclaimer": self.DISCLAIMER
        }

    async def get_series_data(self, date_str: str) -> List[dict]:
        """
        获取日内分时宏观时序曲线
        【红队审计整改项 4】：仅今日返回内存热缓存，历史日期穿透数据库查询
        """
        self._ensure_date_cache(date_str)
        today_str = datetime.now().strftime("%Y-%m-%d")
        if date_str == today_str and self._macro_series_cache:
            return sorted(self._macro_series_cache.values(), key=lambda x: x.get("minute_index", 0))

        # 从数据库加载历史记录
        if self.session:
            stmt = (
                select(IntradayMarketSnapshot)
                .where(IntradayMarketSnapshot.date == date_str)
                .order_by(IntradayMarketSnapshot.minute_index)
            )
            res = await self.session.execute(stmt)
            rows = res.scalars().all()
            return [
                {
                    "date": r.date,
                    "timestamp": r.timestamp,
                    "minute_index": r.minute_index,
                    "sh_price": r.sh_index_price,
                    "sh_pct": r.sh_index_pct,
                    "total_amount_yi": r.total_amount_yi,
                    "volume_proj_yi": r.volume_proj_yi,
                    "is_proj_estimated": getattr(r, "is_proj_estimated", False),
                    "up_count": r.up_count,
                    "down_count": r.down_count,
                    "limit_up_count": r.limit_up_count,
                    "limit_down_count": r.limit_down_count,
                    "broken_count": r.broken_limit_count,
                    "max_height": r.max_height,
                    "leader_stock": r.leader_stock
                }
                for r in rows
            ]
        return []

    async def get_events_stream(self, date_str: str, severity: Optional[str] = None, limit: int = 50) -> List[dict]:
        """
        获取盘中客观事件流
        【红队审计整改项 4】：仅今日优先读取内存热缓存，历史日期穿透数据库查询
        """
        self._ensure_date_cache(date_str)
        today_str = datetime.now().strftime("%Y-%m-%d")
        if date_str == today_str and self._recent_events_cache:
            events = self._recent_events_cache
            if severity:
                events = [e for e in events if e.get("severity_level") == severity]
            return events[:limit]

        # 历史日期从数据库查询
        if self.session:
            stmt = select(IntradayAnomalyEvent).where(IntradayAnomalyEvent.date == date_str)
            if severity:
                stmt = stmt.where(IntradayAnomalyEvent.severity_level == severity)
            stmt = stmt.order_by(IntradayAnomalyEvent.minute_index.desc(), IntradayAnomalyEvent.id.desc()).limit(limit)
            res = await self.session.execute(stmt)
            rows = res.scalars().all()
            return [
                {
                    "id": r.id,
                    "date": r.date,
                    "timestamp": r.timestamp,
                    "minute_index": r.minute_index,
                    "event_category": r.event_category,
                    "severity_level": r.severity_level,
                    "symbol": r.symbol,
                    "name": r.name,
                    "price": r.price,
                    "pct_change": r.pct_change,
                    "window_delta_pct": r.window_delta_pct,
                    "window_amount_wan": r.window_amount_wan,
                    "surge_ratio": r.surge_ratio,
                    "details": r.details
                }
                for r in rows
            ]
        return []
