# 06 P0 Contract 与实施方案设计

> **编制日期**：2026-10-01  
> **设计原则**：严格基于 G0 审计事实、G1 冻结基线与 G3 迁移矩阵；只设计经审计、可解释、可验证、风险受控的 Contract；**不直接进入代码实现**；坚守 G5 停止门禁。  
> **重点设计范围**：  
> 1. Sector Crowding State Machine (行业/板块拥挤度状态机)  
> 2. Hierarchical Sell Rule AST (六级分层卖出规则断言语法树)  
> 3. Strategy Context / Profile (策略上下文与风格配置模型)  
> 4. Shadow Reconciliation (双轨影子对账与数据守卫)  
> 5. Baseline Diff (回测与基线差分防退化门禁)  
> 6. “透支年限”模型可行性与 Falsification 方案（定性：`Validate First` / 暂缓生产）  
> 7. “五源联动”模型可行性与 Falsification 方案（定性：`Validate First` / 暂缓生产）

---

## 一、 Sector Crowding State Machine (行业/板块拥挤度状态机)

### 1.1 问题定义与非目标
- **解决问题**：在确定性客观事实基础上，量化识别行业板块交易热度相对其自身历史及全市场的极端拥挤/冰点状态，为交易系统提供回撤防御边界，杜绝高位泡沫追高。
- **明确非目标**：
  - ❌ 不是买卖预测器：不得预测板块明日涨跌；
  - ❌ 不是黑盒评分：严禁使用不可解释的深度学习打分；
  - ❌ 不直接下单：拥挤度仅输出为状态特征，不越权触发交易。

> [!CAUTION] 前置数据可用性准入门禁 (G5.1 审计硬约束)
> **本设计属于【设计规范草案】。在通过 G5.1 规定的 7 项数据可用性审计（行业分类版本、成分股变迁、日频历史时序、两融/ETF覆盖、PIT时点、缺失处理与商业授权）并建立完备物理数据源之前，绝对不得在生产系统中实现或启用该状态机！**

### 1.2 证据来源与选择理由
- **证据来源**：盘股说明书 p.21-22（第 5.3.2 节）、证据卡 KA-01。
- **选择理由**：当前系统 M1/M2 仅有全市场宏观 D1~D6 分数，缺乏中观板块维度的结构化状态机，无法识别二八分化与抱团风险。

### 1.3 统一认知分类与边界剥离
- **原始物理事实 (Physical Fact)**：板块当日成交额、全市场成交额、板块成分股涨跌幅、两融买入额；
- **派生特征 (Derived Feature)**：成交额占比 $Amount_{pct}$、换手率 $Turnover$、均线多头比例 $MA_{bull\_ratio}$、创新高占比 $NewHigh_{ratio}$、乖离率 $Bias$；
- **系统状态 (State)**：`SectorCrowdingState`（EXTREME_COLD ~ OVERHEATED 离散状态）；
- **策略解释 (Strategy Knowledge)**：过热预警、冰点反转博弈假设；
- **交易决策 (Decision)**：仓位上限约束（属于下游 Gate，不属于本模块）。

### 1.4 输入与输出 Contract

```python
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class CrowdingLevel(str, Enum):
    EXTREME_COLD = "EXTREME_COLD"       # 极度低迷 (Index <= 20)
    COLD = "COLD"                       # 冷门冰点 (20 < Index <= 35)
    NORMAL = "NORMAL"                   # 正常中性 (35 < Index <= 65)
    ACTIVE = "ACTIVE"                   # 活跃升温 (65 < Index <= 80)
    CROWDED = "CROWDED"                 # 交易拥挤 (80 < Index <= 90)
    OVERHEATED = "OVERHEATED"           # 极度过热 (Index > 90)
    UNKNOWN = "UNKNOWN"                 # 数据不足降级

class SectorCrowdingInputContract(BaseModel):
    sector_code: str
    trade_date: str
    # 物理事实输入
    sector_amount: float                # 板块当日成交额 (元)
    market_amount: float                # 全市场当日成交额 (元)
    turnover_rate: float                # 板块换手率 (%)
    up_stock_ratio: float               # 板块内上涨股票占比
    new_high_ratio: float               # 创60日新高股票占比
    margin_net_ratio: Optional[float] = None # 两融净买入占比
    # 历史基线输入 (只读注入)
    historical_120d_amount_pct_median: float
    historical_120d_turnover_median: float

class SectorCrowdingOutputContract(BaseModel):
    sector_code: str
    trade_date: str
    crowding_score: float = Field(ge=0.0, le=100.0) # 合成拥挤度指数 (0~100)
    current_level: CrowdingLevel                    # 当前状态机级别
    previous_level: CrowdingLevel                   # 前驱状态级别
    is_confirmed: bool                              # 是否通过确认期检验
    days_in_level: int                              # 当前状态持续交易日数
    cooldown_remaining_days: int                    # 退出过热后的剩余冷却日数
    degraded_factors: List[str] = Field(default_factory=list) # 降级维度清单
    data_quality: str                               # FULL / PARTIAL / INVALID
```

