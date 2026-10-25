#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知见系统 · L0 级底座工程与运行环境健康体检服务 (DoctorService)
"""

import sys
import os
import asyncio
import sqlite3
from pathlib import Path
from typing import Dict, Any, List

def run_doctor(auto_heal: bool = True) -> Dict[str, Any]:
    # 动态探测项目路径与数据目录
    cur_dir = Path(__file__).resolve().parent
    # 兼容在 backend/app/services/ 下或 /app/services/ 下
    backend_dir = cur_dir.parent.parent if cur_dir.name == "services" else cur_dir
    project_root = backend_dir.parent if backend_dir.name == "backend" else backend_dir
    data_dir = project_root / "data"

    report: Dict[str, Any] = {
        "overall_status": "PASS",
        "checks": []
    }

    def add_check(category: str, item: str, status: bool, detail: str, critical: bool = True):
        report["checks"].append({
            "category": category,
            "item": item,
            "status": "PASS" if status else "FAIL",
            "detail": detail,
            "critical": critical
        })
        if not status and critical:
            report["overall_status"] = "FAIL"

    # =========================================================================
    # 1. 运行时依赖检查
    # =========================================================================
    py_ver = sys.version.split()[0]
    add_check("Runtime", "Python Version", sys.version_info >= (3, 10), f"Python {py_ver} (要求 >= 3.10)")

    packages = [
        ("fastapi", "FastAPI 后端核心"),
        ("pandas", "数据处理核心"),
        ("numpy", "向量计算矩阵"),
        ("pyarrow", "Parquet 高速列式存储引擎 (回测核心)"),
        ("pytdx", "通达信原生协议引擎"),
        ("sqlalchemy", "ORM 数据库引擎"),
        ("aiosqlite", "异步 SQLite 驱动"),
    ]

    for pkg, desc in packages:
        try:
            mod = __import__(pkg)
            v = getattr(mod, "__version__", "已安装")
            add_check("Dependencies", pkg, True, f"{desc}: v{v}")
        except ImportError as e:
            add_check("Dependencies", pkg, False, f"{desc}: 缺失 ({str(e)})", critical=(pkg in ["pyarrow", "pandas", "fastapi"]))

    # =========================================================================
    # 2. 历史回测数据底座检查 (Parquet Historical Data)
    # =========================================================================
    hist_candidates = [
        data_dir / "historical",
        project_root / "data" / "historical",
        Path("/app/data/historical"),
    ]
    hist_dir = next((c for c in hist_candidates if c.exists()), data_dir / "historical")

    parquet_files = [
        ("a_share_daily_2023_2026.parquet", "全市场 374 万日线 Bar 数据集", 50.0),
        ("zt_ladder_pool_2023_2026.parquet", "连板高标与炸板梯队池", 5.0),
        ("benchmark_indices.parquet", "沪深300同期基准指数", 0.01),
    ]

    add_check("Storage", "Historical Directory", hist_dir.exists(), f"路径: {hist_dir}")

    if hist_dir.exists():
        for fname, desc, min_size_mb in parquet_files:
            fpath = hist_dir / fname
            if not fpath.exists():
                add_check("Storage", fname, False, f"{desc}: 文件缺失 ({fpath})", critical=True)
                continue
            
            size_mb = round(fpath.stat().st_size / (1024 * 1024), 2)
            if size_mb < min_size_mb:
                add_check("Storage", fname, False, f"{desc}: 文件过小 ({size_mb} MB < {min_size_mb} MB)", critical=True)
                continue

            try:
                import pandas as pd
                df = pd.read_parquet(fpath)
                rows = len(df)
                date_range = f"{df['date'].min()} ~ {df['date'].max()}" if "date" in df.columns else "无 date 列"
                add_check("Storage", fname, True, f"{desc}: {rows:,} 行 ({date_range}, {size_mb} MB)")
            except Exception as e:
                add_check("Storage", fname, False, f"{desc}: 解析异常 ({str(e)})", critical=True)
    else:
        add_check("Storage", "Historical Parquet", False, "历史数据目录不存在，请将 parquet 数据集挂载至 data/historical/", critical=True)

    # =========================================================================
    # 3. 数据库与表结构检查 (Database & Tables)
    # =========================================================================
    db_candidates = [
        data_dir / "trading.db",
        project_root / "data" / "trading.db",
        Path("/app/data/trading.db"),
    ]
    db_path = next((c for c in db_candidates if c.exists()), data_dir / "trading.db")

    tables = set()
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cursor.fetchall()}
            conn.close()
        except Exception:
            pass

    req_tables = ["trade_record", "sim_account", "sim_position", "sim_trade"]
    missing_tables = [t for t in req_tables if t not in tables]

    # 自愈逻辑：若缺失核心表且开启了 auto_heal，立即进行自动建表
    if missing_tables and auto_heal:
        try:
            from ..core.database import init_db
            from .. import models
            asyncio.run(init_db())
            
            if db_path.exists():
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = {row[0] for row in cursor.fetchall()}
                conn.close()
                missing_tables = [t for t in req_tables if t not in tables]
        except Exception as e:
            add_check("Database", "Auto-Heal Schema", False, f"自愈建表异常: {str(e)}", critical=False)

    for t_name in req_tables:
        has_t = t_name in tables
        desc_map = {
            "trade_record": "实盘账本表",
            "sim_account": "模拟账户表",
            "sim_position": "模拟持仓表",
            "sim_trade": "模拟成交流水表",
        }
        add_check("Database", f"Table: {t_name}", has_t, f"{desc_map.get(t_name, t_name)}: {'已就绪' if has_t else '缺失'}")

    # 模拟账户初始资金检查与自愈
    if "sim_account" in tables and db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT initial_capital, current_capital FROM sim_account LIMIT 1;")
            row = cursor.fetchone()
            if not row and auto_heal:
                cursor.execute("""
                    INSERT INTO sim_account (name, initial_capital, current_capital, total_pnl, is_active)
                    VALUES ('知见·默认双轨模拟实战账户', 1000000.0, 1000000.0, 0.0, 1)
                """)
                conn.commit()
                row = (1000000.0, 1000000.0)

            if row:
                add_check("Database", "Sim Account Initialized", True, f"默认账户: 本金 {row[0]:,.2f} 元, 当前可用 {row[1]:,.2f} 元")
            else:
                add_check("Database", "Sim Account Initialized", False, "默认模拟账户未初始化", critical=False)
            conn.close()
        except Exception as e:
            add_check("Database", "Sim Account Check", False, str(e), critical=False)

    # =========================================================================
    # 4. 通达信 (pytdx) 券商行情主站连通性探测 (网络与协议连通)
    # =========================================================================
    try:
        from pytdx.hq import TdxHq_API
        api = TdxHq_API(auto_retry=True, raise_exception=False)
        servers = [
            ("通达信官方主站", "218.75.126.9", 7709),
            ("招商证券深圳主站", "119.147.212.81", 7709),
            ("华泰证券上海主站", "124.71.187.122", 7709),
            ("阿里云华东主站", "47.103.48.45", 7709),
            ("上海双线主站", "180.153.39.51", 7709),
        ]
        connected = False
        active_server = ""
        for s_name, ip, port in servers:
            try:
                if api.connect(ip, port, time_out=2.0):
                    connected = True
                    active_server = f"{s_name} ({ip}:{port})"
                    api.disconnect()
                    break
            except Exception:
                continue

        add_check("Gateway", "TDX Protocol Connection", connected, 
                  f"直连主站: {active_server}" if connected else "未检测到可用主站 (若无外网可忽略，盘后增量更新需要连通)",
                  critical=False)
    except Exception as e:
        add_check("Gateway", "TDX Protocol Connection", False, f"探测异常: {str(e)}", critical=False)

    return report
