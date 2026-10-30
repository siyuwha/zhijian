import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo
import pytest

from backend.app.data.capabilities import DataQuality, DataResult, Freshness
from backend.app.data.providers.tencent import TencentProvider
from backend.app.data.quote_validator import (
    SHANGHAI_TZ,
    get_shanghai_now,
    parse_quote_datetime,
    validate_quote_batch,
    validate_quote_item,
)
from backend.app.data.registry import ProviderRegistry
from backend.app.data.service import DataService


# ---------------------------------------------------------------------------
# 1. 基础时区与时间戳解析测试 (Asia/Shanghai 服务端时区)
# ---------------------------------------------------------------------------

def test_quote_timestamp_parser_shanghai_timezone():
    """验证时间戳解析严格使用 Asia/Shanghai 时区，且对缺少日期的报价坚决不予解析"""
    # 完整 YYYY-MM-DD HH:MM:SS
    dt = parse_quote_datetime({"time": "2026-10-30 09:35:00"})
    assert dt is not None
    assert dt.tzinfo == SHANGHAI_TZ
    assert dt.year == 2026 and dt.month == 10 and dt.day == 30
    assert dt.hour == 9 and dt.minute == 35 and dt.second == 0

    # 拆分 date + time
    dt2 = parse_quote_datetime({"date": "2026-10-30", "time": "09:35:12"})
    assert dt2 is not None
    assert dt2.hour == 9 and dt2.minute == 35 and dt2.second == 12

    # TDX 若包含合法 trade_date 与 servertime
    dt3 = parse_quote_datetime({"trade_date": "20261030", "servertime": "09:35:12.500"})
    assert dt3 is not None
    assert dt3.day == 30 and dt3.hour == 9 and dt3.minute == 35 and dt3.second == 12

    # P0 治理防线：无真实日期的孤立 servertime 坚决返回 None，绝不假装为当前日期
    dt_orphan = parse_quote_datetime({"servertime": "09:35:12"})
    assert dt_orphan is None

    # 完全缺少时间戳信息返回 None
    assert parse_quote_datetime({}) is None
    assert parse_quote_datetime({"code": "600519"}) is None


# ---------------------------------------------------------------------------
# 2. 当日判断与 0 <= now - quote_time <= 300 秒新鲜度区间判定
# ---------------------------------------------------------------------------

def test_validate_quote_shanghai_today_rule():
    """验证必须使用 Asia/Shanghai 的服务端时间判断当日"""
    base_now = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)

    # 当日报价合格
    ok, err = validate_quote_item(
        {"code": "600519", "date": "2026-10-30", "time": "2026-10-30 09:58:00"},
        now=base_now,
    )
    assert ok is True
    assert err == ""

    # 昨日同一时刻报价 (跨日) -> 刚性拒绝
    ok, err = validate_quote_item(
        {"code": "600519", "date": "2026-10-29", "time": "2026-10-29 09:58:00"},
        now=base_now,
    )
    assert ok is False
    assert "Date mismatch" in err
    assert "Asia/Shanghai" in err

    # 明日报价 -> 刚性拒绝
    ok, err = validate_quote_item(
        {"code": "600519", "date": "2026-10-31", "time": "2026-10-31 10:00:00"},
        now=base_now,
    )
    assert ok is False


def test_validate_quote_freshness_boundary_conditions():
    """
    验证严格数学区间：0 ≤ 当前时间 − 报价时间 ≤ 300 秒
    - 0 秒 (完全同步): 合格
    - 300.0 秒 (窗口边界): 合格
    - 300.1 秒 (超时): 拒绝 (Stale quote)
    - -0.1 秒 (未来时间戳): 严格拒绝 (Future timestamp)
    """
    base_now = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)

    # 边界 1: 当前时间完全等于报价时间 (diff = 0)
    q_now = {"code": "600519", "date": "2026-10-30", "time": "2026-10-30 10:00:00"}
    ok, _ = validate_quote_item(q_now, now=base_now)
    assert ok is True

    # 边界 2: 恰好在 300 秒窗口极限 (diff = 300)
    q_300s = {"code": "600519", "date": "2026-10-30", "time": "2026-10-30 09:55:00"}
    ok, _ = validate_quote_item(q_300s, now=base_now)
    assert ok is True

    # 边界 3: 超过 300 秒哪怕 1 秒 (diff = 301)
    q_301s = {"code": "600519", "date": "2026-10-30", "time": "2026-10-30 09:54:59"}
    ok, err = validate_quote_item(q_301s, now=base_now)
    assert ok is False
    assert "Stale quote" in err
    assert "exceeds 300s" in err

    # 边界 4: 未来时间戳 (哪怕快 1 秒, diff = -1) -> 必须严格拒绝
    q_future = {"code": "600519", "date": "2026-10-30", "time": "2026-10-30 10:00:01"}
    ok, err = validate_quote_item(q_future, now=base_now)
    assert ok is False
    assert "Future timestamp" in err

    # 边界 5: 未来时间戳 (快 60 秒) -> 严格拒绝
    q_future_60s = {"code": "600519", "date": "2026-10-30", "time": "2026-10-30 10:01:00"}
    ok, err = validate_quote_item(q_future_60s, now=base_now)
    assert ok is False
    assert "Future timestamp" in err


def test_validate_quote_batch():
    """验证批量行情中只要有任意一只股票时效或日期不达标，整批判定不合格"""
    base_now = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)

    batch_valid = [
        {"code": "600519", "date": "2026-10-30", "time": "2026-10-30 09:59:30"},
        {"code": "000001", "date": "2026-10-30", "time": "2026-10-30 09:59:45"},
    ]
    ok, _ = validate_quote_batch(batch_valid, now=base_now)
    assert ok is True

    # 其中一只混入了过期数据
    batch_mixed_stale = [
        {"code": "600519", "date": "2026-10-30", "time": "2026-10-30 09:59:30"},
        {"code": "000001", "date": "2026-10-30", "time": "2026-10-30 09:50:00"},
    ]
    ok, err = validate_quote_batch(batch_mixed_stale, now=base_now)
    assert ok is False
    assert "000001" in err
    assert "Stale quote" in err


