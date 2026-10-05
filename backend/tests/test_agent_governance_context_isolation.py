"""
Governance Test Matrix (T01 ~ T12)
Specification: SPEC-GOVERNANCE-P0-CTX-20261006
Policy: Independent by default, shared only through immutable evidence.
Rules: Rule G-CTX-01 ~ Rule G-CTX-10

验证目标：
通过真实可执行的单元与集成测试，客观证明四个 Agent 不仅仅是拥有不同的 Conversation，
而且在代码、文件、消息、证据层面实现了受控的信息流隔离与防污染阻断。
"""

import pytest
from app.governance.context_isolation import (
    InformationLevel,
    AgentRole,
    ImmutableEvidenceRecord,
    CrossAgentMessage,
    PrivateWorkspaceGuard,
    ContextContaminationChecker,
    GatekeeperTwoStageEvaluator,
    ContaminationViolationError,
    UnauthorizedWorkspaceAccessError,
    EvidenceIntegrityError,
    BlindAssessmentViolationError,
    CanaryCrossContextAttackError,
    CanaryTokenManager,
    RuntimeIsolationAttestation
)


# ==============================================================================
# T01: Developer 无法读取 Red-Team Private Workspace
# ==============================================================================
def test_t01_developer_cannot_access_redteam_private_workspace():
    """T01: Developer 试图读取 Red-Team 的 LEVEL 1 私有工作区时被刚性拦截"""
    target_path = "governance/workspaces/board_red_team/attack_plan_draft.md"
    with pytest.raises(UnauthorizedWorkspaceAccessError) as exc_info:
        PrivateWorkspaceGuard.validate_access(
            requesting_role=AgentRole.PRIMARY_DEVELOPER,
            target_path=target_path,
            action="read"
        )
    assert "Access Denied" in str(exc_info.value)
    assert "primary_developer" in str(exc_info.value)
    assert "board_red_team" in str(exc_info.value)


# ==============================================================================
# T02: Red-Team 无法读取 Developer Preliminary Conclusion
# ==============================================================================
def test_t02_redteam_cannot_access_developer_preliminary_conclusion():
    """T02: Red-Team 试图读取 Developer 的未封存草稿与自测说明时被刚性拦截"""
    target_path = "governance/workspaces/primary_developer/self_assessment_draft.json"
    with pytest.raises(UnauthorizedWorkspaceAccessError) as exc_info:
        PrivateWorkspaceGuard.validate_access(
            requesting_role=AgentRole.BOARD_RED_TEAM,
            target_path=target_path,
            action="read"
        )
    assert "Access Denied" in str(exc_info.value)
    assert "board_red_team" in str(exc_info.value)
    assert "primary_developer" in str(exc_info.value)


# ==============================================================================
# T03: Tester 无法读取 Board Preliminary Conclusion
# ==============================================================================
def test_t03_tester_cannot_access_board_preliminary_conclusion():
    """T03: Tester 试图读取 Board 的初步判断草稿时被刚性拦截"""
    target_path = "governance/workspaces/board_red_team/preliminary_verdict.md"
    with pytest.raises(UnauthorizedWorkspaceAccessError) as exc_info:
        PrivateWorkspaceGuard.validate_access(
            requesting_role=AgentRole.RED_TEAM_TESTER,
            target_path=target_path,
            action="read"
        )
    assert "Access Denied" in str(exc_info.value)
    assert "red_team_tester" in str(exc_info.value)


# ==============================================================================
# T04: Gatekeeper 在 Blind Assessment 阶段无法读取其他 Agent 未封存结论
# ==============================================================================
def test_t04_gatekeeper_blind_assessment_cannot_read_unsealed_conclusions():
    """T04: Gatekeeper 在任务上下文中若混入了未封存草稿，启动检查立即阻断"""
    input_context = {
        "allowed_level0": ["backend/app/", "开发文档/"],
        "unsealed_drafts": {
            "primary_developer": "developer_unsealed_notes.txt"
        }
    }
    with pytest.raises(ContaminationViolationError) as exc_info:
        ContextContaminationChecker.check_task_context(
            task_id="TASK-GK-STAGE-A-001",
            role=AgentRole.QUALITY_GATEKEEPER,
            baseline_commit="9ceeafd",
            input_context=input_context
        )
    assert "Unsealed LEVEL 1 drafts from 'primary_developer' leaked" in str(exc_info.value)


