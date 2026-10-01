# Phase 2A Step 4 与 Step 5 职责边界澄清与架构裁决方案
**文档编号**: `DOC-PHASE2A-STEP4-BOUNDARY-20261001`  
**关联决议**: `BOARD DECISION: PLAN-PHASE2A-STEP4-20261001 = CONDITIONALLY APPROVED`  
**当前状态**: `FROZEN / SUBMITTED FOR FINAL BOARD ADJUDICATION`  
**核心议题**: 厘清事前假说定义投影（Step 4）与事后真值对撞验证（Step 5）的物理与逻辑分水岭，防范职责早熟溢出

---

## 一、 董事会有条件批准令执行声明

董事会针对《Phase 2A Step 4 假说定义投影与收窄 AST 断言执行器实施规划》下达工程裁决：
> `PLAN-PHASE2A-STEP4-20261001 = CONDITIONALLY APPROVED`  
> 
> **授权**:  
> ✓ Step 4.1 Contracts & Definition Projection (契约模型与假说定义投影)  
> ✓ Narrowed AST Schema Definition (收窄 AST 语法 Schema 白名单定义)  
> ✓ RFC 8785 JCS Fingerprint (假说指纹与集合指纹计算)  
> ✓ Immutability & Hash Invariants (C-02 隔离不变量与不可变约束)  
> ✓ Unit Tests for Definition Layer (定义层 4 项刚性单元测试)  
> 
> **暂不授权**:  
> ✗ Step 4.2 Assertion Runtime (断言求值运行时)  
> ✗ Step 4.3 Falsification Runtime (证伪裁决运行时)  
> ✗ Step 4.4 Validation Pipeline (验证状态机流水线)  
> ✗ LLM Runtime / Production DB / Trading Integration  
> 
> **前置阻断条件**:  
> 必须彻底澄清 Step 4 与 Step 5 的职责边界、明确 Assertion AST 语言属性、明确 Validation State 物理归属，防止将 Step 5 核心能力提前塞入 Step 4。

工程团队即刻无条件响应：
1. **立即归档隔离**: 试验性求值器草稿代码与执行测试已全量移出正式代码库，暂存于隔离暂存区 (`scratch/`)，生产 Python 命名空间及测试集仅保留已获授权的 Sub-Step 4.1 定义层契约与指纹组件；
2. **基准测试闭环**: Sub-Step 4.1 定义层 4 项契约测试 100% 通过，全系统 103/103 自动化回归 100% 通过（耗时 37.22s），零 LLM、零交易泄漏、零数据库 Migration；
3. **架构专向答辩**: 形成本报告，逐项彻底澄清董事会关注的四大前置问题，并提交重组建议。

---

## 二、 核心问题一：Step 4 与 Step 5 的刚性职责边界澄清

### 2.1 时域与语义的根本差异

在 AI 认知复盘与交易系统中，“假说定义（Hypothesis Definition）”与“假说验证（Hypothesis Validation）”分属于两个**不可跨越的时间维度**：

```text
========================================================================================
【时域 A: 决策推演时刻 T_decision (09:15 / 盘前 / 盘中)】 -> Step 4 的唯一领地
========================================================================================
输入: EffectiveInferenceInput (Step 3 冻结契约)
行为: 基于已知事实进行认知推演，提出具有“可证伪性”的前瞻性主张与预期。
契约: 产出结构化假说定义投影 (MarketHypothesisDefinition / HypothesisSetProjection)
特征: 此时未来的实际市场数据 Y_t 尚未发生，不可访问，不可假设！
边界: 仅定义“什么情况下我认为我错了（证伪条件）”，并完成 JCS 哈希锚定。
状态: 假说在此刻的状态永远是 COMMITTED (已提报/待验证)，不存在任何确认或被证伪的实际事实。

----------------------------------------------------------------------------------------
【时域 B: 真实截面对撞时刻 T_realization (09:25 / 09:30 / 15:00 / T+1)】 -> Step 5 的唯一领地
========================================================================================
输入: T_realization 时刻的事实切片 (Realization ObservationSnapshot) + 冻结的假说集合
行为: 解释执行 AST 谓词，提取实际数值，执行操作符判定，按“证伪优先”判定胜负。
契约: 产出事后验证记录 (CognitionValidationRecord / HypothesisValidationRecord)
特征: 事实真值已经落定，与事前承诺的假说发生确定性对撞。
边界: 驱动状态机流转 (CONFIRMED / FALSIFIED / INCONCLUSIVE)，追踪认知偏差与漂移。
```

### 2.2 职责分工矩阵表

