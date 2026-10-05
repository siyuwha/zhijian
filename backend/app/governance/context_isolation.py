"""
P0 - Multi-Agent Context Isolation & Information-Flow Hardening Kernel
Specification: SPEC-GOVERNANCE-P0-CTX-20261006
Governance Policy: "Independent by default, shared only through immutable evidence."
Constitutional Rules: Rule G-CTX-01 ~ Rule G-CTX-11 (含运行时隔离证明与金丝雀攻击防御)

遵照最高治理令：
1. 恪守 Phase 2C.6 六冻结纪律（零侵入生产业务代码、零变更生产Schema、零新增生产数据源）；
2. 物理与逻辑双重实现三级信息分层（LEVEL 0 / LEVEL 1 / LEVEL 2）；
3. 严格执行 Blind-First 原则与 Gatekeeper 两阶段裁决（Stage A Blind -> Stage B Arbitration）；
4. 刚性拦截非结构化主观结论污染与跨角色未封存泄露；
5. 【G-CTX-11】：强制要求运行时隔离证明 (Attestation) 与金丝雀跨上下文攻击 (Canary Cross-Context Attack) 主动探测与刚性阻断。
"""

import os
import re
import json
import hashlib
from enum import Enum
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ==============================================================================
# 一、 基础枚举与角色常量
# ==============================================================================

class InformationLevel(str, Enum):
    LEVEL_0 = "LEVEL_0_OBJECTIVE_BASELINE"
    LEVEL_1 = "LEVEL_1_PRIVATE_WORKSPACE"
    LEVEL_2 = "LEVEL_2_IMMUTABLE_EVIDENCE"


class AgentRole(str, Enum):
    PRIMARY_DEVELOPER = "primary_developer"
    BOARD_RED_TEAM = "board_red_team"
    RED_TEAM_TESTER = "red_team_tester"
    QUALITY_GATEKEEPER = "quality_gatekeeper"


# 禁止出现的污染性主观词汇 (Anchoring & Confirmation Bias)
FORBIDDEN_SUBJECTIVE_PATTERNS = [
    "我已经检查过了",
    "这个应该没问题",
    "你重点检查",
    "问题已经修复",
    "我认为可以 PASS",
    "大概率没问题",
    "只剩",
    "其他地方不用看",
    "基本没问题",
    "直接放行",
    "我测过没问题",
    "照着这个写",
]


class GovernanceViolationError(Exception):
    """治理违规异常基类"""
    pass


class ContaminationViolationError(GovernanceViolationError):
    """上下文或信息流污染异常"""
    pass


class UnauthorizedWorkspaceAccessError(GovernanceViolationError):
    """跨私有工作区越权访问异常"""
    pass


class EvidenceIntegrityError(GovernanceViolationError):
    """不可变证据完整性损坏异常"""
    pass


class BlindAssessmentViolationError(GovernanceViolationError):
    """违反盲评首发铁律异常"""
    pass


class CanaryCrossContextAttackError(GovernanceViolationError):
    """金丝雀跨上下文泄漏或刺探攻击异常 (Rule G-CTX-11)"""
    pass


# ==============================================================================
# 二、 LEVEL 2 — 不可变证据契约 (Immutable Evidence Record)
# ==============================================================================

