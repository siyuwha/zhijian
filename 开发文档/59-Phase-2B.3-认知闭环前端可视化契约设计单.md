# Phase 2B.3 认知闭环前端可视化契约设计单

> **文档版本**：v1.0.0-FINAL  
> **上位依据**：  
> 1. 《Phase 2B.2 基线封存与真实 LLM Sandbox Trial 执行指令》  
> 2. 《开发文档/56-Phase-2B.2-受约束LLM认知假说提议器契约设计单.md》  
> 3. 《开发文档/58-Phase-2B.2-真实LLM-Sandbox-Trial验收报告.md》  
> **核心铁律**：  
> 1. 先设计契约，再写代码；  
> 2. 只验证认知，不做交易预测，UI 绝不宣称投资确定性；  
> 3. 保持 M4/M5 冻结。

---

## 一、系统定位与认知边界声明

### 1.1 系统定位
本阶段（Phase 2B.3）的核心目标是完成**“认知闭环的可视化呈现”**。将 Phase 2B.2 中在内存沙箱中验证跑通的科学推演链路，转化为每日收盘后在系统前端界面上**清晰可见、可追踪、可审计**的人机交互单元。

### 1.2 认知有效性界限与反误导铁律
- **已证明的机制**：系统已证明在限定契约下，“受约束 LLM 提案 → 刚性准入校验 → AST 编译 → 次日事实 → 证伪引擎客观裁决”的工程管道与时间因果完全成立。
- **未证明的边界**：系统**尚未证明**大模型提出的假说具备长期稳定的市场解释力、阈值合理性或预测 Alpha。
- **UI 呈现原则**：
  - 严禁将实验性假说包装为投资建议、选股信号或买卖指导；
  - 必须对“客观事实”与“衍生推论”进行显式分层（Fact vs. Derived State）；
  - 今日 AI 假说必须醒目标记为【待验证 (PENDING)】；
  - 仲裁结论必须严格基于客观事实比对，不可主观美化。

---

## 二、前端三核心卡片架构规范

前端呈现聚焦于收盘后的三个核心信息卡片，构成完整的“认知记忆与证伪闭环”：

```text
┌─────────────────────────────────────────────────────────────┐
│                    ① 今日事实卡 (Today's Facts)             │
│   [客观事实 Fact]                          [派生状态 Derived] │
│   指数涨跌幅 / 涨跌停家数 / 连板高度 / 炸板率   市场物理状态标签       │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              ② 今日 AI 假说卡 (Today's Hypothesis)          │
│   状态：【待验证 PENDING】                                    │
│   AI 提出了什么宏观假说？ (标的 / 类型 / 支撑逻辑 / 预期现象)       │
│   [预期指标断言 Expected]         [刚性证伪红线 Invalidation]  │
│   元数据：PromptSpec v1.1.0 / 模型名称 / AST Hash / 目标验证日 │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│          ③ 昨日假说裁决卡 (Yesterday's Adjudication)        │
│   认知记忆单元：昨天 AI 说了什么 -> 今天发生了什么 -> 机器如何裁决 │
│   裁决结果：【CONFIRMED】 / 【FALSIFIED】 / 【INCONCLUSIVE】 │
│   证据明细：各项预期指标达成情况、是否触碰证伪红线对比                │
└─────────────────────────────────────────────────────────────┘
```

---

### 2.1 卡片 ①：今日事实卡 (Today's Observation Facts)
- **目标**：清晰展示系统在当日 15:00 收盘后观察到的不可推翻物理事实，为假说生成提供唯一合法输入。
- **结构划分**：
  1. **客观事实层 (Fact Layer)**：
     - 核心宽基指数收盘表现：上证指数 (`sh000001`)、深证成指 (`sz399001`)、创业板指 (`sz399006`)、科创50 (`sh000688`) 之最新价与涨跌幅；
     - 投机情绪客观统计：涨停家数、跌停家数、连板最高高度（空间板）、炸板数与炸板率；
     - 市场广度：上涨家数、下跌家数、平盘家数。
  2. **派生状态层 (Derived State Layer)**：
     - 市场物理状态标签（如“平稳震荡”、“分化出清”、“极弱恐慌”）；
     - 状态算法版本与置信度元数据。

