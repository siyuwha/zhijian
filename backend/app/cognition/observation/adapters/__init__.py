"""
Cognition Observation Fact Adapters Package (Phase 2A Step 3.2 Sandbox)
上位依据：最高董事会工程授权令 BOARD-APPROVAL-20260930-STEP3
核心铁律：Adapter 严格保持“只转换、不决策”（Only Transform, No Decisions）。
"""

from .base import BaseFactAdapter
from .m1_adapter import M1ReviewFactAdapter
from .m2_adapter import M2PremarketFactAdapter
from .m4_adapter import M4AuctionFactAdapter
from .m5_adapter import M5SettlementFactAdapter
from .s4_adapter import S4NewsFactAdapter

__all__ = [
    "BaseFactAdapter",
    "M1ReviewFactAdapter",
    "M2PremarketFactAdapter",
    "M4AuctionFactAdapter",
    "M5SettlementFactAdapter",
    "S4NewsFactAdapter",
]
