"""
Phase 3A.3: Intraday Drift Service (盘中认知偏离判定编排服务)
============================================================
上位依据：
1. 最高董事会终审裁决令：《DOC-92 APPROVED WITH REMEDIATIONS & PHASE 3A.1 AUTHORIZED》
2. 《DOC-92 · Phase 3A 盘中 4 阶段动态跟踪与认知偏离实时告警系统技术设计单》

核心职责：
1. 从只读存储中提取 T 日复盘战报与前夜假说；
2. 调度 CanonicalIntradayService 获取盘中微观事实快照；
3. 执行 IntradayDriftComparator 认知偏离计算与事件判定；
4. 调度 IntradaySafetyGuard 执行物理拦截与封闭语义安全审查；
5. 提供内存只读缓存，实现全字节级恒定幂等与零数据库写副作用。
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.schemas.popper_verdict import (
    PopperianHypothesisRecord,
    AssertionItemVerdict,
    AssertionSeverityEnum,
)
from backend.app.schemas.canonical_intraday import (
    CanonicalIntradaySnapshot,
    IntradayStageEnum,
)
from backend.app.schemas.intraday_drift_verdict import (
    DriftStateEnum,
    DriftInconclusiveReasonEnum,
    IntradayDriftVerdict,
)
from backend.app.services.canonical_market_service import CanonicalMarketService
from backend.app.services.canonical_intraday_service import CanonicalIntradayService
from backend.app.services.intraday_drift_comparator import IntradayDriftComparator
from backend.app.services.intraday_safety_guard import (
    IntradaySafetyGuard,
    IntradaySafetyInterceptionError,
)
from backend.app.core.calendar import calendar
from backend.app.cognition.jcs import hash_jcs

logger = logging.getLogger(__name__)

# 内存只读结果缓存 (保证进程生命周期内 100% 字节级幂等)
_INTRADAY_VERDICT_MEMORY_CACHE: Dict[str, IntradayDriftVerdict] = {}


class IntradayDriftService:
    """
    盘中波普尔证伪与认知偏离编排服务
    """

    def __init__(
        self,
        session: AsyncSession,
        comparator: Optional[IntradayDriftComparator] = None,
        safety_guard: Optional[IntradaySafetyGuard] = None,
    ):
        self.session = session
        self.market_service = CanonicalMarketService(session)
        self.intraday_service = CanonicalIntradayService(session)
        self.comparator = comparator or IntradayDriftComparator()
        self.safety_guard = safety_guard or IntradaySafetyGuard()

    async def get_or_compute_verdict(
        self,
        trade_date: str,
        snapshot_time: Optional[str] = None,
        force_replay_data: Optional[Dict[str, Any]] = None,
    ) -> IntradayDriftVerdict:
        """
        获取或计算指定日期及时间的盘中认知偏离对账单
        """
        time_slot = snapshot_time or "10:30:00"
        cache_key = f"INTRADAY_VERDICT:{trade_date}:{time_slot}"
        if not force_replay_data and cache_key in _INTRADAY_VERDICT_MEMORY_CACHE:
            return _INTRADAY_VERDICT_MEMORY_CACHE[cache_key]

        is_trading = calendar.is_trading_day(trade_date)
        prev_date = calendar.prev_trading_day(trade_date).strftime("%Y-%m-%d")

        # 1. 物理休市 / 非交易日拦截
        if not is_trading:
            eval_time = f"{trade_date}T{time_slot}+08:00"
            trace_id = f"TRACE-{prev_date}-TO-{trade_date}-INTRADAY-00000000"
            hypo_id = f"HYPO-{prev_date}-00000000"
            closed_fp = "0" * 64

            dummy_hypo = PopperianHypothesisRecord(
                hypothesis_id=hypo_id,
                registered_at=f"{prev_date}T18:00:00+08:00",
                base_trade_date=prev_date,
                target_trade_date=trade_date,
                bound_briefing_trace_id=trace_id,
                bound_briefing_fingerprint=closed_fp,
                bound_snapshot_fingerprint=closed_fp,
                expected_market_state="休市停牌",
                expected_turnover_ratio_min=Decimal("0.00"),
                expected_turnover_ratio_max=Decimal("1.00"),
                space_leader_code="000001",
                space_leader_name="休市无标的",
                space_leader_falsification_threshold=Decimal("-3.00"),
                mainline_leader_codes=[],
                required_observation_symbols=["000001"],
                hypothesis_fingerprint=closed_fp,
            )
            dummy_snap = await self.intraday_service.produce_canonical_intraday_snapshot(
                trade_date=trade_date, snapshot_time=time_slot, prev_date=prev_date
            )
            raw_verdict = self.comparator.evaluate_drift(
                hypothesis=dummy_hypo,
                snapshot=dummy_snap,
                evaluation_time=eval_time,
            )
            guarded_verdict = self.safety_guard.audit_verdict(raw_verdict)
            if not force_replay_data:
                _INTRADAY_VERDICT_MEMORY_CACHE[cache_key] = guarded_verdict
            return guarded_verdict

        # 2. 单向加载 T 日市场快照与基准假说
        prev_snapshot = await self.market_service.get_canonical_snapshot(prev_date)
        if not prev_snapshot:
            raise ValueError(f"Base market snapshot for {prev_date} not found")

        # 提取空间标杆与核心主线
        space_leader_code = "000001"
        space_leader_name = "暂无空间标杆"
        if prev_snapshot.truth.ladder_tree and len(prev_snapshot.truth.ladder_tree) > 0:
            highest_group = prev_snapshot.truth.ladder_tree[0]
            if highest_group.stocks and len(highest_group.stocks) > 0:
                space_leader_code = highest_group.stocks[0].code
                space_leader_name = highest_group.stocks[0].name

        mainline_codes: list[str] = []
        if prev_snapshot.cognition and prev_snapshot.cognition.mainlines:
            for ml in prev_snapshot.cognition.mainlines[:3]:
                if ml.constituency and ml.constituency.leader_code:
                    mainline_codes.append(ml.constituency.leader_code)

        bound_trace_id = f"TRACE-{prev_date}-TO-{trade_date}-INTRADAY-{prev_snapshot.envelope_fingerprint[:8]}"
        hypo_id = f"HYPO-{prev_date}-{prev_snapshot.envelope_fingerprint[:8]}"
        expected_state_name = "高位剧烈分化期"
        if prev_snapshot.cognition and prev_snapshot.cognition.market_state_calibration:
            expected_state_name = prev_snapshot.cognition.market_state_calibration.state_display_name
        elif prev_snapshot.cognition and prev_snapshot.cognition.market_state_summary:
            expected_state_name = prev_snapshot.cognition.market_state_summary

        raw_hypo_dict = {
            "hypothesis_id": hypo_id,
            "registered_at": f"{prev_date}T18:00:00+08:00",
            "base_trade_date": prev_date,
            "target_trade_date": trade_date,
            "bound_briefing_trace_id": bound_trace_id,
            "bound_briefing_fingerprint": prev_snapshot.envelope_fingerprint,
            "bound_snapshot_fingerprint": prev_snapshot.envelope_fingerprint,
            "expected_market_state": expected_state_name,
            "expected_turnover_ratio_min": Decimal("8.00"),
            "expected_turnover_ratio_max": Decimal("15.00"),
            "space_leader_code": space_leader_code,
            "space_leader_name": space_leader_name,
            "space_leader_falsification_threshold": Decimal("-3.00"),
            "mainline_leader_codes": mainline_codes,
            "required_observation_symbols": [space_leader_code] + mainline_codes,
        }
        hypo_fp = hash_jcs({k: str(v) if isinstance(v, Decimal) else v for k, v in raw_hypo_dict.items()})
        hypothesis = PopperianHypothesisRecord(**raw_hypo_dict, hypothesis_fingerprint=hypo_fp)

        # 3. 生产/获取盘中微观事实快照
        intraday_snapshot = await self.intraday_service.produce_canonical_intraday_snapshot(
            trade_date=trade_date,
            snapshot_time=time_slot,
            prev_date=prev_date,
            force_replay_data=force_replay_data,
        )

        # 4. 执行波普尔判定器裁判 (固化 evaluated_at 以实现字节幂等)
        eval_time = f"{trade_date}T{time_slot}+08:00"
        raw_verdict = self.comparator.evaluate_drift(
            hypothesis=hypothesis,
            snapshot=intraday_snapshot,
            evaluation_time=eval_time,
        )

        # 5. 安全守卫合规审查
        guarded_verdict = self.safety_guard.audit_verdict(raw_verdict)

        # 6. 存入只读缓存
        if not force_replay_data:
            _INTRADAY_VERDICT_MEMORY_CACHE[cache_key] = guarded_verdict

        return guarded_verdict
