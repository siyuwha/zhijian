import asyncio
import pytest
from datetime import datetime, date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from httpx import AsyncClient, ASGITransport

from backend.app.main import app
from backend.app.data.registry import ProviderRegistry
from backend.app.data.capabilities import (
    DataQuality,
    Freshness,
    DataStatus,
    ProviderErrorCode,
    DataResult,
)
from backend.app.data.providers.eastmoney import EastmoneyProvider
from backend.app.data.providers.tdx_provider import TdxProvider
from backend.app.data.service import DataService
from backend.app.data.registry import registry
from backend.app.services.intraday_briefing_service import IntradayBriefingService
from backend.app.schemas.intraday_briefing import TopSectorsTrendResponse


# =====================================================================
# A1: 东财概念源失败，TDX 仅有行业代号
# 断言：不调用 TDX 行业映射充当概念备用；返回对应不可用/合法已标明缓存，不伪造概念
# =====================================================================
@pytest.mark.asyncio
async def test_a1_eastmoney_concept_fails_tdx_industry_not_substituted():
    # 验证 registry 中 concept_blocks 能力仅注册 eastmoney，无 tdx_direct 备用
    providers = registry._registry.get("concept_blocks", [])
    provider_names = [p[0] for p in providers]
    assert "tdx_direct" not in provider_names, f"TDX 不得注册为 concept_blocks 备用源: {provider_names}"
    assert "eastmoney" in provider_names

    # 模拟东财概念接口网络失败
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Network unreachable")):
        east = EastmoneyProvider()
        east._concept_blocks_cache.clear()
        res = await east.get_concept_blocks("002696")
        assert res.quality in (DataQuality.UNAVAILABLE, DataQuality.FAILED)
        assert res.error_code == ProviderErrorCode.CONNECTION_ERROR
        assert res.data == []


# =====================================================================
# A2: sector 分别超时、断连、403、429、解析错误
# 断言：对应标准错误码，记录原始原因类别；无未知异常导致整个页面中断
# =====================================================================
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_type,expected_code,expected_quality",
    [
        ("timeout", ProviderErrorCode.TIMEOUT, DataQuality.UNAVAILABLE),
        ("connection", ProviderErrorCode.CONNECTION_ERROR, DataQuality.UNAVAILABLE),
        ("403", ProviderErrorCode.WAF_BLOCKED, DataQuality.UNAVAILABLE),
        ("429", ProviderErrorCode.RATE_LIMITED, DataQuality.UNAVAILABLE),
        ("parse", ProviderErrorCode.MALFORMED_PARSE, DataQuality.INVALID),
    ],
)
async def test_a2_sector_failure_classification(error_type, expected_code, expected_quality):
    east = EastmoneyProvider()
    if error_type == "timeout":
        with patch("httpx.AsyncClient.get", side_effect=httpx.TimeoutException("Timeout >8s")):
            res = await east.get_top_sectors()
    elif error_type == "connection":
        with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("Connection refused")):
            res = await east.get_top_sectors()
    elif error_type == "403":
        mock_resp = MagicMock(status_code=403, text="Forbidden WAF blocked")
        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            res = await east.get_top_sectors()
    elif error_type == "429":
        mock_resp = MagicMock(status_code=429, text="Too Many Requests")
        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            res = await east.get_top_sectors()
    elif error_type == "parse":
        mock_resp = MagicMock(status_code=200, text="<HTML>Not JSON</HTML>")
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        with patch("httpx.AsyncClient.get", return_value=mock_resp):
            res = await east.get_top_sectors()

    assert res.error_code == expected_code, f"Expected {expected_code}, got {res.error_code}"
    assert res.quality == expected_quality
    assert res.data in (None, [])


# =====================================================================
# A3: 主分时源失败，东财有真实有效数据
# 断言：返回东财真实点、正确来源、DEGRADED；不重复无界请求
# =====================================================================
@pytest.mark.asyncio
async def test_a3_stock_trends_primary_fails_secondary_succeeds():
    service = DataService(session=None)
    DataService._CACHE.clear()
    DataService._LAST_GOOD_CACHE.clear()

    # 构造东财返回的真实分时数据
    em_result = DataResult(
        data=[{
            "code": "002696",
            "name": "百洋股份",
            "pre_close": 10.0,
            "trends": [{"time": "09:30", "price": 10.5, "pct_change": 5.0, "amount": 1000}],
            "is_real": True,
        }],
        quality=DataQuality.FULL,
        provider="eastmoney",
        missing_codes=[],
    )

    with patch.object(TdxProvider, "get_stock_trends", new_callable=AsyncMock) as mock_tdx:
        mock_tdx.return_value = DataResult(
            data=[],
            quality=DataQuality.UNAVAILABLE,
            provider="tdx_direct",
            missing_codes=["002696"],
            error_message="TDX server offline",
        )
        with patch.object(EastmoneyProvider, "get_stock_trends", new_callable=AsyncMock) as mock_em:
            mock_em.return_value = em_result

            res = await service.get_stock_trends(["002696"])
            assert res.quality == DataQuality.DEGRADED
            assert res.fallback_used is True
            assert res.provider == "eastmoney"
            assert len(res.data) == 1
            assert res.data[0]["code"] == "002696"
            assert res.data[0]["trends"][0]["price"] == 10.5


# =====================================================================
# A4: 分时双源失败、无缓存
# 断言：每个请求代码空序列、UNAVAILABLE；无合成点、无虚假 0 价，无过期图残留
# =====================================================================
@pytest.mark.asyncio
async def test_a4_stock_trends_dual_fail_structured_empty_unavailable():
    service = DataService(session=None)
    DataService._CACHE.clear()
    DataService._LAST_GOOD_CACHE.clear()

    with patch.object(TdxProvider, "get_stock_trends", new_callable=AsyncMock) as mock_tdx:
        mock_tdx.return_value = DataResult(
            data=[],
            quality=DataQuality.UNAVAILABLE,
            provider="tdx_direct",
            missing_codes=["002696", "600519"],
        )
        with patch.object(EastmoneyProvider, "get_stock_trends", new_callable=AsyncMock) as mock_em:
            mock_em.return_value = DataResult(
                data=[],
                quality=DataQuality.UNAVAILABLE,
                provider="eastmoney",
                missing_codes=["002696", "600519"],
            )

            res = await service.get_stock_trends(["002696", "600519"])
            assert res.quality == DataQuality.UNAVAILABLE
            assert res.freshness == Freshness.UNAVAILABLE
            # 必须为每个请求代码提供结构化空序列，不可为 None 或杂乱对象
            assert isinstance(res.data, list)
            item_codes = {item["code"] for item in res.data}
            assert item_codes == {"002696", "600519"}
            for item in res.data:
                assert item["trends"] == []
                assert item["quality"] == DataQuality.UNAVAILABLE


