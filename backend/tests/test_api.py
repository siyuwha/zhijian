import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from httpx import AsyncClient, ASGITransport
from app.main import app

async def test_backend_core_flows():
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
        r_rev = await client.post("/api/v1/reports/daily-review/generate")
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

if __name__ == "__main__":
    asyncio.run(test_backend_core_flows())
    print("All backend tests passed!")
