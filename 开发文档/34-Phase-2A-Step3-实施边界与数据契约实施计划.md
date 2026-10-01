# Phase 2A Step 3 实施边界与数据契约实施计划
# （ObservationSnapshot & EffectiveInferenceInput 规范化抽取与沙箱投影方案）

> **计划编号**：`PLAN-COGNITION-PHASE2A-STEP3-20260930`  
> **提交日期**：2026-09-30  
> **上位依据**：  
> - 最高董事会工程裁决令（2026-09-30：批准 Phase 2A Step 3，严格限制在 Sandbox / Test 环境；未经审核批准前严禁写入业务代码）  
> - 《开发文档/28-Cognition-Phase2-可审计结构化认知引擎技术设计单.md》（版本：v1.2.1-FINAL-CLOSURE）  
> - 《开发文档/29-Cognition-Phase2A架构与数据契约冻结决议与实施约束单.md》（编号：BOARD-DECISION-20260930-01）  
> - 《开发文档/32-Track-A-Production-Readiness闭环验收报告.md》（Track A Fact Supply Gate: PASSED）  
> - 《开发文档/33-Phase-2A-Step1-WORM-Hardening闭环验收报告.md》（Step 1 WORM Hardening: COMPLETE）  
> **执行状态**：**SUBMITTED FOR BOARD REVIEW（提请最高董事会审议）**  
> **实施红线**：**在最高董事会签发正式批准令前，严禁启动任何 Step 3 业务代码编写与数据库迁移！**

---

## 一、 架构定位与实施边界（Architecture Boundary & Sandbox Isolation）

### 1.1 核心职能定性：事实提取与资格筛选，绝非认知推演
Phase 2A Step 3 在整个认知体系中充当**“物理事实向认知世界的法定海关”**。其唯一职责是：
1. **真实事实抽取**：从底层 M1（盘后复盘）、M2（盘前推演）、M4（早盘竞价）、M5（历史结算）及 S4（资讯流）的物理落盘数据中，按照严格的时间戳与唯一标识抽取事实切片，构建不可变只读投影对象 `ObservationSnapshot`；
2. **法定资格审查**：根据事实的时效性（Freshness）、状态（Status）、冲突策略（Conflict Resolution）和来源优先级（Source Priority），筛选出具备推理资格的事实子集；
3. **确定性渲染保全**：将通过审查的合格事实注入冻结的 Prompt 模板，形成字节级确定的 `EffectiveInferenceInput`，并计算保全 `effective_input_hash`。

