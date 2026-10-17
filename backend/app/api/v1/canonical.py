"""
Phase 2D.0 / 2D.1: Canonical Market Snapshot API Endpoint
GET /api/v1/canonical/market-snapshot/{date}
前端未来唯一合法单向消费的数据载体！
严格分离并承载 MarketTruthSnapshot (FACT + DERIVED) 与 CognitionSnapshot (COGNITION)
"""
import logging
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ...core.database import get_db
from ...models.market import MarketDailySnapshot
from ...models.report import DailyReview
from ...services.canonical_market_service import CanonicalMarketService
from ...schemas.canonical_market import CanonicalMarketSnapshot
from ...schemas.tactical_briefing import TacticalBriefingReport
from ...services.narrative_context_service import NarrativeContextExtractor
from ...services.constrained_briefing_generator import ConstrainedBriefingGenerator

from ...core.calendar import calendar

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/canonical", tags=["Canonical Market Truth & Cognition"])


@router.get("/latest-date")
async def get_latest_market_date(
    db: AsyncSession = Depends(get_db),
):
    """
    获取系统中最新的市场复盘/快照基准日期
    当今日为有效交易日且已到盘前准备时间 (>= 08:30)，返回今日；
    当今日为周末或休市日，返回数据库中最近的完整交易日。
    """
    try:
        from zoneinfo import ZoneInfo
        cst = ZoneInfo("Asia/Shanghai")
        now = datetime.now(cst)
    except Exception:
        now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    # 1. 如果今天是A股正常交易日，且已经过了早上 08:30 (北京时间)，优先认定今天为最新基准交易日
    if calendar.is_trading_day(now.date()) and (now.hour > 8 or (now.hour == 8 and now.minute >= 30)):
        return {"code": 200, "data": {"latest_date": today_str}}

    # 2. 否则查找历史最近的 EOD_CLOSE
    stmt = (
        select(MarketDailySnapshot.date)
        .where(MarketDailySnapshot.snapshot_type == "EOD_CLOSE")
        .order_by(MarketDailySnapshot.date.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    latest = result.scalar_one_or_none()

    if not latest:
        stmt_any = (
            select(MarketDailySnapshot.date)
            .order_by(MarketDailySnapshot.date.desc())
            .limit(1)
        )
        res_any = await db.execute(stmt_any)
        latest = res_any.scalar_one_or_none()

    if not latest:
        stmt_rev = (
            select(DailyReview.date)
            .order_by(DailyReview.date.desc())
            .limit(1)
        )
        res_rev = await db.execute(stmt_rev)
        latest = res_rev.scalar_one_or_none()

    if not latest:
        if calendar.is_trading_day(now.date()):
            latest = today_str
        else:
            latest = calendar.prev_trading_day(now.date()).strftime("%Y-%m-%d")

    return {"code": 200, "data": {"latest_date": str(latest)}}


@router.get("/market-snapshot/{date}", response_model=CanonicalMarketSnapshot)
async def get_canonical_market_snapshot(
    date: str,
    db: AsyncSession = Depends(get_db),
):
    """
    获取指定日期的标准市场真相与认知快照
    """
    service = CanonicalMarketService(db)
    snapshot = await service.get_canonical_snapshot(date)
    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail=f"Canonical market snapshot for {date} not found in storage",
        )
    return snapshot


@router.get("/tactical-briefing/{date}", response_model=TacticalBriefingReport)
async def get_tactical_briefing(
    date: str,
    db: AsyncSession = Depends(get_db),
):
    """
    获取指定日期的受约束操盘手内参实战战报 (Phase 2D.3)
    双轨制安全防线：BriefingSafetyGuard 硬拦截审查 + 3ms 确定性保底兜底
    """
    service = CanonicalMarketService(db)
    snapshot = await service.get_canonical_snapshot(date)
    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail=f"Canonical market snapshot for {date} not found in storage",
        )
    # 计算底层物理快照哈希与关联追踪 Trace ID (可审计血缘链路)
    import hashlib
    raw_snapshot_json = snapshot.model_dump_json()
    snapshot_hash = hashlib.sha256(raw_snapshot_json.encode("utf-8")).hexdigest()
    trace_id = f"TRACE-{date}-API-{hashlib.sha256((raw_snapshot_json + date).encode('utf-8')).hexdigest()[:12]}"

    extractor = NarrativeContextExtractor()
    context = extractor.extract_context(snapshot)
    generator = ConstrainedBriefingGenerator()
    briefing = generator.generate_briefing(
        contract=context,
        trace_id=trace_id,
        source_snapshot_hash=snapshot_hash,
    )
    return briefing


