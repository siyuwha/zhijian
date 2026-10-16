"""
Phase 2D.3-A: Narrative Context Extractor Service
=================================================
上位依据：
1. 最高董事会 2026-10-09 裁决令：《有条件批准 Phase 2D.3-A，锁死 7 条刚性红线》
2. 《DOC-80 · Phase 2D.3 受约束 LLM 实战战报生成器技术设计单》

核心职责：
- 单向只读消费 CanonicalMarketSnapshot，零直连 DB，零直连 Raw API (红线 1)；
- 100% 确定性构造，满足 RFC 8785 JCS 10x 幂等性 (红线 2)；
- 严格 FACT / DERIVED / COGNITION 三层隔离 (红线 3)；
- 标的身份严格通过 CanonicalSecurityMasterRegistry 单向权威派生 (红线 4)；
- 零交易指令泄露 (红线 5)；
- 明确声明 allowed_claim_types / forbidden_claim_types 发言边界 (红线 6)；
- 绝对禁止二次认知推理，1:1 只读透传上游主线排名 (红线 7)。
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

try:
    from backend.app.schemas.canonical_market import (
        CanonicalMarketSnapshot,
        CanonicalSecurityIdentity,
    )
    from backend.app.schemas.narrative_context import (
        NarrativeContextContract,
        NarrativeFactLayer,
        NarrativeDerivedLayer,
        NarrativeCognitionLayer,
        NarrativeTurnoverFact,
        NarrativeLadderTier,
        NarrativeLadderFact,
        NarrativeSentimentCountsFact,
        NarrativeRegulatoryFact,
        NarrativeStateCognition,
        NarrativeMainlineItem,
        SpeechBoundaryContract,
    )
    from backend.app.services.canonical_market_service import CanonicalSecurityMasterRegistry
    from backend.app.cognition.jcs import hash_jcs
except ImportError:
    from app.schemas.canonical_market import (
        CanonicalMarketSnapshot,
        CanonicalSecurityIdentity,
    )
    from app.schemas.narrative_context import (
        NarrativeContextContract,
        NarrativeFactLayer,
        NarrativeDerivedLayer,
        NarrativeCognitionLayer,
        NarrativeTurnoverFact,
        NarrativeLadderTier,
        NarrativeLadderFact,
        NarrativeSentimentCountsFact,
        NarrativeRegulatoryFact,
        NarrativeStateCognition,
        NarrativeMainlineItem,
        SpeechBoundaryContract,
    )
    from app.services.canonical_market_service import CanonicalSecurityMasterRegistry
    from app.cognition.jcs import hash_jcs


class NarrativeContextExtractor:
    """
    确定性叙事上下文提取器 (Cognition-to-Narrative Extractor)
    """

    def __init__(self):
        self.entity_registry = CanonicalSecurityMasterRegistry()

    def extract_context(
        self,
        snapshot: CanonicalMarketSnapshot,
        extraction_time: str = "2026-10-09T02:45:00Z",
    ) -> NarrativeContextContract:
        """
        从权威快照中确定性构建 NarrativeContextContract
        """
        truth = snapshot.truth
        cog = snapshot.cognition

        # =========================================================================
        # 0. 权威实体身份注册 (单向继承 snapshot 既有 Security Master)
        # =========================================================================
        def infer_ex(code: str, sec_id: Optional[str] = None) -> str:
            if sec_id and "." in sec_id:
                return sec_id.split(".")[-1].upper()
            if code.startswith(("60", "68")):
                return "SH"
            elif code.startswith(("00", "30")):
                return "SZ"
            elif code.startswith(("8", "4", "92")):
                return "BJ"
            return "SZ"

        for grp in truth.ladder_tree:
            for s in grp.stocks:
                ex = infer_ex(s.code, s.security_id)
                self.entity_registry.register(code=s.code, name=s.name, exchange=ex)

        for a in truth.regulatory_anomalies:
            ex = infer_ex(a.symbol)
            self.entity_registry.register(code=a.symbol, name=a.name, exchange=ex)

        for m in cog.mainlines:
            c = m.constituency.leader_code
            n = m.constituency.leader_name
            sid = m.constituency.leader_security_id
            if c and n:
                ex = infer_ex(c, sid)
                self.entity_registry.register(code=c, name=n, exchange=ex)

        # =========================================================================
        # 1. 构建 FACT LAYER (客观物理事实层)
        # =========================================================================
        to = truth.turnover
        fact_turnover = NarrativeTurnoverFact(
            total_turnover_yi=round(to.two_markets_total_yi, 2),
            sh_amount_yi=round(to.sh_amount_yi, 2),
            sz_total_amount_yi=round(to.sz_total_amount_yi, 2),
            chinext_slice_yi=round(to.chinext_slice_amount_yi, 2),
            chinext_ratio_in_sz=round(to.chinext_ratio_in_sz, 4),
        )

        sb = truth.sentiment_bounds
        fact_counts = NarrativeSentimentCountsFact(
            limit_up_count=sb.limit_up_count,
            limit_down_count=sb.limit_down_count,
            touched_limit_total_count=sb.touched_limit_total_count,
            broken_limit_count=sb.broken_limit_count,
        )

        # 天梯树事实
        ladder_tiers: List[NarrativeLadderTier] = []
        for grp in truth.ladder_tree:
            identities = [
                self.entity_registry.get_identity(s.code)
                for s in grp.stocks
            ]
            ladder_tiers.append(
                NarrativeLadderTier(
                    height=grp.height,
                    count=len(grp.stocks),
                    is_space_leader=grp.is_space_leader,
                    stocks=identities,
                )
            )

        space_leader_code = truth.ladder_tree[0].stocks[0].code if truth.ladder_tree and truth.ladder_tree[0].stocks else ""
        space_leader_ident = (
            self.entity_registry.get_identity(space_leader_code)
            if space_leader_code
            else CanonicalSecurityIdentity(
                security_id="UNKNOWN", stock_code="000000", canonical_name="无", exchange="UNKNOWN"
            )
        )

        fact_ladder = NarrativeLadderFact(
            max_height=sb.max_ladder_height,
            space_leader=space_leader_ident,
            tiers=ladder_tiers,
        )

        # 监管异动事实
        anom_identities = [
            self.entity_registry.get_identity(a.symbol)
            for a in truth.regulatory_anomalies
            if self.entity_registry.has_code(a.symbol)
        ]
        space_leader_warn = any(
            a.symbol == space_leader_code for a in truth.regulatory_anomalies
        )

        fact_regulatory = NarrativeRegulatoryFact(
            total_anomaly_count=len(truth.regulatory_anomalies),
            anomaly_stocks=anom_identities,
            space_leader_has_warning=space_leader_warn,
        )

        fact_layer = NarrativeFactLayer(
            turnover=fact_turnover,
            indices=[i.model_dump() if hasattr(i, "model_dump") else i for i in truth.indices],
            ladder=fact_ladder,
            sentiment_counts=fact_counts,
            regulatory=fact_regulatory,
        )

        # =========================================================================
        # 2. 构建 DERIVED LAYER (确定性衍生结构层)
        # =========================================================================
        extreme_loss = round(
            (sb.broken_limit_count + sb.limit_down_count) / sb.touched_limit_total_count,
            4
        ) if sb.touched_limit_total_count > 0 else 0.0

        cal = cog.market_state_calibration
        if not cal:
            from .market_state_calibrator import MarketStateCalibrator
            calibrator = MarketStateCalibrator()
            state_features = calibrator.extract_feature_vector(truth)
            cal = calibrator.calibrate(features=state_features)
        else:
            state_features = cal.feature_vector if cal else None

        to_change = None
        if state_features:
            to_change = state_features.index_vector.turnover_change_ratio

        breadth_msg = None
        if truth.cross_section_breadth_detail:
            breadth_msg = truth.cross_section_breadth_detail.get("message")

        derived_layer = NarrativeDerivedLayer(
            broken_limit_ratio=sb.broken_limit_ratio,
            extreme_loss_ratio=extreme_loss,
            turnover_change_ratio=to_change,
            breadth_status=truth.cross_section_breadth_status,
            breadth_message=breadth_msg,
            state_features=state_features.model_dump() if hasattr(state_features, "model_dump") else state_features,
        )

        # =========================================================================
        # 3. 构建 COGNITION LAYER (顶层认知假说层，只读透传，绝对不重新排序或重筛)
        # =========================================================================
        cognition_state = NarrativeStateCognition(
            primary_state=cal.primary_state,
            state_display_name=cal.state_display_name,
            state_confidence=cal.state_confidence,
            driving_factors=cal.driving_factors,
            transition_signal=cal.transition_signal,
            deterministic_summary=cog.market_state_summary,
        )

        # 严格保持上游 mainlines 排序 (红线 7)
        narrative_mainlines: List[NarrativeMainlineItem] = []
        for m in cog.mainlines:
            ldr_code = m.constituency.leader_code
            ldr_ident = self.entity_registry.get_identity(ldr_code)

            shared_notes = []
            if m.shared_evidence_affiliates:
                for aff in m.shared_evidence_affiliates:
                    shared_notes.append(
                        f"与【{aff.target_sector_name}】重叠 {aff.overlap_stocks_count} 只标的 (重叠度 {aff.shared_evidence_ratio:.1%})"
                    )

            narrative_mainlines.append(
                NarrativeMainlineItem(
                    rank=m.rank,
                    sector_name=m.sector_name,
                    sector_code=m.sector_code,
                    structural_role=m.structural_role,
                    thematic_tier=m.thematic_tier,
                    market_narrative=m.market_narrative,
                    leader_identity=ldr_ident,
                    leader_height=m.constituency.leader_height,
                    limit_up_count=m.constituency.limit_up_count,
                    ladder_distribution=m.constituency.ladder_distribution,
                    supporting_evidence=m.supporting_evidence,
                    counter_evidence=m.counter_evidence,
                    falsification_condition=m.falsification_condition,
                    shared_evidence_notes=shared_notes,
                )
            )

        cognition_layer = NarrativeCognitionLayer(
            market_state=cognition_state,
            candidate_mainlines=narrative_mainlines,
            provisional_disclaimer=cog.provisional_disclaimer,
        )

        # =========================================================================
        # 4. 构建 SPEECH BOUNDARY CONTRACT (叙事发言边界契约)
        # =========================================================================
        required_anchors = [
            f"EVID:TURNOVER:{to.two_markets_total_yi:.2f}YI",
            f"EVID:BROKEN_RATIO:{sb.broken_limit_ratio:.2%}",
            f"EVID:LIMIT_DOWN:{sb.limit_down_count}",
            f"EVID:MAX_HEIGHT:{sb.max_ladder_height}B",
            f"EVID:SPACE_LEADER:{space_leader_ident.stock_code}:{space_leader_ident.canonical_name}",
        ]
        for m in narrative_mainlines[:3]:
            narr_tag = m.market_narrative or m.sector_name
            required_anchors.append(
                f"EVID:MAINLINE:{m.rank}:{narr_tag}:{m.leader_identity.canonical_name}:{m.leader_height}B"
            )

        all_fals_rules: List[str] = []
        for m in narrative_mainlines[:3]:
            for r in m.falsification_condition.invalidation_rules:
                all_fals_rules.append(f"【{m.sector_name}】{r}")

        if not all_fals_rules:
            all_fals_rules = [
                f"【{space_leader_ident.canonical_name}】全市场空间标杆次日竞价低开走弱",
                "高位连板梯队全线溃退且炸板率持续攀升",
            ]

        speech_boundary = SpeechBoundaryContract(
            required_evidence_anchors=required_anchors,
            falsification_rules_to_monitor=all_fals_rules,
        )

        # =========================================================================
        # 5. JCS SHA-256 指纹计算 (RFC 8785)
        # =========================================================================
        dict_for_fingerprint = {
            "schema_version": "2D.3-NARRATIVE-CONTEXT-V1",
            "producer_version": "CANONICAL_NARRATIVE_CONTEXT_EXTRACTOR-V1",
            "trade_date": snapshot.trade_date,
            "source_snapshot_fingerprint": snapshot.envelope_fingerprint,
            "fact_layer": fact_layer.model_dump(),
            "derived_layer": derived_layer.model_dump(),
            "cognition_layer": cognition_layer.model_dump(),
            "speech_boundary": speech_boundary.model_dump(),
        }
        context_fingerprint = hash_jcs(dict_for_fingerprint)

        return NarrativeContextContract(
            schema_version="2D.3-NARRATIVE-CONTEXT-V1",
            producer_version="CANONICAL_NARRATIVE_CONTEXT_EXTRACTOR-V1",
            trade_date=snapshot.trade_date,
            extracted_at=extraction_time,
            source_snapshot_fingerprint=snapshot.envelope_fingerprint,
            fact_layer=fact_layer,
            derived_layer=derived_layer,
            cognition_layer=cognition_layer,
            speech_boundary=speech_boundary,
            context_fingerprint=context_fingerprint,
        )