```text
┌────────────────────────────────────────────────────────────────────────────────┐
│                       Operational Fact Layer (M1~M5 / S4)                      │
│      - MarketDailySnapshot (EOD_CLOSE / AUCTION_0925)                          │
│      - MarketNews (CLS / Sina)                                                 │
│      - MarketSettlementCache (Baostock)                                        │
└──────────────────────────────────────┬─────────────────────────────────────────┘
                                       │ 抽取 & 物理投影 (Step 3 职能)
                                       ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│             ObservationSnapshot (客观物理事实投影，JCS Canonical JSON)           │
│      - 记录物理世界“真实观察到了什么”                                           │
│      - 包含 AVAILABLE, STALE, EMPTY, TIMEOUT, ERROR 等所有真实观测状态          │
│      - 纯事实记录，绝对不含任何 AI 观点、情绪倾向或买卖结论                      │
└──────────────────────────────────────┬─────────────────────────────────────────┘
                                       │ 严苛资格筛选 & 过滤网 (Step 3 职能)
                                       ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│           EffectiveInferenceInput (法定生效推理输入，JCS Canonical JSON)          │
│      - 仅收录满足 Freshness、Quality、Temporal 准入资格的事实                    │
│      - 注入不可变 PromptSpec 模板，生成全文保全                                  │
│      - 严格计算 effective_input_hash = SHA256(JCS(InputPayload))               │
└──────────────────────────────────────┬─────────────────────────────────────────┘
                                       │ 隔离红线 (STEP 3 边界在此截止！)
  ═════════════════════════════════════╪═════════════════════════════════════════
                                       │ [STRICTLY FORBIDDEN IN STEP 3]
                                       ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│           Cognition & Inference Layer (Step 4 ~ Step 6 / LLM Runtime)          │
│      - LLM API 调用 (DEEPSEEK / OPENAI) ── [PROHIBITED]                        │
│      - Hypothesis Generation / Assertion AST ── [PROHIBITED]                   │
│      - Trading Decision / Order Signal ── [PROHIBITED]                         │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 严格沙箱隔离保障（Sandbox Guarantees）
1. **代码包隔离**：Step 3 的全部抽取器、转换器与校验器均封装于 `backend/app/cognition/observation/` 与 `backend/app/cognition/input/` 纯逻辑包中；
2. **运行环境隔离**：所有 Step 3 逻辑仅在单元测试套件 `backend/tests/test_cognition_step3_sandbox.py` 及只读调试 API 下运行，**零切入真实交易进程，零接入调度定时任务**；
3. **真实 LLM 零调用**：Step 3 仅测试“事实是否正确投射进 Prompt 字符串及 Hash 是否精确无误”，禁止任何外部 HTTP 调用大模型 API；
4. **真实交易零接触**：严禁向订单、撮合、账户持仓等模块输出任何数据。

### 1.3 明确不做清单（Explicit Non-Goals）
- **NON-GOAL 1**：不进行任何 LLM 推理生成；
- **NON-GOAL 2**：不生成任何交易假说（Hypothesis）；
- **NON-GOAL 3**：不执行断言 AST 验证（Assertion Validation）；
- **NON-GOAL 4**：不输出买卖推荐、仓位建议或信号排序；
- **NON-GOAL 5**：不开发 Replay / Diff Engine（严格封存在 Phase 2B）；
- **NON-GOAL 6**：不修改既有冻结的 G0/G1/G3 及 28/29 号设计单基线。

---

## 二、 ObservationSnapshot 法定数据契约（Canonical Fact Schema）

`ObservationSnapshot` 是对物理世界观测切片的确定性快照。它必须是自包含的、不可变的、具备完备时间与血缘维度的结构化实体。**严禁出现任何“以后再定义”的占位字段。**

### 2.1 顶级实体结构（ObservationSnapshot Schema v1.0）

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ObservationSnapshot",
  "type": "object",
  "required": [
    "snapshot_id",
    "schema_version",
    "observation_window",
    "snapshot_time",
    "market_date",
    "stage",
    "overall_quality",
    "fact_items",
    "degraded_fields",
    "source_manifest",
    "snapshot_fingerprint"
  ],
  "properties": {
    "snapshot_id": {
      "type": "string",
      "description": "唯一快照ID，格式: obs_{market_date}_{stage}_{UUID前8位}"
    },
    "schema_version": {
      "type": "string",
      "enum": ["1.0.0"]
    },
    "market_date": {
      "type": "string",
      "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
      "description": "所观测的交易日 (YYYY-MM-DD)"
    },
    "stage": {
      "type": "string",
      "enum": ["PRE_MARKET", "MORNING_AUCTION", "MIDDAY", "POST_CLOSE", "NIGHT_REVIEW"],
      "description": "推演业务阶段"
    },
    "observation_window": {
      "type": "object",
      "required": ["window_start", "window_end", "window_type"],
      "properties": {
        "window_start": {"type": "string", "description": "观测窗口起始时刻 (ISO-8601 或 HH:MM:SS)"},
        "window_end": {"type": "string", "description": "观测窗口截止时刻 (ISO-8601 或 HH:MM:SS)"},
        "window_type": {"type": "string", "enum": ["POINT_IN_TIME", "ACCUMULATIVE_RANGE"]}
      }
    },
    "snapshot_time": {
      "type": "string",
      "format": "date-time",
      "description": "快照对象在内存中被封包的物理时钟时间 (ISO-8601 UTC+8)"
    },
    "overall_quality": {
      "type": "string",
      "enum": ["FULL", "PARTIAL", "DEGRADED", "INVALID"],
      "description": "本快照整体综合质量"
    },
    "fact_items": {
      "type": "array",
      "description": "按 fact_key 严格 UTF-16 字典序排列的事实项列表",
      "items": {
        "$ref": "#/$defs/FactItem"
      }
    },
    "degraded_fields": {
      "type": "array",
      "items": {"type": "string"},
      "description": "所有非 AVAILABLE 状态的事实键名列表，供审计快速索引"
    },
    "source_manifest": {
      "type": "array",
      "description": "涉及的所有底层数据源元数据凭证",
      "items": {
        "$ref": "#/$defs/SourceCredential"
      }
    },
    "snapshot_fingerprint": {
      "type": "string",
      "pattern": "^[a-f0-9]{64}$",
      "description": "SHA-256(JCS(ObservationSnapshot 去除 snapshot_fingerprint))"
    }
  },
  "$defs": {
    "FactItem": {
      "type": "object",
      "required": [
        "fact_id",
        "fact_key",
        "fact_type",
        "event_time",
        "observed_time",
        "ingestion_time",
        "effective_time",
        "status",
        "freshness",
        "source",
        "source_record_id",
        "payload",
        "provenance",
        "fact_fingerprint"
      ],
      "properties": {
        "fact_id": {"type": "string", "description": "事实项全局唯一UUID"},
        "fact_key": {"type": "string", "description": "规范化业务键 (如 indices.sh000001, breadth.limit_up_count)"},
        "fact_type": {
          "type": "string",
          "enum": ["INDEX_QUOTE", "MARKET_BREADTH", "LIMIT_UP_POOL", "HIGH_TIER_STAT", "NEWS_BULLETIN", "OVERNIGHT_MACRO", "SETTLEMENT_PRICE"]
        },
        "event_time": {"type": "string", "description": "物理世界事实发生的真实时间 (如交易所成交撮合时间 09:25:00)"},
        "observed_time": {"type": "string", "description": "系统网络I/O抓取到该事实的时刻"},
        "ingestion_time": {"type": "string", "description": "该事实持久化落入本地数据库的时刻"},
        "effective_time": {"type": "string", "description": "该事实在业务规则上生效的起始时间"},
        "status": {
          "type": "string",
          "enum": ["AVAILABLE", "EMPTY", "STALE", "TIMEOUT", "ERROR", "MISSING", "INCONCLUSIVE"]
        },
        "freshness": {
          "type": "string",
          "enum": ["REALTIME", "DELAYED", "STALE", "HISTORICAL_REPLAY", "UNKNOWN"]
        },
        "source": {"type": "string", "description": "最终事实提供者 (cls / sina / eastmoney / baostock / local_snapshot)"},
        "source_record_id": {"type": "string", "description": "底层事实在源表中的主键ID (如 market_daily_snapshot.id)"},
        "payload": {
          "type": ["object", "null"],
          "description": "JCS规范化事实正文载荷；当 status!=AVAILABLE 且无有效数据时为 null 或空结构，严禁假0填充"
        },
        "provenance": {
          "type": "object",
          "required": ["original_source", "fallback_occurred", "fallback_reason", "trace_id"],
          "properties": {
            "original_source": {"type": "string"},
            "fallback_occurred": {"type": "boolean"},
            "fallback_reason": {"type": ["string", "null"]},
            "trace_id": {"type": "string"}
          }
        },
        "fact_fingerprint": {"type": "string", "pattern": "^[a-f0-9]{64}$"}
      }
    },
    "SourceCredential": {
      "type": "object",
      "required": ["source_name", "fetch_status", "latency_ms", "records_count"],
      "properties": {
        "source_name": {"type": "string"},
        "fetch_status": {"type": "string"},
        "latency_ms": {"type": "number"},
        "records_count": {"type": "integer"}
      }
    }
  }
}
```