| 维度 | Step 4: 假说定义投影层 | Step 5: 事后证伪与验证引擎 |
| :--- | :--- | :--- |
| **所属时域** | 事前决策时刻 ($T_{decision}$) | 事后真实截面到达时刻 ($T_{realization}$) |
| **核心使命** | 约束 LLM/规则引擎输出**合规的、收窄的、不可篡改的科学假说定义** | 依据实际到达的市场事实，**无情裁决假说是被证实还是被证伪** |
| **输入标的** | `EffectiveInferenceInput` (Step 3 产物) | 冻结的 `HypothesisSetProjection` + 真实截面 `ObservationSnapshot` |
| **核心产物** | `MarketHypothesisDefinition`, `HypothesisSetProjection`, `hypothesis_set_hash` | `AssertionOutcome`, `HypothesisValidationRecord`, `ValidationStateMachine` |
| **AST 角色** | **声明式语法定义 (Schema / Definition DSL)** | **解释执行器靶标 (Execution Target & Runtime)** |
| **持久化目标** | 作为 `CognitionRecord` 的核心不可变字段（事前存证） | 写入只追加的 `cognition_validation_record`（事后存证） |
| **状态修改权** | **绝对无权变更状态**（无状态运行时） | **唯一拥有核验裁决权与状态流转权** |

---

## 三、 核心问题二：Assertion AST 是“定义语言”还是“执行语言”？

**董事会问**: Assertion AST 究竟是“定义语言”还是“执行语言”？如果是执行语言，为何放在事前定义的 Step 4？

**架构结论**: **Assertion AST 的双重属性在生命周期中严格解耦——在 Step 4 中它是纯粹的“定义语言（Schema DSL）”，在 Step 5 中才成为解释器的“执行语言（Executable AST）”。**

### 3.1 Step 4 中的定位：纯粹的声明式定义语言 (DSL Schema)
在 Step 4，AST 是一组强类型、严格受限的 Pydantic 数据规范（Value Object）：
1. **语法封闭性**: 仅允许白名单字段（`board_height`, `open_pct_change`, `sector_code` 等），严禁任意 SQL 语句或动态脚本；
2. **结构平铺性**: 条件选择器 `StructuredFilter` 仅允许单层条件平铺（AND/OR），彻底封杀嵌套子查询、关联查询或动态表达式；
3. **序列化唯一性**: AST 的每一个节点都能无损映射为 RFC 8785 JCS 字典，用于计算 `assertion_hash` 和 `hypothesis_hash`；
4. **静态只读性**: 在 Step 4，AST 是一张“体检清单”或“军令状”。**写下军令状（Step 4）不需要马上打仗（Step 5），军令状本身的语法完备性与格式合规性独立于打仗的结果！**

### 3.2 Step 5 中的定位：确定性解释执行靶标 (Execution Runtime)
只有当真实市场的观测快照在 $T_{realization}$ 到达时，AST 才被投入执行运行时：
1. `AssertionEvaluator`（运行时解释器）接受冻结的 AST 和真实快照，按 AST 指定的 universe 筛选标的，应用单层过滤，计算聚合值，比对操作符；
2. 如果把解释执行器与流水线提前在 Step 4 实现，不仅会导致 Step 4 职能膨胀，还会诱使开发人员在假说定义阶段就试图引入 Mock 数据进行自测，混淆“事前承诺”与“事后验证”的时序边界。

**裁决建议**: **Step 4 仅固化 AST Schema（定义语言）；AST Evaluator Runtime（执行语言解释器）正式划归 Step 5。**

---

## 四、 核心问题三：Validation State 的唯一物理与逻辑归属

**董事会问**: Validation State 的唯一归属是谁？如果放在 `CognitionRecord` 中，如何不违反 Step 1 已冻结的 WORM 数据库触发器？

**架构结论**: **Validation State 物理上必须严格归属于独立的、只追加的验证账本（`CognitionValidationRecord`），绝对不得作为 `CognitionRecord` 的可变状态字段进行原地 `UPDATE`。**

### 4.1 物理约束：Step 1 WORM 触发器不可逾越
在 Step 1 中，我们在 SQLite/PostgreSQL 底座建立了不可篡改触发器：
```sql
CREATE TRIGGER prevent_cognition_record_update
BEFORE UPDATE ON cognition_record
BEGIN
    SELECT RAISE(FAIL, 'WORM Violation: cognition_record is immutable.');
END;
```
如果 Step 4 或 Step 5 试图通过 `UPDATE cognition_record SET status = 'CONFIRMED'` 来记录验证结果，将**直接触发物理数据库异常**。任何试图放开此 WORM 限制的建议都是倒退与违规。

