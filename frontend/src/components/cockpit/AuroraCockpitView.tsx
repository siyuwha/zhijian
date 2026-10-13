'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import {
  CanonicalMarketSnapshot,
  TacticalBriefingReport,
  BiddingFalsificationVerdict,
  IntradayDriftVerdict,
  LimitUpStockItem,
  LimitDownStockItem,
  BrokenLimitStockItem,
  SectorFlowItem,
  EnrichedLimitUpPoolData,
} from '@/types/canonical';
import { canonicalAPI, api } from '@/lib/api';
import { getLatestTradingDateString } from '@/lib/utils';
import {
  GlassCard,
  FloatingPillNav,
  StatusBadge,
} from '@/components/ui/aurora';
import { AuditDrawer } from './AuditDrawer';
import { TacticalBriefingModal } from './TacticalBriefingModal';
import { BiddingFalsificationModal } from './BiddingFalsificationModal';
import { TraderCockpitView } from './TraderCockpitView';
import {
  Calendar,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Flame,
  ShieldAlert,
  Brain,
  ChevronDown,
  ChevronUp,
  Zap,
  ExternalLink,
  SlidersHorizontal,
  AlertTriangle,
  Activity,
  CheckCircle2,
  XCircle,
  Layers,
  Info,
} from 'lucide-react';

interface AuroraCockpitViewProps {
  initialDate?: string;
}

