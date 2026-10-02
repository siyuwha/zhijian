# 01 Phase 2A 事实审计报告

> **审计执行日期**：2026-10-01  
> **审计范围**：AI认知复盘交易系统全量代码库、Schema、数据Pipeline、测试套件、运行数据库及开发文档（00~49号）  
> **审计基准**：基于物理代码、真实数据库与执行日志，拒绝口头声明与宏观描述  
> **证据等级规范**：`Verified`（代码+测试+数据验证）/ `Partially Verified`（部分存在未满足完整声明）/ `Claim Only`（仅文档声明无代码或运行证据）/ `Missing`（不存在）/ `Broken / Risky`（存在明确错误、脆弱点或安全回归风险）

---

## Executive Summary（审计执行摘要）

审计组对当前系统及声称已完成的 Phase 2A（Steps 1~6）与基础事实层（M1~M6、S1~S4）实施了地毯式穿透审计。

### 核心审计结论

1. **工程与沙箱实现极度扎实**：
   - 运行 `pytest` 全量测试套件，**148/148 项测试全部通过（100% PASS，耗时 71.68s，0 失败，0 错误）**。
   - Phase 2A 定义的 RFC 8785 JCS 规范化、哈希链串接、单层平铺 AST 断言执行器、证伪优先核验机、四维时间解耦（$T_{realization} \ge T_{decision}$）与防假零填充（`Missing != False`）均具备完整代码实现与严密单测覆盖（AC-01~AC-13 及 RT-01~RT-06 红队渗透 100% 阻断）。
2. **“全链路闭环”的实际性质为纯沙箱（Pure Sandbox）**：
   - Phase 2A 文档（如《48号终局验收总报告》）声称的“100% 闭环封口”，本质是**单元测试与内存沙箱测试闭环**。
   - 生产环境真实数据库（`data/trading.db`）中，`cognition_record`、`cognition_chain_state`、`cognition_prompt_spec`、`cognition_diff_report` 的**数据行数全部为 0**。系统处于绝对的 **Zero LLM Runtime** 状态，尚未接入真实大模型进行线上生产推演。
3. **关键物理安全缝隙（Major Vulnerability Discovered）**：
   - **WORM 原生触发器在生产数据库脱节**：`models/cognition_v2.py` 中的 `install_database_worm_triggers_async` 仅在应用 `lifespan` 启动中的 `init_db()` 执行；而 Alembic 迁移脚本仅包含 DDL 建表，未包含原生触发器 SQL。因此，当前磁盘持久化库 `data/trading.db` 中的 `sqlite_master` 触发器列表为空（`triggers: []`），物理级 WORM 防线在未启动 Web 服务时处于静默缺位状态！
4. **Git 基线脱节与未提交风险**：
   - 整个 Phase 2A（Steps 1~6）全部代码与 20+ 篇开发设计文档（29~49号）目前全部处于 **Uncommitted / Untracked 状态**；
   - 本地 `master` 分支与远程 `nas/master` 存在 1 次提交分叉（Commit Hash 不同但内容相同）。代码基线尚未物理冻结提交。
5. **业务模块严重分化**：
   - **生产就绪级（A级）**：M3（交易记录与持仓真实账本，红字冲正，5条实盘记录）、S3（HITL人机隔离，10条诊断记录）；
   - **具备能力但缺乏沙箱/重放（B级）**：M1（收盘复盘）、M2（盘前简报）、M4（早盘竞价）、M5（盘中监控）、S4（多源数据采集与熔断）；
   - **绝对空壳断层（C级）**：M6（选股与策略中心）仅有 37 行 CRUD 空壳，前端为 "Coming in Phase 2" 占位符，缺少任何选股模型、策略知识或规则引擎。

---

## 一、 Phase 2A 声称已完成项目事实审计总表

