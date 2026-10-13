"""
批量为历史复盘记录补充落库「知见」11章全景深度研报数据 (transcendent_review)
确保历史任意交易日切换时均具备完整的 11 章客观数据、表格、推演与证伪闭环
"""
import sys
import os
import sqlite3
import json
import asyncio
from datetime import datetime

# 注入项目根目录
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from backend.app.services.zhijian_transcendent_review_service import zhijian_transcendent_service

DB_PATH = "Z:/AI-Trading-System/data/trading.db"

async def backfill_all():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, date, market_overview, limit_up_analysis, report_content FROM daily_review ORDER BY date DESC")
    rows = cursor.fetchall()

    print(f"Total reviews found: {len(rows)}")

    for row_id, date_str, mo_str, lua_str, rc_str in rows:
        print(f"\nChecking review for date: {date_str} (ID: {row_id})...")
        try:
            rc = json.loads(rc_str) if rc_str else {}
        except Exception:
            rc = {}

        # 检查是否已存在有效的 11 章研报 (markdown_content > 2000 字符)
        tr = rc.get("transcendent_review", {})
        if tr and len(tr.get("markdown_content", "")) > 2000:
            print(f"[{date_str}] Already has valid transcendent_review ({len(tr['markdown_content'])} chars), skipping.")
            continue

        try:
            mo = json.loads(mo_str) if mo_str else []
        except Exception:
            mo = []

        try:
            lua = json.loads(lua_str) if lua_str else {}
        except Exception:
            lua = {}

        raw_indices = rc.get("indices") or mo or []
        raw_limit_up = rc.get("limit_up") or lua or {}
        raw_breadth = rc.get("breadth") or {}

        # 计算两市去重成交额
        total_turnover_str = "--"
        if raw_indices:
            sum_wan = sum(float(i.get("amount_wan") or 0) for i in raw_indices if "000001" in str(i.get("code", "")) or "399001" in str(i.get("code", "")))
            if sum_wan > 100000000:
                total_turnover_str = f"{(sum_wan / 100000000):.2f} 万亿元"
            elif sum_wan > 10000:
                total_turnover_str = f"{(sum_wan / 10000):.0f} 亿元"

        facts = {
            "date": date_str,
            "indices": raw_indices,
            "turnover": rc.get("turnover") or {"total_amount": total_turnover_str, "shrinkage_amount": "--", "shrinkage_pct": "--"},
            "breadth": raw_breadth,
            "limit_up": raw_limit_up,
            "audit_delta": rc.get("audit_delta") or [],
            "market_state": rc.get("market_state") or {}
        }

        print(f"Generating transcendent_review for {date_str} with {len(raw_indices)} indices, {raw_breadth.get('up_count', 0)} up, {raw_limit_up.get('total_count', 0)} limit-up...")
        try:
            new_tr = await zhijian_transcendent_service.generate_transcendent_review(facts)
            rc["transcendent_review"] = new_tr
            updated_rc_str = json.dumps(rc, ensure_ascii=False)

            cursor.execute("UPDATE daily_review SET report_content = ? WHERE id = ?", (updated_rc_str, row_id))
            conn.commit()
            print(f"[{date_str}] Successfully updated and committed! Markdown len: {len(new_tr.get('markdown_content', ''))}")
        except Exception as e:
            print(f"[{date_str}] Error generating transcendent_review: {e}")

    conn.close()
    print("\nBackfill complete!")

if __name__ == "__main__":
    asyncio.run(backfill_all())
