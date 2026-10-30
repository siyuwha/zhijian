import pytest
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, date
from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import engine, async_session
from app.models.simulation import SimAccount, SimTrade, SimPosition
from app.schemas.simulation import SimTradeCreate
from app.services.simulation import SimulationService, is_t0_instrument
from app.services.autonomous_executor import AutonomousJobEngine
from app.core.calendar import calendar, CalendarCoverageError
from app.data.capabilities import DataQuality, Freshness


class MockDataService:
    """离线假行情服务"""
    def __init__(self, quotes: Optional[Dict[str, Dict]] = None, quality=DataQuality.FULL, freshness=Freshness.REALTIME):
        self.quotes = quotes or {}
        self.quality = quality
        self.freshness = freshness
        self.current_date: Optional[str] = None

    async def get_stock_quotes(self, symbols: List[str]):
        data = []
        now_dt = datetime.now()
        effective_date = self.current_date or now_dt.strftime("%Y-%m-%d")
        effective_time = f"{effective_date} 14:30:00"
        for s in symbols:
            clean = s.replace("sh", "").replace("sz", "").replace("bj", "")
            q = self.quotes.get(clean, self.quotes.get(s, {"price": 10.0, "name": f"股票_{clean}"}))
            price = q.get("price", 10.0)
            name = q.get("name", f"股票_{clean}")
            open_p = q.get("open", price)
            open_pct = q.get("open_pct", 0.0)
            data.append({
                "code": s,
                "symbol": s,
                "name": name,
                "price": price,
                "open": open_p,
                "open_pct": open_pct,
                "low": price * 0.98,
                "limit_up": price * 1.10,
                "date": q["date"] if "date" in q else effective_date,
                "time": q["time"] if "time" in q else effective_time
            })
        return type("QuotesResponse", (), {
            "data": data,
            "quality": self.quality,
            "freshness": self.freshness,
            "error_message": None,
            "quality_log_success": True
        })()


@pytest.fixture
async def db_session():
    """沙盒测试会话，测试前后清理模拟交易相关数据"""
    async with AsyncSession(engine, expire_on_commit=False) as session:
        await session.execute(delete(SimTrade))
        await session.execute(delete(SimPosition))
        await session.execute(delete(SimAccount))
        await session.commit()
        yield session
        await session.execute(delete(SimTrade))
        await session.execute(delete(SimPosition))
        await session.execute(delete(SimAccount))
        await session.commit()


# =====================================================================
# 场景 1: 当日首次买入 1000 股，当日手动要求卖出 ➔ 成交为 0，资金/持仓/流水不变
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_1_same_day_buy_and_manual_sell_rejected(db_session: AsyncSession):
    mock_data = MockDataService({"000001": {"price": 10.0, "name": "平安银行"}})
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)

    # 1. 2026-10-27 (周二) 买入 1000 股 @ 10.0 元
    buy_res = await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="buy",
            price=10.0,
            quantity=1000,
            trade_time="2026-10-27 10:00:00"
        ),
        allow_future=True
    )
    assert buy_res.id is not None
    assert buy_res.quantity == 1000

    # 检查当日 14:00 可卖持仓
    account = await service.get_or_create_default_account()
    avail_qty = await service.get_available_quantity(account.id, "000001", as_of_time="2026-10-27 14:00:00")
    assert avail_qty == 0

    capital_before = account.current_capital

    # 2. 当日 14:30 尝试手动卖出 1000 股 ➔ 必须抛出 HTTPException 400，并说明 T+1 原因
    with pytest.raises(HTTPException) as exc_info:
        await service.execute_trade(
            SimTradeCreate(
                code="000001",
                name="平安银行",
                direction="sell",
                price=11.0,
                quantity=1000,
                trade_time="2026-10-27 14:30:00"
            ),
            allow_future=True
        )
    assert exc_info.value.status_code == 400
    assert "A股T+1规则限制" in exc_info.value.detail
    assert "今日买入尚未转为可卖仓" in exc_info.value.detail

    # 验证资金、持仓、流水完全未变（原子性保证）
    positions = await service.get_positions(as_of_time="2026-10-27 14:30:00")
    assert len(positions) == 1
    assert positions[0].quantity == 1000
    assert positions[0].available_quantity == 0

    records = await service.get_records()
    assert len(records) == 1
    assert records[0].direction == "buy"

    refreshed_acc = await service.get_or_create_default_account()
    assert refreshed_acc.current_capital == capital_before


# =====================================================================
# 场景 2: 昨日持仓 600 股，今日买入 400 股，手动要求卖 1000 股 ➔ 拒绝，不产生部分写入
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_2_mixed_holding_manual_sell_over_available_rejected(db_session: AsyncSession):
    mock_data = MockDataService({"000001": {"price": 10.0, "name": "平安银行"}})
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)

    # 1. 2026-10-26 (周一) 买入 600 股
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="buy",
            price=10.0,
            quantity=600,
            trade_time="2026-10-26 10:00:00"
        ),
        allow_future=True
    )

    # 2. 2026-10-27 (周二) 买入 400 股
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="buy",
            price=10.0,
            quantity=400,
            trade_time="2026-10-27 10:00:00"
        ),
        allow_future=True
    )

    account = await service.get_or_create_default_account()
    avail_qty = await service.get_available_quantity(account.id, "000001", as_of_time="2026-10-27 14:00:00")
    assert avail_qty == 600

    # 3. 2026-10-27 手动尝试卖出 1000 股 (超出可卖 600 股)
    with pytest.raises(HTTPException) as exc_info:
        await service.execute_trade(
            SimTradeCreate(
                code="000001",
                name="平安银行",
                direction="sell",
                price=11.0,
                quantity=1000,
                trade_time="2026-10-27 14:30:00"
            ),
            allow_future=True
        )
    assert exc_info.value.status_code == 400
    assert "卖出数量超出可卖仓" in exc_info.value.detail
    assert "可卖 600 股" in exc_info.value.detail
    assert "当日买入冻结 400 股" in exc_info.value.detail

    # 验证不产生部分写入，持仓仍为 1000 股
    positions = await service.get_positions(as_of_time="2026-10-27 14:30:00")
    assert len(positions) == 1
    assert positions[0].quantity == 1000
    assert positions[0].available_quantity == 600

    records = await service.get_records()
    assert len(records) == 2  # 只有两次买入流水，没有卖出流水


