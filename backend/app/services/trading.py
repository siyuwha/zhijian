from typing import List, Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.trading import TradeRecord, Position, TradeNote

class TradingService:
    """交易记录与持仓管理服务 (M3)"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_trade_record(
        self,
        code: str,
        name: str,
        direction: str,
        price: float,
        quantity: int,
        trade_time: str,
        trade_reason: Optional[str] = None,
        source: str = "manual"
    ) -> TradeRecord:
        amount = round(price * quantity, 2)
        record = TradeRecord(
            code=code,
            name=name,
            direction=direction.lower(),
            price=price,
            quantity=quantity,
            amount=amount,
            trade_time=trade_time,
            trade_reason=trade_reason,
            source=source
        )
        self.session.add(record)
        await self._update_position(code, name, direction.lower(), price, quantity)
        await self.session.commit()
        await self.session.refresh(record)
        return record

    async def _update_position(self, code: str, name: str, direction: str, price: float, quantity: int):
        stmt = select(Position).where(Position.code == code)
        pos = (await self.session.execute(stmt)).scalars().first()

        if direction == "buy":
            if pos:
                new_qty = pos.quantity + quantity
                total_cost = pos.total_cost + (price * quantity)
                pos.quantity = new_qty
                pos.total_cost = total_cost
                pos.avg_cost = round(total_cost / new_qty, 3) if new_qty > 0 else 0.0
            else:
                pos = Position(
                    code=code,
                    name=name,
                    quantity=quantity,
                    avg_cost=price,
                    total_cost=price * quantity,
                    current_price=price,
                    floating_pnl=0.0
                )
                self.session.add(pos)
        elif direction == "sell":
            if pos:
                pos.quantity = max(0, pos.quantity - quantity)
                if pos.quantity == 0:
                    pos.total_cost = 0.0
                else:
                    pos.total_cost = round(pos.quantity * pos.avg_cost, 2)

    async def get_positions(self) -> List[Position]:
        stmt = select(Position).where(Position.quantity > 0)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_records(self, limit: int = 50) -> List[TradeRecord]:
        stmt = select(TradeRecord).order_by(TradeRecord.trade_time.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())

    async def add_trade_note(
        self,
        date: str,
        mental_state: str,
        decision_logic: str,
        reflection: str,
        lessons: str,
        trade_id: Optional[int] = None
    ) -> TradeNote:
        note = TradeNote(
            date=date,
            trade_id=trade_id,
            mental_state=mental_state,
            decision_logic=decision_logic,
            reflection=reflection,
            lessons=lessons
        )
        self.session.add(note)
        await self.session.commit()
        await self.session.refresh(note)
        return note

    async def get_notes(self, trade_id: Optional[int] = None) -> List[TradeNote]:
        stmt = select(TradeNote)
        if trade_id:
            stmt = stmt.where(TradeNote.trade_id == trade_id)
        stmt = stmt.order_by(TradeNote.created_at.desc())
        return list((await self.session.execute(stmt)).scalars().all())
