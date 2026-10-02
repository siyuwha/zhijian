# 02 候选 Baseline 清单 (Candidate Baseline)

> **基线状态**：**候选 Baseline（Candidate Baseline）**（根据 G5.1 审计裁决，在代码、文档、迁移、测试环境和证据形成可重放的原子提交并推送到 NAS 之前，本基线保持“候选”状态，严禁声明最终冻结）  
> **基线代号**：`CANDIDATE-BASELINE-PRE-P0-20261001-ALPHA`  
> **基准日期**：2026-10-01  
> **候选基线目的**：固化当前工程、Schema、契约、测试与运行状态，作为后续任何 G5.1 整改与 P0 增强方案的唯一比对参照物与回归判定基准。

---

## 一、 代码版本与提交标识

### 1. Git 状态与版本标识
- **当前 HEAD Commit**：`c52d1c8` (`feat(version): upgrade system to v0.2.0 with engineering dynamic versioning`)
- **系统动态版本探针**：`v0.2.0`（`STAGE_NAME = "P2 生产运行版"`，构建日期 `2026-09-29`）
- **远程分支状态**：
  - 本地 `master` 与远程 `nas/master` (`\\Fn-evo2-xh\项目文件夹\git_repos\AI认知复盘交易系统.git`) 各自存在 1 个分叉提交（`c52d1c8` vs `f012efe`，内容仅在文档 28 的早期版本有差异）。
- **工作区未提交状态（Critical Baseline Fact）**：
  - **修改文件（14 个）**：`backend/app/api/v1/cognition.py`, `backend/app/core/database.py`, `backend/app/data/capabilities.py`, `backend/app/data/providers/__init__.py`, `baostock_provider.py`, `cls.py`, `eastmoney.py`, `sina.py`, `backend/app/models/__init__.py`, `market.py`, `backend/app/services/auction.py`, `daily_review.py`, `pytest.ini`, `开发文档/28-...md`。
  - **未跟踪新文件（核心构件 25+ 项）**：`backend/alembic.ini`, `backend/migrations/`, `backend/app/cognition/` (全量子目录), `backend/app/models/cognition_v2.py`, `backend/tests/` (13 个 Phase 2A 专项测试文件), `开发文档/29~49号`。
  - **证据留存**：详见 `baseline_evidence/git_status_and_diff_stat.txt`。

---

## 二、 Schema 版本与物理表基线

### 1. Alembic 迁移版本
- **当前迁移 Head**：`d440da877b6a` (`p2_track_a_and_cognition_phase2a_baseline`)
- **迁移特性**：开启 `render_as_batch=True`（SQLite 兼容模式）
- **证据留存**：详见 `baseline_evidence/alembic_history.txt`。

### 2. 数据库物理表清单（`data/trading.db`，共 24 张业务与控制表）

