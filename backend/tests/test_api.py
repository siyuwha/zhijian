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

if __name__ == "__main__":
    asyncio.run(test_backend_core_flows())
    print("All backend tests passed!")
