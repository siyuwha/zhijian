# 交易数据源接口清单（接口级，供新 AI 交易系统直接继承）

> 生成：2026-09-15，从 Trading AI OS 生产脚本逐行提取（closure_run_*.py、daily_review_v12.py、premarket_collect_*.py、check_auction_data.py、find_market_stats*.py、test_sector_em.py）。
> 每个接口含：URL、必需 header、参数、字段映射、已踩坑。新系统接数据源时直接按此实现，勿重新试错。
> 按 Owner 指令：**TDX 本地接口（PC 192.168.3.15:8080/8081）不继承**，本清单不含。

---

## 1. 新浪 Sina — hq.sinajs.cn（主力实时/前收/隔夜行情）

**基础接口**
```
GET https://hq.sinajs.cn/list={codes}
Headers（必需，缺 Referer 会被拒）:
  Referer: https://finance.sina.com.cn
  User-Agent: Mozilla/5.0 ...
响应编码: GBK
```

**行情代码前缀与字段映射**（按 `line.split('"')[1].split(",")` 取 parts）

| 前缀 | 示例代码 | 用途 | 关键字段 |
|---|---|---|---|
| `s_` | s_sh000001, s_sz399001, s_sz399006, s_sh000688, s_sh000016 | A股指数 | [0]=名称 [1]=现价/收盘 [2]=昨收 [3]=涨跌幅% [5]=成交额(万) |
| 无前缀 | sh600354 / sz300xxx | A股个股 | [0]=名称 [1]=今开 [2]=昨收 [3]=现价 [4]=最高 [5]=最低 [8]=成交量 |
| `gb_` | gb_dji, gb_ixic, gb_inx | 美股隔夜 | [0]=名称 [1]=收盘 [2]=涨跌幅% [3]=日期 [4]=涨跌点数 |
| `b_` | b_HSI, b_FSSTI, b_N225, b_KQ11, b_TWII | 亚太指数 | [0]=名称 [1]=点位 [2]=涨跌点 [3]=涨跌幅% |
| `hf_` | hf_CL, hf_GC, hf_SI | 商品期货 | [0]=现价 [8]=昨收 [13]=名称 |

**坑（已验证）**
- 批量查询 URL 超长会**静默失败**（40 只一批返回空）→ 分 10 只一批 + `time.sleep(0.3)`。
- `parts[2]`（昨收）= 上一交易日收盘，可直接拿次日数据验证选股（无需历史接口）。
- 指数 `s_` 序列用于核对交易日（容器时钟会跳，勿信容器 date）。

**新浪新闻聚合（盘前简报用）**
```
GET https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid={lid}&k=&num=10&page=1
lid ∈ {2509, 2516, 2544}  → data.result.data[]: {media_name, title}
```

---

## 2. 东方财富 — push2.eastmoney.com（板块/涨停池/资金流）

**通用 Headers**: `User-Agent` + `Referer: https://quote.eastmoney.com/`（部分接口）

| 接口 | URL | 说明 |
|---|---|---|
| 指数实时 | `/api/qt/ulist.np/get?fltt=2&fields=f2,f3,f4,f12,f14&secids=1.000001,0.399001,0.399006,1.000688&uf=123&pi=0&pz=5` | secid: 1.=沪 0.=深 |
| 行业板块排行 | `/api/qt/clist/get?pn=1&pz=5&po=1&np=1&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f2,f3,f14,f62` | `fs=m:90+t:2`=行业，`m:90+t:3`=概念；f2=价 f3=涨跌幅 f14=名称 f62=主力净流入 |
| 涨停池 | 同上 clist，`fs=m:0+t:T&fields=f2,f3,f14`（基础）；扩展字段 `fbt`=首次封板时间（如 92500=09:25，前 4 位 HHMM；上午涨停判定 `int(fbt[:4])<1130`）、`hybk`=行业板块 | ⚠️ hybk 是**行业**维度≠题材维度，题材共振要看同花顺 reason_type |
| 资金流(分时) | `/api/qt/stock/fflow/kline/get?secid=1.000001&fields=f51,f52,f53,f54,f55` | |
| 资金流(日) | `/api/qt/stock/fflow/day/get?secid=1.000001&fields=f57,f58,f59,f169,f170,f171` | |
| 大盘概况 | `/api/qt/summary/get?fltt=2&fields=f58,f107,f57,f43,f169,f170,f171&secids=1.000001` | |
| 全市场涨跌分布 | clist + `fs=m:0+t:6,m:0+t:80,m:0+t:81,m:0+t:82&fields=f12,f100,f62` | 8/10 验证时容器内时通时断，NAS 侧可用，接入前实测 |

**坑（已验证）**
- **盘外返回价 0 会误触发告警**（8/24 教训）→ 所有东财实时数据消费必须 `is_trading_time() and 价>0` 双查。
- `ut=bd1d9ddb04089700cf9c27f6f7426281` 是固定 token，直接照抄。

---

## 3. 同花顺 — data.10jqka.com.cn（涨停池，情绪/连板/题材核心源）