### 1.5 状态机转换规则与磁滞参数
- **磁滞跃迁（Hysteresis Buffer）**：
  - 向上跃迁门槛：从 `NORMAL` 跃迁至 `CROWDED` 必须评分 $\ge 80.0$，且在随后 1 个交易日复验维持 $\ge 80.0$（确认期 2 日）；
  - 向下回退门槛：从 `CROWDED` 回退至 `NORMAL` 必须评分跌破 $72.0$（保留 8.0 分缓冲区，杜绝临界点跳档）；
  - 冷却期（Cooldown）：从 `OVERHEATED` 脱离后，强制维持 3 个交易日的“观察冷却期”，在此期间仓位上限不自动解除。

### 1.6 默认失败与降级策略
- 若成分股缺失 $> 30\%$ 或成交额为 None：评分强制置为 None，状态标记为 `UNKNOWN`；
- 注入显式元数据：`[DATA_DEFICIENCY: 板块数据缺失，拥挤度状态机停机降级]`；
- 严禁假 0 填充。

---

## 二、 Hierarchical Sell Rule AST (六级分层卖出规则断言语法树)

### 2.1 问题定义与非目标
- **解决问题**：交易执行中最容易被人类贪婪与恐惧破坏的是卖出环节。本方案将多层卖出理由形式化为带优先级的无二义性 AST 规则树，解决多信号并发冲突，提供全链路可解释审计与回放。
- **明确非目标**：
  - ❌ 不包含自动报单：触发的动作仅为 `SellOrderProposal`，必须走 S3 HITL 确认；
  - ❌ 不允许运行时动态执行未经治理的 Python `eval()` 字符串。

### 2.2 证据来源与选择理由
- **证据来源**：盘股说明书 p.26-27（第 5.10 节）、证据卡 KA-03、Redmi/TRADING_KNOWLEDGE 绿盟案例。
- **选择理由**：当前系统 M3 只有被动记账，缺乏前瞻性风险保护与多优先级卖出仲裁能力。

### 2.3 六级优先级架构与动作语义

> [!CAUTION] 核心参数定性与实盘禁用红线 (G5.1 审计裁决)
> **以下各级规则所列数值阈值（如浮亏 $\le -5\%$、峰值回撤 $\ge 8\%$、移动止盈等）全部定性为【未验证研究参数 (Unverified Research Parameters)】！**  
> 它们仅代表盘股脱敏材料中的经验假设，**只允许用于历史回放（Historical Replay）或影子提案（Shadow Proposal Observation）中进行观察与证伪；绝对不得直接作为默认实盘规则生效！**

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│              六级分层卖出规则优先级与仲裁架构 (研究观察参数模型)                 │
├──────┬──────────────────────┬─────────────┬───────────────┬──────────────────────┤
│ 优先级│ 触发主题             │ 假说判定逻辑│ 提案观察动作  │ 冲突仲裁权重         │
├──────┼──────────────────────┼─────────────┼───────────────┼──────────────────────┤
│  L1  │ 绝对亏损 (硬止损)    │ 浮亏 <= -5% │ LIQUIDATE     │ 100 (最高, 一票否决) │
│  L2  │ 势散监测 (动能衰竭)  │ 缩量滞涨    │ LIQUIDATE     │ 80                   │
│  L3  │ 趋势走弱 (破位离场)  │ 跌破 MA20   │ REDUCE_HALF   │ 60                   │
│  L4  │ 顶部确认 (形态见顶)  │ 双顶/头肩顶 │ REDUCE_HALF   │ 40                   │
│  L5  │ 波浪回撤 (高点回撤)  │ 峰值回撤>=8%│ REDUCE_HALF   │ 20                   │
│  L6  │ 移动止盈 (锁盈保护)  │ 盈利后回撤  │ LIQUIDATE     │ 10                   │
└──────┴──────────────────────┴─────────────┴───────────────┴──────────────────────┘
```


### 2.4 AST 节点与规则 Schema

```python
class SellActionType(str, Enum):
    HOLD = "HOLD"                   # 维持持仓
    REDUCE_HALF = "REDUCE_HALF"     # 减仓 50% (向下取整至100股)
    LIQUIDATE = "LIQUIDATE"         # 全量清仓 (100%)

