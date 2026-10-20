from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from ...core.database import get_db
from ...services.trading import TradingService
from ...schemas.trading import (
    TradeRecordCreate,
    ReversalTradeCreate,
    CorrectTradeRecordRequest,
    TradeNoteCreate,
)

router = APIRouter(prefix="/trading", tags=["Trading"])

@router.get("/security/search")
async def search_securities(
    q: str = Query(..., min_length=1, description="股票代码/名称/首字母拼音"),
    limit: int = Query(10, ge=1, le=50, description="返回数量"),
    db: AsyncSession = Depends(get_db),
):
    """A股证券主数据与代码/名称/拼音模糊搜索 (P1-A)"""
    service = TradingService(db)
    results = await service.search_securities(query=q, limit=limit)
    return {"code": 200, "data": results}

@router.get("/records")
async def list_records(
    code: Optional[str] = Query(None, description="按股票代码过滤"),
    direction: Optional[str] = Query(None, description="按买卖方向过滤 buy / sell"),
    record_type: Optional[str] = Query(None, description="按记录属性过滤 TRADE / REVERSAL"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
):
    """多维查询历史交易流水"""
    service = TradingService(db)
    result = await service.get_records(code=code, direction=direction, record_type=record_type, page=page, limit=limit)
    return {"code": 200, "data": result}

@router.post("/records")
async def add_record(payload: TradeRecordCreate, db: AsyncSession = Depends(get_db)):
    """录入交易事实并驱动派生持仓更新（支持幂等与60s指纹防重，拦截超卖）"""
    service = TradingService(db)
    record = await service.add_trade_record(payload)
    return {"code": 200, "data": record}

@router.post("/records/reverse")
async def reverse_record(payload: ReversalTradeCreate, db: AsyncSession = Depends(get_db)):
    """对指定错误流水生成红字冲正对冲记录（成对消除，完全复原持仓）"""
    service = TradingService(db)
    rev_record = await service.create_reversal_record(payload)
    return {"code": 200, "data": rev_record}

@router.post("/records/correct")
async def correct_record(payload: CorrectTradeRecordRequest, db: AsyncSession = Depends(get_db)):
    """对既有流水执行审计链安全纠错 (P1-C: 生成冲正消除原交易 + 创建修正新交易)"""
    service = TradingService(db)
    res = await service.correct_trade_record(payload)
    return {"code": 200, "data": res}

@router.get("/records/{id}")
async def get_record(id: int = Path(..., description="交易记录ID"), db: AsyncSession = Depends(get_db)):
    """获取单笔交易明细及附带复盘笔记"""
    service = TradingService(db)
    record_detail = await service.get_record_detail(id)
    return {"code": 200, "data": record_detail}

@router.get("/positions")
async def list_positions(
    refresh_quote: bool = Query(True, description="是否联动获取最新行情与浮盈"),
    db: AsyncSession = Depends(get_db),
):
    """获取当前有效持仓派生快照"""
    service = TradingService(db)
    positions = await service.get_positions(refresh_quote=refresh_quote)
    return {"code": 200, "data": positions}

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """获取严密量化统计指标（单笔卖出胜率、盈亏比、总已实现盈亏，冲正对物理隔离）"""
    service = TradingService(db)
    stats = await service.get_stats()
    return {"code": 200, "data": stats}

@router.post("/notes")
async def add_note(payload: TradeNoteCreate, db: AsyncSession = Depends(get_db)):
    """提交或增量追加交易复盘反思笔记（1:1强绑定）"""
    service = TradingService(db)
    note = await service.add_or_update_note(payload)
    return {"code": 200, "data": note}

@router.get("/notes/{trade_id}")
async def get_note(trade_id: int = Path(..., description="关联交易记录ID"), db: AsyncSession = Depends(get_db)):
    """获取指定交易的复盘笔记"""
    service = TradingService(db)
    note = await service.get_note_by_trade_id(trade_id)
    return {"code": 200, "data": note}

@router.post("/reconcile")
async def reconcile_positions(
    code: Optional[str] = Query(None, description="可选指定股票代码对账"),
    db: AsyncSession = Depends(get_db),
):
    """全量顺序回放历史流水（排除冲正对），核验并重建派生持仓"""
    service = TradingService(db)
    report = await service.reconcile_positions(code=code)
    return {"code": 200, "data": report}

@router.get("/broker/status")
async def get_broker_status():
    """获取真实券商委托通道连接状态（目前用户未接入）"""
    return {
        "code": 200,
        "data": {
            "connected": False,
            "status": "DISCONNECTED",
            "status_label": "未接入",
            "broker_name": None,
            "channel_type": None,
            "account_id": None,
            "message": "当前尚未接入真实券商委托通道。知见系统对真实交易账本执行物理隔离保护，严禁任何策略模拟数据混入。",
            "supported_channels": ["QMT (迅投极速实盘)", "Ptrade (恒生智能实盘)", "交割单 CSV/Excel 导入"]
        }
    }

@router.post("/purge-sim")
async def purge_sim_data(db: AsyncSession = Depends(get_db)):
    """清除误混入真实交易账本的历史策略模拟数据，恢复账本纯净"""
    service = TradingService(db)
    res = await service.purge_simulation_records_from_truth_ledger()
    return {"code": 200, "data": res}
