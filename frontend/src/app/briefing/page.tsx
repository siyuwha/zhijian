'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent } from '@/components/ui/card';
import { api } from '@/lib/api';
import { PremarketBriefingSummaryItem, OvernightIndexItem } from '@/types/report';
import { 
  RefreshCw, 
  Calendar, 
  ArrowRight, 
  Globe, 
  Sunrise, 
  Sparkles, 
  AlertCircle 
} from 'lucide-react';

export default function BriefingPage() {
  const [briefings, setBriefings] = useState<PremarketBriefingSummaryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchBriefings = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getPremarketBriefings(30, 0);
      setBriefings(res.items || []);
    } catch (err: any) {
      console.error('获取盘前简报列表失败:', err);
      setError(err.message || '获取盘前简报列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBriefings();
  }, []);

  const handleGenerateToday = async () => {
    try {
      setGenerating(true);
      setError(null);
      await api.generatePremarketBriefing();
      await fetchBriefings();
    } catch (err: any) {
      console.error('生成今日盘前简报失败:', err);
      setError(err.message || '生成今日盘前简报失败');
    } finally {
      setGenerating(false);
    }
  };

  const getStateBadgeStyle = (label: string) => {
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

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-6">
      {/* 头部导航与操作栏 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Sunrise className="w-7 h-7 text-amber-400" />
            <h1 className="text-2xl md:text-3xl font-bold text-white tracking-tight">
              M2 盘前简报归档
            </h1>
          </div>
          <p className="text-sm text-slate-400">
            开盘前客观事实映射系统 · 隔夜外盘跟踪 · 纯净状态继承 · 4 维客观观察推演
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={fetchBriefings}
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
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 text-sm font-semibold shadow-lg shadow-amber-500/20 transition disabled:opacity-50"
          >
            <Sparkles className={`w-4 h-4 ${generating ? 'animate-spin' : ''}`} />
            {generating ? '生成中...' : '生成今日盘前简报'}
          </button>
        </div>
      </div>

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
      {loading && briefings.length === 0 ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-28 rounded-xl bg-slate-900/60 border border-slate-800 animate-pulse"
            />
          ))}
        </div>
      ) : briefings.length === 0 ? (
        <Card className="bg-slate-900/60 border-slate-800 text-center py-16">
          <CardContent className="space-y-4">
            <Globe className="w-12 h-12 text-slate-600 mx-auto" />
            <div className="text-slate-300 font-medium text-lg">暂无已生成的盘前简报</div>
            <p className="text-sm text-slate-500 max-w-md mx-auto">
              系统每日开盘前 08:30~09:15 自动汇聚隔夜外盘、财经快讯及前日纯净状态向量。点击右上角即可立即生成今日简报。
            </p>
            <button
              onClick={handleGenerateToday}
              disabled={generating}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 text-sm font-semibold transition"
            >
              <Sparkles className="w-4 h-4" />
              立即生成首份简报
            </button>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {briefings.map((item) => (
            <Link key={item.id} href={`/briefing/${item.date}`}>
              <Card className="bg-slate-900/70 border-slate-800 hover:border-amber-500/50 hover:bg-slate-850/80 transition-all cursor-pointer group shadow-sm">
                <CardContent className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  {/* 左侧：日期与昨日继承状态 */}
                  <div className="space-y-2">
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-1.5 text-base font-bold text-white group-hover:text-amber-300 transition">
                        <Calendar className="w-4 h-4 text-amber-400" />
                        <span>{item.date} 盘前简报</span>
                      </div>
                      <span
                        className={`px-2.5 py-0.5 rounded-full text-xs font-semibold border ${getStateBadgeStyle(
                          item.yesterday_state_label
                        )}`}
                      >
                        前日状态: {item.yesterday_state_label}
                      </span>
                    </div>

                    {/* 隔夜外盘概览胶囊 */}
                    <div className="flex flex-wrap items-center gap-2 pt-1">
                      <span className="text-xs text-slate-400 flex items-center gap-1">
                        <Globe className="w-3.5 h-3.5 text-slate-400" />
                        隔夜外盘:
                      </span>
                      {item.overnight_summary && item.overnight_summary.length > 0 ? (
                        item.overnight_summary.map((idx: OvernightIndexItem) => (
                          <div
                            key={idx.code || idx.symbol}
                            className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-800/80 border border-slate-700/60 text-xs"
                          >
                            <span className="text-slate-300">{idx.name}</span>
                            <span className={`font-mono font-medium ${getPreviewPctColor(idx.pct_change ?? idx.change_pct)}`}>
                              {formatPct(idx.pct_change ?? idx.change_pct)}
                            </span>
                          </div>
                        ))
                      ) : (
                        <span className="text-xs text-slate-400 font-mono">--</span>
                      )}
                    </div>
                  </div>

                  {/* 右侧：生成时间与进入箭头 */}
                  <div className="flex items-center justify-between md:justify-end gap-4 shrink-0 pt-2 md:pt-0 border-t md:border-t-0 border-slate-800">
                    <div className="text-xs text-slate-400">
                      生成时间:{' '}
                      <span className="font-mono text-slate-400">
                        {item.generated_at ? item.generated_at.replace('T', ' ').slice(0, 19) : '--'}
                      </span>
                    </div>
                    <div className="inline-flex items-center gap-1 text-sm font-medium text-amber-400 group-hover:translate-x-1 transition-transform">
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

function getPreviewPctColor(val?: number | null) {
  if (val === null || val === undefined) return 'text-slate-400';
  if (val > 0) return 'text-rose-400';
  if (val < 0) return 'text-emerald-400';
  return 'text-slate-400';
}