| 表名 | 字段数 | 真实数据行数 | 核心主键与唯一索引 | 状态 |
|:---|:---:|:---:|:---|:---:|
| `trade_record` | 14 | 5 | `id` (PK), `idempotency_key` | 生产有效 (M3真实账本) |
| `position` | 11 | 2 | `id` (PK), `code` (UQ) | 生产有效 (当前持仓) |
| `trade_note` | 9 | 1 | `id` (PK), `trade_id` | 生产有效 (反思笔记) |
| `cognitive_trade_diagnosis` | 18 | 10 | `id` (PK), `trade_id` | 生产有效 (S3人机协同) |
| `market_hypothesis` | 12 | 1 | `id` (PK) | 历史验证记录 |
| `hypothesis_verification` | 9 | 2 | `id` (PK), `(hypothesis_id, stage)` (UQ) | 历史核验记录 |
| `market_settlement_cache` | 15 | 1 | `id` (PK), `(code, date)` (UQ) | 缓存生效 |
| `market_daily_snapshot` | 13 | 2 | `id` (PK), `(date, snapshot_type)` (UQ) | EOD快照生效 |
| `data_quality_log` | 8 | 309 | `id` (PK) | 持续记录中 |
| `cognition_record` | 33 | 0 | `id` (PK), `sequence_id` (UQ), `record_hash` (UQ) | 空表 (Phase 2A 沙箱) |
| `cognition_chain_state` | 4 | 0 | `chain_id` (PK) | 空表 (未初始化创世行) |
| `cognition_prompt_spec` | 8 | 0 | `id` (PK), `prompt_hash` (UQ) | 空表 |
| `cognition_diff_report` | 6 | 0 | `id` (PK) | 空表 |
| `daily_review` | 9 | 0 | `id` (PK), `date` (UQ) | 历史报告实例未导入 |
| `premarket_briefing` | 9 | 0 | `id` (PK), `date` (UQ) | 历史报告实例未导入 |
| `auction_report` | 10 | 0 | `id` (PK), `date` (UQ) | 历史报告实例未导入 |
| `intraday_market_snapshot` | 20 | 0 | `id` (PK), `(date, minute_index)` | 历史分时未持久化 |
| `intraday_anomaly_event` | 15 | 0 | `id` (PK) | 历史事件未持久化 |
| `selection_result` | 7 | 0 | `id` (PK) | 选股中心空置 |
| `selection_candidate` | 8 | 0 | `id` (PK) | 选股中心空置 |
| `strategy` | 7 | 0 | `id` (PK) | 选股中心空置 |
| `sim_account` | 7 | 0 | `id` (PK) | 模拟盘空置 |
| `sim_position` | 9 | 0 | `id` (PK) | 模拟盘空置 |
| `sim_trade` | 12 | 0 | `id` (PK) | 模拟盘空置 |

- **证据留存**：全量字段类型与索引快照见 `baseline_evidence/db_schema_snapshot.json`。

---

## 三、 关键 Contract 与契约接口基线

### 1. 物理事实与观测快照契约（`Observation Contract`）
- **实体**：`CanonicalFact`, `FactItem`, `FactStatus`, `ObservationSnapshot`, `EffectiveInferenceInput`
- **代码路径**：`backend/app/cognition/observation/contracts.py`
- **规范标准**：
  - 强状态枚举：`AVAILABLE`, `EMPTY`, `STALE`, `TIMEOUT`, `ERROR`；
  - 四维时间字段强制包含：`market_event_time`, `observation_window`, `data_snapshot_time`, `verification_execute_time`；
  - 严禁假 0 填充：缺失值必须为 `None`，并附带缺失血缘。

### 2. 结构化假说与断言 DSL 契约（`Hypothesis & Assertion Contract`）
- **实体**：`MarketHypothesisDefinition`, `AssertionDSL`, `StructuredFilter`, `HypothesisSetProjection`
- **代码路径**：`backend/app/cognition/hypothesis/contracts.py`
- **规范标准**：
  - 白名单操作符：`==, !=, >, >=, <, <=, in, not_in`；
  - 聚合函数：`count, sum, avg, max, min`；
  - 单层平铺 Filter：必须以 `metric_name` 为白名单字段，禁止嵌套执行代码；
  - C-02 不变量：`definition_hash` 使用 RFC 8785 JCS 对定义本身计算 SHA-256，严禁混入运行时状态。

### 3. 不可变认知账本契约（`Cognition Ledger Contract`）
- **实体**：`CognitionRecord`
- **代码路径**：`backend/app/models/cognition_v2.py`
- **规范标准**：
  - 链式前驱：`previous_record_hash` 强约束；
  - 创世规则：第 1 条记录前驱必须为 64 个 `'0'`；
  - 序号自增：`sequence_id` 严格单调递增，无断号无并发空洞；
  - WORM 约束：禁止一切 UPDATE / DELETE。

### 4. 交易事实账本契约（`Trading Truth Ledger Contract`）
- **实体**：`TradeRecord`, `Position`, `TradeNote`
- **代码路径**：`backend/app/models/trading.py`, `services/trading.py`
- **规范标准**：
  - 成交金额服务端强制计算 `price * quantity`；
  - 撤单/修正仅采用追加 `REVERSAL` 会计红字冲正；
  - 超卖 100% 阻断；
  - 60秒幂等键防重。

---

## 四、 自动化测试套件与执行基准