---

### 2.2 卡片 ②：今日 AI 假说卡 (Today's AI Hypothesis)
- **目标**：展示受约束大模型基于卡片 ① 的事实，对下一个交易日提出的可证伪推演。
- **关键视觉规范**：
  - 醒目标记 **【待验证 / PENDING】**，提示用户此内容属于前瞻性科研假说，绝非操作建议；
  - **前置逻辑与预期现象**：自然语言展示 `premise_logic` 与 `expected_phenomenon`；
  - **双轨断言对照区**：
    - 预期满足指标 (Expected Assertions)：表格列出指标、标的代码、期望算子、期望阈值；
    - **刚性证伪红线 (Invalidation Assertions)**：**高亮红框警示展示**，列出一旦被市场触发即判定假说破产的不可逾越红线。
  - **不可篡改凭证**：展示 `target_date`, `model_name`, `prompt_spec_version`, `hypothesis_hash`，支持溯源。

---

### 2.3 卡片 ③：昨日假说裁决卡 (Yesterday's Hypothesis Adjudication)
- **目标**：连接历史与现实的“认知记忆单元”，对昨天提出的假说进行不可推翻的事后打脸或确认。
- **关键视觉规范**：
  - **三态仲裁徽章**：
    - 🔴 `FALSIFIED` (已证伪)：触碰了证伪红线，推演破产；
    - 🟢 `CONFIRMED` (已证实)：预期条件全部满足，零红线触碰；
    - ⚪ `UNCONFIRMED` (未证实)：部分满足但未达全部证实标准，未触碰红线；
    - ⏳ `INCONCLUSIVE` (不可判定/数据缺失)：因节假日、停牌或数据源异常客观留白。
  - **打脸/证实对比矩阵**：
    - 逐项对比：昨日预期条件 vs. 今日收盘真实数据；
    - 若被证伪，醒目标出是哪一条证伪断言触发了事实打脸；
  - **客观裁决日志**：输出 `FalsificationEngine` 的权威判定详情。

---

## 三、前后端通信契约 (API Specification)

为支撑前端三卡片的高效渲染，后端提供专用聚合端点：

### 3.1 聚合查询端点：`GET /api/v1/cognition/review-loop/{date}`

- **描述**：获取指定复盘日期的完整认知闭环数据（今日事实 + 今日假说 + 昨日假说裁决）。
- **请求参数**：
  - `date`: 交易日期（YYYY-MM-DD）
- **响应 Schema (`CognitionReviewLoopResponse`)**：