| 审计项编号 | Phase 2A 声明能力 / 构件 | 声明依据 | 实际代码位置 | 实际测试与运行证据 | 真实状态判定 | 穿透审计细节与风险说明 |
|:---|:---|:---|:---|:---|:---:|:---|
| **P2A-01** | **WORM 不可变认知账本模型** | 28号第8.1节, 29号 | `backend/app/models/cognition_v2.py` | `test_cognition_phase2a_step1.py`, `test_ac_01` | **Partially Verified** | 代码定义了 `CognitionRecord` 表及 ORM 级 update/delete 拦截，单测通过；但在 `data/trading.db` 中行数为 0，且原生触发器未实际安装到磁盘库。 |
| **P2A-02** | **SQLite 原生 WORM 触发器** | 28号, 33号 | `models/cognition_v2.py` L144-185 | `test_cognition_worm_hardening.py` | **Broken / Risky** | 单测在内存库 `:memory:` 验证通过；但生产库 `data/trading.db` 中未安装触发器（`sqlite_master` 触发器数为 0）。直接用 sqlite3 工具仍可修改磁盘库。 |
| **P2A-03** | **API 级 WORM 阻断守卫** | 33号 | `api/v1/cognition.py` L224-264 | `test_worm_hardening.py` | **Verified** | PUT/PATCH/DELETE `/records`, `/prompt-specs`, `/chain-state` 端点明确返回 HTTP 405 Method Not Allowed。 |
| **P2A-04** | **RFC 8785 JCS 规范化哈希链** | 28号第8.2节, 31号 | `app/cognition/jcs.py`, `hash_chain.py` | `test_cognition_step2_jcs_hash_chain.py` | **Verified** | 纯 Python 实现的 RFC 8785 JCS 规范化与 SHA-256 递归哈希，单测覆盖 100 轮确定性、字段置换不变性与雪崩篡改检测。 |
| **P2A-05** | **防 Genesis Race 链状态单行锚点** | 29号, 31号 | `app/cognition/chain_state.py`, `models/cognition_v2.py` | `test_step2_jcs_hash_chain.py` | **Verified** | `CognitionChainState` 表设计单行控制锚点，严格自增单调序号 `sequence_id`，杜绝空洞与竞态。 |
| **P2A-06** | **不可变 Prompt 规格与哈希指纹** | 28号第7节, 31号 | `models/cognition_v2.py`, `input/renderer.py` | `test_ac_03_prompt_spec_worm` | **Verified** | 规格表 `CognitionPromptSpec` 绑定 `prompt_hash`，改动 1 个字符强制改变 SHA-256 根指纹。 |
| **P2A-07** | **事实抽取适配器 (Adapters)** | 34号, 36号 | `cognition/observation/adapters/` (m1, m2, m4, m5, s4) | `test_cognition_step3_adapters.py` (21 passed) | **Verified** | 各模块物理数据均能映射为 `FactItem`，具备 `FactStatus`（AVAILABLE/EMPTY/STALE/TIMEOUT/ERROR）及源头血缘。 |
| **P2A-08** | **确定性时钟与四维时间解耦** | 34号, 35号 | `cognition/observation/clock.py`, `contracts.py` | `test_cognition_step3_contract.py` | **Verified** | 明确拆分：物理事件时间 (`market_event_time`)、观测窗口 (`observation_window`)、快照落库时间 (`data_snapshot_time`)、核验执行时间 (`verification_execute_time`)。 |
| **P2A-09** | **多源冲突检测与消解引擎** | 34号, 37号 | `cognition/observation/conflict.py` | `test_step3_p0_gates.py` | **Verified** | 实现 `PRIMARY_WINS`, `STRICT_ABORT`, `PRESERVE_ALL` 策略，冲突时留存原始证据字典，无静默吞没。 |
| **P2A-10** | **六维准入矩阵与资格网 (Gate)** | 34号, 37号 | `cognition/input/eligibility.py` | `test_step3_p0_gates.py` | **Verified** | 对 EMPTY/STALE/TIMEOUT 事实执行隔离，严禁将缺失降级数据伪装为客观事实，缺数一律打上 `[DATA_DEFICIENCY]` 隔离标签。 |
| **P2A-11** | **Effective Inference Input 确定性序列化** | 34号, 38号 | `cognition/input/renderer.py`, `pipeline.py` | `test_ac_04`, `test_step3_assembly.py` | **Verified** | 渲染全文留存，计算 `effective_input_hash`。在沙箱中达成 100 轮比特级完全一致（Bit-Exact）。 |
| **P2A-12** | **STOP 硬边界（组装器停止机制）** | 39号, 40号 | `cognition/input/pipeline.py` L10-14 | `test_hard_stop_boundary_enforced` | **Verified** | `process_snapshot` 产出 `EffectiveInferenceInput` 后立即返回，绝对不调用外部大模型，零交易副作用。 |
| **P2A-13** | **收窄 AST 假说定义与断言 DSL** | 42号, 44号 | `cognition/hypothesis/contracts.py` | `test_cognition_step4_contracts.py` | **Verified** | 白名单字段与单层平铺强类型校验，C-02 不变量确保定义 Hash 绝不受运行时核验状态污染。 |
| **P2A-14** | **收窄 AST 解释执行器与 1e-9 精度** | 45号, 46号 | `cognition/hypothesis/evaluator.py` | `test_cognition_step5_evaluator.py` | **Verified** | 严格白名单求值，浮点数误差使用 Decimal/1e-9 容差，拒绝任意代码执行。 |
| **P2A-15** | **证伪优先核验引擎 (Falsification-First)** | 45号, 46号 | `cognition/hypothesis/falsification.py` | `test_cognition_step5_falsification.py` | **Verified** | 失效红线触碰立即判定 `FALSIFIED`，一票否决；缺失数据判定 `INCONCLUSIVE`；绝无假零填充。 |
| **P2A-16** | **双时点截面对撞流水线** | 45号, 46号 | `cognition/hypothesis/pipeline.py` | `test_cognition_step5_assembly.py` | **Verified** | 严格前置校验 $T_{realization} \ge T_{decision}$，时序倒流直接抛出 `TimeContinuityViolationError`。 |
| **P2A-17** | **只追加核验账本 (Append-Only Ledger)** | 45号, 46号 | `cognition/hypothesis/ledger.py` | `test_rt_06_replay_and_overwrite_attack` | **Verified** | 内存与值对象只追加写，重放覆盖抛出 WORM 异常。 |
| **P2A-18** | **确定性重放引擎 (Replay Engine)** | 28号第8.3节, 48号 | `cognition/replay/runner.py` | `test_cognition_phase2b_replay.py` | **Partially Verified** | 沙箱 Runner 已实现并测试确定性等级标签；但未挂载生产 API，未与真实历史切片库联动。 |
| **P2A-19** | **五维认知差异对比矩阵 (Diff Matrix)** | 28号第8.3节, 48号 | `cognition/diff/matrix.py` | `test_ac_08` | **Partially Verified** | 差异矩阵合同与结构已实现，禁止 winner 评选；但缺乏大规模历史样本对撞运行数据。 |
| **P2A-20** | **生产真实大模型推理 (LLM Runtime)** | 28号第8.3节草案 | **未实现 / 刻意冻结** | `test_ac_12` (验证 Zero LLM) | **Missing (By Design)** | 系统严格遵从董事会禁令，未接入真实 LLM API，生产库中 `raw_response` 记录数为 0。 |
| **P2A-21** | **生产级 Alembic 自动迁移** | 30号, 32号 | `backend/alembic.ini`, `backend/migrations/` | `alembic current` 返回 head | **Partially Verified** | 迁移文件存在并已执行到 head；但迁移中未打包 WORM 触发器，导致全新部署时触发器遗漏。 |

