import pytest
from unittest.mock import patch, AsyncMock
from backend.app.data.providers.tonghuashun import TongHuaShunProvider
from backend.app.data.providers.eastmoney import EastmoneyProvider
from backend.app.data.capabilities import DataQuality, DataStatus

@pytest.mark.asyncio
async def test_tonghuashun_provider_enriched_parsing():
    """验证 TongHuaShunProvider 是否完整保留并解析跌停板、炸板大面标的与涨停封单明细"""
    provider = TongHuaShunProvider()

    mock_zt_resp = {
        "data": {
            "tc": 2,
            "pool": [
                {
                    "c": "002058", "n": "威尔泰", "p": 24440, "zdp": 9.99,
                    "amount": 100791831, "ltsz": 3503860934.0, "hs": 2.88,
                    "lbc": 4, "fbt": 92500, "lbt": 92500, "fund": 89302489,
                    "zbc": 0, "hybk": "专用设备", "zttj": {"days": 4, "ct": 4}
                },
                {
                    "c": "603001", "n": "奥康国际", "p": 12500, "zdp": 10.02,
                    "amount": 50000000, "ltsz": 2000000000.0, "hs": 2.50,
                    "lbc": 1, "fbt": 93012, "lbt": 94500, "fund": 12000000,
                    "zbc": 2, "hybk": "纺织服装", "zttj": {"days": 1, "ct": 1}
                }
            ]
        }
    }

    mock_dt_resp = {
        "data": {
            "tc": 1,
            "pool": [
                {
                    "c": "603400", "n": "华之杰", "p": 42930, "zdp": -10.0,
                    "amount": 286680592, "hs": 18.13, "fund": 3142476,
                    "lbt": 150000, "days": 2, "hybk": "通用设备"
                }
            ]
        }
    }

    mock_zb_resp = {
        "data": {
            "tc": 1,
            "pool": [
                {
                    "c": "605303", "n": "园林股份", "p": 32210, "ztp": 34680, "zdp": 2.16,
                    "amount": 849336400, "hs": 16.30, "fbt": 92502, "zbc": 1,
                    "zf": 17.76, "hybk": "建筑装饰"
                }
            ]
        }
    }

    class MockResponse:
        def __init__(self, data):
            self._data = data
            self.status_code = 200
            self.text = "ok"

        def json(self):
            return self._data

    async def mock_get(url, *args, **kwargs):
        if "getTopicZTPool" in url:
            return MockResponse(mock_zt_resp)
        elif "getTopicDTPool" in url:
            return MockResponse(mock_dt_resp)
        elif "getTopicZBPool" in url:
            return MockResponse(mock_zb_resp)
        return MockResponse({})

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        res = await provider.get_limit_up_pool("2026-10-09")

    assert res.quality == DataQuality.FULL
    assert res.data is not None
    data = res.data

    # 1. 验证常规统计
    assert data["total_count"] == 2
    assert data["limit_down_count"] == 1
    assert data["broken_limit_count"] == 1
    assert data["max_height"] == 4
    assert data["broken_limit_ratio"] == round(1 / 3, 4)

    # 2. 验证涨停池细化指标
    items = data["items"]
    assert len(items) == 2
    top1 = items[0]
    assert top1["code"] == "002058"
    assert top1["fund_wan"] == 8930.25
    assert top1["fund_yi"] == 0.893
    assert top1["amount_yi"] == 1.0079
    assert top1["turnover_ratio"] == 2.88
    assert top1["open_count"] == 0
    assert top1["fbt_str"] == "09:25:00"

    top2 = items[1]
    assert top2["open_count"] == 2
    assert top2["fbt_str"] == "09:30:12"
    assert top2["lbt_str"] == "09:45:00"

    # 3. 验证跌停池标的榜单 (核按钮榜)
    dt_items = data["limit_down_items"]
    assert len(dt_items) == 1
    dt_top = dt_items[0]
    assert dt_top["code"] == "603400"
    assert dt_top["name"] == "华之杰"
    assert dt_top["price"] == 42.93
    assert dt_top["pct_change"] == -10.0
    assert dt_top["amount_yi"] == 2.8668
    assert dt_top["fund_wan"] == 314.25
    assert dt_top["turnover_ratio"] == 18.13
    assert dt_top["days"] == 2
    assert dt_top["lbt_str"] == "15:00:00"
    assert dt_top["sector"] == "通用设备"

    # 4. 验证炸板大面榜单 (日内跳水亏钱榜)
    zb_items = data["broken_limit_items"]
    assert len(zb_items) == 1
    zb_top = zb_items[0]
    assert zb_top["code"] == "605303"
    assert zb_top["name"] == "园林股份"
    assert zb_top["price"] == 32.21
    assert zb_top["limit_up_price"] == 34.68
    assert zb_top["pct_change"] == 2.16
    assert zb_top["fall_back_pct"] == 15.6  # 17.76 - 2.16
    assert zb_top["amount_yi"] == 8.4934
    assert zb_top["turnover_ratio"] == 16.30
    assert zb_top["open_count"] == 1
    assert zb_top["fbt_str"] == "09:25:02"
    assert zb_top["amplitude"] == 17.76