# ---------------------------------------------------------------------------
# 3. P0 治理专项：TDX 无日期报价绝不臆造当前时间，刚性拒绝并切源
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tdx_dateless_quote_rejected_and_fails_over():
    """
    P0 治理专项测试：
    验证 TDX 返回的无日期原始快照不会被补造成当前时间，
    时态校验器必须判定其缺少可验证日期 (Missing or unparseable quote timestamp)，
    从而拒收该报价并顺利触发故障转移到具备真实时间戳的备用源。
    """
    simulated_now = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)

    # 模拟真实 TDX 客户端：仅返回价格与 servertime，没有真实 exchange date
    def tdx_dateless_resp(codes):
        return DataResult(
            data=[
                {
                    "code": c,
                    "symbol": c,
                    "price": 11.5,
                    "last_close": 11.2,
                    "servertime": "10:15:30.200",
                    "date": None,  # 绝不补造当前日期
                    "trade_date": None,
                    "time": "10:15:30.200",
                }
                for c in codes
            ],
            quality=DataQuality.FULL,
            provider="tdx_direct",
        )

    # 备用源 (腾讯): 带有真实日期和时间的完整行情
    def tencent_backup_resp(codes):
        return DataResult(
            data=[
                {
                    "code": f"sz{c}",
                    "symbol": c,
                    "name": "平安银行",
                    "price": 11.54,
                    "prev_close": 11.31,
                    "open": 11.30,
                    "pct_change": 2.03,
                    "date": "2026-10-30",
                    "trade_date": "2026-10-30",
                    "time": "2026-10-30 09:59:50",
                    "amount_wan": 228390.0,
                }
                for c in codes
            ],
            quality=DataQuality.FULL,
            provider="tencent",
        )

    reg = ProviderRegistry()
    class DummyProvider:
        def __init__(self, name, fn):
            self.name = name
            self.fn = fn
        async def get_stock_quotes(self, codes):
            return self.fn(codes)

    reg.register("stock_quote", "tdx_direct", DummyProvider("tdx_direct", tdx_dateless_resp), is_primary=True)
    reg.register("stock_quote", "tencent", DummyProvider("tencent", tencent_backup_resp), is_primary=False)

    res = await reg.execute_with_fallback(
        "stock_quote",
        "get_stock_quotes",
        ["000001"],
        reference_now=simulated_now,
    )

    # 核心断言：
    # 1. TDX 无日期旧价未被放行，系统切换到腾讯备用源
    assert res.provider == "tencent"
    assert res.fallback_used is True
    assert len(res.data) == 1
    assert res.data[0]["symbol"] == "000001"
    assert res.data[0]["price"] == 11.54
    assert res.data[0]["date"] == "2026-10-30"
    assert res.data[0]["time"] == "2026-10-30 09:59:50"

    # 2. 检查审计事件
    logs = reg.get_audit_logs()
    assert len(logs) >= 1
    log_entry = [l for l in logs if l.capability == "stock_quote"][-1]
    assert log_entry.original_provider == "tdx_direct"
    assert log_entry.target_provider == "tencent"
    assert "Missing or unparseable quote timestamp" in log_entry.failover_reason


# ---------------------------------------------------------------------------
# 4. P1 治理专项：腾讯备用报价源 (TencentProvider) 协议解析与契约测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tencent_provider_quote_parsing_and_contract():
    """
    验证 TencentProvider 对 qt.gtimg.cn 协议的完整解析与时态真实性
    验证点：第 30 位 YYYYMMDDHHMMSS 格式精准解析为 date 与 time，不伪造系统时间
    """
    raw_payload = (
        'v_sh600519="1~贵州茅台~600519~1354.00~1330.75~1349.99~42992~24647~18345~'
        '1353.77~1~1352.00~2~1351.06~1~1351.00~2~1350.99~1~'
        '1354.00~27~1354.01~1~1354.02~1~1354.18~1~1354.40~1~~'
        '20261030095830~23.25~1.75~1356.00~1330.01~1354.00/42992/5797980334~42992~579798~0.34~20.79~~'
        '1356.00~1330.01~1.95~16926.10~16926.10~6.74~1463.83~1197.68~0.98~-24~1348.61~19.01~20.56~~~0.03~579798.0334";'
    )

    provider = TencentProvider()

    # Mock 外部网络响应
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = raw_payload.encode("gbk")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        res = await provider.get_stock_quotes(["600519"])
        assert res.quality == DataQuality.FULL
        assert res.provider == "tencent"
        assert len(res.data) == 1

        q = res.data[0]
        # 完整字段结构断言
        assert q["code"] == "sh600519"
        assert q["symbol"] == "600519"
        assert q["name"] == "贵州茅台"
        assert q["price"] == 1354.00
        assert q["prev_close"] == 1330.75
        assert q["open"] == 1349.99
        assert q["high"] == 1356.00
        assert q["low"] == 1330.01
        assert q["pct_change"] == 1.75
        assert q["amount"] == 5797980000.0
        assert q["amount_wan"] == 579798.0
        assert q["bid1_price"] == 1353.77
        assert q["bid1_vol"] == 100.0
        assert q["ask1_price"] == 1354.00
        assert q["ask1_vol"] == 2700.0

        # 时态契约断言：严格来自第 30 位 '20261030095830'
        assert q["date"] == "2026-10-30"
        assert q["trade_date"] == "2026-10-30"
        assert q["time"] == "2026-10-30 09:58:30"


@pytest.mark.asyncio
async def test_tencent_provider_index_quotes_contract():
    """验证 TencentProvider 大盘指数解析与字段契约"""
    raw_index_payload = (
        'v_sh000001="1~上证指数~000001~3651.43~3681.47~3676.77~443564144~0~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~'
        '0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~~20261030095900~-30.04~-0.82~3678.46~3645.26~'
        '3651.43/443564144/715620694906~443564144~71562069~0.91~16.08~~3678.46~3645.26~0.90~572708.44~639245.91";'
    )

    provider = TencentProvider()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = raw_index_payload.encode("gbk")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        res = await provider.get_index_quotes(["sh000001"])
        assert res.quality == DataQuality.FULL
        assert len(res.data) == 1
        idx = res.data[0]
        assert idx["code"] == "sh000001"
        assert idx["name"] == "上证指数"
        assert idx["price"] == 3651.43
        assert idx["pre_close"] == 3681.47
        assert idx["pct_change"] == -0.82
        assert idx["date"] == "2026-10-30"
        assert idx["time"] == "2026-10-30 09:59:00"
        assert idx["amount_wan"] == 71562069.0