# ==============================================================================
# T05: 未包含 Evidence ID 的治理消息不得进入正式 Evidence Flow
# ==============================================================================
def test_t05_unidentified_message_rejected_from_evidence_flow():
    """T05: 缺少必要字段（如 EVIDENCE_ID）的治理消息无法通过结构化校验"""
    malformed_msg = """
    TASK_ID: TASK-001
    ARTIFACT_ID: ART-001
    BASELINE_COMMIT: 9ceeafd
    QUESTION_ID: Q-01
    OBJECTIVE_FACT: Tests executed
    REPRODUCTION_COMMAND: pytest
    EXPECTED_CHECK: All pass
    HASH: 12345678
    STATUS: PASS
    """
    with pytest.raises(ContaminationViolationError) as exc_info:
        CrossAgentMessage.parse_raw_message(malformed_msg)
    assert "Missing mandatory fields" in str(exc_info.value)
    assert "EVIDENCE_ID" in str(exc_info.value)


# ==============================================================================
# T06: 新 Task 必须使用新的 Task Context
# ==============================================================================
def test_t06_new_task_must_have_new_task_context():
    """T06: 复用已存在前序任务 ID 启动新任务会被防污染检测器拦截"""
    with pytest.raises(ContaminationViolationError) as exc_info:
        ContextContaminationChecker.check_task_context(
            task_id="TASK-PREV-001",
            role=AgentRole.PRIMARY_DEVELOPER,
            baseline_commit="9ceeafd",
            input_context={"status": "init"},
            previous_task_id="TASK-PREV-001"
        )
    assert "reuses previous task ID" in str(exc_info.value)


# ==============================================================================
# T07: Previous Task Context 不得自动泄漏到新 Task
# ==============================================================================
def test_t07_previous_task_context_cannot_leak_to_new_task():
    """T07: 检测到带有前序任务残留会话状态时刚性阻断"""
    dirty_context = {
        "task_data": "fresh_input",
        "leak_from_previous_task": True
    }
    with pytest.raises(ContaminationViolationError) as exc_info:
        ContextContaminationChecker.check_task_context(
            task_id="TASK-NEW-002",
            role=AgentRole.RED_TEAM_TESTER,
            baseline_commit="9ceeafd",
            input_context=dirty_context,
            previous_task_id="TASK-OLD-001"
        )
    assert "Previous Task Context Contamination" in str(exc_info.value)


# ==============================================================================
# T08: 跨 Agent 共享只能通过 LEVEL 2 Evidence
# ==============================================================================
def test_t08_cross_agent_sharing_only_via_level2_evidence():
    """T08: 跨 Agent 传递未打防伪封印指纹的伪证据会被直接拦截"""
    invalid_context = {
        "evidence_items": [
            {"finding": "something_broken", "evidence_id": "plain_text_id"}
        ]
    }
    with pytest.raises(ContaminationViolationError) as exc_info:
        ContextContaminationChecker.check_task_context(
            task_id="TASK-SHARE-003",
            role=AgentRole.QUALITY_GATEKEEPER,
            baseline_commit="9ceeafd",
            input_context=invalid_context
        )
    assert "lacks valid sealed evidence_id" in str(exc_info.value)


