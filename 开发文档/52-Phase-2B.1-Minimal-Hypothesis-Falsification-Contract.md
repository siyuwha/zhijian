# Phase 2B.1 Minimal Hypothesis & Falsification Loop 数据与交互契约冻结单

> **文档版本**：v1.0.0-FROZEN  
> **归档位置**：`开发文档/52-Phase-2B.1-Minimal-Hypothesis-Falsification-Contract.md`  
> **基线依赖**：`v0.2.1-cognition-guard-baseline` (`662e6f9`)  
> **工程治理状态**：契约先导（先设计契约，再编写代码）  
> **冻结时间**：2026-10-02T14:12:00+08:00  

---

## 一、铁律约束与设计边界

本契约严格遵照最高裁决指令的**三大铁律**：

| 铁律 | 约束规范 | 实施边界与防御措施 |
| :--- | :--- | :--- |
| **铁律 1：先设计契约，再写代码** | 必须先完成本契约文档并冻结数据结构与交互定义，方可进入代码落地。 | 任何代码提交必须溯源本契约中的字段命名、枚举定义与状态机规则。 |
| **铁律 2：只验证认知，不做交易预测** | 仅聚焦于“对市场宏观状态与情绪周期的认知推演”，坚决不做任何个股买卖推荐与交易预测。 | **绝对禁止**出现：个股代码推荐、买卖开仓点位、目标收益率百分比、止损止盈价预测或策略信号。全部断言仅围绕大盘指数、涨跌停家数、市场广度与情绪阶段。 |
| **铁律 3：保持 M4/M5 冻结** | M4 盘中动态流式异动与 M5 选股系统继续保持绝对物理冻结。 | 验证事实完全源自 M1 日终复盘与既有快照，零流式推送，零外接策略依赖。 |

---

## 二、数据契约定义 (Data Contracts)

### 2.1 假说定义输入契约 (Hypothesis Definition Contract)
假说定义在 T 日收盘后生成，描述对 T+1 日市场认知演变的前瞻判断。

```json
{
  "target_date": "2026-09-29",
  "hypothesis_type": "SENTIMENT_CYCLE",
  "target_asset": "全市场短线情绪与主要宽基",
  "expected_scenario": "WEAK_CONSOLIDATION",
  "premise_logic": "09-28全市场大跌仅33家涨停，高位退潮，次日预期惯性弱势整理，缺乏强反弹动能",
  "expected_phenomenon": "大盘微涨跌或低开，涨停家数受限，跌停家数处于低位",
  "invalidation_condition": "次日大盘单边暴涨>1.5%，或涨停家数超过70家发生反转",
  "assertion_metrics": {
    "expected_assertions": [
      {
        "assertion_id": "exp_sh_pct_bound",
        "metric_type": "pct_change",
        "target_code": "sh000001",
        "operator": "BETWEEN",
        "threshold": [-1.0, 0.5],
        "description": "上证收盘涨跌幅在 [-1.0%, +0.5%] 弱势整理区间"
      },
      {
        "assertion_id": "exp_limit_up_ceiling",
        "metric_type": "limit_up_count",
        "target_code": "ALL_A",
        "operator": "LTE",
        "threshold": 60,
        "description": "全市场涨停家数 <= 60 家 (未发生情绪反转)"
      }
    ],
    "invalidation_assertions": [
      {
        "assertion_id": "inv_surge_breakout",
        "metric_type": "pct_change",
        "target_code": "sh000001",
        "operator": "GT",
        "threshold": 1.5,
        "description": "上证收盘涨幅 > +1.5% (暴力反弹证伪弱势推演)"
      },
      {
        "assertion_id": "inv_sentiment_super_cycle",
        "metric_type": "limit_up_count",
        "target_code": "ALL_A",
        "operator": "GT",
        "threshold": 70,
        "description": "涨停家数 > 70 家 (情绪全面逆转证伪弱势推演)"
      }
    ]
  }
}
```

### 2.2 认知指标白名单契约 (Metric Whitelist)
严格限定为**宏观大盘与市场生态指标**，绝不包含任何个股交易预测：

