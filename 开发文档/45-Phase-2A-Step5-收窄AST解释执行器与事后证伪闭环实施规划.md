# Phase 2A Step 5: 收窄 AST 解释执行器与事后证伪闭环实施规划
**文档编号**: `PLAN-PHASE2A-STEP5-20261001`  
**关联决议**: `DOC-PHASE2A-STEP4-BOUNDARY-20261001` 与董事会终审工程裁决  
**实施目标**: 构建事后真值对撞、收窄 AST 解释求值、证伪优先仲裁与只追加验证账本的完整闭环  
**执行基准**: 纯沙箱实现（Pure Sandbox），Zero LLM Runtime，Zero Trading Side-Effect，Zero Database Migration  
**状态**: **PENDING BOARD REVIEW / 待董事会审议**  

---

## 一、 Step 5 背景与工程使命

随着 Step 4（假说定义投影与收窄 AST 契约层）正式验收封口（`REPORT-PHASE2A-STEP4-FINAL-CLOSURE-20261001`），系统已在事前时域 ($T_{decision}$) 建立了强类型、单层平铺、抗篡改的假说定义规范与 JCS SHA-256 密码学指纹。

**Phase 2A Step 5 的核心使命**是跨越到**事后真实截面时域 ($T_{realization}$)**，实现科学假说的无情对撞与闭环检验：

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        Phase 2A Step 5 双时点对撞与证伪闭环流向                        │
└────────────────────────────────────────────────────────────────────────────────────────┘

 [事前 T_decision 冻结]
  CognitionRecord (WORM)
  ├── hypothesis_set_hash
  └── MarketHypothesisDefinition ──────┐
      ├── invalidation_assertions      │
      └── expected_assertions          │
                                       ▼
 [事后 T_realization 到达]   ┌──────────────────────────────────────────┐
  ObservationSnapshot ──────>│ 5.1 收窄 AST 解释执行器 (Stateless Eval)   │
  (真实市场截面真值数据)     └────────────────────┬─────────────────────┘
                                                  │ AssertionOutcome (逐项求值结果)
                                                  ▼
                             ┌──────────────────────────────────────────┐
                             │ 5.2 证伪优先裁决引擎 (Falsification-First)│
                             │ • Step A: invalidation 触发 -> FALSIFIED │
                             │ • Step B: 关键数据缺失 -> INCONCLUSIVE   │
                             │ • Step C: 预期断言符合 -> CONFIRMED      │
                             └────────────────────┬─────────────────────┘
                                                  │ HypothesisAdjudicationResult
                                                  ▼
                             ┌──────────────────────────────────────────┐
                             │ 5.3 双时点快照对撞流水线 (ValidationPipeline)
                             │ • 四维时间契约校验 (T_realization > T_dec) │
                             │ • 密码学全血缘关联 (Hash & Provenance)    │
                             └────────────────────┬─────────────────────┘
                                                  │
                                                  ▼
                             ┌──────────────────────────────────────────┐
                             │ 5.4 只追加验证账本 (CognitionValidationRecord)
                             │ • WORM 零侵入 (绝对不修改原 cognition_record)│
                             │ • 验证状态机流转 (PENDING -> 终局状态)    │
                             └──────────────────────────────────────────┘
```

---

## 二、 刚性工程约束与不变式清单

在 Step 5 的全过程实施中，必须严格恪守以下 6 项刚性不变量：

1. **Falsification-First 原则 (C-01)**:
   证伪断言（`invalidation_assertions`）拥有最高优先仲裁权。只要任一证伪断言触发，假说即刻被无情判定为 `FALSIFIED`，严禁被任何预期断言覆盖或稀释；
2. **Missing != False 铁律 (防 Zero-Fill)**:
   当真实市场切片中关键字段为 `TIMEOUT`、`MISSING` 或标的集合无法提取时，断言结果必须被判定为 `INCONCLUSIVE`（依据策略），严禁填充默认值 0 或将其静默解释为断言失败/通过；
3. **C-02 隔离不变量 (物理不改事前哈希)**:
   事后提取的实际数据快照、逐项断言求值结果、验证状态流转，必须与事前冻结的 `MarketHypothesisDefinition` 和 `hypothesis_hash` 严格物理隔离；
4. **WORM 存储不可侵犯**:
   绝不执行任何针对 `cognition_record` 的 `UPDATE` 操作。所有核验结果必须作为新的记录行写入只追加的 `cognition_validation_record` 账本；
5. **Zero LLM / Zero Trading 刚性红线**:
   纯确定性算法求值，严禁调用 LLM 运行时，严禁触碰交易接口、账户或订单系统；
6. **IEEE-754 临界精度安全**:
   浮点数比对采用 `math.isclose` 与 `1e-9` 容差，彻底防范由于浮点数表示误差引起的断言抖动。

---

## 三、 Step 5 工序拆解与实施路线图

Step 5 分为 5 个原子工序，逐层受控推进：

```text
Step 5.1: 收窄 AST 解释执行器 (Narrowed AST Evaluator)
  ├── 恢复并标准化 AssertionEvaluator (从 scratch 导入并强化)
  ├── 标的池解析: ALL_A / LADDER_HIGH_SPEC / SECTOR / CUSTOM_LIST
  ├── 单层平铺过滤: FilterCondition 与 StructuredFilter
  ├── 聚合计算: COUNT / MEAN / MEDIAN / MAX / MIN / SUM / NONE
  ├── 临界操作符判定: GT / GTE / LT / LTE / EQ / NE / BETWEEN / IN
  └── 空集与缺失策略: MissingDataPolicy 严格响应

