#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知见系统 · 无人值守交易时钟与双轨撮合执行引擎 (AutonomousJobEngine)
实现全自动闭环：
1. 09:26 竞价策略计算 ➔ 生成待执行候选并预埋入双轨缓冲队列 (09:25-09:29:50 预留一票否决)
2. 09:30 开盘真实滑点撮合成交 (0.1% 滑点、一字板流动性锁定过滤)
3. 盘中波普尔刚性风控守护机 (触及 -5% 止损、次日低开抢跑、持股到期无条件平仓)
4. 15:05 盘后净值对账与清算结算
5. 包含 replay_single_day 历史单日全时钟全真倍速回放验证器 (原生支持 Parquet 离线回放)
"""

import logging
import asyncio
from collections import deque
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd
from fastapi import HTTPException

from ..config import DATA_DIR, PROJECT_ROOT
from ..core.calendar import calendar, CalendarCoverageError
from ..models.simulation import SimAccount, SimPosition, SimTrade
from ..schemas.simulation import SimTradeCreate
from ..services.selection import SelectionService
from ..services.simulation import SimulationService
from ..data.service import DataService
from ..data.capabilities import DataQuality, Freshness

logger = logging.getLogger(__name__)

class AutonomousJobEngine:
    """无人值守交易时钟与双轨执行引擎"""

    def __init__(
        self,
        session: AsyncSession,
        simulation_service: Optional[SimulationService] = None,
        data_service: Optional[Any] = None
    ):
        self.session = session
        self.selection_service = SelectionService(session)
        self.simulation_service = simulation_service or SimulationService(session)
        self.data_service = data_service or DataService(session)
        self.last_liquidated_trades: List[Dict[str, Any]] = []

        # 定位 Parquet 历史数据目录
        hist_candidates = [
            DATA_DIR / "historical",
            PROJECT_ROOT / "data" / "historical",
            Path("data/historical").resolve(),
            Path("/app/data/historical"),
        ]
        self.hist_dir = next((c for c in hist_candidates if c.exists() and (c / "zt_ladder_pool_2023_2026.parquet").exists()), DATA_DIR / "historical")
        self.daily_parquet = self.hist_dir / "a_share_daily_2023_2026.parquet"
        self.pool_parquet = self.hist_dir / "zt_ladder_pool_2023_2026.parquet"

    # =========================================================================
    # 0. 历史数据支撑辅助 (支持离线倍速穿透回放)
    # =========================================================================
    def _get_historical_candidates(self, target_date: str) -> List[Dict[str, Any]]:
        """从高质量 Parquet 底座提取指定历史日期的达标候选 (供回放与验证)"""
        if not (self.pool_parquet.exists() and self.daily_parquet.exists()):
            return []
        try:
            df_pool = pd.read_parquet(self.pool_parquet)
            df_daily = pd.read_parquet(self.daily_parquet)

            all_dates = sorted(df_pool["date"].unique().tolist())
            if target_date not in all_dates:
                return []
            d_idx = all_dates.index(target_date)
            if d_idx == 0:
                return []
            prev_date = all_dates[d_idx - 1]

            prev_pool = df_pool[df_pool["date"] == prev_date]
            today_daily = df_daily[df_daily["date"] == target_date].set_index("code").to_dict("index")

            cands = []
            # 策略：弱转强竞价抢筹
            for _, row in prev_pool.iterrows():
                code = row["code"]
                bar = today_daily.get(code)
                if not bar or bar.get("open", 0) <= 0:
                    continue
                open_p = bar["open"]
                close_p = row["close"]
                open_pct = round((open_p - close_p) / close_p * 100.0, 2)
                lbc = int(row.get("lbc") or 1)
                is_broken = bool(row.get("is_broken", False))

                if 1.5 <= open_pct <= 5.5:
                    score = round(78.0 + lbc * 5.0 + open_pct * 2.0 + (5.0 if is_broken else 0.0), 1)
                    cands.append({
                        "code": code,
                        "name": row["name"],
                        "score": score,
                        "current_price": open_p,
                        "open_pct": open_pct,
                        "volume_ratio": 13.5,
                        "strat_name": "弱转强竞价抢筹"
                    })

            cands.sort(key=lambda x: x["score"], reverse=True)
            return cands[:2]
        except Exception as e:
            logger.warning(f"Parquet 离线候选提取异常: {e}")
            return []

    def _get_historical_quotes(self, codes: List[str], target_date: str) -> Dict[str, Dict[str, Any]]:
        """从 Parquet 提取历史日期的真实开高低收价格"""
        if not self.daily_parquet.exists():
            return {}
        try:
            df_daily = pd.read_parquet(self.daily_parquet)
            subset = df_daily[(df_daily["date"] == target_date) & (df_daily["code"].isin(codes))]
            quotes = {}
            for _, r in subset.iterrows():
                quotes[r["code"]] = {
                    "open": r["open"],
                    "high": r["high"],
                    "low": r["low"],
                    "price": r["close"],
                    "open_pct": r.get("pct_change", 0.0),
                    "limit_up": round(r["open"] * 1.10, 2)  # 估算涨停参考
                }
            return quotes
        except Exception as e:
            logger.warning(f"Parquet 离线行情提取异常: {e}")
            return {}

    # =========================================================================
    # 1. 09:26 早盘竞价策略计算与待否决指令预埋 (Morning Strategy Pipeline)
    # =========================================================================
    async def run_morning_strategy_pipeline(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        09:26:00 执行竞价策略推演，将候选标的转化为待撮合买入指令（进入双轨否决窗口）
        """
        now = datetime.now()
        date_str = target_date or now.strftime("%Y-%m-%d")

        # 1. 时效性防呆保护 (Stale Guard)
        if not target_date and (now.hour > 9 or (now.hour == 9 and now.minute > 29)):
            logger.warning(f"09:26 竞价任务触发延迟 (当前时间 {now.strftime('%H:%M:%S')} > 09:29:30)，触发 EXPIRED_SKIPPED 保护，严禁追高下单！")
            return {
                "status": "SKIPPED_STALE",
                "message": "任务超出 09:29:30 最晚时效门槛，已自动废弃以防盘中盲目追高",
                "orders_generated": 0
            }

        # 2. 获取候选标的 (实盘走实时推演，历史回放走离线 Parquet)
        candidates = []
        if target_date:
            candidates = self._get_historical_candidates(target_date)
            market_stage = "REPAIR"
        else:
            eval_res = await self.selection_service.evaluate_classic_strategies(date=date_str)
            market_stage = eval_res.get("market_stage", "REPAIR")
            if market_stage == "PANIC":
                logger.info(f"[{date_str}] 大盘情绪处于退潮恐慌期 (PANIC)，策略准入闸门全关闭，禁止任何开仓！")
                return {
                    "status": "GATE_BLOCKED",
                    "market_stage": market_stage,
                    "message": "大盘退潮期硬关闸，防守空仓",
                    "orders_generated": 0
                }
            for strat in eval_res.get("strategies", []):
                s_name = strat.get("name", "经典策略")
                for cand in strat.get("candidates", []):
                    score = float(cand.get("score") or 0.0)
                    open_pct = float(cand.get("open_pct") or 0.0)
                    vol_ratio = float(cand.get("volume_ratio") or 0.0)
                    if score >= 80.0 and 1.0 <= open_pct <= 6.0 and vol_ratio >= 8.0:
                        cand["strat_name"] = s_name
                        candidates.append(cand)
            candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
            candidates = candidates[:2]

        if not candidates:
            logger.info(f"[{date_str}] 09:26 竞价扫描完毕，全市场无满足严苛门禁的触发标的。")
            return {
                "status": "NO_CANDIDATE",
                "message": "今日无符合条件的候选标的",
                "orders_generated": 0
            }

        # 3. 账户资金风控与挂单生成
        account = await self.simulation_service.get_or_create_default_account()
        positions = await self.simulation_service.get_positions(refresh_quote=False)

        if len(positions) >= 5:
            logger.info(f"[{date_str}] 模拟持仓已达上限 5 只，禁止新增建仓。")
            return {
                "status": "MAX_POSITIONS_REACHED",
                "message": "持仓数量已达 5 只上限，禁止加仓",
                "orders_generated": 0
            }

        total_assets = account.current_capital + sum(p.market_value for p in positions)
        max_single_budget = min(total_assets * 0.20, account.current_capital)

        queued_orders = []
        for cand in candidates:
            code = cand.get("code")
            name = cand.get("name")
            cur_p = float(cand.get("current_price") or 10.0)
            if cur_p <= 0:
                continue

            if any(p.code == code for p in positions):
                continue

            budget = max_single_budget
            raw_shares = int(budget / cur_p)
            shares = (raw_shares // 100) * 100
            if shares < 100 or (shares * cur_p) > account.current_capital:
                continue

            order_info = {
                "code": code,
                "name": name,
                "direction": "buy",
                "price": cur_p,
                "quantity": shares,
                "trade_time": f"{date_str} 09:26:00",
                "decision_summary": f"[双轨待决] {cand.get('strat_name')} (评分{cand.get('score')}) · 09:26 竞价高开{cand.get('open_pct')}%"
            }
            queued_orders.append(order_info)

        logger.info(f"[{date_str}] 09:26 预埋 {len(queued_orders)} 笔指令进入双轨缓冲窗口 (09:25~09:29:50 待决)")
        return {
            "status": "QUEUED_FOR_VETO",
            "orders": queued_orders,
            "orders_generated": len(queued_orders),
            "veto_deadline": f"{date_str} 09:29:50"
        }

    # =========================================================================
    # 2. 09:30 开盘真实滑点撮合成交 (Open Market Execution)
    # =========================================================================
    async def execute_open_market_match(self, queued_orders: List[Dict[str, Any]], target_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        09:30:00 开盘撮合：对未被交易员否决的预埋指令以真实开盘价 + 0.1% 滑点自动撮合
        """
        if not queued_orders:
            return []

        now_str = target_date or datetime.now().strftime("%Y-%m-%d")
        # 严格执行交易日历覆盖范围核验：日历未覆盖年份主动抛出 CalendarCoverageError 刚性阻断自动撮合
        try:
            calendar.check_coverage(now_str)
        except CalendarCoverageError as e:
            logger.error(f"[{now_str}] 交易日历未覆盖年份，阻断自动开盘撮合: {e}")
            raise

        if not calendar.is_trading_day(now_str, enforce_coverage=True):
            logger.info(f"[{now_str}] 非交易日，跳过自动开盘撮合。")
            return []

        executed_trades = []
        symbols = [o["code"] for o in queued_orders]

        # 行情获取：历史回放读 Parquet，实盘读实时接口
        quotes_map = {}
        if target_date:
            quotes_map = self._get_historical_quotes(symbols, target_date)
        else:
            try:
                quotes_resp = await self.data_service.get_stock_quotes(symbols)
                if quotes_resp and quotes_resp.data:
                    for q in quotes_resp.data:
                        c = q.get("code") or q.get("symbol")
                        if c:
                            quotes_map[c.replace("sh", "").replace("sz", "").replace("bj", "")] = q
            except Exception as e:
                logger.warning(f"获取开盘实时快照异常: {e}")

        for order in queued_orders:
            code = order["code"]
            q = quotes_map.get(code, {})
            open_p = float(q.get("open") or q.get("price") or order["price"])
            limit_up = float(q.get("limit_up") or 0.0)

            # 流动性真实约束：开盘即一字涨停无法排进
            if limit_up > 0 and open_p >= limit_up:
                logger.info(f"[{code} {order['name']}] 开盘一字涨停无法买入，触发 REASON_LIMIT_UP_LOCKED 废弃指令！")
                continue

            # 加上 0.1% 买入冲击滑点
            match_price = round(open_p * 1.001, 2)

            try:
                trade_payload = SimTradeCreate(
                    code=code,
                    name=order["name"],
                    direction="buy",
                    price=match_price,
                    quantity=order["quantity"],
                    trade_time=f"{now_str} 09:30:00",
                    decision_summary=order["decision_summary"].replace("[双轨待决]", "[自动撮合建仓]")
                )
                res = await self.simulation_service.execute_trade(trade_payload)
                executed_trades.append({
                    "code": code,
                    "name": order["name"],
                    "match_price": match_price,
                    "quantity": order["quantity"],
                    "status": "FILLED"
                })
                logger.info(f"✅ 09:30 自动撮合成交: {order['name']} ({code}) 买入 {order['quantity']}股 @ ￥{match_price}")
            except Exception as err:
                logger.error(f"09:30 撮合买入失败 [{code}]: {err}")

        return executed_trades

    # =========================================================================
    # 3. 盘中波普尔刚性风控守护机 (Popper Risk Guardian Daemon)
    # =========================================================================
    @staticmethod
    def _validate_quote_freshness(
        q: Dict[str, Any],
        date_str: str,
        now: datetime,
        max_age_seconds: int = 300
    ) -> Tuple[bool, str]:
        """
        严格核验单标的行情源时间、交易日与最大时差 (秒级时效防线):
        1. 拒绝日期缺失、时间缺失、未知来源行情
        2. 拒绝格式错误、非法日期
        3. 拒绝历史早于当天 (陈旧行情) 与晚于当天 (未来异常日期)
        4. 拒绝同日采样时差超限 (同日过期行情) 与超前当前时间超限 (未来异常时间)
        """
        from datetime import timedelta
        raw_date = q.get("date") or q.get("trade_date")
        raw_time = q.get("time") or q.get("servertime")

        if not raw_date or not str(raw_date).strip():
            return False, "行情来源日期缺失 (missing trade_date)"

        q_date_str = str(raw_date).strip()
        if len(q_date_str) == 8 and q_date_str.isdigit():
            q_date_str = f"{q_date_str[:4]}-{q_date_str[4:6]}-{q_date_str[6:8]}"
        else:
            q_date_str = q_date_str[:10]

        try:
            datetime.strptime(q_date_str, "%Y-%m-%d")
        except Exception:
            return False, f"行情来源日期格式非法: {raw_date}"

        if q_date_str < date_str:
            return False, f"行情来源日期 ({q_date_str}) 早于当前巡检日期 ({date_str})，属于历史过期行情"
        if q_date_str > date_str:
            return False, f"行情来源日期 ({q_date_str}) 晚于当前巡检日期 ({date_str})，属于未来异常日期"

        if not raw_time or not str(raw_time).strip():
            return False, "行情采样时间缺失 (missing timestamp)"

        q_time_str = str(raw_time).strip()
        if " " in q_time_str:
            q_time_part = q_time_str.split(" ", 1)[1]
        else:
            q_time_part = q_time_str

        time_clean = q_time_part.split(".")[0]
        try:
            q_datetime = datetime.strptime(f"{q_date_str} {time_clean}", "%Y-%m-%d %H:%M:%S")
        except Exception:
            return False, f"行情时间戳解析失败: {raw_time}"

        if now.tzinfo is not None and q_datetime.tzinfo is None:
            q_datetime = q_datetime.replace(tzinfo=now.tzinfo)
        elif now.tzinfo is None and q_datetime.tzinfo is not None:
            now = now.replace(tzinfo=q_datetime.tzinfo)
        diff_sec = (now - q_datetime).total_seconds()
        if diff_sec < 0:
            return False, f"行情采样时间 ({q_datetime}) 超前于当前时间 ({now})，属于未来异常行情"
        if diff_sec > max_age_seconds:
            return False, f"行情采样时间 ({q_datetime}) 距当前 ({now}) 延迟达 {int(diff_sec)} 秒 (> {max_age_seconds}s)，属于同日过期行情"

        return True, "OK"

    async def run_intraday_risk_guard(self, target_date: Optional[str] = None, now_dt: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """
        盘中风控巡检守护：向后兼容接口，返回全部事件流水列表 (含 LIQUIDATED, T1_PROTECTED, LEDGER_ANOMALY 等)
        """
        detailed = await self.run_intraday_risk_guard_detailed(target_date=target_date, now_dt=now_dt)
        return detailed.get("events", [])

    async def run_intraday_risk_guard_detailed(self, target_date: Optional[str] = None, now_dt: Optional[datetime] = None, quotes_result: Optional[Any] = None) -> Dict[str, Any]:
        """
        盘中风控巡检守护 (带结构化执行诊断状态与标的覆盖追踪)：
        1. 触及 -5% 刚性硬止损红线 ➔ 立即市价平仓
        2. 次日竞价大幅低开超过 -2.5% ➔ 逻辑被证伪立即平仓
        3. 持仓周期到期 ➔ 尾盘 14:55 刚性出局 (严格 T+1 与账本校验)
        严格执行行情有效性与新鲜度铁律：
        - 质量必须为 FULL 或 PARTIAL (DEGRADED/INVALID/UNAVAILABLE/FAILED 坚决拒绝)
        - 新鲜度必须为 REALTIME (STALE/EXPIRED/DELAYED/UNAVAILABLE/缺失 坚决拒绝)
        - 单标的市价缺失或 <=0 时跳过该标的，严禁拿成本价作为平仓成交价
        - 准确追踪未检查标的与安全标的，杜绝部分标的缺行情时虚报“全部持仓安全”
        """
        if target_date and not now_dt:
            try:
                target_d = datetime.strptime(target_date, "%Y-%m-%d").date()
                now = datetime.combine(target_d, dtime(14, 30, 0))
            except Exception:
                now = datetime.now()
        else:
            now = now_dt or datetime.now()
        date_str = target_date or now.strftime("%Y-%m-%d")

        if hasattr(self.data_service, "current_now"):
            self.data_service.current_now = now
        if hasattr(self.data_service, "current_date"):
            self.data_service.current_date = date_str

        try:
            calendar.check_coverage(date_str)
        except CalendarCoverageError as e:
            logger.error(f"[{date_str}] 交易日历未覆盖年份，阻断自动风控巡检: {e}")
            raise

        if not calendar.is_trading_day(date_str, enforce_coverage=True):
            logger.info(f"[{date_str}] 非交易日，跳过自动风控巡检。")
            return {
                "status": "NON_TRADING_DAY",
                "reason": f"[{date_str}] 非交易日，跳过风控巡检",
                "events": [],
                "actual_liquidations": [],
                "protected_events": [],
                "ledger_events": [],
                "missing_quotes": [],
                "checked_symbols": [],
                "quotes_quality": "N/A",
                "quotes_freshness": "N/A",
                "quality_log_success": True
            }

        account = await self.simulation_service.get_or_create_default_account()
        account_id = int(account.id)
        stmt = select(SimPosition).where(SimPosition.account_id == account_id, SimPosition.quantity > 0)
        positions = list((await self.session.execute(stmt)).scalars().all())

        if not positions:
            return {
                "status": "NO_POSITIONS",
                "reason": "当前无在持仓位，无需风控巡检",
                "events": [],
                "actual_liquidations": [],
                "protected_events": [],
                "ledger_events": [],
                "missing_quotes": [],
                "checked_symbols": [],
                "quotes_quality": "N/A",
                "quotes_freshness": "N/A",
                "quality_log_success": True
            }

        symbols = [p.code for p in positions]
        quotes_map = {}
        quotes_resp = quotes_result
        quotes_quality = None
        quotes_freshness = None
        quotes_error = None
        has_valid_quotes = False
        quotes_quality_log_success = True

        if target_date and not quotes_result:
            quotes_map = self._get_historical_quotes(symbols, target_date)
            if quotes_map:
                has_valid_quotes = True
                quotes_quality = DataQuality.FULL
                quotes_freshness = Freshness.REALTIME

        # 若历史底层未命中（或实时环境/离线注入测试），从 data_service 补充行情或使用注入的 quotes_result
        if not quotes_map:
            if quotes_result:
                quotes_resp = quotes_result
            elif self.data_service:
                if hasattr(self.data_service, "current_now") and self.data_service.current_now is None:
                    self.data_service.current_now = now
                if hasattr(self.data_service, "current_date") and self.data_service.current_date is None:
                    self.data_service.current_date = today
                try:
                    try:
                        quotes_resp = await self.data_service.get_stock_quotes(symbols, reference_now=now)
                    except TypeError:
                        quotes_resp = await self.data_service.get_stock_quotes(symbols)
                except Exception as e:
                    logger.warning(f"风控巡检获取行情异常: {e}")
                    quotes_error = str(e)
                    quotes_quality = DataQuality.FAILED
                    quotes_freshness = Freshness.UNAVAILABLE

            if quotes_resp:
                quotes_quality = getattr(quotes_resp, "quality", None)
                quotes_freshness = getattr(quotes_resp, "freshness", None)
                quotes_error = getattr(quotes_resp, "error_message", None)
                q_log_succ = getattr(quotes_resp, "quality_log_success", True)
                quotes_quality_log_success = True if q_log_succ is None else bool(q_log_succ)

                orig_q = getattr(quotes_resp, "original_quality", quotes_quality)
                # 严格实时性与质量铁律：
                # 1. 质量必须明确为 FULL 或 PARTIAL，或者来源切换至备用源 (fallback_used=True, DEGRADED) 但原始质量必须确证合格为 FULL/PARTIAL 且新鲜度为 REALTIME 且非 STALE 快照
                # 2. 原生明确为 DEGRADED 的备用数据严禁用于风控平仓！
                # 3. 新鲜度必须存在且明确为 REALTIME (STALE/EXPIRED/DELAYED/UNAVAILABLE/缺失 坚决拒绝)
                is_fallback_realtime = (
                    quotes_quality == DataQuality.DEGRADED
                    and getattr(quotes_resp, "fallback_used", False)
                    and quotes_freshness == Freshness.REALTIME
                    and orig_q in (DataQuality.FULL, DataQuality.PARTIAL)
                )
                is_quality_valid = (quotes_quality in (DataQuality.FULL, DataQuality.PARTIAL)) or is_fallback_realtime
                is_freshness_valid = (quotes_freshness == Freshness.REALTIME)

                if is_quality_valid and is_freshness_valid and getattr(quotes_resp, "data", None):
                    for q in quotes_resp.data:
                        c = q.get("code") or q.get("symbol")
                        if c:
                            clean_c = c.replace("sh", "").replace("sz", "").replace("bj", "")
                            p_val = float(q.get("price") or 0.0)
                            if p_val > 0:
                                quotes_map[clean_c] = q
                                quotes_map[c] = q
                    has_valid_quotes = bool(quotes_map)
                else:
                    if not quotes_error:
                        quotes_error = f"行情质量或新鲜度不合规 (quality={quotes_quality}, freshness={quotes_freshness})"
                    logger.warning(
                        f"风控巡检拦截：行情质量或新鲜度不合规 "
                        f"(quality={quotes_quality}, freshness={quotes_freshness}, error={quotes_error})"
                    )
            elif not quotes_error:
                quotes_error = "行情接口无有效数据返回"

        # 若行情无效、过期、缺失或全部标的无有效市价，明确跳过并杜绝伪造成交
        if not has_valid_quotes:
            q_str = str(quotes_quality) if quotes_quality is not None else "NONE"
            f_str = str(quotes_freshness) if quotes_freshness is not None else "NONE"
            skip_msg = f"行情数据无效或非实时 (quality={q_str}, freshness={f_str}, error={quotes_error})，风控巡检明确跳过，严禁伪造成交"
            logger.warning(skip_msg)
            return {
                "status": "SKIPPED",
                "reason": skip_msg,
                "events": [],
                "actual_liquidations": [],
                "protected_events": [],
                "ledger_events": [],
                "missing_quotes": symbols,
                "checked_symbols": [],
                "quotes_quality": q_str,
                "quotes_freshness": f_str,
                "quality_log_success": quotes_quality_log_success
            }

        # 提取纯字典持仓快照，彻底与 session ORM 解耦，杜绝 session.rollback() 后属性访问异常
        pos_snapshots = [
            {
                "code": p.code,
                "name": p.name or p.code,
                "quantity": int(p.quantity),
                "avg_cost": float(p.avg_cost),
                "current_price": float(p.current_price or p.avg_cost),
            }
            for p in positions
        ]

        liquidated_trades = []
        checked_symbols = []
        missing_quote_symbols = []
        failed_executions = []

        for pos_info in pos_snapshots:
            code = pos_info["code"]
            pos_name = pos_info["name"]
            orig_qty = pos_info["quantity"]
            pos_cost = pos_info["avg_cost"]
            clean_code = code.replace("sh", "").replace("sz", "").replace("bj", "")
            q = quotes_map.get(clean_code) or quotes_map.get(code)

            # 若单标的缺少行情或市价 <= 0，严格跳过该标的，绝不使用成本价伪造成交
            if not q or float(q.get("price") or 0.0) <= 0:
                logger.warning(f"标的 {code} 缺乏有效实时市价，跳过该标的风控检查，绝不使用成本价伪造成交")
                missing_quote_symbols.append(code)
                continue

            # 严格核验单标的行情源日期、采样时间与时差，杜绝历史、未来、同日过期及缺时间行情
            is_fresh, freshness_reason = self._validate_quote_freshness(q, date_str, now, max_age_seconds=300)
            if not is_fresh:
                logger.warning(
                    f"标的 {pos_name} ({code}) 行情时效校验未通过: {freshness_reason}，"
                    f"坚决拒绝伪造平仓！"
                )
                missing_quote_symbols.append(code)
                continue

            cur_price = float(q.get("price"))
            low_price = float(q.get("low") or cur_price)
            checked_symbols.append(code)

            # 浮亏比例
            loss_pct = round(((cur_price - pos_cost) / pos_cost) * 100.0, 2)
            exit_reason = ""

            # 规则 1: 触及 -5.0% 刚性止损
            if loss_pct <= -5.0:
                exit_reason = f"[波普尔硬止损] 浮亏触及 {loss_pct}% (<= -5.0% 熔断红线)"

            # 规则 2: 次日跳空大幅低开 (<= -2.5%)
            open_pct = float(q.get("open_pct") or 0.0)
            if open_pct <= -2.5 and not exit_reason:
                exit_reason = f"[次日竞价抢跑] 跳空低开 {open_pct}%，逻辑被证伪离场"

            # 规则 3: 回放测试或实际尾盘到期离场（严格按交易日历核算持股周期是否成熟）
            cur_time_str = now.strftime("%H:%M")
            is_eod_time = cur_time_str >= "14:55" or (bool(target_date) and now_dt is None)
            if exit_reason or is_eod_time:
                try:
                    await self.simulation_service.verify_ledger_integrity(account_id, code)
                except HTTPException as e:
                    if e.status_code != 409:
                        raise
                    reason = f"账本异常，风控平仓被阻断: {e.detail}"
                    logger.error(reason)
                    liquidated_trades.append({
                        "code": code, "name": pos_name, "action": "HOLD",
                        "status": "LEDGER_ANOMALY_HOLD", "trigger_reason": exit_reason or "持仓周期检查",
                        "quantity": 0, "sell_price": 0.0, "remaining_quantity": orig_qty,
                        "pnl_pct": loss_pct, "reason": reason,
                    })
                    continue
            if is_eod_time and not exit_reason:
                # 检查完整主账本是否存在真实超卖/无成本卖出异常（对齐 409 契约，阻断自动卖出）
                stmt_all = (
                    select(SimTrade)
                    .where(
                        SimTrade.account_id == account_id,
                        SimTrade.code == code
                    )
                    .order_by(SimTrade.id.asc())
                )
                all_ledger_trades = list((await self.session.execute(stmt_all)).scalars().all())
                full_pos = 0
                has_real_oversell = False
                for t in all_ledger_trades:
                    t_dir = (t.direction or "").lower().strip()
                    t_qty = int(t.quantity)
                    if t_dir == "buy":
                        full_pos += t_qty
                    elif t_dir == "sell":
                        if full_pos < t_qty:
                            has_real_oversell = True
                        full_pos -= t_qty

                if has_real_oversell:
                    logger.error(f"标的 {code} 完整主账本存在真实超卖异常，阻断持股周期到期离场")
                    has_mature_holding = False
                else:
                    stmt_trades = (
                        select(SimTrade)
                        .where(
                            SimTrade.account_id == account_id,
                            SimTrade.code == code,
                            SimTrade.trade_time <= f"{date_str} 23:59:59"
                        )
                        .order_by(SimTrade.id.asc())
                    )
                    time_trades = list((await self.session.execute(stmt_trades)).scalars().all())

                    lots = deque()
                    unmatched_gap_sells = 0
                    for t in time_trades:
                        t_dir = (t.direction or "").lower().strip()
                        t_qty = int(t.quantity)
                        if t_qty <= 0:
                            continue
                        if t_dir == "buy":
                            b_dt = datetime.strptime((t.trade_time or "")[:10], "%Y-%m-%d").date()
                            lots.append({"qty": t_qty, "buy_date": b_dt})
                        elif t_dir == "sell":
                            rem = t_qty
                            while rem > 0 and lots:
                                if lots[0]["qty"] <= rem:
                                    rem -= lots[0]["qty"]
                                    lots.popleft()
                                else:
                                    lots[0]["qty"] -= rem
                                    rem = 0
                            if rem > 0:
                                unmatched_gap_sells += rem

                    has_mature_holding = False
                    if unmatched_gap_sells == 0:
                        cur_date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
                        for lot in lots:
                            try:
                                calendar.check_coverage(lot["buy_date"])
                                next_trade_day = calendar.next_trading_day(lot["buy_date"])
                                calendar.check_coverage(next_trade_day)
                                if cur_date_obj >= next_trade_day:
                                    has_mature_holding = True
                                    break
                            except CalendarCoverageError as e:
                                logger.error(f"日历未覆盖年份，无法评估持仓成熟度: {e}")
                                raise

                if has_mature_holding:
                    exit_reason = "[持股周期到期] 短线持仓达 T+1 周期，尾盘刚性平仓"

            if exit_reason:
                # 检查当前实际可卖数量 (A 股 T+1 规则校验)
                as_of_trade_time = f"{date_str} 14:55:00" if target_date else f"{date_str} {now.strftime('%H:%M:%S')}"
                try:
                    avail_qty = await self.simulation_service.get_available_quantity(
                        account_id, code, as_of_time=as_of_trade_time
                    )
                except HTTPException as e:
                    if e.status_code == 409:
                        logger.error(
                            f"⚠️ 标的 {pos_name} ({code}) 账本存在真实超卖异常 (HTTP 409)，"
                            f"风控刚性阻断平仓操作: {e.detail}"
                        )
                        continue
                    raise

                if avail_qty <= 0:
                    logger.warning(
                        f"⚠️ 标的 {pos_name} ({code}) 触发风控 [{exit_reason}]，"
                        f"但受 A 股 T+1 规则限制当前可卖数量为 0 (当日买入仓位不可当日卖出)，记录触发并保留持仓。"
                    )
                    liquidated_trades.append({
                        "code": code,
                        "name": pos_name,
                        "action": "HOLD",
                        "status": "TRIGGERED_T1_PROTECTED",
                        "trigger_reason": exit_reason,
                        "quantity": 0,
                        "sell_price": 0.0,
                        "remaining_quantity": orig_qty,
                        "pnl_pct": loss_pct,
                        "reason": f"触发风控 [{exit_reason}]，但受 A 股 T+1 规则限制可卖数量为 0，保留持仓"
                    })
                    continue

                # 混合持仓 (昨日可卖仓 + 今日不可卖仓)：在持仓被成交函数更新前保存原始数量，仅平仓可卖数量，保留今日买入余量
                sell_qty = min(orig_qty, avail_qty)
                remaining_qty = orig_qty - sell_qty
                is_partial = sell_qty < orig_qty
                summary = exit_reason
                if is_partial:
                    summary += f" (T+1部分平仓: 可卖 {sell_qty} 股，今日不可卖余量 {remaining_qty} 股保留)"

                sell_price = round(cur_price * 0.999, 2)
                try:
                    sell_payload = SimTradeCreate(
                        code=code,
                        name=pos_name,
                        direction="sell",
                        price=sell_price,
                        quantity=sell_qty,
                        trade_time=as_of_trade_time,
                        decision_summary=summary
                    )
                    await self.simulation_service.execute_trade(sell_payload, allow_future=bool(target_date))
                    action_type = "PARTIAL_SELL" if is_partial else "SELL"
                    status_type = "PARTIAL_LIQUIDATED" if is_partial else "LIQUIDATED"
                    trade_record = {
                        "code": code,
                        "name": pos_name,
                        "action": action_type,
                        "status": status_type,
                        "trigger_reason": exit_reason,
                        "sell_price": sell_price,
                        "quantity": sell_qty,
                        "remaining_quantity": remaining_qty,
                        "pnl_pct": loss_pct,
                        "reason": summary
                    }
                    liquidated_trades.append(trade_record)
                    self.last_liquidated_trades = list(liquidated_trades)
                    logger.warning(f"🛑 触发风控平仓出局: {pos_name} ({code}) 卖出 {sell_qty}股 @ ￥{sell_price} | 原因: {summary}")
                except Exception as e:
                    logger.error(f"风控平仓执行失败 [{code}]: {e}")
                    if self.session:
                        try:
                            await self.session.rollback()
                        except Exception as rb_err:
                            logger.warning(f"Session rollback failed: {rb_err}")
                    failed_event = {
                        "code": code,
                        "name": pos_name,
                        "action": "ERROR",
                        "status": "EXECUTION_ERROR",
                        "trigger_reason": exit_reason,
                        "sell_price": 0.0,
                        "quantity": 0,
                        "remaining_quantity": orig_qty,
                        "pnl_pct": loss_pct,
                        "reason": f"风控平仓执行失败: {e}",
                        "error": str(e)
                    }
                    liquidated_trades.append(failed_event)
                    failed_executions.append(failed_event)
                    self.last_liquidated_trades = list(liquidated_trades)

        actual_liquidations = [l for l in liquidated_trades if l.get("status") in ("LIQUIDATED", "PARTIAL_LIQUIDATED") and l.get("quantity", 0) > 0]
        protected_events = [l for l in liquidated_trades if l.get("status") == "TRIGGERED_T1_PROTECTED"]
        ledger_events = [l for l in liquidated_trades if l.get("status") == "LEDGER_ANOMALY_HOLD"]

        if failed_executions and actual_liquidations:
            status = "PARTIAL_LIQUIDATED_WITH_ERROR"
            reason = f"实际平仓 {len(actual_liquidations)} 笔，部分平仓失败 {len(failed_executions)} 笔: {[f['code'] for f in failed_executions]}"
        elif failed_executions:
            status = "EXECUTION_ERROR"
            reason = f"风控平仓执行失败 {len(failed_executions)} 笔: {[f['code'] for f in failed_executions]}"
        elif actual_liquidations:
            status = "PARTIAL_LIQUIDATED" if (missing_quote_symbols or protected_events or len(actual_liquidations) < len(pos_snapshots)) else "LIQUIDATED"
            reason = f"实际平仓 {len(actual_liquidations)} 笔" + (f"，缺失行情标的: {missing_quote_symbols}" if missing_quote_symbols else "")
        elif missing_quote_symbols:
            status = "PARTIAL_HOLD"
            reason = f"部分标的缺失有效实时行情跳过检查: {missing_quote_symbols}；已核验安全标的: {checked_symbols}"
        elif protected_events:
            status = "T1_PROTECTED"
            reason = f"触发风控但处于 T+1 保护期，保持持仓: {[p['code'] for p in protected_events]}"
        elif ledger_events:
            status = "LEDGER_ANOMALY"
            reason = f"账本异常阻断平仓: {[p['code'] for p in ledger_events]}"
        else:
            status = "HOLD"
            reason = f"全部在持标的 ({len(positions)} 只) 均在安全阈值内，继续持有"

        return {
            "status": status,
            "reason": reason,
            "events": liquidated_trades,
            "actual_liquidations": actual_liquidations,
            "protected_events": protected_events,
            "ledger_events": ledger_events,
            "failed_executions": failed_executions,
            "missing_quotes": missing_quote_symbols,
            "checked_symbols": checked_symbols,
            "quotes_quality": str(quotes_quality),
            "quotes_freshness": str(quotes_freshness),
            "quotes_provider": getattr(quotes_resp, "provider", "unknown") if quotes_resp else "unknown",
            "quality_log_success": quotes_quality_log_success
        }

    # =========================================================================
    # 4. 15:05 盘后清算与净值结算 (Post Market Settlement)
    # =========================================================================
    async def run_post_market_settlement(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        15:05:00 收盘清算：核算持仓市值、可用资金、总盈亏与净值
        """
        date_str = target_date or datetime.now().strftime("%Y-%m-%d")
        summary = await self.simulation_service.get_account_summary()
        logger.info(f"[{date_str}] 收盘资产清算完毕: 总资产 ￥{summary.total_asset:,.2f} | 可用现金 ￥{summary.current_capital:,.2f} | 累计盈亏 {summary.total_pnl_pct}%")
        return {
            "date": date_str,
            "total_asset": summary.total_asset,
            "current_capital": summary.current_capital,
            "market_value": summary.market_value,
            "total_pnl": summary.total_pnl,
            "total_pnl_pct": summary.total_pnl_pct
        }

    # =========================================================================
    # 5. 核心测试武器：单交易日全时钟全真倍速回放验证器 (Replay Single Day)
    # =========================================================================
    async def replay_single_day(self, test_date: str = "2024-03-05") -> Dict[str, Any]:
        """
        在非交易时间倍速回放任意真实历史交易日，无需人工干预跑通全流程闭环：
        09:26 早盘选股 ➔ 09:28 预埋队列 ➔ 09:30 开盘撮合 ➔ 盘中风控守护 ➔ 15:05 收盘结算
        """
        logger.info(f"==================================================")
        logger.info(f"  启动单日倍速全真无人值守闭环穿透回放测试: {test_date}")
        logger.info(f"==================================================")

        t_res: Dict[str, Any] = {"test_date": test_date, "steps": {}}

        # Step 1: 09:26 竞价推演
        step1 = await self.run_morning_strategy_pipeline(target_date=test_date)
        t_res["steps"]["09:26_auction_strategy"] = step1

        # Step 2: 09:30 开盘撮合
        queued = step1.get("orders", [])
        step2 = await self.execute_open_market_match(queued, target_date=test_date)
        t_res["steps"]["09:30_market_match"] = step2

        # Step 3: 盘中风控守护
        step3 = await self.run_intraday_risk_guard(target_date=test_date)
        t_res["steps"]["intraday_risk_guard"] = step3

        # Step 4: 15:05 收盘结算
        step4 = await self.run_post_market_settlement(target_date=test_date)
        t_res["steps"]["15:05_settlement"] = step4

        logger.info(f"==================================================")
        logger.info(f"  单日回放闭环穿透测试完成: 产生买单 {len(step2)} 笔, 风控平仓 {len(step3)} 笔")
        logger.info(f"==================================================")
        return t_res
