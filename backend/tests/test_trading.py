import asyncio
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import init_db, engine
from sqlalchemy import text

async def test_trading_full_lifecycle():
    await init_db()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM trade_note;"))
        await conn.execute(text("DELETE FROM position;"))
        await conn.execute(text("DELETE FROM trade_record;"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 0. 初始持仓查询
        r_init_pos = await client.get("/api/v1/trading/positions?refresh_quote=false")
        assert r_init_pos.status_code == 200
        assert r_init_pos.json()["code"] == 200

        # 1. AC-1 第一步：首笔买入 600519 200股 @ 1600.00
        buy1_payload = {
            "code": "600519",
            "name": "贵州茅台",
            "direction": "buy",
            "price": 1600.00,
            "quantity": 200,
            "trade_time": "2026-09-26 09:35:00",
            "trade_reason": "回踩支撑建仓",
            "source": "manual",
            "idempotency_key": "test_buy_001",
        }
        r_buy1 = await client.post("/api/v1/trading/records", json=buy1_payload)
        assert r_buy1.status_code == 200
        data_buy1 = r_buy1.json()["data"]
        rec1_id = data_buy1["id"]
        assert data_buy1["amount"] == 320000.00
        assert data_buy1["record_type"] == "TRADE"

        # 验证持仓生成
        r_pos1 = await client.get("/api/v1/trading/positions?refresh_quote=false")
        pos_list1 = r_pos1.json()["data"]
        pos_600519 = next((p for p in pos_list1 if p["code"] == "600519"), None)
        assert pos_600519 is not None
        assert pos_600519["quantity"] == 200
        assert pos_600519["avg_cost"] == 1600.00
        assert pos_600519["total_cost"] == 320000.00

        # 2. AC-1 第二步：加仓买入 600519 100股 @ 1660.00
        buy2_payload = {
            "code": "600519",
            "name": "贵州茅台",
            "direction": "buy",
            "price": 1660.00,
            "quantity": 100,
            "trade_time": "2026-09-26 10:15:00",
            "trade_reason": "放量突破加仓",
            "source": "manual",
            "idempotency_key": "test_buy_002",
        }
        r_buy2 = await client.post("/api/v1/trading/records", json=buy2_payload)
        assert r_buy2.status_code == 200
        assert r_buy2.json()["data"]["amount"] == 166000.00

        # 验证加仓后持仓均价严格为加权移动平均: (320000 + 166000) / 300 = 1620.00
        r_pos2 = await client.get("/api/v1/trading/positions?refresh_quote=false")
        pos_600519 = next((p for p in r_pos2.json()["data"] if p["code"] == "600519"), None)
        assert pos_600519["quantity"] == 300
        assert pos_600519["avg_cost"] == 1620.00
        assert pos_600519["total_cost"] == 486000.00

        # 3. AC-4 超卖拦截测试：当前持仓300股，试图卖出500股
        oversell_payload = {
            "code": "600519",
            "name": "贵州茅台",
            "direction": "sell",
            "price": 1700.00,
            "quantity": 500,
            "trade_time": "2026-09-26 11:00:00",
            "trade_reason": "试图超卖",
            "idempotency_key": "test_oversell_001",
        }
        r_oversell = await client.post("/api/v1/trading/records", json=oversell_payload)
        assert r_oversell.status_code == 400
        err_detail = r_oversell.json()["detail"]
        assert err_detail["error_type"] == "INSUFFICIENT_POSITION_ERROR"

        # 验证持仓未被非法扣减，依然为 300 股
        r_pos_check = await client.get("/api/v1/trading/positions?refresh_quote=false")
        pos_600519 = next((p for p in r_pos_check.json()["data"] if p["code"] == "600519"), None)
        assert pos_600519["quantity"] == 300

        # 4. AC-1 第三步：部分减仓卖出 100股 @ 1700.00
        sell1_payload = {
            "code": "600519",
            "name": "贵州茅台",
            "direction": "sell",
            "price": 1700.00,
            "quantity": 100,
            "trade_time": "2026-09-26 11:15:00",
            "trade_reason": "触及阻力位减半止盈",
            "source": "manual",
            "idempotency_key": "test_sell_001",
        }
        r_sell1 = await client.post("/api/v1/trading/records", json=sell1_payload)
        assert r_sell1.status_code == 200

        # 验证部分减仓后：剩余持仓 200 股，均价依然保持 1620.00 不变，总成本相应减少
        r_pos3 = await client.get("/api/v1/trading/positions?refresh_quote=false")
        pos_600519 = next((p for p in r_pos3.json()["data"] if p["code"] == "600519"), None)
        assert pos_600519["quantity"] == 200
        assert pos_600519["avg_cost"] == 1620.00
        assert pos_600519["total_cost"] == 324000.00

        # 5. 验证已实现盈亏与单笔卖出胜率统计
        r_stats1 = await client.get("/api/v1/trading/stats")
        assert r_stats1.status_code == 200
        stats1 = r_stats1.json()["data"]
        # 卖出100股: (1700 - 1620) * 100 = +8,000.00
        assert stats1["closed_trades"] == 1
        assert stats1["win_trades"] == 1
        assert stats1["closed_leg_win_rate"] == 100.0
        assert stats1["total_realized_pnl"] == 8000.00

        # 6. AC-2：认知笔记 1:1 强绑定与增量追加测试
        note_create_payload = {
            "trade_id": rec1_id,
            "date": "2026-09-26",
            "mental_state": "冷静执行纪律",
            "decision_logic": "5日线企稳突破，符合早盘预案",
            "reflection": "进场点位精准",
            "lessons": "按预案执行不恐慌",
            "append_mode": True,
        }
        r_note1 = await client.post("/api/v1/trading/notes", json=note_create_payload)
        assert r_note1.status_code == 200
        note_data1 = r_note1.json()["data"]
        assert note_data1["trade_id"] == rec1_id
        assert "进场点位精准" in note_data1["reflection"]

        # 增量追加反思
        note_append_payload = {
            "trade_id": rec1_id,
            "date": "2026-09-26",
            "reflection": "午后回踩确认，后续持有信心充足",
            "append_mode": True,
        }
        r_note2 = await client.post("/api/v1/trading/notes", json=note_append_payload)
        assert r_note2.status_code == 200
        note_data2 = r_note2.json()["data"]
        assert "进场点位精准" in note_data2["reflection"]
        assert "追加]: 午后回踩确认" in note_data2["reflection"]

        # 回显单条交易详情
        r_detail = await client.get(f"/api/v1/trading/records/{rec1_id}")
        assert r_detail.status_code == 200
        detail_data = r_detail.json()["data"]
        assert detail_data["note"] is not None
        assert "冷静执行纪律" in detail_data["note"]["mental_state"]

        # 7. 红字冲正与隔离验证（补丁 1 落地）：误买入 000001 500股，随后立即冲正
        mistake_buy = {
            "code": "000001",
            "name": "平安银行",
            "direction": "buy",
            "price": 10.50,
            "quantity": 500,
            "trade_time": "2026-09-26 13:30:00",
            "trade_reason": "录错标的代码",
            "idempotency_key": "mistake_001",
        }
        r_mistake = await client.post("/api/v1/trading/records", json=mistake_buy)
        assert r_mistake.status_code == 200
        mistake_id = r_mistake.json()["data"]["id"]

        # 验证产生了平安银行持仓 500 股
        r_pos_mistake = await client.get("/api/v1/trading/positions?refresh_quote=false")
        pos_pingan = next((p for p in r_pos_mistake.json()["data"] if p["code"] == "000001"), None)
        assert pos_pingan is not None
        assert pos_pingan["quantity"] == 500

        # 执行红字冲正
        reversal_payload = {
            "target_record_id": mistake_id,
            "reason": "录入笔误，立即对冲抹除",
            "idempotency_key": "rev_001",
        }
        r_rev = await client.post("/api/v1/trading/records/reverse", json=reversal_payload)
        assert r_rev.status_code == 200
        rev_data = r_rev.json()["data"]
        assert rev_data["record_type"] == "REVERSAL"
        assert rev_data["reversed_record_id"] == mistake_id

        # 验证冲正后：平安银行持仓归零（不在有效持仓列表中）
        r_pos_after_rev = await client.get("/api/v1/trading/positions?refresh_quote=false")
        pos_pingan_after = next((p for p in r_pos_after_rev.json()["data"] if p["code"] == "000001"), None)
        assert pos_pingan_after is None

        # 关键断言：冲正对成对排除，绝不计入卖出胜率，已实现盈亏依然保持原本的 +12,000.00
        r_stats2 = await client.get("/api/v1/trading/stats")
        stats2 = r_stats2.json()["data"]
        assert stats2["closed_trades"] == 1  # 依然只有 600519 的那笔卖出，冲正卖出被严格隔离排除
        assert stats2["total_realized_pnl"] == 8000.00
        assert stats2["closed_leg_win_rate"] == 100.0

        # 8. 幂等性与 60s 指纹防重拦截（补丁 5）
        dup_buy = {
            "code": "600519",
            "name": "贵州茅台",
            "direction": "buy",
            "price": 1600.00,
            "quantity": 200,
            "trade_time": "2026-09-26 09:35:00",
            "trade_reason": "完全相同的重复提交",
        }
        r_dup = await client.post("/api/v1/trading/records", json=dup_buy)
        assert r_dup.status_code == 409

        # 9. 对账重算接口验证
        r_reconcile = await client.post("/api/v1/trading/reconcile")
        assert r_reconcile.status_code == 200
        rec_data = r_reconcile.json()["data"]
        assert rec_data["status"] == "SUCCESS"

        # 10. 历史流水多维查询与冲正标记回显
        r_records = await client.get("/api/v1/trading/records?page=1&limit=10")
        assert r_records.status_code == 200
        items = r_records.json()["data"]["items"]
        assert len(items) >= 4
        assert any(item["record_type"] == "REVERSAL" for item in items)

if __name__ == "__main__":
    asyncio.run(test_trading_full_lifecycle())