- **测试框架**：`pytest 9.1.1` + `pytest-asyncio` + `Python 3.12.10`
- **测试用例总数**：**148 个**
- **执行结果**：**148 passed, 0 failed, 0 error**
- **全量执行时间**：**71.68 秒**
- **测试覆盖模块与用例数**：
  1. `test_cognition_step3_p0_gates.py`: 18 passed
  2. `test_cognition_step3_contract.py`: 12 passed
  3. `test_cognition_step3_adapters.py`: 21 passed
  4. `test_cognition_step3_assembly.py`: 16 passed
  5. `test_cognition_static_architecture_scan.py`: 6 passed
  6. `test_cognition_step4_contracts.py`: 4 passed
  7. `test_cognition_step5_evaluator.py`: 6 passed
  8. `test_cognition_step5_falsification.py`: 6 passed
  9. `test_cognition_step5_assembly.py`: 7 passed
  10. `test_cognition_step6_ac_and_red_team.py`: 19 passed (AC-01~13, RT-01~06)
  11. `test_cognition_step2_jcs_hash_chain.py`: 8 passed
  12. `test_cognition_phase2a_step1.py`: 6 passed
  13. `test_cognition_worm_hardening.py`: 6 passed
  14. `test_cognition_phase2b_replay.py`: 1 passed
  15. `test_track_a_production_readiness.py`: 5 passed
  16. `test_p2_resilience.py`: 15 passed
  17. `test_red_team_g1_m3_attacks.py`: 1 passed
  18. `test_m14_market_state.py`: 1 passed
  19. `test_cognition_validation.py`: 1 passed
  20. `test_trading.py`: 1 passed
  21. `test_api.py`: 2 passed
- **证据留存**：完整用例树与输出日志详见 `baseline_evidence/pytest_full_run.log`。

---

## 五、 可运行 API 路由与 Pipeline 入口基线

### 1. 核心 Pipeline 入口
- `CognitionObservationPipeline.process_snapshot()`: 事实适配器 → 快照组装 → 冲突策略 → 资格网门禁 → 确定性渲染 → EffectiveInput (带 STOP 边界)
- `DualTimestampValidationPipeline.validate_hypothesis_set()`: 四维时钟校验 → 假说完整性验真 → 证伪优先执行器 → 只追加核验账本 (带 STOP 边界)
- `DailyReviewService.generate_daily_review()`: M1 盘后全链路
- `PremarketService.generate_briefing()`: M2 盘前简报
- `AuctionService.generate_auction_report()`: M4 09:25 集合竞价快照

### 2. FastAPI 挂载端点清单（共 32 个有效路由）
- `/health`, `/version`
- `/api/v1/market/index/daily`, `/limit-up/daily`, `/limit-up/summary`, `/news/recent`
- `/api/v1/monitor/stream`, `/snapshot/latest`, `/anomalies`, `/chart/timeline`
- `/api/v1/reports/daily-review/{date}`, `/premarket-briefing/{date}`, `/auction/{date}`
- `/api/v1/trading/records`, `/positions`, `/orders`, `/correct`, `/notes`
- `/api/v1/cognition/market-state/{date}`, `/config/indicators`, `/diagnosis/trade/{id}`, `/hypotheses`, `/hypotheses/{id}/verify`
- `/api/v1/cognition/records/{id}` (WORM 405 Guard)
- `/api/v1/cognition/prompt-specs/{id}` (WORM 405 Guard)
- `/api/v1/cognition/chain-state/{id}` (WORM 405 Guard)
- **证据留存**：详见 `baseline_evidence/api_routes_snapshot.json`。

---

## 六、 审计结论与基线冻结签署

```text
================================================================================
BASELINE FREEZE CERTIFICATE:
Codebase Snapshot: c52d1c8 + Working Tree Modifications (14 modified, 25 untracked)
Test Suite Pass Rate: 148 / 148 (100.0%)
Active DB Schema: 24 Tables (data/trading.db)
Alembic Version: d440da877b6a (head)
Status: FROZEN FOR P0 ENHANCEMENT ANALYSIS
================================================================================
```
