import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import init_db

async def test_backend_core_flows():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        r_health = await client.get("/health")
        assert r_health.status_code == 200
        assert r_health.json()["status"] == "ok"

        # 2. Market indices
        r_indices = await client.get("/api/v1/market/indices")
        assert r_indices.status_code == 200
        assert r_indices.json()["code"] == 200

        # 3. Cognition indicators config
        r_cog = await client.get("/api/v1/cognition/config/indicators")
        assert r_cog.status_code == 200

        # 4. Generate Review (M1)
        r_rev = await client.post("/api/v1/reports/daily-review/generate?force=true")
        assert r_rev.status_code == 200
        gen_data = r_rev.json()
        assert gen_data["code"] == 200
        rev_date = gen_data["date"]

        # 5. List Reviews (M1 list endpoint)
        r_list = await client.get("/api/v1/reports/daily-review")
        assert r_list.status_code == 200
        list_data = r_list.json()
        assert list_data["code"] == 200
        assert "items" in list_data["data"]
        assert list_data["data"]["total"] >= 1

        # 6. Get Daily Review Detail (M1 detail endpoint)
        r_detail = await client.get(f"/api/v1/reports/daily-review/{rev_date}")
        assert r_detail.status_code == 200
        detail_data = r_detail.json()
        assert detail_data["code"] == 200
        assert "market_state" in detail_data["data"]
        assert detail_data["data"]["market_state"] is not None
        assert "dimensions" in detail_data["data"]["market_state"]
        # 验证 1A.2 状态向量：D3 双子域与 score 为 None
        d3_data = detail_data["data"]["market_state"]["dimensions"].get("D3")
        assert d3_data is not None
        assert d3_data.get("score") is None
        assert "sub_domains" in d3_data
        assert "speculative_structure" in d3_data["sub_domains"]
        assert "tail_extremes" in d3_data["sub_domains"]

        # 7. Generate Premarket Briefing (M2)
        r_pre = await client.post("/api/v1/reports/premarket/generate?force=true")
        assert r_pre.status_code == 200
        pre_gen_data = r_pre.json()
        assert pre_gen_data["code"] == 200
        pre_date = pre_gen_data["date"]

        # 8. List Premarket Briefings (M2 list endpoint)
        r_pre_list = await client.get("/api/v1/reports/premarket")
        assert r_pre_list.status_code == 200
        pre_list_data = r_pre_list.json()
        assert pre_list_data["code"] == 200
        assert "items" in pre_list_data["data"]
        assert pre_list_data["data"]["total"] >= 1
        first_item = pre_list_data["data"]["items"][0]
        assert "yesterday_state_label" in first_item

        # 9. Get Premarket Briefing Detail (M2 detail endpoint)
        r_pre_detail = await client.get(f"/api/v1/reports/premarket/{pre_date}")
        assert r_pre_detail.status_code == 200
        pre_detail_data = r_pre_detail.json()
        assert pre_detail_data["code"] == 200
        data = pre_detail_data["data"]
        assert "overnight_summary" in data
        assert isinstance(data["overnight_summary"], list)
        assert "news_digest" in data
        assert isinstance(data["news_digest"], list)
        assert "yesterday_review_summary" in data
        assert "today_focus" in data
        assert len(data["today_focus"]) == 4

        # 10. M2 铁律断言：D3 score 坚决为 None，推演维度客观免责
        if data["yesterday_review_summary"] and "dimensions" in data["yesterday_review_summary"]:
            yd_d3 = data["yesterday_review_summary"]["dimensions"].get("D3")
            if yd_d3:
                assert yd_d3.get("score") is None
                assert "sub_domains" in yd_d3

        for focus_item in data["today_focus"]:
            assert "disclaimer" in focus_item
            assert "非买卖建议" in focus_item["disclaimer"]
            assert focus_item["dimension"] in ["竞价量能", "高标溢价", "尾部极端", "外盘扰动"]

        # 11. Generate Auction Report (M3)
        r_auc = await client.post("/api/v1/reports/auction/generate?force=true")
        assert r_auc.status_code == 200
        auc_gen_data = r_auc.json()
        assert auc_gen_data["code"] == 200
        auc_date = auc_gen_data["date"]

        # 12. List Auction Reports (M3 list endpoint)
        r_auc_list = await client.get("/api/v1/reports/auction")
        assert r_auc_list.status_code == 200
        auc_list_data = r_auc_list.json()
        assert auc_list_data["code"] == 200
        assert "items" in auc_list_data["data"]
        assert auc_list_data["data"]["total"] >= 1
        first_auc = auc_list_data["data"]["items"][0]
        assert "emotion_label" in first_auc

        # 13. Get Auction Report Detail (M3 detail endpoint)
        r_auc_detail = await client.get(f"/api/v1/reports/auction/{auc_date}")
        assert r_auc_detail.status_code == 200
        auc_detail_data = r_auc_detail.json()
        assert auc_detail_data["code"] == 200
        auc_data = auc_detail_data["data"]
        assert "index_open_data" in auc_data
        assert "indices" in auc_data["index_open_data"]
        assert "one_word_count" in auc_data
        assert "high_open_stats" in auc_data
        assert "emotion_judgment" in auc_data
        assert "label" in auc_data["emotion_judgment"]
        assert "disclaimer" in auc_data["emotion_judgment"]
        assert "非买卖建议" in auc_data["emotion_judgment"]["disclaimer"]

        # 14. M3 铁律断言：绝无主观买卖指令，量能分母严谨
        narrative = auc_data["emotion_judgment"].get("narrative", "")
        for forbidden in ["建议买入", "强烈推荐", "打板买入", "挂单清仓", "开盘做多"]:
            assert forbidden not in narrative

        # 15. M4 Monitor Realtime Snapshot
        r_mon_rt = await client.get("/api/v1/monitor/realtime")
        assert r_mon_rt.status_code == 200
        mon_rt_data = r_mon_rt.json()["data"]
        assert "session_state" in mon_rt_data
        assert "macro" in mon_rt_data
        assert "watchlist" in mon_rt_data
        assert "disclaimer" in mon_rt_data
        assert "非买卖建议" in mon_rt_data["disclaimer"]

        # 16. M4 Monitor Series
        r_mon_series = await client.get("/api/v1/monitor/series")
        assert r_mon_series.status_code == 200
        mon_series_data = r_mon_series.json()["data"]
        assert isinstance(mon_series_data, list)

        # 17. M4 Monitor Events
        r_mon_events = await client.get("/api/v1/monitor/events")
        assert r_mon_events.status_code == 200
        mon_events_data = r_mon_events.json()["data"]
        assert isinstance(mon_events_data, list)

        # 18. M4 铁律断言：零买卖信号与免责隔离
        all_mon_text = f"{r_mon_rt.text} {r_mon_events.text}"
        for forbidden in ["买入", "卖出", "加仓", "建仓", "清仓", "打板建议", "主力吸筹", "止损点"]:
            assert forbidden not in all_mon_text

if __name__ == "__main__":
    asyncio.run(test_backend_core_flows())
    print("All backend tests passed!")


