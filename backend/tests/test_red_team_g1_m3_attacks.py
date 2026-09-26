"""
G1-M3 交易记录与持仓管理 - 红队破坏性攻击测试套件 (Red Team Destructive Attack Suite)
测试目标：全面实施对 G1-M3 交付代码的边界穿透、破坏性攻击与数学健壮性压力测试
测试依据：
- 《开发文档/02-G1业务需求（正式版）.md》
- 《开发文档/20-G1-M3交易记录与持仓管理技术设计单.md》 (v1.2 终极修订版)
- 《RED-TEAM-AUDIT-G1-M3-02 (v1.2 终审)》
"""

import asyncio
import sys
import os
import pytest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import init_db, engine
from sqlalchemy import text

@pytest.mark.asyncio
async def test_red_team_g1_m3_all_attacks():
    """红队全链路攻击对抗测试主流程"""
    await init_db()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM trade_note;"))
        await conn.execute(text("DELETE FROM position;"))
        await conn.execute(text("DELETE FROM trade_record;"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        # =====================================================================
        # 攻击 1：【AC-1 不可篡改与冲正物理隔离攻击 (BUY & SELL 双向穿透)】
        # =====================================================================
        # 1.1 探测是否存在就地修改或删除接口 (PUT / DELETE)
        r_del = await client.delete("/api/v1/trading/records/1")
        assert r_del.status_code in (404, 405), "安全阻断失败：严禁提供 DELETE /records/{id} 接口！"
        r_put = await client.put("/api/v1/trading/records/1", json={"price": 100})
        assert r_put.status_code in (404, 405), "安全阻断失败：严禁提供 PUT /records/{id} 接口！"

        # 1.2 误买入冲正攻击：模拟误买 100 股贵州茅台 @ 1600.00，持仓应建立；冲正后持仓必须物理清空，统计中绝对不能有卖出结算！
        r_mis_buy = await client.post("/api/v1/trading/records", json={
            "code": "600519",
            "name": "贵州茅台",
            "direction": "buy",
            "price": 1600.00,
            "quantity": 100,
            "trade_time": "2026-09-26 09:30:00",
            "trade_reason": "红队误录买入测试",
            "idempotency_key": "atk_mis_buy_01"
        })
        assert r_mis_buy.status_code == 200
        mis_buy_id = r_mis_buy.json()["data"]["id"]

        # 发起冲正
        r_rev_buy = await client.post("/api/v1/trading/records/reverse", json={
            "target_record_id": mis_buy_id,
            "reason": "误买立即冲正",
            "idempotency_key": "atk_rev_buy_01"
        })
        assert r_rev_buy.status_code == 200
        assert r_rev_buy.json()["data"]["record_type"] == "REVERSAL"
        assert r_rev_buy.json()["data"]["reversed_record_id"] == mis_buy_id

        # 查验持仓：贵州茅台持仓已彻底归零，不在有效持仓列表
        r_pos = await client.get("/api/v1/trading/positions?refresh_quote=false")
        assert not any(p["code"] == "600519" for p in r_pos.json()["data"]), "持仓复原失败：冲正后持仓未归零！"

        # 查验统计：冲正对必须 100% 物理隔离，闭环卖出数必须为 0，胜率必须为 None，盈亏必须为 0
        r_stats = await client.get("/api/v1/trading/stats")
        stats_data = r_stats.json()["data"]
        assert stats_data["closed_trades"] == 0, "统计污染击穿：冲正卖出被计入了 closed_trades！"
        assert stats_data["closed_leg_win_rate"] is None, "胜率伪造击穿：无有效平仓时胜率未输出 None！"
        assert stats_data["total_realized_pnl"] == 0.0, "盈亏凭空捏造：冲正产生了虚假盈亏！"

        # 1.3 冲正反向攻击：尝试对冲正记录发起二次冲正，必须被 400 拦截
        rev_id = r_rev_buy.json()["data"]["id"]
        r_rev_rev = await client.post("/api/v1/trading/records/reverse", json={
            "target_record_id": rev_id,
            "reason": "试图冲正冲正单",
        })
        assert r_rev_rev.status_code == 400, "状态机破坏：允许对冲正流水再次冲正！"

        # 1.4 重复冲正攻击：尝试对已被冲正的记录再次冲正，必须被 400 拦截
        r_rev_dup = await client.post("/api/v1/trading/records/reverse", json={
            "target_record_id": mis_buy_id,
            "reason": "试图重复冲正",
        })
        assert r_rev_dup.status_code == 400, "并发一致性被破：允许对同一错账重复冲正！"


        # =====================================================================
        # 攻击 2：【AC-2 持仓派生与超卖强拦截破坏测试】
        # =====================================================================
        # 2.1 无持仓超卖攻击：从未买入过平安银行 (000001)，直接发起卖出
        r_oversell_0 = await client.post("/api/v1/trading/records", json={
            "code": "000001",
            "direction": "sell",
            "price": 10.50,
            "quantity": 100,
            "trade_time": "2026-09-26 10:00:00",
            "trade_reason": "空手套白狼超卖",
        })
        assert r_oversell_0.status_code == 400, "风控击穿：允许无仓做空！"
        assert r_oversell_0.json()["detail"]["error_type"] == "INSUFFICIENT_POSITION_ERROR"

        # 2.2 买入 200 股平安银行 @ 10.00
        await client.post("/api/v1/trading/records", json={
            "code": "000001",
            "name": "平安银行",
            "direction": "buy",
            "price": 10.00,
            "quantity": 200,
            "trade_time": "2026-09-26 10:05:00",
        })

        # 2.3 持有 200 股试图卖出 201 股（差 1 股越界超卖攻击）
        r_oversell_1 = await client.post("/api/v1/trading/records", json={
            "code": "000001",
            "direction": "sell",
            "price": 11.00,
            "quantity": 201,
            "trade_time": "2026-09-26 10:10:00",
        })
        assert r_oversell_1.status_code == 400, "风控击穿：允许超持仓数量卖出！"

        # 2.4 加权移动平均成本核算攻击：
        # 再加仓买入 300 股 @ 12.00
        # 当前持有: 200 @ 10.00 (总成本 2000) + 300 @ 12.00 (总成本 3600) = 500 股，总成本 5600，均价 11.200
        await client.post("/api/v1/trading/records", json={
            "code": "000001",
            "direction": "buy",
            "price": 12.00,
            "quantity": 300,
            "trade_time": "2026-09-26 10:15:00",
        })
        pos_check = (await client.get("/api/v1/trading/positions?refresh_quote=false")).json()["data"]
        pos_pa = next(p for p in pos_check if p["code"] == "000001")
        assert pos_pa["quantity"] == 500
        assert pos_pa["avg_cost"] == 11.200
        assert pos_pa["total_cost"] == 5600.00

        # 分批减仓 200 股 @ 13.20（盈利 (13.20 - 11.20) * 200 = 400.00）
        await client.post("/api/v1/trading/records", json={
            "code": "000001",
            "direction": "sell",
            "price": 13.20,
            "quantity": 200,
            "trade_time": "2026-09-26 10:20:00",
        })
        pos_check2 = (await client.get("/api/v1/trading/positions?refresh_quote=false")).json()["data"]
        pos_pa2 = next(p for p in pos_check2 if p["code"] == "000001")
        # 剩余 300 股，均价依然精确维持 11.200，总成本 3360.00，无浮点漂移
        assert pos_pa2["quantity"] == 300
        assert pos_pa2["avg_cost"] == 11.200
        assert pos_pa2["total_cost"] == 3360.00


        # =====================================================================
        # 攻击 3：【AC-3 幂等性与 60s 指纹防重攻击】
        # =====================================================================
        # 3.1 相同 idempotency_key 幂等攻击：重复请求应直接返回原记录，持仓绝不加倍
        payload_idem = {
            "code": "600036",
            "name": "招商银行",
            "direction": "buy",
            "price": 35.00,
            "quantity": 100,
            "trade_time": "2026-09-26 11:00:00",
            "idempotency_key": "fixed_idem_uuid_001"
        }
        r_id1 = await client.post("/api/v1/trading/records", json=payload_idem)
        assert r_id1.status_code == 200
        id1 = r_id1.json()["data"]["id"]

        r_id2 = await client.post("/api/v1/trading/records", json=payload_idem)
        assert r_id2.status_code == 200
        assert r_id2.json()["data"]["id"] == id1, "幂等键击穿：相同 idempotency_key 创建了不同记录！"

        pos_cmb = next(p for p in (await client.get("/api/v1/trading/positions?refresh_quote=false")).json()["data"] if p["code"] == "600036")
        assert pos_cmb["quantity"] == 100, "持仓翻倍灾难：幂等重试导致持仓被多次累加！"

        # 3.2 60s 业务指纹防重攻击（无 idempotency_key 但五元组一模一样）
        payload_dup = {
            "code": "600036",
            "direction": "buy",
            "price": 35.00,
            "quantity": 100,
            "trade_time": "2026-09-26 11:00:00",
        }
        r_dup = await client.post("/api/v1/trading/records", json=payload_dup)
        assert r_dup.status_code == 409, "指纹防重击穿：相同五元组未被 409 拦截！"


        # =====================================================================
        # 攻击 4：【AC-4 反思笔记 1:1 强绑定与增量反思攻击】
        # =====================================================================
        # 为招商银行流水添加初次反思笔记
        r_note1 = await client.post("/api/v1/trading/notes", json={
            "trade_id": id1,
            "date": "2026-09-26",
            "mental_state": "冷静从容",
            "decision_logic": "破净高股息防御",
            "reflection": "早盘开仓位置适中",
            "lessons": "坚守价值原则",
            "append_mode": True
        })
        assert r_note1.status_code == 200
        note1 = r_note1.json()["data"]
        assert note1["trade_id"] == id1

        # 模拟盘后增量追加反思
        r_note2 = await client.post("/api/v1/trading/notes", json={
            "trade_id": id1,
            "date": "2026-09-26",
            "reflection": "收盘表现抗跌，与大盘背离显现韧性",
            "append_mode": True
        })
        assert r_note2.status_code == 200
        note2 = r_note2.json()["data"]
        assert note2["id"] == note1["id"], "1:1契约击穿：为同一交易创建了多条笔记记录！"
        assert "早盘开仓位置适中" in note2["reflection"], "覆写破坏：增量追加冲掉了历史反思！"
        assert "收盘表现抗跌" in note2["reflection"], "增量丢失：新反思未成功追加！"
        assert "追加]:" in note2["reflection"], "规范违背：未自动带上时间戳追加标记！"

        # 4.2 关联不存在流水的外键攻击
        r_note_ghost = await client.post("/api/v1/trading/notes", json={
            "trade_id": 999999,
            "date": "2026-09-26",
            "reflection": "幽灵笔记",
        })
        assert r_note_ghost.status_code == 404, "外键约束击穿：允许为不存在的流水关联笔记！"


        # =====================================================================
        # 攻击 5：【AC-5 / AC-6 极端数学统计与全量对账一致性测试】
        # =====================================================================
        # 当前仅有一笔平仓：平安银行卖出 200 股 @ 13.20 (成本 11.20)，实现盈亏 +400.00
        stats_final = (await client.get("/api/v1/trading/stats")).json()["data"]
        assert stats_final["closed_trades"] == 1
        assert stats_final["win_trades"] == 1
        assert stats_final["loss_trades"] == 0
        assert stats_final["closed_leg_win_rate"] == 100.0
        # 只有盈利单没有亏损单，盈亏比必须输出 None，绝不能除以 0 崩溃
        assert stats_final["payoff_ratio"] is None
        assert stats_final["total_realized_pnl"] == 400.00

        # 全量对账重建测试：调用 /reconcile，持仓必须与当前状态完全相同
        r_rec = await client.post("/api/v1/trading/reconcile")
        assert r_rec.status_code == 200
        assert r_rec.json()["data"]["status"] == "SUCCESS"

        pos_reconciled = (await client.get("/api/v1/trading/positions?refresh_quote=false")).json()["data"]
        pa_rec = next(p for p in pos_reconciled if p["code"] == "000001")
        assert pa_rec["quantity"] == 300
        assert pa_rec["avg_cost"] == 11.200


        # =====================================================================
        # 攻击 6：【参数边界与注入攻击】
        # =====================================================================
        # 非法代码格式注入
        bad_codes = ["60051", "6005199", "SZ0001", "'; DROP TABLE trade_record;--"]
        for bc in bad_codes:
            r_bad = await client.post("/api/v1/trading/records", json={
                "code": bc,
                "direction": "buy",
                "price": 10.0,
                "quantity": 100,
                "trade_time": "2026-09-26 12:00:00"
            })
            assert r_bad.status_code == 422, f"代码强校验击穿：非法代码 {bc} 未被 422 拦截！"

        # 非法价格或数量
        r_bad_price = await client.post("/api/v1/trading/records", json={
            "code": "000001",
            "direction": "buy",
            "price": -10.0,
            "quantity": 100,
            "trade_time": "2026-09-26 12:00:00"
        })
        assert r_bad_price.status_code == 422, "负单价未被拦截！"

        r_bad_qty = await client.post("/api/v1/trading/records", json={
            "code": "000001",
            "direction": "buy",
            "price": 10.0,
            "quantity": 0,
            "trade_time": "2026-09-26 12:00:00"
        })
        assert r_bad_qty.status_code == 422, "零股数未被拦截！"

    print("\n✅ [RED TEAM STRESS TEST] 所有 6 大破坏性攻击向量测试全部执行并通过！系统防御坚固！")

if __name__ == "__main__":
    asyncio.run(test_red_team_g1_m3_all_attacks())
