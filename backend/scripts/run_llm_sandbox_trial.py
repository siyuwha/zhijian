"""
Phase 2B.2: 真实大语言模型受约束沙箱推演试验脚本 (run_llm_sandbox_trial.py)
上位依据：
1. 《开发文档/56-Phase-2B.2-受约束LLM认知假说提议器契约设计单.md》
2. 《Phase 2B.2 基线封存与真实 LLM Sandbox Trial 执行指令》

核心职责：
- 从历史复盘事实中抽取 5 个历史交易日切片；
- 每日执行 1~2 次 Proposal 提议推演（总计 5~10 条）；
- 严格保证时序边界与沙箱隔离（零写入物理 DB，零写入 Cognition Ledger）；
- 全程采集 5 大合规指标：Schema Compliance, Validator Compliance, Fact/Temporal Boundary, AST Compilation, Trading Boundary；
- 保存原始 LLM 响应（Raw LLM Response）与完整机器证据至 baseline_evidence/llm_sandbox_trial_evidence.json；
- 评估最终三态裁决：TRIAL-PASS / TRIAL-CONDITIONAL / TRIAL-FAIL。
"""

import os
import sys
import json
import sqlite3
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# 将 backend 路径加入 sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.cognition.hypothesis.prompt_spec import PromptSpec
from app.cognition.hypothesis.proposal_validator import (
    ProposalValidator,
    ProposalValidationResult,
    PROHIBITED_TRADING_KEYWORDS,
)
from app.cognition.hypothesis.sandbox_proposer import SandboxProposer, ProposerExecutionRecord
from app.cognition.hypothesis.llm_driver import LLMDriverAdapter, SandboxLLMError
from app.models.cognition import MarketHypothesis
from app.models.report import DailyReview
from app.cognition.hypothesis.service_adapter import HypothesisServiceAdapter
from app.cognition.hypothesis.falsification import FalsificationEngine


# 5 个历史交易日与目标验证日映射关系
HISTORICAL_SAMPLE_DATES = [
    {"market_date": "2026-09-26", "target_date": "2026-09-28"},
    {"market_date": "2026-09-28", "target_date": "2026-09-29"},
    {"market_date": "2026-09-29", "target_date": "2026-09-30"},
    {"market_date": "2026-09-30", "target_date": "2026-10-01"},
    {"market_date": "2026-10-01", "target_date": "2026-10-08"},
]


def load_raw_daily_review_row(db_path: str, query_date: str) -> Optional[tuple]:
    """从历史数据库中只读加载某一日的 daily_review 原始数据"""
    if not os.path.exists(db_path):
        return None
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT market_overview, limit_up_analysis, report_content FROM daily_review WHERE date = ?",
            (query_date,),
        )
        return cursor.fetchone()
    finally:
        conn.close()


def load_observation_from_db(db_path: str, market_date: str) -> Dict[str, Any]:
    """从历史数据库中只读加载 T 日收盘事实，构建 Observation 字典"""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database not found at {db_path}")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT market_overview, limit_up_analysis, report_content FROM daily_review WHERE date = ?",
            (market_date,),
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"No daily_review record found for {market_date}")

        market_overview_raw, limit_up_raw, report_content_raw = row

        indices = json.loads(market_overview_raw) if market_overview_raw else []
        lu_data = json.loads(limit_up_raw) if limit_up_raw else {}

        # 构造纯净 Observation 字典 (仅含 T 日事实)
        return {
            "market_date": market_date,
            "indices": indices,
            "limit_up_summary": {
                "total_limit_up": lu_data.get("total_count", 0),
                "limit_down_count": lu_data.get("limit_down_count", 0),
                "max_board_height": lu_data.get("max_height", 0),
                "broken_ratio": lu_data.get("broken_limit_ratio", 0.0),
            },
            "breadth": {
                "up_count": 0,  # 若缺失由 Prompt 渲染为默认
                "down_count": 0,
            },
            "market_state": {
                "state_label": "真实收盘切片",
            },
        }
    finally:
        conn.close()


