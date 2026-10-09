"""
Phase 3A.1: Canonical Intraday Service (盘中微观行情切片与量能投影服务)
======================================================================
上位依据：
1. 最高董事会终审裁决令：《DOC-92 APPROVED WITH REMEDIATIONS & PHASE 3A.1 AUTHORIZED》
2. 《DOC-92 · Phase 3A 盘中 4 阶段动态跟踪与认知偏离实时告警系统技术设计单》

刚性工程准则：
- 严格遵循单向依赖：消费已冻结的 CanonicalMarketSnapshot 与 CanonicalAuctionSnapshot；
- 贯彻 Decimal 高保真与防重算会计准则；
- 落实交易分钟时间衰减量能投影模型 (Zero-Falsification & Real Math)；
- 继承 RFC 8785 JCS 不可变数字指纹与血缘元数据信封。
"""

import json
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.schemas.canonical_intraday import (
    IntradayStageEnum,
    StockIntradayQuote,
    CanonicalIntradayIndexQuote,
    CanonicalIntradaySnapshot,
)
from backend.app.schemas.canonical_auction import CanonicalAuctionSnapshot
from backend.app.schemas.canonical_market import (
    ProvenanceEnvelope,
    TruthSource,
    DataQualityGrade,
    CanonicalMarketSnapshot,
)
from backend.app.services.canonical_market_service import (
    CanonicalMarketService,
    CanonicalSecurityMasterRegistry,
)
from backend.app.services.canonical_auction_service import CanonicalAuctionService
from backend.app.services.briefing_safety_guard import canonical_round_decimal
from backend.app.cognition.jcs import hash_jcs
from backend.app.core.calendar import calendar
from backend.app.data.service import DataService

logger = logging.getLogger(__name__)


def calculate_intraday_stage(time_str: str) -> Tuple[IntradayStageEnum, int]:
    """
    根据采样时间 HH:MM:SS 或 HH:MM 计算盘中 4 阶段时间窗口及已交易分钟数 (0~240)
    """
    parts = [int(p) for p in time_str.split(":")[:2]]
    h, m = parts[0], parts[1]
    t = h * 60 + m

    t_open_am = 9 * 60 + 30    # 09:30 -> 570
    t_stage1_end = 10 * 60     # 10:00 -> 600
    t_close_am = 11 * 60 + 30  # 11:30 -> 690
    t_open_pm = 13 * 60        # 13:00 -> 780
    t_stage3_end = 14 * 60 + 30# 14:30 -> 870
    t_close_pm = 15 * 60       # 15:00 -> 900

    if t < t_open_am:
        return IntradayStageEnum.OFF_MARKET, 0
    elif t_open_am <= t < t_stage1_end:
        elapsed = t - t_open_am
        return IntradayStageEnum.STAGE_1_OPENING, elapsed
    elif t_stage1_end <= t < t_close_am:
        elapsed = 30 + (t - t_stage1_end)
        return IntradayStageEnum.STAGE_2_MORNING, elapsed
    elif t_close_am <= t < t_open_pm:
        return IntradayStageEnum.LUNCH_BREAK, 120
    elif t_open_pm <= t < t_stage3_end:
        elapsed = 120 + (t - t_open_pm)
        return IntradayStageEnum.STAGE_3_AFTERNOON, elapsed
    elif t_stage3_end <= t <= t_close_pm:
        elapsed = 210 + (t - t_stage3_end)
        return IntradayStageEnum.STAGE_4_CLOSING, elapsed
    else:  # t > t_close_pm
        return IntradayStageEnum.OFF_MARKET, 240


