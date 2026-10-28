import pytest
from typing import Dict, List, Optional
from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import engine
from app.models.simulation import SimAccount, SimTrade, SimPosition
from app.schemas.simulation import SimTradeCreate
from app.services.simulation import SimulationService


class MockDataService:
    """明确的离线假行情源，不依赖在线行情与网络"""

    def __init__(self, quotes: Optional[Dict[str, float]] = None):
        self.quotes = quotes or {}

    async def get_stock_quotes(self, symbols: List[str]):
        data = []
        for s in symbols:
            clean = s.replace("sh", "").replace("sz", "").replace("bj", "")
            price = self.quotes.get(clean, self.quotes.get(s, 10.0))
            data.append({"code": s, "price": price})
        return type("QuotesResponse", (), {"data": data})()


@pytest.fixture
async def db_session():
    """获取沙盒测试会话，并在测试前后清理模拟交易数据"""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        # 清理之前的模拟数据
        await session.execute(delete(SimTrade))
        await session.execute(delete(SimPosition))
        await session.execute(delete(SimAccount))
        await session.commit()
        yield session
        # 清理当前会话涉及的数据
        await session.execute(delete(SimTrade))
        await session.execute(delete(SimPosition))
        await session.execute(delete(SimAccount))
        await session.commit()


@pytest.mark.asyncio
async def test_stats_no_trades(db_session: AsyncSession):
    """场景1a: 无交易，无平仓，胜率及盈亏比为 null"""
    mock_data = MockDataService()
    service = SimulationService(session=db_session, data_service=mock_data)

    stats = await service.get_stats()
    assert stats.total_trades == 0
    assert stats.closed_trades == 0
    assert stats.win_trades == 0
    assert stats.loss_trades == 0
    assert stats.win_rate is None
    assert stats.closed_leg_win_rate is None
    assert stats.payoff_ratio is None
    assert stats.total_realized_pnl == 0.0


@pytest.mark.asyncio
async def test_stats_only_buy(db_session: AsyncSession):
    """场景1b: 只有买入，无平仓，胜率及盈亏比为 null"""
    mock_data = MockDataService({"000001": 10.5})
    service = SimulationService(session=db_session, data_service=mock_data)

    await service.execute_trade(
        SimTradeCreate(code="000001", direction="buy", price=10.0, quantity=100)
    )

    stats = await service.get_stats()
    assert stats.total_trades == 1
    assert stats.closed_trades == 0
    assert stats.win_trades == 0
    assert stats.loss_trades == 0
    assert stats.win_rate is None
    assert stats.closed_leg_win_rate is None
    assert stats.payoff_ratio is None
    assert stats.total_realized_pnl == 0.0


@pytest.mark.asyncio
async def test_stats_single_loss(db_session: AsyncSession):
    """场景2: 单笔亏损：10 元买 100 股，9 元卖 100 股，已实现 -100 元，胜率 0%，亏损 1 笔，盈亏比 null"""
    mock_data = MockDataService({"000001": 9.0})
    service = SimulationService(session=db_session, data_service=mock_data)

    await service.execute_trade(
        SimTradeCreate(code="000001", direction="buy", price=10.0, quantity=100)
    )
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="sell", price=9.0, quantity=100)
    )

    stats = await service.get_stats()
    assert stats.total_trades == 2
    assert stats.closed_trades == 1
    assert stats.win_trades == 0
    assert stats.loss_trades == 1
    assert stats.win_rate == 0.0
    assert stats.closed_leg_win_rate == 0.0
    assert stats.payoff_ratio is None
    assert stats.total_realized_pnl == -100.0


@pytest.mark.asyncio
async def test_stats_single_win(db_session: AsyncSession):
    """场景3: 单笔盈利：10 元买 100 股，12 元卖 100 股，盈利 1 笔、胜率 100%，盈亏比仍 null"""
    mock_data = MockDataService({"000001": 12.0})
    service = SimulationService(session=db_session, data_service=mock_data)

    await service.execute_trade(
        SimTradeCreate(code="000001", direction="buy", price=10.0, quantity=100)
    )
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="sell", price=12.0, quantity=100)
    )

    stats = await service.get_stats()
    assert stats.total_trades == 2
    assert stats.closed_trades == 1
    assert stats.win_trades == 1
    assert stats.loss_trades == 0
    assert stats.win_rate == 100.0
    assert stats.closed_leg_win_rate == 100.0
    assert stats.payoff_ratio is None
    assert stats.total_realized_pnl == 200.0


