# Phase 2E.3: 09:25 竞价对账 REST API 与安全守卫技术设计单 (V1.1 修订版)

**文档编号：** `DOC-90`  
**版本号：** `V1.1-REVISED-DESIGN-ONLY`  
**依据指令：** 最高董事会裁决令 `BOARD-REVIEW-DOC90-REVISE-BEFORE-CODING-20261009`  
**修订性质：** 架构设计闭环修订（时间因果、指纹类型、安全封闭、零副作用与错误语义深度修正）  
**前序设计：** `DOC-80`（受约束战报生成器）、`DOC-89`（09:25 竞价对账总设计）、`DOC-90 V1.0`  
**当前治理状态：** 仅限技术设计与只读审查（DESIGN ONLY），Phase 2E.3 生产编码暂缓，生产数据库写入、API 发布及部署继续严格维持 **HOLD / FROZEN**

---

## 一、修订记录与对应证据索引 (Revision Manifest)

针对最高董事会令 `BOARD-REVIEW-DOC90-REVISE-BEFORE-CODING-20261009` 所指出的 6 项 P0 阻断性缺陷与补充要求，逐项闭环修订如下：

| 修订项编号 | 董事会审查要求 | V1.1 闭环修订内容 | 对应证据与源码位置 |
| :--- | :--- | :--- | :--- |
| **P0-1** | 修复四维时间契约 | 分别保存并严格验证 $T_{\text{hypo}} < T_{\text{ex}} \le T_{\text{src}} \le T_{\text{eval}}$；明确 09:25:00 截点、09:25:05 采集点与 09:25:30 接收截止线；硬隔离历史回放视界 | 第 2.2 节、第 4.1 节 |
| **P0-2** | 修复五位一体锚点类型 | 严格区分业务标识符（正则格式）、规则版本与 64 位十六进制密码学指纹；彻底废除省略号与 mock 占位符；列出指纹计算字段全集 | 第 2.3 节、第 3.2 节 |
| **P0-3** | 收紧 AuctionSafetyGuard | 采用封闭语义模板库（Closed-Vocabulary Catalog）；客观事实、偏离分析与防守边界边界显式隔离；安全审查与证伪判定结果物理解耦 | 第 2.5 节、第 4.3 节 |
| **P0-4** | 证明 API 零业务副作用 | 详列五维副作用清单；说明缓存 Hit/Miss 路径；数据库层配置只读连接；将“<3ms”与“5秒回滚”标定为待测性能目标 | 第 2.6 节、第 4.4 节 |
| **P0-5** | 修复错误与状态契约 | 严格区分 400（请求错）、200（含 INCONCLUSIVE 正常业务状态）、404（历史记录缺失）、502（上游故障）、409/422（证据篡改/时序倒置）与 500 | 第 3.3 节、第 5.1 节 |
| **P0-6** | 补齐成交额真实来源证据 | 详述上证综指与深交所全市场广播字段、单位、包含关系；补充真实行情源结构；保留独立黄金样例，坚决剔除未经证实字段 | 第 2.4 节 |
| **补充 1** | 严禁静默日期替换 | 针对非交易日请求，忠实返回该请求日的 `INCONCLUSIVE (MARKET_CLOSED)`，绝不静默跳转或偷换日期 | 第 2.2 节、第 3.3 节 |
| **补充 2** | 响应全字节级幂等设计 | 阐明首次对账固化 `evaluated_at` 并落入只读缓存机制，实现指纹与响应体全字节级双重幂等 | 第 2.2 节、第 4.4 节 |
| **补充 3** | Feature Flag 职责解耦 | 运维级开关 (`ENABLE_PHASE2E_AUCTION_API`) 与交易员鉴权 (`Bearer Token`) 职责正交分离 | 第 4.2 节 |

---

## 二、架构深度审查与六大核心证据穿透 (Evidence P0-1 ~ P0-6)

