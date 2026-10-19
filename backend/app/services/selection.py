from typing import List, Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from ..models.strategy import Strategy, SelectionResult, SelectionCandidate
from ..strategy.interfaces import StrategyMode
from ..strategy.classic_strategies import ClassicStrategyEngine
from ..data.service import DataService
from ..data.providers.tdx_session_manager import tdx_session_manager
from ..services.canonical_market_service import CanonicalMarketService
from ..core.calendar import calendar

class SelectionService:
    """策略与选股业务服务 (M6)"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.data_service = DataService(session)

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

    async def evaluate_classic_strategies(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        执行三大经典策略真实盘面动态推演与标的打分
        """
        target_date = date
        if not target_date:
            now = datetime.now()
            today_str = now.strftime("%Y-%m-%d")
            if calendar.is_trading_day(now.date()) and (now.hour > 8 or (now.hour == 8 and now.minute >= 30)):
                target_date = today_str
            else:
                prev_d = calendar.get_previous_trading_day(now.date())
                target_date = prev_d.strftime("%Y-%m-%d") if prev_d else today_str

        prev_date = target_date
        try:
            cur_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
            prev_d = calendar.get_previous_trading_day(cur_dt)
            if prev_d:
                prev_date = prev_d.strftime("%Y-%m-%d")
        except Exception:
            pass

        # 1. 打捞今日与昨日真实涨停池
        today_pool_res = await self.data_service.get_limit_up_pool(target_date)
        prev_pool_res = await self.data_service.get_limit_up_pool(prev_date)

        today_items = today_pool_res.data.get("items", []) if today_pool_res and today_pool_res.data else []
        prev_items = prev_pool_res.data.get("items", []) if prev_pool_res and prev_pool_res.data else []

        # 2. 汇集所有标的代码，向 TDX 获取实时五档盘口
        codes_set = set()
        for it in today_items:
            if it.get("code"):
                codes_set.add(str(it["code"]))
        for it in prev_items:
            if it.get("code"):
                codes_set.add(str(it["code"]))

        quotes_map: Dict[str, Dict[str, Any]] = {}
        client = tdx_session_manager.get_client()
        if client and codes_set:
            try:
                tdx_quotes = client.get_quotes(list(codes_set)[:40])
                for q in tdx_quotes:
                    if q.get("code"):
                        quotes_map[q["code"]] = q
            except Exception:
                pass

        # 3. 获取大盘五阶段门禁
        canonical_svc = CanonicalMarketService(self.session)
        snap = await canonical_svc.get_canonical_snapshot(target_date)
        market_stage = "REPAIR"
        if snap and snap.cognition:
            calib = getattr(snap.cognition, "market_state_calibration", None)
            if calib and getattr(calib, "primary_state", None):
                st_val = str(calib.primary_state).upper()
                if "EXPANSION" in st_val:
                    market_stage = "RESONANCE"
                elif "HIGH_DIVERGENCE" in st_val:
                    market_stage = "OVERHEAT"
                elif "RECESSION" in st_val:
                    market_stage = "PANIC"
                elif "FREEZING" in st_val:
                    market_stage = "ICE"
                elif "LOW_REBOUND" in st_val or "CHAOTIC" in st_val:
                    market_stage = "REPAIR"

        # 4. 运行 3 大经典策略推演
        weak_to_strong = ClassicStrategyEngine.evaluate_weak_to_strong(
            prev_items, quotes_map, market_stage
        )
        multi_board_dip = ClassicStrategyEngine.evaluate_multi_board_dip(
            today_items, quotes_map, market_stage
        )
        dragon_pullback = ClassicStrategyEngine.evaluate_dragon_pullback(
            prev_items[:8], quotes_map, market_stage
        )

        stage_position_map = {
            "ICE": ("阶段 1 · 冰点期", "0%~10% (防守观望)"),
            "REPAIR": ("阶段 2 · 弱势修复期", "30%~50% (低吸为主)"),
            "RESONANCE": ("阶段 3 · 主升共振期", "70%~100% (顺势重仓)"),
            "OVERHEAT": ("阶段 4 · 高位过热期", "40%~60% (逢高落袋)"),
            "PANIC": ("阶段 5 · 恐慌退潮期", "0%~20% (空仓避险)"),
        }
        stage_name, pos_sug = stage_position_map.get(market_stage, ("阶段 2 · 弱势修复期", "30%~50%"))

        return {
            "code": 200,
            "trade_date": target_date,
            "market_stage": market_stage,
            "market_stage_name": stage_name,
            "suggested_position": pos_sug,
            "strategies": [
                {
                    "id": "weak_to_strong",
                    "name": "竞价弱转强抢筹策略",
                    "description": "昨日分歧/炸板，今日09:25竞价超预期高开且量比>5.0",
                    "candidates_count": len(weak_to_strong),
                    "candidates": weak_to_strong,
                },
                {
                    "id": "multi_board_dip",
                    "name": "连板分歧低吸策略",
                    "description": "2连板及以上高标，分时振荡下杀释放流动性分歧，支撑位低吸",
                    "candidates_count": len(multi_board_dip),
                    "candidates": multi_board_dip,
                },
                {
                    "id": "dragon_pullback",
                    "name": "首板龙回头策略",
                    "description": "前期首板领涨主线，缩量回踩至10日均线企稳",
                    "candidates_count": len(dragon_pullback),
                    "candidates": dragon_pullback,
                },
            ]
        }