# =====================================================================
# 场景 3: 同一混合持仓触发自动风控全平 ➔ 仅平仓 600 股，结构化区分 T+1 部分成交
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_3_mixed_holding_auto_risk_guard_partial_sell(db_session: AsyncSession):
    # 模拟现价下跌触及 -6% 止损 (买入成本 10.0，现价 9.4)
    mock_data = MockDataService({"000001": {"price": 9.4, "name": "平安银行"}})
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)

    # 1. 2026-10-26 买入 600 股
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="buy",
            price=10.0,
            quantity=600,
            trade_time="2026-10-26 10:00:00"
        ),
        allow_future=True
    )

    # 2. 2026-10-27 买入 400 股
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="buy",
            price=10.0,
            quantity=400,
            trade_time="2026-10-27 10:00:00"
        ),
        allow_future=True
    )

    # 3. 运行自动风控巡检 (目标日期 2026-10-27)
    engine_runner = AutonomousJobEngine(session=db_session, simulation_service=service, data_service=mock_data)
    events = await engine_runner.run_intraday_risk_guard(target_date="2026-10-27")

    assert len(events) == 1
    e = events[0]
    assert e["code"] == "000001"
    assert e["action"] == "PARTIAL_SELL"
    assert e["status"] == "PARTIAL_LIQUIDATED"
    assert e["quantity"] == 600  # 仅平仓可卖的 600 股
    assert e["remaining_quantity"] == 400  # 明确剩余 400 股保留
    assert "T+1部分平仓: 可卖 600 股" in e["reason"]

    # 验证持仓记录剩余 400 股
    positions = await service.get_positions(as_of_time="2026-10-27 15:00:00")
    assert len(positions) == 1
    assert positions[0].quantity == 400
    assert positions[0].available_quantity == 0  # 剩余 400 为今日买入，不可卖

    # 核实流水
    records = await service.get_records()
    assert len(records) == 3
    sells = [r for r in records if r.direction == "sell"]
    assert len(sells) == 1
    assert sells[0].quantity == 600


# =====================================================================
# 场景 4: 昨日可卖 600 股，先卖 200 股，再卖 400 股 ➔ 均成功，第 3 次被拒绝
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_4_sequential_sells_exhaustion(db_session: AsyncSession):
    mock_data = MockDataService({"000001": {"price": 10.0, "name": "平安银行"}})
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)

    # 1. 2026-10-26 买入 600 股
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="buy",
            price=10.0,
            quantity=600,
            trade_time="2026-10-26 10:00:00"
        ),
        allow_future=True
    )

    # 2. 2026-10-27 卖出 200 股 ➔ 成功
    t1 = await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="sell",
            price=11.0,
            quantity=200,
            trade_time="2026-10-27 10:30:00"
        ),
        allow_future=True
    )
    assert t1.quantity == 200

    # 3. 2026-10-27 卖出 400 股 ➔ 成功
    t2 = await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="sell",
            price=11.2,
            quantity=400,
            trade_time="2026-10-27 11:00:00"
        ),
        allow_future=True
    )
    assert t2.quantity == 400

    # 4. 2026-10-27 再次卖出 100 股 ➔ 拒绝
    with pytest.raises(HTTPException) as exc_info:
        await service.execute_trade(
            SimTradeCreate(
                code="000001",
                name="平安银行",
                direction="sell",
                price=11.5,
                quantity=100,
                trade_time="2026-10-27 14:00:00"
            ),
            allow_future=True
        )
    assert exc_info.value.status_code == 400
    assert "无持仓" in exc_info.value.detail or "不足" in exc_info.value.detail


# =====================================================================
# 场景 5: 跨会话/多连接并发争用同一可卖仓 ➔ 累计成交不超过可卖数量，无负持仓
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_5_concurrent_sell_multi_session_protection():
    # 使用两个独立会话模拟跨连接/多实例并发
    async with async_session() as s1, async_session() as s2:
        await s1.execute(delete(SimTrade))
        await s1.execute(delete(SimPosition))
        await s1.execute(delete(SimAccount))
        await s1.commit()

        mock_data = MockDataService({"000001": {"price": 10.0, "name": "平安银行"}})
        service1 = SimulationService(session=s1, data_service=mock_data, enforce_t1=True)
        service2 = SimulationService(session=s2, data_service=mock_data, enforce_t1=True)

        # 1. 会话 1 于 2026-10-26 买入 500 股
        await service1.execute_trade(
            SimTradeCreate(
                code="000001",
                name="平安银行",
                direction="buy",
                price=10.0,
                quantity=500,
                trade_time="2026-10-26 10:00:00"
            ),
            allow_future=True
        )

        # 2. 会话 1 与 会话 2 同时尝试在 2026-10-27 卖出 400 股（总计 800 股 > 500 股）
        req1 = SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="sell",
            price=10.5,
            quantity=400,
            trade_time="2026-10-27 10:00:00"
        )
        req2 = SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="sell",
            price=10.5,
            quantity=400,
            trade_time="2026-10-27 10:00:00"
        )

        results = await asyncio.gather(
            service1.execute_trade(req1, allow_future=True),
            service2.execute_trade(req2, allow_future=True),
            return_exceptions=True
        )

        # 预期：严格一个成功，一个抛出 HTTPException 400 失败
        successes = [r for r in results if not isinstance(r, Exception)]
        failures = [r for r in results if isinstance(r, HTTPException)]

        assert len(successes) == 1
        assert len(failures) == 1
        assert failures[0].status_code == 400

        # 验证最终持仓恰好为 100 股，绝无负持仓
        positions = await service1.get_positions(as_of_time="2026-10-27 10:01:00")
        assert len(positions) == 1
        assert positions[0].quantity == 100
        assert positions[0].available_quantity == 100

        # 清理
        await s1.execute(delete(SimTrade))
        await s1.execute(delete(SimPosition))
        await s1.execute(delete(SimAccount))
        await s1.commit()


# =====================================================================
# 场景 6: 周五买入、周末及法定节假日休市核验、未覆盖年份拒绝
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_6_weekend_holiday_and_unsupported_year(db_session: AsyncSession):
    mock_data = MockDataService({"000001": {"price": 10.0, "name": "平安银行"}})
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)

    # 1. 2026-09-30 (国庆前周三) 买入 800 股
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="buy",
            price=10.0,
            quantity=800,
            trade_time="2026-09-30 10:00:00"
        ),
        allow_future=True
    )

    account = await service.get_or_create_default_account()

    # 2. 国庆长假期间 (2026-10-01 ~ 2026-10-07)：全部休市，可卖量恒为 0
    for day in range(1, 8):
        dt_str = f"2026-10-{day:02d} 10:00:00"
        avail = await service.get_available_quantity(account.id, "000001", as_of_time=dt_str)
        assert avail == 0, f"国庆节休市日 {dt_str} 可卖数量应为 0"

    # 3. 节后首个交易日 2026-10-08 (周四)：全量 800 股成熟转为可卖
    avail_after = await service.get_available_quantity(account.id, "000001", as_of_time="2026-10-08 09:30:00")
    assert avail_after == 800

    # 4. 未覆盖年份防线校验：尝试对 2027 年（超出当前 2024-2026 覆盖范围）核算可卖
    with pytest.raises(HTTPException) as exc_info:
        await service.get_available_quantity(account.id, "000001", as_of_time="2027-01-05 10:00:00")
    assert exc_info.value.status_code == 500
    assert "交易日历不可用" in exc_info.value.detail or "未覆盖年份" in exc_info.value.detail


