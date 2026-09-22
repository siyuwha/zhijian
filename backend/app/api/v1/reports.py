import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from ...core.database import get_db
from ...services.daily_review import DailyReviewService
from ...services.premarket import PremarketService
from ...services.auction import AuctionService

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get("/daily-review/{date}")
async def get_daily_review(date: str, db: AsyncSession = Depends(get_db)):
    service = DailyReviewService(db)
    review = await service.get_review_by_date(date)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found for this date")
    return {
        "code": 200,
        "data": {
            "date": review.date,
            "market_overview": json.loads(review.market_overview) if review.market_overview else [],
            "limit_up_analysis": json.loads(review.limit_up_analysis) if review.limit_up_analysis else {},
            "report_content": json.loads(review.report_content) if review.report_content else {},
            "data_quality": review.data_quality
        }
    }

@router.post("/daily-review/generate")
async def generate_daily_review(date: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    service = DailyReviewService(db)
    review = await service.generate_review(date)
    return {
        "code": 200,
        "message": "Review generated successfully",
        "date": review.date
    }

@router.get("/premarket/{date}")
async def get_premarket_briefing(date: str, db: AsyncSession = Depends(get_db)):
    service = PremarketService(db)
    briefing = await service.get_briefing_by_date(date)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found for this date")
    return {
        "code": 200,
        "data": {
            "date": briefing.date,
            "overnight_summary": json.loads(briefing.overnight_summary) if briefing.overnight_summary else [],
            "news_digest": json.loads(briefing.news_digest) if briefing.news_digest else [],
            "yesterday_review_summary": briefing.yesterday_review_summary,
            "today_focus": json.loads(briefing.today_focus) if briefing.today_focus else []
        }
    }

@router.post("/premarket/generate")
async def generate_premarket_briefing(date: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    service = PremarketService(db)
    briefing = await service.generate_briefing(date)
    return {
        "code": 200,
        "message": "Briefing generated successfully",
        "date": briefing.date
    }
