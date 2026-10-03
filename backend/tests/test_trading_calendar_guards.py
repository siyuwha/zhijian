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
    """测试 2026 年法定节假日跳跃正确性与中文星期格式化"""
    assert calendar.is_trading_day("2026-09-30") is True
    assert calendar.is_trading_day("2026-10-01") is False
    assert calendar.is_trading_day("2026-10-07") is False
    assert calendar.is_trading_day("2026-10-08") is True
    assert str(calendar.next_trading_day("2026-09-30")) == "2026-10-08"
    assert str(calendar.prev_trading_day("2026-10-08")) == "2026-09-30"

    # 星期几格式化验证
    assert calendar.get_weekday_name("2026-09-30") == "周三"
    assert calendar.get_weekday_name("2026-09-28") == "周一"
    assert calendar.get_weekday_name("2026-09-27") == "周日"
    assert calendar.format_date_with_weekday("2026-09-30") == "2026-09-30 (周三)"
    assert calendar.format_date_with_weekday("2026-10-01") == "2026-10-01 (周四·国庆休市)"
    assert calendar.format_date_with_weekday("2026-09-26") == "2026-09-26 (周六·周末休市)"


@pytest.mark.asyncio
async def test_monday_comparison_skips_weekend_contamination(test_session: AsyncSession):
    """
    核心防扰动测试：
    验证周一复盘与盘前简报在追溯前一交易日基准时，即使数据库中存在脏的周日复盘记录，
    系统也必须通过交易日历刚性跳过周末，严格与周五（或上一个真实交易日）对齐！
    """
    import json
    from app.models.report import DailyReview

    # 1. 注入有效周五复盘 (2026-09-18，成交额 15000 亿)
    friday_review = DailyReview(
        date="2026-09-18",
        market_overview=json.dumps([{"code": "sh000001", "name": "上证指数", "amount_wan": 150000000.0}]),
        limit_up_analysis=json.dumps({"total_count": 58, "max_height": 5}),
        report_content=json.dumps({
            "market_state": {
                "dimensions": {
                    "D6": {"metrics": {"total_amount": 15000.0}},
                    "D3": {
                        "sub_domains": {
                            "tail_extremes": {
                                "metrics": {"limit_up_count": 58}
                            }
                        }
                    }
                }
            }
        }),
        data_quality="FULL",
    )
    # 2. 注入被污染的错误周日复盘 (2026-09-20，成交额 0 亿)
    sunday_review = DailyReview(
        date="2026-09-20",
        market_overview=json.dumps([{"code": "sh000001", "name": "上证指数", "amount_wan": 0.0}]),
        limit_up_analysis=json.dumps({"total_count": 0, "max_height": 0}),
        report_content=json.dumps({
            "market_state": {
                "dimensions": {
                    "D6": {"metrics": {"total_amount": 0.0}},
                    "D3": {
                        "sub_domains": {
                            "tail_extremes": {
                                "metrics": {"limit_up_count": 0}
                            }
                        }
                    }
                }
            }
        }),
        data_quality="INVALID",
    )
    test_session.add(friday_review)
    test_session.add(sunday_review)
    await test_session.commit()

    # 3. 周一 (2026-09-21) 生成盘前简报，追溯昨日状态向量
    pre_service = PremarketService(test_session)
    # force=True 允许测试环境中执行
    briefing = await pre_service.generate_briefing("2026-09-21", force=True)

    # 断言：盘前简报继承的必须是周五 (2026-09-18)，坚决杜绝周日 (2026-09-20) 污染
    prev_summary = json.loads(briefing.yesterday_review_summary)
    assert prev_summary["date"] == "2026-09-18", f"预期对齐周五 2026-09-18，但实际对齐了 {prev_summary['date']}"
    assert prev_summary["total_amount"] == 15000.0
    assert prev_summary["sub_b_extremes"]["limit_up_count"] == 58

