import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
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

logger = logging.getLogger(__name__)

class SimulationService:
    """策略实盘模拟交易与沙盒管理服务 (与真实券商账户物理隔离)"""

    def __init__(self, session: AsyncSession, data_service: Optional[DataService] = None):
        self.session = session
        self.data_service = data_service or DataService()

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

    async def get_positions(self, refresh_quote: bool = True) -> List[SimPositionResponse]:
        """获取策略模拟持仓快照（支持实时行情对齐）"""
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

            result.append(SimPositionResponse(
                id=pos.id,
                account_id=pos.account_id,
                code=pos.code,
                name=pos.name or pos.code,
                quantity=pos.quantity,
                avg_cost=pos.avg_cost,
                total_cost=round(pos.quantity * pos.avg_cost, 2),
                current_price=latest_price,
                market_value=mkt_val,
                floating_pnl=flt_pnl,
                floating_pnl_pct=flt_pct,
                updated_at=pos.updated_at
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

    async def execute_trade(self, payload: SimTradeCreate) -> SimTradeResponse:
        """执行模拟委托买入/卖出（策略跟单或手动模拟）"""
        account = await self.get_or_create_default_account()
        direction = payload.direction.lower().strip()
        price = round(payload.price, 3)
        qty = int(payload.quantity)
        amount = round(price * qty, 2)
        trade_time_str = payload.trade_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 检查标的名称自动补齐
        stock_name = payload.name
        if not stock_name or stock_name == payload.code:
            try:
                q_res = await self.data_service.get_stock_quotes([payload.code])
                if q_res and q_res.data and len(q_res.data) > 0:
                    stock_name = q_res.data[0].get("name") or payload.code
            except Exception:
                stock_name = payload.code

        stmt_pos = select(SimPosition).where(
            SimPosition.account_id == account.id,
            SimPosition.code == payload.code
        )
        pos = (await self.session.execute(stmt_pos)).scalars().first()

        if direction == "buy":
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
            if not pos or pos.quantity < qty:
                available = pos.quantity if pos else 0
                raise HTTPException(status_code=400, detail=f"模拟账户可用持仓不足: 当前可用 {available} 股，拟卖出 {qty} 股")

            realized_pnl = round((price - pos.avg_cost) * qty, 2)
            account.current_capital = round(account.current_capital + amount, 2)
            account.total_pnl = round(account.total_pnl + realized_pnl, 2)

            pos.quantity -= qty
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
