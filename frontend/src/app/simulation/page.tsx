'use client';

import React, { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { 
  PlaySquare, 
  Wallet, 
  TrendingUp, 
  ShieldCheck, 
  Clock, 
  CheckCircle2, 
  AlertTriangle,
  RotateCcw,
  Zap,
  Sliders,
  RefreshCw,
  Plus,
  ArrowRight,
  TrendingDown,
  X,
  Target
} from 'lucide-react';
import { api } from '@/lib/api';
import { SimPosition, SimTrade, SimStats } from '@/types/simulation';
import { DirectionType } from '@/types/trading';

export default function SimulationPage() {
  const [activeTab, setActiveTab] = useState<'positions' | 'orders' | 'strategy_linkage' | 'risk'>('positions');
  const [positions, setPositions] = useState<SimPosition[]>([]);
  const [records, setRecords] = useState<SimTrade[]>([]);
  const [stats, setStats] = useState<SimStats | null>(null);
  const [strategyData, setStrategyData] = useState<any>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [actionNotice, setActionNotice] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  // 模拟下单弹窗状态
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [orderCode, setOrderCode] = useState('');
  const [orderName, setOrderName] = useState('');
  const [orderDirection, setOrderDirection] = useState<DirectionType>('buy');
  const [orderPrice, setOrderPrice] = useState<number>(10.0);
  const [orderQuantity, setOrderQuantity] = useState<number>(1000);
  const [orderReason, setOrderReason] = useState('策略信号手动模拟跟单');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 综合加载核心数据
  const loadAllData = useCallback(async (quiet: boolean = false) => {
    if (!quiet) setIsLoading(true);
    else setIsRefreshing(true);

    try {
      const [posRes, recRes, statsRes, stratRes] = await Promise.allSettled([
        api.getSimPositions(true),
        api.getSimRecords(40),
        api.getSimStats(),
        api.getClassicStrategies(),
      ]);

      if (posRes.status === 'fulfilled' && Array.isArray(posRes.value)) {
        setPositions(posRes.value);
      }
      if (recRes.status === 'fulfilled' && recRes.value?.items) {
        setRecords(recRes.value.items);
      }
      if (statsRes.status === 'fulfilled' && statsRes.value) {
        setStats(statsRes.value);
      }
      if (stratRes.status === 'fulfilled' && stratRes.value) {
        setStrategyData(stratRes.value);
      }
    } catch (err) {
      console.warn('Simulation data load error:', err);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadAllData();
  }, [loadAllData]);

  // 显示提示横幅
  const showNotice = (text: string, type: 'success' | 'error' = 'success') => {
    setActionNotice({ text, type });
    setTimeout(() => {
      setActionNotice(null);
    }, 4500);
  };

  // 策略候选标的一键模拟买入 (跟单建仓)
  const handleQuickStrategyBuy = async (cand: any, stratName: string) => {
    setIsSubmitting(true);
    try {
      const p = Number(cand.current_price) > 0 ? Number(cand.current_price) : 10.0;
      const q = 1000;
      const nowStr = new Date().toISOString().replace('T', ' ').slice(0, 19);

      await api.executeSimTrade({
        code: cand.code,
        name: cand.name,
        direction: 'buy',
        price: p,
        quantity: q,
        trade_time: nowStr,
        decision_summary: `[${stratName}] ${cand.status_tag || ''} (评分 ${cand.score || '--'}) · 策略联动模拟建仓`,
      });

      showNotice(`已成功模拟买入【${cand.name} (${cand.code})】1,000 股，买入价 ${p.toFixed(2)} 元！`, 'success');
      await loadAllData(true);
    } catch (err: any) {
      showNotice(err.message || '模拟买入执行失败', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  // 持仓一键平仓卖出
  const handleSellPosition = async (pos: SimPosition) => {
    if (!confirm(`确认按市价模拟平仓卖出【${pos.name || pos.code}】全部 ${pos.quantity} 股吗？`)) {
      return;
    }
    setIsSubmitting(true);
    try {
      const p = Number(pos.current_price) > 0 ? Number(pos.current_price) : Number(pos.avg_cost);
      const nowStr = new Date().toISOString().replace('T', ' ').slice(0, 19);

      await api.executeSimTrade({
        code: pos.code,
        name: pos.name || undefined,
        direction: 'sell',
        price: p,
        quantity: pos.quantity,
        trade_time: nowStr,
        decision_summary: `模拟盘手动止盈止损平仓 (原成本 ${pos.avg_cost.toFixed(2)})`,
      });

      showNotice(`已成功平仓【${pos.name || pos.code}】${pos.quantity} 股，成交价 ${p.toFixed(2)} 元！`, 'success');
      await loadAllData(true);
    } catch (err: any) {
      showNotice(err.message || '平仓执行失败', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  // 手动模拟报单提交
  const handleManualOrderSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!orderCode || !orderPrice || !orderQuantity) {
      showNotice('请填写完整的股票代码、成交价格和数量', 'error');
      return;
    }

    setIsSubmitting(true);
    try {
      const nowStr = new Date().toISOString().replace('T', ' ').slice(0, 19);
      await api.executeSimTrade({
        code: orderCode.trim(),
        name: orderName.trim() || undefined,
        direction: orderDirection,
        price: Number(orderPrice),
        quantity: Number(orderQuantity),
        trade_time: nowStr,
        decision_summary: orderReason,
      });

      showNotice(`已成功记录【${orderDirection === 'buy' ? '买入' : '卖出'}】${orderCode} ${orderQuantity} 股！`, 'success');
      setIsModalOpen(false);
      setOrderCode('');
      setOrderName('');
      await loadAllData(true);
    } catch (err: any) {
      showNotice(err.message || '报单失败', 'error');
    } finally {
      setIsSubmitting(false);
    }
  };

  // 资产指标运算 (初始虚拟金 1,000,000 元)
  const initialCapital = 1000000.0;
  const totalMarketValue = positions.reduce((acc, p) => acc + (p.market_value || (p.current_price || p.avg_cost) * p.quantity), 0);
  const totalCost = positions.reduce((acc, p) => acc + p.total_cost, 0);
  const totalFloatingPnl = positions.reduce((acc, p) => acc + (p.floating_pnl || 0), 0);
  const totalRealizedPnl = stats?.total_realized_pnl || 0;
  const availableCash = Math.max(0, initialCapital - totalCost + totalRealizedPnl);
  const totalAssets = availableCash + totalMarketValue;
  const totalPnlRatio = Number((((totalAssets - initialCapital) / initialCapital) * 100).toFixed(2));
  const positionRatio = totalAssets > 0 ? Number(((totalMarketValue / totalAssets) * 100).toFixed(1)) : 0;

  // 策略推演候选总列表
  const allStrategyCandidates: Array<{ cand: any; strategyName: string }> = [];
  if (strategyData?.strategies && Array.isArray(strategyData.strategies)) {
    strategyData.strategies.forEach((s: any) => {
      if (s.candidates && Array.isArray(s.candidates)) {
        s.candidates.forEach((c: any) => {
          allStrategyCandidates.push({ cand: c, strategyName: s.name });
        });
      }
    });
  }

  return (
    <div className="min-h-screen px-4 md:px-6 py-6 max-w-[1780px] mx-auto space-y-6 select-none">
      
      {/* 顶部通知条 */}
      {actionNotice && (
        <div className={`p-3.5 rounded-xl border text-sm font-mono flex items-center justify-between transition-all animate-fade-in ${
          actionNotice.type === 'success'
            ? 'bg-emerald-950/80 border-emerald-500/50 text-emerald-300'
            : 'bg-rose-950/80 border-rose-500/50 text-rose-300'
        }`}>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>{actionNotice.text}</span>
          </div>
          <button onClick={() => setActionNotice(null)} className="text-slate-400 hover:text-white">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* 顶部标题横幅 */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 pb-2 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl md:text-2xl font-black text-white tracking-wide flex items-center gap-2">
              <span className="w-8 h-8 rounded-lg bg-gradient-to-tr from-cyan-600 to-indigo-600 flex items-center justify-center text-white text-sm shadow-md">
                模
              </span>
              模拟交易沙盒 · 策略实时联动台账
            </h1>
            <span className="px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/35 text-sm font-mono font-bold flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              虚拟 PaperBroker · 严格 A 股 T+1
            </span>
          </div>
          <p className="text-sm text-slate-400 font-mono mt-1">
            三大经典策略全自动信号驱动 · 真实计算印花税 (0.05%)、佣金 (万一) 与 0.1% 冲击滑点
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => loadAllData(true)}
            disabled={isRefreshing}
            className="px-3.5 py-1.5 rounded-xl bg-white/10 hover:bg-white/15 border border-white/10 text-sm font-semibold text-slate-200 transition flex items-center gap-1.5"
            title="刷新持仓、流水与最新行情"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-cyan-400 ${isRefreshing ? 'animate-spin' : ''}`} />
            <span>刷新行情</span>
          </button>

          <button
            onClick={async () => {
              if (confirm("确认重置策略实盘模拟账户吗？所有模拟持仓与流水将被清空，虚拟资金恢复 100 万元。")) {
                try {
                  await api.resetSimAccount();
                  showNotice("策略实盘模拟账户已重置恢复 100 万元初始虚拟资金！", "success");
                  await loadAllData(true);
                } catch (err: any) {
                  showNotice(err?.message || "重置失败", "error");
                }
              }
            }}
            className="px-3.5 py-1.5 rounded-xl bg-rose-950/40 hover:bg-rose-900/40 border border-rose-800/40 text-sm font-semibold text-rose-300 transition flex items-center gap-1.5"
            title="一键清空模拟持仓与流水，恢复初始 100 万"
          >
            <RotateCcw className="w-3.5 h-3.5 text-rose-400" />
            <span className="hidden sm:inline">重置模拟盘</span>
          </button>

          <button
            onClick={() => setIsModalOpen(true)}
            className="px-3.5 py-1.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-sm font-bold text-white transition flex items-center gap-1.5 shadow-lg shadow-cyan-900/30"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>新建模拟交易</span>
          </button>

          <Link 
            href="/strategy"
            className="px-3.5 py-1.5 rounded-xl bg-purple-600/30 hover:bg-purple-600/40 border border-purple-500/40 text-sm font-semibold text-purple-200 transition flex items-center gap-1.5"
          >
            <Sliders className="w-3.5 h-3.5 text-purple-300" />
            <span>策略工作台</span>
          </Link>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 账户资产三足鼎立卡 (三宫格 Bento) */}
      {/* ========================================================================= */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 总资产卡 */}
        <div className="glass-card rounded-2xl p-5 bg-white/[0.02] border border-white/10 space-y-2">
          <div className="flex justify-between items-center text-sm text-slate-400">
            <span>虚拟账户总资产</span>
            <span className={`px-1.5 py-0.5 rounded font-mono text-xs font-bold ${
              totalPnlRatio >= 0 ? 'bg-rose-500/20 text-rose-300' : 'bg-emerald-500/20 text-emerald-300'
            }`}>
              {totalPnlRatio >= 0 ? `+${totalPnlRatio}%` : `${totalPnlRatio}%`}
            </span>
          </div>
          <div className="text-2xl font-black font-mono text-white tabular-nums">
            {totalAssets.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} <span className="text-xs font-normal text-slate-400">元</span>
          </div>
          <div className={`text-sm font-mono flex items-center gap-1 ${totalFloatingPnl >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
            {totalFloatingPnl >= 0 ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
            <span>当前浮动盈亏: {totalFloatingPnl >= 0 ? `+${totalFloatingPnl.toFixed(2)}` : totalFloatingPnl.toFixed(2)} 元</span>
          </div>
        </div>

        {/* 可用现金 */}
        <div className="glass-card rounded-2xl p-5 bg-white/[0.02] border border-white/10 space-y-2">
          <div className="flex justify-between items-center text-sm text-slate-400">
            <span>可用现金 (Cash)</span>
            <span className="text-slate-500 font-mono text-xs">初始金 100 万</span>
          </div>
          <div className="text-2xl font-black font-mono text-white tabular-nums">
            {availableCash.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} <span className="text-xs font-normal text-slate-400">元</span>
          </div>
          <div className="text-sm text-slate-400 font-mono">
            现金储备率: <span className="text-emerald-400 font-bold">{((availableCash / (totalAssets || 1)) * 100).toFixed(1)}%</span>
          </div>
        </div>

        {/* 当前持仓市值与仓位 */}
        <div className="glass-card rounded-2xl p-5 bg-white/[0.02] border border-white/10 space-y-2">
          <div className="flex justify-between items-center text-sm text-slate-400">
            <span>持仓总市值 ({positions.length} 只标的)</span>
            <span className="text-amber-400 font-mono text-xs">
              {strategyData?.market_stage_name || '大盘门禁'}
            </span>
          </div>
          <div className="text-2xl font-black font-mono text-white tabular-nums">
            {totalMarketValue.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} <span className="text-xs font-normal text-slate-400">元</span>
          </div>
          <div className="text-sm text-slate-400 font-mono">
            当前实战仓位: <span className="text-amber-400 font-bold">{positionRatio}%</span> (建议 {strategyData?.suggested_position || '30%~50%'})
          </div>
        </div>

        {/* 胜率与累计交易统计 */}
        <div className="glass-card rounded-2xl p-5 bg-white/[0.02] border border-white/10 space-y-2">
          <div className="flex justify-between items-center text-sm text-slate-400">
            <span>实战演练胜率统计</span>
            <span className="text-slate-500 font-mono text-xs">已平仓周期</span>
          </div>
          <div className="text-2xl font-black font-mono text-rose-400 tabular-nums">
            {stats?.closed_leg_win_rate != null ? `${stats.closed_leg_win_rate}%` : '--'}
            <span className="text-xs font-normal text-slate-400 ml-1.5">
              ({stats?.win_trades || 0}/{stats?.closed_trades || 0} 胜)
            </span>
          </div>
          <div className="text-sm text-slate-400 font-mono">
            盈亏比: <span className="text-white font-bold">{stats?.payoff_ratio != null ? `${stats.payoff_ratio} : 1` : '--'}</span> | 已实现: {totalRealizedPnl.toFixed(2)}元
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* 策略联动信号池快速模拟跟单横幅 (Strategy Linkage Quick Sniping) */}
      {/* ========================================================================= */}
      <div className="glass-card rounded-2xl p-4 bg-gradient-to-r from-purple-950/30 via-slate-900/40 to-cyan-950/30 border border-purple-500/25 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-cyan-400" />
            <h2 className="text-sm font-bold text-white tracking-wide">
              今日三大经典策略推演联动信号池 (可一键虚拟跟单)
            </h2>
            <span className="px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 text-xs font-mono font-bold">
              共 {allStrategyCandidates.length} 只推荐候选
            </span>
          </div>
          <Link
            href="/strategy"
            className="text-sm text-purple-300 hover:text-white flex items-center gap-1 font-mono transition"
          >
            <span>进入策略工作台细看逻辑</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {allStrategyCandidates.length === 0 ? (
          <div className="py-4 text-center text-sm text-slate-500 font-mono">
            当前交易日暂无符合门禁的策略触发候选，保持防守观望
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
            {allStrategyCandidates.slice(0, 5).map(({ cand, strategyName }) => {
              const isHolding = positions.some((p) => p.code === cand.code);
              const isUp = (cand.pct_change || 0) >= 0;

              return (
                <div
                  key={`${strategyName}-${cand.code}`}
                  className="rounded-xl border border-white/10 p-3 bg-slate-950/60 hover:bg-slate-900/80 transition flex flex-col justify-between gap-2.5"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="font-bold text-white text-sm flex items-center gap-1.5">
                        <span>{cand.name}</span>
                        <span className="font-mono text-xs text-slate-400">{cand.code}</span>
                      </div>
                      <div className="text-xs text-cyan-300 font-mono mt-0.5">
                        {strategyName} · {cand.status_tag || '触发候选'}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`font-mono font-bold text-sm ${isUp ? 'text-rose-400' : 'text-emerald-400'}`}>
                        {isUp ? '+' : ''}{Number(cand.pct_change || 0).toFixed(2)}%
                      </div>
                      <div className="text-xs font-mono text-slate-400">
                        评分 {cand.score}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-1 border-t border-white/5">
                    <span className="text-xs text-slate-400 font-mono">
                      现价: {Number(cand.current_price || 0) > 0 ? `¥${Number(cand.current_price).toFixed(2)}` : '--'}
                    </span>
                    {isHolding ? (
                      <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-xs font-bold border border-emerald-500/30">
                        已在持仓中
                      </span>
                    ) : (
                      <button
                        onClick={() => handleQuickStrategyBuy(cand, strategyName)}
                        disabled={isSubmitting}
                        className="px-2.5 py-1 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold transition flex items-center gap-1 shadow-sm"
                      >
                        <PlaySquare className="w-3 h-3" />
                        <span>模拟跟单</span>
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* 选项卡切换 (持仓明细 / 当日成交流水 / 策略候选联动 / 波普尔止损风控) */}
      {/* ========================================================================= */}
      <div className="glass-card rounded-2xl p-5 bg-white/[0.02] border border-white/10 space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-white/10">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab('positions')}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-bold transition flex items-center gap-1.5 ${
                activeTab === 'positions'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>当前模拟持仓 ({positions.length})</span>
            </button>
            <button
              onClick={() => setActiveTab('orders')}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-bold transition flex items-center gap-1.5 ${
                activeTab === 'orders'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>模拟交易成交流水 ({records.length})</span>
            </button>
            <button
              onClick={() => setActiveTab('strategy_linkage')}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-bold transition flex items-center gap-1.5 ${
                activeTab === 'strategy_linkage'
                  ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>三大策略候选全集 ({allStrategyCandidates.length})</span>
            </button>
            <button
              onClick={() => setActiveTab('risk')}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-bold transition flex items-center gap-1.5 ${
                activeTab === 'risk'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>波普尔证伪哨兵</span>
            </button>
          </div>
          <span className="text-sm font-mono text-slate-500">更新频率: 盘中每 3 秒实时拉取</span>
        </div>

        {/* 1. 当前持仓列表 */}
        {activeTab === 'positions' && (
          <div className="overflow-x-auto">
            {positions.length === 0 ? (
              <div className="py-12 text-center text-slate-500 space-y-2 font-mono">
                <Target className="w-8 h-8 text-slate-600 mx-auto" />
                <div className="text-base font-bold text-slate-300">当前暂无模拟持仓标的</div>
                <div className="text-sm text-slate-500">
                  可点击上方“今日策略联动信号池”一键跟单，或点击右上角“新建模拟交易”开仓
                </div>
              </div>
            ) : (
              <table className="w-full text-left text-sm font-mono border-collapse">
                <thead>
                  <tr className="border-b border-white/10 text-slate-400">
                    <th className="py-2.5 px-3">代码/名称</th>
                    <th className="py-2.5 px-3 text-right">持股数 / 可用</th>
                    <th className="py-2.5 px-3 text-right">买入均价</th>
                    <th className="py-2.5 px-3 text-right">最新现价</th>
                    <th className="py-2.5 px-3 text-right">持仓市值</th>
                    <th className="py-2.5 px-3 text-right">浮动盈亏</th>
                    <th className="py-2.5 px-3 text-center">T+1 状态</th>
                    <th className="py-2.5 px-3 text-center">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 text-slate-200">
                  {positions.map((pos) => {
                    const curPrice = pos.current_price != null ? pos.current_price : pos.avg_cost;
                    const mktCap = pos.market_value != null ? pos.market_value : curPrice * pos.quantity;
                    const pnl = pos.floating_pnl != null ? pos.floating_pnl : (curPrice - pos.avg_cost) * pos.quantity;
                    const pnlPct = pos.floating_pnl_pct != null ? pos.floating_pnl_pct : ((curPrice - pos.avg_cost) / pos.avg_cost) * 100;
                    const isUp = pnl >= 0;

                    return (
                      <tr key={pos.code} className="hover:bg-white/[0.02] transition">
                        <td className="py-3 px-3">
                          <div className="font-bold text-white text-sm font-sans">{pos.name || pos.code}</div>
                          <div className="text-xs text-slate-400 font-mono">{pos.code}</div>
                        </td>
                        <td className="py-3 px-3 text-right tabular-nums">
                          <div>{pos.quantity.toLocaleString()} 股</div>
                          <div className="text-xs text-amber-400">0 股可用 (T+1锁定)</div>
                        </td>
                        <td className="py-3 px-3 text-right tabular-nums text-slate-300">
                          {pos.avg_cost.toFixed(3)}
                        </td>
                        <td className={`py-3 px-3 text-right tabular-nums font-bold text-sm ${isUp ? 'text-rose-400' : 'text-emerald-400'}`}>
                          {curPrice.toFixed(3)}
                        </td>
                        <td className="py-3 px-3 text-right tabular-nums text-white font-bold">
                          {mktCap.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} 元
                        </td>
                        <td className={`py-3 px-3 text-right tabular-nums font-bold ${isUp ? 'text-rose-400' : 'text-emerald-400'}`}>
                          <div>{isUp ? `+${pnl.toFixed(2)}` : pnl.toFixed(2)} 元</div>
                          <div className="text-xs">{isUp ? `+${pnlPct.toFixed(2)}` : pnlPct.toFixed(2)}%</div>
                        </td>
                        <td className="py-3 px-3 text-center">
                          <span className="px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 text-xs border border-amber-500/30">
                            今日买入 · 次日可卖
                          </span>
                        </td>
                        <td className="py-3 px-3 text-center">
                          <button
                            onClick={() => handleSellPosition(pos)}
                            disabled={isSubmitting}
                            className="px-2.5 py-1 rounded bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 text-xs font-bold border border-rose-500/30 transition"
                          >
                            模拟平仓
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* 2. 成交流水表 */}
        {activeTab === 'orders' && (
          <div className="overflow-x-auto">
            {records.length === 0 ? (
              <div className="py-12 text-center text-slate-500 font-mono text-sm">
                暂无历史模拟交易成交流水
              </div>
            ) : (
              <table className="w-full text-left text-sm font-mono border-collapse">
                <thead>
                  <tr className="border-b border-white/10 text-slate-400">
                    <th className="py-2.5 px-3">委托时间</th>
                    <th className="py-2.5 px-3">证券代码/名称</th>
                    <th className="py-2.5 px-3">方向</th>
                    <th className="py-2.5 px-3 text-right">委托股数</th>
                    <th className="py-2.5 px-3 text-right">成交价格</th>
                    <th className="py-2.5 px-3 text-right">成交总额</th>
                    <th className="py-2.5 px-3">策略依据/备注</th>
                    <th className="py-2.5 px-3 text-center">状态</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 text-slate-200">
                  {records.map((r) => {
                    const isBuy = r.direction === 'buy';
                    return (
                      <tr key={r.id} className="hover:bg-white/[0.02] transition">
                        <td className="py-2.5 px-3 text-slate-400">{r.trade_time}</td>
                        <td className="py-2.5 px-3 font-bold text-white font-sans">
                          {r.name || r.code} <span className="font-mono text-slate-400 text-xs">({r.code})</span>
                        </td>
                        <td className={`py-2.5 px-3 font-bold ${isBuy ? 'text-rose-400' : 'text-emerald-400'}`}>
                          {isBuy ? '买入' : '卖出'}
                        </td>
                        <td className="py-2.5 px-3 text-right tabular-nums">{r.quantity.toLocaleString()}</td>
                        <td className="py-2.5 px-3 text-right tabular-nums">{r.price.toFixed(3)}</td>
                        <td className="py-2.5 px-3 text-right tabular-nums">{r.amount.toLocaleString()} 元</td>
                        <td className="py-2.5 px-3 text-slate-300 max-w-[240px] truncate" title={r.decision_summary || r.trade_reason || ''}>
                          {r.decision_summary || r.trade_reason || '--'}
                        </td>
                        <td className="py-2.5 px-3 text-center text-emerald-400 font-bold">
                          全部成交
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        )}

        {/* 3. 策略候选全景联动池 */}
        {activeTab === 'strategy_linkage' && (
          <div className="space-y-4">
            {strategyData?.strategies?.map((strat: any) => (
              <div key={strat.id} className="p-4 rounded-xl bg-slate-950/40 border border-white/5 space-y-3">
                <div className="flex items-center justify-between border-b border-white/5 pb-2">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-cyan-400" />
                    <span className="font-bold text-white text-sm">{strat.name}</span>
                    <span className="text-sm text-slate-400 font-mono">({strat.candidates_count} 只推荐标的)</span>
                  </div>
                  <span className="text-xs text-slate-500 font-mono">{strat.description}</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {strat.candidates?.map((cand: any) => {
                    const isHolding = positions.some((p) => p.code === cand.code);
                    const isUp = (cand.pct_change || 0) >= 0;

                    return (
                      <div
                        key={cand.code}
                        className="p-3 rounded-lg border border-white/10 bg-black/40 flex items-center justify-between gap-3"
                      >
                        <div className="space-y-1">
                          <div className="font-bold text-white text-sm flex items-center gap-1.5">
                            <span>{cand.name}</span>
                            <span className="text-slate-400 font-mono text-xs">{cand.code}</span>
                            <span className="px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 text-[10px] font-bold">
                              {cand.status_tag}
                            </span>
                          </div>
                          <div className="text-xs text-slate-400 font-mono flex items-center gap-2">
                            <span>评分: <b className="text-rose-400">{cand.score}</b></span>
                            <span className={isUp ? 'text-rose-400' : 'text-emerald-400'}>
                              {isUp ? '+' : ''}{Number(cand.pct_change || 0).toFixed(2)}%
                            </span>
                          </div>
                        </div>

                        <div>
                          {isHolding ? (
                            <span className="px-2 py-1 rounded bg-emerald-500/20 text-emerald-300 text-xs font-bold">
                              已持仓
                            </span>
                          ) : (
                            <button
                              onClick={() => handleQuickStrategyBuy(cand, strat.name)}
                              disabled={isSubmitting}
                              className="px-2.5 py-1 rounded bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold transition flex items-center gap-1"
                            >
                              <PlaySquare className="w-3 h-3" />
                              <span>跟单</span>
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 4. 波普尔证伪监控 */}
        {activeTab === 'risk' && (
          <div className="space-y-3">
            {positions.length === 0 ? (
              <div className="py-8 text-center text-slate-500 font-mono text-sm">
                当前暂无持仓标的需要风控哨兵监控
              </div>
            ) : (
              positions.map((pos) => {
                const curPrice = pos.current_price != null ? pos.current_price : pos.avg_cost;
                const stopPrice = (pos.avg_cost * 0.95).toFixed(2);

                return (
                  <div key={pos.code} className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-sm space-y-1.5">
                    <div className="font-bold text-amber-300 flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <AlertTriangle className="w-4 h-4" />
                        <span>{pos.name || pos.code} ({pos.code}) · 波普尔证伪哨兵生效中</span>
                      </div>
                      <span className="font-mono text-xs text-slate-400">
                        买入均价: ¥{pos.avg_cost.toFixed(2)} | 当前现价: ¥{curPrice.toFixed(2)}
                      </span>
                    </div>
                    <p className="text-slate-300 leading-relaxed font-mono">
                      防守止损线：成本 -5.0% (¥{stopPrice})。若盘中击穿该分水岭或发生炸板下杀超过 3 分钟未能修复，次日竞价触发强制抢跑止损保护。
                    </p>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* 新建模拟交易 Modal */}
      {/* ========================================================================= */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-white/15 rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <h3 className="text-base font-bold text-white flex items-center gap-2">
                <PlaySquare className="w-4 h-4 text-cyan-400" />
                <span>新建模拟交易订单</span>
              </h3>
              <button onClick={() => setIsModalOpen(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleManualOrderSubmit} className="space-y-3.5 text-sm font-mono">
              <div>
                <label className="block text-slate-400 mb-1">股票代码 (如 002724, 600519)</label>
                <input
                  type="text"
                  required
                  value={orderCode}
                  onChange={(e) => setOrderCode(e.target.value)}
                  placeholder="输入6位代码"
                  className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white focus:outline-none focus:border-cyan-500 text-sm"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">股票简称 (可选)</label>
                <input
                  type="text"
                  value={orderName}
                  onChange={(e) => setOrderName(e.target.value)}
                  placeholder="如 海洋王"
                  className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white focus:outline-none focus:border-cyan-500 text-sm"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-400 mb-1">买卖方向</label>
                  <select
                    value={orderDirection}
                    onChange={(e) => setOrderDirection(e.target.value as DirectionType)}
                    className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white focus:outline-none focus:border-cyan-500 text-sm"
                  >
                    <option value="buy">买入 (Buy)</option>
                    <option value="sell">卖出 (Sell)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-400 mb-1">委托价格 (元)</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={orderPrice}
                    onChange={(e) => setOrderPrice(parseFloat(e.target.value) || 0)}
                    className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white focus:outline-none focus:border-cyan-500 text-sm"
                  />
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1">委托数量 (股)</label>
                <input
                  type="number"
                  step="100"
                  required
                  value={orderQuantity}
                  onChange={(e) => setOrderQuantity(parseInt(e.target.value, 10) || 0)}
                  className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white focus:outline-none focus:border-cyan-500 text-sm"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">交易依据与反思备注</label>
                <input
                  type="text"
                  value={orderReason}
                  onChange={(e) => setOrderReason(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-black/50 border border-white/10 text-white focus:outline-none focus:border-cyan-500 text-sm"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/15 text-slate-300 text-sm font-semibold"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-sm font-bold shadow-md shadow-cyan-900/40"
                >
                  {isSubmitting ? '正在提交...' : '确认执行模拟交易'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}