def calculate_projected_turnover(
    total_accumulated_yi: Decimal,
    elapsed_minutes: int,
    prev_total_yi: Decimal,
) -> Tuple[Decimal, Decimal]:
    """
    基于交易分钟数时间衰减模型计算全天预估成交额 (亿元) 及量能 Pace 比率 (%)
    
    A 股微观成交衰减曲线规律：
    - 前 30 分钟 (09:30-10:00): 占全天约 28%
    - 早盘后 90 分钟 (10:00-11:30): 占全天约 35% (早盘合计 63%)
    - 午盘前 90 分钟 (13:00-14:30): 占全天约 23% (累计达 86%)
    - 尾盘后 30 分钟 (14:30-15:00): 占全天约 14% (累计达 100%)
    """
    if elapsed_minutes <= 0 or total_accumulated_yi <= Decimal("0.00"):
        return Decimal("0.00"), Decimal("0.00")

    if elapsed_minutes >= 240:
        proj = canonical_round_decimal(total_accumulated_yi, 2)
        pace = (
            canonical_round_decimal((proj / prev_total_yi) * Decimal("100.0"), 2)
            if prev_total_yi > Decimal("0.00")
            else Decimal("0.00")
        )
        return proj, pace

    m = Decimal(str(elapsed_minutes))
    if m <= Decimal("30"):
        p = (m / Decimal("30")) * Decimal("0.28")
    elif m <= Decimal("120"):
        p = Decimal("0.28") + ((m - Decimal("30")) / Decimal("90")) * Decimal("0.35")
    elif m <= Decimal("210"):
        p = Decimal("0.63") + ((m - Decimal("120")) / Decimal("90")) * Decimal("0.23")
    else:
        p = Decimal("0.86") + ((m - Decimal("210")) / Decimal("30")) * Decimal("0.14")

    if p <= Decimal("0.001"):
        p = Decimal("0.001")

    proj = canonical_round_decimal(total_accumulated_yi / p, 2)
    pace = (
        canonical_round_decimal((proj / prev_total_yi) * Decimal("100.0"), 2)
        if prev_total_yi > Decimal("0.00")
        else Decimal("0.00")
    )
    return proj, pace


