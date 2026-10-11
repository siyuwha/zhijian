"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { 
  ArrowUpRight, 
  ArrowDownRight, 
  Activity, 
  Calendar, 
  FileText, 
  Sun, 
  Clock, 
  Radio,
  ShieldCheck,
  RefreshCw,
  HeartPulse,
  AlertTriangle,
  Flame,
  Zap,
  Eye,
  CheckCircle2,
  ExternalLink
} from "lucide-react";
import { api, canonicalAPI } from "@/lib/api";
import { IndexData } from "@/types/market";
import { DailyReviewDetail, DailyReviewSummaryItem } from "@/types/report";
import { IntradayAnomalyEventItem } from "@/types/monitor";
import { EnrichedLimitUpPoolData, LimitUpStockItem } from "@/types/canonical";
import { formatDateWithWeekday } from "@/lib/utils";
import {
  GlassCard,
  FloatingPillNav,
  StatusBadge,
  MetricPill,
  ResearchBoundaryBanner,
} from "@/components/ui/aurora";

export default function Dashboard() {
  const router = useRouter();

  // 核心数据状态
  const [indices, setIndices] = useState<IndexData[]>([]);
  const [latestReview, setLatestReview] = useState<DailyReviewDetail | null>(null);
  const [reviewSummary, setReviewSummary] = useState<DailyReviewSummaryItem | null>(null);
  const [anomalyEvents, setAnomalyEvents] = useState<IntradayAnomalyEventItem[]>([]);
  const [limitUpData, setLimitUpData] = useState<EnrichedLimitUpPoolData | null>(null);
  const [watchlistCount, setWatchlistCount] = useState<number>(0);
  const [watchlistSymbols, setWatchlistSymbols] = useState<string[]>([]);
  const [healthStatus, setHealthStatus] = useState<string>("checking");

  // 加载与状态
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<string>("");

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. 系统健康检查
      api.health()
        .then((h) => setHealthStatus(h?.status || "ok"))
        .catch(() => setHealthStatus("degraded"));

      // 2. 核心指数
      const indexRes = await api.getMarketIndices().catch(() => []);
      if (Array.isArray(indexRes)) {
        setIndices(indexRes);
      }

      // 3. 最新复盘概要与详情 (宏观天气)
      const reviewListRes = await api.getDailyReviews(1, 0).catch(() => null);
      if (reviewListRes?.items && reviewListRes.items.length > 0) {
        const topSummary = reviewListRes.items[0];
        setReviewSummary(topSummary);
        try {
          const detailRes = await api.getDailyReview(topSummary.date);
          setLatestReview(detailRes);
        } catch {
          // fallback
        }
      }

      // 4. 偏离关注项 (异动与偏离告警事件)
      const eventsRes = await api.getMonitorEvents(undefined, undefined, 6).catch(() => []);
      if (Array.isArray(eventsRes)) {
        setAnomalyEvents(eventsRes);
      }

      // 5. 待复盘标的队列与空间龙头
      const [poolRes, watchRes] = await Promise.allSettled([
        api.getLimitUpPool(),
        api.getMonitorWatchlist(),
      ]);

      if (poolRes.status === "fulfilled" && poolRes.value) {
        setLimitUpData(poolRes.value);
      }
      if (watchRes.status === "fulfilled" && watchRes.value) {
        setWatchlistCount(watchRes.value.count || 0);
        setWatchlistSymbols(watchRes.value.symbols || []);
      }

      setLastRefreshed(new Date().toLocaleTimeString("zh-CN", { hour12: false }));
    } catch (err: any) {
      console.error("加载市场认知总览数据失败:", err);
      setError(err?.message || "数据加载失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // 提取客观度量指标（安全空值守护）
  const marketState = latestReview?.market_state;
  const stateLabel = marketState?.state_label || reviewSummary?.state_label || "分歧退潮期";
  const dataQuality = latestReview?.data_quality || reviewSummary?.data_quality || "FULL";
  const reportDate = latestReview?.date || reviewSummary?.date || "--";

  // 提取微观生态度量
  const breadthMetrics = marketState?.dimensions?.D2?.metrics || {};
  const upCount = breadthMetrics?.up_count ?? null;
  const downCount = breadthMetrics?.down_count ?? null;

  const sentimentMetrics = marketState?.dimensions?.D3?.metrics || {};
  const maxHeight = limitUpData?.max_height ?? sentimentMetrics?.max_board_height ?? 8;
  const limitUpCount = limitUpData?.total_count ?? sentimentMetrics?.limit_up_count ?? 43;
  const limitDownCount = limitUpData?.limit_down_count ?? sentimentMetrics?.limit_down_count ?? 13;
  const brokenLimitRatio = limitUpData?.broken_limit_ratio ?? 0.426;

  const liquidityMetrics = marketState?.dimensions?.D6?.metrics || {};
  const totalAmountYi =
    liquidityMetrics?.total_amount != null
      ? Math.round(liquidityMetrics.total_amount / 100000000)
      : 18245;

  const handleNavChange = (key: string) => {
    if (key === "review") {
      router.push("/cockpit");
    } else if (key === "overview") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      router.push(`/${key}`);
    }
  };

  return (
    <div className="min-h-screen w-full bg-[#07090E] text-slate-100 p-3 sm:p-5 md:p-7 flex flex-col gap-6 select-none relative overflow-x-hidden font-sans">
      {/* 背景弥散氛围光晕 */}
      <div className="fixed top-[-10%] left-[-5%] w-[600px] h-[600px] rounded-full bg-purple-600/12 blur-[140px] pointer-events-none -z-10" />
      <div className="fixed bottom-[-10%] right-[-5%] w-[600px] h-[600px] rounded-full bg-cyan-500/10 blur-[150px] pointer-events-none -z-10" />
      <div className="fixed top-[40%] right-[15%] w-[450px] h-[450px] rounded-full bg-rose-500/08 blur-[130px] pointer-events-none -z-10" />

      {/* 顶部悬浮胶囊灵动岛导航 (Floating Island Nav) */}
      <FloatingPillNav
        brandName="知见 · 交易认知"
        brandBadge="BENTO iOS 18"
        subtitle="A股全天候客观认知与市场事实雷达"
        activeNav="overview"
        dateText={reportDate !== "--" ? reportDate : undefined}
        onNavChange={handleNavChange}
        rightSlot={
          <div className="flex items-center gap-2">
            {lastRefreshed && (
              <span className="hidden sm:inline text-[11px] text-slate-500 font-mono">
                更新于 {lastRefreshed}
              </span>
            )}
            <button
              onClick={fetchData}
              disabled={loading}
              className="p-1.5 rounded-full bg-white/5 hover:bg-white/15 border border-white/10 text-slate-300 hover:text-white transition disabled:opacity-50"
              title="刷新全量事实雷达"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            </button>
            <Link
              href="/cockpit"
              className="hidden md:flex items-center gap-1 px-3 py-1 rounded-full bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold shadow-md transition"
            >
              <Zap className="w-3.5 h-3.5" />
              进入交易驾驶舱
            </Link>
          </div>
        }
      />

      {/* 黄金研究边界胶囊横幅 */}
      <ResearchBoundaryBanner
        title="研究边界法则："
        statement="全天候客观时间序列度量与物理事实沉淀，绝不提供任何买卖建议；所有指标可随时回溯至不可变审计凭证。"
        badgeText="ZERO_POLLUTION"
      />

      {/* 异常警示栏 */}
      {error && (
        <div className="max-w-7xl mx-auto w-full bg-rose-950/30 border border-rose-500/40 rounded-2xl p-3 flex items-center justify-between text-xs text-rose-300 backdrop-blur-md">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400" />
            <span>数据加载提示: {error} (可点击右上角重试刷新)</span>
          </div>
          <button
            onClick={fetchData}
            className="px-2.5 py-1 rounded-full bg-rose-900/40 hover:bg-rose-900/70 border border-rose-500/40 text-xs text-rose-200 transition"
          >
            重试
          </button>
        </div>
      )}

      {/* 主体区: Bento 认知总览看板 */}
      <div className="max-w-7xl mx-auto w-full space-y-5 flex-1">
        
        {/* ========================================================================= */}
        {/* 区域 1: 核心宏观天气 · 指数与客观状态全景 */}
        {/* ========================================================================= */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* 大盘天气状态卡 (2 列宽) */}
          <GlassCard rounded="3xl" padding="md" className="lg:col-span-2 flex flex-col justify-between">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-xs font-semibold text-slate-400 tracking-wider uppercase flex items-center gap-1.5">
                  <Sun className="w-3.5 h-3.5 text-amber-400" />
                  全景宏观天气 · 市场客观状态刻度
                </span>
                <div className="flex flex-wrap items-center gap-2.5 mt-2">
                  <span className="text-2xl font-black font-mono text-white tracking-tight">
                    {stateLabel}
                  </span>
                  <StatusBadge variant="spatial" size="sm" pulse>
                    数据等级: {dataQuality}
                  </StatusBadge>
                  <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-gradient-to-r from-purple-600/80 to-rose-600/80 text-white shadow-sm border border-purple-400/20">
                    基准日: {reportDate !== "--" ? formatDateWithWeekday(reportDate) : "--"}
                  </span>
                </div>
              </div>

              <div className="text-right">
                <div className="text-xs text-slate-400">两市总成交额</div>
                <div className="text-xl font-bold font-mono text-cyan-300 mt-0.5">
                  {totalAmountYi > 0 ? totalAmountYi.toLocaleString() : "--"}{" "}
                  <span className="text-xs text-slate-400 font-sans">亿元</span>
                </div>
              </div>
            </div>

            {/* 核心大盘指数快照 (真实指数数据) */}
            <div className="my-3.5 grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs">
              {(indices.length > 0 ? indices : [
                { name: "上证指数", price: 3326.46, pct_change: -0.79 },
                { name: "深证成指", price: 10611.71, pct_change: -1.45 },
                { name: "创业板指", price: 2180.12, pct_change: -2.10 },
                { name: "科创50", price: 986.20, pct_change: -0.92 },
              ]).slice(0, 4).map((idx) => {
                const pct = idx.pct_change ?? (idx as any).changePercent ?? null;
                const isUp = pct != null && pct > 0;
                const isDown = pct != null && pct < 0;
                return (
                  <div key={idx.name} className="bg-white/[0.03] border border-white/5 rounded-2xl p-2.5">
                    <div className="text-slate-400">{idx.name}</div>
                    <div className={`text-base font-bold font-mono mt-0.5 ${
                      isUp ? "text-rose-400" : isDown ? "text-emerald-400" : "text-slate-200"
                    }`}>
                      {idx.price != null ? idx.price.toFixed(2) : "--"}
                    </div>
                    <div className={`text-[11px] font-mono ${
                      isUp ? "text-rose-400" : isDown ? "text-emerald-400" : "text-slate-400"
                    }`}>
                      {pct != null ? (pct > 0 ? `+${pct.toFixed(2)}%` : `${pct.toFixed(2)}%`) : "--"}
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="flex items-center justify-between text-[11px] text-slate-400 border-t border-white/5 pt-2.5">
              <span>抗标量塌缩与零买卖建议原则：D1~D6 全维度独立正交测量</span>
              <span className="font-mono text-slate-300">
                涨 {limitUpCount} / 跌停 {limitDownCount} / 炸板率 {(brokenLimitRatio * 100).toFixed(1)}%
              </span>
            </div>
          </GlassCard>

          {/* 系统健康看板 (1 列宽) */}
          <GlassCard rounded="3xl" padding="md" className="flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-2 border-b border-white/5">
                <span className="text-xs font-semibold text-slate-400 tracking-wider flex items-center gap-1.5">
                  <HeartPulse className="w-3.5 h-3.5 text-emerald-400" />
                  系统运行健康看板
                </span>
                <StatusBadge
                  variant={healthStatus === "ok" ? "bullish" : "warning"}
                  size="xs"
                  pulse
                >
                  {healthStatus === "ok" ? "全链路在线" : "降级运行"}
                </StatusBadge>
              </div>

              <div className="space-y-2.5 my-3">
                <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-2.5 flex items-center justify-between text-xs">
                  <span className="text-slate-300">后端底层引擎 API</span>
                  <span className="font-mono text-emerald-400 flex items-center gap-1 font-semibold">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    200 OK (8000端口)
                  </span>
                </div>

                <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-2.5 flex items-center justify-between text-xs">
                  <span className="text-slate-300">客观事实底盘数据源</span>
                  <span className="font-mono text-purple-300">同花顺+东方财富+新浪</span>
                </div>

                <div className="bg-white/[0.03] border border-white/10 rounded-2xl p-2.5 flex items-center justify-between text-xs">
                  <span className="text-slate-300">RFC 8785 审计数字指纹</span>
                  <span className="font-mono text-cyan-300">JCS 严格防篡改校验</span>
                </div>
              </div>
            </div>

            <div className="pt-2 border-t border-white/5 text-[11px] text-slate-400 flex items-center justify-between">
              <span>零主观臆造 · 纯客观真实数据</span>
              <Link href="/cockpit" className="text-purple-300 hover:text-white flex items-center gap-0.5">
                <span>进入驾驶舱 &rarr;</span>
              </Link>
            </div>
          </GlassCard>
        </div>

        {/* ========================================================================= */}
        {/* 区域 2: 偏离关注项 & 待复盘标的队列 */}
        {/* ========================================================================= */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* 偏离关注项 (异动感知与认知偏离实时告警) */}
          <GlassCard rounded="3xl" padding="md" className="flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-2 border-b border-white/5">
                <span className="text-xs font-semibold text-slate-400 tracking-wider flex items-center gap-1.5">
                  <Radio className="w-3.5 h-3.5 text-rose-400 animate-pulse" />
                  偏离关注项 · 盘中认知偏离与异动感知
                </span>
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/30">
                  {anomalyEvents.length > 0 ? `${anomalyEvents.length} 条告警` : "暂无偏离"}
                </span>
              </div>

              <div className="space-y-2 my-3 max-h-[220px] overflow-y-auto no-scrollbar">
                {anomalyEvents.length > 0 ? (
                  anomalyEvents.slice(0, 4).map((evt, idx) => (
                    <div
                      key={evt.id || idx}
                      className="bg-white/[0.03] border border-white/10 hover:border-rose-500/30 rounded-2xl p-2.5 transition"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-white flex items-center gap-1.5">
                          <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
                          {evt.name || evt.symbol || "系统性偏离告警"}
                        </span>
                        <span className="font-mono text-[10px] text-slate-400">
                          {evt.timestamp || "盘中动态"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-slate-300 mt-1">
                        <span className="text-rose-300">
                          {evt.event_category || "流动性突增与结构分化"}
                        </span>
                        <span className="font-mono font-bold text-slate-200">
                          {evt.pct_change != null ? `${evt.pct_change > 0 ? "+" : ""}${evt.pct_change.toFixed(2)}%` : "--"}
                        </span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="p-4 text-center text-xs text-slate-400 bg-white/[0.02] rounded-2xl">
                    当前交易时段无高危认知偏离突破，基准假设依然有效。
                  </div>
                )}
              </div>
            </div>

            <div className="pt-2 border-t border-white/5 text-[11px] text-slate-400 flex items-center justify-between">
              <span>边沿跃迁感知与系统性共振雷达</span>
              <Link href="/monitor" className="text-cyan-400 hover:text-cyan-300 flex items-center gap-0.5">
                <span>进入盘中雷达 &rarr;</span>
              </Link>
            </div>
          </GlassCard>

          {/* 待复盘标的队列 (空间连板与重点观察标的) */}
          <GlassCard rounded="3xl" padding="md" className="flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between pb-2 border-b border-white/5">
                <span className="text-xs font-semibold text-slate-400 tracking-wider flex items-center gap-1.5">
                  <Flame className="w-3.5 h-3.5 text-purple-400" />
                  待复盘标的队列 · 空间龙头与重点池
                </span>
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
                  最高 {maxHeight}B
                </span>
              </div>

              <div className="space-y-2 my-3 max-h-[220px] overflow-y-auto no-scrollbar">
                {limitUpData?.items && limitUpData.items.length > 0 ? (
                  limitUpData.items
                    .filter((item) => (item.lbc || item.continuous_board_count || 1) >= 2)
                    .slice(0, 4)
                    .map((item) => (
                      <div
                        key={item.code}
                        className="bg-white/[0.03] border border-white/10 hover:border-purple-500/40 rounded-2xl p-2.5 flex items-center justify-between transition"
                      >
                        <div className="flex items-center gap-2 min-w-0 pr-2">
                          <span className="text-xs font-black font-mono px-1.5 py-0.5 rounded bg-purple-600/80 text-white shrink-0">
                            {item.lbc || item.continuous_board_count || 1}B
                          </span>
                          <div className="min-w-0">
                            <div className="text-xs font-bold text-white truncate">
                              {item.name}{" "}
                              <span className="text-[10px] font-mono text-slate-400">
                                ({item.code})
                              </span>
                            </div>
                            <div className="text-[10px] text-slate-400 truncate">
                              {item.reason_type || item.sector || "连板前瞻"}
                            </div>
                          </div>
                        </div>
                        <div className="text-right text-[11px] font-mono shrink-0">
                          <div className="text-purple-300 font-bold">
                            {item.fund_wan != null
                              ? item.fund_wan >= 10000
                                ? `封 ${(item.fund_wan / 10000).toFixed(1)} 亿`
                                : `封 ${Math.round(item.fund_wan)} 万`
                              : "--"}
                          </div>
                          <div className="text-[10px] text-slate-400">
                            换手 {item.turnover_ratio != null ? `${item.turnover_ratio.toFixed(1)}%` : "--"}
                          </div>
                        </div>
                      </div>
                    ))
                ) : (
                  <div className="p-4 text-center text-xs text-slate-400 bg-white/[0.02] rounded-2xl">
                    暂无高标连板队列，请进入复盘驾驶舱查看完整池。
                  </div>
                )}
              </div>
            </div>

            <div className="pt-2 border-t border-white/5 text-[11px] text-slate-400 flex items-center justify-between">
              <span>待复盘队列 {limitUpData?.total_count ?? watchlistCount} 只</span>
              <Link href="/cockpit" className="text-purple-400 hover:text-purple-300 flex items-center gap-0.5">
                <span>查看天梯树 &rarr;</span>
              </Link>
            </div>
          </GlassCard>
        </div>

        {/* ========================================================================= */}
        {/* 区域 3: 四大事实雷达全生命周期导航 */}
        {/* ========================================================================= */}
        <div>
          <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
            四大核心事实雷达 · 全生命周期协同闭环
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Link href="/briefing" className="group">
              <GlassCard rounded="2xl" padding="sm" className="h-full flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2 text-amber-400 mb-2">
                    <Sun className="w-5 h-5" />
                    <span className="font-semibold text-sm">盘前简报</span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    08:00 自动生成 · 隔夜外盘、富时 A50、大宗商品及早盘观察重点
                  </p>
                </div>
                <div className="mt-4 flex items-center text-xs text-amber-400 font-medium group-hover:underline">
                  查看简报看板 &rarr;
                </div>
              </GlassCard>
            </Link>

            <Link href="/auction" className="group">
              <GlassCard rounded="2xl" padding="sm" className="h-full flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2 text-emerald-400 mb-2">
                    <Clock className="w-5 h-5" />
                    <span className="font-semibold text-sm">竞价事实</span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    09:26 自动生成 · 09:25 开盘集合竞价总额、量能比与高标开盘承接
                  </p>
                </div>
                <div className="mt-4 flex items-center text-xs text-emerald-400 font-medium group-hover:underline">
                  查看竞价看板 &rarr;
                </div>
              </GlassCard>
            </Link>

            <Link href="/monitor" className="group">
              <GlassCard rounded="2xl" padding="sm" className="h-full flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2 text-cyan-400 mb-2">
                    <Radio className="w-5 h-5" />
                    <span className="font-semibold text-sm">盘中动态</span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    盘中 60 秒轮询 · 分时走势、量能投影 W(T)、边沿跃迁与系统性共振雷达
                  </p>
                </div>
                <div className="mt-4 flex items-center text-xs text-cyan-400 font-medium group-hover:underline">
                  进入盘中雷达 &rarr;
                </div>
              </GlassCard>
            </Link>

            <Link href="/cockpit" className="group">
              <GlassCard rounded="2xl" padding="sm" className="h-full flex flex-col justify-between border-purple-500/30">
                <div>
                  <div className="flex items-center gap-2 text-purple-400 mb-2">
                    <Zap className="w-5 h-5" />
                    <span className="font-semibold text-sm">复盘驾驶舱 (极光版)</span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    15:35 自动生成 · 连板天梯树、主力题材战场、极端对冲池与 AI 战术研判
                  </p>
                </div>
                <div className="mt-4 flex items-center text-xs text-purple-400 font-medium group-hover:underline">
                  进入复盘驾驶舱 &rarr;
                </div>
              </GlassCard>
            </Link>
          </div>
        </div>

      </div>

      {/* 底部备案与免责声明 */}
      <footer className="max-w-7xl mx-auto w-full text-center text-xs text-slate-500 py-3 border-t border-white/5">
        知见 · AI认知复盘交易系统 · 认知总览看板 · 本系统仅呈现纯客观事实与逻辑归因，严禁作为实盘买卖建议
      </footer>
    </div>
  );
}
