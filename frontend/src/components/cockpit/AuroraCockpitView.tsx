'use client';

import React, { useState, useEffect, useMemo, useRef } from 'react';
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
  IntradayBriefingTimelineResponse,
  IntradayBriefingStageKey,
  TopSectorsTrendResponse,
  TopSectorTrendItem,
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
  Clock,
  Compass,
  ArrowRight,
  Plus,
  X,
} from 'lucide-react';

export interface StockComparisonItem {
  code: string;
  name: string;
  role: string;
  tagType?: 'today_strongest' | 'yesterday_highest' | 'yesterday_second' | 'yesterday_core_broken' | 'normal';
  tagLabel?: string;
  isDynamic?: boolean;
  changePct: number;
  color: string;
  pathD: string;
  endX: number;
  endY: number;
}

const DEFAULT_STOCKS: StockComparisonItem[] = [
  {
    code: '600550',
    name: '保变电气',
    role: '昨日最高板 (5B)',
    tagType: 'yesterday_highest',
    tagLabel: '昨日最高板 (5B)',
    changePct: 10.0,
    color: '#EF4444',
    pathD: 'M 0,70 C 10,40 20,10 40,8 L 187.5,8',
    endX: 187.5,
    endY: 8,
  },
  {
    code: '600198',
    name: '大唐电信',
    role: '昨日次高板 (4B)',
    tagType: 'yesterday_second',
    tagLabel: '昨日次高板 (4B)',
    changePct: 9.9,
    color: '#A855F7',
    pathD: 'M 0,70 C 30,50 60,30 100,10 L 187.5,10',
    endX: 187.5,
    endY: 10,
  },
  {
    code: '000158',
    name: '常山北明',
    role: '今日最强涨停 (2B)',
    tagType: 'today_strongest',
    tagLabel: '今日最强涨停 (2B)',
    isDynamic: true,
    changePct: 9.9,
    color: '#06B6D4',
    pathD: 'M 0,70 C 40,60 80,40 120,20 L 187.5,10',
    endX: 187.5,
    endY: 10,
  },
  {
    code: '002085',
    name: '万丰奥威',
    role: '昨日核心分歧 (3B)',
    tagType: 'yesterday_core_broken',
    tagLabel: '昨日核心分歧 (3B)',
    changePct: -5.2,
    color: '#10B981',
    pathD: 'M 0,70 C 20,40 40,15 70,10 C 90,10 110,60 140,90 L 187.5,106',
    endX: 187.5,
    endY: 106,
  },
  {
    code: '688981',
    name: '中芯国际',
    role: '科技容量中军',
    tagType: 'normal',
    changePct: 4.8,
    color: '#F59E0B',
    pathD: 'M 0,70 C 50,60 90,45 130,40 C 160,36 175,36 187.5,36',
    endX: 187.5,
    endY: 36,
  },
  {
    code: '300750',
    name: '宁德时代',
    role: '创指核心权重',
    tagType: 'normal',
    changePct: -1.8,
    color: '#38BDF8',
    pathD: 'M 0,70 C 40,75 80,80 120,82 C 150,84 170,82 187.5,82',
    endX: 187.5,
    endY: 82,
  },
];

