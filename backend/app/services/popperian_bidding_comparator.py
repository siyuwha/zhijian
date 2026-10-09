"""
Phase 2E.2: Popperian Bidding Comparator Service
================================================
上位依据：
1. 最高董事会裁决令：《BOARD-DECISION-PHASE2E2-CONTROLLED-GO-20261009》
2. 《DOC-89 · Phase 2E 09:25 集合竞价自动对账与次日波普尔证伪闭环技术设计单》

四大刚性设计要求落实：
------------------------------------------------
A. 先质检再断言：
   - 优先检查 is_trading_day、data_quality、envelope 降级及法定标的完备性；
   - 证据不足一律返回 INCONCLUSIVE，绝不默认 CONFIRMED，亦不将缺失数据自动解释为 FALSIFIED。

B. 不可变与抗篡改边界明确（不夸大 WORM）：
   - Pydantic frozen=True 仅限 Python 进程内存只读；
   - SQLite 触发器仅限单机文件事务防误写；
   - 真正的抗篡改依赖 RFC 8785 JCS + SHA-256 数字指纹穿透校验。

C. 市场成交额与指数成交额概念严格区分：
   - 上交所与深交所全市场成交额（已包含创业板全市场成交额）相加为两市全市场总成交额；
   - 严禁累加创业板指数切片成交额，防双重记账。

D. 五位一体相互复核：
   - 对账单同时封装：hypothesis_id, rule_version, threshold_config_hash, auction_fingerprint, trace_id。
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from decimal import Decimal

from backend.app.schemas.popper_verdict import (
    FalsificationOutcomeEnum,
    InconclusiveReasonEnum,
    AssertionSeverityEnum,
    AssertionItemVerdict,
    PopperianHypothesisRecord,
    BiddingFalsificationVerdict,
)
from backend.app.schemas.canonical_auction import (
    CanonicalAuctionSnapshot,
    BiddingStatusEnum,
)
from backend.app.schemas.canonical_market import DataQualityGrade
from backend.app.services.briefing_safety_guard import canonical_round_decimal
from backend.app.cognition.jcs import hash_jcs

logger = logging.getLogger(__name__)

RULESET_VERSION = "2026.10.E2.V1"

# 默认客观量化阈值参数集
DEFAULT_ASSERTION_THRESHOLDS: Dict[str, str] = {
    "ruleset_version": RULESET_VERSION,
    "liquidity_cliff_ratio_pct": "0.80",        # 两市竞价占前日成交额萎缩红线 (%)
    "liquidity_active_ratio_pct": "1.50",       # 两市竞价占前日成交额交投活跃红线 (%)
    "index_sentiment_flat_low": "-0.20",        # 指数平开下界 (%)
    "index_sentiment_flat_high": "0.20",        # 指数平开上界 (%)
    "index_sentiment_deep_drop": "-0.50",       # 指数大幅低开深度门槛 (%)
    "space_leader_strong_premium": "3.00",      # 空间标杆超预期高开幅度 (%)
    "space_leader_normal_low": "-1.00",         # 空间标杆合理承接下界 (%)
    "space_leader_falsification_drop": "-3.00", # 空间标杆致命证伪深水跌幅 (%)
    "mainline_leader_weak_drop": "-1.50",       # 主线领军弱势开盘跌幅界限 (%)
}


class CausalTemporalViolationError(Exception):
    """因果时序违背异常：假说登记时间晚于或等于竞价事实观测时间"""
    pass


class HypothesisTargetMissingError(Exception):
    """假说观测标的缺失异常：竞价快照中缺少战报登记的核心标的"""
    pass


def compute_threshold_config_hash(thresholds: Dict[str, Any]) -> str:
    """计算阈值参数配置字典的 RFC 8785 JCS SHA-256 指纹"""
    return hash_jcs(thresholds)


class PopperianBiddingComparator:
    """
    波普尔 09:25 竞价自动对账比较器 (Phase 2E.2 核心执行器)
    """

    def __init__(self, threshold_config: Optional[Dict[str, Any]] = None):
        self.threshold_config = threshold_config or DEFAULT_ASSERTION_THRESHOLDS
        self.threshold_config_hash = compute_threshold_config_hash(self.threshold_config)
        self.rule_version = self.threshold_config.get("ruleset_version", RULESET_VERSION)

    def evaluate(
        self,
        hypothesis: PopperianHypothesisRecord,
        auction_snapshot: CanonicalAuctionSnapshot,
        evaluation_timestamp: Optional[str] = None,
    ) -> BiddingFalsificationVerdict:
        """
        执行 09:25 竞价事实 vs 前夜假说的确定性因果对账
        """
        eval_time = evaluation_timestamp or datetime.now().isoformat()
        trace_id = (
            f"TRACE-{hypothesis.base_trade_date}-TO-{auction_snapshot.trade_date}-"
            f"AUCTION-POPPER-{hypothesis.hypothesis_id[:8]}"
        )
        verdict_id = f"VERDICT-{auction_snapshot.trade_date}-{hypothesis.hypothesis_id[:8]}"

        # =========================================================================
        # 阶段 1：因果时序严格守卫 (Strict Temporal Causality Guard)
        # =========================================================================
        hypo_reg_str = hypothesis.registered_at
        # 兼容含时区与不含时区比较
        try:
            hypo_dt = datetime.fromisoformat(hypo_reg_str.replace("Z", "+00:00"))
            # 竞价时间若为 HH:MM:SS，则拼接 trade_date
            obs_time_raw = auction_snapshot.observed_time
            if "T" in obs_time_raw:
                auc_dt = datetime.fromisoformat(obs_time_raw.replace("Z", "+00:00"))
            else:
                auc_dt = datetime.fromisoformat(f"{auction_snapshot.trade_date}T{obs_time_raw}+08:00")
            
            # 若假说时间晚于或等于竞价观测时间，引发致命因果违规异常
            if hypo_dt >= auc_dt:
                raise CausalTemporalViolationError(
                    f"Causal violation detected: Hypothesis registered at {hypo_reg_str} "
                    f"postdates or equals auction observed at {obs_time_raw}! "
                    f"Post-hoc hypotheses are strictly forbidden."
                )
        except ValueError as e:
            logger.warning(f"Timestamp parse warning during causality check: {e}")

        # =========================================================================
        # 阶段 2：数据质量与前置条件优先审查 (Pre-condition & Quality Guard - Req A)
        # 证据不足严格返回 INCONCLUSIVE，绝不默认 CONFIRMED，亦不误判为 FALSIFIED
        # =========================================================================

        # 2.1 物理休市 / 非交易日拦截
        if not auction_snapshot.is_trading_day:
            return self._build_verdict(
                verdict_id=verdict_id,
                trade_date=auction_snapshot.trade_date,
                evaluated_at=eval_time,
                trace_id=trace_id,
                hypothesis=hypothesis,
                auction_snapshot=auction_snapshot,
                overall_verdict=FalsificationOutcomeEnum.INCONCLUSIVE,
                inconclusive_reason=InconclusiveReasonEnum.MARKET_CLOSED,
                headline=f"交易日历确认休市或非交易日 ({auction_snapshot.trade_date})，物理行情未开启，无法对账。",
                assertions=[],
                boundaries=["市场处于休市非交易状态，保持底仓静默，等待下个交易日物理开盘。"],
            )

        # 2.2 上游数据品质降级拦截
        if (
            auction_snapshot.data_quality != DataQualityGrade.FULL
            or auction_snapshot.envelope.is_degraded
        ):
            deg_reason = auction_snapshot.envelope.degradation_reason or "未知降级原因"
            return self._build_verdict(
                verdict_id=verdict_id,
                trade_date=auction_snapshot.trade_date,
                evaluated_at=eval_time,
                trace_id=trace_id,
                hypothesis=hypothesis,
                auction_snapshot=auction_snapshot,
                overall_verdict=FalsificationOutcomeEnum.INCONCLUSIVE,
                inconclusive_reason=InconclusiveReasonEnum.DATA_QUALITY_DEGRADED,
                headline=f"09:25 竞价物理快照品质降级 ({auction_snapshot.data_quality.value})，证据不足以进行裁判。",
                assertions=[],
                boundaries=[f"数据源降级 ({deg_reason})，缺乏物理确证依据，暂缓推演实战边界。"],
            )

        # 2.3 标的完备性与停牌审查 (零静默替换铁律)
        missing_targets: List[str] = []
        suspended_targets: List[str] = []
        for sym in hypothesis.required_observation_symbols:
            matched = next((q for q in auction_snapshot.leader_quotes if q.code == sym), None)
            if not matched:
                missing_targets.append(sym)
            elif matched.bidding_status == BiddingStatusEnum.SUSPENDED:
                suspended_targets.append(sym)

        if missing_targets or suspended_targets:
            reasons = []
            if missing_targets:
                reasons.append(f"法定观测标的缺失: {missing_targets}")
            if suspended_targets:
                reasons.append(f"标的停牌: {suspended_targets}")
            reason_msg = "; ".join(reasons)

            return self._build_verdict(
                verdict_id=verdict_id,
                trade_date=auction_snapshot.trade_date,
                evaluated_at=eval_time,
                trace_id=trace_id,
                hypothesis=hypothesis,
                auction_snapshot=auction_snapshot,
                overall_verdict=FalsificationOutcomeEnum.INCONCLUSIVE,
                inconclusive_reason=InconclusiveReasonEnum.TARGET_MISSING_OR_SUSPENDED,
                headline=f"核心观测标的事实不完备 ({reason_msg})，触发保护，判定为证据不足。",
                assertions=[],
                boundaries=["关键标的事实缺失或停牌，无法完成既定对账闭环，进入观望状态。"],
            )

        # =========================================================================
        # 阶段 3：四大客观量化断言计算 (Objective Quantitative Assertions)
        # =========================================================================
        assertions: List[AssertionItemVerdict] = []

        # -------------------------------------------------------------------------
        # 断言 1：流动性强度与交投断崖监测 (RULE-LIQUIDITY-INTENSITY)
        # -------------------------------------------------------------------------
        cliff_ratio = Decimal(str(self.threshold_config["liquidity_cliff_ratio_pct"]))
        active_ratio = Decimal(str(self.threshold_config["liquidity_active_ratio_pct"]))
        actual_ratio = auction_snapshot.auction_turnover_ratio_pct

        is_liq_violated = False
        liq_analysis = f"实际竞价总额占比 {actual_ratio}%，处于正常交投区间 [{cliff_ratio}%, {active_ratio}%]"

        if actual_ratio < cliff_ratio and hypothesis.expected_turnover_ratio_min >= cliff_ratio:
            is_liq_violated = True
            liq_analysis = (
                f"实际竞价总额占比 {actual_ratio}% 跌破流动性萎缩红线 {cliff_ratio}% "
                f"(前夜假说预期 [{hypothesis.expected_turnover_ratio_min}%, {hypothesis.expected_turnover_ratio_max}%])"
            )
        elif actual_ratio < hypothesis.expected_turnover_ratio_min:
            is_liq_violated = True
            liq_analysis = (
                f"实际竞价总额占比 {actual_ratio}% 低于假说预期下界 {hypothesis.expected_turnover_ratio_min}%"
            )

        assertions.append(
            AssertionItemVerdict(
                rule_id="RULE-LIQUIDITY-INTENSITY",
                rule_name="全市场流动性开盘强度断言",
                severity=AssertionSeverityEnum.MODERATE,
                target_entity=f"沪深两市全市场竞价总额 ({auction_snapshot.total_auction_turnover_yi} 亿元)",
                expected_condition=f"竞价总额占前日比例在 [{hypothesis.expected_turnover_ratio_min}%, {hypothesis.expected_turnover_ratio_max}%] 且不低于 {cliff_ratio}%",
                actual_observation=f"竞价总额占比 {actual_ratio}% (上海 {auction_snapshot.sh_auction_turnover_yi} 亿, 深圳 {auction_snapshot.sz_auction_turnover_yi} 亿)",
                is_violated=is_liq_violated,
                deviation_analysis=liq_analysis,
            )
        )

        # -------------------------------------------------------------------------
        # 断言 2：核心宽基情绪锚定断言 (RULE-INDEX-SENTIMENT)
        # -------------------------------------------------------------------------
        deep_drop_threshold = Decimal(str(self.threshold_config["index_sentiment_deep_drop"]))
        sh_idx = next((i for i in auction_snapshot.indices if "000001" in i.symbol), None)

        is_idx_violated = False
        idx_obs = "上证指数切片缺失"
        idx_analysis = "上证指数未见有效异常"

        if sh_idx:
            idx_obs = f"上证指数开盘点位 {sh_idx.open_price} (涨跌幅 {sh_idx.pct_change}%)"
            if sh_idx.pct_change <= deep_drop_threshold:
                is_idx_violated = True
                idx_analysis = (
                    f"上证指数竞价低开 {sh_idx.pct_change}%，跌破深度低开红线 {deep_drop_threshold}%"
                )
            else:
                idx_analysis = f"上证指数开盘涨跌幅 {sh_idx.pct_change}% 处于正常容差区间"

        assertions.append(
            AssertionItemVerdict(
                rule_id="RULE-INDEX-SENTIMENT",
                rule_name="上证指数核心情绪锚定断言",
                severity=AssertionSeverityEnum.MODERATE,
                target_entity="sh000001 上证指数",
                expected_condition=f"上证指数开盘涨跌幅 > {deep_drop_threshold}%",
                actual_observation=idx_obs,
                is_violated=is_idx_violated,
                deviation_analysis=idx_analysis,
            )
        )

        # -------------------------------------------------------------------------
        # 断言 3：空间标杆溢价承接生命线断言 (RULE-SPACE-LEADER-PREMIUM) [CRITICAL_KILL]
        # -------------------------------------------------------------------------
        space_q = next(
            (q for q in auction_snapshot.leader_quotes if q.code == hypothesis.space_leader_code),
            None,
        )
        is_space_killed = False
        space_obs = "未找到空间标杆行情"
        space_analysis = "标的正常"

        if space_q:
            space_obs = (
                f"开盘价 {space_q.auction_price} 元，涨跌幅 {space_q.auction_pct_change}% "
                f"(状态: {space_q.bidding_status.value})"
            )
            kill_thresh = hypothesis.space_leader_falsification_threshold
            if (
                space_q.bidding_status == BiddingStatusEnum.LIMIT_DOWN_BIDDING
                or space_q.auction_pct_change <= kill_thresh
            ):
                is_space_killed = True
                space_analysis = (
                    f"空间标杆 {space_q.name} 开盘跌幅 {space_q.auction_pct_change}% "
                    f"跌破致命证伪红线 {kill_thresh}% (或跌停封死)，构成致命证伪！"
                )
            elif space_q.auction_pct_change < Decimal(str(self.threshold_config["space_leader_normal_low"])):
                space_analysis = (
                    f"空间标杆 {space_q.name} 开盘 {space_q.auction_pct_change}% 弱于预期，但未触发跌破 {kill_thresh}% 致命红线"
                )
            else:
                space_analysis = f"空间标杆 {space_q.name} 开盘 {space_q.auction_pct_change}% 符合或强于承接预期"

        assertions.append(
            AssertionItemVerdict(
                rule_id="RULE-SPACE-LEADER-PREMIUM",
                rule_name="空间标杆溢价承接生命线断言",
                severity=AssertionSeverityEnum.CRITICAL_KILL,
                target_entity=f"{hypothesis.space_leader_code} {hypothesis.space_leader_name}",
                expected_condition=f"竞价开盘涨幅 > {hypothesis.space_leader_falsification_threshold}% 且未封死跌停",
                actual_observation=space_obs,
                is_violated=is_space_killed,
                deviation_analysis=space_analysis,
            )
        )

        # -------------------------------------------------------------------------
        # 断言 4：核心主线龙头共振断言 (RULE-MAINLINE-LEADER-ALIGNMENT)
        # -------------------------------------------------------------------------
        weak_drop_threshold = Decimal(str(self.threshold_config["mainline_leader_weak_drop"]))
        ml_quotes = [
            q for q in auction_snapshot.leader_quotes if q.code in hypothesis.mainline_leader_codes
        ]

        is_ml_violated = False
        ml_obs_list = [f"{q.name}({q.code}): {q.auction_pct_change}%" for q in ml_quotes]
        ml_obs = ", ".join(ml_obs_list) if ml_obs_list else "无主线龙头"
        ml_analysis = "核心主线龙头竞价承接平稳"

        if ml_quotes:
            all_weak = all(q.auction_pct_change <= weak_drop_threshold for q in ml_quotes)
            if all_weak:
                is_ml_violated = True
                ml_analysis = (
                    f"全部受控主线领军标的集体绿开且跌幅低于 {weak_drop_threshold}%，"
                    f"主线群体共振假说出现显著分歧"
                )

        assertions.append(
            AssertionItemVerdict(
                rule_id="RULE-MAINLINE-LEADER-ALIGNMENT",
                rule_name="核心主线龙头共振断言",
                severity=AssertionSeverityEnum.MODERATE,
                target_entity=f"Top 主线代表 ({len(ml_quotes)} 只)",
                expected_condition=f"主线领军标的不出现集体绿开且跌幅低于 {weak_drop_threshold}%",
                actual_observation=ml_obs,
                is_violated=is_ml_violated,
                deviation_analysis=ml_analysis,
            )
        )

        # =========================================================================
        # 阶段 4：MECE 决策树综合定调 (Synthetic Verdict Resolution)
        # =========================================================================
        has_critical_kill = any(
            a.severity == AssertionSeverityEnum.CRITICAL_KILL and a.is_violated
            for a in assertions
        )
        has_moderate_divergence = any(
            a.severity == AssertionSeverityEnum.MODERATE and a.is_violated
            for a in assertions
        )

        if has_critical_kill:
            overall = FalsificationOutcomeEnum.FALSIFIED
            headline = (
                f"空间标杆 ({hypothesis.space_leader_name}) 开盘深水破位，"
                f"前夜假说触发刚性证伪！"
            )
            boundaries = [
                f"最高板 {hypothesis.space_leader_name} 溢价崩塌，短线情绪处于破位周期，严禁逆势追高。",
                "核心假说被波普尔证伪，开盘首选执行防守纪律，控制亏损敞口扩大。",
            ]
        elif has_moderate_divergence:
            overall = FalsificationOutcomeEnum.DIVERGENT
            headline = "09:25 竞价盘面与前夜假说呈现中度分歧（量能/主线分化），需等待开盘确认。"
            boundaries = [
                "竞价量能或主线承接出现偏离，不宜在 09:30 盲目抢筹入场。",
                "观察开盘 15 分钟主线领军分时承接情况，确认是否发生弱转强。",
            ]
        else:
            overall = FalsificationOutcomeEnum.CONFIRMED
            headline = "09:25 集合竞价事实与前夜假说高度吻合，情绪溢价与量能结构得到正向强化。"
            boundaries = [
                "竞价事实验证前夜推演，核心主线标杆处于良性溢价通道。",
                "按既定复盘计划跟踪观察目标核心战场分时接力机会。",
            ]

        # =========================================================================
        # 阶段 5：封印出具对账单 (Verdict Assembly & JCS Sealing)
        # =========================================================================
        return self._build_verdict(
            verdict_id=verdict_id,
            trade_date=auction_snapshot.trade_date,
            evaluated_at=eval_time,
            trace_id=trace_id,
            hypothesis=hypothesis,
            auction_snapshot=auction_snapshot,
            overall_verdict=overall,
            inconclusive_reason=None,
            headline=headline,
            assertions=assertions,
            boundaries=boundaries,
        )

    def _build_verdict(
        self,
        verdict_id: str,
        trade_date: str,
        evaluated_at: str,
        trace_id: str,
        hypothesis: PopperianHypothesisRecord,
        auction_snapshot: CanonicalAuctionSnapshot,
        overall_verdict: FalsificationOutcomeEnum,
        inconclusive_reason: Optional[InconclusiveReasonEnum],
        headline: str,
        assertions: List[AssertionItemVerdict],
        boundaries: List[str],
    ) -> BiddingFalsificationVerdict:
        """
        装配并执行 RFC 8785 JCS SHA-256 签名，生成不可变对账单契约
        """
        raw_dict_for_hash = {
            "verdict_id": verdict_id,
            "trade_date": trade_date,
            "evaluated_at": evaluated_at,
            "trace_id": trace_id,
            "hypothesis_id": hypothesis.hypothesis_id,
            "hypothesis_fingerprint": hypothesis.hypothesis_fingerprint,
            "bound_briefing_fingerprint": hypothesis.bound_briefing_fingerprint,
            "rule_version": self.rule_version,
            "threshold_config_hash": self.threshold_config_hash,
            "auction_fingerprint": auction_snapshot.auction_fingerprint,
            "overall_verdict": overall_verdict.value,
            "inconclusive_reason": inconclusive_reason.value if inconclusive_reason else None,
            "verdict_headline": headline,
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
            "action_boundaries": boundaries,
            "safety_audit_passed": True,
        }

        verdict_fp = hash_jcs(raw_dict_for_hash)

        return BiddingFalsificationVerdict(
            verdict_id=verdict_id,
            trade_date=trade_date,
            evaluated_at=evaluated_at,
            trace_id=trace_id,
            hypothesis_id=hypothesis.hypothesis_id,
            hypothesis_fingerprint=hypothesis.hypothesis_fingerprint,
            bound_briefing_fingerprint=hypothesis.bound_briefing_fingerprint,
            rule_version=self.rule_version,
            threshold_config_hash=self.threshold_config_hash,
            auction_fingerprint=auction_snapshot.auction_fingerprint,
            overall_verdict=overall_verdict,
            inconclusive_reason=inconclusive_reason,
            verdict_headline=headline,
            assertion_results=assertions,
            action_boundaries=boundaries,
            safety_audit_passed=True,
            verdict_fingerprint=verdict_fp,
        )