# =====================================================================
# 场景 7: 今日买入触发尾盘持仓到期信号与止损 ➔ 结构化记录 TRIGGERED_T1_PROTECTED
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_7_holding_period_and_t1_protection_structure(db_session: AsyncSession):
    # 模拟现价下跌触发 -5% 止损
    mock_data = MockDataService({"000001": {"price": 9.4, "name": "平安银行"}})
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)

    # 1. 当日 2026-10-28 10:00 买入 1000 股
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="buy",
            price=10.0,
            quantity=1000,
            trade_time="2026-10-28 10:00:00"
        ),
        allow_future=True
    )

    # 2. 模拟 14:55 运行风控巡检 (target_date="2026-10-28")
    engine_runner = AutonomousJobEngine(session=db_session, simulation_service=service, data_service=mock_data)
    events = await engine_runner.run_intraday_risk_guard(target_date="2026-10-28")

    # 当日买入持仓周期未成熟（持股 0 个交易日），但触及 -5% 止损；
    # 因 A 股 T+1 限制可卖为 0，风控必须结构化返回 TRIGGERED_T1_PROTECTED，动作保留持仓 HOLD！
    assert len(events) == 1
    e = events[0]
    assert e["code"] == "000001"
    assert e["action"] == "HOLD"
    assert e["status"] == "TRIGGERED_T1_PROTECTED"
    assert e["quantity"] == 0
    assert e["remaining_quantity"] == 1000
    assert "波普尔硬止损" in e["trigger_reason"]

    # 验证持仓仍为 1000 股未强平
    positions = await service.get_positions(as_of_time="2026-10-28 15:00:00")
    assert len(positions) == 1
    assert positions[0].quantity == 1000


# =====================================================================
# 场景 8: T+0 品种严格白名单号段与可信名称校验 vs 未知代码 T+1 防御
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_8_t0_strict_whitelist_defense(db_session: AsyncSession):
    # 严格白名单与可信名称校验
    assert is_t0_instrument("113050", name="南银转债") is True   # 上交所可转债
    assert is_t0_instrument("128012", name="交行转债") is True   # 深交所可转债
    assert is_t0_instrument("123001", name="创业转债") is True   # 创业板可转债
    assert is_t0_instrument("118001", name="科创EB") is True     # 科创板交换债
    # 虚假/非转债标的检验：即使号段匹配，若名称非可转债，坚决不猜测为 T+0！
    assert is_t0_instrument("113999", name="测试假代码") is False
    assert is_t0_instrument("113999", name=None) is False
    assert is_t0_instrument("119999", name="未知代码") is False
    assert is_t0_instrument("120001", name="非转债号段") is False
    assert is_t0_instrument("000001", name="平安银行") is False
    assert is_t0_instrument("600519", name="贵州茅台") is False

    mock_data = MockDataService({
        "113050": {"price": 120.0, "name": "南银转债"},
        "113999": {"price": 100.0, "name": "测试假股票"},
        "119999": {"price": 100.0, "name": "未知代码"}
    })
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)

    # 1. 当日买入合规可转债 113050 (100 张)
    await service.execute_trade(
        SimTradeCreate(
            code="113050",
            name="南银转债",
            direction="buy",
            price=120.0,
            quantity=100,
            trade_time="2026-10-28 10:00:00"
        ),
        allow_future=True
    )
    # 可转债当日可卖且允许当日卖出
    account = await service.get_or_create_default_account()
    avail_cb = await service.get_available_quantity(account.id, "113050", as_of_time="2026-10-28 11:00:00")
    assert avail_cb == 100

    cb_sell = await service.execute_trade(
        SimTradeCreate(
            code="113050",
            name="南银转债",
            direction="sell",
            price=125.0,
            quantity=100,
            trade_time="2026-10-28 14:00:00"
        ),
        allow_future=True
    )
    assert cb_sell.quantity == 100

    # 2. 当日买入假可转债号段 113999 (名称为非转债)
    await service.execute_trade(
        SimTradeCreate(
            code="113999",
            name="测试假股票",
            direction="buy",
            price=10.0,
            quantity=100,
            trade_time="2026-10-28 10:00:00"
        ),
        allow_future=True
    )
    # 名称不可信，严格回落至 T+1 约束，当日不可卖！
    avail_fake = await service.get_available_quantity(account.id, "113999", as_of_time="2026-10-28 11:00:00")
    assert avail_fake == 0

    with pytest.raises(HTTPException) as exc_info:
        await service.execute_trade(
            SimTradeCreate(
                code="113999",
                name="测试假股票",
                direction="sell",
                price=11.0,
                quantity=100,
                trade_time="2026-10-28 14:00:00"
            ),
            allow_future=True
        )
    assert exc_info.value.status_code == 400
    assert "A股T+1规则限制" in exc_info.value.detail

    # 3. 客户端伪造名称攻击防御：客户端传入 code="113999", name="假转债" 试图冒充可转债
    # 服务端 verify_t0_instrument 向权威数据源核验，由于真实官方名称为"测试假股票"，坚决拒绝认定为 T+0！
    await service.execute_trade(
        SimTradeCreate(
            code="113999",
            name="假转债",  # 客户端伪造名称！
            direction="buy",
            price=10.0,
            quantity=100,
            trade_time="2026-10-28 10:00:00"
        ),
        allow_future=True
    )
    # 当日卖出必须被 A 股 T+1 刚性拦截，绝不采信客户端传入的伪造名称！
    with pytest.raises(HTTPException) as exc_info:
        await service.execute_trade(
            SimTradeCreate(
                code="113999",
                name="假转债",
                direction="sell",
                price=11.0,
                quantity=100,
                trade_time="2026-10-28 14:00:00"
            ),
            allow_future=True
        )
    assert exc_info.value.status_code == 400
    assert "A股T+1规则限制" in exc_info.value.detail


# =====================================================================
# 场景 9: 公共接口与未来时间防线校验 (P0 漏洞闭环)
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_9_future_time_rejection(db_session: AsyncSession):
    mock_data = MockDataService({"000001": {"price": 10.0, "name": "平安银行"}})
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)

    # 尝试指定未来时间 (2099-01-01) 试图让今日买入在未来可卖
    with pytest.raises(HTTPException) as exc_info:
        await service.execute_trade(
            SimTradeCreate(
                code="000001",
                name="平安银行",
                direction="buy",
                price=10.0,
                quantity=1000,
                trade_time="2099-01-01 10:00:00"
            ),
            allow_future=False  # 生产模式严禁未来时间
        )
    assert exc_info.value.status_code == 400
    assert "禁止指定未来成交时间" in exc_info.value.detail


