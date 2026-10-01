# Cognition Phase 2A 架构与数据契约冻结决议与实施约束单

> **决议编号**：`BOARD-DECISION-20260930-01`  
> **决议日期**：2026-09-30  
> **裁决机构**：最高董事会（用户）  
> **执行机构**：Antigravity 主开发、独立红队特使兼基线审查官、独立质量发布闸门裁判  
> **上位依据**：  
> - 《开发文档/01-项目决策基线（G0-正式版）.md》  
> - 《开发文档/02-G1需求基线（正式冻结版）.md》  
> - 《开发文档/04-G3架构与详细设计（正式版）.md》  
> - 《开发文档/10-项目多Agent四权分立工程治理规范.md》  
> - 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》（版本：v1.2.1-FINAL-CLOSURE）

---

## 一、 最高董事会正式裁决：A — FREEZE（正式冻结）

最高董事会正式签署里程碑架构冻结令：  
> **《Cognition Phase 2A 架构与数据契约》正式通过三轮深度红队审查，核心概念完成重大架构跃迁，审计验真算法、假说定义隔离、收窄断言 DSL、创世并发串行化等关键漏洞全面实现闭环，正式予以裁决：`A — FREEZE`（冻结基线，准予进入实施阶段）！**

### 核心架构跃迁定性
本决议标志着本系统彻底终结了“将状态计算器误当认知系统”的初级阶段，正式完成了从被动打分器到独立认知实体的跨越：

```text
【跃迁前 (v0.2.0 现状)】：
M1 ~ M5 ──→ D1 ~ D6 加权计算 ──→ MarketState ──→ (声称为 Cognition)

【跃迁后 (Phase 2A 冻结基线)】：
M1 ~ M5 (底层物理事实账本)
   │
   ▼
Immutable Observation Snapshot (事实投影切片)
   │
   ▼
MarketState Snapshot (六维物理测量切片)
   │
   ▼
Effective Inference Input (真实生效推理输入保全)
   │
   ▼
LLM Cognition (主体结构化推导与因果论证)
   │
   ▼
Structured Cognition (核心论点、事实依据、自我置信度)
   │
   ▼
Hypothesis Definition Projection (假说定义投影，与运行态物理隔离)
   │
   ▼
Hypothesis Definition Hash ──→ Hypothesis Set Hash
   │
   ▼
Canonical Payload Hash (RFC 8785 JCS 全要素规范化覆盖)
   │
   ▼
Record Hash Chain (结合 chain_state 实现单向排他 Gapless 链式溯源)
   │
   ▼
Machine Verification (收窄 AST 断言求值器，证伪优先，INCONCLUSIVE 零伪造)
   │
   ▼
Cognition Feedback (反思沉淀与经验修正)
```

---

## 二、 冻结边界与实施自主性划分

为避免教条主义并确保工程实施的高效落地，最高董事会严正界定**“法定冻结边界”**与**“实施自主性空间”**：

```text
                    ┌────────────────────────────────────────┐
                    │      Architecture & Contract Freeze    │
                    │               v1.2.1-FINAL             │
                    └───────────────────┬────────────────────┘
                                        │
                ┌───────────────────────┴────────────────────────┐
                ▼                                                ▼
     【法定冻结：绝对不可擅改】                       【实施自主：主开发受控落地】
                │                                                │
       CognitionRecord 聚合根                           Ledger Verifier 具体编码
       “四可”科学闭环原则                               Assertion Executor AST 解析
       RFC 8785 / JCS 哈希链体系                        Missing-data 语义求值
       Hypothesis 假说定义隔离                          DB 级 WORM / Trigger 实现
       全要素只读输入快照                               Prompt/Model 工件表 Migration
       收窄白名单断言 DSL                               事务并发排他锁实现
       四维时间语义契约                                 AC-01 ~ AC-13 自动化测试用例
       Phase 2A / 2B 阶段边界                           ORM / Service 代码模块划分
```

---

## 三、 法定冻结的 12 项刚性实施约束（12 Implementation Invariants）

在进入 Phase 2A 代码实现阶段，主开发（Implementer）必须将以下 12 条约束作为不可逾越的红线：

1. **v1.2.1 架构基线不可擅改（Strict Baseline Invariance）**：
   所有表结构字段命名、哈希计算公式、状态机流转必须严格对齐《28-设计单 v1.2.1》规范，严禁私自变更或偷工减料；
2. **CognitionRecord 为唯一 Aggregate Root**：
   认知推演的所有要素必须通过 `CognitionRecord` 聚合，严禁出现游离于认知账本之外的孤立假说或无主快照；
3. **所有事实输入必须 Snapshot（只读快照隔离）**：
   推演过程严禁动态读取可能变动的业务表，必须在触发时刻将 `ObservationSnapshot` 与 `MarketStateSnapshot` 固化为只读切片；