@pytest.mark.asyncio
async def test_stats_breakeven(db_session: AsyncSession):
    """场景4: 保本卖出：平仓 1 笔、盈利/亏损均 0、胜率 0%，盈亏比 null"""
    mock_data = MockDataService({"000001": 10.0})
    service = SimulationService(session=db_session, data_service=mock_data)

    await service.execute_trade(
        SimTradeCreate(code="000001", direction="buy", price=10.0, quantity=100)
    )
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="sell", price=10.0, quantity=100)
    )

    stats = await service.get_stats()
    assert stats.total_trades == 2
    assert stats.closed_trades == 1
    assert stats.win_trades == 0
    assert stats.loss_trades == 0
    assert stats.win_rate == 0.0
    assert stats.closed_leg_win_rate == 0.0
    assert stats.payoff_ratio is None
    assert stats.total_realized_pnl == 0.0


@pytest.mark.asyncio
async def test_stats_win_and_loss(db_session: AsyncSession):
    """场景5: 同时有盈利、亏损：按实际各笔盈亏计算胜率及平均盈亏比"""
    mock_data = MockDataService({"000001": 10.0, "000002": 10.0})
    service = SimulationService(session=db_session, data_service=mock_data)

    # 标的1: 买 100@10.0，卖 100@13.0 -> 盈利 +300.0
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="buy", price=10.0, quantity=100)
    )
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="sell", price=13.0, quantity=100)
    )

    # 标的2: 买 100@10.0，卖 100@9.0 -> 亏损 -100.0
    await service.execute_trade(
        SimTradeCreate(code="000002", direction="buy", price=10.0, quantity=100)
    )
    await service.execute_trade(
        SimTradeCreate(code="000002", direction="sell", price=9.0, quantity=100)
    )

    stats = await service.get_stats()
    assert stats.total_trades == 4
    assert stats.closed_trades == 2
    assert stats.win_trades == 1
    assert stats.loss_trades == 1
    assert stats.win_rate == 50.0
    assert stats.closed_leg_win_rate == 50.0
    # avg_win = 300.0, avg_loss = 100.0 -> payoff_ratio = 3.0
    assert stats.payoff_ratio == 3.0
    assert stats.total_realized_pnl == 200.0


@pytest.mark.asyncio
async def test_stats_rebuys_and_partial_sells(db_session: AsyncSession):
    """场景6: 加仓、部分卖出、卖清重买：成本和已实现盈亏正确，原有成本不串入新仓"""
    mock_data = MockDataService({"000001": 35.0})
    service = SimulationService(session=db_session, data_service=mock_data)

    # 1. 买入 100 股 @ 10 元 (成本 10.0)
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="buy", price=10.0, quantity=100)
    )
    # 2. 加仓 100 股 @ 20 元 (总成本 3000, 均价 15.0)
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="buy", price=20.0, quantity=100)
    )
    # 3. 部分卖出 50 股 @ 18 元 (已实现 (18-15)*50 = +150.0, 余 150 股，均价仍 15.0)
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="sell", price=18.0, quantity=50)
    )
    # 4. 卖清剩余 150 股 @ 12 元 (已实现 (12-15)*150 = -450.0, 余 0 股)
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="sell", price=12.0, quantity=150)
    )
    # 5. 卖清后重新建仓买入 100 股 @ 30 元 (新成本 30.0，不串入历史 15.0)
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="buy", price=30.0, quantity=100)
    )
    # 6. 卖出 100 股 @ 35 元 (已实现 (35-30)*100 = +500.0)
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="sell", price=35.0, quantity=100)
    )

    stats = await service.get_stats()
    assert stats.total_trades == 6
    assert stats.closed_trades == 3
    assert stats.win_trades == 2
    assert stats.loss_trades == 1
    # 胜率: 2 / 3 = 66.67%
    assert stats.win_rate == 66.67
    assert stats.closed_leg_win_rate == 66.67
    # avg_win = (150 + 500) / 2 = 325.0, avg_loss = 450.0 -> payoff_ratio = round(325/450, 2) = 0.72
    assert stats.payoff_ratio == 0.72
    # total_realized_pnl = 150 - 450 + 500 = 200.0
    assert stats.total_realized_pnl == 200.0