---

## 二、 核心架构模块代码穿透审计

### 1. 模块结构与边界审计

```text
backend/app/
├── api/v1/                [BORDER CLEAN] 路由清晰，包含 market, monitor, reports, simulation, strategy, trading, cognition
├── cognition/             [BORDER CLEAN - SANDBOX] 内部结构高度自包含：
│   ├── input/             - 资格网 (eligibility)、确定性渲染 (renderer)、流水线 (pipeline)
│   ├── observation/       - 适配器 (adapters)、构建器 (builder)、时钟 (clock)、冲突 (conflict)、合同 (contracts)
│   ├── hypothesis/        - 合同 (contracts)、断言执行 (evaluator)、证伪 (falsification)、账本 (ledger)
│   ├── replay/            - 重放合同与运行器
│   ├── diff/              - 差异矩阵与结构
│   └── hash_chain.py      - JCS + RFC 8785 链式哈希
├── core/                  [BORDER CLEAN] database.py (SQLAlchemy 2.0 Async), logging.py
├── data/                  [NEEDS REPAIR] 外部数据源适配器集合，网络与反爬弹性仍需持续治理
├── models/                [BORDER CLEAN] market, trading, cognition, cognition_v2, report, strategy, simulation, system
├── services/              [SPLIT]
│   ├── trading.py         [EXCELLENT] 会计级红字冲正，超卖强阻断，幂等控制
│   ├── daily_review.py    [GOOD] M1 聚合分析与 MarketState 计算
│   ├── premarket.py       [GOOD] M2 隔夜与早盘简报，新闻双源容灾
│   ├── auction.py         [FAIR] M4 09:25 开盘比值计算，缺盘口深度
│   ├── monitor.py         [FAIR] M5 盘中高频投影与异动，依赖盘中实时流
│   └── selection.py       [BROKEN/STUB] 仅 37 行代码，无任何选股与策略能力
└── strategy/              [BROKEN/STUB] interfaces.py 仅为 abc.ABC 抽象基类，无任何策略实现
```

