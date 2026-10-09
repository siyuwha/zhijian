"""
Phase 3A.3: Intraday Safety Guard Service (盘中认知偏离安全守卫服务)
===================================================================
上位依据：
1. 最高董事会终审裁决令：《DOC-92 APPROVED WITH REMEDIATIONS & PHASE 3A.1 AUTHORIZED》
2. 《DOC-92 · Phase 3A 盘中 4 阶段动态跟踪与认知偏离实时告警系统技术设计单》

四大刚性安全职责：
1. 封闭防守词典刚性约束 (Closed-Vocabulary Catalog)：
   - preservation_boundaries 必须严格属于系统预设的封闭安全防守词典；
2. 交易诱导指令物理拦截 (L5 Directive Interception)：
   - 严厉拦截买卖动词、抄底、追涨、加减仓指令及拼音/同音变体；
3. 五位一体锚点类型精准检验：
   - 严格校验 verdict_id, trace_id, hypothesis_id 正则；
   - 严格校验 64 位十六进制 SHA-256 密码学指纹；
4. 安全审查与证伪判定物理解耦与隔离留痕：
   - 安全拦截抛出 IntradaySafetyInterceptionError，错误响应零泄露违规内容。
"""

import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.intraday_drift_verdict import IntradayDriftVerdict
from backend.app.services.intraday_drift_comparator import ALLOWED_INTRADAY_BOUNDARIES
from backend.app.services.briefing_safety_guard import (
    FORBIDDEN_DIRECTIVE_TERMS,
    PHONETIC_DIRECTIVE_TERMS,
    INDIRECT_DIRECTIVE_REGEX,
    HOMOGLYPH_TRANSLATION_TABLE,
    SEP_PATTERN,
)

logger = logging.getLogger(__name__)

# 允许的封闭防守边界集合
ALLOWED_INTRADAY_BOUNDARY_SET: set[str] = set(ALLOWED_INTRADAY_BOUNDARIES.values())

# 正则格式
BUSINESS_HYPO_ID_REGEX = re.compile(r"^HYPO-\d{4}-\d{2}-\d{2}-.*$")
BUSINESS_TRACE_ID_REGEX = re.compile(r"^TRACE-\d{4}-\d{2}-\d{2}-TO-\d{4}-\d{2}-\d{2}-INTRADAY-.*$")
BUSINESS_VERDICT_ID_REGEX = re.compile(r"^VERDICT-\d{4}-\d{2}-\d{2}-INTRADAY-[a-f0-9]{8,12}$")
RULE_VERSION_REGEX = re.compile(r"^\d{4}\.\d{2}\.3A\d+\.V\d+$")
HEX64_SHA256_REGEX = re.compile(r"^[a-f0-9]{64}$")