```json
{
  "code": 200,
  "data": {
    "market_date": "2026-09-28",
    "today_facts": {
      "fact_layer": {
        "indices": [
          {"code": "sh000001", "name": "上证指数", "price": 3823.62, "pct_change": -1.67},
          {"code": "sz399001", "name": "深证成指", "price": 12858.75, "pct_change": -3.44},
          {"code": "sz399006", "name": "创业板指", "price": 3139.82, "pct_change": -4.53},
          {"code": "sh000688", "name": "科创50", "price": 1555.98, "pct_change": -4.06}
        ],
        "sentiment": {
          "limit_up_count": 33,
          "limit_down_count": 56,
          "max_board_height": 5,
          "broken_limit_count": 11,
          "broken_ratio": 0.25
        },
        "breadth": {
          "up_count": 820,
          "down_count": 4210
        }
      },
      "derived_state": {
        "state_label": "极弱恐慌出清",
        "composite_score": 18.5,
        "config_version": "v1.0"
      }
    },
    "today_hypothesis": {
      "id": 101,
      "status": "PENDING",
      "target_date": "2026-09-29",
      "hypothesis_type": "SENTIMENT_CYCLE",
      "target_asset": "全市场短线投机生态",
      "expected_scenario": "OVERSOLD_REBOUND",
      "premise_logic": "09-28 跌停56家恐慌出清，连板高度保持在5板，预期次日修复",
      "expected_phenomenon": "全A涨停家数重回40家以上，跌停收敛至30家以内",
      "expected_assertions": [
        {
          "assertion_id": "exp_lu",
          "metric_type": "limit_up_count",
          "target_code": "ALL_A",
          "operator": "GTE",
          "threshold": 40.0,
          "description": "涨停家数>=40"
        }
      ],
      "invalidation_condition": "若跌停家数仍大于50家则反弹假说证伪",
      "invalidation_assertions": [
        {
          "assertion_id": "inv_ld",
          "metric_type": "limit_down_count",
          "target_code": "ALL_A",
          "operator": "GT",
          "threshold": 50.0,
          "description": "跌停家数>50"
        }
      ],
      "meta": {
        "model_name": "deepseek-flash",
        "prompt_spec_version": "1.1.0",
        "hypothesis_hash": "a1b2c3d4..."
      }
    },
    "yesterday_adjudication": {
      "hypothesis_id": 99,
      "created_date": "2026-09-26",
      "target_date": "2026-09-28",
      "hypothesis_type": "SENTIMENT_CYCLE",
      "premise_logic": "预期跌幅收敛，跌停不扩散",
      "outcome": "FALSIFIED",
      "falsification_triggered": true,
      "details": "触碰刚性证伪红线 inv_3 (limit_down_count > 30)，实际跌停56家，假说客观证伪",
      "comparison_matrix": [
        {
          "assertion_id": "exp_lu",
          "kind": "EXPECTED",
          "metric_type": "limit_up_count",
          "operator": "GTE",
          "threshold": 35.0,
          "actual_value": 33.0,
          "is_satisfied": false
        },
        {
          "assertion_id": "inv_3",
          "kind": "INVALIDATION",
          "metric_type": "limit_down_count",
          "operator": "GT",
          "threshold": 30.0,
          "actual_value": 56.0,
          "is_satisfied": true
        }
      ]
    }
  }
}
```

---

### 3.2 触发生成端点：`POST /api/v1/cognition/hypotheses/propose-today`

- **描述**：在收盘后由用户或自动化任务主动触发受约束 LLM 假说提议，经 `ProposalValidator` 强校验后持久化并冻结入库。
- **请求参数**：
  ```json
  {
    "market_date": "2026-09-28",
    "target_date": "2026-09-29"
  }
  ```
- **响应**：校验成功返回新增的 `MarketHypothesis` 结构；校验失败返回 HTTP 400 与违规拦截码（如 `VR-01` 或 `VR-07`），杜绝脏假说入库。

---

## 四、实施计划与防退化门禁

1. **第 1 步：契约固化与 Schema 扩展**（已完成本文档编制）；
2. **第 2 步：后端聚合服务与 API 实现**：
   - 在 [`CognitionReviewService`](file:///d:/项目库/AI认知复盘交易系统/backend/app/services/cognition_review.py) 中实现 `get_review_loop_data(market_date)` 与 `propose_today_hypothesis(market_date, target_date)`；
   - 在 [`backend/app/api/v1/cognition.py`](file:///d:/项目库/AI认知复盘交易系统/backend/app/api/v1/cognition.py) 挂载路由；
   - 编写后端单元测试，确保 180+ 项测试全绿。
3. **第 3 步：前端三卡片组件开发**：
   - 在 `frontend/src/app/review/[date]/page.tsx` 中嵌入 `CognitionLoopVisualizer` 组件；
   - 实现清晰的 Fact/Derived 视觉隔离、待验证标记与证伪裁决高亮；
4. **第 4 步：端到端验证与门禁检查**：
   - 启动前后端验证真实渲染；
   - 执行 KA-06 基线检查，确认物理数据库零污染。