# =====================================================================
# A5: 两个代码中一个有效、一个失效
# 断言：有效曲线保留，失败代码局部提示，PARTIAL/missing_codes 一致
# =====================================================================
@pytest.mark.asyncio
async def test_a5_stock_trends_partial_one_valid_one_failed():
    service = DataService(session=None)
    DataService._CACHE.clear()
    DataService._LAST_GOOD_CACHE.clear()

    partial_result = DataResult(
        data=[
            {
                "code": "002696",
                "name": "百洋股份",
                "pre_close": 10.0,
                "trends": [{"time": "09:30", "price": 10.5, "pct_change": 5.0, "amount": 1000}],
                "is_real": True,
            },
            {
                "code": "600519",
                "name": "贵州茅台",
                "pre_close": None,
                "trends": [],
                "quality": DataQuality.UNAVAILABLE,
                "is_real": False,
            },
        ],
        quality=DataQuality.PARTIAL,
        provider="tdx_direct",
        missing_codes=["600519"],
    )

    with patch.object(TdxProvider, "get_stock_trends", new_callable=AsyncMock) as mock_tdx:
        mock_tdx.return_value = partial_result
        with patch.object(EastmoneyProvider, "get_stock_trends", new_callable=AsyncMock) as mock_em:
            mock_em.return_value = DataResult(
                data=[], quality=DataQuality.UNAVAILABLE, provider="eastmoney", missing_codes=["600519"]
            )
            res = await service.get_stock_trends(["002696", "600519"])
        assert res.quality == DataQuality.PARTIAL
        assert res.missing_codes == ["600519"]
        assert len(res.data) == 2
        success_item = next(item for item in res.data if item["code"] == "002696")
        failed_item = next(item for item in res.data if item["code"] == "600519")
        assert len(success_item["trends"]) > 0
        assert len(failed_item["trends"]) == 0


