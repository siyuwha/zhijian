import os
import sys
import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from collections import deque
from contextlib import asynccontextmanager
from fastapi import HTTPException
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.simulation import SimAccount, SimTrade, SimPosition
from ..schemas.simulation import (
    SimTradeCreate,
    SimAccountResponse,
    SimPositionResponse,
    SimTradeResponse,
    SimStatsResponse,
)
from ..data.service import DataService
from ..core.calendar import calendar, CalendarCoverageError

logger = logging.getLogger(__name__)

# A 股明确合规的可转债 T+0 代码段（上交所 110/111/113/118，深交所 123/127/128）
VALID_CONVERTIBLE_BOND_PREFIXES = ("110", "111", "113", "118", "123", "127", "128")
CONVERTIBLE_BOND_NAME_KEYWORDS = ("转债", "可转债", "EB", "转2", "转3")

def is_t0_instrument(code: str, name: Optional[str] = None) -> bool:
    """
    严格判定标的是否属于明确合规的 T+0 品种（仅限 A 股特定号段且名称具备可信可转债标识的品种）。
    - 代码号段约束：
      - 上交所可转债：110xxx, 111xxx, 113xxx, 118xxx(科创转债)
      - 深交所可转债：123xxx(创业板转债), 127xxx, 128xxx
    - 证券类型校验：
      - 若提供了标的名称，必须包含明确的可转债/交换债关键字（转债、可转债、EB、转2、转3）。
      - 若无名称或名称不匹配，坚决不猜测为 T+0，一律安全回落至 T+1 严格约束。
    - 普通股票（00/30/60/68/8/4）与未知号段（如 119xxx、120xxx 等）一律返回 False。
    """
    if not code:
        return False
    c = str(code).lower().replace("sh", "").replace("sz", "").replace("bj", "").strip()
    if not (len(c) == 6 and c.isdigit() and c.startswith(VALID_CONVERTIBLE_BOND_PREFIXES)):
        return False
    if not name:
        return False
    n = str(name).strip().upper()
    return any(kw in n for kw in ("转债", "可转债", "EB", "转2", "转3"))

# 绝对路径绑定锁文件，防止工作目录偏移导致跨进程锁隔离失效
LOCK_FILE_PATH = (Path(__file__).resolve().parent.parent.parent / "data" / ".sim_trade_mutex.lock").resolve()

_trade_locks: Dict[Any, asyncio.Lock] = {}

