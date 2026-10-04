"""
A股市场物理事实心跳确权单元测试 (Market Heartbeat Tests)
验证：
1. 极端博弈心跳 (全市场涨跌停非零判定)
2. 指数撮合流动性心跳 (各大核心指数成交额大于零判定)
3. 全市场广度心跳 (上涨与下跌家数非零判定)
4. 容错性与降级韧性 (单源不可用时不产生伪休市误杀)
5. DailyReviewService 集成：物理心跳失败时刚性阻断复盘生成
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.database import Base
from app.core.market_heartbeat import MarketHeartbeatDetector, MarketHeartbeatResult
from app.services.daily_review import DailyReviewService


def test_heartbeat_normal_trading_day():
    """测试常规真实交易日：指数有巨额成交撮合、涨跌停极端博弈活跃、全市场广度正常"""
    indices = [
        {"code": "sh000001", "name": "上证指数", "price": 3350.5, "amount_wan": 45000000.0},
        {"code": "sz399001", "name": "深证成指", "price": 10800.0, "amount_wan": 65000000.0},
        {"code": "sz399006", "name": "创业板指", "price": 2250.0, "amount_wan": 30000000.0},
    ]
    limit_up = {
        "total_count": 68,
        "limit_down_count": 3,
        "max_height": 5,
    }
    breadth = {
        "up_count": 3200,
        "down_count": 1950,
        "flat_count": 150,
    }

    result = MarketHeartbeatDetector.detect(
        indices=indices,
        limit_up=limit_up,
        breadth=breadth,
        target_date="2026-09-30",
    )

    assert result.is_active_trading_day is True
    assert result.confidence == 1.0
    assert result.metrics["total_amount_yi"] == 14000.0
    assert result.metrics["total_limits"] == 71
    assert result.metrics["total_active_breadth"] == 5150
    assert any("成交撮合" in r for r in result.reasons)
    assert any("极端博弈" in r for r in result.reasons)


def test_heartbeat_weekend_or_holiday_all_zero():
    """测试周末或休市法定节假日：指数成交额为0，涨停跌停均为0，广度为0"""
    indices = [
        {"code": "sh000001", "name": "上证指数", "price": 3350.5, "amount_wan": 0.0},
        {"code": "sz399001", "name": "深证成指", "price": 10800.0, "amount_wan": 0.0},
        {"code": "sz399006", "name": "创业板指", "price": 2250.0, "amount_wan": 0.0},
    ]
    limit_up = {
        "total_count": 0,
        "limit_down_count": 0,
        "max_height": 0,
    }
    breadth = {
        "up_count": 0,
        "down_count": 0,
        "flat_count": 0,
    }

    result = MarketHeartbeatDetector.detect(
        indices=indices,
        limit_up=limit_up,
        breadth=breadth,
        target_date="2026-10-01",
    )

    assert result.is_active_trading_day is False
    assert result.confidence == 0.99
    assert result.metrics["total_amount_yi"] == 0.0
    assert result.metrics["total_limits"] == 0
    assert any("涨跌停家数全为0" in r for r in result.reasons)
    assert any("核心大盘指数成交额归零" in r for r in result.reasons)
    assert any("全市场活跃涨跌家数为0" in r for r in result.reasons)


def test_heartbeat_eastmoney_holiday_empty_pools():
    """测试东方财富节假日空池响应：涨停跌停归零且成交额归零"""
    indices = [
        {"code": "sh000001", "name": "上证指数", "price": 0.0, "amount_wan": 0.0},
    ]
    limit_up = {
        "total_count": 0,
        "limit_down_count": 0,
    }

    result = MarketHeartbeatDetector.detect(
        indices=indices,
        limit_up=limit_up,
        breadth=None,
        target_date="2026-10-02",
    )

    assert result.is_active_trading_day is False
    assert result.confidence == 0.99
    assert result.metrics["total_limits"] == 0


def test_heartbeat_resilience_partial_source_failure():
    """
    测试接口降级容错：
    当某一接口异常（如涨停池API挂掉导致 limit_up 为空），
    但大盘成交额达1.2万亿、全市场有3500家股票上涨，
    心跳检测器绝不应该武断地误杀正常交易日！
    """
    indices = [
        {"code": "sh000001", "name": "上证指数", "price": 3350.5, "amount_wan": 50000000.0},
        {"code": "sz399001", "name": "深证成指", "price": 10800.0, "amount_wan": 70000000.0},
    ]
    # limit_up 缺失 (None)
    breadth = {
        "up_count": 3500,
        "down_count": 1500,
    }

    result = MarketHeartbeatDetector.detect(
        indices=indices,
        limit_up=None,
        breadth=breadth,
        target_date="2026-09-30",
    )

    assert result.is_active_trading_day is True
    assert result.metrics["total_amount_yi"] == 12000.0


def test_heartbeat_resilience_index_failure_with_active_limits():
    """
    测试接口降级容错：
    当指数接口暂时无响应，但全市场有88只涨停板和3只跌停板，
    极端博弈心跳明显，判定依然为有效开盘交易日。
    """
    limit_up = {
        "total_count": 88,
        "limit_down_count": 3,
    }

    result = MarketHeartbeatDetector.detect(
        indices=[],
        limit_up=limit_up,
        breadth=None,
        target_date="2026-09-30",
    )

    assert result.is_active_trading_day is True
    assert result.metrics["total_limits"] == 91


def test_heartbeat_total_data_missing():
    """测试所有维度数据全部缺失的极限边界情况"""
    result = MarketHeartbeatDetector.detect(
        indices=None,
        limit_up=None,
        breadth=None,
        target_date="2026-10-01",
    )

    assert result.is_active_trading_day is False
    assert any("全维度市场物理数据完全缺失" in r for r in result.reasons)


def test_heartbeat_prev_close_mirror():
    """测试场景二：通信正常，但核心指数点位与前一交易日收盘绝对镜像 (The Mirror Test)"""
    prev_indices = [
        {"code": "sh000001", "name": "上证指数", "price": 3336.50, "amount_wan": 45000000.0},
        {"code": "sz399001", "name": "深证成指", "price": 10550.20, "amount_wan": 60000000.0},
        {"code": "sz399006", "name": "创业板指", "price": 2180.10, "amount_wan": 25000000.0},
    ]
    # 周末或节假日，行情源通信正常200，但数据直接返回上周五收盘点位
    cur_indices = [
        {"code": "sh000001", "name": "上证指数", "price": 3336.50, "amount_wan": 45000000.0},
        {"code": "sz399001", "name": "深证成指", "price": 10550.20, "amount_wan": 60000000.0},
        {"code": "sz399006", "name": "创业板指", "price": 2180.10, "amount_wan": 25000000.0},
    ]
    limit_up = {"total_count": 0, "limit_down_count": 0}

    result = MarketHeartbeatDetector.detect(
        indices=cur_indices,
        limit_up=limit_up,
        breadth=None,
        prev_indices=prev_indices,
        prev_date="2026-09-30",
        target_date="2026-10-04",
    )

    assert result.is_active_trading_day is False
    assert result.status == "MARKET_CLOSED"
    assert result.confirm_type == "PREV_CLOSE_MIRROR"
    assert result.confidence == 1.0
    assert result.last_active_date == "2026-09-30"
    assert any("前一交易日" in r for r in result.reasons)


@pytest_asyncio.fixture
async def test_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_daily_review_service_heartbeat_gate_confirms_closure(test_session: AsyncSession):
    """
    端到端集成测试：
    验证当物理心跳确权为休市状态（归零或前日镜像）时：
    DailyReviewService 绝不随意抛出 400 报警错误，而是优雅返回 None，确权休市无警报！
    """
    service = DailyReviewService(test_session)

    # Mock DataService 返回成交额与涨跌停全归零的休市数据
    mock_data_service = AsyncMock()
    mock_data_service.get_market_indices.return_value = AsyncMock(
        data=[{"code": "sh000001", "name": "上证指数", "price": 3300.0, "amount_wan": 0.0}],
        quality=None,
    )
    mock_data_service.get_limit_up_pool.return_value = AsyncMock(
        data={"total_count": 0, "limit_down_count": 0}
    )
    mock_data_service.get_market_breadth.return_value = AsyncMock(
        data={"up_count": 0, "down_count": 0}
    )
    mock_data_service.get_micro_cap_quote.return_value = AsyncMock(data={})
    mock_data_service.get_external_risk.return_value = AsyncMock(data={})
    mock_data_service.get_high_tier_performance.return_value = AsyncMock(data={})

    service.data_service = mock_data_service

    # 2026-09-30 是测试日期，物理心跳确权休市
    res = await service.generate_review("2026-09-30", force=False)
    assert res is None
    assert service.last_heartbeat is not None
    assert service.last_heartbeat.is_active_trading_day is False
    assert service.last_heartbeat.status == "MARKET_CLOSED"


@pytest.mark.asyncio
async def test_daily_review_service_real_error_raises_502(test_session: AsyncSession):
    """
    严禁掩盖真实错误原则测试：
    如果行情数据源发生真实网络故障 (DataQuality.FAILED)，
    系统必须严肃抛出 HTTP 502 异常，坚决不伪装成休市！
    """
    from app.data.capabilities import DataQuality, DataResult

    service = DailyReviewService(test_session)
    mock_data_service = AsyncMock()
    mock_data_service.get_index_quotes.return_value = DataResult(
        data=None,
        quality=DataQuality.FAILED,
        provider="sina",
        error_message="Connection to Sina/Tencent API timed out (504)"
    )
    mock_data_service.get_limit_up_pool.return_value = AsyncMock(data={})
    mock_data_service.get_market_breadth.return_value = AsyncMock(data={})

    service.data_service = mock_data_service

    with pytest.raises(HTTPException) as exc_info:
        await service.generate_review("2026-09-30", force=False)

    assert exc_info.value.status_code == 502
    assert "行情数据源通信异常" in exc_info.value.detail


@pytest.mark.asyncio
async def test_auction_service_heartbeat_confirms_closure_and_real_error_raises_502(test_session: AsyncSession):
    """
    集合竞价测试：
    1. 真实故障抛出 502
    2. 物理确认为休市返回 None
    """
    from app.services.auction import AuctionService
    from app.data.capabilities import DataQuality, DataResult

    service = AuctionService(test_session)

    # 1. 真实网络故障
    mock_data_service = AsyncMock()
    mock_data_service.get_index_quotes.return_value = DataResult(
        data=None,
        quality=DataQuality.FAILED,
        provider="sina",
        error_message="Gateway timeout"
    )
    service.data_service = mock_data_service

    with pytest.raises(HTTPException) as exc_info:
        await service.generate_auction_report("2026-10-04", force=False)
    assert exc_info.value.status_code == 502

    # 2. 物理数据确认为休市（点位为0或归零）
    mock_data_service.get_index_quotes.return_value = DataResult(
        data=[{"code": "sh000001", "name": "上证指数", "price": 0.0, "amount_wan": 0.0}],
        quality=DataQuality.FULL,
        provider="sina"
    )
    res = await service.generate_auction_report("2026-10-04", force=False)
    assert res is None
    assert service.last_heartbeat is not None
    assert service.last_heartbeat.is_active_trading_day is False
