# G5-Phase 1C：M3 集合竞价观测与状态承接系统技术设计单 (v1.1)

> **设计单编号**：DESIGN-G5-PHASE-1C-M3-01 (v1.1 修订版)  
> **编制日期**：2026-09-24  
> **编制机构**：Antigravity 主开发团队  
> **上位依据**：  
> 1. [《开发文档/10-项目多Agent四权分立工程治理规范.md》](file:///d:/项目库/AI认知复盘交易系统/开发文档/10-项目多Agent四权分立工程治理规范.md)  
> 2. [《开发文档/12-G5-Phase-1A.3封口与边界冻结决议.md》](file:///d:/项目库/AI认知复盘交易系统/开发文档/12-G5-Phase-1A.3封口与边界冻结决议.md)（8项核心边界冻结）  
> 3. [《开发文档/14-G5-Phase-1B封口与边界冻结决议.md》](file:///d:/项目库/AI认知复盘交易系统/开发文档/14-G5-Phase-1B封口与边界冻结决议.md)（8项核心边界冻结）  
> 4. 最高董事会批示：“先设计、后实施；暂缓实施授权；专项补充 M3定位、M2→M3兑现关系、数据源可得性与分母定义三项规范”  

---

## 一、系统定位与业务场景

### 1.1 业务时序与全链路承接闭环
M3 系统（历史代号：集合竞价决策系统；法定工程定位：**开盘微观事实观测与状态承接系统**）在交易链路中处于每个交易日 **09:25 ~ 09:30** 的关键微观时间窗口：
- **前置依赖（M1 + M2 承接）**：
  - 继承 M1（昨日收盘状态向量）：直接引用前日已固化的两市全天总成交金额、最高空间板、连板晋级率、跌停家数、真实炸板率；
  - 核验 M2（盘前简报 4 维推演）：以 09:25 集中撮合的物理事实，逐项核验“竞价量能比值、高标溢价、尾部释放修复、外盘扰动映射”在开盘瞬间的实际兑现情况。
- **后置输出（Phase 2 盘中监控底座）**：
  - 输出 09:25 集合竞价全市场开盘多空承接物理事实、指数跳空幅度和高标竞价溢价生态，作为 09:30 连续竞价开启后“盘中实时异动监控”的确定性物理基准。

```mermaid
flowchart TD
    M1["M1 收盘复盘 (前日状态向量 + 涨停池)"] --> M3["M3 集合竞价观测与状态承接系统 (09:25)"]
    M2["M2 盘前简报 (隔夜外盘 + 4 维观察假设)"] --> M3
    subgraph M3_CORE ["M3 微观事实观测核心引擎 (09:25~09:30)"]
        D1["三大指数跳空开盘与竞价量能承接比"]
        D2["一字板与极端封单生态 (涨跌停)"]
        D3["昨日高标/连板池竞价溢价与抢筹率"]
        D4["开盘客观承接物理研判 (全免责/零买卖信号)"]
    end
    M3 --> M3_CORE
    M3_CORE --> OUT["REST API & 前端全景作战看板 (动态归档 + 详情看板)"]
```

---

### 1.2 M3 核心定位：微观事实观测与状态承接，不承担交易决策（【专项补充 1】）

依据最高董事会指示，本设计单正式对 M3 的权限边界予以刚性锚定与法定限权：

1. **名称内涵与职责纠偏**：
   - 历史沿革中的“集合竞价决策系统”名称保留仅作为模块代号标识，**其实质定位严格限定为「微观物理事实观测仪（Micro-Observation Sensor）与开盘状态承接器（State Receiver）」**；
   - M3 绝非交易执行器，也绝非策略下单引擎。
2. **“绝不承担交易决策”的权力负面清单（Prohibition List）**：
   - 🚫 **严禁产生买卖交易信号**：绝不生成任何“买入、卖出、加仓、减仓、平仓、清仓”等操作指令；
   - 🚫 **严禁输出选股与打板建议**：绝不给出“推荐打板、竞价抢筹、排单买入、挂单跑路”等诱导性投资建议；
   - 🚫 **严禁参与仓位与风控决策**：绝不干涉交易员或后续策略系统的资金配置、头寸比例或止损止盈设置。
3. **“忠实观测与承接”的工程职责正面清单（Positive List）**：
   - ✅ **微观事实的高保真测量**：在 09:25 撮合产生的物理切片中，精确、客观、无偏地采集并计算指数跳空、真实竞价额、高标溢价率、一字涨跌停等确定性事实；
   - ✅ **宏观到微观的状态平滑承接**：将昨日 M1.4 的大盘六维宏观认知基线，通过 09:25 的量价事实平滑过渡到早盘物理刻度，为下游监控提供标准化、强类型的只读数据契约。

---

### 1.3 M2 → M3 兑现闭环契约：事实验证与物理核对，绝非预测评分（【专项补充 2】）

依据最高董事会指示，明确界定 M2 盘前推演与 M3 集合竞价观测之间的逻辑闭环关系：

1. **M2 的推演属性定义**：
   - M2 盘前简报产出的 4 维“今日关注推演”（竞价量能比值、高标溢价、尾部释放修复、外盘扰动映射），其本质是**「客观观察维度与跟踪假设（Observation Dimensions & Hypotheses）」**，**绝非主观猜多空或胜率预测**。
2. **M3 的核验属性定义（事实验证）**：
   - M2 到 M3 的过程是纯粹的**「事实验证与物理核对（Fact Verification & Audit）」**：
     - **核验 1（量能承接）**：M2 提出跟踪竞价量能比值是否充盈 $\to$ M3 测量 09:25 真实两市竞价总金额与前日成交比值，核对早盘实际承接意愿；
     - **核验 2（高标生态）**：M2 提出跟踪昨日最高空间连板股溢价 $\to$ M3 测量最高板标的真实开盘涨幅与封单特征，核对多头投机动能延续性；
     - **核验 3（尾部修复）**：M2 提出跟踪跌停撬板与炸板释放 $\to$ M3 测量实际跌停标的开盘开板率、一字跌停家数增减，核对极端亏钱效应修复事实；
     - **核验 4（外盘扰动）**：M2 测算隔夜 A50 与美股涨跌扰动 $\to$ M3 测量早盘 A 股权重与科技成长板块实际开盘跳空点位，核对外部冲击吸收程度。
3. **严禁“预测评分”的工程红线（No Accuracy Scoring）**：
   - 认知系统追求的是“忠实刻画客观物理事实”，不是把市场当赌场做玄学猜涨跌；
   - **严禁**在 M3 中对 M2 进行“预测准确率打分”、“猜对/猜错评分”、“胜率命中率评级”；
   - M3 的综述述评仅客观记录事实核对结果：“M2 盘前关注假设已由 09:25 物理事实核验：实际两市竞价额为 XX 亿元（比值 YY%），最高板实际开盘 ZZ%...”。

---

## 二、架构设计与契约约束（零 Schema 变更原则）

### 2.1 数据库持久化（零 Schema 变更）
系统严格复用 SQLite 中已存在的 `auction_report` 表结构，严禁破坏性迁移：

```python
class AuctionReport(Base):
    """竞价观察报告 (复用已有模型)"""
    __tablename__ = "auction_report"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False, unique=True, index=True)
    index_open_data = Column(Text)          # 指数开盘数据 JSON (包含上证/深证/创业板/科创/北证及量能承接比)
    one_word_count = Column(Integer, default=0) # 一字涨跌停统计 (含一字涨停家数)
    high_open_stats = Column(Text)          # 高开与生态统计 JSON (高标溢价、高开率、极端核按钮等)
    emotion_judgment = Column(String)       # 开盘客观承接物理研判 JSON 或 标签描述
    generated_at = Column(DateTime, server_default=func.now())
```

### 2.2 数据采集与指标清洗规范
1. **三大指数与宽基指数开盘快照 (`index_open_data`)**：
   - 采集标的：上证指数 (`s_sh000001`)、深证成指 (`s_sz399001`)、创业板指 (`s_sz399006`)、科创50 (`s_sh000688`)、北证50 (`s_bj899050`)；
   - 提取字段：开盘点位 (`price`)、开盘涨跌幅 (`pct_change`)、开盘涨跌额 (`change`)、竞价成交额 (`amount_wan`)。
2. **昨日高标/连板梯队竞价溢价 (`high_open_stats`)**：
   - 数据源：继承前日 M1 复盘中的 `limit_up_analysis.pool`（昨日涨停/连板个股列表）；
   - 通过 `sina.get_stock_quotes` 批量查询 09:25 开盘快照：
     - 开盘价格 $P_{open}$（`parts[1]`）、昨日收盘价 $P_{prev}$（`parts[2]`）；
     - 开盘涨跌幅 $\text{open\_pct} = \frac{P_{open} - P_{prev}}{P_{prev}} \times 100\%$；
     - 最高空间板开盘溢价：昨日最高空间连板股的开盘涨幅与封单特征；
     - 高标平均溢价率：样本池标的竞价涨幅均值；
     - 高开比例：开盘涨幅 $> 0\%$ 的标的占比；
     - 抢筹与核按钮标的：高开 $> 4\%$ 或低开 $< -4\%$ 的极端异动标的列表。
3. **一字板与极端封单统计 (`one_word_count`, `high_open_stats`)**：
   - 一字涨停判定：$P_{open} = High = Low$ 且 $\text{open\_pct} \ge 9.8\%$（主板）或 $\ge 19.8\%$（创业板/科创板）；
   - 一字跌停判定：$P_{open} = High = Low$ 且 $\text{open\_pct} \le -9.8\%$（主板）或 $\le -19.8\%$（创业板/科创板）。
4. **开盘多空承接客观研判 (`emotion_judgment`)**：
   - 综合指数跳空度、竞价成交量比、高标平均溢价与极端一字板数量，映射为客观物理承接状态：
     - 【放量高开偏强承接】
     - 【平开中性震荡分化】
     - 【缩量低开承接偏弱】
     - 【极端低开流动性释放】
   - 严禁产生任何主观买卖指令，输出 100~200 字客观事实综述，并在界面醒目标注免责声明。

---

### 2.3 数据源可用性、时间一致性、覆盖率与数学定义验收规范（【专项补充 3】）

依据最高董事会专项指示，对 M3 数据质量与数学定义做出严格工程约束：

#### 1. 09:25 ~ 09:30 数据可得性验收规范（Data Availability SLA）
- **交易所撮合时序机制**：
  - `09:15 ~ 09:20`：自由申报与撤单（虚假申报频发，严禁用于开盘定性）；
  - `09:20 ~ 09:25`：只报不撤，买卖撮合试算；
  - `09:25:00`：**交易所撮合主机瞬间集中完成全市场集合竞价撮合**，产生全市场标的今日开盘价（Open Price）与集合竞价成交额/成交量；
  - `09:25 ~ 09:30`：静默期（仅接受申报，不进行撮合）。
- **外部数据源分发窗口**：
  - 新浪财经行情网关与东财 Push 接口通常在 **09:25:05 ~ 09:25:25** 完成各标的 09:25 撮合开盘快照向公网的分发；
  - **M3 触发与调用时间窗口严格锚定为：`09:25:30 ~ 09:28:00`**；
  - **未开盘/提前调用的防伪判定**：若在交易日 09:25:00 之前请求，或非交易日/停盘时段调用，检测到底层开盘价为 0 或时间戳未更新，数据质量标记为 `DataQuality.UNAVAILABLE`，开盘指标严格置为 `None`，严禁填 0 伪造平盘！

#### 2. 时间一致性核验规范（Temporal Consistency Verification）
- **时间戳交叉校验**：
  - 采集的所有标的（指数、昨日连板池个股），其行情数据必须满足以下同构校验：
    - 日期校验：数据包中的交易日期字段必须与目标日期 `YYYY-MM-DD` 100% 一致；
    - 时间戳校验：时间字段必须处于 `09:25:00` 及之后，严禁串入前一日收盘数据或历史陈旧快照；
    - 若某一标的时间戳滞后或属于前日，标记该标的为数据失效（`None`），不得混入当日竞价均值计算。

#### 3. 样本覆盖率与稳定性标准（Coverage & Sampling Stability）
- **指数覆盖率**：5 大核心宽基指数（上证指数 `sh000001`、深证成指 `sz399001`、创业板指 `sz399006`、科创50 `sh000688`、北证50 `bj899050`）覆盖率必须达到 **100%**。若三大核心指数有任一缺失，标记为 `DataQuality.PARTIAL`；
- **高标池样本覆盖率**：样本池直接继承前日 M1 复盘的 `limit_up_analysis.pool`（昨日所有涨停个股）：
  - 批处理查询成功率需 $\ge 90\%$；
  - 单只个股停牌或未匹配时，以 `None` 标注并扣减有效样本数，不中断整体指标统计；
  - 若昨日无涨停个股（极端极弱市场，pool 为空），高标溢价各项指标显式置为 `None` / `'--'`，提示“前日无连板高标，指标缺省”，严禁崩溃。

#### 4. 竞价量能比的严格数学定义与验收（Bidding Volume Ratio Formal Definition）
- **分子（Numerator）—— 当日两市竞价总金额**：
  $$V_{bid} = A_{sh\_open} + A_{sz\_open} \quad (\text{单位：亿元})$$
  - $A_{sh\_open}$：上证指数集合竞价成交额（新浪 `s_sh000001` 的 `parts[5]` 万元 $\div 10000$）；
  - $A_{sz\_open}$：深证成指集合竞价成交额（新浪 `s_sz399001` 的 `parts[5]` 万元 $\div 10000$）；
  - 注：基线以沪深两市为主口径，确保与历史统计学口径对齐。
- **分母（Denominator）—— 严格数学定义与数据绑定**：
  $$V_{base} = \text{前一交易日沪深两市全天总成交金额} \quad (\text{单位：亿元})$$
  - **数据来源严格冻结**：必须直接继承前一日已持久化封口的 M1.4 复盘事实 `yesterday_review.market_state.dimensions.D6.metrics.total_amount`（两市全天成交总额，已在 1A.3 验收闭环）；
  - **统计口径对称性铁律**：严禁分子用“两市”而分母单用“上证”，也严禁分子用“上证”而分母用“两市”，分子分母必须在且仅在“沪深两市（或全市场）”同一物理边界内正交对应；
  - **分母缺失与 0 值防御铁律**：
    - 若前一日为长假后首日、或者数据库无前日复盘（$V_{base}$ 为 `None` 或 $\le 0$）：
      $$\text{竞价量能比 } R_{bid} = \text{None} \quad (\text{前端渲染为 } \text{'--'})$$
    - **严禁**使用硬编码预设值（如默认 10000 亿或 8000 亿）作为分母假造比值！
- **比值计算与物理刻度标准**：
  $$R_{bid} = \frac{V_{bid}}{V_{base}} \times 100\%$$
  - 物理承接状态标尺（基于 A 股全市场历史统计学分位数）：
    - $R_{bid} \ge 1.50\%$：【竞价活跃放量】（开盘资金承接极度踊跃，短线情绪充盈，易产生主线题材与连板高溢价）；
    - $1.00\% \le R_{bid} < 1.50\%$：【竞价平量承接】（开盘交投处于均衡常态，多空力量平稳）；
    - $0.60\% \le R_{bid} < 1.00\%$：【竞价缩量观望】（开盘资金参与意愿谨慎，防范冲高回落与存量轮动）；
    - $R_{bid} < 0.60\%$：【竞价极端地量】（流动性极度匮乏或极端避险）。

---

## 三、前后端数据契约定义

### 3.1 后端 REST API 契约补全
在 `backend/app/api/v1/reports.py` 中新增/强化以下端点：

1. **`GET /api/v1/reports/auction`（归档列表）**：
   - 入参：`limit: int = 30, offset: int = 0`
   - 返回：
     ```json
     {
       "code": 200,
       "data": {
         "items": [
           {
             "id": 1,
             "date": "2026-09-24",
             "emotion_judgment": "平开中性震荡分化",
             "bidding_amount_yi": 85.6,
             "bidding_ratio": 1.15,
             "one_word_up_count": 3,
             "one_word_down_count": 0,
             "generated_at": "2026-09-24T09:25:30"
           }
         ],
         "total": 1
       }
     }
     ```
2. **`GET /api/v1/reports/auction/{date}`（全景详情）**：
   - 返回结构化反序列化的完整对象：
     ```json
     {
       "code": 200,
       "data": {
         "id": 1,
         "date": "2026-09-24",
         "index_open_data": {
           "indices": [
             { "code": "000001", "name": "上证指数", "price": 3120.5, "change": 2.3, "pct_change": 0.07, "amount_wan": 450000 },
             { "code": "399001", "name": "深证成指", "price": 10500.2, "change": -10.5, "pct_change": -0.10, "amount_wan": 520000 },
             { "code": "399006", "name": "创业板指", "price": 2150.8, "change": -3.2, "pct_change": -0.15, "amount_wan": 210000 }
           ],
           "total_bidding_amount_yi": 97.0,
           "yesterday_total_amount_yi": 8500.0,
           "bidding_volume_ratio": 1.14
         },
         "one_word_count": 3,
         "high_open_stats": {
           "one_word_up_count": 3,
           "one_word_down_count": 0,
           "tested_count": 12,
           "high_open_count": 8,
           "low_open_count": 4,
           "high_open_ratio": 66.7,
           "avg_premium_pct": 2.45,
           "max_board_info": {
             "symbol": "600XXX",
             "name": "某高标",
             "board_height": 5,
             "open_pct": 5.2,
             "is_one_word": false
           },
           "extreme_stocks": [
             { "symbol": "000XXX", "name": "抢筹股A", "open_pct": 9.9, "tag": "竞价顶板抢筹" },
             { "symbol": "600YYY", "name": "分歧股B", "open_pct": -4.5, "tag": "大幅低开分歧" }
           ]
         },
         "emotion_judgment": {
           "label": "平开中性震荡分化",
           "narrative": "今日早盘两市竞价总金额约 97 亿元，占前日全天成交额比值为 1.14%，竞价交投意愿处于中性平稳区间。昨日 5 板最高空间标的高开 5.2% 保持承接，昨日涨停梯队平均溢价 2.45%，高开率 66.7%。一字涨停 3 家，无一字跌停核按钮，尾部极端情绪维持收敛，开盘整体呈现平开震荡分化格局。",
           "disclaimer": "客观观察维度提示，非买卖建议"
         },
         "generated_at": "2026-09-24T09:25:30"
       }
     }
     ```
3. **`POST /api/v1/reports/auction/generate`（一键生成）**：
   - 触发 09:25 实时或指定日期的竞价报告生成与落库。

### 3.2 前端 TypeScript 强类型契约 (`frontend/src/types/report.ts`)
```typescript
export interface IndexOpenItem {
  code: string;
  name: string;
  price: number | null;
  change: number | null;
  pct_change: number | null;
  amount_wan: number | null;
}

export interface IndexOpenOverview {
  indices: IndexOpenItem[];
  total_bidding_amount_yi: number | null;
  yesterday_total_amount_yi: number | null;
  bidding_volume_ratio: number | null;
}

export interface HighTierAuctionStock {
  symbol: string;
  name: string;
  board_height?: number | null;
  open_pct: number | null;
  is_one_word?: boolean;
  tag?: string;
}

export interface AuctionHighOpenStats {
  one_word_up_count: number;
  one_word_down_count: number;
  tested_count: number;
  high_open_count: number;
  low_open_count: number;
  high_open_ratio: number | null;
  avg_premium_pct: number | null;
  max_board_info?: HighTierAuctionStock | null;
  extreme_stocks?: HighTierAuctionStock[];
}

export interface AuctionEmotionJudgment {
  label: string;
  narrative: string;
  disclaimer: string;
}

export interface AuctionReportDetail {
  id?: number;
  date: string;
  index_open_data: IndexOpenOverview;
  one_word_count: number;
  high_open_stats: AuctionHighOpenStats;
  emotion_judgment: AuctionEmotionJudgment;
  generated_at?: string | null;
}

export interface AuctionReportSummaryItem {
  id: number;
  date: string;
  emotion_label: string;
  bidding_amount_yi: number | null;
  bidding_ratio: number | null;
  one_word_up_count: number;
  one_word_down_count: number;
  generated_at: string | null;
}
```

---

## 四、前端全景看板产品化设计

### 4.1 归档列表页 (`frontend/src/app/auction/page.tsx`)
- 淘汰现有占位符，升级为生产级动态归档看板：
  - 头部导航、一键生成今日竞价报告按钮、刷新按钮；
  - 列表卡片展示：日期、开盘客观承接标签（徽章颜色对齐 5 级客观物理刻度）、两市竞价金额、量能承接比（活跃/平量/缩量状态指示）、一字涨停/跌停数、生成时间、点击进入全景详情。

### 4.2 全景详情页 (`frontend/src/app/auction/[date]/page.tsx`)
打造面向专业交易员的 09:25 集合竞价作战看板，划分为四大核心功能卡片：
1. **模块一：全景指数开盘跳空与竞价量能比值网格**：
   - 上证指数、深证成指、创业板指、科创50 卡片，呈现开盘点位、跳空幅度与竞价成交额；
   - 核心量能承接柱状/指标：两市竞价成交总额（亿元）及其占前日比例（%），直观标识量能充盈度；
2. **模块二：09:25 开盘客观情绪承接研判与 M2 推演事实验证**：
   - 顶部全景免责风险横幅（“客观观察维度提示，非买卖建议”）；
   - 客观承接物理标签大徽章（如【放量高开偏强承接】）；
   - M2 盘前 4 维推演回看与兑现核验述评（严格的事实验证对比，绝无预测准确率打分）；
3. **模块三：高标梯队竞价溢价与连板生态看板**：
   - 最高连板股开盘溢价与封单表现；
   - 昨日连板梯队平均溢价率、高开比例（%）；
   - 一字涨停家数 vs 一字跌停（核按钮）家数对比；
4. **模块四：开盘竞价异动池（抢筹与核按钮关注）**：
   - 竞价大幅高开抢筹标的 vs 大幅低开分歧标的列表（代码、名称、开盘幅、异动特征说明）。

---

## 五、合规与工程铁律保障方案（7 大铁律对照）

1. **零填充防伪铁律 (Zero-Falsification)**：
   - 指数开盘点位、竞价额、个股溢价率在数据源未就绪或未开盘时，严格保持 `None`，前端统一显示 `'--'`；
   - 真实 0% 开盘（平开）与 0 跌停严格显示为 `0.00%` 或 `0 家`，严禁伪造默认值。
2. **抗标量塌缩与正交继承 (Anti-Scalar-Collapse)**：
   - M3 消费 M1 状态向量时，严格只读引用，坚决不在 M3 对 D1~D6 进行重新加权或标量均值压缩；
   - D3 核心得分在 M3 中继续保持为 `None`。
3. **物理极性与交易信号隔离 (Polarity Isolation)**：
   - 严禁在竞价报告中出现“建议买入、开盘打板、挂单卖出、积极做多”等诱导性交易黑话；
   - 所有承接研判统一表述为“客观多空物理承接测量”，全网逐项绑定免责声明。
4. **分类标签客观化 (Objective Labeling)**：
   - 情绪研判统一采用客观物理描述，淘汰主观情绪化词汇。
5. **真实数据端到端验证 (Real-Data Evidence)**：
   - 接入新浪官方真实接口获取开盘数据，编写 `verify_m3_auction.py` 自动化端到端测试脚本。
6. **零 Mock 残留与纯净架构 (Clean Architecture)**：
   - 物理清除 `frontend/src/app/auction/page.tsx` 中的“Coming in Phase 2”占位符；
   - Next.js 生产构建 (`next build`) 保持 100% 编译通过，0 错误，0 警告。
7. **严格遵循四权分立治理规范**：
   - 实施完成后提交本地 Git，依次移交独立红队特使（`red_team_tester`）攻击渗透与独立质量发布闸门裁判（`quality_gatekeeper`）终审放行，最终呈递董事会封口。

---

## 六、实施分工与执行工序（Plan 实施层排期）

- **Task 1: 后端数据与计算增强**
  - 在 `backend/app/data/providers/sina.py` 补充完善开盘多标的批处理与量能提取，支持 09:25 时间戳一致性与可得性检查；
  - 在 `backend/app/services/auction.py` 实现完整 M3 业务编排（指数聚合、量能承接比严格分母计算、高标溢价统计、一字板识别与承接研判）；
- **Task 2: API 契约补全与自动化单测**
  - 在 `backend/app/api/v1/reports.py` 实现 `/auction` 列表分页、详情反序列化与生成接口；
  - 编写 `backend/tests/test_api.py` 与 `backend/scripts/verify_m3_auction.py` 自动化验证脚本；
- **Task 3: 前端强类型与全景看板重构**
  - 更新 `frontend/src/types/report.ts` 契约定义；
  - 更新 `frontend/src/lib/api.ts` 新增竞价 API 方法；
  - 重写 `frontend/src/app/auction/page.tsx`（归档列表）与 `frontend/src/app/auction/[date]/page.tsx`（全景作战看板）；
  - 运行 `npm run build` 确保 100% 编译成功；
- **Task 4: 四权分立审计与闭环**
  - 提交本地 Git commit；
  - 唤醒 `red_team_tester` 执行 Step 3 攻击渗透测试；
  - 唤醒 `quality_gatekeeper` 执行 Step 4 终审裁决；
  - 呈报最高董事会做最终签章。
