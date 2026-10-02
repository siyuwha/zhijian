# Phase 2B.2 受约束 LLM 认知假说提议器契约设计单 (Constrained LLM Cognition Proposer Contract)

> **文档版本**：v1.0.0-FROZEN  
> **归档位置**：`开发文档/56-Phase-2B.2-受约束LLM认知假说提议器契约设计单.md`  
> **基线依赖**：`v0.2.3-reality-replay-audit-baseline` (`97899fd`)  
> **工程治理原则**：契约先导（先设计契约，再写代码）、四权分立（LLM 只提议，绝不裁判）  
> **编制时间**：2026-10-02T20:45:00+08:00  

---

## 一、架构定位与宪法铁律

### 1.1 架构分权模型 (Separation of Concerns)

在系统的认知演进主线中，Phase 2B.1 已经确立了**“客观事实法庭与执行引擎（Falsification Engine & WORM Ledger）”**。  
本阶段（Phase 2B.2）的唯一核心使命，是为大模型建立一个**“戴着严密思维枷锁的认知假说提议器（Constrained Proposer）”**：

```text
  [T 日真实客观复盘事实 M1/M2]
               │
               ▼
  [只读提取：ObservationContext (绝无未来数据)]
               │
               ▼
 ┌──────────────────────────────────────────────┐
 │     LLM Cognition Proposer (假说提议器)      │
 │  • 依据不可变 PromptSpec 推理市场博弈逻辑    │
 │  • 提出前瞻性宏观假说与可证伪预期            │
 └──────────────────────┬───────────────────────┘
                        │ 输出候选 JSON 提案 (Candidate Proposal)
                        ▼
 ┌──────────────────────────────────────────────┐
 │     ProposalValidator (契约准入检查笼头)     │  <--- [核心防御卡点]
 │  • 校验 1: Schema 结构完备性                 │
 │  • 校验 2: 白名单指标与操作符               │
 │  • 校验 3: 刚性证伪断言必须非空 (强制波普尔) │
 │  • 校验 4: 时序因果与反未来偷看              │
 │  • 校验 5: 严禁个股买卖与交易预测            │
 └──────────────────────┬───────────────────────┘
                        │ 校验通过 (PASS) ───[拒绝则丢弃并记录审计日志]
                        ▼
 ┌──────────────────────────────────────────────┐
 │   编译为 AST (MarketHypothesisDefinition)    │
 └──────────────────────┬───────────────────────┘
                        │
                        ▼
 ┌──────────────────────────────────────────────┐
 │ 写入不可变账本 (WORM Ledger: PENDING 状态)   │
 └──────────────────────┬───────────────────────┘
                        │ 次日 15:30 收盘客观事实对撞
                        ▼
 ┌──────────────────────────────────────────────┐
 │  FalsificationEngine (客观法庭自动裁决)      │
 │  CONFIRMED / FALSIFIED / INCONCLUSIVE        │
 └──────────────────────────────────────────────┘
```

### 1.2 五大宪法铁律 (Constitutional Invariants)

1. **铁律 1（先设计契约，再写代码）**：必须先冻结 Prompt 结构、输入输出 Schema 与 Validator 规则，方可编码；
2. **铁律 2（LLM 只负责提议，绝不负责裁判）**：
   - LLM 只能生成命题、预期现象、证伪红线；
   - LLM **严禁**自行宣布假说成立，**严禁**修改已冻结假说，**严禁**参与后验核验打分；裁判权 100% 归属于确定性 AST 执行引擎；
3. **铁律 3（时序因果单向隔离）**：
   - LLM 在提议 T 日假说时，其输入上下文**物理上仅允许包含 T 日及以前**的复盘事实，严禁注入任何 T+1 日及未来数据；
   - 假说目标日期（`target_date`）必须严格晚于建立日期（`created_date`）；
4. **铁律 4（宏观认知受限，严禁交易预测）**：
   - 标的仅限全A宏观聚合（`ALL_A`）与四大核心宽基指数（`sh000001`, `sz399001`, `sz399006`, `sh000688`）；
   - **绝对禁止**出现：个股代码、买入卖出建议、目标价格、仓位指令；
5. **铁律 5（外网 API 解耦，沙箱确定性先行）**：
   - 本阶段首先通过 Mock/沙箱执行确定性验证，保证在断网或无 API Key 状态下，Validator 与 AST 编译全套测试 100% 跑通，不破坏 KA-06 门禁基线。

---

## 二、输入上下文契约 (ObservationContext Contract)

LLM 接收的输入切片由系统只读从 `DailyReview` 与 `MarketDailySnapshot` 抽取，格式严格限定如下：

```json
{
  "market_date": "2026-09-28",
  "indices": [
    {"code": "sh000001", "name": "上证指数", "close": 3823.62, "pct_change": -1.67},
    {"code": "sz399001", "name": "深证成指", "close": 12858.75, "pct_change": -3.44},
    {"code": "sz399006", "name": "创业板指", "close": 2988.10, "pct_change": -4.21},
    {"code": "sh000688", "name": "科创50", "close": 1055.30, "pct_change": -2.15}
  ],
  "limit_up_summary": {
    "total_limit_up": 33,
    "limit_down_count": 56,
    "max_board_height": 5,
    "broken_ratio": 0.25
  },
  "breadth": {
    "up_count": 820,
    "down_count": 4350
  },
  "market_state": {
    "state_label": "极弱收缩",
    "d1_sentiment": "恐慌退潮"
  }
}
```

