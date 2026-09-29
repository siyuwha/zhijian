import asyncio
import logging
from typing import Optional
from .base import BaseProvider
from ..capabilities import DataQuality, DataResult, SettlementCapability

logger = logging.getLogger(__name__)

class BaostockProvider(BaseProvider, SettlementCapability):
    """
    Baostock 日线结算数据适配器
    参考 G1 规则：
    baostock 结算可能存在延迟，若失败或延迟则降级标记 PARTIAL
    """

    def __init__(self):
        super().__init__(
            name="baostock",
            implementation_status="已接入",
            connectivity_verified="已验证",
            schema_verified="已验证",
            semantic_verified="已验证",
            production_eligible="准入",
        )

    async def is_available(self) -> bool:
        return True

    def _sync_fetch_settlement(self, code: str, date: str) -> Optional[dict]:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != '0':
            logger.warning(f"baostock login error: {lg.error_msg}")
            return None

        try:
            # 格式化代码，如 sh.000001
            bs_code = code
            if not ("." in code):
                if code.startswith("sh") or code.startswith("sz"):
                    bs_code = f"{code[:2]}.{code[2:]}"

            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,code,open,high,low,close,preclose,volume,amount,pctChg",
                start_date=date,
                end_date=date,
                frequency="d",
                adjustflag="3"
            )

            data_list = []
            while (rs.error_code == '0') and rs.next():
                data_list.append(rs.get_row_data())

            if data_list:
                row = data_list[0]
                return {
                    "date": row[0],
                    "code": row[1],
                    "open": float(row[2]) if row[2] else 0.0,
                    "high": float(row[3]) if row[3] else 0.0,
                    "low": float(row[4]) if row[4] else 0.0,
                    "close": float(row[5]) if row[5] else 0.0,
                    "prev_close": float(row[6]) if row[6] else 0.0,
                    "volume": float(row[7]) if row[7] else 0.0,
                    "amount": float(row[8]) if row[8] else 0.0,
                    "pct_change": float(row[9]) if row[9] else 0.0,
                }
            return None
        finally:
            bs.logout()

    async def get_daily_settlement(self, code: str, date: str) -> DataResult:
        try:
            # 在线程池中执行同步 baostock 查询
            data = await asyncio.to_thread(self._sync_fetch_settlement, code, date)
            if data:
                return DataResult(data=data, quality=DataQuality.FULL, provider=self.name)
            else:
                return DataResult(
                    data=None,
                    quality=DataQuality.PARTIAL,
                    provider=self.name,
                    error_message=f"Baostock no data for {code} on {date}"
                )
        except Exception as e:
            logger.error(f"Baostock get_daily_settlement failed: {e}")
            return DataResult(data=None, quality=DataQuality.FAILED, provider=self.name, error_message=str(e))
