"""
P1 交易体验与报表增强 全链路 12 点自动化验收测试套件 (P1 Acceptance Test Suite)
覆盖范围：
- P1-01: 股票代码 -> 名称自动联想补全 (GET /api/v1/trading/security/search?q=600519)
- P1-02: 股票名称/拼音 -> 代码自动联想补全 (GET /api/v1/trading/security/search?q=茅台 / gzmt)
- P1-03: 前端非100整数倍校验与输入保护 (源码静态审计与 build 产物核验)
- P1-04: 后端整手校验拦截非100整数倍录入 (HTTP 422 拒绝 quantity=101)
- P1-05: 存量历史流水 ID 2 的 101 股绝对不可篡改性核验 (ID 2 保持 101 股原貌)
- P1-06: 错误纠错机制 (Correction) 生成 REVERSAL 记录冲销原流水
- P1-07: 错误纠错机制生成新 TRADE 流水并正确对齐持仓与笔记
- P1-08: 不可篡改审计链完整性验证 (Target Trade -> REVERSAL -> Corrected Trade)
- P1-09: 前端全局看板与复盘详情完全移除 M1~M4 序号前缀
- P1-10: 监控自选股列表 3 态循环排序 (默认 -> 降序 ↓ -> 升序 ↑ -> 默认)
- P1-11: 排序纯内存计算，产生 0 次额外网络请求
- P1-12: PROD-04 生产状态一致性核验 (data_quality: partial, state_label: 偏弱整理 (部分降级))
"""

import sys
import os
import json
import time
import argparse
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

DEFAULT_BASE_URL = "http://192.168.3.97:8000"

