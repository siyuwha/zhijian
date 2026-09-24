'use client';

import { useEffect, useState, use } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api } from '@/lib/api';
import { PremarketBriefingDetail, OvernightIndexItem, NewsDigestItem, TodayFocusItem } from '@/types/report';
import {
  ArrowLeft,
  RefreshCw,
  Globe,
  Sunrise,
  ShieldAlert,
  Compass,
  FileText,
  Clock,
  TrendingUp,
  TrendingDown,
  Activity,
  Layers,
  Flame,
  AlertTriangle,
  Info,
  ExternalLink,
  ChevronRight
} from 'lucide-react';

export default function BriefingDetailPage({ params }: { params: Promise<{ date: string }> }) {
  const { date } = use(params);
  const [data, setData] = useState<PremarketBriefingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        setError(null);
        const res = await api.getPremarketBriefing(date);
        setData(res);
      } catch (err: any) {
        console.error('获取盘前简报详情失败:', err);
        setError(err.message || '获取盘前简报详情失败');
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [date]);

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
    if (val === null || val === undefined) return 'bg-slate-800/40 border-slate-700/60';
    if (val > 0) return 'bg-rose-950/30 border-rose-900/50';
    if (val < 0) return 'bg-emerald-950/30 border-emerald-900/50';
    return 'bg-slate-800/40 border-slate-700/60';
  };

  const formatNumber = (val?: number | null, decimals = 2) => {
    if (val === null || val === undefined) return '--';
    return val.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  };

  if (loading) {
    return (
      <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-6">
        <div className="flex items-center gap-2 text-slate-400 text-sm">
          <Link href="/briefing" className="hover:text-amber-400 transition flex items-center gap-1">
            <ArrowLeft className="w-4 h-4" /> 返回归档列表
          </Link>
        </div>
        <div className="h-20 rounded-xl bg-slate-900 border border-slate-800 animate-pulse" />
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-28 rounded-xl bg-slate-900 border border-slate-800 animate-pulse" />
          ))}
        </div>
        <div className="h-64 rounded-xl bg-slate-900 border border-slate-800 animate-pulse" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-6">
        <div className="flex items-center gap-2 text-slate-400 text-sm">
          <Link href="/briefing" className="hover:text-amber-400 transition flex items-center gap-1">
            <ArrowLeft className="w-4 h-4" /> 返回归档列表
          </Link>
        </div>
        <Card className="bg-rose-950/30 border-rose-800 text-rose-300 p-8 text-center">
          <AlertTriangle className="w-12 h-12 text-rose-400 mx-auto mb-3" />
          <h2 className="text-xl font-bold mb-2">获取盘前简报失败</h2>
          <p className="text-sm text-slate-400 mb-4">{error || '未找到该日期的盘前简报记录'}</p>
          <Link
            href="/briefing"
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium transition"
          >
            返回列表
          </Link>
        </Card>
      </div>
    );
  }

  const { overnight_summary = [], news_digest = [], yesterday_review_summary, today_focus = [], generated_at } = data;

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-8">
      {/* 顶部导航与操作 */}
      <div className="space-y-4">
        <div className="flex items-center justify-between text-slate-400 text-sm">
          <Link
            href="/briefing"
            className="hover:text-amber-400 transition flex items-center gap-1.5 font-medium"
          >
            <ArrowLeft className="w-4 h-4" /> 返回归档列表
          </Link>
          <div className="flex items-center gap-1 text-xs text-slate-400 font-mono">
            <Clock className="w-3.5 h-3.5" />
            生成时间: {generated_at ? generated_at.replace('T', ' ').slice(0, 19) : '--'}
          </div>
        </div>

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <Sunrise className="w-8 h-8 text-amber-400" />
              <h1 className="text-2xl md:text-3xl font-extrabold text-white tracking-tight">
                M2 盘前全景简报 · {date}
              </h1>
            </div>
            <p className="text-xs md:text-sm text-slate-400">
              汇聚隔夜外盘波动 · 继承前日 M1.4 状态向量 · 4 维客观观察方向推演
            </p>
          </div>
        </div>

        {/* 免责声明提示条 */}
        <div className="p-3.5 rounded-lg bg-amber-950/20 border border-amber-900/40 text-amber-300 text-xs flex items-start gap-2.5">
          <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="leading-relaxed">
            <span className="font-semibold text-amber-200">【客观事实映射与观察提示】</span>
            本简报所列隔夜外盘、财经快讯、昨日状态与早盘 4 维推演均为纯客观数据统计与物理观察维度提示，严禁作为买卖操作指令。市场有风险，投资需谨慎。
          </div>
        </div>
      </div>

      {/* 模块一：隔夜外盘全景网格 */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Globe className="w-5 h-5 text-teal-400" />
            <h2 className="text-lg font-bold text-white tracking-wide">隔夜外盘全景</h2>
            <span className="text-xs text-slate-400 font-mono">
              ({overnight_summary.length} 项标的)
            </span>
          </div>
          <span className="text-xs text-slate-400">源自新浪财经官方接口清洗</span>
        </div>

        {overnight_summary.length === 0 ? (
          <div className="p-6 rounded-xl bg-slate-900/60 border border-slate-800 text-center text-slate-400 text-sm">
            暂无隔夜外盘数据
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
            {overnight_summary.map((idx: OvernightIndexItem) => {
              const pct = idx.pct_change ?? idx.change_pct;
              return (
                <Card
                  key={idx.code || idx.symbol}
                  className={`bg-slate-900/80 border transition-all ${getPctBg(pct)}`}
                >
                  <CardContent className="p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-slate-200 truncate" title={idx.name}>
                        {idx.name}
                      </span>
                      <span className="text-[10px] text-slate-400 font-mono uppercase">
                        {idx.code || idx.symbol}
                      </span>
                    </div>

                    <div className="flex items-baseline justify-between pt-1">
                      <div className="text-lg font-bold font-mono text-white">
                        {idx.price !== null && idx.price !== undefined ? formatNumber(idx.price, 2) : '--'}
                      </div>
                      <div className={`text-sm font-bold font-mono ${getPctColor(pct)}`}>
                        {formatPct(pct)}
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-800/80">
                      <span>点位变动</span>
                      <span className={`font-mono ${getPctColor(idx.change_val)}`}>
                        {idx.change_val !== null && idx.change_val !== undefined
                          ? (idx.change_val > 0 ? `+${idx.change_val.toFixed(2)}` : idx.change_val.toFixed(2))
                          : '--'}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      {/* 模块二：前日 M1.4 状态向量继承看板 */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-5 h-5 text-indigo-400" />
            <h2 className="text-lg font-bold text-white tracking-wide">
              前日 M1.4 纯净状态向量继承
            </h2>
            <span className="text-xs text-slate-400">（物理事实承接 · 防标量塌缩）</span>
          </div>
          {yesterday_review_summary?.date && (
            <Link
              href={`/review/${yesterday_review_summary.date}`}
              className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-medium transition"
            >
              查阅 {yesterday_review_summary.date} 收盘全景复盘
              <ExternalLink className="w-3.5 h-3.5" />
            </Link>
          )}
        </div>

        {!yesterday_review_summary ? (
          <div className="p-6 rounded-xl bg-slate-900/60 border border-slate-800 text-center text-slate-400 text-sm">
            未关联到前一交易日复盘数据
          </div>
        ) : (
          <Card className="bg-slate-900/70 border-slate-800">
            <CardContent className="p-5 md:p-6 space-y-6">
              {/* 核心指标状态摘要 */}
              <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-lg bg-slate-850/80 border border-slate-800">
                <div className="flex items-center gap-3">
                  <div className="text-xs text-slate-400">前日物理状态:</div>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-bold border ${getStateBadgeStyle(
                      yesterday_review_summary.state_label
                    )}`}
                  >
                    {yesterday_review_summary.state_label || '未定义'}
                  </span>
                </div>

                <div className="flex items-center gap-6 text-sm">
                  <div>
                    <span className="text-xs text-slate-400 mr-2">综合得分:</span>
                    <span className="font-mono font-bold text-white">
                      {yesterday_review_summary.composite_score !== null &&
                      yesterday_review_summary.composite_score !== undefined
                        ? yesterday_review_summary.composite_score.toFixed(1)
                        : '--'}
                    </span>
                  </div>
                  <div>
                    <span className="text-xs text-slate-400 mr-2">全市场成交额:</span>
                    <span className="font-mono font-bold text-teal-300">
                      {yesterday_review_summary.total_amount !== null &&
                      yesterday_review_summary.total_amount !== undefined
                        ? `${yesterday_review_summary.total_amount.toFixed(0)} 亿元`
                        : '--'}
                    </span>
                  </div>
                </div>
              </div>

              {/* 事实指标网格：全市场广度 + D3 投机博弈事实 */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* 左列：全市场广度 */}
                <div className="p-4 rounded-lg bg-slate-900 border border-slate-800 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                    <span className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                      <Activity className="w-3.5 h-3.5 text-cyan-400" />
                      全市场多空广度 (Breadth)
                    </span>
                    <span className="text-[11px] text-slate-400">全市场沪深北</span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center pt-1">
                    <div className="p-2 rounded bg-slate-850 border border-slate-800">
                      <div className="text-[11px] text-slate-400 mb-0.5">上涨家数</div>
                      <div className="text-sm font-mono font-bold text-rose-400">
                        {yesterday_review_summary.breadth?.up_count !== null &&
                        yesterday_review_summary.breadth?.up_count !== undefined
                          ? `${yesterday_review_summary.breadth.up_count} 家`
                          : '--'}
                      </div>
                    </div>
                    <div className="p-2 rounded bg-slate-850 border border-slate-800">
                      <div className="text-[11px] text-slate-400 mb-0.5">下跌家数</div>
                      <div className="text-sm font-mono font-bold text-emerald-400">
                        {yesterday_review_summary.breadth?.down_count !== null &&
                        yesterday_review_summary.breadth?.down_count !== undefined
                          ? `${yesterday_review_summary.breadth.down_count} 家`
                          : '--'}
                      </div>
                    </div>
                    <div className="p-2 rounded bg-slate-850 border border-slate-800">
                      <div className="text-[11px] text-slate-400 mb-0.5">涨跌比值</div>
                      <div className="text-sm font-mono font-bold text-white">
                        {yesterday_review_summary.breadth?.up_down_ratio !== null &&
                        yesterday_review_summary.breadth?.up_down_ratio !== undefined
                          ? yesterday_review_summary.breadth.up_down_ratio.toFixed(2)
                          : '--'}
                      </div>
                    </div>
                  </div>
                </div>

                {/* 右列：D3 投机博弈事实 (Sub-A + Sub-B) */}
                <div className="p-4 rounded-lg bg-slate-900 border border-slate-800 space-y-3">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                    <span className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                      <Flame className="w-3.5 h-3.5 text-amber-400" />
                      D3 投机博弈双子域事实 (Speculative & Extremes)
                    </span>
                    <span className="text-[10px] text-amber-400/80 font-mono bg-amber-950/40 px-1.5 py-0.5 rounded border border-amber-900/60">
                      核心分: -- (防塌缩)
                    </span>
                  </div>

                  <div className="space-y-2 pt-1">
                    {/* Sub-A 投机结构 */}
                    <div className="flex items-center justify-between text-xs p-2 rounded bg-slate-850 border border-slate-800">
                      <span className="text-slate-300 font-medium">Sub-A 投机结构:</span>
                      <div className="flex items-center gap-3 font-mono">
                        <span className="text-slate-400">
                          最高空间:{' '}
                          <b className="text-amber-400">
                            {yesterday_review_summary.sub_a_structure?.max_board_height !== null &&
                            yesterday_review_summary.sub_a_structure?.max_board_height !== undefined
                              ? `${yesterday_review_summary.sub_a_structure.max_board_height} 板`
                              : '--'}
                          </b>
                        </span>
                        <span className="text-slate-400">
                          晋级率:{' '}
                          <b className="text-slate-200">
                            {yesterday_review_summary.sub_a_structure?.promotion_rate !== null &&
                            yesterday_review_summary.sub_a_structure?.promotion_rate !== undefined
                              ? `${yesterday_review_summary.sub_a_structure.promotion_rate.toFixed(1)}%`
                              : '--'}
                          </b>
                        </span>
                      </div>
                    </div>

                    {/* Sub-B 尾部极端 */}
                    <div className="flex items-center justify-between text-xs p-2 rounded bg-slate-850 border border-slate-800">
                      <span className="text-slate-300 font-medium">Sub-B 尾部极端:</span>
                      <div className="flex items-center gap-3 font-mono">
                        <span className="text-slate-400">
                          涨停/跌停:{' '}
                          <b className="text-rose-400">
                            {yesterday_review_summary.sub_b_extremes?.limit_up_count ?? '--'}
                          </b>
                          /
                          <b className="text-emerald-400">
                            {yesterday_review_summary.sub_b_extremes?.limit_down_count ?? '--'}
                          </b>
                        </span>
                        <span className="text-slate-400">
                          真实炸板率:{' '}
                          <b className="text-slate-200">
                            {yesterday_review_summary.sub_b_extremes?.broken_limit_ratio !== null &&
                            yesterday_review_summary.sub_b_extremes?.broken_limit_ratio !== undefined
                              ? `${yesterday_review_summary.sub_b_extremes.broken_limit_ratio.toFixed(1)}%`
                              : '--'}
                          </b>
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* 叙事段落 */}
              {yesterday_review_summary.narrative && (
                <div className="p-3.5 rounded-lg bg-slate-950/60 border border-slate-800 text-xs text-slate-300 leading-relaxed">
                  <span className="font-semibold text-slate-100 mr-2">【前日复盘事实述评】</span>
                  {yesterday_review_summary.narrative}
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </section>

      {/* 模块三：早盘 4 维客观观察方向推演看板 */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Compass className="w-5 h-5 text-amber-400" />
            <h2 className="text-lg font-bold text-white tracking-wide">
              早盘 4 维客观观察方向推演
            </h2>
            <span className="text-xs text-slate-400">（物理观察维度 · 严禁主观买卖指令）</span>
          </div>
          <span className="text-xs px-2.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300">
            开盘竞价客观核验
          </span>
        </div>

        {today_focus.length === 0 ? (
          <div className="p-6 rounded-xl bg-slate-900/60 border border-slate-800 text-center text-slate-400 text-sm">
            暂无今日关注推演
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {today_focus.map((focus: TodayFocusItem, idx: number) => {
              const borderStyles = [
                'hover:border-teal-500/50',
                'hover:border-amber-500/50',
                'hover:border-rose-500/50',
                'hover:border-indigo-500/50',
              ];
              const tagColors = [
                'bg-teal-950/60 text-teal-300 border-teal-800',
                'bg-amber-950/60 text-amber-300 border-amber-800',
                'bg-rose-950/60 text-rose-300 border-rose-800',
                'bg-indigo-950/60 text-indigo-300 border-indigo-800',
              ];

              return (
                <Card
                  key={idx}
                  className={`bg-slate-900/80 border-slate-800 ${borderStyles[idx % 4]} transition-all flex flex-col justify-between`}
                >
                  <CardHeader className="pb-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span
                        className={`text-xs px-2.5 py-0.5 rounded-full font-semibold border ${tagColors[idx % 4]}`}
                      >
                        {focus.dimension}
                      </span>
                      <span className="text-[11px] text-slate-400">维度 {idx + 1}</span>
                    </div>
                    <CardTitle className="text-base text-slate-100 font-bold leading-snug">
                      {focus.title}
                    </CardTitle>
                  </CardHeader>

                  <CardContent className="space-y-3 pt-0">
                    {/* 观察核心 */}
                    <div className="p-2.5 rounded bg-slate-850/90 border border-slate-800 text-xs">
                      <span className="text-slate-400 font-medium mr-1.5">核心观察点:</span>
                      <span className="text-slate-200 font-semibold">{focus.observation_point}</span>
                    </div>

                    {/* 客观推演 */}
                    <p className="text-xs text-slate-300 leading-relaxed">
                      {focus.analysis}
                    </p>

                    {/* 免责声明提示 */}
                    <div className="flex items-center gap-1.5 text-[11px] text-slate-400 pt-2 border-t border-slate-800/80">
                      <Info className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span>{focus.disclaimer}</span>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      {/* 模块四：盘前最新财经快讯 (Top 10) */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-sky-400" />
            <h2 className="text-lg font-bold text-white tracking-wide">盘前财经快讯</h2>
            <span className="text-xs text-slate-400 font-mono">
              (最新 Top {news_digest.length})
            </span>
          </div>
          <span className="text-xs text-slate-400">实时源汇聚 · 盘前宏观与行业动态</span>
        </div>

        {news_digest.length === 0 ? (
          <div className="p-6 rounded-xl bg-slate-900/60 border border-slate-800 text-center text-slate-400 text-sm">
            暂无早盘快讯记录
          </div>
        ) : (
          <div className="space-y-2.5">
            {news_digest.map((news: NewsDigestItem, idx: number) => (
              <div
                key={idx}
                className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 hover:border-slate-700 hover:bg-slate-850/60 transition space-y-1.5"
              >
                <div className="flex items-center justify-between gap-3 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-teal-400/90 font-medium">
                      {news.time || news.publish_time || '--:--'}
                    </span>
                    <span className="px-1.5 py-0.2 rounded bg-slate-800 text-slate-400 text-[10px] uppercase">
                      {news.source || '快讯'}
                    </span>
                  </div>
                  {news.url && (
                    <a
                      href={news.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-slate-400 hover:text-slate-200 transition"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </a>
                  )}
                </div>

                <div className="text-sm font-semibold text-slate-100 leading-snug">
                  {news.title}
                </div>

                {news.brief && (
                  <p className="text-xs text-slate-400 line-clamp-2 leading-relaxed">
                    {news.brief}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