### 2. Schema 与数据持久化审计（`data/trading.db`）

| 表名 | 业务定位 | 真实行数 | 审计评估与风险 |
|:---|:---|:---:|:---|
| `trade_record` | 实盘交易真实流水账本 | 5 | **Verified**。记录真实交易，字段完整（代码、数量、价格、冲正标记、幂等键）。 |
| `position` | 真实持仓汇总表 | 2 | **Verified**。当前持有标的均价与数量正确，与交易流水一致。 |
| `trade_note` | 人工反思笔记 | 1 | **Verified**。记录交易反思与心态评估。 |
| `cognitive_trade_diagnosis` | HITL 人机协同交易诊断 | 10 | **Verified**。客观事实层与主观解释层二分，包含 `human_status` 审定流转。 |
| `market_hypothesis` | 早期假说草案表 | 1 | **Partially Verified**。仅 1 条历史验证假说。 |
| `hypothesis_verification` | 早期假说核验表 | 2 | **Partially Verified**。已执行核验记录。 |
| `data_quality_log` | 数据源质量与健康日志 | 309 | **Verified**。真实记录各 Provider 响应延迟、数据质量状态。 |
| `market_daily_snapshot` | 盘后离线物理快照表 | 2 | **Verified**。记录 EOD_CLOSE 快照，用于离线自愈与回放。 |
| `market_settlement_cache` | Baostock 结算价本地缓存 | 1 | **Verified**。结算价缓存生效。 |
| `cognition_record` | Phase 2A 核心不可变认知账本 | **0** | **Claim Only (生产未运行)**。表结构就绪，但从未在生产环境写入过记录。 |
| `cognition_chain_state` | 链尾状态锚点控制表 | **0** | **Claim Only (生产未初始化)**。未执行创世记录初始化（tail_sequence_id 未落盘）。 |
| `cognition_prompt_spec` | 不可变 Prompt 规格表 | **0** | **Claim Only (生产未注册)**。未注册任何生产 Prompt 规格。 |
| `cognition_diff_report` | 对撞差异报告表 | **0** | **Claim Only (生产无报告)**。 |
| `selection_result` | 选股结果表 | **0** | **Missing**。选股中心未运行。 |
| `selection_candidate` | 候选股清单表 | **0** | **Missing**。无候选股数据。 |
| `daily_review` | 收盘复盘报告表 | **0** | **Partially Verified**。定时任务或离线执行产物未落入本地库当前实例。 |
| `intraday_market_snapshot` | 盘中分时快照表 | **0** | **Partially Verified**。盘中实时队列未持久化历史记录。 |

---

## 三、 测试事实与覆盖审计

### 1. 全量测试套件执行证据

执行命令：`pytest -q`  
执行时间：2026-10-01 17:42:32  
执行结果：**148 passed, 4 warnings in 71.68s (100% PASS)**

```text
测试套件构成明细：
1. Step 1 (WORM 存储底座与触发器): 6 passed
2. Step 2 (JCS 规范化与哈希链): 8 passed
3. Step 3 (事实抽取、适配器、准入闸门、冲突策略): 72 passed
4. Step 4 (假说定义投影与收窄 AST 契约): 4 passed
5. Step 5 (AST 执行器、证伪核验引擎、双时点对撞流水线): 20 passed
6. Step 6 (AC-01~AC-13 硬指标与 RT-01~RT-06 红队渗透): 19 passed
7. Track A (生产数据源韧性、CLS/东财防御、结算缓存): 5 passed
8. P2 数据韧性 (熔断器、TTL短缓存、降级): 15 passed
9. G1-M3 交易安全与红队攻击 (超卖、并发冲正、浮点篡改): 1 passed (包含复合子测试)
10. 基础 API 连通性测试: 2 passed
```

