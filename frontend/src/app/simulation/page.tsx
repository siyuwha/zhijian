'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { 
  PlaySquare, 
  Wallet, 
  TrendingUp, 
  ShieldCheck, 
  ArrowUpRight, 
  Clock, 
  CheckCircle2, 
  AlertTriangle,
  RotateCcw,
  Zap,
  Sliders,
  DollarSign
} from 'lucide-react';

export default function SimulationPage() {
  const [activeTab, setActiveTab] = useState<'positions' | 'orders' | 'risk'>('positions');

  return (
    <div className="min-h-screen px-4 md:px-6 py-6 max-w-[1780px] mx-auto space-y-6 select-none">
      
      {/* 顶部标题横幅 */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-2 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl md:text-2xl font-black text-white tracking-wide flex items-center gap-2">
              <span className="w-8 h-8 rounded-lg bg-gradient-to-tr from-cyan-600 to-indigo-600 flex items-center justify-center text-white text-sm shadow-md">
                模
              </span>
              模拟交易沙盒 · 自动演练台账
            </h1>
            <span className="px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/35 text-xs font-mono font-bold flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              虚拟 PaperBroker 运行中 · 严格 A 股 T+1
            </span>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-1">
            由方案 B 策略全自动驱动建仓 · 真实计算印花税 (0.05%)、佣金 (万一) 与 0.1% 冲击滑点
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Link 
            href="/strategy"
            className="px-3.5 py-1.5 rounded-xl bg-white/10 hover:bg-white/15 border border-white/10 text-xs font-semibold text-slate-200 transition flex items-center gap-1.5"
          >
            <Sliders className="w-3.5 h-3.5 text-purple-400" />
            <span>调整策略参数</span>
          </Link>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 账户资产三足鼎立卡 (三宫格 Bento) */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 总资产卡 */}
        <div className="glass-card rounded-2xl p-5 bg-white/[0.02] border border-white/10 space-y-2">
          <div className="flex justify-between items-center text-xs text-slate-400">
            <span>虚拟账户总资产</span>
            <span className="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono text-[10px] font-bold">浮盈 +4.82%</span>
          </div>
          <div className="text-2xl font-black font-mono text-white tabular-nums">
            1,048,200.00 <span className="text-xs font-normal text-slate-400">元</span>
          </div>
          <div className="text-xs font-mono text-rose-400 flex items-center gap-1">
            <TrendingUp className="w-3.5 h-3.5" />
            <span>当日浮动盈亏: +48,200.00 元</span>
          </div>
        </div>

        {/* 可用现金 */}
        <div className="glass-card rounded-2xl p-5 bg-white/[0.02] border border-white/10 space-y-2">
          <div className="flex justify-between items-center text-xs text-slate-400">
            <span>可用现金 (Cash)</span>
            <span className="text-slate-500 font-mono text-[10px]">初始金 100 万</span>
          </div>
          <div className="text-2xl font-black font-mono text-white tabular-nums">
            698,200.00 <span className="text-xs font-normal text-slate-400">元</span>
          </div>
          <div className="text-xs text-slate-400 font-mono">
            现金储备率: <span className="text-emerald-400 font-bold">66.6%</span>
          </div>
        </div>

        {/* 当前持仓市值与仓位 */}
        <div className="glass-card rounded-2xl p-5 bg-white/[0.02] border border-white/10 space-y-2">
          <div className="flex justify-between items-center text-xs text-slate-400">
            <span>持仓总市值 (2 只标的)</span>
            <span className="text-amber-400 font-mono text-[10px]">符合大盘建议仓位</span>
          </div>
          <div className="text-2xl font-black font-mono text-white tabular-nums">
            350,000.00 <span className="text-xs font-normal text-slate-400">元</span>
          </div>
          <div className="text-xs text-slate-400 font-mono">
            当前仓位: <span className="text-amber-400 font-bold">33.4%</span> (建议 30%~50%)
          </div>
        </div>

        {/* 胜率与累计交易统计 */}
        <div className="glass-card rounded-2xl p-5 bg-white/[0.02] border border-white/10 space-y-2">
          <div className="flex justify-between items-center text-xs text-slate-400">
            <span>实战演练统计</span>
            <span className="text-slate-500 font-mono text-[10px]">近 30 天</span>
          </div>
          <div className="text-2xl font-black font-mono text-rose-400 tabular-nums">
            71.4% <span className="text-xs font-normal text-slate-400">(5/7 胜)</span>
          </div>
          <div className="text-xs text-slate-400 font-mono">
            盈亏比: <span className="text-white font-bold">2.85 : 1</span> | 摩擦损耗: 397 元
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 选项卡切换 (持仓明细 / 当日成交流水 / 波普尔止损风控) */}
      {/* ========================================================================= */}
      <div className="glass-card rounded-2xl p-5 bg-white/[0.02] border border-white/10 space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-white/10">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab('positions')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
                activeTab === 'positions'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>当前模拟持仓明细 (2)</span>
            </button>
            <button
              onClick={() => setActiveTab('orders')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
                activeTab === 'orders'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>今日自动委托与成交流水 (2)</span>
            </button>
            <button
              onClick={() => setActiveTab('risk')}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
                activeTab === 'risk'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>波普尔证伪与止损哨兵</span>
            </button>
          </div>
          <span className="text-xs font-mono text-slate-500">更新频率: 盘中每 3 秒</span>
        </div>

        {/* 1. 当前持仓列表 */}
        {activeTab === 'positions' && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono border-collapse">
              <thead>
                <tr className="border-b border-white/10 text-slate-400">
                  <th className="py-2.5 px-3">代码/名称</th>
                  <th className="py-2.5 px-3">触发策略</th>
                  <th className="py-2.5 px-3 text-right">持股数 / 可用</th>
                  <th className="py-2.5 px-3 text-right">买入成本</th>
                  <th className="py-2.5 px-3 text-right">当前现价</th>
                  <th className="py-2.5 px-3 text-right">持仓市值</th>
                  <th className="py-2.5 px-3 text-right">浮动盈亏</th>
                  <th className="py-2.5 px-3 text-center">T+1 状态</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-slate-200">
                {/* 标的 1: 百洋股份 */}
                <tr className="hover:bg-white/[0.02] transition">
                  <td className="py-3 px-3">
                    <div className="font-bold text-white text-sm font-sans">百洋股份</div>
                    <div className="text-[11px] text-slate-400">002696 · 渔业龙头</div>
                  </td>
                  <td className="py-3 px-3">
                    <span className="px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 text-[10px] font-bold">
                      09:25 弱转强竞价抢筹
                    </span>
                  </td>
                  <td className="py-3 px-3 text-right tabular-nums">
                    <div>29,300 股</div>
                    <div className="text-[10px] text-amber-400">0 股可用 (T+1锁定)</div>
                  </td>
                  <td className="py-3 px-3 text-right tabular-nums text-slate-300">6.350</td>
                  <td className="py-3 px-3 text-right tabular-nums text-rose-400 font-bold text-sm">6.820</td>
                  <td className="py-3 px-3 text-right tabular-nums">199,826 元</td>
                  <td className="py-3 px-3 text-right tabular-nums text-rose-400 font-bold">
                    <div>+13,771.00 元</div>
                    <div className="text-[10px]">+7.40%</div>
                  </td>
                  <td className="py-3 px-3 text-center">
                    <span className="px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 text-[10px] border border-amber-500/30">
                      今日买入 · 次日可卖
                    </span>
                  </td>
                </tr>

                {/* 标的 2: 慈文传媒 */}
                <tr className="hover:bg-white/[0.02] transition">
                  <td className="py-3 px-3">
                    <div className="font-bold text-white text-sm font-sans">慈文传媒</div>
                    <div className="text-[11px] text-slate-400">002343 · 影视短剧</div>
                  </td>
                  <td className="py-3 px-3">
                    <span className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 text-[10px] font-bold">
                      盘中主线首板突破
                    </span>
                  </td>
                  <td className="py-3 px-3 text-right tabular-nums">
                    <div>21,000 股</div>
                    <div className="text-[10px] text-amber-400">0 股可用 (T+1锁定)</div>
                  </td>
                  <td className="py-3 px-3 text-right tabular-nums text-slate-300">7.050</td>
                  <td className="py-3 px-3 text-right tabular-nums text-rose-400 font-bold text-sm">7.150</td>
                  <td className="py-3 px-3 text-right tabular-nums">150,150 元</td>
                  <td className="py-3 px-3 text-right tabular-nums text-rose-400 font-bold">
                    <div>+2,100.00 元</div>
                    <div className="text-[10px]">+1.42%</div>
                  </td>
                  <td className="py-3 px-3 text-center">
                    <span className="px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 text-[10px] border border-amber-500/30">
                      今日买入 · 次日可卖
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {/* 2. 成交流水表 */}
        {activeTab === 'orders' && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono border-collapse">
              <thead>
                <tr className="border-b border-white/10 text-slate-400">
                  <th className="py-2.5 px-3">委托时间</th>
                  <th className="py-2.5 px-3">证券代码/名称</th>
                  <th className="py-2.5 px-3">方向</th>
                  <th className="py-2.5 px-3 text-right">委托股数</th>
                  <th className="py-2.5 px-3 text-right">成交均价</th>
                  <th className="py-2.5 px-3 text-right">成交总额</th>
                  <th className="py-2.5 px-3 text-right">手续费+滑点</th>
                  <th className="py-2.5 px-3 text-center">状态</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-slate-200">
                <tr>
                  <td className="py-2.5 px-3 text-slate-400">09:30:02</td>
                  <td className="py-2.5 px-3 font-bold text-white font-sans">002696 百洋股份</td>
                  <td className="py-2.5 px-3 text-rose-400 font-bold">买入 (自动)</td>
                  <td className="py-2.5 px-3 text-right tabular-nums">29,300</td>
                  <td className="py-2.5 px-3 text-right tabular-nums">6.350</td>
                  <td className="py-2.5 px-3 text-right tabular-nums">186,055 元</td>
                  <td className="py-2.5 px-3 text-right tabular-nums text-slate-400">232.50 元</td>
                  <td className="py-2.5 px-3 text-center text-emerald-400 font-bold">全部成交</td>
                </tr>
                <tr>
                  <td className="py-2.5 px-3 text-slate-400">09:42:15</td>
                  <td className="py-2.5 px-3 font-bold text-white font-sans">002343 慈文传媒</td>
                  <td className="py-2.5 px-3 text-rose-400 font-bold">买入 (自动)</td>
                  <td className="py-2.5 px-3 text-right tabular-nums">21,000</td>
                  <td className="py-2.5 px-3 text-right tabular-nums">7.050</td>
                  <td className="py-2.5 px-3 text-right tabular-nums">148,050 元</td>
                  <td className="py-2.5 px-3 text-right tabular-nums text-slate-400">165.10 元</td>
                  <td className="py-2.5 px-3 text-center text-emerald-400 font-bold">全部成交</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {/* 3. 波普尔证伪监控 */}
        {activeTab === 'risk' && (
          <div className="space-y-3">
            <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-xs space-y-1.5">
              <div className="font-bold text-amber-300 flex items-center gap-1.5">
                <AlertTriangle className="w-4 h-4" />
                <span>百洋股份 (002696) · 证伪哨兵规则已挂载</span>
              </div>
              <p className="text-slate-300 leading-relaxed font-mono">
                防守底线：分时黄色均价线 6.65 元。若发生炸板下破且 3 分钟内无法回封，次日开盘若低开超 -2% 执行抢跑止损。
              </p>
            </div>

            <div className="p-3.5 rounded-xl bg-purple-500/10 border border-purple-500/30 text-xs space-y-1.5">
              <div className="font-bold text-purple-300 flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4" />
                <span>慈文传媒 (002343) · 均线承接监控中</span>
              </div>
              <p className="text-slate-300 leading-relaxed font-mono">
                防守底线：买入价 -2.5% (6.87 元)。当前涨停封单强劲，继续保持观察。
              </p>
            </div>
          </div>
        )}
      </div>

    </div>
  );
}