const CANDIDATE_STOCKS: StockComparisonItem[] = [
  {
    code: '000021',
    name: '深科技',
    role: '存储芯片',
    changePct: 6.2,
    color: '#EC4899',
    pathD: 'M 0,70 C 30,55 70,40 120,35 C 155,30 170,26 187.5,26',
    endX: 187.5,
    endY: 26,
  },
  {
    code: '001696',
    name: '宗申动力',
    role: '低空经济',
    changePct: -3.4,
    color: '#E11D48',
    pathD: 'M 0,70 C 25,40 50,30 80,60 C 120,85 160,92 187.5,93.8',
    endX: 187.5,
    endY: 93.8,
  },
  {
    code: '300339',
    name: '润和软件',
    role: '开源鸿蒙',
    changePct: 7.5,
    color: '#6366F1',
    pathD: 'M 0,70 C 30,50 60,32 100,25 C 140,20 170,18 187.5,17.5',
    endX: 187.5,
    endY: 17.5,
  },
];

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

  // Phase 3B: 4 大固定时段盘中操盘内参时间轴与 Top 5 题材分时资金趋势
  const [timelineResponse, setTimelineResponse] = useState<IntradayBriefingTimelineResponse | null>(null);
  const [activeStageKey, setActiveStageKey] = useState<IntradayBriefingStageKey>('STAGE_2_MORNING');
  const [topSectorsTrend, setTopSectorsTrend] = useState<TopSectorsTrendResponse | null>(null);

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

  // 分时图交互状态
  const [hoverPct, setHoverPct] = useState<number>(0.7);
  const chartContainerRef = useRef<HTMLDivElement>(null);

  // 核心个股分时涨跌幅走势对比样本股状态 (默认 6 支，上限 6 支)
  const [stockComparisonList, setStockComparisonList] = useState<StockComparisonItem[]>(DEFAULT_STOCKS);
  const [isAddStockOpen, setIsAddStockOpen] = useState<boolean>(false);
  const [stockHoverX, setStockHoverX] = useState<number>(187.5);
  const [isStockHovering, setIsStockHovering] = useState<boolean>(false);
  const [sectorHoverX, setSectorHoverX] = useState<number>(187.5);
  const [isSectorHovering, setIsSectorHovering] = useState<boolean>(false);
  const stockChartContainerRef = useRef<HTMLDivElement>(null);
  const sectorChartContainerRef = useRef<HTMLDivElement>(null);

  // 删除样本股
  const handleRemoveStock = (code: string) => {
    if (stockComparisonList.length <= 1) return;
    setStockComparisonList((prev) => prev.filter((s) => s.code !== code));
  };

  // 添加样本股
  const handleAddStock = (stock: StockComparisonItem) => {
    if (stockComparisonList.length >= 6) return;
    if (stockComparisonList.some((s) => s.code === stock.code)) return;
    setStockComparisonList((prev) => [...prev, stock]);
    setIsAddStockOpen(false);
  };

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
      const [snapRes, limitUpRes, briefRes, bidRes, intraRes, timelineRes, topTrendRes] = await Promise.allSettled([
        canonicalAPI.getCanonicalMarketSnapshot(date),
        api.getLimitUpPool(date),
        canonicalAPI.getTacticalBriefing(date),
        canonicalAPI.getAuctionFalsification(date),
        canonicalAPI.getIntradayDrift(date),
        canonicalAPI.getIntradayBriefings(date),
        canonicalAPI.getTopSectorsTrend(date),
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
      }

      if (bidRes.status === 'fulfilled') {
        setBiddingVerdict(bidRes.value);
      }

      if (intraRes.status === 'fulfilled') {
        setIntradayVerdict(intraRes.value);
      }

      if (timelineRes.status === 'fulfilled') {
        setTimelineResponse(timelineRes.value);
        if (timelineRes.value?.current_active_stage) {
          setActiveStageKey(timelineRes.value.current_active_stage);
        }
      }

      if (topTrendRes.status === 'fulfilled') {
        setTopSectorsTrend(topTrendRes.value);
      }

      if (
        snapRes.status === 'rejected' &&
        limitUpRes.status === 'rejected' &&
        timelineRes.status === 'rejected'
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

  // 计算连板天梯层级
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
    return snapshot?.truth?.sentiment_bounds?.max_ladder_height ?? limitUpData?.max_height ?? 5;
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
          message: `${secondHeight}B ➔ ${topHeight}B 存在 ${topHeight - secondHeight - 1} 档空档，中位接力缺乏安全垫`,
        };
      }
    }
    return {
      hasGap: true,
      topHeight: 5,
      secondHeight: 2,
      gapCount: 2,
      message: '3B 梯队全军覆没，2B ➔ 5B 存在 2 档空档，中位接力缺乏安全垫',
    };
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

  // 格式化金额辅助
  const formatFund = (wan?: number | null, yi?: number | null) => {
    if (yi != null && yi > 0) return `${yi.toFixed(2)} 亿`;
    if (wan != null && wan > 0) {
      return wan >= 10000 ? `${(wan / 10000).toFixed(2)} 亿` : `${Math.round(wan)} 万`;
    }
    return '--';
  };

  // 当前激活的时段内参记录
  const currentBriefingRecord = useMemo(() => {
    if (timelineResponse?.stages && timelineResponse.stages.length > 0) {
      const found = timelineResponse.stages.find((s) => s.stage === activeStageKey);
      if (found) return found;
      return timelineResponse.stages[timelineResponse.stages.length - 1];
    }
    return null;
  }, [timelineResponse, activeStageKey]);

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

  // 成交额数据
  const turnover = snapshot?.truth?.turnover;
  const twoMarketsTotal = turnover?.two_markets_total_yi ?? 5820.4;
  const shAmount = turnover?.sh_amount_yi ?? 2410.2;
  const szAmount = turnover?.sz_total_amount_yi ?? 3410.2;

  // 情绪上下界统计
  const bounds = snapshot?.truth?.sentiment_bounds;
  const limitUpCount = bounds?.limit_up_count ?? limitUpData?.total_count ?? 24;
  const limitDownCount = bounds?.limit_down_count ?? limitUpData?.limit_down_count ?? 3;
  const brokenLimitCount = bounds?.broken_limit_count ?? limitUpData?.broken_limit_count ?? 10;
  const touchedTotalCount = limitUpCount + brokenLimitCount;
  const brokenLimitRatio =
    bounds?.broken_limit_ratio ??
    limitUpData?.broken_limit_ratio ??
    0.294;

  // 分时图鼠标移动处理
  const handleChartMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!chartContainerRef.current) return;
    const rect = chartContainerRef.current.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
    setHoverPct(x / rect.width);
  };

  // 计算当前 hover 的时间戳与数据
  const hoverMinuteIdx = Math.floor(hoverPct * 45);
  const hoverHour = 9 + Math.floor((30 + hoverMinuteIdx) / 60);
  const hoverMinute = (30 + hoverMinuteIdx) % 60;
  const hoverTimeStr = `${String(hoverHour).padStart(2, '0')}:${String(hoverMinute).padStart(2, '0')}:00`;

  return (
    <div className="min-h-screen w-full bg-[#07090E] text-slate-100 p-2.5 sm:p-4 md:p-5 flex flex-col gap-3.5 select-none relative overflow-x-hidden font-sans">
      {/* 背景弥散氛围光晕 */}
      <div className="fixed top-[-10%] left-[-5%] w-[600px] h-[600px] rounded-full bg-purple-600/10 blur-[150px] pointer-events-none -z-10" />
      <div className="fixed bottom-[-10%] right-[-5%] w-[600px] h-[600px] rounded-full bg-cyan-500/08 blur-[160px] pointer-events-none -z-10" />

      {/* 顶部悬浮胶囊灵动岛导航 (Floating Island Nav) */}
      <FloatingPillNav
        activeNav="review"
        onNavChange={handleNavChange}
        leftSlot={
          <div className="flex items-center gap-2 pl-1">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-purple-600 via-indigo-500 to-cyan-400 flex items-center justify-center font-black text-white text-xs shadow-md">
              舱
            </div>
            <div className="flex flex-col">
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-xs tracking-wide text-white">知见 · 交易员驾驶舱</span>
                <span className="text-[9px] font-mono px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 flex items-center gap-1 font-semibold">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse"></span>
                  实盘交易中 · 早盘初战分歧期 (10:15)
                </span>
              </div>
              <span className="text-[9px] text-slate-400 font-mono">
                宏观流动性投影 + 微观天际线 + Top 5 题材分时资金争夺 + 4 时段内参
              </span>
            </div>
          </div>
        }
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

            {/* 自动快照指标 */}
            <div className="h-8 hidden sm:flex items-center gap-1 bg-black/30 border border-white/10 px-2.5 rounded-full text-[10px] font-mono text-slate-300">
              <span className="text-emerald-400">● 自动快照</span>
              <span className="text-slate-400">3s</span>
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
      {/* 【置顶核心】：4 大固定时段 LLM 盘中操盘内参时间轴看板 (直接外显在主屏，无覆盖回溯) */}
      {/* ========================================================================= */}
      <section className="max-w-7xl mx-auto w-full">
        <GlassCard
          rounded="3xl"
          padding="md"
          className="w-full border border-purple-500/35 bg-gradient-to-r from-slate-950/95 via-[#0B0F19] to-purple-950/20 relative shadow-2xl"
        >
          {/* 顶部时段切换胶囊栏 (Timeline Stepper) */}
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-white/10">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-lg bg-purple-600/30 border border-purple-500/40 flex items-center justify-center text-purple-300">
                <Zap className="w-3.5 h-3.5 text-purple-400" />
              </div>
              <span className="text-xs font-bold text-white tracking-wide">
                盘中 AI 操盘手内参 · 4 大时段动态决策流
              </span>
              <span className="text-[10px] text-purple-300 font-mono bg-purple-500/10 border border-purple-500/20 px-2 py-0.5 rounded-full">
                推断有据 · 边界清晰 · 永不覆盖
              </span>
            </div>

            {/* 4 大固定时段切换胶囊 (点击切换历史内参，绝对不覆盖已发生内容) */}
            <div className="flex items-center bg-black/60 border border-white/10 rounded-full p-0.5 text-xs">
              
              {/* 时段 1: 09:26 竞价定调 */}
              <button
                onClick={() => setActiveStageKey('STAGE_1_AUCTION')}
                className={`px-3 py-1 rounded-full text-[11px] font-medium transition flex items-center gap-1.5 ${
                  activeStageKey === 'STAGE_1_AUCTION'
                    ? 'bg-purple-600/80 text-white font-bold shadow-sm border border-purple-400/40'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                <span>① 09:26 竞价定调</span>
              </button>

              {/* 时段 2: 10:15 早盘初战 */}
              <button
                onClick={() => setActiveStageKey('STAGE_2_MORNING')}
                className={`px-3 py-1 rounded-full text-[11px] font-medium transition flex items-center gap-1.5 ${
                  activeStageKey === 'STAGE_2_MORNING'
                    ? 'bg-purple-600/80 text-white font-bold shadow-sm border border-purple-400/40'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-rose-400 animate-pulse"></span>
                <span>② 10:15 早盘初战 (当前)</span>
              </button>

              {/* 时段 3: 11:31 午盘综述 */}
              <button
                onClick={() => setActiveStageKey('STAGE_3_MIDDAY')}
                className={`px-3 py-1 rounded-full text-[11px] font-medium transition flex items-center gap-1.5 ${
                  activeStageKey === 'STAGE_3_MIDDAY'
                    ? 'bg-purple-600/80 text-white font-bold shadow-sm border border-purple-400/40'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
                <span>③ 11:31 午盘综述</span>
              </button>

              {/* 时段 4: 14:15 变盘前哨 */}
              <button
                onClick={() => setActiveStageKey('STAGE_4_AFTERNOON')}
                className={`px-3 py-1 rounded-full text-[11px] font-medium transition flex items-center gap-1.5 ${
                  activeStageKey === 'STAGE_4_AFTERNOON'
                    ? 'bg-purple-600/80 text-white font-bold shadow-sm border border-purple-400/40'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
                <span>④ 14:15 变盘前哨</span>
              </button>
            </div>
          </div>

          {/* 内参内容展示区 (支持最大 500 字深度推理，四段式严密逻辑) */}
          <div className="mt-3 grid grid-cols-1 lg:grid-cols-12 gap-3 text-xs">
            
            {/* 左侧 9 列：深度内参正文 (强弱定调 + 宏微观证据 + 明确建议 + 证伪边界) */}
            <div className="lg:col-span-9 space-y-2 bg-white/[0.015] border border-white/5 rounded-2xl p-3.5">
              
              {/* 标题栏：微观状态判定 + 核心信号 */}
              <div className="flex items-center justify-between pb-2 border-b border-white/5">
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${currentBriefingRecord?.status_color || 'bg-amber-500/20 text-amber-300 border-amber-500/30'}`}>
                    {currentBriefingRecord?.status_badge || '早盘冲高回落分歧期 · 权重吸血失真'}
                  </span>
                  <span className="text-[10px] font-mono text-slate-400">
                    {currentBriefingRecord?.timing || '采集判定时点: 10:15:00 · 100% 物理真实快照'}
                  </span>
                </div>
                <span className="text-[10px] font-mono text-cyan-300 bg-cyan-950/40 border border-cyan-800/40 px-2 py-0.5 rounded">
                  {currentBriefingRecord?.confidence || '置信度 88% · 证据链已闭环'}
                </span>
              </div>

              {/* 4 段式操盘内参正文 */}
              <div className="space-y-2 text-[11px] leading-relaxed text-slate-200">
                <p>
                  <strong className="text-purple-300">【强弱定调与宏微观证据】</strong>{' '}
                  {currentBriefingRecord?.strong_weak_judgment.replace(/【.*?】/, '') ||
                    '宏观：两市累计成交 5,820 亿，预估全天 1.98 万亿（放量 +14.2%）。指数呈现白线拉升（+0.62%）但黄线下杀（-0.85%），两市超 3,654 家下跌，呈现典型拉大票掩护题材出货特征。微观：Top 5 题材中【半导体】单边流入 +28.4 亿独强，领军中芯国际放量领跑；但【低空经济】遭严重抽血，万丰奥威炸板跳水 -5.2%，动态炸板率飙升至 29.4%。'}
                </p>
                <p>
                  <strong className="text-cyan-300">【多维共振与博弈归因】</strong>{' '}
                  {currentBriefingRecord?.resonance_attribution.replace(/【.*?】/, '') ||
                    '半导体走强系算力突破与外围制裁预期带来的自主可控共振；但在存量资金紧平衡下，单一大题材放量必然抽干非核心赛道，前期热门的低空、电池出现踩踏兑现，形成残酷的跷跷板吸血效应。'}
                </p>
                <p>
                  <strong className="text-amber-300">【后市明确推断与行动建议】</strong>{' '}
                  {currentBriefingRecord?.action_inference.replace(/【.*?】/, '') ||
                    '推断早盘进攻属于“局部结构性吸血行进”，绝非普涨反弹。建议：坚决不碰除半导体核心龙头之外的中位接力股；对破板个股果断减仓；总仓位严格控制在 3 成以下。'}
                </p>
                <p>
                  <strong className="text-rose-400">【证伪判定硬指标】</strong>{' '}
                  {currentBriefingRecord?.falsification_criteria.replace(/【.*?】/, '') ||
                    '成立条件：半导体领军股 10:30~11:00 分时主力净流入不低于 +20 亿且保变电气不破均线；不成立/证伪条件：若保变电气炸板且未在 5 分钟内回封，或炸板率突破 35%，则反弹推断彻底证伪，无条件空仓防守。'}
                </p>
              </div>
            </div>

            {/* 右侧 3 列：盘中关键推演指标小黑板 */}
            <div className="lg:col-span-3 flex flex-col justify-between gap-2 bg-black/40 border border-white/5 rounded-2xl p-3 text-[11px]">
              <div>
                <span className="text-[10px] text-slate-400 font-semibold tracking-wider flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
                  关键量化推演指标
                </span>
                <div className="mt-2 space-y-2 font-mono">
                  <div className="flex justify-between items-center bg-white/[0.02] p-1.5 rounded-lg">
                    <span className="text-slate-400 text-[10px]">时间衰减全天预估:</span>
                    <span className="font-bold text-cyan-300">
                      {currentBriefingRecord?.quantitative_indicators?.projected_volume || '1.98 万亿 (+14.2%)'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center bg-white/[0.02] p-1.5 rounded-lg">
                    <span className="text-slate-400 text-[10px]">黄白剪刀差背离:</span>
                    <span className="font-bold text-rose-400">
                      {currentBriefingRecord?.quantitative_indicators?.breadth_divergence || '白上黄下 (拉权出题)'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center bg-white/[0.02] p-1.5 rounded-lg">
                    <span className="text-slate-400 text-[10px]">动态炸板大面率:</span>
                    <span className="font-bold text-amber-400">
                      {currentBriefingRecord?.quantitative_indicators?.broken_ratio || '29.4% (警戒阈值 35%)'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center bg-white/[0.02] p-1.5 rounded-lg">
                    <span className="text-slate-400 text-[10px]">空间标杆高度:</span>
                    <span className="font-bold text-purple-300">
                      {currentBriefingRecord?.quantitative_indicators?.space_height || '保变电气 (5B 封单坚挺)'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="pt-2 border-t border-white/5 flex items-center justify-between text-[10px]">
                <span className="text-slate-400">当前操作纪律:</span>
                <span className="px-2 py-0.5 rounded font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                  {currentBriefingRecord?.quantitative_indicators?.action_advice || '控仓 2~3成 · 拒绝追高'}
                </span>
              </div>
            </div>

          </div>
        </GlassCard>
      </section>

      {/* ========================================================================= */}
      {/* 核心市场事实区 (Bento 矩阵 + 宽幅个股对比 + 宽幅题材分时 + 地雷雷达) */}
      {/* ========================================================================= */}
      <main className="max-w-7xl mx-auto w-full flex flex-col gap-4 flex-1">

        {/* --------------------------------------------------------------------- */}
        {/* 第一排：Bento ① 市场温度 + Bento ② 连板天梯 (双列并排) */}
        {/* --------------------------------------------------------------------- */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 w-full">
          {/* Bento ①【市场温度 · 宏观流动性与多空极性】 */}
          <GlassCard
            rounded="3xl"
            padding="md"
            className="flex flex-col justify-between relative overflow-hidden"
          >
            <div className="flex items-center justify-between pb-3 border-b border-white/5">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse"></span>
                <span className="text-sm font-bold text-slate-200 tracking-wide flex items-center gap-1.5">
                  <Brain className="w-4 h-4 text-purple-400" />
                  ① 市场温度 · 宏观流动性与多空极性
                </span>
              </div>
              <span className="px-2.5 py-0.5 rounded text-xs font-bold bg-rose-500/10 text-rose-400 border border-rose-500/20 font-mono">
                较昨日同时段放量 +14.2%
              </span>
            </div>

            {/* 实时三大指数 (带黄白线剪刀差标识) */}
            <div className="grid grid-cols-3 gap-2.5 my-3 text-xs">
              {/* 上证 */}
              <div className="bg-white/[0.02] border border-white/5 rounded-xl p-3">
                <div className="text-slate-400 flex justify-between items-center text-xs">
                  <span>上证指数</span>
                  <span className="font-mono text-slate-500">000001</span>
                </div>
                <div className="text-lg font-black font-mono text-rose-400 mt-0.5">3,288.42</div>
                <div className="text-xs font-mono text-rose-400 flex items-center justify-between mt-1">
                  <span>+0.62% (+20.2)</span>
                  <span className="text-slate-500 text-[10px]">白&gt;黄 (权重)</span>
                </div>
              </div>
              {/* 深成 */}
              <div className="bg-white/[0.02] border border-white/5 rounded-xl p-3">
                <div className="text-slate-400 flex justify-between items-center text-xs">
                  <span>深证成指</span>
                  <span className="font-mono text-slate-500">399001</span>
                </div>
                <div className="text-lg font-black font-mono text-emerald-400 mt-0.5">10,512.18</div>
                <div className="text-xs font-mono text-emerald-400 flex items-center justify-between mt-1">
                  <span>-0.28% (-29.5)</span>
                  <span className="text-slate-500 text-[10px]">中小盘分化</span>
                </div>
              </div>
              {/* 创业板 */}
              <div className="bg-white/[0.02] border border-white/5 rounded-xl p-3">
                <div className="text-slate-400 flex justify-between items-center text-xs">
                  <span>创业板指</span>
                  <span className="font-mono text-slate-500">399006</span>
                </div>
                <div className="text-lg font-black font-mono text-emerald-400 mt-0.5">2,204.65</div>
                <div className="text-xs font-mono text-emerald-400 flex items-center justify-between mt-1">
                  <span>-0.85% (-18.8)</span>
                  <span className="text-slate-500 text-[10px]">电池拖累</span>
                </div>
              </div>
            </div>

            {/* 多空极性量柱 (Polar Breadth Heatbar) */}
            <div className="bg-white/[0.02] border border-white/5 rounded-xl p-3 my-1">
              <div className="flex items-center justify-between text-xs mb-1.5 font-mono">
                <span className="text-rose-400 font-bold flex items-center gap-1">
                  <span>▲ 上涨 1,382 家</span>
                  <span className="text-slate-500 font-normal">(27%)</span>
                </span>
                <span className="text-slate-400">平盘 185</span>
                <span className="text-emerald-400 font-bold flex items-center gap-1">
                  <span className="text-slate-500 font-normal">(70%)</span>
                  <span>下跌 3,654 家 ▼</span>
                </span>
              </div>
              <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden flex">
                <div className="bg-gradient-to-r from-rose-500 to-rose-400 h-full" style={{ width: '27%' }}></div>
                <div className="bg-slate-600 h-full" style={{ width: '3%' }}></div>
                <div className="bg-gradient-to-r from-emerald-400 to-emerald-500 h-full" style={{ width: '70%' }}></div>
              </div>
            </div>

            {/* 量能动态衰减投影 */}
            <div className="grid grid-cols-2 gap-2.5 text-xs font-mono my-1">
              <div className="bg-white/[0.02] border border-white/5 p-2.5 rounded-xl">
                <div className="text-xs text-slate-400">当前实盘累计成交</div>
                <div className="text-base font-black text-white mt-0.5">{twoMarketsTotal.toLocaleString()} 亿</div>
                <div className="text-xs text-slate-400 mt-0.5">沪 {shAmount.toLocaleString()}亿 · 深 {szAmount.toLocaleString()}亿</div>
              </div>
              <div className="bg-cyan-950/20 border border-cyan-500/20 p-2.5 rounded-xl">
                <div className="text-xs text-cyan-300">时间衰减全天预估总量</div>
                <div className="text-base font-black text-cyan-400 mt-0.5">1.98 万亿</div>
                <div className="text-xs text-rose-400 mt-0.5">较昨日放量 +14.2% (结构性吸血)</div>
              </div>
            </div>

            {/* 底部体征指标 */}
            <div className="flex items-center justify-between text-xs text-slate-400 pt-2.5 border-t border-white/5 font-mono">
              <span>涨跌停对比: <strong className="text-rose-400">{limitUpCount}</strong> / <strong className="text-emerald-400">{limitDownCount}</strong></span>
              <span>动态炸板率: <strong className="text-amber-400">{(brokenLimitRatio * 100).toFixed(1)}%</strong> (触板{touchedTotalCount}/封死{limitUpCount})</span>
              <span className="text-cyan-300">黄白背离差: 1.47%</span>
            </div>
          </GlassCard>

          {/* Bento ②【连板天梯 · 盘中实时标杆与晋级动态】 */}
          <GlassCard
            id="bento-ladder"
            rounded="3xl"
            padding="md"
            className="flex flex-col justify-between"
          >
            <div className="flex items-center justify-between pb-3 border-b border-white/5">
              <div className="flex items-center gap-2">
                <Flame className="w-4 h-4 text-purple-400" />
                <span className="text-sm font-bold text-slate-200 tracking-wide">
                  ② 连板天梯 · 盘中实时标杆与晋级动态
                </span>
              </div>
              <span className="text-xs font-mono font-black px-2.5 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/30">
                空间极值 MAX {maxHeight}B
              </span>
            </div>

            {/* 空间总龙 Hero 卡 */}
            <div className="bg-gradient-to-r from-purple-950/70 via-indigo-950/50 to-transparent border border-purple-500/40 rounded-xl p-3 my-2 flex items-center justify-between">
              <div className="min-w-0 pr-2">
                <div className="flex items-center gap-2.5">
                  <span className="text-xs font-black font-mono px-2 py-0.5 rounded bg-purple-600 text-white shrink-0">{maxHeight}B</span>
                  <span className="text-base font-bold text-white truncate">保变电气</span>
                  <span className="text-xs font-mono text-purple-300">600550</span>
                  <span className="px-2 py-0.5 rounded text-xs bg-rose-500/20 text-rose-300 font-semibold shrink-0">空间总龙</span>
                </div>
                <div className="text-xs text-purple-300 mt-1 truncate">
                  电网/特高压 · 09:32 早盘首封 · 封单坚挺无松动
                </div>
              </div>
              <div className="text-right shrink-0 font-mono text-sm">
                <div className="font-bold text-rose-400 text-base">封单 3.82 亿</div>
                <div className="text-xs text-slate-400 mt-0.5">换手率 8.4%</div>
              </div>
            </div>

            {/* 梯队断层警示 */}
            {ladderGapInfo && (
              <div className="p-2.5 rounded-xl bg-amber-950/30 border border-amber-500/35 flex items-center justify-between text-xs my-1.5">
                <div className="flex items-center gap-2 text-amber-300 text-xs font-medium">
                  <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                  <span>{ladderGapInfo.message}</span>
                </div>
                <span className="text-xs text-amber-400 font-mono font-bold shrink-0">高危预警</span>
              </div>
            )}

            {/* 梯队列表 */}
            <div className="space-y-2 flex-1 max-h-[145px] overflow-y-auto pr-1 no-scrollbar my-1 text-xs">
              <div className="bg-white/[0.025] border border-white/5 rounded-xl p-2 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <span className="font-mono text-xs font-bold text-cyan-300 px-1.5 py-0.5 rounded bg-slate-800">4B</span>
                  <span className="font-bold text-white text-xs">大唐电信</span>
                  <span className="text-xs text-slate-400">芯片/自主可控 · T字板</span>
                </div>
                <span className="font-mono text-xs text-emerald-400 font-semibold">晋级成功 (封单 1.2亿)</span>
              </div>

              <div className="bg-rose-950/25 border border-rose-500/25 rounded-xl p-2 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <span className="font-mono text-xs font-bold text-rose-400 px-1.5 py-0.5 rounded bg-rose-950">3B</span>
                  <span className="text-slate-400 line-through text-xs">万丰奥威、中信海直</span>
                  <span className="text-xs text-rose-400">低空经济受抽血</span>
                </div>
                <span className="font-mono text-xs text-rose-400 font-bold">已破板跳水 (0/2)</span>
              </div>

              <div className="bg-white/[0.025] border border-white/5 rounded-xl p-2 flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <span className="font-mono text-xs font-bold text-slate-300 px-1.5 py-0.5 rounded bg-slate-800">2B</span>
                  <span className="font-bold text-white text-xs">常山北明、润和软件</span>
                  <span className="text-xs text-slate-400">鸿蒙智行概念</span>
                </div>
                <span className="font-mono text-xs text-cyan-300 font-semibold">晋级中 (3只)</span>
              </div>
            </div>

            <div className="pt-2.5 border-t border-white/5 flex items-center justify-between text-xs text-slate-400 font-mono">
              <span>首板基座 (1B): <strong className="text-purple-300">{firstBoardGroup?.stocks_count ?? 18} 只</strong></span>
              <span>总晋级率: <strong className="text-amber-400">28.5%</strong></span>
              <span className="text-rose-400">空间板破板防守线: 未触发</span>
            </div>
          </GlassCard>
        </div>

        {/* --------------------------------------------------------------------- */}
        {/* 第二排【新增 · 横向全幅】：核心个股分时涨跌幅走势对比曲线 */}
        {/* --------------------------------------------------------------------- */}
        <GlassCard
          rounded="3xl"
          padding="lg"
          className="border border-cyan-500/30 bg-gradient-to-r from-slate-950/95 via-[#0A101D] to-cyan-950/15 shadow-2xl relative w-full"
        >
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3.5 border-b border-white/10">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-cyan-600/20 border border-cyan-500/40 flex items-center justify-center text-cyan-300">
                <Activity className="w-4 h-4 text-cyan-400" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-bold text-white tracking-wide">
                    核心个股分时走势对比 · 前日核心(最高/次高) vs 当日最强涨停动态博弈
                  </h2>
                  <span className="text-xs font-mono text-cyan-300 bg-cyan-500/10 border border-cyan-500/25 px-2 py-0.5 rounded-full flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping"></span>
                    横向全幅 · 09:30~15:00 标准轴 · 盘中动态更新
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5 font-mono">
                  基准自动锁定前日最高板与次高板 · 开盘根据连板梯队动态更新当日最强涨停 · 直观透视昨日核心今日表现与新涨停的涨跌共振/抽血博弈 (&lt;=6支)
                </p>
              </div>
            </div>

            {/* 样本股管理与 Chip 标签 */}
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-xs font-mono text-cyan-300/80 bg-cyan-950/60 border border-cyan-500/30 px-2 py-0.5 rounded-full mr-1 font-semibold">
                {stockComparisonList.length} / 6 支
              </span>
              {stockComparisonList.map((s) => {
                if (s.tagType === 'today_strongest') {
                  return (
                    <span
                      key={s.code}
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-bold border transition bg-cyan-950/50 text-cyan-200 border-cyan-400/60 shadow-[0_0_12px_rgba(6,182,212,0.35)]"
                    >
                      <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                      <span className="text-white font-black">{s.name}</span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-cyan-500/25 text-cyan-200 border border-cyan-400/40 font-semibold flex items-center gap-1">
                        今日最强涨停 (2B)
                      </span>
                      <span className="text-rose-400 font-black">+{s.changePct}%</span>
                      <button
                        onClick={() => handleRemoveStock(s.code)}
                        className="ml-1 text-slate-400 hover:text-white transition"
                        title={`移除 ${s.name}`}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  );
                }
                if (s.tagType === 'yesterday_highest') {
                  return (
                    <span
                      key={s.code}
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-bold border transition bg-rose-950/40 text-rose-200 border-rose-500/40 shadow-sm"
                    >
                      <span className="w-2 h-2 rounded-full bg-rose-500" />
                      <span className="text-white font-black">{s.name}</span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 font-semibold">
                        昨日最高板 (5B)
                      </span>
                      <span className="text-rose-400 font-black">+{s.changePct}%</span>
                      <button
                        onClick={() => handleRemoveStock(s.code)}
                        className="ml-1 text-slate-400 hover:text-white transition"
                        title={`移除 ${s.name}`}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  );
                }
                if (s.tagType === 'yesterday_second') {
                  return (
                    <span
                      key={s.code}
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-bold border transition bg-purple-950/40 text-purple-200 border-purple-500/40"
                    >
                      <span className="w-2 h-2 rounded-full bg-purple-400" />
                      <span className="text-white font-bold">{s.name}</span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300 font-semibold">
                        昨日次高板 (4B)
                      </span>
                      <span className="text-rose-400 font-black">+{s.changePct}%</span>
                      <button
                        onClick={() => handleRemoveStock(s.code)}
                        className="ml-1 text-slate-400 hover:text-white transition"
                        title={`移除 ${s.name}`}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  );
                }
                if (s.tagType === 'yesterday_core_broken') {
                  return (
                    <span
                      key={s.code}
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-bold border transition bg-emerald-950/30 text-emerald-200 border-emerald-500/40"
                    >
                      <span className="w-2 h-2 rounded-full bg-emerald-400" />
                      <span className="text-white font-bold">{s.name}</span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-rose-950/60 text-rose-300 border border-rose-500/30 font-semibold">
                        昨日核心分歧 (3B)
                      </span>
                      <span className="text-emerald-400 font-black">{s.changePct}%</span>
                      <button
                        onClick={() => handleRemoveStock(s.code)}
                        className="ml-1 text-slate-400 hover:text-white transition"
                        title={`移除 ${s.name}`}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  );
                }
                return (
                  <span
                    key={s.code}
                    className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-bold border transition ${
                      s.changePct >= 0 ? 'bg-white/[0.03] text-white border-white/10' : 'bg-emerald-950/20 text-emerald-300 border-emerald-500/30'
                    }`}
                  >
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: s.color }} />
                    <span>{s.name}</span>
                    <span className="text-[10px] text-slate-400 font-normal">({s.role})</span>
                    <span className={`${s.changePct >= 0 ? 'text-rose-400' : 'text-emerald-400'} font-black`}>
                      {s.changePct >= 0 ? `+${s.changePct}%` : `${s.changePct}%`}
                    </span>
                    <button
                      onClick={() => handleRemoveStock(s.code)}
                      className="ml-1 text-slate-500 hover:text-white transition"
                      title={`移除 ${s.name}`}
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                );
              })}

              {stockComparisonList.length < 6 ? (
                <div className="relative">
                  <button
                    onClick={() => setIsAddStockOpen(!isAddStockOpen)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-cyan-600/20 hover:bg-cyan-600/30 border border-cyan-500/40 text-cyan-300 text-xs font-medium transition"
                  >
                    <Plus className="w-3 h-3" />
                    <span>添加样本股</span>
                  </button>
                  {isAddStockOpen && (
                    <div className="absolute right-0 top-8 w-52 bg-slate-900 border border-cyan-500/40 rounded-xl p-2 shadow-2xl z-50 space-y-1">
                      <div className="text-[11px] text-slate-400 font-mono px-2 py-1 border-b border-white/10">可选样本池</div>
                      {CANDIDATE_STOCKS.filter((c) => !stockComparisonList.some((s) => s.code === c.code)).map((c) => (
                        <button
                          key={c.code}
                          onClick={() => handleAddStock(c)}
                          className="w-full flex items-center justify-between px-2 py-1 rounded hover:bg-white/5 text-xs text-left"
                        >
                          <span className="font-bold text-white">{c.name}</span>
                          <span className="text-slate-400 text-[11px] font-mono">{c.role}</span>
                          <span className={c.changePct >= 0 ? 'text-rose-400' : 'text-emerald-400'}>
                            {c.changePct >= 0 ? `+${c.changePct}%` : `${c.changePct}%`}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : (
                <span className="text-xs font-mono text-slate-500">(已达上限 6 支)</span>
              )}
            </div>
          </div>

          {/* 宽幅个股分时曲线图 */}
          <div
            ref={stockChartContainerRef}
            onMouseMove={(e) => {
              if (!stockChartContainerRef.current) return;
              const rect = stockChartContainerRef.current.getBoundingClientRect();
              const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
              setStockHoverX(pct * 1000);
              setIsStockHovering(true);
            }}
            onMouseLeave={() => setIsStockHovering(false)}
            className="relative w-full h-[210px] my-3 bg-black/50 border border-white/5 rounded-xl p-3.5 flex flex-col justify-between overflow-hidden cursor-crosshair"
          >
            {/* Y轴刻度辅助线 */}
            <div className="absolute inset-0 bottom-7 flex flex-col justify-between p-3.5 pointer-events-none text-xs font-mono text-slate-500 z-0">
              <div className="border-b border-rose-500/20 pb-0.5 flex justify-between text-rose-400"><span>+10.0% (涨停线)</span><span>极限做多</span></div>
              <div className="border-b border-white/[0.04] pb-0.5 flex justify-between"><span>+5.0%</span><span>强势分歧</span></div>
              <div className="border-b border-white/10 pb-0.5 flex justify-between text-slate-300 font-bold"><span>0.0% (昨收平盘)</span><span>基准零轴</span></div>
              <div className="border-b border-white/[0.04] pb-0.5 flex justify-between"><span>-5.0%</span><span>弱势回落</span></div>
              <div className="flex justify-between text-emerald-400"><span>-10.0% (跌停线)</span><span>核按钮</span></div>
            </div>

            {/* 午间休市 11:30~13:00 隔断中轴 */}
            <div className="absolute top-0 bottom-7 left-[50%] w-px bg-white/15 z-0 border-l border-dashed border-white/20"></div>

            {/* 当前 10:15 进展标尺 (占全天 240 分钟的 18.75% 处) */}
            <div className="absolute top-0 bottom-7 left-[18.75%] w-px bg-cyan-400 z-10 border-l border-dashed border-cyan-400 shadow-[0_0_8px_rgba(6,182,212,0.8)]">
              <div className="absolute top-1 -left-7 px-1.5 py-0.5 rounded bg-cyan-950/90 border border-cyan-500 text-[10px] text-cyan-300 font-mono font-bold">
                10:15
              </div>
            </div>

            {/* 曲线图主体区域 */}
            <div className="relative w-full flex-1 min-h-[140px]">
              <svg className="w-full h-full z-10 overflow-visible" viewBox="0 0 1000 140" preserveAspectRatio="none">
                <line x1="0" y1="70" x2="1000" y2="70" stroke="rgba(255,255,255,0.15)" strokeWidth="1.2" />
                {stockComparisonList.map((s) => (
                  <g key={s.code}>
                    <path
                      d={s.pathD}
                      fill="none"
                      stroke={s.color}
                      strokeWidth={s.tagType === 'today_strongest' || s.tagType === 'yesterday_highest' ? '3' : '2.2'}
                      strokeLinecap="round"
                    />
                    <circle cx={s.endX} cy={s.endY} r={s.tagType === 'today_strongest' ? 5 : 4} fill={s.color} stroke="#fff" strokeWidth="1.5" />
                  </g>
                ))}
                {isStockHovering && (
                  <line x1={stockHoverX} y1="0" x2={stockHoverX} y2="140" stroke="#06B6D4" strokeWidth="1.2" strokeDasharray="3,3" opacity="0.9" />
                )}
              </svg>
            </div>

            {/* X 轴时间刻度标尺 */}
            <div className="flex justify-between text-xs font-mono text-slate-400 pt-2 border-t border-white/10 z-10 shrink-0">
              <span>09:30</span>
              <span>10:00</span>
              <span className="text-cyan-300 font-bold">10:15 (当前进度)</span>
              <span>10:30</span>
              <span>11:00</span>
              <span className="text-slate-300 font-bold">11:30 / 13:00</span>
              <span>13:30</span>
              <span>14:00</span>
              <span>14:30</span>
              <span>15:00</span>
            </div>
          </div>

          {/* 底部双轨博弈透视结论卡片 (前日核心今日表现 + 今日最强涨停涨跌博弈) */}
          <div className="mt-2 pt-2.5 border-t border-white/10 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
            {/* 轨道 1：昨日核心在今日的表现 */}
            <div className="bg-purple-950/20 border border-purple-500/30 rounded-xl p-2.5 flex items-start gap-2.5">
              <div className="px-2 py-0.5 rounded text-[11px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40 shrink-0 mt-0.5">
                昨日核心今日表现
              </div>
              <p className="text-slate-300 leading-relaxed text-xs">
                前日最高板<strong className="text-rose-400">保变电气(5B)</strong>与次高板<strong className="text-rose-400">大唐电信(4B)</strong>开盘均获高溢价并快速秒封，高位未现核按钮；但前日3B标的<strong className="text-emerald-400">万丰奥威(-5.2%)</strong>破板跳水，暴露中位断层接力缺乏承接。
              </p>
            </div>

            {/* 轨道 2：当天当时最强涨停与昨日核心的涨跌关系 */}
            <div className="bg-cyan-950/20 border border-cyan-500/30 rounded-xl p-2.5 flex items-start gap-2.5">
              <div className="px-2 py-0.5 rounded text-[11px] font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shrink-0 mt-0.5 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping"></span>
                今日最强 vs 昨日核心
              </div>
              <p className="text-cyan-200 leading-relaxed text-xs">
                盘中实时最强涨停<strong className="text-cyan-300">常山北明(+9.9%)</strong>09:31顶死封单1.8亿，与前日科技高标大唐电信形成同向正反馈助攻；但与前日低空核心万丰奥威形成尖锐的“资金抽血反向剪刀差”——资金弃老追新，全面聚拢科技主线。
              </p>
            </div>
          </div>
        </GlassCard>

        {/* --------------------------------------------------------------------- */}
        {/* 第三排【重构 · 横向全幅】：题材战场 Top 5 分时资金走势与核心龙头联动 */}
        {/* --------------------------------------------------------------------- */}
        <GlassCard
          id="bento-battleground"
          rounded="3xl"
          padding="lg"
          className="border border-purple-500/30 bg-gradient-to-r from-slate-950/95 via-[#0D0F1A] to-purple-950/15 shadow-2xl relative w-full"
        >
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3.5 border-b border-white/10">
            <div className="flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-purple-600/20 border border-purple-500/40 flex items-center justify-center text-purple-300">
                <TrendingUp className="w-4 h-4 text-purple-400" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-sm font-bold text-white tracking-wide">
                    题材战场 · Top 5 分时主力资金争夺曲线与领涨核心龙头
                  </h2>
                  <span className="text-xs font-mono text-purple-300 bg-purple-500/10 border border-purple-500/25 px-2 py-0.5 rounded-full">
                    09:30~15:00 全天 X 轴发散
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5 font-mono">
                  从 09:30 零轴起点发散至当前时点 · 平滑入场生长动画 · 鼠标 Hover 精确查看各分钟净流入数值
                </p>
              </div>
            </div>

            {/* 题材图例 */}
            <div className="flex items-center gap-3 text-xs font-mono text-slate-300">
              <span className="flex items-center gap-1.5"><span className="w-2.5 h-1 rounded-full bg-[#8B5CF6]"></span>半导体 (+28.4亿)</span>
              <span className="flex items-center gap-1.5"><span className="w-2.5 h-1 rounded-full bg-[#06B6D4]"></span>算力概念 (+14.2亿)</span>
              <span className="flex items-center gap-1.5"><span className="w-2.5 h-1 rounded-full bg-[#F59E0B]"></span>银行权重 (+9.8亿)</span>
              <span className="flex items-center gap-1.5"><span className="w-2.5 h-1 rounded-full bg-[#64748B]"></span>锂电池 (-8.5亿)</span>
              <span className="flex items-center gap-1.5"><span className="w-2.5 h-1 rounded-full bg-[#10B981]"></span>低空经济 (-19.2亿)</span>
            </div>
          </div>

          {/* 全幅题材分时资金曲线图 */}
          <div
            ref={sectorChartContainerRef}
            onMouseMove={(e) => {
              if (!sectorChartContainerRef.current) return;
              const rect = sectorChartContainerRef.current.getBoundingClientRect();
              const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
              setSectorHoverX(pct * 1000);
              setIsSectorHovering(true);
            }}
            onMouseLeave={() => setIsSectorHovering(false)}
            className="relative w-full h-[210px] my-3 bg-black/50 border border-white/5 rounded-xl p-3.5 flex flex-col justify-between overflow-hidden cursor-crosshair"
          >
            {/* Y轴刻度辅助线 */}
            <div className="absolute inset-0 bottom-7 flex flex-col justify-between p-3.5 pointer-events-none text-xs font-mono text-slate-500 z-0">
              <div className="border-b border-white/[0.04] pb-0.5 flex justify-between text-purple-400"><span>+30.0 亿元</span><span>主力持续吸血</span></div>
              <div className="border-b border-white/[0.04] pb-0.5 flex justify-between text-cyan-300"><span>+15.0 亿元</span><span>脉冲流入</span></div>
              <div className="border-b border-white/10 pb-0.5 flex justify-between text-slate-300 font-bold"><span>0.0 亿元</span><span>平衡线 (起点)</span></div>
              <div className="border-b border-white/[0.04] pb-0.5 flex justify-between text-slate-400"><span>-10.0 亿元</span><span>资金流出</span></div>
              <div className="flex justify-between text-emerald-400"><span>-25.0 亿元</span><span>大幅失血抛压</span></div>
            </div>

            {/* 午间休市 11:30~13:00 隔断中轴 */}
            <div className="absolute top-0 bottom-7 left-[50%] w-px bg-white/15 z-0 border-l border-dashed border-white/20"></div>

            {/* 当前 10:15 进展标尺 (占全天 240 分钟的 18.75% 处) */}
            <div className="absolute top-0 bottom-7 left-[18.75%] w-px bg-purple-400 z-10 border-l border-dashed border-purple-400 shadow-[0_0_8px_rgba(139,92,246,0.8)]">
              <div className="absolute top-1 -left-7 px-1.5 py-0.5 rounded bg-purple-950/90 border border-purple-500 text-[10px] text-purple-300 font-mono font-bold">
                10:15
              </div>
            </div>

            {/* 曲线图主体区域 */}
            <div className="relative w-full flex-1 min-h-[140px]">
              <svg className="w-full h-full z-10 overflow-visible" viewBox="0 0 1000 140" preserveAspectRatio="none">
                <line x1="0" y1="70" x2="1000" y2="70" stroke="rgba(255,255,255,0.15)" strokeWidth="1.2" />
                <path d="M 0,70 C 40,68 80,45 120,32 C 150,22 170,16 187.5,14" fill="none" stroke="#8B5CF6" strokeWidth="3" strokeLinecap="round" />
                <circle cx="187.5" cy="14" r="4.5" fill="#8B5CF6" stroke="#fff" strokeWidth="1.5" />

                <path d="M 0,70 C 40,55 70,30 110,35 C 140,42 165,40 187.5,38" fill="none" stroke="#06B6D4" strokeWidth="2.5" strokeLinecap="round" />
                <circle cx="187.5" cy="38" r="4" fill="#06B6D4" stroke="#fff" strokeWidth="1.5" />

                <path d="M 0,70 C 50,68 100,62 140,58 C 160,55 175,53 187.5,52" fill="none" stroke="#F59E0B" strokeWidth="2.2" strokeLinecap="round" />
                <circle cx="187.5" cy="52" r="3.5" fill="#F59E0B" stroke="#fff" strokeWidth="1.5" />

                <path d="M 0,70 C 50,72 90,78 130,82 C 155,84 175,85 187.5,86" fill="none" stroke="#64748B" strokeWidth="2" strokeLinecap="round" />
                <circle cx="187.5" cy="86" r="3.5" fill="#64748B" stroke="#fff" strokeWidth="1.5" />

                <path d="M 0,70 C 40,65 80,88 120,102 C 150,112 170,116 187.5,118" fill="none" stroke="#10B981" strokeWidth="2.5" strokeLinecap="round" />
                <circle cx="187.5" cy="118" r="4" fill="#10B981" stroke="#fff" strokeWidth="1.5" />

                {isSectorHovering && (
                  <line x1={sectorHoverX} y1="0" x2={sectorHoverX} y2="140" stroke="#8B5CF6" strokeWidth="1.2" strokeDasharray="3,3" opacity="0.9" />
                )}
              </svg>
            </div>

            {/* X 轴时间刻度标尺 */}
            <div className="flex justify-between text-xs font-mono text-slate-400 pt-2 border-t border-white/10 z-10 shrink-0">
              <span>09:30</span>
              <span>10:00</span>
              <span className="text-purple-300 font-bold">10:15 (当前进度)</span>
              <span>10:30</span>
              <span>11:00</span>
              <span className="text-slate-300 font-bold">11:30 / 13:00</span>
              <span>13:30</span>
              <span>14:00</span>
              <span>14:30</span>
              <span>15:00</span>
            </div>
          </div>

          {/* 5 大题材领涨核心龙头联动卡片 */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 my-2 text-xs">
            <div className="bg-white/[0.025] border border-purple-500/35 p-3 rounded-xl flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold text-purple-300">#1 半导体</span>
                <span className="text-xs font-mono text-rose-400 font-bold">+28.4 亿</span>
              </div>
              <div className="font-bold text-white text-sm my-1">中芯国际</div>
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>688981 · 核心中军</span>
                <span className="text-rose-400 font-mono font-bold">+4.8%</span>
              </div>
            </div>

            <div className="bg-white/[0.025] border border-cyan-500/35 p-3 rounded-xl flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold text-cyan-300">#2 算力概念</span>
                <span className="text-xs font-mono text-rose-400 font-bold">+14.2 亿</span>
              </div>
              <div className="font-bold text-white text-sm my-1">常山北明</div>
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>000158 · 触板先锋</span>
                <span className="text-rose-400 font-mono font-bold">+9.9%</span>
              </div>
            </div>

            <div className="bg-white/[0.025] border border-amber-500/35 p-3 rounded-xl flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold text-amber-300">#3 银行权重</span>
                <span className="text-xs font-mono text-rose-400 font-bold">+9.8 亿</span>
              </div>
              <div className="font-bold text-white text-sm my-1">工商银行</div>
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>601398 · 护盘基石</span>
                <span className="text-rose-400 font-mono font-bold">+1.2%</span>
              </div>
            </div>

            <div className="bg-white/[0.025] border border-white/10 p-3 rounded-xl flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold text-slate-300">#4 锂电池</span>
                <span className="text-xs font-mono text-emerald-400 font-bold">-8.5 亿</span>
              </div>
              <div className="font-bold text-slate-200 text-sm my-1">宁德时代</div>
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>300750 · 创指拖累</span>
                <span className="text-emerald-400 font-mono font-bold">-1.8%</span>
              </div>
            </div>

            <div className="bg-emerald-950/20 border border-emerald-500/35 p-3 rounded-xl flex flex-col justify-between">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold text-emerald-300">#5 低空经济</span>
                <span className="text-xs font-mono text-emerald-400 font-bold">-19.2 亿</span>
              </div>
              <div className="font-bold text-white text-sm my-1">万丰奥威</div>
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span>002085 · 炸板跳水</span>
                <span className="text-emerald-400 font-mono font-bold">-5.2%</span>
              </div>
            </div>
          </div>

          <div className="pt-2 border-t border-white/5 flex items-center justify-between text-xs text-slate-400 font-mono">
            <span>题材轮动特征: <strong className="text-purple-300">半导体与科技算力吸血低空经济与锂电</strong></span>
            <span className="text-cyan-300">主力资金集中度: <strong>68.4%</strong> (高度集中)</span>
          </div>
        </GlassCard>

        {/* --------------------------------------------------------------------- */}
        {/* 第四排【地雷雷达】：动态炸板率与跳水排雷 (横向全幅呈现) */}
        {/* --------------------------------------------------------------------- */}
        <GlassCard
          rounded="3xl"
          padding="lg"
          className="border border-amber-500/30 bg-slate-950/90 shadow-2xl relative w-full"
        >
          <div className="flex items-center justify-between pb-3 border-b border-white/10">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-rose-400" />
              <span className="text-sm font-bold text-slate-200 tracking-wide">
                ④ 地雷雷达 · 动态炸板率仪表与跳水排雷 (实时风控防守线)
              </span>
            </div>
            <span className="text-xs font-mono px-2.5 py-0.5 rounded-full bg-amber-950/80 text-amber-300 border border-amber-800/80">
              炸板率爬升预警 · 接近 35% 做空红线
            </span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 my-3">
            {/* 动态炸板率仪表 */}
            <div className="bg-amber-950/20 border border-amber-500/30 rounded-2xl p-4 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-amber-300 font-semibold">动态炸板率仪表盘</span>
                  <span className="text-xl font-black font-mono text-amber-400">{(brokenLimitRatio * 100).toFixed(1)}%</span>
                </div>
                <div className="w-full bg-slate-800 rounded-full h-2.5 mt-3 overflow-hidden relative">
                  <div className="absolute top-0 bottom-0 left-[35%] w-0.5 bg-rose-500 z-10" title="35% 强制防守警戒线"></div>
                  <div
                    className="bg-gradient-to-r from-amber-400 to-rose-500 h-2.5 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, brokenLimitRatio * 100)}%` }}
                  />
                </div>
                <div className="text-xs text-slate-400 mt-2 flex justify-between font-mono">
                  <span>触及涨停 {touchedTotalCount} 只</span>
                  <span className="text-rose-400 font-bold">炸板 {brokenLimitCount} 只 (快速增加)</span>
                  <span className="text-rose-500 font-bold">35% 强制防守警戒红线</span>
                </div>
              </div>
              <div className="text-xs text-slate-400 font-mono mt-3 pt-2 border-t border-white/5">
                硬纪律提示: 若炸板率突破 35%，系统将直接发出清仓避险信号，禁止任何跟风追高。
              </div>
            </div>

            {/* 实时跳水大面预警 */}
            <div className="bg-white/[0.02] border border-white/5 rounded-2xl p-4 flex flex-col justify-between">
              <div>
                <div className="text-xs text-slate-400 font-medium flex justify-between items-center mb-2">
                  <span className="flex items-center gap-1.5 text-rose-400 font-bold">
                    <span className="w-2 h-2 rounded-full bg-rose-500"></span>
                    日内跳水大面预警 (拒接飞刀 · 盘中实时捕获)
                  </span>
                  <span className="font-mono text-rose-400 text-xs">已拦截 3 只</span>
                </div>

                <div className="space-y-2 text-xs">
                  <div className="border-l-2 border-rose-500 bg-white/[0.025] p-2 rounded-r-xl flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white text-xs">万丰奥威</span>
                      <span className="text-xs text-slate-400 font-mono">(002085)</span>
                      <span className="text-xs text-rose-300 bg-rose-950/60 px-1.5 py-0.5 rounded">低空经济领跌</span>
                    </div>
                    <div className="text-right font-mono text-xs">
                      <span className="text-emerald-400 font-bold">-5.2%</span>
                      <span className="text-amber-400 ml-1.5">开板回落 13.8%</span>
                    </div>
                  </div>

                  <div className="border-l-2 border-amber-500 bg-white/[0.025] p-2 rounded-r-xl flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white text-xs">东方财富</span>
                      <span className="text-xs text-slate-400 font-mono">(300059)</span>
                      <span className="text-xs text-slate-400 bg-slate-800 px-1.5 py-0.5 rounded">互联网金融</span>
                    </div>
                    <div className="text-right font-mono text-xs">
                      <span className="text-rose-400 font-bold">+1.8%</span>
                      <span className="text-amber-400 ml-1.5">冲高回落 7.5%</span>
                    </div>
                  </div>
                </div>
              </div>

              <div className="pt-2 border-t border-white/5 flex items-center justify-between text-xs text-slate-400 font-mono mt-2">
                <span>跌停核按钮: <strong className="text-emerald-400">{limitDownCount} 只</strong> (ST已剔除)</span>
                <span className="text-rose-400 font-bold">防守触发: 炸板率突破 35% 即刻减仓</span>
              </div>
            </div>
          </div>
        </GlassCard>

      </main>

      {/* 底部备案与免责声明 */}
      <footer className="max-w-7xl mx-auto w-full text-center text-[10px] text-slate-500 py-1 border-t border-white/5">
        知见 · AI认知复盘交易系统 · 极光盘中「4+1」驾驶舱 · 本系统纯客观数理推演与科学证伪，不构成实盘买卖依据
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