# ---------------------------------------------------------------------------
# 5. P1 治理专项：双源容灾切换 (Sina 主源失败 -> 自动切换 Tencent 备用源)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_failover_from_sina_to_tencent_backup():
    """
    完整容灾验收：
    Primary 为 Sina，Secondary 为 Tencent；
    当 Sina 返回陈旧数据 (超过 300 秒) 时，系统必须自动切源至 Tencent 获取最新报价。
    """
    simulated_now = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)

    # Sina: 返回 09:50:00 (滞后 600 秒)
    class FakeSina:
        async def get_stock_quotes(self, codes):
            return DataResult(
                data=[{"code": f"sh{c}", "symbol": c, "name": "贵州茅台", "price": 1350.0, "date": "2026-10-30", "time": "2026-10-30 09:50:00"} for c in codes],
                quality=DataQuality.FULL,
                provider="sina",
            )

    # Tencent: 返回 09:59:45 (仅滞后 15 秒，合规)
    class FakeTencent:
        async def get_stock_quotes(self, codes):
            return DataResult(
                data=[{"code": f"sh{c}", "symbol": c, "name": "贵州茅台", "price": 1354.0, "date": "2026-10-30", "time": "2026-10-30 09:59:45"} for c in codes],
                quality=DataQuality.FULL,
                provider="tencent",
            )

    reg = ProviderRegistry()
    reg.register("stock_quote", "sina", FakeSina(), is_primary=True)
    reg.register("stock_quote", "tencent", FakeTencent(), is_primary=False)

    res = await reg.execute_with_fallback(
        "stock_quote",
        "get_stock_quotes",
        ["600519"],
        reference_now=simulated_now,
    )

    # 断言成功平滑切换到 Tencent
    assert res.provider == "tencent"
    assert res.fallback_used is True
    assert res.data[0]["price"] == 1354.0
    assert res.data[0]["time"] == "2026-10-30 09:59:45"

    logs = reg.get_audit_logs()
    failover_log = [l for l in logs if l.capability == "stock_quote"][-1]
    assert failover_log.original_provider == "sina"
    assert failover_log.target_provider == "tencent"
    assert "QUOTE_FRESHNESS_FAIL" in failover_log.failover_reason


# ---------------------------------------------------------------------------
# 6. P1 治理专项：缓存命中时态二次校验 (防止缓存期内超过 300 秒或跨日)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_hit_revalidates_freshness_and_evicts_stale():
    """
    P1 治理专项测试：
    验证缓存命中时若行情在缓存驻留期间超过 300 秒或跨日，
    DataService 阶段 1 必须主动拒绝并淘汰过期缓存，触发物理管线重新拉取。
    """
    ds = DataService(session=None)
    DataService._CACHE.clear()

    # 设基准时间为 10:00:00，此时写入一条 09:56:00 (当时 240 秒前，尚在 300 秒内有效)
    t0_now = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)
    fresh_item = {
        "code": "sh600519",
        "symbol": "600519",
        "price": 1350.0,
        "date": "2026-10-30",
        "time": "2026-10-30 09:56:00",
    }
    initial_res = DataResult(
        data=[fresh_item],
        quality=DataQuality.FULL,
        provider="sina",
    )

    # 将其置入 DataService 内存缓存
    cache_key = "stock_quote:get_stock_quotes:(['600519'],)"
    DataService._CACHE[cache_key] = (1000.0, initial_res)  # 物理时间假定在 TTL 内

    # 1. 在时差仅 240 秒时命中缓存 -> 合法返回
    with patch("time.time", return_value=1005.0):  # 经过 5 秒，TTL(15s) 未超
        res1 = await ds.get_stock_quotes(["600519"], validate_freshness=True, reference_now=t0_now)
        # reference_now 为 10:00:00 时，diff = 240s <= 300s
        with patch("backend.app.data.service.time.time", return_value=1005.0):
            # 重新通过 _execute_pipeline 测试
            is_valid, _ = validate_quote_batch([fresh_item], now=t0_now)
            assert is_valid is True

    # 2. 模拟时钟前移至 10:02:00 (距离报价 09:56:00 已经 360 秒，超过 300 秒)
    # 尽管缓存条目的 TTL 仍在有效期内，重新校验必须将该条目主动淘汰并判定为 cache miss
    t_stale_now = datetime(2026, 10, 30, 10, 2, 0, tzinfo=SHANGHAI_TZ)
    is_valid_later, err = validate_quote_batch([fresh_item], now=t_stale_now)
    assert is_valid_later is False
    assert "Stale quote" in err

    # 模拟 DataService 穿透执行：由于缓存时态失效，缓存被淘汰，调用物理 execute_with_fallback
    re_fetched = DataResult(
        data=[{"code": "sh600519", "symbol": "600519", "price": 1356.0, "date": "2026-10-30", "time": "2026-10-30 10:01:50"}],
        quality=DataQuality.FULL,
        provider="tencent",
    )

    with patch("backend.app.data.service.time.time", return_value=1005.0):
        with patch("backend.app.data.registry.registry.execute_with_fallback", new_callable=AsyncMock, return_value=re_fetched):
            res2 = await ds.get_stock_quotes(["600519"], validate_freshness=True, reference_now=t_stale_now)
            # 验证拿到了穿透重算后的新价格 1356.0，而不是陈旧缓存 1350.0
            assert res2.data[0]["price"] == 1356.0
            assert res2.data[0]["time"] == "2026-10-30 10:01:50"


# ---------------------------------------------------------------------------
# 7. 全网无源可用终局降级测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_providers_fail_enters_degraded_stale_or_unavailable():
    """所有提供者均时效不合格时的终局收口验证"""
    simulated_now = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)

    def stale_func(codes):
        return DataResult(
            data=[{"code": c, "price": 10.0, "time": "2026-10-25 15:00:00"} for c in codes],
            quality=DataQuality.FULL,
            provider="stale_prov",
        )

    class DummyP:
        async def get_stock_quotes(self, codes):
            return stale_func(codes)

    reg = ProviderRegistry()
    reg.register("stock_quote", "src1", DummyP(), is_primary=True)
    reg.register("stock_quote", "src2", DummyP(), is_primary=False)

    # 1. 无快照缓存 -> UNAVAILABLE
    res_none = await reg.execute_with_fallback(
        "stock_quote",
        "get_stock_quotes",
        ["600000"],
        last_good_cache=None,
        reference_now=simulated_now,
    )
    assert res_none.quality == DataQuality.UNAVAILABLE
    assert res_none.freshness == Freshness.UNAVAILABLE

    # 2. 有快照缓存 -> DEGRADED + STALE
    cached_snap = DataResult(
        data=[{"code": "600000", "price": 9.98}],
        quality=DataQuality.FULL,
        provider="cached_primary",
    )
    res_cached = await reg.execute_with_fallback(
        "stock_quote",
        "get_stock_quotes",
        ["600000"],
        last_good_cache=cached_snap,
        reference_now=simulated_now,
    )
    assert res_cached.quality == DataQuality.DEGRADED
    assert res_cached.freshness == Freshness.STALE
    assert res_cached.data[0]["price"] == 9.98


# ---------------------------------------------------------------------------
# 8. P2 治理专项：北交所 92 前缀与各市场代码标准化映射核验
# ---------------------------------------------------------------------------