def _get_trade_lock() -> asyncio.Lock:
    """获取当前事件循环绑定的交易互斥锁"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.Lock()
    if loop not in _trade_locks:
        _trade_locks[loop] = asyncio.Lock()
    return _trade_locks[loop]

@asynccontextmanager
async def _acquire_trade_mutex():
    """
    双层互斥锁：
    1. 进程内事件循环级 asyncio.Lock
    2. 跨进程/跨实例 OS 文件级独占锁（带 3.0s 超时重试与 Fail-Closed 刚性拒绝）
    """
    async with _get_trade_lock():
        LOCK_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        f = None
        locked = False
        try:
            f = open(LOCK_FILE_PATH, "a+")
            start_t = asyncio.get_event_loop().time()
            timeout = 3.0

            while True:
                try:
                    f.seek(0)
                    if sys.platform == "win32":
                        import msvcrt
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                    break
                except (OSError, IOError):
                    if asyncio.get_event_loop().time() - start_t >= timeout:
                        break
                    await asyncio.sleep(0.02)
                except Exception as e:
                    logger.error(f"跨进程锁发生非预期异常: {e}")
                    raise HTTPException(status_code=500, detail=f"文件互斥锁系统异常: {e}")

            if not locked:
                logger.error("跨进程交易文件锁获取超时 (3.0s)，严格拒绝并发写入以防资金与持仓超卖")
                raise HTTPException(status_code=423, detail="系统交易互斥锁争用超时，拒绝并发写入")

            yield
        finally:
            if f:
                if locked:
                    try:
                        f.seek(0)
                        if sys.platform == "win32":
                            import msvcrt
                            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                    except Exception as e:
                        logger.warning(f"释放交易文件锁异常: {e}")
                try:
                    f.close()
                except Exception:
                    pass

class SimulationService:
    """策略实盘模拟交易与沙盒管理服务 (与真实券商账户物理隔离)"""

    def __init__(
        self,
        session: AsyncSession,
        data_service: Optional[DataService] = None,
        enforce_t1: bool = True
    ):
        self.session = session
        self.data_service = data_service or DataService()
        self.enforce_t1 = enforce_t1

    async def verify_t0_instrument(self, code: str) -> bool:
        """
        严格由服务端可信行情数据源判定标的是否属于合规可转债 T+0 品种（杜绝客户端伪造名称绕过 T+1）。
        1. 标的代码必须符合 A 股法定可转债号段（110/111/113/118/123/127/128）。
        2. 标的名称必须由服务端 DataService 权威行情源拉取，且官方名称包含可转债特征关键字。
           坚决不采信客户端请求体传入的任何名称！
        3. 查无官方行情、拉取失败、或名称不含可转债特征关键字的，一律拒绝判定为 T+0，安全回落至 T+1 严格约束。
        """
        if not code:
            return False
        clean_code = str(code).lower().replace("sh", "").replace("sz", "").replace("bj", "").strip()
        if not (len(clean_code) == 6 and clean_code.isdigit() and clean_code.startswith(VALID_CONVERTIBLE_BOND_PREFIXES)):
            return False

        try:
            q_res = await self.data_service.get_stock_quotes([clean_code])
            if q_res and hasattr(q_res, "data") and q_res.data:
                for item in q_res.data:
                    c = str(item.get("code") or item.get("symbol") or "").lower().replace("sh", "").replace("sz", "").replace("bj", "").strip()
                    if c == clean_code or not c:
                        official_name = str(item.get("name") or "").strip().upper()
                        if any(kw in official_name for kw in CONVERTIBLE_BOND_NAME_KEYWORDS):
                            return True
        except Exception as e:
            logger.warning(f"服务端核验标的 {code} 证券类型权威数据异常: {e}")

        return False

    async def get_available_quantity(
        self,
        account_id: int,
        code: str,
        as_of_time: Optional[str] = None
    ) -> int:
        """
        按交易日及成交流水时序（严格 FIFO 批次重建法）核算指定时点的 A 股可卖持仓数量。
        - 仅纳入发生于 as_of_time 及之前的历史流水，严禁后序未来流水逆向污染历史时点。
        - 采用标准 FIFO 批次队列模拟真实持仓消耗：
          1. 每一笔买入流水按 id.asc 入队为待成熟/已成熟批次；
          2. 每一笔卖出流水按 FIFO 严格依次扣减最早买入批次（不论该批次当时是否已成熟）；
          3. 截止 as_of_time，统计队列中所有剩余未平仓批次中，其次交易日 <= as_of_date 的可卖数量之和。
        - 标的若属于可转债 T+0（经服务端权威行情双重认证），则截止该时点所有未平批次均立即可卖。
        - 日历覆盖范围缺失时严格抛出 500 阻止操作。
        """
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_str = (as_of_time or now_str).strip()

        try:
            as_of_date_str = time_str[:10]
            as_of_date = datetime.strptime(as_of_date_str, "%Y-%m-%d").date()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"交易时间格式无效无法核算 T+1 可卖数量: {e}")

        # 日历覆盖范围与可用性校验：未覆盖年份或日历异常直接抛 500 阻止操作
        try:
            calendar.check_coverage(as_of_date)
            _ = calendar.is_trading_day(as_of_date, enforce_coverage=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"交易日历不可用，拒绝依赖 T+1 的操作: {e}")

        # 完整主账本超卖异常核验（区分【时间筛选临时缺口】与【完整账本真实异常】）
        # 若主账本自身存在真实超卖，则当前持仓在账本上不合法，可卖数量必为 0
        stmt_full = (
            select(SimTrade)
            .where(
                SimTrade.account_id == account_id,
                SimTrade.code == code,
            )
            .order_by(SimTrade.id.asc())
        )
        all_trades_for_code = list((await self.session.execute(stmt_full)).scalars().all())

        running_full_qty = 0
        has_real_anomaly = False
        for t in all_trades_for_code:
            t_dir = (t.direction or "").lower().strip()
            t_qty = int(t.quantity)
            if t_dir == "buy":
                running_full_qty += t_qty
            elif t_dir == "sell":
                if running_full_qty < t_qty:
                    has_real_anomaly = True
                running_full_qty -= t_qty

        if has_real_anomaly:
            return 0

        # 仅查询 <= as_of_time 的历史交易流水，按流水 ID 严格升序排列（与系统主账本及统计口径统一）
        stmt_trades = (
            select(SimTrade)
            .where(
                SimTrade.account_id == account_id,
                SimTrade.code == code,
                SimTrade.trade_time <= time_str
            )
            .order_by(SimTrade.id.asc())
        )
        trades = list((await self.session.execute(stmt_trades)).scalars().all())

        if not trades:
            return 0

        # 服务端权威校验标的是否属于可信 T+0 品种（绝不采信客户端传入名称）
        is_t0 = await self.verify_t0_instrument(code)

        # 严格 FIFO 批次队列模拟（在完整账本合法前提下，安全处理时间筛选造成的临时缺口）
        lots = deque()  # 每个元素: {"qty": int, "sellable_date": Optional[date]}
        unmatched_gap_sells = 0

        for t in trades:
            t_dir = (t.direction or "").lower().strip()
            qty = int(t.quantity)
            if qty <= 0:
                continue

            if t_dir == "buy":
                if is_t0:
                    sellable_date = None
                else:
                    try:
                        b_date_str = (t.trade_time or "").strip()[:10]
                        b_date = datetime.strptime(b_date_str, "%Y-%m-%d").date()
                        calendar.check_coverage(b_date)
                        sellable_date = calendar.next_trading_day(b_date)
                        calendar.check_coverage(sellable_date)
                    except Exception as e:
                        raise HTTPException(status_code=500, detail=f"交易日历无法推算流水 ID {t.id} 的次交易日: {e}")
                lots.append({"qty": qty, "sellable_date": sellable_date})

            elif t_dir == "sell":
                # 卖出流水按 FIFO 优先扣减最早未闭环的买入批次
                to_deduct = qty
                while to_deduct > 0 and lots:
                    first_lot = lots[0]
                    if first_lot["qty"] <= to_deduct:
                        to_deduct -= first_lot["qty"]
                        lots.popleft()
                    else:
                        first_lot["qty"] -= to_deduct
                        to_deduct = 0

                # 若卖出数量超出已有买入批次（由于时间筛选导致对应买入发生在 as_of_time 之后）
                if to_deduct > 0:
                    unmatched_gap_sells += to_deduct

        # 若遍历结束仍有未冲抵的卖出量（时间筛选临时缺口），说明当前历史时点无可卖现货持仓
        if unmatched_gap_sells > 0:
            return 0

        # 核算截止 as_of_time 剩余未闭环批次中的可卖数量
        available_qty = 0
        total_remaining = 0
        for lot in lots:
            total_remaining += lot["qty"]
            if is_t0:
                available_qty += lot["qty"]
            else:
                if lot["sellable_date"] is not None and as_of_date >= lot["sellable_date"]:
                    available_qty += lot["qty"]

        return min(total_remaining, available_qty)

    async def verify_ledger_integrity(self, account_id: int, code: Optional[str] = None) -> None:
        """
        独立核验账本完整性（独立于 T+1，对齐 get_stats 统计口径与 HTTP 409 契约）。
        按全账户流水 ID 严格升序遍历；若历史存在无成本卖出或超卖，刚性抛出 HTTP 409 阻断卖出。
        若指定 code，仅在涉及该标的发生异常时抛出；若未指定 code，则全账户首个异常即抛出。
        """
        stmt = (
            select(SimTrade)
            .where(SimTrade.account_id == account_id)
            .order_by(SimTrade.id.asc())
        )
        trades = list((await self.session.execute(stmt)).scalars().all())

        pos_tracker: Dict[str, int] = {}
        for t in trades:
            direction = (t.direction or "").lower().strip()
            qty = int(t.quantity)
            c = t.code

            if direction == "buy":
                pos_tracker[c] = pos_tracker.get(c, 0) + qty
            elif direction == "sell":
                curr_q = pos_tracker.get(c, 0)
                if curr_q <= 0:
                    if code is None or c == code:
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                f"模拟交易统计失败: 流水 ID {t.id} 存在无成本卖出异常 "
                                f"(标的代码 {c}, 拟卖出 {qty} 股, 当前持仓 0 股)"
                            ),
                        )
                elif curr_q < qty:
                    if code is None or c == code:
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                f"模拟交易统计失败: 流水 ID {t.id} 存在超卖异常 "
                                f"(标的代码 {c}, 拟卖出 {qty} 股, 当前持仓仅 {curr_q} 股)"
                            ),
                        )
                pos_tracker[c] = curr_q - qty

    async def get_or_create_default_account(self) -> SimAccount:
        """获取或初始化默认策略实盘模拟账户 (初始虚拟资金 100 万元)"""
        stmt = select(SimAccount).where(SimAccount.is_active == 1).order_by(SimAccount.id.asc())
        account = (await self.session.execute(stmt)).scalars().first()
        if not account:
            account = SimAccount(
                name="策略实盘模拟账户",
                initial_capital=1000000.0,
                current_capital=1000000.0,
                total_pnl=0.0,
                is_active=1
            )
            self.session.add(account)
            await self.session.commit()
            await self.session.refresh(account)
        return account

    async def get_account_summary(self) -> SimAccountResponse:
        """获取模拟账户总览（现金、持仓市值、总资产、收益率）"""
        account = await self.get_or_create_default_account()
        positions = await self.get_positions(refresh_quote=True)
        
        market_value = sum(p.market_value for p in positions)
        total_asset = round(account.current_capital + market_value, 2)
        total_pnl = round(total_asset - account.initial_capital, 2)
        total_pnl_pct = round((total_pnl / account.initial_capital) * 100, 2) if account.initial_capital > 0 else 0.0

        return SimAccountResponse(
            id=account.id,
            name=account.name,
            initial_capital=account.initial_capital,
            current_capital=round(account.current_capital, 2),
            market_value=round(market_value, 2),
            total_asset=total_asset,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct
        )

    async def get_positions(
        self,
        refresh_quote: bool = True,
        as_of_time: Optional[str] = None
    ) -> List[SimPositionResponse]:
        """获取策略模拟持仓快照（支持实时行情对齐与特定时点 T+1 可卖数量核算）"""
        account = await self.get_or_create_default_account()
        stmt = select(SimPosition).where(SimPosition.account_id == account.id, SimPosition.quantity > 0)
        positions = list((await self.session.execute(stmt)).scalars().all())

        if not positions:
            return []

        # 批量获取最新市价
        quotes: Dict[str, Any] = {}
        if refresh_quote:
            try:
                symbols = [p.code for p in positions]
                quotes_resp = await self.data_service.get_stock_quotes(symbols)
                if quotes_resp and quotes_resp.data:
                    for item in quotes_resp.data:
                        code = item.get("code") or item.get("symbol")
                        if code:
                            clean_c = code.replace("sh", "").replace("sz", "").replace("bj", "")
                            quotes[clean_c] = float(item.get("price") or item.get("close") or 0.0)
            except Exception as e:
                logger.warning(f"Failed to fetch quotes for sim positions: {e}")

        result: List[SimPositionResponse] = []
        for pos in positions:
            clean_code = pos.code.replace("sh", "").replace("sz", "").replace("bj", "")
            latest_price = quotes.get(clean_code) or pos.current_price or pos.avg_cost
            if latest_price > 0 and latest_price != pos.current_price:
                pos.current_price = latest_price
                pos.floating_pnl = round((latest_price - pos.avg_cost) * pos.quantity, 2)

            mkt_val = round(latest_price * pos.quantity, 2)
            flt_pnl = round((latest_price - pos.avg_cost) * pos.quantity, 2)
            flt_pct = round(((latest_price - pos.avg_cost) / pos.avg_cost) * 100, 2) if pos.avg_cost > 0 else 0.0

            avail_qty = await self.get_available_quantity(pos.account_id, pos.code, as_of_time=as_of_time)

            updated_at_val = pos.__dict__.get("updated_at")

            result.append(SimPositionResponse(
                id=pos.id,
                account_id=pos.account_id,
                code=pos.code,
                name=pos.name or pos.code,
                quantity=pos.quantity,
                available_quantity=avail_qty,
                avg_cost=pos.avg_cost,
                total_cost=round(pos.quantity * pos.avg_cost, 2),
                current_price=latest_price,
                market_value=mkt_val,
                floating_pnl=flt_pnl,
                floating_pnl_pct=flt_pct,
                updated_at=updated_at_val
            ))

        await self.session.commit()
        return result

    async def get_records(self, limit: int = 50) -> List[SimTradeResponse]:
        """获取策略模拟交易流水明细"""
        account = await self.get_or_create_default_account()
        stmt = select(SimTrade).where(SimTrade.account_id == account.id).order_by(SimTrade.id.desc()).limit(limit)
        trades = list((await self.session.execute(stmt)).scalars().all())

        return [
            SimTradeResponse(
                id=t.id,
                account_id=t.account_id,
                code=t.code,
                name=t.name,
                direction=t.direction,
                price=t.price,
                quantity=t.quantity,
                amount=round(t.price * t.quantity, 2),
                trade_time=t.trade_time,
                strategy_id=t.strategy_id,
                decision_summary=t.decision_summary,
                actual_outcome=t.actual_outcome,
                created_at=t.created_at
            )
            for t in trades
        ]

    async def execute_trade(
        self,
        payload: SimTradeCreate,
        check_t1: Optional[bool] = None,
        allow_future: bool = False
    ) -> SimTradeResponse:
        """执行模拟委托买入/卖出（策略跟单或手动模拟）"""
        async with _acquire_trade_mutex():
            account = await self.get_or_create_default_account()
            direction = payload.direction.lower().strip()
            price = round(payload.price, 3)
            qty = int(payload.quantity)
            amount = round(price * qty, 2)
            now = datetime.now()

            # 成交时间防御：严禁指定未来时间试图绕过 T+1 判定
            if payload.trade_time and not allow_future:
                try:
                    t_dt = datetime.strptime(payload.trade_time[:19], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        t_dt = datetime.strptime(payload.trade_time[:10], "%Y-%m-%d")
                    except ValueError:
                        raise HTTPException(status_code=400, detail="成交时间格式无效")
                if t_dt > now:
                    raise HTTPException(
                        status_code=400,
                        detail=f"禁止指定未来成交时间 ({payload.trade_time}) 绕过 A 股 T+1 规则"
                    )

            trade_time_str = payload.trade_time or now.strftime("%Y-%m-%d %H:%M:%S")

            # 优先从服务端权威行情源自动补齐/纠正官方真实标的名称
            stock_name = None
            try:
                q_res = await self.data_service.get_stock_quotes([payload.code])
                if q_res and hasattr(q_res, "data") and q_res.data:
                    for item in q_res.data:
                        c_item = str(item.get("code") or item.get("symbol") or "").lower().replace("sh", "").replace("sz", "").replace("bj", "").strip()
                        c_clean = payload.code.lower().replace("sh", "").replace("sz", "").replace("bj", "").strip()
                        if c_item == c_clean or not c_item:
                            stock_name = item.get("name")
                            break
            except Exception:
                pass
            if not stock_name:
                stock_name = payload.name or payload.code

            stmt_pos = select(SimPosition).where(
                SimPosition.account_id == account.id,
                SimPosition.code == payload.code
            )
            pos = (await self.session.execute(stmt_pos)).scalars().first()

            if direction == "buy":
                # 校验交易日历覆盖范围与可用性（未覆盖年份刚性阻断买入操作）
                try:
                    t_date = datetime.strptime(trade_time_str[:10], "%Y-%m-%d").date()
                    calendar.check_coverage(t_date)
                except CalendarCoverageError as e:
                    raise HTTPException(status_code=500, detail=f"交易日历未覆盖年份，拒绝依赖交易日历的成交操作: {e}")
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"成交时间格式无效: {e}")

                if account.current_capital < amount:
                    raise HTTPException(status_code=400, detail=f"模拟账户可用资金不足: 可用 {account.current_capital:.2f} 元，需 {amount:.2f} 元")

                account.current_capital = round(account.current_capital - amount, 2)

                if pos:
                    new_qty = pos.quantity + qty
                    total_cost = round(pos.quantity * pos.avg_cost + amount, 2)
                    pos.avg_cost = round(total_cost / new_qty, 3)
                    pos.quantity = new_qty
                    pos.current_price = price
                    pos.floating_pnl = 0.0
                else:
                    pos = SimPosition(
                        account_id=account.id,
                        code=payload.code,
                        name=stock_name,
                        quantity=qty,
                        avg_cost=price,
                        current_price=price,
                        floating_pnl=0.0
                    )
                    self.session.add(pos)

            elif direction == "sell":
                # 1. 物理持仓必须存在且数量足够（刚性防线：杜绝任何负持仓与超卖）
                if not pos or pos.quantity <= 0:
                    raise HTTPException(status_code=400, detail=f"模拟账户持仓不足: 标的 {payload.code} 当前无持仓，拟卖出 {qty} 股")
                if pos.quantity < qty:
                    raise HTTPException(status_code=400, detail=f"模拟账户持仓不足: 标的 {payload.code} 当前持仓 {pos.quantity} 股，拟卖出 {qty} 股")

                # 2. 独立核验账本完整性（独立于 T+1，覆盖包括可转债 T+0 在内的所有标的，遇异常刚性抛出 HTTP 409 阻断卖出）
                await self.verify_ledger_integrity(account.id, payload.code)

                # 3. 严格核对 A 股股票 T+1 可卖数量（由服务端可信行情锁定，请求体伪造名称无效）
                should_check = check_t1 if check_t1 is not None else self.enforce_t1
                is_t0 = await self.verify_t0_instrument(payload.code)
                if should_check and not is_t0:
                    available_qty = await self.get_available_quantity(
                        account.id,
                        payload.code,
                        as_of_time=trade_time_str
                    )
                    if qty > available_qty:
                        if available_qty == 0:
                            detail = (
                                f"模拟交易拒绝 (A股T+1规则限制): 标的 {payload.code} 今日买入尚未转为可卖仓 "
                                f"(当前持仓 {pos.quantity} 股，可卖 0 股，拟卖出 {qty} 股)"
                            )
                        else:
                            detail = (
                                f"模拟交易拒绝 (A股T+1规则限制): 标的 {payload.code} 卖出数量超出可卖仓 "
                                f"(当前持仓 {pos.quantity} 股，可卖 {available_qty} 股，当日买入冻结 {pos.quantity - available_qty} 股，拟卖出 {qty} 股)"
                            )
                        raise HTTPException(status_code=400, detail=detail)

                # 3. 最终刚性断言：卖出数量绝不能超出当前物理持仓
                if qty > pos.quantity:
                    raise HTTPException(status_code=400, detail=f"卖出数量 {qty} 严禁超过当前持仓总量 {pos.quantity}")

                realized_pnl = round((price - pos.avg_cost) * qty, 2)
                account.current_capital = round(account.current_capital + amount, 2)
                account.total_pnl = round(account.total_pnl + realized_pnl, 2)

                pos.quantity -= qty
                assert pos.quantity >= 0, "持仓数量不可为负数"
                if pos.quantity == 0:
                    await self.session.delete(pos)
                else:
                    pos.current_price = price
                    pos.floating_pnl = round((price - pos.avg_cost) * pos.quantity, 2)
            else:
                raise HTTPException(status_code=400, detail="不支持的交易方向，仅支持 buy 或 sell")

            trade = SimTrade(
                account_id=account.id,
                code=payload.code,
                name=stock_name,
                direction=direction,
                price=price,
                quantity=qty,
                trade_time=trade_time_str,
                strategy_id=payload.strategy_id,
                decision_summary=payload.decision_summary or "策略实盘模拟交易执行"
            )
            self.session.add(trade)

            await self.session.commit()
            await self.session.refresh(trade)

            return SimTradeResponse(
                id=trade.id,
                account_id=trade.account_id,
                code=trade.code,
                name=trade.name,
                direction=trade.direction,
                price=trade.price,
                quantity=trade.quantity,
                amount=amount,
                trade_time=trade.trade_time,
                strategy_id=trade.strategy_id,
                decision_summary=trade.decision_summary,
                created_at=trade.created_at
            )

    async def get_stats(self) -> SimStatsResponse:
        """获取策略实盘模拟胜率与盈亏比统计"""
        account = await self.get_or_create_default_account()
        positions = await self.get_positions(refresh_quote=True)

        # 完整流水按 id 升序读取，不截断为 200 条
        stmt_trades = (
            select(SimTrade)
            .where(SimTrade.account_id == account.id)
            .order_by(SimTrade.id.asc())
        )
        trades = list((await self.session.execute(stmt_trades)).scalars().all())

        market_value = sum(p.market_value for p in positions)
        total_asset = round(account.current_capital + market_value, 2)
        total_pnl = round(total_asset - account.initial_capital, 2)

        # 重建各代码持仓与平仓交易腿 (移动加权平均成本，与 execute_trade 舍入口径完全一致)
        pos_tracker: Dict[str, Dict[str, Any]] = {}
        closed_leg_pnls: List[float] = []
        win_pnls: List[float] = []
        loss_pnls: List[float] = []
        win_trades = 0
        loss_trades = 0

        for t in trades:
            direction = (t.direction or "").lower().strip()
            price = round(float(t.price), 3)
            qty = int(t.quantity)
            code = t.code

            if direction == "buy":
                if code not in pos_tracker:
                    pos_tracker[code] = {"quantity": qty, "avg_cost": price}
                else:
                    curr = pos_tracker[code]
                    if curr["quantity"] > 0:
                        amount = round(price * qty, 2)
                        new_qty = curr["quantity"] + qty
                        total_cost = round(curr["quantity"] * curr["avg_cost"] + amount, 2)
                        curr["avg_cost"] = round(total_cost / new_qty, 3)
                        curr["quantity"] = new_qty
                    else:
                        curr["quantity"] = qty
                        curr["avg_cost"] = price
            elif direction == "sell":
                curr = pos_tracker.get(code)
                if not curr or curr["quantity"] <= 0:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"模拟交易统计失败: 流水 ID {t.id} 存在无成本卖出异常 "
                            f"(标的代码 {code}, 拟卖出 {qty} 股, 当前持仓 0 股)"
                        ),
                    )

                if curr["quantity"] < qty:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"模拟交易统计失败: 流水 ID {t.id} 存在超卖异常 "
                            f"(标的代码 {code}, 拟卖出 {qty} 股, 当前持仓仅 {curr['quantity']} 股)"
                        ),
                    )

                realized_pnl = round((price - curr["avg_cost"]) * qty, 2)
                curr["quantity"] -= qty
                if curr["quantity"] == 0:
                    curr["avg_cost"] = 0.0

                closed_leg_pnls.append(realized_pnl)
                if realized_pnl > 0:
                    win_trades += 1
                    win_pnls.append(realized_pnl)
                elif realized_pnl < 0:
                    loss_trades += 1
                    loss_pnls.append(realized_pnl)

        total_trades = len(trades)
        closed_trades = len(closed_leg_pnls)

        if closed_trades > 0:
            win_rate = round((win_trades / closed_trades) * 100, 2)
            closed_leg_win_rate = win_rate
        else:
            win_rate = None
            closed_leg_win_rate = None

        if len(win_pnls) > 0 and len(loss_pnls) > 0:
            avg_win = sum(win_pnls) / len(win_pnls)
            avg_loss = abs(sum(loss_pnls) / len(loss_pnls))
            payoff_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else None
        else:
            payoff_ratio = None

        total_realized_pnl = round(sum(closed_leg_pnls), 2) if closed_leg_pnls else 0.0

        return SimStatsResponse(
            total_trades=total_trades,
            win_trades=win_trades,
            loss_trades=loss_trades,
            closed_trades=closed_trades,
            win_rate=win_rate,
            closed_leg_win_rate=closed_leg_win_rate,
            payoff_ratio=payoff_ratio,
            total_pnl=total_pnl,
            total_realized_pnl=total_realized_pnl,
            available_cash=round(account.current_capital, 2),
            market_value=round(market_value, 2),
            total_asset=total_asset
        )

    async def reset_account(self) -> Dict[str, Any]:
        """一键重置策略实盘模拟账户 (资金恢复100万，清空持仓与流水)"""
        account = await self.get_or_create_default_account()
        
        # 删除所有该账户的模拟持仓与流水
        from sqlalchemy import delete
        await self.session.execute(delete(SimPosition).where(SimPosition.account_id == account.id))
        await self.session.execute(delete(SimTrade).where(SimTrade.account_id == account.id))
        
        account.current_capital = account.initial_capital
        account.total_pnl = 0.0
        
        await self.session.commit()
        return {"status": "SUCCESS", "message": "策略实盘模拟账户已重置恢复初始 100 万虚拟资金"}
