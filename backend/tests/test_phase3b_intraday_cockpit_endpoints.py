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

        # 验证 Top 1 题材及领涨龙头
        top1 = data["sectors"][0]
        assert top1["rank"] == 1
        assert len(top1["name"]) > 0
        assert top1["leader"]["name"] != ""
        assert len(top1["trends"]) >= 10
        assert top1["trends"][0]["time"] == "09:30"