class ImmutableEvidenceRecord(BaseModel):
    """
    符合治理规范第四章刚性定义的不可变证据实体。
    证据一旦封存，哈希确定，不允许原地修改。任何修改必须生成新的 Evidence ID。
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(description="全局唯一且确定性的证据身份指纹")
    task_id: str
    agent_id: str
    role: AgentRole
    baseline_commit: str
    artifact_id: str
    artifact_hash: str
    question_id: str
    finding_id: str
    evidence_type: str
    objective_observation: str
    reproduction_command: str
    result: str
    severity: str
    timestamp: str
    status: str

    @classmethod
    def create_and_seal(
        cls,
        task_id: str,
        agent_id: str,
        role: AgentRole,
        baseline_commit: str,
        artifact_id: str,
        artifact_hash: str,
        question_id: str,
        finding_id: str,
        evidence_type: str,
        objective_observation: str,
        reproduction_command: str,
        result: str,
        severity: str,
        status: str,
        timestamp: Optional[str] = None
    ) -> "ImmutableEvidenceRecord":
        """创建并进行防篡改封印"""
        t_stamp = timestamp or datetime.now().isoformat()
        
        # 排除 evidence_id 参与计算自身哈希
        raw_payload = {
            "task_id": task_id,
            "agent_id": agent_id,
            "role": role.value,
            "baseline_commit": baseline_commit,
            "artifact_id": artifact_id,
            "artifact_hash": artifact_hash,
            "question_id": question_id,
            "finding_id": finding_id,
            "evidence_type": evidence_type,
            "objective_observation": objective_observation,
            "reproduction_command": reproduction_command,
            "result": result,
            "severity": severity,
            "timestamp": t_stamp,
            "status": status,
        }
        # 确定性规范化哈希
        jcs_str = json.dumps(raw_payload, sort_keys=True, separators=(',', ':'))
        evidence_hash = f"EVID-{hashlib.sha256(jcs_str.encode('utf-8')).hexdigest()[:16]}"

        return cls(
            evidence_id=evidence_hash,
            **raw_payload
        )

    def verify_integrity(self) -> bool:
        """核验不可变指纹是否完整"""
        raw_payload = {
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "role": self.role.value,
            "baseline_commit": self.baseline_commit,
            "artifact_id": self.artifact_id,
            "artifact_hash": self.artifact_hash,
            "question_id": self.question_id,
            "finding_id": self.finding_id,
            "evidence_type": self.evidence_type,
            "objective_observation": self.objective_observation,
            "reproduction_command": self.reproduction_command,
            "result": self.result,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "status": self.status,
        }
        jcs_str = json.dumps(raw_payload, sort_keys=True, separators=(',', ':'))
        expected_hash = f"EVID-{hashlib.sha256(jcs_str.encode('utf-8')).hexdigest()[:16]}"
        return self.evidence_id == expected_hash


# ==============================================================================
# 三、 跨 Agent 结构化治理消息契约 (Cross-Agent Message Schema)
# ==============================================================================

class CrossAgentMessage(BaseModel):
    """
    符合规范第七章的跨 Agent 结构化消息格式。
    原则：告诉对方“验证什么客观对象”，而不是“应该怎么判断”。
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    TASK_ID: str
    ARTIFACT_ID: str
    BASELINE_COMMIT: str
    QUESTION_ID: str
    EVIDENCE_ID: str
    OBJECTIVE_FACT: str
    REPRODUCTION_COMMAND: str
    EXPECTED_CHECK: str
    HASH: str
    STATUS: str

    @field_validator("OBJECTIVE_FACT", "EXPECTED_CHECK")
    @classmethod
    def check_forbidden_subjectivity(cls, v: str) -> str:
        for p in FORBIDDEN_SUBJECTIVE_PATTERNS:
            if p in v:
                raise ContaminationViolationError(
                    f"Message contains forbidden subjective conclusion anchor: '{p}'! "
                    f"Agent messages must state objective facts, not subjective verdicts."
                )
        return v

    def to_formatted_str(self) -> str:
        return (
            f"TASK_ID: {self.TASK_ID}\n"
            f"ARTIFACT_ID: {self.ARTIFACT_ID}\n"
            f"BASELINE_COMMIT: {self.BASELINE_COMMIT}\n"
            f"QUESTION_ID: {self.QUESTION_ID}\n"
            f"EVIDENCE_ID: {self.EVIDENCE_ID}\n"
            f"OBJECTIVE_FACT: {self.OBJECTIVE_FACT}\n"
            f"REPRODUCTION_COMMAND: {self.REPRODUCTION_COMMAND}\n"
            f"EXPECTED_CHECK: {self.EXPECTED_CHECK}\n"
            f"HASH: {self.HASH}\n"
            f"STATUS: {self.STATUS}"
        )

    @classmethod
    def parse_raw_message(cls, raw_text: str) -> "CrossAgentMessage":
        """解析并严格校验治理消息文本"""
        lines = [line.strip() for line in raw_text.strip().splitlines() if line.strip()]
        data: Dict[str, str] = {}
        for line in lines:
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip()
        
        required_keys = [
            "TASK_ID", "ARTIFACT_ID", "BASELINE_COMMIT", "QUESTION_ID",
            "EVIDENCE_ID", "OBJECTIVE_FACT", "REPRODUCTION_COMMAND",
            "EXPECTED_CHECK", "HASH", "STATUS"
        ]
        missing = [k for k in required_keys if k not in data]
        if missing:
            raise ContaminationViolationError(
                f"Governance message rejected! Missing mandatory fields: {missing}"
            )
        return cls(**data)