---

## 三、 EffectiveInferenceInput 法定数据契约与准入资格网（Fact Eligibility）

### 3.1 核心铁律：禁止“有值就用”
大模型作为黑盒概率推理机，极易受过期、脏污或假零数据的误导。因此，`EffectiveInferenceInput` **绝对不是 `ObservationSnapshot` 的无脑全量复制**，而是经过**法定资格准入网（Fact Eligibility Gate）**筛选后的安全合规推理视图。

### 3.2 事实准入准出规则集（Eligibility Rules）

| 规则维度 | 规则名称 | 判定逻辑与强制动作 |
| :--- | :--- | :--- |
| **Inclusion Rule**<br>（准入规则） | `RULE-ELIG-01` | **只有同时满足以下条件的事实项方可作为有效数据注入 Context**：<br>1. `status == AVAILABLE`；<br>2. `freshness in (REALTIME, DELAYED)`；<br>3. `payload is not None` 且符合对应 Schema；<br>4. 事实的时间戳符合所处 stage 的时间窗口。 |
| **Exclusion Rule**<br>（准出与剔除规则） | `RULE-ELIG-02` | **以下数据一律禁止作为正常业务数值注入**：<br>1. `status in (ERROR, TIMEOUT, MISSING, INCONCLUSIVE)`；<br>2. 带有未捕获异常或解析残损的 payload；<br>3. `event_time` 晚于当前 `snapshot_time`（未来函数，直接一票否决）。 |
| **Stale Rule**<br>（陈旧数据规则） | `RULE-ELIG-03` | 当 `status == STALE` 或 `freshness == STALE` 时（如 Baostock 降级缓存或非时段回放）：<br>1. **严禁混作实时数据注入**；<br>2. 必须剥离其实时有效性，将其移入 `stale_warnings` 专区；<br>3. 显式附加警示文案：`[STALE FACT: 来源为本地历史缓存/非当时数据，距当前观测延迟 X 秒，仅供基准参考]`。 |
| **Missing Rule**<br>（缺失数据规则） | `RULE-ELIG-04` | 当某关键维度（如微盘股、竞价额）`status in (EMPTY, MISSING)` 时：<br>1. **严禁零填充 (Zero-Filling Forbidden)**（如不能将缺失的竞价额记为 0.00 亿）；<br>2. 必须在推理输入中显式标记为 `null / NOT_AVAILABLE`；<br>3. 注入显式元数据：`[DATA_DEFICIENCY: 维度 X 缺失，严禁作出该维度的方向性确定推论]`。 |
| **Conflict Rule**<br>（多源冲突决策） | `RULE-ELIG-05` | 当同一指标存在双源（如 CLS 快讯 vs Sina 快讯，或东财指数 vs 新浪指数）：<br>1. 严格按照预设优先顺序采信（主源可用采信主源；主源失败备源接管）；<br>2. 若双源均存活且数值冲突超过阈值（如涨跌幅相差 > 0.5%），强制标记该指标为 `INCONCLUSIVE` 并记录分歧告警，两方数值均作为冲突事实原样列出供审计。 |
| **Deterministic Ordering**<br>（确定性排序） | `RULE-ELIG-06` | 输入 Context 中的所有事实列表、指标键值对，在生成最终渲染字符串前，必须**严格按照键名 UTF-16 代码单元字典序（RFC 8785 规则）排序**，消除任何因 Python 字典无序或数据库查询返回顺序不同导致的哈希漂移。 |

