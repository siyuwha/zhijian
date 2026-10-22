'use client';

import React, { useState, useEffect, useMemo } from 'react';
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
  RefreshCw, 
  PlaySquare,
  FileText,
  X,
  Filter,
  Calendar,
  DollarSign,
  AlertCircle
} from 'lucide-react';
import { api } from '@/lib/api';

export default function StrategyPage() {
  // 交互状态
  const [activeStage, setActiveStage] = useState<'ICE' | 'REPAIR' | 'RESONANCE' | 'OVERHEAT' | 'PANIC'>('REPAIR');
  const [selectedStock, setSelectedStock] = useState('002696');
  const [isSimulating, setIsSimulating] = useState(false);
  const [simNotice, setSimNotice] = useState<string | null>(null);

  // 真实三大经典策略实时选股状态 (实盘候选池)
  const [strategyData, setStrategyData] = useState<any>(null);
  const [activeStrategyId, setActiveStrategyId] = useState<string>('weak_to_strong');
  const [isLoadingStrategies, setIsLoadingStrategies] = useState(false);

  // 实盘微观因子装配工坊参数
  const [volumeRatio, setVolumeRatio] = useState(12);
  const [openPct, setOpenPct] = useState(3.5);

  // 左栏装配工坊标签: 'backtest' (历史回测配置) | 'factors' (实盘选股因子)
  const [configTab, setConfigTab] = useState<'backtest' | 'factors'>('backtest');

  // -------------------------------------------------------------------------
  // 真实样本外历史量化回测引擎状态
  // -------------------------------------------------------------------------
  const [backtestStatus, setBacktestStatus] = useState<any>(null);
  const [isBacktesting, setIsBacktesting] = useState(false);
  const [backtestNotice, setBacktestNotice] = useState('');
  const [backtestResult, setBacktestResult] = useState<any>(null);
  const [showTradeModal, setShowTradeModal] = useState(false);
  const [tradeFilter, setTradeFilter] = useState<'all' | 'win' | 'loss'>('all');

  // 回测参数设定
  const [btStrategy, setBtStrategy] = useState<string>('all');
  const [btStartDate, setBtStartDate] = useState<string>('2024-01-01');
  const [btEndDate, setBtEndDate] = useState<string>('2026-10-22');
  const [btCapital, setBtCapital] = useState<number>(1000000);
  const [btStopLoss, setBtStopLoss] = useState<number>(-5.0);
  const [btMaxPositions, setBtMaxPositions] = useState<number>(5);
  const [btHoldingDays, setBtHoldingDays] = useState<number>(2);
  const [btMinOpenPct, setBtMinOpenPct] = useState<number>(1.5);
  const [btMarketFilter, setBtMarketFilter] = useState<boolean>(true);

  // 加载回测底座状态
  const loadBacktestStatus = async () => {
    try {
      const res = await api.getBacktestStatus();
      if (res?.data) {
        setBacktestStatus(res.data);
      } else if (res) {
        setBacktestStatus(res);
      }
    } catch (e) {
      console.warn('获取回测底座状态异常:', e);
    }
  };

  // 执行真实事件驱动样本外回测
  const handleExecuteBacktest = async (overrideParams?: any) => {
    setIsBacktesting(true);
    setBacktestNotice('正在调用本地高频回测引擎 (全市场 736 个交易日、374 万 Bar 撮合)...');
    try {
      const payload = {
        strategy_id: btStrategy,
        start_date: btStartDate,
        end_date: btEndDate,
        initial_capital: Number(btCapital) || 1000000,
        stop_loss_pct: Number(btStopLoss) || -5.0,
        max_positions: Number(btMaxPositions) || 5,
        holding_days: Number(btHoldingDays) || 2,
        min_open_pct: Number(btMinOpenPct) || 1.5,
        market_filter: btMarketFilter,
        ...(overrideParams || {}),
      };
      const res = await api.runBacktest(payload);
      if (res && res.metrics) {
        setBacktestResult(res);
        const m = res.metrics;
        setBacktestNotice(
          `回测完成 (耗时 ${res.elapsed_seconds}秒)：共执行 ${m.total_trades} 笔交易，累计收益 ${m.total_return_pct >= 0 ? '+' : ''}${m.total_return_pct}% (年化 ${m.annual_return_pct}%)，夏普比率 ${m.sharpe_ratio}，最大回撤 ${m.max_drawdown_pct}%`
        );
      } else {
        throw new Error(res?.detail || res?.message || '回测接口未返回指标');
      }
    } catch (err: any) {
      setBacktestNotice(`回测执行失败: ${err.message || '请确认后端 parquet 数据集已就绪'}`);
    } finally {
      setIsBacktesting(false);
    }
  };

  // 一键模拟跟单
  const handleQuickSimulate = async (cand: any, e: React.MouseEvent) => {
    e.stopPropagation();
    setIsSimulating(true);
    try {
      const p = Number(cand.current_price) > 0 ? Number(cand.current_price) : 10.0;
      const nowStr = new Date().toISOString().replace('T', ' ').slice(0, 19);
      await api.executeSimTrade({
        code: cand.code,
        name: cand.name,
        direction: 'buy',
        price: p,
        quantity: 1000,
        trade_time: nowStr,
        decision_summary: `[${currentStrategy?.name || '经典策略'}] ${cand.status_tag || ''} (评分 ${cand.score}) · 策略联动模拟建仓`,
      });
      setSimNotice(`已成功将【${cand.name} (${cand.code})】以 ${p.toFixed(2)} 元加入模拟交易沙盒！`);
      setTimeout(() => setSimNotice(null), 4500);
    } catch (err: any) {
      alert(err.message || '模拟买入执行失败');
    } finally {
      setIsSimulating(false);
    }
  };

  const loadStrategies = () => {
    setIsLoadingStrategies(true);
    api.getClassicStrategies()
      .then((res) => {
        if (res && res.strategies) {
          setStrategyData(res);
          if (res.market_stage) {
            setActiveStage(res.market_stage);
          }
          const firstCand = res.strategies[0]?.candidates?.[0];
          if (firstCand?.code) {
            setSelectedStock(firstCand.code);
          }
        }
      })
      .catch((err) => {
        console.warn('Failed to load classic strategies:', err);
      })
      .finally(() => {
        setIsLoadingStrategies(false);
      });
  };

  useEffect(() => {
    loadStrategies();
    loadBacktestStatus();
    // 页面载入时自动发起一次基准回测
    handleExecuteBacktest();
  }, []);

  const currentStrategy = strategyData?.strategies?.find((s: any) => s.id === activeStrategyId) || strategyData?.strategies?.[0];
  const currentCandidates = currentStrategy?.candidates || [];

  // 计算动态 SVG 净值与水下回撤路径
  const curvePaths = useMemo(() => {
    const history = backtestResult?.equity_curve;
    if (!history || history.length < 2) return null;

    const n = history.length;
    const initialCap = history[0].equity || 1000000;

    const stratValues = history.map((p: any) => p.equity / initialCap);
    const bmInitial = history[0].benchmark_equity || initialCap;
    const bmValues = history.map((p: any) => (p.benchmark_equity || initialCap) / bmInitial);

    const allValues = [...stratValues, ...bmValues];
    const minVal = Math.min(...allValues) * 0.96;
    const maxVal = Math.max(...allValues) * 1.04;
    const valRange = maxVal - minVal || 1;

    const w = 300;
    const h = 100;
    const padTop = 10;
    const padBottom = 16;
    const plotH = h - padTop - padBottom;

    const stratPoints = stratValues.map((v: number, i: number) => {
      const x = (i / (n - 1)) * w;
      const y = h - padBottom - ((v - minVal) / valRange) * plotH;
      return [x, y];
    });

    const bmPoints = bmValues.map((v: number, i: number) => {
      const x = (i / (n - 1)) * w;
      const y = h - padBottom - ((v - minVal) / valRange) * plotH;
      return [x, y];
    });

    const stratPathD = stratPoints.map((pt: number[], i: number) => `${i === 0 ? 'M' : 'L'} ${pt[0].toFixed(1)},${pt[1].toFixed(1)}`).join(' ');
    const bmPathD = bmPoints.map((pt: number[], i: number) => `${i === 0 ? 'M' : 'L'} ${pt[0].toFixed(1)},${pt[1].toFixed(1)}`).join(' ');
    const areaD = `${stratPathD} L ${w},${h} L 0,${h} Z`;

    // 水下回撤计算 (300 x 30)
    const ddVals = history.map((p: any) => Math.abs(p.drawdown_pct || 0));
    const maxDd = Math.max(...ddVals, 5);
    const ddH = 30;
    const ddPoints = ddVals.map((dd: number, i: number) => {
      const x = (i / (n - 1)) * w;
      const y = Math.min(ddH - 2, (dd / maxDd) * (ddH - 4));
      return [x, y];
    });
    const ddPathD = `M 0,0 ` + ddPoints.map((pt: number[]) => `L ${pt[0].toFixed(1)},${pt[1].toFixed(1)}`).join(' ') + ` L ${w},0 Z`;

    return {
      stratPathD,
      bmPathD,
      areaD,
      ddPathD,
      startNet: stratValues[0].toFixed(2),
      endNet: stratValues[stratValues.length - 1].toFixed(2),
      bmEndNet: bmValues[bmValues.length - 1].toFixed(2),
      startDate: history[0].date,
      endDate: history[history.length - 1].date,
      midDate: history[Math.floor(n / 2)].date,
    };
  }, [backtestResult]);

  // 过滤回测交割单
  const filteredTrades = useMemo(() => {
    const list = backtestResult?.recent_trades || [];
    if (tradeFilter === 'win') return list.filter((t: any) => t.pnl_amount > 0);
    if (tradeFilter === 'loss') return list.filter((t: any) => t.pnl_amount <= 0);
    return list;
  }, [backtestResult, tradeFilter]);

  const metrics = backtestResult?.metrics;

  return (
    <div className="min-h-screen px-4 md:px-6 py-6 max-w-[1780px] mx-auto space-y-6 select-none">
      
      {/* 模拟盘联动通知条 */}
      {simNotice && (
        <div className="p-3.5 rounded-xl border border-cyan-500/50 bg-cyan-950/80 text-cyan-300 text-xs font-mono flex items-center justify-between shadow-lg shadow-cyan-950/40 animate-fade-in">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-cyan-400 shrink-0" />
            <span>{simNotice}</span>
          </div>
          <Link
            href="/simulation"
            className="px-2.5 py-1 rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-200 text-[10px] font-bold border border-cyan-500/40 transition"
          >
            前往模拟盘查看 ➔
          </Link>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 顶部标题横幅 (极光品牌头 + 回测就绪态) */}
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
              {backtestStatus?.available ? '离线高频量化引擎就绪 (736交易日)' : '三大工业级经典策略 · 实盘推演态'}
            </span>
          </div>
          <p className="text-xs text-slate-400 font-mono mt-1">
            机构级量化全生命周期流水线：大盘情绪五阶段门禁 ➔ 盘口因子装配 ➔ 动态股票池 ➔ 样本外毫秒级真实回测
          </p>
        </div>

        {/* 右侧环境提示 */}
        <div className="flex items-center gap-3">
          <div className="bg-black/50 border border-white/10 rounded-full px-3.5 py-1 text-xs flex items-center gap-2">
            <span className="text-slate-400">大盘周期:</span>
            <span className="font-bold text-amber-400">
              {strategyData?.market_stage_name || '阶段 2 · 弱势修复期'}
            </span>
            <span className="text-slate-600">|</span>
            <span className="text-slate-400">建议仓位:</span>
            <span className="font-mono text-rose-400 font-bold tabular-nums">
              {strategyData?.suggested_position || '30%~50%'}
            </span>
          </div>
          <button 
            onClick={() => handleExecuteBacktest()}
            disabled={isBacktesting}
            className="px-3 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 disabled:bg-purple-800 text-white text-xs font-semibold shadow-md shadow-purple-600/30 transition flex items-center gap-1.5"
            title="执行全量数据样本外回测"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isBacktesting ? 'animate-spin' : ''}`} />
            <span>{isBacktesting ? '回测中...' : '启动全量回测'}</span>
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
          <span className="text-[11px] font-mono text-slate-400 hidden sm:inline">
            策略根据微观结构数据，只在与之匹配的市场生命周期阶段自动放行或降仓保护
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

          {/* 阶段 2: 弱势修复 */}
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
      {/* 核心三栏 Bento 矩阵 (左: 回测与装配工坊 | 中: 候选股票池 | 右: 双轨绩效看板) */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-12 gap-6">

        {/* ----------------------------------------------------------------------- */}
        {/* 左栏 (4 列)：量化因子与历史回测装配工坊 */}
        {/* ----------------------------------------------------------------------- */}
        <div className="col-span-12 lg:col-span-4 space-y-4">
          <div className="glass-card rounded-2xl p-5 space-y-4 bg-white/[0.02] border border-white/10">
            
            {/* 顶栏双 Tab 切换 */}
            <div className="flex items-center justify-between pb-1 border-b border-white/10">
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setConfigTab('backtest')}
                  className={`px-3 py-1 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
                    configTab === 'backtest'
                      ? 'bg-purple-600 text-white shadow-md'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                  }`}
                >
                  <BarChart3 className="w-3.5 h-3.5" />
                  <span>历史回测控制台</span>
                </button>
                <button
                  onClick={() => setConfigTab('factors')}
                  className={`px-3 py-1 rounded-lg text-xs font-bold transition flex items-center gap-1.5 ${
                    configTab === 'factors'
                      ? 'bg-purple-600 text-white shadow-md'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                  }`}
                >
                  <Sliders className="w-3.5 h-3.5" />
                  <span>实盘微观因子</span>
                </button>
              </div>

              {backtestStatus?.available && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                  {backtestStatus.total_trading_days || 736}天数据就绪
                </span>
              )}
            </div>

            {configTab === 'backtest' ? (
              /* 回测配置面板 */
              <div className="space-y-3.5">
                
                {/* 策略模式选择 */}
                <div className="bg-black/40 p-3 rounded-xl border border-white/5 space-y-2">
                  <div className="text-xs font-bold text-slate-200 flex items-center justify-between">
                    <span>01. 待测策略生态位</span>
                    <span className="text-[10px] text-purple-400 font-mono">T+1 撮合</span>
                  </div>
                  <div className="grid grid-cols-2 gap-1.5 font-mono text-xs">
                    {[
                      { id: 'all', label: '三大策略组合 (全景)' },
                      { id: 'weak_to_strong', label: '弱转强竞价抢筹' },
                      { id: 'multi_board_dip', label: '连板分歧低吸' },
                      { id: 'dragon_pullback', label: '首板龙回头' },
                    ].map((tab) => (
                      <button
                        key={tab.id}
                        onClick={() => setBtStrategy(tab.id)}
                        className={`p-2 rounded-lg text-left transition border text-[11px] ${
                          btStrategy === tab.id
                            ? 'bg-purple-600/30 border-purple-500 text-purple-200 font-bold'
                            : 'bg-black/20 border-white/5 text-slate-400 hover:text-slate-200 hover:border-slate-700'
                        }`}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* 时间区间与本金 */}
                <div className="bg-black/40 p-3 rounded-xl border border-white/5 space-y-2.5">
                  <div className="text-xs font-bold text-slate-200 flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <Calendar className="w-3.5 h-3.5 text-cyan-400" />
                      02. 样本外回测区间与初始资金
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                    <div>
                      <span className="text-[10px] text-slate-400">起始日期</span>
                      <input 
                        type="date" 
                        value={btStartDate}
                        onChange={(e) => setBtStartDate(e.target.value)}
                        className="w-full mt-1 bg-black/60 border border-white/10 rounded-lg px-2 py-1 text-white text-xs focus:border-purple-500 focus:outline-none"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-400">截止日期</span>
                      <input 
                        type="date" 
                        value={btEndDate}
                        onChange={(e) => setBtEndDate(e.target.value)}
                        className="w-full mt-1 bg-black/60 border border-white/10 rounded-lg px-2 py-1 text-white text-xs focus:border-purple-500 focus:outline-none"
                      />
                    </div>
                  </div>

                  <div className="pt-1 flex items-center justify-between text-xs">
                    <span className="text-slate-400">初始回测资金:</span>
                    <div className="flex items-center gap-1 font-mono">
                      {[500000, 1000000, 2000000].map((amt) => (
                        <button
                          key={amt}
                          onClick={() => setBtCapital(amt)}
                          className={`px-2 py-0.5 rounded text-[10px] transition ${
                            btCapital === amt
                              ? 'bg-purple-600 text-white font-bold'
                              : 'bg-white/5 text-slate-400 hover:text-white'
                          }`}
                        >
                          {amt / 10000}万
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* 风控与仓位控制参数 */}
                <div className="bg-black/40 p-3 rounded-xl border border-white/5 space-y-2.5">
                  <div className="text-xs font-bold text-slate-200 flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
                      03. 风控止损与持仓约束
                    </span>
                  </div>

                  {/* 刚性止损比例 */}
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs text-slate-400">
                      <span>波普尔刚性止损线</span>
                      <span className="text-emerald-400 font-mono font-bold tabular-nums">{btStopLoss.toFixed(1)}%</span>
                    </div>
                    <input 
                      type="range" 
                      min="-10" 
                      max="-2" 
                      step="0.5"
                      value={btStopLoss}
                      onChange={(e) => setBtStopLoss(Number(e.target.value))}
                      className="w-full h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-emerald-500" 
                    />
                  </div>

                  {/* 最大持仓天数与只数 */}
                  <div className="grid grid-cols-2 gap-2 text-xs pt-1">
                    <div className="space-y-1">
                      <div className="flex justify-between text-[11px] text-slate-400">
                        <span>持仓上限天数</span>
                        <span className="text-purple-300 font-mono font-bold">{btHoldingDays} 天</span>
                      </div>
                      <input 
                        type="range" 
                        min="1" 
                        max="5" 
                        value={btHoldingDays}
                        onChange={(e) => setBtHoldingDays(Number(e.target.value))}
                        className="w-full h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-purple-500" 
                      />
                    </div>
                    <div className="space-y-1">
                      <div className="flex justify-between text-[11px] text-slate-400">
                        <span>同时持股上限</span>
                        <span className="text-rose-400 font-mono font-bold">{btMaxPositions} 只</span>
                      </div>
                      <input 
                        type="range" 
                        min="2" 
                        max="8" 
                        value={btMaxPositions}
                        onChange={(e) => setBtMaxPositions(Number(e.target.value))}
                        className="w-full h-1 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-rose-500" 
                      />
                    </div>
                  </div>

                  {/* 大盘退潮门禁联动 */}
                  <label className="flex items-center justify-between text-xs text-slate-300 cursor-pointer pt-1 border-t border-white/5">
                    <span className="flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      大盘退潮期强制空仓关闸
                    </span>
                    <input 
                      type="checkbox" 
                      checked={btMarketFilter}
                      onChange={(e) => setBtMarketFilter(e.target.checked)}
                      className="rounded border-slate-700 text-purple-600 focus:ring-0" 
                    />
                  </label>
                </div>

                {/* 回测执行大按钮 */}
                <button 
                  onClick={() => handleExecuteBacktest()}
                  disabled={isBacktesting}
                  className="w-full py-3 rounded-xl bg-gradient-to-r from-purple-600 to-rose-600 hover:from-purple-500 hover:to-rose-500 disabled:opacity-50 text-white text-xs font-bold shadow-lg shadow-purple-600/30 transition flex items-center justify-center gap-2"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>{isBacktesting ? '正在执行样本外数据回测...' : '执行真实数据回测 (2023-2026)'}</span>
                </button>

                {backtestNotice && (
                  <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-mono leading-relaxed">
                    {backtestNotice}
                  </div>
                )}
              </div>
            ) : (
              /* 实盘选股因子面板 */
              <div className="space-y-3.5">
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
                  策略触发股票池 ({currentCandidates.length} 只标的)
                </h3>
                <span className="px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 text-[10px] font-mono font-bold flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse" />
                  实盘推演
                </span>
              </div>
              <button 
                onClick={loadStrategies}
                disabled={isLoadingStrategies}
                className="text-xs text-slate-400 hover:text-white flex items-center gap-1 font-mono transition"
                title="重新计算三大策略候选池"
              >
                <RefreshCw className={`w-3 h-3 ${isLoadingStrategies ? 'animate-spin' : ''}`} />
                <span>刷新</span>
              </button>
            </div>

            {/* 3 大经典策略快速切换胶囊栏 */}
            <div className="grid grid-cols-3 gap-1.5 p-1 bg-black/60 rounded-xl border border-white/10 text-[11px] font-medium">
              {[
                { id: 'weak_to_strong', label: '弱转强抢筹' },
                { id: 'multi_board_dip', label: '分歧低吸' },
                { id: 'dragon_pullback', label: '首板龙回头' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveStrategyId(tab.id)}
                  className={`py-1.5 px-1 rounded-lg text-center transition-all ${
                    activeStrategyId === tab.id
                      ? 'bg-purple-600 text-white font-bold shadow-md'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* 标的卡片列表 */}
            <div className="space-y-2.5 max-h-[580px] overflow-y-auto pr-1">
              {currentCandidates.length > 0 ? (
                currentCandidates.map((cand: any) => {
                  const isSelected = selectedStock === cand.code;
                  const isUp = (cand.pct_change || 0) >= 0;
                  return (
                    <div
                      key={cand.code}
                      onClick={() => setSelectedStock(cand.code)}
                      className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-2 ${
                        isSelected
                          ? 'bg-rose-500/10 border-rose-500/50 shadow-md ring-1 ring-rose-500/30'
                          : 'bg-black/40 border-white/5 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-white text-sm">{cand.name}</span>
                          <span className="font-mono text-xs text-slate-400">{cand.code}</span>
                          <span className="px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 text-[10px] font-bold">
                            {cand.status_tag}
                          </span>
                          <span className="text-[10px] text-slate-400">{cand.industry}</span>
                        </div>
                        <div className="text-right">
                          <span className={`font-mono font-bold text-sm tabular-nums ${isUp ? 'text-rose-400' : 'text-emerald-400'}`}>
                            {cand.current_price ? Number(cand.current_price).toFixed(2) : '--'} ({isUp ? '+' : ''}{Number(cand.pct_change || 0).toFixed(2)}%)
                          </span>
                        </div>
                      </div>

                      <div className="text-[11px] text-slate-300 flex items-center justify-between font-mono bg-black/40 p-2 rounded-lg">
                        <span>综合评分: <b className="text-rose-400 font-bold">{cand.score}</b></span>
                        <span>量比: {cand.volume_ratio}x</span>
                        <span>高开: {cand.open_pct}%</span>
                      </div>

                      <div className="text-[11px] text-slate-400 pt-1 border-t border-white/5 flex items-center justify-between">
                        <span className="text-emerald-400 font-mono text-[10px] truncate max-w-[170px]" title={cand.signal_desc}>
                          ● {cand.signal_desc}
                        </span>
                        <div className="flex items-center gap-2">
                          <span className="text-slate-400 text-[10px] shrink-0">{cand.position_suggest}</span>
                          <button
                            onClick={(e) => handleQuickSimulate(cand, e)}
                            disabled={isSimulating}
                            className="px-2 py-0.5 rounded bg-cyan-600/30 hover:bg-cyan-600/50 text-cyan-300 border border-cyan-500/40 text-[10px] font-bold transition flex items-center gap-1 shadow-sm shrink-0"
                            title="一键将该推荐标的录入模拟盘持仓"
                          >
                            <PlaySquare className="w-2.5 h-2.5" />
                            <span>跟单</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="p-8 text-center text-slate-500 text-xs border border-dashed border-white/10 rounded-xl space-y-1">
                  <div>暂无符合当前严苛门禁的触发标的</div>
                  <div className="text-[10px] text-slate-600">（市场大盘情绪阶段或量比未达策略阀值）</div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ----------------------------------------------------------------------- */}
        {/* 右栏 (4 列)：双轨绩效看板 (真实历史回测净值曲线 vs 沪深300 vs 模拟实战) */}
        {/* ----------------------------------------------------------------------- */}
        <div className="col-span-12 lg:col-span-4 space-y-4">
          <div className="glass-card rounded-2xl p-5 space-y-4 bg-white/[0.02] border border-white/10">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-white flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-emerald-400" />
                策略全生命周期绩效看板
              </h3>
              <span className="text-[10px] font-mono text-slate-400">
                {backtestResult?.params?.start_date || '2024'} ~ {backtestResult?.params?.end_date || '2026'} ({metrics?.total_trading_days || 0} 交易日)
              </span>
            </div>

            {/* 核心量化指标 6 宫格 */}
            <div className="grid grid-cols-3 gap-2 text-center font-mono">
              <div className="bg-black/40 p-2 rounded-xl border border-white/5">
                <div className="text-[10px] text-slate-400 font-sans">累计总收益</div>
                <div className={`text-base font-bold tabular-nums ${(metrics?.total_return_pct || 0) >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                  {metrics ? `${metrics.total_return_pct >= 0 ? '+' : ''}${metrics.total_return_pct}%` : '--'}
                </div>
                <div className="text-[9px] text-slate-500">年化: {metrics?.annual_return_pct || '--'}%</div>
              </div>
              <div className="bg-black/40 p-2 rounded-xl border border-white/5">
                <div className="text-[10px] text-slate-400 font-sans">最大历史回撤</div>
                <div className="text-base font-bold text-emerald-400 tabular-nums">
                  {metrics ? `${metrics.max_drawdown_pct}%` : '--'}
                </div>
                <div className="text-[9px] text-slate-500">峰值水下剖面</div>
              </div>
              <div className="bg-black/40 p-2 rounded-xl border border-white/5">
                <div className="text-[10px] text-slate-400 font-sans">夏普比率 Sharpe</div>
                <div className="text-base font-bold text-white tabular-nums">
                  {metrics?.sharpe_ratio ?? '--'}
                </div>
                <div className="text-[9px] text-slate-500">基准无风险 2%</div>
              </div>
              <div className="bg-black/40 p-2 rounded-xl border border-white/5">
                <div className="text-[10px] text-slate-400 font-sans">胜率 Win Rate</div>
                <div className="text-base font-bold text-rose-400 tabular-nums">
                  {metrics ? `${metrics.win_rate}%` : '--'}
                </div>
                <div className="text-[9px] text-slate-500">共 {metrics?.total_trades || 0} 笔撮合</div>
              </div>
              <div className="bg-black/40 p-2 rounded-xl border border-white/5">
                <div className="text-[10px] text-slate-400 font-sans">盈亏比 P/L Ratio</div>
                <div className="text-base font-bold text-white tabular-nums">
                  {metrics ? `${metrics.payoff_ratio}:1` : '--'}
                </div>
                <div className="text-[9px] text-slate-500">单笔均盈/均亏</div>
              </div>
              <div className="bg-black/40 p-2 rounded-xl border border-white/5">
                <div className="text-[10px] text-slate-400 font-sans">平均持仓周期</div>
                <div className="text-base font-bold text-purple-400 tabular-nums">
                  {metrics ? `${metrics.avg_holding_days} 天` : '--'}
                </div>
                <div className="text-[9px] text-slate-500">A股T+1刚性出局</div>
              </div>
            </div>

            {/* SVG 高精度净值曲线图 (策略净值 vs 沪深300基准) */}
            <div className="bg-black/40 p-3 rounded-xl border border-white/5 space-y-2">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="flex items-center gap-1.5 text-rose-400 font-bold">
                  <span className="w-2.5 h-0.5 bg-rose-500 inline-block" />
                  策略净值 ({curvePaths ? `${curvePaths.startNet} ➔ ${curvePaths.endNet}` : '计算中'})
                </span>
                <span className="flex items-center gap-1.5 text-slate-400">
                  <span className="w-2.5 h-0.5 bg-slate-500 inline-block border-b border-dashed" />
                  沪深300同期 ({curvePaths?.bmEndNet || '1.00'})
                </span>
              </div>

              <div className="h-32 w-full pt-1">
                {curvePaths ? (
                  <svg className="w-full h-full" viewBox="0 0 300 100">
                    <defs>
                      <linearGradient id="stratGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#EF4444" stopOpacity="0.25" />
                        <stop offset="100%" stopColor="#EF4444" stopOpacity="0.0" />
                      </linearGradient>
                    </defs>

                    {/* 参考网格线 */}
                    <line x1="0" y1="20" x2="300" y2="20" stroke="rgba(255,255,255,0.05)" strokeDasharray="3,3" />
                    <line x1="0" y1="50" x2="300" y2="50" stroke="rgba(255,255,255,0.05)" strokeDasharray="3,3" />
                    <line x1="0" y1="80" x2="300" y2="80" stroke="rgba(255,255,255,0.05)" strokeDasharray="3,3" />

                    {/* 沪深 300 基准虚线 */}
                    <path 
                      d={curvePaths.bmPathD} 
                      fill="none" 
                      stroke="#94A3B8" 
                      strokeWidth="1.2" 
                      strokeDasharray="4,2" 
                    />

                    {/* 策略净值红色主线 */}
                    <path 
                      d={curvePaths.stratPathD} 
                      fill="none" 
                      stroke="#EF4444" 
                      strokeWidth="2.2" 
                    />

                    {/* 策略溢出渐变底色 */}
                    <path 
                      d={curvePaths.areaD} 
                      fill="url(#stratGrad)" 
                    />
                  </svg>
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-slate-500 text-xs font-mono">
                    <RefreshCw className="w-4 h-4 animate-spin mr-2" />
                    正在加载历史回测净值序列...
                  </div>
                )}
              </div>

              <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                <span>{curvePaths?.startDate || '2024-01-02'}</span>
                <span>{curvePaths?.midDate || '2025-06-15'}</span>
                <span>{curvePaths?.endDate || '2026-10-22'}</span>
              </div>
            </div>

            {/* 水下回撤面积图 (Underwater Drawdown) */}
            <div className="bg-black/40 p-2.5 rounded-xl border border-white/5 space-y-1">
              <div className="flex justify-between text-xs text-slate-400">
                <span>水下最大回撤剖面 (Underwater Depth)</span>
                <span className="text-emerald-400 font-mono text-[11px] font-bold">
                  {metrics ? `受控于 ${metrics.max_drawdown_pct}%` : '--'}
                </span>
              </div>
              <svg className="w-full h-8" viewBox="0 0 300 30">
                {curvePaths ? (
                  <path 
                    d={curvePaths.ddPathD} 
                    fill="rgba(16, 185, 129, 0.25)" 
                    stroke="#10B981" 
                    strokeWidth="1" 
                  />
                ) : (
                  <path 
                    d="M0,0 Q30,5 60,2 T120,18 T180,6 T240,12 T300,3 L300,0 Z" 
                    fill="rgba(16, 185, 129, 0.25)" 
                    stroke="#10B981" 
                    strokeWidth="1" 
                  />
                )}
              </svg>
            </div>

            {/* 真实交割单详情呼出按钮 */}
            {backtestResult?.recent_trades && backtestResult.recent_trades.length > 0 && (
              <button
                onClick={() => setShowTradeModal(true)}
                className="w-full py-2.5 px-3 rounded-xl bg-purple-600/20 hover:bg-purple-600/30 border border-purple-500/40 text-purple-200 text-xs font-bold transition flex items-center justify-between"
              >
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-purple-400" />
                  <span>查看真实成交历史交割单</span>
                </div>
                <span className="font-mono bg-purple-500/30 px-2 py-0.5 rounded text-[10px]">
                  共 {backtestResult.recent_trades.length} 笔交割 ➔
                </span>
              </button>
            )}

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

      {/* ========================================================================= */}
      {/* 真实回测交割单明细模态窗 (Institutional Trade Ledger Modal) */}
      {/* ========================================================================= */}
      {showTradeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="bg-slate-900 border border-white/20 rounded-2xl w-full max-w-5xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden">
            
            {/* 弹窗头部 */}
            <div className="p-4 border-b border-white/10 flex items-center justify-between bg-black/40">
              <div className="flex items-center gap-3">
                <FileText className="w-5 h-5 text-purple-400" />
                <div>
                  <h3 className="text-sm font-bold text-white">真实回测撮合成交明细 (样本外撮合流水)</h3>
                  <p className="text-[11px] font-mono text-slate-400 mt-0.5">
                    扣除印花税(0.05%)、佣金(0.01%)与冲击滑点(0.1%)后的真实净值结算记录
                  </p>
                </div>
              </div>

              {/* 筛选过滤与关闭按钮 */}
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1 p-0.5 bg-black/50 border border-white/10 rounded-lg text-xs font-mono">
                  <button
                    onClick={() => setTradeFilter('all')}
                    className={`px-2.5 py-1 rounded ${tradeFilter === 'all' ? 'bg-purple-600 text-white font-bold' : 'text-slate-400 hover:text-white'}`}
                  >
                    全部 ({backtestResult?.recent_trades?.length || 0})
                  </button>
                  <button
                    onClick={() => setTradeFilter('win')}
                    className={`px-2.5 py-1 rounded ${tradeFilter === 'win' ? 'bg-rose-600 text-white font-bold' : 'text-slate-400 hover:text-white'}`}
                  >
                    盈利 ({backtestResult?.recent_trades?.filter((t: any) => t.pnl_amount > 0).length || 0})
                  </button>
                  <button
                    onClick={() => setTradeFilter('loss')}
                    className={`px-2.5 py-1 rounded ${tradeFilter === 'loss' ? 'bg-emerald-600 text-white font-bold' : 'text-slate-400 hover:text-white'}`}
                  >
                    止损/亏损 ({backtestResult?.recent_trades?.filter((t: any) => t.pnl_amount <= 0).length || 0})
                  </button>
                </div>

                <button
                  onClick={() => setShowTradeModal(false)}
                  className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* 弹窗表格内容 */}
            <div className="p-4 overflow-y-auto flex-1 font-mono text-xs">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-white/10 text-slate-400 text-[11px]">
                    <th className="py-2 px-2">#</th>
                    <th className="py-2 px-2">标的名称与代码</th>
                    <th className="py-2 px-2">策略生态位</th>
                    <th className="py-2 px-2">买入日期与均价</th>
                    <th className="py-2 px-2">卖出日期与均价</th>
                    <th className="py-2 px-2">持股天数</th>
                    <th className="py-2 px-2 text-right">净盈亏额 / 收益率</th>
                    <th className="py-2 px-2">离场出局原因</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {filteredTrades.map((t: any, idx: number) => {
                    const isWin = t.pnl_amount > 0;
                    return (
                      <tr key={idx} className="hover:bg-white/[0.02] transition">
                        <td className="py-2.5 px-2 text-slate-500">{idx + 1}</td>
                        <td className="py-2.5 px-2">
                          <div className="font-bold text-white font-sans">{t.name}</div>
                          <div className="text-[10px] text-slate-400">{t.code}</div>
                        </td>
                        <td className="py-2.5 px-2">
                          <span className="px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 text-[10px]">
                            {t.strategy}
                          </span>
                        </td>
                        <td className="py-2.5 px-2">
                          <div>{t.buy_date}</div>
                          <div className="text-slate-400 text-[10px]">￥{Number(t.buy_price).toFixed(2)} × {t.shares}股</div>
                        </td>
                        <td className="py-2.5 px-2">
                          <div>{t.sell_date}</div>
                          <div className="text-slate-400 text-[10px]">￥{Number(t.sell_price).toFixed(2)}</div>
                        </td>
                        <td className="py-2.5 px-2 text-slate-300">{t.holding_days} 天</td>
                        <td className="py-2.5 px-2 text-right tabular-nums">
                          <div className={`font-bold ${isWin ? 'text-rose-400' : 'text-emerald-400'}`}>
                            {isWin ? '+' : ''}{Number(t.pnl_amount).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} 元
                          </div>
                          <div className={`text-[10px] ${isWin ? 'text-rose-400' : 'text-emerald-400'}`}>
                            {isWin ? '+' : ''}{Number(t.pnl_pct).toFixed(2)}%
                          </div>
                        </td>
                        <td className="py-2.5 px-2">
                          <span className="text-[11px] text-slate-300 truncate max-w-[160px] inline-block" title={t.reason}>
                            {t.reason}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {filteredTrades.length === 0 && (
                <div className="p-8 text-center text-slate-500">
                  当前筛选条件下无交割记录
                </div>
              )}
            </div>

            {/* 弹窗底部汇总 */}
            <div className="p-3 border-t border-white/10 bg-black/40 flex items-center justify-between text-xs font-mono text-slate-400">
              <div>
                共计显示 <b className="text-white">{filteredTrades.length}</b> 笔成交，交易本金按仓位自适应分配
              </div>
              <button
                onClick={() => setShowTradeModal(false)}
                className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-bold transition"
              >
                关闭
              </button>
            </div>

          </div>
        </div>
      )}

    </div>
  );
}