# =====================================================================
# 场景 10: 历史时点因果隔离验证 (后续流水不可逆向污染历史时点)
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_10_causal_ledger_isolation(db_session: AsyncSession):
    mock_data = MockDataService({"000001": {"price": 10.0, "name": "平安银行"}})
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)
    account = await service.get_or_create_default_account()

    # Day 1 (2026-10-26 周一): 买入 600 股
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="buy",
            price=10.0,
            quantity=600,
            trade_time="2026-10-26 10:00:00"
        ),
        allow_future=True
    )

    # Day 2 (2026-10-27 周二 10:00): 卖出 200 股
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="sell",
            price=11.0,
            quantity=200,
            trade_time="2026-10-27 10:00:00"
        ),
        allow_future=True
    )

    # 此时当前持仓为 400 股。
    # 核心检验：回溯查询 Day 2 早盘 09:30（在 10:00 卖出之前）的可卖数量：
    # 必须为 600 股！后序 10:00 的 200 股卖出严禁逆向扣减 09:30 的可卖数量！
    avail_at_0930 = await service.get_available_quantity(account.id, "000001", as_of_time="2026-10-27 09:30:00")
    assert avail_at_0930 == 600

    # 回溯查询 Day 2 盘后 15:00（在 10:00 卖出之后）的可卖数量：
    # 此时扣减 200 股，可卖为 400 股。
    avail_at_1500 = await service.get_available_quantity(account.id, "000001", as_of_time="2026-10-27 15:00:00")
    assert avail_at_1500 == 400


# =====================================================================
# 场景 11: 启用 T+1 生产链路下的完整模拟统计闭环核验
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_11_simulation_stats_pipeline_with_t1_enabled(db_session: AsyncSession):
    mock_data = MockDataService({"000001": {"price": 11.0, "name": "平安银行"}})
    # 显式使用 enforce_t1=True（生产默认值）
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)

    # Day 1 (2026-10-26) 买入 1000 股 @ 10.0 元
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="buy",
            price=10.0,
            quantity=1000,
            trade_time="2026-10-26 10:00:00"
        ),
        allow_future=True
    )

    # Day 2 (2026-10-27) 卖出 1000 股 @ 11.0 元 (盈利 +1000.0 元)
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="sell",
            price=11.0,
            quantity=1000,
            trade_time="2026-10-27 10:00:00"
        ),
        allow_future=True
    )

    # 验证在 enforce_t1=True 生产模式下，完整统计接口各项指标闭环
    stats = await service.get_stats()
    assert stats.total_trades == 2
    assert stats.closed_trades == 1
    assert stats.win_trades == 1
    assert stats.loss_trades == 0
    assert stats.win_rate == 100.0
    assert stats.total_realized_pnl == 1000.0
    assert stats.closed_leg_win_rate == 100.0


# =====================================================================
# 场景 12: 公共 API 入口严禁客户端指定 trade_time 倒填时间 (P0 漏洞闭环)
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_12_public_api_rejects_client_trade_time(db_session: AsyncSession):
    from app.api.v1.simulation import execute_simulation_trade

    # 尝试向正式交易 API 传入过去的成交时间试图绕过 T+1
    payload = SimTradeCreate(
        code="000001",
        name="平安银行",
        direction="buy",
        price=10.0,
        quantity=500,
        trade_time="2026-10-26 10:00:00"
    )
    with pytest.raises(HTTPException) as exc_info:
        await execute_simulation_trade(payload=payload, db=db_session)
    assert exc_info.value.status_code == 400
    assert "禁止客户端指定成交时间" in exc_info.value.detail


# =====================================================================
# 场景 13: 倒填卖出时间与当前持仓双重校验防线 (P1 杜绝负持仓)
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_13_backdated_sell_bounded_by_current_position(db_session: AsyncSession):
    mock_data = MockDataService({"000001": {"price": 10.0, "name": "平安银行"}})
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)

    # 1. Day 1 (2026-10-26): 买入 600 股
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="buy",
            price=10.0,
            quantity=600,
            trade_time="2026-10-26 10:00:00"
        ),
        allow_future=True
    )

    # 2. Day 2 (2026-10-27 10:00): 卖出 500 股 (当前物理持仓仅剩 100 股)
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="sell",
            price=11.0,
            quantity=500,
            trade_time="2026-10-27 10:00:00"
        ),
        allow_future=True
    )

    # 3. 尝试倒填到 09:30 卖出 600 股（虽然 09:30 时历史可卖为 600，但当前物理持仓仅剩 100）
    # 必须刚性拒绝，绝不允许产生负持仓！
    with pytest.raises(HTTPException) as exc_info:
        await service.execute_trade(
            SimTradeCreate(
                code="000001",
                name="平安银行",
                direction="sell",
                price=11.0,
                quantity=600,
                trade_time="2026-10-27 09:30:00"
            ),
            allow_future=True
        )
    assert exc_info.value.status_code == 400
    assert "持仓不足" in exc_info.value.detail

    # 验证物理持仓严格保留为 100 股，绝无负持仓
    positions = await service.get_positions()
    assert len(positions) == 1
    assert positions[0].quantity == 100


# =====================================================================
# 场景 14: 清仓后再买入的持仓周期与 T+1 成熟度独立性 (P1 旧仓污染彻底解决)
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_14_reopened_position_holding_cycle_fifo_isolation(db_session: AsyncSession):
    mock_data = MockDataService({"000001": {"price": 10.0, "name": "平安银行"}})
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)

    # 1. Day 1 (2026-10-26): 买入 500 股
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="buy",
            price=10.0,
            quantity=500,
            trade_time="2026-10-26 10:00:00"
        ),
        allow_future=True
    )

    # 2. Day 2 (2026-10-27 10:00): 全量卖出 500 股 (旧仓完全清空)
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="sell",
            price=11.0,
            quantity=500,
            trade_time="2026-10-27 10:00:00"
        ),
        allow_future=True
    )

    # 3. Day 2 (2026-10-27 11:00): 重新买入 500 股 (今日新开仓位)
    await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="buy",
            price=10.5,
            quantity=500,
            trade_time="2026-10-27 11:00:00"
        ),
        allow_future=True
    )

    # 4. 模拟 Day 2 尾盘 14:55 运行风控守护巡检
    # 严格检验：新持仓是今日买入，持股周期为 0 交易日，绝不能受 Day 1 已平仓历史流水污染而错误产生到期信号！
    engine_runner = AutonomousJobEngine(session=db_session, simulation_service=service, data_service=mock_data)
    events = await engine_runner.run_intraday_risk_guard(target_date="2026-10-27")

    # 预期：无任何风控平仓或持仓保护误报（events 为空列表）
    assert len(events) == 0


