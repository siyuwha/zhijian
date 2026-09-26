import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ...core.database import get_db
from ...models.cognition import CognitionMarketState
from ...cognition.market_state import market_state_computer
from ...cognition.config import MarketStateV1Config
from ...services.cognition_review import CognitionReviewService
from ...schemas.cognition import (
    DiagnosisConfirmPayload,
    MarketHypothesisCreate,
)

router = APIRouter(prefix="/cognition", tags=["Cognition"])

# =========================================================================
# 既有端点 (保持不动)
# =========================================================================

@router.get("/market-state/{date}")
async def get_market_state(date: str, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(CognitionMarketState)
        .where(CognitionMarketState.date == date)
        .order_by(CognitionMarketState.id.desc())
    )
    record = (await db.execute(stmt)).scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="Cognition market state not found")

    return {
        "code": 200,
        "data": {
            "date": record.date,
            "timestamp": record.timestamp,
            "composite_score": record.composite_score,
            "state_label": record.state_label,
            "indicators": json.loads(record.indicators) if record.indicators else [],
            "data_quality": record.data_quality,
        },
    }

@router.get("/config/indicators")
async def get_indicators_config():
    """获取当前可配置的指标体系与权重"""
    return {"code": 200, "data": market_state_computer.config.model_dump()}

@router.put("/config/indicators")
async def update_indicators_config(config: MarketStateV1Config):
    """更新指标体系与权重设置"""
    market_state_computer.update_config(config)
    return {
        "code": 200,
        "message": "Indicators config updated successfully",
        "data": market_state_computer.config.model_dump(),
    }

# =========================================================================
# 验证闭环增强新端点 (G1-Cognition MVP)
# =========================================================================

# 1. 单笔交易认知诊断
@router.post("/diagnosis/trade/{trade_id}")
async def trigger_trade_diagnosis(trade_id: int, db: AsyncSession = Depends(get_db)):
    """触发或重新生成单笔交易双层认知诊断"""
    service = CognitionReviewService(db)
    diag = await service.diagnose_trade(trade_id)
    return {
        "code": 200,
        "message": "Diagnosis generated successfully",
        "data": {
            "id": diag.id,
            "trade_id": diag.trade_id,
            "date": diag.date,
            "trade_price": diag.trade_price,
            "trade_quantity": diag.trade_quantity,
            "trade_amount": diag.trade_amount,
            "trade_direction": diag.trade_direction,
            "market_d1_d6_snapshot": json.loads(diag.market_d1_d6_snapshot) if diag.market_d1_d6_snapshot else {},
            "post_trade_mdd": diag.post_trade_mdd,
            "post_trade_max_profit": diag.post_trade_max_profit,
            "env_match_type": diag.env_match_type,
            "env_match_score": diag.env_match_score,
            "logic_realization": diag.logic_realization,
            "cognitive_gap_analysis": diag.cognitive_gap_analysis,
            "human_status": diag.human_status,
            "human_comment": diag.human_comment,
            "created_at": diag.created_at,
            "updated_at": diag.updated_at,
        },
    }

@router.get("/diagnosis/trade/{trade_id}")
async def get_trade_diagnosis(trade_id: int, db: AsyncSession = Depends(get_db)):
    """查询单笔交易诊断结果"""
    service = CognitionReviewService(db)
    diag = await service.get_trade_diagnosis(trade_id)
    if not diag:
        raise HTTPException(status_code=404, detail=f"交易记录 #{trade_id} 尚未生成诊断")

    return {
        "code": 200,
        "data": {
            "id": diag.id,
            "trade_id": diag.trade_id,
            "date": diag.date,
            "trade_price": diag.trade_price,
            "trade_quantity": diag.trade_quantity,
            "trade_amount": diag.trade_amount,
            "trade_direction": diag.trade_direction,
            "market_d1_d6_snapshot": json.loads(diag.market_d1_d6_snapshot) if diag.market_d1_d6_snapshot else {},
            "post_trade_mdd": diag.post_trade_mdd,
            "post_trade_max_profit": diag.post_trade_max_profit,
            "env_match_type": diag.env_match_type,
            "env_match_score": diag.env_match_score,
            "logic_realization": diag.logic_realization,
            "cognitive_gap_analysis": diag.cognitive_gap_analysis,
            "human_status": diag.human_status,
            "human_comment": diag.human_comment,
            "created_at": diag.created_at,
            "updated_at": diag.updated_at,
        },
    }

