'use client';

import { useEffect, useState, use } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api } from '@/lib/api';
import { DailyReviewDetail, SubDimensionState } from '@/types/report';
import { formatDateWithWeekday, getWeekday } from '@/lib/utils';
import {
  ArrowLeft,
  RefreshCw,
  ShieldCheck,
  AlertTriangle,
  AlertCircle,
  Activity,
  Layers,
  Flame,
  Info,
  Sliders,
  Globe,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Scale,
  HelpCircle,
  Crosshair,
  CheckCircle2,
  XCircle,
  Clock,
  Play,
  Plus
} from 'lucide-react';
import { MarketHypothesis, MarketHypothesisCreatePayload } from '@/types/cognition';
import { CognitionLoopVisualizer } from '@/components/cognition/CognitionLoopVisualizer';

export default function ReviewDetailPage({ params }: { params: Promise<{ date: string }> }) {
  const { date } = use(params);
  const [data, setData] = useState<DailyReviewDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 推演假说跟踪器状态 (G1-Cognition Pre-market Hypothesis Tracker)
  const [hypotheses, setHypotheses] = useState<MarketHypothesis[]>([]);
  const [hypoLoading, setHypoLoading] = useState(false);
  const [showCreateHypo, setShowCreateHypo] = useState(false);
  const [creatingHypo, setCreatingHypo] = useState(false);
  const [verifyingId, setVerifyingId] = useState<number | null>(null);
  const [hypoError, setHypoError] = useState<string | null>(null);
  const [hypoSuccess, setHypoSuccess] = useState<string | null>(null);

  // 表单默认针对下一个交易日
  const [newHypoForm, setNewHypoForm] = useState<MarketHypothesisCreatePayload>({
    target_date: '',
    hypothesis_type: 'SENTIMENT_CYCLE',
    target_asset: '全市场短线情绪',
    expected_scenario: 'ROTATION',
    premise_logic: '',
    expected_phenomenon: '',
    invalidation_condition: '',
    assertion_metrics: {
      auction_up_ratio_min: 0.5,
      auction_limit_down_max: 0,
      close_limit_up_min: 30
    }
  });

  const loadHypotheses = async () => {
    try {
      setHypoLoading(true);
      const res = await api.getMarketHypotheses({ target_date: date });
      setHypotheses(res.items || []);
    } catch (err: any) {
      console.error('加载推演假说失败:', err);
    } finally {
      setHypoLoading(false);
    }
  };

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        setError(null);
        const res = await api.getDailyReview(date);
        setData(res);
      } catch (err: any) {
        console.error('获取复盘详情失败:', err);
        setError(err.message || '获取复盘详情失败');
      } finally {
        setLoading(false);
      }
    }
    loadData();
    loadHypotheses();
  }, [date]);

  // 创建推演假说
  const handleCreateHypo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (creatingHypo) return;
    setCreatingHypo(true);
    setHypoError(null);
    try {
      if (!newHypoForm.target_date || !newHypoForm.premise_logic || !newHypoForm.expected_phenomenon) {
        throw new Error('请完整填写目标日期、前提逻辑与预期盘面现象');
      }
      await api.createMarketHypothesis(newHypoForm);
      setHypoSuccess('推演假说已成功锁定录入！');
      setShowCreateHypo(false);
      await loadHypotheses();
      setTimeout(() => setHypoSuccess(null), 3000);
    } catch (err: any) {
      setHypoError(err?.message || '创建推演假说失败');
    } finally {
      setCreatingHypo(false);
    }
  };

  // 触发客观核验
  const handleVerify = async (hypoId: number, stage: 'AUCTION_0925' | 'CLOSE_1530') => {
    setVerifyingId(hypoId);
    setHypoError(null);
    try {
      await api.verifyMarketHypothesis(hypoId, stage);
      setHypoSuccess(`假说 #${hypoId} [${stage === 'AUCTION_0925' ? '09:25 竞价' : '15:30 收盘'}] 客观核对完成！`);
      await loadHypotheses();
      setTimeout(() => setHypoSuccess(null), 3000);
    } catch (err: any) {
      setHypoError(err?.message || '执行客观核对失败');
    } finally {
      setVerifyingId(null);
    }
  };

  // 物理状态标签颜色映射
  const getStateBadgeStyle = (label?: string) => {
    switch (label) {
      case '极弱收缩':
        return 'bg-rose-950/60 text-rose-300 border-rose-800/80';
      case '偏弱整理':
        return 'bg-amber-950/60 text-amber-300 border-amber-800/80';
      case '平稳中性':
        return 'bg-slate-800/80 text-cyan-300 border-cyan-800/80';
      case '偏强扩散':
        return 'bg-emerald-950/60 text-emerald-300 border-emerald-800/80';
      case '极度亢奋':
        return 'bg-purple-950/60 text-purple-300 border-purple-800/80';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  // 数据质量徽标（防御性空安全与未知状态中性处理）
  const renderQualityBadge = (quality?: string | null) => {
    const q = (quality || 'unknown').toLowerCase();
    if (q === 'full') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-950/80 text-emerald-400 border border-emerald-800">
          <ShieldCheck className="w-3.5 h-3.5" />
          全网有效 (Full)
        </span>
      );
    } else if (q === 'partial') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-950/80 text-amber-400 border border-amber-800">
          <AlertTriangle className="w-3.5 h-3.5" />
          部分降级 (Partial)
        </span>
      );
    } else if (q === 'invalid') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-950/80 text-rose-400 border border-rose-800">
          <AlertCircle className="w-3.5 h-3.5" />
          数据无效 (Invalid)
        </span>
      );
    } else {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-800 text-slate-400 border border-slate-700">
          <HelpCircle className="w-3.5 h-3.5" />
          质量未知 ({quality || 'Unknown'})
        </span>
      );
    }
  };

  if (loading) {
    return (
      <div className="py-32 text-center space-y-3">
        <RefreshCw className="w-8 h-8 text-teal-400 animate-spin mx-auto" />
        <p className="text-slate-400 text-sm">正在加载 {formatDateWithWeekday(date)} 复盘认知全景...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-8 max-w-4xl mx-auto space-y-4">
        <Link href="/review" className="inline-flex items-center gap-1 text-sm text-teal-400 hover:underline">
          <ArrowLeft className="w-4 h-4" /> 返回复盘列表
        </Link>
        <div className="p-6 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-200">
          <h3 className="font-semibold text-lg mb-2">未找到该日期的复盘数据</h3>
          <p className="text-sm text-slate-300">{error || '该日期可能尚未生成复盘记录。'}</p>
        </div>
      </div>
    );
  }

  const ms = data.market_state;
  const dims = ms?.dimensions || {};
  const d1 = dims['D1'];
  const d2 = dims['D2'];
  const d3 = dims['D3'];
  const d4 = dims['D4'];
  const d5 = dims['D5'];
  const d6 = dims['D6'];

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-8">
      {/* 顶部导航与状态条 */}
      <div className="space-y-4 border-b border-slate-800 pb-6">
        <Link
          href="/review"
          className="inline-flex items-center gap-1 text-sm text-slate-400 hover:text-teal-400 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> 返回复盘归档
        </Link>

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Activity className="w-7 h-7 text-teal-400" />
              <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-white">
                收盘认知复盘全景 · {formatDateWithWeekday(date)}
              </h1>
            </div>
            <p className="text-xs md:text-sm text-slate-400">
              数据采集与计算时间: {data.generated_at ? new Date(data.generated_at).toLocaleString('zh-CN') : '--'}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {ms?.state_label && (
              <span
                className={`px-3.5 py-1 rounded-full text-xs md:text-sm font-semibold border ${getStateBadgeStyle(
                  ms.state_label
                )}`}
              >
                全局物理状态：{ms.state_label}
              </span>
            )}
            {renderQualityBadge(data.data_quality)}
          </div>
        </div>
      </div>

      {/* 铁律质量警示条 */}
      {data.data_quality?.toLowerCase() === 'invalid' && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800 text-rose-300 text-sm flex items-start gap-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5 text-rose-400" />
          <div className="space-y-1">
            <div className="font-semibold text-rose-200">数据质量警示：INVALID (关键维度缺失)</div>
            <div className="text-xs text-rose-300/90 leading-relaxed">
              根据系统防伪铁律（Zero-Falsification Invariant），因核心市场数据缺失，全局综合分依法置空（None），严禁使用默认值伪造，不可作为策略执行的输入。
              {ms?.missing_metrics && ms.missing_metrics.length > 0 && (
                <span className="block mt-1 text-xs text-slate-300">
                  缺失指标: {ms.missing_metrics.join(', ')}
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {data.data_quality?.toLowerCase() === 'partial' && (
        <div className="p-3.5 rounded-xl bg-amber-950/30 border border-amber-800/80 text-amber-300 text-xs flex items-center gap-2.5">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 text-amber-400" />
          <span>
            提示：本期存在部分非关键指标缺失，已启用重归一化动态权重补偿。缺失项：
            {ms?.missing_metrics?.join(', ') || '微盘/外部衍生指标'}。其余维度均为真实网络数据。
          </span>
        </div>
      )}

      {/* ==================================================================== */}
      {/* Phase 2B.3: 认知闭环三核心卡片 (今日事实 -> 今日假说 -> 昨日裁决) */}
      {/* ==================================================================== */}
      <CognitionLoopVisualizer marketDate={date} />

      {/* ==================================================================== */}
      {/* 核心第一板块：六维市场状态向量 (Market State Vector) 看板 */}
      {/* ==================================================================== */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sliders className="w-5 h-5 text-teal-400" />
            <h2 className="text-lg font-bold text-white">市场状态向量 (Market State Vector)</h2>
          </div>
          <div className="text-xs text-slate-400 flex items-center gap-1">
            <Info className="w-3.5 h-3.5 text-teal-400" />
            <span>极性仅为物理测量属性，绝非买卖建议</span>
          </div>
        </div>

        {/* 6 大维度状态网格 */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* D1: 市场整体 */}
          {d1 && <DimensionCard dimension={d1} />}

          {/* D2: 纯粹广度 */}
          {d2 && <DimensionCard dimension={d2} />}

          {/* D4: 风格偏好 */}
          {d4 && <DimensionCard dimension={d4} />}

          {/* D5: 外部环境 */}
          {d5 && <DimensionCard dimension={d5} />}

          {/* D6: 流动性活跃度 */}
          {d6 && <DimensionCard dimension={d6} />}

          {/* 综合参考分诊断卡 */}
          <Card className="bg-slate-900/80 border-slate-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold text-slate-300 flex items-center justify-between">
                <span>综合参考分诊断 (Diagnostic)</span>
                <Scale className="w-4 h-4 text-cyan-400" />
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 pt-2">
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-slate-400">全局综合标量分</span>
                <span className="text-2xl font-mono font-bold text-cyan-300">
                  {ms?.composite_score !== null ? ms?.composite_score : '--'}
                </span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed">
                {ms?.composite_score !== null
                  ? '由 D1、D2、D4、D5、D6 按动态有效权重综合。D3 已按铁律正交隔离，绝不计入。'
                  : '因关键维度数据质量不满足阈值，全局综合分依法置空。'}
              </p>
              <div className="pt-2 border-t border-slate-800/80 text-[11px] text-slate-500">
                铁律：状态向量为主，综合标量仅作历史趋势辅助参考。
              </div>
            </CardContent>
          </Card>
        </div>

        {/* D3 短线情绪与极端生态：独立全宽/双子域卡片 (抗标量塌缩核心) */}
        {d3 && <D3OrthogonalCard dimension={d3} />}
      </div>

      {/* ==================================================================== */}
      {/* 核心第二板块：核心指数全景事实 */}
      {/* ==================================================================== */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-teal-400" />
          <h2 className="text-lg font-bold text-white">核心大盘指数行情全景</h2>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {(data.market_overview || []).map((idx: any, i: number) => {
            const rawPct = idx.pct_change ?? idx.changePercent;
            const hasPct = rawPct !== null && rawPct !== undefined && rawPct !== '';
            const pct = hasPct ? parseFloat(rawPct) : null;
            const isUp = pct !== null && pct > 0;
            const isDown = pct !== null && pct < 0;
            return (
              <Card key={i} className="bg-slate-900/90 border-slate-800">
                <CardContent className="p-4 space-y-2">
                  <div className="text-xs text-slate-400 font-medium">{idx.name}</div>
                  <div className="text-lg font-mono font-bold text-white">
                    {idx.price !== null && idx.price !== undefined ? Number(idx.price).toFixed(2) : '--'}
                  </div>
                  <div
                    className={`flex items-center gap-1 text-xs font-semibold ${
                      isUp ? 'text-rose-400' : isDown ? 'text-emerald-400' : 'text-slate-400'
                    }`}
                  >
                    {isUp ? <TrendingUp className="w-3.5 h-3.5" /> : isDown ? <TrendingDown className="w-3.5 h-3.5" /> : null}
                    <span>{pct !== null ? (pct >= 0 ? `+${pct.toFixed(2)}%` : `${pct.toFixed(2)}%`) : '--'}</span>
                  </div>
                  {idx.amount_wan !== null && idx.amount_wan !== undefined && (
                    <div className="text-[11px] text-slate-500 font-mono">
                      成交: {(Number(idx.amount_wan) / 10000).toFixed(0)} 亿元
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      {/* ==================================================================== */}
      {/* 核心第三板块：客观复盘结构化分析 */}
      {/* ==================================================================== */}
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Flame className="w-5 h-5 text-teal-400" />
          <h2 className="text-lg font-bold text-white">客观复盘归因与认知摘要</h2>
        </div>

        <Card className="bg-slate-900/80 border-slate-800">
          <CardContent className="p-6 space-y-4 text-slate-300 text-sm leading-relaxed">
            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-teal-300">维度事实总览</h3>
              <p>
                本交易日（{formatDateWithWeekday(date)}）全市场物理状态表征为【
                <span className="font-semibold text-white">{ms?.state_label || '未定义'}</span>
                】。全市场上涨家数约 {d2?.metrics?.up_count ?? '--'} 家，下跌家数约{' '}
                {d2?.metrics?.down_count ?? '--'} 家（涨跌家数比 {d2?.metrics?.up_down_ratio ?? '--'}）。
                两市总成交额约为 {d6?.metrics?.total_amount ? Number(d6.metrics.total_amount).toFixed(0) : '--'}{' '}
                亿元。
              </p>
            </div>

            <div className="space-y-2 pt-2 border-t border-slate-800">
              <h3 className="text-sm font-semibold text-teal-300">投机与尾部博弈事实</h3>
              <p>
                短线连板最高空间为 {d3?.sub_domains?.speculative_structure?.metrics?.max_board_height?.raw ?? d3?.metrics?.max_board_height ?? '--'} 板。
                全市场涨停 {d3?.sub_domains?.tail_extremes?.metrics?.limit_up_count?.raw ?? d3?.metrics?.limit_up_count ?? '--'} 家，
                跌停 {d3?.sub_domains?.tail_extremes?.metrics?.limit_down_count?.raw ?? d3?.metrics?.limit_down_count ?? '--'} 家，
                涨跌停净差为 {d3?.sub_domains?.tail_extremes?.metrics?.limit_diff?.raw ?? d3?.metrics?.limit_diff ?? '--'} 家，
                真实炸板率为 {
                  d3?.sub_domains?.tail_extremes?.metrics?.broken_limit_ratio?.raw !== null &&
                  d3?.sub_domains?.tail_extremes?.metrics?.broken_limit_ratio?.raw !== undefined
                    ? (Number(d3.sub_domains.tail_extremes.metrics.broken_limit_ratio.raw) * 100).toFixed(1) + '%'
                    : '--'
                }。
              </p>
            </div>

            <div className="p-3 rounded bg-slate-950/70 border border-slate-800/80 text-xs text-slate-400">
              系统认知准则：本复盘严格基于客观物理指标输出，不作任何“主升、退潮”等主观交易周期定性，不构成任何投资买卖信号。
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ==================================================================== */}
      {/* 核心第四板块：跨交易日推演假说跟踪器 (Pre-market Hypothesis Tracker) */}
      {/* ==================================================================== */}
      <div className="space-y-4 pt-4 border-t border-slate-800">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Crosshair className="w-5 h-5 text-teal-400" />
            <h2 className="text-lg font-bold text-white">跨交易日推演假说跟踪与客观核对</h2>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-teal-950 text-teal-300 border border-teal-800 font-mono">
              Hypothesis Tracker
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setShowCreateHypo(!showCreateHypo);
                if (!newHypoForm.target_date) {
                  // 计算下一个交易日草稿
                  const d = new Date(date);
                  d.setDate(d.getDate() + (d.getDay() === 5 ? 3 : 1));
                  const nextDateStr = d.toISOString().split('T')[0];
                  setNewHypoForm(f => ({ ...f, target_date: nextDateStr }));
                }
              }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-500 text-white font-medium text-xs transition shadow-sm"
            >
              <Plus className="w-3.5 h-3.5" />
              {showCreateHypo ? '收起录入表单' : '录入推演假说'}
            </button>
            <button
              onClick={loadHypotheses}
              disabled={hypoLoading}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs border border-slate-700 transition"
              title="刷新假说与兑现核对状态"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${hypoLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* 提示消息 */}
        {hypoSuccess && (
          <div className="flex items-center gap-2 p-3 bg-emerald-950/70 border border-emerald-800 text-emerald-300 rounded-lg text-xs">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{hypoSuccess}</span>
          </div>
        )}
        {hypoError && (
          <div className="flex items-center gap-2 p-3 bg-rose-950/70 border border-rose-800 text-rose-300 rounded-lg text-xs">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{hypoError}</span>
          </div>
        )}

        {/* 新建假说录入表单 */}
        {showCreateHypo && (
          <Card className="bg-slate-900 border-teal-500/40 animate-in fade-in">
            <CardHeader className="pb-3 border-b border-slate-800">
              <CardTitle className="text-sm font-bold text-teal-300 flex items-center gap-2">
                <Crosshair className="w-4 h-4 text-teal-400" />
                录入前向推演假说（不可篡改锁定）
              </CardTitle>
              <p className="text-xs text-slate-400">
                依据科学哲学原则，假说必须具备可证伪性与客观兑现条件，开盘后状态机将自动锁定并禁止篡改。
              </p>
            </CardHeader>
            <CardContent className="p-4 md:p-6">
              <form onSubmit={handleCreateHypo} className="space-y-4 text-xs">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-slate-400 mb-1">
                      目标验证日期 (YYYY-MM-DD) * {newHypoForm.target_date && <span className="text-teal-400 font-mono">({getWeekday(newHypoForm.target_date)})</span>}
                    </label>
                    <input
                      type="date"
                      required
                      value={newHypoForm.target_date}
                      onChange={(e) => setNewHypoForm(f => ({ ...f, target_date: e.target.value }))}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 font-mono"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 mb-1">假说类型 (Hypothesis Type) *</label>
                    <select
                      value={newHypoForm.hypothesis_type}
                      onChange={(e) => setNewHypoForm(f => ({ ...f, hypothesis_type: e.target.value as any }))}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100"
                    >
                      <option value="SENTIMENT_CYCLE">情绪周期推演 (SENTIMENT_CYCLE)</option>
                      <option value="INDEX_TREND">大盘指数趋势 (INDEX_TREND)</option>
                      <option value="SECTOR_LEADER">核心板块与高标 (SECTOR_LEADER)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-slate-400 mb-1">目标标的/主线资产 *</label>
                    <input
                      type="text"
                      required
                      value={newHypoForm.target_asset}
                      onChange={(e) => setNewHypoForm(f => ({ ...f, target_asset: e.target.value }))}
                      placeholder="例如：连板高标空间 / 芯片半导体 / 沪深300"
                      className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-400 mb-1">预期情景 (Expected Scenario) *</label>
                    <select
                      value={newHypoForm.expected_scenario}
                      onChange={(e) => setNewHypoForm(f => ({ ...f, expected_scenario: e.target.value as any }))}
                      className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100"
                    >
                      <option value="ROTATION">轮动博弈 (ROTATION)</option>
                      <option value="ACCELERATION">加速扩散 (ACCELERATION)</option>
                      <option value="DIVERGENCE">分歧分化 (DIVERGENCE)</option>
                      <option value="REBOUND">超跌反弹 (REBOUND)</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-slate-400 mb-1">核心前提逻辑 (Premise Logic) *</label>
                    <input
                      type="text"
                      required
                      value={newHypoForm.premise_logic}
                      onChange={(e) => setNewHypoForm(f => ({ ...f, premise_logic: e.target.value }))}
                      placeholder="例如：今日高标全部晋级，两市成交放量，短线情绪处于扩散主升期..."
                      className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-400 mb-1">预期客观盘面现象 (Expected Phenomenon) *</label>
                    <textarea
                      rows={2}
                      required
                      value={newHypoForm.expected_phenomenon}
                      onChange={(e) => setNewHypoForm(f => ({ ...f, expected_phenomenon: e.target.value }))}
                      placeholder="例如：09:25 竞价核心高标高开>3%，全天上证成交额突破1万亿，涨停数>40家..."
                      className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-slate-100"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 mb-1">失效/证伪刚性条件 (Invalidation Condition) *</label>
                    <textarea
                      rows={2}
                      required
                      value={newHypoForm.invalidation_condition}
                      onChange={(e) => setNewHypoForm(f => ({ ...f, invalidation_condition: e.target.value }))}
                      placeholder="例如：开盘跌停家数>2家，或核心高标竞价跌停低开，或大盘缩量超15%..."
                      className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-slate-100"
                    />
                  </div>
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setShowCreateHypo(false)}
                    className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded font-medium"
                  >
                    取消
                  </button>
                  <button
                    type="submit"
                    disabled={creatingHypo}
                    className="px-5 py-1.5 bg-teal-600 hover:bg-teal-500 text-white rounded font-bold transition shadow-sm disabled:opacity-50"
                  >
                    {creatingHypo ? '正在锁定...' : '锁定并提交假说'}
                  </button>
                </div>
              </form>
            </CardContent>
          </Card>
        )}

        {/* 假说列表与双轨客观核对 */}
        {hypotheses.length === 0 ? (
          <div className="p-8 text-center rounded-xl bg-slate-900/40 border border-dashed border-slate-800 text-slate-400 space-y-2">
            <Crosshair className="w-8 h-8 mx-auto text-slate-600" />
            <div className="text-sm font-semibold text-slate-300">本日暂无推演假说跟踪记录</div>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              可以在上方点击【录入推演假说】针对下一交易日制定推演预案，系统将在开盘后执行 09:25 竞价初判与 15:30 收盘终核。
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {hypotheses.map((hypo) => {
              const vAuction = hypo.verifications?.find(v => v.verification_stage === 'AUCTION_0925');
              const vClose = hypo.verifications?.find(v => v.verification_stage === 'CLOSE_1530');

              const getOutcomeBadge = (outcome?: string) => {
                switch (outcome) {
                  case 'CONFIRMED':
                    return <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold text-[10px]">🟢 逻辑证实 (CONFIRMED)</span>;
                  case 'FALSIFIED':
                    return <span className="px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800 font-bold text-[10px]">🔴 逻辑证伪 (FALSIFIED)</span>;
                  case 'PARTIAL':
                    return <span className="px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800 font-bold text-[10px]">🟡 部分兑现 (PARTIAL)</span>;
                  case 'INCONCLUSIVE':
                    return <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700 font-bold text-[10px]">⚪ 数据缺失防伪 (INCONCLUSIVE)</span>;
                  case 'INVALID':
                    return <span className="px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800 font-bold text-[10px]">🟣 前提失效 (INVALID)</span>;
                  default:
                    return <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 text-[10px]">待核验</span>;
                }
              };

              return (
                <Card key={hypo.id} className="bg-slate-900/80 border-slate-800 shadow-md">
                  <CardHeader className="pb-3 border-b border-slate-800/80">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs px-2 py-0.5 rounded bg-slate-800 text-teal-400 border border-slate-700">
                          #{hypo.id}
                        </span>
                        <CardTitle className="text-base font-bold text-slate-100">
                          {hypo.target_asset} · {hypo.expected_scenario}
                        </CardTitle>
                        <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                          {hypo.hypothesis_type}
                        </span>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-400 font-mono">
                          目标验证日: <strong className="text-slate-200">{formatDateWithWeekday(hypo.target_date)}</strong>
                        </span>
                        <span className={`text-[11px] px-2 py-0.5 rounded font-mono font-semibold uppercase ${
                          hypo.status === 'CLOSED'
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                            : hypo.status === 'VERIFYING'
                            ? 'bg-cyan-950 text-cyan-400 border border-cyan-800'
                            : 'bg-slate-800 text-slate-300 border border-slate-700'
                        }`}>
                          状态: {hypo.status}
                        </span>
                      </div>
                    </div>
                  </CardHeader>

                  <CardContent className="p-4 md:p-6 space-y-4 text-xs">
                    {/* 推演前提与预期 */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 bg-slate-950/60 p-3 rounded-xl border border-slate-800/60">
                      <div>
                        <div className="text-[10px] text-slate-500 font-semibold mb-1">核心逻辑依据 (Premise)</div>
                        <div className="text-slate-300 leading-relaxed">{hypo.premise_logic}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-teal-400 font-semibold mb-1">预期兑现盘面现象 (Phenomenon)</div>
                        <div className="text-slate-300 leading-relaxed">{hypo.expected_phenomenon}</div>
                      </div>
                      <div>
                        <div className="text-[10px] text-rose-400 font-semibold mb-1">失效/证伪刚性条件 (Invalidation)</div>
                        <div className="text-slate-300 leading-relaxed">{hypo.invalidation_condition}</div>
                      </div>
                    </div>

                    {/* 双轨核验快照卡片 (Stage 1 & Stage 2) */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                      {/* Stage 1: 早盘竞价初判 */}
                      <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2.5">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5 font-bold text-slate-200">
                            <Clock className="w-3.5 h-3.5 text-teal-400" />
                            <span>早盘竞价初判快照 (AUCTION_0925)</span>
                          </div>
                          {vAuction ? getOutcomeBadge(vAuction.outcome) : (
                            <button
                              onClick={() => handleVerify(hypo.id, 'AUCTION_0925')}
                              disabled={verifyingId === hypo.id}
                              className="px-2.5 py-1 rounded bg-teal-700 hover:bg-teal-600 text-white font-medium text-[11px] transition shadow-sm disabled:opacity-50 flex items-center gap-1"
                            >
                              <Play className="w-3 h-3" />
                              {verifyingId === hypo.id ? '核对中...' : '执行早盘初核'}
                            </button>
                          )}
                        </div>

                        {vAuction ? (
                          <div className="space-y-1.5 text-slate-400 text-xs">
                            <div className="text-slate-300 bg-slate-900/60 p-2 rounded border border-slate-800">
                              <span className="text-slate-500 font-semibold">客观偏差分析: </span>
                              {vAuction.deviation_analysis}
                            </div>
                            <div className="text-[11px] text-slate-500 font-mono">
                              核验时间: {vAuction.verified_at || '--'}
                            </div>
                          </div>
                        ) : (
                          <p className="text-slate-500 text-[11px] italic">
                            早盘 09:25:30 竞价数据到达后，将自动对撞高标溢价与竞价量能比。
                          </p>
                        )}
                      </div>

                      {/* Stage 2: 全天收盘终核 */}
                      <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2.5">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-1.5 font-bold text-slate-200">
                            <CheckCircle2 className="w-3.5 h-3.5 text-indigo-400" />
                            <span>全天收盘结案终核 (CLOSE_1530)</span>
                          </div>
                          {vClose ? getOutcomeBadge(vClose.outcome) : (
                            <button
                              onClick={() => handleVerify(hypo.id, 'CLOSE_1530')}
                              disabled={verifyingId === hypo.id}
                              className="px-2.5 py-1 rounded bg-indigo-700 hover:bg-indigo-600 text-white font-medium text-[11px] transition shadow-sm disabled:opacity-50 flex items-center gap-1"
                            >
                              <Play className="w-3 h-3" />
                              {verifyingId === hypo.id ? '终核中...' : '执行收盘终核'}
                            </button>
                          )}
                        </div>

                        {vClose ? (
                          <div className="space-y-1.5 text-slate-400 text-xs">
                            <div className="text-slate-300 bg-slate-900/60 p-2 rounded border border-slate-800">
                              <span className="text-slate-500 font-semibold">终局 Gap 归因: </span>
                              {vClose.deviation_analysis}
                            </div>
                            <div className="text-[11px] text-slate-500 font-mono">
                              终核时间: {vClose.verified_at || '--'}
                            </div>
                          </div>
                        ) : (
                          <p className="text-slate-500 text-[11px] italic">
                            15:30 收盘后终局裁决。联合唯一键确保双快照并存，不可物理覆盖。
                          </p>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------
// 子组件：通用维度卡片 (D1, D2, D4, D5, D6)
// --------------------------------------------------------------------------
function DimensionCard({ dimension: dim }: { dimension: SubDimensionState }) {
  const getQualityBadge = (quality: string) => {
    const q = quality.toLowerCase();
    if (q === 'full') return <span className="text-[11px] text-emerald-400">Full</span>;
    if (q === 'partial') return <span className="text-[11px] text-amber-400">Partial</span>;
    return <span className="text-[11px] text-rose-400">Invalid</span>;
  };

  return (
    <Card className="bg-slate-900/90 border-slate-800 flex flex-col justify-between">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-mono font-bold text-teal-400 uppercase tracking-wide">
            {dim.dimension_id}
          </span>
          {getQualityBadge(dim.quality)}
        </div>
        <CardTitle className="text-base font-semibold text-slate-100 mt-1">
          {dim.name}
        </CardTitle>
        <div className="text-xs text-slate-400 line-clamp-1">{dim.semantics_desc}</div>
      </CardHeader>

      <CardContent className="space-y-3 pt-1">
        <div className="flex items-baseline justify-between border-t border-slate-800/80 pt-2">
          <span className="text-xs text-slate-400">归一化得分</span>
          <span className="text-2xl font-mono font-bold text-white">
            {dim.score !== null ? dim.score : '--'}
          </span>
        </div>

        <div className="flex items-center justify-between text-xs">
          <span className="text-slate-400">物理刻度标签:</span>
          <span className="font-medium text-slate-200">{dim.state_label || '--'}</span>
        </div>

        {/* 关键物理指标数值 */}
        <div className="p-2.5 rounded bg-slate-950/60 border border-slate-800/60 space-y-1 text-xs font-mono">
          {Object.entries(dim.metrics || {}).map(([key, val]) => (
            <div key={key} className="flex justify-between items-center text-slate-400">
              <span className="truncate max-w-[150px]">{key}</span>
              <span className="text-slate-200 font-semibold">{val !== null && val !== undefined ? String(val) : '--'}</span>
            </div>
          ))}
        </div>

        <div className="text-[10px] text-slate-500 flex items-center justify-between pt-1">
          <span>极性元数据: {dim.metric_polarity}</span>
          <span>非买卖信号</span>
        </div>
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------------------------------
// 子组件：D3 短线情绪与极端生态 (独立正交双子域卡片)
// --------------------------------------------------------------------------
function D3OrthogonalCard({ dimension: dim }: { dimension: SubDimensionState }) {
  const subA = dim.sub_domains?.['speculative_structure'];
  const subB = dim.sub_domains?.['tail_extremes'];

  return (
    <Card className="bg-slate-900 border-teal-500/30 shadow-lg shadow-teal-950/20">
      <CardHeader className="pb-3 border-b border-slate-800">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-teal-950 text-teal-400 border border-teal-800">
                {dim.dimension_id} 特殊正交维度
              </span>
              <span className="text-xs text-amber-400 font-medium">
                [铁律：核心综合分强制为 None，杜绝标量塌缩]
              </span>
            </div>
            <CardTitle className="text-lg font-bold text-white mt-1.5">
              {dim.name}
            </CardTitle>
            <p className="text-xs text-slate-400 mt-0.5">{dim.semantics_desc}</p>
          </div>

          <div className="text-right sm:self-center">
            <span className="text-xs text-slate-400 block">诊断参考分 (仅回溯备查):</span>
            <span className="text-lg font-mono font-bold text-slate-300">
              {dim.reference_score !== null && dim.reference_score !== undefined
                ? dim.reference_score
                : '--'}
            </span>
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-4 md:p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* 子域 A: 投机高标结构事实 */}
          <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Flame className="w-4 h-4 text-orange-400" />
                <h4 className="text-sm font-bold text-slate-200">
                  子域 A：投机高标结构事实
                </h4>
              </div>
              <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                质量: {subA?.quality || 'partial'}
              </span>
            </div>

            <div className="flex items-baseline justify-between border-t border-slate-800/80 pt-2">
              <span className="text-xs text-slate-400">子域独立物理得分</span>
              <span className="text-xl font-mono font-bold text-orange-300">
                {subA?.score !== null && subA?.score !== undefined ? subA.score : '--'}
              </span>
            </div>

            <div className="space-y-1.5 text-xs font-mono">
              <div className="flex justify-between py-1 border-b border-slate-800/40 text-slate-400">
                <span>最高空间板 (max_board_height):</span>
                <span className="text-white font-bold">
                  {subA?.metrics?.max_board_height?.raw ?? dim.metrics?.max_board_height ?? '--'} 板
                </span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/40 text-slate-400">
                <span>连板晋级率 (promotion_rate):</span>
                <span className="text-white font-bold">
                  {subA?.metrics?.promotion_rate?.raw !== null && subA?.metrics?.promotion_rate?.raw !== undefined
                    ? (Number(subA.metrics.promotion_rate.raw) * 100).toFixed(1) + '%'
                    : '-- (无连续样本防填0)'}
                </span>
              </div>
            </div>
            <div className="text-[11px] text-slate-500">
              描述连板空间与高标梯度，不掺杂任何涨跌停总数。
            </div>
          </div>

          {/* 子域 B: 尾部极端博弈事实 */}
          <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <Layers className="w-4 h-4 text-cyan-400" />
                <h4 className="text-sm font-bold text-slate-200">
                  子域 B：尾部极端博弈事实
                </h4>
              </div>
              <span className="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300">
                质量: {subB?.quality || 'partial'}
              </span>
            </div>

            <div className="flex items-baseline justify-between border-t border-slate-800/80 pt-2">
              <span className="text-xs text-slate-400">子域独立物理得分</span>
              <span className="text-xl font-mono font-bold text-cyan-300">
                {subB?.score !== null && subB?.score !== undefined ? subB.score : '--'}
              </span>
            </div>

            <div className="space-y-1.5 text-xs font-mono">
              <div className="flex justify-between py-1 border-b border-slate-800/40 text-slate-400">
                <span>全市场涨停 (limit_up_count):</span>
                <span className="text-rose-400 font-bold">
                  {subB?.metrics?.limit_up_count?.raw ?? dim.metrics?.limit_up_count ?? '--'} 家
                </span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/40 text-slate-400">
                <span>全市场跌停 (limit_down_count):</span>
                <span className="text-emerald-400 font-bold">
                  {subB?.metrics?.limit_down_count?.raw ?? dim.metrics?.limit_down_count ?? '--'} 家
                </span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/40 text-slate-400">
                <span>涨跌停净差 (limit_diff):</span>
                <span className="text-white font-bold">
                  {subB?.metrics?.limit_diff?.raw ?? dim.metrics?.limit_diff ?? '--'} 家
                </span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/40 text-slate-400">
                <span>真实炸板率 (broken_limit_ratio):</span>
                <span className="text-amber-400 font-bold">
                  {subB?.metrics?.broken_limit_ratio?.raw !== null && subB?.metrics?.broken_limit_ratio?.raw !== undefined
                    ? (Number(subB.metrics.broken_limit_ratio.raw) * 100).toFixed(1) + '%'
                    : '--'}
                </span>
              </div>
            </div>
            <div className="text-[11px] text-slate-500">
              描述涨停封板率与极端尾部冷热，由 D3 独立原生统计。
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
