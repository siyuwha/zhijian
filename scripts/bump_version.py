#!/usr/bin/env python3
"""
AI认知复盘交易系统 - 工程化动态版本自动升级管理工具
===================================================

用于在完成重要功能阶段（P0/P1/P2/P3）或热修缺陷（Patch）后自动升级版本。
自动维护单一真实源：
  1. frontend/package.json
  2. frontend/src/config/version.ts
  3. backend/app/version.py

用法示例：
  # 升级次版本号（例如 0.2.0 -> 0.3.0，用于完成新的功能里程碑如 P3）
  python scripts/bump_version.py --type minor --stage "P3 实时计算版"

  # 升级补丁号（例如 0.2.0 -> 0.2.1，用于生产缺陷紧急热修）
  python scripts/bump_version.py --type patch

  # 直接指定版本号与阶段
  python scripts/bump_version.py --set 0.2.0 --stage "P2 生产运行版"

  # 仅同步当前 Git Commit 到版本代码中（不变更版本号）
  python scripts/bump_version.py --sync
"""

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_PKG = ROOT_DIR / "frontend" / "package.json"
FRONTEND_VERSION_TS = ROOT_DIR / "frontend" / "src" / "config" / "version.ts"
BACKEND_VERSION_PY = ROOT_DIR / "backend" / "app" / "version.py"


def get_current_git_commit() -> str:
    """获取当前的 Git short commit hash"""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=2,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "unknown"


def read_current_version() -> tuple[int, int, int]:
    """从 frontend/package.json 读取当前版本号"""
    if not FRONTEND_PKG.exists():
        raise FileNotFoundError(f"找不到 package.json: {FRONTEND_PKG}")
    with open(FRONTEND_PKG, "r", encoding="utf-8") as f:
        data = json.load(f)
    version_str = data.get("version", "0.1.0")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version_str.strip())
    if not match:
        raise ValueError(f"无法解析 package.json 中的版本号: {version_str}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_version_tuple(
    current: tuple[int, int, int], bump_type: str
) -> tuple[int, int, int]:
    major, minor, patch = current
    if bump_type == "major":
        return major + 1, 0, 0
    elif bump_type == "minor":
        return major, minor + 1, 0
    elif bump_type == "patch":
        return major, minor, patch + 1
    else:
        raise ValueError(f"未知的升级类型: {bump_type}")


