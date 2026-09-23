# G5-Phase 1A.2 市场状态配置与语义微调设计单

> **文件版本**：v1.1（最终审查修正稿）  
> **上位依据**：  
> 1. 《G5-Phase 1A.2 市场状态语义与状态向量校准设计 v1.0》  
> 2. 《G5-Phase 1A.2 综合审阅意见》  
> 3. 《G5-Phase 1A.2 最终审查结论（实施前最后一道设计闸门）》  
> **核心军规**：**本设计单只明确配置变动、指标归属、统计口径与语义极性元数据。在获得正式审查批准前：不改代码、不改生产参数、不改 DB Schema、不进入 M2、不做 Regime / Cognition 扩展。**

---

## 一、核心定位与事实原则

根据上位最终审查裁决，彻底冻结核心架构原则：

1. **事实与解释严格剥离**：  
   > **M1 负责“正确描述市场事实”，不负责“解释市场事实意味着什么”。**
2. **极性元数据不可滥用铁律**：  
   > **`metric_polarity` 仅用于解释各维度的客观物理含义与测量属性，绝不得被下游系统直接解释为交易方向、买卖信号或开平仓建议！**
3. **彻底防止“标量塌缩”在维度内重演**：  
   严禁将正交矛盾的事实重新加权压缩为单一分值。既防止 Global Scalar（全局总分塌缩），也坚决防止 Dimension Scalar（维度内子域塌缩）。

---

## 二、六大子维度指标重构与归属调整表

严格在既有 22 项事实指标集合内调整归属，绝不盲目扩充新指标：

```text
                  【指标归属调整示意】
    [原 D2 广度/赚钱]                     [新 D2 纯粹广度]
    - 上涨家数                           - 上涨家数
    - 下跌家数                           - 下跌家数
    - 涨跌家数比                         - 涨跌家数比
    - 涨停家数 ───(剥离移交)───┐
    - 跌停家数 ───(剥离移交)───┼──►     [新 D3 短线情绪与极端生态]
    - 涨跌停差 ───(剥离移交)───┤        ├── Sub-Domain A: 投机高标结构事实（独立输出）
    - 炸板率   ───(剥离移交)───┘        └── Sub-Domain B: 尾部极端博弈事实（独立输出）
```

---

### 1. D1 市场整体（Market Macro Index）
* **物理语义 / 极性（Polarity）**：**`DIRECTIONAL`（方向性刻度）**
* **物理含义**：`>50` 代表核心指数均值偏向上行，`<50` 代表核心指数均值偏向下行，`=50` 附近代表指数横盘中性。
* **指标清单**：
  1. `sh_pct_change`（上证涨跌幅，权重 0.35，CRITICAL）
  2. `sz_pct_change`（深成涨跌幅，权重 0.25，IMPORTANT）
  3. `cyb_pct_change`（创指涨跌幅，权重 0.25，IMPORTANT）
  4. `kc50_pct_change`（科创50涨跌幅，权重 0.15，IMPORTANT）

---

### 2. D2 市场广度（Market Breadth）
* **物理语义 / 极性（Polarity）**：**`BREADTH_EXPANSION`（广度扩散/收缩刻度）**
* **统计基准口径（严格吸收审阅意见）**：
  - **统计总体**：以**全市场有效交易股票（Active Trading Equities）** 为统计基准；
  - **剔除原则**：剔除当日全天停牌、无有效价格变动的非交易样本；
  - **平盘处理**：平盘股票保留在统计总体与分子分母基数中。
* **物理含义**：`>50` 代表多数有效个股处于上涨状态（普涨扩散），`<50` 代表多数有效个股处于下跌状态（普跌收缩）。
* **指标清单（纯化后）**：
  1. `up_count`（全市场有效上涨家数，权重 0.35，IMPORTANT）
  2. `down_count`（全市场有效下跌家数，反向映射，权重 0.35，IMPORTANT）
  3. `up_down_ratio`（有效涨跌家数比，权重 0.30，IMPORTANT）
* **语义校准原则（已删除预设数值区间）**：在全市场跌多涨少的盘面下，D2 广度刻度必须客观反映收缩偏弱态势，彻底杜绝因涨停等尾部指标对冲而被拉高至多头强势。具体数值由实盘映射自然得出，不预设任何主观区间。

