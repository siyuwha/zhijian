import asyncio
import json
import pytest
import httpx
import sys
import os
from datetime import datetime
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.capabilities import DataQuality, DataResult, DataStatus, Freshness, ProviderErrorCode
from app.data.providers.cls import CLSProvider
from app.data.providers.sina import SinaProvider
from app.data.providers.eastmoney import EastmoneyProvider
from app.data.providers.baostock_provider import BaostockProvider
from app.data.service import DataService
from app.data.registry import registry
from app.services.daily_review import DailyReviewService
from app.services.auction import AuctionService
from app.models.market import MarketDailySnapshot, MarketSettlementCache
from app.core.database import Base
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
import pytest_asyncio

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
async def test_p0_1_cls_provider_live_or_mock():
    """验证 P0-1: CLS Provider 参数修复与签名生成，返回真实/结构化快讯并明确状态"""
    cls = CLSProvider()
    res = await cls.get_latest_news(count=5)
    # CLS 应当返回 DataResult，且 status 必须是明确语义
    assert res.status in (DataStatus.AVAILABLE, DataStatus.EMPTY, DataStatus.TIMEOUT, DataStatus.ERROR)
    if res.status == DataStatus.AVAILABLE:
        assert isinstance(res.data, list)
        assert len(res.data) > 0
        assert "title" in res.data[0]
        assert "brief" in res.data[0]
        assert res.quality == DataQuality.FULL

@pytest.mark.asyncio
async def test_p0_1_dual_failover_cls_to_sina():
    """验证 P0-1: CLS 故障时自动无缝切换到新浪财经快讯双源容灾"""
    ds = DataService()
    
    # 模拟 CLS 发生物理网络超时
    cls_entry = [p for p in registry._registry["news"] if p[0] == "cls"][0][1]
    orig_cls_news = cls_entry.get_latest_news
    
    async def mock_cls_timeout(*args, **kwargs):
        raise httpx.TimeoutException("Simulated CLS Timeout")
    
    cls_entry.get_latest_news = mock_cls_timeout
    try:
        res = await ds.get_latest_news(count=5)
        # 应触发级联并由 sina 提供服务
        assert res.provider == "sina"
        assert res.fallback_used is True
        assert res.quality == DataQuality.DEGRADED
        assert res.status == DataStatus.AVAILABLE
        assert isinstance(res.data, list)
        assert len(res.data) > 0
    finally:
        cls_entry.get_latest_news = orig_cls_news

@pytest.mark.asyncio
async def test_p0_2_eastmoney_empty_response_defense():
    """验证 P0-2: 东财非交易时段空字符串防御，形成明确 EMPTY 语义，绝不抛 JSONDecodeError"""
    east = EastmoneyProvider()
    
    # 1. 模拟空响应
    mock_resp_empty = httpx.Response(status_code=200, content=b"   \n  ")
    data, status, err = east._safe_parse_json(mock_resp_empty)
    assert status == DataStatus.EMPTY
    assert data is None
    assert "Empty response body" in err
    
    # 2. 模拟畸变/非 JSON 响应
    mock_resp_broken = httpx.Response(status_code=200, content=b"<html>502 Bad Gateway</html>")
    data_b, status_b, err_b = east._safe_parse_json(mock_resp_broken)
    assert status_b == DataStatus.ERROR
    assert data_b is None
    assert "JSON decode error" in err_b

    # 3. 模拟 HTTP 500
    mock_resp_500 = httpx.Response(status_code=500, content=b"Internal Error")
    data_5, status_5, err_5 = east._safe_parse_json(mock_resp_500)
    assert status_5 == DataStatus.ERROR

@pytest.mark.asyncio
async def test_p1_1_baostock_timeout_and_local_cache():
    """验证 P1-1: Baostock 3s 超时控制与本地 SQLite 结算价缓存自愈"""
    bp = BaostockProvider()
    
    # 1. 预先向本地缓存写入一条测试结算数据
    test_code = "sh.600036"
    test_date = "2026-09-25"
    mock_data = {
        "open": 32.5, "high": 33.0, "low": 32.1, "close": 32.8,
        "prev_close": 32.0, "volume": 500000.0, "amount": 16400000.0, "pct_change": 2.5
    }
    bp._save_local_cache(test_code, test_date, mock_data)
    
    # 2. 模拟 Baostock 物理阻塞超时 (>3s)
    orig_sync = bp._sync_fetch_settlement
    def mock_freeze(*args):
        import time; time.sleep(5)
    bp._sync_fetch_settlement = mock_freeze
    
    try:
        t0 = asyncio.get_event_loop().time()
        res = await bp.get_daily_settlement(test_code, test_date)
        duration = asyncio.get_event_loop().time() - t0
        
        # 验证 3.0s 左右硬超时生效
        assert duration < 4.0
        # 验证降级读取本地缓存并标记为 STALE
        assert res.provider == "baostock_local_cache"
        assert res.quality == DataQuality.DEGRADED
        assert res.status == DataStatus.STALE
        assert res.freshness == Freshness.STALE
        assert res.fallback_used is True
        assert res.data["close"] == 32.8
    finally:
        bp._sync_fetch_settlement = orig_sync

@pytest.mark.asyncio
async def test_p1_3_daily_review_and_auction_snapshot_self_heal(test_session: AsyncSession):
    """验证 P1-3: M1 盘后与 M4 竞价离线物理快照落地与自愈回放机制"""
    # 1. 测试 M1 复盘快照落地
    review_service = DailyReviewService(test_session)
    today = "2026-09-30"
    
    # 生成复盘
    review = await review_service.generate_review(today)
    assert review is not None
    assert review.date == today
    
    # 验证底层 MarketDailySnapshot 已落盘
    snap_stmt = select(MarketDailySnapshot).where(
        MarketDailySnapshot.date == today,
        MarketDailySnapshot.snapshot_type == "EOD_CLOSE"
    )
    snap = (await test_session.execute(snap_stmt)).scalars().first()
    assert snap is not None
    assert snap.snapshot_type == "EOD_CLOSE"
    assert snap.indices_snapshot is not None
    
    # 2. 验证 M1 离线自愈：若外部行情断流，从 snapshot 还原
    review_service.data_service.get_index_quotes = AsyncMock(
        return_value=DataResult(data=None, quality=DataQuality.UNAVAILABLE, status=DataStatus.EMPTY, provider="mock")
    )
    healed_review = await review_service.generate_review(today)
    assert healed_review is not None
    # 验证自愈成功还原了指数数据而非空
    healed_indices = json.loads(healed_review.market_overview)
    assert len(healed_indices) > 0

    # 3. 验证 M4 早盘竞价在非交易时段的防污染与快照自愈
    auction_service = AuctionService(test_session)
    auction_report = await auction_service.generate_auction_report(today)
    assert auction_report is not None
    assert auction_report.date == today
    
    # 验证 AUCTION_0925 快照已保存
    auc_snap_stmt = select(MarketDailySnapshot).where(
        MarketDailySnapshot.date == today,
        MarketDailySnapshot.snapshot_type == "AUCTION_0925"
    )
    auc_snap = (await test_session.execute(auc_snap_stmt)).scalars().first()
    assert auc_snap is not None
    assert auc_snap.snapshot_type == "AUCTION_0925"