def test_tencent_symbol_format_and_bse_mapping():
    """
    验证 TencentProvider._format_symbol 规范：
    1. 北交所前缀：92 (新直投上市代码)、43/83/87 (精选层平移/创新层) 映射为 bj
    2. 沪市前缀：6、688 (科创板)、900 (B股) 映射为 sh
    3. 深市前缀：0、300 (创业板)、200 (B股) 映射为 sz
    4. 已包含市场前缀的代码保持不变
    """
    # 北交所
    assert TencentProvider._format_symbol("920001") == "bj920001"
    assert TencentProvider._format_symbol("920002") == "bj920002"
    assert TencentProvider._format_symbol("430001") == "bj430001"
    assert TencentProvider._format_symbol("830001") == "bj830001"
    assert TencentProvider._format_symbol("870001") == "bj870001"
    assert TencentProvider._format_symbol("880001") == "bj880001"
    assert TencentProvider._format_symbol("bj920001") == "bj920001"
    assert TencentProvider._format_symbol("920001.BJ") == "bj920001"

    # 沪市
    assert TencentProvider._format_symbol("600519") == "sh600519"
    assert TencentProvider._format_symbol("688981") == "sh688981"
    assert TencentProvider._format_symbol("900901") == "sh900901"
    assert TencentProvider._format_symbol("sh600519") == "sh600519"
    assert TencentProvider._format_symbol("600519.SH") == "sh600519"

    # 深市
    assert TencentProvider._format_symbol("000001") == "sz000001"
    assert TencentProvider._format_symbol("002594") == "sz002594"
    assert TencentProvider._format_symbol("300750") == "sz300750"
    assert TencentProvider._format_symbol("200002") == "sz200002"
    assert TencentProvider._format_symbol("sz000001") == "sz000001"
    assert TencentProvider._format_symbol("000001.SZ") == "sz000001"


# ---------------------------------------------------------------------------
# 9. P1 治理专项：腾讯单条畸形报文异常隔离 (逐标的容错，不使全批失败)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tencent_per_symbol_error_isolation_stock():
    """
    验证腾讯提供方单标的异常隔离机制：
    当一个批次包含 3 个标的，其中 1 条报文存在非数字非法字段或解析异常时：
    1. 坚决不使整批返回 FAILED 或丢弃有效标的；
    2. 有效标的 (600519, 000002) 正常成功解析并入库；
    3. 异常标的 (000001) 被精准计入 missing_codes；
    4. 质量判定为 PARTIAL，状态为 AVAILABLE。
    """
    valid_payload_600519 = (
        'v_sh600519="1~贵州茅台~600519~1354.00~1330.75~1349.99~42992~24647~18345~'
        '1353.77~1~1352.00~2~1351.06~1~1351.00~2~1350.99~1~'
        '1354.00~27~1354.01~1~1354.02~1~1354.18~1~1354.40~1~~'
        '20261030095830~23.25~1.75~1356.00~1330.01~1354.00/42992/5797980334~42992~579798~0.34~20.79~~'
        '1356.00~1330.01~1.95~16926.10~16926.10~6.74~1463.83~1197.68~0.98~-24~1348.61~19.01~20.56~~~0.03~579798.0334";'
    )
    # 畸形报文：价格位置是字符串 "CORRUPTED_PRICE"，float 必炸
    malformed_payload_000001 = (
        'v_sz000001="1~平安银行~000001~CORRUPTED_PRICE~11.31~11.30~1000~200~800~'
        '11.30~10~0~0~0~0~0~0~0~0~11.31~20~0~0~0~0~0~0~0~0~~'
        '20261030095830~0.20~1.77~11.50~11.20~11.35/1000/1135000~1000~1135000~0.01~5.0~~'
        '11.50~11.20~1.0~1000~1000~1.0~12.0~10.0~0.5~-1~11.3~1.0~1.0~~~0.01~1135000";'
    )
    valid_payload_000002 = (
        'v_sz000002="1~万科A~000002~8.50~8.30~8.40~5000~2000~3000~'
        '8.49~10~0~0~0~0~0~0~0~0~8.50~20~0~0~0~0~0~0~0~0~~'
        '20261030095830~0.20~2.41~8.60~8.30~8.50/5000/4250000~5000~425000~0.05~6.0~~'
        '8.60~8.30~1.0~1000~1000~1.0~9.0~7.5~0.5~-1~8.4~1.0~1.0~~~0.01~425000";'
    )
    mixed_content = f"{valid_payload_600519}\n{malformed_payload_000001}\n{valid_payload_000002}"

    provider = TencentProvider()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = mixed_content.encode("gbk")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        res = await provider.get_stock_quotes(["600519", "000001", "000002"])

        # 核心断言：
        # 1. 批次未被整批废弃，质量为 PARTIAL，状态为 AVAILABLE
        assert res.quality == DataQuality.PARTIAL
        assert res.status.value == "AVAILABLE"
        assert res.freshness == Freshness.REALTIME
        assert len(res.data) == 2

        # 2. 正常标的解析完全正确
        symbols = [item["symbol"] for item in res.data]
        assert "600519" in symbols
        assert "000002" in symbols

        # 3. 畸形标的 000001 被准确标记到 missing_codes
        assert res.missing_codes is not None
        assert "000001" in res.missing_codes


@pytest.mark.asyncio
async def test_tencent_per_symbol_error_isolation_index():
    """验证腾讯指数解析同样具备单标的异常隔离能力"""
    valid_index = (
        'v_sh000001="1~上证指数~000001~3651.43~3681.47~3676.77~443564144~0~0~0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~'
        '0.00~0~0.00~0~0.00~0~0.00~0~0.00~0~~20261030095900~-30.04~-0.82~3678.46~3645.26~'
        '3651.43/443564144/715620694906~443564144~71562069~0.91~16.08~~3678.46~3645.26~0.90~572708.44~639245.91";'
    )
    malformed_index = (
        'v_sz399001="1~深证成指~399001~INVALID_PRICE~11000.0~11050.0~0~0~0~0~0~0~0~0~0~0~0~0~0~'
        '0~0~0~0~0~0~0~0~0~0~~20261030095900~0~0~11100~10900~0~0~0~0~0~~0~0~0~0~0~0~0~0~0~0~0~0~0~~~0~0";'
    )
    mixed_content = f"{valid_index}\n{malformed_index}"

    provider = TencentProvider()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = mixed_content.encode("gbk")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_resp):
        res = await provider.get_index_quotes(["sh000001", "sz399001"])
        assert res.quality == DataQuality.PARTIAL
        assert len(res.data) == 1
        assert res.data[0]["name"] == "上证指数"
        assert res.missing_codes is not None
        assert "sz399001" in res.missing_codes


