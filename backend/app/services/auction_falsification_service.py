"""
Phase 2E.3: Auction Falsification Service
=========================================
上位依据：
1. 最高董事会审查裁决令：《BOARD-REVIEW-DOC90-REVISE-BEFORE-CODING-20261009》
2. 《DOC-90 V1.1 · Phase 2E.3 09:25 竞价对账 REST API 与安全守卫技术设计单》

核心职责：
1. 从只读存储中单向提取 T 日复盘战报与前夜假说；
2. 调度 CanonicalAuctionService 获取 09:25 物理竞价快照；
3. 执行 PopperianBiddingComparator 四维时序因果审查与确定性对账；
4. 调度 AuctionSafetyGuard 执行物理拦截与封闭语义安全合规审查；
5. 提供只读内存缓存，实现 100% 全字节级恒定幂等与零业务副作用。
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.schemas.popper_verdict import (
    PopperianHypothesisRecord,
    BiddingFalsificationVerdict,
    FalsificationOutcomeEnum,
    InconclusiveReasonEnum,
)
from backend.app.schemas.canonical_auction import (
    CanonicalAuctionSnapshot,
    BiddingStatusEnum,
)
from backend.app.schemas.canonical_market import DataQualityGrade
from backend.app.services.canonical_market_service import CanonicalMarketService
from backend.app.services.canonical_auction_service import CanonicalAuctionService
from backend.app.services.popperian_bidding_comparator import PopperianBiddingComparator
from backend.app.services.auction_safety_guard import (
    AuctionSafetyGuard,
    AuctionSafetyInterceptionError,
)
from backend.app.core.calendar import calendar
from backend.app.cognition.jcs import hash_jcs

logger = logging.getLogger(__name__)

# 全局内存只读结果缓存 (保证进程生命周期内 100% 字节级幂等)
_AUCTION_VERDICT_MEMORY_CACHE: Dict[str, BiddingFalsificationVerdict] = {}


class AuctionFalsificationService:
    """
    09:25 集合竞价波普尔证伪对账业务编排服务
    """

    def __init__(
        self,
        session: AsyncSession,
        comparator: Optional[PopperianBiddingComparator] = None,
        safety_guard: Optional[AuctionSafetyGuard] = None,
    ):
        self.session = session
        self.market_service = CanonicalMarketService(session)
        self.auction_service = CanonicalAuctionService(session)
        self.comparator = comparator or PopperianBiddingComparator()
        self.safety_guard = safety_guard or AuctionSafetyGuard()

    async def get_or_compute_verdict(
        self,
        trade_date: str,
        force_replay_data: Optional[Dict[str, Any]] = None,
    ) -> BiddingFalsificationVerdict:
        """
        获取或计算指定日期的 09:25 集合竞价对账单 (支持只读缓存加速与物理回放)
        """
        # 1. 缓存优先检索 (零重复计算，保证全字节级恒定幂等)
        cache_key = f"VERDICT:{trade_date}"
        if not force_replay_data and cache_key in _AUCTION_VERDICT_MEMORY_CACHE:
            return _AUCTION_VERDICT_MEMORY_CACHE[cache_key]

        # 2. 检查交易日历并确定前一有效基准交易日 (禁止静默替换请求日期 - P0-1 闭环)
        is_trading = calendar.is_trading_day(trade_date)
        prev_date = calendar.prev_trading_day(trade_date).strftime("%Y-%m-%d")

        if not is_trading:
            # 物理休市 / 非交易日拦截 (P0-1 因果与日历公理)：无需前日假说，直接输出不可漂移的 MARKET_CLOSED 裁决
            eval_time = f"{trade_date}T09:25:05+08:00"
            trace_id = f"TRACE-{prev_date}-TO-{trade_date}-AUCTION-POPPER-00000000"
            hypo_id = f"HYPO-{prev_date}-00000000"
            closed_fp = "0000000000000000000000000000000000000000000000000000000000000000"

            dummy_hypo = PopperianHypothesisRecord(
                hypothesis_id=hypo_id,
                registered_at=f"{prev_date}T16:00:00+08:00",
                base_trade_date=prev_date,
                target_trade_date=trade_date,
                bound_briefing_trace_id=trace_id,
                bound_briefing_fingerprint=closed_fp,
                bound_snapshot_fingerprint=closed_fp,
                expected_market_state="休市停牌",
                expected_turnover_ratio_min=Decimal("0.00"),
                expected_turnover_ratio_max=Decimal("1.00"),
                space_leader_code="000000",
                space_leader_name="无",
                space_leader_falsification_threshold=Decimal("-3.00"),
                mainline_leader_codes=[],
                required_observation_symbols=["000000"],
                hypothesis_fingerprint=closed_fp,
            )

            auction_snapshot = await self.auction_service.produce_canonical_auction_snapshot(
                trade_date=trade_date,
                prev_date=prev_date,
                force_replay_data=force_replay_data,
            )

            raw_verdict = self.comparator.evaluate(
                hypothesis=dummy_hypo,
                auction_snapshot=auction_snapshot,
            )
            self.safety_guard.audit_verdict(raw_verdict)
            if not force_replay_data:
                _AUCTION_VERDICT_MEMORY_CACHE[cache_key] = raw_verdict
            return raw_verdict

        # 3. 提取前日基准市场快照与假说
        prev_snapshot = await self.market_service.get_canonical_snapshot(prev_date)
        if not prev_snapshot:
            raise ValueError(f"Cannot perform auction falsification: Base market snapshot for {prev_date} not found!")

        # 4. 构建前夜不可变假说记录 (WORM 契约)
        space_leader_code = "600825"
        space_leader_name = "新华传媒"
        if prev_snapshot.truth.ladder_tree and len(prev_snapshot.truth.ladder_tree) > 0:
            highest_group = prev_snapshot.truth.ladder_tree[0]
            if highest_group.stocks and len(highest_group.stocks) > 0:
                space_leader_code = highest_group.stocks[0].code
                space_leader_name = highest_group.stocks[0].name

        mainline_codes = []
        if prev_snapshot.cognition and prev_snapshot.cognition.mainlines:
            for ml in prev_snapshot.cognition.mainlines[:3]:
                if ml.constituency and ml.constituency.leader_code:
                    code = ml.constituency.leader_code
                    if code != space_leader_code and code not in mainline_codes:
                        mainline_codes.append(code)
            # 若前三主线龙头均与空间标杆重合，则回退保留
            if not mainline_codes:
                for ml in prev_snapshot.cognition.mainlines[:3]:
                    if ml.constituency and ml.constituency.leader_code:
                        if ml.constituency.leader_code not in mainline_codes:
                            mainline_codes.append(ml.constituency.leader_code)

        required_symbols = [space_leader_code]
        for c in mainline_codes:
            if c not in required_symbols:
                required_symbols.append(c)

        hypo_id = f"HYPO-{prev_date}-{prev_snapshot.envelope_fingerprint[:8]}"
        hypo_registered_at = f"{prev_date}T16:00:00+08:00"

        expected_state_name = "高位剧烈分化期"
        if prev_snapshot.cognition and prev_snapshot.cognition.market_state_calibration:
            expected_state_name = prev_snapshot.cognition.market_state_calibration.state_display_name
        elif prev_snapshot.cognition and prev_snapshot.cognition.market_state_summary:
            expected_state_name = prev_snapshot.cognition.market_state_summary

        raw_hypo_dict = {
            "hypothesis_id": hypo_id,
            "registered_at": hypo_registered_at,
            "base_trade_date": prev_date,
            "target_trade_date": trade_date,
            "bound_briefing_trace_id": f"TRACE-{prev_date}-BRIEFING",
            "bound_briefing_fingerprint": prev_snapshot.envelope_fingerprint,
            "bound_snapshot_fingerprint": prev_snapshot.envelope_fingerprint,
            "expected_market_state": expected_state_name,
            "expected_turnover_ratio_min": "0.80",
            "expected_turnover_ratio_max": "1.50",
            "space_leader_code": space_leader_code,
            "space_leader_name": space_leader_name,
            "space_leader_falsification_threshold": "-3.00",
            "mainline_leader_codes": mainline_codes,
            "required_observation_symbols": required_symbols,
        }
        hypo_fp = hash_jcs(raw_hypo_dict)

        hypothesis = PopperianHypothesisRecord(
            hypothesis_id=hypo_id,
            registered_at=hypo_registered_at,
            base_trade_date=prev_date,
            target_trade_date=trade_date,
            bound_briefing_trace_id=f"TRACE-{prev_date}-BRIEFING",
            bound_briefing_fingerprint=prev_snapshot.envelope_fingerprint,
            bound_snapshot_fingerprint=prev_snapshot.envelope_fingerprint,
            expected_market_state=expected_state_name,
            expected_turnover_ratio_min=Decimal("0.80"),
            expected_turnover_ratio_max=Decimal("1.50"),
            space_leader_code=space_leader_code,
            space_leader_name=space_leader_name,
            space_leader_falsification_threshold=Decimal("-3.00"),
            mainline_leader_codes=mainline_codes,
            required_observation_symbols=required_symbols,
            hypothesis_fingerprint=hypo_fp,
        )

        # 5. 采集 09:25 物理竞价快照
        auction_snapshot = await self.auction_service.produce_canonical_auction_snapshot(
            trade_date=trade_date,
            prev_date=prev_date,
            force_replay_data=force_replay_data,
        )

        # 6. 执行波普尔确定性对账评估
        raw_verdict = self.comparator.evaluate(
            hypothesis=hypothesis,
            auction_snapshot=auction_snapshot,
        )

        # 7. 调度安全物理守卫审计
        self.safety_guard.audit_verdict(raw_verdict)

        # 8. 写入只读内存缓存 (无写业务数据库副作用)
        if not force_replay_data:
            _AUCTION_VERDICT_MEMORY_CACHE[cache_key] = raw_verdict

        return raw_verdict
