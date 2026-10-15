'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent } from '@/components/ui/card';
import { api } from '@/lib/api';
import { AuctionReportSummaryItem } from '@/types/report';
import { formatDateWithWeekday, formatAuctionTime } from '@/lib/utils';
import { 
  RefreshCw, 
  Calendar, 
  ArrowRight, 
  Clock, 
  Flame, 
  Sparkles, 
  AlertCircle,
  Activity,
  Layers,
  Info
} from 'lucide-react';

export default function AuctionPage() {
  const [reports, setReports] = useState<AuctionReportSummaryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastActiveDate, setLastActiveDate] = useState<string | null>(null);

  const fetchReports = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getAuctionReports(30, 0);
      setReports(res.items || []);
    } catch (err: any) {
      console.error('获取集合竞价列表失败:', err);
      setError(err.message || '获取集合竞价列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchReports();
  }, []);

  const handleGenerateToday = async () => {
    try {
      setGenerating(true);
      setError(null);
      setNotice(null);
      const res: any = await api.generateAuctionReport();
      if (res && (res.status === 'MARKET_CLOSED' || res.market_status === 'CLOSED')) {
        setNotice(res.message || '数据通信正常：集合竞价物理确认为休市状态，无需生成竞价报告。');
        setLastActiveDate(res.last_active_date || res.data?.last_active_date || null);
      } else {
        await fetchReports();
      }
    } catch (err: any) {
      console.error('生成集合竞价报告失败:', err);
      // 严肃真实错误守卫：网络超时/服务不可用真实报错！
      setError(err.message || '生成今日竞价报告失败');
    } finally {
      setGenerating(false);
    }
  };

  const getEmotionBadgeStyle = (label: string) => {
    if (label.includes('放量高开') || label.includes('偏强')) {
      return 'bg-emerald-950/60 text-emerald-300 border-emerald-800/80';
    } else if (label.includes('平开') || label.includes('中性')) {
      return 'bg-slate-800/80 text-cyan-300 border-cyan-800/80';
    } else if (label.includes('缩量') || label.includes('偏弱')) {
      return 'bg-amber-950/60 text-amber-300 border-amber-800/80';
    } else if (label.includes('极端') || label.includes('分歧') || label.includes('释放')) {
      return 'bg-rose-950/60 text-rose-300 border-rose-800/80';
    } else {
      return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  const formatRatio = (val?: number | null) => {
    if (val === null || val === undefined) return '--';
    return `${val.toFixed(2)}%`;
  };

  const getRatioBadge = (ratio?: number | null) => {
    if (ratio === null || ratio === undefined) {
      return <span className="text-slate-400 font-mono text-xs">--</span>;
    }
    if (ratio >= 1.50) {
      return (
        <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-800">
          活跃放量 ({ratio.toFixed(2)}%)
        </span>
      );
    } else if (ratio >= 1.00) {
      return (
        <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-cyan-950/80 text-cyan-300 border border-cyan-800">
          平量承接 ({ratio.toFixed(2)}%)
        </span>
      );
    } else if (ratio >= 0.60) {
      return (
        <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-950/80 text-amber-300 border border-amber-800">
          缩量观望 ({ratio.toFixed(2)}%)
        </span>
      );
    } else {
      return (
        <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-950/80 text-rose-300 border border-rose-800">
          地量避险 ({ratio.toFixed(2)}%)
        </span>
      );
    }
  };

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-6">
      {/* 头部导航与操作栏 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Clock className="w-7 h-7 text-purple-400" />
            <h1 className="text-2xl md:text-3xl font-bold text-white tracking-tight">
              M3 集合竞价观测归档
            </h1>
          </div>
          <p className="text-sm text-slate-400">
            09:25 开盘微观事实观测 · 竞价量能比值 · 高标开盘溢价 · 零交易信号物理测量
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchReports}
            disabled={loading || generating}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800 hover:bg-slate-750 text-slate-200 text-sm font-medium border border-slate-700 transition disabled:opacity-50"
            title="刷新列表"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
          <button
            onClick={handleGenerateToday}
            disabled={generating || loading}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-semibold shadow-lg shadow-purple-900/30 transition disabled:opacity-50"
            title="生成今日竞价报告"
          >
            <Sparkles className={`w-4 h-4 ${generating ? 'animate-spin' : ''}`} />
            {generating ? '生成中...' : '生成今日竞价报告'}
          </button>
        </div>
      </div>

      {/* 物理确权休市状态通知（通信正常、物理事实确认为休市，不作为错误报警） */}
      {notice && (
        <div className="p-4 rounded-xl bg-cyan-950/40 border border-cyan-800/80 text-cyan-200 text-sm space-y-2">
          <div className="flex items-start gap-3">
            <Info className="w-5 h-5 text-cyan-400 flex-shrink-0 mt-0.5" />
            <div className="space-y-1 flex-1">
              <div className="font-semibold text-cyan-300">集合竞价休市确权通知</div>
              <p className="text-cyan-200/90 leading-relaxed">{notice}</p>
              {lastActiveDate && (
                <div className="pt-1">
                  <Link
                    href={`/auction/${lastActiveDate}`}
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-cyan-400 hover:text-cyan-300 underline underline-offset-4"
                  >
                    查看最近有效交易日（{formatDateWithWeekday(lastActiveDate)}）竞价记录
                    <ArrowRight className="w-3.5 h-3.5" />
                  </Link>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 错误提示 */}
      {error && (
        <div className="p-4 rounded-lg bg-rose-950/40 border border-rose-800/80 text-rose-300 text-sm flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
          <div>
            <div className="font-semibold">操作异常</div>
            <div>{error}</div>
          </div>
        </div>
      )}

      {/* 列表主体 */}
      {loading && reports.length === 0 ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-28 rounded-xl bg-slate-900/60 border border-white/10 animate-pulse"
            />
          ))}
        </div>
      ) : reports.length === 0 ? (
        <Card className="bg-slate-900/60 border-white/10 text-center py-16">
          <CardContent className="space-y-4">
            <Clock className="w-12 h-12 text-slate-600 mx-auto" />
            <div className="text-slate-300 font-medium text-lg">暂无已生成的集合竞价观测报告</div>
            <p className="text-sm text-slate-500 max-w-md mx-auto">
              系统每日 09:25~09:28 汇聚三大指数开盘跳空、两市竞价金额、高标开盘溢价与一字板多空封单。点击右上角即可生成报告。
            </p>
            <button
              onClick={handleGenerateToday}
              disabled={generating}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-semibold shadow-lg shadow-purple-900/30 transition"
            >
              <Sparkles className="w-4 h-4" />
              立即生成首份报告
            </button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {reports.map((item) => (
            <Link key={item.id} href={`/auction/${item.date}`}>
              <Card className="bg-slate-900/70 border-white/10 hover:border-purple-500/50 hover:bg-slate-850/80 transition-all cursor-pointer group shadow-sm">
                <CardContent className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  {/* 左侧：日期与开盘状态 */}
                  <div className="space-y-2">
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-1.5 text-base font-bold text-white group-hover:text-purple-300 transition">
                        <Calendar className="w-4 h-4 text-cyan-400" />
                        <span>{formatDateWithWeekday(item.date)} 集合竞价观测</span>
                      </div>
                      <span
                        className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${getEmotionBadgeStyle(
                          item.emotion_label
                        )}`}
                      >
                        {item.emotion_label}
                      </span>
                    </div>

                    {/* 指标胶囊：两市竞价总额、量能承接比、一字板 */}
                    <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
                      <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-800/80 border border-slate-700/60">
                        <Activity className="w-3.5 h-3.5 text-cyan-400" />
                        <span className="text-slate-400">两市竞价额:</span>
                        <span className="font-mono font-medium text-white">
                          {item.bidding_amount_yi !== null && item.bidding_amount_yi !== undefined
                            ? `${item.bidding_amount_yi.toFixed(1)} 亿元`
                            : '--'}
                        </span>
                      </div>

                      <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-800/80 border border-slate-700/60">
                        <span className="text-slate-400">量能比值:</span>
                        {getRatioBadge(item.bidding_ratio)}
                      </div>

                      <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-800/80 border border-slate-700/60">
                        <Flame className="w-3.5 h-3.5 text-amber-400" />
                        <span className="text-slate-400">一字涨/跌停:</span>
                        <span className="font-mono text-rose-400 font-semibold">{item.one_word_up_count}</span>
                        <span className="text-slate-500">/</span>
                        <span className="font-mono text-emerald-400 font-semibold">{item.one_word_down_count}</span>
                      </div>
                    </div>
                  </div>

                  {/* 右侧：生成时间与进入箭头 */}
                  <div className="flex items-center justify-between md:justify-end gap-4 shrink-0 pt-2 md:pt-0 border-t md:border-t-0 border-white/10">
                    <div className="text-xs text-slate-400">
                      生成时间:{' '}
                      <span className="font-mono text-slate-400">
                        {formatAuctionTime(item.generated_at, item.date)}
                      </span>
                    </div>
                    <div className="inline-flex items-center gap-1 text-sm font-medium text-purple-400 group-hover:translate-x-1 transition-transform">
                      <span>查看看板</span>
                      <ArrowRight className="w-4 h-4" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
