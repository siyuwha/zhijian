'use client';

import Link from 'next/link';
import { PlaySquare, Sparkles, ArrowRight, Activity, Cpu, RotateCcw } from 'lucide-react';

export default function SimulationPage() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[85vh] px-4 py-12 relative">
      {/* 极光流光背景辐射球 */}
      <div 
        aria-hidden="true" 
        className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-cyan-500/15 rounded-full blur-[140px] pointer-events-none -z-10" 
      />
      <div 
        aria-hidden="true" 
        className="absolute top-1/2 left-1/2 -translate-x-1/3 translate-y-12 w-80 h-80 bg-purple-600/10 rounded-full blur-[130px] pointer-events-none -z-10" 
      />

      {/* 高保真极光暗夜毛玻璃预告卡 */}
      <div className="glass-card max-w-lg w-full rounded-2xl p-8 md:p-10 text-center relative border border-white/10 shadow-2xl backdrop-blur-2xl">
        {/* 极光播放器图标容器 */}
        <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-cyan-950/60 to-slate-900/80 border border-cyan-500/30 flex items-center justify-center mx-auto mb-6 shadow-xl shadow-cyan-950/50 relative group">
          <div className="absolute inset-0 rounded-2xl bg-cyan-500/10 blur-md group-hover:bg-cyan-500/20 transition-colors" />
          <PlaySquare className="w-10 h-10 text-cyan-400 relative z-10 transition-transform duration-500 group-hover:scale-110" />
        </div>

        {/* 极光胶囊徽章 */}
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-medium bg-cyan-950/60 border border-cyan-500/30 text-cyan-300 mb-4 shadow-sm">
          <Sparkles className="w-3.5 h-3.5 text-purple-400 animate-pulse" />
          <span>Phase 3 · 沙盒模拟回测演练室</span>
        </div>

        {/* 极光渐变标题 */}
        <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight bg-gradient-to-r from-cyan-400 via-indigo-200 to-purple-400 bg-clip-text text-transparent mb-3">
          模拟回测 · Simulation Sandbox
        </h1>

        {/* 沙盒回测演练说明 */}
        <p className="text-sm text-slate-300/90 leading-relaxed mb-6">
          基于真实历史行情的高拟真沙盒回测演练引擎。支持毫秒级分时回放、滑点与交易摩擦损耗仿真，以及历史极端分歧下的 Popper 证伪压力测试。
        </p>

        {/* 核心特性预告胶囊清单 */}
        <div className="grid grid-cols-2 gap-2.5 text-left mb-8">
          <div className="p-2.5 rounded-lg bg-white/[0.03] border border-white/5 flex items-center gap-2 text-xs text-slate-300">
            <RotateCcw className="w-4 h-4 text-cyan-400 shrink-0" />
            <span>毫秒级分时回放</span>
          </div>
          <div className="p-2.5 rounded-lg bg-white/[0.03] border border-white/5 flex items-center gap-2 text-xs text-slate-300">
            <Cpu className="w-4 h-4 text-purple-400 shrink-0" />
            <span>交易滑点摩擦仿真</span>
          </div>
        </div>

        {/* 快捷引导按钮 */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link
            href="/cockpit"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-lg shadow-purple-900/30 transition-all hover:scale-[1.02] active:scale-[0.98]"
          >
            <span>进入全景驾驶舱</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            href="/trading"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800/80 hover:bg-slate-750 text-slate-300 hover:text-white text-xs font-medium border border-white/10 transition-all"
          >
            <span>查看交易台账</span>
          </Link>
        </div>
      </div>
    </div>
  );
}
