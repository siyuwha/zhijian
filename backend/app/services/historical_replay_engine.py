"""
Historical Replay & Falsification Engine (DOC-78 Phase 2D.2)
============================================================
多周期时空历史回放与波普尔证伪对账引擎

核心职责：
1. 跨交易日 (T-1 -> T -> T+1) 批量切片回放与状态转移矩阵审计；
2. 10x 连续重跑 RFC 8785 JCS 哈希零漂移与幂等性保障；
3. 波普尔反向证伪对账 (次日竞价/开盘检验前日认知规则)。
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.schemas.canonical_market import (
    CanonicalMarketSnapshot,
    MarketStateEnum,
)
from backend.app.services.canonical_market_service import CanonicalMarketService


class HistoricalReplayEngine:
    """
    多周期历史回放与波普尔对账引擎
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.service = CanonicalMarketService(session)

    async def replay_date(
        self,
        date_str: str,
        prior_snapshot: Optional[CanonicalMarketSnapshot] = None,
    ) -> Optional[CanonicalMarketSnapshot]:
        """
        回放单一交易日，并可选传入前序快照用于跨周期流动性比对与状态转移识别
        """
        snapshot = await self.service.get_canonical_snapshot(date_str)
        if snapshot is None:
            return None

        # 若存在前序快照，更新状态转移定性
        if prior_snapshot and snapshot.cognition.market_state_calibration:
            prior_cal = prior_snapshot.cognition.market_state_calibration
            prior_state = prior_cal.primary_state if prior_cal else None
            if prior_state:
                curr_features = self.service.state_calibrator.extract_feature_vector(
                    truth=snapshot.truth,
                    prior_truth=prior_snapshot.truth,
                )
                core_mainlines = [
                    m.sector_name
                    for m in snapshot.cognition.mainlines
                    if m.structural_role in ("CORE_MAINLINE", "BRANCH_ROTATION")
                ]
                top_grp = snapshot.truth.ladder_tree[0] if snapshot.truth.ladder_tree else None
                space_leader_txt = f"最高{top_grp.height}B{top_grp.stocks[0].name}" if top_grp and top_grp.stocks else ""

                recalibrated = self.service.state_calibrator.calibrate(
                    features=curr_features,
                    prior_state=prior_state,
                    core_mainlines=core_mainlines,
                    space_leader_desc=space_leader_txt,
                )
                # 使用更新后的校准对象 (对冻结模型执行深度 model_copy)
                updated_cognition = snapshot.cognition.model_copy(
                    update={"market_state_calibration": recalibrated}
                )
                snapshot = snapshot.model_copy(
                    update={"cognition": updated_cognition}
                )

        return snapshot

    async def replay_multi_periods(
        self,
        date_sequence: List[str],
    ) -> List[CanonicalMarketSnapshot]:
        """
        按时间序列连续回放多周期切片
        """
        results: List[CanonicalMarketSnapshot] = []
        prior: Optional[CanonicalMarketSnapshot] = None

        for d in date_sequence:
            snap = await self.replay_date(d, prior_snapshot=prior)
            if snap:
                results.append(snap)
                prior = snap

        return results

    async def audit_transition_matrix(
        self,
        snapshots: List[CanonicalMarketSnapshot],
    ) -> List[Dict[str, Any]]:
        """
        生成状态转移矩阵审计报告
        """
        transitions: List[Dict[str, Any]] = []
        for i in range(len(snapshots) - 1):
            s_from = snapshots[i]
            s_to = snapshots[i + 1]

            state_from = s_from.cognition.market_state_calibration.primary_state if s_from.cognition.market_state_calibration else None
            state_to = s_to.cognition.market_state_calibration.primary_state if s_to.cognition.market_state_calibration else None

            transitions.append({
                "from_date": s_from.trade_date,
                "from_state": state_from.value if state_from else "UNKNOWN",
                "to_date": s_to.trade_date,
                "to_state": state_to.value if state_to else "UNKNOWN",
                "transition_signal": s_to.cognition.market_state_calibration.transition_signal if s_to.cognition.market_state_calibration else None,
                "turnover_delta_ratio": s_to.cognition.market_state_calibration.feature_vector.index_vector.turnover_change_ratio if s_to.cognition.market_state_calibration and s_to.cognition.market_state_calibration.feature_vector else None,
            })

        return transitions

    async def verify_idempotence(
        self,
        date_str: str,
        runs: int = 10,
    ) -> Dict[str, Any]:
        """
        对指定交易日连续重跑 10 次，检验 JCS SHA-256 指纹零漂移
        """
        first = await self.service.get_canonical_snapshot(date_str)
        if not first:
            return {"status": "FAILED", "reason": f"No data for date {date_str}"}

        first_fp = first.envelope_fingerprint
        first_cog_fp = first.cognition.cognition_fingerprint
        first_truth_fp = first.truth.truth_fingerprint

        for idx in range(1, runs):
            sub = await self.service.get_canonical_snapshot(date_str)
            if not sub:
                return {"status": "FAILED", "reason": f"Run {idx+1} failed to load snapshot"}
            if sub.envelope_fingerprint != first_fp:
                return {
                    "status": "FAILED",
                    "reason": f"Run {idx+1} envelope fingerprint drifted: {sub.envelope_fingerprint} != {first_fp}",
                }
            if sub.cognition.cognition_fingerprint != first_cog_fp:
                return {
                    "status": "FAILED",
                    "reason": f"Run {idx+1} cognition fingerprint drifted",
                }
            if sub.truth.truth_fingerprint != first_truth_fp:
                return {
                    "status": "FAILED",
                    "reason": f"Run {idx+1} truth fingerprint drifted",
                }

        return {
            "status": "PASS",
            "runs": runs,
            "trade_date": date_str,
            "envelope_fingerprint": first_fp,
            "is_invariant": True,
        }

    def evaluate_popperian_falsification(
        self,
        snapshot: CanonicalMarketSnapshot,
        t_plus_one_auction: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        波普尔反向证伪对账：用次日真实竞价数据检验前日快照中的证伪条件
        t_plus_one_auction 格式:
        {
            "symbols": {
                "600825": {"open_pct_change": -3.5, "open_volume": ...},
                "600111": {"open_pct_change": +1.2, ...}
            },
            "market_open_broken_ratio": 0.45
        }
        """
        audit_results: List[Dict[str, Any]] = []

        for m in snapshot.cognition.mainlines:
            fals = m.falsification_condition
            rules = fals.invalidation_rules
            symbols = fals.critical_observation_symbols
            ldr_code = m.constituency.leader_code

            # 检验龙头开盘表现
            ldr_data = t_plus_one_auction.get("symbols", {}).get(ldr_code, {})
            open_pct = ldr_data.get("open_pct_change")

            is_falsified = False
            falsified_reasons: List[str] = []

            if open_pct is not None and open_pct <= -3.0:
                is_falsified = True
                falsified_reasons.append(
                    f"核心标杆 {m.constituency.leader_name} ({ldr_code}) 次日开盘 {open_pct:+.2f}% 触发大幅低开证伪条件"
                )

            audit_results.append({
                "sector_name": m.sector_name,
                "leader_name": m.constituency.leader_name,
                "leader_code": ldr_code,
                "open_pct_change": open_pct,
                "is_falsified": is_falsified,
                "falsified_reasons": falsified_reasons,
                "monitored_rules": rules,
            })

        return {
            "evaluation_date": snapshot.trade_date,
            "evaluated_mainlines_count": len(audit_results),
            "results": audit_results,
        }