@pytest.mark.asyncio
async def test_eastmoney_provider_sectors_with_capital_flow():
    """验证 EastmoneyProvider 行业与概念板块是否返回成交额、主力资金流向及领涨龙头"""
    provider = EastmoneyProvider()

    mock_clist_resp = {
        "data": {
            "diff": [
                {
                    "f12": "BK1296", "f14": "短剧互动游戏", "f2": 1500.2, "f3": 19.98,
                    "f6": 2385000000.0, "f62": 268000000.0,
                    "f128": "天威视讯", "f140": "002238", "f136": 19.98
                },
                {
                    "f12": "BK1518", "f14": "华为算力", "f2": 2100.5, "f3": 7.78,
                    "f6": 6952000000.0, "f62": 808000000.0,
                    "f128": "恒银科技", "f140": "603106", "f136": 9.99
                }
            ]
        }
    }

    class MockResponse:
        def __init__(self, data):
            self._data = data
            self.status_code = 200
            self.text = "ok"

        def json(self):
            return self._data

    with patch("httpx.AsyncClient.get", return_value=MockResponse(mock_clist_resp)):
        res = await provider.get_top_sectors(limit=5, sector_type="concept")

    assert res.quality == DataQuality.FULL
    assert res.data is not None
    sectors = res.data
    assert len(sectors) == 2

    s1 = sectors[0]
    assert s1["code"] == "BK1296"
    assert s1["name"] == "短剧互动游戏"
    assert s1["pct_change"] == 19.98
    assert s1["amount_yi"] == 23.85
    assert s1["net_inflow_yi"] == 2.68
    assert s1["leader_name"] == "天威视讯"
    assert s1["leader_code"] == "002238"
    assert s1["leader_pct"] == 19.98

    s2 = sectors[1]
    assert s2["code"] == "BK1518"
    assert s2["name"] == "华为算力"
    assert s2["amount_yi"] == 69.52
    assert s2["net_inflow_yi"] == 8.08
    assert s2["leader_name"] == "恒银科技"
    assert s2["leader_pct"] == 9.99

    # 验证 SectorCapability 抽象方法对接
    with patch("httpx.AsyncClient.get", return_value=MockResponse(mock_clist_resp)):
        res_ranking = await provider.get_sector_ranking(sector_type="industry")
    assert res_ranking.quality == DataQuality.FULL
    assert len(res_ranking.data) == 2


@pytest.mark.asyncio
async def test_market_api_limit_up_and_sectors():
    """验证 REST API /api/v1/market/limit-up 和 /api/v1/market/sectors 正确暴露细化指标"""
    from httpx import AsyncClient, ASGITransport
    from backend.app.main import app

    mock_sectors_payload = [
        {
            "code": "BK1296", "name": "短剧互动游戏", "price": 1500.2, "pct_change": 19.98,
            "amount_yi": 23.85, "net_inflow_yi": 2.68,
            "leader_name": "天威视讯", "leader_code": "002238", "leader_pct": 19.98
        }
    ]

    mock_limit_up_payload = {
        "total_count": 35,
        "max_height": 5,
        "first_limit_count": 25,
        "continued_count": 10,
        "limit_down_count": 3,
        "broken_limit_count": 12,
        "broken_limit_ratio": 0.2553,
        "top_reasons": [["华为算力", 12], ["跨境电商", 5]],
        "items": [
            {
                "code": "603106", "name": "恒银科技", "lbc": 5,
                "fund_wan": 15600.0, "fund_yi": 1.56, "open_count": 0,
                "turnover_ratio": 5.2, "amount_yi": 4.5
            }
        ],
        "limit_down_items": [
            {
                "code": "000001", "name": "测试跌停", "price": 9.5, "pct_change": -10.0,
                "fund_wan": 500.0, "amount_yi": 1.2, "days": 1
            }
        ],
        "broken_limit_items": [
            {
                "code": "000002", "name": "测试炸板", "price": 10.2, "limit_up_price": 11.0,
                "pct_change": 2.0, "fall_back_pct": 8.0, "amount_yi": 3.4, "open_count": 2
            }
        ]
    }

    from backend.app.data.capabilities import DataResult, DataQuality
    from backend.app.data.service import DataService

    with patch.object(DataService, "get_limit_up_pool", return_value=DataResult(data=mock_limit_up_payload, quality=DataQuality.FULL, provider="tonghuashun")), \
         patch.object(DataService, "get_sector_ranking", return_value=DataResult(data=mock_sectors_payload, quality=DataQuality.FULL, provider="eastmoney")):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. 验证 limit-up 包含核按钮榜与大面榜
            resp_lu = await client.get("/api/v1/market/limit-up")
            assert resp_lu.status_code == 200
            json_lu = resp_lu.json()
            assert json_lu["code"] == 200
            assert "limit_down_items" in json_lu["data"]
            assert len(json_lu["data"]["limit_down_items"]) == 1
            assert json_lu["data"]["limit_down_items"][0]["code"] == "000001"

            assert "broken_limit_items" in json_lu["data"]
            assert len(json_lu["data"]["broken_limit_items"]) == 1
            assert json_lu["data"]["broken_limit_items"][0]["fall_back_pct"] == 8.0

            assert json_lu["data"]["items"][0]["fund_wan"] == 15600.0

            # 2. 验证 sectors 包含资金流与领涨龙头
            resp_sec = await client.get("/api/v1/market/sectors?sector_type=industry&limit=10")
            assert resp_sec.status_code == 200
            json_sec = resp_sec.json()
            assert json_sec["code"] == 200
            sec_items = json_sec["data"]
            assert len(sec_items) == 1
            assert sec_items[0]["net_inflow_yi"] == 2.68
            assert sec_items[0]["leader_name"] == "天威视讯"

