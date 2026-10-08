"""
Phase 2D.3-B: Briefing Safety Guard Service
===========================================
上位依据：
1. 最高董事会 2026-10-09 裁决令：《Phase 2D.3-B 授权与安全防线规范》
2. 《DOC-80 · Phase 2D.3 受约束 LLM 实战战报生成器技术设计单》

核心职责：
- 充当战报生成链路的“后置物理拦截审查器” (Post-Generation Hard Interceptor)；
- 100% 杜绝 LLM 幻觉数字漂移 (Numerical Fidelity Guard)；
- 100% 杜绝实体身份漂移，坚决防御 002242 -> 毅昌科技 (Entity Identity Guard)；
- 100% 拦截一切 L5 买卖/仓位交易指令与价格预测 (Illegal Directive Defense)；
- 100% 校验长度、排版与必备证据锚点 (Structure & Speech Boundary Guard)；
- 审查不通过则返回明确 violations，触发无感安全降级。
"""

import re
from datetime import datetime
from typing import List, Dict, Optional, Set, Any

from backend.app.schemas.narrative_context import NarrativeContextContract
from backend.app.schemas.tactical_briefing import (
    TacticalBriefingReport,
    SafetyAuditResult,
)
from backend.app.schemas.canonical_market import CanonicalSecurityIdentity
from backend.app.services.canonical_market_service import CanonicalSecurityMasterRegistry


# 绝对禁止出现的 L5 交易指令与主观操作引导词汇
FORBIDDEN_DIRECTIVE_TERMS: List[str] = [
    "买入", "卖出", "加仓", "减仓", "建仓", "满仓", "半仓", "清仓",
    "抄底", "割肉", "冲锋", "梭哈", "追高", "建议操作", "目标价",
    "止盈", "止损", "开仓", "平仓", "低吸", "重仓", "轻仓", "打板买入"
]