### 3.3 EffectiveInferenceInput 数据契约 Schema (v1.0)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "EffectiveInferenceInput",
  "type": "object",
  "required": [
    "input_id",
    "snapshot_id",
    "prompt_id",
    "prompt_version",
    "prompt_hash",
    "model_provider",
    "model_name",
    "model_version",
    "inference_config",
    "admitted_facts",
    "suppressed_facts",
    "data_quality_warnings",
    "rendered_system_prompt",
    "rendered_user_prompt",
    "effective_input_hash"
  ],
  "properties": {
    "input_id": {"type": "string"},
    "snapshot_id": {"type": "string"},
    "prompt_id": {"type": "string"},
    "prompt_version": {"type": "string"},
    "prompt_hash": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "model_provider": {"type": "string"},
    "model_name": {"type": "string"},
    "model_version": {"type": "string"},
    "inference_config": {
      "type": "object",
      "required": ["temperature", "top_p", "seed"],
      "properties": {
        "temperature": {"type": "number", "maximum": 0.2},
        "top_p": {"type": "number"},
        "seed": {"type": "integer"}
      }
    },
    "admitted_facts": {
      "type": "object",
      "description": "通过资格审查的有效业务事实，字典序键值对"
    },
    "suppressed_facts": {
      "type": "array",
      "description": "被排除在推理之外的事实及被排除原因",
      "items": {
        "type": "object",
        "required": ["fact_key", "status", "rejection_rule", "reason"],
        "properties": {
          "fact_key": {"type": "string"},
          "status": {"type": "string"},
          "rejection_rule": {"type": "string"},
          "reason": {"type": "string"}
        }
      }
    },
    "data_quality_warnings": {
      "type": "array",
      "items": {"type": "string"},
      "description": "注入 Prompt 的硬性数据质量警示清单"
    },
    "rendered_system_prompt": {"type": "string", "description": "渲染后的最终 System Prompt 字符全文"},
    "rendered_user_prompt": {"type": "string", "description": "注入事实与质量警示后的最终 User Prompt 字符全文"},
    "effective_input_hash": {
      "type": "string",
      "pattern": "^[a-f0-9]{64}$",
      "description": "SHA256(JCS({rendered_system_prompt, rendered_user_prompt, prompt_hash, admitted_facts_fingerprint}))"
    }
  }
}
```

---

## 四、 物理与业务状态语义冻结（Status Semantics Matrix）

系统正式冻结 7 大物理与业务状态语义，彻底废除任何“通过 None/空字符/0/假默认值抹平状态”的非规范编码。

### 4.1 七大状态严正定义与处理矩阵

| 状态枚举 | 物理产生条件 | 允许入快照 | 允许入推理输入 | 参与后续断言 | 原始状态保留 | 允许降级 | 降级审计要求 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **`AVAILABLE`** | 事实源正常响应，数据完整，解析校验 100% 通过。 | **YES** | **YES** | **YES** | 是 | 否 | 正常审计，记录物理延迟与条数。 |
| **`EMPTY`** | 接口通信正常（HTTP 200），但物理事实池在客观上为 0（如盘中零涨停、非交易日无快讯）。 | **YES** | **YES** (作为0事实) | **YES** | 是 | 否 | 明确标注 `EMPTY`，**严禁等同于 ERROR**。业务语义为“客观存在且数量为0”。 |
| **`STALE`** | 外部接口超时或中断，系统回退读取了本地历史持久化快照/缓存。 | **YES** | **RESTRICTED**<br>(仅入警示区) | **CONDITIONAL**<br>(加注陈旧性) | 是 | 是 | 必须记录原始陈旧时间、距今延迟秒数及 `fallback_used=True`。 |
| **`TIMEOUT`** | 外部提供商网络请求超出物理硬超时限制（如 Baostock > 3.0s, CLS > 5.0s）。 | **YES** | **NO**<br>(强行准出) | **NO** | 是 | 是 (降级至STALE) | 记录物理超时耗时、尝试次数、熔断器计数；**严禁将 TIMEOUT 伪造为数值 0**。 |
| **`ERROR`** | HTTP 状态码异常（4xx/5xx）、底层驱动抛出异常或数据协议完全损坏。 | **YES** | **NO**<br>(强行准出) | **NO** | 是 | 是 (降级至备源) | 记录具体异常类名、堆栈摘要与 HTTP 状态码；**严禁吞没异常返回空结果**。 |
| **`MISSING`** | 预期应有的指标物理上缺失（如某冷门股票停牌导致缺失开盘竞价撮合数据）。 | **YES** | **NO**<br>(强行准出) | **INCONCLUSIVE** | 是 | 否 | 记录键名缺失；断言引擎触达此键时，**强制产出 INCONCLUSIVE，严禁伪造为 FALSE**。 |
| **`INCONCLUSIVE`** | 多源冲突不可调和、数据时序倒挂，或断言依赖的事实未被满足。 | **YES** | **NO**<br>(强行准出) | **NO** | 是 | 否 | 记录冲突各方的原始取值、时间戳与分歧差值，不可下确定性结论。 |

### 4.2 核心状态五大不等式铁律
在所有 Step 3 的代码与数据流中，必须严格恪守以下五个不等式，任何违反的单元测试直接判死刑：
1. **`EMPTY ≠ ERROR`**：空数据是客观事实（市场没涨停也是一种事实），错误是通道故障，两者在审计与推理输入中严禁混淆；
2. **`TIMEOUT ≠ 0`**：请求超时代表“未知”，绝不代表“成交量为0”或“跌幅为0”；
3. **`STALE ≠ AVAILABLE`**：昨天的数据即使再精确，也是陈旧事实，绝不能当成今天的实时输入；
4. **`MISSING ≠ FALSE`**：没有证据证明某事发生，不等于证明某事没有发生；
5. **`INCONCLUSIVE ≠ FALSE`**：推导证据不足必须输出“无法判定”，严禁强行断言为假。

---

## 五、 四维时间语义契约（Four-Dimensional Time Semantics）

为彻底消灭时间穿梭、未来函数与时钟混淆，Step 3 严格锁定四维解耦时间语义：

```text
 物理世界真实发生                  系统抓取到内存                  物理写入数据库落盘                业务生效或截止窗口
        │                               │                               │                               │
        ▼                               ▼                               ▼                               ▼
