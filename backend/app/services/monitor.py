from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from ..data.service import DataService

class MonitorService:
    """
    盘中市场结构观察服务 (M5)
    严格遵守 G1 三层观察边界：
    1. 短线情绪层 (涨停/连板/高标)
    2. 核心结构层 (市场核心辨识度龙头)
    3. 资金趋势结构层 (容量中军/趋势中枢)
    """

    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session
        self.data_service = DataService(session)

    async def get_market_structure_snapshot(self) -> dict:
        # 1. 短线情绪层观察
        limit_up_res = await self.data_service.get_limit_up_pool()
        limit_up_data = limit_up_res.data or {}

        # 2. 指数与核心观察标的实时快照
        core_index_codes = ["s_sh000001", "s_sz399001", "s_sz399006", "s_sh000688"]
        index_res = await self.data_service.get_index_quotes(core_index_codes)

        return {
            "indices": index_res.data or [],
            "emotion_layer": {
                "total_limit_up": limit_up_data.get("total_count", 0),
                "max_height": limit_up_data.get("max_height", 0),
                "top_reasons": limit_up_data.get("top_reasons", []),
                "high_board_items": [i for i in limit_up_data.get("items", []) if i.get("lbc", 0) >= 2][:10]
            },
            "core_structure_layer": {
                "description": "市场核心高辨识度标的观察（待配置标的库）",
                "leaders": []
            },
            "capital_trend_layer": {
                "description": "容量中军与趋势核心标的观察（待配置标的库）",
                "trend_cores": []
            }
        }