# =====================================================================
# 场景 15: 调度器与日志状态严格区分平仓与保护 HOLD (P1 真实调度器验证)
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_15_scheduler_liquidation_vs_hold_separation(db_session: AsyncSession):
    from unittest.mock import patch, AsyncMock
    from app.tasks.scheduler import task_scheduler

    mock_events = [
        {
            "code": "000001",
            "name": "平安银行",
            "action": "HOLD",
            "status": "TRIGGERED_T1_PROTECTED",
            "quantity": 0,
            "remaining_quantity": 1000,
            "sell_price": 0.0,
            "reason": "触发风控，但受 A 股 T+1 规则限制可卖数量为 0，保留持仓"
        },
        {
            "code": "600519",
            "name": "贵州茅台",
            "action": "SELL",
            "status": "LIQUIDATED",
            "quantity": 200,
            "remaining_quantity": 0,
            "sell_price": 1800.0,
            "reason": "触及 -5% 止损"
        },
        {
            "code": "113050", "name": "南银转债", "action": "HOLD",
            "status": "LEDGER_ANOMALY_HOLD", "quantity": 0,
            "remaining_quantity": 100, "reason": "账本异常，流水 ID 42 超卖",
        },
    ]

    with patch("app.core.calendar.calendar.is_trading_day", return_value=True), \
         patch("app.services.monitor.MonitorService.get_trading_session_state", return_value="ACTIVE"), \
         patch("app.data.providers.tdx_session_manager.tdx_session_manager.ensure_connected"), \
         patch("app.tasks.scheduler.MonitorService.capture_macro_snapshot", new_callable=AsyncMock), \
         patch("app.tasks.scheduler.MonitorService.detect_anomalies", new_callable=AsyncMock, return_value=[]), \
         patch("app.tasks.scheduler.MonitorService.flush_async_queue", new_callable=AsyncMock), \
         patch("app.services.cockpit_snapshot_service.CockpitSnapshotService.get_instant_snapshot", new_callable=AsyncMock), \
         patch("app.services.autonomous_executor.AutonomousJobEngine.run_intraday_risk_guard", new_callable=AsyncMock, return_value=mock_events):

        # 执行真实的调度器盘中巡检方法
        await task_scheduler._run_intraday_monitor()

    # 验证真实调度器执行历史严格区分平仓与保护 HOLD
    hold_records = [h for h in task_scheduler._execution_history if h.get("action") == "T1_PROTECTED_HOLD"]
    liq_records = [h for h in task_scheduler._execution_history if h.get("action") == "RISK_LIQUIDATION"]

    assert any(h["code"] == "000001" and h["quantity"] == 0 for h in hold_records)
    assert any(l["code"] == "600519" and l["quantity"] == 200 for l in liq_records)
    assert any(h.get("action") == "LEDGER_ANOMALY_HOLD" and h.get("code") == "113050" for h in task_scheduler._execution_history)

    # 验证真实调度器落库日志：明确区分 Liquidations 与 T+1 Holds
    from app.models.system import TaskLog
    stmt = select(TaskLog).where(TaskLog.task_name == "intraday_monitor").order_by(TaskLog.id.desc())
    latest_log = (await db_session.execute(stmt)).scalars().first()
    assert latest_log is not None
    assert latest_log.status == "success"
    assert "Liquidations: 1" in (latest_log.error_message or "")
    assert "T+1 Holds: 1" in (latest_log.error_message or "")
    assert "Ledger Holds: 1" in (latest_log.error_message or "")