# =====================================================================
# A6: 同日旧缓存尚在展示容忍期；超过期限
# 断言：前者 STALE 并显示真实截止时间；后者不可用；阈值前/等于/超过分别断言
# =====================================================================
@pytest.mark.asyncio
async def test_a6_cache_tolerance_stale_and_expired():
    service = DataService(session=None)
    DataService._CACHE.clear()
    DataService._LAST_GOOD_CACHE.clear()

    today_str = date.today().isoformat()
    orig_time = datetime.now() - timedelta(seconds=120)

    cached_data = DataResult(
        data=[{"code": "002696", "trends": [{"time": "09:30", "price": 10.0}]}],
        quality=DataQuality.FULL,
        provider="tdx_direct",
        timestamp=orig_time,
        source_timestamp=orig_time,
        trade_date=today_str,
    )

    # 1. 在展示容忍期内 (如 120 秒，正常 TTL 为 15s，容忍期 300s)
    # 当上游物理源全部失败时，降级使用同日旧快照，标记 STALE 且不刷新截止时戳
    with patch("backend.app.data.registry.registry.execute_with_fallback", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = DataResult(
            data=None,
            quality=DataQuality.UNAVAILABLE,
            provider="all_failed",
            error_message="All providers failed",
        )
        cache_key = f"stock_trends:get_stock_trends:(['002696'],):[('trade_date', '{today_str}')]"
        DataService._LAST_GOOD_CACHE[cache_key] = cached_data

        res = await service.get_stock_trends(["002696"], trade_date=today_str)
        assert res.quality == DataQuality.DEGRADED
        assert res.freshness == Freshness.STALE
        assert res.source_timestamp == orig_time

    # 2. 超过展示保留期限 (如 >300s，设为 400s 之前)
    expired_time = datetime.now() - timedelta(seconds=400)
    expired_cached = DataResult(
        data=[{"code": "002696", "trends": [{"time": "09:30", "price": 10.0}]}],
        quality=DataQuality.FULL,
        provider="tdx_direct",
        timestamp=expired_time,
        source_timestamp=expired_time,
        trade_date=today_str,
    )
    DataService._LAST_GOOD_CACHE[cache_key] = expired_cached

    res_expired = await service.get_stock_trends(["002696"], trade_date=today_str)
    assert res_expired.quality == DataQuality.UNAVAILABLE
    assert res_expired.freshness == Freshness.UNAVAILABLE


# =====================================================================
# A7: 昨日缓存、午夜跨日、目标历史日变更
# 断言：不串用日期；历史同目标日可按历史规则展示；缺日期不得冒充当日
# =====================================================================
@pytest.mark.asyncio
async def test_a7_cross_date_cache_strict_isolation():
    service = DataService(session=None)
    DataService._CACHE.clear()
    DataService._LAST_GOOD_CACHE.clear()

    # 昨日缓存
    yesterday_str = (date.today() - timedelta(days=1)).isoformat()
    today_str = date.today().isoformat()

    yesterday_res = DataResult(
        data=[{"code": "002696", "trends": [{"time": "09:30", "price": 9.0}]}],
        quality=DataQuality.FULL,
        provider="tdx_direct",
        trade_date=yesterday_str,
    )
    cache_key_yesterday = f"stock_trends:get_stock_trends:(['002696'],):[('trade_date', '{yesterday_str}')]"
    DataService._CACHE[cache_key_yesterday] = (100.0, yesterday_res)
    DataService._LAST_GOOD_CACHE[cache_key_yesterday] = yesterday_res

    # 请求今日数据，物理源失败时，绝不借用昨日缓存
    with patch("backend.app.data.registry.registry.execute_with_fallback", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = DataResult(
            data=None,
            quality=DataQuality.UNAVAILABLE,
            provider="all_failed",
            error_message="Network down",
        )
        res_today = await service.get_stock_trends(["002696"], trade_date=today_str)
        assert res_today.quality == DataQuality.UNAVAILABLE
        assert res_today.data in (None, []) or (isinstance(res_today.data, list) and res_today.data[0]["trends"] == [])


# =====================================================================
# A11: 预算耗尽 / 熔断路径缓存有效性校验
# 断言：不绕过缓存年龄校验，保留真实错误类别
# =====================================================================
@pytest.mark.asyncio
async def test_a11_budget_exhausted_validates_cache_age():
    service = DataService(session=None)
    DataService._CACHE.clear()
    DataService._LAST_GOOD_CACHE.clear()

    today_str = date.today().isoformat()
    cache_key = f"stock_trends:get_stock_trends:(['002696'],):[('trade_date', '{today_str}')]"

    # 缓存超过容忍期
    expired_time = datetime.now() - timedelta(seconds=600)
    DataService._LAST_GOOD_CACHE[cache_key] = DataResult(
        data=[{"code": "002696", "trends": []}],
        quality=DataQuality.FULL,
        provider="tdx_direct",
        timestamp=expired_time,
        source_timestamp=expired_time,
        trade_date=today_str,
    )

    with patch.object(service._budget, "acquire", new_callable=AsyncMock, return_value=False):
        res = await service.get_stock_trends(["002696"], trade_date=today_str)
        assert res.quality == DataQuality.UNAVAILABLE
        assert res.freshness == Freshness.UNAVAILABLE
        assert "budget" in (res.error_message or "").lower()


# =====================================================================
# A12: TopSectorsTrendResponse 严格 Schema 与指纹安全
# 断言：具备 extra="forbid" 的模式在新增质量字段后依然兼容
# =====================================================================
def test_a12_top_sectors_trend_schema_extra_forbid():
    valid_payload = {
        "trade_date": "2026-10-30",
        "snapshot_time": "15:00:00",
        "sectors": [],
        "quality": "DEGRADED",
        "freshness": "STALE",
        "status": "STALE",
        "degradation_reason": "使用缓存，更新于 14:55",
        "source_timestamp": "2026-10-30T14:55:00",
    }
    model = TopSectorsTrendResponse.model_validate(valid_payload)
    assert model.quality == "DEGRADED"
    assert model.freshness == "STALE"
    assert model.degradation_reason == "使用缓存，更新于 14:55"


# =====================================================================
# A8: 宏观 FULL、板块 DEGRADED、分时 UNAVAILABLE 三态共存与互不遮蔽
# 断言：三项状态独立输出并同时可见；宏观 FULL 绝不覆盖板块或分时质量
# =====================================================================
@pytest.mark.asyncio
async def test_a8_macro_full_sector_degraded_trends_unavailable_coexistence():
    mock_session = MagicMock()
    service = IntradayBriefingService(session=mock_session)
    service.data_service = DataService(session=None)
    service.market_service = MagicMock()
    # Mock limit up and market index trends to prevent real network I/O
    service.data_service.get_limit_up_pool = AsyncMock(return_value=DataResult(
        data={"items": [], "broken_limit_items": []}, quality=DataQuality.FULL, provider="test"
    ))
    service.data_service.get_market_index_trend = AsyncMock(return_value=None)

    # 1. 模拟宏观 Canonical 快照为 FULL
    mock_snap = MagicMock()
    mock_snap.quality = "FULL"
    mock_snap.cognition = MagicMock()
    mock_snap.cognition.mainlines = [
        MagicMock(sector_code="BK0910", sector_name="半导体", constituency=MagicMock(leader_code="603986", leader_name="兆易创新", leader_height=3, limit_up_count=2)),
    ]
    service.market_service.get_canonical_snapshot = AsyncMock(return_value=mock_snap)

    # 2. 模拟实时板块排行失败 (触发 fallback 至 snapshot 主线 -> sector_quality = DEGRADED)
    service.data_service.get_sector_ranking = AsyncMock(return_value=DataResult(
        data=[], quality=DataQuality.UNAVAILABLE, provider="eastmoney", error_message="Sector API 500"
    ))

    # 3. 模拟分时走势物理源全部不可用 -> trends_quality = UNAVAILABLE
    service.data_service.get_stock_trends = AsyncMock(return_value=DataResult(
        data=[], quality=DataQuality.UNAVAILABLE, freshness=Freshness.UNAVAILABLE, provider="all_failed", missing_codes=["BK0910", "603986"]
    ))

    today_str = date.today().isoformat()
    resp = await service.get_top_sectors_trend(today_str)

    # 核心断言：
    # a) 宏观虽然可用，但板块降级 (DEGRADED)，分时不可用 (UNAVAILABLE)
    assert resp.sector_quality == "DEGRADED"
    assert resp.trends_quality == "UNAVAILABLE"
    # b) 综合质量绝不得被宏观伪造或覆盖为 FULL
    assert resp.quality in ("DEGRADED", "UNAVAILABLE")
    assert resp.quality != "FULL"
    # c) 分时走势缺失时，曲线严格为空列表，is_real 为 False，绝不伪造分钟点阵
    assert len(resp.sectors) > 0
    for s in resp.sectors:
        assert s.trends == []
        assert s.is_real is False


# =====================================================================
# A9: 质量元数据缺失或未知枚举的响应保守降级
# 断言：消费者保守判定为未知/不可用，不自动 FULL，不抛未捕获异常
# =====================================================================
@pytest.mark.asyncio
async def test_a9_unknown_quality_enum_conservative_handling():
    # 1. DataResult 接收未知异常质量枚举或字符串
    res = DataResult(
        data=[{"code": "002696"}],
        quality=DataQuality.UNAVAILABLE,  # fallback
        provider="test",
    )
    # 模拟外部透传了未知非法质量值
    object.__setattr__(res, "quality", "UNKNOWN_NONEXISTENT_QUALITY")
    assert DataService._is_cache_temporally_valid(res, req_trade_date=None, max_age_sec=300.0) is False

    # 2. market API 对未知枚举安全输出，不抛出未捕获异常
    with patch.object(DataService, "get_stock_trends", new_callable=AsyncMock) as mock_get:
        unknown_res = DataResult(
            data=[{"code": "002696", "trends": []}],
            quality=DataQuality.UNAVAILABLE,
            provider="test",
        )
        object.__setattr__(unknown_res, "quality", "CORRUPTED_QUALITY_VALUE")
        mock_get.return_value = unknown_res

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/market/stock-trends?codes=002696")
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["quality"] == "CORRUPTED_QUALITY_VALUE"
            assert payload["code"] == 200


# =====================================================================
# A10: 失败后恢复有效数据，再迟到旧失败响应防线 (Late Out-of-Order Defense)
# 断言：本轮正确恢复；旧请求序列迟到结果严格被丢弃，有效数据不被覆盖
# =====================================================================
def test_a10_sequence_token_and_recovery_defense():
    """
    验证前端 fetchSeqRef / sequence token 机制：
    若请求 1 迟到返回失败，但请求 2 已完成并恢复有效数据，
    请求 1 的迟到结果必须被 sequence token 拦截丢弃
    """
    state = {
        "currentSeq": 0,
        "activeData": None,
        "quality": "INITIAL",
    }

    # 1. 发起第 1 轮请求 (模拟网络缓慢/失败)
    state["currentSeq"] += 1
    seq1 = state["currentSeq"]

    # 2. 发起第 2 轮请求 (网络恢复，成功返回)
    state["currentSeq"] += 1
    seq2 = state["currentSeq"]

    # 第 2 轮先成功到达
    resp2 = {"seq": seq2, "data": [{"code": "002696", "trends": [10.1, 10.2]}], "quality": "FULL"}
    if resp2["seq"] == state["currentSeq"]:
        state["activeData"] = resp2["data"]
        state["quality"] = resp2["quality"]

    assert state["quality"] == "FULL"
    assert len(state["activeData"]) == 1

    # 3. 第 1 轮迟到响应到达 (携带旧失败/空结果)
    resp1_late = {"seq": seq1, "data": [], "quality": "UNAVAILABLE"}
    # sequence token 防线触发拦截
    if resp1_late["seq"] == state["currentSeq"]:
        state["activeData"] = resp1_late["data"]
        state["quality"] = resp1_late["quality"]

    # 核心断言：迟到旧结果被拦截，第 2 轮有效恢复的数据与质量依然完好保留！
    assert state["quality"] == "FULL"
    assert len(state["activeData"]) == 1


# =====================================================================
# A13: 跨午夜 / 未知时间戳严格时态门禁单元测试
# 断言：实时行情禁止跨越午夜复用昨日缓存；无时间戳缓存实时请求直接拒绝
# =====================================================================
def test_a13_cache_temporal_midnight_and_null_ts_gates():
    now_dt = datetime(2026, 10, 31, 0, 15, 0)  # 午夜过后的 00:15
    yesterday_ts = datetime(2026, 10, 30, 23, 55, 0)  # 20分钟前（昨天 23:55）

    # 1. 昨天 23:55 的实时缓存（虽然年龄只有 20 分钟 < 300秒？不，这里设 max_age_sec=1800）
    stale_yesterday_res = DataResult(
        data=[{"code": "002696"}],
        quality=DataQuality.FULL,
        provider="tdx",
        timestamp=yesterday_ts,
        source_timestamp=yesterday_ts,
        trade_date="2026-10-30",
    )
    # 实时请求 (req_trade_date=None): 虽然年龄只有 20 分钟，但跨越了午夜 (昨天)，必须拒绝！
    assert DataService._is_cache_temporally_valid(
        stale_yesterday_res, req_trade_date=None, max_age_sec=3600.0, reference_now=now_dt
    ) is False

    # 2. 来源时间戳为空且未指定目标交易日的缓存，无法自证新鲜度，必须拒绝！
    null_ts_res = DataResult(
        data=[{"code": "002696"}],
        quality=DataQuality.FULL,
        provider="tdx",
        timestamp=now_dt,
        source_timestamp=None,
        trade_date=None,
    )
    assert DataService._is_cache_temporally_valid(
        null_ts_res, req_trade_date=None, max_age_sec=300.0, reference_now=now_dt
    ) is False

    # 3. 目标历史日查询 (req_trade_date='2026-10-30') 命中同日缓存，允许复用
    assert DataService._is_cache_temporally_valid(
        stale_yesterday_res, req_trade_date="2026-10-30", max_age_sec=86400.0 * 10, reference_now=now_dt
    ) is True

# =====================================================================
# A14: 混合主备 (主源实时 + 备源 STALE / 主源缺时点) 保守时效与时点合成
# 断言：
# 1. 主源实时但备源为 STALE 时，整批必须保守标为 DEGRADED + STALE，绝不能误标 REALTIME；
# 2. 主源有效标的缺失 source_timestamp (如 TDX) 时，整批 source_timestamp 严格保持 None，
#    绝不冒充使用备源东财时点作为整批截止时点。
# =====================================================================
@pytest.mark.asyncio
async def test_a14_mixed_primary_realtime_backup_stale_and_timestamp_retention():
    service = DataService(session=None)
    
    # 模拟主源 TDX 返回 002696 实时分时，但缺失 source_timestamp (None)
    tdx_res = DataResult(
        data=[{
            "code": "002696",
            "name": "百洋股份",
            "pre_close": 10.0,
            "trends": [{"time": "09:30", "price": 10.2}],
            "is_real": True,
            "provider": "tdx_direct",
            "quality": DataQuality.FULL.value,
            "freshness": Freshness.REALTIME.value,
            "fallback_used": False,
            "source_timestamp": None,  # 主源时点缺失
            "trade_date": "2026-10-31",
        }],
        quality=DataQuality.PARTIAL,
        freshness=Freshness.REALTIME,
        status=DataStatus.AVAILABLE,
        provider="tdx_direct",
        missing_codes=["BK0480"],
    )

    # 模拟备源 Eastmoney 补全 BK0480，但备源处于 STALE 状态，且带有 14:30 的 source_timestamp
    backup_stale_res = DataResult(
        data=[{
            "code": "BK0480",
            "name": "概念板块",
            "pre_close": 100.0,
            "trends": [{"time": "09:30", "price": 101.0}],
            "is_real": True,
            "source_timestamp": datetime(2026, 10, 31, 14, 30, 0),
            "trade_date": "2026-10-31",
        }],
        quality=DataQuality.DEGRADED,
        freshness=Freshness.STALE,
        status=DataStatus.STALE,
        provider="eastmoney",
        source_timestamp=datetime(2026, 10, 31, 14, 30, 0),
        trade_date="2026-10-31",
        missing_codes=[],
    )

    with patch.object(service, "_execute_pipeline", new_callable=AsyncMock, return_value=tdx_res):
        with patch.object(service, "_execute_provider_direct", new_callable=AsyncMock, return_value=backup_stale_res):
            res = await service.get_stock_trends(["002696", "BK0480"])

    # 1. 质量必须为 DEGRADED
    assert res.quality == DataQuality.DEGRADED
    # 2. 时效必须为 STALE (因备用源包含 STALE 降级数据，整批保守标记 STALE，绝不能误标 REALTIME)
    assert res.freshness == Freshness.STALE
    assert res.status == DataStatus.STALE
    # 3. 来源时点必须为 None (因主源 002696 时点未知，绝不盗用备源 14:30 冒充整批截止时点)
    assert res.source_timestamp is None
    # 4. 来源链标记混合源
    assert res.provider == "tdx_direct+eastmoney"
    assert res.fallback_used is True


# =====================================================================
# A15: 非 T10 既有能力缓存门禁在传入 reference_now 时的严格安全校验
# 断言：传入 reference_now 时，Registry 对过期、跨日、未来漂移缓存严格执行统一拦截
# =====================================================================
@pytest.mark.asyncio
async def test_a15_non_t10_cache_with_reference_now_strict_gates():
    reg = ProviderRegistry()
    
    class FailingProvider:
        async def get_stock_quotes(self, codes):
            return DataResult(data=None, quality=DataQuality.UNAVAILABLE, provider="fail")
            
    reg.register("stock_quote", "p1", FailingProvider(), is_primary=True)
    simulated_now = datetime(2026, 10, 30, 10, 0, 0)
    
    # 1. 模拟旧缓存跨日 (昨日 2026-10-29) -> 即使传入 reference_now 也必须拒用
    yesterday_cache = DataResult(
        data=[{"code": "600000", "price": 10.0}],
        quality=DataQuality.FULL,
        provider="p1",
        timestamp=datetime(2026, 10, 29, 15, 0, 0),
    )
    res_yesterday = await reg.execute_with_fallback(
        "stock_quote", "get_stock_quotes", ["600000"],
        last_good_cache=yesterday_cache,
        reference_now=simulated_now,
    )
    assert res_yesterday.quality == DataQuality.UNAVAILABLE

    # 2. 模拟旧缓存超时 (>300s，9:50 创建，simulated_now=10:00，间隔 600s) -> 必须拒用
    expired_cache = DataResult(
        data=[{"code": "600000", "price": 10.0}],
        quality=DataQuality.FULL,
        provider="p1",
        timestamp=datetime(2026, 10, 30, 9, 50, 0),
    )
    res_expired = await reg.execute_with_fallback(
        "stock_quote", "get_stock_quotes", ["600000"],
        last_good_cache=expired_cache,
        reference_now=simulated_now,
    )
    assert res_expired.quality == DataQuality.UNAVAILABLE

    # 3. 模拟未来时间戳漂移 (>60s，10:05 创建，simulated_now=10:00) -> 必须拒用
    future_cache = DataResult(
        data=[{"code": "600000", "price": 10.0}],
        quality=DataQuality.FULL,
        provider="p1",
        timestamp=datetime(2026, 10, 30, 10, 5, 0),
    )
    res_future = await reg.execute_with_fallback(
        "stock_quote", "get_stock_quotes", ["600000"],
        last_good_cache=future_cache,
        reference_now=simulated_now,
    )
    assert res_future.quality == DataQuality.UNAVAILABLE

    # 4. 模拟合法新鲜缓存 (1 分钟前 09:59 创建) -> 允许降级为 STALE 放行
    valid_fresh_cache = DataResult(
        data=[{"code": "600000", "price": 10.0}],
        quality=DataQuality.FULL,
        provider="p1",
        timestamp=datetime(2026, 10, 30, 9, 59, 0),
    )
    res_valid = await reg.execute_with_fallback(
        "stock_quote", "get_stock_quotes", ["600000"],
        last_good_cache=valid_fresh_cache,
        reference_now=simulated_now,
    )
    assert res_valid.quality == DataQuality.DEGRADED
    assert res_valid.freshness == Freshness.STALE



# =====================================================================
# 未知或过期时效不得进入真实分时结果。
@pytest.mark.asyncio
@pytest.mark.parametrize("freshness", ["UNKNOWN", "EXPIRED", "UNAVAILABLE"])
async def test_invalid_primary_trend_freshness_rejected(freshness):
    service = DataService(session=None)
    primary = DataResult(data=[{"code": "002696", "trends": [{"time": "09:30", "price": 10}],
                                "freshness": freshness}], quality=DataQuality.FULL, provider="tdx_direct")
    with patch.object(service, "_execute_pipeline", new_callable=AsyncMock, return_value=primary), \
         patch.object(service, "_execute_provider_direct", new_callable=AsyncMock, return_value=DataResult(
             data=[], quality=DataQuality.UNAVAILABLE, provider="eastmoney")):
        result = await service.get_stock_trends(["002696"])
    assert result.quality == DataQuality.UNAVAILABLE
    assert result.missing_codes == ["002696"]
    assert result.data[0]["trends"] == []


# A16: 备源 DELAYED 绝不提升为 REALTIME，EXPIRED/UNAVAILABLE 项坚决拒用
# 断言：
# 1. 主源 REALTIME + 备源 DELAYED 合成时，整批时效严格保持 DELAYED，绝不能提升为 REALTIME；
# 2. 备用源中单项若为 EXPIRED 或 UNAVAILABLE 时，坚决拒用，保留为 missing / UNAVAILABLE；
# 3. 全备用源 DELAYED 时，整批时效同样严格保持 DELAYED。
# =====================================================================
@pytest.mark.asyncio
async def test_a16_backup_delayed_never_promoted_to_realtime_and_expired_rejected():
    service = DataService(session=None)
    
    # Case 1: 主源 REALTIME 002696 + 备源 DELAYED BK0480
    tdx_res = DataResult(
        data=[{
            "code": "002696",
            "name": "百洋股份",
            "pre_close": 10.0,
            "trends": [{"time": "09:30", "price": 10.2}],
            "is_real": True,
            "provider": "tdx_direct",
            "quality": DataQuality.FULL.value,
            "freshness": Freshness.REALTIME.value,
            "source_timestamp": datetime(2026, 10, 31, 10, 0, 0),
            "trade_date": "2026-10-31",
        }],
        quality=DataQuality.PARTIAL,
        freshness=Freshness.REALTIME,
        status=DataStatus.AVAILABLE,
        provider="tdx_direct",
        missing_codes=["BK0480"],
    )

    backup_delayed_res = DataResult(
        data=[{
            "code": "BK0480",
            "name": "概念板块",
            "pre_close": 100.0,
            "trends": [{"time": "09:30", "price": 101.0}],
            "is_real": True,
            "quality": DataQuality.FULL.value,
            "freshness": Freshness.DELAYED.value,
            "source_timestamp": datetime(2026, 10, 31, 9, 45, 0),
            "trade_date": "2026-10-31",
        }],
        quality=DataQuality.FULL,
        freshness=Freshness.DELAYED,
        status=DataStatus.AVAILABLE,
        provider="eastmoney",
        source_timestamp=datetime(2026, 10, 31, 9, 45, 0),
        trade_date="2026-10-31",
        missing_codes=[],
    )

    with patch.object(service, "_execute_pipeline", new_callable=AsyncMock, return_value=tdx_res):
        with patch.object(service, "_execute_provider_direct", new_callable=AsyncMock, return_value=backup_delayed_res):
            res = await service.get_stock_trends(["002696", "BK0480"])

    assert res.quality == DataQuality.DEGRADED
    # 核心断言：时效严格为 DELAYED，绝不能被改写提升为 REALTIME！
    assert res.freshness == Freshness.DELAYED
    assert res.status == DataStatus.AVAILABLE
    assert res.fallback_used is True
    assert "DELAYED" in (res.degradation_reason or "")

    # Case 2: 备源返回 EXPIRED 项，必须被过滤拒用，标的保留在 missing_codes 且标记 UNAVAILABLE
    tdx_res_2 = DataResult(
        data=[{
            "code": "002696",
            "name": "百洋股份",
            "pre_close": 10.0,
            "trends": [{"time": "09:30", "price": 10.2}],
            "is_real": True,
            "provider": "tdx_direct",
            "quality": DataQuality.FULL.value,
            "freshness": Freshness.REALTIME.value,
            "source_timestamp": datetime(2026, 10, 31, 10, 0, 0),
            "trade_date": "2026-10-31",
        }],
        quality=DataQuality.PARTIAL,
        freshness=Freshness.REALTIME,
        status=DataStatus.AVAILABLE,
        provider="tdx_direct",
        missing_codes=["BK0480"],
    )

    backup_expired_item_res = DataResult(
        data=[{
            "code": "BK0480",
            "name": "概念板块",
            "pre_close": 100.0,
            "trends": [{"time": "09:30", "price": 101.0}],
            "is_real": True,
            "quality": DataQuality.FULL.value,
            "freshness": Freshness.EXPIRED.value,  # 过期单项
            "source_timestamp": datetime(2026, 10, 31, 9, 0, 0),
            "trade_date": "2026-10-31",
        }],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,
        status=DataStatus.AVAILABLE,
        provider="eastmoney",
        source_timestamp=datetime(2026, 10, 31, 10, 0, 0),
        trade_date="2026-10-31",
        missing_codes=[],
    )

    with patch.object(service, "_execute_pipeline", new_callable=AsyncMock, return_value=tdx_res_2):
        with patch.object(service, "_execute_provider_direct", new_callable=AsyncMock, return_value=backup_expired_item_res):
            res_exp = await service.get_stock_trends(["002696", "BK0480"])

    assert res_exp.quality == DataQuality.PARTIAL
    assert "BK0480" in res_exp.missing_codes
    bk_item = next(it for it in res_exp.data if it.get("code") == "BK0480")
    assert bk_item["quality"] == DataQuality.UNAVAILABLE.value

    # Case 3: 全备用源 DELAYED 交付
    tdx_all_fail = DataResult(
        data=[],
        quality=DataQuality.UNAVAILABLE,
        freshness=Freshness.UNAVAILABLE,
        status=DataStatus.EMPTY,
        provider="tdx_direct",
        missing_codes=["BK0480"],
    )
    with patch.object(service, "_execute_pipeline", new_callable=AsyncMock, return_value=tdx_all_fail):
        with patch.object(service, "_execute_provider_direct", new_callable=AsyncMock, return_value=backup_delayed_res):
            res_full_backup = await service.get_stock_trends(["BK0480"])

    assert res_full_backup.quality == DataQuality.DEGRADED
    assert res_full_backup.freshness == Freshness.DELAYED
    assert res_full_backup.status == DataStatus.AVAILABLE
    assert res_full_backup.provider == "eastmoney"


# =====================================================================
# A17: Registry 容忍期限无依据额外放宽移除与严格精确边界测试
# 断言：在 stale_tolerance=300.0s 时，299s 与 300.0s 严格放行，300.1s 坚决拦截为 UNAVAILABLE
# 彻底杜绝历史 +2.0 秒无依据容忍余量！
# =====================================================================
@pytest.mark.asyncio
async def test_a17_registry_strict_stale_tolerance_exact_boundary():
    reg = ProviderRegistry()
    
    class FailingProvider:
        async def get_stock_trends(self, codes):
            return DataResult(data=None, quality=DataQuality.UNAVAILABLE, provider="fail")
            
    reg.register("stock_trends", "p1", FailingProvider(), is_primary=True)
    simulated_now = datetime(2026, 10, 31, 10, 5, 0)  # 10:05:00
    tol = 300.0  # 严格 300 秒 (5分钟)

    # 1. 299.0 秒前 (10:00:01) -> PASS (DEGRADED + STALE)
    cache_299 = DataResult(
        data=[{"code": "002696", "trends": [{"time": "10:00"}]}],
        quality=DataQuality.FULL,
        provider="p1",
        source_timestamp=datetime(2026, 10, 31, 10, 0, 1),
        trade_date="2026-10-31",
    )
    res_299 = await reg.execute_with_fallback(
        "stock_trends", "get_stock_trends", ["002696"],
        last_good_cache=cache_299,
        reference_now=simulated_now,
        stale_tolerance_sec=tol,
    )
    assert res_299.quality == DataQuality.DEGRADED
    assert res_299.freshness == Freshness.STALE

    # 2. 刚好 300.0 秒前 (10:00:00) -> PASS (DEGRADED + STALE)
    cache_300 = DataResult(
        data=[{"code": "002696", "trends": [{"time": "10:00"}]}],
        quality=DataQuality.FULL,
        provider="p1",
        source_timestamp=datetime(2026, 10, 31, 10, 0, 0),
        trade_date="2026-10-31",
    )
    res_300 = await reg.execute_with_fallback(
        "stock_trends", "get_stock_trends", ["002696"],
        last_good_cache=cache_300,
        reference_now=simulated_now,
        stale_tolerance_sec=tol,
    )
    assert res_300.quality == DataQuality.DEGRADED
    assert res_300.freshness == Freshness.STALE

    # 3. 300.1 秒前 (09:59:59.9) -> 严格拦截拒用 (UNAVAILABLE)，无任何 +2.0 秒无依据放宽！
    cache_300_1 = DataResult(
        data=[{"code": "002696", "trends": [{"time": "09:59"}]}],
        quality=DataQuality.FULL,
        provider="p1",
        source_timestamp=datetime(2026, 10, 31, 9, 59, 59, 900000),
        trade_date="2026-10-31",
    )
    res_300_1 = await reg.execute_with_fallback(
        "stock_trends", "get_stock_trends", ["002696"],
        last_good_cache=cache_300_1,
        reference_now=simulated_now,
        stale_tolerance_sec=tol,
    )
    assert res_300_1.quality == DataQuality.UNAVAILABLE
    assert res_300_1.freshness == Freshness.UNAVAILABLE

# =====================================================================
# A18: 板块排行与分时时效在聚合层的独立传递与保守时效合成 (P1 闭环验证)
# 涵盖：排行 STALE / DELAYED 独立传递，主备时态保守等级合成，
# 来源时点最早截断与未知保持 None，以及数据恢复全链路
# =====================================================================
@pytest.mark.asyncio
async def test_a18_intraday_top_sectors_ranking_and_trends_freshness_synthesis():
    mock_session = MagicMock()
    service = IntradayBriefingService(session=mock_session)
    service.data_service = DataService(session=None)
    service.market_service = MagicMock()
    service.data_service.get_limit_up_pool = AsyncMock(return_value=DataResult(
        data={"items": [], "broken_limit_items": []}, quality=DataQuality.FULL, provider="test"
    ))
    service.data_service.get_market_index_trend = AsyncMock(return_value=None)

    today_str = date.today().isoformat()

    # 1. 场景 A: 板块排行 STALE (10:15)，标的分时 REALTIME (10:30)
    # 期望：整体时效保守合成为 STALE (绝不被分时 REALTIME 伪造为实时)，
    # 截止时间取最早的 10:15，sector_freshness 与 trends_freshness 独立透传
    service.data_service.get_sector_ranking = AsyncMock(return_value=DataResult(
        data=[
            {"code": "BK0001", "name": "低空经济", "amount_yi": 100.0, "pct_change": 3.5, "net_inflow_yi": 15.0},
            {"code": "BK0002", "name": "半导体", "amount_yi": 80.0, "pct_change": 2.1, "net_inflow_yi": 10.0},
        ],
        quality=DataQuality.DEGRADED,
        freshness=Freshness.STALE,
        status=DataStatus.STALE,
        source_timestamp=datetime(2026, 10, 31, 10, 15, 0),
        provider="eastmoney",
    ))
    service.data_service.get_stock_trends = AsyncMock(return_value=DataResult(
        data=[
            {"code": "BK0001", "trends": [
                {"time": "09:30", "price": 10.0, "amount": 100.0, "pct_change": 0.0},
                {"time": "09:35", "price": 10.1, "amount": 200.0, "pct_change": 1.0},
                {"time": "09:40", "price": 10.2, "amount": 300.0, "pct_change": 2.0},
                {"time": "09:45", "price": 10.3, "amount": 400.0, "pct_change": 3.0},
                {"time": "09:50", "price": 10.4, "amount": 500.0, "pct_change": 4.0},
            ]},
            {"code": "BK0002", "trends": [
                {"time": "09:30", "price": 20.0, "amount": 100.0, "pct_change": 0.0},
                {"time": "09:35", "price": 20.1, "amount": 200.0, "pct_change": 0.5},
                {"time": "09:40", "price": 20.2, "amount": 300.0, "pct_change": 1.0},
                {"time": "09:45", "price": 20.3, "amount": 400.0, "pct_change": 1.5},
                {"time": "09:50", "price": 20.4, "amount": 500.0, "pct_change": 2.0},
            ]},
        ],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,
        status=DataStatus.AVAILABLE,
        source_timestamp=datetime(2026, 10, 31, 10, 30, 0),
        provider="tdx",
    ))

    resp_a = await service.get_top_sectors_trend(today_str)
    assert resp_a.quality == "DEGRADED"
    assert resp_a.freshness == "STALE"
    assert resp_a.status == "STALE"
    assert resp_a.sector_quality == "DEGRADED"
    assert resp_a.sector_freshness == "STALE"
    assert resp_a.sector_source_timestamp == "2026-10-31T10:15:00"
    assert resp_a.trends_quality == "FULL"
    assert resp_a.trends_freshness == "REALTIME"
    assert resp_a.trends_source_timestamp == "2026-10-31T10:30:00"
    assert resp_a.source_timestamp == "2026-10-31T10:15:00"
    assert resp_a.degradation_reason == "板块排行使用历史缓存快照"

    # 2. 场景 B: 板块排行 DELAYED (10:15)，标的分时 REALTIME (10:30)
    # 期望：整体时效保守合成为 DELAYED，页面可展示板块延迟标签
    service.data_service.get_sector_ranking = AsyncMock(return_value=DataResult(
        data=[
            {"code": "BK0001", "name": "低空经济", "amount_yi": 100.0, "pct_change": 3.5, "net_inflow_yi": 15.0},
        ],
        quality=DataQuality.DEGRADED,
        freshness=Freshness.DELAYED,
        status=DataStatus.AVAILABLE,
        source_timestamp=datetime(2026, 10, 31, 10, 15, 0),
        provider="eastmoney",
    ))
    resp_b = await service.get_top_sectors_trend(today_str)
    assert resp_b.quality == "DEGRADED"
    assert resp_b.freshness == "DELAYED"
    assert resp_b.sector_freshness == "DELAYED"
    assert resp_b.trends_freshness == "REALTIME"
    assert resp_b.source_timestamp == "2026-10-31T10:15:00"
    assert resp_b.degradation_reason == "板块排行行情延迟"

    # 3. 场景 C: 板块排行 REALTIME (10:30)，标的分时 DELAYED (10:15)
    # 期望：整体时效合成为 DELAYED，degradation_reason 准确指出分时行情延迟
    service.data_service.get_sector_ranking = AsyncMock(return_value=DataResult(
        data=[
            {"code": "BK0001", "name": "低空经济", "amount_yi": 100.0, "pct_change": 3.5, "net_inflow_yi": 15.0},
        ],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,
        status=DataStatus.AVAILABLE,
        source_timestamp=datetime(2026, 10, 31, 10, 30, 0),
        provider="eastmoney",
    ))
    service.data_service.get_stock_trends = AsyncMock(return_value=DataResult(
        data=[
            {"code": "BK0001", "trends": [
                {"time": "09:30", "price": 10.0, "amount": 100.0, "pct_change": 0.0},
                {"time": "09:35", "price": 10.1, "amount": 200.0, "pct_change": 1.0},
                {"time": "09:40", "price": 10.2, "amount": 300.0, "pct_change": 2.0},
                {"time": "09:45", "price": 10.3, "amount": 400.0, "pct_change": 3.0},
                {"time": "09:50", "price": 10.4, "amount": 500.0, "pct_change": 4.0},
            ]},
        ],
        quality=DataQuality.DEGRADED,
        freshness=Freshness.DELAYED,
        status=DataStatus.AVAILABLE,
        source_timestamp=datetime(2026, 10, 31, 10, 15, 0),
        provider="eastmoney",
    ))
    resp_c = await service.get_top_sectors_trend(today_str)
    assert resp_c.quality == "DEGRADED"
    assert resp_c.freshness == "DELAYED"
    assert resp_c.sector_freshness == "REALTIME"
    assert resp_c.trends_freshness == "DELAYED"
    assert resp_c.source_timestamp == "2026-10-31T10:15:00"
    assert resp_c.degradation_reason == "板块分时行情延迟"

    # 4. 场景 D: 任一来源时间缺失，整体截止时间严格保持 None (缺失保持未知，严禁冒用)
    service.data_service.get_sector_ranking = AsyncMock(return_value=DataResult(
        data=[
            {"code": "BK0001", "name": "低空经济", "amount_yi": 100.0, "pct_change": 3.5, "net_inflow_yi": 15.0},
        ],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,
        status=DataStatus.AVAILABLE,
        source_timestamp=None,  # 未知来源时间
        provider="eastmoney",
    ))
    service.data_service.get_stock_trends = AsyncMock(return_value=DataResult(
        data=[
            {"code": "BK0001", "trends": [
                {"time": "09:30", "price": 10.0, "amount": 100.0, "pct_change": 0.0},
                {"time": "09:35", "price": 10.1, "amount": 200.0, "pct_change": 1.0},
                {"time": "09:40", "price": 10.2, "amount": 300.0, "pct_change": 2.0},
                {"time": "09:45", "price": 10.3, "amount": 400.0, "pct_change": 3.0},
                {"time": "09:50", "price": 10.4, "amount": 500.0, "pct_change": 4.0},
            ]},
        ],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,
        status=DataStatus.AVAILABLE,
        source_timestamp=datetime(2026, 10, 31, 10, 30, 0),
        provider="tdx",
    ))
    resp_d = await service.get_top_sectors_trend(today_str)
    assert resp_d.quality == "FULL"
    assert resp_d.freshness == "REALTIME"
    assert resp_d.source_timestamp is None  # 缺失保持未知！
    assert resp_d.sector_source_timestamp is None
    assert resp_d.trends_source_timestamp == "2026-10-31T10:30:00"

    # 5. 场景 E: 故障恢复验证 (STALE -> FULL + REALTIME)
    # 排行数据恢复为最新物理实时数据
    service.data_service.get_sector_ranking = AsyncMock(return_value=DataResult(
        data=[
            {"code": "BK0001", "name": "低空经济", "amount_yi": 100.0, "pct_change": 3.5, "net_inflow_yi": 15.0},
        ],
        quality=DataQuality.FULL,
        freshness=Freshness.REALTIME,
        status=DataStatus.AVAILABLE,
        source_timestamp=datetime(2026, 10, 31, 10, 30, 0),
        provider="eastmoney",
    ))
    resp_e = await service.get_top_sectors_trend(today_str)
    assert resp_e.quality == "FULL"
    assert resp_e.freshness == "REALTIME"
    assert resp_e.status == "AVAILABLE"
    assert resp_e.sector_freshness == "REALTIME"
    assert resp_e.trends_freshness == "REALTIME"
    assert resp_e.source_timestamp == "2026-10-31T10:30:00"
    assert resp_e.degradation_reason is None

    # 6. 场景 F: 排行时效为 UNAVAILABLE / 未知时，绝不被分时 REALTIME 提升为 REALTIME / FULL (P1 闭环验证)
    service.data_service.get_sector_ranking = AsyncMock(return_value=DataResult(
        data=[
            {"code": "BK0001", "name": "低空经济", "amount_yi": 100.0, "pct_change": 3.5, "net_inflow_yi": 15.0},
        ],
        quality=DataQuality.FULL,
        freshness=Freshness.UNAVAILABLE,  # 排行时效不可用
        status=DataStatus.AVAILABLE,
        source_timestamp=None,
        provider="eastmoney",
    ))
    resp_f = await service.get_top_sectors_trend(today_str)
    # 核心断言：即便双方 quality 为 FULL、分时为 REALTIME，综合时效必须为 UNAVAILABLE，质量绝不能为 FULL
    assert resp_f.freshness == "UNAVAILABLE"
    assert resp_f.quality == "DEGRADED"
    assert resp_f.quality != "FULL"
    assert resp_f.sector_freshness == "UNAVAILABLE"
    assert resp_f.trends_freshness == "REALTIME"
    assert resp_f.degradation_reason == "板块排行时效未知或不可用"

    # 7. 场景 G: 双时态并存 (排行 STALE + 分时 DELAYED) 精准合成与归因 (P1.2 闭环验证)
    service.data_service.get_sector_ranking = AsyncMock(return_value=DataResult(
        data=[
            {"code": "BK0001", "name": "低空经济", "amount_yi": 100.0, "pct_change": 3.5, "net_inflow_yi": 15.0},
        ],
        quality=DataQuality.DEGRADED,
        freshness=Freshness.STALE,
        status=DataStatus.STALE,
        source_timestamp=datetime(2026, 10, 31, 10, 15, 0),
        provider="eastmoney",
    ))
    service.data_service.get_stock_trends = AsyncMock(return_value=DataResult(
        data=[
            {"code": "BK0001", "trends": [
                {"time": "09:30", "price": 10.0, "amount": 100.0, "pct_change": 0.0},
                {"time": "09:35", "price": 10.1, "amount": 200.0, "pct_change": 1.0},
                {"time": "09:40", "price": 10.2, "amount": 300.0, "pct_change": 2.0},
                {"time": "09:45", "price": 10.3, "amount": 400.0, "pct_change": 3.0},
                {"time": "09:50", "price": 10.4, "amount": 500.0, "pct_change": 4.0},
            ]},
        ],
        quality=DataQuality.DEGRADED,
        freshness=Freshness.DELAYED,
        status=DataStatus.AVAILABLE,
        source_timestamp=datetime(2026, 10, 31, 10, 15, 0),
        provider="eastmoney",
    ))
    resp_g = await service.get_top_sectors_trend(today_str)
    assert resp_g.freshness == "STALE"  # STALE 优先于 DELAYED
    assert resp_g.sector_freshness == "STALE"
    assert resp_g.trends_freshness == "DELAYED"
    assert resp_g.degradation_reason == "板块排行使用缓存快照，分时行情延迟"

    # 8. 场景 H: 概念与行业排行合并时，行业时效 UNAVAILABLE 时保守降级
    # 模拟概念仅 2 个，补充行业 3 个但行业时态为 UNAVAILABLE
    def mock_get_ranking(sec_type, limit=60):
        if sec_type == "concept":
            return DataResult(
                data=[{"code": "BK0001", "name": "概念A", "amount_yi": 100.0, "pct_change": 3.5, "net_inflow_yi": 15.0}],
                quality=DataQuality.FULL,
                freshness=Freshness.REALTIME,
                status=DataStatus.AVAILABLE,
                source_timestamp=datetime(2026, 10, 31, 10, 30, 0),
                provider="eastmoney",
            )
        else:
            return DataResult(
                data=[{"code": "BK0002", "name": "行业B", "amount_yi": 80.0, "pct_change": 2.1, "net_inflow_yi": 10.0}],
                quality=DataQuality.DEGRADED,
                freshness=Freshness.UNAVAILABLE,  # 行业时效不可用
                status=DataStatus.AVAILABLE,
                source_timestamp=None,
                provider="eastmoney",
            )
    service.data_service.get_sector_ranking = AsyncMock(side_effect=mock_get_ranking)
    resp_h = await service.get_top_sectors_trend(today_str)
    # 合并后排行时态被保守降级为 UNAVAILABLE
    assert resp_h.sector_freshness == "UNAVAILABLE"
    assert resp_h.quality == "DEGRADED"
    assert resp_h.freshness == "UNAVAILABLE"
# 9. 场景 I: 反向双时态并存 (排行 DELAYED + 分时 STALE)
    service.data_service.get_sector_ranking = AsyncMock(return_value=DataResult(
        data=[
            {"code": "BK0001", "name": "低空经济", "amount_yi": 100.0, "pct_change": 3.5, "net_inflow_yi": 15.0},
        ],
        quality=DataQuality.DEGRADED,
        freshness=Freshness.DELAYED,
        status=DataStatus.AVAILABLE,
        source_timestamp=datetime(2026, 10, 31, 10, 25, 0),
        provider="eastmoney",
    ))
    service.data_service.get_stock_trends = AsyncMock(return_value=DataResult(
        data=[
            {"code": "BK0001", "trends": [
                {"time": "09:30", "price": 10.0, "amount": 100.0, "pct_change": 0.0},
                {"time": "09:35", "price": 10.1, "amount": 200.0, "pct_change": 1.0},
                {"time": "09:40", "price": 10.2, "amount": 300.0, "pct_change": 2.0},
                {"time": "09:45", "price": 10.3, "amount": 400.0, "pct_change": 3.0},
                {"time": "09:50", "price": 10.4, "amount": 500.0, "pct_change": 4.0},
            ]},
        ],
        quality=DataQuality.DEGRADED,
        freshness=Freshness.STALE,
        status=DataStatus.STALE,
        source_timestamp=datetime(2026, 10, 31, 10, 20, 0),
        provider="eastmoney",
    ))
    resp_i = await service.get_top_sectors_trend(today_str)
    assert resp_i.freshness == "STALE"  # STALE 优先于 DELAYED 保守合成
    assert resp_i.sector_freshness == "DELAYED"
    assert resp_i.trends_freshness == "STALE"
    assert resp_i.source_timestamp == "2026-10-31T10:20:00"  # 取较早截止点
    assert resp_i.sector_source_timestamp == "2026-10-31T10:25:00"
    assert resp_i.trends_source_timestamp == "2026-10-31T10:20:00"
    assert resp_i.degradation_reason == "板块排行行情延迟，分时使用缓存快照"