# ==============================================================================
# T09: Evidence Hash 被篡改时必须导致 Integrity Failure
# ==============================================================================
def test_t09_tampered_evidence_hash_causes_integrity_failure():
    """T09: 篡改已封存证据的内容或指纹必然导致核验失败与裁决阻断"""
    # 1. 正常生成封存证据
    ev = ImmutableEvidenceRecord.create_and_seal(
        task_id="TASK-AUDIT-001",
        agent_id="agent-redteam-01",
        role=AgentRole.BOARD_RED_TEAM,
        baseline_commit="9ceeafd",
        artifact_id="ART-GATE-01",
        artifact_hash="abc1234567890",
        question_id="Q-CANONICAL",
        finding_id="FIND-01",
        evidence_type="AUDIT_VERIFICATION",
        objective_observation="AST Evaluator handles empty universe properly",
        reproduction_command="pytest backend/tests/test_phase2c_sector_cognition.py",
        result="PASS",
        severity="INFO",
        status="VERIFIED"
    )
    assert ev.verify_integrity() is True

    # 2. 伪造或就地篡改对象属性 (由于 frozen=True，通过底层字典或伪造对象验证)
    tampered_dict = ev.model_dump()
    tampered_dict["result"] = "FAILED"  # 篡改结果但未重算哈希
    tampered_ev = ImmutableEvidenceRecord(**tampered_dict)
    assert tampered_ev.verify_integrity() is False

    # 3. 提交给 Gatekeeper 仲裁时必须触发异常阻断
    gk = GatekeeperTwoStageEvaluator(baseline_commit="9ceeafd")
    gk.execute_stage_a_blind_assessment(
        objective_tests_pass_rate=1.0,
        working_tree_clean=True,
        scope_drift_detected=False,
        unauthorized_mocks_detected=False
    )
    with pytest.raises(EvidenceIntegrityError) as exc_info:
        gk.execute_stage_b_arbitration([tampered_ev])
    assert "Evidence tampering detected" in str(exc_info.value)


# ==============================================================================
# T10: Forbidden Context 出现时必须 BLOCK
# ==============================================================================
def test_t10_forbidden_context_pattern_causes_execution_block():
    """T10: 包含“我认为可以 PASS”、“这个问题已经修复”等锚定性词汇时刚性阻断"""
    contaminated_context = {
        "developer_comment": "我已经检查过了，这个应该没问题，我认为可以 PASS"
    }
    with pytest.raises(ContaminationViolationError) as exc_info:
        ContextContaminationChecker.check_task_context(
            task_id="TASK-CONTAM-010",
            role=AgentRole.BOARD_RED_TEAM,
            baseline_commit="9ceeafd",
            input_context=contaminated_context
        )
    assert "Forbidden Context Detected" in str(exc_info.value)
    assert "我认为可以 PASS" in str(exc_info.value)


# ==============================================================================
# T11: Gatekeeper 必须先独立判断，再读取其他 Evidence
# ==============================================================================
def test_t11_gatekeeper_must_execute_blind_assessment_before_evidence():
    """T11: 违反 Rule G-CTX-06，未执行 Stage A 盲评直接调用 Stage B 仲裁必须报错"""
    gk = GatekeeperTwoStageEvaluator(baseline_commit="9ceeafd")
    
    dummy_ev = ImmutableEvidenceRecord.create_and_seal(
        task_id="TASK-EV-011",
        agent_id="agent-dev-01",
        role=AgentRole.PRIMARY_DEVELOPER,
        baseline_commit="9ceeafd",
        artifact_id="ART-CODE-01",
        artifact_hash="hash0001",
        question_id="Q-IMPL",
        finding_id="F-001",
        evidence_type="UNIT_TEST",
        objective_observation="All tests pass",
        reproduction_command="pytest",
        result="PASS",
        severity="INFO",
        status="SEALED"
    )

    # 未执行 execute_stage_a_blind_assessment 直接执行 Stage B
    with pytest.raises(BlindAssessmentViolationError) as exc_info:
        gk.execute_stage_b_arbitration([dummy_ev])
    assert "cannot access cross-agent evidences before completing Stage A Blind Assessment" in str(exc_info.value)

    # 规范执行：先 Stage A 再 Stage B 成功放行
    verdict_a = gk.execute_stage_a_blind_assessment(
        objective_tests_pass_rate=1.0,
        working_tree_clean=True,
        scope_drift_detected=False,
        unauthorized_mocks_detected=False
    )
    assert verdict_a == "PRELIMINARY_BLIND_PASS"

    res_b = gk.execute_stage_b_arbitration([dummy_ev])
    assert res_b["status"] == "APPROVED"


