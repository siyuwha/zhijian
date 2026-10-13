import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from ...core.database import get_db
from ...services.daily_review import DailyReviewService
from ...services.premarket import PremarketService
from ...services.auction import AuctionService

from ...models.cognition import CognitionMarketState

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get("/daily-review")
async def list_daily_reviews(
    limit: int = 30,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    service = DailyReviewService(db)
    items, total = await service.get_reviews(limit=limit, offset=offset)
    return {
        "code": 200,
        "data": {
            "items": items,
            "total": total
        }
    }

@router.get("/daily-review/{date}")
async def get_daily_review(date: str, db: AsyncSession = Depends(get_db)):
    service = DailyReviewService(db)
    review = await service.get_review_by_date(date)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found for this date")

    market_overview = json.loads(review.market_overview) if review.market_overview else []
    limit_up_analysis = json.loads(review.limit_up_analysis) if review.limit_up_analysis else {}
    report_content = json.loads(review.report_content) if review.report_content else {}

    # 提取结构化 market_state（优先从 report_content 获取，兜底从 CognitionMarketState 表查）
    market_state = report_content.get("market_state")
    if not market_state and review.market_state_id:
        cog_record = await db.get(CognitionMarketState, review.market_state_id)
        if cog_record:
            market_state = {
                "composite_score": cog_record.composite_score,
                "state_label": cog_record.state_label,
                "data_quality": cog_record.data_quality,
                "dimensions": json.loads(cog_record.indicators) if cog_record.indicators else {},
                "missing_metrics": []
            }

    # 提取或补全「知见」11章全景深度复盘数据
    transcendent_review = report_content.get("transcendent_review")
    if not transcendent_review:
        try:
            from ...services.zhijian_transcendent_review_service import zhijian_transcendent_service
            raw_indices = report_content.get("indices") or market_overview or []
            raw_limit_up = report_content.get("limit_up") or limit_up_analysis or {}
            raw_breadth = report_content.get("breadth") or {}

            # 计算两市去重成交额
            total_turnover_str = "--"
            if raw_indices:
                sum_wan = sum(float(i.get("amount_wan") or 0) for i in raw_indices if "000001" in str(i.get("code", "")) or "399001" in str(i.get("code", "")))
                if sum_wan > 100000000:
                    total_turnover_str = f"{(sum_wan / 100000000):.2f} 万亿元"
                elif sum_wan > 10000:
                    total_turnover_str = f"{(sum_wan / 10000):.0f} 亿元"

            facts = {
                "date": date,
                "indices": raw_indices,
                "turnover": report_content.get("turnover") or {"total_amount": total_turnover_str, "shrinkage_amount": "--", "shrinkage_pct": "--"},
                "breadth": raw_breadth,
                "limit_up": raw_limit_up,
                "audit_delta": report_content.get("audit_delta") or [],
                "market_state": market_state or report_content.get("market_state") or {}
            }
            transcendent_review = await zhijian_transcendent_service.generate_transcendent_review(facts)
        except Exception:
            transcendent_review = None

    return {
        "code": 200,
        "data": {
            "id": review.id,
            "date": review.date,
            "market_overview": market_overview,
            "limit_up_analysis": limit_up_analysis,
            "market_state": market_state,
            "transcendent_review": transcendent_review,
            "report_content": report_content,
            "data_quality": review.data_quality,
            "generated_at": review.generated_at.isoformat() if review.generated_at else None
        }
    }

@router.post("/daily-review/generate")
async def generate_daily_review(date: Optional[str] = None, force: bool = False, db: AsyncSession = Depends(get_db)):
    service = DailyReviewService(db)
    review = await service.generate_review(date, force=force)
    if review is None:
        hb = service.last_heartbeat
        reason_str = "；".join(hb.reasons) if hb else "市场处于休市状态"
        msg = f"数据源通信正常：物理心跳确认为休市状态（{reason_str}），无需生成复盘。"
        return {
            "code": 200,
            "status": "MARKET_CLOSED",
            "message": msg,
            "data": {
                "status": "MARKET_CLOSED",
                "market_status": "CLOSED",
                "message": msg,
                "target_date": date or datetime.now().strftime("%Y-%m-%d"),
                "last_active_date": hb.last_active_date if hb else None,
                "confirm_type": hb.confirm_type if hb else "CLOSED",
                "reasons": hb.reasons if hb else []
            }
        }
    return {
        "code": 200,
        "status": "SUCCESS",
        "message": "Review generated successfully",
        "date": review.date,
        "data": {
            "id": review.id,
            "date": review.date
        }
    }

class ReviewChatRequest(BaseModel):
    date: str
    query: str
    chapter: Optional[str] = None
    history: Optional[List[Dict[str, str]]] = None

@router.post("/daily-review/chat")
async def chat_daily_review(payload: ReviewChatRequest, db: AsyncSession = Depends(get_db)):
    """向「知见」AI 认知推演助手深入提问接口 (支持全量研报上下文与多轮追问)"""
    service = DailyReviewService(db)
    review = await service.get_review_by_date(payload.date)
    context_text = ""
    if review and review.report_content:
        try:
            rc = json.loads(review.report_content)
            tr = rc.get("transcendent_review")
            if tr:
                context_text = tr.get("markdown_content", "")
        except Exception:
            pass

    from ...services.zhijian_transcendent_review_service import zhijian_transcendent_service
    if not context_text:
        context_text = zhijian_transcendent_service.get_baseline_review_md() or ""

    answer = await zhijian_transcendent_service.ask_ai_cognitive_query(
        query=payload.query,
        review_context=context_text,
        conversation_history=payload.history
    )
    return {
        "code": 200,
        "data": {
            "query": payload.query,
            "answer": answer,
            "date": payload.date
        }
    }

@router.get("/premarket")
async def list_premarket_briefings(
    limit: int = 30,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    service = PremarketService(db)
    items, total = await service.get_briefings(limit=limit, offset=offset)
    return {
        "code": 200,
        "data": {
            "items": items,
            "total": total
        }
    }

@router.get("/premarket/{date}")
async def get_premarket_briefing(date: str, db: AsyncSession = Depends(get_db)):
    service = PremarketService(db)
    briefing = await service.get_briefing_by_date(date)
    if not briefing:
        raise HTTPException(status_code=404, detail="Briefing not found for this date")

    overnight_summary = json.loads(briefing.overnight_summary) if briefing.overnight_summary else []
    news_digest = json.loads(briefing.news_digest) if briefing.news_digest else []
    
    yesterday_review_summary = None
    if briefing.yesterday_review_summary:
        try:
            yesterday_review_summary = json.loads(briefing.yesterday_review_summary)
        except Exception:
            yesterday_review_summary = briefing.yesterday_review_summary

    today_focus = json.loads(briefing.today_focus) if briefing.today_focus else []

    return {
        "code": 200,
        "data": {
            "id": briefing.id,
            "date": briefing.date,
            "overnight_summary": overnight_summary,
            "news_digest": news_digest,
            "yesterday_review_summary": yesterday_review_summary,
            "today_focus": today_focus,
            "generated_at": briefing.generated_at.isoformat() if briefing.generated_at else None
        }
    }

@router.post("/premarket/generate")
async def generate_premarket_briefing(date: Optional[str] = None, force: bool = False, db: AsyncSession = Depends(get_db)):
    service = PremarketService(db)
    briefing = await service.generate_briefing(date, force=force)
    return {
        "code": 200,
        "message": "Briefing generated successfully",
        "date": briefing.date
    }

@router.get("/auction")
async def list_auction_reports(
    limit: int = 30,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    service = AuctionService(db)
    items, total = await service.get_auction_reports(limit=limit, offset=offset)
    return {
        "code": 200,
        "data": {
            "items": items,
            "total": total
        }
    }

@router.get("/auction/{date}")
async def get_auction_report(date: str, db: AsyncSession = Depends(get_db)):
    service = AuctionService(db)
    report = await service.get_auction_report_by_date(date)
    if not report:
        raise HTTPException(status_code=404, detail="Auction report not found for this date")

    index_open_data = json.loads(report.index_open_data) if report.index_open_data else {}
    high_open_stats = json.loads(report.high_open_stats) if report.high_open_stats else {}

    emotion_judgment = {}
    if report.emotion_judgment:
        try:
            ej = json.loads(report.emotion_judgment)
            emotion_judgment = ej if isinstance(ej, dict) else {
                "label": str(ej),
                "narrative": str(ej),
                "disclaimer": "客观观察维度提示，非买卖建议"
            }
        except Exception:
            emotion_judgment = {
                "label": str(report.emotion_judgment),
                "narrative": str(report.emotion_judgment),
                "disclaimer": "客观观察维度提示，非买卖建议"
            }

    return {
        "code": 200,
        "data": {
            "id": report.id,
            "date": report.date,
            "index_open_data": index_open_data,
            "one_word_count": report.one_word_count or 0,
            "high_open_stats": high_open_stats,
            "emotion_judgment": emotion_judgment,
            "generated_at": report.generated_at.isoformat() if report.generated_at else None
        }
    }

@router.post("/auction/generate")
async def generate_auction_report(date: Optional[str] = None, force: bool = False, db: AsyncSession = Depends(get_db)):
    service = AuctionService(db)
    report = await service.generate_auction_report(date, force=force)
    if report is None:
        hb = service.last_heartbeat
        reason_str = "；".join(hb.reasons) if hb else "集合竞价无物理撮合"
        msg = f"数据源通信正常：集合竞价物理确认为休市状态（{reason_str}），无需生成竞价报告。"
        return {
            "code": 200,
            "status": "MARKET_CLOSED",
            "message": msg,
            "data": {
                "status": "MARKET_CLOSED",
                "market_status": "CLOSED",
                "message": msg,
                "target_date": date or datetime.now().strftime("%Y-%m-%d"),
                "last_active_date": hb.last_active_date if hb else None,
                "confirm_type": hb.confirm_type if hb else "CLOSED",
                "reasons": hb.reasons if hb else []
            }
        }
    return {
        "code": 200,
        "status": "SUCCESS",
        "message": "Auction report generated successfully",
        "date": report.date,
        "data": {
            "id": report.id,
            "date": report.date
        }
    }