# =====================================================================
# 场景 16: 跨进程互斥文件锁超时与 Fail-Closed 拒绝对抗验证 (P0 独立子进程实测)
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_16_file_lock_timeout_fail_closed(db_session: AsyncSession):
    import subprocess
    import sys
    from app.services.simulation import LOCK_FILE_PATH

    mock_data = MockDataService({"000001": {"price": 10.0, "name": "平安银行"}})
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)

    LOCK_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 启动独立 Python 真实子进程，在操作系统层面持有文件互斥排他锁 5 秒
    child_code = f"""import sys, time
from pathlib import Path
lock_path = Path({repr(str(LOCK_FILE_PATH))})
f = open(lock_path, 'a+')
if sys.platform == 'win32':
    import msvcrt
    msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
else:
    import fcntl
    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
sys.stdout.write('LOCKED\\n')
sys.stdout.flush()
time.sleep(5)
if sys.platform == 'win32':
    import msvcrt
    f.seek(0)
    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl
    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
f.close()
"""

    proc = subprocess.Popen(
        [sys.executable, "-c", child_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    try:
        ready = proc.stdout.readline().strip()
        assert ready == "LOCKED", f"子进程未能成功获取锁: {proc.stderr.read()}"

        # 锁被外部独立进程独占时，主进程 execute_trade 必须超时并 Fail-Closed 抛出 HTTPException 423
        t0 = asyncio.get_event_loop().time()
        with pytest.raises(HTTPException) as exc_info:
            await service.execute_trade(
                SimTradeCreate(
                    code="000001",
                    name="平安银行",
                    direction="buy",
                    price=10.0,
                    quantity=100
                )
            )
        duration = asyncio.get_event_loop().time() - t0
        assert exc_info.value.status_code == 423
        assert "互斥锁争用超时" in exc_info.value.detail
        assert duration >= 2.8  # 确实完整经历了 3.0s 超时轮询
    finally:
        proc.terminate()
        proc.wait()

    # 子进程释放锁后，主进程重试交易应当顺利获取锁并执行成功
    res = await service.execute_trade(
        SimTradeCreate(
            code="000001",
            name="平安银行",
            direction="buy",
            price=10.0,
            quantity=100
        )
    )
    assert res.quantity == 100


# =====================================================================
# 场景 17: 倒填异常流水时序与主账本统计一致性验证 (P1 账本时序对齐)
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_17_out_of_order_trade_time_ledger_consistency(db_session: AsyncSession):
    mock_data = MockDataService({"600519": {"price": 105.0, "name": "贵州茅台"}})
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=False)

    # ID 1: 买入 100 股，时点标记为 2026-10-28 10:00:00
    await service.execute_trade(
        SimTradeCreate(
            code="600519",
            name="贵州茅台",
            direction="buy",
            price=100.0,
            quantity=100,
            trade_time="2026-10-28 10:00:00"
        ),
        allow_future=True
    )

    # ID 2: 卖出 100 股，由于历史补录填写的 trade_time 为 2026-10-27 09:30:00 (时间倒填，但主账本 ID 为 2)
    await service.execute_trade(
        SimTradeCreate(
            code="600519",
            name="贵州茅台",
            direction="sell",
            price=105.0,
            quantity=100,
            trade_time="2026-10-27 09:30:00"
        ),
        allow_future=True
    )

    account = await service.get_or_create_default_account()

    # 1. 验证中间时点 (2026-10-27 15:00:00) 查询安全性：
    # 此时仅筛选到 ID 2 (卖出 100 股)，无对应买入批次。
    # 系统安全结转 unmatched_sells = 100，坚决杜绝静默丢弃，且返回可卖数量严格为 0！
    avail_intermediate = await service.get_available_quantity(account.id, "600519", as_of_time="2026-10-27 15:00:00")
    assert avail_intermediate == 0

    # 2. 验证后序时点 (2026-10-28 15:00:00 与 2026-10-29 15:00:00)：
    # 纳入 ID 1 (买入 100 股) 与 ID 2 (卖出 100 股)，两者完全对冲闭环，剩余未平仓批次为 0。
    # 绝不会发生因为 trade_time 倒填而在队列为空时丢弃 ID 2，进而将 ID 1 误判为剩余未平仓批次！
    avail_at_buy_day = await service.get_available_quantity(account.id, "600519", as_of_time="2026-10-28 15:00:00")
    assert avail_at_buy_day == 0

    avail_qty = await service.get_available_quantity(account.id, "600519", as_of_time="2026-10-29 15:00:00")
    assert avail_qty == 0

    # 3. 验证统计接口与账户已实现盈亏完全闭环
    stats = await service.get_stats()
    assert stats.total_realized_pnl == round(account.total_pnl, 2)
    assert stats.total_realized_pnl == 500.0
    assert stats.closed_trades == 1
    assert stats.win_trades == 1
    assert stats.win_rate == 100.0


# =====================================================================
# 场景 18: 前端三个交易入口无 trade_time 正常提交与执行验证 (P0 闭环验证)
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_18_frontend_entrypoints_without_trade_time(db_session: AsyncSession):
    from app.api.v1.simulation import execute_simulation_trade

    # 1. 模拟前端【策略跟单买入】调用：不携带 trade_time
    buy_payload = SimTradeCreate(
        code="000001",
        name="平安银行",
        direction="buy",
        price=10.0,
        quantity=1000,
        decision_summary="[首板掘金] (评分 92) · 策略联动模拟建仓"
    )
    res_buy = await execute_simulation_trade(payload=buy_payload, db=db_session)
    assert res_buy["code"] == 200
    trade_buy = res_buy["data"]
    assert trade_buy.quantity == 1000
    assert trade_buy.direction == "buy"
    assert trade_buy.trade_time is not None  # 服务端自动填充当前受控时间

    # 2. 模拟前端【手动报单买入】调用：不携带 trade_time
    manual_payload = SimTradeCreate(
        code="600519",
        name="贵州茅台",
        direction="buy",
        price=1600.0,
        quantity=100,
        decision_summary="手动技术形态建仓"
    )
    res_manual = await execute_simulation_trade(payload=manual_payload, db=db_session)
    assert res_manual["code"] == 200
    trade_manual = res_manual["data"]
    assert trade_manual.quantity == 100
    assert trade_manual.code == "600519"

    # 3. 模拟前端同日尝试卖出刚才买入的普通股票 ➔ A 股 T+1 刚性拒绝
    sell_t1_payload = SimTradeCreate(
        code="000001",
        name="平安银行",
        direction="sell",
        price=10.5,
        quantity=1000,
        decision_summary="模拟盘手动止盈止损平仓"
    )
    with pytest.raises(HTTPException) as exc_info:
        await execute_simulation_trade(payload=sell_t1_payload, db=db_session)
    assert exc_info.value.status_code == 400
    assert "今日买入尚未转为可卖仓" in exc_info.value.detail


# =====================================================================
# 场景 19: 异常超卖结转、买入冲抵与风控周期多时点一致性核验 (P1 未抵扣卖出结转闭环)
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_19_unmatched_sell_carry_forward_and_risk_guard(db_session: AsyncSession):
    from app.models.simulation import SimTrade, SimPosition
    from app.services.autonomous_executor import AutonomousJobEngine

    mock_data = MockDataService({"000001": {"price": 10.0, "name": "平安银行"}})
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)
    account = await service.get_or_create_default_account()

    # 1. 模拟底层直接补录/历史异常流水 (验证批次算法抗扰动与未抵扣卖出结转鲁棒性)
    # Trade 1: 买入 100 股 @ 2026-10-26 10:00:00 (周一)
    t1 = SimTrade(
        account_id=account.id,
        code="000001",
        name="平安银行",
        direction="buy",
        price=10.0,
        quantity=100,
        trade_time="2026-10-26 10:00:00",
        decision_summary="底仓买入"
    )
    # Trade 2: 卖出 200 股 @ 2026-10-27 10:00:00 (周二，超额卖出 100 股)
    t2 = SimTrade(
        account_id=account.id,
        code="000001",
        name="平安银行",
        direction="sell",
        price=10.5,
        quantity=200,
        trade_time="2026-10-27 10:00:00",
        decision_summary="超额卖出流水"
    )
    # Trade 3: 补录买入 100 股 @ 2026-10-28 10:00:00 (周三，刚好吸收前序未抵扣的 100 股超卖)
    t3 = SimTrade(
        account_id=account.id,
        code="000001",
        name="平安银行",
        direction="buy",
        price=10.0,
        quantity=100,
        trade_time="2026-10-28 10:00:00",
        decision_summary="补单买入"
    )
    # Trade 4: 再次买入 150 股 @ 2026-10-29 10:00:00 (周四，真实有效多头持仓)
    t4 = SimTrade(
        account_id=account.id,
        code="000001",
        name="平安银行",
        direction="buy",
        price=10.0,
        quantity=150,
        trade_time="2026-10-29 10:00:00",
        decision_summary="有效建仓"
    )
    db_session.add_all([t1, t2, t3, t4])

    # 建立对应真实当前持仓 150 股 (净头寸: 100 - 200 + 100 + 150 = 150)
    pos = SimPosition(
        account_id=account.id,
        code="000001",
        name="平安银行",
        quantity=150,
        avg_cost=10.0,
        current_price=10.0,
        floating_pnl=0.0
    )
    db_session.add(pos)
    await db_session.commit()

    # 1. 完整主账本真实超卖核验（对齐 get_stats 统计口径与 HTTP 409 契约）
    # 流水 t1(买100) -> t2(卖200) 在物理账本上发生真实超卖异常（卖出数量超出持仓）
    # 统计接口必须抛出 HTTP 409，可卖数量安全返回 0（避免持仓查询崩溃），卖出操作必须刚性被 409 阻断！
    with pytest.raises(HTTPException) as exc_stats:
        await service.get_stats()
    assert exc_stats.value.status_code == 409
    assert "超卖" in exc_stats.value.detail

    avail_qty = await service.get_available_quantity(account.id, "000001", as_of_time="2026-10-30 09:30:00")
    assert avail_qty == 0

    # 尝试调用 execute_trade 卖出该普通股票，必须被刚性阻断并返回 HTTP 409
    with pytest.raises(HTTPException) as exc_sell:
        await service.execute_trade(
            SimTradeCreate(
                code="000001",
                name="平安银行",
                direction="sell",
                price=11.0,
                quantity=100,
                trade_time="2026-10-30 10:00:00"
            ),
            allow_future=True
        )
    assert exc_sell.value.status_code == 409
    assert "超卖" in exc_sell.value.detail

    # 2. 可转债 T+0 标的独立账本完整性核验（防御 P1 漏洞：杜绝 T+0 品种因绕过 T+1 而在损坏账本上卖出）
    # 模拟可转债 113050 (南银转债) 存在历史超卖：买 100 -> 卖 200 -> 再买 100
    cb_buy1 = SimTrade(
        account_id=account.id,
        code="113050",
        name="南银转债",
        direction="buy",
        price=120.0,
        quantity=100,
        trade_time="2026-10-28 10:00:00",
        decision_summary="转债建仓"
    )
    cb_sell_over = SimTrade(
        account_id=account.id,
        code="113050",
        name="南银转债",
        direction="sell",
        price=125.0,
        quantity=200,
        trade_time="2026-10-28 11:00:00",
        decision_summary="转债超卖"
    )
    cb_buy2 = SimTrade(
        account_id=account.id,
        code="113050",
        name="南银转债",
        direction="buy",
        price=120.0,
        quantity=100,
        trade_time="2026-10-28 14:00:00",
        decision_summary="转债补买"
    )
    db_session.add_all([cb_buy1, cb_sell_over, cb_buy2])
    pos_cb = SimPosition(
        account_id=account.id,
        code="113050",
        name="南银转债",
        quantity=100,
        avg_cost=120.0,
        current_price=120.0,
        floating_pnl=0.0
    )
    db_session.add(pos_cb)
    await db_session.commit()

    # 尝试卖出可转债 113050：虽然品种是 T+0 且物理持仓为 100 股，但由于独立账本校验，坚决阻断并返回 HTTP 409！
    with pytest.raises(HTTPException) as exc_cb:
        await service.execute_trade(
            SimTradeCreate(
                code="113050",
                name="南银转债",
                direction="sell",
                price=125.0,
                quantity=100,
                trade_time="2026-10-28 14:30:00"
            ),
            allow_future=True
        )
    assert exc_cb.value.status_code == 409
    assert "超卖" in exc_cb.value.detail
    assert str(cb_sell_over.id) in exc_cb.value.detail

    # 3. 验证风控执行器 AutonomousJobEngine 在主账本存在真实超卖异常时刚性阻断卖出
    executor = AutonomousJobEngine(session=db_session, data_service=mock_data)

    # 2026-10-28 尾盘：账本存在真实超卖异常，严禁误触发到期平仓
    res_28 = await executor.run_intraday_risk_guard(target_date="2026-10-28")
    assert not any(act.get("action") in ("SELL", "PARTIAL_SELL") for act in res_28)

    # 2026-10-29 尾盘：严禁触发平仓
    res_29 = await executor.run_intraday_risk_guard(target_date="2026-10-29")
    assert not any(act.get("action") in ("SELL", "PARTIAL_SELL") for act in res_29)

    # 2026-10-30 尾盘：即便后续买入 t4 达到 T+1，因历史账本真实超卖，风控坚决阻断卖出！
    res_30 = await executor.run_intraday_risk_guard(target_date="2026-10-30")
    assert not any(act.get("action") in ("SELL", "PARTIAL_SELL") for act in res_30)
    assert {event["code"] for event in res_30 if event["status"] == "LEDGER_ANOMALY_HOLD"} == {"000001", "113050"}
    assert all("流水 ID" in event["reason"] for event in res_30)
    mock_data.quotes["000001"] = {"price": 9.0, "name": "平安银行"}
    mock_data.quotes["113050"] = {"price": 100.0, "name": "南银转债"}
    stop_events = await executor.run_intraday_risk_guard(target_date="2026-10-30")
    assert {event["code"] for event in stop_events if event["status"] == "LEDGER_ANOMALY_HOLD"} == {"000001", "113050"}
    assert all("硬止损" in event["trigger_reason"] for event in stop_events)