# ---------------------------------------------------------------------------
# 10. P0/P1/P2 端到端集成风控贯穿测试：
# 贯穿真实 TencentProvider 协议报文 -> DataService 容灾切换 -> AutonomousJobEngine 风控执行与真实账本结算
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_real_tencent_failover_triggers_stop_loss_in_ledger():
    """
    【端到端真实闭环 A】
    1. 预设持仓：贵州茅台 1000 股 @ 成本 1400.0 元 (已过 T+1)
    2. 主数据源 Sina 返回陈旧行情 (超过 300 秒)，触发时态时效拦截
    3. 系统自动故障转移至真实 TencentProvider
    4. TencentProvider 真实解析腾讯协议格式报文，现价为 1316.0 元 (浮亏 -6.0% <= -5.0% 熔断红线)
    5. DataService 将来源降级标记为 fallback_used=True，quality=DEGRADED，但 freshness=REALTIME
    6. AutonomousJobEngine 识别其为备用源真实新鲜行情，准入风控并触发【波普尔硬止损】市价平仓
    7. 验证账本：持仓归零，资金回流 1,316,000 元 (扣手续费)，SimTrade 记录平仓流水！
    """
    from backend.app.core.database import async_session
    from backend.app.models.simulation import SimAccount, SimPosition, SimTrade
    from backend.app.services.simulation import SimulationService
    from backend.app.services.autonomous_executor import AutonomousJobEngine
    from backend.app.data.providers.sina import SinaProvider
    from sqlalchemy import select

    simulated_now = datetime(2026, 10, 30, 10, 30, 0, tzinfo=SHANGHAI_TZ)
    today_str = simulated_now.strftime("%Y-%m-%d")

    # 1. 准备仿真账户与 T-1 持仓
    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 100000.0

        # 清除历史脏数据
        await session.execute(SimTrade.__table__.delete())
        await session.execute(SimPosition.__table__.delete())

        # T-1 建立持仓 1000 股 @ 1400.0
        trade = SimTrade(
            account_id=acc.id,
            code="600519",
            name="贵州茅台",
            direction="buy",
            price=1400.0,
            quantity=1000,
            trade_time="2026-10-28 10:00:00",
            decision_summary="初始建仓"
        )
        pos = SimPosition(
            account_id=acc.id,
            code="600519",
            name="贵州茅台",
            quantity=1000,
            avg_cost=1400.0,
            current_price=1400.0,
            floating_pnl=0.0
        )
        session.add_all([trade, pos])
        await session.commit()

    # 2. 模拟 Sina 主源返回过期数据 (2026-10-30 09:40:00，滞后 50 分钟)
    sina_stale_content = (
        'var hq_str_sh600519="贵州茅台,1400.0,1400.0,1316.0,1400.0,1316.0,1316.0,1316.0,'
        '1000,1400000,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-10-30,09:40:00,00";'
    )
    # 3. 模拟 Tencent 备用源返回真实新鲜行情 (2026-10-30 10:29:50，滞后 10 秒)，价格 1316.0 (-6.0%)
    tencent_fresh_content = (
        'v_sh600519="1~贵州茅台~600519~1316.00~1400.00~1390.00~50000~25000~25000~'
        '1315.00~10~0~0~0~0~0~0~0~0~1316.00~20~0~0~0~0~0~0~0~0~~'
        '20261030102950~-84.00~-6.00~1400.00~1315.00~1316.00/50000/6580000000~50000~658000~0.5~20.0~~'
        '1400.00~1315.00~2.0~50000~50000~2.0~1500~1200~0.9~-10~1350.0~20.0~20.0~~~0.03~658000";'
    )

    sina_prov = SinaProvider()
    tencent_prov = TencentProvider()

    test_reg = ProviderRegistry()
    test_reg.register("stock_quote", "sina", sina_prov, is_primary=True)
    test_reg.register("stock_quote", "tencent", tencent_prov, is_primary=False)

    async def mock_http_get(url, *args, **kwargs):
        mock_r = MagicMock()
        mock_r.status_code = 200
        if "sinajs.cn" in str(url):
            mock_r.content = sina_stale_content.encode("gbk")
        elif "gtimg.cn" in str(url):
            mock_r.content = tencent_fresh_content.encode("gbk")
        else:
            mock_r.content = b""
        return mock_r

    with patch("httpx.AsyncClient.get", side_effect=mock_http_get),          patch("app.core.calendar.calendar.is_trading_day", return_value=True),          patch("backend.app.data.registry.registry", test_reg),          patch("backend.app.data.service.registry", test_reg):

        async with async_session() as session:
            ds = DataService(session)
            ds.current_now = simulated_now
            ds.current_date = today_str
            engine = AutonomousJobEngine(session, data_service=ds)

            # 运行风控守护机
            guard_res = await engine.run_intraday_risk_guard_detailed(
                target_date=today_str,
                now_dt=simulated_now
            )

            # 核心断言 1: 风控识别并成功执行平仓
            assert guard_res["status"] in ("LIQUIDATED", "PARTIAL_LIQUIDATED")
            assert len(guard_res["actual_liquidations"]) == 1
            liq_event = guard_res["actual_liquidations"][0]
            assert liq_event["code"] == "600519"
            expected_sell_price = round(1316.00 * 0.999, 2)
            assert liq_event["sell_price"] == expected_sell_price
            assert liq_event["quantity"] == 1000
            assert "波普尔硬止损" in liq_event["trigger_reason"]
            assert liq_event["status"] == "LIQUIDATED"

            # 核心断言 2: 验证账本真实成交与持仓清空
            positions = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalars().all()
            assert len(positions) == 0, "平仓后持仓必须被完全清空！"

            trades = (await session.execute(select(SimTrade).where(SimTrade.code == "600519"))).scalars().all()
            sell_trades = [t for t in trades if t.direction == "sell"]
            assert len(sell_trades) == 1, "账本中必须存在一笔真实卖出平仓流水！"
            assert sell_trades[0].quantity == 1000
            assert sell_trades[0].price == expected_sell_price

            # 核心断言 3: 资金正确回流
            acc_after = (await session.execute(select(SimAccount))).scalar_one()
            # 卖出金额: 1000 * 1314.68 = 1314680.0
            # 初始 100,000 + 1,314,680 = 1,414,680
            expected_capital = round(100000.0 + (1000 * expected_sell_price), 2)
            assert round(acc_after.current_capital, 2) == expected_capital


