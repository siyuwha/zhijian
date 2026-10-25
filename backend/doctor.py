#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
知见系统 · L0 级底座工程与运行环境健康体检探针命令行入口 (CLI Doctor)
"""

import sys
import os
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

from app.services.doctor import run_doctor

def print_cli_report(report):
    print("\n" + "=" * 70)
    print("  知见系统 · L0 级底座工程与运行环境健康体检报告 (Health Probe)")
    print("=" * 70)

    cur_category = ""
    for c in report["checks"]:
        if c["category"] != cur_category:
            cur_category = c["category"]
            print(f"\n【{cur_category}】")
        
        status_label = "[PASS]" if c["status"] == "PASS" else ("[FAIL]" if c["critical"] else "[WARN]")
        print(f"  {status_label:<9} {c['item']:<28} : {c['detail']}")

    print("\n" + "-" * 70)
    if report["overall_status"] == "PASS":
        print("  >>> L0 级底座工程验收结果：全部通过 (PASSED)！核心链路无阻塞！<<<")
    else:
        print("  >>> L0 级底座工程验收结果：未通过 (FAILED)！请按上方 FAIL 项目修复！<<<")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    rep = run_doctor(auto_heal=True)
    print_cli_report(rep)
    sys.exit(0 if rep["overall_status"] == "PASS" else 1)
