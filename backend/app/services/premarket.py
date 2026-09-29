import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..data.service import DataService
from ..models.report import PremarketBriefing, DailyReview
from ..models.market import MarketNews

logger = logging.getLogger(__name__)

class PremarketService:
    """盘前简报业务编排服务 (M2)"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.data_service = DataService(session)

    async def generate_briefing(self, date_str: Optional[str] = None) -> PremarketBriefing:
        today = date_str or datetime.now().strftime("%Y-%m-%d")

        # 1. 获取隔夜外盘
        overnight_res = await self.data_service.get_overnight_data()
        overnight_data = overnight_res.data or []

        # 2. 获取盘前最新财经快讯 (Top 10) 并幂等落盘 market_news (P2 标准资讯链)
        news_res = await self.data_service.get_latest_news(count=10)
        news_data = news_res.data or []

        if news_data:
            for item in news_data:
                title = item.get("title", "")
                pub_time = str(item.get("publish_time", ""))
                source = item.get("source", "sina")
                brief = item.get("brief", "")
                if title:
                    stmt_check = select(MarketNews).where(
                        MarketNews.title == title,
                        MarketNews.publish_time == pub_time,
                    )
                    exist_news = (await self.session.execute(stmt_check)).scalars().first()
                    if not exist_news:
                        self.session.add(MarketNews(
                            source=source,
                            title=title,
                            brief=brief,
                            publish_time=pub_time,
                        ))
        else:
            news_data = [{
                "title": "今日早盘财经资讯数据源暂未就绪",
                "brief": "物理数据源断流，保持客观观望",
                "publish_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "source": "system",
            }]

        # 3. 严格继承昨日 M1 纯净状态向量（防标量塌缩）
        stmt = (
            select(DailyReview)
            .where(DailyReview.date < today)
            .order_by(DailyReview.date.desc())
            .limit(1)
        )
        prev_review = (await self.session.execute(stmt)).scalars().first()

        prev_summary_dict: Dict[str, Any] = {
            "date": None,
            "state_label": "数据未就绪",
            "data_quality": "unknown",
            "composite_score": None,
            "total_amount": None,
            "breadth": {"up_count": None, "down_count": None, "up_down_ratio": None},
            "sub_a_structure": {"max_board_height": None, "promotion_rate": None, "score": None},
            "sub_b_extremes": {
                "limit_up_count": None,
                "limit_down_count": None,
                "limit_diff": None,
                "broken_limit_ratio": None,
                "score": None,
            },
            "narrative": "暂无前一交易日复盘记录，保持客观观望。",
        }

        # 提取昨日指标用于推演
        max_board = 0
        limit_down_count = 0
        broken_pct_str = "--"
        total_amount_val = 0.0

        if prev_review and prev_review.report_content:
            try:
                prev_json = json.loads(prev_review.report_content)
                ms = prev_json.get("market_state", {})
                dims = ms.get("dimensions", {})

                d1 = dims.get("D1", {})
                d2 = dims.get("D2", {})
                d3 = dims.get("D3", {})
                d6 = dims.get("D6", {})

                d2_metrics = d2.get("metrics", {})
                d6_metrics = d6.get("metrics", {})

                sub_domains = d3.get("sub_domains") or {}
                sub_a = sub_domains.get("speculative_structure") or {}
                sub_b = sub_domains.get("tail_extremes") or {}

                sub_a_metrics = sub_a.get("metrics") or {}
                sub_b_metrics = sub_b.get("metrics") or {}

                max_board_val = (
                    sub_a_metrics.get("max_board_height", {}).get("raw")
                    if isinstance(sub_a_metrics.get("max_board_height"), dict)
                    else sub_a_metrics.get("max_board_height")
                )
                promotion_rate_val = (
                    sub_a_metrics.get("promotion_rate", {}).get("raw")
                    if isinstance(sub_a_metrics.get("promotion_rate"), dict)
                    else sub_a_metrics.get("promotion_rate")
                )

                limit_up_val = (
                    sub_b_metrics.get("limit_up_count", {}).get("raw")
                    if isinstance(sub_b_metrics.get("limit_up_count"), dict)
                    else sub_b_metrics.get("limit_up_count")
                )
                limit_down_val = (
                    sub_b_metrics.get("limit_down_count", {}).get("raw")
                    if isinstance(sub_b_metrics.get("limit_down_count"), dict)
                    else sub_b_metrics.get("limit_down_count")
                )
                limit_diff_val = (
                    sub_b_metrics.get("limit_diff", {}).get("raw")
                    if isinstance(sub_b_metrics.get("limit_diff"), dict)
                    else sub_b_metrics.get("limit_diff")
                )
                broken_ratio_val = (
                    sub_b_metrics.get("broken_limit_ratio", {}).get("raw")
                    if isinstance(sub_b_metrics.get("broken_limit_ratio"), dict)
                    else sub_b_metrics.get("broken_limit_ratio")
                )

                total_amount_raw = d6_metrics.get("total_amount")
                if total_amount_raw is not None:
                    total_amount_val = round(float(total_amount_raw), 0)

                state_label = ms.get("state_label") or "未定义"
                max_board = int(max_board_val) if max_board_val is not None else 0
                limit_down_count = int(limit_down_val) if limit_down_val is not None else 0
                broken_pct_str = (
                    f"{round(float(broken_ratio_val) * 100, 1)}%"
                    if broken_ratio_val is not None
                    else "--"
                )

                up_cnt = d2_metrics.get("up_count", "--")
                down_cnt = d2_metrics.get("down_count", "--")
                ratio_val = d2_metrics.get("up_down_ratio", "--")

                prev_summary_dict = {
                    "date": prev_review.date,
                    "state_label": state_label,
                    "data_quality": prev_review.data_quality or "unknown",
                    "composite_score": ms.get("composite_score"),
                    "total_amount": total_amount_val if total_amount_val > 0 else None,
                    "breadth": {
                        "up_count": up_cnt,
                        "down_count": down_cnt,
                        "up_down_ratio": ratio_val,
                    },
                    "sub_a_structure": {
                        "max_board_height": max_board if max_board > 0 else None,
                        "promotion_rate": promotion_rate_val,
                        "score": sub_a.get("score"),
                    },
                    "sub_b_extremes": {
                        "limit_up_count": limit_up_val,
                        "limit_down_count": limit_down_count if limit_down_val is not None else None,
                        "limit_diff": limit_diff_val,
                        "broken_limit_ratio": broken_ratio_val,
                        "score": sub_b.get("score"),
                    },
                    "dimensions": dims,
                    "narrative": (
                        f"前一交易日（{prev_review.date}）市场物理状态表征为【{state_label}】，两市成交额约 "
                        f"{total_amount_val if total_amount_val > 0 else '--'} 亿元。全市场连板最高空间为 "
                        f"{max_board if max_board > 0 else '--'} 板，全市场涨跌家数比为 {ratio_val}，"
                        f"真实炸板率为 {broken_pct_str}。"
                    ),
                }
            except Exception as e:
                logger.warning(f"解析前日复盘快照失败: {e}")

        # 4. 今日关注重点客观推演 (4 维观察提示，严禁主观买卖信号)
        # 提取外盘 A50 与美股涨跌
        a50_pct = None
        nasdaq_pct = None
        for item in overnight_data:
            if item.get("code") == "CHA50CFD":
                a50_pct = item.get("pct_change")
            elif item.get("code") == "ixic":
                nasdaq_pct = item.get("pct_change")

        a50_str = f"{a50_pct:+.2f}%" if a50_pct is not None else "数据缺失"
        nasdaq_str = f"{nasdaq_pct:+.2f}%" if nasdaq_pct is not None else "数据缺失"

        today_focus = [
            {
                "dimension": "竞价量能",
                "title": "开盘两市成交比值承接",
                "observation_point": "09:25 集合竞价成交额承接比",
                "analysis": (
                    f"前一交易日两市总成交额约为 {total_amount_val:.0f} 亿元。"
                    if total_amount_val > 0
                    else "前日两市成交额基准未就绪。"
                )
                + " 重点观察今日 09:25 集合竞价开盘成交额占昨日比例，检验早盘交投是否具备持续承接意愿，若竞价缩量明显需防范盘中轮动分化。",
                "disclaimer": "客观观察维度提示，非买卖建议",
            },
            {
                "dimension": "高标溢价",
                "title": (
                    f"昨日最高空间（{max_board}板）开盘竞价溢价"
                    if max_board > 0
                    else "连板高标梯队竞价溢价"
                ),
                "observation_point": "最高连板股竞价溢价率与封单额",
                "analysis": "观察连板空间标的竞价溢价及封单额变化，检验短线投机动能在连板拓维方向的延续性与抗分歧承接力。",
                "disclaimer": "客观观察维度提示，非买卖建议",
            },
            {
                "dimension": "尾部极端",
                "title": f"炸板（{broken_pct_str}）与跌停（{limit_down_count}家）释放修复",
                "observation_point": "开盘跌停撬板力度与冲板回封意愿",
                "analysis": f"前日尾部博弈事实中，跌停家数为 {limit_down_count} 家，真实炸板率为 {broken_pct_str}。早盘重点跟踪跌停个股有无撬板资金介入，评估尾部极端亏钱效应是否迎来物理缓解。",
                "disclaimer": "客观观察维度提示，非买卖建议",
            },
            {
                "dimension": "外盘扰动",
                "title": f"A50 ({a50_str}) 与纳斯达克 ({nasdaq_str}) 扰动映射",
                "observation_point": "宏观权重与科技成长股早盘抗跌性",
                "analysis": f"隔夜富时中国 A50 期货变动 {a50_str}，纳斯达克变动 {nasdaq_str}。关注早盘大盘权重股与科技成长方向在外部冲击下的低开承接意愿及开盘 15 分钟情绪平稳度。",
                "disclaimer": "客观观察维度提示，非买卖建议",
            },
        ]

        # 5. 持久化存储
        stmt = select(PremarketBriefing).where(PremarketBriefing.date == today)
        existing = (await self.session.execute(stmt)).scalars().first()

        overnight_json = json.dumps(overnight_data, ensure_ascii=False)
        news_json = json.dumps(news_data, ensure_ascii=False)
        yesterday_json = json.dumps(prev_summary_dict, ensure_ascii=False)
        focus_json = json.dumps(today_focus, ensure_ascii=False)

        if existing:
            existing.overnight_summary = overnight_json
            existing.news_digest = news_json
            existing.yesterday_review_summary = yesterday_json
            existing.today_focus = focus_json
            briefing_record = existing
        else:
            briefing_record = PremarketBriefing(
                date=today,
                overnight_summary=overnight_json,
                news_digest=news_json,
                yesterday_review_summary=yesterday_json,
                today_focus=focus_json,
            )
            self.session.add(briefing_record)

        await self.session.commit()
        await self.session.refresh(briefing_record)
        return briefing_record

    async def get_briefing_by_date(self, date_str: str) -> Optional[PremarketBriefing]:
        stmt = select(PremarketBriefing).where(PremarketBriefing.date == date_str)
        return (await self.session.execute(stmt)).scalars().first()

    async def get_briefings(self, limit: int = 30, offset: int = 0) -> Tuple[List[Dict[str, Any]], int]:
        """获取盘前简报历史归档列表（带分页与概览）"""
        count_stmt = select(func.count(PremarketBriefing.id))
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            select(PremarketBriefing)
            .order_by(PremarketBriefing.date.desc())
            .offset(offset)
            .limit(limit)
        )
        records = (await self.session.execute(stmt)).scalars().all()

        items = []
        for r in records:
            overnight_list = []
            yesterday_state = "未定义"
            if r.overnight_summary:
                try:
                    overnight_list = json.loads(r.overnight_summary)
                except Exception:
                    pass
            if r.yesterday_review_summary:
                try:
                    yd = json.loads(r.yesterday_review_summary)
                    yesterday_state = yd.get("state_label", "未定义")
                except Exception:
                    pass

            items.append({
                "id": r.id,
                "date": r.date,
                "overnight_summary": overnight_list,
                "yesterday_state_label": yesterday_state,
                "generated_at": r.generated_at.isoformat() if r.generated_at else None,
            })

        return items, total