# ---------------------------------------------------------------------------
# 11. P0 治理专项：双源完全失效或仅有历史缓存时，绝对零成交刚性守卫测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dual_source_failure_zero_trade_strict_guarantee():
    """
    【双源失效零成交铁律】
    1. 持仓 600519 浮亏严重 (成本 1400.0)
    2. 主源 Sina 网络异常/超时，备源 Tencent 亦异常超时 (双源全断流)
    3. 注册中心降级返回 UNAVAILABLE (或历史 STALE 缓存快照)
    4. AutonomousJobEngine 坚决拒绝使用旧缓存或持仓成本价成交！
    5. 严格核验：资金、持仓数量、交易流水 100% 毫无变化！
    """
    from backend.app.core.database import async_session
    from backend.app.models.simulation import SimAccount, SimPosition, SimTrade
    from backend.app.services.simulation import SimulationService
    from backend.app.services.autonomous_executor import AutonomousJobEngine
    from sqlalchemy import select

    simulated_now = datetime(2026, 10, 30, 10, 30, 0, tzinfo=SHANGHAI_TZ)
    today_str = simulated_now.strftime("%Y-%m-%d")

    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 500000.0

        await session.execute(SimTrade.__table__.delete())
        await session.execute(SimPosition.__table__.delete())

        t = SimTrade(account_id=acc.id, code="600519", name="贵州茅台", direction="buy", price=1400.0, quantity=1000, trade_time="2026-10-28 10:00:00")
        p = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=1400.0, current_price=1400.0, floating_pnl=0.0)
        session.add_all([t, p])
        await session.commit()

    # 模拟双源全断流返回 UNAVAILABLE
    failed_quotes_result = DataResult(
        data=None,
        quality=DataQuality.UNAVAILABLE,
        freshness=Freshness.UNAVAILABLE,
        provider="all_failed",
        fallback_used=True,
        error_message="Both Sina and Tencent physical networks timed out"
    )

    async with async_session() as session:
        engine = AutonomousJobEngine(session)
        guard_res = await engine.run_intraday_risk_guard_detailed(
            target_date=today_str,
            now_dt=simulated_now,
            quotes_result=failed_quotes_result
        )

        # 核心断言 1: 风控状态跳过，平仓列表为空，未检查标的记录为 600519
        assert guard_res["status"] == "SKIPPED"
        assert len(guard_res["actual_liquidations"]) == 0
        assert "600519" in guard_res["missing_quotes"]
        assert "严禁伪造成交" in guard_res["reason"]

        # 核心断言 2: 账本持仓完全不变 (仍为 1000 股)
        pos = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalar_one()
        assert pos.quantity == 1000
        assert pos.avg_cost == 1400.0

        # 核心断言 3: 绝无卖出流水
        trades = (await session.execute(select(SimTrade).where(SimTrade.code == "600519"))).scalars().all()
        sell_trades = [t for t in trades if t.direction == "sell"]
        assert len(sell_trades) == 0

        # 核心断言 4: 现金毫厘不爽
        acc_after = (await session.execute(select(SimAccount))).scalar_one()
        assert acc_after.current_capital == 500000.0


# ---------------------------------------------------------------------------
# 12. P0 治理专项：部分标的缺行情时，隔离跳过并绝不伪造卖出
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_partial_quotes_missing_isolated_and_zero_unwarranted_sell():
    """
    验证持仓多标的时，若某一标的缺失有效行情或行情过期：
    - 有效标的 (正常安全) 正常巡检
    - 缺行情标的被跳过，严禁借用成本价将其视为安全或执行平仓
    - 状态返回 PARTIAL_HOLD，持仓和资金毫无变动
    """
    from backend.app.core.database import async_session
    from backend.app.models.simulation import SimAccount, SimPosition, SimTrade
    from backend.app.services.simulation import SimulationService
    from backend.app.services.autonomous_executor import AutonomousJobEngine
    from sqlalchemy import select

    simulated_now = datetime(2026, 10, 30, 10, 30, 0, tzinfo=SHANGHAI_TZ)
    today_str = simulated_now.strftime("%Y-%m-%d")

    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()

        await session.execute(SimTrade.__table__.delete())
        await session.execute(SimPosition.__table__.delete())

        # 标的 1: 600519 (有新鲜行情，现价 1390.0，浮亏 -0.7%，安全)
        t1 = SimTrade(account_id=acc.id, code="600519", name="贵州茅台", direction="buy", price=1400.0, quantity=1000, trade_time="2026-10-28 10:00:00")
        p1 = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=1400.0, current_price=1400.0, floating_pnl=0.0)

        # 标的 2: 000001 (行情完全缺失)
        t2 = SimTrade(account_id=acc.id, code="000001", name="平安银行", direction="buy", price=12.0, quantity=2000, trade_time="2026-10-28 10:00:00")
        p2 = SimPosition(account_id=acc.id, code="000001", name="平安银行", quantity=2000, avg_cost=12.0, current_price=12.0, floating_pnl=0.0)

        session.add_all([t1, p1, t2, p2])
        await session.commit()

    # 仅返回 600519 的行情，000001 缺失
    partial_quotes = DataResult(
        data=[
            {
                "code": "sh600519",
                "symbol": "600519",
                "price": 1390.0,
                "date": today_str,
                "time": f"{today_str} 10:29:55",
            }
        ],
        quality=DataQuality.PARTIAL,
        freshness=Freshness.REALTIME,
        provider="tencent"
    )

    async with async_session() as session:
        engine = AutonomousJobEngine(session)
        guard_res = await engine.run_intraday_risk_guard_detailed(
            target_date=today_str,
            now_dt=simulated_now,
            quotes_result=partial_quotes
        )

        # 核心断言：
        # 1. 状态为 PARTIAL_HOLD，绝非盲目宣称全部安全
        assert guard_res["status"] == "PARTIAL_HOLD"
        assert len(guard_res["actual_liquidations"]) == 0
        assert "000001" in guard_res["missing_quotes"]
        assert "600519" in guard_res["checked_symbols"]

        # 2. 两只标的持仓均保持原状
        pos_600519 = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalar_one()
        pos_000001 = (await session.execute(select(SimPosition).where(SimPosition.code == "000001"))).scalar_one()
        assert pos_600519.quantity == 1000
        assert pos_000001.quantity == 2000


# ---------------------------------------------------------------------------
# 13. P1 治理专项：断路器冷却后半开探针探测主源恢复测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_circuit_breaker_probe_and_primary_recovery():
    """
    验证断路器熔断恢复状态机：
    1. 主源 Sina 连续失败触发断路器 OPEN，流量切到备用源 Tencent；
    2. 冷却窗口到达后，断路器自动进入 HALF_OPEN 状态；
    3. 半开探测请求放行主源 Sina，当主源返回正常时，断路器恢复 CLOSED，主源自动复位！
    """
    simulated_now = datetime(2026, 10, 30, 10, 0, 0, tzinfo=SHANGHAI_TZ)

    reg = ProviderRegistry()
    cb_sina = reg.get_circuit_breaker("sina")
    # 设置极短冷却时间用于测试
    cb_sina.base_cooldown_seconds = 0.1
    cb_sina.current_cooldown = 0.1

    # 1. 模拟 Sina 连续失败熔断
    for _ in range(cb_sina.failure_threshold):
        await cb_sina.record_failure("test_error")

    assert cb_sina.state.value == "OPEN"

    # 此时无法直接执行
    can_exec, is_probe = await cb_sina.can_execute()
    assert can_exec is False

    # 2. 等待冷却时间过去，进入 HALF_OPEN
    await asyncio.sleep(0.12)
    can_exec, is_probe = await cb_sina.can_execute()
    assert can_exec is True
    assert is_probe is True
    assert cb_sina.state.value == "HALF_OPEN"

    # 3. 探测成功 -> 恢复 CLOSED
    await cb_sina.record_success()
    assert cb_sina.state.value == "CLOSED"
    assert cb_sina.consecutive_failures == 0