---

### 3. D3 短线情绪与极端生态（Short-term Sentiment & Extremes）
* **物理语义 / 极性（Polarity）**：**`HEAT_EXTREMITY`（投机活跃与极端程度刻度）**
* **防误读铁律**：高分仅表示“短线博弈与极端两极分化处于极高状态”，**绝不代表“适合买入”或“多头强度高”**。彻底剔除“游资”等非规范主观措辞，保持纯粹客观事实陈述。
* **取消单一综合分，双子域独立并行输出（核心审查修正）**：  
  严禁将 Sub-Domain A 与 Sub-Domain B 强行 50/50 融合成一个单一分数作为核心事实输出，防止“从全局标量塌缩变成维度内标量塌缩”。D3 必须直接输出两个独立正交的事实子域：

```text
D3 结构定义（双子域独立输出，互不掩盖）：
├── Sub-Domain A: 投机高标结构事实 (Speculative Structure)
│   ├── max_board_height      (连板最高空间, CRITICAL)
│   ├── promotion_rate        (连板晋级率, IMPORTANT)
│   └── high_tier_performance (高位股溢价表现, OPTIONAL)
│
└── Sub-Domain B: 尾部极端博弈事实 (Tail Extremes)
    ├── limit_up_count        (全市场涨停数, IMPORTANT)
    ├── limit_down_count      (全市场跌停数, 反向, IMPORTANT)
    ├── limit_diff            (涨跌停绝对差, IMPORTANT)
    └── broken_limit_ratio    (真实炸板率, 反向, IMPORTANT)
```
* **正交事实保真**：若出现“6~7 板高标加速连板（Sub-Domain A 极度亢奋），但全市场 50~100 只跌停（Sub-Domain B 极度恐慌）”，下游必须同时收到这两个尖锐冲突的事实，禁止在 D3 内部对冲抵消。若计算综合参考值，仅作为辅助诊断标签（`reference_only`），不得作为核心事实。

---

### 4. D4 风格偏好（Style & Risk Appetite）
* **物理语义 / 极性（Polarity）**：**`STYLE_ELASTICITY`（小市值弹性偏好刻度）**
* **物理含义**：`>50` 代表小市值/微盘股相对大盘宽基呈现正向超额弹性，`<50` 代表权重蓝筹占优、微盘股表现落后。
* **指标清单**：
  1. `micro_cap_pct_change`（微盘板块涨跌幅，权重 0.60，IMPORTANT）
  2. `micro_vs_macro_ratio`（微盘相对上证超额，权重 0.40，IMPORTANT）

---

### 5. D5 外部环境（External Environment）
* **名称校准（消除歧义）**：由“外部风险（External Risk）”正式更名为 **“外部环境（External Environment）”**，彻底消除“分高到底是风险高还是环境好”的语义歧义。
* **物理语义 / 极性（Polarity）**：**`EXTERNAL_BENIGNITY`（外部环境平稳/友好度刻度）**
* **物理含义**：`>50` 代表离岸衍生品与外盘隔夜环境平稳偏暖，`<50` 代表外部市场承压扰动加大。
* **指标清单**：
  1. `a50_pct_change`（富时 A50 变动，权重 0.70，IMPORTANT）
  2. `a50_long_short_indicator`（多空指标，不可得时留白防伪，权重 0.30，OPTIONAL）

---

### 6. D6 流动性（Liquidity）
* **物理语义 / 极性（Polarity）**：**`LIQUIDITY_ACTIVITY`（成交活跃规模刻度）**
* **防误读铁律**：数值高仅表示“当前成交额处于历史高度活跃/巨量区间”，**绝不代表“多头单边大牛市”**！
* **参数定位澄清（审查修正）**：
  - 关于阈值区间（如 `[8000, 20000]` 亿），明确定义为**候选实验参数（Candidate Validation Parameter）**，不在本设计单中硬编码固化；
  - 本设计单仅固化 D6 的物理事实语义为“资金活跃度与深度规模”，具体阈值留待后续在验证环境中结合实盘回测审慎调优。
* **指标清单**：
  1. `total_amount`（两市有效成交额，权重 0.60，CRITICAL）
  2. `amount_change_ratio`（成交额环比变动率，权重 0.40，IMPORTANT）

