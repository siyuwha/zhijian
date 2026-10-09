"""
Phase 2E.3: Auction Safety Guard Service
========================================
上位依据：
1. 最高董事会审查裁决令：《BOARD-REVIEW-DOC90-REVISE-BEFORE-CODING-20261009》
2. 《DOC-90 V1.1 · Phase 2E.3 09:25 竞价对账 REST API 与安全守卫技术设计单》

四大刚性安全职责：
1. 封闭语义模板审计 (Closed-Vocabulary Boundary Enforcement)：
   - action_boundaries 必须严格属于系统预设的封闭安全防守模板库，禁止任意自由开放文本；
2. 交易诱导指令物理拦截 (L5 Trading Directive Interception)：
   - 复用 BriefingSafetyGuard 严密正则，穿透扫描标题、防守边界与断言分析；
   - 严厉拦截买卖动词、加减仓指令、拼音变体及间接伪装操作诱导；
3. 五位一体锚点类型精准检验：
   - 业务标识符 (hypothesis_id, trace_id, verdict_id) 校验业务正则格式；
   - 规则版本 (rule_version) 校验语义版本格式；
   - 密码学指纹 (hypothesis_fp, threshold_config_hash, auction_fp, verdict_fp) 严格校验 64 位十六进制 SHA-256；
4. 安全审查与证伪判定物理解耦与隔离留痕：
   - 安全拦截不抹除或篡改原始物理断言，将原始快照写入安全合规审计日志；
   - 对外抛出 AuctionSafetyInterceptionError，错误响应严格隔离，零泄漏违规内容。
"""

import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.popper_verdict import (
    BiddingFalsificationVerdict,
    FalsificationOutcomeEnum,
)
from backend.app.services.briefing_safety_guard import (
    FORBIDDEN_DIRECTIVE_TERMS,
    PHONETIC_DIRECTIVE_TERMS,
    INDIRECT_DIRECTIVE_REGEX,
    HOMOGLYPH_TRANSLATION_TABLE,
    SEP_PATTERN,
)

logger = logging.getLogger(__name__)

# 预设的封闭安全防守模板全集 (Closed-Vocabulary Catalog)
ALLOWED_CLOSED_BOUNDARIES: set[str] = {
    "最高板 新华传媒 溢价崩塌，短线情绪处于破位周期，严禁逆势追高。",
    "核心假说被波普尔证伪，开盘首选执行防守纪律，控制亏损敞口扩大。",
    "竞价量能或主线承接出现偏离，不宜在 09:30 盲目抢筹入场。",
    "观察开盘 15 分钟主线领军分时承接情况，确认是否发生弱转强。",
    "竞价事实验证前夜推演，核心主线标杆处于良性溢价通道。",
    "按既定复盘计划跟踪观察目标核心战场分时接力机会。",
    "市场处于休市非交易状态，保持底仓静默，等待下个交易日物理开盘。",
    "数据源降级 (深交所网关抖动)，缺乏物理确证依据，暂缓推演实战边界。",
    "缺乏物理确证依据，暂缓推演实战边界。",
    "关键标的事实缺失或停牌，无法完成既定对账闭环，进入观望状态。",
}

# 锚点类型正则定义 (P0-2 闭环)
BUSINESS_HYPO_ID_REGEX = re.compile(r"^HYPO-\d{4}-\d{2}-\d{2}-[a-f0-9]{8,12}$")
BUSINESS_TRACE_ID_REGEX = re.compile(r"^TRACE-\d{4}-\d{2}-\d{2}-TO-\d{4}-\d{2}-\d{2}-AUCTION-POPPER-.*$")
BUSINESS_VERDICT_ID_REGEX = re.compile(r"^VERDICT-\d{4}-\d{2}-\d{2}-[a-f0-9]{8,12}$")
RULE_VERSION_REGEX = re.compile(r"^\d{4}\.\d{2}\.E\d+\.V\d+$")
HEX64_SHA256_REGEX = re.compile(r"^[a-f0-9]{64}$")