# ---------------------------------------------------------------------------
# 14. P1 专项：时态解析日期时间精度与时区偏移严格核验测试
# ---------------------------------------------------------------------------

def test_quote_date_only_and_timezone_offset_handling():
    """
    【Codex 第三轮 P1-1 闭环验证】
    1. 仅有日期的报价 (无论何时) 坚决拒绝伪造零点，防止 00:02 等特殊时刻被误判为新鲜；
    2. 带时区偏移的 ISO 时间字符串 (如 UTC +00:00) 必须正确换算为 Asia/Shanghai；
       - 例如：在上海时间 10:00:30，报价时间为 2026-10-30 10:00:00+00:00 (UTC 10:00 即上海 18:00)，
         属于未来行情，必须严格拒绝，绝不允许截断 "+00:00" 误判为有效！
    3. 带本地 +08:00 偏移的时间字符串正常解析并与服务端时间对齐。
    """
    # 1. 模拟上海时间 00:02:00，传入仅包含 date="2026-10-30" 的报价 -> 必须拒绝
    now_0002 = datetime(2026, 10, 30, 0, 2, 0, tzinfo=SHANGHAI_TZ)
    ok_date_only, err_date_only = validate_quote_item({"code": "600519", "date": "2026-10-30"}, now=now_0002)
    assert ok_date_only is False, "仅有日期的报价绝不能被判定为有效实时行情！"
    assert "requires valid HH:MM:SS" in err_date_only or "Missing" in err_date_only

    # 传入 time="2026-10-30" (缺少时分秒) -> 同样必须拒绝
    ok_time_date_only, _ = validate_quote_item({"code": "600519", "time": "2026-10-30"}, now=now_0002)
    assert ok_time_date_only is False

    # 2. 模拟上海时间 10:00:30，传入 2026-10-30 10:00:00+00:00 (UTC 10:00 换算为上海 18:00，超前当前时间 8 小时)
    now_1000 = datetime(2026, 10, 30, 10, 0, 30, tzinfo=SHANGHAI_TZ)
    ok_utc, err_utc = validate_quote_item(
        {"code": "600519", "time": "2026-10-30 10:00:00+00:00"},
        now=now_1000
    )
    assert ok_utc is False, "带 UTC 偏移的超前未来时间必须被拒！"
    assert "Future timestamp" in err_utc
    assert "18:00:00" in err_utc  # 确认正确换算为了上海时间 18:00:00

    # 3. 模拟上海时间 10:00:30，传入 2026-10-30 10:00:00+08:00 (上海时间 10:00:00，距当前 30 秒) -> 合格
    ok_shanghai_tz, err_shanghai_tz = validate_quote_item(
        {"code": "600519", "time": "2026-10-30 10:00:00+08:00"},
        now=now_1000
    )
    assert ok_shanghai_tz is True
    assert err_shanghai_tz == ""

    # 4. 【Codex 第四轮 P1 核心验证】模拟上海时间 10:00:30，传入缺少秒数的报价 (如 time="2026-10-30 10:00")
    # 坚决杜绝 datetime.fromisoformat 自动补 00 秒后按 10:00:00 误判为有效！
    ok_no_sec, err_no_sec = validate_quote_item(
        {"code": "600519", "time": "2026-10-30 10:00"},
        now=now_1000
    )
    assert ok_no_sec is False, "缺少秒数的报价绝不能通过秒级新鲜度校验！"

    # 带时区偏移但缺少秒数: time="2026-10-30 10:00+08:00" -> 必须严格拒绝
    ok_no_sec_tz, _ = validate_quote_item(
        {"code": "600519", "time": "2026-10-30 10:00+08:00"},
        now=now_1000
    )
    assert ok_no_sec_tz is False, "带时区偏移但缺少秒数的报价必须严格拒绝！"

    # 仅有时分: time="10:00", date="2026-10-30" -> 同样必须拒绝
    ok_short_time, _ = validate_quote_item(
        {"code": "600519", "date": "2026-10-30", "time": "10:00"},
        now=now_1000
    )
    assert ok_short_time is False

    # 批量校验接口与全量管线拒绝缺少秒数报价
    batch_ok, batch_err = validate_quote_batch([{"code": "600519", "time": "2026-10-30 10:00"}], now=now_1000)
    assert batch_ok is False

    # 5. 【Codex 第五轮 P1 核心验证】负时区偏移 (如 -05:30) 且缺少秒数，坚决防范时区负号导致数字统计误判为具备秒级
    # 模拟上海时间 10:00:30，传入 2026-10-29T20:30-05:30 (无秒数，换算后恰为上海 10:00:00，距当前 30 秒)
    # 通用行情校验器必须刚性拒绝放行！
    ok_neg_tz_no_sec, err_neg_tz_no_sec = validate_quote_item(
        {"code": "600519", "time": "2026-10-29T20:30-05:30"},
        now=now_1000
    )
    assert ok_neg_tz_no_sec is False, "负时区偏移且缺少秒数的报价必须刚性拒绝！"
    assert "dateless or invalid HH:MM:SS" in err_neg_tz_no_sec

    # 补充对照：带有秒数的负时区偏移 (2026-10-29T20:30:00-05:30) -> 换算为上海 10:00:00，距当前 30 秒，属于有效范围
    ok_neg_tz_with_sec, err_neg_tz_with_sec = validate_quote_item(
        {"code": "600519", "time": "2026-10-29T20:30:00-05:30"},
        now=now_1000
    )
    assert ok_neg_tz_with_sec is True, "带完整秒数的负时区偏移在时效范围内应当正常合格放行"
    assert err_neg_tz_with_sec == ""


def test_tencent_provider_admission_metadata():
    """
    【Codex 第四轮 P2 闭环验证】
    核实 TencentProvider 五维准入元数据准确如实标注：
    物理网络连通性、协议结构真实抓包核验与语义判定均恪守 '待验证'，生产资格严格标识 '仅作备用'。
    """
    prov = TencentProvider()
    meta = prov.get_admission_metadata()
    assert meta["implementation_status"] == "已接入"
    assert meta["connectivity_verified"] == "待验证"
    assert meta["schema_verified"] == "待验证"
    assert meta["semantic_verified"] == "待验证"
    assert meta["production_eligible"] == "仅作备用"