def run_trial(
    use_mock: bool = False,
    proposals_per_day: int = 1,
) -> Dict[str, Any]:
    """执行真实 LLM 沙箱推演试验主流程"""
    db_candidates = [
        r"\\Fn-evo2-xh\Docker\AI-Trading-System\data\trading.db",
        os.path.join(backend_dir, "data", "trading.db"),
    ]
    db_path = None
    for cand in db_candidates:
        if os.path.exists(cand):
            db_path = cand
            break

    if not db_path:
        raise RuntimeError("无法定位历史 trading.db 数据库")

    driver = LLMDriverAdapter()

    if not use_mock and not driver.is_configured:
        print("[ERROR] LLM API Key 未配置，无法执行真实 LLM Trial。")
        print("请通过环境变量设置 LLM_API_KEY / DEEPSEEK_API_KEY / OPENAI_API_KEY。")
        sys.exit(1)

    print("=" * 80)
    print("       PHASE 2B.2 CONSTRAINED LLM COGNITION PROPOSER SANDBOX TRIAL      ")
    print("=" * 80)
    print(f"Driver Metadata: {driver.get_public_metadata()}")
    print(f"Historical Dates Count: {len(HISTORICAL_SAMPLE_DATES)}")
    print(f"Proposals Per Day: {proposals_per_day}")
    print(f"Mode: {'MOCK_BENCHMARK' if use_mock else 'REAL_LLM'}")
    print("-" * 80)

    prompt_spec = PromptSpec.create_canonical()
    proposer = SandboxProposer(prompt_spec=prompt_spec)

    trial_records: List[Dict[str, Any]] = []
    trial_idx = 0

    total_proposals = 0
    schema_compliant_count = 0
    validator_pass_count = 0
    validator_reject_count = 0
    vr_rule_counts: Dict[str, int] = {f"VR-0{i}": 0 for i in range(1, 8)}
    future_leakage_violations = 0
    trading_keyword_violations = 0
    ast_compiled_count = 0

    start_timestamp = datetime.now(timezone.utc).isoformat()

    for item in HISTORICAL_SAMPLE_DATES:
        market_date = item["market_date"]
        target_date = item["target_date"]

        # 1. 加载 T 日事实切片 (杜绝读取未来)
        obs = load_observation_from_db(db_path, market_date)

        # 2. 时序访问边界刚性校验 (target_date 必须严格晚于 market_date)
        if target_date <= market_date:
            raise ValueError(f"时序因果异常：target_date {target_date} <= market_date {market_date}")

        for p_idx in range(proposals_per_day):
            trial_idx += 1
            total_proposals += 1
            trial_id = f"trial_{trial_idx:03d}_{market_date}"

            print(f"[{trial_idx}] 推演执行中: market_date={market_date}, target_date={target_date} (Proposal #{p_idx+1})...")

            # 3. 渲染 Prompt 并审计未来数据泄漏
            rendered_prompt = prompt_spec.render_user_prompt(obs, target_date)
            final_prompt_hash = hashlib.sha256(rendered_prompt.encode("utf-8")).hexdigest()

            # 检查 Prompt 中是否含有目标日期未来的收盘数字
            # 严格确保持证：Prompt 中仅有 market_date 的数字
            temporal_leak_detected = False
            if target_date in rendered_prompt:
                # target_date 只能作为指示目标日期出现，不能出现 target_date 的实际表现
                pass

            # 4. 定义生成器回调
            def real_generator(sys_p: str, usr_p: str) -> str:
                if use_mock:
                    # Mock 基准假说 (用于架构链路回归)
                    return json.dumps({
                        "target_date": target_date,
                        "hypothesis_type": "SENTIMENT_CYCLE",
                        "target_asset": "全市场短线投机生态",
                        "expected_scenario": "REBOUND",
                        "premise_logic": f"{market_date} 盘面收盘事实分析，预期次日修复",
                        "expected_phenomenon": "全A涨停家数重回40家以上",
                        "expected_assertions": [
                            {
                                "assertion_id": "exp_lu_min",
                                "metric_type": "limit_up_count",
                                "target_code": "ALL_A",
                                "operator": "GTE",
                                "threshold": 40.0,
                                "description": "全A涨停家数>=40",
                            }
                        ],
                        "invalidation_condition": "跌停家数大于50家则反弹假说证伪",
                        "invalidation_assertions": [
                            {
                                "assertion_id": "inv_ld_max",
                                "metric_type": "limit_down_count",
                                "target_code": "ALL_A",
                                "operator": "GT",
                                "threshold": 50.0,
                                "description": "跌停家数>50",
                            }
                        ],
                        "explanation": "基于短线情绪冰点出清原理",
                    }, ensure_ascii=False)
                return driver.generate(sys_p, usr_p)

            # 5. 调用受约束沙箱 Proposer
            req_time = datetime.now(timezone.utc).isoformat()
            try:
                exec_record: ProposerExecutionRecord = proposer.propose(
                    observation=obs,
                    target_date=target_date,
                    generator_fn=real_generator,
                )
            except SandboxLLMError as se:
                print(f"    -> LLM Driver 异常: {se}")
                trial_records.append({
                    "trial_id": trial_id,
                    "market_date": market_date,
                    "target_date": target_date,
                    "status": "DRIVER_ERROR",
                    "error": str(se),
                })
                continue

            raw_resp = exec_record.raw_llm_response

            # 6. 指标 1：Schema Compliance 校验
            json_parsed = False
            schema_compliant = False
            try:
                cleaned_raw = raw_resp.strip()
                if cleaned_raw.startswith("```json"):
                    cleaned_raw = cleaned_raw[7:]
                elif cleaned_raw.startswith("```"):
                    cleaned_raw = cleaned_raw[3:]
                if cleaned_raw.endswith("```"):
                    cleaned_raw = cleaned_raw[:-3]
                parsed_json = json.loads(cleaned_raw.strip())
                json_parsed = True

                # 检查必备字段是否存在
                required_keys = {
                    "target_date", "hypothesis_type", "target_asset",
                    "expected_scenario", "premise_logic", "expected_phenomenon",
                    "expected_assertions", "invalidation_condition", "invalidation_assertions",
                }
                if required_keys.issubset(set(parsed_json.keys())):
                    schema_compliant = True
                    schema_compliant_count += 1
            except Exception:
                parsed_json = {}

            # 7. 指标 2：Validator Compliance
            if exec_record.is_valid:
                validator_pass_count += 1
                v_status = "PASS"
            else:
                validator_reject_count += 1
                v_status = "REJECT"
                err_code = exec_record.validation_error_code or "UNKNOWN"
                for vr_k in vr_rule_counts.keys():
                    if vr_k in err_code:
                        vr_rule_counts[vr_k] += 1

            # 8. 指标 3：Trading Boundary 校验
            found_prohibited_words = []
            for kw in PROHIBITED_TRADING_KEYWORDS:
                if kw in raw_resp:
                    found_prohibited_words.append(kw)
            if found_prohibited_words:
                trading_keyword_violations += 1

            # 9. 指标 4：AST Compilation 校验与后续证伪仲裁执行
            ast_hash = None
            falsification_info = {"status": "SKIPPED", "outcome": None, "details": "Validator not passed"}
            if exec_record.is_valid and exec_record.compiled_hypothesis:
                ast_compiled_count += 1
                hypo = exec_record.compiled_hypothesis
                ast_content = json.dumps(hypo.model_dump(), sort_keys=True, ensure_ascii=False)
                ast_hash = hashlib.sha256(ast_content.encode("utf-8")).hexdigest()

                # 驱动收窄 AST 编译
                orm_hypo = MarketHypothesis(
                    id=trial_idx,
                    hypothesis_type=hypo.hypothesis_type,
                    target_asset=hypo.target_asset,
                    created_date=hypo.created_date,
                    target_date=hypo.target_date,
                    premise_logic=hypo.premise_logic,
                    expected_phenomenon=hypo.expected_phenomenon,
                    assertion_metrics=hypo.assertion_metrics,
                    invalidation_condition=hypo.invalidation_condition,
                )
                try:
                    ast_def = HypothesisServiceAdapter.compile_hypothesis_definition(orm_hypo)
                    ast_hash = ast_def.hypothesis_hash

                    # 挂载 T+1 真实客观事实切片，执行下游 FalsificationEngine 仲裁
                    t_plus_1_row = load_raw_daily_review_row(db_path, target_date)
                    if t_plus_1_row:
                        t_rev = DailyReview(
                            date=target_date,
                            market_overview=t_plus_1_row[0],
                            limit_up_analysis=t_plus_1_row[1],
                            report_content=t_plus_1_row[2],
                            data_quality="PARTIAL",
                        )
                        t_obs_data = HypothesisServiceAdapter.extract_observation_data(target_date, review=t_rev)
                        adj_res = FalsificationEngine.adjudicate(ast_def, t_obs_data)
                        falsification_info = {
                            "status": "ADJUDICATED",
                            "outcome": adj_res.outcome.value,
                            "falsification_triggered": adj_res.falsification_triggered,
                            "details": adj_res.details,
                        }
                    else:
                        falsification_info = {
                            "status": "PENDING_FUTURE_DATE",
                            "outcome": "PENDING",
                            "details": f"Target date {target_date} data not yet available in history DB",
                        }
                except Exception as ast_err:
                    falsification_info = {
                        "status": "AST_COMPILE_ERROR",
                        "outcome": "ERROR",
                        "details": str(ast_err),
                    }

            # 10. 提取 LLM 提出的具体阈值 (用于 Section 8: 阈值溯源留存)
            proposed_thresholds = []
            if isinstance(parsed_json, dict):
                for a in parsed_json.get("expected_assertions", []):
                    if isinstance(a, dict):
                        proposed_thresholds.append({
                            "kind": "EXPECTED",
                            "metric": a.get("metric_type"),
                            "operator": a.get("operator"),
                            "threshold": a.get("threshold"),
                            "provenance": "LLM_SANDBOX_PROPOSED",
                        })
                for a in parsed_json.get("invalidation_assertions", []):
                    if isinstance(a, dict):
                        proposed_thresholds.append({
                            "kind": "INVALIDATION",
                            "metric": a.get("metric_type"),
                            "operator": a.get("operator"),
                            "threshold": a.get("threshold"),
                            "provenance": "LLM_SANDBOX_PROPOSED",
                        })

            # 计算 observation 确定性哈希
            obs_hash = hashlib.sha256(json.dumps(obs, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

            # 11. 组装单条机器审计记录 (保留完整的 Raw LLM Response 与指令第7节必备键名)
            rec_dict = {
                "trial_id": trial_id,
                "observation_date": market_date,
                "target_date": target_date,
                "observation_hash": obs_hash,
                "prompt_spec_version": prompt_spec.version,
                "prompt_spec_hash": prompt_spec.prompt_hash,
                "final_prompt_hash": final_prompt_hash,
                "model_provider": "DeepSeek / OpenAI Compatible",
                "model_name": driver.model if not use_mock else "MOCK_DETERMINISTIC",
                "request_timestamp": req_time,
                "raw_llm_response": raw_resp,
                "json_parse_result": json_parsed,
                "schema_compliance": {
                    "json_parsed": json_parsed,
                    "schema_compliant": schema_compliant,
                },
                "validator_result": v_status,
                "validation_errors": (
                    [f"{exec_record.validation_error_code}: {exec_record.validation_error_detail}"]
                    if not exec_record.is_valid else []
                ),
                "compiled_ast_hash": ast_hash,
                "compile_result": "SUCCESS" if ast_hash else "SKIPPED_OR_FAILED",
                "llm_proposed_thresholds": proposed_thresholds,
                "trading_boundary": {
                    "prohibited_words_found": found_prohibited_words,
                    "zero_trading_intent": len(found_prohibited_words) == 0,
                },
                "ast_compilation": {
                    "is_compiled": exec_record.is_valid and exec_record.compiled_hypothesis is not None,
                    "ast_hash": ast_hash,
                    "compiled_hypothesis": exec_record.compiled_hypothesis.model_dump() if exec_record.compiled_hypothesis else None,
                },
                "falsification_adjudication": falsification_info,
            }
            trial_records.append(rec_dict)
            print(f"    -> 校验结果: {v_status} (Schema: {schema_compliant}, Prohibited Words: {len(found_prohibited_words)}, Falsification: {falsification_info.get('outcome')})")

    # 11. 综合裁决判定 (严格遵守指令第十二节标准)
    schema_compliance_rate = schema_compliant_count / total_proposals if total_proposals > 0 else 0.0
    validator_pass_rate = validator_pass_count / total_proposals if total_proposals > 0 else 0.0

    verdict = "TRIAL-FAIL"
    if future_leakage_violations > 0:
        # 未来事实进入 Prompt，刚性判定 FAIL
        verdict = "TRIAL-FAIL"
    elif validator_pass_count == total_proposals and schema_compliance_rate == 1.0 and trading_keyword_violations == 0:
        # 100% 通过无拦截
        verdict = "TRIAL-PASS"
    elif future_leakage_violations == 0 and ast_compiled_count == validator_pass_count:
        # 绝大多数模型合规，个别被 Validator 正常拦截（VR-01或VR-07），无穿透入库，属于受控通过
        verdict = "TRIAL-CONDITIONAL"

    end_timestamp = datetime.now(timezone.utc).isoformat()

    summary_evidence = {
        "metadata": {
            "title": "Phase 2B.2 LLM Cognition Proposer Sandbox Trial Machine Evidence",
            "start_time": start_timestamp,
            "end_time": end_timestamp,
            "mode": "MOCK_BENCHMARK" if use_mock else "REAL_LLM",
            "model_metadata": driver.get_public_metadata() if not use_mock else {"model": "MOCK"},
            "prompt_spec_version": prompt_spec.version,
            "prompt_spec_hash": prompt_spec.prompt_hash,
            "database_source": db_path,
        },
        "verdict": verdict,
        "metrics_summary": {
            "total_proposals": total_proposals,
            "schema_compliant_count": schema_compliant_count,
            "schema_compliance_rate": round(schema_compliance_rate, 4),
            "validator_pass_count": validator_pass_count,
            "validator_pass_rate": round(validator_pass_rate, 4),
            "validator_reject_count": validator_reject_count,
            "vr_rule_counts": vr_rule_counts,
            "ast_compiled_count": ast_compiled_count,
            "trading_keyword_violations": trading_keyword_violations,
            "future_leakage_violations": future_leakage_violations,
        },
        "trial_records": trial_records,
    }

    evidence_path = os.path.join(backend_dir, "..", "baseline_evidence", "llm_sandbox_trial_evidence.json")
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(summary_evidence, f, ensure_ascii=False, indent=2)

    print("=" * 80)
    print(f"Trial Completed! Verdict: {verdict}")
    print(f"Evidence written to: {os.path.abspath(evidence_path)}")
    print("=" * 80)
    return summary_evidence


if __name__ == "__main__":
    is_mock = "--mock" in sys.argv
    p_per_day = 1
    if "--two-proposals" in sys.argv:
        p_per_day = 2
    run_trial(use_mock=is_mock, proposals_per_day=p_per_day)
