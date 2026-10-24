"""
Tests for Phase 3B Intraday 4-Stage Briefing Timeline & Top 5 Sectors Trend Endpoints
"""

import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app


@pytest.mark.asyncio
async def test_get_intraday_briefings_timeline():
    """验证 4 大固定时段盘中操盘内参时间轴接口 (绝不覆盖早先时段)"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/canonical/intraday-briefings/2026-10-15")
        assert res.status_code == 200
        data = res.json()

        assert data["trade_date"] == "2026-10-15"
        assert "current_active_stage" in data
        assert "stages" in data
        assert len(data["stages"]) >= 1

        # 验证时段 1 (09:26 竞价定调)
        stage1 = data["stages"][0]
        assert stage1["stage"] == "STAGE_1_AUCTION"
        assert "09:26" in stage1["stage_label"]
        assert "强弱定调与宏微观证据" in stage1["strong_weak_judgment"]
        assert "成立条件" in stage1["falsification_criteria"]
        assert "不成立/证伪条件" in stage1["falsification_criteria"]
        assert stage1["quantitative_indicators"]["projected_volume"] != ""


@pytest.mark.asyncio
async def test_get_intraday_top_sectors_trend():
    """验证 Top 5 题材分时资金曲线与领涨核心龙头联动接口"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/canonical/intraday-top-sectors-trend?date=2026-10-15")
        assert res.status_code == 200
        data = res.json()

        assert data["trade_date"] == "2026-10-15"
        assert len(data["sectors"]) == 5

        # 验证 Top 1 题材及领涨龙头与升级梯队/跷跷板字段
        top1 = data["sectors"][0]
        assert top1["rank"] == 1
        assert len(top1["name"]) > 0
        assert top1["leader"]["name"] != ""
        assert len(top1["trends"]) >= 10
        assert top1["trends"][0]["time"] == "09:30"
        assert "echelon_summary" in top1
        assert "echelon_stocks" in top1
        assert "seesaw_analysis" in data


@pytest.mark.asyncio
async def test_intraday_game_cognition_and_history_audit():
    """验证 AI 题材轮动推演与当日触发轨迹历史留痕接口"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "trade_date": "2026-10-15",
            "stocks": [
                {
                    "code": "000001",
                    "name": "平安银行",
                    "changePct": 3.5,
                    "tagType": "yesterday_highest",
                    "roles": ["核心中军"],
                }
            ],
            "strongest_stock": {
                "code": "300033",
                "name": "同花顺",
                "sector": "金融科技",
                "changePct": 10.0,
            },
            "sectors": [
                {
                    "name": "金融科技",
                    "net": 18.5,
                    "leader": "同花顺",
                    "leaderPct": 10.0,
                    "amount_yi": 85.0,
                    "max_height": 3,
                    "limit_up_count": 5,
                },
                {
                    "name": "房地产",
                    "net": -12.3,
                    "leader": "万科A",
                    "leaderPct": -2.1,
                    "amount_yi": 45.0,
                    "max_height": 1,
                    "limit_up_count": 0,
                },
            ],
            "force_refresh": True,
        }

        # 1. 触发生成推演
        res = await client.post("/api/v1/canonical/intraday-game-cognition", json=payload)
        assert res.status_code == 200
        body = res.json()
        assert body["code"] == 200
        data = body["data"]
        assert "sector_rotation" in data
        assert "history" in data
        assert len(data["history"]) >= 1

        first_record = data["history"][0]
        assert "time" in first_record
        assert "event_type" in first_record
        assert first_record["lead_sector"] == "金融科技"
        assert first_record["tail_sector"] == "房地产"

        # 2. 独立拉取当日触发轨迹接口
        hist_res = await client.get("/api/v1/canonical/intraday-game-cognition/history?trade_date=2026-10-15")
        assert hist_res.status_code == 200
        hist_body = hist_res.json()
        assert hist_body["code"] == 200
        hist_records = hist_body["data"]
        assert isinstance(hist_records, list)
        assert len(hist_records) >= 1
        assert hist_records[0]["lead_sector"] == "金融科技"