class IntradaySafetyAuditReport(BaseModel):
    """
    盘中安全审查报告契约
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool = Field(..., description="安全合规审查是否通过")
    audited_at: str = Field(..., description="审查执行时间戳 ISO-8601")
    trace_id: str = Field(..., description="关联的调用 Trace ID")
    violations: List[str] = Field(default_factory=list, description="检举的违规项列表")
    quarantined: bool = Field(False, description="是否已被隔离存档")


class IntradaySafetyInterceptionError(Exception):
    """
    盘中安全守卫拦截异常
    """
    def __init__(self, message: str, audit_report: IntradaySafetyAuditReport):
        super().__init__(message)
        self.message = message
        self.audit_report = audit_report

    def to_safe_error_detail(self) -> Dict[str, Any]:
        """
        生成严格隔离的客户端错误字典 (零违规内容泄露)
        """
        return {
            "error_code": "ERR_INTRADAY_SAFETY_INTERCEPTION",
            "message": "Intraday verdict failed security & compliance guard.",
            "trace_id": self.audit_report.trace_id,
            "audited_at": self.audit_report.audited_at,
            "violations_count": len(self.audit_report.violations),
        }


class IntradaySafetyGuard:
    """
    盘中认知偏离安全守卫引擎
    """

    def __init__(self):
        # 预编译禁止词正则
        self._compiled_forbidden_patterns = [
            re.compile(SEP_PATTERN.join(map(re.escape, term)))
            for term in FORBIDDEN_DIRECTIVE_TERMS
        ]
        self._compiled_phonetic_patterns = [
            re.compile(re.escape(term), re.IGNORECASE)
            for term in PHONETIC_DIRECTIVE_TERMS
        ]
        self._compiled_indirect_patterns = [
            re.compile(p) for p in INDIRECT_DIRECTIVE_REGEX
        ]

    def audit_verdict(self, verdict: IntradayDriftVerdict) -> IntradayDriftVerdict:
        """
        执行全面的安全审查：封闭词典、交易诱导拦截与五位一体格式审计
        """
        violations: List[str] = []
        audited_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")

        # 1. 封闭防守边界词典审计
        for b in verdict.preservation_boundaries:
            if b not in ALLOWED_INTRADAY_BOUNDARY_SET:
                violations.append(f"UNAUTHORIZED_BOUNDARY: Boundary '{b}' is outside closed-vocabulary catalog")

        # 2. 交易诱导指令物理拦截扫描 (扫描自由文本：标题与偏离分析)
        texts_to_scan = [verdict.verdict_headline]
        for a in verdict.assertion_results:
            texts_to_scan.append(a.deviation_analysis)

        for text in texts_to_scan:
            norm_text = text.translate(HOMOGLYPH_TRANSLATION_TABLE)
            # A: 直接禁止词
            for pattern in self._compiled_forbidden_patterns:
                if pattern.search(norm_text):
                    violations.append(f"FORBIDDEN_DIRECTIVE: Detected forbidden trading directive term")
                    break
            # B: 间接句式
            for pattern in self._compiled_indirect_patterns:
                if pattern.search(norm_text):
                    violations.append(f"INDIRECT_DIRECTIVE: Detected indirect operational directive pattern")
                    break
            # C: 拼音变体
            for pattern in self._compiled_phonetic_patterns:
                if pattern.search(norm_text):
                    violations.append(f"PHONETIC_DIRECTIVE: Detected phonetic variant of forbidden directive")
                    break

        # 3. 五位一体锚点类型与格式审计
        if not BUSINESS_VERDICT_ID_REGEX.match(verdict.verdict_id):
            violations.append(f"INVALID_VERDICT_ID_FORMAT: {verdict.verdict_id}")

        if not BUSINESS_TRACE_ID_REGEX.match(verdict.trace_id):
            violations.append(f"INVALID_TRACE_ID_FORMAT: {verdict.trace_id}")

        if not BUSINESS_HYPO_ID_REGEX.match(verdict.hypothesis_id):
            violations.append(f"INVALID_HYPOTHESIS_ID_FORMAT: {verdict.hypothesis_id}")

        if not RULE_VERSION_REGEX.match(verdict.rule_version):
            violations.append(f"INVALID_RULE_VERSION_FORMAT: {verdict.rule_version}")

        # 校验 64 位 SHA-256 十六进制指纹
        for fp_name, fp_val in [
            ("hypothesis_fingerprint", verdict.hypothesis_fingerprint),
            ("intraday_snapshot_fingerprint", verdict.intraday_snapshot_fingerprint),
            ("threshold_config_hash", verdict.threshold_config_hash),
            ("verdict_fingerprint", verdict.verdict_fingerprint),
        ]:
            if not HEX64_SHA256_REGEX.match(fp_val):
                violations.append(f"INVALID_HEX64_FINGERPRINT: {fp_name} ('{fp_val}') is not valid 64-char SHA256")

        # 4. 判定与处置
        if violations:
            logger.warning(
                f"[IntradaySafetyGuard] Intercepted {len(violations)} safety violations for Trace {verdict.trace_id}"
            )
            report = IntradaySafetyAuditReport(
                passed=False,
                audited_at=audited_at,
                trace_id=verdict.trace_id,
                violations=violations,
                quarantined=True,
            )
            raise IntradaySafetyInterceptionError(
                message=f"Intraday verdict failed security compliance ({len(violations)} violations)",
                audit_report=report,
            )

        return verdict
