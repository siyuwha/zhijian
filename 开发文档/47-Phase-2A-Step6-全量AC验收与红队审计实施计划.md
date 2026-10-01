# Phase 2A Step 6: 全量 AC 验收与红队审计实施计划
**文档编号**: `PLAN-PHASE2A-STEP6-20261001`  
**实施项目**: Phase 2A Step 6 — AC-01 ~ AC-13 自动化测试与红队验收证据链  
**上位依据**:  
1. 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》v1.2.1-FINAL (第8.2节 13项硬指标)  
2. 《开发文档/29-Cognition-Phase2A架构公约与实施契约.md》  
**实施目标**: 针对 Phase 2A 全链路（Step 1 ~ Step 5）构建端到端自动化综合验收与红队对抗审计证据链  
**当前状态**: **IN PROGRESS / 正在实施**  

---

## 一、 Step 6 实施使命与终局定位

Phase 2A 前 5 个工序已完成全部代码实施与单元测试：
- **Step 1**: WORM 物理存储与 SQLite 触发器底座（`CLOSED`）
- **Step 2**: Track A 生产就绪度与多源容灾降级（`CLOSED`）
- **Step 3**: 事实规范投影、P0 闸门、EffectiveInput 全链路装配（`CLOSED`）
- **Step 4**: 假说定义投影、收窄 AST Schema、JCS 指纹引擎与 C-02 隔离契约（`CLOSED`）
- **Step 5**: 收窄 AST 解释执行器、证伪优先裁决、双时点对撞流水线与只追加验证账本（`COMPLETED`）

**Step 6 的终局使命**：
不再新增业务模型代码，而是作为**独立的验收与红队审计层**，建立全量 **AC-01 ~ AC-13 硬指标自动化测试** 与 **红队对抗穿透测试（Red-Team Attacks）**，形成不可辩驳的闭环验收证据链，完成 Phase 2A 的全系统终审封口。

---

## 二、 AC-01 ~ AC-13 全量硬指标验收映射表

| 指标编号 | 指标名称 | 核心判决标准 | 验证测试用例 | 否决等级 |
| :--- | :--- | :--- | :--- | :--- |
| **AC-01** | **认知不可变性** | 调用修改或删除 `cognition_record` 接口，系统直接抛出 405/403 或 SQL 异常；严禁暴露 Update/Delete 接口 | `test_ac_01_cognition_immutability` | **一票否决** |
| **AC-02** | **自包含可审计性** | 单条 CognitionRecord 配合其引用的不可变工件，能 100% 无损还原当时推演上下文，无悬空失效引用 | `test_ac_02_self_contained_auditability` | **一票否决** |
| **AC-03** | **Prompt 规格 WORM** | 修改已发布 Prompt 模板任一字符，系统自动计算全新 `prompt_hash`，旧 Hash 记录严格保持只读 | `test_ac_03_prompt_spec_worm` | **一票否决** |
| **AC-04** | **生效推理输入保全** | `rendered_system_prompt` 与 `rendered_user_prompt` 全文留存，`effective_input_hash` 与数据库记录 100% 一致 | `test_ac_04_effective_inference_input_preservation` | **一票否决** |
| **AC-05** | **机器断言 DSL 约束** | 假说必须包含白名单 AST（`StructuredFilter` 结构）；`invalidation_assertions` 必须由强类型操作符和数值构成；模糊口号强制拦截 | `test_ac_05_machine_assertion_dsl_constraint` | **一票否决** |
| **AC-06** | **验证状态机自愈** | 在历史数据回放中，竞价触碰红线准确跃迁为 `FALSIFIED`；数据缺失时客观断言 `INCONCLUSIVE`，**绝无偷填 0** | `test_ac_06_validation_state_machine_and_no_zero_fill` | **一票否决** |
| **AC-07** | **确定性重放标记** | 契约支持重放新记录 `parent_cognition_id` 指向原记录，并打上 `deterministic_level` 标签 | `test_ac_07_deterministic_replay_tagging` | **规范对齐** |
| **AC-08** | **差异结果对照矩阵** | 输出 Observation、Reasoning、Hypothesis 与事实验证对照矩阵，严禁存在 winner 评选 | `test_ac_08_diff_comparison_matrix_contract` | **规范对齐** |
| **AC-09** | **降级输入显式透传** | 当 M1~M5 为 `PARTIAL` 时，`ObservationSnapshot` 显式记录 `degraded_fields`，且渲染输入中带有安全约束与数据隔离 | `test_ac_09_degraded_input_explicit_quarantine` | **一票否决** |
| **AC-10** | **全链路验真算法达标** | 运行验真算法，修改快照、输入、输出、推导或假说定义中任意字段，校验器在 T1/T2 威胁模型下 100% 识别篡改 | `test_ac_10_full_chain_tamper_detection` | **一票否决** |
| **AC-11** | **时钟锁死防作弊** | 假说锁定时间必须在目标时间窗口开启之前；时序倒流（$T_{realization} < T_{decision}$）被物理拒绝 | `test_ac_11_clock_freeze_and_time_continuity` | **一票否决** |
| **AC-12** | **生产代码零侵入** | 纯沙箱实现；生产交易系统代码修改量与数据库 Migration 严格保持为 0 | `test_ac_12_zero_production_trading_and_migration` | **一票否决** |
| **AC-13** | **时间语义四维对齐** | 记录中物理字段明确区分 `market_event_time`、`observation_window`、`data_snapshot_time` 与 `verification_execute_time` | `test_ac_13_four_dimensional_time_semantics` | **必须满足** |