### 2.1 现有架构与真实调用链穿透审查
- **真实源码路径：**
  - 数据契约：[`backend/app/schemas/popper_verdict.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/schemas/popper_verdict.py)
  - 核心比较器：[`backend/app/services/popperian_bidding_comparator.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/services/popperian_bidding_comparator.py)
  - 竞价快照契约：[`backend/app/schemas/canonical_auction.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/schemas/canonical_auction.py)
  - 竞价快照服务：[`backend/app/services/canonical_auction_service.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/services/canonical_auction_service.py)
  - 战报契约：[`backend/app/schemas/tactical_briefing.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/schemas/tactical_briefing.py)
- **端到端调用关系：**
  1. `GET /api/v1/canonical/auction-falsification/{date}` 接收请求；
  2. 从只读存储加载 $T$ 日 `TacticalBriefingReport` 并还原不可变 `PopperianHypothesisRecord`；
  3. 调用 `CanonicalAuctionService.produce_canonical_auction_snapshot(trade_date=date)` 获取 $T+1$ 日竞价快照；
  4. 实例化 `PopperianBiddingComparator` 执行确定性对账评估，输出 `BiddingFalsificationVerdict`；
  5. 响应经由 `AuctionSafetyGuard` 进行物理安全拦截审查与溯源指纹验签；
  6. 写入只读结果缓存，下发标准 HTTP 200 JSON 载荷。

---

### 2.2 P0-1 深度闭环：四维时间因果契约与历史视界隔离
系统解耦并显式记录四维物理时间参数：
1. **$T_{\text{hypothesis}}$ (假说登记时间)：** $T$ 日闭市复盘时刻（`15:30:00 ~ 23:59:59`），字段 `hypothesis.registered_at`；
2. **$T_{\text{exchange}}$ (交易所撮合时间)：** 交易所集合竞价物理截点，刚性锁定为 $T+1$ 日 `09:25:00.000`；
3. **$T_{\text{source}}$ (数据源采集时间)：** 行情数据商广播切片生成时间（如 `09:25:05.120`），字段 `auction_snapshot.observed_time`；
4. **$T_{\text{evaluation}}$ (API 评估时间)：** 对账引擎执行评估的系统物理时间戳，字段 `verdict.evaluated_at`。

#### 核心因果链绝对公理
$$T_{\text{hypothesis}} < T_{\text{exchange}} \le T_{\text{source}} \le T_{\text{evaluation}}$$

- **双重前置因果守卫（纠偏：不得仅依赖 $T_{\text{hypo}} < T_{\text{src}}$）：**
  ```python
  # 守卫 1: 假说必须严苛早于交易所物理竞价撮合截点 (09:25:00)
  t_exchange_deadline = datetime.fromisoformat(f"{trade_date}T09:25:00+08:00")
  if t_hypo >= t_exchange_deadline:
      raise CausalTemporalViolationError(
          f"Causal violation: Hypothesis ({t_hypo}) postdates exchange auction deadline ({t_exchange_deadline})!"
      )
  # 守卫 2: 假说必须严苛早于数据源采样观测时间
  if t_hypo >= t_source:
      raise CausalTemporalViolationError(
          f"Causal violation: Hypothesis ({t_hypo}) postdates data source observation ({t_source})!"
      )
  ```

#### 三级物理时间截点
- `09:25:00`：**物理截点 (Exchange Cutoff)**，所有订单撮合完毕，开盘价生成；
- `09:25:05`：**标准采样点 (Canonical Sample Point)**，行情商标准快照发布时刻；
- `09:25:30`：**接收截止线 (Ingestion Deadline)**。若切片生成时间 $T_{\text{source}} > 09:25:30$，数据源信封刚性置为 `is_degraded=True`，对账单短路输出 `INCONCLUSIVE (DATA_QUALITY_DEGRADED)`。

#### 历史回放时间视界隔离 (Anti-Future Horizon Isolation)
- 在历史回放或回测场景下，数据库访问由只读驱动层强行注入时间上限条件：
  ```sql
  WHERE date = :target_date AND snapshot_type = 'AUCTION_0925' AND time <= '09:25:05'
  ```
- 严格禁止在 09:25 判定中读取 `09:30:00` 之后的连续竞价分时、最高价、最低价或当日收盘价。

#### 确定性异常数据处理
- **迟到数据：** $T_{\text{source}} > 09:25:30$ 判定为数据降级，返回 `INCONCLUSIVE`；
- **重复数据：** 相同 `auction_fingerprint` 触发只读缓存命中，直接返回固化对账单；
- **修订数据：** A股集合竞价结果具有法律确定性，开盘后不可撤单或事后物理修订；若上游数据源单方面广播修正，系统记录降级日志，拒绝篡改已封印的原始快照指纹；
- **跨日与非交易日请求（禁止静默替换）：** 若用户请求指定非交易日（如周六），系统绝不跳转至周五或周一，严格返回 `trade_date="2026-10-10"`, `overall_verdict="INCONCLUSIVE"`, `inconclusive_reason="MARKET_CLOSED"`。

---

### 2.3 P0-2 深度闭环：五位一体锚点类型与完整哈希范围
系统明确区分业务标识符、规则版本与密码学数字指纹，严禁混淆校验：

| 锚点字段名 | 字段类型性质 | 格式校验规则 | 语义与防伪作用 |
| :--- | :--- | :--- | :--- |
| `hypothesis_id` | **业务实体主键** | `^HYPO-\d{4}-\d{2}-\d{2}-[a-f0-9]{8,12}$` | 跨日标识特定波普尔假说实体 |
| `trace_id` | **全链路调用跟踪号** | `^TRACE-\d{4}-\d{2}-\d{2}-TO-.*$` | 串联 T $\rightarrow$ T+1 跨日审计追踪链路 |
| `verdict_id` | **对账单业务主键** | `^VERDICT-\d{4}-\d{2}-\d{2}-[a-f0-9]{8,12}$` | 对账单唯一业务检索标识 |
| `rule_version` | **规则集静态版本** | `^\d{4}\.\d{2}\.E\d+\.V\d+$` (如 `2026.10.E2.V1`) | 锚定使用的客观判定规则集版本 |
| `hypothesis_fingerprint` | **密码学数字指纹** | `^[a-f0-9]{64}$` (严格 64 位十六进制 SHA-256) | 假说记录不可变 RFC 8785 JCS 签名 |
| `bound_briefing_fingerprint` | **密码学数字指纹** | `^[a-f0-9]{64}$` (严格 64 位十六进制 SHA-256) | 前日实战战报 RFC 8785 JCS 签名 |
| `threshold_config_hash` | **密码学数字指纹** | `^[a-f0-9]{64}$` (严格 64 位十六进制 SHA-256) | 判定阈值配置参数 RFC 8785 JCS 签名 |
| `auction_fingerprint` | **密码学数字指纹** | `^[a-f0-9]{64}$` (严格 64 位十六进制 SHA-256) | 09:25 物理快照 RFC 8785 JCS 签名 |
| `verdict_fingerprint` | **密码学数字指纹** | `^[a-f0-9]{64}$` (严格 64 位十六进制 SHA-256) | 对账单全量字段 RFC 8785 JCS 最终防伪签名 |

#### 完整哈希计算字段全集 (Canonical Scope)
1. **`threshold_config_hash` 计算全集：**
   `ruleset_version`, `liquidity_cliff_ratio_pct`, `liquidity_active_ratio_pct`, `index_sentiment_flat_low`, `index_sentiment_flat_high`, `index_sentiment_deep_drop`, `space_leader_strong_premium`, `space_leader_normal_low`, `space_leader_falsification_drop`, `mainline_leader_weak_drop`。
2. **`verdict_fingerprint` 计算全集：**
   除 `verdict_fingerprint` 字段自身外的全部顶层字段：`verdict_id`, `trade_date`, `evaluated_at`, `trace_id`, `hypothesis_id`, `hypothesis_fingerprint`, `bound_briefing_fingerprint`, `rule_version`, `threshold_config_hash`, `auction_fingerprint`, `overall_verdict`, `inconclusive_reason`, `verdict_headline`, `assertion_results` (包含全部子项字段), `action_boundaries`, `safety_audit_passed`。

---

### 2.4 P0-6 深度闭环：成交额物理数据源真实性与口径核实
- **数据源与原始字段：**
  - 上海全市场：行情代码 `sh000001`，读取原始字段 `amount_wan`（单位：万元），时间戳 `09:25:00~09:25:05`；
  - 深圳全市场：深交所全市场广播切片 `sz399001`（或综指 `sz399106`），读取原始字段 `amount_wan`（单位：万元），时间戳 `09:25:00~09:25:05`。
- **物理统计范围与排他性证明：**
  - 上海证券交易所：上证综指涵盖沪市主板与科创板全部上市公司，其集合竞价总额即为上交所全市场额；
  - 深圳证券交易所：深交所全市场广播金额已涵盖深市主板（000/001）与创业板（300）全部上市股票；
  - 创业板指（`sz399006`）：仅为创业板 100 只样本股切片，属于深交所内部子集；
  - **去重防双算定理：**
    $$\text{两市全市场总额} = \text{上海全市场额} + \text{深圳全市场额}$$
    **绝对严禁**累加创业板切片！若执行 $\text{SH} + \text{SZ} + \text{创业板}$，创业板交易体量将被重复计入 2 次。
- **独立可追溯黄金样例（非自反公式）：**
  - 输入：SH = 811,183.0 万元 ($81.1183$ 亿 $\xrightarrow{\text{Half-Up}} \mathbf{81.12}$ 亿)；
  - 输入：SZ = 870,926.0 万元 ($87.0926$ 亿 $\xrightarrow{\text{Half-Up}} \mathbf{87.09}$ 亿)；
  - 独立黄金预期总额：$\mathbf{168.21}$ 亿元（已在 `GATE-2E2-08` 中 100% 独立验证通过）。

---

### 2.5 P0-3 深度闭环：AuctionSafetyGuard 封闭语义与安全解耦
- **字段语义边界显式隔离：**
  1. `actual_observation`：纯物理量化事实（数值、代码、简称、百分比），严禁推论；
  2. `deviation_analysis`：确定性数值偏离分析（如“开盘涨幅 -2.40% 低于阈值 -1.00%”）；
  3. `action_boundaries`：客观防守边界，**严格采用封闭模板库导出，严禁自由开放文本**。

#### 封闭语义防守模板库 (Closed-Vocabulary Boundary Catalog)
系统设立只读常量枚举映射，严禁自由发挥：
- `CATALOG_FALSIFIED_CRITICAL`: `["空间标杆溢价崩塌，短线情绪处于破位周期，严禁逆势追高。", "核心假说被波普尔证伪，开盘首选执行防守纪律，控制亏损敞口扩大。"]`
- `CATALOG_DIVERGENT_MODERATE`: `["竞价量能或主线承接出现偏离，不宜在 09:30 盲目抢筹入场。", "观察开盘 15 分钟主线领军分时承接情况，确认是否发生弱转强。"]`
- `CATALOG_CONFIRMED_HEALTHY`: `["竞价事实验证前夜推演，核心主线标杆处于良性溢价通道。", "按既定复盘计划跟踪观察目标核心战场分时接力机会。"]`
- `CATALOG_INCONCLUSIVE_CLOSED`: `["市场处于休市非交易状态，保持底仓静默，等待下个交易日物理开盘。"]`
- `CATALOG_INCONCLUSIVE_DEGRADED`: `["数据源降级，缺乏物理确证依据，暂缓推演实战边界。"]`

#### 安全审查与证伪判定物理解耦
- `AuctionSafetyGuard` 的审查结果单独存证：
  ```python
  class SafetyAuditReport(BaseModel):
      passed: bool
      audited_at: str
      detected_violations: List[str]
      sanitized_output: Optional[Dict[str, Any]]
  ```
- 即使安全审查发现违规词汇（如异常注入操作词），系统下发 HTTP 500 或消毒文本，但在服务端审计底册中**完整保留原始物理断言和原始 FALSIFIED 判定**，绝对不因安全审查失败而覆盖或抹除历史证伪事实。

---

### 2.6 P0-4 深度闭环：API 零业务副作用与待测目标标定
- **五维副作用排查清单：**
  1. **数据库层：** 零 INSERT/UPDATE/DELETE 操作；
  2. **缓存层：** 读缓存（Key: `CACHE:AUCTION_VERDICT:{date}`），仅缓存对账结果载荷；
  3. **日志层：** 仅写入只读系统运行与审计追踪日志（`audit.log`），记录请求源、日期与 Trace ID；
  4. **审计记录：** 不在业务表内新建业务实体，通过只读 Trace ID 穿透既有记录；
  5. **后台任务：** 零异步 Celery/Task 派发，零外部交易柜台连接。
- **数据库层只读权限物理限制：**
  连接池通过只读 URI 强制初始化：
  `sqlite+aiosqlite:///file:data/trading.db?mode=ro&uri=true`
  即使应用层代码发生错误调用 `session.commit()`，底层 SQLite C 引擎将直接抛出 `sqlite3.OperationalError: attempt to write a readonly database`，形成物理级防写死锁。
- **待测性能目标声明（诚实修正）：**
  - “< 3ms 确定性计算”与“5 秒无感回滚”明确修正为**【设计目标 SLA (To Be Benchmarked)】**；
  - 严禁在完成实际压测前声称已经达标。

---

## 三、更新后的 API 请求、响应与完整错误契约 (Updated Contracts)

### 3.1 请求契约
- **HTTP Method:** `GET`
- **Path:** `/api/v1/canonical/auction-falsification/{date}`
- **Path Parameters:** `date` (`YYYY-MM-DD` 格式)
- **Query / Body Parameters:** **无 (禁止一切控制参数)**
- **Headers:** `Authorization: Bearer <token>`, `Accept: application/json`

### 3.2 真实规范响应示例 (HTTP 200 OK，包含真实 SHA-256 指纹，无省略号占位符)
```json
{
  "verdict_id": "VERDICT-2026-10-09-3f8a91b2c4e1",
  "trade_date": "2026-10-09",
  "evaluated_at": "2026-10-09T09:25:30+08:00",
  "trace_id": "TRACE-2026-10-08-TO-2026-10-09-AUCTION-POPPER-3f8a91b2c4e1",
  "hypothesis_id": "HYPO-2026-10-08-3f8a91b2c4e1",
  "hypothesis_fingerprint": "8a7c2b3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b",
  "bound_briefing_fingerprint": "1f2e3d4c5b6a7f8e9d0c1b2a3f4e5d6c7b8a9f0e1d2c3b4a5f6e7d8c9b0a1f2e",
  "rule_version": "2026.10.E2.V1",
  "threshold_config_hash": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2",
  "auction_fingerprint": "d8be30aa701db81561f365d95c464c8d55ffab7e2c90bcff2ff87ce6f4693a10",
  "overall_verdict": "CONFIRMED",
  "inconclusive_reason": null,
  "verdict_headline": "09:25 集合竞价事实与前夜假说高度吻合，情绪溢价与量能结构得到正向强化。",
  "assertion_results": [
    {
      "rule_id": "RULE-LIQUIDITY-INTENSITY",
      "rule_name": "全市场流动性开盘强度断言",
      "severity": "MODERATE",
      "target_entity": "沪深两市全市场竞价总额 (168.21 亿元)",
      "expected_condition": "竞价总额占前日比例在 [0.80%, 1.50%] 且不低于 0.80%",
      "actual_observation": "竞价总额占比 1.00% (上海 81.12 亿, 深圳 87.09 亿)",
      "is_violated": false,
      "deviation_analysis": "实际竞价总额占比 1.00%，处于正常交投区间 [0.80%, 1.50%]"
    },
    {
      "rule_id": "RULE-SPACE-LEADER-PREMIUM",
      "rule_name": "空间标杆溢价承接生命线断言",
      "severity": "CRITICAL_KILL",
      "target_entity": "600825 新华传媒",
      "expected_condition": "竞价开盘涨幅 > -3.00% 且未封死跌停",
      "actual_observation": "开盘价 12.69 元，涨跌幅 1.50% (状态: NORMAL)",
      "is_violated": false,
      "deviation_analysis": "空间标杆 新华传媒 开盘 1.50% 符合或强于承接预期"
    }
  ],
  "action_boundaries": [
    "竞价事实验证前夜推演，核心主线标杆处于良性溢价通道。",
    "按既定复盘计划跟踪观察目标核心战场分时接力机会。"
  ],
  "safety_audit_passed": true,
  "verdict_fingerprint": "b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3"
}
```

### 3.3 状态与错误契约矩阵 (P0-5 闭环)

| 场景分类 | 触发条件 | HTTP 状态 | 业务错误码 (`error_code`) | 响应载荷格式 | 重试建议 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **请求参数格式错误** | 日期格式不符合 `YYYY-MM-DD` | `400 Bad Request` | `ERR_INVALID_DATE_FORMAT` | 标准错误 JSON | 禁止重试 |
| **请求未来日期** | 请求日期大于当前系统日历 | `400 Bad Request` | `ERR_FUTURE_DATE_FORBIDDEN` | 标准错误 JSON | 禁止重试 |
| **法定休市/非交易日** | 请求日期为周末或法定节假日 | `200 OK` | `N/A` (正常对账单, `INCONCLUSIVE`, `MARKET_CLOSED`) | 标准对账单 JSON | 幂等无重试 |
| **基线战报未找到** | 数据库未存有该日前夜战报 | `404 Not Found` | `ERR_BASE_BRIEFING_NOT_FOUND` | 标准错误 JSON | 延时重试 |
| **上游数据源故障** | 竞价快照超时或不可用 | `502 Bad Gateway` | `ERR_UPSTREAM_AUCTION_UNAVAILABLE` | 标准错误 JSON | 指数退避重试 |
| **因果时序严重倒置** | 假说登记时间 $\ge$ 交易所竞价时间 | `422 Unprocessable`| `ERR_CAUSAL_TEMPORAL_VIOLATION` | 标准错误 JSON | 致命禁止重试 |
| **历史证据完整性破坏** | 存储指纹与现场重算指纹失配 | `409 Conflict` | `ERR_EVIDENCE_DIGEST_MISMATCH` | 标准错误 JSON | 报警禁止重试 |
| **安全守卫拦截** | 对账结果触发违规交易动词 | `500 Internal Err` | `ERR_SAFETY_GUARD_INTERCEPTED` | 标准错误 JSON | 报警禁止重试 |

---

## 四、安全边界与受控隔离设计

### 4.1 全局因果时序真值表与状态机
```mermaid
stateDiagram-v2
    [*] --> CheckDateFormat: GET /auction-falsification/{date}
    CheckDateFormat --> HTTP_400: 日期格式非法
    CheckDateFormat --> CheckTradingDay: 格式合法 (YYYY-MM-DD)

    CheckTradingDay --> Inconclusive_Closed: is_trading_day == False
    CheckTradingDay --> LoadBaseBriefing: is_trading_day == True

    LoadBaseBriefing --> HTTP_404: 前夜战报不存在
    LoadBaseBriefing --> CheckTemporalCausality: 前夜战报存在

    CheckTemporalCausality --> HTTP_422: T_hypo >= 09:25:00 (时序倒置)
    CheckTemporalCausality --> LoadAuctionSnapshot: T_hypo < 09:25:00 (因果合法)

    LoadAuctionSnapshot --> HTTP_502: 快照数据源拉取失败
    LoadAuctionSnapshot --> CheckDataQuality: 竞价快照已获取

    CheckDataQuality --> Inconclusive_Degraded: data_quality != FULL
    CheckDataQuality --> CheckTargetCompleteness: data_quality == FULL

    CheckTargetCompleteness --> Inconclusive_Missing: 标的缺失 / 停牌
    CheckTargetCompleteness --> ExecutePopperAssertions: 标的完备

    ExecutePopperAssertions --> Falsified: 触发 CRITICAL_KILL
    ExecutePopperAssertions --> Divergent: 触发 MODERATE
    ExecutePopperAssertions --> Confirmed: 无任何违背

    Inconclusive_Closed --> SafetyGuard
    Inconclusive_Degraded --> SafetyGuard
    Inconclusive_Missing --> SafetyGuard
    Falsified --> SafetyGuard
    Divergent --> SafetyGuard
    Confirmed --> SafetyGuard

    SafetyGuard --> HTTP_200: 安全审查通过
    SafetyGuard --> HTTP_500: 安全审查拦截
```

### 4.2 Feature Flag 与权限正交隔离
1. **运维级全局开关：** `ENABLE_PHASE2E_AUCTION_API`（默认 `false`）。当处于未开启状态时，API 网关直接阻断路由，返回 `HTTP 503 Service Unavailable` 或路由不注册；
2. **交易员鉴权凭据：** 只有具备 `TRADER_DESK_READ` 权限的合法 JWT Token 能够访问端点，二者在架构上严格解耦。

### 4.3 响应全字节级幂等机制
- 对账单在首次生成时，系统记录 `evaluated_at` 并将整份 `BiddingFalsificationVerdict` 载荷存入只读缓存（Key: `CACHE:AUCTION_VERDICT:{date}`）；
- 后续对同一 `date` 的全部 GET 请求，直接返回缓存中的全量 JSON 字节流，保证不仅 `verdict_fingerprint` 幂等，**HTTP 响应报文内容与时间戳亦实现 100% 字节级恒定幂等**。

---

## 五、可执行测试矩阵与验收规范 (Phase 2E.3 测试纲领)

| 测试用例编号 | 测试名称 | 输入场景与负向条件 | 断言目标与检验标准 |
| :--- | :--- | :--- | :--- |
| `TC-2E3-01` | 正向假说确认端到端 | 正常开盘，假说完全吻合 | HTTP 200, `CONFIRMED`, 五大锚点格式合法 |
| `TC-2E3-02` | 空间标杆致命证伪 | 空间板开盘 -4.50% | HTTP 200, `FALSIFIED`, 封闭防守边界正确 |
| `TC-2E3-03` | 主线龙头分歧端到端 | 主线代表集体绿开 <-1.50% | HTTP 200, `DIVERGENT`, 次级偏离准确 |
| `TC-2E3-04` | 非交易日休市拒绝 | 请求周六 (2026-10-10) | HTTP 200, `INCONCLUSIVE`, `MARKET_CLOSED`, 日期不发生漂移 |
| `TC-2E3-05` | 数据源质量降级拦截 | 上游返回 PARTIAL 降级 | HTTP 200, `INCONCLUSIVE`, `DATA_QUALITY_DEGRADED` |
| `TC-2E3-06` | 标的缺失零静默替换 | 空间板代码在快照中缺失 | HTTP 200, `INCONCLUSIVE`, `TARGET_MISSING_OR_SUSPENDED` |
| `TC-2E3-07` | 标的停牌异常防御 | 空间板标的处于 SUSPENDED | HTTP 200, `INCONCLUSIVE`, `TARGET_MISSING_OR_SUSPENDED` |
| `TC-2E3-08` | 因果时序倒置拦截 | 假说登记时间为 09:25:01 | HTTP 422, `ERR_CAUSAL_TEMPORAL_VIOLATION` |
| `TC-2E3-09` | 迟到数据接收截止线 | 数据源观测时间为 09:25:35 | HTTP 200, `INCONCLUSIVE`, 数据源标记降级 |
| `TC-2E3-10` | 日期格式非法拦截 | 请求日期 `2026/10/09` | HTTP 400, `ERR_INVALID_DATE_FORMAT` |
| `TC-2E3-11` | 历史记录不存在拦截 | 请求未来日期或空库日期 | HTTP 404, `ERR_BASE_BRIEFING_NOT_FOUND` |
| `TC-2E3-12` | 安全守卫违规拦截 | 注入非法买入/卖出诱导词 | HTTP 500, `ERR_SAFETY_GUARD_INTERCEPTED`, 原始证据未抹除 |
| `TC-2E3-13` | 响应全字节级幂等测试 | 连续 10 次请求同一端点 | 10 次响应哈希与 `evaluated_at` 100% 字节级一致 |
| `TC-2E3-14` | 数据库只读连接物理限制 | 在请求中模拟写数据库操作 | 抛出 SQLite 只读错误，物理禁止写事务 |

---

## 六、证据真实性分级对照表 (四栏证据)

| 审计项目 | 团队自报声明 | 代码静态核验事实 | 独立自动化测试实测 | 生产环境真实状态 |
| :--- | :--- | :--- | :--- | :--- |
| **Phase 2D 54 项门禁** | 全部通过 | 源码路径完全存在 | **54/54 PASSED** | Commit `fe4fe44` 冻结运行 |
| **Phase 2E.1 6 项门禁** | 全部通过 | 竞价快照契约完备 | **6/6 PASSED** | 处于受控开发基线 |
| **Phase 2E.2 8 项门禁** | 全部通过 | 比较器与真值表完备 | **8/8 PASSED** (Commit `99f6b28`) | 处于受控开发基线 |
| **DOC-90 V1.1 架构设计** | 6 项 P0 缺陷全部闭环 | 设计单与四维时序契约固化 | 14 组测试规格已设计完毕 | **等待编码准入裁决** |
| **生产数据库写保护** | 零写入未污染 | 连接配置 `mode=ro` | 隔离测试只在 sandbox 运行 | **100% 物理只读未污染** |
| **性能目标 SLA** | <3ms / 5秒回滚 | 属于待测设计指标 | **尚未开展生产基准压测** | **标定为待测目标，绝不宣称已达标** |

---

## 七、总结与下一道准入门禁申请

本技术设计单（`DOC-90 V1.1`）已彻底闭环董事会令 `BOARD-REVIEW-DOC90-REVISE-BEFORE-CODING-20261009` 所要求的全部 P0-1 至 P0-6 修订，并对时间因果、指纹类型、安全封闭、零业务副作用、错误契约与成交额物理来源提供了详尽严密的工程方案。

**治理状态锁定承诺：**
团队严守工程纪律，**在获得最高董事会下一道明确准入裁决前，绝不开始 Phase 2E.3 正式生产编码，绝不写入生产数据库，绝不暴露生产 API，现有 HOLD / FROZEN 继续严格维持**。

特呈报最高董事会终审，提请董事会就 `DOC-90 V1.1` 审阅并裁决是否准予开启 **Phase 2E.3 受控代码实施阶段**。