@pytest.mark.asyncio
async def test_stats_over_200_trades(db_session: AsyncSession):
    """场景7: 超过 200 条流水：早期买入成本和早期平仓计入全量统计，不截断为 200 条"""
    mock_data = MockDataService({"600000": 10.0})
    service = SimulationService(session=db_session, data_service=mock_data)

    # 循环执行 120 轮买卖，共 240 笔流水（远超 200 条）
    # 前 60 轮: 买 100@10.0, 卖 100@11.0 -> 盈利 +100.0 (共 60 笔盈利)
    # 后 60 轮: 买 100@10.0, 卖 100@9.0 -> 亏损 -100.0 (共 60 笔亏损)
    for _ in range(60):
        await service.execute_trade(
            SimTradeCreate(code="600000", direction="buy", price=10.0, quantity=100)
        )
        await service.execute_trade(
            SimTradeCreate(code="600000", direction="sell", price=11.0, quantity=100)
        )

    for _ in range(60):
        await service.execute_trade(
            SimTradeCreate(code="600000", direction="buy", price=10.0, quantity=100)
        )
        await service.execute_trade(
            SimTradeCreate(code="600000", direction="sell", price=9.0, quantity=100)
        )

    stats = await service.get_stats()
    assert stats.total_trades == 240
    assert stats.closed_trades == 120
    assert stats.win_trades == 60
    assert stats.loss_trades == 60
    assert stats.win_rate == 50.0
    assert stats.closed_leg_win_rate == 50.0
    assert stats.payoff_ratio == 1.0
    assert stats.total_realized_pnl == 0.0


@pytest.mark.asyncio
async def test_stats_multi_account_isolation(db_session: AsyncSession):
    """场景8: 多账户隔离：其他账户的成交不进入当前默认账户统计（直接通过夹具插入独立账户流水验证）"""
    mock_data = MockDataService()
    service = SimulationService(session=db_session, data_service=mock_data)

    # 默认账户执行正常交易: 买 100@10.0，卖 100@15.0 -> 盈利 +500.0
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="buy", price=10.0, quantity=100)
    )
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="sell", price=15.0, quantity=100)
    )

    # 创建独立其他账户 B 并在数据库中为其插入孤立流水
    account_b = SimAccount(
        name="测试独立其他账户B",
        initial_capital=500000.0,
        current_capital=500000.0,
        total_pnl=0.0,
        is_active=0
    )
    db_session.add(account_b)
    await db_session.commit()
    await db_session.refresh(account_b)

    trade_b1 = SimTrade(
        account_id=account_b.id,
        code="000002",
        direction="buy",
        price=20.0,
        quantity=200,
        trade_time="2026-10-28 10:00:00"
    )
    trade_b2 = SimTrade(
        account_id=account_b.id,
        code="000002",
        direction="sell",
        price=10.0,
        quantity=200,
        trade_time="2026-10-28 10:30:00"
    )
    db_session.add_all([trade_b1, trade_b2])
    await db_session.commit()

    # 校验默认账户的统计：仅包含自身 2 笔流水，不串入账户 B 的交易
    stats = await service.get_stats()
    assert stats.total_trades == 2
    assert stats.closed_trades == 1
    assert stats.win_trades == 1
    assert stats.loss_trades == 0
    assert stats.win_rate == 100.0
    assert stats.total_realized_pnl == 500.0


@pytest.mark.asyncio
async def test_stats_orphan_sell_raises_409(db_session: AsyncSession):
    """场景9: 无成本卖出异常流水：返回 HTTP 409 拒绝统计，注明异常流水 ID 和原因"""
    mock_data = MockDataService()
    service = SimulationService(session=db_session, data_service=mock_data)
    account = await service.get_or_create_default_account()

    # 直接向数据库插入一条没有先验买入成本的异常卖出流水
    orphan_trade = SimTrade(
        account_id=account.id,
        code="999999",
        name="无买入标的",
        direction="sell",
        price=10.0,
        quantity=100,
        trade_time="2026-10-28 10:00:00",
        decision_summary="测试孤儿流水"
    )
    db_session.add(orphan_trade)
    await db_session.commit()
    await db_session.refresh(orphan_trade)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_stats()

    assert exc_info.value.status_code == 409
    assert str(orphan_trade.id) in exc_info.value.detail
    assert "无成本卖出" in exc_info.value.detail