---

## 三、 红队对抗渗透测试矩阵 (Red-Team Attacks)

针对结构化认知系统的薄弱环节，设计 6 类红队攻击场景：

1. **RT-01 (WORM 穿透攻击)**: 尝试绕过 ORM 直接向 SQLite 执行原生 SQL `UPDATE/DELETE cognition_record`，验证数据库底层触发器能否 100% 熔断；
2. **RT-02 (收窄 AST 注入攻击)**: 尝试在指标名称中注入 SQL 片段（`DROP TABLE`）、在过滤字段注入非法列名、在操作符中传入未知表达式，验证 AST 白名单解析器能否 100% 拦截并抛出 `AssertionSyntaxError`；
3. **RT-03 (假零填充绕过攻击)**: 构造包含 `TIMEOUT`、`MISSING` 或空集合的极端切片，验证断言执行器是否能坚守 `Missing != False` 铁律，100% 杜绝输出伪 `0.0` 或伪 `PASSED`；
4. **RT-04 (时空倒流与抢跑攻击)**: 模拟偷看未来数据的抢跑假说，传入 $T_{realization} < T_{decision}$ 或试图在开盘后修改 09:15 的早盘假说，验证时序校验器能否 100% 拦截；
5. **RT-05 (雪崩哈希篡改攻击)**: 针对已冻结的假说、事实快照、有效输入进行单比特修改（如将 2.0 改为 2.000000000001 或微调一个标的），验证 RFC 8785 JCS SHA-256 检验算法能否 100% 捕获哈希雪崩并报警；
6. **RT-06 (重放与覆盖攻击)**: 尝试向 `AppendOnlyValidationLedger` 重复写入相同 `validation_id` 的记录，验证只追加账本能否 100% 拦截原地覆写。

---

## 四、 实施交付物清单

1. `backend/tests/test_cognition_step6_ac_and_red_team.py`:
   - 包含 AC-01 ~ AC-13 的 13 项硬指标端到端全量测试；
   - 包含 RT-01 ~ RT-06 的 6 项红队穿透对抗测试；
2. `开发文档/48-Phase-2A-Step6-终局验收与红队审计总报告.md`:
   - 汇集全量 140+ 项测试执行结果；
   - 形成 Phase 2A 最终封口单据。