# ==============================================================================
# T12: Agent 无法通过普通消息绕过 Evidence Layer
# ==============================================================================
def test_t12_agent_cannot_bypass_evidence_layer_via_unstructured_message():
    """T12: 试图通过非结构化口头消息传递主观定性结论时被刚性拒绝"""
    unstructured_attempt = "兄弟，我已经检查过了，代码全绿，直接放行吧！"
    with pytest.raises(ContaminationViolationError):
        CrossAgentMessage.parse_raw_message(unstructured_attempt)

    # 即使键名齐全，但若在事实描述中塞入“基本没问题”等主观定性词，依然被拦截
    sneaky_msg = (
        "TASK_ID: T-12\n"
        "ARTIFACT_ID: ART-12\n"
        "BASELINE_COMMIT: 9ceeafd\n"
        "QUESTION_ID: Q-12\n"
        "EVIDENCE_ID: EVID-12\n"
        "OBJECTIVE_FACT: 这个应该没问题，数据正常\n"
        "REPRODUCTION_COMMAND: pytest\n"
        "EXPECTED_CHECK: pass\n"
        "HASH: 123456\n"
        "STATUS: PASS"
    )
    with pytest.raises(ContaminationViolationError) as exc_info:
        CrossAgentMessage.parse_raw_message(sneaky_msg)
    assert "forbidden subjective conclusion anchor" in str(exc_info.value)


# ==============================================================================
# T13: Canary Cross-Context Attack Detected and Blocked (Rule G-CTX-11)
# ==============================================================================
def test_t13_canary_cross_context_attack_detected_and_blocked():
    """
    T13: 金丝雀跨上下文攻击防御 (Canary Cross-Context Attack)
    模拟攻击场景：测试特使的输入上下文中混入了来自 board_red_team 的专属金丝雀标记，
    系统金丝雀传感器立即捕获异常，抛出 CanaryCrossContextAttackError 并刚性阻断任务执行。
    """
    # 1. 模拟 board_red_team 生成其专属金丝雀密标
    board_canary = CanaryTokenManager.generate_canary(AgentRole.BOARD_RED_TEAM, "TASK-RED-001")
    assert "CANARY-SECRET:BOARD_RED_TEAM:" in board_canary

    # 2. 模拟跨上下文泄露/刺探攻击：将 board_canary 注入 primary_developer 的任务上下文
    leaked_context = {
        "allowed_level0": ["backend/app/"],
        "developer_task": "implement feature",
        "injected_leak": f"Confidential note with {board_canary} inside"
    }

    # 3. primary_developer 启动防污染检查时必须立即引爆阻断
    with pytest.raises(CanaryCrossContextAttackError) as exc_info:
        ContextContaminationChecker.check_task_context(
            task_id="TASK-DEV-013",
            role=AgentRole.PRIMARY_DEVELOPER,
            baseline_commit="9ceeafd",
            input_context=leaked_context
        )
    assert "Canary Cross-Context Attack Detected" in str(exc_info.value)
    assert "Foreign canary token" in str(exc_info.value)
    assert "BOARD_RED_TEAM" in str(exc_info.value)


# ==============================================================================
# T14: Runtime Isolation Attestation Generated and Verified (Rule G-CTX-11)
# ==============================================================================
def test_t14_runtime_isolation_attestation_generated_and_verified():
    """
    T14: 运行时隔离证明签发与完整性核验 (Runtime Isolation Attestation)
    合规任务必须生成具备不可伪造指纹的隔离证明；一旦证明遭到篡改，核验必须失败。
    """
    clean_context = {
        "allowed_level0": ["backend/app/", "backend/tests/"],
        "objective_requirement": "Refactor AST Evaluator"
    }

    # 1. 签发合规证明
    attestation = RuntimeIsolationAttestation.issue(
        task_id="TASK-ATTEST-014",
        role=AgentRole.PRIMARY_DEVELOPER,
        baseline_commit="9ceeafd",
        input_context=clean_context,
        target_workspace="governance/workspaces/primary_developer/"
    )

    assert attestation.status == "ATTESTED_ISOLATED"
    assert attestation.attestation_id.startswith("ATT-")
    assert attestation.forbidden_patterns_zero_presence is True
    assert attestation.workspace_boundary_verified is True
    assert len(attestation.foreign_canaries_detected) == 0
    assert attestation.verify_signature() is True

    # 2. 模拟篡改证明对象（例如伪造状态）
    tampered_dict = attestation.model_dump()
    tampered_dict["status"] = "BLOCKED_CONTAMINATED"
    tampered_attestation = RuntimeIsolationAttestation(**tampered_dict)
    assert tampered_attestation.verify_signature() is False