### 4.2 C-02 隔离不变量的数学必然
在 Step 4 确立的 C-02 不变量规定：
$$\text{hypothesis\_hash} = \text{SHA-256}(\text{JCS}(\text{CanonicalDefinition}))$$
如果假说的验证状态（如 `status="CONFIRMED"`、`actual_data_snapshot`、`verified_at`）物理内嵌在假说定义中：
- 一旦事后填充实际值或修改状态，定义哈希必将发生雪崩突变（Avalanche Effect）；
- 破坏了区块链式哈希追溯的根本基础（事前承诺哈希无法对应事后审计记录）。

### 4.3 终局设计：两层物理实体解耦与外键引用

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 表 1: cognition_record (WORM 物理只读存证，T_decision 写入)           │
├────────────────────────────────────────────────────────────────────────┤
│ • cognition_id (PK)                                                    │
│ • effective_input_hash (指向 Step 3 输入)                              │
│ • hypothesis_set (包含 MarketHypothesisDefinition 列表与 AST 定义)     │
│ • hypothesis_set_hash (事前计算并冻结的 JCS 根哈希)                   │
│ • created_at                                                           │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ 1 : N (物理只追加关联)
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ 表 2: cognition_validation_record (事后验证只追加账本，T_realization 写入)│
├────────────────────────────────────────────────────────────────────────┤
│ • validation_id (PK)                                                   │
│ • cognition_record_id (FK -> 指向被核验的认知主记录)                  │
│ • hypothesis_hash (FK -> 指向被核验的具体假说指纹)                     │
│ • verification_snapshot_id (指向 T_realization 到达的事实切片)         │
│ • verification_outcome (CONFIRMED / FALSIFIED / INCONCLUSIVE)          │
│ • actual_metrics (实际提取出来的物理指标字典)                          │
│ • verified_at (验证完成时刻)                                           │
│ • provenance_trace (完整的四维时间与输入指纹证据链)                    │
└────────────────────────────────────────────────────────────────────────┘
```

**归属裁决**:
1. `CognitionRecord` **仅承载假说的事前定义与集合哈希**，写入后永久只读；
2. `Validation State` **唯一归属于 `CognitionValidationRecord`**，每次验证产生一条独立的 Append-Only 证据行；
3. 内存运行时的 `HypothesisRuntimeState` 仅作为展现层或计算层的瞬态视图模型（Ephemeral Projection），严禁反向污染 `MarketHypothesisDefinition`。

---

## 五、 核心问题四：4.2～4.4 归属裁决与重组方案

基于上述三大核心澄清，工程团队对 Step 4 与 Step 5 的实施范围提出**清晰彻底的重组裁决方案**：

```text
【原计划方案 (职责重叠风险)】:
Step 4 = 定义契约 (4.1) + AST 求值器 (4.2) + 证伪引擎 (4.3) + 组装流水线 (4.4)
Step 5 = 验证状态机 + 双时点对撞闭环 (与 Step 4.2~4.4 存在大量功能重叠与边界模糊)

【重组后方案 (职责绝对清晰，物理解耦)】:
================================================================================
Step 4 (当前步): 假说定义投影与收窄 AST 契约层 (Hypothesis Definition Layer)
================================================================================
  ✓ Sub-Step 4.1: Contracts & AST Schema Definition (定义契约与 AST 白名单)
  ✓ Sub-Step 4.2: JCS Fingerprint & C-02 Invariant (不可变指纹与隔离验证)
  ✓ 产物交付:
    - backend/app/cognition/hypothesis/contracts.py
    - backend/app/cognition/hypothesis/fingerprint.py
    - backend/tests/test_cognition_step4_contracts.py (4/4 PASS)
  ✓ 边界状态: 立即以此为基准完成 Step 4 终局封口！不再引入任何运行时求值代码！

================================================================================
Step 5 (下一步): 收窄 AST 解释执行器与事后证伪闭环 (Validation & Falsification Engine)
================================================================================
  ✓ Sub-Step 5.1: Narrowed AST Evaluator Runtime (AST 解释器运行时，从 scratch 恢复并标准化)
  ✓ Sub-Step 5.2: Falsification-First Adjudication Engine (证伪优先裁决引擎)
  ✓ Sub-Step 5.3: Dual-Timestamp Snapshot Pairing (09:15 vs 09:25/09:30/15:00 快照对撞)
  ✓ Sub-Step 5.4: Append-Only Validation Ledger & State Machine (只追加验证账本与流转状态机)
  ✓ Sub-Step 5.5: 端到端验证装配与 AST 架构静态扫描 (Zero-LLM / Zero-Trading 边界闭环)
