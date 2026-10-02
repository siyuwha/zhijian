import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class MetricDelta(BaseModel):
    """单项度量差分模型"""
    metric_name: str
    base_value: Any
    candidate_value: Any
    delta: Optional[float] = None
    is_regressed: bool = False
    reason: Optional[str] = None

class BaselineDiffReport(BaseModel):
    """KA-06 基线差分与防退化门禁裁决报告"""
    status: str = Field(description="PASS 或 FAIL")
    evaluated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    golden_version: str
    golden_commit: str
    violations: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    metrics_diff: Dict[str, MetricDelta] = Field(default_factory=dict)
    schema_diff: Dict[str, Any] = Field(default_factory=dict)
    isolation_passed: bool = True

    def to_markdown(self) -> str:
        """格式化输出标准 Markdown 门禁裁决看板"""
        lines = [
            "# KA-06 基线差分防退化门禁裁决报告",
            f"> **裁决结论**：{'🟢 准入放行 (PASS)' if self.status == 'PASS' else '🔴 阻断拦截 (FAIL)'}  ",
            f"> **基线版本**：`{self.golden_version}` (`{self.golden_commit[:8]}`)  ",
            f"> **评估时间**：`{self.evaluated_at}`  ",
            "",
            "## 一、核心拦截与违规事项",
        ]
        if not self.violations:
            lines.append("- ✅ 零退化违规项，全部核心指标满足或优于黄金基线要求。")
        else:
            for v in self.violations:
                lines.append(f"- ❌ **门禁拦截**：{v}")

        if self.warnings:
            lines.append("\n## 二、非阻断警示项")
            for w in self.warnings:
                lines.append(f"- ⚠️ {w}")

        lines.extend([
            "",
            "## 三、核心度量对比矩阵 (Metric Comparison Matrix)",
            "| 度量指标 | 黄金基准值 | 当前待测值 | 差分变动 | 状态判定 |",
            "| :--- | :---: | :---: | :---: | :---: |"
        ])

        for name, m in self.metrics_diff.items():
            status_badge = "❌ 退化" if m.is_regressed else "✅ 正常"
            delta_str = f"{m.delta:+.2f}" if m.delta is not None else "--"
            lines.append(f"| {name} | `{m.base_value}` | `{m.candidate_value}` | `{delta_str}` | {status_badge} |")

        lines.extend([
            "",
            "## 四、物理 Schema 与隔离状态",
            f"- 表结构完整性：`{'100% 匹配' if self.schema_diff.get('tables_all_present') else '存在缺失'}`",
            f"- WORM 触发器存在性：`{'100% 就绪' if self.schema_diff.get('triggers_all_present') else '存在缺失'}`",
            f"- 创世链锚点：`{'已锚定' if self.schema_diff.get('genesis_valid') else '异常'}`",
            f"- 数据库物理隔离：`{'完全隔离 (零修改)' if self.isolation_passed else '发生意外写入'}`",
            "",
            f"**裁决签名**：KA-06 BaselineDiffEngine Auto-Adjudication -> `{self.status}`"
        ])
        return "\n".join(lines)


