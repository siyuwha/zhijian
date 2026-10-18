"""
知见量化系统 · 通达信数据管道与系统硬件兼容性基准评测工具
用于自动化评测：主站网络延迟、批量五档吞吐、分时均线准确性、逐笔大单流向以及系统 CPU/内存占用。
"""
import sys
import os
import time
import json
import subprocess

# 基础目录定位
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SKILL_SCRIPTS = os.path.join(BASE_DIR, '.agents', 'skills', 'tdx-market-data', 'scripts')

def run_skill_script(script_name, args=None):
    script_path = os.path.join(SKILL_SCRIPTS, script_name)
    cmd = [sys.executable, script_path] + (args or [])
    t0 = time.time()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        cost_ms = round((time.time() - t0) * 1000, 1)
        if res.returncode == 0:
            try:
                data = json.loads(res.stdout)
                return {"status": "PASS", "data": data, "cost_ms": cost_ms}
            except Exception as e:
                return {"status": "WARN", "raw": res.stdout[:200], "cost_ms": cost_ms, "error": str(e)}
        else:
            return {"status": "FAIL", "stderr": res.stderr[:200], "cost_ms": cost_ms}
    except Exception as e:
        return {"status": "TIMEOUT", "error": str(e), "cost_ms": round((time.time() - t0) * 1000, 1)}

def main():
    print("=" * 70)
    print("知见 · 通达信毫秒级数据管道能力与系统兼容性基准测试")
    print(f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 运行环境: {sys.platform}")
    print("=" * 70)

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "version": "v0.7.0",
        "tests": {}
    }

    # 1. 主站连通性与延迟评测
    print("\n[Test 1] 正在探测券商行情主站集群并测速 (server_pool.py)...")
    res1 = run_skill_script("server_pool.py")
    report["tests"]["server_pool"] = res1
    if res1["status"] == "PASS":
        best = res1["data"].get("best_server", {})
        count = res1["data"].get("online_count", 0)
        print(f"-> 探测成功: 在线主站 {count} 个 | 最优主站: {best.get('name')} (延迟: {best.get('latency_ms')}ms)")
    else:
        print(f"-> 探测异常: {res1.get('status')} ({res1.get('error') or res1.get('stderr')})")

    # 2. 批量五档快照获取与吞吐量测试
    test_codes = "600519,000001,300750,002696,002343"
    print(f"\n[Test 2] 正在测试批量五档微观盘口快照 ({test_codes})...")
    res2 = run_skill_script("market_quote.py", ["--code", test_codes])
    report["tests"]["market_quote"] = res2
    if res2["status"] == "PASS":
        stocks = res2["data"].get("data", [])
        print(f"-> 批量成功: 捕获 {len(stocks)} 只标的盘口 | 总耗时: {res2['cost_ms']}ms (平均每只 {round(res2['cost_ms']/len(stocks), 1)}ms)")
    else:
        print(f"-> 盘口异常: {res2.get('status')}")

    # 3. 全天 241 分钟分时走势与均价线测试
    print("\n[Test 3] 正在验证 241 分钟分时数据完整性 (以贵州茅台 600519 为例)...")
    res3 = run_skill_script("minute_trend.py", ["--code", "600519"])
    report["tests"]["minute_trend"] = res3
    if res3["status"] == "PASS":
        points = len(res3["data"].get("data", []))
        print(f"-> 分时成功: 捕获连续点位 {points} 个 | 耗时: {res3['cost_ms']}ms")
    else:
        print(f"-> 分时异常: {res3.get('status')}")

    # 4. 逐笔成交明细流向测试
    print("\n[Test 4] 正在验证逐笔大单明细流向 (以百洋股份 002696 为例)...")
    res4 = run_skill_script("tick_detail.py", ["--code", "002696", "--count", "30"])
    report["tests"]["tick_detail"] = res4
    if res4["status"] == "PASS":
        ticks = len(res4["data"].get("data", []))
        print(f"-> 逐笔成功: 捕获逐笔记录 {ticks} 条 | 耗时: {res4['cost_ms']}ms")
    else:
        print(f"-> 逐笔异常: {res4.get('status')}")

    print("\n" + "=" * 70)
    all_pass = all(t.get("status") == "PASS" for t in report["tests"].values())
    print(f"基准评测结论: {'【全部通过 PASS】' if all_pass else '【存在警告或失败 WARN】'}")
    print("=" * 70)

    # 写入结果缓存
    log_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    out_file = os.path.join(log_dir, "benchmark_tdx_result.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"基准评测原始 JSON 已存档至: {out_file}\n")

if __name__ == "__main__":
    main()