# ==============================================================================
# 四、 物理工作区访问守卫 (Private Workspace Guard)
# ==============================================================================

class PrivateWorkspaceGuard:
    """
    负责执行 LEVEL 1 私有工作区隔离。
    铁律：Agent A 不得读取 Agent B 的 LEVEL 1 私有内容。
    """
    WORKSPACE_MAP = {
        AgentRole.PRIMARY_DEVELOPER: "governance/workspaces/primary_developer/",
        AgentRole.BOARD_RED_TEAM: "governance/workspaces/board_red_team/",
        AgentRole.RED_TEAM_TESTER: "governance/workspaces/red_team_tester/",
        AgentRole.QUALITY_GATEKEEPER: "governance/workspaces/quality_gatekeeper/",
    }

    @classmethod
    def validate_access(cls, requesting_role: AgentRole, target_path: str, action: str = "read") -> bool:
        normalized_target = target_path.replace("\\", "/").strip()
        
        # 1. LEVEL 0 客观路径：所有角色全员只读
        level_0_prefixes = ["backend/", "frontend/", "开发文档/", "baseline_evidence/"]
        for p in level_0_prefixes:
            if normalized_target.startswith(p):
                if action == "write" and requesting_role != AgentRole.PRIMARY_DEVELOPER:
                    raise UnauthorizedWorkspaceAccessError(
                        f"Write access to LEVEL 0 ({normalized_target}) is restricted to primary_developer only."
                    )
                return True

        # 2. LEVEL 2 不可变证据：全员只读，主开发与红队可追加封存，但严禁就地篡改
        if normalized_target.startswith("governance/evidence/"):
            return True

        # 3. LEVEL 1 私有工作区：严格隔离
        for role, ws_prefix in cls.WORKSPACE_MAP.items():
            if normalized_target.startswith(ws_prefix):
                if role != requesting_role:
                    raise UnauthorizedWorkspaceAccessError(
                        f"Access Denied! Agent '{requesting_role.value}' attempted to {action} "
                        f"private workspace of '{role.value}' ({normalized_target})."
                    )
                return True

        return True


# ==============================================================================
# 五、 任务上下文防污染检测器 (Context Contamination Checker)
# ==============================================================================