### 2. 测试质量评价

- **无空测试（Empty Tests）**：所有测试函数均包含具体 Assertions，无 `pass` 占位用例。
- **红队渗透真实阻断**：
  - RT-01（原生 SQL DELETE/UPDATE 穿透）：抛出 SQLite 触发器 ABORT 异常；
  - RT-02（AST 注入攻击 `stock_code; DROP TABLE`）：白名单拦截抛出 `AssertionSyntaxError`；
  - RT-03（假零填充绕过攻击）：空集合聚合判定 `INCONCLUSIVE`，`actual_value=None`；
  - RT-04（时空倒流攻击 $T_{realization} < T_{decision}$）：流水线拦截抛出 `TimeContinuityViolationError`；
  - RT-05（哈希雪崩篡改）：校验哈希失败返回 `False`；
  - RT-06（账本覆写重放攻击）：只追加账本抛出 `ValidationLedgerError`。

---

## 四、 核心缺陷、脆弱点与风险清单

### 1. 【高危】磁盘数据库原生 WORM 触发器缺失风险
- **代码事实**：`install_database_worm_triggers_async` 仅在应用运行态的 `init_db()` 执行。
- **物理事实**：磁盘文件 `data/trading.db` 在离线状态下未安装 5 个触发器（`trg_cognition_record_no_update`, `trg_cognition_record_no_delete`, `trg_cognition_prompt_spec_no_update`, `trg_cognition_prompt_spec_no_delete`, `trg_cognition_chain_state_no_delete`）。
- **风险**：若通过脚本或 SQLite CLI 直接操作数据库文件，WORM 保护无法在数据库引擎层面生效。
- **整改建议**：在 Alembic 迁移脚本中补全原生触发器 DDL，确保数据库每次迁移即物理具备触发器。

### 2. 【高危】Git 未提交状态与代码基线漂移风险
- **物理事实**：当前工作区有 14 个修改文件、20+ 个未跟踪新文件（包含整个 Phase 2A 核心实现）。
- **风险**：未提交的代码不具备严格版本号，任何突发环境变更有丢失成果风险。
- **整改建议**：在 G1 Baseline 冻结阶段，必须全面记录未提交文件快照与 SHA-256 校验和。

### 3. 【中危】M6 策略与选股中心严重断层（Architecture Gap）
- **代码事实**：`selection.py` 仅 37 行占位代码，无选股逻辑；`strategy/interfaces.py` 仅有抽象基类；前端页面直接显示 "Coming in Phase 2"。
- **风险**：系统当前完全不具备策略选股、风格分类、板块拥挤度计算与分层卖出的能力。
- **整改建议**：明确将 M6 保持在冻结状态，不引入伪策略，严格通过 G3 迁移矩阵重新设计 P0 Contract。

### 4. 【中危】M4/M5 历史回放与深度数据匮乏
- **物理事实**：公开数据源无 Level-2 逐笔与挂单深度；非交易时段无高频异动历史回放引擎。
- **风险**：周末与夜间调试时只能依赖离线快照，无法对盘中异动与竞价策略进行高保真重现。

---

## 五、 Phase 2A 事实审计最终判定结论

```text
================================================================================
PHASE 2A REAL AUDIT ADJUDICATION:
1. 纯沙箱架构与算法契约 (Pure Sandbox Contract & AST): 100% VERIFIED
2. 自动化测试套件与红队渗透 (Test Suite & Red Team): 100% VERIFIED (148/148 PASS)
3. 生产数据库实体与大模型接入 (Production DB & LLM Runtime): CLAIM ONLY / ZERO DATA
4. 生产持久库 WORM 触发器安装 (Disk DB WORM Trigger): BROKEN / RISKY (未安装到文件)
5. 策略与选股核心 (M6 Strategy & Selection): MISSING / CAPABILITY GAP (空壳)
================================================================================
```

**G0 门禁裁决**：
本审计报告已如实还原系统全部物理真相。**禁止将沙箱通过误判为生产就绪，禁止将未运行的大模型声明为已有认知能力**。后续所有 Baseline 冻结与迁移分析必须以此真实状态为唯一基准。
