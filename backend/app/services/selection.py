from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.strategy import Strategy, SelectionResult, SelectionCandidate
from ..strategy.interfaces import StrategyMode

class SelectionService:
    """策略与选股业务服务 (M6)"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_strategies(self) -> List[Strategy]:
        stmt = select(Strategy).where(Strategy.is_active == 1)
        return list((await self.session.execute(stmt)).scalars().all())

    async def create_strategy(
        self,
        name: str,
        mode: str = StrategyMode.USER_DEFINED.value,
        description: Optional[str] = None,
        conditions: Optional[str] = None,
        universe_config: Optional[str] = None
    ) -> Strategy:
        strat = Strategy(
            name=name,
            mode=mode,
            description=description,
            conditions=conditions or "{}",
            universe_config=universe_config or "{}",
            created_by="user"
        )
        self.session.add(strat)
        await self.session.commit()
        await self.session.refresh(strat)
        return strat
