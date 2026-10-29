import os
import time
import math
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from ..config import DATA_DIR, PROJECT_ROOT

class BacktestService:
    """知见三大经典工业级策略真实历史回测引擎 (Backtest Engine)"""

    def __init__(self):
        # 寻找数据目录
        candidates = [
            DATA_DIR / "historical",
            PROJECT_ROOT / "data" / "historical",
            Path("data/historical").resolve(),
            Path("/app/data/historical"),
        ]
        self.historical_dir = next((c for c in candidates if c.exists() and (c / "zt_ladder_pool_2023_2026.parquet").exists()), None)
        if not self.historical_dir:
            self.historical_dir = DATA_DIR / "historical"

        self.pool_parquet = self.historical_dir / "zt_ladder_pool_2023_2026.parquet"
        self.daily_parquet = self.historical_dir / "a_share_daily_2023_2026.parquet"
        self.benchmark_parquet = self.historical_dir / "benchmark_indices.parquet"

    def get_status(self) -> Dict[str, Any]:
        """获取历史回测数据底座就绪状态"""
        has_pool = self.pool_parquet.exists()
        has_daily = self.daily_parquet.exists()
        
        if not (has_pool and has_daily):
            return {
                "available": False,
                "message": f"未检测到历史回测数据集，请将数据放置于 {self.historical_dir} 目录下",
                "historical_dir": str(self.historical_dir),
            }

        try:
            pool_stat = os.stat(self.pool_parquet)
            daily_stat = os.stat(self.daily_parquet)
            total_size_mb = round((pool_stat.st_size + daily_stat.st_size) / (1024 * 1024), 2)

            # 快速读取元数据范围
            df_pool = pd.read_parquet(self.pool_parquet, columns=["date"])
            min_date = str(df_pool["date"].min())
            max_date = str(df_pool["date"].max())
            total_days = int(df_pool["date"].nunique())

            return {
                "available": True,
                "min_date": min_date,
                "max_date": max_date,
                "total_trading_days": total_days,
                "data_size_mb": total_size_mb,
                "historical_dir": str(self.historical_dir),
                "supported_strategies": [
                    {"id": "weak_to_strong", "name": "弱转强竞价抢筹策略", "desc": "昨日涨停/炸板，今日竞价超预期高开抢筹"},
                    {"id": "multi_board_dip", "name": "连板分歧低吸策略", "desc": "2连板及以上高标日内分歧回踩低吸"},
                    {"id": "dragon_pullback", "name": "首板龙回头策略", "desc": "前期首板领涨龙头，缩量回踩10日线企稳"},
                    {"id": "all", "name": "三大经典策略全景组合", "desc": "全策略多生态位动态择优建仓"}
                ]
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e),
                "historical_dir": str(self.historical_dir)
            }

    def run_backtest(
        self,
        start_date: str = "2024-01-01",
        end_date: str = "2026-10-22",
        strategy_id: str = "weak_to_strong",
        initial_capital: float = 1000000.0,
        min_open_pct: float = 1.5,
        max_open_pct: float = 5.5,
        stop_loss_pct: float = -5.0,
        max_positions: int = 5,
        holding_days: int = 2,
        market_filter: bool = True
    ) -> Dict[str, Any]:
        """
        执行事件驱动的日级别历史回测
        - 真实模拟 A 股 T+1 交易制度
        - 真实扣除佣金（万一）、印花税（万五，仅卖出）与冲击滑点（0.1%）
        """
        t0 = time.time()
        if not (self.pool_parquet.exists() and self.daily_parquet.exists()):
            raise RuntimeError(f"历史数据文件未找到，请确认已上传至: {self.historical_dir}")

        df_pool = pd.read_parquet(self.pool_parquet)
        df_daily = pd.read_parquet(self.daily_parquet)

        # 过滤日期区间
        df_pool = df_pool[(df_pool["date"] >= start_date) & (df_pool["date"] <= end_date)]
        daily_filtered = df_daily[(df_daily["date"] >= start_date) & (df_daily["date"] <= end_date)]
        all_dates = sorted(daily_filtered["date"].unique())

        if not all_dates:
            raise ValueError(f"指定时间区间 [{start_date} ~ {end_date}] 内无交易日数据")

        # 读取上证指数 (优先 sh000001，兜底 sh000300) 基准走势
        benchmark_map = {}
        if self.benchmark_parquet.exists():
            try:
                df_bm = pd.read_parquet(self.benchmark_parquet)
                df_bench = df_bm[df_bm["code"] == "sh000001"]
                if df_bench.empty:
                    df_bench = df_bm[df_bm["code"] == "sh000300"]
                if not df_bench.empty:
                    benchmark_map = df_bench.set_index("date")["close"].to_dict()
            except Exception:
                pass

        # 快速哈希索引以供 O(1) 查询行情
        daily_map = daily_filtered.set_index(["date", "code"])[["open", "high", "low", "close", "pct_change"]].to_dict("index")
        pool_by_date = {d: g for d, g in df_pool.groupby("date")}

        # 回测状态变量
        cash = float(initial_capital)
        positions: Dict[str, Dict[str, Any]] = {}
        trades: List[Dict[str, Any]] = []
        equity_history: List[Dict[str, Any]] = []
        peak_equity = float(initial_capital)
        max_dd_pct = 0.0

        fee_buy = 0.0011   # 买入：0.1% 滑点 + 万一佣金
        fee_sell = 0.0016  # 卖出：0.1% 滑点 + 万一佣金 + 万五印花税

        # 上证指数基准归一化基数
        first_date = all_dates[0]
        bm_base_price = benchmark_map.get(first_date, 2962.28)

        for date_idx, date in enumerate(all_dates):
            # -------------------------------------------------------------
            # 1. 检查既有持仓出局（止盈、止损、次日抢跑、持有到期）
            # -------------------------------------------------------------
            closed_codes = []
            for code, pos in list(positions.items()):
                bar = daily_map.get((date, code))
                if not bar:
                    continue

                days_held = date_idx - pos["buy_date_idx"]
                if days_held < 1:  # 严格遵守 A 股 T+1，当日买入不可卖出
                    continue

                open_p = bar["open"]
                close_p = bar["close"]
                low_p = bar["low"]
                buy_p = pos["buy_price"]

                open_gap = (open_p - buy_p) / buy_p * 100.0
                low_dip = (low_p - buy_p) / buy_p * 100.0

                sell_p = None
                sell_reason = ""

                # 出局规则 1: 次日竞价大幅低开（-2.0%及以下），波普尔刚性抢跑
                if open_gap <= -2.0:
                    sell_p = open_p
                    sell_reason = "次日竞价低开抢跑出局"
                # 出局规则 2: 盘中击穿止损线（如 -5%）
                elif low_dip <= stop_loss_pct:
                    sell_p = round(buy_p * (1.0 + stop_loss_pct / 100.0), 2)
                    sell_reason = f"触及 {stop_loss_pct}% 刚性止损线"
                # 出局规则 3: 达到最大持仓天数（默认 2 个交易日），尾盘按收盘价出局
                elif days_held >= holding_days:
                    sell_p = close_p
                    sell_reason = f"超短周期持仓满 {holding_days} 日平仓"

                if sell_p is not None:
                    sell_amount = round(sell_p * pos["qty"] * (1.0 - fee_sell), 2)
                    pnl_amount = round(sell_amount - pos["buy_cost"], 2)
                    pnl_pct = round((sell_p - buy_p) / buy_p * 100.0, 2)
                    cash += sell_amount

                    trades.append({
                        "code": code,
                        "name": pos["name"],
                        "strategy": pos.get("strategy_name", "经典量化"),
                        "buy_date": pos["buy_date"],
                        "buy_price": buy_p,
                        "sell_date": date,
                        "sell_price": sell_p,
                        "qty": pos["qty"],
                        "pnl_amount": pnl_amount,
                        "pnl_pct": pnl_pct,
                        "holding_days": days_held,
                        "reason": sell_reason
                    })
                    closed_codes.append(code)

            for c in closed_codes:
                del positions[c]

            # -------------------------------------------------------------
            # 2. 策略信号推演与建仓
            # -------------------------------------------------------------
            if date_idx > 0 and len(positions) < max_positions:
                prev_date = all_dates[date_idx - 1]
                prev_pool = pool_by_date.get(prev_date)

                if prev_pool is not None and not prev_pool.empty:
                    cands_to_buy = []

                    # 策略 A: 弱转强竞价抢筹
                    if strategy_id in ("weak_to_strong", "all"):
                        w2s_pool = prev_pool[prev_pool["is_limit_up"] | prev_pool["is_broken"]]
                        for _, row in w2s_pool.iterrows():
                            c = row["code"]
                            if c in positions:
                                continue
                            bar = daily_map.get((date, c))
                            if not bar or bar["open"] <= 0:
                                continue
                            open_pct = (bar["open"] - row["close"]) / row["close"] * 100.0
                            if min_open_pct <= open_pct <= max_open_pct:
                                score = 75.0 + row["lbc"] * 5.0 + open_pct * 2.0 + (5.0 if row["is_broken"] else 0.0)
                                cands_to_buy.append((score, c, row["name"], bar["open"], "弱转强竞价抢筹"))

                    # 策略 B: 连板分歧低吸
                    if strategy_id in ("multi_board_dip", "all"):
                        dip_pool = prev_pool[prev_pool["lbc"] >= 2]
                        for _, row in dip_pool.iterrows():
                            c = row["code"]
                            if c in positions:
                                continue
                            bar = daily_map.get((date, c))
                            if not bar or bar["open"] <= 0:
                                continue
                            # 盘中有分歧回踩（日内最低价跌回昨收附近或低开），买入点取开盘与日内低点均衡
                            if bar["low"] <= row["close"] * 1.03 and bar["pct_change"] > -8.0:
                                dip_price = round((bar["open"] + bar["low"]) / 2.0, 2)
                                score = 72.0 + row["lbc"] * 6.0
                                cands_to_buy.append((score, c, row["name"], dip_price, "连板分歧低吸"))

                    # 策略 C: 首板龙回头
                    if strategy_id in ("dragon_pullback", "all"):
                        pb_pool = prev_pool[(prev_pool["days_since_limit_up"] >= 1) & (prev_pool["days_since_limit_up"] <= 4) & (~prev_pool["is_limit_up"])]
                        for _, row in pb_pool.iterrows():
                            c = row["code"]
                            if c in positions:
                                continue
                            bar = daily_map.get((date, c))
                            if not bar or bar["open"] <= 0:
                                continue
                            # 回踩温和 (-4.5% ~ +2.5%)
                            if -4.5 <= bar["pct_change"] <= 2.5:
                                score = 76.0 + (row["pct_change"] * 0.5)
                                cands_to_buy.append((score, c, row["name"], bar["open"], "首板龙回头"))

                    # 排序并分配资金建仓
                    cands_to_buy.sort(key=lambda x: x[0], reverse=True)
                    slots = max_positions - len(positions)
                    slot_budget = (cash * 0.95) / max(1, slots)

                    for score, code, name, enter_p, strat_name in cands_to_buy[:slots]:
                        if enter_p <= 0 or slot_budget < 3000:
                            continue
                        qty = int(slot_budget / enter_p / 100) * 100
                        if qty < 100:
                            continue
                        buy_cost = round(enter_p * qty * (1.0 + fee_buy), 2)
                        if buy_cost > cash:
                            continue
                        cash -= buy_cost
                        positions[code] = {
                            "buy_date": date,
                            "buy_date_idx": date_idx,
                            "buy_price": enter_p,
                            "buy_cost": buy_cost,
                            "qty": qty,
                            "name": name,
                            "strategy_name": strat_name
                        }

            # -------------------------------------------------------------
            # 3. 当日收盘计算资产净值与回撤
            # -------------------------------------------------------------
            mkt_val = 0.0
            for code, pos in positions.items():
                bar = daily_map.get((date, code))
                cur_p = bar["close"] if bar else pos["buy_price"]
                mkt_val += cur_p * pos["qty"]

            tot_equity = round(cash + mkt_val, 2)
            if tot_equity > peak_equity:
                peak_equity = tot_equity
            cur_dd = round((tot_equity - peak_equity) / peak_equity * 100.0, 2)
            if cur_dd < max_dd_pct:
                max_dd_pct = cur_dd

            # 对应沪深300基准净值折算
            bm_cur = benchmark_map.get(date, bm_base_price)
            bm_equity = round(initial_capital * (bm_cur / bm_base_price), 2) if bm_base_price > 0 else initial_capital

            equity_history.append({
                "date": date,
                "equity": tot_equity,
                "cash": round(cash, 2),
                "market_value": round(mkt_val, 2),
                "drawdown_pct": cur_dd,
                "benchmark_equity": bm_equity,
                "positions_count": len(positions)
            })

        # -----------------------------------------------------------------
        # 4. 统计与量化绩效指标计算
        # -----------------------------------------------------------------
        final_equity = equity_history[-1]["equity"] if equity_history else initial_capital
        total_ret_pct = round((final_equity - initial_capital) / initial_capital * 100.0, 2)
        total_days = len(all_dates)
        years = total_days / 250.0
        annual_ret_pct = round(((final_equity / initial_capital) ** (1.0 / max(0.1, years)) - 1.0) * 100.0, 2) if final_equity > 0 else -100.0

        win_trades = [t for t in trades if t["pnl_amount"] > 0]
        loss_trades = [t for t in trades if t["pnl_amount"] <= 0]
        win_rate = round(len(win_trades) / len(trades) * 100.0, 2) if trades else 0.0

        avg_win = float(np.mean([t["pnl_amount"] for t in win_trades])) if win_trades else 0.0
        avg_loss = float(abs(np.mean([t["pnl_amount"] for t in loss_trades]))) if loss_trades else 1.0
        payoff_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else 0.0

        # 夏普比率 (年化无风险利率设为 2%)
        eq_series = pd.Series([e["equity"] for e in equity_history])
        daily_rets = eq_series.pct_change().dropna()
        if len(daily_rets) > 1 and daily_rets.std() > 0:
            excess_ret = daily_rets.mean() - (0.02 / 250.0)
            sharpe = round(float(excess_ret / daily_rets.std() * np.sqrt(250)), 2)
        else:
            sharpe = 0.0

        avg_holding = round(float(np.mean([t["holding_days"] for t in trades])), 1) if trades else 0.0

        # 上证指数同期收益率
        bm_final = equity_history[-1]["benchmark_equity"] if equity_history else initial_capital
        bm_return_pct = round((bm_final - initial_capital) / initial_capital * 100.0, 2)

        # 抽样曲线数据 (若数据点过多，抽样保留 120~200 个关键点以供前端渲染)
        step = max(1, len(equity_history) // 150)
        sampled_curve = equity_history[::step]
        if equity_history and sampled_curve[-1]["date"] != equity_history[-1]["date"]:
            sampled_curve.append(equity_history[-1])

        elapsed_seconds = round(time.time() - t0, 2)

        return {
            "code": 200,
            "message": "回测执行完成",
            "elapsed_seconds": elapsed_seconds,
            "params": {
                "start_date": start_date,
                "end_date": end_date,
                "strategy_id": strategy_id,
                "initial_capital": initial_capital,
                "min_open_pct": min_open_pct,
                "max_open_pct": max_open_pct,
                "stop_loss_pct": stop_loss_pct,
                "max_positions": max_positions,
                "holding_days": holding_days
            },
            "metrics": {
                "initial_capital": initial_capital,
                "final_equity": final_equity,
                "total_return_pct": total_ret_pct,
                "annual_return_pct": annual_ret_pct,
                "max_drawdown_pct": max_dd_pct,
                "sharpe_ratio": sharpe,
                "win_rate": win_rate,
                "payoff_ratio": payoff_ratio,
                "total_trades": len(trades),
                "win_trades": len(win_trades),
                "loss_trades": len(loss_trades),
                "avg_holding_days": avg_holding,
                "benchmark_return_pct": bm_return_pct,
                "total_trading_days": total_days
            },
            "equity_curve": sampled_curve,
            "recent_trades": trades[-100:] if len(trades) > 100 else trades
        }
