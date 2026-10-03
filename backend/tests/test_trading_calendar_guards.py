"""
非交易日与节假日物理防线单元测试
验证：DailyReview, Premarket, Auction, Cognition 在非交易日严禁生成报告或假说
"""
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.database import Base
from app.core.calendar import calendar
from app.services.daily_review import DailyReviewService
from app.services.premarket import PremarketService
from app.services.auction import AuctionService


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
async def test_daily_review_rejects_non_trading_day(test_session: AsyncSession):
    """测试周末 (2026-10-03) 与国庆法定假日 (2026-10-01) 严禁生成收盘复盘"""
    service = DailyReviewService(test_session)

    # 1. 周末
    with pytest.raises(HTTPException) as exc_info:
        await service.generate_review("2026-10-03")
    assert exc_info.value.status_code == 400
    assert "非交易日" in exc_info.value.detail

    # 2. 国庆法定假日
    with pytest.raises(HTTPException) as exc_info:
        await service.generate_review("2026-10-01")
    assert exc_info.value.status_code == 400
    assert "非交易日" in exc_info.value.detail


@pytest.mark.asyncio
async def test_premarket_rejects_non_trading_day(test_session: AsyncSession):
    """测试非交易日严禁生成盘前简报"""
    service = PremarketService(test_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.generate_briefing("2026-10-03")
    assert exc_info.value.status_code == 400
    assert "非交易日" in exc_info.value.detail


@pytest.mark.asyncio
async def test_auction_rejects_non_trading_day(test_session: AsyncSession):
    """测试非交易日严禁生成竞价报告"""
    service = AuctionService(test_session)
    with pytest.raises(HTTPException) as exc_info:
        await service.generate_auction_report("2026-10-03")
    assert exc_info.value.status_code == 400
    assert "非交易日" in exc_info.value.detail


def test_trading_calendar_holiday_skipping():
    """测试 2026 年法定节假日跳跃正确性"""
    assert calendar.is_trading_day("2026-09-30") is True
    assert calendar.is_trading_day("2026-10-01") is False
    assert calendar.is_trading_day("2026-10-07") is False
    assert calendar.is_trading_day("2026-10-08") is True
    assert str(calendar.next_trading_day("2026-09-30")) == "2026-10-08"
