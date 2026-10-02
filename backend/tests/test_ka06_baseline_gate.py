import pytest
from app.governance.baseline_gate import BaselineDiffEngine

@pytest.fixture
def gate_engine():
    return BaselineDiffEngine()

def test_baseline_gate_pass_on_perfect_metrics(gate_engine):
    """验证 KA-06 门禁：符合或优于黄金基线要求时放行 (PASS)"""
    req_tests = gate_engine.manifest["metrics"]["total_tests_required"]
    candidate_metrics = {
        "total_tests": req_tests + 1,
        "failed_tests": 0,
        "error_tests": 0,
        "pass_rate": 1.0,
        "duration_seconds": 65.0
    }
    candidate_tables = gate_engine.manifest["schema_contract"]["expected_tables"]
    candidate_triggers = gate_engine.manifest["schema_contract"]["expected_triggers"]
    genesis_row = gate_engine.manifest["schema_contract"]["genesis_anchor"]

    report = gate_engine.evaluate(
        candidate_metrics=candidate_metrics,
        candidate_tables=candidate_tables,
        candidate_triggers=candidate_triggers,
        genesis_row=genesis_row,
        isolation_hashes_match=True
    )

    assert report.status == "PASS"
    assert len(report.violations) == 0
    assert report.isolation_passed is True
    md = report.to_markdown()
    assert "🟢 准入放行 (PASS)" in md

def test_baseline_gate_reject_on_test_failure(gate_engine):
    """验证 KA-06 门禁：单测发生失败时必须刚性阻断 (FAIL)"""
    req_tests = gate_engine.manifest["metrics"]["total_tests_required"]
    candidate_metrics = {
        "total_tests": req_tests,
        "failed_tests": 1, # 出现 1 个失败
        "error_tests": 0,
        "pass_rate": 0.993,
    }
    candidate_tables = gate_engine.manifest["schema_contract"]["expected_tables"]
    candidate_triggers = gate_engine.manifest["schema_contract"]["expected_triggers"]
    genesis_row = gate_engine.manifest["schema_contract"]["genesis_anchor"]

    report = gate_engine.evaluate(
        candidate_metrics=candidate_metrics,
        candidate_tables=candidate_tables,
        candidate_triggers=candidate_triggers,
        genesis_row=genesis_row,
        isolation_hashes_match=True
    )

    assert report.status == "FAIL"
    assert any("测试套件出现失败" in v for v in report.violations)
    md = report.to_markdown()
    assert "🔴 阻断拦截 (FAIL)" in md

def test_baseline_gate_reject_on_dropped_tests(gate_engine):
    """验证 KA-06 门禁：测试数量掉线（测试被误删/跳过）时必须刚性阻断 (FAIL)"""
    req_tests = gate_engine.manifest["metrics"]["total_tests_required"]
    candidate_metrics = {
        "total_tests": req_tests - 8, # 缺失 8 项
        "failed_tests": 0,
        "error_tests": 0,
        "pass_rate": 1.0,
    }
    candidate_tables = gate_engine.manifest["schema_contract"]["expected_tables"]
    candidate_triggers = gate_engine.manifest["schema_contract"]["expected_triggers"]
    genesis_row = gate_engine.manifest["schema_contract"]["genesis_anchor"]

    report = gate_engine.evaluate(
        candidate_metrics=candidate_metrics,
        candidate_tables=candidate_tables,
        candidate_triggers=candidate_triggers,
        genesis_row=genesis_row,
        isolation_hashes_match=True
    )

    assert report.status == "FAIL"
    assert any("测试用例总数退化" in v for v in report.violations)

def test_baseline_gate_reject_on_missing_trigger_or_schema(gate_engine):
    """验证 KA-06 门禁：缺失 WORM 触发器或表结构时必须刚性阻断 (FAIL)"""
    req_tests = gate_engine.manifest["metrics"]["total_tests_required"]
    candidate_metrics = {
        "total_tests": req_tests,
        "failed_tests": 0,
        "error_tests": 0,
        "pass_rate": 1.0,
    }
    # 故意剔除一个核心触发器
    candidate_triggers = [
        "trg_cognition_prompt_spec_no_delete",
        "trg_cognition_prompt_spec_no_update"
    ]
    candidate_tables = gate_engine.manifest["schema_contract"]["expected_tables"]
    genesis_row = gate_engine.manifest["schema_contract"]["genesis_anchor"]

    report = gate_engine.evaluate(
        candidate_metrics=candidate_metrics,
        candidate_tables=candidate_tables,
        candidate_triggers=candidate_triggers,
        genesis_row=genesis_row,
        isolation_hashes_match=True
    )

    assert report.status == "FAIL"
    assert any("物理 WORM 防篡改触发器缺失" in v for v in report.violations)

def test_baseline_gate_reject_on_database_leak(gate_engine):
    """验证 KA-06 门禁：测试污染物理开发库时必须刚性阻断 (FAIL)"""
    req_tests = gate_engine.manifest["metrics"]["total_tests_required"]
    candidate_metrics = {
        "total_tests": req_tests,
        "failed_tests": 0,
        "error_tests": 0,
        "pass_rate": 1.0,
    }
    candidate_tables = gate_engine.manifest["schema_contract"]["expected_tables"]
    candidate_triggers = gate_engine.manifest["schema_contract"]["expected_triggers"]
    genesis_row = gate_engine.manifest["schema_contract"]["genesis_anchor"]

    report = gate_engine.evaluate(
        candidate_metrics=candidate_metrics,
        candidate_tables=candidate_tables,
        candidate_triggers=candidate_triggers,
        genesis_row=genesis_row,
        isolation_hashes_match=False # 物理文件哈希改变
    )

    assert report.status == "FAIL"
    assert any("物理数据库未隔离" in v for v in report.violations)