```

---

## 六、 Sub-Step 4.1 实施完成现状与验收证据链

在董事会有条件授权下，Sub-Step 4.1 已完成最高标准的工程落地与自动化验证：

### 6.1 代码交付物清册
1. `backend/app/cognition/hypothesis/__init__.py`: 规范化包导出，仅暴露定义层契约与指纹工具；
2. `backend/app/cognition/hypothesis/contracts.py`:
   - 强类型枚举: `MetricType`, `UniverseType`, `OperatorType`, `AggregationType`, `MissingDataPolicy`, `AssertionOutcome`, `HypothesisOutcome`；
   - AST 语法白名单: `WHITELIST_FILTER_FIELDS = {"board_height", "sector_code", "is_highest_board", "is_st", "market_cap", "code", "name"}`；
   - 强类型 AST 节点: `FilterCondition`, `StructuredFilter`, `MetricAssertion`；
   - 假说定义主体: `MarketHypothesisDefinition`, `HypothesisSetProjection` (全部 `frozen=True`)；
   - 瞬态状态模型: `HypothesisRuntimeState` (与定义层物理隔离)。
3. `backend/app/cognition/hypothesis/fingerprint.py`:
   - RFC 8785 JCS 规范序列化实现；
   - `compute_hypothesis_hash()`: 基于假说定义字段的 SHA-256 计算；
   - `compute_hypothesis_set_hash()`: 基于排序假说哈希数组的集合哈希聚合计算；
   - `verify_hypothesis_hash()`, `verify_hypothesis_set_hash()`: 防篡改验真函数。

### 6.2 自动化测试证据 (4/4 PASS)
测试文件: `backend/tests/test_cognition_step4_contracts.py`

| 测试用例 | 验证目标 | 裁决结果 |
| :--- | :--- | :--- |
| `test_01_hypothesis_model_immutability` | 验证假说模型属性不可变约束（`ValidationError` 拦截原地修改） | **PASS** |
| `test_02_hypothesis_hash_determinism_and_verification` | 验证 JCS SHA-256 指纹跨环境可重现性与篡改检测雪崩效应 | **PASS** |
| `test_03_hypothesis_set_hash_aggregation` | 验证集合根哈希聚合的排序无关性（强制 JCS 排序）与完整性 | **PASS** |
| `test_04_c02_invariant_runtime_state_does_not_pollute_definition_hash` | **C-02 隔离不变量证明**: 验证后验状态流转与实际切片注入完全不改变假说定义哈希 | **PASS** |

### 6.3 全系统回归与架构扫描证据 (103/103 PASS)
- **运行命令**: `pytest backend/tests -v`
- **执行耗时**: 37.22 秒
- **通过数量**: **103 passed, 0 failed, 0 error** (涵盖 Step 1 WORM、Step 2 韧性底座、Step 3 事实投影与装配、Step 4.1 定义层契约)
- **静态合规**:
  - 无任何 live LLM API 调用 (Zero LLM Runtime)；
  - 无任何交易系统与订单路由调用 (Zero Trading Leakage)；
  - 无新增数据库迁移脚本 (Zero Database Schema Migration)；
  - 严守 `Physical Facts -> ObservationSnapshot -> EffectiveInferenceInput -> HypothesisDefinition -> Hash -> STOP` 刚性边界。

---

## 七、 报请董事会决议事项

基于上述架构边界厘清与 Sub-Step 4.1 验收证据，工程团队正式提请董事会发布如下终审工程裁决：

1. **批准 Step 4 重组方案**:
   正式将 Step 4 边界缩窄并重新定义为：  
   `PHASE 2A STEP 4 = 假说定义投影与收窄 AST 契约层 (HYPOTHESIS DEFINITION & NARROWED AST SCHEMA)`。
2. **正式验收通过 Step 4**:
   鉴于 Sub-Step 4.1 的契约、AST Schema、JCS 指纹、C-02 不变量已全部完成且通过 4/4 契约测试与 103/103 全量回归，批准：  
   `STEP 4 = ACCEPTED / OFFICIALLY CLOSED`。
3. **正式批准将 AST 执行器与证伪流水线移入 Step 5**:
   将原规划中的 4.2（求值运行时）、4.3（证伪引擎）、4.4（流水线）与原 Step 5 合并，重构为统一的：  
   `PHASE 2A STEP 5: 收窄 AST 解释执行器、事后真值对撞与证伪闭环 (VALIDATION & FALSIFICATION ENGINE)`。
4. **准予受控启动 Step 5 实施规划编制**:
   授权工程团队按照重构后的 Step 5 边界，编制《Phase 2A Step 5 实施规划与双时点对撞设计方案》，待董事会审议通过后启动编码。
