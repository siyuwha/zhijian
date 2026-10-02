# Phase 2B.2 受约束 LLM 认知假说提议器验收报告 (Phase 2B.2 Acceptance Report)

> **执行周期**：Phase 2B.2 契约设计、校验器实现与沙箱闭环验证  
> **执行时间**：2026-10-02 20:48  
> **上位依据**：  
> 1. 《开发文档/56-Phase-2B.2-受约束LLM认知假说提议器契约设计单.md》  
> 2. 用户指示：建立并验证受约束的 LLM 认知生成器；LLM 只负责提议，绝不负责裁判；继续冻结 M4/M5 与真实 API Key。  
> **门禁裁决**：🟢 **KA-06 全量门禁放行 (PASS)** (180/180 测试全绿，物理库零污染)  

---

## 一、核心结论与交付清单

本阶段严格遵循**“先设计契约，再写代码”**与**“LLM 仅提议、绝不裁判”**的核心工程哲学，完成了受约束大模型假说提议器的规范定义、强类型校验笼头、不可变提示词规范与离线确定性沙箱闭环：

```text
 ┌────────────────────────────────────────────────────────┐
 │ 1. 契约设计先行                                         │
 │    • 《开发文档/56-Phase-2B.2-受约束LLM认知假说提议器契约设计单.md》 │
 └──────────────────────────┬─────────────────────────────┘
                            │
 ┌──────────────────────────▼─────────────────────────────┐
 │ 2. 核心代码实现                                         │
 │    • ProposalValidator (7大刚性准入防御规则)            │
 │    • PromptSpec (不可变提示词与 SHA-256 溯源存证)        │
 │    • SandboxProposer (沙箱驱动管道与断网确定性执行器)   │
 └──────────────────────────┬─────────────────────────────┘
                            │
 ┌──────────────────────────▼─────────────────────────────┐
 │ 3. 测试与门禁验证                                       │
 │    • 8 项新单元测试与沙箱端到端集成测试全绿             │
 │    • 全量测试从 172 项扩充至 180 项 (100% PASS)         │
 │    • KA-06 基线门禁放行 (PASS)，物理数据库零修改         │
 └────────────────────────────────────────────────────────┘
```

---

## 二、七大刚性校验规则实现与实证拦截矩阵 (VR-01 ~ VR-07)

`ProposalValidator` 在大模型输出与下游不可变账本之间构筑了不可逾越的“思维枷锁”，全部规则在专属测试套件中得到 100% 实证拦截：

| 规则编号 | 规则名称 | 拦截目标与场景 | 实证测试函数 | 测试判定 |
| :---: | :--- | :--- | :--- | :---: |
| **VR-01** | **Schema 结构合法性** | 字段缺失、非 JSON 格式或非法数据类型 | `test_proposal_validator_valid_proposal` | ✅ PASS |
| **VR-02** | **类型与标的白名单** | 严禁具体个股代码（如 `sh600519`），仅限全A宏观与4大宽基指数 | `test_proposal_validator_reject_single_stock_target` | ✅ PASS |
| **VR-03** | **指标白名单校验** | 严禁大模型脑补未采集指标（如 `northbound_capital_inflow`） | `test_proposal_validator_reject_unapproved_metric` | ✅ PASS |
| **VR-04** | **操作符与阈值合理性** | 操作符限定于白名单，BETWEEN 必须为升序双元素区间，常规操作符必须为标量 | `test_proposal_validator_valid_proposal` | ✅ PASS |
| **VR-05** | **刚性证伪断言必须非空** | 必须至少包含 1 条量化失效红线，严禁“只唱多、不可证伪”的假说入库 | `test_proposal_validator_reject_missing_invalidation` | ✅ PASS |
| **VR-06** | **时序因果硬约束** | 假说 `target_date` 必须严格大于建立日期，禁止时间倒挂与当天自证 | `test_proposal_validator_reject_time_inversion` | ✅ PASS |
| **VR-07** | **交易禁令黑名单过滤** | 文本中严禁包含“买入”、“卖出”、“建仓”、“加仓”、“目标价”等交易词汇 | `test_proposal_validator_reject_trading_advice` | ✅ PASS |

---

## 三、不可变提示词治理 (PromptSpec WORM Governance)

- **模块位置**：[`backend/app/cognition/hypothesis/prompt_spec.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/hypothesis/prompt_spec.py)
- **核心特性**：
  - 提示词以结构化实体管理，默认版本 `v1.0.0`；
  - 绑定规范化 SHA-256 指纹：`prompt_hash`；
  - 提示词正文中明确印刻“7大必须遵守的铁律”与 JSON Schema 输出规范；
  - 提供 `render_user_prompt` 函数，严格从 T 日客观事实切片（指数、涨停、跌停、连板、广度、物理标签）单向渲染，物理阻断未来数据。

---

## 四、离线确定性沙箱闭环 (Sandbox Proposer E2E Pipeline)

- **模块位置**：[`backend/app/cognition/hypothesis/sandbox_proposer.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/hypothesis/sandbox_proposer.py)
- **闭环验证成果**：
  - 在 `test_sandbox_proposer_e2e_to_falsification_engine` 中，沙箱驱动管道成功实现了：
    `Observation (09-28真实事实) -> Proposer (Mock LLM) -> ProposalValidator (VR-01~VR-07准入审核通过) -> 编译为 AST -> WORM账本锁定 -> 灌入 09-29 事实 -> FalsificationEngine 客观终局证实 (CONFIRMED)`
  - **全程 0 外网请求、0 Token 损耗、0 浮点不确定性**，完美融入持续集成与门禁系统。

---

## 五、KA-06 防退化门禁回归数据

门禁执行时间：2026-10-02 20:47:25  
门禁执行报告：[`baseline_evidence/ka06_gate_report.md`](file:///d:/项目库/AI认知复盘交易系统/baseline_evidence/ka06_gate_report.md)

| 门禁度量项 | 黄金基线要求 | 当前实际测量值 | 状态判定 |
| :--- | :---: | :---: | :---: |
| **Total Tests** | 180 | **180** | ✅ PASS |
| **Failed / Error Tests** | 0 / 0 | **0 / 0** | ✅ PASS |
| **Test Pass Rate** | 1.0 (100%) | **1.0 (100%)** | ✅ PASS |
| **Max Allowed Duration** | 180.0s | **98.82s** | ✅ PASS |
| **Root DB Zero-Modification** | `True` | **`True`** | ✅ PASS |
| **Backend DB Zero-Modification** | `True` | **`True`** | ✅ PASS |
| **Clean Schema Tables** | 32 | **32 (100% match)** | ✅ PASS |
| **WORM Triggers** | 5 | **5 (100% ready)** | ✅ PASS |
| **Genesis Ledger Anchor** | Tail Seq=0 | **Tail Seq=0 (Anchored)** | ✅ PASS |
| **门禁裁决结论** | - | **PASS** | ✅ 放行 |

---

## 六、下一步建议

随着 Phase 2B.2 契约与沙箱成功闭环，系统已经为大模型铺设好了安全严密的“铁轨”。下一步只需：
1. **配置真实模型驱动器（LLM Driver Adapter）**：提供一个轻量的 HTTP 适配器连接 OpenAI / DeepSeek / 通义千问（仅作为生成器驱动插入 `SandboxProposer`）；
2. **在受控环境中进行首轮真实 LLM 提议试跑**，验证大模型在真实市场切片下的 Schema 遵守率；
3. **M4/M5 与盘股资产继续保持安全冻结**。
