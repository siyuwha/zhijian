"""
Phase 2D.0 / 2D.1: Canonical Market Snapshot API Endpoint
GET /api/v1/canonical/market-snapshot/{date}
前端未来唯一合法单向消费的数据载体！
严格分离并承载 MarketTruthSnapshot (FACT + DERIVED) 与 CognitionSnapshot (COGNITION)
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ...core.database import get_db
from ...services.canonical_market_service import CanonicalMarketService
from ...schemas.canonical_market import CanonicalMarketSnapshot
from ...schemas.tactical_briefing import TacticalBriefingReport
from ...services.narrative_context_service import NarrativeContextExtractor
from ...services.constrained_briefing_generator import ConstrainedBriefingGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/canonical", tags=["Canonical Market Truth & Cognition"])


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

