import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from datetime import datetime

from backend.app.main import app
from backend.app.data.capabilities import DataResult, DataQuality, DataStatus
from backend.app.data.service import DataService
from backend.app.data.providers.tdx_client import TdxDirectClient
from backend.app.data.providers.tdx_provider import TdxProvider
from backend.app.data.providers.eastmoney import EastmoneyProvider


@pytest.mark.asyncio
async def test_api_date_passthrough_and_alias():
    """验证 /api/v1/market/stock-trends 支持 trade_date 与 date 别名参数透传"""
    with patch.object(DataService, "get_stock_trends", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = DataResult(
            data=[{"code": "002696", "name": "百洋股份", "pre_close": 10.73, "trends": [], "is_real": True}],
            quality=DataQuality.FULL,
            provider="test",
            missing_codes=[],
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            # 1. 显式 trade_date
            resp1 = await ac.get("/api/v1/market/stock-trends?codes=002696&trade_date=2026-10-27")
            assert resp1.status_code == 200
            assert mock_get.call_args[0][0] == ["002696"]
            assert mock_get.call_args[1].get("trade_date") == "2026-10-27"
            payload1 = resp1.json()
            assert payload1["code"] == 200
            assert "missing_codes" in payload1

            # 2. 别名 date 参数
            resp2 = await ac.get("/api/v1/market/stock-trends?codes=002696&date=2026-10-26")
            assert resp2.status_code == 200
            assert mock_get.call_args[1].get("trade_date") == "2026-10-26"

            # 3. 未传日期参数保持兼容 (None)
            resp3 = await ac.get("/api/v1/market/stock-trends?codes=002696")
            assert resp3.status_code == 200
            assert mock_get.call_args[1].get("trade_date") is None


@pytest.mark.asyncio
async def test_data_service_cache_isolation_by_date():
    """验证 DataService 缓存 key 完备包含交易日期，彻底杜绝不同日期串缓存"""
    service = DataService(session=None)
    DataService._CACHE.clear()

    call_history = []

    async def fake_execute_pipeline(capability, method, *args, **kwargs):
        call_history.append((args, kwargs))
        return DataResult(
            data=[{"code": args[0][0], "trends": []}],
            quality=DataQuality.FULL,
            provider="mock",
        )

    with patch.object(service, "_execute_pipeline", side_effect=fake_execute_pipeline):
        # 针对 2026-10-27 请求
        await service.get_stock_trends(["002696"], trade_date="2026-10-27")
        # 针对 2026-10-26 请求
        await service.get_stock_trends(["002696"], trade_date="2026-10-26")
        # 针对无日期请求
        await service.get_stock_trends(["002696"])

        assert len(call_history) == 3
        assert call_history[0][1]["trade_date"] == "2026-10-27"
        assert call_history[1][1]["trade_date"] == "2026-10-26"
        assert call_history[2][1]["trade_date"] is None

    # 测试真实的 _execute_pipeline 缓存键隔离
    DataService._CACHE.clear()
    with patch("backend.app.data.registry.registry.execute_with_fallback", new_callable=AsyncMock) as mock_reg:
        mock_reg.side_effect = lambda cap, meth, codes, trade_date=None, **kw: DataResult(
            data=[{"code": codes[0], "trends": [{"time": "09:30", "price": 10.0}], "is_real": True, "trade_date": trade_date}],
            quality=DataQuality.FULL,
            provider="mock",
            trade_date=trade_date,
        )
        with patch.object(service._budget, "acquire", new_callable=AsyncMock, return_value=True):
            with patch.object(service._rate_limiter, "acquire", new_callable=AsyncMock, return_value=True):
                # 第一次带 2026-10-27
                await service.get_stock_trends(["002696"], trade_date="2026-10-27")
                # 第二次带 2026-10-26
                await service.get_stock_trends(["002696"], trade_date="2026-10-26")

                # 必须产生两个不同的缓存条目，且 execute_with_fallback 被调用了两次（未被第一个日期的缓存吞噬）
                assert mock_reg.call_count == 2
                cache_keys = list(DataService._CACHE.keys())
                assert any("2026-10-27" in k for k in cache_keys)
                assert any("2026-10-26" in k for k in cache_keys)


def test_tdx_client_explicit_history_no_fallback():
    """验证 TdxDirectClient 显式指定历史日期时严格只取该日，缺数绝不回退至其他交易日或实时行情"""
    client = TdxDirectClient()
    client.connect_best_server = MagicMock(return_value=True)
    client.api = MagicMock()

    # 1. 模拟历史日期取不到数据 (返回空列表)
    client.api.get_history_minute_time_data.return_value = []
    client.api.get_minute_time_data.return_value = [{"price": 15.0, "vol": 100}]

    # Invalid explicit dates must be rejected before connecting or requesting
    # either live or historical minute data.
    res_invalid = client.get_minute_trend("002696", date="2026-13-40")
    assert res_invalid == []
    client.connect_best_server.assert_not_called()
    client.api.get_history_minute_time_data.assert_not_called()
    client.api.get_minute_time_data.assert_not_called()

    res = client.get_minute_trend("002696", date="2026-10-20")
    # 严格防穿透：绝不返回实时数据，也不向前循环回溯
    assert res == []
    assert client.api.get_minute_time_data.call_count == 0

    # 2. 模拟未来日期
    client.connect_best_server.reset_mock()
    res_future = client.get_minute_trend("002696", date="2099-01-01")
    assert res_future == []
    client.connect_best_server.assert_not_called()

    # 3. 模拟显式历史日期成功返回 240 点
    hist_sample = [{"price": 10.0 + i * 0.01, "vol": 100} for i in range(240)]
    client.api.get_history_minute_time_data.return_value = hist_sample
    res_success = client.get_minute_trend("002696", date="2026-10-20")
    assert len(res_success) == 240
    assert res_success[0]["price"] == 10.0


@pytest.mark.asyncio
async def test_tdx_provider_history_no_quote_contamination():
    """验证 TdxProvider 历史日绝不用当前实时的 quote (开盘价/昨收价) 污染历史分时点"""
    provider = TdxProvider()
    mock_client = MagicMock()
    mock_client.connect_best_server.return_value = True
    
    # 模拟当前实时行情：价格 99.0 元 (与历史严重不符)
    mock_client.get_quotes.return_value = [
        {"code": "002696", "name": "百洋股份", "open": 99.0, "last_close": 98.0, "price": 99.5}
    ]
    # 模拟历史真实分时 240 点：价格基准在 10.50 元
    historical_240 = [{"price": 10.50, "vol": 500, "trade_date": "2026-10-20"}] * 240
    mock_client.get_minute_trend.return_value = historical_240
    mock_client.get_kline.return_value = [
        {"datetime": "2026-10-19 00:00", "open": 9.80, "close": 10.00},
        {"datetime": "2026-10-20 00:00", "open": 10.50, "close": 11.00},
    ]

    with patch.object(provider, "_get_client", return_value=mock_client):
        # 显式拉取历史日期 2026-10-20
        result = await provider.get_stock_trends(["002696"], trade_date="2026-10-20")
        assert result.quality in (DataQuality.FULL, DataQuality.PARTIAL)
        assert len(result.data) == 1
        item = result.data[0]
        assert item["code"] == "002696"
        assert item["is_real"] is True
        # The prior trading session close, not today's quote or first minute,
        # is the historical return baseline.
        assert item["pre_close"] == 10.00
        assert len(item["trends"]) == 241
        # Use the selected historical session's actual daily open for 09:30.
        assert item["trends"][0]["price"] == 10.50
        assert item["trends"][0]["pct_change"] == 5.0
        assert item["trends"][1]["pct_change"] == 5.0


@pytest.mark.asyncio
async def test_tdx_provider_missing_reliable_previous_close_marks_stock_unavailable():
    provider = TdxProvider()
    mock_client = MagicMock()
    mock_client.connect_best_server.return_value = True
    mock_client.get_quotes.return_value = [
        {"code": "002696", "name": "百洋股份", "open": 10.5, "last_close": 0.0}
    ]
    mock_client.get_minute_trend.return_value = [
        {"price": 10.5, "vol": 100, "trade_date": "2026-10-20"}
    ]
    mock_client.get_kline.return_value = []

    with patch.object(provider, "_get_client", return_value=mock_client):
        result = await provider.get_stock_trends(["002696"], trade_date="2026-10-20")

    assert result.data == []
    assert result.quality == DataQuality.UNAVAILABLE
    assert result.missing_codes == ["002696"]


@pytest.mark.asyncio
async def test_tdx_provider_current_date_missing_quote_baseline_does_not_use_first_minute():
    provider = TdxProvider()
    mock_client = MagicMock()
    mock_client.connect_best_server.return_value = True
    mock_client.get_quotes.return_value = [
        {"code": "002696", "name": "百洋股份", "open": 10.5, "last_close": 0.0}
    ]
    mock_client.get_minute_trend.return_value = [
        {"price": 10.5, "vol": 100, "trade_date": datetime.now().date().isoformat()}
    ]
    mock_client.get_kline.return_value = []

    backup = MagicMock()
    backup.get_stock_trends = AsyncMock(return_value=DataResult(
        data=[],
        quality=DataQuality.UNAVAILABLE,
        provider="eastmoney",
        missing_codes=["002696"],
    ))
    with patch.object(provider, "_get_client", return_value=mock_client):
        with patch("backend.app.data.providers.eastmoney.EastmoneyProvider", return_value=backup):
            result = await provider.get_stock_trends(["002696"])

    assert result.data == []
    assert result.quality == DataQuality.UNAVAILABLE
    assert result.missing_codes == ["002696"]


@pytest.mark.asyncio
async def test_tdx_provider_preserves_real_prices_above_twenty_two_percent():
    provider = TdxProvider()
    mock_client = MagicMock()
    mock_client.connect_best_server.return_value = True
    mock_client.get_quotes.return_value = [
        {"code": "832000", "name": "测试北交所", "open": 99.0, "last_close": 98.0}
    ]
    mock_client.get_minute_trend.return_value = [
        {"price": 13.0, "vol": 100, "trade_date": "2026-10-20"}
    ]
    mock_client.get_kline.return_value = [
        {"datetime": "2026-10-19", "open": 10.0, "close": 10.0},
        {"datetime": "2026-10-20", "open": 13.0, "close": 13.0},
    ]

    with patch.object(provider, "_get_client", return_value=mock_client):
        result = await provider.get_stock_trends(["832000"], trade_date="2026-10-20")

    item = result.data[0]
    assert item["pre_close"] == 10.0
    assert item["trends"][0]["price"] == 13.0
    assert item["trends"][0]["pct_change"] == 30.0


@pytest.mark.asyncio
async def test_tdx_provider_returns_partial_for_unsupported_codes():
    """验证 TdxProvider 严禁直接内部硬编码调用 EastmoneyProvider，仅返回自身物理产物与 missing_codes"""
    provider = TdxProvider()
    mock_client = MagicMock()
    mock_client.connect_best_server.return_value = True
    mock_client.get_quotes.return_value = [
        {"code": "002696", "name": "百洋股份", "open": 10.0, "last_close": 10.0}
    ]
    mock_client.get_minute_trend.return_value = [
        {"price": 10.2, "vol": 100, "trade_date": datetime.now().date().isoformat()}
    ]

    with patch.object(provider, "_get_client", return_value=mock_client):
        result = await provider.get_stock_trends(["002696", "BK0480"])

    assert result.quality == DataQuality.PARTIAL
    assert result.provider == "tdx_direct"
    assert result.fallback_used is False
    assert len(result.data) == 1
    assert result.data[0]["code"] == "002696"
    assert result.data[0]["provider"] == "tdx_direct"
    assert result.missing_codes == ["BK0480"]


@pytest.mark.asyncio
async def test_data_service_completes_missing_codes_via_unified_governance():
    """验证 DataService 在主源 TDX 部分缺失时，由统一治理管线调度备用源东财受控补全"""
    service = DataService(session=None)

    tdx_res = DataResult(
        data=[{"code": "002696", "name": "百洋股份", "pre_close": 10.0, "trends": [{"time": "09:30", "price": 10.2}], "is_real": True, "provider": "tdx_direct", "quality": "FULL", "fallback_used": False}],
        quality=DataQuality.PARTIAL,
        provider="tdx_direct",
        missing_codes=["BK0480"],
    )
    east_res = DataResult(
        data=[{"code": "BK0480", "name": "概念板块", "pre_close": 100.0, "trends": [{"time": "09:30", "price": 101.0}], "is_real": True}],
        quality=DataQuality.FULL,
        provider="eastmoney",
        missing_codes=[],
    )

    with patch.object(service, "_execute_pipeline", new_callable=AsyncMock, return_value=tdx_res):
        with patch.object(service, "_execute_provider_direct", new_callable=AsyncMock, return_value=east_res) as mock_direct:
            res = await service.get_stock_trends(["002696", "BK0480"])

    mock_direct.assert_awaited_once()
    assert res.quality == DataQuality.DEGRADED
    assert res.fallback_used is True
    assert "tdx_direct" in res.provider and "eastmoney" in res.provider
    assert len(res.data) == 2
    codes = {item["code"] for item in res.data}
    assert codes == {"002696", "BK0480"}
    item_map = {item["code"]: item for item in res.data}
    assert item_map["002696"]["provider"] == "tdx_direct"
    assert item_map["BK0480"]["provider"] == "eastmoney"
    assert item_map["BK0480"]["fallback_used"] is True


@pytest.mark.asyncio
async def test_eastmoney_no_synthesis_on_missing_and_date_check():
    """验证 EastmoneyProvider 缺数不得合成虚假分时，且必须检查返回日期是否匹配所请求历史日"""
    provider = EastmoneyProvider()

    # 1. 模拟东财接口缺数/返回 None
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_http:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": None}
        mock_http.return_value = mock_resp

        result = await provider.get_stock_trends(["002696", "002343"])
        # 坚决不合成虚假数据
        assert result.data == []
        assert "002696" in result.missing_codes
        assert "002343" in result.missing_codes

    # 2. 模拟东财接口返回其他日期的数据 (如请求 2026-10-20，但东财返回 2026-10-27)
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_http:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "name": "百洋股份",
                "prePrice": 10.73,
                "trends": [
                    "2026-10-27 09:30,11.28,11.28,11.28,11.28,42683,48146424.00,11.280"
                ]
            }
        }
        mock_http.return_value = mock_resp

        # 请求历史日 2026-10-20
        result_mismatch = await provider.get_stock_trends(["002696"], trade_date="2026-10-20")
        # 日期不匹配被严格拒绝，不得冒充真实数据
        assert result_mismatch.data == []
        assert "002696" in result_mismatch.missing_codes

    # 3. 即便首条记录日期正确，后续混入其他交易日也必须整组拒绝
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_http:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "name": "百洋股份",
                "prePrice": 10.73,
                "trends": [
                    "2026-10-20 09:30,11.28,11.28,11.28,11.28,42683,48146424.00,11.280",
                    "2026-10-27 09:31,11.30,11.30,11.30,11.30,102,1152.60,11.290",
                ]
            }
        }
        mock_http.return_value = mock_resp

        result_mixed = await provider.get_stock_trends(["002696"], trade_date="2026-10-20")
        assert result_mixed.data == []
        assert "002696" in result_mixed.missing_codes
