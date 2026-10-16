import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app

@pytest.mark.asyncio
async def test_stock_trends_api_contract():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/v1/market/stock-trends?codes=002696,BK0480")
        assert response.status_code == 200
        payload = response.json()
        assert payload.get("code") == 200
        data = payload.get("data")
        assert isinstance(data, list)
        if data:
            first = data[0]
            assert "code" in first
            assert "name" in first
            assert "pre_close" in first
            assert "trends" in first
            assert isinstance(first["trends"], list)
            if first["trends"]:
                pt = first["trends"][0]
                assert "time" in pt
                assert "price" in pt
                assert "pct_change" in pt
                assert "amount" in pt
