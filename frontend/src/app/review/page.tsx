'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Card, CardContent } from '@/components/ui/card';
import { api } from '@/lib/api';
import { DailyReviewSummaryItem, DailyReviewDetail } from '@/types/report';
import { formatDateWithWeekday } from '@/lib/utils';
import { 
  RefreshCw, Calendar, ArrowRight, ShieldCheck, AlertTriangle, AlertCircle, 
  Activity, HelpCircle, Info, Compass, ArrowLeft 
} from 'lucide-react';
import { ZhijianReviewCockpit } from '@/components/cockpit/ZhijianReviewCockpit';

export default function ReviewPage() {
  const [reviews, setReviews] = useState<DailyReviewSummaryItem[]>([]);
  const [activeDate, setActiveDate] = useState<string | null>(null);
  const [currentDetail, setCurrentDetail] = useState<DailyReviewDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [lastActiveDate, setLastActiveDate] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'cockpit' | 'archive'>('cockpit');

  const loadDateDetail = async (dateStr: string) => {
    try {
      setDetailLoading(true);
      setError(null);
      const detail = await api.getDailyReview(dateStr);
      setCurrentDetail(detail);
      setActiveDate(dateStr);
    } catch (err: any) {
      console.error(`获取 ${dateStr} 复盘详情失败:`, err);
      setError(err.message || '获取复盘详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const fetchInitialData = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getDailyReviews(30, 0);
      const items = res.items || [];
      setReviews(items);

      if (items.length > 0) {
        const latestDate = items[0].date;
        setActiveDate(latestDate);
        const detail = await api.getDailyReview(latestDate);
        setCurrentDetail(detail);
      }
    } catch (err: any) {
      console.error('获取复盘数据失败:', err);
      setError(err.message || '获取复盘数据失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInitialData();
  }, []);

  const handleSelectDate = (dateStr: string) => {
    loadDateDetail(dateStr);
  };

  // 物理状态标签颜色映射
  const getStateBadgeStyle = (label: string) => {
    switch (label) {
      case '极弱收缩':
        return 'bg-emerald-950/60 text-emerald-300 border-emerald-800/80';
      case '偏弱整理':
        return 'bg-amber-950/60 text-amber-300 border-amber-800/80';
      case '平稳中性':
        return 'bg-slate-800/80 text-cyan-300 border-cyan-800/80';
      case '偏强扩散':
        return 'bg-rose-950/60 text-rose-300 border-rose-800/80';
      case '极度亢奋':
        return 'bg-purple-950/60 text-purple-300 border-purple-800/80';
      default:
        return 'bg-slate-800 text-slate-300 border-slate-700';
    }
  };

  // 数据质量标签颜色与图标映射
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

  if (loading) {
    return (
      <div className="min-h-screen bg-[#07090E] flex flex-col items-center justify-center space-y-4">
        <div className="relative">
          <div className="w-12 h-12 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 animate-pulse">
            <Compass className="w-6 h-6 animate-spin" />
          </div>
        </div>
        <div className="text-center space-y-1">
          <h2 className="text-base font-bold text-white tracking-wide">知见 · A股全景深度复盘工作台</h2>
          <p className="text-xs text-slate-400 font-mono">正在装载最新交易日客观事实与认知推演数据...</p>
        </div>
      </div>
    );
  }

  // 默认：直接进入最新深度的复盘工作台 (满足用户“复盘页面进去就是深度”的核心诉求)
  if (viewMode === 'cockpit' && currentDetail && activeDate) {
    return (
      <div className="relative">
        {detailLoading && (
          <div className="fixed top-14 left-1/2 transform -translate-x-1/2 z-50 bg-[#0B0E17]/95 border border-amber-500/40 text-amber-300 px-4 py-2 rounded-xl text-xs shadow-2xl backdrop-blur-xl flex items-center gap-2">
            <RefreshCw className="w-3.5 h-3.5 animate-spin text-amber-400" />
            <span>正在载入 {formatDateWithWeekday(activeDate)} 深度复盘...</span>
          </div>
        )}
        <ZhijianReviewCockpit
          date={activeDate}
          dailyReview={currentDetail}
          transcendentData={(currentDetail as any)?.transcendent_review || (currentDetail as any)?.report_content?.transcendent_review}
          historicalDates={reviews}
          onSelectDate={handleSelectDate}
          onToggleArchiveView={() => setViewMode('archive')}
        />
      </div>
    );
  }

  // 历史复盘归档模式
  return (
    <div className="p-4 md:p-8 max-w-6xl mx-auto space-y-6">
      {/* 顶部标题与操作栏 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/10 pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Activity className="w-6 h-6 text-amber-400" />
            <h1 className="text-2xl font-bold tracking-tight text-white">收盘认知复盘 · 历史归档</h1>
          </div>
          <p className="text-sm text-slate-400">
            真实多源行情驱动 · 六维正交状态向量 · 物理分级客观表征 · 零填充防伪
          </p>
        </div>

        <div className="flex items-center gap-3">
          {activeDate && (
            <button
              onClick={() => setViewMode('cockpit')}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-gradient-to-r from-amber-600 to-amber-700 hover:from-amber-500 hover:to-amber-600 text-black font-bold text-xs transition shadow-lg shadow-amber-950/40"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>返回深度复盘工作台 ({activeDate})</span>
            </button>
          )}

          <div className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl bg-emerald-950/40 border border-emerald-800/40 text-emerald-400 text-xs font-mono">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span>交易日 16:30 自动结算归档</span>
          </div>
        </div>
      </div>

      {/* 核心亮点：快速进入知见深度复盘 */}
      <div className="p-5 rounded-2xl bg-gradient-to-r from-[#0C1222] via-[#0E172E] to-[#0A0F1D] border border-amber-500/40 shadow-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-4 text-white">
        <div className="flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 shrink-0">
            <Compass className="w-5 h-5" />
          </div>
          <div>
            <div className="font-extrabold text-base flex items-center gap-2">
              <span>知见 · A股全景深度复盘工作台</span>
              <span className="text-[10px] font-mono bg-amber-950 text-amber-300 border border-amber-700/60 px-2 py-0.5 rounded-full font-bold">
                11章全景研报
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1">
              杂志级排版美学 · 连板天梯图谱 · 多空双向热力条 · 6类机制样本 · 伴随证据链与 AI 认知推演助手
            </p>
          </div>
        </div>
        <button
          onClick={() => {
            if (reviews.length > 0) {
              handleSelectDate(reviews[0].date);
            }
            setViewMode('cockpit');
          }}
          className="inline-flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-amber-600 to-amber-700 hover:from-amber-500 hover:to-amber-600 text-xs font-bold text-black rounded-xl shadow-lg shadow-amber-600/30 transition shrink-0 self-start sm:self-center active:scale-95"
        >
          <span>进入最新深度复盘 ({reviews[0]?.date || '今日'})</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>

      {/* 物理确权休市状态通知 */}
      {notice && (
        <div className="p-4 rounded-xl bg-cyan-950/40 border border-cyan-800/80 text-cyan-200 text-sm space-y-2">
          <div className="flex items-start gap-3">
            <Info className="w-5 h-5 text-cyan-400 flex-shrink-0 mt-0.5" />
            <div className="space-y-1 flex-1">
              <div className="font-semibold text-cyan-300">市场休市确权通知</div>
              <p className="text-cyan-200/90 leading-relaxed">{notice}</p>
              {lastActiveDate && (
                <div className="pt-1">
                  <button
                    onClick={() => {
                      handleSelectDate(lastActiveDate);
                      setViewMode('cockpit');
                    }}
                    className="inline-flex items-center gap-1.5 text-xs font-medium text-cyan-400 hover:text-cyan-300 underline underline-offset-4"
                  >
                    查看最近有效交易日（{formatDateWithWeekday(lastActiveDate)}）深度复盘
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
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

      {/* 历史复盘列表 */}
      {reviews.length === 0 ? (
        <div className="py-24 text-center space-y-4 rounded-xl border border-dashed border-white/10 bg-slate-900/40">
          <Activity className="w-12 h-12 text-slate-600 mx-auto" />
          <div className="space-y-1">
            <h3 className="text-base font-medium text-slate-200">暂无复盘历史记录</h3>
            <p className="text-sm text-slate-500 max-w-sm mx-auto">
              系统将在交易日 16:30 自动抓取收盘行情、推演六维认知状态并持久化归档。
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="text-xs font-semibold text-slate-400 tracking-wider uppercase px-1">
            历史复盘归档 ({reviews.length})
          </div>

          <div className="grid gap-3">
            {reviews.map((item) => (
              <div
                key={item.id}
                onClick={() => {
                  handleSelectDate(item.date);
                  setViewMode('cockpit');
                }}
                className="cursor-pointer"
              >
                <Card className="bg-slate-900/90 border-white/10 hover:border-amber-500/60 transition-all hover:shadow-lg hover:shadow-amber-950/30 group">
                  <CardContent className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-3">
                        <div className="flex items-center gap-1.5 text-base font-semibold text-white">
                          <Calendar className="w-4 h-4 text-cyan-400" />
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

                    <div className="flex items-center gap-1 text-sm font-medium text-amber-400 group-hover:text-amber-300 group-hover:translate-x-1 transition-all self-end sm:self-center">
                      <span>查看全景深度</span>
                      <ArrowRight className="w-4 h-4" />
                    </div>
                  </CardContent>
                </Card>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
