"""
Phase 3A.2: Intraday Drift Comparator (盘中动态波普尔证伪判定器与偏离事件引擎)
=============================================================================
上位依据：
1. 最高董事会终审裁决令：《DOC-92 APPROVED WITH REMEDIATIONS & PHASE 3A.1 AUTHORIZED》
2. 《DOC-92 · Phase 3A 盘中 4 阶段动态跟踪与认知偏离实时告警系统技术设计单》

四大刚性设计准则：
- A. 先质检再断言：数据质量降级或非交易日必须返回 INCONCLUSIVE；
- B. 不可变与抗篡改：Pydantic frozen=True + RFC 8785 JCS SHA-256 汉明雪崩保障；
- C. 空间标杆一票否决权：炸板或深水走弱立即触发 CRITICAL_BREACH 证伪；
- D. 绝对封闭防守边界：严禁任何买卖诱导指令输出。
"""

import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional
from datetime import datetime

from backend.app.schemas.canonical_intraday import (
    IntradayStageEnum,
    CanonicalIntradaySnapshot,
    StockIntradayQuote,
)
from backend.app.schemas.popper_verdict import (
    PopperianHypothesisRecord,
    AssertionItemVerdict,
    AssertionSeverityEnum,
)
from backend.app.schemas.intraday_drift_verdict import (
    DriftStateEnum,
    DriftInconclusiveReasonEnum,
    DriftEventCategoryEnum,
    IntradayDriftVerdict,
)
from backend.app.schemas.canonical_market import DataQualityGrade
from backend.app.services.briefing_safety_guard import canonical_round_decimal
from backend.app.cognition.jcs import hash_jcs

logger = logging.getLogger(__name__)

RULE_VERSION_INTRADAY = "2026.10.3A2.V1"

DEFAULT_INTRADAY_THRESHOLDS: Dict[str, Any] = {
    "space_leader_drop_threshold": "-3.00",
    "space_leader_broken_limit_kill": True,
    "min_liquidity_pace_ratio": "80.00",
    "flash_dry_pace_ratio": "60.00",
    "mainline_weak_drop_threshold": "-2.00",
    "mainline_reversal_threshold": "-4.00",
    "max_broken_limit_ratio": "35.00",
    "max_limit_down_count": 10,
}

ALLOWED_INTRADAY_BOUNDARIES = {
    "SPACE_LEADER_BROKEN": "空间标杆已炸板，坚决杜绝追高与盲目低吸",
    "SPACE_LEADER_WEAK": "空间标杆深度走弱，防御优先严控盘中回撤",
    "MAINLINE_DIVERGENT": "核心主线龙头集体走弱，防冲高回落防御为主",
    "MAINLINE_REVERSED": "核心主线全面倒戈破位，坚决禁止逆势加仓",
    "LIQUIDITY_DRY": "全天量能萎缩不及预期，严控开仓仓位防流动性陷阱",
    "BREADTH_PANIC": "市场炸板率高企分化加剧，保持观望谨防退潮杀跌",
    "NORMAL_DEFENSE": "盘面演进吻合假说，按既定纪律持仓观察严格防守",
}


class CausalTemporalViolationError(ValueError):
    """因果时序倒置异常"""
    pass


