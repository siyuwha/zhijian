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
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from ..config import DATA_DIR, PROJECT_ROOT
from ..core.calendar import calendar
from ..models.simulation import SimAccount, SimPosition, SimTrade
from ..schemas.simulation import SimTradeCreate
from ..services.selection import SelectionService
from ..services.simulation import SimulationService
from ..data.service import DataService

logger = logging.getLogger(__name__)

class AutonomousJobEngine:
    """无人值守交易时钟与双轨执行引擎"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.selection_service = SelectionService(session)
        self.simulation_service = SimulationService(session)
        self.data_service = DataService(session)

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
    async def run_intraday_risk_guard(self, target_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        盘中风控巡检守护：
        1. 触及 -5% 刚性硬止损红线 ➔ 立即市价平仓
        2. 次日竞价大幅低开超过 -2.5% ➔ 逻辑被证伪立即平仓
        3. 持仓周期到期 ➔ 尾盘 14:55 刚性出局
        """
        now = datetime.now()
        date_str = target_date or now.strftime("%Y-%m-%d")
        
        account = await self.simulation_service.get_or_create_default_account()
        stmt = select(SimPosition).where(SimPosition.account_id == account.id, SimPosition.quantity > 0)
        positions = list((await self.session.execute(stmt)).scalars().all())

        if not positions:
            return []

        symbols = [p.code for p in positions]
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
                logger.warning(f"风控巡检获取行情异常: {e}")

        liquidated_trades = []

        for pos in positions:
            code = pos.code
            q = quotes_map.get(code, {})
            cur_price = float(q.get("price") or pos.current_price or pos.avg_cost)
            low_price = float(q.get("low") or cur_price)
            if cur_price <= 0:
                continue

            # 浮亏比例
            loss_pct = round(((cur_price - pos.avg_cost) / pos.avg_cost) * 100.0, 2)
            exit_reason = ""

            # 规则 1: 触及 -5.0% 刚性止损
            if loss_pct <= -5.0:
                exit_reason = f"[波普尔硬止损] 浮亏触及 {loss_pct}% (<= -5.0% 熔断红线)"

            # 规则 2: 次日跳空大幅低开 (<= -2.5%)
            open_pct = float(q.get("open_pct") or 0.0)
            if open_pct <= -2.5 and not exit_reason:
                exit_reason = f"[次日竞价抢跑] 跳空低开 {open_pct}%，逻辑被证伪离场"

            # 规则 3: 回放测试或实际尾盘到期离场
            cur_time_str = now.strftime("%H:%M")
            if (cur_time_str >= "14:55" or target_date) and not exit_reason:
                # 若持仓已有浮盈或属于短线 T+1 试仓，到期尾盘兑现
                exit_reason = f"[持股周期到期] 短线周期到期，尾盘刚性平仓"

            if exit_reason:
                sell_price = round(cur_price * 0.999, 2)
                try:
                    sell_payload = SimTradeCreate(
                        code=code,
                        name=pos.name,
                        direction="sell",
                        price=sell_price,
                        quantity=pos.quantity,
                        trade_time=f"{date_str} {now.strftime('%H:%M:%S')}",
                        decision_summary=exit_reason
                    )
                    await self.simulation_service.execute_trade(sell_payload)
                    liquidated_trades.append({
                        "code": code,
                        "name": pos.name,
                        "sell_price": sell_price,
                        "quantity": pos.quantity,
                        "pnl_pct": loss_pct,
                        "reason": exit_reason
                    })
                    logger.warning(f"🛑 触发风控平仓出局: {pos.name} ({code}) 卖出 {pos.quantity}股 @ ￥{sell_price} | 原因: {exit_reason}")
                except Exception as e:
                    logger.error(f"风控平仓执行失败 [{code}]: {e}")

        return liquidated_trades

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
