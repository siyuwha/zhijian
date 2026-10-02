#!/usr/bin/env python3
"""
KA-06 基线差分与防退化门禁执行工具 (Baseline Gate CLI Runner)
用法：
    python backend/scripts/verify_baseline_gate.py
"""
import hashlib
import json
import os
import subprocess
import sys
import sqlite3
import tempfile
from pathlib import Path
from typing import Optional

# Add backend to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.governance.baseline_gate import BaselineDiffEngine

def get_file_sha256(filepath: Path) -> Optional[str]:
    if not filepath.exists():
        return None
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def main():
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

    repo_root = backend_dir.parent
    manifest_path = repo_root / "baseline_evidence" / "golden_baseline_manifest.json"
    engine = BaselineDiffEngine(manifest_path)

    print("================================================================================")
    print("           KA-06 BASELINE DIFF & ANTI-REGRESSION GATE VERIFICATION              ")
    print("================================================================================")

    # 1. 记录物理开发库运行前哈希
    db_root = repo_root / "data" / "trading.db"
    db_backend = backend_dir / "data" / "trading.db"
    pre_hash_root = get_file_sha256(db_root)
    pre_hash_backend = get_file_sha256(db_backend)

    # 2. 执行 pytest 测试套件
    print("\n[Step 1/3] Running Full Pytest Test Suite...")
    pytest_res = subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "--tb=short"],
        cwd=str(backend_dir),
        capture_output=True,
        text=True
    )
    
    stdout = pytest_res.stdout
    print(stdout[-500:] if len(stdout) > 500 else stdout)

    # 解析测试统计
    # 类似 "153 passed, 4 warnings in 65.43s"
    total_passed = 0
    total_failed = 0
    total_errors = 0
    
    import re
    pass_match = re.search(r"(\d+)\s+passed", stdout)
    fail_match = re.search(r"(\d+)\s+failed", stdout)
    error_match = re.search(r"(\d+)\s+error", stdout)

    if pass_match:
        total_passed = int(pass_match.group(1))
    if fail_match:
        total_failed = int(fail_match.group(1))
    if error_match:
        total_errors = int(error_match.group(1))

    total_tests = total_passed + total_failed + total_errors
    pass_rate = (total_passed / total_tests) if total_tests > 0 else 0.0

    candidate_metrics = {
        "total_tests": total_tests,
        "failed_tests": total_failed,
        "error_tests": total_errors,
        "pass_rate": pass_rate,
        "return_code": pytest_res.returncode
    }

    # 3. 校验真实物理库文件零污染
    print("\n[Step 2/3] Verifying Physical Database Zero-Pollution...")
    post_hash_root = get_file_sha256(db_root)
    post_hash_backend = get_file_sha256(db_backend)

    isolation_match = (pre_hash_root == post_hash_root) and (pre_hash_backend == post_hash_backend)
    print(f"  Root DB Hash Match:    {pre_hash_root == post_hash_root}")
    print(f"  Backend DB Hash Match: {pre_hash_backend == post_hash_backend}")

    # 4. 执行空库 Schema 迁移验证
    print("\n[Step 3/3] Verifying Clean Alembic Schema Migration...")
    temp_db = Path(tempfile.gettempdir()) / f"gate_schema_verify_{os.getpid()}.db"
    if temp_db.exists():
        temp_db.unlink()

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{temp_db.as_posix()}"

    alembic_res = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
        env=env
    )

    candidate_tables = []
    candidate_triggers = []
    genesis_row = None

    if alembic_res.returncode == 0 and temp_db.exists():
        conn = sqlite3.connect(str(temp_db))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        candidate_tables = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        candidate_triggers = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT chain_id, tail_sequence_id, tail_record_hash FROM cognition_chain_state LIMIT 1")
        row = cur.fetchone()
        if row:
            genesis_row = {
                "chain_id": row[0],
                "tail_sequence_id": row[1],
                "tail_record_hash": row[2]
            }
        conn.close()
        temp_db.unlink()

    # 5. 门禁综合裁决
    report = engine.evaluate(
        candidate_metrics=candidate_metrics,
        candidate_tables=candidate_tables,
        candidate_triggers=candidate_triggers,
        genesis_row=genesis_row,
        isolation_hashes_match=isolation_match
    )

    md_report = report.to_markdown()
    print("\n" + md_report)

    # 归档门禁报告
    report_file = repo_root / "baseline_evidence" / "ka06_gate_report.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(md_report)
    print(f"\nReport written to: {report_file}")

    if report.status == "PASS":
        print("\n>>> KA-06 GATE RESULT: PASS (All baseline metrics satisfied) <<<")
        sys.exit(0)
    else:
        print("\n>>> KA-06 GATE RESULT: FAIL (Regression detected!) <<<")
        sys.exit(1)

if __name__ == "__main__":
    main()
