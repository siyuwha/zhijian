# Observation / M1~M5 上游事实底盘充分性深度审计报告
# (Observation & M1-M5 Fact Foundation Sufficiency Audit Report)

> **报告编号**：`AUDIT-OBS-M1M5-20261003-01`  
> **审计基线**：commit `95d290c` (`v0.2.4-llm-proposer-contract-baseline`, Phase 2B.3 Engineering PASS)  
> **审计日期**：2026-10-03  
> **审计机构**：独立架构安全与质量发布闸门裁判组、Antigravity 核心工程审计组  
> **归档位置**：`开发文档/61-Observation-M1-M5-Fact-Foundation-Audit-Report.md` 与根目录镜像

---

## 目录
1. [Executive Summary（执行摘要与裁决）](#一executive-summary执行摘要与裁决)
2. [Observation 真实定义反向确立](#二observation-真实定义反向确立)
3. [M1~M5 当前实际能力审计清单](#三m1m5-当前实际能力审计清单)
4. [完整 Fact Inventory（事实资产清单）](#四完整-fact-inventory事实资产清单)
5. [Physical Fact / Derived Fact / Cognition 三层严格划分](#五physical-fact--derived-fact--cognition-三层严格划分)
6. [五维事实质量深度审计](#六五维事实质量深度审计)
7. [Temporal Integrity 时态与因果一致性审计](#七temporal-integrity-时态与因果一致性审计)
8. [Relational Integrity 实体关系穿透审计](#八relational-integrity-实体关系穿透审计)
9. [Missingness Semantics 缺失语义严格审计](#九missingness-semantics-缺失语义严格审计)
10. [Provenance 全息血缘与主备回退审计](#十provenance-全息血缘与主备回退审计)
11. [Real Historical Replay 真实历史生产数据回放](#十一real-historical-replay-真实历史生产数据回放)
12. [Observation 实际样本结构切片](#十二observation-实际样本结构切片)
13. [Cognition Coverage Matrix 认知覆盖度矩阵](#十三cognition-coverage-matrix-认知覆盖度矩阵)
14. [Fact Gaps 事实缺陷与断层清单](#十四fact-gaps-事实缺陷与断层清单)
15. [Architecture Risks 架构系统性风险](#十五architecture-risks-架构系统性风险)
16. [Mock / Production Gap 单元测试与生产真实鸿沟](#十六mock--production-gap-单元测试与生产真实鸿沟)
17. [当前能力边界定性（Cognition 到底知道了什么？）](#十七当前能力边界定性cognition-到底知道了什么)
18. [是否需要 M1~M5 返工判定](#十八是否需要-m1m5-返工判定)
19. [Observation Sufficiency Gate 终审门禁裁决](#十九observation-sufficiency-gate-终审门禁裁决)
20. [后续工程演进建议](#二十后续工程演进建议)

---

## 一、Executive Summary（执行摘要与裁决）

当前项目已顺利完成 Phase 2B.1（最小证伪闭环）、Phase 2B.2（受约束 LLM 假说沙盒试炼）与 Phase 2B.3（前端三卡片可视化与只读收口补丁），测试套件达到 186 项 100% 通过，物理库零污染守卫固若金汤。

然而，在即将迈入 Cognition Layer 深层能力拓展（如板块轮动、主线梯队、高标博弈、多标的证伪）的重大分水岭前，审计组贯彻**“以真实代码为准、以真实数据为准、以可追溯事实为准”**的最高铁律，对上游事实底盘（M1~M5、S4）实施了地毯式独立审计与 NAS 生产数据库（1.19MB 真实库）穿透核验。

### 1. 核心审计发现
1. **认知管道通畅，但管道流淌的事实严重“贫血”**：
   - 现有系统验证了“Cognition 闭环框架”是可行的，但当前运转完全依赖于一个**极度收窄的宏观标量微型子集**：4 个指数收盘点位（上证、深成、创业、科创）与 1 个全市场虚拟聚合标的（`ALL_A` 的涨跌停数、涨跌家数、连板高度）。
2. **个股与板块事实在认知层全面缺席**：
   - 虽然底层生产库抓取了部分个股（M5 异动、M3 真实持仓）以及涨停池明细（`items`），但在 Cognition 摄入流水线与 AST 解释执行器中，**行业板块事实覆盖率为 0%，个股实体关联度为 0%**。所有个股均无法作为证伪标的，所有板块假说在求值器中均会被抛入空集合。
3. **重大键名错配缺陷（Schema Key Mismatch）**：
   - 底层收盘快照 `MarketDailySnapshot` 中保存的涨停池个股列表键名为 `"items"`（共 52 只明细）；但事实适配器 `M1ReviewFactAdapter` 却硬编码读取 `"pool"`。此缺陷导致**生产环境下 `M1ReviewFactAdapter` 将全部 52 只涨停股判定为“池为空（EMPTY）”，抹杀了所有个股事实明细**。
4. **M4 早盘竞价高标事实常态化缺省**：
   - 真实生产数据库回放显示，`auction_report.high_open_stats` 的 `tested_count` 在全部历史交易日中均为 `0`，`【6板高标数据缺省】`。AI 无法核验任何高标开盘溢价。
5. **M5 盘中高频时序与异动事实与 Cognition 完全脱钩**：
   - M5 拥有 189 条盘中 5 分钟快照与 152 条异动事件，但 Cognition 层为 M5 设计的适配器 `M5SettlementFactAdapter` 仅用于对接尚未运行的 Baostock 结算价缓存（当前生产库为 0 条），导致**盘中宝贵的微观量价与异动事实从未输入给 Cognition**。

### 2. 最终门禁裁决

```text
================================================================================
          OBSERVATION / M1-M5 SUFFICIENCY GATE AUDIT ADJUDICATION
================================================================================
  [宏观全A/指数标量认知]   ->  🟢 PASS WITH GAPS (在严格限制于 ALL_A 范围下准入)
  [中观板块/微观个股认知]   ->  🔴 BLOCK (事实断层，刚性禁止启动深层假说)
================================================================================
```

---

## 二、Observation 真实定义反向确立

基于代码库实现、数据库 Schema、API 路由、适配器流水线及测试事实，对 `Observation` 的真实定义进行反向确立：

### 1. 真实定义属性
`Observation` **不是**单一数据库表，**不是** AI 推理得出的结论，也**不是**简单的 DTO。  
**它是：跨 M1~M5 上游事实模块、在严格物理时变时间窗口（Window）内对客观交易市场状态的不可变结构化切片与事实装配体（Fact Assembly & Canonical Contract）。**

| 属性 | 实际代码落地与工程实现 |
|:---|:---|
| **Definition** | 不可变值对象，记录指定交易日、指定交易时段的客观多源物理事实项（`FactItem`）集合，严禁带有买卖倾向与观点解释。 |
| **Lifecycle** | `Physical World Event` → `Provider (S4/M1~M5)` → `Adapter Extraction` → `Deep Detachment` → `Quality Aggregation` → `JCS Canonical Fingerprinting` → `WORM Ledger Anchor / Pipeline Consumer` |
| **Producer** | - 适配器层：[`M1ReviewFactAdapter`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/adapters/m1_adapter.py)<br>- 构建器：[`ObservationSnapshotBuilder`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/builder.py) |
| **Consumer** | - 准入网：[`FactEligibilityGate`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/input/eligibility.py)<br>- 认知流水线：[`CognitionObservationPipeline`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/input/pipeline.py)<br>- 证伪引擎适配器：[`HypothesisServiceAdapter`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/hypothesis/service_adapter.py)<br>- 统一复盘服务：[`CognitionReviewService`](file:///d:/项目库/AI认知复盘交易系统/backend/app/services/cognition_review.py) |
| **Schema** | [`backend/app/cognition/observation/contracts.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/contracts.py) 中的 `ObservationSnapshot` (Pydantic v2, `frozen=True, extra="forbid"`) |
| **Identity** | `snapshot_id`: 形如 `obs_20260930_POST_CLOSE` 或 `obs_628382a3f17e`，由确定性时钟生成并与 `market_date` + `stage` 强绑定。 |
| **Timestamp** | 严格实施四维时间解耦（`FourDimensionalTime`）：`event_time` (物理发生), `observed_time` (内存抓取), `ingestion_time` (落库), `effective_time` (业务生效)。 |
| **Provenance** | `Provenance` 模型：记录 `primary_source`、主备切换痕迹 `fallback_occurred`、`trace_id`、重复与冲突原貌记录 `ConflictRecord`。 |
| **Hash / Identity** | 遵循 RFC 8785 JSON Canonicalization Scheme (JCS)，按 `fact_key` UTF-16 字典序排列，生成 SHA-256 `snapshot_fingerprint`。 |

---

## 三、M1~M5 当前实际能力审计清单

本节对 M1、M2、M3、M4、M5 进行逐一穿透，严格区分**“设计上宣称具备的能力”**与**“当前代码及真实生产库中实际表现的能力”**。

### 1. M1: 盘后复盘系统 (Post-Close Review)
- **当前职责**：收盘后 15:30 抽取指数收盘、市场量能与涨跌家数、涨停池统计、六维市场状态 D1~D6 打分。
- **实际代码入口**：[`backend/app/services/daily_review.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/services/daily_review.py) 与 [`backend/app/cognition/observation/adapters/m1_adapter.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/adapters/m1_adapter.py)
- **数据源**：Eastmoney (东方财富) 公开接口、Sina (新浪) 兜底。
- **原始输入**：HTTP GET 返回的 JSON 串及文本。
- **输出事实**：
  - 4 只宽基指数收盘价、涨跌幅、成交额（`sh000001`, `sz399001`, `sz399006`, `sh000688`）
  - 全市场广度：总成交额（亿元）、上涨/下跌/平盘家数
  - 涨停聚合：总涨停数、跌停数、最高连板数、炸板数、炸板率
- **底层 Schema**：`daily_review`, `market_daily_snapshot` (EOD_CLOSE)
- **API**：`GET /api/v1/review/daily/{date}`
- **时间粒度**：日级（Daily），`event_time` 锁定在 `15:00:00`
- **更新频率**：每个交易日收盘后执行 1 次
- **Provenance**：记录 `market_daily_snapshot:EOD_CLOSE` 或 `daily_review`，带 `trace_id`
- **Quality Metadata**：`FULL`, `PARTIAL`, `DEGRADED`, `INVALID`
- **缺失值语义**：严格执行零填充防伪，缺失时保持 `None` 或显式标为 `FactStatus.MISSING`；零涨停标为 `FactStatus.EMPTY`。
- **Hash / Identity**：`fact_fingerprint` 与 `snapshot_fingerprint`
- **是否真实数据**：**真实数据**（来自真实 A 股行情）。
- **是否存在 Mock**：单测中使用手工字典 Mock；生产环境直连真实数据。
- **当前测试方式**：`test_cognition_step3_adapters.py::test_01_m1_adapter_contract`
- **实际限制与断层**：
  1. 严重依赖东财接口，盘后网络超时容易导致 `breadth` 缺失（5 天真实生产数据中有 3 天缺失广度，评级为 PARTIAL/INVALID）；
  2. **代码缺陷**：`m1_adapter.py` 读取 `"pool"` 字段，而真实数据库快照写入的是 `"items"` 字段，导致适配器提取涨停明细池恒为空；
  3. `sector_analysis` 缺乏结构化标准，个股到板块的映射为 None。

### 2. M2: 盘前简报系统 (Premarket Briefing)
- **当前职责**：交易日早晨 08:30~08:45 收集隔夜外盘、宏观资讯快讯，推演今日开盘观察点。
- **实际代码入口**：[`backend/app/services/premarket.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/services/premarket.py) 与 [`backend/app/cognition/observation/adapters/m2_adapter.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/adapters/m2_adapter.py)
- **数据源**：Sina 财经外盘接口、CLS (财联社) 快讯。
- **原始输入**：隔夜期货指数行情、外盘收盘、新闻快讯流。
- **输出事实**：
  - 5 项隔夜标的行情事实（富时 A50、纳指、道琼斯、标普500、恒生指数）
  - 10~20 条宏观新闻标题与摘要（`news_digest`）
- **底层 Schema**：`premarket_briefing`
- **API**：`GET /api/v1/premarket/{date}`
- **时间粒度**：盘前时点，`event_time` 锁定在 `08:30:00`
- **更新频率**：每个交易日早盘执行 1 次
- **Provenance**：记录 `premarket_briefing`，带 `trace_id`
- **Quality Metadata**：无显式单独 Quality 枚举列，仅由上游 S4 状态隐式决定。
- **缺失值语义**：外盘缺失时标为 `FactStatus.MISSING`，新闻列表为空时输出 `FactStatus.EMPTY`。
- **Hash / Identity**：`fact_fingerprint`
- **是否真实数据**：**真实数据**。
- **是否存在 Mock**：单测中使用 Mock。
- **当前测试方式**：`test_cognition_step3_adapters.py::test_02_m2_adapter_contract`
- **实际限制与断层**：
  1. `today_focus` 字段属于系统自动生成的**主观/推演解释型叙述**，并非客观物理事实；
  2. 新闻快讯无任何语义实体标签（无个股代码、无板块关联、无事件分类）。

### 3. M3: 交易记录与持仓管理 (Trading & Position Ledger)
- **当前职责**：提供完全不可变的物理交易记录账本，记录买入/卖出真实流水、持仓状态、红字冲正。
- **实际代码入口**：[`backend/app/services/trading.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/services/trading.py)
- **数据源**：用户真实录入或券商成交凭据。
- **原始输入**：交易动作、标的代码、价格、股数、理由、时间戳。
- **输出事实**：不可变流水表 `trade_record` 与仓位表 `position`。
- **底层 Schema**：`trade_record`, `trade_note`, `position`
- **API**：`POST /api/v1/trading/record`, `GET /api/v1/trading/positions`
- **时间粒度**：秒级（精确到交易发生瞬间）。
- **更新频率**：事件驱动（实时）。
- **Provenance**：具备严格的 `idempotency_key` 与 `reversed_record_id` 审计链条。
- **Quality Metadata**：由 WORM 账本与数据库外键约束保障。
- **缺失值语义**：必填项非空约束；冲正记录保留原单关联。
- **Hash / Identity**：业务主键与幂等键保证唯一性。
- **是否真实数据**：**100% 真实生产交易数据**。
- **是否存在 Mock**：红队攻击测试中使用模拟流水；生产库保留真实用户交易。
- **当前测试方式**：`test_red_team_g1_m3_attacks.py`, `test_trading.py`
- **实际限制与断层**：
  1. M3 是事实性最坚固的模块，但在 Cognition 中仅用于 `CognitiveTradeDiagnosis`（单笔交易事后环境复盘）；
  2. M3 的交易事实未与 M5 的日内分时切片、M4 的早盘竞价做微观因果关联。

### 4. M4: 早盘竞价观察系统 (Morning Auction Observation)
- **当前职责**：09:25:00 集合竞价结束瞬间，抓取两市开盘点位、竞价成交总额、前日连板高标开盘溢价。
- **实际代码入口**：[`backend/app/services/auction.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/services/auction.py) 与 [`backend/app/cognition/observation/adapters/m4_adapter.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/adapters/m4_adapter.py)
- **数据源**：Eastmoney / Sina 早盘 09:25 快照。
- **原始输入**：指数开盘数据、昨日连板池股票开盘价。
- **输出事实**：
  - 4 只宽基指数开盘涨跌幅与点位
  - 两市竞价总额（亿元）及竞价承接比（较昨日全天总成交的比例）
  - 昨日连板高标开盘溢价统计
- **底层 Schema**：`auction_report`, `market_daily_snapshot` (AUCTION_0925)
- **API**：`GET /api/v1/auction/{date}`
- **时间粒度**：时点采样（Point-in-Time），严格锁定在 `09:25:00`
- **更新频率**：每个交易日早盘执行 1 次
- **Provenance**：记录 `market_daily_snapshot:AUCTION_0925` 或 `auction_report`
- **Quality Metadata**：`OFFLINE_INFERRED` 或 `AVAILABLE`
- **缺失值语义**：竞价额缺失标为 `FactStatus.MISSING`，严禁填 0 亿伪造；一字板为 0 时输出合法数值 0。
- **Hash / Identity**：`fact_fingerprint`
- **是否真实数据**：**真实数据**。
- **是否存在 Mock**：单测中使用手工 Mock。
- **当前测试方式**：`test_cognition_step3_adapters.py::test_03_m4_adapter_contract`
- **实际限制与断层**：
  1. **高标数据缺省**：生产库全部 4 个早盘报告中，昨日连板样本池数量均为 0，连板高标开盘溢价率恒为 `--`；
  2. `emotion_judgment` 是基于规则生成的叙事标签，属于推论而非事实。

### 5. M5: 盘中动态异动感知系统 (Intraday Anomaly & Settlement)
- **当前职责**：
  - 职责 A（盘中监控）：盘中每 5 分钟采样宏观量价、W(T) 投影预测、边沿跃迁检测、急速放量/直线拉升异动。
  - 职责 B（结算补偿）：提供标的历史结算收盘价与基准值缓存。
- **实际代码入口**：[`backend/app/services/monitor.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/services/monitor.py) 与 [`backend/app/cognition/observation/adapters/m5_adapter.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/adapters/m5_adapter.py)
- **数据源**：Sina 实时分时流、Baostock 离线收盘数据。
- **原始输入**：盘中分时行情、个股逐笔放量切片。
- **输出事实**：
  - 盘中宏观分时快照（指数涨跌、实时成交、量能投影、涨跌家数）
  - 个股异动事件记录（`event_category`, `symbol`, `surge_ratio` 等）
  - 个股结算价事实（`close`, `prev_close`, `volume`, `amount`）
- **底层 Schema**：`intraday_market_snapshot`, `intraday_anomaly_event`, `market_settlement_cache`
- **API**：`GET /api/v1/monitor/snapshots`, `GET /api/v1/monitor/events`
- **时间粒度**：5 分钟分时切片与秒级异动事件。
- **更新频率**：盘中 09:30~15:00 连续采样。
- **Provenance**：记录 `baostock`、`baostock_local_cache`、`sina_intraday`。
- **Quality Metadata**：`AVAILABLE`, `STALE`, `TIMEOUT`
- **缺失值语义**：09:30~09:45 量能投影冷启动保持 `None`，异动判定冷却期防刷屏。
- **Hash / Identity**：`fact_fingerprint`
- **是否真实数据**：**真实数据**（生产库已累计 189 条快照、152 条异动事件）。
- **是否存在 Mock**：单测中使用 Mock。
- **当前测试方式**：`test_cognition_step3_adapters.py::test_04_m5_adapter_contract`
- **实际限制与断层**：
  1. **与认知层完全脱节**：M5 盘中采集的海量分时快照与异动事件，目前**没有任何一条被接入 `CognitionObservationPipeline`**；
  2. 认知层适配器 `m5_adapter.py` 仅仅读取 `market_settlement_cache`（Baostock 个股结算价），而该表在 NAS 生产库中只有 0 条记录！

---

## 四、完整 Fact Inventory（事实资产清单）

| 事实唯一标识 (`fact_key`) | 物理事实是什么？ (`What`) | 数据源 (`Source`) | 观察时间点 (`When`) | 归属实体 (`Entity`) | 粒度 (`Granularity`) | 血缘追溯 (`Provenance`) | 质量描述 (`Quality`) | 唯一标识依据 (`Identity`) | 可关联事实 (`Relation`) | 认知可信证据 (`Evidence`) |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---:|
| `indices.sh000001` | 上证指数收盘点位、涨跌幅、成交额 | M1 (Eastmoney) | T日 15:00:00 | 上证指数 | 日终标量 | URL/API 原始响应 + trace_id | FULL / PARTIAL | 指数代码 + 日期 | `indices.*`, `breadth.summary` | **可用 (A级)** |
| `indices.sz399001` | 深证成指收盘点位、涨跌幅、成交额 | M1 (Eastmoney) | T日 15:00:00 | 深证成指 | 日终标量 | URL/API 原始响应 + trace_id | FULL / PARTIAL | 指数代码 + 日期 | `indices.*`, `breadth.summary` | **可用 (A级)** |
| `indices.sz399006` | 创业板指收盘点位、涨跌幅、成交额 | M1 (Eastmoney) | T日 15:00:00 | 创业板指 | 日终标量 | URL/API 原始响应 + trace_id | FULL / PARTIAL | 指数代码 + 日期 | `indices.*`, `breadth.summary` | **可用 (A级)** |
| `indices.sh000688` | 科创50收盘点位、涨跌幅、成交额 | M1 (Eastmoney) | T日 15:00:00 | 科创50 | 日终标量 | URL/API 原始响应 + trace_id | FULL / PARTIAL | 指数代码 + 日期 | `indices.*`, `breadth.summary` | **可用 (A级)** |
| `breadth.summary` | 全市场总成交额、上涨/下跌/平盘家数 | M1 (Eastmoney) | T日 15:00:00 | 全A市场 | 市场宏观聚合 | URL/API 原始响应 + trace_id | 易受盘后超时影响降级 | 事实键名 + 日期 | `indices.*`, `limit_up.pool` | **部分可用 (B级)** |
| `limit_up.summary` | 全市场涨跌停数、连板高度、炸板数 | M1 (Eastmoney) | T日 15:00:00 | 全A投机生态 | 市场宏观聚合 | URL/API 原始响应 + trace_id | 稳定 | 事实键名 + 日期 | `breadth.summary` | **可用 (A级)** |
| `limit_up.pool` (明细) | 涨停个股代码、封板时间、连板天数、板块 | M1 (Eastmoney) | T日 15:00:00 | 涨停标的列表 | 个股集合切片 | 存在字段读取错配 bug | **不可用 (当前提取为空)** | 股票代码 + 日期 | 板块、个股成交 | **阻断 (需修复)** |
| `macro.overnight` | 5 项主要外盘与期货点位及涨跌 | M2 (Sina) | T日 08:30:00 | 外盘宽基/商品 | 盘前标量 | Sina 接口 + trace_id | 稳定 | 标的代码 + 日期 | `indices.*` | **可用 (A级)** |
| `macro.news` | 滚动财经快讯标题与发布时间 | S4 (CLS/Sina) | 实时发布 | 宏观/资讯 | 文本流切片 | 双源主备全息血缘记录 | 文本未结构化 | 资讯ID / 时间戳 | 无实体映射 | **仅供定性参考** |
| `auction.indices` | 09:25:00 开盘指数点位与开盘涨跌幅 | M4 (Eastmoney) | T日 09:25:00 | 宽基指数 | 时点标量 | 竞价快照 + trace_id | 稳定 | 指数代码 + 时点 | `indices.*` | **可用 (A级)** |
| `auction.volume` | 两市集合竞价成交额及承接比值 | M4 (Eastmoney) | T日 09:25:00 | 全A竞价额 | 时点标量 | 竞价快照 + trace_id | 稳定 | 时点 + 日期 | `breadth.summary` | **可用 (A级)** |
| `auction.high_tier` | 昨日高标开盘溢价、高开率、一字板数 | M4 (Eastmoney) | T日 09:25:00 | 昨日高标池 | 标的集合统计 | 真实生产库无昨日样本 | **缺省 (值为 None/0)** | 事实键名 + 日期 | `limit_up.summary` | **不可用 (缺数)** |
| `intraday.series` | 盘中 5 分钟宏观量价、W(T) 投影 | M5 (Sina) | 09:30~15:00 | 市场分时 | 5分钟时间序列 | Sina 分时流 + trace_id | 生产库有数据但未接认知 | minute_index + 日期 | `indices.*` | **未接通 (断层)** |
| `intraday.anomaly` | 盘中异动标的急速放量、拉升冲击 | M5 (Sina) | 盘中秒级 | 异动个股 | 事件流水 | 异动检测器 + 冷却期记录 | 生产库有数据但未接认知 | 事件ID + 时间戳 | 对应股票代码 | **未接通 (断层)** |
| `trading.record` | 用户真实成交方向、价格、数量、理由 | M3 (Ledger) | 交易物理时间 | 交易流水 | 逐笔交易事件 | 幂等键 + WORM 不可变账本 | 极高 (生产核心) | trade_id / idempotency | 持仓、当日 D1~D6 | **可用 (A级)** |
| `settlement.price` | 个股历史结算收盘价、复权因子 | M5 (Baostock) | T日 15:30:00 | 个股 | 日级标量 | Baostock 历史缓存 | 生产库为 0 条 | 股票代码 + 日期 | 交易记录核算 | **未激活** |

---

## 五、Physical Fact / Derived Fact / Cognition 三层严格划分

本审计报告对系统中所有数据项进行严谨的三层定性，严防推论伪装成物理事实：

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                             COGNITION LAYER (认知层)                        │
│ - MarketHypothesis (命题、前置逻辑、预期形态、证伪红线)                      │
│ - CognitiveTradeDiagnosis (环境匹配类型、逻辑兑现判定、认知差距反思)        │
│ - FalsificationEngine 裁决结果 (CONFIRMED, FALSIFIED, INCONCLUSIVE)         │
│ - EMD / LRD / ODD 认知样本分布统计与进化偏置分析                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                          DERIVED FACT LAYER (衍生推导事实)                  │
│ - D1~D6 市场状态打分 (加权综合分 composite_score、定性状态 state_label)     │
│ - M5 W(T) 全天量能投影预测 (volume_proj_yi，带有 ESTIMATED 标记)            │
│ - M4 emotion_judgment (开盘情绪定性标签，如“极端地量避险观望”)               │
│ - M2 today_focus (盘前推演重点分析)                                         │
│ - 连板高度 (board_height)、炸板率 (broken_ratio)、竞价承接比 (bidding_ratio) │
├─────────────────────────────────────────────────────────────────────────────┤
│                         PHYSICAL FACT LAYER (客观物理事实)                  │
│ - 指数及个股实时成交价 (close, price, open, high, low)                      │
│ - 成交量与成交金额 (volume, amount_wan, total_amount_yi)                    │
│ - 涨停封单金额、封板时点 (fbt)、涨停家数、跌停家数、上涨/下跌家数           │
│ - 真实成交委托记录 (trade_record: buy/sell, 股数, 成交时间戳)              │
│ - 外部新闻原始文本与发布时间戳 (market_news: publish_time, title)          │
└─────────────────────────────────────────────────────────────────────────────┘
```

> **审计警告（Architecture Debt）**：  
> 在先前的 UI 与 DTO 设计中，`state_label`（如“平稳中性”、“放量高开偏强承接”）常与指数收盘点位并列展示。审计要求必须在 Schema 与 UI 上严格进行视觉与元数据隔离，**严禁将包含算法权重的 Derived Fact 混为 Physical Fact 呈现**！

---

## 六、五维事实质量深度审计

### 1. Coverage（事实覆盖度）：**严重不足 (25/100)**
- **宏观大盘**：覆盖充分（4 宽基指数 + 成交总额 + 涨跌统计）。
- **行业中观**：**覆盖度为 0%**。无板块涨跌幅排位，无行业资金流向，无题材轮动关系。
- **微观个股**：**覆盖度接近 0%**。除 M3 录入的 4 只持仓个股与 M5 抓取的未连通异动个股外，全市场 5000+ 个股行情在 Cognition 输入端无法访问。
- **高标与连板梯队**：仅有单一标量数字（`max_height: 7`），但梯队分布（首板、二板、高标名称）在 Cognition 输入切片中全部断裂。

### 2. Fidelity（真实性与保真度）：**中等偏高 (75/100)**
- 凡是进入数据库的数值，公式与口径均准确，未发现单位错乱（万与亿在核心代码中严格区分）；
- 严格遵循零填充防伪，缺失指标保持 `None`，未发现将缺失数据篡改为 `0` 的欺诈行为。
- **缺陷**：由于 M1 适配器 `"pool"` vs `"items"` 键名不一致，导致高保真的真实涨停明细在进入 ObservationSnapshot 时丢失。

### 3. Temporal Integrity（时间一致性）：**良好但存在盘后伪时点风险 (70/100)**
- 建立了四维时间解耦（`FourDimensionalTime`），严格区分物理事件时间与入库时间；
- 实现了 `target_date <= market_date` 刚性时间因果守卫（HTTP 400 阻断穿越）；
- **风险**：在盘后生成 `MarketDailySnapshot` 时，由于非交易时段抓取，部分第三方接口返回的是前日缓存或修正后数据，容易导致盘前、盘中与盘后时态混淆。

### 4. Relational Integrity（实体关联性）：**极度匮乏 (10/100)**
- 见第八节专项穿透，系统缺乏实体关系图谱（Entity Graph），各模块如同孤岛。

### 5. Missingness Semantics（缺失语义）：**优秀 (90/100)**
- 实现了系统级的 `FactStatus`（七态）与 AST `MissingDataPolicy`（三态），彻底落实了 `Missing != False` 与 `Missing != 0` 的科学哲学原则。

---

## 七、Temporal Integrity 时态与因果一致性审计

时态审计着重排查是否存在“未来函数”、“时间倒挂”与“时点冒充”。

| 场景 / 事实 | 声称事件时点 (`event_time`) | 实际抓取时点 (`observed_time`) | 入库落盘时点 (`ingestion_time`) | 业务生效时点 (`effective_time`) | 时态审计结论 |
|:---|:---|:---|:---|:---|:---|
| **M1 盘后复盘** | `T日 15:00:00` | `T日 15:30:12` (调度运行) | `T日 15:30:14` | `T日 15:00:00` | ✅ **时态合规**。盘后事实锁定于收盘切片。 |
| **M2 盘前宏观** | `T日 08:30:00` | `T日 08:45:00` (调度运行) | `T日 08:45:02` | `T日 08:30:00` | ✅ **时态合规**。外盘数据为隔夜结算。 |
| **M4 早盘竞价** | `T日 09:25:00` | `T日 09:26:01` (调度运行) | `T日 09:26:03` | `T日 09:25:00` | ✅ **时态严格锁定**。严禁用盘中连续竞价冒充开盘。 |
| **M5 盘中分时** | `T日 HH:MM:00` | `T日 HH:MM:05` (轮询采样) | `T日 HH:MM:15` (异步刷盘) | `T日 HH:MM:00` | ⚠️ **存在时间漂移**。网络抖动时采样时间可能延迟 1~2 分钟。 |
| **假说提出时间** | `T日 16:00:00` | `T日 16:00:00` | `T日 16:00:01` | `T+1日 09:25/15:00` | ✅ **强因果守卫**。系统已建立硬编码拦截：`target_date <= market_date` 抛出 HTTP 400，杜绝事后诸葛亮。 |

---

## 八、Relational Integrity 实体关系穿透审计

审计组对系统内预设的 9 大实体关系链条进行了地毯式代码追溯：

| 实体关系链条 | 理论需求与设计设想 | 当前代码与数据库实现现状 | 关系是否连通 | 阻断根因分析 |
|:---|:---|:---|:---:|:---|
| **1. 股票 ↔ 板块** | 输入股票代码能查到其所属申万行业与核心概念板块 | `daily_review.sector_analysis` 为非规范化纯字符串；无 `stock_sector_mapping` 表或字段。 | 🔴 **断裂** | 缺乏个股与板块的静态主数据字典与动态归属表。 |
| **2. 股票 ↔ 涨跌停** | 从涨停事实能关联到具体哪只个股涨停、连板几板 | 快照中有 `items`，但 `m1_adapter.py` 读取 `"pool"` 导致丢失；`HypothesisServiceAdapter` 仅抽取了标量数字。 | 🔴 **断裂** | 键名错配 bug + 假说适配器未下钻至个股数组。 |
| **3. 股票 ↔ 连板高度** | 明确识别当前 7 板最高标是哪只股票（如新华传媒） | M5 快照中有字符串 `'新华传媒(600825) 7连板'`；但 Cognition 输入中无此实体解析。 | 🔴 **断裂** | 仅作为 UI 拼接展示字符串存在，未转化为结构化实体关系。 |
| **4. 股票 ↔ 梯队分布** | 空间板、中位板、首板的完整股票分布矩阵 | 生产数据库无此结构，API 无此字段。 | 🔴 **断裂** | 尚未开发梯队构建算法。 |
| **5. 股票 ↔ 市场阶段** | 某股票属于分歧期龙头还是退潮期补跌标的 | 仅在 M3 人工反思笔记中有文字描述，系统无状态映射。 | 🔴 **断裂** | 属于主观认知推断，无物理事实映射。 |
| **6. 板块 ↔ 市场情绪** | 领涨板块与全市场赚钱效应共振关系 | 仅有 D3 情绪维度加权分，无法下钻到具体板块贡献度。 | 🔴 **断裂** | 板块数据缺失导致无法计算板块情绪。 |
| **7. 市场 ↔ 时间阶段** | 盘前、竞价、盘中、盘后状态单向流转继承 | M1/M2/M4/M5 各自独立生成 report，缺乏统一的上下文管道。 | 🟡 **弱连通** | 仅在 M2 盘前抓取了昨日 M1 复盘作为文本参考。 |
| **8. 事件/新闻 ↔ 股票** | 某条快讯或突发事件精准映射受影响标的 | `market_news` 仅有 `title` 和 `brief`，无 `related_symbols` 列。 | 🔴 **断裂** | 无 NLP 实体抽取或正则映射逻辑。 |
| **9. 事件/新闻 ↔ 板块** | 某产业政策快讯映射到对应受益板块 | 无实体关系映射。 | 🔴 **断裂** | 缺乏事件本体分类与板块映射字典。 |

---

## 九、Missingness Semantics 缺失语义严格审计

根据波普尔科学哲学与系统架构规范，严格审计 8 类缺失语义的落地情况：

| 语义状态 | 业务定义 | 系统实际实现与代码证据 | 是否杜绝假零/假布尔 | 评级 |
|:---|:---|:---|:---:|:---:|
| `AVAILABLE` | 数据源响应正常，字段完备且自洽 | `FactStatus.AVAILABLE` (contracts.py line 18) | 是 | ✅ 优 |
| `EMPTY` | 正常响应但客观事实集为空（如全市场零涨停） | `FactStatus.EMPTY`，`limit_up_count: 0` 但 `status: EMPTY` (m1_adapter.py line 215) | 是 (明确区分零与缺) | ✅ 优 |
| `STALE` | 超时或故障回退读取本地历史快照/缓存 | `Freshness.STALE`，`allow_stale_reference` 契约控制 (contracts.py line 163) | 是 | ✅ 优 |
| `TIMEOUT` | 外部物理网络请求超时（严禁用 0 冒充） | `FactStatus.TIMEOUT`，不填 0 亿，payload 严格为 `None` (m4_adapter.py) | 是 | ✅ 优 |
| `ERROR` | 通道异常、HTTP报错或数据结构损坏 | `FactStatus.ERROR`，记录异常堆栈，整体快照降级 (quality.py) | 是 | ✅ 优 |
| `MISSING` | 预期关键指标物理缺失 | `FactStatus.MISSING`，断言输出 `INCONCLUSIVE` (evaluator.py line 66) | 是 | ✅ 优 |
| `INCONCLUSIVE` | 多源事实冲突不可调和或时序倒挂 | `ConflictEngine.evaluate` 输出 `INCONCLUSIVE` (conflict.py) | 是 | ✅ 优 |
| `NOT_APPLICABLE` | 某些标的在特定规则下不适用（如科创板无一字涨停规则） | AST 中仅有 `SKIP` 策略，尚未细化出 `NOT_APPLICABLE` 显式枚举。 | 存在轻微混合 | ⚠️ 中 |

---

## 十、Provenance 全息血缘与主备回退审计

审计组穿透检查了 S4 与各 Adapter 的血缘追踪机制：

### 1. S4 快讯双源切换血缘证据（`S4NewsFactAdapter`）
- **实现位置**：[`backend/app/cognition/observation/adapters/s4_adapter.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/observation/adapters/s4_adapter.py#L39-L53)
- **血缘追踪**：当 CLS 超时回退 Sina 时，系统显式记录：
  ```python
  fallback_meta = {
      "fallback_occurred": True,
      "primary_source": "cls",
      "fallback_source": "sina",
      "fallback_reason": "HTTP_TIMEOUT_504",
      "primary_error_detail": "Connection to cls.cn timed out after 3000ms"
  }
  ```
- **审计评定**：全息血缘双向保全，严禁静默丢弃主源失败证据，符合董事会决策规范。

### 2. M1/M4 事实血缘
- 每条 `FactItem` 均内嵌 `Provenance(primary_source=..., trace_id=...)`；
- 构建 `ObservationSnapshot` 时附带 `source_manifest`，记录各 Provider 的网络耗时 `latency_ms` 与记录条数 `records_count`。

---

## 十一、Real Historical Replay 真实历史生产数据回放

审计组使用只读方式连接生产数据库（`\\Fn-evo2-xh\Docker\AI-Trading-System\data\trading.db`），对历史上真实存在的 5 个连续交易日执行了现场穿透回放：

```text
================================================================================
                    REAL HISTORICAL REPLAY AUDIT EVIDENCE
================================================================================
```

### 1. 2026-09-26 回放实况
- **M1 DailyReview**：存在 (`id=1`, `generated_at=2026-09-26 06:15:23`)
  - `indices`: 4 项正常 (`sh000001`, `sz399001`, `sz399006`, `sh000688`)
  - `limit_up`: `total_count: 52`, `max_height: 5`
  - `breadth`: **缺失（全市场成交额与涨跌家数为空）**
  - `data_quality`: `invalid`
  - **Cognition 准入判定**：🔴 **REJECT_INVALID_QUALITY**（因关键广度缺失，阻断入账，防止污染主账本）
- **M4 AuctionReport**：存在 (`id=1`)，高标开盘样本数 `tested_count: 0`
- **M5 Intraday**：仅 2 条快照，无异动事件
- **M3 Trades**：0 笔

### 2. 2026-09-28 回放实况
- **M1 DailyReview**：存在 (`id=2`, `data_quality=partial`)
  - `indices`: 4 项正常
  - `limit_up`: `total_count: 33`, `max_height: 5`
  - `breadth`: **缺失**
  - **Cognition 准入判定**：🔴 **REJECT_INVALID_QUALITY**
- **M4 AuctionReport**：存在 (`id=2`)，高标开盘样本数 `tested_count: 0`
- **M5 Intraday**：75 条快照，41 条异动事件（真实运行充分）
- **M3 Trades**：2 笔（真实买入 600165 宁科生物、600699 均胜电子）

### 3. 2026-09-29 回放实况
- **M1 DailyReview**：存在 (`id=3`, `data_quality=PARTIAL`)
  - `indices`: 4 项正常
  - `limit_up`: `total_count: 57`, `max_height: 6`
  - `breadth`: **缺失**
  - **Cognition 准入判定**：🔴 **REJECT_INVALID_QUALITY**
- **M4 AuctionReport**：存在 (`id=3`)，高标开盘样本数 `tested_count: 0`
- **M5 Intraday**：59 条快照，54 条异动事件
- **M3 Trades**：3 笔（买入 002074、卖出 600699、买入 002119）
- **S4 News**：23 条有效财经快讯

### 4. 2026-09-30 回放实况
- **M1 DailyReview**：存在 (`id=4`, `data_quality=PARTIAL`)
  - `indices`: 4 项正常
  - `limit_up`: `total_count: 52`, `max_height: 7`
  - `breadth`: **完备**（上涨 2614，下跌 2841，成交额 16477.2 亿元）
  - **Cognition 准入判定**：🟢 **ADMISSION_PASSED**（成功生成 `cog_20260930_POST_CLOSE_0001`）
- **M4 AuctionReport**：存在 (`id=4`)，高标开盘样本数 `tested_count: 0`
- **M5 Intraday**：49 条快照，57 条异动事件
- **M3 Trades**：0 笔

### 5. 2026-10-01 回放实况（国庆非交易日）
- **M1 DailyReview**：存在 (`id=5`, `data_quality=PARTIAL`)，复用前一日快照
- **M4 AuctionReport**：**物理缺失**
- **M5 Intraday**：0 条
- **Cognition 准入判定**：🟢 **ADMISSION_PASSED**（测试环境模拟准入，生成 `cog_20261001_POST_CLOSE_0002`）

### 6. 回放事实统计汇总
- **回放总交易日**：5 天
- **物理事实完全完备（FULL）天数**：**0 天**
- **部分事实完备（PARTIAL）天数**：**4 天**
- **关键事实损坏（INVALID）天数**：**1 天**
- **个股池（pool）成功提取天数**：**0 天**（受 bug 阻断）
- **行业板块事实提取天数**：**0 天**（全空）
- **高标早盘溢价成功提取天数**：**0 天**（全部缺省）

---

## 十二、Observation 实际样本结构切片

以下为系统在 2026-09-30 收盘生成的**真实 ObservationSnapshot JCS 规范化切片**：

```json
{
  "snapshot_id": "obs_20260930_POST_CLOSE",
  "schema_version": "1.0.0",
  "market_date": "2026-09-30",
  "stage": "POST_CLOSE",
  "observation_window": {
    "window_start": "2026-09-30T09:15:00.000+08:00",
    "window_end": "2026-09-30T15:00:00.000+08:00",
    "window_type": "ACCUMULATIVE_RANGE"
  },
  "snapshot_time": "2026-09-30T15:30:00.000+08:00",
  "overall_quality": "PARTIAL",
  "degraded_fields": [
    "limit_up.pool"
  ],
  "fact_items": [
    {
      "fact_id": "fact_indices_sh000001",
      "fact_key": "indices.sh000001",
      "fact_type": "INDEX_QUOTE",
      "time_context": {
        "event_time": "2026-09-30T15:00:00.000+08:00",
        "observed_time": "2026-09-30T15:30:00.000+08:00",
        "ingestion_time": "2026-09-30T15:30:02.000+08:00",
        "effective_time": "2026-09-30T15:00:00.000+08:00"
      },
      "status": "AVAILABLE",
      "freshness": "REALTIME",
      "source": "market_daily_snapshot:EOD_CLOSE",
      "source_record_id": "1",
      "payload": {
        "amount_wan": 65000000.0,
        "close": 3842.19,
        "code": "sh000001",
        "name": "上证指数",
        "pct_change": 0.31
      },
      "provenance": {
        "fallback_occurred": false,
        "primary_source": "market_daily_snapshot:EOD_CLOSE",
        "trace_id": "trace_20260930_close"
      },
      "fact_fingerprint": "8d3e21a..."
    },
    {
      "fact_id": "fact_breadth_summary",
      "fact_key": "breadth.summary",
      "fact_type": "MARKET_BREADTH",
      "time_context": {
        "event_time": "2026-09-30T15:00:00.000+08:00",
        "observed_time": "2026-09-30T15:30:00.000+08:00",
        "ingestion_time": "2026-09-30T15:30:02.000+08:00",
        "effective_time": "2026-09-30T15:00:00.000+08:00"
      },
      "status": "AVAILABLE",
      "freshness": "REALTIME",
      "source": "market_daily_snapshot:EOD_CLOSE",
      "source_record_id": "1",
      "payload": {
        "down_count": 2841,
        "flat_count": 183,
        "total_amount_yi": 16477.2,
        "up_count": 2614
      },
      "provenance": {
        "fallback_occurred": false,
        "primary_source": "market_daily_snapshot:EOD_CLOSE",
        "trace_id": "trace_20260930_close"
      },
      "fact_fingerprint": "1a9c45b..."
    },
    {
      "fact_id": "fact_limit_up_pool",
      "fact_key": "limit_up.pool",
      "fact_type": "LIMIT_UP_POOL",
      "time_context": {
        "event_time": "2026-09-30T15:00:00.000+08:00",
        "observed_time": "2026-09-30T15:30:00.000+08:00",
        "ingestion_time": "2026-09-30T15:30:02.000+08:00",
        "effective_time": "2026-09-30T15:00:00.000+08:00"
      },
      "status": "EMPTY",
      "freshness": "REALTIME",
      "source": "market_daily_snapshot:EOD_CLOSE",
      "source_record_id": "1",
      "payload": {
        "limit_up_count": 0,
        "max_board_height": 0,
        "pool": []
      },
      "provenance": {
        "fallback_occurred": false,
        "primary_source": "market_daily_snapshot:EOD_CLOSE",
        "trace_id": "trace_20260930_close"
      },
      "fact_fingerprint": "e3b0c44..."
    }
  ],
  "source_manifest": [
    {
      "fetch_status": "SUCCESS",
      "latency_ms": 124.5,
      "records_count": 3,
      "source_name": "market_daily_snapshot:EOD_CLOSE"
    }
  ],
  "snapshot_fingerprint": "6b7df0a6e02cbda361b93f14afeb824f5b498562d245cd95fbc8c17a29a8ea0d"
}
```

---

## 十三、Cognition Coverage Matrix 认知覆盖度矩阵

站在 Cognition 理想推演需求的反向视角，对 M1~M5 的事实供给能力建立覆盖度矩阵：

| Cognition 推演所需事实范畴 | 具体所需事实指标 | 当前是否存在 | 来源模块 | 时间一致性 | 实体关联度 | Provenance | 事实质量 | 核心缺口与裁决 |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **大盘指数趋势推演** | 上证/深成/创业/科创 点位与涨幅 | ✅ 存在 | M1 | ✅ 良好 | ✅ 宽基代码 | ✅ 完备 | FULL | **无缺口**：可完整支持指数涨跌断言与证伪。 |
| **全市场情绪周期推演** | 涨跌停家数、全市场涨跌比 | ✅ 存在 | M1 | ✅ 良好 | ✅ ALL_A | ✅ 完备 | PARTIAL | **轻微缺口**：缺少炸板个股明细，但标量统计足够。 |
| **主线题材与板块轮动** | 申万一级行业涨跌幅、板块成交额 | ❌ 缺失 | M1 / M5 | ❌ 无时点 | ❌ 无代码 | ❌ 无 | MISSING | **致命缺口**：完全无法提出或验证任何板块假说。 |
| **龙头高度与连板晋级** | 最高板股票代码、连板梯队名单 | ⚠️ 存在但被过滤 | M1 (`items`) | ⚠️ 键名错配 | ❌ 未映射 | ⚠️ 降级 | DEGRADED | **重大缺陷**：快照中有数据，但适配器读取错误。 |
| **早盘竞价承接推演** | 09:25 开盘成交额比值、一字板数 | ✅ 存在 | M4 | ✅ 09:25锁定 | ⚠️ 仅大盘 | ✅ 完备 | AVAILABLE | **部分支持**：大盘竞价可用；高标溢价缺数。 |
| **昨日高标断板/分歧核验** | 连板股开盘溢价率、首板晋级率 | ❌ 缺数 | M4 | ❌ 样本为0 | ❌ 无代码 | ❌ 无 | EMPTY_SET | **严重缺口**：`tested_count: 0`，高标推演必落入 INCONCLUSIVE。 |
| **盘中日内量能突变核验** | 10:00/14:00 量能投影、分时背离 | ⚠️ 库中有但未接 | M5 | ⚠️ 盘中时序 | ⚠️ 宏观分时 | ⚠️ 孤岛 | AVAILABLE | **架构断层**：M5 丰富分时数据未向 Cognition 输送。 |
| **盘中个股急速异动感知** | 个股放量突拉、大单砸盘事件 | ⚠️ 库中有但未接 | M5 | ⚠️ 秒级事件 | ✅ 股票代码 | ⚠️ 孤岛 | AVAILABLE | **架构断层**：M5 异动事件未向 Cognition 输送。 |
| **单笔交易因果诊断** | 买卖点位、成交时 D1~D6 环境 | ✅ 存在 | M3 / M1.4 | ⚠️ 分钟级 | ✅ 真实交易 | ✅ WORM | FULL | **可用**：已支持单笔交易环境匹配度回测。 |

---

## 十四、Fact Gaps 事实缺陷与断层清单

按照审计规范标准化分类，全面列出上游事实底盘存在的致命缺陷：

```text
1. [GAP-01] 行业板块结构化事实全面缺失 (Missing Fact)
   - 现象：M1~M5 未输出结构化板块代码 (sector_code)、板块涨跌幅与成分股对照表。
   - 影响：Cognition 无法支持任何题材轮动、板块分歧或主线认知的提出与证伪。

2. [GAP-02] M1 适配器涨停池键名错配 Bug (Architecture Debt / Code Bug)
   - 现象：m1_adapter.py 读取 'pool' 字段，底层 MarketDailySnapshot 存储的是 'items' 字段。
   - 影响：导致生产环境下涨停股票明细 100% 丢失，被误判为 FactStatus.EMPTY (零涨停)。

3. [GAP-03] M4 早盘高标样本池常态化缺省 (Insufficient Evidence)
   - 现象：auction_report.high_open_stats 的 tested_count 恒为 0，高标溢价率为 None。
   - 影响：导致所有针对早盘连板高标溢价的预期断言在求值时均触发 INCONCLUSIVE 证据不足。

4. [GAP-04] M5 盘中高频时序与异动事件成为“事实数据孤岛” (Architecture Gap)
   - 现象：M5 生产库已积累 189 条分时快照与 152 条异动事件，但未向 Cognition 开放适配器。
   - 影响：Cognition 只能做“盲目的日终静态核算”，无法感知盘中量能衰竭与日内多空跃迁。

5. [GAP-05] 新闻资讯缺乏实体关系抽取 (Missing Fact / Invalid Assumption)
   - 现象：S4 market_news 仅抓取文本 title 与 brief，无股票代码与行业标签关联。
   - 影响：无法从新闻直接建立因果假说，设计文档宣称的“外盘新闻驱动推演”目前缺乏事实支撑。

6. [GAP-06] 真实历史交易日数据质量脆弱 (Risk)
   - 现象：5 个历史交易日中有 3 个交易日因 Eastmoney 接口盘后超时缺失广度，评级为 PARTIAL/INVALID。
   - 影响：直接触发 Cognition 准入守卫拦截，导致认知账本在真实环境下无法连续成链。
```

---

## 十五、Architecture Risks 架构系统性风险

1. **“假说空转”风险（Unfalsifiable Hypothesis Risk）**：
   - 若在当前事实底盘下放开 LLM 生成板块或个股假说，由于底层缺乏对应事实切片，证伪引擎在执行 AST 评估时将**100% 返回 `INCONCLUSIVE`（证据不足）**。大模型会误以为假说未被推翻，从而引发虚假认知自洽与认知幻觉。
2. **“全A虚拟标的过度拟合”风险（ALL_A Overfitting Risk）**：
   - 目前系统的全部认知闭环几乎完全押注在虚拟标的 `ALL_A` 之上。这种将全市场 5000 只股票打包成单一宏观标量的做法，掩盖了市场极端结构性分化（如“指数微涨但4000只个股普跌”、“大盘股护盘但题材股暴跌”）的真实物理面貌。
3. **“写接口被动触发”虽已收口，但事实源缓存机制未建立（Cache Starvation Risk）**：
   - 虽在 Phase 2B.3 闭环补丁中彻底去除了 UI 查询时的重算副作用，但底层缺乏独立的事实采集与持久化守护进程，当遇到非交易日或接口故障时，系统极易陷入事实饥饿。

---

## 十六、Mock / Production Gap 单元测试与生产真实鸿沟

审计组对比了单元测试用例与生产库真实数据，揭示了触目惊心的**测试虚假繁荣（Mock Prosperity）**：

| 测试场景 / 模块 | 单元测试环境的表现 (Mock Environment) | 生产数据库真实环境的表现 (Production Reality) | 鸿沟严重性与定性 |
|:---|:---|:---|:---:|
| **M1 涨停池抽取** | 手工构造 `pool: [{"code": "000001", "height": 1}]`，单测 100% PASS。 | 生产库字段名为 `items`，适配器提取结果为 `[]`，判定为 `EMPTY`。 | 🔴 **严重伪绿**：单测掩盖了键名错配的致命 Bug。 |
| **M4 高标溢价** | 手工构造 `high_open_stats: {"tested_count": 5, "high_open_ratio": 0.8}`，单测 PASS。 | 生产库真实数据 `tested_count: 0`，数据全为 None。 | 🔴 **严重断层**：测试在真空中运行，生产中高标事实根本不存在。 |
| **M5 结算价适配** | 手工构造 `MarketSettlementCache` ORM 对象，单测 PASS。 | 生产库该表记录数为 **0**，Baostock 结算接口根本未运行。 | 🔴 **空壳适配**：测试覆盖了代码分支，但生产没有数据流入。 |
| **AST 板块选择器** | 手工在测试切片中注入 `sector_stocks: [{"sector_code": "BK0437"}]`，单测 PASS。 | 真实复盘与快照中 **从未生成过 `sector_stocks`**。 | 🔴 **虚幻能力**：DSL 支持板块过滤，但底层从未提供板块数据。 |

---

## 十七、当前能力边界定性（Cognition 到底知道了什么？）

依据审计原则第十五节，正面回答六个核心认知哲学问题：

### 1. Cognition 到底知道了什么？
- 知道 **4 个主要宽基指数**（上证、深成、创业板、科创50）在收盘和竞价时刻的点位与涨跌幅；
- 知道 **全市场宏观聚合总量**：全天成交总额（亿元）、上涨/下跌/平盘总家数、涨停/跌停总家数、最高板数值；
- 知道 **隔夜 5 项外盘指数**（A50、纳指、道指、标普、恒指）的涨跌表现；
- 知道 **用户真实的 5 笔交易动作**（买入/卖出价格、时间与自述理由）。

### 2. Cognition 到底不知道什么？
- **不知道任何行业板块**：不知道半导体、券商、医药还是地产在领涨；
- **不知道任何具体个股的连板与走势**：不知道今天连板龙头是谁，不知道哪只高标炸板；
- **不知道盘中分时动态与量能波折**：不知道早盘冲高回落还是尾盘偷袭，不知道盘中放量节点；
- **不知道新闻与股票的关系**：不知道利好消息究竟对应哪家上市公司。

### 3. 哪些事实可信？
- 4 宽基指数收盘价与涨跌幅：**完全可信（A级）**；
- 全市场涨跌家数与总成交额：**在数据源未超时时可信（B级）**；
- 用户交易记录：**完全可信（A级，不可变账本保证）**。

### 4. 哪些事实可以关联？
- 宽基指数 ↔ 全市场广度：**可以关联**；
- 用户交易 ↔ 当日大盘 D1~D6 状态：**可以关联**；
- **其余任何涉及个股、板块、新闻的关联：目前全部无法关联**！

### 5. 哪些认知命题能够被真正验证？
- 形如：“明日上证指数跌幅不超过 1.0%” —— **能够验证**；
- 形如：“明日全市场涨停家数不少于 40 家，跌停不超过 20 家” —— **能够验证**；
- 形如：“明日大盘早盘竞价成交额承接比高于 0.8%” —— **能够验证**。

### 6. 哪些认知命题目前实际上没有足够证据？
- 形如：“明日高标龙头继续晋级 8 板” —— **没有证据**（个股缺失）；
- 形如：“明日科技半导体板块将迎来资金回流反弹” —— **没有证据**（板块缺失）；
- 形如：“昨日断板的均胜电子今日会有水下承接” —— **没有证据**（微观个股与日内时序缺失）；
- 形如：“午后量能若萎缩则引发高标集体跳水” —— **没有证据**（M5 盘中时序未连通）。

---

## 十八、是否需要 M1~M5 返工判定

**审计结论：必须对 M1~M5 进行针对性工程补强与返工修复！**  
**但坚决不推翻现有架构，而是按以下 P0 / P1 / P2 优先级实施外科手术式精准返工：**

### 1. P0 级刚性缺陷修复（阻断级，必须在任何 Cognition 前进前完成）
1. **修复 `m1_adapter.py` 涨停明细提取 Bug**：
   - 将读取 `"pool"` 修正为同时兼容 `"items"` 与 `"pool"`，恢复 52 只涨停股的实体明细输入。
2. **保持 Phase 2B.2 PromptSpec 与 Validator 的收窄约束**：
   - 严禁擅自解除 `target_asset` 仅限 `ALL_A` 和 4 宽基指数的限制；坚决禁止在事实补齐前放开个股假说。

### 2. P1 级事实底盘能力补强（支撑深层 Cognition 必需）
1. **M1 引入标准化板块事实抽取（Sector Fact Provider）**：
   - 规范化持久化申万一级行业或东财核心板块的日终涨跌幅与成交额，输出 `sector.*` 事实项。
2. **M4 早盘竞价高标追踪链路修复**：
   - 修复昨日连板高标向今日 09:25 竞价池的自动结转逻辑，解决 `tested_count: 0` 的缺数问题。
3. **M5 盘中宏观分时向 Cognition 开放只读事实切片**：
   - 编写 `M5IntradayFactAdapter`，将盘中 5 分钟宏观分时与异动事件转化为标准 `FactItem`。

### 3. P2 级架构治理与韧性强化
1. **S4 外部数据采集双源容灾加固**：
   - 增加对 Eastmoney 盘后复盘超时的多级重试与本地备份机制，降低 PARTIAL / INVALID 发生率。
2. **新闻快讯轻量实体标签标注**：
   - 对 S4 快讯增加基于正则与关键字的股票代码/板块标签自动匹配。

---

## 十九、Observation Sufficiency Gate 终审门禁裁决

依据指令第十三节，给出权威审计门禁裁决：

```text
================================================================================
             OBSERVATION / M1-M5 SUFFICIENCY GATE 最终裁决
================================================================================

  裁决结论： 🟡 PASS WITH GAPS (有条件放行 / 严格限制性准入)

================================================================================
```

### 1. 为什么是 PASS WITH GAPS 而非完全 BLOCK？
- **因为闭环通道本身已经通过工程终审**：Phase 2B.1 ~ Phase 2B.3 已完备证明，在**宏观全A聚合（`ALL_A`）与 4 宽基指数**范围内，事实提取、JCS 哈希、WORM 入账、AST 证伪与前端可视化完全自洽、可复现、可审计。这部分认知能力具备坚固的事实基础，**无需完全推倒重来或全面冻结**。

### 2. 哪些 Cognition 可以继续推进？（Permitted Scope）
- ✅ **全市场宏观情绪周期假说**：允许推演全A涨跌停数量、涨跌家数比、最高连板空间。
- ✅ **宽基指数趋势与分化假说**：允许推演上证、深成、创业板、科创50的涨跌幅范围与强弱对比。
- ✅ **大盘早盘竞价量能承接假说**：允许推演 09:25 两市竞价总额与承接比值。
- ✅ **单笔交易事后环境匹配诊断**：允许基于当日客观 D1~D6 快照进行交易行为反思。

### 3. 哪些 Cognition 必须严格限制并刚性 BLOCK？（Forbidden Scope）
- 🛑 **刚性禁止生成任何行业/板块轮动假说**（如“半导体领涨”、“医药避险”）：因底层板块事实完全缺失，必导致伪证伪！
- 🛑 **刚性禁止生成任何具体个股的涨跌或断板假说**：因底层个股事实未打通，AST 无法求值！
- 🛑 **刚性禁止引入买卖推荐、仓位建议、个股 Alpha 收益预测**（违背最高铁律 2）。
- 🛑 **刚性禁止放宽 PromptSpec 与 ProposalValidator 边界**：必须维持 VR-01~VR-07 刚性拦截网。

---

## 二十、后续工程演进建议

为确保系统稳健进化，建议工程团队采取**“双轨并行、事实先行”**的演进路径：

```text
               ┌────────────────────────────────────────────────────────┐
               │              Track A: 事实底盘补强攻坚                 │
               │ 1. 修复 m1_adapter "pool" vs "items" 键名 bug          │
               │ 2. 打通 M4 连板高标竞价自动结转                        │
               │ 3. 规范化 M1 板块事实输出 (sector_code)                │
               │ 4. 接入 M5 盘中 5 分钟宏观时序切片                     │
               └──────────────────────────┬─────────────────────────────┘
                                          │ 验证事实完备性 (Fact Gate PASS)
                                          ▼
               ┌────────────────────────────────────────────────────────┐
               │              Track B: 认知层受控演进                   │
               │ 1. 保持当前 Phase 2B.3 宏观认知稳定运行                │
               │ 2. 待 Track A 交付后，扩展 AST 支持 UniverseType.SECTOR │
               │ 3. 升级 PromptSpec v1.2.0，逐步放开板块假说生成        │
               │ 4. 严守不可变账本与波普尔证伪原则                      │
               └──────────────────────────┘
```

1. **第一步（立即执行）**：以最小代码补丁修复 `m1_adapter.py` 中的 `"pool"` 键名错配问题，并补充单元测试，确保真实涨停个股明细恢复进入 `ObservationSnapshot`。
2. **第二步（冻结等待）**：在 M1 板块事实和 M4 高标事实未完成生产级持久化前，坚决不擅自启动个股级或板块级假说推演。
3. **第三步（保持隔离）**：继续保持物理开发库零污染、保持 M4/M5/M6 交易隔离、保持 NAS 生产部署隔离。

---

> **报告发布声明**：  
> 本审计报告全部结论均基于本地工作区实际代码、SQLite 生产数据库 `\\Fn-evo2-xh\Docker\AI-Trading-System\data\trading.db` 现场穿透回放及 KA-06 基线测试铁证独立得出，坚决摒弃任何主观推测与文档设想，特此呈报最高董事会裁决。