class BriefingSafetyGuard:
    """
    战报安全合规审查器 (BriefingSafetyGuard)
    双轨物理拦截，确保对外发布的每一份战报在数学、实体、法律和风控上绝对保真。
    """

    def __init__(self, registry: Optional[CanonicalSecurityMasterRegistry] = None):
        self.custom_registry = registry

    def audit(
        self,
        report_or_text: str | TacticalBriefingReport,
        context: NarrativeContextContract,
        key_battlegrounds: Optional[List[str]] = None,
        risk_warnings: Optional[List[str]] = None,
        next_day_observation_posts: Optional[List[str]] = None,
    ) -> SafetyAuditResult:
        """
        全量执行四大安全合规审查项：
        1. 数字保真度审查 (Numerical Fidelity)
        2. 标的身份单射与 002242 防御审查 (Entity Master Binding)
        3. 交易指令与发言禁区拦截审查 (Illegal Directive Defense)
        4. 结构完整度与必备证据锚点审查 (Structure & Anchors)
        """
        if isinstance(report_or_text, TacticalBriefingReport):
            text = report_or_text.tactical_briefing_text
            battlegrounds = report_or_text.key_battlegrounds
            risks = report_or_text.risk_warnings
            observations = report_or_text.next_day_observation_posts
        else:
            text = str(report_or_text)
            battlegrounds = key_battlegrounds or []
            risks = risk_warnings or []
            observations = next_day_observation_posts or []

        violations: List[str] = []
        checks_run: List[str] = [
            "NumericalFidelityGuard",
            "EntityMasterIntegrityGuard",
            "IllegalDirectiveDefense",
            "StructureAndAnchorsGuard",
        ]

        # 1. 数字保真度审查
        violations.extend(self._check_numerical_fidelity(text, context))

        # 2. 实体身份单射与 002242 防御审查
        violations.extend(self._check_entity_master_binding(text, context))

        # 3. 交易指令与发言边界拦截审查
        violations.extend(
            self._check_illegal_directives(
                text=text,
                battlegrounds=battlegrounds,
                risks=risks,
                observations=observations,
                context=context,
            )
        )

        # 4. 结构完整度与必备证据锚点审查
        violations.extend(
            self._check_structure_and_anchors(
                report_or_text=report_or_text,
                text=text,
                battlegrounds=battlegrounds,
                risks=risks,
                observations=observations,
                context=context,
            )
        )

        passed = len(violations) == 0
        audited_at = datetime.now().isoformat()

        return SafetyAuditResult(
            passed=passed,
            trade_date=context.trade_date,
            audited_at=audited_at,
            checks_run=checks_run,
            violations=violations,
            sanitized_text=text if passed else None,
        )

    # -------------------------------------------------------------------------
    # 审查项 1: 数字保真度审查 (Numerical Fidelity)
    # -------------------------------------------------------------------------
    def _check_numerical_fidelity(
        self, text: str, context: NarrativeContextContract
    ) -> List[str]:
        violations: List[str] = []

        # 1.1 总成交额校验
        turnover_patterns = [
            r'(?:两市|沪深两市)?(?:真实)?(?:总成交额|总成交|成交额|成交金额)[^，。；\n]{0,10}?([0-9]+(?:\.[0-9]+)?)\s*(?:亿元|亿)',
            r'([0-9]+(?:\.[0-9]+)?)\s*(?:亿元|亿)[^，。；\n]{0,10}?(?:的总成交|成交额)',
        ]
        true_turnover = context.fact_layer.turnover.total_turnover_yi
        for pat in turnover_patterns:
            matches = re.finditer(pat, text)
            for m in matches:
                val = float(m.group(1))
                rel_diff = abs(val - true_turnover) / true_turnover
                abs_diff = abs(val - true_turnover)
                if rel_diff > 0.001 and abs_diff > 1.0:
                    violations.append(
                        f"NumericalFidelityViolation: Total turnover '{val}' diverges from true fact "
                        f"'{true_turnover:.2f}' (divergence: {abs_diff:.2f}亿 > 0.1% tolerance)"
                    )

        # 1.2 炸板率校验
        broken_patterns = [
            r'(?:真实)?炸板率[^，。；\n]{0,10}?([0-9]+(?:\.[0-9]+)?)\s*%',
            r'([0-9]+(?:\.[0-9]+)?)\s*%[^，。；\n]{0,10}?(?:真实)?炸板率',
        ]
        true_broken_pct = context.derived_layer.broken_limit_ratio * 100
        for pat in broken_patterns:
            matches = re.finditer(pat, text)
            for m in matches:
                val = float(m.group(1))
                if abs(val - true_broken_pct) > 0.2:
                    violations.append(
                        f"NumericalFidelityViolation: Broken limit ratio '{val}%' diverges from derived fact "
                        f"'{true_broken_pct:.2f}%'"
                    )

        # 1.3 空间最高板高度校验
        space_leader_patterns = [
            r'(?:最高空间标杆|空间标杆|高度标杆|全市场最高板|最高板)[^，。；\n]{0,15}?([0-9]+)\s*(?:连板|板|B)',
            r'([0-9]+)\s*(?:连板|板|B)[^，。；\n]{0,15}?(?:最高空间标杆|空间标杆|高度标杆)',
        ]
        true_max_height = context.fact_layer.ladder.max_height
        for pat in space_leader_patterns:
            matches = re.finditer(pat, text)
            for m in matches:
                val = int(m.group(1))
                if val != true_max_height:
                    violations.append(
                        f"NumericalFidelityViolation: Space leader max height '{val}B' diverges from true fact "
                        f"'{true_max_height}B'"
                    )

        # 1.4 全市场收盘跌停家数校验
        down_patterns = [
            r'(?:收盘)?跌停[^，。；\n]{0,10}?([0-9]+)\s*(?:只|家)',
            r'([0-9]+)\s*(?:只|家)[^，。；\n]{0,10}?(?:收盘)?跌停',
        ]
        true_down = context.fact_layer.sentiment_counts.limit_down_count
        for pat in down_patterns:
            matches = re.finditer(pat, text)
            for m in matches:
                val = int(m.group(1))
                if abs(val - true_down) > 0:
                    violations.append(
                        f"NumericalFidelityViolation: Limit down count '{val}' diverges from true fact "
                        f"'{true_down}'"
                    )

        # 1.5 严重异常波动家数校验
        reg_patterns = [
            r'(?:严重异常波动|严重异动|监管异动)[^，。；\n]{0,20}?([0-9]+)\s*(?:只|家)',
            r'([0-9]+)\s*(?:只|家)[^，。；\n]{0,10}?(?:严重异常波动|严重异动)',
        ]
        true_anomaly = context.fact_layer.regulatory.total_anomaly_count
        for pat in reg_patterns:
            matches = re.finditer(pat, text)
            for m in matches:
                val = int(m.group(1))
                if abs(val - true_anomaly) > 0:
                    violations.append(
                        f"NumericalFidelityViolation: Regulatory anomaly count '{val}' diverges from true fact "
                        f"'{true_anomaly}'"
                    )

        return violations

    # -------------------------------------------------------------------------
    # 审查项 2: 实体身份单射与 002242 防御审查
    # -------------------------------------------------------------------------
    def _check_entity_master_binding(
        self, text: str, context: NarrativeContextContract
    ) -> List[str]:
        violations: List[str] = []

        # 2.1 刚性红线: 毅昌科技绝对禁止出现 (002242 历史重大实体混淆防御)
        if "毅昌科技" in text:
            violations.append(
                "EntityIdentityViolation: '毅昌科技' is strictly forbidden in tactical briefing. "
                "Stock '002242' is authoritative '九阳股份', never '毅昌科技'!"
            )

        # 2.2 构建当前合法的个股主数据字典 (从 context 与 custom_registry)
        authorized_identities: Dict[str, str] = {}  # code -> name
        if self.custom_registry:
            for c, id_obj in self.custom_registry.get_dictionary().items():
                authorized_identities[c] = id_obj.canonical_name

        # 从 contract 注入所有已知个股身份
        for tier in context.fact_layer.ladder.tiers:
            for s in tier.stocks:
                authorized_identities[s.stock_code] = s.canonical_name
        authorized_identities[context.fact_layer.ladder.space_leader.stock_code] = (
            context.fact_layer.ladder.space_leader.canonical_name
        )
        for anom in context.fact_layer.regulatory.anomaly_stocks:
            authorized_identities[anom.stock_code] = anom.canonical_name
        for ml in context.cognition_layer.candidate_mainlines:
            authorized_identities[ml.leader_identity.stock_code] = ml.leader_identity.canonical_name

        # 2.3 检查 002242 的映射
        if "002242" in text:
            # 若包含 002242，附近必须不得出现除 九阳股份 之外的错误名称
            surrounding = text[max(0, text.find("002242") - 20) : min(len(text), text.find("002242") + 30)]
            if "毅昌科技" in surrounding:
                violations.append(
                    "EntityIdentityViolation: Code '002242' associated with '毅昌科技' detected in text."
                )

        # 2.4 扫描文本中出现的 6 位股票代码，必须属于 authorized_identities
        code_matches = re.findall(r'\b([0-368][0-9]{5})\b', text)
        for code in code_matches:
            if code not in authorized_identities:
                violations.append(
                    f"EntityIdentityViolation: Unregistered security code referenced in briefing text: '{code}'"
                )

        return violations

    # -------------------------------------------------------------------------
    # 审查项 3: 交易指令与发言禁区拦截审查 (Illegal Directive Defense)
    # -------------------------------------------------------------------------
    def _check_illegal_directives(
        self,
        text: str,
        battlegrounds: List[str],
        risks: List[str],
        observations: List[str],
        context: NarrativeContextContract,
    ) -> List[str]:
        violations: List[str] = []

        all_content_blocks = [text] + battlegrounds + risks + observations
        combined_text = "\n".join(all_content_blocks)

        # 3.1 违规 L5 交易指令词汇扫描
        for term in FORBIDDEN_DIRECTIVE_TERMS:
            if term in combined_text:
                violations.append(
                    f"IllegalDirectiveViolation: Forbidden L5 trading directive term detected: '{term}'"
                )

        # 3.2 预测具体目标价 / 买卖点位扫描
        price_target_patterns = [
            r'目标价\s*[:：]?\s*[0-9]+(?:\.[0-9]+)?\s*元?',
            r'上看\s*[0-9]+(?:\.[0-9]+)?\s*元',
            r'买入点\s*[:：]?\s*[0-9]+(?:\.[0-9]+)?',
            r'止损价\s*[:：]?\s*[0-9]+(?:\.[0-9]+)?',
        ]
        for pat in price_target_patterns:
            if re.search(pat, combined_text):
                violations.append(
                    "ForbiddenClaimViolation: Unverified price target / exact trading level prediction detected."
                )
                break

        # 3.3 创业板重复累加会计违规扫描 (REDUNDANT_DOUBLE_COUNT_CLAIMS)
        double_count_patterns = [
            r'加上创业板(?:后)?两市成交',
            r'总成交额加上创业板',
            r'两市加上创业板共',
        ]
        for pat in double_count_patterns:
            if re.search(pat, combined_text):
                violations.append(
                    "ForbiddenClaimViolation: Redundant double-count accounting claim detected "
                    "(ChiNext already included in Shenzhen turnover)."
                )

        # 3.4 主线事实化伪造声明 (COGNITION_TO_FACT_PROMOTION)
        fact_promotion_patterns = [
            r'主线已成为绝对客观事实',
            r'毫无疑问的绝对主线',
        ]
        for pat in fact_promotion_patterns:
            if re.search(pat, combined_text):
                violations.append(
                    "ForbiddenClaimViolation: Cognition-to-fact promotion detected "
                    "(L3 hypothesis promoted to L0 physical truth)."
                )

        return violations

    # -------------------------------------------------------------------------
    # 审查项 4: 结构完整度与必备证据锚点审查 (Structure & Anchors)
    # -------------------------------------------------------------------------
    def _check_structure_and_anchors(
        self,
        text: str,
        battlegrounds: List[str],
        risks: List[str],
        observations: List[str],
        context: NarrativeContextContract,
        report_or_text: Optional[Any] = None,
    ) -> List[str]:
        violations: List[str] = []

        # 4.1 文本长度校验 (150 ~ 600 字，设计区间 250 ~ 350 字)
        clean_text = text.strip()
        if len(clean_text) < 150:
            violations.append(
                f"StructureViolation: Tactical briefing text is too short ({len(clean_text)} chars, minimum is 150)"
            )
        elif len(clean_text) > 600:
            violations.append(
                f"StructureViolation: Tactical briefing text is too long ({len(clean_text)} chars, maximum is 600)"
            )

        # 4.2 结构列表非空校验 (若审查完整报告，或调用方显式提供了结构化列表)
        if isinstance(report_or_text, TacticalBriefingReport):
            if not battlegrounds:
                violations.append("StructureViolation: 'key_battlegrounds' list cannot be empty")
            if not risks:
                violations.append("StructureViolation: 'risk_warnings' list cannot be empty")
            if not observations:
                violations.append("StructureViolation: 'next_day_observation_posts' list cannot be empty")

        # 4.3 必备证据锚点校验 (至少覆盖 3 个)
        anchors_found = 0
        # 锚点 A: 成交额
        if re.search(r'(?:成交额|成交金额|总成交)', clean_text):
            anchors_found += 1
        # 锚点 B: 空间最高板或连板高度
        if str(context.fact_layer.ladder.max_height) in clean_text or "空间" in clean_text:
            anchors_found += 1
        # 锚点 C: 炸板率或负反馈
        if "炸板" in clean_text or "跌停" in clean_text:
            anchors_found += 1
        # 锚点 D: 市场状态
        if context.cognition_layer.market_state.state_display_name in clean_text:
            anchors_found += 1
        # 锚点 E: 核心主线龙头
        if context.cognition_layer.candidate_mainlines:
            top_leader = context.cognition_layer.candidate_mainlines[0].leader_identity.canonical_name
            if top_leader in clean_text:
                anchors_found += 1

        if anchors_found < 3:
            violations.append(
                f"StructureViolation: Insufficient required evidence anchors satisfied (found {anchors_found}, required >= 3)"
            )

        return violations