---

## 三、各维度语义极性（Polarity Metadata）数据契约定义

在输出结构中为每个维度注入清晰的元数据描述，彻底防止下游大模型或规则引擎产生歧义：

```json
{
  "dimensions": {
    "D1": {
      "name": "市场整体",
      "score": 35.62,
      "metric_polarity": "DIRECTIONAL",
      "semantics_desc": "核心宽基指数均值方向刻度（>50偏多，<50偏空）"
    },
    "D2": {
      "name": "市场广度",
      "score": 33.19,
      "metric_polarity": "BREADTH_EXPANSION",
      "semantics_desc": "全市场有效个股普适覆盖度（>50普涨扩散，<50普跌收缩）"
    },
    "D3": {
      "name": "短线情绪与极端生态",
      "metric_polarity": "HEAT_EXTREMITY",
      "semantics_desc": "短线投机活跃与两极极端博弈热度（数值高代表极端分化活跃，非买入信号）",
      "sub_domains": {
        "speculative_structure": {
          "score": 31.85,
          "desc": "投机高标结构（最高板/连板高度/溢价）"
        },
        "tail_extremes": {
          "score": 41.20,
          "desc": "尾部极端博弈（涨停/跌停/差值/炸板率）"
        }
      },
      "reference_heat_index": 36.53
    },
    "D4": {
      "name": "风格偏好",
      "score": 46.98,
      "metric_polarity": "STYLE_ELASTICITY",
      "semantics_desc": "微盘/小市值相对大盘弹性比（>50小票强，<50蓝筹强）"
    },
    "D5": {
      "name": "外部环境",
      "score": 46.50,
      "metric_polarity": "EXTERNAL_BENIGNITY",
      "semantics_desc": "离岸衍生品与外盘扰动平稳度刻度（>50偏暖平稳，<50承压扰动）"
    },
    "D6": {
      "name": "流动性",
      "score": 98.50,
      "metric_polarity": "LIQUIDITY_ACTIVITY",
      "semantics_desc": "两市换手活跃度与资金深度（数值高代表巨量交投，非多头定论）"
    }
  }
}
```

---

## 四、`composite_score` 的降级定位实施准则

严格吸收上位审阅意见，**当前不修改字段名，执行语义与权限降级**：

1. **属性定性**：`Reference / Diagnostic Only`（仅供系统历史回测、基线对比与调试诊断）；
2. **决策隔离**：
   - 严禁在上层任何策略（Strategy）中使用 `composite_score > 某阈值` 作为加仓或多空依据；
   - M2 盘前简报在读取市场状态时，**必须以 D1～D6 的 Vector 事实为第一上下文输入**；
3. **标签剥离**：
   - 废除“全局标签 = 偏强主升”对整个市场的单一定论；
   - 报告与看板突出各维度的独立标签组合，例如：`D1偏弱震荡 | D2普跌收缩 | D3[高标退潮+尾部偏冷] | D6巨量交投`。

---

## 五、受控代码调整实施步骤（待用户正式授权后执行）

| 步骤 | 涉及文件 | 变动性质 | 预期改动量 |
|:---:|---|---|:---:|
| **Step 1** | `backend/app/cognition/config.py` | 微调 MetricConfig，将极端指标移至 D3 双子域，定义极性元数据与统计口径常量 | 约 35 行配置 |
| **Step 2** | `backend/app/cognition/interfaces.py` | 在 `SubDimensionState` 中增加 `metric_polarity`、`semantics_desc` 及子域支撑结构 | 约 10 行声明 |
| **Step 3** | `backend/app/cognition/market_state.py` | 适配 D2/D3 指标流转，在提取器中正确路由字段，实现双子域独立输出 | 约 20 行映射 |
| **Step 4** | `backend/scripts/verify_m14_real_data.py` | 运行真实数据验证：对比 2026-09-22 与 09-23 在新体系下的输出 | 纯测试执行 |

---

## 六、审查结论确认

本设计单（v1.1）已全额落实最终审查提出的 5 项修正与 1 条铁律原则，完全封堵了维度内再次标量塌缩的隐患，边界极其严整。  
**当前状态：处于实施前最后一道设计闸门。在获得用户最终审查核准前，保持不改代码、不改生产参数、不提交 Git。**
