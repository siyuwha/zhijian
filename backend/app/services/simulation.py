from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.simulation import SimAccount, SimTrade, SimPosition

class SimulationService:
    """前向模拟交易与决策闭环服务 (M8)"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_accounts(self) -> List[SimAccount]:
        stmt = select(SimAccount).where(SimAccount.is_active == 1)
        return list((await self.session.execute(stmt)).scalars().all())

    async def create_account(self, name: str, initial_capital: float = 100000.0) -> SimAccount:
        acc = SimAccount(
            name=name,
            initial_capital=initial_capital,
            current_capital=initial_capital,
            total_pnl=0.0
        )
        self.session.add(acc)
        await self.session.commit()
        await self.session.refresh(acc)
        return acc

    async def get_positions(self, account_id: int) -> List[SimPosition]:
        stmt = select(SimPosition).where(SimPosition.account_id == account_id, SimPosition.quantity > 0)
        return list((await self.session.execute(stmt)).scalars().all())