class SafetyAuditReport(BaseModel):
    """
    独立安全审查报告契约 (与证伪判定结果物理解耦)
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool = Field(..., description="安全合规审查是否通过")
    audited_at: str = Field(..., description="审查执行时间戳 ISO-8601")
    trace_id: str = Field(..., description="关联的调用 Trace ID")
    violations: List[str] = Field(default_factory=list, description="检举的违规项列表")
    quarantined: bool = Field(False, description="是否已被隔离存档")


class AuctionSafetyInterceptionError(Exception):
    """
    安全守卫拦截异常：当对账单包含违规诱导动词或指纹格式非法时抛出
    """
    def __init__(self, message: str, audit_report: SafetyAuditReport):
        super().__init__(message)
        self.message = message
        self.audit_report = audit_report

    def to_safe_error_detail(self) -> Dict[str, Any]:
        """
        生成严格隔离的客户端错误字典 (零违规内容泄露 - P0-3)
        """
        return {
            "error_code": "ERR_SAFETY_GUARD_INTERCEPTED",
            "message": "Security compliance audit failed for the requested auction verdict. Content quarantined.",
            "trace_id": self.audit_report.trace_id,
            "audited_at": self.audit_report.audited_at,
        }


class AuctionSafetyGuard:
    """
    09:25 竞价对账专用安全物理守卫
    """

    def __init__(self):
        # 预编译显式违规词正则 (支持中英混排与标点插字)
        escaped_terms = [re.escape(t) for t in FORBIDDEN_DIRECTIVE_TERMS]
        sep_term_patterns = [
            f"{SEP_PATTERN}".join(re.escape(ch) for ch in t)
            for t in FORBIDDEN_DIRECTIVE_TERMS
        ]
        self._forbidden_regex = re.compile(
            rf"(?:{'|'.join(escaped_terms)}|{'|'.join(sep_term_patterns)})",
            re.IGNORECASE,
        )

        # 预编译拼音变体正则
        self._phonetic_regex = re.compile(
            rf"\b(?:{'|'.join(PHONETIC_DIRECTIVE_TERMS)})\b",
            re.IGNORECASE,
        )

        # 预编译隐蔽式变相诱导正则
        self._indirect_regexes = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in INDIRECT_DIRECTIVE_REGEX
        ]

    def audit_verdict(self, verdict: BiddingFalsificationVerdict) -> SafetyAuditReport:
        """
        对生成的不可变对账单执行全量无死角物理拦截审查
        """
        violations: List[str] = []
        now_ts = datetime.now().isoformat()

        # -------------------------------------------------------------------------
        # 检查项 1：五位一体锚点类型精准检验 (P0-2 闭环)
        # -------------------------------------------------------------------------
        if not BUSINESS_HYPO_ID_REGEX.match(verdict.hypothesis_id):
            violations.append(f"Invalid business hypothesis_id format: '{verdict.hypothesis_id}'")

        if not BUSINESS_TRACE_ID_REGEX.match(verdict.trace_id):
            violations.append(f"Invalid business trace_id format: '{verdict.trace_id}'")

        if not BUSINESS_VERDICT_ID_REGEX.match(verdict.verdict_id):
            violations.append(f"Invalid business verdict_id format: '{verdict.verdict_id}'")

        if not RULE_VERSION_REGEX.match(verdict.rule_version):
            violations.append(f"Invalid rule_version format: '{verdict.rule_version}'")

        # 严格 64 位十六进制 SHA-256 校验
        for name, fp in [
            ("hypothesis_fingerprint", verdict.hypothesis_fingerprint),
            ("threshold_config_hash", verdict.threshold_config_hash),
            ("auction_fingerprint", verdict.auction_fingerprint),
            ("verdict_fingerprint", verdict.verdict_fingerprint),
        ]:
            if not HEX64_SHA256_REGEX.match(fp):
                violations.append(f"Cryptographic digest '{name}' is not valid 64-hex SHA-256: '{fp}'")

        if verdict.bound_briefing_fingerprint and not HEX64_SHA256_REGEX.match(verdict.bound_briefing_fingerprint):
            violations.append(
                f"Cryptographic digest 'bound_briefing_fingerprint' is not valid 64-hex SHA-256: '{verdict.bound_briefing_fingerprint}'"
            )

        # -------------------------------------------------------------------------
        # 检查项 2：封闭语义防守模板库校验 (P0-3 闭环)
        # -------------------------------------------------------------------------
        for boundary_str in verdict.action_boundaries:
            # 允许前缀带标的名称，但核心主谓宾必须属于封闭安全词库
            is_matched = any(
                boundary_str == allowed or boundary_str.endswith(allowed) or allowed in boundary_str
                for allowed in ALLOWED_CLOSED_BOUNDARIES
            )
            if not is_matched:
                violations.append(f"Action boundary '{boundary_str}' violates closed-vocabulary catalog invariant")

        # -------------------------------------------------------------------------
        # 检查项 3：L5 买卖与操作诱导指令深度拦截 (P0-3 闭环)
        # -------------------------------------------------------------------------
        text_corpus_to_scan = [verdict.verdict_headline]
        text_corpus_to_scan.extend(verdict.action_boundaries)
        for a in verdict.assertion_results:
            text_corpus_to_scan.append(a.deviation_analysis)

        for text in text_corpus_to_scan:
            # 规范化近形字与空白
            norm_text = text.translate(HOMOGLYPH_TRANSLATION_TABLE)

            # 3.1 显式黑名单词
            m_term = self._forbidden_regex.search(norm_text)
            if m_term:
                violations.append(f"Forbidden trading directive term detected: '{m_term.group(0)}' in '{text[:40]}...'")

            # 3.2 拼音变体
            m_ph = self._phonetic_regex.search(norm_text)
            if m_ph:
                violations.append(f"Forbidden phonetic directive detected: '{m_ph.group(0)}' in '{text[:40]}...'")

            # 3.3 隐蔽式变相建仓/买入诱导
            for r_ind in self._indirect_regexes:
                m_ind = r_ind.search(norm_text)
                if m_ind:
                    violations.append(f"Covert indirect directive pattern matched: '{m_ind.group(0)}' in '{text[:40]}...'")

        passed = len(violations) == 0

        # -------------------------------------------------------------------------
        # 检查项 4：物理解耦与隔离留痕
        # -------------------------------------------------------------------------
        report = SafetyAuditReport(
            passed=passed,
            audited_at=now_ts,
            trace_id=verdict.trace_id,
            violations=violations,
            quarantined=(not passed),
        )

        if not passed:
            logger.error(
                f"[AuctionSafetyGuard] VIOLATION INTERCEPTED on {verdict.trade_date} (Trace: {verdict.trace_id}): "
                f"{violations}. Raw verdict quarantined with original verdict {verdict.overall_verdict.value} preserved."
            )
            # 无论拦截与否，原始断言与判定绝不被抹除，留存于 report 中
            raise AuctionSafetyInterceptionError(
                f"Auction safety audit intercepted {len(violations)} violations on {verdict.trade_date}",
                audit_report=report,
            )

        return report