┌──────────────┐               ┌────────────────┐              ┌────────────────┐              ┌────────────────┐
│  event_time  │ ────────────> │  observed_time │ ───────────> │ ingestion_time │ ───────────> │ effective_time │
└──────────────┘               └────────────────┘              └────────────────┘              └────────────────┘
```

### 5.1 四维时间权威定义表

| 时间维度 | 定义与产生源 | 权威度 / 可信度 | 决定职能 | 允许为空 | 时钟异常处理规则 |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **`event_time`** | 交易所撮合时点、新闻发布时点。由交易所、新闻源物理产生。 | **最高（客观事实）** | 决定 **Temporal Eligibility**（事实是否属于观测窗口）。 | **否** | **严禁伪造**：若数据源未提供 `event_time`，必须标记为 `TIME_CORRUPTED` 并拒入，严禁用本地 `datetime.now()` 冒充！ |
| **`observed_time`** | 后端服务发起 I/O 读取并成功解析该事实的本地单调时钟时刻。 | **次高（系统观察）** | 决定 **Freshness**（新鲜度度量：`observed_time - event_time`）。 | **否** | 使用本机高精度时钟生成。 |
| **`ingestion_time`** | 该事实落入 SQLite / PostgreSQL 数据库行中的 `created_at`。 | **系统存证（落盘审计）** | 决定 **WORM 存证序与回放基线**。 | **否** | 数据库 `CURRENT_TIMESTAMP` 自动生成；**严禁将 `ingestion_time` 当作 `event_time`**。 |
| **`effective_time`** | 业务契约规定的该事实法定生效时间（如隔夜外盘结算价在次日 09:15 生效）。 | **业务规则定义** | 决定 **推理规则是否生效**。 | **是** | 若无特殊业务时限，默认与 `event_time` 相同。 |

### 5.2 时序异常防御机制
1. **未来时钟防御（Future Event Defense）**：若 `event_time > observed_time + 30s`（允许30秒网络时钟容差），立即触发 `FUTURE_EVENT_VIOLATION`，事实直接阻断，强制置为 `ERROR`；
2. **时钟回拨防御（Monotonic Time Guard）**：同一数据源下连续事实的 `event_time` 若出现逆向倒挂，记录 `OUT_OF_ORDER_EVENT` 警告，保持物理原貌，严禁重写时间戳；
3. **统一时区格式**：内存与持久化全量统一采用 `Asia/Shanghai (UTC+8)`，规范字符串表示为 `YYYY-MM-DDTHH:MM:SS.sss+08:00`，彻底消灭本地时区漂移。

---

## 六、 全链路来源血缘追溯体系（Source Lineage & Provenance）

每个进入认知快照的事实，必须携带可回溯至物理报文的六级血缘链条：

```text
 Level 1: 物理源头 (Source) ── 例如: CLS (财联社快讯接口)
    │
 Level 2: 源头报文ID (Source Record ID) ── 例如: roll_news_id=1790776430
    │
 Level 3: 采集物理状态 (Acquisition Status) ── 包含: HTTP 200, 耗时 124ms, 签名合法
    │
 Level 4: 事实快照投影 (ObservationSnapshot) ── 落入 FactItem[fact_id='fact_cls_092501']
    │
 Level 5: 准入资格筛选 (EffectiveInferenceInput) ── 准入通过, 注入 admitted_facts.news
    │
 Level 6: 认知账本锚定 (CognitionRecord) ── 绑定至 sequence_id=42, record_hash=...
