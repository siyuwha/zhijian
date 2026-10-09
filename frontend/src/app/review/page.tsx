'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent } from '@/components/ui/card';
import { api } from '@/lib/api';
import { DailyReviewSummaryItem } from '@/types/report';
import { formatDateWithWeekday } from '@/lib/utils';
import { RefreshCw, Calendar, ArrowRight, ShieldCheck, AlertTriangle, AlertCircle, Activity, HelpCircle, Info, Compass } from 'lucide-react';

export default function ReviewPage() {
  const [reviews, setReviews] = useState<DailyReviewSummaryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchReviews = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getDailyReviews(30, 0);
      setReviews(res.items || []);
    } catch (err: any) {
      console.error('获取复盘列表失败:', err);
      setError(err.message || '获取复盘列表失败');
    } finally {
      setLoading(false);
    }
  };

  const [notice, setNotice] = useState<string | null>(null);
  const [lastActiveDate, setLastActiveDate] = useState<string | null>(null);

  useEffect(() => {
    fetchReviews();
  }, []);

  const handleGenerateToday = async () => {
    try {
      setGenerating(true);
      setError(null);
      setNotice(null);
      const res: any = await api.generateDailyReview();
      if (res && (res.status === 'MARKET_CLOSED' || res.market_status === 'CLOSED')) {
        setNotice(res.message || '数据通信正常：大盘点位与前一交易日收盘一致，物理确认为休市状态。');
        setLastActiveDate(res.last_active_date || res.data?.last_active_date || null);
      } else {
        await fetchReviews();
      }
    } catch (err: any) {
      console.error('生成复盘失败:', err);
      // 严肃真实错误守卫：网络超时/服务不可用真实报错！
      setError(err.message || '生成今日复盘失败');
    } finally {
      setGenerating(false);
    }
  };

  // 物理状态标签颜色映射
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

  // 数据质量标签颜色与图标映射（严格判空与未知质量处理）
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
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-850 text-slate-400 border border-slate-700">
          <HelpCircle className="w-3.5 h-3.5" />
          质量未知 ({quality || 'Unknown'})
        </span>
      );
    }
  };

  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-6">
      {/* 顶部标题与操作栏 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Activity className="w-6 h-6 text-teal-400" />
            <h1 className="text-2xl font-bold tracking-tight text-white">收盘认知复盘</h1>
          </div>
          <p className="text-sm text-slate-400">
            真实多源行情驱动 · 六维正交状态向量 · 物理分级客观表征 · 零填充防伪
          </p>
        </div>

        <button
          onClick={handleGenerateToday}
          disabled={generating}
          className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-teal-600 hover:bg-teal-500 text-white text-sm font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-teal-900/30"
          title="抓取并计算今日收盘客观复盘"
        >
          <RefreshCw className={`w-4 h-4 ${generating ? 'animate-spin' : ''}`} />
          {generating ? '正在抓取计算...' : '一键生成今日复盘'}
        </button>
      </div>

      {/* 升级引导：全景交易员驾驶舱 · Trader Cockpit */}
      <div className="p-4 rounded-xl bg-indigo-950/40 border border-indigo-700/60 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-indigo-200 text-sm">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-indigo-600/20 text-indigo-400 border border-indigo-500/30 shrink-0">
            <Compass className="w-5 h-5" />
          </div>
          <div>
            <div className="font-bold text-slate-100 flex items-center gap-2">
              全景交易员驾驶舱 · Trader Cockpit 已就绪
              <span className="text-[10px] font-mono bg-indigo-900/80 text-indigo-300 border border-indigo-700/60 px-1.5 py-0.5 rounded">
                推荐使用
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              集成三层倒金字塔架构、7问第一屏、操盘内参战报与 09:25 集合竞价波普尔证伪闭环。
            </p>
          </div>
        </div>
        <Link
          href="/cockpit"
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-xs font-bold text-white rounded-lg transition shrink-0 self-start sm:self-center"
        >
          <span>进入交易员驾驶舱</span>
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      {/* 物理确权休市状态通知（通信正常、物理事实确认为休市，不作为错误报警） */}
      {notice && (
        <div className="p-4 rounded-xl bg-cyan-950/40 border border-cyan-800/80 text-cyan-200 text-sm space-y-2">
          <div className="flex items-start gap-3">
            <Info className="w-5 h-5 text-cyan-400 flex-shrink-0 mt-0.5" />
            <div className="space-y-1 flex-1">
              <div className="font-semibold text-cyan-300">市场休市确权通知</div>
              <p className="text-cyan-200/90 leading-relaxed">{notice}</p>
              {lastActiveDate && (
                <div className="pt-1">
                  <Link
                    href={`/review/${lastActiveDate}`}
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-cyan-400 hover:text-cyan-300 underline underline-offset-4"
                  >
                    查看最近有效交易日（{formatDateWithWeekday(lastActiveDate)}）复盘
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
        <div className="p-4 rounded-lg bg-rose-950/50 border border-rose-800/80 text-rose-300 text-sm flex items-center gap-2">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 复盘列表 */}
      {loading ? (
        <div className="py-24 text-center space-y-3">
          <RefreshCw className="w-8 h-8 text-teal-400 animate-spin mx-auto" />
          <p className="text-slate-400 text-sm">正在加载复盘记录...</p>
        </div>
      ) : reviews.length === 0 ? (
        <div className="py-24 text-center space-y-4 rounded-xl border border-dashed border-slate-800 bg-slate-900/40">
          <Activity className="w-12 h-12 text-slate-600 mx-auto" />
          <div className="space-y-1">
            <h3 className="text-base font-medium text-slate-200">暂无复盘历史记录</h3>
            <p className="text-sm text-slate-500 max-w-sm mx-auto">
              点击上方“一键生成今日复盘”按钮，系统将立即从真实数据源抓取并计算今日六维状态。
            </p>
          </div>
          <button
            onClick={handleGenerateToday}
            disabled={generating}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-teal-700 hover:bg-teal-600 text-white transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${generating ? 'animate-spin' : ''}`} />
            立即生成第一期复盘
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="text-xs font-semibold text-slate-400 tracking-wider uppercase px-1">
            历史复盘归档 ({reviews.length})
          </div>

          <div className="grid gap-3">
            {reviews.map((item) => (
              <Link key={item.id} href={`/review/${item.date}`}>
                <Card className="bg-slate-900/90 border-slate-800 hover:border-teal-500/60 transition-all hover:shadow-lg hover:shadow-teal-950/30 cursor-pointer group">
                  <CardContent className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-3">
                        <div className="flex items-center gap-1.5 text-base font-semibold text-white">
                          <Calendar className="w-4 h-4 text-teal-400" />
                          <span>{formatDateWithWeekday(item.date)}</span>
                        </div>

                        {/* 物理状态刻度标签 */}
                        <span
                          className={`px-3 py-0.5 rounded-full text-xs font-semibold border ${getStateBadgeStyle(
                            item.state_label
                          )}`}
                        >
                          物理刻度：{item.state_label}
                        </span>

                        {/* 综合得分或防塌缩标签 */}
                        <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800/80 text-slate-300 border border-slate-700">
                          {item.composite_score !== null
                            ? `综合参考分: ${item.composite_score}`
                            : '综合分: -- (未塌缩/数据降级)'}
                        </span>

                        {/* 数据质量徽标 */}
                        {renderQualityBadge(item.data_quality)}
                      </div>

                      <div className="text-xs text-slate-400">
                        生成时间: {item.generated_at ? new Date(item.generated_at).toLocaleString('zh-CN') : '未知'}
                      </div>
                    </div>

                    <div className="flex items-center gap-1 text-sm font-medium text-teal-400 group-hover:text-teal-300 group-hover:translate-x-1 transition-all self-end sm:self-center">
                      <span>查看认知全景</span>
                      <ArrowRight className="w-4 h-4" />
                    </div>
                  </CardContent>
                </Card>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