```
GET https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool
params: page=1&limit=200&date={YYYYMMDD}&field=199112,10,9001,330323,330324,330325,9002,330329,133971,133970,1968584,3475914,9003,9004
Headers: User-Agent + Referer: https://data.10jqka.com.cn/
```

**响应结构**
- `data.info[]`：`code / name / reason_type / change_tag / high_days / limit_up_type`
- `data.limit_up_count.today.{num, history_num, open_num}`：涨停总数 / 昨涨停今续涨 / 开盘涨停
- `data.limit_down_count.today.{num, history_num}`：跌停总数 / 昨跌停今续跌

**字段用法**
- `change_tag`：`ONE_WORD`=一字板，`FIRST_LIMIT`=首板，`LIMIT_BACK`=回封/连板
- `reason_type` 按 `+` 拆分后做 Counter → 主线关键词/板块集中度（板块归因的核心输入）
- `high_days` 中文标签（"N天M板"/"首板"）→ 连板梯队统计（正则 `(\d+)天(\d+)板`）

**已知限制**
- ❌ 不提供**炸板率** → 复盘报告的"炸板率>70% 硬规则"目前无法触发（8/31 冰点日炸板率 51.94% 是手工补的），新系统若要启用该规则须补数据源。
- 备用端点：`/dataapi/limit_up/daily_limit_up`（已试通，字段未固化，接入时实测）。

---

## 4. 财联社 CLS — www.cls.cn（盘前快讯）

```
GET https://www.cls.cn/v1/roll/get_roll_list?{qs}&sign={sign}
sign 算法: sign = md5( sha1( 按key排序后的query string ) )
Headers: User-Agent + Referer: https://www.cls.cn/
```

两个已验证的参数变体：
- A（check_auction_data.py）：`app=CailianpressWeb&category=&last_time={ts}&os=web&rn=5&sv=81.1.2` → `data.roll_data.list[].title`
- B（premarket_collect）：`appName=CailianpressWeb&os=web&sv=7.7.5&last_time=&refresh_type=1&rn=30` → `data.roll_data[].{ctime, title, brief}`

---

## 5. baostock（指数结算，优先源）

```python
import baostock as bs
bs.login()
rs = bs.query_history_k_data_plus(
    "sh.000001",                       # 指数代码: sh.000001/sz.399001/sz.399006/sh.000688
    "date,open,high,low,close,volume,amount,pctChg",
    start_date=td, end_date=td, frequency="d", adjustflag="3")
row = rs.get_row_data()   # [date, open, high, low, close, volume, amount, pctChg] 字符串
bs.logout()
```

**降级策略（daily_review_v12 生产模式）**：当日数据缺失（baostock 结算延迟）→ fallback Sina `s_` 实时行情，数据质量标 PARTIAL 而非 INVALID。

---

## 6. 模型服务（非行情源，但 pipeline 依赖）

| 服务 | 端点 / 配置 | 用途 |
|---|---|---|
| DeepSeek | `https://api.deepseek.com/v1/chat/completions`；`deepseek-v4-flash`（对话）/ `deepseek-v4-pro`（Cognition 层） | LLM 推理，key=`DEEPSEEK_API_KEY`（.env） |
| DashScope | `qwen3-vl-32b`（视觉） | 持仓截图/图像识别，key=`DASHSCOPE_API_KEY`（.env） |

---

## 继承建议（场景→接口映射）

| 场景 | 接口组合 |
|---|---|
| 盘前简报 | CLS(B 变体) + Sina 美股/亚太/期货 + Sina A 股前收 + Sina 新闻(lid) |
| 竞价观察 | Sina `s_` 指数开盘 + 同花顺涨停池(num/history_num/open_num、一字、change_tag) |
| 收盘复盘 | baostock 指数（Sina fallback）+ 同花顺涨停池(情绪/连板/题材/龙头 Top20) |
| 盘中盯盘 | 东财 clist/涨停池 + Sina 个股实时；双查 is_trading_time + 价>0 |

## 明确不继承 / 不可得

- TDX 本地 HTTP 接口（PC 192.168.3.15:8080 K线 / 8081 板块，源 `D:\new_tdx64`）——Owner 指令剔除。
- 竞价逐笔 / Level-2 / 封单盘口深度 / 竞价量比——公开接口不提供（8/10 竞价概述验证结论，公开 API 仅能覆盖约 40% 竞价需求）。

## 源文件索引（想核对实现时）

- `/opt/data/daily_review_v12.py` — baostock+同花顺+Sina fallback 全链路
- `/opt/data/closure_run_2026082*.py` — Sina 收盘结算 + 同花顺涨停池（生产 cron 版）
- `/opt/data/premarket_collect_20260810.py` — 盘前全接口采集样板
- `/opt/data/check_auction_data.py` — 竞价源可行性验证 + CLS 变体 A
- `/opt/data/test_sector_em.py`、`/opt/data/find_market_stats*.py` — 东财板块/统计接口探活
