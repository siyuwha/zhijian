import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.services.zhijian_transcendent_review_service import ZhijianTranscendentReviewService

@pytest.mark.asyncio
async def test_zhijian_service_baseline_fallback():
    """验证知见服务在离线或LLM故障时能正确优雅兜底 baseline 研报"""
    service = ZhijianTranscendentReviewService()
    facts = {
        "date": "2026-10-12",
        "turnover": {"total_amount": "1.54 万亿元"},
        "breadth": {"up": 1182, "down": 4371}
    }
    # 模拟 LLM 抛出异常
    with patch.object(service.llm_client, "call_stream_with_metrics", side_effect=Exception("Network error")):
        result = await service.generate_transcendent_review(facts)
        assert result["system_brand"] == "知见"
        assert len(result["skyline_ladder"]) >= 4
        assert len(result["mechanism_samples"]) == 6
        assert "1.54" in result["stats_summary"]["total_turnover"]
        assert len(result["markdown_content"]) > 1000

@pytest.mark.asyncio
async def test_zhijian_chat_endpoint():
    """验证 /api/v1/reports/daily-review/chat 认知问答端点"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "date": "2026-10-12",
            "query": "明天九阳股份如果低开超过-3%，该怎么应对？"
        }
        resp = await client.post("/api/v1/reports/daily-review/chat", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert "answer" in data["data"]
        assert len(data["data"]["answer"]) > 10
