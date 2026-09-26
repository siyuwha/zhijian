import asyncio
import sys
import os
import json
from datetime import datetime
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import init_db, engine
from sqlalchemy import text

@pytest.mark.asyncio
async def test_cognition_validation_loop():
    """
    G1-Cognition 验证闭环增强 (Cognitive Validation Loop MVP) 自动化测试套件
    覆盖 v1.2 设计单 AC-1 ~ AC-6 刚性契约
    """
    await init_db()
    # 1. 清理测试表保证隔离
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM hypothesis_verification;"))
        await conn.execute(text("DELETE FROM market_hypothesis;"))
        await conn.execute(text("DELETE FROM cognitive_trade_diagnosis;"))
        await conn.execute(text("DELETE FROM trade_note;"))
        await conn.execute(text("DELETE FROM position;"))
        await conn.execute(text("DELETE FROM trade_record;"))
        await conn.execute(text("DELETE FROM cognition_market_state;"))
        await conn.execute(text("DELETE FROM auction_report;"))
        await conn.execute(text("DELETE FROM daily_review;"))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # =====================================================================
        # 测试 1: 准备基础数据 (交易事实 + 市场客观状态)
        # =====================================================================
        today_str = datetime.now().strftime("%Y-%m-%d")
        now_time_str = f"{today_str} 10:00:00"

        # 录入一笔买入交易
        r_trade = await client.post("/api/v1/trading/records", json={
            "code": "000001",
            "name": "平安银行",
            "direction": "buy",
            "price": 10.0,
            "quantity": 1000,
            "trade_time": now_time_str,
            "trade_reason": "核心突破买入预案",
            "idempotency_key": "test_cog_trade_01"
        })
        assert r_trade.status_code == 200
        trade_id = r_trade.json()["data"]["id"]

        # 添加 TradeNote 主观反思笔记
        r_note = await client.post("/api/v1/trading/notes", json={
            "trade_id": trade_id,
            "date": today_str,
            "mental_state": "冷静执行预案",
            "decision_logic": "核心突破买入预案，预期目标5%",
            "reflection": "开盘集合竞价确认强度后买入",
            "lessons": "严格执行止损线",
            "append_mode": True
        })
        assert r_note.status_code == 200

        # 伪造当日六维市场状态向量 (D1~D6)
        async with engine.begin() as conn:
            indicators_json = json.dumps([
                {"dimension": "D1趋势与动量", "score": 75.0},
                {"dimension": "D3结构分化", "score": 30.0},
                {"dimension": "D5情绪连板", "score": 80.0},
            ], ensure_ascii=False)
            await conn.execute(text(
                "INSERT INTO cognition_market_state (date, timestamp, indicators, composite_score, state_label, data_quality) "
                "VALUES (:d, :t, :ind, :cs, :sl, 'full')"
            ), {
                "d": today_str,
                "t": "15:30:00",
                "ind": indicators_json,
                "cs": 75.0,
                "sl": "主升共振强市"
            })

        # =====================================================================
        # 测试 2: 【AC-1 事实与解释双层隔离】触发单笔交易认知诊断
        # =====================================================================
        r_diag = await client.post(f"/api/v1/cognition/diagnosis/trade/{trade_id}")
        assert r_diag.status_code == 200
        diag_data = r_diag.json()["data"]

        # 事实层断言
        assert diag_data["trade_id"] == trade_id
        assert diag_data["trade_price"] == 10.0
        assert diag_data["trade_amount"] == 10000.0
        assert diag_data["market_d1_d6_snapshot"]["state_label"] == "主升共振强市"

        # 解释层断言: 顺势主升共振环境
        assert diag_data["env_match_type"] == "HIGH_MATCH"
        assert diag_data["logic_realization"] == "REALIZED"
        assert diag_data["env_match_score"] is None  # 拒绝拍脑袋标量打分
        # 人机回环初始状态断言
        assert diag_data["human_status"] == "UNCONFIRMED"

        # =====================================================================
        # 测试 3: 【AC-2 未确认隔离铁律】周度复盘统计样本纯净度检验
        # =====================================================================
        # 当前有 1 笔交易，但 human_status 为 UNCONFIRMED，绝不能计入周度复盘！
        r_audit_unconfirmed = await client.get("/api/v1/cognition/audit/weekly?week_offset=0")
        assert r_audit_unconfirmed.status_code == 200
        audit_res = r_audit_unconfirmed.json()["data"]

        assert audit_res["total_trades"] == 1
        assert audit_res["confirmed_samples_count"] == 0
        # 样本为空，三维指标必须严格输出 None (前端呈现 --)
        assert audit_res["metrics"]["env_match_degree"] is None
        assert audit_res["metrics"]["logic_realization_degree"] is None
        assert audit_res["metrics"]["outcome_deviation_degree"] is None

        # =====================================================================
        # 测试 4: 【人机审定回环】确认单笔诊断并核验周报计算 (EMD / LRD)
        # =====================================================================
        r_confirm = await client.put(f"/api/v1/cognition/diagnosis/trade/{trade_id}/confirm", json={
            "human_status": "CONFIRMED",
            "human_comment": "完全符合开盘预案，采纳 AI 诊断"
        })
        assert r_confirm.status_code == 200
        assert r_confirm.json()["data"]["human_status"] == "CONFIRMED"

        # 确认后重新拉取周报
        r_audit_confirmed = await client.get("/api/v1/cognition/audit/weekly?week_offset=0")
        assert r_audit_confirmed.status_code == 200
        audit_confirmed_res = r_audit_confirmed.json()["data"]

        assert audit_confirmed_res["confirmed_samples_count"] == 1
        assert audit_confirmed_res["metrics"]["env_match_degree"] == 100.0  # 1/1 为 HIGH_MATCH
        assert audit_confirmed_res["metrics"]["logic_realization_degree"] == 100.0  # 1/1 为 REALIZED

        # =====================================================================
        # 测试 5: 【AC-3 验证表联合唯一键物理约束】推演假说创建与双阶段快照追加
        # =====================================================================
        target_monday = "2026-09-28"
        r_hypo = await client.post("/api/v1/cognition/hypotheses", json={
            "target_date": target_monday,
            "hypothesis_type": "SECTOR_LEADER",
            "target_asset": "芯片半导体核心龙头",
            "expected_scenario": "DIVERGENCE",
            "premise_logic": "周末自主可控利好发酵，但外盘半导体大跌",
            "expected_phenomenon": "早盘开盘小幅低开后迅速企稳，成交量维持前三",
            "invalidation_condition": "开盘大幅低开超-3%且跌停家数大于3家",
            "assertion_metrics": {"sh_open_pct_min": -0.5}
        })
        assert r_hypo.status_code == 200
        hypo_id = r_hypo.json()["data"]["id"]
        assert r_hypo.json()["data"]["status"] == "PENDING"

        # 阶段 1: 触发早盘竞价事实验证 (此时无真实竞价数据，断言 INCONCLUSIVE 防伪)
        r_v_auction = await client.post(f"/api/v1/cognition/hypotheses/{hypo_id}/verify?stage=AUCTION_0925")
        assert r_v_auction.status_code == 200
        v_auc_data = r_v_auction.json()["data"]
        assert v_auc_data["verification_stage"] == "AUCTION_0925"
        assert v_auc_data["outcome"] == "INCONCLUSIVE"  # 数据缺失坚决断言 INCONCLUSIVE

        # 阶段 2: 伪造竞价真实数据并再次验证
        # 由于联合唯一键存在，已有 AUCTION_0925 快照不会被覆盖
        r_v_dup = await client.post(f"/api/v1/cognition/hypotheses/{hypo_id}/verify?stage=AUCTION_0925")
        assert r_v_dup.status_code == 200
        assert r_v_dup.json()["data"]["id"] == v_auc_data["id"]  # 幂等返回已有快照

        # 阶段 3: 触发收盘事实验证 (AUCTION_0925 与 CLOSE_1530 联合唯一键和平共存)
        r_v_close = await client.post(f"/api/v1/cognition/hypotheses/{hypo_id}/verify?stage=CLOSE_1530")
        assert r_v_close.status_code == 200
        v_close_data = r_v_close.json()["data"]
        assert v_close_data["verification_stage"] == "CLOSE_1530"
        # 此时收盘数据缺失，同样断言为 INCONCLUSIVE
        assert v_close_data["outcome"] == "INCONCLUSIVE"

        # =====================================================================
        # 测试 6: 查询假说列表，断言关联两条独立历史快照
        # =====================================================================
        r_list = await client.get(f"/api/v1/cognition/hypotheses?target_date={target_monday}")
        assert r_list.status_code == 200
        hypo_list = r_list.json()["data"]["items"]
        assert len(hypo_list) == 1
        target_h = hypo_list[0]
        assert len(target_h["verifications"]) == 2  # 早盘与收盘两条独立快照并存！
        stages = [v["verification_stage"] for v in target_h["verifications"]]
        assert "AUCTION_0925" in stages
        assert "CLOSE_1530" in stages

    print("\n[SUCCESS] [COGNITION TEST] G1-Cognition Validation Loop All 6 core test assertions 100% PASSED!")

if __name__ == "__main__":
    asyncio.run(test_cognition_validation_loop())