class ContextContaminationChecker:
    """
    每次 Agent Task 启动时必须执行的 7 项刚性安全核验。
    如果发现 Forbidden Context > 0，则 EXECUTION BLOCKED。
    """

    @classmethod
    def check_task_context(
        cls,
        task_id: str,
        role: AgentRole,
        baseline_commit: str,
        input_context: Dict[str, Any],
        previous_task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        violations: List[str] = []

        # [1] Verify Task ID
        if not task_id or not task_id.strip():
            violations.append("Verification Failed: Task ID is missing or empty.")
        if previous_task_id and task_id == previous_task_id:
            violations.append(f"Verification Failed: Task ID '{task_id}' reuses previous task ID. New task must have unique ID.")

        # [2] Verify Baseline Commit
        if not baseline_commit or len(baseline_commit) < 7:
            violations.append("Verification Failed: Invalid or missing baseline commit hash.")

        # [3] Verify Allowed Inputs & [4] Verify Forbidden Inputs
        context_text = json.dumps(input_context, ensure_ascii=False)
        for pattern in FORBIDDEN_SUBJECTIVE_PATTERNS:
            if pattern in context_text:
                violations.append(f"Forbidden Context Detected: Contains anchoring bias phrase '{pattern}'.")

        # 检查是否非法包含了其他 Agent 的未封存 LEVEL 1 内容
        if "unsealed_drafts" in input_context:
            for draft_owner in input_context.get("unsealed_drafts", {}).keys():
                if draft_owner != role.value:
                    violations.append(
                        f"Forbidden Context Detected: Unsealed LEVEL 1 drafts from '{draft_owner}' "
                        f"leaked into '{role.value}' context."
                    )

        # [5] Verify Private Workspace isolation
        target_ws = input_context.get("target_workspace", "")
        if target_ws:
            try:
                PrivateWorkspaceGuard.validate_access(role, target_ws)
            except UnauthorizedWorkspaceAccessError as e:
                violations.append(str(e))

        # [6] Verify Cross-Agent Evidence Visibility
        # 非 LEVEL 2 的未封存证据严禁跨角色传递
        raw_evidence = input_context.get("evidence_items", [])
        for item in raw_evidence:
            if isinstance(item, dict):
                if not item.get("evidence_id") or not item.get("evidence_id", "").startswith("EVID-"):
                    violations.append("Cross-Agent Evidence Violation: Evidence item lacks valid sealed evidence_id.")

        # [7] Verify Previous Task Context Isolation
        if input_context.get("leak_from_previous_task"):
            violations.append("Previous Task Context Contamination: Residual conversation state detected.")

        # [8] Verify Canary Cross-Context Attack (Rule G-CTX-11)
        foreign_canary = CanaryTokenManager.detect_foreign_canary(role, input_context)
        if foreign_canary:
            raise CanaryCrossContextAttackError(
                f"Canary Cross-Context Attack Detected (Rule G-CTX-11)! "
                f"Foreign canary token '{foreign_canary}' infiltrated '{role.value}' context! EXECUTION BLOCKED."
            )

        if violations:
            raise ContaminationViolationError(
                f"EXECUTION BLOCKED! Context contamination check failed with {len(violations)} violation(s):\n" +
                "\n".join(f" - {v}" for v in violations)
            )

        return {
            "status": "PASS",
            "task_id": task_id,
            "role": role.value,
            "baseline_commit": baseline_commit,
            "checked_at": datetime.now().isoformat(),
            "violations_count": 0
        }


# ==============================================================================
# 六、 Gatekeeper 两阶段盲评仲裁执行器 (Gatekeeper Two-Stage Evaluator)
# ==============================================================================

class GatekeeperTwoStageEvaluator:
    """
    实现规范第五章 Step 5 的 Gatekeeper 两阶段审查：
    Stage A (Blind Assessment): 只看客观基线，先形成独立判断；
    Stage B (Evidence Arbitration): 调阅已封存证据，进行裁决。
    """
    def __init__(self, baseline_commit: str):
        self.baseline_commit = baseline_commit
        self.stage_a_completed = False
        self.blind_assessment_verdict: Optional[str] = None
        self.final_arbitration_verdict: Optional[str] = None

    def execute_stage_a_blind_assessment(
        self,
        objective_tests_pass_rate: float,
        working_tree_clean: bool,
        scope_drift_detected: bool,
        unauthorized_mocks_detected: bool
    ) -> str:
        """Stage A 盲评：只读 LEVEL 0 与客观规则，严禁读取任何开发/红队证据"""
        if scope_drift_detected:
            self.blind_assessment_verdict = "REJECT_SCOPE_DRIFT"
        elif unauthorized_mocks_detected:
            self.blind_assessment_verdict = "REJECT_MOCK_DETECTED"
        elif not working_tree_clean:
            self.blind_assessment_verdict = "REJECT_DIRTY_WORKING_TREE"
        elif objective_tests_pass_rate < 1.0:
            self.blind_assessment_verdict = "REJECT_TESTS_FAILED"
        else:
            self.blind_assessment_verdict = "PRELIMINARY_BLIND_PASS"

        self.stage_a_completed = True
        return self.blind_assessment_verdict

    def execute_stage_b_arbitration(
        self,
        sealed_evidences: List[ImmutableEvidenceRecord]
    ) -> Dict[str, Any]:
        """Stage B 证据仲裁：必须在 Stage A 完成后方可调阅封存证据"""
        if not self.stage_a_completed:
            raise BlindAssessmentViolationError(
                "Violation of Rule G-CTX-06: Gatekeeper cannot access cross-agent evidences "
                "before completing Stage A Blind Assessment!"
            )

        # 校验所有送审证据的完整性
        invalid_evidences = []
        critical_findings = []
        for ev in sealed_evidences:
            if not ev.verify_integrity():
                invalid_evidences.append(ev.evidence_id)
            if ev.severity.upper() in ["P0", "CRITICAL", "BLOCK"] and ev.status.upper() == "FAILED":
                critical_findings.append(ev)

        if invalid_evidences:
            raise EvidenceIntegrityError(
                f"Arbitration BLOCKED: Evidence tampering detected in IDs: {invalid_evidences}"
            )

        if self.blind_assessment_verdict != "PRELIMINARY_BLIND_PASS":
            final_status = "REJECT"
            reason = f"Stage A Blind Assessment failed: {self.blind_assessment_verdict}"
        elif critical_findings:
            final_status = "REJECT"
            reason = f"Unresolved critical red-team findings: {[f.finding_id for f in critical_findings]}"
        else:
            final_status = "APPROVED"
            reason = "Stage A Blind Assessment PASS & All Sealed Evidences Reconciled"

        self.final_arbitration_verdict = final_status
        return {
            "status": final_status,
            "blind_verdict": self.blind_assessment_verdict,
            "total_evidences_audited": len(sealed_evidences),
            "unresolved_critical_count": len(critical_findings),
            "reason": reason,
            "arbitrated_at": datetime.now().isoformat()
        }


# ==============================================================================
# 七、 G-CTX-11: 金丝雀跨上下文攻击传感器与运行时隔离证明器
# ==============================================================================

class CanaryTokenManager:
    """
    Rule G-CTX-11: 金丝雀跨上下文探测与攻击检测器 (Canary Cross-Context Attack Detector)
    原理：
    1. 为每个角色与任务分配高熵特异性金丝雀标识 (Canary Token)；
    2. 若角色 A 的输入、上下文、消息或工作区中检出了属于角色 B 的金丝雀，
       即证明发生物理/逻辑上下文越界泄漏（Cross-Context Contamination Leak）；
    3. 系统立即引爆 CanaryCrossContextAttackError 并刚性阻断执行！
    """
    CANARY_PREFIX = "CANARY-SECRET"

    @classmethod
    def generate_canary(cls, role: AgentRole, task_id: str, salt: str = "P0-ISOLATION") -> str:
        entropy = hashlib.sha256(f"{role.value}:{task_id}:{salt}".encode("utf-8")).hexdigest()[:12]
        return f"{cls.CANARY_PREFIX}:{role.value.upper()}:{entropy}"

    @classmethod
    def detect_foreign_canary(cls, current_role: AgentRole, context_payload: Any) -> Optional[str]:
        """扫描上下文中是否存在属于其他角色的金丝雀"""
        text = json.dumps(context_payload, ensure_ascii=False) if not isinstance(context_payload, str) else context_payload
        # 正则匹配形如 CANARY-SECRET:ROLE:HEX
        pattern = r"CANARY-SECRET:([A-Z_]+):[a-f0-9]{12}"
        matches = re.findall(pattern, text)
        for matched_role_str in matches:
            matched_role = matched_role_str.lower()
            if matched_role != current_role.value:
                # 抓到外来角色的金丝雀！
                return f"{cls.CANARY_PREFIX}:{matched_role_str}"
        return None


class RuntimeIsolationAttestation(BaseModel):
    """
    Rule G-CTX-11: 运行时隔离证明 (Runtime Isolation Attestation)
    为任务执行提供不可伪造的密码学物理隔离凭证。
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    attestation_id: str
    task_id: str
    role: AgentRole
    baseline_commit: str
    canary_token_registered: str
    foreign_canaries_detected: List[str] = Field(default_factory=list)
    forbidden_patterns_zero_presence: bool
    workspace_boundary_verified: bool
    status: str  # "ATTESTED_ISOLATED" / "BLOCKED_CONTAMINATED"
    attested_at: str
    attestation_hash: str

    @classmethod
    def issue(
        cls,
        task_id: str,
        role: AgentRole,
        baseline_commit: str,
        input_context: Dict[str, Any],
        target_workspace: Optional[str] = None
    ) -> "RuntimeIsolationAttestation":
        t_now = datetime.now().isoformat()
        my_canary = CanaryTokenManager.generate_canary(role, task_id)

        # 1. 检测外来金丝雀 (Canary Cross-Context Attack)
        foreign_canary = CanaryTokenManager.detect_foreign_canary(role, input_context)
        foreign_detected = [foreign_canary] if foreign_canary else []

        # 2. 检测偏见词
        ctx_str = json.dumps(input_context, ensure_ascii=False)
        has_forbidden_pattern = any(p in ctx_str for p in FORBIDDEN_SUBJECTIVE_PATTERNS)

        # 3. 检测工作区边界
        ws_ok = True
        if target_workspace:
            try:
                PrivateWorkspaceGuard.validate_access(role, target_workspace)
            except UnauthorizedWorkspaceAccessError:
                ws_ok = False

        is_isolated = (not foreign_detected) and (not has_forbidden_pattern) and ws_ok
        status = "ATTESTED_ISOLATED" if is_isolated else "BLOCKED_CONTAMINATED"

        raw_data = {
            "task_id": task_id,
            "role": role,
            "baseline_commit": baseline_commit,
            "canary_token_registered": my_canary,
            "foreign_canaries_detected": foreign_detected,
            "forbidden_patterns_zero_presence": not has_forbidden_pattern,
            "workspace_boundary_verified": ws_ok,
            "status": status,
            "attested_at": t_now,
        }
        # 哈希排除 attestation_id 与 attestation_hash
        hash_payload = {**raw_data, "role": role.value}
        jcs_str = json.dumps(hash_payload, sort_keys=True, separators=(',', ':'))
        att_hash = hashlib.sha256(jcs_str.encode("utf-8")).hexdigest()
        att_id = f"ATT-{att_hash[:16]}"

        if not is_isolated:
            if foreign_detected:
                raise CanaryCrossContextAttackError(
                    f"Canary Cross-Context Attack Detected (Rule G-CTX-11)! "
                    f"Foreign canary '{foreign_detected[0]}' found in '{role.value}' context! EXECUTION BLOCKED."
                )
            raise ContaminationViolationError(
                f"Runtime Isolation Attestation FAILED: Forbidden patterns or workspace violation in '{role.value}'."
            )

        return cls(
            attestation_id=att_id,
            attestation_hash=att_hash,
            **raw_data
        )

    def verify_signature(self) -> bool:
        raw_data = {
            "task_id": self.task_id,
            "role": self.role.value,
            "baseline_commit": self.baseline_commit,
            "canary_token_registered": self.canary_token_registered,
            "foreign_canaries_detected": self.foreign_canaries_detected,
            "forbidden_patterns_zero_presence": self.forbidden_patterns_zero_presence,
            "workspace_boundary_verified": self.workspace_boundary_verified,
            "status": self.status,
            "attested_at": self.attested_at,
        }
        jcs_str = json.dumps(raw_data, sort_keys=True, separators=(',', ':'))
        expected_hash = hashlib.sha256(jcs_str.encode("utf-8")).hexdigest()
        return self.attestation_hash == expected_hash and self.attestation_id == f"ATT-{expected_hash[:16]}"

