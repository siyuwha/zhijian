"""
G1-M3 交易 (Truth Ledger) 与 实盘模拟 (Paper Trading) 物理隔离契约测试
- 确保两者底层表物理解耦 (TradeRecord / Position vs SimAccount / SimPosition / SimTrade)
- 确保真实交易账本严禁混入策略模拟数据
- 确保真实账本防误触拦截（含关键词阻断）与沙盒数据清洗机制正常运行
- 确保券商状态接口明确报告“未接入实盘券商”
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from app.main import app
from app.core.database import engine, init_db

@pytest.mark.asyncio
async def test_simulation_trading_physical_isolation():
    await init_db()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM trade_note;"))
        await conn.execute(text("DELETE FROM position;"))
        await conn.execute(text("DELETE FROM trade_record;"))
        await conn.execute(text("DELETE FROM sim_position;"))
        await conn.execute(text("DELETE FROM sim_trade;"))
        await conn.execute(text("DELETE FROM sim_account;"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. 验证真实券商连接状态
        r_broker = await client.get("/api/v1/trading/broker/status")
        assert r_broker.status_code == 200
        broker_data = r_broker.json()["data"]
        assert broker_data["connected"] is False
        assert broker_data["status"] == "DISCONNECTED"
        assert "尚未接入真实券商委托通道" in broker_data["message"]
        assert any("QMT" in ch for ch in broker_data["supported_channels"])

        # 2. 验证初始状态下，真实持仓与真实流水为空
        r_real_pos = await client.get("/api/v1/trading/positions?refresh_quote=false")
        assert r_real_pos.status_code == 200
        assert len(r_real_pos.json()["data"]) == 0

        r_real_rec = await client.get("/api/v1/trading/records")
        assert r_real_rec.status_code == 200
        assert r_real_rec.json()["data"]["total"] == 0

        # 3. 在实盘模拟（Simulation）中执行两笔买入
        sim_buy_payload = {
            "code": "002696",
            "name": "百洋股份",
            "direction": "buy",
            "price": 10.50,
            "quantity": 1000,
            "decision_summary": "[弱转强抢筹] 策略联动模拟建仓"
        }
        r_sim_buy = await client.post("/api/v1/simulation/trades", json=sim_buy_payload)
        assert r_sim_buy.status_code == 200
        sim_trade_data = r_sim_buy.json()["data"]
        assert sim_trade_data["code"] == "002696"
        assert sim_trade_data["amount"] == 10500.0

        # 检查模拟账户及模拟持仓
        r_sim_acc = await client.get("/api/v1/simulation/account")
        assert r_sim_acc.status_code == 200
        assert r_sim_acc.json()["data"]["current_capital"] == 1000000.0 - 10500.0

        r_sim_pos = await client.get("/api/v1/simulation/positions?refresh_quote=false")
        assert r_sim_pos.status_code == 200
        sim_positions = r_sim_pos.json()["data"]
        assert len(sim_positions) == 1
        assert sim_positions[0]["code"] == "002696"
        assert sim_positions[0]["quantity"] == 1000

        # 4. 【核心隔离断言】检查真实交易系统，持仓和流水必须依旧为 0！绝无任何污染！
        r_real_pos_after_sim = await client.get("/api/v1/trading/positions?refresh_quote=false")
        assert len(r_real_pos_after_sim.json()["data"]) == 0

        r_real_rec_after_sim = await client.get("/api/v1/trading/records")
        assert r_real_rec_after_sim.json()["data"]["total"] == 0

        # 5. 【真实账本输入守卫断言】若有任何尝试将模拟标识推入真实账本，直接拦截 HTTP 400
        bad_payload = {
            "code": "002696",
            "name": "百洋股份",
            "direction": "buy",
            "price": 10.50,
            "quantity": 1000,
            "trade_time": "2026-10-20 10:00:00",
            "trade_reason": "[弱转强] 虚拟跟单建仓",
            "idempotency_key": "bad_sim_key_001"
        }
        r_bad = await client.post("/api/v1/trading/records", json=bad_payload)
        assert r_bad.status_code == 400
        assert "/api/v1/simulation" in str(r_bad.json()["detail"])

        # 6. 正常录入真实交易 600519
        real_buy_payload = {
            "code": "600519",
            "name": "贵州茅台",
            "direction": "buy",
            "price": 1600.00,
            "quantity": 100,
            "trade_time": "2026-10-20 14:00:00",
            "trade_reason": "用户手工确认线下券商交割建仓",
            "idempotency_key": "real_trade_001"
        }
        r_real_buy = await client.post("/api/v1/trading/records", json=real_buy_payload)
        assert r_real_buy.status_code == 200

        # 真实账本有且仅有 600519
        r_real_pos_final = await client.get("/api/v1/trading/positions?refresh_quote=false")
        real_items = r_real_pos_final.json()["data"]
        assert len(real_items) == 1
        assert real_items[0]["code"] == "600519"

        # 模拟沙盒有且仅有 002696
        r_sim_pos_final = await client.get("/api/v1/simulation/positions?refresh_quote=false")
        sim_items = r_sim_pos_final.json()["data"]
        assert len(sim_items) == 1
        assert sim_items[0]["code"] == "002696"

        # 7. 测试清洗沙盒数据接口 POST /api/v1/trading/purge-sim
        r_purge = await client.post("/api/v1/trading/purge-sim")
        assert r_purge.status_code == 200
        assert r_purge.json()["data"]["purged_records_count"] == 0