```

### 6.1 主备切换（Fallback）与降级全息审计
当发生主备容灾切换（如 CLS 挂起 -> 备源 Sina 顶替）时，系统**严禁只保留最终的 Sina 数据**，必须在 `Provenance` 中保全双向痕迹：
```json
{
  "fact_key": "news.macro_bulletin",
  "source": "sina",
  "source_record_id": "sina_doc_991823",
  "provenance": {
    "primary_source": "cls",
    "primary_attempt_status": "TIMEOUT",
    "primary_error_detail": "asyncio.TimeoutError after 5000ms",
    "fallback_occurred": true,
    "fallback_source": "sina",
    "fallback_reason": "PRIMARY_SOURCE_UNAVAILABLE",
    "fallback_latency_ms": 312,
    "trace_id": "trace_20260930_091500_001"
  }
}
```

---

## 七、 RFC 8785 JCS 规范化与指纹/哈希计算契约

Step 3 的一切哈希运算必须无缝承接 Step 2 已经验证通过的纯 Python RFC 8785 JCS 引擎（[`app/cognition/jcs.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/jcs.py) 与 [`app/cognition/hash_chain.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/cognition/hash_chain.py)），严禁引入第三方未经沙箱审查的序列化库。

### 7.1 哈希计算对象与公式定义

| 哈希标识 | 算法 | 参与规范化计算的输入字段（Canonical Payload） | 排序与空值处理规则 |
| :--- | :--- | :--- | :--- |
| **`fact_fingerprint`**<br>(单个事实项指纹) | `SHA-256` | `JCS({fact_key, event_time, status, source, payload, provenance})` | 严格按字典序排序；`payload=null` 显式保留；`status` 与 `provenance` **必须**参与计算。 |
| **`snapshot_fingerprint`**<br>(快照整体指纹) | `SHA-256` | `JCS(ObservationSnapshot 排除 snapshot_fingerprint 自身)` | 包含全量 `fact_items`（已按 `fact_key` 排序）、`observation_window`、`overall_quality` 及 `source_manifest`。 |
| **`effective_input_hash`**<br>(生效推理输入哈希) | `SHA-256` | `JCS({prompt_id, prompt_version, prompt_hash, model_provider, model_name, inference_config, admitted_facts, rendered_system_prompt, rendered_user_prompt})` | **双重锁定**：既锁定 Prompt 模板与推理模型配置，又锁定渲染后的输入全文与合格事实字典。 |

### 7.2 规范化细节铁律
1. **浮点数格式**：严格遵循 IEEE 754 规则（零表示为 `0` 而非 `0.0`，无多余尾随0，指数小写 `e`）；
2. **字符集**：必须为纯 UTF-8 编码，字符转义严格对齐 RFC 8785；
3. **Schema Version 锁定**：`schema_version` 字符串必须作为 Canonical Payload 顶级字段参与哈希，升级版本立即产生全新哈希。

---

## 八、 M1 / M2 / M4 / M5 / S4 事实到认知输入逐项映射表

本节对系统当前各基础事实源到 Cognition 的抽取映射进行逐项穷尽定义：

| 模块 | 业务事实项 | 物理落盘表及主键 | `event_time` 提取源 | 状态判定条件 | 准入 EffectiveInput 规则 | 缺失或异常时行为 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **M1** | **指数收盘事实**<br>(上证/深证/创业板/科创) | `market_daily_snapshot`<br>`snapshot_type='EOD_CLOSE'`<br>`indices_snapshot` 字段 | 交易所收盘时间 `15:00:00` | 快照存在且点位 > 0 为 `AVAILABLE`；依赖缓存为 `STALE`。 | 允许。注入 `admitted_facts.indices`。 | 缺失时尝试从当日复盘表回放，若无则置 `MISSING`，阻断大盘方向推演。 |
| **M1** | **市场量能与涨跌家数** | `daily_review.market_overview`<br>及六维状态 D6 | 交易所收盘时间 `15:00:00` | 成交额 > 0 且两市总和合法为 `AVAILABLE`。 | 允许。注入 `admitted_facts.breadth`。 | 缺失时置 `MISSING`，禁止假定为平盘或0成交。 |
| **M1** | **连板高度与涨停池** | `daily_review.limit_up_analysis` | 交易所收盘时间 `15:00:00` | 正常解析为 `AVAILABLE`；涨停为0家为 `EMPTY`。 | 允许。若 `EMPTY` 注入数量为0事实。 | 若解析损坏置 `ERROR`，移入 `suppressed_facts`。 |
| **M2** | **隔夜外盘与宏观**<br>(美股/A50/美元指数) | `premarket_briefing.overnight_summary` | 外盘结算或 08:30 抓取时刻 | 标的齐备为 `AVAILABLE`；部分缺失为 `PARTIAL`。 | `AVAILABLE` 全量注入；`PARTIAL` 注入可用部分并注警示。 | 缺失时标记外盘盲区，提示外部宏观不可靠。 |
| **M4** | **早盘 09:25 竞价指数** | `market_daily_snapshot`<br>`snapshot_type='AUCTION_0925'`<br>`indices_snapshot` 字段 | 物理撮合时点 `09:25:00` | 处于 09:25~09:30 为 `AVAILABLE`；离线自愈回放为 `STALE`。 | 仅在 stage==MORNING_AUCTION 时准入；若非实时加注 `STALE` 警示。 | 非竞价时段绝不将盘中价格误当竞价价格。 |
| **M4** | **早盘两市竞价金额** | `auction_report.index_open_data` -> `total_bidding_amount_yi` | 物理撮合时点 `09:25:00` | 金额数值存在为 `AVAILABLE`。 | 允许。与前日全天总额计算竞价量比。 | 缺失时严禁填 0 亿，置 `MISSING`。 |
| **M4** | **高标开盘溢价生态** | `auction_report.high_open_stats` | 物理撮合时点 `09:25:00` | 高标统计存在为 `AVAILABLE`；无昨日连板为 `EMPTY`。 | 允许。注入最高板开盘承接情况。 | 若昨日无高标则 `EMPTY`（正常事实）。 |
| **M5** | **标的收盘结算价** | `market_settlement_cache` | 结算归档日 `15:00:00` | 本地有效为 `AVAILABLE`；超时读旧缓存为 `STALE`。 | `AVAILABLE` 准入；`STALE` 限制性准入并附带时效标签。 | 彻底超时且无缓存置 `TIMEOUT`，拒入。 |
| **S4** | **财经滚动快讯流** | `market_news` (source: cls / sina) | 快讯物理发布时点 (秒级时间戳) | CLS 主源成功为 `AVAILABLE`；Sina 备源成功为 `AVAILABLE (FALLBACK)`。 | 准入前 15 条重要快讯；按重要度与时间倒序。 | 双源均挂起时置 `ERROR`，快讯事实集合为空并告警。 |

---

## 九、 负向异常与混沌穿透测试矩阵（Failure & Negative Test Matrix - 15 Scenarios）

为彻底贯彻“先设计失败路径”的工程铁律，Step 3 设立 15 大负向异常单测场景，**全部纳入自动化验收闸门**：

| 编号 | 测试场景（Attack / Fault Vector） | 模拟手段与注入方法 | 预期状态流转 | 预期准入与快照结果 | 判定通过标准 (Assertion) |
| :---: | :--- | :--- | :--- | :--- | :--- |
| **F-01** | **Source Timeout**<br>(数据源物理超时) | Mock 数据源延时 > 5.0s，触发硬超时。 | `PENDING -> TIMEOUT` | 快照记录 `TIMEOUT`，`EffectiveInput` 拒绝准入，移入 `suppressed_facts`。 | `item.status == "TIMEOUT"`<br>`"total_bidding_amount_yi" not in admitted_facts` |
| **F-02** | **Source Empty**<br>(数据源空数据) | Mock 返回合法的空列表 `[]`（如市场零涨停）。 | `PENDING -> EMPTY` | 快照记录 `EMPTY`，`EffectiveInput` 准入为“数量为0”。 | `item.status == "EMPTY"`<br>`admitted_facts["limit_up_count"] == 0` |
| **F-03** | **Source Error**<br>(数据源崩溃/500) | Mock 抛出 `HTTPError(500)` 或解析严重畸变。 | `PENDING -> ERROR` | 快照记录 `ERROR` 与错误信息，`EffectiveInput` 严厉拒入。 | `item.status == "ERROR"`<br>`overall_quality in ("DEGRADED", "INVALID")` |
| **F-04** | **Stale Snapshot**<br>(陈旧/离线回放数据) | 注入带有 `Freshness.STALE` 标志的持久化历史快照。 | `PENDING -> STALE` | 快照记录 `STALE`，`EffectiveInput` 隔离至 `stale_warnings` 专区。 | `item.freshness == "STALE"`<br>`len(data_quality_warnings) > 0` |
| **F-05** | **Missing Snapshot**<br>(快照物理缺失) | 查询不存在的日期或未生成快照的窗口。 | `PENDING -> MISSING` | 整体快照标记 `INVALID`，推演直接中止，拒绝生成 `EffectiveInput`。 | 抛出 `SnapshotNotFoundError`<br>阻止下游无效推演 |
| **F-06** | **Conflicting Sources**<br>(多源事实冲突) | Mock CLS 称大盘跌 1%，Sina 称大盘涨 1%。 | `AVAILABLE -> INCONCLUSIVE` | 针对该指标置为 `INCONCLUSIVE`，双向值列入冲突记录，拒入正式计算。 | `item.status == "INCONCLUSIVE"`<br>`"conflict_details" in item.provenance` |
| **F-07** | **Duplicate Observation**<br>(重复事实观测注入) | 人为注入两条相同 `fact_key` 的事实。 | `CONFLICT -> DEDUPLICATED` | 依据 `observed_time` 最新原则或首个原则排他去重，绝不产生无序覆盖。 | `len([f for f in items if f.key == k]) == 1` |
| **F-08** | **Out-of-Order Event**<br>(事实时间倒流乱序) | 连续两批快讯中，后到达的事实其 `event_time` 早于前一个。 | `WARNING -> REORDERED` | 触发时序告警，Canonical 序列化前强制按物理时戳重新重排。 | 快照内事实序列严格保全时序正确性 |
| **F-09** | **Future Event Time**<br>(未来时间事实入侵) | 伪造事实的 `event_time` 大于当前时间 1 小时。 | `REJECTED -> ERROR` | **一票否决**：直接抛出 `FutureEventViolation`，判定事实受污染。 | `item.status == "ERROR"`<br>`item.payload is None` |
| **F-10** | **Invalid Timestamp**<br>(残损/非标准时间戳) | 注入无法解析的时间格式字符串（如 `"invalid_time"`）。 | `REJECTED -> ERROR` | 时间解析器安全拦截，标记 `TIME_CORRUPTED`，拒绝使用系统时间填充。 | 严禁静默 fallback 为 `now()` |
| **F-11** | **Malformed Payload**<br>(报文正文格式破坏) | 注入无法反序列化为 JSON 的二进制或破坏报文。 | `REJECTED -> ERROR` | 异常严密封闭于该指标项内部，不引发整个系统 Crash。 | 系统平稳降级，记录解析错误日志 |
| **F-12** | **Fingerprint Mismatch**<br>(事实篡改/指纹不符) | 生成快照后，人为在内存修改某个字段的值。 | `CORRUPTED -> TAMPERED` | 指纹验真函数计算 `SHA256(JCS(item))` 与原指纹不符，直接报警。 | `verify_fingerprint(item) is False` |
| **F-13** | **Schema Version Mismatch**<br>(版本协议不兼容) | 传入带有 `schema_version='0.9.0'` 的历史快照。 | `REJECTED -> INCOMPATIBLE`| 架构版本网关拒绝直接合流，必须经过适配迁移器。 | 抛出 `SchemaVersionMismatchError` |
| **F-14** | **Fallback Activation**<br>(主源故障，备源激活) | Mock CLS 故障，验证 Sina 备源毫秒级接管。 | `FALLBACK_OK` | 最终状态为 `AVAILABLE`，但 `provenance.fallback_occurred == True`。 | `item.source == "sina"`<br>`item.provenance["fallback_occurred"] is True` |
| **F-15** | **Fallback Failure**<br>(主备双源全灭) | Mock CLS 与 Sina 同时抛出网络不可达异常。 | `DUAL_FAILED -> ERROR` | 状态定格为 `ERROR`，记录双源全灭日志，彻底杜绝伪造数据。 | `item.status == "ERROR"`<br>`item.payload is None` |

---

## 十、 确定性保障规则（Determinism Rules）

系统必须达成以下数学级确定性准则：

> **`Determinism Axiom`**：  
> 在任意机器、任意操作系统（Windows/Linux/macOS）以及任意 Python 3.12 次要版本上，给定完全相同的物理事实输入、相同的 Prompt 模板和相同的模型配置，必须产出**逐字节完全一致（Bit-Exact Identical）**的 `ObservationSnapshot` 规范化 JSON 串与 `effective_input_hash`。

为保障该公理，代码必须实现：
1. **纯纯函数转换（Pure Functional Transformation）**：从原始事实生成快照的函数为纯函数，除显式传入的 Mock 时钟外，严禁在函数内部调用 `datetime.now()`、`uuid.uuid4()` 等不确定性源；
2. **字典序强制排序**：所有字典与列表在入 Hash 前，必须经过 `jcs.canonicalize()` 或显式字典序排序；
3. **浮点数舍入收敛**：所有计算出的浮点数（如量能比、涨跌幅）必须统一使用 `round(x, 4)` 显式截断，彻底消除不同硬件 FPU 架构引起的微小精度差异。

---

## 十一、 数据库与迁移影响分析（Database & Migration Impact）

### 11.1 零破坏现有 Cognition v2 基线表
Step 1 建立的 `cognition_record`、`cognition_prompt_spec`、`cognition_chain_state` 及 Track A 建立的 `market_daily_snapshot` 已完全覆盖了 Step 3 的存储需求：
- `cognition_record.observation_snapshot`（Text 物理列）：直接存储 Step 3 产出的 JCS 规范化字符串全文；
- `cognition_record.effective_input_hash`（String(64) 列）：直接存储 Step 3 产出的 64 位 SHA-256 哈希；
- `cognition_record.rendered_system_prompt` 与 `rendered_user_prompt`：完整接收 Step 3 渲染的全文。

### 11.2 是否需要新增数据表？
**结论：不需要新增任何物理表，零 Alembic 破坏！**
Step 3 在架构上属于**计算转换与投影层（Transformation & Projection Engine）**，其产物直接作为不可变值对象嵌入 `CognitionRecord` 中持久化，不需单独建表，从而完全规避数据库迁移风险，保持 Alembic 基线版本 `d440da877b6a` 干净稳定。

---

## 十二、 API 契约与沙箱端点规范（API & Sandbox Endpoints）

Step 3 的全部外部交互严格限制在**调试与只读沙箱端点**下，前缀统一为 `/api/v1/sandbox/cognition/`：

```text
1. POST /api/v1/sandbox/cognition/observation-snapshot/extract
   - 作用：传入指定 date 和 stage，执行纯内存事实抽取，返回 ObservationSnapshot 规范化 JSON
   - 权限：只读计算，零数据库写入，零 LLM 调用

2. POST /api/v1/sandbox/cognition/effective-input/render
   - 作用：传入 ObservationSnapshot 与 PromptId，执行资格过滤与 Prompt 渲染，返回 EffectiveInferenceInput
   - 权限：只读计算，返回有效载荷与 effective_input_hash

3. POST /api/v1/sandbox/cognition/verify-fingerprint
   - 作用：传入任意 Snapshot 或 Input 载荷，验证 JCS 规范化指纹是否吻合
   - 权限：数学纯函数验真
```

---

## 十三、 实施步骤与测试计划（Implementation & Verification Plan）

### 13.1 四阶段受控实施路线（Sub-Steps）

```text
┌────────────────────────────────────────────────────────┐
│ Sub-Step 3.1: 规范化数据模型与 JCS 序列化器           │
│ • 编写 ObservationSnapshot / FactItem Pydantic/DataClass│
│ • 编写 EffectiveInferenceInput 契约模型                │
│ • 实现事实项 JCS 规范化与指纹计算器                     │
├────────────────────────────────────────────────────────┤
│ Sub-Step 3.2: 事实抽取器与多源适配网关 (Extractors)    │
│ • 封装 M1/M2/M4/M5/S4 专用抽取适配器                   │
│ • 实现四维时间戳对齐与 DataStatus 映射器               │
│ • 实现主备降级血缘 Provenance 生成器                   │
├────────────────────────────────────────────────────────┤
│ Sub-Step 3.3: 资格过滤网与 Prompt 安全渲染器           │
│ • 实现 6 大准入准出规则引擎 (Eligibility Engine)        │
│ • 实现多源冲突消解与数据质量警示注入器                 │
│ • 接入 PromptSpec 模板，完成 UTF-16 字典序渲染与哈希固化│
├────────────────────────────────────────────────────────┤
│ Sub-Step 3.4: 15 项负向混沌单测与沙箱验收              │
│ • 编写 tests/test_cognition_step3_sandbox.py          │
│ • 100% 覆盖 F-01 ~ F-15 异常穿透矩阵                  │
│ • 验证跨平台 Bit-Exact 确定性复现                      │
└────────────────────────────────────────────────────────┘
```

### 13.2 交付验收物清单
1. 源码模块：
   - `backend/app/cognition/observation/models.py`
   - `backend/app/cognition/observation/extractor.py`
   - `backend/app/cognition/input/eligibility.py`
   - `backend/app/cognition/input/renderer.py`
2. 测试套件：
   - `backend/tests/test_cognition_step3_sandbox.py`（预期通过率 100%）
3. 结项报告：
   - `开发文档/35-Phase-2A-Step3-实施状态与Sandbox验收报告.md`

---

## 十四、 与既有冻结基线（28/29/G0/G1/G3）一致性检查表

| 序号 | 检查项 | 既有冻结基线要求 | Step 3 实施方案对齐状态 | 对齐证明与依据 |
| :---: | :--- | :--- | :---: | :--- |
| 1 | **G0/G1 决策基线** | 客观真实，严禁交易造假与未来函数。 | **100% 对齐** | 第 5.2 节实施未来事件一票否决；第 4.2 节禁止假零填充。 |
| 2 | **G3 架构基线** | 模块解耦，清晰分层。 | **100% 对齐** | 严格划定事实层与认知层边界，Step 3 零业务侵入。 |
| 3 | **28号设计单 3.2** | `ObservationSnapshot` 输入快照规范。 | **100% 对齐** | 指数、量能、梯队、外盘、快讯要素全覆盖，Schema 逐字段匹配。 |
| 4 | **28号设计单 3.3** | `EffectiveInferenceInput` 显式保全。 | **100% 对齐** | 全量保全渲染后 System/User Prompt，公式为 SHA256(JCS(...))。 |
| 5 | **29号决议单 约束2** | `CognitionRecord` 唯一聚合根。 | **100% 对齐** | 快照与生效输入最终均归口至 `CognitionRecord`，无孤立实体。 |
| 6 | **29号决议单 约束3** | 所有事实输入必须 Snapshot 只读隔离。| **100% 对齐** | 杜绝动态查询变动表，推演发起瞬间冻结为不可变投影。 |
| 7 | **29号决议单 约束5** | 哈希规范化严格遵循 RFC 8785 (JCS)。 | **100% 对齐** | 复用 Step 2 JCS 引擎，按 UTF-16 严格排序。 |
| 8 | **29号决议单 约束8** | Missing-data 严格求值。 | **100% 对齐** | `MISSING` 强行导致 `INCONCLUSIVE`，严守零伪造铁律。 |
| 9 | **29号决议单 约束11**| Phase 2A 严禁实现 Replay/Diff Engine。 | **100% 对齐** | 严格封存，本计划零相关实现。 |
| 10 | **董事会工程裁决** | 严格限制在 Sandbox，严禁真实 LLM。 | **100% 对齐** | 仅供单测与只读调试 API 运行，零外部网络 API 调用。 |

---

## 十五、 结论与提请决议事项

本《Phase 2A Step 3 实施边界与数据契约实施计划》已全面、彻底地回答了董事会提出的 9 大关键问题，逐项穷尽了数据契约、状态语义、四维时戳、全息血缘、哈希规则、M1~M5 映射、15项负向异常矩阵与基线对齐检查。

**提请最高董事会决议：**
> **审议批准本实施计划。待董事会签发正式批准令后，方可受控启动 Sub-Step 3.1 ~ 3.4 纯沙箱代码实现。**
