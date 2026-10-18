'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { 
  Sliders, 
  Activity, 
  TrendingUp, 
  BarChart3, 
  Layers, 
  ShieldAlert, 
  Play, 
  CheckCircle2, 
  Clock, 
  Flame, 
  Zap, 
  ArrowUpRight,
  Info,
  RefreshCw,
  Sparkles
} from 'lucide-react';

export default function StrategyPage() {
  // 交互状态
  const [activeStage, setActiveStage] = useState<'ICE' | 'REPAIR' | 'RESONANCE' | 'OVERHEAT' | 'PANIC'>('REPAIR');
  const [volumeRatio, setVolumeRatio] = useState(12);
  const [openPct, setOpenPct] = useState(3.5);
  const [selectedStock, setSelectedStock] = useState('002696');
  const [isBacktesting, setIsBacktesting] = useState(false);
  const [backtestNotice, setBacktestNotice] = useState('');

  const handleRunBacktest = () => {
    setIsBacktesting(true);
    setBacktestNotice('正在进行 3 年样本外数据回测 (2023-2026)...');
    setTimeout(() => {
      setIsBacktesting(false);
      setBacktestNotice('回测完成：当前因子组合在 730 个交易日中累计年化收益 +46.8%，夏普比率 2.62');
    }, 800);
  };

  return (
    <div className="min-h-screen px-4 md:px-6 py-6 max-w-[1780px] mx-auto space-y-6 select-none">
      
      {/* ========================================================================= */}
      {/* 顶部标题横幅 (极光品牌头 + 第3阶段状态) */}
      {/* ========================================================================= */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-2 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl md:text-2xl font-black text-white tracking-wide flex items-center gap-2">
              <span className="w-8 h-8 rounded-lg bg-gradient-to-tr from-rose-600 to-purple-600 flex items-center justify-center text-white text-sm shadow-md">
                策
              </span>
              策略中心 · 量化工场全景
            </h1>
            <span className="px-2.5 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/35 text-xs font-mono font-bold flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />
              方案 B 正式载入 · 实战演练态
            </span>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-1">
            机构级量化全生命周期流水线：大盘情绪五阶段门禁 ➔ 盘口因子装配 ➔ 动态股票池 ➔ 双轨回测看板
          </p>
        </div>

        {/* 右侧环境提示 */}
        <div className="flex items-center gap-3">
          <div className="bg-black/50 border border-white/10 rounded-full px-3.5 py-1 text-xs flex items-center gap-2">
            <span className="text-slate-400">大盘周期:</span>
            <span className="font-bold text-amber-400">阶段 2 · 弱势修复期</span>
            <span className="text-slate-600">|</span>
            <span className="text-slate-400">建议仓位:</span>
            <span className="font-mono text-rose-400 font-bold tabular-nums">30%~50%</span>
          </div>
          <button 
            onClick={handleRunBacktest}
            className="px-3 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-md shadow-purple-600/30 transition flex items-center gap-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isBacktesting ? 'animate-spin' : ''}`} />
            <span>执行回测</span>
          </button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 顶部贯穿大屏：大盘情绪周期五阶段状态机与策略准入管线 */}
      {/* ========================================================================= */}
      <div className="glass-card rounded-2xl p-5 border-t-2 border-t-purple-500 bg-white/[0.02] border border-white/10">
        <div className="flex items-center justify-between mb-3.5">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-purple-400" />
            <h2 className="text-xs md:text-sm font-bold text-white uppercase tracking-wider">
              大盘情绪周期五阶段 · 策略动态准入状态机 (5-Stage Lifecycle Pipeline)
            </h2>
          </div>
          <span className="text-[11px] font-mono text-slate-400">
            根据微观结构数据，策略只在与之匹配的市场生命周期阶段自动放行或降仓保护
          </span>
        </div>

        {/* 5 阶段卡片横向流 */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {/* 阶段 1: 冰点分歧 */}
          <div 
            onClick={() => setActiveStage('ICE')}
            className={`p-3 rounded-xl border transition-all cursor-pointer ${
              activeStage === 'ICE' 
                ? 'bg-cyan-500/10 border-cyan-500/50 shadow-lg shadow-cyan-500/10' 
                : 'bg-black/40 border-white/5 opacity-60 hover:opacity-90'
            }`}
          >
            <div className="flex justify-between text-xs font-mono text-slate-300">
              <span className="font-bold">01. 冰点分歧</span>
              <span className="text-cyan-400">10%~20% 仓</span>
            </div>
            <div className="text-[11px] text-slate-400 mt-1.5">准入: 恐慌抄底、龙虎逆势低吸</div>
            <div className={`mt-2 h-1 rounded-full ${activeStage === 'ICE' ? 'bg-cyan-400' : 'bg-white/10'}`} />
          </div>

          {/* 阶段 2: 弱势修复 (当前激活) */}
          <div 
            onClick={() => setActiveStage('REPAIR')}
            className={`p-3 rounded-xl border transition-all cursor-pointer ${
              activeStage === 'REPAIR' 
                ? 'bg-amber-500/10 border-amber-500/50 shadow-lg shadow-amber-500/10 ring-1 ring-amber-500/30' 
                : 'bg-black/40 border-white/5 opacity-60 hover:opacity-90'
            }`}
          >
            <div className="flex justify-between text-xs font-mono">
              <span className="font-bold text-amber-300 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                02. 弱势修复 (当前)
              </span>
              <span className="text-amber-400 font-bold">30%~50% 仓</span>
            </div>
            <div className="text-[11px] text-slate-200 mt-1.5">准入: 09:25弱转强、首板共振反包</div>
            <div className={`mt-2 h-1 rounded-full ${activeStage === 'REPAIR' ? 'bg-amber-400' : 'bg-white/10'}`} />
          </div>

          {/* 阶段 3: 主线共振 */}
          <div 
            onClick={() => setActiveStage('RESONANCE')}
            className={`p-3 rounded-xl border transition-all cursor-pointer ${
              activeStage === 'RESONANCE' 
                ? 'bg-rose-500/10 border-rose-500/50 shadow-lg shadow-rose-500/10' 
                : 'bg-black/40 border-white/5 opacity-60 hover:opacity-90'
            }`}
          >
            <div className="flex justify-between text-xs font-mono text-slate-300">
              <span className="font-bold">03. 主线共振</span>
              <span className="text-rose-400">70%~100% 仓</span>
            </div>
            <div className="text-[11px] text-slate-400 mt-1.5">准入: 连板龙头接力、主升浪突破</div>
            <div className={`mt-2 h-1 rounded-full ${activeStage === 'RESONANCE' ? 'bg-rose-500' : 'bg-white/10'}`} />
          </div>

          {/* 阶段 4: 高潮过热 */}
          <div 
            onClick={() => setActiveStage('OVERHEAT')}
            className={`p-3 rounded-xl border transition-all cursor-pointer ${
              activeStage === 'OVERHEAT' 
                ? 'bg-purple-500/10 border-purple-500/50 shadow-lg shadow-purple-500/10' 
                : 'bg-black/40 border-white/5 opacity-60 hover:opacity-90'
            }`}
          >
            <div className="flex justify-between text-xs font-mono text-slate-300">
              <span className="font-bold">04. 高潮过热</span>
              <span className="text-purple-400">逢高减仓兑现</span>
            </div>
            <div className="text-[11px] text-slate-400 mt-1.5">准入: 仅尾盘防守、禁止追高</div>
            <div className={`mt-2 h-1 rounded-full ${activeStage === 'OVERHEAT' ? 'bg-purple-400' : 'bg-white/10'}`} />
          </div>

          {/* 阶段 5: 退潮恐慌 */}
          <div 
            onClick={() => setActiveStage('PANIC')}
            className={`p-3 rounded-xl border transition-all cursor-pointer ${
              activeStage === 'PANIC' 
                ? 'bg-emerald-500/10 border-emerald-500/50 shadow-lg shadow-emerald-500/10' 
                : 'bg-black/40 border-white/5 opacity-60 hover:opacity-90'
            }`}
          >
            <div className="flex justify-between text-xs font-mono text-slate-300">
              <span className="font-bold">05. 退潮恐慌</span>
              <span className="text-emerald-400">0% 空仓关闸</span>
            </div>
            <div className="text-[11px] text-slate-400 mt-1.5">准入: 全策略强制熔断防护</div>
            <div className={`mt-2 h-1 rounded-full ${activeStage === 'PANIC' ? 'bg-emerald-400' : 'bg-white/10'}`} />
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 核心三栏 Bento 矩阵 (左: 因子工坊 | 中: 候选股票池 | 右: 回测与模拟看板) */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-12 gap-6">

        {/* ----------------------------------------------------------------------- */}
        {/* 左栏 (4 列)：策略因子装配工坊 (黄金默认参数 + 滑块调节) */}
        {/* ----------------------------------------------------------------------- */}
        <div className="col-span-12 lg:col-span-4 space-y-4">
          <div className="glass-card rounded-2xl p-5 space-y-4 bg-white/[0.02] border border-white/10">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <Sliders className="w-4 h-4 text-purple-400" />
                策略因子装配工坊
              </h3>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">
                默认黄金参数
              </span>
            </div>

            {/* 规则积木 1: 市场环境门禁 */}
            <div className="bg-black/40 p-3.5 rounded-xl border border-white/5 space-y-2">
              <div className="text-xs font-bold text-slate-200 flex items-center justify-between">
                <span>01. 市场环境门禁</span>
                <span className="text-[10px] text-emerald-400 font-mono flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> 校验通过
                </span>
              </div>
              <div className="space-y-1.5 text-xs text-slate-400">
                <label className="flex items-center gap-2 cursor-pointer hover:text-slate-200">
                  <input type="checkbox" defaultChecked className="rounded border-slate-700 text-rose-500 focus:ring-0" />
                  <span>全市场上涨家数 &gt; 1800 家</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer hover:text-slate-200">
                  <input type="checkbox" defaultChecked className="rounded border-slate-700 text-rose-500 focus:ring-0" />
                  <span>两市预估成交额放量 &gt; 15%</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer hover:text-slate-200">
                  <input type="checkbox" defaultChecked className="rounded border-slate-700 text-rose-500 focus:ring-0" />
                  <span>非退潮恐慌期 (严格禁止熔断)</span>
                </label>
              </div>
            </div>

            {/* 规则积木 2: 盘口与微观选股因子 */}
            <div className="bg-black/40 p-3.5 rounded-xl border border-white/5 space-y-3">
              <div className="text-xs font-bold text-slate-200 flex items-center justify-between">
                <span>02. 盘口与微观选股因子</span>
                <span className="text-[10px] text-purple-400 font-mono">微观结构阈值</span>
              </div>

              {/* 竞价量比滑块 */}
              <div className="space-y-1">
                <div className="flex justify-between text-xs text-slate-400">
                  <span>集合竞价量比阈值</span>
                  <span className="text-rose-400 font-mono font-bold tabular-nums">&gt; {volumeRatio}.0 倍</span>
                </div>
                <input 
                  type="range" 
                  min="5" 
                  max="30" 
                  value={volumeRatio}
                  onChange={(e) => setVolumeRatio(Number(e.target.value))}
                  className="w-full h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-rose-500" 
                />
                <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                  <span>5x (宽松)</span>
                  <span className="text-amber-400">推荐: 12x</span>
                  <span>30x (严苛)</span>
                </div>
              </div>

              {/* 竞价开盘涨幅 */}
              <div className="space-y-1 pt-1">
                <div className="flex justify-between text-xs text-slate-400">
                  <span>竞价开盘涨幅区间</span>
                  <span className="text-rose-400 font-mono font-bold tabular-nums">+{openPct}% ~ +5.5%</span>
                </div>
                <input 
                  type="range" 
                  min="1" 
                  max="6" 
                  step="0.5"
                  value={openPct}
                  onChange={(e) => setOpenPct(Number(e.target.value))}
                  className="w-full h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-purple-500" 
                />
              </div>

              {/* 流通市值区间 */}
              <div className="text-xs text-slate-400 pt-1 flex justify-between items-center">
                <span>流通市值锁定:</span>
                <span className="font-mono text-slate-200 font-medium">30 亿 ~ 120 亿 (最佳弹性)</span>
              </div>
            </div>

            {/* 规则积木 3: 刚性出局与止损纪律 */}
            <div className="bg-amber-500/5 p-3.5 rounded-xl border border-amber-500/25 space-y-2">
              <div className="text-xs font-bold text-amber-300 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <ShieldAlert className="w-3.5 h-3.5" />
                  03. 止损与次日出局纪律
                </span>
                <span className="text-[10px] text-amber-400 font-mono">波普尔刚性执行</span>
              </div>
              <div className="space-y-1 text-xs text-slate-300 leading-relaxed font-mono">
                <div>• 日内买入破分时均线 2% 坚决减半仓</div>
                <div>• 炸板未在 3 分钟内回封立即核按钮离场</div>
                <div>• 次日 09:25 若低开超过 -2% 竞价抢跑止损</div>
              </div>
            </div>

            {/* 快捷回测执行按钮 */}
            <button 
              onClick={handleRunBacktest}
              disabled={isBacktesting}
              className="w-full py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:bg-purple-800 text-white text-xs font-bold shadow-lg shadow-purple-600/25 transition flex items-center justify-center gap-2"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>{isBacktesting ? '正在执行样本外回测...' : '执行快速回测验证 (2023-2026)'}</span>
            </button>
            {backtestNotice && (
              <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-mono leading-relaxed">
                {backtestNotice}
              </div>
            )}
          </div>
        </div>

        {/* ----------------------------------------------------------------------- */}
        {/* 中栏 (4 列)：全市场策略触发股票池与微观生态位 */}
        {/* ----------------------------------------------------------------------- */}
        <div className="col-span-12 lg:col-span-4 space-y-4">
          <div className="glass-card rounded-2xl p-5 space-y-4 bg-white/[0.02] border border-white/10">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <Layers className="w-4 h-4 text-cyan-400" />
                  策略触发股票池 (3 只标的)
                </h3>
                <span className="px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 text-[10px] font-mono font-bold">
                  今日实时
                </span>
              </div>
              <span className="text-xs text-slate-400 font-mono">按综合评分排序</span>
            </div>

            {/* 标的卡片 1：百洋股份 002696 (选中高亮) */}
            <div 
              onClick={() => setSelectedStock('002696')}
              className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-2 ${
                selectedStock === '002696'
                  ? 'bg-rose-500/10 border-rose-500/50 shadow-md ring-1 ring-rose-500/30'
                  : 'bg-black/40 border-white/5 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white text-sm">百洋股份</span>
                  <span className="font-mono text-xs text-slate-400">002696</span>
                  <span className="px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 text-[10px] font-bold">先锋2连板</span>
                  <span className="text-[10px] text-slate-400">渔业/预制菜</span>
                </div>
                <div className="text-right">
                  <span className="font-mono font-bold text-rose-500 text-sm tabular-nums">6.82 (+10.00%)</span>
                </div>
              </div>
              
              <div className="text-[11px] text-slate-300 flex items-center justify-between font-mono bg-black/40 p-2 rounded-lg">
                <span>因子综合分: <b className="text-rose-400 font-bold">94.5</b></span>
                <span>竞价量比: 18.6x</span>
                <span>秒板: 15秒</span>
              </div>

              <div className="text-[11px] text-slate-400 pt-1 border-t border-white/5 flex items-center justify-between">
                <span className="text-emerald-400 font-mono">● 模拟盘已于 6.35 自动挂单成交</span>
                <span className="text-slate-500 text-[10px]">持仓 20万 (1/5仓)</span>
              </div>
            </div>

            {/* 标的卡片 2：慈文传媒 002343 */}
            <div 
              onClick={() => setSelectedStock('002343')}
              className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-2 ${
                selectedStock === '002343'
                  ? 'bg-purple-500/10 border-purple-500/50 shadow-md ring-1 ring-purple-500/30'
                  : 'bg-black/40 border-white/5 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white text-sm">慈文传媒</span>
                  <span className="font-mono text-xs text-slate-400">002343</span>
                  <span className="px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300 text-[10px] font-bold">首板反包</span>
                  <span className="text-[10px] text-slate-400">影视短剧</span>
                </div>
                <div className="text-right">
                  <span className="font-mono font-bold text-rose-500 text-sm tabular-nums">7.15 (+9.98%)</span>
                </div>
              </div>

              <div className="text-[11px] text-slate-300 flex items-center justify-between font-mono bg-black/40 p-2 rounded-lg">
                <span>因子综合分: <b className="text-purple-400 font-bold">88.2</b></span>
                <span>竞价量比: 14.2x</span>
                <span>回踩均线买入</span>
              </div>

              <div className="text-[11px] text-slate-400 pt-1 border-t border-white/5 flex items-center justify-between">
                <span className="text-purple-400 font-mono">● 09:42 封板 · 模拟盘已跟进半仓</span>
                <span className="text-slate-500 text-[10px]">持仓 15万</span>
              </div>
            </div>

            {/* 标的卡片 3：新华传媒 600825 */}
            <div 
              onClick={() => setSelectedStock('600825')}
              className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-2 ${
                selectedStock === '600825'
                  ? 'bg-amber-500/10 border-amber-500/50 shadow-md ring-1 ring-amber-500/30'
                  : 'bg-black/40 border-white/5 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-bold text-white text-sm">新华传媒</span>
                  <span className="font-mono text-xs text-slate-400">600825</span>
                  <span className="px-1.5 py-0.2 rounded bg-white/10 text-slate-300 text-[10px]">梯队跟风</span>
                  <span className="text-[10px] text-slate-400">出版传媒</span>
                </div>
                <div className="text-right">
                  <span className="font-mono font-bold text-rose-400 text-sm tabular-nums">5.42 (+6.27%)</span>
                </div>
              </div>

              <div className="text-[11px] text-slate-400 flex items-center justify-between font-mono bg-black/40 p-2 rounded-lg">
                <span>因子综合分: <b className="text-slate-200">76.0</b></span>
                <span>跟风冲高</span>
                <span className="text-amber-400">冲高未板 (观察)</span>
              </div>

              <div className="text-[11px] text-slate-500 pt-1 border-t border-white/5">
                风控拦截提示: 龙头若炸板，此标的禁止追高
              </div>
            </div>
          </div>
        </div>

        {/* ----------------------------------------------------------------------- */}
        {/* 右栏 (4 列)：双轨绩效看板 (3年回测净值曲线 vs 模拟实战) */}
        {/* ----------------------------------------------------------------------- */}
        <div className="col-span-12 lg:col-span-4 space-y-4">
          <div className="glass-card rounded-2xl p-5 space-y-4 bg-white/[0.02] border border-white/10">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-emerald-400" />
                策略全生命周期绩效看板
              </h3>
              <span className="text-[10px] font-mono text-slate-400">
                3年样本外测试 (2023-2026)
              </span>
            </div>

            {/* 核心量化指标 6 宫格 */}
            <div className="grid grid-cols-3 gap-2 text-center font-mono">
              <div className="bg-black/40 p-2 rounded-xl border border-white/5">
                <div className="text-[10px] text-slate-400 font-sans">累计年化收益</div>
                <div className="text-base font-bold text-rose-400 tabular-nums">+46.8%</div>
              </div>
              <div className="bg-black/40 p-2 rounded-xl border border-white/5">
                <div className="text-[10px] text-slate-400 font-sans">最大历史回撤</div>
                <div className="text-base font-bold text-emerald-400 tabular-nums">-8.4%</div>
              </div>
              <div className="bg-black/40 p-2 rounded-xl border border-white/5">
                <div className="text-[10px] text-slate-400 font-sans">夏普比率 Sharpe</div>
                <div className="text-base font-bold text-white tabular-nums">2.62</div>
              </div>
              <div className="bg-black/40 p-2 rounded-xl border border-white/5">
                <div className="text-[10px] text-slate-400 font-sans">胜率 Win Rate</div>
                <div className="text-base font-bold text-rose-400 tabular-nums">67.3%</div>
              </div>
              <div className="bg-black/40 p-2 rounded-xl border border-white/5">
                <div className="text-[10px] text-slate-400 font-sans">盈亏比 P/L Ratio</div>
                <div className="text-base font-bold text-white tabular-nums">2.9:1</div>
              </div>
              <div className="bg-black/40 p-2 rounded-xl border border-white/5">
                <div className="text-[10px] text-slate-400 font-sans">平均持仓周期</div>
                <div className="text-base font-bold text-purple-400 tabular-nums">1.6 天</div>
              </div>
            </div>

            {/* SVG 高精度净值曲线图 (策略净值 vs 沪深300基准) */}
            <div className="bg-black/40 p-3 rounded-xl border border-white/5 space-y-2">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="flex items-center gap-1.5 text-rose-400 font-bold">
                  <span className="w-2.5 h-0.5 bg-rose-500 inline-block" />
                  策略净值 (1.00 ➔ 2.48)
                </span>
                <span className="flex items-center gap-1.5 text-slate-500">
                  <span className="w-2.5 h-0.5 bg-slate-600 inline-block" />
                  沪深300基准 (0.92)
                </span>
              </div>

              <div className="h-32 w-full pt-1">
                <svg className="w-full h-full" viewBox="0 0 300 100">
                  {/* 背景参考线 */}
                  <line x1="0" y1="20" x2="300" y2="20" stroke="rgba(255,255,255,0.05)" strokeDasharray="3,3" />
                  <line x1="0" y1="50" x2="300" y2="50" stroke="rgba(255,255,255,0.05)" strokeDasharray="3,3" />
                  <line x1="0" y1="80" x2="300" y2="80" stroke="rgba(255,255,255,0.05)" strokeDasharray="3,3" />

                  {/* 沪深 300 基准线 (灰绿震荡) */}
                  <path 
                    d="M0,70 Q40,65 80,75 T150,85 T220,80 T300,88" 
                    fill="none" 
                    stroke="#64748B" 
                    strokeWidth="1.5" 
                    strokeDasharray="4,2" 
                  />

                  {/* 策略净值主线 (红色稳健上扬) */}
                  <path 
                    d="M0,75 Q50,70 90,55 T160,40 T230,25 T300,10" 
                    fill="none" 
                    stroke="#EF4444" 
                    strokeWidth="2.5" 
                  />
                  {/* 红色溢出渐变光晕 */}
                  <path 
                    d="M0,75 Q50,70 90,55 T160,40 T230,25 T300,10 L300,100 L0,100 Z" 
                    fill="rgba(239, 68, 68, 0.08)" 
                  />
                </svg>
              </div>

              <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                <span>2024-01</span>
                <span>2024-12</span>
                <span>2025-06</span>
                <span>2026-10 (今日)</span>
              </div>
            </div>

            {/* 水下回撤面积图 (Underwater Drawdown) */}
            <div className="bg-black/40 p-2.5 rounded-xl border border-white/5 space-y-1">
              <div className="flex justify-between text-xs text-slate-400">
                <span>水下最大回撤剖面 (Underwater Depth)</span>
                <span className="text-emerald-400 font-mono text-[11px] font-bold">受控于 -8.4% 内</span>
              </div>
              <svg className="w-full h-8" viewBox="0 0 300 30">
                <path 
                  d="M0,0 Q30,5 60,2 T120,18 T180,6 T240,12 T300,3 L300,0 Z" 
                  fill="rgba(16, 185, 129, 0.25)" 
                  stroke="#10B981" 
                  strokeWidth="1" 
                />
              </svg>
            </div>

            {/* 模拟盘实时联动 */}
            <div className="p-3 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2">
                <Zap className="w-4 h-4 text-purple-400" />
                <span className="text-slate-200">模拟交易账户已自动联动 (100万初始金)</span>
              </div>
              <Link 
                href="/simulation"
                className="text-purple-300 hover:text-white flex items-center gap-0.5 font-mono text-[11px]"
              >
                查看台账 <ArrowUpRight className="w-3 h-3" />
              </Link>
            </div>

          </div>
        </div>

      </div>

    </div>
  );
}