# =====================================================================
# 场景 20: 时间筛选临时缺口安全处理与日历覆盖外买入刚性阻断核验 (P1 闭环)
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_20_temporary_gap_and_uncovered_year_buy_rejection(db_session: AsyncSession):
    from app.core.calendar import CalendarCoverageError
    from app.models.simulation import SimTrade, SimPosition
    from app.services.autonomous_executor import AutonomousJobEngine

    mock_data = MockDataService({"600519": {"price": 100.0, "name": "贵州茅台"}})
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=True)
    account = await service.get_or_create_default_account()

    # -------------------------------------------------------------
    # Part 1: 时间筛选造成的临时缺口安全处理（主账本完全合法无真实超卖）
    # -------------------------------------------------------------
    # ID 1: 买入 100 股，标记 trade_time 为 2026-10-28 10:00:00
    t1 = SimTrade(
        account_id=account.id,
        code="600519",
        name="贵州茅台",
        direction="buy",
        price=100.0,
        quantity=100,
        trade_time="2026-10-28 10:00:00",
        decision_summary="底仓"
    )
    # ID 2: 卖出 100 股，历史补录标记 trade_time 为 2026-10-27 09:30:00 (倒填，但主账本 ID=2 且数量完全闭环)
    t2 = SimTrade(
        account_id=account.id,
        code="600519",
        name="贵州茅台",
        direction="sell",
        price=105.0,
        quantity=100,
        trade_time="2026-10-27 09:30:00",
        decision_summary="倒填平仓"
    )
    # ID 3: 再次买入 150 股，trade_time 为 2026-10-29 10:00:00 (合法新多头)
    t3 = SimTrade(
        account_id=account.id,
        code="600519",
        name="贵州茅台",
        direction="buy",
        price=100.0,
        quantity=150,
        trade_time="2026-10-29 10:00:00",
        decision_summary="合法建仓"
    )
    db_session.add_all([t1, t2, t3])
    pos = SimPosition(
        account_id=account.id,
        code="600519",
        name="贵州茅台",
        quantity=150,
        avg_cost=100.0,
        current_price=100.0,
        floating_pnl=0.0
    )
    db_session.add(pos)
    await db_session.commit()

    # 主账本按 ID 升序遍历无任何超卖（100 -> 0 -> 150），统计接口顺利通过
    stats = await service.get_stats()
    assert stats.closed_trades == 1
    assert stats.total_realized_pnl == 500.0

    # 中间时点 (2026-10-27 15:00:00) 查询：属于时间筛选造成的临时缺口，安全返回 0（不报 409！）
    avail_gap = await service.get_available_quantity(account.id, "600519", as_of_time="2026-10-27 15:00:00")
    assert avail_gap == 0

    # 2026-10-28 15:00:00: t1 与 t2 对冲闭环，可卖数量为 0
    avail_28 = await service.get_available_quantity(account.id, "600519", as_of_time="2026-10-28 15:00:00")
    assert avail_28 == 0

    # 2026-10-29 15:00:00: t3 尚未成熟，可卖数量为 0
    avail_29 = await service.get_available_quantity(account.id, "600519", as_of_time="2026-10-29 15:00:00")
    assert avail_29 == 0

    # 2026-10-30 09:30:00: t3 正式成熟，可卖数量精确为 150 股！
    avail_30 = await service.get_available_quantity(account.id, "600519", as_of_time="2026-10-30 09:30:00")
    assert avail_30 == 150

    # -------------------------------------------------------------
    # Part 2: 日历覆盖外的自动撮合与买入刚性阻断核验 (2027 年工作日防线)
    # -------------------------------------------------------------
    executor = AutonomousJobEngine(session=db_session, data_service=mock_data)

    # 1. 自动撮合入口 execute_open_market_match 针对 2027 年工作日必须抛出 CalendarCoverageError 刚性阻断
    queued_order = [{
        "code": "600519",
        "name": "贵州茅台",
        "price": 100.0,
        "quantity": 100,
        "decision_summary": "[双轨待决] 2027 年非法测试订单"
    }]
    with pytest.raises(CalendarCoverageError) as exc_cov:
        await executor.execute_open_market_match(queued_order, target_date="2027-01-04")
    assert "未覆盖年份 2027" in str(exc_cov.value)

    # 2. 模拟交易执行买入分支针对 2027 年成交时间必须刚性抛出 HTTP 500 阻断买入
    with pytest.raises(HTTPException) as exc_buy_cov:
        await service.execute_trade(
            SimTradeCreate(
                code="600519",
                name="贵州茅台",
                direction="buy",
                price=100.0,
                quantity=100,
                trade_time="2027-01-04 09:30:00"
            ),
            allow_future=True
        )
    assert exc_buy_cov.value.status_code == 500
    assert "交易日历未覆盖年份" in exc_buy_cov.value.detail


