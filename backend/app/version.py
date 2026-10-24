"""
系统版本定义与动态探针模块
单点真实源：管理后端系统版本、阶段标识与 Git Commit 动态获取
"""
import os
import subprocess
from pathlib import Path

APP_NAME = "AI认知复盘交易系统"
VERSION = "0.8.4"
STAGE_NAME = "知见·题材战场梯队下钻与自适应动态量程版"
BUILD_DATE = "2026-10-24"
FALLBACK_COMMIT = "1a1e781"


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
    return {
        "status": "ok",
        "app_name": APP_NAME,
        "version": f"v{VERSION}",
        "stage": STAGE_NAME,
        "commit": get_git_commit(),
        "build_date": BUILD_DATE,
        "sina_protocol": "http"
    }