def update_frontend_package_json(version_str: str):
    with open(FRONTEND_PKG, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["version"] = version_str
    with open(FRONTEND_PKG, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  [OK] frontend/package.json -> {version_str}")


def update_frontend_version_ts(
    version_str: str, stage_name: str, commit_hash: str, today_str: str
):
    FRONTEND_VERSION_TS.parent.mkdir(parents=True, exist_ok=True)
    content = f'''import pkg from "../../package.json";

/**
 * 前端工程化动态版本与环境标识
 * 版本号源于 package.json，Git Commit 与构建时间于构建期动态注入
 */
export const APP_VERSION = `v${{pkg.version}}`;
export const STAGE_NAME = "{stage_name}";
export const BUILD_DATE = process.env.NEXT_PUBLIC_BUILD_DATE || "{today_str}";
export const GIT_COMMIT = process.env.NEXT_PUBLIC_GIT_COMMIT || "{commit_hash}";

export const FULL_VERSION_STRING = `${{APP_VERSION}} (${{GIT_COMMIT}})`;
'''
    with open(FRONTEND_VERSION_TS, "w", encoding="utf-8") as f:
        f.write(content)
    print(
        f"  [OK] frontend/src/config/version.ts -> v{version_str} ({stage_name}, #{commit_hash})"
    )


def update_backend_version_py(
    version_str: str, stage_name: str, commit_hash: str, today_str: str
):
    BACKEND_VERSION_PY.parent.mkdir(parents=True, exist_ok=True)
    content = f'''"""
系统版本定义与动态探针模块
单点真实源：管理后端系统版本、阶段标识与 Git Commit 动态获取
"""
import os
import subprocess
from pathlib import Path

APP_NAME = "AI认知复盘交易系统"
VERSION = "{version_str}"
STAGE_NAME = "{stage_name}"
BUILD_DATE = "{today_str.replace('.', '-')}"
FALLBACK_COMMIT = "{commit_hash}"


def get_git_commit() -> str:
    """获取当前生效的 Git Commit 短哈希"""
    # 1. 优先读取环境变量 (Docker 运行时可通过 Compose 环境变量直接注入)
    env_commit = os.getenv("GIT_COMMIT")
    if env_commit:
        return env_commit.strip()[:7]

    # 2. 尝试从本地 Git 执行获取
    try:
        root_dir = Path(__file__).resolve().parent.parent.parent
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass

    return FALLBACK_COMMIT


def get_version_info() -> dict:
    """获取标准化版本信息字典"""
    return {{
        "status": "ok",
        "app_name": APP_NAME,
        "version": f"v{{VERSION}}",
        "stage": STAGE_NAME,
        "commit": get_git_commit(),
        "build_date": BUILD_DATE,
        "sina_protocol": "http"
    }}
'''
    with open(BACKEND_VERSION_PY, "w", encoding="utf-8") as f:
        f.write(content)
    print(
        f"  [OK] backend/app/version.py -> v{version_str} ({stage_name}, #{commit_hash})"
    )


def main():
    parser = argparse.ArgumentParser(
        description="AI认知复盘交易系统 - 版本升级管理工具"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--type",
        choices=["minor", "patch", "major"],
        help="升级类型：minor (功能升级), patch (Bugfix), major (重大架构变革)",
    )
    group.add_argument("--set", help="显式指定版本号，例如: 0.2.0")
    group.add_argument(
        "--sync", action="store_true", help="同步当前 git commit 与日期到版本配置"
    )

    parser.add_argument(
        "--stage",
        default=None,
        help="阶段标识文案 (例如: 'P2 生产运行版', 'P3 实时计算版')",
    )

    args = parser.parse_args()

    cur_major, cur_minor, cur_patch = read_current_version()
    current_version_str = f"{cur_major}.{cur_minor}.{cur_patch}"
    commit_hash = get_current_git_commit()
    today_str = datetime.date.today().strftime("%Y.%m.%d")

    # 确定目标版本
    if args.set:
        new_version_str = args.set.lstrip("v")
    elif args.type:
        next_major, next_minor, next_patch = bump_version_tuple(
            (cur_major, cur_minor, cur_patch), args.type
        )
        new_version_str = f"{next_major}.{next_minor}.{next_patch}"
    else:  # sync or default
        new_version_str = current_version_str

    # 确定阶段文案
    stage_name = args.stage or "P2 生产运行版"

    print(f"\n==========================================")
    print(f"AI认知复盘交易系统 - 工程化版本提升")
    print(f"==========================================")
    print(f"当前版本: v{current_version_str}")
    print(f"目标版本: v{new_version_str}")
    print(f"阶段定义: {stage_name}")
    print(f"Git提交 : #{commit_hash}")
    print(f"构建日期: {today_str}")
    print(f"------------------------------------------")

    update_frontend_package_json(new_version_str)
    update_frontend_version_ts(
        new_version_str, stage_name, commit_hash, today_str
    )
    update_backend_version_py(
        new_version_str, stage_name, commit_hash, today_str
    )

    print(f"------------------------------------------")
    print(f"版本元数据同步完成！")
    print(f"建议后续操作:")
    print(
        f'  1. git commit -am "chore(release): bump version to v{new_version_str}"'
    )
    print(
        f'  2. git tag -a v{new_version_str} -m "Release v{new_version_str}: {stage_name}"'
    )
    print(f"==========================================\n")


if __name__ == "__main__":
    main()