---

## 三、输出假说提案契约 (LLMProposalPayload Contract)

LLM 必须以严格的 JSON 格式输出，由 JSON Schema 实施约束：

```json
{
  "target_date": "2026-09-29",
  "hypothesis_type": "SENTIMENT_CYCLE",
  "target_asset": "全市场短线投机生态",
  "expected_scenario": "REBOUND",
  "premise_logic": "09-28全市场跌停家数达56家，高位连板大幅出清，呈现情绪严重冰点，预期09-29迎来超跌修复",
  "expected_phenomenon": "涨停家数重回40家以上，跌停家数大幅收窄",
  "expected_assertions": [
    {
      "assertion_id": "exp_lu_rebound",
      "metric_type": "limit_up_count",
      "target_code": "ALL_A",
      "operator": "GTE",
      "threshold": 40.0,
      "description": "全市场涨停数恢复至40家以上"
    }
  ],
  "invalidation_condition": "若跌停家数仍大于50家，或上证指数跌破重要支撑，则修复假说证伪",
  "invalidation_assertions": [
    {
      "assertion_id": "inv_ld_panic",
      "metric_type": "limit_down_count",
      "target_code": "ALL_A",
      "operator": "GT",
      "threshold": 50.0,
      "description": "跌停家数依然大于50家表明恐慌踩踏延续"
    }
  ],
  "explanation": "基于短线情绪冰点出清理论，次日通常存在情绪修复脉冲，但若跌停未止则逻辑推演失效"
}
```

---

## 四、提案校验器规则清单 (ProposalValidator Rules)

`ProposalValidator` 设立 6 大刚性校验规则，任一违规立即阻断，不予进入 WORM 账本：

| 规则编号 | 规则名称 | 校验逻辑 | 违规处理 |
| :---: | :--- | :--- | :--- |
| **VR-01** | **Schema 结构合法性** | 必须包含 `target_date`, `hypothesis_type`, `premise_logic`, `expected_assertions`, `invalidation_assertions` 等必填字段。 | 抛出 `ValidationError("MISSING_REQUIRED_FIELDS")` |
| **VR-02** | **类型与标的白名单** | `hypothesis_type` 必须在四大宏观枚举内；`target_code` 只能是 `ALL_A`, `sh000001`, `sz399001`, `sz399006`, `sh000688`。严禁具体个股代码。 | 抛出 `ValidationError("ILLEGAL_UNIVERSE_OR_TYPE")` |
| **VR-03** | **指标白名单校验** | `metric_type` 必须在白名单内（`limit_up_count`, `limit_down_count`, `pct_change`, `up_count`, `down_count`, `turnover_ratio`, `board_height`）。严禁脑补“北向资金”、“主力净额”等未采集指标。 | 抛出 `ValidationError("UNAPPROVED_METRIC_DETECTED")` |
| **VR-04** | **操作符与阈值合理性** | `operator` 必须在 (`GT`, `GTE`, `LT`, `LTE`, `EQ`, `BETWEEN`) 中；阈值必须为合法浮点数或双元素闭区间列表。 | 抛出 `ValidationError("ILLEGAL_OPERATOR_OR_THRESHOLD")` |
| **VR-05** | **刚性证伪断言必须非空** | `invalidation_assertions` 列表长度必须 $\ge 1$。必须有明确可量化的反向失效红线。 | 抛出 `ValidationError("MISSING_FALSIFICATION_REDLINE")` |
| **VR-06** | **时序因果硬约束** | 假说 `target_date` 必须严格大于当前事实日期 `market_date`。严禁时间倒挂与当天自证。 | 抛出 `ValidationError("TIME_CAUSALITY_VIOLATION")` |
| **VR-07** | **交易禁令黑名单过滤** | 文本字段中严禁出现交易词汇黑名单（如：“买入”、“卖出”、“建仓”、“加仓”、“目标价”、“清仓”）。 | 抛出 `ValidationError("PROHIBITED_TRADING_ADVICE")` |

---

## 五、提示词规范治理 (PromptSpec WORM Governance)

1. **不可变提示词模板规范**：
   - 提示词定义包含：`prompt_id`, `version`, `system_prompt`, `user_template`, `json_schema_spec`。
   - 每次版本升级生成唯一的 SHA-256 哈希签名。
2. **数据库落库绑定**：
   - 提示词记录受 `cognition_prompt_spec` 表及 `trg_cognition_prompt_spec_no_update` / `trg_cognition_prompt_spec_no_delete` WORM 触发器保护，物理禁止修改。
   - 生成的每条假说均记录 `prompt_spec_version`，确保认知血缘可追溯。

---

## 六、实施边界与交付清单

1. **代码交付物**：
   - `backend/app/cognition/hypothesis/proposal_validator.py`：提案校验器与 AST 转换器；
   - `backend/app/cognition/hypothesis/prompt_spec.py`：提示词规范定义与 WORM 管理；
   - `backend/app/cognition/hypothesis/sandbox_proposer.py`：完全隔离的沙箱推演器。
2. **测试用例交付物**：
   - `backend/tests/test_cognition_phase2b2_llm_proposer.py`：覆盖 VR-01 ~ VR-07 的 7 项拦截测试及全流程冷启动测试。
3. **门禁与基线**：
   - KA-06 基线门禁测试通过率保持 100%，测试用例数预计提升至 178 项；
   - 物理数据库保持零修改。