| 指标代码 (`metric_type`) | 支持的标的 (`target_code`) | 语义与量纲 | 认知用途 |
| :--- | :--- | :--- | :--- |
| `pct_change` | `sh000001`, `sz399001`, `sz399006`, `sh000688` | 百分比浮点数 (如 `0.18` 代表 +0.18%) | 宽基趋势与分化验证 |
| `limit_up_count` | `ALL_A` | 整数 (如 `52`) | 短线投机做多情绪承接 |
| `limit_down_count` | `ALL_A` | 整数 (如 `3`) | 恐慌与流动性杀跌释放 |
| `up_count` | `ALL_A` | 整数 (如 `2614`) | 全市场赚钱效应广度 |
| `down_count` | `ALL_A` | 整数 (如 `2841`) | 全市场亏钱效应扩散 |
| `turnover_ratio` | `ALL_A` | 百分比浮点数 | 市场量能换手水位 |

---

## 三、事后证伪仲裁契约 (Falsification-First Engine Contract)

### 3.1 仲裁优先级状态机
遵循严谨科学哲学（波普尔证伪原则）：**假说无法被绝对证实，只能被持续证伪**。

```
              [输入 T+1 日真实市场数据]
                         │
                         ▼
             【第一步：证伪断言求值】
             invalidation_assertions
                         │
        ┌────────────────┴────────────────┐
        │ 命中任一证伪条件                │ 全部未触发
        ▼                                 ▼
   [🔴 FALSIFIED]             【第二步：缺数完整性检查】
  (立即裁决推翻，不再等待)                  │
                         ┌────────────────┴────────────────┐
                         │ 关键指标缺失                    │ 数据完整
                         ▼                                 ▼
                  [⚪ INCONCLUSIVE]             【第三步：预期断言求值】
                 (证据不足，严禁假0)             expected_assertions
                                                           │
                                          ┌────────────────┴────────────────┐
                                          │ 全部满足                        │ 存在不满足
                                          ▼                                 ▼
                                    [🟢 CONFIRMED]                    [🟡 PARTIAL]
                                   (阶段性与预期吻合)                (部分吻合/未被证伪)
```

### 3.2 仲裁持久化数据结构 (`HypothesisVerification`)
```json
{
  "hypothesis_id": 1,
  "verification_stage": "CLOSE_1530",
  "outcome": "FALSIFIED",
  "actual_data_snapshot": {
    "sh000001_pct_change": 0.18,
    "limit_up_count": 57,
    "up_count": 2800,
    "down_count": 2200
  },
  "deviation_analysis": "核心断言比对：上证实际涨幅 +0.18%（符合区间），但全市场涨停达 57 家逼近反弹上限。反向证伪断言均未触发，假说未被击溃。",
  "gap_summary": "认知预期与实际偏离度：+0.32% 强度差，情绪修复强于原弱势假说。",
  "verified_at": "2026-09-29T15:35:00"
}
```

---

## 四、API 接口交互契约

| 端点 | 方法 | 职责 | 响应规范 |
| :--- | :---: | :--- | :--- |
| `/cognition/hypotheses` | `GET` | 查询指定日期或状态的假说及核验记录 | 返回假说列表、AST 规则、以及已关联的双轨核验快照 |
| `/cognition/hypotheses` | `POST` | 录入新假说 (进入 `PENDING` 待锁定) | 返回创建的假说实体及生成的唯一 ID |
| `/cognition/hypotheses/{id}/verify` | `POST` | 驱动 `FalsificationEngine` 执行核对 | `stage=CLOSE_1530`，返回权威仲裁结果，并在 DB 中原子落盘 |

---

## 五、物理不可篡改性与幂等保障

1. **联合唯一索引**：`UNIQUE(hypothesis_id, verification_stage)` 确保针对某假说的同阶段核验记录**物理级唯一**。
2. **幂等查询**：若某假说在某阶段已完成核验，重复发起调用将直接返回已持久化的快照，严禁更新、删除或覆盖（WORM 一致性）。
3. **零修改开发库**：在单元测试与回放期间，严格运行于沙箱隔离数据库，真实开发库哈希零变化。

---

## 六、契约生效裁决
本契约自签署之日起立即生效冻结，后续代码实施严格以此契约为唯一验收标准。