class SellRulePriority(int, Enum):
    P1_HARD_STOP = 1        # 第一优先级: 绝对亏损保护
    P2_MOMENTUM_LOST = 2    # 第二优先级: 势散监测
    P3_TREND_BREAK = 3      # 第三优先级: 关键均线破位
    P4_TOP_STRUCTURE = 4    # 第四优先级: 顶部形态确认
    P5_PEAK_DRAWDOWN = 5    # 第五优先级: 峰值回撤控制
    P6_TRAILING_PROFIT = 6  # 补充层: 移动止盈

class SellRuleNode(BaseModel):
    rule_id: str
    priority: SellRulePriority
    rule_name: str
    condition_ast: Dict[str, Any]       # 复用现有 Narrowed AssertionAST
    action: SellActionType
    is_active: bool = True

class SellEvaluationResultContract(BaseModel):
    symbol: str
    current_price: float
    cost_price: float
    max_price_since_buy: float
    evaluated_at: str
    # 仲裁决策结果
    final_action: SellActionType
    arbitrated_priority: Optional[SellRulePriority] = None
    triggered_rules: List[str] = Field(default_factory=list)
    # 证据链追溯
    evidence_snapshot: Dict[str, Any]
    rationale_text: str
```

### 2.5 冲突消解协议（Arbitration Protocol）
- **仲裁铁律**：同一时间若有多个规则满足条件，**严格以优先级数值最小（Priority = 1 最优先）的规则动作作为最终裁决**。
- **示例**：若同时触发 L4（顶部确认，建议 REDUCE_HALF）与 L1（浮亏触碰 5%，建议 LIQUIDATE），系统强制采纳 L1，输出 `LIQUIDATE`，禁止贪婪减半。

### 2.6 安全边界与防误触守卫
- **实盘开市守卫**：评估前强制执行 `is_trading_time() and current_price > 0.0`；若当前为收盘时段且无有效结算价，严禁触发止损动作。

---

## 三、 Strategy Context / Profile (策略上下文与风格配置模型)

### 3.1 认知分类界定
- **认知分类**：`State`（环境状态）+ `Strategy Knowledge`（策略方法论与仓位约束）。
- **绝对红线**：**Strategy Context 绝非 Physical Fact，绝对不得越权覆盖 M3 交易底线与风控 Gate！**

### 3.2 产生机制、失效机制与消费者
- **生成机制**：每日 15:30 盘后由 M1 市场状态聚合计算，或盘前 08:45 由 M2 确认，产出当日全局 `StrategyContextProfile`；
- **失效机制**：当日 15:00 收盘后自动失效；若盘中大盘指数发生超 3% 的剧烈日内波动，触发紧急重置为 `VOLATILE_EMERGENCY`；
- **消费方**：M6 选股候选池开仓门禁、S3 HITL 诊断建议。

### 3.3 Contract 定义

```python
class MarketStyleRegime(str, Enum):
    BULL_AGGRESSIVE = "BULL_AGGRESSIVE" # 单边强牛
    BULL_STRUCTURAL = "BULL_STRUCTURAL" # 结构性慢牛
    OSCILLATION = "OSCILLATION"         # 宽幅震荡 (中性)
    BEAR_WEAK = "BEAR_WEAK"             # 弱势阴跌
    BEAR_PANIC = "BEAR_PANIC"           # 恐慌性主跌