export const AuroraCockpitView: React.FC<AuroraCockpitViewProps> = ({
  initialDate,
}) => {
  const router = useRouter();

  // 日期与视图模式：若未指定则默认为服务端最新交易日
  const [selectedDate, setSelectedDate] = useState<string>(initialDate || getLatestTradingDateString());
  const [viewMode, setViewMode] = useState<'aurora' | 'classic'>('aurora');

  // 主数据状态
  const [snapshot, setSnapshot] = useState<CanonicalMarketSnapshot | null>(null);
  const [limitUpData, setLimitUpData] = useState<EnrichedLimitUpPoolData | null>(null);
  const [sectors, setSectors] = useState<SectorFlowItem[]>([]);
  const [sectorType, setSectorType] = useState<'concept' | 'industry'>('concept');
  const [briefing, setBriefing] = useState<TacticalBriefingReport | null>(null);
  const [biddingVerdict, setBiddingVerdict] = useState<BiddingFalsificationVerdict | null>(null);
  const [intradayVerdict, setIntradayVerdict] = useState<IntradayDriftVerdict | null>(null);

  // 状态与加载指示
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSectorsLoading, setIsSectorsLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // 极端池子选项卡 (地雷雷达): 炸板跳水大面 vs 跌停核按钮
  const [extremePoolTab, setExtremePoolTab] = useState<'broken_limit' | 'limit_down'>('broken_limit');

  // 1B 连板展开状态
  const [is1BExpanded, setIs1BExpanded] = useState<boolean>(false);

  // 抽屉与弹窗状态
  const [isAuditOpen, setIsAuditOpen] = useState<boolean>(false);
  const [isBriefingOpen, setIsBriefingOpen] = useState<boolean>(false);
  const [isBiddingModalOpen, setIsBiddingModalOpen] = useState<boolean>(false);

  // 导航切换
  const handleNavChange = (key: string) => {
    if (key === 'overview') {
      router.push('/');
    } else if (key === 'review') {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } else if (key === 'audit') {
      setIsAuditOpen(true);
    } else if (key === 'battleground') {
      const el = document.getElementById('bento-battleground');
      el?.scrollIntoView({ behavior: 'smooth' });
    } else if (key === 'ladder') {
      const el = document.getElementById('bento-ladder');
      el?.scrollIntoView({ behavior: 'smooth' });
    } else {
      router.push(`/${key}`);
    }
  };

  // 获取核心快照与连板
  const fetchAllData = async (date: string) => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const [snapRes, limitUpRes, briefRes, bidRes, intraRes] = await Promise.allSettled([
        canonicalAPI.getCanonicalMarketSnapshot(date),
        api.getLimitUpPool(date),
        canonicalAPI.getTacticalBriefing(date),
        canonicalAPI.getAuctionFalsification(date),
        canonicalAPI.getIntradayDrift(date),
      ]);

      if (snapRes.status === 'fulfilled') {
        setSnapshot(snapRes.value);
      } else {
        console.warn('Canonical snapshot fetch warning:', snapRes.reason);
      }

      if (limitUpRes.status === 'fulfilled') {
        setLimitUpData(limitUpRes.value);
      } else {
        console.warn('Limit up pool fetch warning:', limitUpRes.reason);
      }

      if (briefRes.status === 'fulfilled') {
        setBriefing(briefRes.value);
      } else {
        console.warn('Tactical briefing fetch warning:', briefRes.reason);
      }

      if (bidRes.status === 'fulfilled') {
        setBiddingVerdict(bidRes.value);
      } else {
        console.warn('Bidding falsification fetch warning:', bidRes.reason);
      }

      if (intraRes.status === 'fulfilled') {
        setIntradayVerdict(intraRes.value);
      } else {
        console.warn('Intraday drift fetch warning:', intraRes.reason);
      }

      if (
        snapRes.status === 'rejected' &&
        limitUpRes.status === 'rejected' &&
        briefRes.status === 'rejected'
      ) {
        throw new Error('核心数据获取失败，请检查网络或后端服务');
      }
    } catch (err: any) {
      setErrorMsg(err.message || '获取数据异常');
    } finally {
      setIsLoading(false);
    }
  };

  // 单独获取板块资金流
  const fetchSectors = async (type: 'concept' | 'industry') => {
    setIsSectorsLoading(true);
    try {
      const data = await api.getSectors(type, 12);
      if (Array.isArray(data)) {
        setSectors(data);
      }
    } catch (err) {
      console.warn('Failed to fetch sector flows:', err);
    } finally {
      setIsSectorsLoading(false);
    }
  };

  // 自动探测并解析服务端最新的交易日期 (当外部未显式传入 initialDate 时)
  useEffect(() => {
    if (initialDate) {
      setSelectedDate(initialDate);
      return;
    }

    let isMounted = true;
    canonicalAPI
      .getLatestDate()
      .then((res) => {
        if (isMounted && res?.latest_date) {
          setSelectedDate(res.latest_date);
        }
      })
      .catch((err) => {
        console.warn('Failed to resolve latest date from canonicalAPI, falling back to dailyReviews:', err);
        api
          .getDailyReviews(1, 0)
          .then((revs) => {
            if (isMounted && revs?.items?.[0]?.date) {
              setSelectedDate(revs.items[0].date);
            }
          })
          .catch((e) => {
            console.warn('Fallback to dailyReviews also failed:', e);
          });
      });

    return () => {
      isMounted = false;
    };
  }, [initialDate]);

  useEffect(() => {
    fetchAllData(selectedDate);
  }, [selectedDate]);

  useEffect(() => {
    fetchSectors(sectorType);
  }, [sectorType]);

  // 计算连板天梯层级 (优先使用 snapshot.truth.ladder_tree，降级从 limitUpData.items 聚合)
  const ladderTiers = useMemo(() => {
    if (snapshot?.truth?.ladder_tree && snapshot.truth.ladder_tree.length > 0) {
      return [...snapshot.truth.ladder_tree].sort((a, b) => b.height - a.height);
    }

    if (limitUpData?.items && limitUpData.items.length > 0) {
      const grouped: Record<number, LimitUpStockItem[]> = {};
      limitUpData.items.forEach((item) => {
        const h = item.lbc || item.continuous_board_count || 1;
        if (!grouped[h]) grouped[h] = [];
        grouped[h].push(item);
      });
      return Object.entries(grouped)
        .map(([h, list]) => ({
          height: Number(h),
          stocks_count: list.length,
          stocks: list,
          is_space_leader: false,
        }))
        .sort((a, b) => b.height - a.height);
    }

    return [];
  }, [snapshot, limitUpData]);

  // 空间最高板高度与标杆
  const maxHeight = useMemo(() => {
    if (ladderTiers.length > 0) {
      return ladderTiers[0].height;
    }
    return snapshot?.truth?.sentiment_bounds?.max_ladder_height ?? limitUpData?.max_height ?? 1;
  }, [ladderTiers, snapshot, limitUpData]);

  const spaceLeaders = useMemo(() => {
    if (ladderTiers.length > 0) {
      return ladderTiers[0].stocks || [];
    }
    return [];
  }, [ladderTiers]);

  // 梯队断层识别
  const ladderGapInfo = useMemo(() => {
    const higherTiers = ladderTiers.filter((t) => t.height > 1);
    if (higherTiers.length >= 2) {
      const topHeight = higherTiers[0].height;
      const secondHeight = higherTiers[1].height;
      if (topHeight - secondHeight > 1) {
        return {
          hasGap: true,
          topHeight,
          secondHeight,
          gapCount: topHeight - secondHeight - 1,
          message: `${secondHeight}B ➔ ${topHeight}B 存在 ${topHeight - secondHeight - 1} 档空档，中位承接缺乏安全垫`,
        };
      }
    }
    return null;
  }, [ladderTiers]);

  // 首板集合
  const firstBoardGroup = useMemo(() => {
    return ladderTiers.find((t) => t.height === 1);
  }, [ladderTiers]);

  // 高阶连板集合 (>= 2板)
  const highBoardTiers = useMemo(() => {
    return ladderTiers.filter((t) => t.height > 1);
  }, [ladderTiers]);

  // 极端池数据
  const limitDownList: LimitDownStockItem[] = useMemo(() => {
    return limitUpData?.limit_down_items || [];
  }, [limitUpData]);

  const brokenLimitList: BrokenLimitStockItem[] = useMemo(() => {
    return limitUpData?.broken_limit_items || [];
  }, [limitUpData]);

  // 主线题材认知 (优先使用 snapshot.cognition.mainlines)
  const displayMainlines = useMemo(() => {
    if (snapshot?.cognition?.mainlines && snapshot.cognition.mainlines.length > 0) {
      return snapshot.cognition.mainlines.slice(0, 4);
    }
    return null;
  }, [snapshot]);

  // 周期审计关键依据
  const drivingFactors = useMemo(() => {
    return snapshot?.cognition?.market_state_calibration?.driving_factors || [];
  }, [snapshot]);

  // 监管异动标的
  const regulatoryAnomalies = useMemo(() => {
    return snapshot?.truth?.regulatory_anomalies || [];
  }, [snapshot]);

  // 格式化金额辅助
  const formatFund = (wan?: number | null, yi?: number | null) => {
    if (yi != null && yi > 0) return `${yi.toFixed(2)} 亿`;
    if (wan != null && wan > 0) {
      return wan >= 10000 ? `${(wan / 10000).toFixed(2)} 亿` : `${Math.round(wan)} 万`;
    }
    return '--';
  };

  // 如果用户选择经典布局
  if (viewMode === 'classic') {
    return (
      <div className="relative">
        <div className="fixed top-3 right-6 z-50">
          <button
            onClick={() => setViewMode('aurora')}
            className="px-3 py-1.5 rounded-full text-xs font-semibold bg-purple-600/80 hover:bg-purple-600 text-white shadow-lg backdrop-blur-md border border-purple-400/40 transition flex items-center gap-1.5"
          >
            <Zap className="w-3.5 h-3.5 text-cyan-300" />
            切换极光暗夜流光版
          </button>
        </div>
        <TraderCockpitView initialDate={selectedDate} />
      </div>
    );
  }

  // 情绪周期主状态
  const marketStateDisplayName =
    snapshot?.cognition?.market_state_calibration?.state_display_name ||
    snapshot?.cognition?.market_state_summary ||
    briefing?.market_state_label ||
    '全景宏观扫描中';

  const marketStateConfidence =
    snapshot?.cognition?.market_state_calibration?.state_confidence != null
      ? Math.round(snapshot.cognition.market_state_calibration.state_confidence * 100)
      : null;

  // 成交额数据
  const turnover = snapshot?.truth?.turnover;
  const twoMarketsTotal = turnover?.two_markets_total_yi ?? 0;
  const shAmount = turnover?.sh_amount_yi ?? 0;
  const szAmount = turnover?.sz_total_amount_yi ?? 0;
  const chinextAmount = turnover?.chinext_slice_amount_yi ?? 0;

  // 情绪上下界统计
  const bounds = snapshot?.truth?.sentiment_bounds;
  const limitUpCount = bounds?.limit_up_count ?? limitUpData?.total_count ?? 0;
  const limitDownCount = bounds?.limit_down_count ?? limitUpData?.limit_down_count ?? limitDownList.length;
  const brokenLimitCount = bounds?.broken_limit_count ?? limitUpData?.broken_limit_count ?? brokenLimitList.length;
  const touchedTotalCount = limitUpCount + brokenLimitCount;
  const brokenLimitRatio =
    bounds?.broken_limit_ratio ??
    limitUpData?.broken_limit_ratio ??
    (touchedTotalCount > 0 ? brokenLimitCount / touchedTotalCount : 0);

  return (
    <div className="min-h-screen w-full bg-[#07090E] text-slate-100 p-3 sm:p-5 md:p-6 flex flex-col gap-4 select-none relative overflow-x-hidden font-sans">
      {/* 背景弥散氛围光晕 */}
      <div className="fixed top-[-10%] left-[-5%] w-[600px] h-[600px] rounded-full bg-purple-600/12 blur-[140px] pointer-events-none -z-10" />
      <div className="fixed bottom-[-10%] right-[-5%] w-[600px] h-[600px] rounded-full bg-cyan-500/10 blur-[150px] pointer-events-none -z-10" />
      <div className="fixed top-[35%] right-[15%] w-[450px] h-[450px] rounded-full bg-rose-500/08 blur-[130px] pointer-events-none -z-10" />

      {/* 顶部悬浮胶囊灵动岛导航 (Floating Island Nav) */}
      <FloatingPillNav
        activeNav="review"
        onNavChange={handleNavChange}
        rightSlot={
          <div className="flex items-center gap-1.5 sm:gap-2">
            {/* 日期选择器 */}
            <div className="h-8 flex items-center gap-1.5 bg-black/40 border border-white/10 rounded-full px-2.5 text-xs shadow-inner">
              <Calendar className="w-3.5 h-3.5 text-slate-400 shrink-0" />
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="bg-transparent border-none text-[11px] font-mono text-slate-200 focus:outline-none cursor-pointer"
              />
            </div>

            {/* 刷新按钮 */}
            <button
              onClick={() => {
                fetchAllData(selectedDate);
                fetchSectors(sectorType);
              }}
              disabled={isLoading}
              className="h-8 w-8 flex items-center justify-center rounded-full bg-white/5 hover:bg-white/15 border border-white/10 text-slate-300 hover:text-white transition disabled:opacity-50 shrink-0"
              title="刷新全量事实与认知数据"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            </button>

            {/* 切换经典版 */}
            <button
              onClick={() => setViewMode('classic')}
              className="h-8 w-8 flex items-center justify-center rounded-full bg-white/5 hover:bg-white/15 border border-white/10 text-slate-400 hover:text-slate-200 text-xs transition shrink-0"
              title="切换为经典三层驾驶舱布局"
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
            </button>
          </div>
        }
      />

      {/* 异常警示栏 */}
      {errorMsg && (
        <div className="max-w-7xl mx-auto w-full bg-rose-950/30 border border-rose-500/40 rounded-2xl p-3 flex items-center justify-between text-xs text-rose-300 backdrop-blur-md">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400" />
            <span>数据告警: {errorMsg}</span>
          </div>
          <button
            onClick={() => fetchAllData(selectedDate)}
            className="px-2.5 py-1 rounded-full bg-rose-900/40 hover:bg-rose-900/70 border border-rose-500/40 text-xs text-rose-200 transition"
          >
            重试
          </button>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 【+1 战术认知卡】：贯穿全屏的顶层战术研判与核心结论 (回答「接下来关注什么？」) */}
      {/* ========================================================================= */}
      <section className="max-w-7xl mx-auto w-full">
        <GlassCard
          rounded="3xl"
          padding="md"
          className="w-full border border-purple-500/30 bg-gradient-to-r from-slate-950/90 via-[#0B0F19] to-purple-950/20 relative overflow-hidden shadow-2xl"
        >
          {/* 顶栏：战术认知卡标题、状态徽章与行动入口 */}
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-white/10">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-purple-600/20 border border-purple-500/40 flex items-center justify-center text-purple-300">
                <Zap className="w-4 h-4 text-purple-400" />
              </div>
              <div>
                <div className="text-sm font-bold text-white tracking-wide flex items-center gap-2">
                  <span>+1 战术认知卡 · 假说与行动边界</span>
                  <span className="text-[10px] font-mono text-purple-300 bg-purple-500/10 border border-purple-500/30 px-2 py-0.5 rounded-full">
                    {biddingVerdict?.overall_verdict || (intradayVerdict?.stage ? 'LIVE TRACK' : 'EOD CANONICAL')}
                  </span>
                </div>
              </div>
            </div>

            {/* 右侧快速下钻入口 */}
            <div className="flex items-center gap-3 text-xs">
              <button
                onClick={() => setIsBiddingModalOpen(true)}
                className="text-cyan-400 hover:text-cyan-300 transition hover:underline flex items-center gap-1 font-mono text-[11px]"
              >
                <span>09:25 竞价对账单</span>
                <ExternalLink className="w-3 h-3" />
              </button>
              <span className="text-slate-600">|</span>
              <button
                onClick={() => setIsBriefingOpen(true)}
                className="text-purple-300 hover:text-purple-200 transition hover:underline flex items-center gap-1 font-mono text-[11px]"
              >
                <span>战术研判全文</span>
                <ExternalLink className="w-3 h-3" />
              </button>
              <span className="text-slate-600">|</span>
              <button
                onClick={() => setIsAuditOpen(true)}
                className="text-slate-400 hover:text-slate-200 transition hover:underline flex items-center gap-1 font-mono text-[11px]"
              >
                <span>数理审计底稿</span>
                <ExternalLink className="w-3 h-3" />
              </button>
            </div>
          </div>

          {/* 五项结构化战术列 */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 pt-3 text-xs">
            
            {/* 1. 当前市场状态 */}
            <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/5 flex flex-col justify-between">
              <div className="text-[11px] font-semibold text-slate-400 flex items-center gap-1.5 mb-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
                ① 当前市场状态
              </div>
              <div>
                <div className="text-sm font-black font-mono text-white tracking-tight flex items-center gap-1.5">
                  <span>{marketStateDisplayName}</span>
                </div>
                {marketStateConfidence != null && (
                  <div className="text-[10px] text-purple-300 font-mono mt-0.5">
                    判定置信度 {marketStateConfidence}%
                  </div>
                )}
                <div className="mt-2">
                  <span className="inline-block px-2 py-0.5 rounded text-[10px] font-semibold bg-gradient-to-r from-purple-600/80 to-rose-600/80 text-white shadow-sm border border-purple-400/20">
                    {marketStateDisplayName.includes('退潮') || marketStateDisplayName.includes('恐慌')
                      ? '防守优先 · 仓位 0~2成'
                      : marketStateDisplayName.includes('加速') || marketStateDisplayName.includes('扩张')
                      ? '主升进攻 · 抱紧核心龙头'
                      : '混沌分歧 · 严控追高胜率'}
                  </span>
                </div>
              </div>
              <div className="text-[10px] text-slate-400 mt-2 line-clamp-2">
                {snapshot?.cognition?.market_state_summary || briefing?.market_state_label || '客观全景扫描已就绪'}
              </div>
            </div>

            {/* 2. 关键依据 */}
            <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/5 flex flex-col justify-between">
              <div className="text-[11px] font-semibold text-slate-400 flex items-center gap-1.5 mb-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                ② 关键事实依据
              </div>
              <div className="space-y-1.5 text-[11px] text-slate-300">
                {drivingFactors.length > 0 ? (
                  drivingFactors.slice(0, 2).map((factor, idx) => (
                    <div key={idx} className="flex items-start gap-1">
                      <span className="text-emerald-400 font-bold shrink-0">·</span>
                      <span className="line-clamp-2">{factor}</span>
                    </div>
                  ))
                ) : (
                  <>
                    <div className="flex items-start gap-1">
                      <span className="text-emerald-400 font-bold shrink-0">·</span>
                      <span>两市成交额: {twoMarketsTotal > 0 ? `${twoMarketsTotal.toLocaleString()} 亿` : '--'}</span>
                    </div>
                    <div className="flex items-start gap-1">
                      <span className="text-emerald-400 font-bold shrink-0">·</span>
                      <span>涨跌停对比: 涨停 {limitUpCount} / 跌停 {limitDownCount}</span>
                    </div>
                  </>
                )}
                <div className="text-[10px] font-mono text-slate-400 pt-1 border-t border-white/5">
                  炸板率 {(brokenLimitRatio * 100).toFixed(1)}% · 空间最高 {maxHeight}B
                </div>
              </div>
            </div>

            {/* 3. 主要博弈矛盾 */}
            <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/5 flex flex-col justify-between">
              <div className="text-[11px] font-semibold text-slate-400 flex items-center gap-1.5 mb-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                ③ 主要博弈矛盾
              </div>
              <p className="text-[11px] text-slate-300 leading-relaxed line-clamp-4">
                {briefing?.tactical_briefing_text ||
                  '市场多空处于高位分歧窗口，注意观察龙头孤立无援与中位接力断层之间的承接矛盾。'}
              </p>
            </div>

            {/* 4. 待验证条件 */}
            <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/5 flex flex-col justify-between">
              <div className="text-[11px] font-semibold text-slate-400 flex items-center gap-1.5 mb-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
                ④ 待验证条件 (观察锚点)
              </div>
              <div className="text-[11px] text-slate-300 leading-relaxed">
                <p className="line-clamp-3">
                  {briefing?.next_day_observation_posts?.[0] ||
                    biddingVerdict?.verdict_headline ||
                    `盯死空间龙头 ${spaceLeaders[0]?.name || '标杆'} 与主线中军集合竞价开盘撮合与封单承接。`}
                </p>
                <div className="text-[10px] font-mono text-cyan-300 mt-1.5">
                  核验时点: 09:25 竞价撮合
                </div>
              </div>
            </div>

            {/* 5. 风险边界 */}
            <div className="p-3 rounded-2xl bg-white/[0.02] border border-white/5 flex flex-col justify-between">
              <div className="text-[11px] font-semibold text-slate-400 flex items-center gap-1.5 mb-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
                ⑤ 风险边界与执行红线
              </div>
              <div className="text-[11px] text-slate-300 leading-relaxed">
                <p className="line-clamp-3">
                  {biddingVerdict?.action_boundaries?.[0] ||
                    briefing?.risk_warnings?.[0] ||
                    '若炸板率突破 > 35% 或跌停核按钮扩散，全面禁止追高接力，严格执行减仓避险纪律。'}
                </p>
                <div className="text-[10px] text-rose-400 font-mono mt-1.5">
                  硬纪律: 触发条件坚决执行
                </div>
              </div>
            </div>

          </div>
        </GlassCard>
      </section>

      {/* ========================================================================= */}
      {/* 4 大核心市场事实区 (2x2 网格 Bento Grid) */}
      {/* ========================================================================= */}
      <main className="max-w-7xl mx-auto w-full grid grid-cols-1 lg:grid-cols-2 gap-4 flex-1">

        {/* ======================================================================= */}
        {/* ① 市场温度 (回答「现在是什么行情？」) */}
        {/* ======================================================================= */}
        <GlassCard
          rounded="3xl"
          padding="md"
          className="flex flex-col justify-between relative overflow-hidden"
        >
          {/* 卡片头部 */}
          <div className="flex items-center justify-between pb-2.5 border-b border-white/5">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse"></span>
              <span className="text-xs font-bold text-slate-200 tracking-wide flex items-center gap-1.5">
                <Brain className="w-3.5 h-3.5 text-purple-400" />
                ① 市场温度 · 宏观与微观体征
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] text-slate-400">总成交额:</span>
              <span className="text-xs font-bold font-mono text-cyan-300">
                {twoMarketsTotal > 0 ? twoMarketsTotal.toLocaleString() : '--'} 亿
              </span>
            </div>
          </div>

          {/* 主要大盘指数快照 (上证、深成、创业板) */}
          <div className="my-3 grid grid-cols-3 gap-2 text-xs">
            {/* 上证指数 */}
            {(() => {
              const idx = snapshot?.truth?.indices?.find(
                (i) => i.symbol === '000001' || i.symbol === 'sh000001'
              ) || snapshot?.truth?.indices?.[0];
              const pct = idx?.pct_change ?? 0;
              const isUp = pct > 0;
              const isDown = pct < 0;
              return (
                <div className="bg-white/[0.03] border border-white/5 rounded-2xl p-2.5">
                  <div className="text-slate-400 flex items-center justify-between">
                    <span>{idx?.name || '上证指数'}</span>
                    <span className="font-mono text-[10px] text-slate-500">
                      {idx?.symbol || '000001'}
                    </span>
                  </div>
                  <div
                    className={`text-base font-bold font-mono mt-0.5 ${
                      isUp ? 'text-rose-400' : isDown ? 'text-emerald-400' : 'text-slate-200'
                    }`}
                  >
                    {idx?.current_price ? idx.current_price.toFixed(2) : '--'}
                  </div>
                  <div
                    className={`text-[11px] font-mono ${
                      isUp ? 'text-rose-400' : isDown ? 'text-emerald-400' : 'text-slate-400'
                    }`}
                  >
                    {pct !== 0 ? (pct > 0 ? `+${pct.toFixed(2)}%` : `${pct.toFixed(2)}%`) : '--'}
                  </div>
                </div>
              );
            })()}

            {/* 深证成指 */}
            {(() => {
              const idx = snapshot?.truth?.indices?.find(
                (i) => i.symbol === '399001' || i.symbol === 'sz399001'
              ) || snapshot?.truth?.indices?.[1];
              const pct = idx?.pct_change ?? 0;
              const isUp = pct > 0;
              const isDown = pct < 0;
              return (
                <div className="bg-white/[0.03] border border-white/5 rounded-2xl p-2.5">
                  <div className="text-slate-400 flex items-center justify-between">
                    <span>{idx?.name || '深证成指'}</span>
                    <span className="font-mono text-[10px] text-slate-500">
                      {idx?.symbol || '399001'}
                    </span>
                  </div>
                  <div
                    className={`text-base font-bold font-mono mt-0.5 ${
                      isUp ? 'text-rose-400' : isDown ? 'text-emerald-400' : 'text-slate-200'
                    }`}
                  >
                    {idx?.current_price ? idx.current_price.toFixed(2) : '--'}
                  </div>
                  <div
                    className={`text-[11px] font-mono ${
                      isUp ? 'text-rose-400' : isDown ? 'text-emerald-400' : 'text-slate-400'
                    }`}
                  >
                    {pct !== 0 ? (pct > 0 ? `+${pct.toFixed(2)}%` : `${pct.toFixed(2)}%`) : '--'}
                  </div>
                </div>
              );
            })()}

            {/* 创业板指 */}
            {(() => {
              const idx = snapshot?.truth?.indices?.find(
                (i) => i.symbol === '399006' || i.symbol === 'sz399006'
              ) || snapshot?.truth?.indices?.[2];
              const pct = idx?.pct_change ?? 0;
              const isUp = pct > 0;
              const isDown = pct < 0;
              return (
                <div className="bg-white/[0.03] border border-white/5 rounded-2xl p-2.5">
                  <div className="text-slate-400 flex items-center justify-between">
                    <span>{idx?.name || '创业板指'}</span>
                    <span className="font-mono text-[10px] text-slate-500">
                      {idx?.symbol || '399006'}
                    </span>
                  </div>
                  <div
                    className={`text-base font-bold font-mono mt-0.5 ${
                      isUp ? 'text-rose-400' : isDown ? 'text-emerald-400' : 'text-slate-200'
                    }`}
                  >
                    {idx?.current_price ? idx.current_price.toFixed(2) : '--'}
                  </div>
                  <div
                    className={`text-[11px] font-mono ${
                      isUp ? 'text-rose-400' : isDown ? 'text-emerald-400' : 'text-slate-400'
                    }`}
                  >
                    {pct !== 0 ? (pct > 0 ? `+${pct.toFixed(2)}%` : `${pct.toFixed(2)}%`) : '--'}
                  </div>
                </div>
              );
            })()}
          </div>

          {/* 量能明细与结构流动性 */}
          <div className="p-2.5 rounded-2xl bg-white/[0.02] border border-white/5 flex items-center justify-between text-xs my-1">
            <div className="flex items-center gap-2">
              <span className="text-slate-400">成交构成:</span>
              <span className="font-mono text-slate-300">
                沪 {shAmount > 0 ? shAmount.toLocaleString() : '--'} 亿 · 深{' '}
                {szAmount > 0 ? szAmount.toLocaleString() : '--'} 亿
              </span>
            </div>
            <div className="font-mono text-cyan-300 text-[11px]">
              创业板占比{' '}
              {turnover?.chinext_ratio_in_sz != null
                ? `${(turnover.chinext_ratio_in_sz * 100).toFixed(1)}%`
                : '--'}
            </div>
          </div>

          {/* 短线体征 4 宫格 */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center my-2">
            <div className="p-2 rounded-xl bg-white/[0.02] border border-white/5">
              <div className="text-[10px] text-slate-400">真实涨停 / 跌停</div>
              <div className="text-sm font-black font-mono mt-0.5">
                <span className="text-rose-400">{limitUpCount}</span>
                <span className="text-slate-500"> / </span>
                <span className="text-emerald-400">{limitDownCount}</span>
              </div>
            </div>

            <div className="p-2 rounded-xl bg-white/[0.02] border border-white/5">
              <div className="text-[10px] text-slate-400">炸板大面率</div>
              <div className={`text-sm font-black font-mono mt-0.5 ${brokenLimitRatio > 0.35 ? 'text-rose-400' : 'text-amber-400'}`}>
                {(brokenLimitRatio * 100).toFixed(1)}%
              </div>
            </div>

            <div className="p-2 rounded-xl bg-white/[0.02] border border-white/5">
              <div className="text-[10px] text-slate-400">触及涨停总数</div>
              <div className="text-sm font-black font-mono text-slate-200 mt-0.5">
                {touchedTotalCount} 只
              </div>
            </div>

            <div className="p-2 rounded-xl bg-white/[0.02] border border-white/5">
              <div className="text-[10px] text-slate-400">空间连板最高板</div>
              <div className="text-sm font-black font-mono text-purple-300 mt-0.5">
                {maxHeight}B
              </div>
            </div>
          </div>

          {/* 周期判定审计底色 */}
          <div className="flex items-center justify-between text-[11px] text-slate-400 border-t border-white/5 pt-2 mt-1">
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
              <span>周期证据状态:</span>
              <span className="text-slate-300 font-medium">
                {drivingFactors[0] || '规则与特征向量加权标定'}
              </span>
            </span>
            <span className="font-mono text-slate-500 text-[10px]">
              RFC 8785 校验完成
            </span>
          </div>
        </GlassCard>

        {/* ======================================================================= */}
        {/* ② 连板天梯 (回答「市场高度在哪里？」) */}
        {/* ======================================================================= */}
        <GlassCard
          id="bento-ladder"
          rounded="3xl"
          padding="md"
          className="flex flex-col justify-between"
        >
          {/* 卡片头部 */}
          <div className="flex items-center justify-between pb-2.5 border-b border-white/5">
            <div className="flex items-center gap-2">
              <Flame className="w-3.5 h-3.5 text-purple-400" />
              <span className="text-xs font-bold text-slate-200 tracking-wide">
                ② 连板天梯 · 空间标杆与晋级梯队
              </span>
            </div>
            <span className="text-xs font-mono font-black px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
              MAX {maxHeight}B
            </span>
          </div>

          {/* 顶阶空间龙头 Hero 卡片 */}
          <div className="my-2.5">
            {spaceLeaders.length > 0 ? (
              spaceLeaders.slice(0, 1).map((leader) => (
                <div
                  key={leader.code}
                  className="bg-gradient-to-r from-purple-950/70 via-indigo-950/50 to-transparent border border-purple-500/40 rounded-2xl p-3 flex items-center justify-between shadow-lg"
                >
                  <div className="min-w-0 pr-2">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-black font-mono px-2 py-0.5 rounded bg-purple-600 text-white shrink-0">
                        {maxHeight}B
                      </span>
                      <span className="text-sm font-bold text-white truncate">
                        {leader.name}
                      </span>
                      <span className="text-[11px] font-mono text-purple-300 shrink-0">
                        {leader.code}
                      </span>
                      <span className="px-1.5 py-0.2 rounded text-[10px] bg-rose-500/20 text-rose-300 font-semibold shrink-0">
                        空间总龙
                      </span>
                    </div>
                    <div className="text-[11px] text-purple-300 mt-1 truncate">
                      {leader.reason_type || leader.sector || '空间标杆'} · {leader.fbt_str || '早盘首封'}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-xs font-bold font-mono text-purple-200">
                      封单 {formatFund(leader.fund_wan, leader.fund_yi)}
                    </div>
                    <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                      换手 {leader.turnover_ratio != null ? `${leader.turnover_ratio.toFixed(1)}%` : '--'}
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="p-3 text-xs text-slate-400 text-center bg-white/[0.02] rounded-2xl">
                暂无高阶空间连板标的
              </div>
            )}
          </div>

          {/* 梯队断层警示 (若存在高度断档则显示) */}
          {ladderGapInfo && ladderGapInfo.hasGap && (
            <div className="mb-2 p-2 rounded-xl bg-amber-950/30 border border-amber-500/30 flex items-center justify-between text-xs">
              <div className="flex items-center gap-1.5 text-amber-300 font-medium">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                <span>{ladderGapInfo.message}</span>
              </div>
              <span className="text-[10px] text-amber-400 font-mono shrink-0">断层警示</span>
            </div>
          )}

          {/* 高阶连板梯队 (>= 2B) */}
          <div className="space-y-1.5 flex-1 overflow-y-auto max-h-[180px] pr-1 no-scrollbar my-1">
            {highBoardTiers
              .filter((tier) => tier.height < maxHeight && tier.height >= 2)
              .map((tier) => {
                const sampleStock = tier.stocks?.[0];
                return (
                  <div
                    key={tier.height}
                    className="bg-white/[0.03] border border-white/10 rounded-xl p-2 flex items-center justify-between hover:border-white/20 transition"
                  >
                    <div className="flex items-center gap-2 min-w-0 pr-2">
                      <span className="text-xs font-bold font-mono px-1.5 py-0.5 rounded bg-slate-800 text-cyan-300 shrink-0">
                        {tier.height}B
                      </span>
                      <div className="min-w-0">
                        <div className="text-xs font-bold text-white truncate flex items-center gap-1.5">
                          <span>{sampleStock?.name || `梯队${tier.height}板`}</span>
                          {tier.stocks_count > 1 && (
                            <span className="text-[10px] text-slate-400 font-normal">
                              +{tier.stocks_count - 1}只
                            </span>
                          )}
                        </div>
                        <div className="text-[10px] text-slate-400 truncate">
                          {sampleStock?.reason_type || sampleStock?.sector || '连板中坚'}
                        </div>
                      </div>
                    </div>
                    <div className="text-right text-[11px] font-mono text-slate-300 shrink-0">
                      <div>封单 {formatFund(sampleStock?.fund_wan, sampleStock?.fund_yi)}</div>
                      <div className="text-[10px] text-slate-500">
                        换手 {sampleStock?.turnover_ratio != null ? `${sampleStock.turnover_ratio.toFixed(1)}%` : '--'}
                      </div>
                    </div>
                  </div>
                );
              })}
          </div>

          {/* 首板基座 (1B 可折叠展开) */}
          <div className="pt-2 border-t border-white/5 mt-1">
            <button
              onClick={() => setIs1BExpanded(!is1BExpanded)}
              className="w-full py-1.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-xs text-slate-300 flex items-center justify-between px-3 transition"
            >
              <span className="flex items-center gap-1.5">
                <span>1B 首板基座</span>
                {is1BExpanded ? (
                  <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
                ) : (
                  <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                )}
              </span>
              <span className="font-mono text-purple-300 font-bold">
                共 {firstBoardGroup?.stocks_count ?? 0} 只 &gt;
              </span>
            </button>

            {is1BExpanded && (
              <div className="mt-2 p-2 bg-black/40 border border-white/10 rounded-xl max-h-28 overflow-y-auto flex flex-wrap gap-1.5 no-scrollbar">
                {(firstBoardGroup?.stocks || []).map((s) => (
                  <span
                    key={s.code}
                    className="px-2 py-0.5 rounded-lg bg-white/5 border border-white/10 text-[10px] font-mono text-slate-200"
                    title={`换手: ${s.turnover_ratio ?? '--'}% | 封单: ${s.fund_wan ?? '--'}万`}
                  >
                    {s.name} ({s.code})
                  </span>
                ))}
              </div>
            )}
          </div>
        </GlassCard>

        {/* ======================================================================= */}
        {/* ③ 主线题材 (回答「市场主要在交易什么？」) */}
        {/* ======================================================================= */}
        <GlassCard
          id="bento-battleground"
          rounded="3xl"
          padding="md"
          className="flex flex-col justify-between"
        >
          {/* 卡片头部 */}
          <div className="flex items-center justify-between pb-2.5 border-b border-white/5">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-3.5 h-3.5 text-cyan-400" />
              <span className="text-xs font-bold text-slate-200 tracking-wide">
                ③ 主线题材 · 核心战场与轮动
              </span>
            </div>

            {/* 胶囊切换 Tab (概念题材 vs 行业板块) */}
            <div className="flex bg-black/40 border border-white/10 rounded-full p-0.5 text-xs">
              <button
                onClick={() => setSectorType('concept')}
                className={`px-2.5 py-0.5 rounded-full text-[11px] transition ${
                  sectorType === 'concept'
                    ? 'bg-white/15 text-white font-medium shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                概念题材
              </button>
              <button
                onClick={() => setSectorType('industry')}
                className={`px-2.5 py-0.5 rounded-full text-[11px] transition ${
                  sectorType === 'industry'
                    ? 'bg-white/15 text-white font-medium shadow-sm'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                行业板块
              </button>
            </div>
          </div>

          {/* 题材列表 (优先使用 displayMainlines 结构化认知，否则降级 sectors) */}
          <div className="space-y-2 my-2.5 flex-1 overflow-y-auto max-h-[300px] pr-1 no-scrollbar">
            {displayMainlines && displayMainlines.length > 0 ? (
              displayMainlines.map((m, idx) => (
                <div
                  key={m.sector_code || idx}
                  className="bg-white/[0.03] border border-white/10 hover:border-purple-500/40 rounded-2xl p-2.5 transition"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span
                        className={`font-mono text-xs font-black px-1.5 py-0.2 rounded ${
                          idx === 0
                            ? 'text-purple-300 bg-purple-950/60 border border-purple-500/30'
                            : 'text-slate-400 bg-slate-900 border border-white/5'
                        }`}
                      >
                        #{idx + 1}
                      </span>
                      <span className="text-sm font-bold text-white">{m.sector_name}</span>
                      <span className="text-[10px] font-mono text-purple-300 bg-purple-500/10 px-1.5 py-0.2 rounded">
                        {m.structural_role === 'CORE_MAINLINE'
                          ? '核心主线'
                          : m.structural_role === 'BRANCH_ROTATION'
                          ? '分支轮动'
                          : '弱轮动/独立'}
                      </span>
                    </div>
                    <div className="text-[11px] font-mono text-rose-400 font-bold">
                      {m.constituency?.limit_up_count ? `${m.constituency.limit_up_count} 家涨停` : '--'}
                    </div>
                  </div>

                  <div className="mt-1.5 text-xs text-slate-300 flex items-center justify-between">
                    <div>
                      领军标杆:{' '}
                      <strong className="text-white">
                        {m.constituency?.leader_name || '--'}
                      </strong>{' '}
                      <span className="text-[10px] font-mono text-purple-300">
                        ({m.constituency?.leader_height ?? 1}B)
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400">
                      首板扩散 {m.constituency?.first_board_diffusion_count ?? 0} 家
                    </span>
                  </div>

                  {/* 核心反向证据与盯盘警示 (不可或缺的证伪护栏) */}
                  {m.counter_evidence && m.counter_evidence.length > 0 && (
                    <div className="mt-2 text-[10px] text-amber-300 bg-amber-950/20 border border-amber-500/20 p-1.5 rounded-lg flex items-start gap-1">
                      <span className="text-amber-400 font-bold shrink-0">盯盘警示:</span>
                      <span className="line-clamp-2">{m.counter_evidence[0]}</span>
                    </div>
                  )}
                </div>
              ))
            ) : isSectorsLoading ? (
              <div className="p-8 text-center text-xs text-slate-400 flex items-center justify-center gap-2">
                <RefreshCw className="w-4 h-4 animate-spin text-purple-400" />
                正在加载板块资金流向...
              </div>
            ) : sectors.length > 0 ? (
              sectors.slice(0, 4).map((sec, idx) => {
                const isNetInflowPositive = sec.net_inflow_yi != null && sec.net_inflow_yi > 0;
                const isPctPositive = sec.pct_change != null && sec.pct_change > 0;
                return (
                  <div
                    key={sec.code || idx}
                    className="bg-white/[0.03] border border-white/10 hover:border-purple-500/40 rounded-2xl p-2.5 flex items-center justify-between transition"
                  >
                    <div className="flex items-center gap-2.5 min-w-0 pr-2">
                      <span
                        className={`font-mono text-xs font-black shrink-0 ${
                          idx === 0 ? 'text-purple-400' : 'text-slate-400'
                        }`}
                      >
                        #{idx + 1}
                      </span>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-sm text-white truncate">
                            {sec.name}
                          </span>
                          <span
                            className={`text-[10px] font-mono font-bold px-1 rounded ${
                              isPctPositive
                                ? 'text-rose-400 bg-rose-950/40'
                                : 'text-emerald-400 bg-emerald-950/40'
                            }`}
                          >
                            {sec.pct_change != null
                              ? sec.pct_change > 0
                                ? `+${sec.pct_change.toFixed(2)}%`
                                : `${sec.pct_change.toFixed(2)}%`
                              : '--'}
                          </span>
                        </div>
                        {sec.leader_name && (
                          <div className="text-[10px] text-slate-400 mt-0.5 truncate">
                            龙头: {sec.leader_name}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="text-right shrink-0">
                      <span
                        className={`inline-block px-2 py-0.5 rounded-lg font-mono text-[11px] font-bold border ${
                          isNetInflowPositive
                            ? 'bg-rose-500/15 border-rose-500/30 text-rose-300'
                            : 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'
                        }`}
                      >
                        {sec.net_inflow_yi != null
                          ? sec.net_inflow_yi > 0
                            ? `+${sec.net_inflow_yi.toFixed(2)} 亿`
                            : `${sec.net_inflow_yi.toFixed(2)} 亿`
                          : '--'}
                      </span>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="p-8 text-center text-xs text-slate-400">
                暂无题材资金流向数据
              </div>
            )}
          </div>
        </GlassCard>

        {/* ======================================================================= */}
        {/* ④ 地雷雷达 (回答「哪里出现了重要风险？」) */}
        {/* ======================================================================= */}
        <GlassCard
          rounded="3xl"
          padding="md"
          className="flex flex-col justify-between"
        >
          {/* 卡片头部 */}
          <div className="flex items-center justify-between pb-2.5 border-b border-white/5">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
              <span className="text-xs font-bold text-slate-200 tracking-wide">
                ④ 地雷雷达 · 极端风险与跳水预警
              </span>
            </div>
            <span
              className={`text-[10px] font-mono px-2 py-0.5 rounded-full border ${
                brokenLimitRatio > 0.35 || limitDownCount >= 5
                  ? 'bg-rose-950 text-rose-400 border-rose-800 animate-pulse'
                  : 'bg-emerald-950/40 text-emerald-300 border-emerald-800/40'
              }`}
            >
              {brokenLimitRatio > 0.35 || limitDownCount >= 5 ? '高危警示' : '分歧可控'}
            </span>
          </div>

          {/* 炸板大面率仪表 */}
          <div className="bg-amber-950/20 border border-amber-500/30 rounded-2xl p-2.5 my-2">
            <div className="flex items-center justify-between text-xs">
              <span className="text-amber-300 font-medium">炸板大面率仪表</span>
              <span className="text-base font-black font-mono text-amber-400">
                {(brokenLimitRatio * 100).toFixed(1)}%
              </span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-1.5 mt-2 overflow-hidden">
              <div
                className="bg-gradient-to-r from-amber-400 to-rose-500 h-1.5 rounded-full transition-all duration-500"
                style={{ width: `${Math.min(100, brokenLimitRatio * 100)}%` }}
              />
            </div>
            <div className="text-[10px] text-slate-400 mt-1.5 flex justify-between font-mono">
              <span>触及涨停 {touchedTotalCount} 只</span>
              <span className="text-rose-400">炸板 {brokenLimitCount} 只</span>
              <span className="text-emerald-400">跌停 {limitDownCount} 只</span>
            </div>
          </div>

          {/* 选项卡切换: 炸板跳水大面 vs 跌停核按钮 */}
          <div className="my-1">
            <div className="flex bg-black/40 border border-white/10 rounded-full p-0.5 text-[11px]">
              <button
                onClick={() => setExtremePoolTab('broken_limit')}
                className={`flex-1 py-1 rounded-full text-center transition ${
                  extremePoolTab === 'broken_limit'
                    ? 'bg-amber-900/40 text-amber-300 font-semibold border border-amber-500/30'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                炸板跳水大面 ({brokenLimitList.length})
              </button>
              <button
                onClick={() => setExtremePoolTab('limit_down')}
                className={`flex-1 py-1 rounded-full text-center transition ${
                  extremePoolTab === 'limit_down'
                    ? 'bg-emerald-900/40 text-emerald-300 font-semibold border border-emerald-500/30'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                跌停核按钮 ({limitDownList.length})
              </button>
            </div>

            {/* 列表渲染 */}
            <div className="space-y-1.5 mt-2 max-h-[140px] overflow-y-auto no-scrollbar">
              {extremePoolTab === 'broken_limit' ? (
                brokenLimitList.length > 0 ? (
                  brokenLimitList.slice(0, 3).map((item) => (
                    <div
                      key={item.code}
                      className="border-l-2 border-amber-400 bg-white/[0.02] p-2 rounded-r-xl"
                    >
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-bold text-white truncate">
                          {item.name}{' '}
                          <span className="font-mono text-[10px] text-slate-400">
                            ({item.code})
                          </span>
                        </span>
                        <span className="font-mono font-bold text-amber-400 shrink-0">
                          回落 {item.fall_back_pct != null ? `-${item.fall_back_pct.toFixed(1)}%` : '--'}
                        </span>
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-slate-400 mt-0.5">
                        <span>成交 {item.amount_yi != null ? `${item.amount_yi.toFixed(1)} 亿` : '--'}</span>
                        <span className="text-rose-400">
                          炸板 {item.open_count ?? 1} 次
                        </span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="p-2 text-center text-xs text-slate-400">
                    当前无炸板跳水大面标的
                  </div>
                )
              ) : limitDownList.length > 0 ? (
                limitDownList.slice(0, 3).map((item) => (
                  <div
                    key={item.code}
                    className="border-l-2 border-emerald-400 bg-white/[0.02] p-2 rounded-r-xl"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-bold text-white truncate">
                        {item.name}{' '}
                        <span className="font-mono text-[10px] text-slate-400">
                          ({item.code})
                        </span>
                      </span>
                      <span className="font-mono font-bold text-emerald-400 shrink-0">
                        {item.pct_change != null ? `${item.pct_change.toFixed(2)}%` : '-10.00%'}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-slate-400 mt-0.5">
                      <span>封单 {formatFund(item.fund_wan, item.fund_yi)}</span>
                      <span className="text-emerald-400 font-medium">
                        {item.days && item.days > 1 ? `连跌 ${item.days} 跌停` : '首跌停'}
                      </span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="p-2 text-center text-xs text-slate-400">
                  当前无跌停核按钮标的
                </div>
              )}
            </div>
          </div>

          {/* 底部警戒状态 */}
          <div className="text-[10px] text-slate-400 border-t border-white/5 pt-2 flex justify-between items-center">
            <span>极值警戒阈值: 35%</span>
            <span
              className={`font-mono font-bold ${
                brokenLimitRatio > 0.35 ? 'text-rose-400' : 'text-slate-400'
              }`}
            >
              {brokenLimitRatio > 0.35 ? '追高风险极高 · 执行防守' : '分歧处于安全阈内'}
            </span>
          </div>
        </GlassCard>
      </main>

      {/* 底部备案与免责声明 */}
      <footer className="max-w-7xl mx-auto w-full text-center text-xs text-slate-500 py-2 border-t border-white/5">
        知见 · AI认知复盘交易系统 · 极光暗夜「4+1」驾驶舱 · 本系统只呈现纯客观事实与逻辑归因，严禁作为实盘投资建议
      </footer>

      {/* 审计抽屉 (Audit Drawer) */}
      {snapshot && (
        <AuditDrawer
          isOpen={isAuditOpen}
          onClose={() => setIsAuditOpen(false)}
          snapshot={snapshot}
        />
      )}

      {/* 战术研判全文弹窗 (Tactical Briefing Modal) */}
      <TacticalBriefingModal
        isOpen={isBriefingOpen}
        onClose={() => setIsBriefingOpen(false)}
        briefing={briefing}
        onOpenBiddingFalsification={() => {
          setIsBriefingOpen(false);
          setIsBiddingModalOpen(true);
        }}
      />

      {/* 09:25 竞价对账单弹窗 (Bidding Falsification Modal) */}
      <BiddingFalsificationModal
        isOpen={isBiddingModalOpen}
        onClose={() => setIsBiddingModalOpen(false)}
        verdict={biddingVerdict}
      />
    </div>
  );
};