class BaselineDiffEngine:
    """KA-06 基线差分与防退化门禁引擎"""

    def __init__(self, manifest_path: Optional[Path] = None):
        if manifest_path is None:
            # 默认指向 baseline_evidence/golden_baseline_manifest.json
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
            manifest_path = repo_root / "baseline_evidence" / "golden_baseline_manifest.json"
        
        self.manifest_path = manifest_path
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> dict:
        if not self.manifest_path.exists():
            raise FileNotFoundError(f"Golden baseline manifest not found at {self.manifest_path}")
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def evaluate(
        self,
        candidate_metrics: Dict[str, Any],
        candidate_tables: List[str],
        candidate_triggers: List[str],
        genesis_row: Optional[dict] = None,
        isolation_hashes_match: bool = True
    ) -> BaselineDiffReport:
        """
        执行基线差分与防退化门禁裁决
        """
        violations = []
        warnings = []
        metrics_diff = {}

        golden_metrics = self.manifest["metrics"]
        golden_schema = self.manifest["schema_contract"]

        # 1. 测试总数防退化检查 (必须 >= 黄金基线 148 项)
        cand_total = candidate_metrics.get("total_tests", 0)
        base_total = golden_metrics["total_tests_required"]
        reg_total = cand_total < base_total
        if reg_total:
            violations.append(f"测试用例总数退化：当前 {cand_total} 项，基线要求至少 {base_total} 项 (缺失 {base_total - cand_total} 项)")
        metrics_diff["total_tests"] = MetricDelta(
            metric_name="total_tests",
            base_value=base_total,
            candidate_value=cand_total,
            delta=float(cand_total - base_total),
            is_regressed=reg_total,
            reason="测试被删除或未能发现" if reg_total else None
        )

        # 2. 测试失败数检查 (必须 == 0)
        cand_failed = candidate_metrics.get("failed_tests", 0)
        reg_failed = cand_failed > golden_metrics["test_failure_max"]
        if reg_failed:
            violations.append(f"测试套件出现失败：当前失败数 {cand_failed}，基线容差为 0")
        metrics_diff["failed_tests"] = MetricDelta(
            metric_name="failed_tests",
            base_value=golden_metrics["test_failure_max"],
            candidate_value=cand_failed,
            delta=float(cand_failed),
            is_regressed=reg_failed,
            reason="存在单测失败" if reg_failed else None
        )

        # 3. 测试错误数检查 (必须 == 0)
        cand_errors = candidate_metrics.get("error_tests", 0)
        reg_errors = cand_errors > golden_metrics["test_error_max"]
        if reg_errors:
            violations.append(f"测试套件出现异常错误：当前错误数 {cand_errors}，基线容差为 0")
        metrics_diff["error_tests"] = MetricDelta(
            metric_name="error_tests",
            base_value=golden_metrics["test_error_max"],
            candidate_value=cand_errors,
            delta=float(cand_errors),
            is_regressed=reg_errors,
            reason="存在单测执行崩溃" if reg_errors else None
        )

        # 4. 通过率检查 (必须 100%)
        cand_rate = candidate_metrics.get("pass_rate", 0.0)
        base_rate = golden_metrics["test_pass_rate_min"]
        reg_rate = cand_rate < base_rate
        if reg_rate:
            violations.append(f"测试通过率低于基线：当前 {cand_rate*100:.1f}%，基线要求 100.0%")
        metrics_diff["pass_rate"] = MetricDelta(
            metric_name="pass_rate",
            base_value=base_rate,
            candidate_value=cand_rate,
            delta=float(cand_rate - base_rate),
            is_regressed=reg_rate
        )

        # 5. Schema 完整性对比
        expected_tables = set(golden_schema["expected_tables"])
        candidate_tables_set = set(candidate_tables)
        missing_tables = expected_tables - candidate_tables_set
        if missing_tables:
            violations.append(f"物理数据库表结构缺失：缺少 {sorted(list(missing_tables))}")

        expected_triggers = set(golden_schema["expected_triggers"])
        candidate_triggers_set = set(candidate_triggers)
        missing_triggers = expected_triggers - candidate_triggers_set
        if missing_triggers:
            violations.append(f"物理 WORM 防篡改触发器缺失：缺少 {sorted(list(missing_triggers))}")

        # 6. Genesis 链锚点校验
        genesis_valid = False
        if genesis_row:
            exp_anchor = golden_schema["genesis_anchor"]
            if (genesis_row.get("chain_id") == exp_anchor["chain_id"] and
                genesis_row.get("tail_sequence_id") == exp_anchor["tail_sequence_id"] and
                genesis_row.get("tail_record_hash") == exp_anchor["tail_record_hash"]):
                genesis_valid = True
            else:
                violations.append(f"创世锚点内容与黄金基线不匹配：当前为 {genesis_row}")
        else:
            violations.append("缺失创世链状态锚点记录 (Genesis Anchor Row)")

        # 7. 数据库物理隔离 (测试不得污染真实开发库)
        if not isolation_hashes_match:
            violations.append("物理数据库未隔离：运行期间开发库文件哈希被改写！")

        schema_diff = {
            "tables_all_present": len(missing_tables) == 0,
            "missing_tables": sorted(list(missing_tables)),
            "triggers_all_present": len(missing_triggers) == 0,
            "missing_triggers": sorted(list(missing_triggers)),
            "genesis_valid": genesis_valid
        }

        status = "PASS" if not violations else "FAIL"

        return BaselineDiffReport(
            status=status,
            golden_version=self.manifest["version"],
            golden_commit=self.manifest["commit"],
            violations=violations,
            warnings=warnings,
            metrics_diff=metrics_diff,
            schema_diff=schema_diff,
            isolation_passed=isolation_hashes_match
        )
