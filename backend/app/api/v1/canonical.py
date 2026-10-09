"""
Phase 2D.0 / 2D.1: Canonical Market Snapshot API Endpoint
GET /api/v1/canonical/market-snapshot/{date}
前端未来唯一合法单向消费的数据载体！
严格分离并承载 MarketTruthSnapshot (FACT + DERIVED) 与 CognitionSnapshot (COGNITION)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from ...core.database import get_db
from ...services.canonical_market_service import CanonicalMarketService
from ...schemas.canonical_market import CanonicalMarketSnapshot
from ...schemas.tactical_briefing import TacticalBriefingReport
from ...services.narrative_context_service import NarrativeContextExtractor
from ...services.constrained_briefing_generator import ConstrainedBriefingGenerator

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