# =====================================================================
# 场景 21: 多标的异常账本全局 ID 顺序核验（防持仓遍历扰动首个异常定位）
# =====================================================================
@pytest.mark.asyncio
async def test_scenario_21_stats_reports_earliest_global_anomaly_across_multiple_symbols(db_session: AsyncSession):
    from app.models.simulation import SimTrade, SimPosition

    mock_data = MockDataService({
        "000001": {"price": 10.0, "name": "平安银行"},
        "000002": {"price": 10.0, "name": "万科A"}
    })
    service = SimulationService(session=db_session, data_service=mock_data, enforce_t1=False)
    account = await service.get_or_create_default_account()

    # 构造流水时序：
    # 1. 标的 A (000001): 正常买入 100 股 (较早 ID)
    trade_a1 = SimTrade(
        account_id=account.id,
        code="000001",
        name="平安银行",
        direction="buy",
        price=10.0,
        quantity=100,
        trade_time="2026-10-26 10:00:00"
    )
    db_session.add(trade_a1)
    await db_session.commit()
    await db_session.refresh(trade_a1)

    # 2. 标的 B (000002): 买入 100 股
    trade_b1 = SimTrade(
        account_id=account.id,
        code="000002",
        name="万科A",
        direction="buy",
        price=10.0,
        quantity=100,
        trade_time="2026-10-26 10:30:00"
    )
    db_session.add(trade_b1)
    await db_session.commit()
    await db_session.refresh(trade_b1)

    # 3. 标的 B (000002): 发生全账户【全局首个超卖异常】(卖出 200 股，超卖 100 股)
    trade_b_oversell = SimTrade(
        account_id=account.id,
        code="000002",
        name="万科A",
        direction="sell",
        price=11.0,
        quantity=200,
        trade_time="2026-10-27 10:00:00"
    )
    db_session.add(trade_b_oversell)
    await db_session.commit()
    await db_session.refresh(trade_b_oversell)

    # 4. 标的 A (000001): 在更靠后的 ID 发生【后发超卖异常】(卖出 200 股)
    trade_a_oversell = SimTrade(
        account_id=account.id,
        code="000001",
        name="平安银行",
        direction="sell",
        price=11.0,
        quantity=200,
        trade_time="2026-10-28 10:00:00"
    )
    db_session.add(trade_a_oversell)
    await db_session.commit()
    await db_session.refresh(trade_a_oversell)

    # 注入当前持仓记录 (标的 A 排序在标的 B 之前)
    pos_a = SimPosition(
        account_id=account.id,
        code="000001",
        name="平安银行",
        quantity=100,
        avg_cost=10.0,
        current_price=10.0,
        floating_pnl=0.0
    )
    pos_b = SimPosition(
        account_id=account.id,
        code="000002",
        name="万科A",
        quantity=100,
        avg_cost=10.0,
        current_price=10.0,
        floating_pnl=0.0
    )
    db_session.add_all([pos_a, pos_b])
    await db_session.commit()

    # 断言：get_stats 严禁因 get_positions 遍历标的 A 而提前报出后发生的 ID (trade_a_oversell)，
    # 必须严格按全账户流水 ID 顺序定位首个异常流水 (trade_b_oversell)！
    with pytest.raises(HTTPException) as exc_info:
        await service.get_stats()

    assert exc_info.value.status_code == 409
    assert str(trade_b_oversell.id) in exc_info.value.detail
    assert "000002" in exc_info.value.detail
    assert str(trade_a_oversell.id) not in exc_info.value.detail



@pytest.mark.asyncio
async def test_risk_guard_preserves_calendar_http_error(db_session):
    from unittest.mock import AsyncMock

    mock_data = MockDataService({"000001": {"price": 9.0, "name": "平安银行"}})
    service = SimulationService(session=db_session, data_service=mock_data)
    account = await service.get_or_create_default_account()
    db_session.add(SimPosition(account_id=account.id, code="000001", name="平安银行", quantity=100, avg_cost=10.0, current_price=9.0, floating_pnl=-100.0))
    await db_session.commit()
    service.get_available_quantity = AsyncMock(side_effect=HTTPException(status_code=500, detail="交易日历不可用"))
    executor = AutonomousJobEngine(session=db_session, simulation_service=service, data_service=mock_data)
    with pytest.raises(HTTPException) as exc:
        await executor.run_intraday_risk_guard(target_date="2026-10-29")
    assert exc.value.status_code == 500
    assert exc.value.detail == "交易日历不可用"