class StrategyContextProfile(BaseModel):
    profile_id: str
    trade_date: str
    market_regime: MarketStyleRegime
    # 账户级硬约束
    global_position_ceiling: float = Field(ge=0.0, le=1.0) # 总仓位上限 (如 0.3)
    single_position_ceiling: float = Field(ge=0.0, le=0.5) # 单票仓位上限 (如 0.15)
    max_active_symbols: int = Field(default=2)             # 最大持仓只数
    # 策略系统激活状态
    core_selection_active: bool = True     # 核心精选系统 (价值波段)
    momentum_breakout_active: bool = False # 强势追涨系统 (顺势打板)
    value_reversion_active: bool = True    # 价值回归系统 (超跌低吸)
    # 防守门禁标志
    force_freeze_new_entries: bool = False # 强制禁止任何新开仓
```

---

## 四、 Shadow Reconciliation (双轨影子对账与数据守卫)

### 4.1 对象模型与对账维度
- **主管道（Primary Pipeline）**：当前生产基于全量 API + 缓存的实时计算模块；
- **影子管道（Shadow Pipeline）**：基于纯本地离线快照 + 独立纯函数实现的复核模块；
- **对账维度**：
  1. 交易持仓对账（持仓数量、均价、可用股数）；
  2. 市场状态评分对账（D1~D6 分数、MarketState 标签）；
  3. 板块拥挤度分级对账。

### 4.2 Contract 定义

```python
class ReconciliationScope(str, Enum):
    TRADING_POSITION = "TRADING_POSITION"
    MARKET_STATE = "MARKET_STATE"
    SECTOR_CROWDING = "SECTOR_CROWDING"

class ReconciliationStatus(str, Enum):
    MATCH = "MATCH"                     # 100% 吻合
    DRIFT_WARNING = "DRIFT_WARNING"     # 存在轻微浮点漂移 (在容差内)
    MISMATCH_ALARM = "MISMATCH_ALARM"   # 严重不符告警

class ShadowReconciliationRecord(BaseModel):
    reconciliation_id: str
    timestamp: str
    scope: ReconciliationScope
    target_entity_id: str               # 标的代码或日期
    primary_value: Any
    shadow_value: Any
    absolute_delta: float
    status: ReconciliationStatus
    audit_notes: str