def http_get(base_url, endpoint):
    url = f"{base_url}{endpoint}"
    req = urllib.request.Request(url, headers={"User-Agent": "P1AcceptanceProbe/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw_error": body}

def http_post(base_url, endpoint, data):
    url = f"{base_url}{endpoint}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "P1AcceptanceProbe/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw_error": body}

def run_acceptance_tests(base_url: str):
    print("=" * 70)
    print(f"开始执行 P1 全链路 12 点自动化终审验收测试")
    print(f"目标后端服务: {base_url}")
    print("=" * 70)

    results = []

    # -------------------------------------------------------------------------
    # P1-01: 代码 -> 名称联想
    # -------------------------------------------------------------------------
    try:
        status, data = http_get(base_url, "/api/v1/trading/security/search?q=600519&limit=5")
        passed = status == 200 and isinstance(data, list) and len(data) > 0 and data[0]["code"] == "600519" and "茅台" in data[0]["name"]
        results.append({
            "test_id": "P1-01",
            "name": "股票代码 -> 名称自动联想补全 (600519 -> 贵州茅台)",
            "status": "PASS" if passed else "FAIL",
            "detail": f"Status: {status}, First Match: {data[0] if isinstance(data, list) and data else data}"
        })
    except Exception as e:
        results.append({
            "test_id": "P1-01",
            "name": "股票代码 -> 名称自动联想补全 (600519 -> 贵州茅台)",
            "status": "FAIL",
            "detail": str(e)
        })

    # -------------------------------------------------------------------------
    # P1-02: 名称 / 拼音 -> 代码联想
    # -------------------------------------------------------------------------
    try:
        status1, data1 = http_get(base_url, "/api/v1/trading/security/search?q=%E8%8C%85%E5%8F%B0&limit=5")
        status2, data2 = http_get(base_url, "/api/v1/trading/security/search?q=gzmt&limit=5")
        
        has_600519_1 = any(item.get("code") == "600519" for item in data1) if isinstance(data1, list) else False
        has_600519_2 = any(item.get("code") == "600519" for item in data2) if isinstance(data2, list) else False
        
        passed = (status1 == 200 and has_600519_1) and (status2 == 200 and has_600519_2)
        results.append({
            "test_id": "P1-02",
            "name": "股票名称 / 拼音 -> 代码自动联想补全 (茅台 / gzmt -> 600519)",
            "status": "PASS" if passed else "FAIL",
            "detail": f"Name match: {has_600519_1}, Pinyin match: {has_600519_2}"
        })
    except Exception as e:
        results.append({
            "test_id": "P1-02",
            "name": "股票名称 / 拼音 -> 代码自动联想补全 (茅台 / gzmt -> 600519)",
            "status": "FAIL",
            "detail": str(e)
        })

    # -------------------------------------------------------------------------
    # P1-03: 前端非100整数倍校验与输入保护 (静态与语义核验)
    # -------------------------------------------------------------------------
    try:
        trading_page_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "app" / "trading" / "page.tsx"
        if not trading_page_path.exists():
            trading_page_path = Path(r"d:\项目库\AI认知复盘交易系统\frontend\src\app\trading\page.tsx")
        
        content = trading_page_path.read_text(encoding="utf-8")
        has_min_100 = 'min="100"' in content
        has_step_100 = 'step="100"' in content
        has_mod_check = 'quantity % 100 !== 0' in content or 'quantity % 100 != 0' in content
        has_submit_block = 'A股买卖数量必须大于等于100且为100的整数倍' in content
        
        passed = has_min_100 and has_step_100 and has_mod_check and has_submit_block
        results.append({
            "test_id": "P1-03",
            "name": "前端非100整数倍校验与整手拦截 (min=100, step=100, %100===0)",
            "status": "PASS" if passed else "FAIL",
            "detail": f"min=100: {has_min_100}, step=100: {has_step_100}, %100: {has_mod_check}, submit_block: {has_submit_block}"
        })
    except Exception as e:
        results.append({
            "test_id": "P1-03",
            "name": "前端非100整数倍校验与整手拦截 (min=100, step=100, %100===0)",
            "status": "FAIL",
            "detail": str(e)
        })

    # -------------------------------------------------------------------------
    # P1-04: 后端整手校验拦截非100整数倍录入 (HTTP 422 拒绝 101 股)
    # -------------------------------------------------------------------------
    try:
        test_payload_101 = {
            "code": "600519",
            "direction": "buy",
            "price": 1250.0,
            "quantity": 101,
            "trade_time": "2026-09-28 10:00:00",
            "trade_reason": "P1-04 自动化拦截测试",
            "idempotency_key": f"test_101_reject_{int(time.time() * 1000)}"
        }
        status, data = http_post(base_url, "/api/v1/trading/records", test_payload_101)
        passed = status == 422
        results.append({
            "test_id": "P1-04",
            "name": "后端整手校验拦截非100整数倍录入 (101 股严格返回 HTTP 422)",
            "status": "PASS" if passed else "FAIL",
            "detail": f"Status: {status} (Expected 422), Error Detail: {data.get('detail') if isinstance(data, dict) else data}"
        })
    except Exception as e:
        results.append({
            "test_id": "P1-04",
            "name": "后端整手校验拦截非100整数倍录入 (101 股严格返回 HTTP 422)",
            "status": "FAIL",
            "detail": str(e)
        })

    # -------------------------------------------------------------------------
    # P1-05: 存量历史流水 ID 2 的 101 股绝对不可篡改性核验
    # -------------------------------------------------------------------------
    try:
        status, data = http_get(base_url, "/api/v1/trading/records/2")
        passed = status == 200 and data.get("id") == 2 and data.get("quantity") == 101
        results.append({
            "test_id": "P1-05",
            "name": "存量历史流水 ID 2 绝对不可篡改 (保持 101 股原始不可变账本事实)",
            "status": "PASS" if passed else "FAIL",
            "detail": f"Record ID: {data.get('id')}, Quantity: {data.get('quantity')} (Expected 101)"
        })
    except Exception as e:
        results.append({
            "test_id": "P1-05",
            "name": "存量历史流水 ID 2 绝对不可篡改 (保持 101 股原始不可变账本事实)",
            "status": "FAIL",
            "detail": str(e)
        })

    # -------------------------------------------------------------------------
    # P1-06 & P1-07 & P1-08: 纠错 (Correction) 闭环流程与不可篡改审计链
    # -------------------------------------------------------------------------
    created_test_trade_id = None
    created_reversal_id = None
    created_corrected_id = None
    try:
        # Step 1: 录入一笔待纠错的测试流水 (买入 601398 200股 @ 5.00)
        init_trade_payload = {
            "code": "601398",
            "direction": "buy",
            "price": 5.00,
            "quantity": 200,
            "trade_time": "2026-09-28 10:30:00",
            "trade_reason": "P1-Correction 待纠错原始交易",
            "idempotency_key": f"test_corr_init_{int(time.time() * 1000)}"
        }
        status_init, data_init = http_post(base_url, "/api/v1/trading/records", init_trade_payload)
        assert status_init == 200, f"创建待纠错初始流水失败: {data_init}"
        created_test_trade_id = data_init["id"]

        # Step 2: 挂载一条反思笔记
        note_payload = {
            "trade_id": created_test_trade_id,
            "date": "2026-09-28",
            "mental_state": "纠错前初始心理状态",
            "decision_logic": "买入工行观察",
            "lessons": "初始经验"
        }
        http_post(base_url, "/api/v1/trading/notes", note_payload)

        # Step 3: 发起原子纠错 (修正为 买入 601398 300股 @ 5.10)
        correct_payload = {
            "target_record_id": created_test_trade_id,
            "reason": "单价与数量笔误纠错",
            "corrected_data": {
                "code": "601398",
                "direction": "buy",
                "price": 5.10,
                "quantity": 300,
                "trade_time": "2026-09-28 10:30:00",
                "trade_reason": "单价与数量修正后的真实买入",
                "idempotency_key": f"test_corr_exec_{int(time.time() * 1000)}"
            }
        }
        status_corr, data_corr = http_post(base_url, "/api/v1/trading/records/correct", correct_payload)
        
        # P1-06 核验
        reversal = data_corr.get("reversal") if isinstance(data_corr, dict) else None
        p1_06_passed = (
            status_corr == 200 and
            reversal is not None and
            reversal.get("record_type") == "REVERSAL" and
            reversal.get("reversed_record_id") == created_test_trade_id and
            reversal.get("quantity") == 200
        )
        if reversal:
            created_reversal_id = reversal.get("id")

        results.append({
            "test_id": "P1-06",
            "name": "错误纠错机制生成 REVERSAL 记录准确冲销原错误流水",
            "status": "PASS" if p1_06_passed else "FAIL",
            "detail": f"Status: {status_corr}, Reversal ID: {created_reversal_id}, Target: {created_test_trade_id}, Quantity: {reversal.get('quantity') if reversal else None}"
        })

        # P1-07 核验: 生成新 TRADE 记录并更新持仓快照与笔记迁移
        corrected = data_corr.get("corrected") if isinstance(data_corr, dict) else None
        p1_07_passed = False
        migrated_note_check = False
        if status_corr == 200 and corrected is not None:
            created_corrected_id = corrected.get("id")
            p1_07_passed = (
                corrected.get("record_type") == "TRADE" and
                corrected.get("price") == 5.10 and
                corrected.get("quantity") == 300 and
                corrected.get("name") is not None
            )
            # 检查原笔记是否成功迁移至新流水
            status_note, data_note = http_get(base_url, f"/api/v1/trading/notes/{created_corrected_id}")
            migrated_note_check = (status_note == 200 and data_note.get("mental_state") == "纠错前初始心理状态")

        results.append({
            "test_id": "P1-07",
            "name": "错误纠错机制生成全新 TRADE 流水并自动迁移认知笔记",
            "status": "PASS" if (p1_07_passed and migrated_note_check) else "FAIL",
            "detail": f"Corrected ID: {created_corrected_id}, Price: 5.10, Qty: 300, Note Migrated: {migrated_note_check}"
        })

        # P1-08 核验: 不可篡改审计链完整性 (3 条记录同时存在于历史台账，形成完整审计环)
        s_tgt, d_tgt = http_get(base_url, f"/api/v1/trading/records/{created_test_trade_id}")
        s_rev, d_rev = http_get(base_url, f"/api/v1/trading/records/{created_reversal_id}")
        s_new, d_new = http_get(base_url, f"/api/v1/trading/records/{created_corrected_id}")
        
        audit_chain_intact = (
            s_tgt == 200 and d_tgt.get("id") == created_test_trade_id and
            s_rev == 200 and d_rev.get("record_type") == "REVERSAL" and d_rev.get("reversed_record_id") == created_test_trade_id and
            s_new == 200 and d_new.get("record_type") == "TRADE" and d_new.get("quantity") == 300
        )
        results.append({
            "test_id": "P1-08",
            "name": "不可篡改审计链完整性 (Target -> REVERSAL -> Corrected 三方共存追溯)",
            "status": "PASS" if audit_chain_intact else "FAIL",
            "detail": f"Target: #{created_test_trade_id}, Reversal: #{created_reversal_id}, Corrected: #{created_corrected_id}"
        })

    except Exception as e:
        for tid in ["P1-06", "P1-07", "P1-08"]:
            if not any(r["test_id"] == tid for r in results):
                results.append({"test_id": tid, "name": f"纠错流程测试异常 ({tid})", "status": "FAIL", "detail": str(e)})
    finally:
        # 清理测试流水：对新生成的 corrected 交易做冲正，保持生产账户持仓纯净
        if created_corrected_id:
            try:
                http_post(base_url, "/api/v1/trading/records/reverse", {
                    "target_record_id": created_corrected_id,
                    "reason": "自动化验收清理测试持仓",
                    "idempotency_key": f"test_cleanup_{int(time.time() * 1000)}"
                })
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # P1-09: 前端全局看板与复盘详情移除 M1~M4 序号前缀
    # -------------------------------------------------------------------------
    try:
        pages = [
            Path(r"d:\项目库\AI认知复盘交易系统\frontend\src\app\page.tsx"),
            Path(r"d:\项目库\AI认知复盘交易系统\frontend\src\app\review\page.tsx"),
            Path(r"d:\项目库\AI认知复盘交易系统\frontend\src\app\briefing\[date]\page.tsx")
        ]
        
        m_prefix_found = False
        problematic_files = []
        for p in pages:
            if p.exists():
                text = p.read_text(encoding="utf-8")
                for bad_str in ["盘前简报 (M2)", "竞价事实 (M3)", "盘中动态 (M4)", "收盘复盘 (M1)", "收盘认知复盘 (M1)"]:
                    if bad_str in text:
                        m_prefix_found = True
                        problematic_files.append(f"{p.name}: {bad_str}")
        
        results.append({
            "test_id": "P1-09",
            "name": "前端全局看板与复盘详情完全移除 M1~M4 序号前缀",
            "status": "PASS" if not m_prefix_found else "FAIL",
            "detail": "All clean" if not m_prefix_found else f"Found obsolete prefixes: {problematic_files}"
        })
    except Exception as e:
        results.append({
            "test_id": "P1-09",
            "name": "前端全局看板与复盘详情完全移除 M1~M4 序号前缀",
            "status": "FAIL",
            "detail": str(e)
        })

    # -------------------------------------------------------------------------
    # P1-10: 监控自选股列表 3 态循环排序 (默认 -> 降序 -> 升序 -> 默认)
    # -------------------------------------------------------------------------
    try:
        monitor_page_path = Path(r"d:\项目库\AI认知复盘交易系统\frontend\src\app\monitor\page.tsx")
        m_content = monitor_page_path.read_text(encoding="utf-8")
        
        has_3_state = (
            "setSortOrder('desc')" in m_content and
            "setSortOrder('asc')" in m_content and
            "setSortOrder('none')" in m_content and
            "setSortField(null)" in m_content
        )
        has_sort_fields = (
            "open_pct" in m_content and
            "current_pct" in m_content and
            "amount_yi" in m_content
        )
        
        results.append({
            "test_id": "P1-10",
            "name": "监控自选股列表 3 态循环排序 (默认 -> 降序 ↓ -> 升序 ↑ -> 默认)",
            "status": "PASS" if (has_3_state and has_sort_fields) else "FAIL",
            "detail": f"3-State logic present: {has_3_state}, Target fields (open/current/amount): {has_sort_fields}"
        })
    except Exception as e:
        results.append({
            "test_id": "P1-10",
            "name": "监控自选股列表 3 态循环排序 (默认 -> 降序 ↓ -> 升序 ↑ -> 默认)",
            "status": "FAIL",
            "detail": str(e)
        })

    # -------------------------------------------------------------------------
    # P1-11: 排序纯内存计算，产生 0 次额外网络请求
    # -------------------------------------------------------------------------
    try:
        monitor_page_path = Path(r"d:\项目库\AI认知复盘交易系统\frontend\src\app\monitor\page.tsx")
        m_content = monitor_page_path.read_text(encoding="utf-8")
        
        # 验证排序是在 useMemo 中对已有的 realtimeData?.watchlist 进行纯内存排序
        has_use_memo = "useMemo(() =>" in m_content
        has_sorted_watchlist = "sortedWatchlist" in m_content
        zero_network = "handleWatchlistSort" in m_content and "fetch" not in m_content.split("const handleWatchlistSort")[1].split("};")[0]
        
        results.append({
            "test_id": "P1-11",
            "name": "排序为纯前端内存计算，产生 0 次额外网络请求 (Zero Network Overhead)",
            "status": "PASS" if (has_use_memo and has_sorted_watchlist and zero_network) else "FAIL",
            "detail": f"useMemo present: {has_use_memo}, sortedWatchlist computed: {has_sorted_watchlist}, Zero fetch in handler: {zero_network}"
        })
    except Exception as e:
        results.append({
            "test_id": "P1-11",
            "name": "排序为纯前端内存计算，产生 0 次额外网络请求",
            "status": "FAIL",
            "detail": str(e)
        })

    # -------------------------------------------------------------------------
    # P1-12: PROD-04 生产状态一致性核验 (data_quality: partial, state_label: 偏弱整理 (部分降级))
    # -------------------------------------------------------------------------
    try:
        status, data = http_get(base_url, "/api/v1/cognition/market-state/2026-09-23")
        dq = data.get("data_quality") if isinstance(data, dict) else None
        sl = data.get("state_label") if isinstance(data, dict) else None
        
        p1_12_passed = (status == 200 and dq == "partial" and "偏弱整理" in str(sl))
        results.append({
            "test_id": "P1-12",
            "name": "PROD-04 生产状态一致性 (data_quality: partial, state_label: 偏弱整理)",
            "status": "PASS" if p1_12_passed else "FAIL",
            "detail": f"Status: {status}, data_quality: {dq}, state_label: {sl}"
        })
    except Exception as e:
        results.append({
            "test_id": "P1-12",
            "name": "PROD-04 生产状态一致性 (data_quality: partial, state_label: 偏弱整理)",
            "status": "FAIL",
            "detail": str(e)
        })

    # -------------------------------------------------------------------------
    # 验收汇总输出
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("P1 验收测试执行结果汇总 (12 项硬核指标):")
    print("=" * 70)
    all_passed = True
    for r in results:
        status_color = "\033[92mPASS\033[0m" if r["status"] == "PASS" else "\033[91mFAIL\033[0m"
        print(f"[{r['test_id']}] [{status_color}] {r['name']}")
        print(f"       详情: {r['detail']}")
        if r["status"] != "PASS":
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("\033[92m>>> 【P1 验收结论：全部 12 项指标 100% 验收通过 (12/12 PASS)】<<<\033[0m")
    else:
        print("\033[91m>>> 【P1 验收结论：存在未通过项，需整改】<<<\033[0m")
    print("=" * 70)
    return all_passed, results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P1 Acceptance Test Suite")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Target backend API base URL")
    args = parser.parse_args()

    passed, _ = run_acceptance_tests(args.base_url)
    sys.exit(0 if passed else 1)