# =========================================================================
# Phase 2E.3: 09:25 集合竞价波普尔证伪对账单 REST API
# =========================================================================
import os
import re
from ...schemas.popper_verdict import BiddingFalsificationVerdict
from ...services.auction_falsification_service import AuctionFalsificationService
from ...services.auction_safety_guard import AuctionSafetyInterceptionError
from ...services.popperian_bidding_comparator import CausalTemporalViolationError

ENABLE_PHASE2E_AUCTION_API = os.getenv("ENABLE_PHASE2E_AUCTION_API", "true").lower() == "true"


@router.get("/auction-falsification/{date}", response_model=BiddingFalsificationVerdict)
async def get_auction_falsification(
    date: str,
    db: AsyncSession = Depends(get_db),
):
    """
    获取指定日期的 09:25 集合竞价波普尔证伪自动对账单 (Phase 2E.3)
    纯只读、确定性、不可伪造，强制流经 AuctionSafetyGuard 拦截审查
    """
    if not ENABLE_PHASE2E_AUCTION_API:
        raise HTTPException(
            status_code=503,
            detail={"error_code": "ERR_FEATURE_FLAG_DISABLED", "message": "Phase 2E auction API is currently disabled"},
        )

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(
            status_code=400,
            detail={"error_code": "ERR_INVALID_DATE_FORMAT", "message": f"Date '{date}' is invalid, must be YYYY-MM-DD"},
        )

    try:
        service = AuctionFalsificationService(db)
        verdict = await service.get_or_compute_verdict(trade_date=date)
        return verdict
    except CausalTemporalViolationError as e:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "ERR_CAUSAL_TEMPORAL_VIOLATION", "message": str(e)},
        )
    except AuctionSafetyInterceptionError as e:
        raise HTTPException(
            status_code=500,
            detail=e.to_safe_error_detail(),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "ERR_BASE_BRIEFING_NOT_FOUND", "message": str(e)},
        )
    except Exception as e:
        logger.error(f"[CANONICAL ERROR] {type(e)}: {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error_code": "ERR_UPSTREAM_AUCTION_UNAVAILABLE", "message": str(e)},
        )


# =========================================================================
# Phase 3A.3: 盘中波普尔证伪与认知偏离实时告警 REST API
# =========================================================================
from ...schemas.intraday_drift_verdict import IntradayDriftVerdict
from ...services.intraday_drift_service import IntradayDriftService
from ...services.intraday_safety_guard import IntradaySafetyInterceptionError
from ...services.intraday_drift_comparator import CausalTemporalViolationError as IntradayCausalViolationError

ENABLE_PHASE3A_INTRADAY_API = os.getenv("ENABLE_PHASE3A_INTRADAY_API", "true").lower() == "true"