class CanonicalIntradayService:
    """
    全市场盘中微观事实快照构建与量能投影服务 (Phase 3A.1)
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.market_service = CanonicalMarketService(session)
        self.auction_service = CanonicalAuctionService(session)
        self.data_service = DataService(session)

    async def produce_canonical_intraday_snapshot(
        self,
        trade_date: str,
        snapshot_time: Optional[str] = None,
        prev_date: Optional[str] = None,
        force_replay_data: Optional[Dict[str, Any]] = None,
    ) -> CanonicalIntradaySnapshot:
        """
        生成标准盘中微观事实快照
        """
        # 1. 对齐交易日历与前一基准交易日
        if not prev_date:
            prev_dt = calendar.prev_trading_day(trade_date)
            prev_date = prev_dt.strftime("%Y-%m-%d")

        is_trading = calendar.is_trading_day(trade_date)
        snap_time = snapshot_time or "10:15:00"
        stage, elapsed_minutes = calculate_intraday_stage(snap_time)

        # 2. 非交易日或休市防御
        if not is_trading:
            dummy_envelope = ProvenanceEnvelope(
                source=TruthSource.INTERNAL_CANONICAL_AGGREGATE,
                observed_time=f"{trade_date}T{snap_time}+08:00",
                quality=DataQualityGrade.UNAVAILABLE,
                is_degraded=True,
                degradation_reason="NON_TRADING_DAY_OR_HOLIDAY",
            )
            raw_empty_dict = {
                "trade_date": trade_date,
                "snapshot_time": snap_time,
                "stage": IntradayStageEnum.OFF_MARKET.value,
                "elapsed_trading_minutes": 0,
                "sh_accumulated_turnover_yi": "0.00",
                "sz_accumulated_turnover_yi": "0.00",
                "total_accumulated_turnover_yi": "0.00",
                "prev_total_turnover_yi": "1.00",
                "projected_turnover_yi": "0.00",
                "turnover_pace_ratio_pct": "0.00",
                "indices": [],
                "leader_quotes": [],
                "up_count": 0,
                "down_count": 0,
                "flat_count": 0,
                "limit_up_count": 0,
                "limit_down_count": 0,
                "broken_limit_count": 0,
                "broken_limit_ratio_pct": "0.00",
                "prev_trade_date": prev_date,
                "bound_snapshot_trace_id": f"TRACE-{prev_date}-TO-{trade_date}-CLOSED",
                "bound_snapshot_fingerprint": "0" * 64,
                "bound_auction_trace_id": None,
                "bound_auction_fingerprint": None,
                "is_trading_day": False,
                "data_quality": DataQualityGrade.UNAVAILABLE.value,
                "envelope": dummy_envelope.model_dump(),
            }
            empty_fp = hash_jcs(raw_empty_dict)
            return CanonicalIntradaySnapshot(
                trade_date=trade_date,
                snapshot_time=snap_time,
                stage=IntradayStageEnum.OFF_MARKET,
                elapsed_trading_minutes=0,
                sh_accumulated_turnover_yi=Decimal("0.00"),
                sz_accumulated_turnover_yi=Decimal("0.00"),
                total_accumulated_turnover_yi=Decimal("0.00"),
                prev_total_turnover_yi=Decimal("1.00"),
                projected_turnover_yi=Decimal("0.00"),
                turnover_pace_ratio_pct=Decimal("0.00"),
                indices=[],
                leader_quotes=[],
                up_count=0,
                down_count=0,
                flat_count=0,
                limit_up_count=0,
                limit_down_count=0,
                broken_limit_count=0,
                broken_limit_ratio_pct=Decimal("0.00"),
                prev_trade_date=prev_date,
                bound_snapshot_trace_id=f"TRACE-{prev_date}-TO-{trade_date}-CLOSED",
                bound_snapshot_fingerprint="0" * 64,
                bound_auction_trace_id=None,
                bound_auction_fingerprint=None,
                is_trading_day=False,
                data_quality=DataQualityGrade.UNAVAILABLE,
                envelope=dummy_envelope,
                snapshot_fingerprint=empty_fp,
            )

        # 3. 严格单向加载前一交易日的 CanonicalMarketSnapshot (提取基准事实与观察哨标的)
        prev_snapshot = await self.market_service.get_canonical_snapshot(prev_date)
        if not prev_snapshot:
            raise ValueError(f"Cannot produce intraday snapshot: Base snapshot for {prev_date} not found!")

        bound_snap_fp = prev_snapshot.envelope_fingerprint
        bound_trace_id = f"TRACE-{prev_date}-TO-{trade_date}-INTRADAY"
        prev_total_turnover = Decimal(str(prev_snapshot.truth.turnover.two_markets_total_yi))

        # 提取前日空间标杆与核心主线龙头
        space_leader_code = None
        if prev_snapshot.truth.ladder_tree and len(prev_snapshot.truth.ladder_tree) > 0:
            highest_group = prev_snapshot.truth.ladder_tree[0]
            if highest_group.stocks and len(highest_group.stocks) > 0:
                space_leader_code = highest_group.stocks[0].code

        mainline_leaders: Dict[str, str] = {}
        if prev_snapshot.cognition and prev_snapshot.cognition.mainlines:
            for ml in prev_snapshot.cognition.mainlines[:3]:
                if ml.constituency and ml.constituency.leader_code:
                    mainline_leaders[ml.constituency.leader_code] = ml.sector_name

        # 4. 加载今晨 09:25 竞价快照 (若存在则挂载血缘)
        bound_auc_trace_id = None
        bound_auc_fp = None
        try:
            auc_snap = await self.auction_service.produce_canonical_auction_snapshot(
                trade_date=trade_date, prev_date=prev_date
            )
            if auc_snap and auc_snap.is_trading_day:
                bound_auc_trace_id = auc_snap.bound_snapshot_trace_id
                bound_auc_fp = auc_snap.auction_fingerprint
        except Exception as e:
            logger.warning(f"Auction snapshot link skipped or unavailable for {trade_date}: {e}")

        # 5. 采集/提取盘中真实行情切片
        raw_indices: List[Dict[str, Any]] = []
        raw_stocks: List[Dict[str, Any]] = []
        sh_amt_wan = Decimal("0.00")
        sz_amt_wan = Decimal("0.00")
        up_c = 0
        down_c = 0
        flat_c = 0
        lu_c = 0
        ld_c = 0
        broken_c = 0
        quality_grade = DataQualityGrade.FULL
        source_type = TruthSource.SINA_HQ_STREAM

        if force_replay_data:
            raw_indices = force_replay_data.get("indices", [])
            raw_stocks = force_replay_data.get("stocks", [])
            sh_amt_wan = Decimal(str(force_replay_data.get("sh_amount_wan", 0)))
            sz_amt_wan = Decimal(str(force_replay_data.get("sz_amount_wan", 0)))
            up_c = int(force_replay_data.get("up_count", 0))
            down_c = int(force_replay_data.get("down_count", 0))
            flat_c = int(force_replay_data.get("flat_count", 0))
            lu_c = int(force_replay_data.get("limit_up_count", 0))
            ld_c = int(force_replay_data.get("limit_down_count", 0))
            broken_c = int(force_replay_data.get("broken_limit_count", 0))
            source_type = TruthSource.INTERNAL_CANONICAL_AGGREGATE
        else:
            # 网络实时采集指数与观测标的行情
            target_codes = []
            if space_leader_code:
                target_codes.append(space_leader_code)
            for c in mainline_leaders.keys():
                if c not in target_codes:
                    target_codes.append(c)

            idx_res = await self.data_service.get_stock_quotes(["sh000001", "sz399001"])
            if idx_res and idx_res.data:
                for idx in idx_res.data:
                    c = idx.get("code") or idx.get("symbol") or ""
                    amt = Decimal(str(idx.get("amount_wan") or idx.get("turnover_wan") or 0))
                    if "000001" in c:
                        sh_amt_wan = amt
                    elif "399001" in c:
                        sz_amt_wan = amt
                    raw_indices.append(idx)

            if target_codes:
                stk_res = await self.data_service.get_stock_quotes(target_codes)
                if stk_res and stk_res.data:
                    raw_stocks = stk_res.data

        # 6. 计算累计成交额与预估量能
        sh_amt_yi = canonical_round_decimal(sh_amt_wan / Decimal("10000.0"), 2)
        sz_amt_yi = canonical_round_decimal(sz_amt_wan / Decimal("10000.0"), 2)
        total_amt_yi = canonical_round_decimal(sh_amt_yi + sz_amt_yi, 2)
        projected_yi, pace_ratio = calculate_projected_turnover(
            total_amt_yi, elapsed_minutes, prev_total_turnover
        )

        # 7. 格式化宽基指数
        indices_model_list: List[CanonicalIntradayIndexQuote] = []
        for idx in raw_indices:
            sym = idx.get("symbol") or idx.get("code") or ""
            name = idx.get("name") or ""
            cur = canonical_round_decimal(idx.get("price") or idx.get("current_price") or idx.get("open") or 1.0, 2)
            pc = canonical_round_decimal(idx.get("pre_close") or idx.get("prev_close") or cur, 2)
            chg = canonical_round_decimal(cur - pc, 2)
            pct = canonical_round_decimal(idx.get("pct_change") or ((chg / pc) * Decimal("100.0")), 2)
            amt_yi = canonical_round_decimal(Decimal(str(idx.get("amount_wan") or idx.get("turnover_wan") or 0)) / Decimal("10000.0"), 2)
            indices_model_list.append(
                CanonicalIntradayIndexQuote(
                    symbol=sym,
                    name=name,
                    current_price=cur,
                    pre_close=pc,
                    change_val=chg,
                    pct_change=pct,
                    amount_yi=amt_yi,
                )
            )

        # 8. 解析并校验重点观测标的 (Security Master 规范映射与炸板识别)
        leader_model_list: List[StockIntradayQuote] = []
        for st in raw_stocks:
            raw_code = str(st.get("code") or st.get("symbol") or "")
            clean_code = raw_code.replace("s_", "").replace("sh", "").replace("sz", "").replace("bj", "")
            if not clean_code:
                continue

            canonical_sec = CanonicalSecurityMasterRegistry.resolve(clean_code)
            auth_name = canonical_sec.canonical_name if canonical_sec else (st.get("name") or "未知")
            canonical_sym = canonical_sec.security_id if canonical_sec else f"{clean_code}.SZ"

            prev_c = canonical_round_decimal(st.get("pre_close") or st.get("yesterday_close") or st.get("prev_close") or 1.0, 2)
            open_p = canonical_round_decimal(st.get("open") or st.get("open_price") or prev_c, 2)
            cur_p = canonical_round_decimal(st.get("price") or st.get("current_price") or open_p, 2)
            high_p = canonical_round_decimal(st.get("high") or st.get("high_price") or cur_p, 2)
            low_p = canonical_round_decimal(st.get("low") or st.get("low_price") or cur_p, 2)
            pct_chg = canonical_round_decimal(st.get("pct_change") or (((cur_p - prev_c) / prev_c) * Decimal("100.0")), 2)
            amt_wan = canonical_round_decimal(st.get("amount_wan") or st.get("turnover_wan") or Decimal("0.0"), 2)
            vol_wan = canonical_round_decimal(st.get("volume_wan") or Decimal("0.0"), 2)

            # 涨跌停与炸板识别
            # 涨停参考价 (主板 10%，精确到分)
            limit_up_price = canonical_round_decimal(prev_c * Decimal("1.10"), 2)
            limit_down_price = canonical_round_decimal(prev_c * Decimal("0.90"), 2)
            
            is_lu = bool(st.get("is_limit_up", False) or (cur_p >= limit_up_price and pct_chg >= Decimal("9.80")))
            is_ld = bool(st.get("is_limit_down", False) or (cur_p <= limit_down_price and pct_chg <= Decimal("-9.80")))
            is_broken = bool(
                st.get("is_broken_limit", False) or (high_p >= limit_up_price and cur_p < limit_up_price)
            )

            is_sl = (clean_code == space_leader_code)
            is_ml = (clean_code in mainline_leaders)
            ml_name = mainline_leaders.get(clean_code)

            leader_model_list.append(
                StockIntradayQuote(
                    code=clean_code,
                    name=auth_name,
                    canonical_symbol=canonical_sym,
                    yesterday_close=prev_c,
                    open_price=open_p,
                    current_price=cur_p,
                    high_price=high_p,
                    low_price=low_p,
                    pct_change=pct_chg,
                    turnover_wan=amt_wan,
                    volume_wan=vol_wan,
                    is_limit_up=is_lu,
                    is_broken_limit=is_broken,
                    is_limit_down=is_ld,
                    is_space_leader=is_sl,
                    is_mainline_leader=is_ml,
                    bound_mainline_name=ml_name,
                )
            )

        # 确定性代码排序 (保证哈希幂等性)
        leader_model_list.sort(key=lambda x: x.code)

        # 9. 炸板率计算
        broken_ratio = Decimal("0.00")
        total_limit_trials = lu_c + broken_c
        if total_limit_trials > 0:
            broken_ratio = canonical_round_decimal(
                (Decimal(str(broken_c)) / Decimal(str(total_limit_trials))) * Decimal("100.0"), 2
            )

        envelope = ProvenanceEnvelope(
            source=source_type,
            observed_time=f"{trade_date}T{snap_time}+08:00",
            quality=quality_grade,
            is_degraded=(quality_grade != DataQualityGrade.FULL),
            degradation_reason=None,
        )

        # 10. 计算 JCS SHA-256 规范指纹 (RFC 8785)
        raw_dict_for_hash = {
            "trade_date": trade_date,
            "snapshot_time": snap_time,
            "stage": stage.value,
            "elapsed_trading_minutes": elapsed_minutes,
            "sh_accumulated_turnover_yi": str(sh_amt_yi),
            "sz_accumulated_turnover_yi": str(sz_amt_yi),
            "total_accumulated_turnover_yi": str(total_amt_yi),
            "prev_total_turnover_yi": str(prev_total_turnover),
            "projected_turnover_yi": str(projected_yi),
            "turnover_pace_ratio_pct": str(pace_ratio),
            "indices": [
                {
                    "symbol": i.symbol,
                    "name": i.name,
                    "current_price": str(i.current_price),
                    "pre_close": str(i.pre_close),
                    "change_val": str(i.change_val),
                    "pct_change": str(i.pct_change),
                    "amount_yi": str(i.amount_yi),
                }
                for i in indices_model_list
            ],
            "leader_quotes": [
                {
                    "code": q.code,
                    "name": q.name,
                    "canonical_symbol": q.canonical_symbol,
                    "yesterday_close": str(q.yesterday_close),
                    "open_price": str(q.open_price),
                    "current_price": str(q.current_price),
                    "high_price": str(q.high_price),
                    "low_price": str(q.low_price),
                    "pct_change": str(q.pct_change),
                    "turnover_wan": str(q.turnover_wan),
                    "volume_wan": str(q.volume_wan),
                    "is_limit_up": q.is_limit_up,
                    "is_broken_limit": q.is_broken_limit,
                    "is_limit_down": q.is_limit_down,
                    "is_space_leader": q.is_space_leader,
                    "is_mainline_leader": q.is_mainline_leader,
                    "bound_mainline_name": q.bound_mainline_name,
                }
                for q in leader_model_list
            ],
            "up_count": up_c,
            "down_count": down_c,
            "flat_count": flat_c,
            "limit_up_count": lu_c,
            "limit_down_count": ld_c,
            "broken_limit_count": broken_c,
            "broken_limit_ratio_pct": str(broken_ratio),
            "prev_trade_date": prev_date,
            "bound_snapshot_trace_id": bound_trace_id,
            "bound_snapshot_fingerprint": bound_snap_fp,
            "bound_auction_trace_id": bound_auc_trace_id,
            "bound_auction_fingerprint": bound_auc_fp,
            "is_trading_day": True,
            "data_quality": quality_grade.value,
            "envelope": envelope.model_dump(),
        }
        snap_fp = hash_jcs(raw_dict_for_hash)

        return CanonicalIntradaySnapshot(
            trade_date=trade_date,
            snapshot_time=snap_time,
            stage=stage,
            elapsed_trading_minutes=elapsed_minutes,
            sh_accumulated_turnover_yi=sh_amt_yi,
            sz_accumulated_turnover_yi=sz_amt_yi,
            total_accumulated_turnover_yi=total_amt_yi,
            prev_total_turnover_yi=prev_total_turnover,
            projected_turnover_yi=projected_yi,
            turnover_pace_ratio_pct=pace_ratio,
            indices=indices_model_list,
            leader_quotes=leader_model_list,
            up_count=up_c,
            down_count=down_c,
            flat_count=flat_c,
            limit_up_count=lu_c,
            limit_down_count=ld_c,
            broken_limit_count=broken_c,
            broken_limit_ratio_pct=broken_ratio,
            prev_trade_date=prev_date,
            bound_snapshot_trace_id=bound_trace_id,
            bound_snapshot_fingerprint=bound_snap_fp,
            bound_auction_trace_id=bound_auc_trace_id,
            bound_auction_fingerprint=bound_auc_fp,
            is_trading_day=True,
            data_quality=quality_grade,
            envelope=envelope,
            snapshot_fingerprint=snap_fp,
        )
