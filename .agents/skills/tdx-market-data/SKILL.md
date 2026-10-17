---
name: tdx-market-data
description: 通达信原生行情直连数据获取技能。基于 pytdx 协议在无需开启任何通达信客户端的情况下，毫秒级直连通达信券商行情主站，获取 A 股全市场实时五档快照、241分钟分时走势、多周期 K 线历史、逐笔成交明细、大盘指数与除权除息股本信息。原生兼容 NAS Linux Docker 无头环境。
metadata: {"openclaw":{"emoji":"⚡","requires":{"bins":["python"]}}}
---

# 通达信原生行情直连技能 (TDX Direct Market Data Skill)

## 一、技能定位与适用场景
- **核心定位**：用于在**完全不开启通达信客户端**、**无需 Windows 图形界面**的纯服务器或 Docker 环境下，直接通过 TCP Socket 协议连接通达信全国高速行情服务器，获取高质量、高保真的 A 股实时与历史行情。
- **运行环境**：100% 纯 Python 编写，原生兼容 **NAS 飞牛私有云 (fnOS)**、**Linux Docker 容器**及本地 Windows 开发环境。
- **主要能力**：
  1. **实时五档快照**（`market_quote.py`）：买一至买五、卖一至卖五挂单量、最新价、成交量、成交额（支持单只或批量标的）；
  2. **全天 241 分钟分时走势**（`minute_trend.py`）：09:30~15:00 连续 241 点完整价格与成交量，彻底解决分时截断或水平拉平问题；
  3. **多周期历史 K 线**（`kline_history.py`）：日线、5分钟、1分钟、15分钟、30分钟、60分钟 OHLCV 历史数据；
  4. **逐笔分笔成交明细**（`tick_detail.py`）：秒级逐笔明细，标注主动买盘、主动卖盘与中性盘，用于短线炸板和资金异动推演；
  5. **大盘核心指数**（`index_quote.py`）：上证指数、深证成指、创业板指、科创50收盘与成交额；
  6. **主站健康与测速**（`server_pool.py`）：自动探测主站池延迟，自动故障迁移。

## 二、意图识别与脚本路由表

| 用户/系统意图 | 调用命令示例 | 输出关键字段 |
|---|---|---|
| 查看个股实时五档/现价 | `python scripts/market_quote.py --code 600519` | `price`, `pct_chg`, `bid1~5`, `ask1~5`, `amount_yi` |
| 批量查询多只个股盘口 | `python scripts/market_quote.py --code 600519,000001,300750` | 批量数组，包含每只股票的最新五档与成交额 |
| 获取个股全天分时走势图 | `python scripts/minute_trend.py --code 600519` | 241 点数组：`minute_idx`, `price`, `vol` |
| 查询历史日 K 线 | `python scripts/kline_history.py --code 600519 --period 1d --count 100` | `datetime`, `open`, `high`, `low`, `close`, `amount_yi` |
| 查询 5分钟 / 1分钟分时K线 | `python scripts/kline_history.py --code 000001 --period 5m --count 48` | 分钟级 OHLCV 数据棒线 |
| 查看盘中逐笔大单/成交明细 | `python scripts/tick_detail.py --code 600519 --count 30` | `time`, `price`, `vol`, `direction` (买盘/卖盘) |
| 查询大盘指数概况 | `python scripts/index_quote.py` | 上证/深证/创业板/科创50最新点位与两市成交额 |
| 诊断通达信服务器状态 | `python scripts/server_pool.py` | 主站在线状态与网络延迟排名 |

## 三、输出数据契约规范 (JSON Contract)

所有脚本执行后统一向 `stdout` 输出结构化 JSON：
```json
{
  "status": "success",
  "count": 1,
  "data": [
    {
      "code": "600519",
      "market": 1,
      "price": 1329.0,
      "last_close": 1313.0,
      "pct_chg": 1.22,
      "open": 1311.57,
      "high": 1329.88,
      "low": 1301.68,
      "vol": 38500,
      "amount": 5076000000,
      "amount_yi": 50.76,
      "bid1": 1328.58, "bid_vol1": 1,
      "ask1": 1329.0, "ask_vol1": 54
    }
  ]
}
```

## 四、技术保障与容灾设计
1. **自动前缀解析**：支持传递纯数字代码（如 `600519`、`000001`）或带后缀代码（如 `600519.SH`、`000001.SZ`），模块内自动识别并分流到正确的交易所端口。
2. **多主站自动轮询与降级**：内置华泰证券、国联证券等多条优质线路，某一台主机若遇网络抖动或临时维护，客户端内部自动重试并切换下一台，外部调用无感知。
3. **与知见现有 API 协同**：可作为知见系统后台（`backend/app/data/providers/`）的一级直连数据源，与现有东方财富 API 形成主备双通道。