@router.get("/intraday-drift/{date}", response_model=IntradayDriftVerdict)
async def get_intraday_drift_verdict(
    date: str,
    time: Optional[str] = None,
    time_str: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    获取指定日期及时间窗口的盘中波普尔认知偏离对账单 (Phase 3A.3)
    纯只读、确定性、不可伪造，强制流经 IntradaySafetyGuard 拦截审查
    """
    target_time = time or time_str

    if not ENABLE_PHASE3A_INTRADAY_API:
        raise HTTPException(
            status_code=503,
            detail={"error_code": "ERR_FEATURE_FLAG_DISABLED", "message": "Phase 3A intraday API is currently disabled"},
        )

    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(
            status_code=400,
            detail={"error_code": "ERR_INVALID_DATE_FORMAT", "message": f"Date '{date}' is invalid, must be YYYY-MM-DD"},
        )

    if target_time and not re.match(r"^\d{2}:\d{2}(:\d{2})?$", target_time):
        raise HTTPException(
            status_code=400,
            detail={"error_code": "ERR_INVALID_TIME_FORMAT", "message": f"Time '{target_time}' is invalid, must be HH:MM or HH:MM:SS"},
        )

    try:
        service = IntradayDriftService(db)
        verdict = await service.get_or_compute_verdict(trade_date=date, snapshot_time=target_time)
        return verdict
    except IntradayCausalViolationError as e:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "ERR_CAUSAL_TEMPORAL_VIOLATION", "message": str(e)},
        )
    except IntradaySafetyInterceptionError as e:
        raise HTTPException(
            status_code=500,
            detail=e.to_safe_error_detail(),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "ERR_BASE_DATA_NOT_FOUND", "message": str(e)},
        )
    except Exception as e:
        logger.error(f"[CANONICAL INTRADAY ERROR] {type(e)}: {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={"error_code": "ERR_UPSTREAM_INTRADAY_UNAVAILABLE", "message": str(e)},
        )


# =========================================================================
# Phase 3B: 4 大固定时段 LLM 盘中操盘内参时间轴与 Top 5 题材分时资金接口
# =========================================================================
from ...schemas.intraday_briefing import IntradayBriefingTimelineResponse, TopSectorsTrendResponse
from ...services.intraday_briefing_service import IntradayBriefingService


@router.get("/intraday-briefings/{date}", response_model=IntradayBriefingTimelineResponse)
async def get_intraday_briefings_timeline(
    date: str,
    time: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    获取指定交易日的 4 大固定时段盘中操盘内参时间轴 (绝不覆盖早先时段)
    时段 1: 09:26:00 竞价定调
    时段 2: 10:15:00 早盘初战
    时段 3: 11:30:30 午盘综述
    时段 4: 14:15:00 变盘前哨
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(
            status_code=400,
            detail={"error_code": "ERR_INVALID_DATE_FORMAT", "message": f"Date '{date}' is invalid, must be YYYY-MM-DD"},
        )

    try:
        service = IntradayBriefingService(db)
        timeline = await service.get_or_compute_timeline(trade_date=date, current_time=time)
        return timeline
    except Exception as e:
        logger.error(f"[INTRADAY BRIEFING ERROR] {type(e)}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error_code": "ERR_INTRADAY_BRIEFING_FAILED", "message": str(e)},
        )


@router.get("/intraday-top-sectors-trend", response_model=TopSectorsTrendResponse)
async def get_intraday_top_sectors_trend(
    date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    获取 Top 5 题材分时资金走势曲线与领涨核心龙头联动数据
    """
    try:
        service = IntradayBriefingService(db)
        res = await service.get_top_sectors_trend(trade_date=date)
        return res
    except Exception as e:
        logger.error(f"[TOP SECTORS TREND ERROR] {type(e)}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error_code": "ERR_TOP_SECTORS_TREND_FAILED", "message": str(e)},
        )


class GameCognitionRequest(BaseModel):
    trade_date: str
    stocks: List[Dict[str, Any]] = []
    strongest_stock: Optional[Dict[str, Any]] = None
    sectors: List[Dict[str, Any]] = []
    force_refresh: bool = False


@router.post("/intraday-game-cognition")
async def get_intraday_game_cognition(
    req: GameCognitionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    基于入选核心个股与题材，调用 LLM 生成富有博弈洞见的深度复盘总结
    """
    from ...services.micro_game_cognition_service import MicroGameCognitionService
    try:
        res = await MicroGameCognitionService.generate_game_cognition(
            trade_date=req.trade_date,
            stocks=req.stocks,
            strongest_stock=req.strongest_stock,
            sectors=req.sectors,
            force_refresh=req.force_refresh,
        )
        return {"code": 200, "data": res}
    except Exception as e:
        logger.error(f"[GAME COGNITION ERROR]: {e}", exc_info=True)
        return {
            "code": 200,
            "data": MicroGameCognitionService._generate_heuristic_cognition(
                req.stocks, req.strongest_stock, req.sectors
            ),
        }