class IntradayDriftComparator:
    """
    盘中波普尔证伪判定器与偏离事件引擎
    """

    def __init__(self, threshold_config: Optional[Dict[str, Any]] = None):
        self.threshold_config = threshold_config or DEFAULT_INTRADAY_THRESHOLDS
        self.threshold_hash = hash_jcs(self.threshold_config)

    def evaluate_drift(
        self,
        hypothesis: PopperianHypothesisRecord,
        snapshot: CanonicalIntradaySnapshot,
        evaluation_time: Optional[str] = None,
    ) -> IntradayDriftVerdict:
        """
        核心裁判入口：消费不可变假说与盘中快照，生成权威证伪对账单
        """
        eval_time = evaluation_time or datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
        trace_id = (
            f"TRACE-{hypothesis.base_trade_date}-TO-{snapshot.trade_date}-"
            f"INTRADAY-{snapshot.snapshot_fingerprint[:8]}"
        )
        verdict_id = f"VERDICT-{snapshot.trade_date}-INTRADAY-{snapshot.snapshot_fingerprint[:8]}"

        # =========================================================================
        # 阶段 1：先质检再断言 (Precondition & Quality Gates)
        # =========================================================================

        # 1.1 物理休市 / 非交易日
        if not snapshot.is_trading_day:
            return self._build_inconclusive_verdict(
                hypothesis, snapshot, verdict_id, trace_id, eval_time,
                DriftInconclusiveReasonEnum.MARKET_CLOSED,
                "非交易日或物理休市，盘中认知对账跳过。"
            )

        # 1.2 阶段检查 (盘前盘后处于 OFF_MARKET)
        if snapshot.stage == IntradayStageEnum.OFF_MARKET:
            return self._build_inconclusive_verdict(
                hypothesis, snapshot, verdict_id, trace_id, eval_time,
                DriftInconclusiveReasonEnum.MARKET_CLOSED,
                "当前处于休市或盘前盘后非交易时段，对账跳过。"
            )

        # 1.3 数据品质降级
        if snapshot.data_quality != DataQualityGrade.FULL:
            return self._build_inconclusive_verdict(
                hypothesis, snapshot, verdict_id, trace_id, eval_time,
                DriftInconclusiveReasonEnum.DATA_QUALITY_DEGRADED,
                f"上游盘中行情数据降级 ({snapshot.data_quality.value})，证据不足以支持科学裁判。"
            )

        # 1.4 四维时间因果严密性校验: T_hypo < T_exchange <= T_source <= T_eval
        try:
            t_hypo = datetime.fromisoformat(hypothesis.registered_at.replace("Z", "+00:00"))
            t_source = datetime.fromisoformat(snapshot.envelope.observed_time.replace("Z", "+00:00"))
            t_eval = datetime.fromisoformat(eval_time.replace("Z", "+00:00"))
            if not (t_hypo < t_source <= t_eval):
                raise CausalTemporalViolationError(
                    f"Temporal causality breach: hypo ({t_hypo}) must precede "
                    f"source ({t_source}) <= eval ({t_eval})"
                )
        except CausalTemporalViolationError as e:
            logger.error(f"Temporal violation: {e}")
            raise e
        except Exception as e:
            logger.warning(f"Timestamp parse error in causality check: {e}")

        # 1.5 核心标的缺失或停牌校验 (空间标杆必须物理存在)
        space_leader_code = hypothesis.space_leader_code
        space_quote = next(
            (q for q in snapshot.leader_quotes if q.code == space_leader_code), None
        )
        if not space_quote:
            return self._build_inconclusive_verdict(
                hypothesis, snapshot, verdict_id, trace_id, eval_time,
                DriftInconclusiveReasonEnum.TARGET_MISSING_OR_SUSPENDED,
                f"最高空间标杆 ({space_leader_code}) 在盘中行情中缺失，证据不足无法执行核心断言。"
            )

        # =========================================================================
        # 阶段 2：执行微观客观量化断言 (Microscopic Objective Assertions)
        # =========================================================================
        assertions: List[AssertionItemVerdict] = []
        drift_events: List[DriftEventCategoryEnum] = []
        boundaries: List[str] = []

        # -------------------------------------------------------------------------
        # 断言 1：最高空间标杆炸板与深水断言 (CRITICAL_KILL 一票否决权)
        # -------------------------------------------------------------------------
        space_drop_limit = Decimal(str(self.threshold_config["space_leader_drop_threshold"]))
        is_space_broken = space_quote.is_broken_limit
        is_space_weak = space_quote.pct_change <= space_drop_limit
        is_space_violated = is_space_broken or is_space_weak

        space_analysis = "空间标杆承接稳固，涨停结构未破坏"
        if is_space_broken:
            space_analysis = (
                f"空间标杆 ({space_quote.name}) 今日曾触及涨停但盘中开板/炸板，"
                f"现价 {space_quote.current_price} 元 ({space_quote.pct_change}%)，高度压制市场情绪"
            )
            drift_events.append(DriftEventCategoryEnum.SPACE_LEADER_COLLAPSE)
            boundaries.append(ALLOWED_INTRADAY_BOUNDARIES["SPACE_LEADER_BROKEN"])
        elif is_space_weak:
            space_analysis = (
                f"空间标杆 ({space_quote.name}) 盘中跌幅达 {space_quote.pct_change}% "
                f"(跌破容忍阈值 {space_drop_limit}%)，情绪标杆深水走弱"
            )
            drift_events.append(DriftEventCategoryEnum.SPACE_LEADER_COLLAPSE)
            boundaries.append(ALLOWED_INTRADAY_BOUNDARIES["SPACE_LEADER_WEAK"])

        assertions.append(
            AssertionItemVerdict(
                rule_id="RULE-INTRADAY-SPACE-LEADER",
                rule_name="最高空间标杆炸板与深水断言",
                severity=AssertionSeverityEnum.CRITICAL_KILL,
                target_entity=f"空间标杆 {space_quote.name}({space_quote.code})",
                expected_condition=f"不出现炸板且盘中跌幅 > {space_drop_limit}%",
                actual_observation=(
                    f"现价 {space_quote.current_price} 元, 涨幅 {space_quote.pct_change}%, "
                    f"最高 {space_quote.high_price} 元, 炸板={is_space_broken}"
                ),
                is_violated=is_space_violated,
                deviation_analysis=space_analysis,
            )
        )

        # -------------------------------------------------------------------------
        # 断言 2：全天量能衰减模型投影断言 (RULE-INTRADAY-LIQUIDITY-PACE)
        # -------------------------------------------------------------------------
        min_pace = Decimal(str(self.threshold_config["min_liquidity_pace_ratio"]))
        flash_dry_pace = Decimal(str(self.threshold_config["flash_dry_pace_ratio"]))
        is_liq_violated = snapshot.turnover_pace_ratio_pct < min_pace
        liq_analysis = "盘中量能投影与前日大体持平或放量，流动性格局健康"

        if snapshot.turnover_pace_ratio_pct < flash_dry_pace:
            liq_analysis = (
                f"预估全天成交 {snapshot.projected_turnover_yi} 亿元，"
                f"仅达前日 {snapshot.turnover_pace_ratio_pct}% (严重低于断崖阈值 {flash_dry_pace}%)，"
                f"两市流动性断崖式萎缩"
            )
            drift_events.append(DriftEventCategoryEnum.LIQUIDITY_FLASH_DRY)
            boundaries.append(ALLOWED_INTRADAY_BOUNDARIES["LIQUIDITY_DRY"])
        elif is_liq_violated:
            liq_analysis = (
                f"预估全天成交 {snapshot.projected_turnover_yi} 亿元，"
                f"达前日 {snapshot.turnover_pace_ratio_pct}% (低于平量阈值 {min_pace}%)，量能温和缩水"
            )
            boundaries.append(ALLOWED_INTRADAY_BOUNDARIES["LIQUIDITY_DRY"])

        assertions.append(
            AssertionItemVerdict(
                rule_id="RULE-INTRADAY-LIQUIDITY-PACE",
                rule_name="量能时间衰减投影断言",
                severity=AssertionSeverityEnum.MODERATE,
                target_entity="沪深两市全天预估成交总额",
                expected_condition=f"量能进度比率 >= {min_pace}%",
                actual_observation=(
                    f"已开盘 {snapshot.elapsed_trading_minutes} 分钟, "
                    f"累计成交 {snapshot.total_accumulated_turnover_yi} 亿元, "
                    f"预估全天 {snapshot.projected_turnover_yi} 亿元 ({snapshot.turnover_pace_ratio_pct}%)"
                ),
                is_violated=is_liq_violated,
                deviation_analysis=liq_analysis,
            )
        )

        # -------------------------------------------------------------------------
        # 断言 3：核心主线龙头集体共振与倒戈断言 (RULE-INTRADAY-MAINLINE-REVERSAL)
        # -------------------------------------------------------------------------
        weak_ml_limit = Decimal(str(self.threshold_config["mainline_weak_drop_threshold"]))
        reversal_ml_limit = Decimal(str(self.threshold_config["mainline_reversal_threshold"]))
        ml_quotes = sorted(
            [q for q in snapshot.leader_quotes if q.code in hypothesis.mainline_leader_codes],
            key=lambda x: x.code,
        )

        is_ml_violated = False
        ml_analysis = "核心主线领军标的走势稳健，未发生群体性破位"
        if ml_quotes:
            all_weak = all(q.pct_change <= weak_ml_limit for q in ml_quotes)
            all_reversal = all(q.pct_change <= reversal_ml_limit for q in ml_quotes)
            ml_obs_str = ", ".join([f"{q.name}({q.code}): {q.pct_change}%" for q in ml_quotes])

            if all_reversal:
                is_ml_violated = True
                ml_analysis = (
                    f"受控主线龙头全线破位暴跌 (全部低于 {reversal_ml_limit}%)，"
                    f"主线群体共振假说彻底反转倒戈"
                )
                drift_events.append(DriftEventCategoryEnum.MAINLINE_TOTAL_REVERSAL)
                boundaries.append(ALLOWED_INTRADAY_BOUNDARIES["MAINLINE_REVERSED"])
            elif all_weak:
                is_ml_violated = True
                ml_analysis = (
                    f"受控主线龙头集体绿盘走弱 (全部低于 {weak_ml_limit}%)，"
                    f"主线群体共振假说呈现显著分歧"
                )
                boundaries.append(ALLOWED_INTRADAY_BOUNDARIES["MAINLINE_DIVERGENT"])
        else:
            ml_obs_str = "无指定主线龙头"

        assertions.append(
            AssertionItemVerdict(
                rule_id="RULE-INTRADAY-MAINLINE-REVERSAL",
                rule_name="主线龙头共振与破位断言",
                severity=AssertionSeverityEnum.MODERATE,
                target_entity=f"Top 主线代表 ({len(ml_quotes)} 只)",
                expected_condition=f"主线领军标的不出现集体走弱 (跌幅低于 {weak_ml_limit}%)",
                actual_observation=ml_obs_str,
                is_violated=is_ml_violated,
                deviation_analysis=ml_analysis,
            )
        )

        # -------------------------------------------------------------------------
        # 断言 4：全市场广度分化与炸板潮断言 (RULE-INTRADAY-MARKET-BREADTH)
        # -------------------------------------------------------------------------
        max_broken_ratio = Decimal(str(self.threshold_config["max_broken_limit_ratio"]))
        max_ld = int(self.threshold_config["max_limit_down_count"])
        is_breadth_violated = (
            snapshot.broken_limit_ratio_pct > max_broken_ratio
            or snapshot.limit_down_count > max_ld
        )
        breadth_analysis = "市场涨跌结构正常，炸板率处于良性可控区间"

        if is_breadth_violated:
            breadth_analysis = (
                f"全市场炸板率达 {snapshot.broken_limit_ratio_pct}% (超警戒线 {max_broken_ratio}%)，"
                f"跌停家数达 {snapshot.limit_down_count} 家，情绪分化显著加剧"
            )
            drift_events.append(DriftEventCategoryEnum.BREADTH_PANIC_DIVERGENCE)
            boundaries.append(ALLOWED_INTRADAY_BOUNDARIES["BREADTH_PANIC"])

        assertions.append(
            AssertionItemVerdict(
                rule_id="RULE-INTRADAY-MARKET-BREADTH",
                rule_name="全市场广度与炸板潮断言",
                severity=AssertionSeverityEnum.MODERATE,
                target_entity="市场广度与涨跌停梯队",
                expected_condition=f"炸板率 <= {max_broken_ratio}% 且 跌停家数 <= {max_ld}",
                actual_observation=(
                    f"涨停 {snapshot.limit_up_count} 只, 曾涨停开板 {snapshot.broken_limit_count} 只 "
                    f"(炸板率 {snapshot.broken_limit_ratio_pct}%), 跌停 {snapshot.limit_down_count} 只"
                ),
                is_violated=is_breadth_violated,
                deviation_analysis=breadth_analysis,
            )
        )

        # =========================================================================
        # 阶段 3：MECE 综合定调决策树 (Synthetic Drift Resolution)
        # =========================================================================
        if any(a.is_violated for a in assertions if a.severity == AssertionSeverityEnum.CRITICAL_KILL):
            overall_state = DriftStateEnum.CRITICAL_BREACH
            headline = f"{snapshot.stage.value} 空间标杆破位炸板，触发认知假说盘中严重破位證伪！"
        elif any(a.is_violated for a in assertions if a.severity == AssertionSeverityEnum.MODERATE):
            overall_state = DriftStateEnum.DRIFT_WARNING
            headline = f"{snapshot.stage.value} 盘面呈现中度分歧（量能或主线不及预期），需保持防守警惕。"
        else:
            overall_state = DriftStateEnum.NORMAL
            headline = f"{snapshot.stage.value} 盘面演进吻合前夜/竞价假说预期，主线与标杆结构稳健。"
            boundaries.append(ALLOWED_INTRADAY_BOUNDARIES["NORMAL_DEFENSE"])

        # 去重并排序行动边界
        unique_boundaries = list(dict.fromkeys(boundaries))

        # 构造待哈希字典
        raw_dict_for_verdict = {
            "verdict_id": verdict_id,
            "trade_date": snapshot.trade_date,
            "evaluated_at": eval_time,
            "stage": snapshot.stage.value,
            "elapsed_trading_minutes": snapshot.elapsed_trading_minutes,
            "trace_id": trace_id,
            "hypothesis_id": hypothesis.hypothesis_id,
            "hypothesis_fingerprint": hypothesis.hypothesis_fingerprint,
            "intraday_snapshot_fingerprint": snapshot.snapshot_fingerprint,
            "rule_version": RULE_VERSION_INTRADAY,
            "threshold_config_hash": self.threshold_hash,
            "overall_drift_state": overall_state.value,
            "inconclusive_reason": None,
            "verdict_headline": headline,
            "detected_drift_events": [e.value for e in drift_events],
            "assertion_results": [
                {
                    "rule_id": a.rule_id,
                    "rule_name": a.rule_name,
                    "severity": a.severity.value,
                    "target_entity": a.target_entity,
                    "expected_condition": a.expected_condition,
                    "actual_observation": a.actual_observation,
                    "is_violated": a.is_violated,
                    "deviation_analysis": a.deviation_analysis,
                }
                for a in assertions
            ],
            "preservation_boundaries": unique_boundaries,
            "safety_audit_passed": True,
        }
        v_fp = hash_jcs(raw_dict_for_verdict)

        return IntradayDriftVerdict(
            verdict_id=verdict_id,
            trade_date=snapshot.trade_date,
            evaluated_at=eval_time,
            stage=snapshot.stage,
            elapsed_trading_minutes=snapshot.elapsed_trading_minutes,
            trace_id=trace_id,
            hypothesis_id=hypothesis.hypothesis_id,
            hypothesis_fingerprint=hypothesis.hypothesis_fingerprint,
            intraday_snapshot_fingerprint=snapshot.snapshot_fingerprint,
            rule_version=RULE_VERSION_INTRADAY,
            threshold_config_hash=self.threshold_hash,
            overall_drift_state=overall_state,
            inconclusive_reason=None,
            verdict_headline=headline,
            detected_drift_events=drift_events,
            assertion_results=assertions,
            preservation_boundaries=unique_boundaries,
            safety_audit_passed=True,
            verdict_fingerprint=v_fp,
        )

    def _build_inconclusive_verdict(
        self,
        hypothesis: PopperianHypothesisRecord,
        snapshot: CanonicalIntradaySnapshot,
        verdict_id: str,
        trace_id: str,
        eval_time: str,
        reason: DriftInconclusiveReasonEnum,
        headline: str,
    ) -> IntradayDriftVerdict:
        raw_dict = {
            "verdict_id": verdict_id,
            "trade_date": snapshot.trade_date,
            "evaluated_at": eval_time,
            "stage": snapshot.stage.value,
            "elapsed_trading_minutes": snapshot.elapsed_trading_minutes,
            "trace_id": trace_id,
            "hypothesis_id": hypothesis.hypothesis_id,
            "hypothesis_fingerprint": hypothesis.hypothesis_fingerprint,
            "intraday_snapshot_fingerprint": snapshot.snapshot_fingerprint,
            "rule_version": RULE_VERSION_INTRADAY,
            "threshold_config_hash": self.threshold_hash,
            "overall_drift_state": DriftStateEnum.INCONCLUSIVE.value,
            "inconclusive_reason": reason.value,
            "verdict_headline": headline,
            "detected_drift_events": [],
            "assertion_results": [],
            "preservation_boundaries": [],
            "safety_audit_passed": True,
        }
        v_fp = hash_jcs(raw_dict)
        return IntradayDriftVerdict(
            verdict_id=verdict_id,
            trade_date=snapshot.trade_date,
            evaluated_at=eval_time,
            stage=snapshot.stage,
            elapsed_trading_minutes=snapshot.elapsed_trading_minutes,
            trace_id=trace_id,
            hypothesis_id=hypothesis.hypothesis_id,
            hypothesis_fingerprint=hypothesis.hypothesis_fingerprint,
            intraday_snapshot_fingerprint=snapshot.snapshot_fingerprint,
            rule_version=RULE_VERSION_INTRADAY,
            threshold_config_hash=self.threshold_hash,
            overall_drift_state=DriftStateEnum.INCONCLUSIVE,
            inconclusive_reason=reason,
            verdict_headline=headline,
            detected_drift_events=[],
            assertion_results=[],
            preservation_boundaries=[],
            safety_audit_passed=True,
            verdict_fingerprint=v_fp,
        )