4. **Hypothesis 定义与验证运行态物理隔离（Definition Projection Invariant）**：
   `status`、`actual_data_snapshot`、`verification_outcome` 等后验运行态字段绝对严禁参与 `hypothesis_hash` 与 `hypothesis_set_hash` 计算，严禁后验结果反向污染原始认知账本；
5. **哈希规范化严格遵循 RFC 8785 (JCS)**：
   参与审计的 JSON 序列化必须通过官方 RFC 8785 兼容的规范化处理，严禁自创第二套序列化规则；
6. **Genesis 必须经过 `chain_state` 串行化（Gapless Monotonic Sequence）**：
   通过 `cognition_chain_state` 单行控制表与排他锁，绝对保证 `sequence_id` 从 1 开始单调连续无空洞，彻底消灭创世竞态；
7. **必须同时实现单记录验真与全账本验真**：
   完整实现第 8.5 节规定的 16 步《全链路审计验真算法》，提供单条记录完整性验真端点与全链连续性巡检能力；
8. **Assertion Executor 必须实现明确的 missing-data semantics**：
   断言求值时若数据缺失，默认强制判定为 `INCONCLUSIVE`，严守零填充防伪铁律；
9. **WORM 必须落实到 DB / Trigger / API 三层守卫**：
   物理表严禁暴露任何 `UPDATE` / `DELETE` 接口，数据库层实施防篡改拦截；
10. **AC-01 ~ AC-13 必须形成自动化验收证据**：
    13 项验收标准必须全部转化为可自动化执行的测试脚本，生成结构化断言日志；
11. **Phase 2A 绝对不实现 Replay / Diff Engine**：
    Replay 与 Cognition Diff 严格封存在 Phase 2B，Phase 2A 聚焦于打牢不可变认知账本底座；
12. **严格遵守既有基线，严禁自行修改 G0/G1/G3**：
    保持项目历史设计基线的神圣性与追溯一致性。

---

## 四、 主开发实施授权清单（Implementation Freedom）

在严格遵守上述 12 项刚性约束的前提下，最高董事会正式向主开发（Antigravity）授予以下工程实施自主权：

* **ORM 与数据库技术栈**：自主采用 SQLAlchemy 2.0 Async 模式与 SQLite/PostgreSQL 驱动，设计清晰的模型继承结构；
* **Repository 与服务分层**：自主设计 `CognitionRepository`、`AuditVerificationService`、`HypothesisAssertionExecutor` 等工程模块；
* **Alembic Schema Migration**：自主规划并执行表结构创建与 `chain_state` 创世行初始化脚本；
* **测试套件架构**：自主组织 `tests/test_cognition_phase2a/` 目录结构，设计包括攻击性测试、篡改模拟测试与并发写入测试在内的完整测试矩阵。

---

## 五、 Phase 2A 标准工程实施路线图（6 步闭环）

按照多 Agent 四权分立工程规范，后续受控实施分为 6 个可验证工序：

```text
┌────────────────────────────────────────────────────────┐
│ Step 1: 物理存储与 WORM 底座                           │
│ • 表结构创建与 Migration (cognition_record, spec, state)│
│ • chain_state 单行创世初始化                           │
│ • 数据访问层只读/追加拦截保障                          │
├────────────────────────────────────────────────────────┤
│ Step 2: RFC 8785 规范化与 Hash Chain 引擎              │
│ • JCS Canonical 序列化工具库引入与测试向量校验          │
│ • 链尾排他串行化入账事务 (Single-Writer Protocol)       │
│ • 16 步只读验真引擎 (Audit Verification Engine)        │
├────────────────────────────────────────────────────────┤
│ Step 3: 事实投影抽取与 Effective Input 渲染器          │
│ • M1~M5 事实数据投影抽取 (ObservationSnapshot)         │
│ • 数据质量警示注入与 EffectiveInferenceInput 渲染全文保全│
├────────────────────────────────────────────────────────┤
│ Step 4: 假说定义投影与收窄 AST 断言执行器              │
│ • HypothesisDefinitionProjection 抽取与集合指纹计算    │
│ • 收窄 AST (StructuredFilter) 机器求值器实现 (证伪优先) │
├────────────────────────────────────────────────────────┤
│ Step 5: 验证状态机与双时点对撞闭环                     │
│ • 四维时间契约对齐 (09:15 / 09:30 锁死)                │
│ • 自动验证状态机 (CONFIRMED / FALSIFIED / INCONCLUSIVE)│
├────────────────────────────────────────────────────────┤
│ Step 6: AC-01 ~ AC-13 自动化测试与红队验收证据链        │
│ • 覆盖全量 13 项硬指标的端到端自动化测试                │
│ • 提交独立红队执行基线审查与攻击对抗                   │
└────────────────────────────────────────────────────────┘
```

---

## 六、 决议生效与执行令

本决议自最高董事会签发时刻起**即刻生效**。
主开发获准在本地环境受控开启 Phase 2A 工程实施。各 Agent 必须恪守权责边界，捍卫认知账本不可篡改性！
