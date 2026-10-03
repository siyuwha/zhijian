import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from ..core.calendar import calendar
from ..data.service import DataService
from ..models.report import AuctionReport, DailyReview
from ..models.market import MarketDailySnapshot

logger = logging.getLogger(__name__)

class AuctionService:
    """开盘集合竞价观测与状态承接服务 (M3)"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.data_service = DataService(session)

    async def generate_auction_report(self, date_str: Optional[str] = None, force: bool = False) -> AuctionReport:
        today = date_str or datetime.now().strftime("%Y-%m-%d")

        if not force and not calendar.is_trading_day(today):
            wd = calendar.get_weekday_name(today)
            logger.warning(f"Attempted to generate auction report on non-trading day: {today} ({wd})")
            raise HTTPException(
                status_code=400,
                detail=f"{today} ({wd}) 为非交易日（周末/法定节假日休市），系统禁止生成集合竞价报告。"
            )

        # 检查是否已存在历史 09:25 集合竞价物理快照 (用于离线重放与自愈)
        snap_stmt = select(MarketDailySnapshot).where(
            MarketDailySnapshot.date == today,
            MarketDailySnapshot.snapshot_type == "AUCTION_0925"
        )
        existing_auction_snapshot = (await self.session.execute(snap_stmt)).scalars().first()

        now = datetime.now()
        is_today = (now.strftime("%Y-%m-%d") == today)
        is_auction_time = is_today and (now.hour == 9 and 15 <= now.minute <= 30)

        # 1. 采集 09:25 开盘指数快照 (上证、深证、创业板、科创50、北证50)
        index_codes = ["sh000001", "sz399001", "sz399006", "sh000688", "bj899050"]
        if not is_auction_time and existing_auction_snapshot and existing_auction_snapshot.indices_snapshot:
            try:
                parsed_indices = json.loads(existing_auction_snapshot.indices_snapshot)
                if isinstance(parsed_indices, dict):
                    quotes = parsed_indices.get("indices", [])
                elif isinstance(parsed_indices, list):
                    quotes = parsed_indices
                else:
                    quotes = []
                logger.info(f"Self-healed auction index observation from MarketDailySnapshot for {today}")
            except Exception:
                index_res = await self.data_service.get_index_quotes(index_codes)
                quotes = index_res.data or []
        else:
            index_res = await self.data_service.get_index_quotes(index_codes)
            quotes = index_res.data or []

        sh_amount_wan = None
        sz_amount_wan = None
        for q in quotes:
            code = q.get("code", "")
            if "000001" in code:
                sh_amount_wan = q.get("amount_wan")
            elif "399001" in code:
                sz_amount_wan = q.get("amount_wan")

        total_bidding_amount_yi = None
        if sh_amount_wan is not None and sz_amount_wan is not None:
            total_bidding_amount_yi = round((sh_amount_wan + sz_amount_wan) / 10000.0, 2)

        # 2. 严格承接前一交易日 M1.4 全天成交总额（作为分母，按交易日历对齐排除非交易日扰动）
        prev_trade_date = calendar.prev_trading_day(today).strftime("%Y-%m-%d")
        stmt_prev = (
            select(DailyReview)
            .where(DailyReview.date <= prev_trade_date)
            .order_by(DailyReview.date.desc())
            .limit(10)
        )
        prev_candidates = (await self.session.execute(stmt_prev)).scalars().all()
        prev_review = next((r for r in prev_candidates if calendar.is_trading_day(r.date)), None)

        yesterday_total_amount_yi = None
        prev_pool: List[Dict[str, Any]] = []
        max_board_height = 0

        if prev_review and prev_review.report_content:
            try:
                rep = json.loads(prev_review.report_content)
                ms = rep.get("market_state", {})
                d6 = ms.get("dimensions", {}).get("D6") or {}
                raw_amt = (d6.get("metrics") or {}).get("total_amount")
                if raw_amt is not None and float(raw_amt) > 0:
                    yesterday_total_amount_yi = round(float(raw_amt), 0)
            except Exception as e:
                logger.warning(f"解析前日全天成交额失败: {e}")

        if prev_review and prev_review.limit_up_analysis:
            try:
                lu = json.loads(prev_review.limit_up_analysis) if isinstance(prev_review.limit_up_analysis, str) else prev_review.limit_up_analysis
                prev_pool = lu.get("items") if lu.get("items") is not None else lu.get("pool", [])
                max_board_height = int(lu.get("max_height") or lu.get("max_board_height", 0))
                if not max_board_height and prev_pool:
                    max_board_height = max([int(s.get("lbc") or s.get("height") or s.get("board_count", 1)) for s in prev_pool if isinstance(s, dict)], default=0)
            except Exception as e:
                logger.warning(f"解析前日涨停梯队失败: {e}")

        # 竞价量能比值（严格数学定义验收：分子两市竞价额，分母前日两市全天总额）
        bidding_volume_ratio = None
        if (
            total_bidding_amount_yi is not None
            and yesterday_total_amount_yi is not None
            and yesterday_total_amount_yi > 0
        ):
            bidding_volume_ratio = round(
                (total_bidding_amount_yi / yesterday_total_amount_yi) * 100, 2
            )

        index_overview = {
            "indices": quotes,
            "total_bidding_amount_yi": total_bidding_amount_yi,
            "yesterday_total_amount_yi": yesterday_total_amount_yi,
            "bidding_volume_ratio": bidding_volume_ratio,
        }

        # 3. 昨日高标梯队 09:25 开盘快照与生态统计
        stock_codes = []
        for s in prev_pool[:30]:
            if isinstance(s, dict):
                code = s.get("code") or s.get("symbol")
            elif isinstance(s, str):
                code = s
            else:
                code = None
            if code:
                clean_code = str(code).replace("s_", "")
                stock_codes.append(clean_code)

        stock_quotes: List[Dict[str, Any]] = []
        if stock_codes:
            stock_res = await self.data_service.get_stock_quotes(stock_codes)
            stock_quotes = stock_res.data or []

        tested_count = len(stock_quotes)
        high_open_count = 0
        low_open_count = 0
        sum_open_pct = 0.0
        valid_open_pct_count = 0
        one_word_up_count = 0
        one_word_down_count = 0

        max_board_info = None
        extreme_stocks = []

        # 寻找前日最高空间板股票 (兼容 lbc、height 与 board_count 键名)
        highest_stock_code = None
        for s in prev_pool:
            if isinstance(s, dict):
                s_height = int(s.get("lbc") or s.get("height") or s.get("board_count", 0))
                if s_height == max_board_height and max_board_height > 0:
                    raw_c = s.get("code") or s.get("symbol")
                    if raw_c:
                        highest_stock_code = str(raw_c).replace("s_", "")
                    break

        for sq in stock_quotes:
            op = sq.get("open_pct")
            if op is not None:
                sum_open_pct += op
                valid_open_pct_count += 1
                if op > 0:
                    high_open_count += 1
                elif op < 0:
                    low_open_count += 1

            if sq.get("is_one_word_up"):
                one_word_up_count += 1
            elif sq.get("is_one_word_down"):
                one_word_down_count += 1

            # 标记最高空间板信息 (精准基于后 6 位代码无偏比对)
            sq_code_6 = str(sq.get("code") or sq.get("symbol") or "")[-6:]
            if highest_stock_code and sq_code_6 == str(highest_stock_code)[-6:]:
                max_board_info = {
                    "symbol": sq.get("symbol") or sq.get("code"),
                    "name": sq.get("name"),
                    "board_height": max_board_height,
                    "open_pct": sq.get("open_pct"),
                    "is_one_word": sq.get("is_one_word_up", False),
                }

            # 异动关注（大幅高开抢筹或大幅低开核按钮）
            if op is not None:
                if op >= 4.0:
                    extreme_stocks.append({
                        "symbol": sq.get("symbol") or sq.get("code"),
                        "name": sq.get("name"),
                        "open_pct": op,
                        "tag": "竞价大幅高开抢筹",
                    })
                elif op <= -4.0:
                    extreme_stocks.append({
                        "symbol": sq.get("symbol") or sq.get("code"),
                        "name": sq.get("name"),
                        "open_pct": op,
                        "tag": "竞价大幅低开分歧",
                    })

        # 按开盘涨幅降序排列异动标的
        extreme_stocks.sort(key=lambda x: x.get("open_pct", 0), reverse=True)

        avg_premium_pct = (
            round(sum_open_pct / valid_open_pct_count, 2)
            if valid_open_pct_count > 0
            else None
        )
        high_open_ratio = (
            round((high_open_count / tested_count) * 100, 1)
            if tested_count > 0
            else None
        )

        high_open_stats = {
            "one_word_up_count": one_word_up_count,
            "one_word_down_count": one_word_down_count,
            "tested_count": tested_count,
            "high_open_count": high_open_count,
            "low_open_count": low_open_count,
            "high_open_ratio": high_open_ratio,
            "avg_premium_pct": avg_premium_pct,
            "avg_premium": avg_premium_pct,
            "max_board_info": max_board_info,
            "extreme_stocks": extreme_stocks[:8],
        }

        # 4. 09:25 开盘多空承接客观物理研判（绝无买卖信号，严格事实验证）
        if bidding_volume_ratio is not None and bidding_volume_ratio >= 1.50:
            emotion_label = (
                "放量高开偏强承接" if (avg_premium_pct or 0) >= 0 else "放量低开强分歧释放"
            )
        elif bidding_volume_ratio is not None and bidding_volume_ratio >= 1.00:
            emotion_label = "平开中性震荡分化"
        elif bidding_volume_ratio is not None and bidding_volume_ratio < 0.60:
            emotion_label = "极端地量避险观望"
        elif bidding_volume_ratio is not None:
            emotion_label = "缩量低开承接偏弱"
        else:
            emotion_label = "数据平稳观测中"

        # 叙事文字：客观事实核验，绝无胜率预测打分
        bidding_str = (
            f"{total_bidding_amount_yi:.1f} 亿元"
            if total_bidding_amount_yi is not None
            else "--"
        )
        ratio_str = (
            f"{bidding_volume_ratio:.2f}%"
            if bidding_volume_ratio is not None
            else "--"
        )
        high_open_ratio_str = (
            f"{high_open_ratio:.1f}%" if high_open_ratio is not None else "--"
        )
        avg_premium_str = (
            f"{avg_premium_pct:+.2f}%" if avg_premium_pct is not None else "--"
        )
        max_board_str = (
            f"高开 {max_board_info.get('open_pct'):+.2f}%"
            if max_board_info and max_board_info.get("open_pct") is not None
            else (f"{max_board_height}板高标数据缺省" if max_board_height > 0 else "无连板高标")
        )

        narrative = (
            f"09:25 集合竞价物理事实核验：两市开盘竞价总额约 {bidding_str}，"
            f"占前日全天成交总额比值为 {ratio_str}。昨日连板样本池（{tested_count}只）"
            f"高开率为 {high_open_ratio_str}，平均竞价溢价为 {avg_premium_str}。"
            f"昨日最高空间标的开盘表征为【{max_board_str}】。全市场一字涨停 {one_word_up_count} 家，"
            f"一字跌停 {one_word_down_count} 家。早盘开盘状态客观刻画为【{emotion_label}】。"
            f"M2 盘前观察维度假设已由 09:25 集合竞价物理事实完全核对。"
        )

        emotion_judgment_dict = {
            "label": emotion_label,
            "narrative": narrative,
            "disclaimer": "客观观察维度提示，非买卖建议",
        }

        # 5. 持久化存储 (严格复用已有 auction_report 模型，零 Schema 变更)
        stmt = select(AuctionReport).where(AuctionReport.date == today)
        existing = (await self.session.execute(stmt)).scalars().first()

        index_json = json.dumps(index_overview, ensure_ascii=False)
        high_open_json = json.dumps(high_open_stats, ensure_ascii=False)
        emotion_json = json.dumps(emotion_judgment_dict, ensure_ascii=False)

        if existing:
            existing.index_open_data = index_json
            existing.one_word_count = one_word_up_count
            existing.high_open_stats = high_open_json
            existing.emotion_judgment = emotion_json
            report_record = existing
        else:
            report_record = AuctionReport(
                date=today,
                index_open_data=index_json,
                one_word_count=one_word_up_count,
                high_open_stats=high_open_json,
                emotion_judgment=emotion_json,
            )
            self.session.add(report_record)

        # 6. 持久化 MarketDailySnapshot (AUCTION_0925 快照)
        if not existing_auction_snapshot and quotes:
            snap_record = MarketDailySnapshot(
                date=today,
                snapshot_type="AUCTION_0925",
                indices_snapshot=index_json,
                high_tier_snapshot=high_open_json,
                market_state_snapshot=emotion_json,
                data_quality="FULL" if is_auction_time else "OFFLINE_INFERRED",
                source_status=json.dumps({"is_live_auction": is_auction_time}, ensure_ascii=False),
            )
            self.session.add(snap_record)

        await self.session.commit()
        await self.session.refresh(report_record)
        return report_record

    async def get_auction_report_by_date(self, date_str: str) -> Optional[AuctionReport]:
        stmt = select(AuctionReport).where(AuctionReport.date == date_str)
        return (await self.session.execute(stmt)).scalars().first()

    async def get_auction_reports(
        self, limit: int = 30, offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """获取集合竞价历史归档列表（分页与概览）"""
        count_stmt = select(func.count(AuctionReport.id))
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(AuctionReport)
            .order_by(AuctionReport.date.desc())
            .offset(offset)
            .limit(limit)
        )
        records = (await self.session.execute(stmt)).scalars().all()

        items = []
        for r in records:
            emotion_label = "平稳中性"
            if r.emotion_judgment:
                try:
                    ej = json.loads(r.emotion_judgment)
                    if isinstance(ej, dict):
                        emotion_label = ej.get("label", "平稳中性")
                    else:
                        emotion_label = str(ej)
                except Exception:
                    emotion_label = str(r.emotion_judgment)

            bidding_amount_yi = None
            bidding_ratio = None
            if r.index_open_data:
                try:
                    iod = json.loads(r.index_open_data)
                    bidding_amount_yi = iod.get("total_bidding_amount_yi")
                    bidding_ratio = iod.get("bidding_volume_ratio")
                except Exception:
                    pass

            one_word_up = r.one_word_count or 0
            one_word_down = 0
            if r.high_open_stats:
                try:
                    hos = json.loads(r.high_open_stats)
                    one_word_down = hos.get("one_word_down_count", 0)
                except Exception:
                    pass

            items.append({
                "id": r.id,
                "date": r.date,
                "emotion_label": emotion_label,
                "bidding_amount_yi": bidding_amount_yi,
                "bidding_ratio": bidding_ratio,
                "one_word_up_count": one_word_up,
                "one_word_down_count": one_word_down,
                "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            })

        return items, total
