#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知见系统 · L2 级单交易日时序回放倍速穿透测试脚本 (Replay Acceptance Test)
运行方式: python backend/run_replay_test.py [可选交易日期: 如 2024-03-05]
"""

import sys
import os
import asyncio
from pathlib import Path

cur_dir = Path(__file__).resolve().parent
project_root = cur_dir.parent if cur_dir.name == "backend" else cur_dir
for p in [str(cur_dir), str(project_root), "/app", "/"]:
    if p not in sys.path:
        sys.path.insert(0, p)

if "backend" not in sys.modules:
    import types
    try:
        import app
        _backend_pkg = types.ModuleType("backend")
        _backend_pkg.app = app
        _backend_pkg.__path__ = []
        sys.modules["backend"] = _backend_pkg
        sys.modules["backend.app"] = app
    except Exception:
        pass

from app.core.database import async_session, init_db
from app.services.autonomous_executor import AutonomousJobEngine
from app import models

async def main():
    test_date = sys.argv[1] if len(sys.argv) > 1 else "2024-03-05"
    print(f"\n=======================================================")
    print(f"  知见 · L2 级单交易日全时钟全真倍速穿透测试: {test_date}")
    print(f"=======================================================\n")

    await init_db()

    async with async_session() as session:
        engine = AutonomousJobEngine(session)
        result = await engine.replay_single_day(test_date=test_date)

    print("\n【回放执行结果汇总】")
    s1 = result["steps"].get("09:26_auction_strategy", {})
    s2 = result["steps"].get("09:30_market_match", [])
    s3 = result["steps"].get("intraday_risk_guard", [])
    s4 = result["steps"].get("15:05_settlement", {})

    print(f"1. 09:26 竞价策略扫描 : 状态 {s1.get('status')} | 预埋候选: {s1.get('orders_generated')} 笔")
    if s1.get("orders"):
        for o in s1["orders"]:
            print(f"   -> 预埋: {o['name']} ({o['code']}) 拟买 {o['quantity']}股 @ ￥{o['price']}")

    print(f"2. 09:30 开盘真实撮合 : 实际撮合完成: {len(s2)} 笔")
    for t in s2:
        print(f"   -> 成交: {t['name']} ({t['code']}) 买入 {t['quantity']}股 @ ￥{t['match_price']} (含0.1%滑点)")

    print(f"3. 盘中波普尔风控守护 : 触发止损/平仓: {len(s3)} 笔")
    for t in s3:
        print(f"   -> 平仓: {t['name']} ({t['code']}) 卖出 {t['quantity']}股 @ ￥{t['sell_price']} | 原因: {t['reason']}")

    print(f"4. 15:05 盘后资产清算 : 账户总资产 ￥{s4.get('total_asset'):,.2f} | 可用现金 ￥{s4.get('current_capital'):,.2f} | 累计盈亏 {s4.get('total_pnl_pct')}%")

    print("\n-------------------------------------------------------")
    print("  >>> L2 级单交易日全自动穿透测试：执行完成！ <<<")
    print("=======================================================\n")

if __name__ == "__main__":
    asyncio.run(main())
