from fastapi import APIRouter
from .market import router as market_router
from .reports import router as reports_router
from .trading import router as trading_router
from .strategy import router as strategy_router
from .simulation import router as simulation_router
from .cognition import router as cognition_router
from .system import router as system_router

router = APIRouter()
router.include_router(market_router)
router.include_router(reports_router)
router.include_router(trading_router)
router.include_router(strategy_router)
router.include_router(simulation_router)
router.include_router(cognition_router)
router.include_router(system_router)

__all__ = ["router"]