# ---------------------------------------------------------------------------
# 15. P1 专项：备用源原生 DEGRADED 拒绝交易与有效备用成交严格对比
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_native_degraded_fallback_quote_rejected_by_risk_engine():
    """
    【Codex 第三轮 P1-2 闭环验证 A：原生 DEGRADED 备用源不成交铁律】
    若备用源数据物理产出即为 DEGRADED (例如自身质量异常或字段缺陷)，
    即使时标新鲜且 fallback_used=True，系统必须保留其 original_quality=DEGRADED，
    AutonomousJobEngine 坚决拒绝交易，资金、持仓和交易流水 100% 保持原样！
    """
    from backend.app.core.database import async_session
    from backend.app.models.simulation import SimAccount, SimPosition, SimTrade
    from backend.app.services.simulation import SimulationService
    from backend.app.services.autonomous_executor import AutonomousJobEngine
    from sqlalchemy import select

    simulated_now = datetime(2026, 10, 30, 10, 30, 0, tzinfo=SHANGHAI_TZ)
    today_str = simulated_now.strftime("%Y-%m-%d")

    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 100000.0

        await session.execute(SimTrade.__table__.delete())
        await session.execute(SimPosition.__table__.delete())

        t = SimTrade(account_id=acc.id, code="600519", name="贵州茅台", direction="buy", price=1400.0, quantity=1000, trade_time="2026-10-28 10:00:00")
        p = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=1400.0, current_price=1400.0, floating_pnl=0.0)
        session.add_all([t, p])
        await session.commit()

    # 构造原生明确为 DEGRADED 的备用源行情 (即使带有 REALTIME 新鲜度标签)
    raw_degraded_fallback = DataResult(
        data=[
            {
                "code": "sh600519",
                "symbol": "600519",
                "price": 1316.0,  # 跌 6%，若放行本会触发止损
                "date": today_str,
                "time": f"{today_str} 10:29:55",
            }
        ],
        quality=DataQuality.DEGRADED,
        original_quality=DataQuality.DEGRADED,  # 关键：原生即为 DEGRADED
        freshness=Freshness.REALTIME,
        provider="tencent_degraded_mock",
        fallback_used=True
    )

    async with async_session() as session:
        engine = AutonomousJobEngine(session)
        guard_res = await engine.run_intraday_risk_guard_detailed(
            target_date=today_str,
            now_dt=simulated_now,
            quotes_result=raw_degraded_fallback
        )

        # 核心断言 1: 风控识别其原始质量为 DEGRADED，坚决拒绝交易
        assert guard_res["status"] == "SKIPPED"
        assert len(guard_res["actual_liquidations"]) == 0
        assert "600519" in guard_res["missing_quotes"]

        # 核心断言 2: 账本持仓与资金分毫不动
        pos = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalar_one()
        assert pos.quantity == 1000

        trades = (await session.execute(select(SimTrade).where(SimTrade.code == "600519"))).scalars().all()
        assert len([tr for tr in trades if tr.direction == "sell"]) == 0

        acc_after = (await session.execute(select(SimAccount))).scalar_one()
        assert acc_after.current_capital == 100000.0


@pytest.mark.asyncio
async def test_native_full_fallback_quote_accepted_for_stop_loss():
    """
    【Codex 第三轮 P1-2 闭环验证 B：确证合格 FULL 备用源准入止损】
    若备用源数据物理产出为 FULL (合格新鲜真实行情)，虽然因发生切源被管线标为 quality=DEGRADED，
    但其 original_quality=FULL 被完整保留并核验，
    AutonomousJobEngine 准予执行波普尔硬止损，确保极端行情下资金安全！
    """
    from backend.app.core.database import async_session
    from backend.app.models.simulation import SimAccount, SimPosition, SimTrade
    from backend.app.services.simulation import SimulationService
    from backend.app.services.autonomous_executor import AutonomousJobEngine
    from sqlalchemy import select

    simulated_now = datetime(2026, 10, 30, 10, 30, 0, tzinfo=SHANGHAI_TZ)
    today_str = simulated_now.strftime("%Y-%m-%d")

    async with async_session() as session:
        sim_svc = SimulationService(session)
        acc = await sim_svc.get_or_create_default_account()
        acc.current_capital = 100000.0

        await session.execute(SimTrade.__table__.delete())
        await session.execute(SimPosition.__table__.delete())

        t = SimTrade(account_id=acc.id, code="600519", name="贵州茅台", direction="buy", price=1400.0, quantity=1000, trade_time="2026-10-28 10:00:00")
        p = SimPosition(account_id=acc.id, code="600519", name="贵州茅台", quantity=1000, avg_cost=1400.0, current_price=1400.0, floating_pnl=0.0)
        session.add_all([t, p])
        await session.commit()

    # 构造原始质量确证合格为 FULL 的备用源切源行情
    valid_full_fallback = DataResult(
        data=[
            {
                "code": "sh600519",
                "symbol": "600519",
                "price": 1316.0,  # 跌 6.0% <= -5.0%
                "date": today_str,
                "time": f"{today_str} 10:29:55",
            }
        ],
        quality=DataQuality.DEGRADED,        # 管线标记备用源降级
        original_quality=DataQuality.FULL,  # 关键：物理产出确证为 FULL
        freshness=Freshness.REALTIME,
        provider="tencent",
        fallback_used=True
    )

    async with async_session() as session:
        engine = AutonomousJobEngine(session)
        guard_res = await engine.run_intraday_risk_guard_detailed(
            target_date=today_str,
            now_dt=simulated_now,
            quotes_result=valid_full_fallback
        )

        # 核心断言 1: 确证合格备用行情准入，成功执行平仓
        assert guard_res["status"] in ("LIQUIDATED", "PARTIAL_LIQUIDATED")
        assert len(guard_res["actual_liquidations"]) == 1
        liq = guard_res["actual_liquidations"][0]
        assert liq["code"] == "600519"
        assert liq["quantity"] == 1000
        assert "波普尔硬止损" in liq["trigger_reason"]

        # 核心断言 2: 账本成功清空持仓
        positions = (await session.execute(select(SimPosition).where(SimPosition.code == "600519"))).scalars().all()
        assert len(positions) == 0

        trades = (await session.execute(select(SimTrade).where(SimTrade.code == "600519"))).scalars().all()
        sell_trades = [tr for tr in trades if tr.direction == "sell"]
        assert len(sell_trades) == 1