Step 5.2: 证伪优先裁决引擎 (Falsification-First Adjudication Engine)
  ├── 实现 FalsificationEngine 与 HypothesisAdjudicationResult (frozen=True)
  ├── 证伪前置判定: 遍历 invalidation_assertions，遇 True 即判 FALSIFIED
  ├── 缺失数据判定: 遇不可用核心数据判 INCONCLUSIVE
  └── 预期断言符合: 遍历 expected_assertions，按 AND/OR 判定 CONFIRMED / UNCONFIRMED

Step 5.3: 双时点真实截面对撞流水线 (Dual-Timestamp Validation Pipeline)
  ├── 搭建 DualTimestampValidationPipeline
  ├── 时域校验: 严格验证 T_realization > T_decision，防范未来函数与时空倒流
  └── 证据链组装: 将真实快照指标、逐项断言状态、最终假说结论装配为完整证据包

Step 5.4: 只追加验证账本与状态机 (Append-Only Validation Ledger & State Machine)
  ├── 定义 CognitionValidationRecord 领域值对象与持久化契约
  ├── 建立对 cognition_record_id 与 hypothesis_hash 的密码学外键指向
  └── 验证状态机流转: PENDING -> CONFIRMED / FALSIFIED / UNCONFIRMED / INCONCLUSIVE

Step 5.5: 端到端极限场景测试与 AST 架构静态扫描
  ├── 7 大极限场景冷启动验证 (CS-H01 ~ CS-H07)
  ├── 100 次确定性重复验证
  └── AST 静态架构扫描防线扩充 (扫描 hypothesis 模块零 LLM/零交易/零网络泄漏)
```

---

## 四、 7 大极限测试场景定义 (CS-H01 ~ CS-H07)

| 场景编号 | 场景名称 | 输入特征 | 预期裁决结果 | 核心验证点 |
| :--- | :--- | :--- | :--- | :--- |
| **CS-H01** | 全量符合预期 | `expected_assertions` 全部满足，`invalidation` 未触发 | `CONFIRMED` | 正常预期验证通路 |
| **CS-H02** | 证伪优先短路 | `expected` 全部满足，但任一 `invalidation` 触发 | `FALSIFIED` | **Falsification-First 铁律** |
| **CS-H03** | 关键数据缺失 | 真实快照中核心字段缺失或标记为 TIMEOUT | `INCONCLUSIVE` | **Missing != False，零填充防御** |
| **CS-H04** | 过滤标的池为空 | 结构化过滤后匹配股票数为 0 | COUNT 为 0.0，数值聚合为 INCONCLUSIVE | 空集合语义确定性分层 |
| **CS-H05** | 浮点临界边界 | 实际指标落在目标阈值 $10^{-7} \sim 10^{-9}$ 边界上 | 精确判别与 `math.isclose` 一致 | 防范 IEEE-754 精度抖动 |
| **CS-H06** | 语法越界防御 | 断言中包含非法字段、嵌套子查询或 SQL 片段 | 抛出 `AssertionSyntaxError` | 收窄 AST 语法白名单刚性封锁 |
| **CS-H07** | C-02 隔离与 WORM | 执行全量验证并输出验证记录 | 原假说定义哈希不变，WORM 不被侵犯 | 密码学血缘闭环与账本隔离 |

---

## 五、 产物清单与交付计划

### 5.1 代码交付物清册
1. `backend/app/cognition/hypothesis/evaluator.py`: 收窄 AST 解释执行器与语法检验器；
2. `backend/app/cognition/hypothesis/falsification.py`: 证伪优先裁决引擎；
3. `backend/app/cognition/hypothesis/pipeline.py`: 双时点对撞与验证流水线；
4. `backend/app/cognition/hypothesis/ledger.py`: 只追加验证记录值对象与状态机；
5. `backend/tests/test_cognition_step5_evaluator.py`: AST 求值器原子测试；
6. `backend/tests/test_cognition_step5_falsification.py`: 证伪引擎与逻辑组合测试；
7. `backend/tests/test_cognition_step5_assembly.py`: 7 大极限场景与全链路组装测试；
8. 更新 `backend/tests/test_cognition_static_architecture_scan.py`: 覆盖 Step 5 模块。

### 5.2 实施步骤与预估进度
- 阶段一: 5.1 解释执行器与 5.2 证伪引擎纯函数实现与单测 (预计 1 工时)
- 阶段二: 5.3 双时点流水线与 5.4 只追加账本实现 (预计 1 工时)
- 阶段三: 5.5 端到端极限装配、AST 扫描与全量 120+ 回归测试 (预计 1 工时)
- 阶段四: 编制《Phase 2A Step 5 实施完成报告与证伪闭环验收单》

---

## 六、 提请董事会授权事项

工程团队提请董事会审议本规划，并签署授权令：
1. **批准《PLAN-PHASE2A-STEP5-20261001》作为 Phase 2A Step 5 的法定实施依据**；
2. **授权启动 Sub-Step 5.1 与 5.2 的代码实施与测试编写**；
3. **重申执行纯沙箱实现（Pure Sandbox），严禁 LLM Runtime 与 Trading 泄漏**。