@router.put("/diagnosis/trade/{trade_id}/confirm")
async def confirm_trade_diagnosis(
    trade_id: int, payload: DiagnosisConfirmPayload, db: AsyncSession = Depends(get_db)
):
    """人工审定确认采纳或修正诊断 (HITL 人机回环)"""
    service = CognitionReviewService(db)
    diag = await service.confirm_trade_diagnosis(trade_id, payload)
    return {
        "code": 200,
        "message": f"Diagnosis status updated to {diag.human_status}",
        "data": {
            "id": diag.id,
            "trade_id": diag.trade_id,
            "human_status": diag.human_status,
            "human_comment": diag.human_comment,
            "updated_at": diag.updated_at,
        },
    }

# 2. 周度认知复盘
@router.get("/audit/weekly")
async def get_weekly_audit(
    week_offset: int = Query(0, description="周偏移量，0为本周，1为上周"),
    db: AsyncSession = Depends(get_db),
):
    """调取周度认知复盘三维客观度量 (严格隔离未确认样本)"""
    service = CognitionReviewService(db)
    data = await service.get_weekly_audit(week_offset)
    return {"code": 200, "data": data}

# 3. 跨日推演假说跟踪器
@router.post("/hypotheses")
async def create_hypothesis(payload: MarketHypothesisCreate, db: AsyncSession = Depends(get_db)):
    """创建跨交易日推演假说 (进入 PENDING 待锁状态)"""
    service = CognitionReviewService(db)
    hypo = await service.create_hypothesis(payload)
    return {
        "code": 200,
        "message": "Market hypothesis created successfully",
        "data": {
            "id": hypo.id,
            "created_date": hypo.created_date,
            "target_date": hypo.target_date,
            "hypothesis_type": hypo.hypothesis_type,
            "target_asset": hypo.target_asset,
            "expected_scenario": hypo.expected_scenario,
            "premise_logic": hypo.premise_logic,
            "expected_phenomenon": hypo.expected_phenomenon,
            "invalidation_condition": hypo.invalidation_condition,
            "assertion_metrics": json.loads(hypo.assertion_metrics) if hypo.assertion_metrics else None,
            "status": hypo.status,
            "created_at": hypo.created_at,
        },
    }

@router.get("/hypotheses")
async def get_hypotheses(
    target_date: Optional[str] = Query(None, description="目标日期 YYYY-MM-DD"),
    status: Optional[str] = Query(None, description="状态过滤 PENDING/LOCKED/VERIFYING/CLOSED"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """查询推演假说列表 (含关联的竞价与收盘双独立验证快照)"""
    service = CognitionReviewService(db)
    res = await service.get_hypotheses(target_date, status, page, limit)
    return {"code": 200, "data": res}

@router.post("/hypotheses/{id}/verify")
async def verify_hypothesis(
    id: int,
    stage: str = Query(..., description="验证时段: AUCTION_0925 或 CLOSE_1530"),
    db: AsyncSession = Depends(get_db),
):
    """触发客观事实验证状态机 (联合唯一键支持双阶段独立快照追加)"""
    service = CognitionReviewService(db)
    v = await service.verify_hypothesis(id, stage)
    return {
        "code": 200,
        "message": f"Hypothesis verified at stage {stage}",
        "data": {
            "id": v.id,
            "hypothesis_id": v.hypothesis_id,
            "verification_stage": v.verification_stage,
            "actual_data_snapshot": json.loads(v.actual_data_snapshot) if v.actual_data_snapshot else {},
            "outcome": v.outcome,
            "accuracy_score": v.accuracy_score,
            "deviation_analysis": v.deviation_analysis,
            "gap_summary": v.gap_summary,
            "verified_at": v.verified_at,
        },
    }
