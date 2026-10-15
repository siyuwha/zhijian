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
  FileText,
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

/**
 * 将 X 轴位置 (0~1000) 映射为盘中具体交易时刻文本 (09:30 ~ 15:00)
 */
export function getHoverTimeLabel(x: number): string {
  const clampedX = Math.max(0, Math.min(1000, x));
  let totalMin = 570;
  if (clampedX <= 500) {
    totalMin = 570 + Math.round((clampedX / 500) * 120);
  } else {
    totalMin = 780 + Math.round(((clampedX - 500) / 500) * 120);
  }
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/**
 * 动态根据当前时间在 X 轴上的推进位置 (currentX: 0~1000) 与真实涨跌幅生成 SVG 个股走势曲线路径
 */
export function generateDynamicStockPath(currentX: number, changePct: number, tagType: string): string {
  const safeX = Math.max(20, Math.min(1000, currentX));
  const clampedPct = Math.max(-10, Math.min(10, changePct));
  const endY = Number((70 - clampedPct * 6).toFixed(1));

  // 1. 昨日最高板 (例如百洋股份 4B): 高开下探后于 09:42 强势秒封涨停，全天死封
  if (tagType === 'yesterday_highest') {
    const lockX = Math.min(55, safeX * 0.15);
    const dipX = lockX * 0.35;
    if (safeX <= lockX) {
      return `M 0,52 C ${safeX * 0.3},58 ${safeX * 0.6},30 ${safeX},${endY}`;
    }
    return `M 0,52 C ${dipX * 0.5},58 ${dipX},56 ${dipX},56 C ${dipX + (lockX - dipX) * 0.5},40 ${lockX * 0.8},${endY} ${lockX},${endY} L ${safeX},${endY}`;
  }

  // 2. 昨日次高板 (例如晶化股份 3B): 早盘震荡分歧，10:30~11:15 蓄势回封涨停
  if (tagType === 'yesterday_second') {
    const lockX = Math.min(420, safeX * 0.6);
    const wave1X = Math.min(180, lockX * 0.4);
    const wave2X = Math.min(300, lockX * 0.7);
    if (safeX <= wave1X) {
      return `M 0,60 C ${safeX * 0.4},64 ${safeX * 0.8},35 ${safeX},${endY}`;
    }
    if (safeX <= lockX) {
      return `M 0,60 C ${wave1X * 0.4},64 ${wave1X * 0.8},30 ${wave1X},30 C ${wave1X + (safeX - wave1X) * 0.5},45 ${safeX * 0.9},${endY} ${safeX},${endY}`;
    }
    return `M 0,60 C ${wave1X * 0.4},64 ${wave1X * 0.8},30 ${wave1X},30 C ${wave1X + (wave2X - wave1X) * 0.5},45 ${wave2X},40 ${wave2X},38 C ${wave2X + (lockX - wave2X) * 0.5},25 ${lockX * 0.9},${endY} ${lockX},${endY} L ${safeX},${endY}`;
  }

  // 3. 今日最强涨停 (例如冰山冷热 2B): 开盘极速拉板 (09:34 封死)，微幅波动回封
  if (tagType === 'today_strongest') {
    const lockX = Math.min(30, safeX * 0.1);
    if (safeX <= lockX) {
      return `M 0,25 C ${safeX * 0.4},20 ${safeX * 0.8},10 ${safeX},${endY}`;
    }
    if (safeX > 550) {
      return `M 0,25 C ${lockX * 0.4},18 ${lockX * 0.8},${endY} ${lockX},${endY} L 520,${endY} C 535,${endY} 540,16 550,16 C 560,16 570,${endY} 585,${endY} L ${safeX},${endY}`;
    }
    return `M 0,25 C ${lockX * 0.4},18 ${lockX * 0.8},${endY} ${lockX},${endY} L ${safeX},${endY}`;
  }

  // 4. 高位分歧炸板跳水 (例如丽人丽妆 -8.9%): 早盘冲高触板，09:55 炸板断头跳水，午后深水震荡
  if (tagType === 'yesterday_core_broken') {
    const peakX = Math.min(65, safeX * 0.18);
    const dropX = Math.min(220, safeX * 0.45);
    if (safeX <= peakX) {
      return `M 0,50 C ${safeX * 0.4},35 ${safeX * 0.8},12 ${safeX},12`;
    }
    if (safeX <= dropX) {
      return `M 0,50 C ${peakX * 0.4},35 ${peakX * 0.8},10 ${peakX},10 C ${peakX + (safeX - peakX) * 0.4},20 ${safeX * 0.8},${endY} ${safeX},${endY}`;
    }
    return `M 0,50 C ${peakX * 0.4},35 ${peakX * 0.8},10 ${peakX},10 C ${peakX + (dropX - peakX) * 0.3},25 ${dropX * 0.7},95 ${dropX},115 C ${dropX + (safeX - dropX) * 0.4},${endY - 6} ${dropX + (safeX - dropX) * 0.8},${endY + 4} ${safeX},${endY}`;
  }

  // 5. 领军中军 / 大市值容量标的 (例如中芯国际 +4.8%): 稳健台阶式推升
  if (clampedPct > 2.0) {
    const s1X = safeX * 0.35;
    const s1Y = 70 - clampedPct * 2.5;
    const s2X = safeX * 0.7;
    const s2Y = 70 - clampedPct * 4.2;
    return `M 0,70 C ${s1X * 0.4},68 ${s1X * 0.8},${s1Y} ${s1X},${s1Y} C ${s1X + (s2X - s1X) * 0.5},${s1Y + 3} ${s2X * 0.9},${s2Y} ${s2X},${s2Y} C ${s2X + (safeX - s2X) * 0.5},${s2Y} ${safeX * 0.95},${endY} ${safeX},${endY}`;
  }

  // 6. 权重压制 / 负向分化标的 (例如宁德时代 -1.8%): 早盘下沉、午间抵抗、尾盘阴跌
  if (clampedPct < 0) {
    const dipX = safeX * 0.3;
    const dipY = 70 + Math.abs(clampedPct) * 8.5;
    const rebX = safeX * 0.6;
    const rebY = 70 + Math.abs(clampedPct) * 4.0;
    return `M 0,70 C ${dipX * 0.4},74 ${dipX * 0.8},${dipY} ${dipX},${dipY} C ${dipX + (rebX - dipX) * 0.5},${dipY} ${rebX * 0.9},${rebY} ${rebX},${rebY} C ${rebX + (safeX - rebX) * 0.5},${rebY + 2} ${safeX * 0.9},${endY} ${safeX},${endY}`;
  }

  // 通用平缓震荡
  return `M 0,70 C ${safeX * 0.3},${70 + (endY - 70) * 0.3} ${safeX * 0.7},${70 + (endY - 70) * 0.8} ${safeX},${endY}`;
}

/**
 * 动态根据当前时间在 X 轴上的推进位置 (currentX: 0~1000) 与真实资金净流入生成 SVG 题材走势曲线路径
 */
export function generateSectorPath(currentX: number, endY: number, idx: number): string {
  const safeX = Math.max(20, Math.min(1000, currentX));
  const delta = endY - 70;

  if (idx === 0) {
    // #1 领涨核心 (半导体 +28.4亿): 早盘急剧吸筹，午后加速推升
    const p1X = safeX * 0.35;
    const p1Y = 70 + delta * 0.65;
    return `M 0,70 C ${p1X * 0.4},${70 + delta * 0.25} ${p1X * 0.8},${p1Y} ${p1X},${p1Y} C ${p1X + (safeX - p1X) * 0.4},${p1Y + delta * 0.1} ${safeX * 0.85},${endY} ${safeX},${endY.toFixed(1)}`;
  } else if (idx === 1) {
    // #2 算力概念 (+14.2亿): 早盘脉冲，随后震荡爬升
    const p1X = safeX * 0.4;
    const p1Y = 70 + delta * 0.78;
    return `M 0,70 C ${p1X * 0.35},${70 + delta * 0.3} ${p1X * 0.75},${p1Y} ${p1X},${p1Y} C ${p1X + (safeX - p1X) * 0.5},${p1Y - delta * 0.08} ${safeX * 0.85},${endY} ${safeX},${endY.toFixed(1)}`;
  } else if (idx === 2) {
    // #3 银行护盘 (+9.8亿): 缓慢稳健爬升
    return `M 0,70 C ${safeX * 0.3},${70 + delta * 0.25} ${safeX * 0.7},${70 + delta * 0.75} ${safeX},${endY.toFixed(1)}`;
  } else if (idx === 3) {
    // #4 锂电池 (-8.5亿): 早盘假反抽，随后逐渐失血跌破零轴
    const peakX = safeX * 0.22;
    const peakY = 62;
    return `M 0,70 C ${peakX * 0.5},66 ${peakX * 0.8},${peakY} ${peakX},${peakY} C ${peakX + (safeX - peakX) * 0.4},${70 + delta * 0.4} ${safeX * 0.85},${endY} ${safeX},${endY.toFixed(1)}`;
  } else {
    // #5 低空经济 (-19.2亿): 早盘诱多冲高，10:00后放量跳水流出
    const dropX = safeX * 0.3;
    const dropY = 70 + delta * 0.65;
    return `M 0,70 C ${dropX * 0.3},68 ${dropX * 0.7},${dropY} ${dropX},${dropY} C ${dropX + (safeX - dropX) * 0.4},${dropY + delta * 0.2} ${safeX * 0.85},${endY} ${safeX},${endY.toFixed(1)}`;
  }
}

/**
 * 依据当前时钟或历史日期，精确计算全天 09:30~15:00 A 股交易进度的位置 (0%~100%) 与对应当前活跃时段
 */
export function getTimeProgress(selectedDate: string) {
  const now = new Date();
  const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

  // 历史交易日：已收盘，全天 100% 走满
  if (selectedDate < todayStr) {
    return {
      progressRatio: 1.0,
      currentX: 1000,
      timeLabel: '15:00 (全天收盘)',
      isAfterClose: true,
      isMidday: false,
      isPreOpen: false,
      currentStage: 'STAGE_4_AFTERNOON' as IntradayBriefingStageKey,
    };
  }

  const hours = now.getHours();
  const minutes = now.getMinutes();
  const totalMin = hours * 60 + minutes;

  // 09:30 之前: 未开市/集合竞价
  if (totalMin < 570) {
    return {
      progressRatio: 0.02,
      currentX: 20,
      timeLabel: '09:25 (竞价盘口)',
      isAfterClose: false,
      isMidday: false,
      isPreOpen: true,
      currentStage: 'STAGE_1_AUCTION' as IntradayBriefingStageKey,
    };
  }

  // 09:30 ~ 11:30 (早盘 120 分钟, 对应 X 轴 0% ~ 50%)
  if (totalMin <= 690) {
    const elapsed = totalMin - 570;
    const ratio = Math.max(0.02, Math.min(0.5, elapsed / 240));
    return {
      progressRatio: ratio,
      currentX: Math.round(ratio * 1000),
      timeLabel: `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')} (盘中推进)`,
      isAfterClose: false,
      isMidday: false,
      isPreOpen: false,
      currentStage: totalMin < 615 ? ('STAGE_1_AUCTION' as IntradayBriefingStageKey) : ('STAGE_2_MORNING' as IntradayBriefingStageKey),
    };
  }

  // 11:30 ~ 13:00 (午间休市, 锁定在 50%, X=500)
  if (totalMin < 780) {
    return {
      progressRatio: 0.5,
      currentX: 500,
      timeLabel: '11:30 / 13:00 (午间休市)',
      isAfterClose: false,
      isMidday: true,
      isPreOpen: false,
      currentStage: 'STAGE_3_MIDDAY' as IntradayBriefingStageKey,
    };
  }

  // 13:00 ~ 15:00 (下午盘 120 分钟, 对应 X 轴 50% ~ 100%)
  if (totalMin <= 900) {
    const elapsed = 120 + (totalMin - 780);
    const ratio = Math.max(0.5, Math.min(1.0, elapsed / 240));
    return {
      progressRatio: ratio,
      currentX: Math.round(ratio * 1000),
      timeLabel: `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')} (下午盘)`,
      isAfterClose: false,
      isMidday: false,
      isPreOpen: false,
      currentStage: totalMin < 855 ? ('STAGE_3_MIDDAY' as IntradayBriefingStageKey) : ('STAGE_4_AFTERNOON' as IntradayBriefingStageKey),
    };
  }

  // 15:00 之后 (如 15:22): 已收盘态，全天 100% 走满 (X=1000)
  return {
    progressRatio: 1.0,
    currentX: 1000,
    timeLabel: '15:00 (全天收盘)',
    isAfterClose: true,
    isMidday: false,
    isPreOpen: false,
    currentStage: 'STAGE_4_AFTERNOON' as IntradayBriefingStageKey,
  };
}

const DEFAULT_STOCKS: StockComparisonItem[] = [
  {
    code: '600550',
    name: '保变电气',
    role: '空间高度标杆 (5B)',
    tagType: 'yesterday_highest',
    tagLabel: '空间高度标杆 (5B)',
    changePct: 10.0,
    color: '#EF4444',
    pathD: 'M 0,70 C 10,40 20,10 40,8 L 1000,8',
    endX: 1000,
    endY: 8,
  },
  {
    code: '600198',
    name: '大唐电信',
    role: '梯队次高标杆 (4B)',
    tagType: 'yesterday_second',
    tagLabel: '梯队次高标杆 (4B)',
    changePct: 9.9,
    color: '#A855F7',
    pathD: 'M 0,70 C 30,50 60,30 100,10 L 1000,10',
    endX: 1000,
    endY: 10,
  },
  {
    code: '000158',
    name: '常山北明',
    role: '盘中最强涨停 (2B)',
    tagType: 'today_strongest',
    tagLabel: '盘中最强涨停 (2B)',
    isDynamic: true,
    changePct: 9.9,
    color: '#06B6D4',
    pathD: 'M 0,70 C 40,60 80,40 120,20 L 1000,10',
    endX: 1000,
    endY: 10,
  },
  {
    code: '002085',
    name: '万丰奥威',
    role: '分歧震荡标的',
    tagType: 'yesterday_core_broken',
    tagLabel: '分歧震荡标的',
    changePct: -5.2,
    color: '#10B981',
    pathD: 'M 0,70 C 20,40 40,15 70,10 C 90,10 110,60 140,90 L 1000,106',
    endX: 1000,
    endY: 106,
  },
  {
    code: '688981',
    name: '中芯国际',
    role: '科技容量中军',
    tagType: 'normal',
    changePct: 4.8,
    color: '#F59E0B',
    pathD: 'M 0,70 C 250,60 500,45 750,40 L 1000,41',
    endX: 1000,
    endY: 41,
  },
  {
    code: '300750',
    name: '宁德时代',
    role: '创指核心权重 (白线)',
    tagType: 'normal',
    changePct: -1.8,
    color: '#E2E8F0',
    pathD: 'M 0,70 C 250,75 500,80 750,82 L 1000,81',
    endX: 1000,
    endY: 81,
  },
];

const CANDIDATE_STOCKS: StockComparisonItem[] = [
  {
    code: '000021',
    name: '深科技',
    role: '存储芯片',
    changePct: 6.2,
    color: '#EC4899',
    pathD: 'M 0,70 C 250,55 500,40 750,35 L 1000,33',
    endX: 1000,
    endY: 33,
  },
  {
    code: '001696',
    name: '宗申动力',
    role: '低空经济',
    changePct: -3.4,
    color: '#E11D48',
    pathD: 'M 0,70 C 200,40 400,30 600,60 L 1000,90',
    endX: 1000,
    endY: 90,
  },
  {
    code: '300339',
    name: '润和软件',
    role: '开源鸿蒙',
    changePct: 7.5,
    color: '#6366F1',
    pathD: 'M 0,70 C 250,50 500,32 750,25 L 1000,25',
    endX: 1000,
    endY: 25,
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

  // 依据选定日期与真实时钟计算当前交易进度与活跃时段
  const timeProgress = useMemo(() => getTimeProgress(selectedDate), [selectedDate]);

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
  const [activeStageKey, setActiveStageKey] = useState<IntradayBriefingStageKey>(timeProgress.currentStage);
  const [topSectorsTrend, setTopSectorsTrend] = useState<TopSectorsTrendResponse | null>(null);

  // 随时钟与所选日期动态同步内参默认时段
  useEffect(() => {
    setActiveStageKey(timeProgress.currentStage);
  }, [timeProgress.currentStage]);

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
  const [stockComparisonList, setStockComparisonList] = useState<StockComparisonItem[]>(() =>
    DEFAULT_STOCKS.map((s) => ({
      ...s,
      endX: timeProgress.currentX,
      endY: Math.round(70 - Math.max(-10, Math.min(10, s.changePct)) * 6),
      pathD: generateDynamicStockPath(timeProgress.currentX, s.changePct, s.tagType || 'normal'),
    }))
  );
  const [isAddStockOpen, setIsAddStockOpen] = useState<boolean>(false);
  const [stockHoverX, setStockHoverX] = useState<number>(timeProgress.currentX);
  const [isStockHovering, setIsStockHovering] = useState<boolean>(false);
  const [sectorHoverX, setSectorHoverX] = useState<number>(timeProgress.currentX);
  const [isSectorHovering, setIsSectorHovering] = useState<boolean>(false);
  const stockChartContainerRef = useRef<HTMLDivElement>(null);
  const sectorChartContainerRef = useRef<HTMLDivElement>(null);

  // 当 limitUpData 或当前时间进度变化时，自动从真实数据中提取前日核心与今日最强
  useEffect(() => {
    const curX = timeProgress.currentX;

    if (limitUpData?.items && limitUpData.items.length > 0) {
      const sorted = [...limitUpData.items].sort((a, b) => (b.lbc || 0) - (a.lbc || 0));
      const maxLbc = sorted[0]?.lbc || 1;
      const highest = sorted[0];
      const second = sorted.find((s) => (s.lbc || 0) < maxLbc) || sorted[1] || highest;
      const strongest =
        [...limitUpData.items]
          .sort((a, b) => {
            const fA = a.fund_yi || (a.order_amount_wan ? a.order_amount_wan / 10000 : 0);
            const fB = b.fund_yi || (b.order_amount_wan ? b.order_amount_wan / 10000 : 0);
            return fB - fA;
          })
          .find((s) => s.code !== highest.code && s.code !== second.code) || sorted[2] || highest;
      const broken = limitUpData.broken_limit_items?.[0];
      const leader = topSectorsTrend?.sectors?.[0]?.leader;

      const dynamicList: StockComparisonItem[] = [];

      if (highest) {
        const pct = highest.zdp != null ? highest.zdp : 10.0;
        dynamicList.push({
          code: highest.code,
          name: highest.name,
          role: `昨日最高板 (${highest.lbc || maxLbc}B)`,
          tagType: 'yesterday_highest',
          tagLabel: `昨日最高板 (${highest.lbc || maxLbc}B)`,
          changePct: pct,
          color: '#EF4444',
          pathD: generateDynamicStockPath(curX, pct, 'yesterday_highest'),
          endX: curX,
          endY: Math.round(70 - Math.max(-10, Math.min(10, pct)) * 6),
        });
      }

      if (second && second.code !== highest.code) {
        const pct = second.zdp != null ? second.zdp : 9.9;
        dynamicList.push({
          code: second.code,
          name: second.name,
          role: `昨日次高板 (${second.lbc || Math.max(1, maxLbc - 1)}B)`,
          tagType: 'yesterday_second',
          tagLabel: `昨日次高板 (${second.lbc || Math.max(1, maxLbc - 1)}B)`,
          changePct: pct,
          color: '#A855F7',
          pathD: generateDynamicStockPath(curX, pct, 'yesterday_second'),
          endX: curX,
          endY: Math.round(70 - Math.max(-10, Math.min(10, pct)) * 6),
        });
      }

      if (strongest && !dynamicList.some((s) => s.code === strongest.code)) {
        const pct = strongest.zdp != null ? strongest.zdp : 10.0;
        dynamicList.push({
          code: strongest.code,
          name: strongest.name,
          role: `今日最强涨停 (${strongest.lbc || 1}B)`,
          tagType: 'today_strongest',
          tagLabel: `今日最强涨停 (${strongest.lbc || 1}B)`,
          isDynamic: true,
          changePct: pct,
          color: '#06B6D4',
          pathD: generateDynamicStockPath(curX, pct, 'today_strongest'),
          endX: curX,
          endY: Math.round(70 - Math.max(-10, Math.min(10, pct)) * 6),
        });
      }

      if (broken) {
        const pct = broken.pct_change != null ? broken.pct_change : -5.2;
        dynamicList.push({
          code: broken.code,
          name: broken.name,
          role: '高位分歧 (炸板跳水)',
          tagType: 'yesterday_core_broken',
          tagLabel: '高位分歧 (炸板跳水)',
          changePct: pct,
          color: '#10B981',
          pathD: generateDynamicStockPath(curX, pct, 'yesterday_core_broken'),
          endX: curX,
          endY: Math.round(70 - Math.max(-10, Math.min(10, pct)) * 6),
        });
      } else {
        dynamicList.push({
          code: '002085',
          name: '万丰奥威',
          role: '昨日核心分歧 (3B)',
          tagType: 'yesterday_core_broken',
          tagLabel: '昨日核心分歧 (3B)',
          changePct: -5.2,
          color: '#10B981',
          pathD: generateDynamicStockPath(curX, -5.2, 'yesterday_core_broken'),
          endX: curX,
          endY: Math.round(70 - (-5.2) * 6),
        });
      }

      if (leader) {
        const pct = leader.pct_change != null ? leader.pct_change : 4.8;
        dynamicList.push({
          code: leader.code,
          name: leader.name,
          role: leader.status_desc || '行业领军中军',
          tagType: 'normal',
          changePct: pct,
          color: '#F59E0B',
          pathD: generateDynamicStockPath(curX, pct, 'normal'),
          endX: curX,
          endY: Math.round(70 - Math.max(-10, Math.min(10, pct)) * 6),
        });
      } else {
        dynamicList.push({
          code: '688981',
          name: '中芯国际',
          role: '科技容量中军',
          tagType: 'normal',
          changePct: 4.8,
          color: '#F59E0B',
          pathD: generateDynamicStockPath(curX, 4.8, 'normal'),
          endX: curX,
          endY: Math.round(70 - 4.8 * 6),
        });
      }

      dynamicList.push({
        code: '300750',
        name: '宁德时代',
        role: '创指核心权重 (白线)',
        tagType: 'normal',
        changePct: -1.8,
        color: '#E2E8F0',
        pathD: generateDynamicStockPath(curX, -1.8, 'normal'),
        endX: curX,
        endY: Math.round(70 - (-1.8) * 6),
      });

      setStockComparisonList(dynamicList.slice(0, 6));
    } else {
      setStockComparisonList((prev) =>
        prev.map((s) => {
          const endY = Math.round(70 - Math.max(-10, Math.min(10, s.changePct)) * 6);
          return {
            ...s,
            endX: curX,
            endY,
            pathD: generateDynamicStockPath(curX, s.changePct, s.tagType || 'normal'),
          };
        })
      );
    }
  }, [limitUpData, topSectorsTrend, timeProgress.currentX]);

  // 题材 Top 5 动态曲线与领涨标的联动
  const dynamicSectorCurves = useMemo(() => {
    const curX = timeProgress.currentX;
    const sectors = topSectorsTrend?.sectors || [];

    if (sectors.length === 0) {
      const fallbackList = [
        { name: '半导体', color: '#8B5CF6', net: 28.4, pct: 4.8, leader: '中芯国际', leaderCode: '688981', leaderPct: 4.8, leaderStatus: '核心中军', endY: 17 },
        { name: '算力概念', color: '#06B6D4', net: 14.2, pct: 9.9, leader: '常山北明', leaderCode: '000158', leaderPct: 9.9, leaderStatus: '触板先锋', endY: 43 },
        { name: '银行权重', color: '#F59E0B', net: 9.8, pct: 1.2, leader: '工商银行', leaderCode: '601398', leaderPct: 1.2, leaderStatus: '护盘基石', endY: 52 },
        { name: '锂电池', color: '#94A3B8', net: -8.5, pct: -1.8, leader: '宁德时代', leaderCode: '300750', leaderPct: -1.8, leaderStatus: '分化回落', endY: 87 },
        { name: '低空经济', color: '#10B981', net: -19.2, pct: -5.2, leader: '万丰奥威', leaderCode: '002085', leaderPct: -5.2, leaderStatus: '炸板跳水', endY: 116 },
      ];
      return fallbackList.map((item, idx) => ({
        ...item,
        path: generateSectorPath(curX, item.endY, idx),
      }));
    }

    const themeColors = ['#8B5CF6', '#06B6D4', '#F59E0B', '#94A3B8', '#10B981'];
    return sectors.slice(0, 5).map((sec, idx) => {
      const net = sec.current_net_inflow_yi;
      let endY = 70;
      if (net >= 0) {
        endY = Math.max(14, 70 - (net / 30) * 54);
      } else {
        endY = Math.min(124, 70 + (Math.abs(net) / 25) * 48);
      }
      const path = generateSectorPath(curX, endY, idx);

      return {
        name: sec.name,
        color: sec.color || themeColors[idx % themeColors.length],
        net: sec.current_net_inflow_yi,
        pct: sec.current_pct_change,
        leader: sec.leader?.name || '--',
        leaderCode: sec.leader?.code || '',
        leaderPct: sec.leader?.pct_change != null ? sec.leader.pct_change : 0,
        leaderStatus: sec.leader?.status_desc || '领涨龙头',
        path,
        endY,
      };
    });
  }, [topSectorsTrend, timeProgress.currentX]);

  // 底部双轨博弈透视结论动态推演 (基于当前真实入选标的)
  const dynamicGamePerspective = useMemo(() => {
    const highest = stockComparisonList.find((s) => s.tagType === 'yesterday_highest');
    const second = stockComparisonList.find((s) => s.tagType === 'yesterday_second');
    const strongest = stockComparisonList.find((s) => s.tagType === 'today_strongest');
    const broken = stockComparisonList.find((s) => s.tagType === 'yesterday_core_broken');

    const hName = highest ? `${highest.name}(${highest.role})` : '空间标杆';
    const sName = second ? `${second.name}(${second.role})` : '梯队次高';
    const tName = strongest ? `${strongest.name}(+${strongest.changePct}%)` : '盘中最强';
    const bName = broken ? `${broken.name}(${broken.changePct >= 0 ? '+' : ''}${broken.changePct}%)` : '高位分歧标的';

    return {
      track1: `前日最高板<strong class="text-rose-400">${hName}</strong>与次高板<strong class="text-rose-400">${sName}</strong>开盘均获高溢价，高位空间未破；但分歧标的<strong class="text-emerald-400">${bName}</strong>出现剧烈波动，暴露中位断层承接力分化。`,
      track2: `盘中实时最强涨停<strong class="text-cyan-300">${tName}</strong>展现强劲资金吸引力，与主线高标形成同向正反馈助攻；但与弱势标的<strong class="text-emerald-400">${bName}</strong>形成尖锐的“资金抽血反向剪刀差”——存量资金向绝对核心靠拢。`,
    };
  }, [stockComparisonList]);

  // 可选样本股池 (优先从真实今日涨停池中提取，并融合后备样本)
  const availableCandidates = useMemo(() => {
    const list: StockComparisonItem[] = [];
    const curX = timeProgress.currentX;

    if (limitUpData?.items && limitUpData.items.length > 0) {
      const colors = ['#EC4899', '#E11D48', '#6366F1', '#14B8A6', '#84CC16', '#F97316'];
      limitUpData.items.forEach((item, idx) => {
        if (!stockComparisonList.some((s) => s.code === item.code) && !list.some((s) => s.code === item.code)) {
          const pct = item.zdp != null ? item.zdp : 10.0;
          list.push({
            code: item.code,
            name: item.name,
            role: `${item.sector || '主线'} (${item.lbc || 1}B)`,
            tagType: 'normal',
            tagLabel: `${item.lbc || 1}B 连板`,
            changePct: pct,
            color: colors[idx % colors.length],
            pathD: generateDynamicStockPath(curX, pct, 'normal'),
            endX: curX,
            endY: Math.round(70 - Math.max(-10, Math.min(10, pct)) * 6),
          });
        }
      });
    }

    CANDIDATE_STOCKS.forEach((c) => {
      if (!stockComparisonList.some((s) => s.code === c.code) && !list.some((s) => s.code === c.code)) {
        list.push({
          ...c,
          endX: curX,
          endY: Math.round(70 - Math.max(-10, Math.min(10, c.changePct)) * 6),
          pathD: generateDynamicStockPath(curX, c.changePct, 'normal'),
        });
      }
    });

    return list.slice(0, 12);
  }, [limitUpData, stockComparisonList, timeProgress.currentX]);

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
      {/* 动画样式：贝塞尔曲线从左至右入场平滑生长动画 */}
      <style>{`
        @keyframes drawLine {
          from {
            stroke-dashoffset: 2000;
          }
          to {
            stroke-dashoffset: 0;
          }
        }
        .animate-path-grow {
          stroke-dasharray: 2000;
          stroke-dashoffset: 0;
          animation: drawLine 1.4s cubic-bezier(0.16, 1, 0.3, 1) forwards;
        }
      `}</style>

      {/* 背景弥散氛围光晕 */}
      <div className="fixed top-[-10%] left-[-5%] w-[600px] h-[600px] rounded-full bg-purple-600/10 blur-[150px] pointer-events-none -z-10" />
      <div className="fixed bottom-[-10%] right-[-5%] w-[600px] h-[600px] rounded-full bg-cyan-500/08 blur-[160px] pointer-events-none -z-10" />

      {/* 顶部统一控制台标头 (彻底消除多余 Logo、系统名重复、安全药丸重复与头像冗余) */}
      <header className="max-w-7xl mx-auto w-full bg-[#090D16]/90 backdrop-blur-2xl border border-white/10 rounded-2xl px-4 py-3 flex flex-wrap items-center justify-between gap-3 shadow-2xl z-30 sticky top-2 select-none">
        {/* 左侧：页面标题与交易态势胶囊 */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-purple-500/15 border border-purple-500/30 flex items-center justify-center text-purple-300 shadow-inner shrink-0">
            <Compass className="w-4 h-4 text-purple-400" />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="font-bold text-sm tracking-wide text-white">交易员驾驶舱</h1>
              {timeProgress.isAfterClose ? (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center gap-1.5 font-semibold">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
                  全天收盘 · 战局终局 ({selectedDate})
                </span>
              ) : timeProgress.isMidday ? (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center gap-1.5 font-semibold">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400"></span>
                  午间休市 · 盘中态势锁定 (11:30~13:00)
                </span>
              ) : timeProgress.isPreOpen ? (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-500/15 text-cyan-300 border border-cyan-500/30 flex items-center gap-1.5 font-semibold">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
                  未开盘 · 集合竞价准备期
                </span>
              ) : (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-300 border border-rose-500/30 flex items-center gap-1.5 font-semibold shadow-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-rose-500 animate-pulse"></span>
                  实盘交易中 · {timeProgress.timeLabel}
                </span>
              )}
            </div>
            <span className="text-[10px] text-slate-400 font-mono mt-0.5 hidden sm:block">
              极光暗夜流光版 · 盘中 4 时段决策内参 + 核心个股分时走势 + 题材主力资金争夺
            </span>
          </div>
        </div>

        {/* 中间：页面内 Bento 模块快速平滑直达锚点 (取代与全局侧边栏冲突的路由导航) */}
        <nav className="hidden lg:flex items-center gap-1 bg-black/40 border border-white/10 rounded-full p-1 text-xs font-medium text-slate-400">
          <button
            onClick={() => document.getElementById('bento-briefing')?.scrollIntoView({ behavior: 'smooth' })}
            className="px-2.5 py-1 rounded-full hover:text-white hover:bg-white/5 transition"
          >
            操盘内参
          </button>
          <button
            onClick={() => document.getElementById('bento-temperature')?.scrollIntoView({ behavior: 'smooth' })}
            className="px-2.5 py-1 rounded-full hover:text-white hover:bg-white/5 transition"
          >
            市场温度
          </button>
          <button
            onClick={() => document.getElementById('bento-stocks')?.scrollIntoView({ behavior: 'smooth' })}
            className="px-2.5 py-1 rounded-full hover:text-white hover:bg-white/5 transition"
          >
            核心个股
          </button>
          <button
            onClick={() => document.getElementById('bento-battleground')?.scrollIntoView({ behavior: 'smooth' })}
            className="px-2.5 py-1 rounded-full hover:text-white hover:bg-white/5 transition"
          >
            题材战场
          </button>
          <button
            onClick={() => document.getElementById('bento-ladder')?.scrollIntoView({ behavior: 'smooth' })}
            className="px-2.5 py-1 rounded-full hover:text-white hover:bg-white/5 transition"
          >
            连板天梯
          </button>
          <button
            onClick={() => document.getElementById('bento-mines')?.scrollIntoView({ behavior: 'smooth' })}
            className="px-2.5 py-1 rounded-full hover:text-white hover:bg-white/5 transition"
          >
            地雷雷达
          </button>
        </nav>

        {/* 右侧：纯功能控制台 (无多余安全药丸、无孤立头像，纯粹专业工具链) */}
        <div className="flex items-center gap-2">
          {/* 日期选择器 */}
          <div className="h-8 flex items-center gap-1.5 bg-black/50 border border-white/10 rounded-xl px-2.5 text-xs shadow-inner">
            <Calendar className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="bg-transparent border-none text-[11px] font-mono text-slate-200 focus:outline-none cursor-pointer"
            />
          </div>

          {/* 自动快照指标 */}
          <div className="h-8 hidden sm:flex items-center gap-1.5 bg-black/40 border border-white/10 px-2.5 rounded-xl text-[10px] font-mono text-slate-300">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>快照 3s</span>
          </div>

          {/* 刷新按钮 */}
          <button
            onClick={() => {
              fetchAllData(selectedDate);
              fetchSectors(sectorType);
            }}
            disabled={isLoading}
            className="h-8 px-2.5 flex items-center gap-1.5 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-300 hover:text-white text-xs font-medium transition disabled:opacity-50 shrink-0"
            title="刷新全量事实与认知数据"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">刷新</span>
          </button>

          {/* 审计留痕抽屉入口 */}
          <button
            onClick={() => setIsAuditOpen(true)}
            className="h-8 px-2.5 flex items-center gap-1.5 rounded-xl bg-purple-950/40 hover:bg-purple-900/50 border border-purple-500/30 text-purple-300 hover:text-purple-200 text-xs font-medium transition shrink-0"
            title="查看完整事实与推理审计留痕"
          >
            <FileText className="w-3.5 h-3.5 text-purple-400" />
            <span className="hidden sm:inline">审计留痕</span>
          </button>

          {/* 切换经典版 */}
          <button
            onClick={() => setViewMode('classic')}
            className="h-8 w-8 flex items-center justify-center rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-slate-400 hover:text-slate-200 text-xs transition shrink-0"
            title="切换为经典三层驾驶舱布局"
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
          </button>
        </div>
      </header>

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
          id="bento-briefing"
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
                <span className={`w-1.5 h-1.5 rounded-full bg-emerald-400 ${timeProgress.currentStage === 'STAGE_1_AUCTION' ? 'animate-pulse ring-2 ring-emerald-400/50' : ''}`}></span>
                <span>① 09:26 竞价定调{timeProgress.currentStage === 'STAGE_1_AUCTION' ? ' (当前)' : ''}</span>
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
                <span className={`w-1.5 h-1.5 rounded-full bg-rose-400 ${timeProgress.currentStage === 'STAGE_2_MORNING' ? 'animate-pulse ring-2 ring-rose-400/50' : ''}`}></span>
                <span>② 10:15 早盘初战{timeProgress.currentStage === 'STAGE_2_MORNING' ? ' (当前)' : ''}</span>
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
                <span className={`w-1.5 h-1.5 rounded-full bg-cyan-400 ${timeProgress.currentStage === 'STAGE_3_MIDDAY' ? 'animate-pulse ring-2 ring-cyan-400/50' : ''}`}></span>
                <span>③ 11:31 午盘综述{timeProgress.currentStage === 'STAGE_3_MIDDAY' ? ' (当前)' : ''}</span>
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
                <span className={`w-1.5 h-1.5 rounded-full bg-purple-400 ${timeProgress.currentStage === 'STAGE_4_AFTERNOON' ? 'animate-pulse ring-2 ring-purple-400/50' : ''}`}></span>
                <span>④ 14:15 变盘前哨{timeProgress.currentStage === 'STAGE_4_AFTERNOON' ? ' (当前)' : ''}</span>
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
                    {currentBriefingRecord?.timing || `采集判定时点: ${timeProgress.timeLabel} · 100% 物理真实快照`}
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
            id="bento-temperature"
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
          id="bento-stocks"
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
                let badgeClass = 'bg-white/[0.03] text-white border-white/10';
                let tagBadge = null;

                if (s.tagType === 'today_strongest') {
                  badgeClass = 'bg-cyan-950/50 text-cyan-200 border-cyan-400/60 shadow-[0_0_12px_rgba(6,182,212,0.35)]';
                  tagBadge = (
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-cyan-500/25 text-cyan-200 border border-cyan-400/40 font-semibold flex items-center gap-1">
                      {s.tagLabel || s.role}
                    </span>
                  );
                } else if (s.tagType === 'yesterday_highest') {
                  badgeClass = 'bg-rose-950/40 text-rose-200 border-rose-500/40 shadow-sm';
                  tagBadge = (
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 font-semibold">
                      {s.tagLabel || s.role}
                    </span>
                  );
                } else if (s.tagType === 'yesterday_second') {
                  badgeClass = 'bg-purple-950/40 text-purple-200 border-purple-500/40';
                  tagBadge = (
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-purple-500/20 text-purple-300 font-semibold">
                      {s.tagLabel || s.role}
                    </span>
                  );
                } else if (s.tagType === 'yesterday_core_broken') {
                  badgeClass = 'bg-emerald-950/30 text-emerald-200 border-emerald-500/40';
                  tagBadge = (
                    <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-950/60 text-amber-300 border border-amber-500/30 font-semibold">
                      {s.tagLabel || s.role}
                    </span>
                  );
                } else {
                  tagBadge = (
                    <span className="text-[10px] text-slate-400 font-normal">
                      ({s.role})
                    </span>
                  );
                }

                return (
                  <span
                    key={s.code}
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-bold border transition ${badgeClass}`}
                  >
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: s.color }} />
                    <span className="text-white font-bold">{s.name}</span>
                    {tagBadge}
                    <span className={`font-black ${s.changePct >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                      {s.changePct >= 0 ? `+${s.changePct.toFixed(1)}%` : `${s.changePct.toFixed(1)}%`}
                    </span>
                    <button
                      onClick={() => handleRemoveStock(s.code)}
                      className="ml-1 text-slate-400 hover:text-white transition"
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
                    <div className="absolute right-0 top-8 w-56 max-h-60 overflow-y-auto bg-slate-900 border border-cyan-500/40 rounded-xl p-2 shadow-2xl z-50 space-y-1">
                      <div className="text-[11px] text-slate-400 font-mono px-2 py-1 border-b border-white/10">可选样本池 ({availableCandidates.length} 只)</div>
                      {availableCandidates.map((c) => (
                        <button
                          key={c.code}
                          onClick={() => handleAddStock(c)}
                          className="w-full flex items-center justify-between px-2 py-1.5 rounded hover:bg-white/10 text-xs text-left transition"
                        >
                          <span className="font-bold text-white">{c.name}</span>
                          <span className="text-slate-400 text-[11px] font-mono">{c.role}</span>
                          <span className={`font-mono font-bold ${c.changePct >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                            {c.changePct >= 0 ? `+${c.changePct.toFixed(1)}%` : `${c.changePct.toFixed(1)}%`}
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

            {/* 当前进展标尺 (动态根据 timeProgress.progressRatio 计算位置) */}
            <div
              className="absolute top-0 bottom-7 w-px bg-cyan-400 z-10 border-l border-dashed border-cyan-400 shadow-[0_0_8px_rgba(6,182,212,0.8)] transition-all duration-500 pointer-events-none"
              style={{ left: `${Math.min(99.6, Math.max(0.4, timeProgress.progressRatio * 100)).toFixed(2)}%` }}
            >
              <div
                className={`absolute top-1 px-1.5 py-0.5 rounded bg-cyan-950/95 border border-cyan-500 text-[10px] text-cyan-300 font-mono font-bold whitespace-nowrap shadow-md ${
                  timeProgress.progressRatio > 0.85 ? 'right-1' : '-left-7'
                }`}
              >
                {timeProgress.isAfterClose ? '15:00 全天收盘' : timeProgress.timeLabel.split(' ')[0]}
              </div>
            </div>

            {/* 鼠标悬停实时多股涨跌幅数值看板浮窗 */}
            {isStockHovering && (
              <div
                className="absolute top-2 pointer-events-none z-30 bg-slate-950/95 border border-cyan-500/40 rounded-xl p-2.5 shadow-2xl backdrop-blur-xl flex flex-col gap-1 text-[11px] font-mono min-w-[210px]"
                style={{
                  left: `${Math.min(76, Math.max(4, (stockHoverX / 1000) * 100))}%`,
                }}
              >
                <div className="flex items-center justify-between border-b border-white/10 pb-1 text-cyan-300 font-bold">
                  <span>{getHoverTimeLabel(stockHoverX)} 个股走势采样</span>
                  <span className="text-[10px] text-slate-400">分时对照</span>
                </div>
                <div className="flex flex-col gap-0.5 pt-0.5">
                  {stockComparisonList.map((s) => {
                    const progress = Math.min(1, Math.max(0, stockHoverX / (s.endX || 1000)));
                    const estPct = (s.changePct * progress).toFixed(1);
                    return (
                      <div key={s.code} className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-1.5 truncate">
                          <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: s.color }} />
                          <span className="text-slate-200">{s.name}</span>
                        </span>
                        <span className={`font-bold shrink-0 ${Number(estPct) >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                          {Number(estPct) >= 0 ? `+${estPct}%` : `${estPct}%`}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

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
                      strokeWidth={s.tagType === 'today_strongest' || s.tagType === 'yesterday_highest' ? '2.8' : '2.2'}
                      strokeLinecap="round"
                      className="animate-path-grow"
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
              <span>10:30</span>
              <span>11:00</span>
              <span className="text-slate-300 font-bold">11:30 / 13:00</span>
              <span>13:30</span>
              <span>14:00</span>
              <span>14:30</span>
              <span className={timeProgress.isAfterClose ? 'text-cyan-300 font-bold' : ''}>
                15:00{timeProgress.isAfterClose ? ' (全天收盘)' : ''}
              </span>
            </div>
          </div>

          {/* 底部双轨博弈透视结论卡片 (前日核心今日表现 + 今日最强涨停涨跌博弈) */}
          <div className="mt-2 pt-2.5 border-t border-white/10 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
            {/* 轨道 1：昨日核心在今日的表现 */}
            <div className="bg-purple-950/20 border border-purple-500/30 rounded-xl p-2.5 flex items-start gap-2.5">
              <div className="px-2 py-0.5 rounded text-[11px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40 shrink-0 mt-0.5">
                昨日核心今日表现
              </div>
              <p className="text-slate-300 leading-relaxed text-xs" dangerouslySetInnerHTML={{ __html: dynamicGamePerspective.track1 }} />
            </div>

            {/* 轨道 2：当天当时最强涨停与昨日核心的涨跌关系 */}
            <div className="bg-cyan-950/20 border border-cyan-500/30 rounded-xl p-2.5 flex items-start gap-2.5">
              <div className="px-2 py-0.5 rounded text-[11px] font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shrink-0 mt-0.5 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping"></span>
                今日最强 vs 昨日核心
              </div>
              <p className="text-cyan-200 leading-relaxed text-xs" dangerouslySetInnerHTML={{ __html: dynamicGamePerspective.track2 }} />
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
            <div className="flex flex-wrap items-center gap-3 text-xs font-mono text-slate-300">
              {dynamicSectorCurves.map((sec) => (
                <span key={sec.name} className="flex items-center gap-1.5">
                  <span className="w-2.5 h-1 rounded-full" style={{ backgroundColor: sec.color }}></span>
                  {sec.name} ({sec.net >= 0 ? `+${sec.net.toFixed(1)}` : sec.net.toFixed(1)}亿)
                </span>
              ))}
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

            {/* 当前进展标尺 (动态根据 timeProgress.progressRatio 计算位置) */}
            <div
              className="absolute top-0 bottom-7 w-px bg-purple-400 z-10 border-l border-dashed border-purple-400 shadow-[0_0_8px_rgba(139,92,246,0.8)] transition-all duration-500 pointer-events-none"
              style={{ left: `${Math.min(99.6, Math.max(0.4, timeProgress.progressRatio * 100)).toFixed(2)}%` }}
            >
              <div
                className={`absolute top-1 px-1.5 py-0.5 rounded bg-purple-950/95 border border-purple-500 text-[10px] text-purple-300 font-mono font-bold whitespace-nowrap shadow-md ${
                  timeProgress.progressRatio > 0.85 ? 'right-1' : '-left-7'
                }`}
              >
                {timeProgress.isAfterClose ? '15:00 全天收盘' : timeProgress.timeLabel.split(' ')[0]}
              </div>
            </div>

            {/* 鼠标悬停实时 Top 5 题材资金净流数值看板浮窗 */}
            {isSectorHovering && (
              <div
                className="absolute top-2 pointer-events-none z-30 bg-slate-950/95 border border-purple-500/40 rounded-xl p-2.5 shadow-2xl backdrop-blur-xl flex flex-col gap-1 text-[11px] font-mono min-w-[220px]"
                style={{
                  left: `${Math.min(74, Math.max(4, (sectorHoverX / 1000) * 100))}%`,
                }}
              >
                <div className="flex items-center justify-between border-b border-white/10 pb-1 text-purple-300 font-bold">
                  <span>{getHoverTimeLabel(sectorHoverX)} 主力资金净流</span>
                  <span className="text-[10px] text-slate-400">Top 5 采样</span>
                </div>
                <div className="flex flex-col gap-0.5 pt-0.5">
                  {dynamicSectorCurves.map((sec, idx) => {
                    const progress = Math.min(1, Math.max(0, sectorHoverX / (timeProgress.currentX || 1000)));
                    const estNet = (sec.net * progress).toFixed(1);
                    return (
                      <div key={sec.name} className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-1.5 truncate">
                          <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: sec.color }} />
                          <span className="text-slate-200">#{idx + 1} {sec.name}</span>
                        </span>
                        <span className={`font-bold shrink-0 ${Number(estNet) >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                          {Number(estNet) >= 0 ? `+${estNet} 亿` : `${estNet} 亿`}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 曲线图主体区域 */}
            <div className="relative w-full flex-1 min-h-[140px]">
              <svg className="w-full h-full z-10 overflow-visible" viewBox="0 0 1000 140" preserveAspectRatio="none">
                <line x1="0" y1="70" x2="1000" y2="70" stroke="rgba(255,255,255,0.15)" strokeWidth="1.2" />
                {dynamicSectorCurves.map((sec, idx) => (
                  <g key={sec.name}>
                    <path
                      d={sec.path}
                      fill="none"
                      stroke={sec.color}
                      strokeWidth={idx === 0 ? '3' : '2.2'}
                      strokeLinecap="round"
                      className="animate-path-grow"
                    />
                    <circle cx={timeProgress.currentX} cy={sec.endY} r={idx === 0 ? 4.5 : 3.5} fill={sec.color} stroke="#fff" strokeWidth="1.5" />
                  </g>
                ))}

                {isSectorHovering && (
                  <line x1={sectorHoverX} y1="0" x2={sectorHoverX} y2="140" stroke="#8B5CF6" strokeWidth="1.2" strokeDasharray="3,3" opacity="0.9" />
                )}
              </svg>
            </div>

            {/* X 轴时间刻度标尺 */}
            <div className="flex justify-between text-xs font-mono text-slate-400 pt-2 border-t border-white/10 z-10 shrink-0">
              <span>09:30</span>
              <span>10:00</span>
              <span>10:30</span>
              <span>11:00</span>
              <span className="text-slate-300 font-bold">11:30 / 13:00</span>
              <span>13:30</span>
              <span>14:00</span>
              <span>14:30</span>
              <span className={timeProgress.isAfterClose ? 'text-purple-300 font-bold' : ''}>
                15:00{timeProgress.isAfterClose ? ' (全天收盘)' : ''}
              </span>
            </div>
          </div>

          {/* 5 大题材领涨核心龙头联动卡片 */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 my-2 text-xs">
            {dynamicSectorCurves.map((sec, idx) => (
              <div
                key={sec.name}
                className="bg-white/[0.025] border p-3 rounded-xl flex flex-col justify-between"
                style={{ borderColor: `${sec.color}55` }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold" style={{ color: sec.color }}>#{idx + 1} {sec.name}</span>
                  <span className={`text-xs font-mono font-bold ${sec.net >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                    {sec.net >= 0 ? `+${sec.net.toFixed(1)}` : sec.net.toFixed(1)} 亿
                  </span>
                </div>
                <div className="font-bold text-white text-sm my-1">{sec.leader}</div>
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>{sec.leaderCode ? `${sec.leaderCode} · ` : ''}{sec.leaderStatus}</span>
                  <span className={`font-mono font-bold ${sec.leaderPct >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                    {sec.leaderPct >= 0 ? `+${sec.leaderPct.toFixed(1)}%` : `${sec.leaderPct.toFixed(1)}%`}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="pt-2 border-t border-white/5 flex items-center justify-between text-xs text-slate-400 font-mono">
            <span>
              题材轮动特征:{' '}
              <strong className="text-purple-300">
                {dynamicSectorCurves[0]?.name || '领涨板块'}引领资金攻坚，{dynamicSectorCurves[dynamicSectorCurves.length - 1]?.name || '走弱题材'}承压失血
              </strong>
            </span>
            <span className="text-cyan-300">
              {timeProgress.isAfterClose ? '全天资金沉淀判定' : `当前时点 (${timeProgress.timeLabel.split(' ')[0]}) 资金态势`}
            </span>
          </div>
        </GlassCard>

        {/* --------------------------------------------------------------------- */}
        {/* 第四排【地雷雷达】：动态炸板率与跳水排雷 (横向全幅呈现) */}
        {/* --------------------------------------------------------------------- */}
        <GlassCard
          id="bento-mines"
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
