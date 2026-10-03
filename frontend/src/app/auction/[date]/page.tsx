'use client';

import { useEffect, useState, use } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api } from '@/lib/api';
import { 
  AuctionReportDetail, 
  IndexOpenItem, 
  HighTierAuctionStock 
} from '@/types/report';
import { formatDateWithWeekday } from '@/lib/utils';
import {
  ArrowLeft,
  Clock,
  ShieldAlert,
  Flame,
  Activity,
  BarChart3,
  TrendingUp,
  TrendingDown,
  Info,
  CheckCircle2,
  AlertTriangle,
  Layers,
  ChevronRight
} from 'lucide-react';

export default function AuctionDetailPage({ params }: { params: Promise<{ date: string }> }) {
  const { date } = use(params);
  const [data, setData] = useState<AuctionReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        setError(null);
        const res = await api.getAuctionReport(date);
        setData(res);
      } catch (err: any) {
        console.error('获取集合竞价详情失败:', err);
        setError(err.message || '获取集合竞价详情失败');
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [date]);

  const getEmotionBadgeStyle = (label?: string) => {
    const l = label || '';
    if (l.includes('放量高开') || l.includes('偏强')) {
      return 'bg-emerald-950/60 text-emerald-300 border-emerald-800/80';
    } else if (l.includes('平开') || l.includes('中性')) {
      return 'bg-slate-800/80 text-cyan-300 border-cyan-800/80';
    } else if (l.includes('缩量') || l.includes('偏弱')) {
      return 'bg-amber-950/60 text-amber-300 border-amber-800/80';
    } else if (l.includes('极端') || l.includes('分歧') || l.includes('释放')) {
      return 'bg-rose-950/60 text-rose-300 border-rose-800/80';
    } else {
      return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  const formatPct = (val?: number | null) => {
    if (val === null || val === undefined) return '--';
    const sign = val > 0 ? '+' : '';
    return `${sign}${val.toFixed(2)}%`;
  };

  const getPctColor = (val?: number | null) => {
    if (val === null || val === undefined) return 'text-slate-400';
    if (val > 0) return 'text-rose-400';
    if (val < 0) return 'text-emerald-400';
    return 'text-slate-400';
  };

  const getPctBg = (val?: number | null) => {
    if (val === null || val === undefined) return 'bg-slate-900/80 border-slate-800';
    if (val > 0) return 'bg-rose-950/20 border-rose-900/40';
    if (val < 0) return 'bg-emerald-950/20 border-emerald-900/40';
    return 'bg-slate-900/80 border-slate-800';
  };

  const formatNumber = (val?: number | null, decimals = 2) => {
    if (val === null || val === undefined) return '--';
    return val.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  };

  if (loading) {
    return (
      <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-6">
        <div className="flex items-center gap-2 text-slate-400 text-sm">
          <Link href="/auction" className="hover:text-teal-400 transition flex items-center gap-1">
            <ArrowLeft className="w-4 h-4" /> 返回归档列表
          </Link>
        </div>
        <div className="h-20 rounded-xl bg-slate-900 border border-slate-800 animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 rounded-xl bg-slate-900 border border-slate-800 animate-pulse" />
          ))}
        </div>
        <div className="h-48 rounded-xl bg-slate-900 border border-slate-800 animate-pulse" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-6">
        <div className="flex items-center gap-2 text-slate-400 text-sm">
          <Link href="/auction" className="hover:text-teal-400 transition flex items-center gap-1">
            <ArrowLeft className="w-4 h-4" /> 返回归档列表
          </Link>
        </div>
        <Card className="bg-rose-950/30 border-rose-800 text-rose-300 p-8 text-center">
          <AlertTriangle className="w-12 h-12 text-rose-400 mx-auto mb-3" />
          <h2 className="text-xl font-bold mb-2">获取集合竞价报告失败</h2>
          <p className="text-sm text-slate-400 mb-4">{error || '未找到该日期的集合竞价记录'}</p>
          <Link
            href="/auction"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium transition"
          >
            返回列表
          </Link>
        </Card>
      </div>
    );
  }

  const { index_open_data, high_open_stats, emotion_judgment, generated_at } = data;
  const indices = index_open_data?.indices || [];

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-8">
      {/* 顶部导航与标题 */}
      <div className="space-y-4">
        <div className="flex items-center justify-between text-slate-400 text-sm">
          <Link
            href="/auction"
            className="hover:text-teal-400 transition flex items-center gap-1.5 font-medium"
          >
            <ArrowLeft className="w-4 h-4" /> 返回归档列表
          </Link>
          <div className="flex items-center gap-1 text-xs text-slate-400 font-mono">
            <Clock className="w-3.5 h-3.5" />
            撮合时间: 09:25 | 记录时间: {generated_at ? generated_at.replace('T', ' ').slice(0, 19) : '--'}
          </div>
        </div>

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <Clock className="w-8 h-8 text-teal-400" />
              <h1 className="text-2xl md:text-3xl font-extrabold text-white tracking-tight">
                M3 集合竞价观测全景 · {formatDateWithWeekday(date)}
              </h1>
            </div>
            <p className="text-xs md:text-sm text-slate-400">
              09:25 开盘微观物理事实观测 · 竞价量能承接比 · 高标开盘溢价 · 零买卖信号
            </p>
          </div>
        </div>

        {/* 免责声明提示条 */}
        <div className="p-3.5 rounded-lg bg-teal-950/20 border border-teal-900/40 text-teal-300 text-xs flex items-start gap-2.5">
          <ShieldAlert className="w-4 h-4 text-teal-400 shrink-0 mt-0.5" />
          <div className="leading-relaxed">
            <span className="font-semibold text-teal-200">【微观事实观测与状态承接】</span>
            本看板在每个交易日 09:25 集中撮合瞬间对全市场物理事实（指数跳空、竞价成交量、高标溢价、一字多空封单）进行无偏测量与事实验证，绝不承担任何交易决策，严禁作为买卖操作信号。市场有风险，投资需谨慎。
          </div>
        </div>
      </div>

      {/* 模块一：全景指数开盘跳空与竞价量能比值网格 */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-teal-400" />
            <h2 className="text-lg font-bold text-white tracking-wide">
              全景指数开盘跳空与竞价量能
            </h2>
          </div>
          <span className="text-xs text-slate-400">09:25 交易所撮合开盘快照</span>
        </div>

        {/* 指数网格 */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
          {indices.map((idx: IndexOpenItem) => (
            <Card key={idx.code} className={`transition-all ${getPctBg(idx.pct_change)}`}>
              <CardContent className="p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-200 truncate">{idx.name}</span>
                  <span className="text-[10px] text-slate-400 font-mono uppercase">{idx.code}</span>
                </div>

                <div className="flex items-baseline justify-between pt-1">
                  <div className="text-lg font-bold font-mono text-white">
                    {formatNumber(idx.price, 2)}
                  </div>
                  <div className={`text-sm font-bold font-mono ${getPctColor(idx.pct_change)}`}>
                    {formatPct(idx.pct_change)}
                  </div>
                </div>

                <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-800/80">
                  <span>竞价成交额</span>
                  <span className="font-mono text-slate-300">
                    {idx.amount_wan !== null && idx.amount_wan !== undefined
                      ? `${(idx.amount_wan / 10000).toFixed(2)} 亿元`
                      : '--'}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* 竞价量能承接比核心指示卡片 */}
        <Card className="bg-slate-900/80 border-slate-800">
          <CardContent className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-cyan-400" />
                <span className="text-sm font-bold text-slate-200">两市竞价量能承接比 (Bidding Ratio)</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed max-w-2xl">
                数学定义：沪深两市 09:25 竞价总成交额占前一交易日两市全天总成交额之比值（口径同构对应）。表征开盘早盘交投承接活跃度。
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-6 shrink-0 pt-3 md:pt-0 border-t md:border-t-0 border-slate-800">
              <div>
                <div className="text-xs text-slate-400 mb-0.5">两市竞价总额</div>
                <div className="text-lg font-bold font-mono text-white">
                  {index_open_data?.total_bidding_amount_yi !== null && index_open_data?.total_bidding_amount_yi !== undefined
                    ? `${index_open_data.total_bidding_amount_yi.toFixed(1)} 亿元`
                    : '--'}
                </div>
              </div>

              <div>
                <div className="text-xs text-slate-400 mb-0.5">前日两市全天额</div>
                <div className="text-lg font-bold font-mono text-teal-300">
                  {index_open_data?.yesterday_total_amount_yi !== null && index_open_data?.yesterday_total_amount_yi !== undefined
                    ? `${index_open_data.yesterday_total_amount_yi.toFixed(0)} 亿元`
                    : '--'}
                </div>
              </div>

              <div>
                <div className="text-xs text-slate-400 mb-0.5">承接比值与状态</div>
                <div className="flex items-center gap-2">
                  <span className="text-xl font-bold font-mono text-amber-400">
                    {index_open_data?.bidding_volume_ratio !== null && index_open_data?.bidding_volume_ratio !== undefined
                      ? `${index_open_data.bidding_volume_ratio.toFixed(2)}%`
                      : '--'}
                  </span>
                  {getRatioStatusBadge(index_open_data?.bidding_volume_ratio)}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* 模块二：09:25 开盘客观情绪承接研判与 M2 事实验证 */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-indigo-400" />
            <h2 className="text-lg font-bold text-white tracking-wide">
              开盘多空承接客观研判与 M2 事实验证
            </h2>
            <span className="text-xs text-slate-400">（物理事实核验 · 绝无预测打分）</span>
          </div>
        </div>

        <Card className="bg-slate-900/80 border-slate-800">
          <CardContent className="p-5 md:p-6 space-y-4">
            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-400">开盘多空承接状态:</span>
              <span
                className={`px-3.5 py-1 rounded-full text-xs font-bold border ${getEmotionBadgeStyle(
                  emotion_judgment?.label
                )}`}
              >
                【{emotion_judgment?.label || '未就绪'}】
              </span>
            </div>

            {/* 叙事实录 */}
            <div className="p-4 rounded-lg bg-slate-950/70 border border-slate-800 text-xs md:text-sm text-slate-300 leading-relaxed space-y-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-200">
                <CheckCircle2 className="w-4 h-4 text-teal-400" />
                <span>09:25 集合竞价物理事实核验述评</span>
              </div>
              <p>{emotion_judgment?.narrative || '暂无述评记录。'}</p>
            </div>

            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 pt-1">
              <Info className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <span>{emotion_judgment?.disclaimer || '客观观察维度提示，非买卖建议'}</span>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* 模块三：昨日高标/连板梯队竞价溢价生态看板 */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Flame className="w-5 h-5 text-amber-400" />
            <h2 className="text-lg font-bold text-white tracking-wide">
              高标梯队开盘溢价与连板生态
            </h2>
            <span className="text-xs text-slate-400">
              (跟踪昨日涨停样本: {high_open_stats?.tested_count ?? 0} 只)
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="bg-slate-900/80 border-slate-800">
            <CardContent className="p-4 space-y-1">
              <span className="text-xs text-slate-400">涨停池高开率</span>
              <div className="text-2xl font-bold font-mono text-white">
                {high_open_stats?.high_open_ratio !== null && high_open_stats?.high_open_ratio !== undefined
                  ? `${high_open_stats.high_open_ratio.toFixed(1)}%`
                  : '--'}
              </div>
              <div className="text-[11px] text-slate-400">
                高开 {high_open_stats?.high_open_count ?? 0} / 低开 {high_open_stats?.low_open_count ?? 0}
              </div>
            </CardContent>
          </Card>

          <Card className="bg-slate-900/80 border-slate-800">
            <CardContent className="p-4 space-y-1">
              <span className="text-xs text-slate-400">高标平均竞价溢价</span>
              <div className={`text-2xl font-bold font-mono ${getPctColor(high_open_stats?.avg_premium_pct)}`}>
                {formatPct(high_open_stats?.avg_premium_pct)}
              </div>
              <div className="text-[11px] text-slate-400">样本标的开盘涨幅算术均值</div>
            </CardContent>
          </Card>

          <Card className="bg-slate-900/80 border-slate-800">
            <CardContent className="p-4 space-y-1">
              <span className="text-xs text-slate-400">一字涨停 / 一字跌停</span>
              <div className="text-2xl font-bold font-mono">
                <span className="text-rose-400">{high_open_stats?.one_word_up_count ?? 0}</span>
                <span className="text-slate-500 mx-1.5">/</span>
                <span className="text-emerald-400">{high_open_stats?.one_word_down_count ?? 0}</span>
              </div>
              <div className="text-[11px] text-slate-400">多头顶板 vs 极端核按钮</div>
            </CardContent>
          </Card>

          <Card className="bg-slate-900/80 border-slate-800">
            <CardContent className="p-4 space-y-1">
              <span className="text-xs text-slate-400">昨日最高空间板表现</span>
              {high_open_stats?.max_board_info ? (
                <div>
                  <div className="text-base font-bold text-white truncate">
                    {high_open_stats.max_board_info.name} ({high_open_stats.max_board_info.board_height}板)
                  </div>
                  <div className={`text-sm font-bold font-mono ${getPctColor(high_open_stats.max_board_info.open_pct)}`}>
                    开盘: {formatPct(high_open_stats.max_board_info.open_pct)}
                    {high_open_stats.max_board_info.is_one_word && (
                      <span className="ml-1 text-[10px] px-1.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800">
                        一字
                      </span>
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-sm font-mono text-slate-400 pt-1">无连板高标数据</div>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      {/* 模块四：开盘竞价异动池（抢筹与核按钮关注） */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-rose-400" />
            <h2 className="text-lg font-bold text-white tracking-wide">
              开盘竞价异动池（抢筹与分歧关注）
            </h2>
            <span className="text-xs text-slate-400">（开盘幅 &gt; 4% 或 &lt; -4% 异动标的）</span>
          </div>
        </div>

        {(!high_open_stats?.extreme_stocks || high_open_stats.extreme_stocks.length === 0) ? (
          <div className="p-6 rounded-xl bg-slate-900/60 border border-slate-800 text-center text-slate-400 text-sm">
            今日无大幅跳空（&gt;4% 或 &lt;-4%）的极端异动标的，开盘多空相对平稳。
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
            {high_open_stats.extreme_stocks.map((stk: HighTierAuctionStock) => (
              <Card key={stk.symbol} className="bg-slate-900/80 border-slate-800">
                <CardContent className="p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-white truncate">{stk.name}</span>
                    <span className="text-[11px] font-mono text-slate-400">{stk.symbol}</span>
                  </div>

                  <div className="flex items-baseline justify-between pt-1">
                    <span className="text-xs text-slate-400">开盘涨幅</span>
                    <span className={`text-base font-bold font-mono ${getPctColor(stk.open_pct)}`}>
                      {formatPct(stk.open_pct)}
                    </span>
                  </div>

                  <div className="pt-1 border-t border-slate-800">
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded font-medium border ${
                        (stk.open_pct || 0) > 0
                          ? 'bg-rose-950/60 text-rose-300 border-rose-800'
                          : 'bg-emerald-950/60 text-emerald-300 border-emerald-800'
                      }`}
                    >
                      {stk.tag || '竞价异动'}
                    </span>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function getRatioStatusBadge(ratio?: number | null) {
  if (ratio === null || ratio === undefined) {
    return <span className="text-xs text-slate-400 font-mono">--</span>;
  }
  if (ratio >= 1.50) {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-800">
        活跃放量
      </span>
    );
  } else if (ratio >= 1.00) {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-cyan-950/80 text-cyan-300 border border-cyan-800">
        平量承接
      </span>
    );
  } else if (ratio >= 0.60) {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-amber-950/80 text-amber-300 border border-amber-800">
        缩量观望
      </span>
    );
  } else {
    return (
      <span className="px-2 py-0.5 rounded text-xs font-semibold bg-rose-950/80 text-rose-300 border border-rose-800">
        地量避险
      </span>
    );
  }
}
