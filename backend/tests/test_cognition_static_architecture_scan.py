"""
Phase 2A Step 3.4 静态架构扫描与安全合规防线（Static Architecture Scanner）
上位依据：
1. 最高董事会工程批准令 BOARD-APPROVAL-20260930-STEP3
2. 《开发文档/39-Phase-2A-Step3.4-综合组装与全链路冷启动静态验收实施计划.md》

核心扫描目标（基于 Python AST 抽象语法树分析）：
1. 外部大模型 SDK 零容忍黑名单 (Zero LLM SDKs)
2. 不可控网络与套接字调用零容忍 (Zero Raw Sockets)
3. 交易系统与执行模块绝对隔离 (Zero Trading Module Leakage)
4. 数据库 Migration 零变更防护 (Zero Unauthorized Migrations)
5. 停机边界语法结构验证 (STOP Boundary Syntactic Audit)
"""

import ast
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COGNITION_DIR = os.path.join(BACKEND_DIR, "app", "cognition")
INPUT_DIR = os.path.join(COGNITION_DIR, "input")
OBSERVATION_DIR = os.path.join(COGNITION_DIR, "observation")
HYPOTHESIS_DIR = os.path.join(COGNITION_DIR, "hypothesis")
MIGRATIONS_DIR = os.path.join(BACKEND_DIR, "migrations", "versions")


FORBIDDEN_LLM_SDKS = {
    "openai",
    "anthropic",
    "google.generativeai",
    "google.genai",
    "langchain",
    "litellm",
    "cohere",
    "huggingface_hub",
    "transformers",
    "torch",
}


def _get_python_files(directory: str):
    """递归获取目录下所有 Python 源代码文件"""
    py_files = []
    for root, _, files in os.walk(directory):
        for f in files:
            if f.endswith(".py") and not f.startswith("."):
                py_files.append(os.path.join(root, f))
    return py_files


def _extract_imported_modules(file_path: str):
    """通过 AST 解析提取某个 Python 文件中导入的所有模块名与符号"""
    with open(file_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=file_path)

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def test_scan_no_external_llm_sdks():
    """扫描 1: 扫描 backend/app/cognition 严禁出现任何大模型 SDK 导入"""
    files = _get_python_files(COGNITION_DIR)
    assert len(files) > 0, "No cognition files found to scan!"

    violations = []
    for file_path in files:
        imports = _extract_imported_modules(file_path)
        rel_path = os.path.relpath(file_path, BACKEND_DIR)
        for imp in imports:
            base_pkg = imp.split(".")[0]
            if base_pkg in FORBIDDEN_LLM_SDKS or imp in FORBIDDEN_LLM_SDKS:
                violations.append(f"{rel_path}: imports forbidden LLM package '{imp}'")

    assert len(violations) == 0, f"Found LLM SDK violations in cognition:\n" + "\n".join(violations)


def test_scan_no_uncontrolled_network_calls():
    """扫描 2: 扫描 input, observation, hypothesis 目录，严禁导入底层原始 socket 或 requests"""
    forbidden_net = {"socket", "requests", "urllib.request"}
    scan_files = _get_python_files(INPUT_DIR) + _get_python_files(OBSERVATION_DIR) + _get_python_files(HYPOTHESIS_DIR)

    violations = []
    for file_path in scan_files:
        imports = _extract_imported_modules(file_path)
        rel_path = os.path.relpath(file_path, BACKEND_DIR)
        for imp in imports:
            if imp in forbidden_net or imp.split(".")[0] in forbidden_net:
                violations.append(f"{rel_path}: imports uncontrolled network module '{imp}'")

    assert len(violations) == 0, f"Found uncontrolled network violations:\n" + "\n".join(violations)


def test_scan_no_trading_module_leakage():
    """扫描 3: 扫描 input, observation, hypothesis 目录，严禁接触交易执行模块或交易持久化模型"""
    forbidden_trading = {"app.trading", "app.models.trading"}
    scan_files = _get_python_files(INPUT_DIR) + _get_python_files(OBSERVATION_DIR) + _get_python_files(HYPOTHESIS_DIR)

    violations = []
    for file_path in scan_files:
        imports = _extract_imported_modules(file_path)
        rel_path = os.path.relpath(file_path, BACKEND_DIR)
        for imp in imports:
            for ft in forbidden_trading:
                if imp == ft or imp.startswith(ft + "."):
                    violations.append(f"{rel_path}: illegally imports trading module '{imp}'")

    assert len(violations) == 0, f"Found trading module leakage in cognition modules:\n" + "\n".join(violations)


def test_scan_no_unauthorized_migrations():
    """扫描 4: 检查 migrations 目录，确认 Step 3/4/5 期间未私自引入任何新的数据库表迁移"""
    if os.path.exists(MIGRATIONS_DIR):
        migration_files = [f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".py") and not f.startswith("__")]
        for m in migration_files:
            m_lower = m.lower()
            assert "step3" not in m_lower, f"Unauthorized Step 3 migration file found: {m}"
            assert "step4" not in m_lower, f"Unauthorized Step 4 migration file found: {m}"
            assert "step5" not in m_lower, f"Unauthorized Step 5 migration file found: {m}"


def test_scan_hard_stop_boundary_in_pipeline():
    """扫描 5: 静态解析 input/pipeline.py，验证 process_snapshot 严格返回 EffectiveInferenceInput"""
    pipeline_file = os.path.join(INPUT_DIR, "pipeline.py")
    with open(pipeline_file, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=pipeline_file)

    process_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "process_snapshot":
            process_fn = node
            break

    assert process_fn is not None, "process_snapshot function not found in pipeline.py!"

    returns = [n for n in ast.walk(process_fn) if isinstance(n, ast.Return)]
    assert len(returns) >= 1, "process_snapshot must have a return statement"
    last_return = returns[-1]
    assert isinstance(last_return.value, ast.Name)
    assert last_return.value.id == "effective_input"


def test_scan_hard_stop_boundary_in_step5_pipeline():
    """扫描 6: 静态解析 hypothesis/pipeline.py，验证 validate_hypothesis_set 严格返回 validation_records"""
    pipeline_file = os.path.join(HYPOTHESIS_DIR, "pipeline.py")
    with open(pipeline_file, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=pipeline_file)

    validate_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "validate_hypothesis_set":
            validate_fn = node
            break

    assert validate_fn is not None, "validate_hypothesis_set function not found in hypothesis/pipeline.py!"

    returns = [n for n in ast.walk(validate_fn) if isinstance(n, ast.Return)]
    assert len(returns) >= 1, "validate_hypothesis_set must have a return statement"
    last_return = returns[-1]
    assert isinstance(last_return.value, ast.Name)
    assert last_return.value.id == "validation_records"