```

### 4.3 物理隔离、故障域独立性与三重安全行为矩阵 (G5.1 审计重构)

#### 1. 独立性与故障域隔离铁律
- **严禁复用主管道资产**：影子数据源必须使用**独立的 HTTP Client 实例、独立的连接池、独立的解析器、独立的内存缓存**；严禁复用主采集管道的解析结果或上下文对象，确保主影子处于物理正交的故障域。
- **只读连接硬约束**：影子守护进程（Shadow Daemon）仅拥有 SQLite 只读连接（`mode=ro`）；严禁调用任何具有写操作的 ORM 事务，严禁直连任何交易执行接口。

#### 2. 三重安全行为状态矩阵 (Tri-State Safety Behavior)

| 场景情形 | 主源状态 | 影子源状态 | 判定性质 | 系统安全响应行为 | 交易流水线影响 |
|:---:|:---:|:---:|:---:|:---|:---|
| **Case A** | **正常** | **失败 / 超时** | 监控守卫降级 | 记录 `data_quality_log`，触发非阻塞 WARNING 告警，标记影子对账缺位。 | **放行**：主流程正常推进，不阻断交易。 |
| **Case B** | **失败** | **正常** | 主采集链路故障 | **绝对禁止盲目自动故障转移（Failover）至影子源下单！** 系统立即触发**安全防御性停牌/只读冻结**，等待人工接入。 | **阻断**：终止自动化决策，进入防御态。 |
| **Case C** | **正常** | **正常**<br>(数值出现差异<br>Primary != Shadow) | **数据源严重背离 (Divergence)** | 触发 `DATA_SOURCE_DIVERGENCE` 严重安全告警，落盘差异审计日志，**系统立即进入防误触/防超卖安全阻断态**。 | **阻断**：暂停自动化提案生成，强制移交 S3 HITL 人工在环仲裁核验。 |

---

## 五、 Baseline Diff (回测与基线差分防退化门禁)

### 5.1 可比较维度与比较粒度
- **代码级可比**：148 项单元测试通过率（容差 0）；
- **数据级可比**：固定历史交易日（金样例 2026-09-28）的 `ObservationSnapshot` JCS SHA-256（容差 0 比特）；
- **策略级可比**：标准历史回测期间（2024年~2026年）的夏普比率、最大回撤、胜率。

### 5.2 差异分类与回归判定门禁
- **可接受良性差异**：
  - 纯性能优化导致计算耗时下降；
  - 补充缺失数据导致 `INCONCLUSIVE` 转为明确证据支持的 `CONFIRMED`/`FALSIFIED`。
- **一票否决回归现象（Hard Regression Gate）**：
  1. 单元测试通过率 $< 148$；
  2. 原本防假零填充用例（RT-03）返回 True 或偷填 0.0；
  3. 固定样本金样例的哈希发生未经授权的改变；
  4. 策略最大回撤在相同历史样本上恶化 $> 1.5\%$。

---

## 六、 “透支年限”模型可行性与 Falsification 方案

### 6.1 审查决议：`Validate First`（暂不接入生产）
- **原因**：当前公开数据源完全缺乏高质量券商一致预期（CAGR）时序数据；强行使用固定假设会导致严重主观幻觉。
- **变量定义**：$T$（年）= $\ln(PE_{cur} / PE_{bench}) / \ln(1 + g)$；
- **数据来源调研**：需商业财经终端（如 Wind/Choice/朝阳永续）提供 Consensus EPS；
- **统计证伪方案**：
  - 收集全市场过去 5 年高透支标的（$T > 3$），检验未来 1 年估值回撤幅度是否显著大于低透支标的；
  - 若 $R^2 < 0.1$ 且相关性不显著，模型宣告失效，永久拒绝进入生产。

---

## 七、 “五源联动”模型可行性与 Falsification 方案

### 7.1 审查决议：`Validate First`（暂不接入生产）
- **原因**：
  1. 方案 v9.3 严重依赖海外高频期货与未建立的 NLP 舆情事件监测系统；
  2. 权重与开盘预测公式（$\times 0.025$）纯属主观经验设定，缺乏样本外实测证据；
  3. 大模型分析离散突发事件存在幻觉风险，误判事件等级可能误触发账户清仓。
- **统计证伪方案**：
  - 以 Python 脚本对 2021~2024 年真实 WTI、10Y 美债、VIX 隔夜数据与次日上证指数真实开盘跳空执行回归分析；
  - 证伪门槛：若开盘跳空方向预测胜率 $\le 52\%$ 或回测证明开盘阶梯减仓造成交易磨损远大于避险收益，则该联动公式被彻底证伪。

---

## 八、 实施顺序、依赖与回滚方案

### 8.1 分阶段实施顺序（严格遵守 G5 停止门禁）
```text
[阶段 0: 人工决策与授权] -> (当前停靠点, 等待授权)
  ↓
[阶段 1: S1 物理安全加固] -> 激活磁盘库 WORM 触发器, 固化 Git 基线, 部署 KA-06 基线差分 CI
  ↓
[阶段 2: 状态机与规则核心] -> 实现 KA-01 拥挤度状态机与 KA-03 分层卖出 AST
  ↓
[阶段 3: 影子与上下文治理] -> 部署 KA-05 影子对账 Daemon 与 KA-04 策略上下文 Profile
  ↓
[阶段 4: 离线科学验证] -> 执行 KA-02 透支年限与 KA-08 五源联动统计证伪
```

### 8.2 回滚预案
- 每一个 P0 增强模块均采用独立文件与命名空间组织；
- 采用特性开关（Feature Flag）默认隔离：`ENABLE_SECTOR_CROWDING=False`, `ENABLE_SELL_RULES=False`, `ENABLE_SHADOW_RECON=False`；
- 发生任何回归时，关闭特性开关即可 0 成本回滚至当前 148 测试全绿基线。