@pytest.mark.asyncio
async def test_stats_oversell_raises_409(db_session: AsyncSession):
    """场景10: 超卖异常流水：买 100 股后历史流水出现卖出 200 股，返回 HTTP 409 拒绝统计，不截断卖出数量伪造盈利"""
    mock_data = MockDataService()
    service = SimulationService(session=db_session, data_service=mock_data)
    account = await service.get_or_create_default_account()

    # 正常买入 100 股
    await service.execute_trade(
        SimTradeCreate(code="002724", direction="buy", price=10.0, quantity=100)
    )

    # 模拟历史流水中存在一笔未支持的超卖流水 (卖出 200 股)
    oversell_trade = SimTrade(
        account_id=account.id,
        code="002724",
        name="海洋王",
        direction="sell",
        price=11.0,
        quantity=200,
        trade_time="2026-10-28 11:00:00",
        decision_summary="超卖流水测试"
    )
    db_session.add(oversell_trade)
    await db_session.commit()
    await db_session.refresh(oversell_trade)

    with pytest.raises(HTTPException) as exc_info:
        await service.get_stats()

    assert exc_info.value.status_code == 409
    assert str(oversell_trade.id) in exc_info.value.detail
    assert "超卖" in exc_info.value.detail


@pytest.mark.asyncio
async def test_stats_partial_sell_then_add_position_three_decimal_rounding(db_session: AsyncSession):
    """场景11: 部分卖出再加仓（三位均价舍入），断言统计已实现盈亏等于 execute_trade 记入的 account.total_pnl"""
    mock_data = MockDataService({"000001": 13.0})
    service = SimulationService(session=db_session, data_service=mock_data)

    # 1. 建仓买入 1000 股 @ 10.0 元
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="buy", price=10.0, quantity=1000)
    )
    # 2. 部分卖出 300 股 @ 12.0 元 (盈亏 (12-10)*300 = +600.0, 余 700 股，均价 10.0)
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="sell", price=12.0, quantity=300)
    )
    # 3. 加仓 500 股 @ 11.23 元
    # 成本计算: total_cost = round(700 * 10.0 + 500 * 11.23, 2) = round(7000 + 5615, 2) = 12615.0
    # 新均价 (Python银行家舍入到三位小数): 12615.0 / 1200 = 10.5125 -> avg_cost = round(10.5125, 3) = 10.512
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="buy", price=11.23, quantity=500)
    )
    # 4. 卖出 400 股 @ 13.0 元
    # 平仓盈亏: realized_pnl = round((13.0 - 10.512) * 400, 2) = round(2.488 * 400, 2) = 995.2
    await service.execute_trade(
        SimTradeCreate(code="000001", direction="sell", price=13.0, quantity=400)
    )

    account = await service.get_or_create_default_account()
    stats = await service.get_stats()

    # 验证已实现盈亏与 account.total_pnl 完全自洽
    assert stats.total_realized_pnl == round(account.total_pnl, 2)
    assert stats.total_realized_pnl == round(600.0 + 995.2, 2)
    assert stats.total_trades == 4
    assert stats.closed_trades == 2
    assert stats.win_trades == 2
    assert stats.win_rate == 100.0


@pytest.mark.asyncio
async def test_stats_backdated_trade_time_respects_id_sequence(db_session: AsyncSession):
    """场景12: 补录时间早于买入但 id 顺序合法的流水，按 id 升序重建成本，断言统计已实现盈亏等于 account.total_pnl"""
    mock_data = MockDataService({"600519": 105.0})
    service = SimulationService(session=db_session, data_service=mock_data)

    # 流水 1: 买入，记录 trade_time 为 2026-10-28 10:00:00
    await service.execute_trade(
        SimTradeCreate(
            code="600519",
            direction="buy",
            price=100.0,
            quantity=100,
            trade_time="2026-10-28 10:00:00"
        )
    )
    # 流水 2: 卖出，补录时间填为 2026-10-27 09:30:00 (早于买入，但 id 顺序合法为 2)
    await service.execute_trade(
        SimTradeCreate(
            code="600519",
            direction="sell",
            price=105.0,
            quantity=100,
            trade_time="2026-10-27 09:30:00"
        )
    )

    account = await service.get_or_create_default_account()
    stats = await service.get_stats()

    # 按照实际流水 id 升序重建，买入先于卖出计算成本，已实现盈亏自洽
    assert stats.total_realized_pnl == round(account.total_pnl, 2)
    assert stats.total_realized_pnl == 500.0
    assert stats.closed_trades == 1
    assert stats.win_trades == 1
    assert stats.win_rate == 100.0
