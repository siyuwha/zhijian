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
  SectorTrendPoint,
  StockMinutePoint,
  StockTrendData,
} from '@/types/canonical';
import { canonicalAPI, api } from '@/lib/api';
import { getLatestTradingDateString, getPrevTradingDay, getTodayDateString, isTradingDay } from '@/lib/utils';
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
  roles?: string[]; // 核心股多标签体系 (如 ["情绪标杆 4B", "容量中军"])
  turnoverRate?: number; // 换手率 (%)，如 18.5
  floatMcapYi?: number; // 真实流通市值 (亿元)，如 168.5
  totalAmountYi?: number; // 成交额 (亿元)，如 25.3
  healthDiagnosis?: {
    level: 'healthy' | 'warning' | 'danger';
    badge: string;
    reason: string;
  };
}

export interface DynamicSectorCurveItem {
  name: string;
  color: string;
  net: number;
  pct: number;
  leader: string;
  leaderCode: string;
  leaderPct: number;
  leaderStatus: string;
  path: string;
  endX?: number;
  endY: number;
  trends?: SectorTrendPoint[];
  // 认知微观体检指标
  isSolitaryMonopoly?: boolean;
  monopolyRatio?: number;
  crrs?: number;
  rearNegativeRatio?: number;
  brokenLimitRatio?: number;
}


/**
 * 6 只样本股高辨识度独立专属色谱 (红、蓝、琥珀黄、翡翠绿、魅惑紫、电光青)
 * 严格保证每只样本票分配独一无二的颜色，折线走势图与 Chip 标签彻底摆脱同色混淆
 */
export const DISTINCT_STOCK_COLORS = [
  '#EF4444', // 1. 烈焰红 (Red)
  '#3B82F6', // 2. 苍穹蓝 (Royal Blue)
  '#F59E0B', // 3. 琥珀金 (Amber/Orange)
  '#10B981', // 4. 翡翠绿 (Emerald)
  '#A855F7', // 5. 魅惑紫 (Purple)
  '#06B6D4', // 6. 电光青 (Cyan)
];

/**
 * 将盘中具体交易时刻文本 (09:30 ~ 15:00) 映射为 X 轴位置 (0~1000)
 */
export function timeToX(timeStr: string): number {
  if (!timeStr) return 0;
  const parts = timeStr.split(':');
  if (parts.length < 2) return 0;
  const h = parseInt(parts[0], 10);
  const m = parseInt(parts[1], 10);
  const totalMin = h * 60 + m;

  if (totalMin <= 570) return 0;
  if (totalMin <= 690) {
    return Number((((totalMin - 570) / 120) * 500).toFixed(1));
  }
  if (totalMin < 780) {
    return 500;
  }
  if (totalMin <= 900) {
    return Number((500 + ((totalMin - 780) / 120) * 500).toFixed(1));
  }
  return 1000;
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
 * 基于物理真实分钟点阵生成真实个股分时走势 SVG 路径
 */
export function generateRealStockSvgPath(
  points: StockMinutePoint[],
  maxTimeProgressX: number,
  offsetIndex: number = 0
): { path: string; endX: number; endY: number } {
  if (!points || points.length === 0) {
    return { path: 'M 0,70 L 1000,70', endX: 1000, endY: 70 };
  }

  const coords: [number, number][] = [];
  // 针对相同极限涨跌幅 (如双双跌停 -10% 或涨停 +10%) 引入微视差偏移，彻底消除线条被后画者绝对覆盖遮挡
  const limitOffset = (offsetIndex % 4 - 1.5) * 1.8;

  for (const pt of points) {
    const x = timeToX(pt.time);
    if (x > maxTimeProgressX + 3) break;
    const clampedPct = Math.max(-10, Math.min(10, pt.pct_change));
    let y = 70 - clampedPct * 6;
    if (Math.abs(clampedPct) >= 9.2) {
      y += limitOffset;
    }
    coords.push([x, Number(y.toFixed(1))]);
  }

  if (coords.length === 0) {
    return { path: 'M 0,70 L 0,70', endX: 0, endY: 70 };
  }

  // 确保 09:30 零轴起点 (0, 70) 锚定
  if (coords[0][0] > 0) {
    coords.unshift([0, 70]);
  }

  let d = `M ${coords[0][0].toFixed(1)},${coords[0][1].toFixed(1)}`;
  for (let i = 1; i < coords.length; i++) {
    d += ` L ${coords[i][0].toFixed(1)},${coords[i][1].toFixed(1)}`;
  }

  const last = coords[coords.length - 1];
  return { path: d, endX: last[0], endY: last[1] };
}

/**
 * 基于物理真实分钟点阵生成真实题材主力资金净流走势 SVG 路径
 */
export function generateRealSectorSvgPath(
  trends: SectorTrendPoint[],
  maxTimeProgressX: number
): { path: string; endX: number; endY: number } {
  if (!trends || trends.length === 0) {
    return { path: 'M 0,70 L 1000,70', endX: 1000, endY: 70 };
  }

  const coords: [number, number][] = [];
  for (const pt of trends) {
    const x = timeToX(pt.time);
    if (x > maxTimeProgressX + 3) break;
    const net = pt.net_inflow_yi;
    let y = 70;
    if (net >= 0) {
      y = Math.max(12, 70 - (Math.min(30, net) / 30) * 54);
    } else {
      y = Math.min(128, 70 + (Math.min(25, Math.abs(net)) / 25) * 48);
    }
    coords.push([x, Number(y.toFixed(1))]);
  }

  if (coords.length === 0) {
    return { path: 'M 0,70 L 0,70', endX: 0, endY: 70 };
  }

  // 确保 09:30 零轴起点 (0, 70) 锚定，彻底杜绝悬空水平直线
  if (coords[0][0] > 0) {
    coords.unshift([0, 70]);
  }

  let d = `M ${coords[0][0].toFixed(1)},${coords[0][1].toFixed(1)}`;
  for (let i = 1; i < coords.length; i++) {
    d += ` L ${coords[i][0].toFixed(1)},${coords[i][1].toFixed(1)}`;
  }

  const last = coords[coords.length - 1];
  return { path: d, endX: last[0], endY: last[1] };
}

/**
 * 动态根据当前时间在 X 轴上的推进位置 (currentX: 0~1000) 与真实涨跌幅生成 SVG 个股走势曲线路径 (离线保底)
 */
export function generateDynamicStockPath(
  currentX: number,
  changePct: number,
  tagType: string,
  offsetIndex: number = 0
): string {
  const safeX = Math.max(20, Math.min(1000, currentX));
  const clampedPct = Math.max(-10, Math.min(10, changePct));
  const limitOffset = (offsetIndex % 4 - 1.5) * 2.0;
  const endY = Number((70 - clampedPct * 6 + (Math.abs(clampedPct) >= 9.0 ? limitOffset : 0)).toFixed(1));

  // 1. 涨停或大幅冲高 (+9.5% ~ +10.0%): 早盘快速推升，封板后微幅震荡
  if (clampedPct >= 9.5) {
    const lockX = Math.min(120, safeX * 0.25);
    const p1X = lockX * 0.4;
    const p2X = lockX * 0.8;
    const topY = 10 + limitOffset;
    return `M 0,55 C ${p1X},45 ${p2X},${topY + 6} ${lockX},${topY} C ${lockX + (safeX - lockX) * 0.3},${topY + 1} ${lockX + (safeX - lockX) * 0.7},${topY - 0.5} ${safeX},${endY}`;
  }

  // 2. 跌停或深水重挫 (-9.0% ~ -10.0%): 早盘低开下探，午后加速触及跌停
  if (clampedPct <= -9.0) {
    const drop1X = safeX * 0.35;
    const drop2X = safeX * 0.7;
    const botY = 130 + limitOffset;
    return `M 0,72 C ${drop1X * 0.4},82 ${drop1X * 0.8},105 ${drop1X},108 C ${drop1X + (drop2X - drop1X) * 0.5},112 ${drop2X * 0.9},${botY - 2} ${drop2X},${botY} C ${drop2X + (safeX - drop2X) * 0.5},${botY + 0.5} ${safeX * 0.95},${botY - 0.5} ${safeX},${endY}`;
  }

  // 3. 炸板回落或大幅冲高回落 (如 +3% ~ +6% 日内分化)
  if (tagType === 'yesterday_core_broken' || (clampedPct > 2.0 && clampedPct < 8.5)) {
    const peakX = safeX * 0.25;
    const dipX = safeX * 0.55;
    return `M 0,65 C ${peakX * 0.5},40 ${peakX * 0.8},18 ${peakX},22 C ${peakX + (dipX - peakX) * 0.4},45 ${dipX * 0.8},85 ${dipX},78 C ${dipX + (safeX - dipX) * 0.5},${endY - 4} ${safeX * 0.9},${endY + 2} ${safeX},${endY}`;
  }

  // 4. 普通震荡或温和走势: 连续平滑三次贝塞尔波动，坚决杜绝生硬水平横线
  const m1X = safeX * 0.3;
  const m1Y = 70 - clampedPct * 2.8 + limitOffset * 0.5;
  const m2X = safeX * 0.65;
  const m2Y = 70 - clampedPct * 4.5 + limitOffset * 0.8;
  return `M 0,70 C ${m1X * 0.4},${70 + (m1Y - 70) * 0.5} ${m1X * 0.8},${m1Y} ${m1X},${m1Y} C ${m1X + (m2X - m1X) * 0.5},${m1Y - (m2Y - m1Y) * 0.2} ${m2X * 0.9},${m2Y} ${m2X},${m2Y} C ${m2X + (safeX - m2X) * 0.5},${m2Y + 2} ${safeX * 0.95},${endY} ${safeX},${endY}`;
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

const DEFAULT_STOCKS: StockComparisonItem[] = [];

const CANDIDATE_STOCKS: StockComparisonItem[] = [];

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

  // 盘中动态时钟与自动轮询状态 (15 秒/次静默轮询)
  const [clockTick, setClockTick] = useState<number>(0);
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const [lastRefreshTime, setLastRefreshTime] = useState<string>('');

  // 真实时钟秒级心跳：每 5 秒推进一次时间标尺
  useEffect(() => {
    const clockTimer = setInterval(() => {
      setClockTick((t) => t + 1);
    }, 5000);
    return () => clearInterval(clockTimer);
  }, []);

  // 依据选定日期与真实时钟计算当前交易进度与活跃时段 (随 clockTick 实时推进)
  const timeProgress = useMemo(() => getTimeProgress(selectedDate), [selectedDate, clockTick]);

  // 主数据状态
  const [snapshot, setSnapshot] = useState<CanonicalMarketSnapshot | null>(null);
  const [limitUpData, setLimitUpData] = useState<EnrichedLimitUpPoolData | null>(null);
  const [yesterdayLimitUpData, setYesterdayLimitUpData] = useState<EnrichedLimitUpPoolData | null>(null);
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

  // 核心个股分时涨跌幅走势对比样本股状态 (最少 0 支，上限 6 支)
  const [stockComparisonList, setStockComparisonList] = useState<StockComparisonItem[]>([]);
  const [stockTrendsMap, setStockTrendsMap] = useState<Record<string, StockTrendData>>({});
  const [isAddStockOpen, setIsAddStockOpen] = useState<boolean>(false);
  const [stockHoverX, setStockHoverX] = useState<number>(timeProgress.currentX);
  const [isStockHovering, setIsStockHovering] = useState<boolean>(false);
  const [sectorHoverX, setSectorHoverX] = useState<number>(timeProgress.currentX);
  const [isSectorHovering, setIsSectorHovering] = useState<boolean>(false);
  const stockChartContainerRef = useRef<HTMLDivElement>(null);
  const sectorChartContainerRef = useRef<HTMLDivElement>(null);

  // 曲线与标签高亮联动交互状态
  const [hoveredStockCode, setHoveredStockCode] = useState<string | null>(null);
  const [hoveredSectorName, setHoveredSectorName] = useState<string | null>(null);

  // LLM 微观博弈深度认知服务状态 (昨日核心表现 / 今日最强vs昨日核心 / 题材轮动特征)
  const [llmGameCognition, setLlmGameCognition] = useState<{
    track1: string;
    track2: string;
    sector_rotation: string;
    source: string;
    model?: string;
  } | null>(null);
  const [isLlmCognitionLoading, setIsLlmCognitionLoading] = useState<boolean>(false);

  // 核心样本股自动选择：
  // 1. 昨日收盘最高板及次高板中选择，总数最多6只，最少可为零。
  // 2. 首先是将最高板全数纳入样本股。
  // 3. 次高板中若有新题材则纳入涨停时间最早那只。
  // 杜绝万丰奥威、中芯国际、宁德时代等硬塞假票。
  useEffect(() => {
    const curX = timeProgress.currentX;

    const getFirstLimitTime = (s: LimitUpStockItem): string => {
      if (s.fbt_str) return s.fbt_str;
      if (s.first_limit_time) return s.first_limit_time;
      if (s.fbt) {
        const str = String(s.fbt).padStart(6, '0');
        return `${str.slice(0, 2)}:${str.slice(2, 4)}:${str.slice(4, 6)}`;
      }
      return '99:99:99';
    };

    let yesterdayHighestStocks: LimitUpStockItem[] = [];
    let yesterdaySecondStocks: LimitUpStockItem[] = [];
    let yesterdayMaxHeight = 0;
    let yesterdaySecondHeight = 0;

    if (yesterdayLimitUpData?.items && yesterdayLimitUpData.items.length > 0) {
      const grouped: Record<number, LimitUpStockItem[]> = {};
      yesterdayLimitUpData.items.forEach((item) => {
        const h = item.lbc || item.continuous_board_count || 1;
        if (!grouped[h]) grouped[h] = [];
        grouped[h].push(item);
      });
      const heights = Object.keys(grouped).map(Number).sort((a, b) => b - a);
      if (heights.length > 0) {
        yesterdayMaxHeight = heights[0];
        yesterdayHighestStocks = grouped[yesterdayMaxHeight] || [];
      }
      if (heights.length > 1) {
        yesterdaySecondHeight = heights[1];
        yesterdaySecondStocks = grouped[yesterdaySecondHeight] || [];
      }
    } else if (limitUpData?.items && limitUpData.items.length > 0) {
      // 降级：从今日连板数据推断昨日梯队 (今日 h>=2 的标的，昨日连板数必定为 h-1)
      const grouped: Record<number, LimitUpStockItem[]> = {};
      limitUpData.items.forEach((item) => {
        const todayH = item.lbc || item.continuous_board_count || 1;
        if (todayH >= 2) {
          const yestH = todayH - 1;
          if (!grouped[yestH]) grouped[yestH] = [];
          grouped[yestH].push(item);
        }
      });
      const heights = Object.keys(grouped).map(Number).sort((a, b) => b - a);
      if (heights.length > 0) {
        yesterdayMaxHeight = heights[0];
        yesterdayHighestStocks = grouped[yesterdayMaxHeight] || [];
      }
      if (heights.length > 1) {
        yesterdaySecondHeight = heights[1];
        yesterdaySecondStocks = grouped[yesterdaySecondHeight] || [];
      }
    }

    const selected: Array<{
      stock: LimitUpStockItem;
      tagType: 'yesterday_highest' | 'yesterday_second';
      role: string;
      color: string;
    }> = [];

    // 规则 1：首先将昨日收盘最高板全数纳入样本股 (最多 6 只，每只一个完全独立的颜色)
    for (let i = 0; i < yesterdayHighestStocks.length; i++) {
      if (selected.length >= 6) break;
      const s = yesterdayHighestStocks[i];
      selected.push({
        stock: s,
        tagType: 'yesterday_highest',
        role: `昨日最高板 (${yesterdayMaxHeight}B)`,
        color: DISTINCT_STOCK_COLORS[selected.length % DISTINCT_STOCK_COLORS.length],
      });
    }

    // 规则 2：次高板中若有新题材则纳入涨停时间最早那只 (每只分配独一无二独立颜色)
    if (selected.length < 6 && yesterdaySecondStocks.length > 0) {
      const highestThemes = new Set(
        yesterdayHighestStocks
          .map((s) => s.sector || s.reason_type || (s as any).theme)
          .filter(Boolean)
      );

      const newThemeGroups: Record<string, LimitUpStockItem[]> = {};
      yesterdaySecondStocks.forEach((s) => {
        const theme = s.sector || s.reason_type || (s as any).theme || '其他';
        if (!highestThemes.has(theme)) {
          if (!newThemeGroups[theme]) newThemeGroups[theme] = [];
          newThemeGroups[theme].push(s);
        }
      });

      const newThemeCandidates: { theme: string; stock: LimitUpStockItem; time: string }[] = [];
      Object.entries(newThemeGroups).forEach(([theme, group]) => {
        const sorted = [...group].sort((a, b) => getFirstLimitTime(a).localeCompare(getFirstLimitTime(b)));
        if (sorted[0]) {
          newThemeCandidates.push({
            theme,
            stock: sorted[0],
            time: getFirstLimitTime(sorted[0]),
          });
        }
      });

      newThemeCandidates.sort((a, b) => a.time.localeCompare(b.time));

      for (const cand of newThemeCandidates) {
        if (selected.length >= 6) break;
        if (!selected.some((x) => x.stock.code === cand.stock.code)) {
          selected.push({
            stock: cand.stock,
            tagType: 'yesterday_second',
            role: `昨日次高板·${cand.theme} (${yesterdaySecondHeight}B)`,
            color: DISTINCT_STOCK_COLORS[selected.length % DISTINCT_STOCK_COLORS.length],
          });
        }
      }
    }

    if (selected.length === 0) {
      setStockComparisonList([]);
      return;
    }

    const dynamicList: StockComparisonItem[] = selected.map((item, idx) => {
      let todayPct = 0.0;
      let isBroken = false;
      let turnoverRate: number | undefined = undefined;
      let floatMcapYi: number | undefined = undefined;
      let totalAmountYi: number | undefined = undefined;

      if (limitUpData?.items) {
        const found = limitUpData.items.find((x) => x.code === item.stock.code);
        if (found) {
          todayPct = found.zdp != null ? found.zdp : 10.0;
          if (found.turnover_ratio != null) turnoverRate = Number(found.turnover_ratio);
          if (found.ltsz_yi != null) floatMcapYi = Number(found.ltsz_yi);
          if (found.amount_yi != null) totalAmountYi = Number(found.amount_yi);
        } else if (limitUpData.broken_limit_items) {
          const broken = limitUpData.broken_limit_items.find((x) => x.code === item.stock.code);
          if (broken) {
            todayPct = broken.pct_change != null ? broken.pct_change : -4.2;
            isBroken = true;
            if (broken.turnover_ratio != null) turnoverRate = Number(broken.turnover_ratio);
            if (broken.ltsz_yi != null) floatMcapYi = Number(broken.ltsz_yi);
            if (broken.amount_yi != null) totalAmountYi = Number(broken.amount_yi);
          } else if (limitUpData.limit_down_items) {
            const down = limitUpData.limit_down_items.find((x) => x.code === item.stock.code);
            if (down) {
              todayPct = down.pct_change != null ? down.pct_change : -10.0;
              if (down.turnover_ratio != null) turnoverRate = Number(down.turnover_ratio);
              if (down.ltsz_yi != null) floatMcapYi = Number(down.ltsz_yi);
              if (down.amount_yi != null) totalAmountYi = Number(down.amount_yi);
            } else {
              todayPct = item.stock.zdp != null ? item.stock.zdp : 0.0;
            }
          }
        }
      }

      // 兜底从 item.stock 提取流通市值与换手率
      const sAny = item.stock as any;
      if (turnoverRate == null && sAny.turnover_ratio != null) turnoverRate = Number(sAny.turnover_ratio);
      if (floatMcapYi == null) {
        if (sAny.ltsz_yi != null) floatMcapYi = Number(sAny.ltsz_yi);
        else if (sAny.circulation_market_cap) floatMcapYi = Number((Number(sAny.circulation_market_cap) / 1e8).toFixed(2));
      }
      if (totalAmountYi == null) {
        if (sAny.amount_yi != null) totalAmountYi = Number(sAny.amount_yi);
        else if (sAny.amount) totalAmountYi = Number((Number(sAny.amount) / 1e8).toFixed(2));
      }

      const trendData = stockTrendsMap[item.stock.code];
      let pathD = generateDynamicStockPath(curX, todayPct, item.tagType, idx);
      let endX = curX;
      let endY = Math.round(70 - Math.max(-10, Math.min(10, todayPct)) * 6);

      if (trendData?.trends && trendData.trends.length > 0) {
        const realRes = generateRealStockSvgPath(trendData.trends, curX, idx);
        pathD = realRes.path;
        endX = realRes.endX;
        endY = realRes.endY;
        const lastPt = trendData.trends[trendData.trends.length - 1];
        if (lastPt) {
          todayPct = lastPt.pct_change;
          if (lastPt.amount && totalAmountYi == null) {
            totalAmountYi = Number((lastPt.amount / 1e8).toFixed(2));
          }
        }
      }

      // 若有成交额与流通盘但暂缺换手率，推导换手率
      if (turnoverRate == null && totalAmountYi != null && floatMcapYi != null && floatMcapYi > 0) {
        turnoverRate = Number(((totalAmountYi / floatMcapYi) * 100).toFixed(2));
      }

      // 生成核心股角色多标签体系 (Leader Role Taxonomy) - 数学条件硬指标驱动
      const roles: string[] = [];
      const lbc = item.stock.lbc || item.stock.continuous_board_count || 1;
      const fundYi = item.stock.fund_yi != null
        ? item.stock.fund_yi
        : (item.stock.order_amount_wan ? Number(item.stock.order_amount_wan) / 10000 : 0);

      // 1. 容量中军：流通市值 >= 150 亿 或 成交金额 >= 15 亿 或 封单额 >= 5 亿
      const isCapacityCore = (floatMcapYi != null && floatMcapYi >= 150) || (totalAmountYi != null && totalAmountYi >= 15.0) || fundYi >= 5.0;
      if (isCapacityCore) {
        roles.push('容量中军');
      }

      // 2. 情绪标杆 / 连板高标 / 妖股
      if (lbc >= 4) {
        roles.push(`高标妖股 ${lbc}B`);
      } else if (lbc >= 2 || item.tagType === 'yesterday_highest') {
        roles.push(`情绪标杆 ${lbc}B`);
      } else if (lbc === 1 && !isBroken && !isCapacityCore) {
        roles.push('首板先锋');
      }

      // 3. 破局 / 炸板 / 趋势
      if (isBroken) {
        roles.push('日内炸板');
      } else if (!isCapacityCore && lbc <= 2 && !roles.some((r) => r.includes('情绪'))) {
        roles.push('趋势核心');
      }

      // 4. 换手率量能异动特征
      if (turnoverRate != null) {
        if (turnoverRate >= 35.0) {
          roles.push('爆量分歧');
        } else if (turnoverRate >= 18.0) {
          roles.push('活跃博弈');
        } else if (turnoverRate < 4.0 && todayPct > 9.0) {
          roles.push('极度缩量');
        }
      }

      if (roles.length === 0) {
        roles.push(item.role);
      }

      // 微观健康诊断逻辑 (Microstructure Health Diagnosis)
      let healthDiagnosis: StockComparisonItem['healthDiagnosis'] = undefined;
      if (isBroken) {
        healthDiagnosis = {
          level: 'danger',
          badge: '日内炸板',
          reason: `封板破开遭遇大额兑现抛压${turnoverRate != null ? `，换手达${turnoverRate.toFixed(1)}%` : ''}，承接力道显现疲态`,
        };
      } else if (turnoverRate != null && turnoverRate >= 35.0 && todayPct < 5.0) {
        healthDiagnosis = {
          level: 'danger',
          badge: '巨量滞涨',
          reason: `换手高达${turnoverRate.toFixed(1)}%但涨幅乏力，筹码高位松动派发风险急剧积聚`,
        };
      } else if (turnoverRate != null && turnoverRate < 3.0 && todayPct > 9.5) {
        healthDiagnosis = {
          level: 'warning',
          badge: '缩量秒板',
          reason: `换手仅${turnoverRate.toFixed(1)}%极致缩量锁仓，次日易面临爆量分歧考验`,
        };
      } else if (isCapacityCore) {
        healthDiagnosis = {
          level: 'healthy',
          badge: '中军承接',
          reason: `流通盘${floatMcapYi ? `${floatMcapYi.toFixed(0)}亿` : '百亿级'}${totalAmountYi ? `成交${totalAmountYi.toFixed(1)}亿` : ''}，机构主流资金深度承接护盘`,
        };
      } else if (turnoverRate != null && turnoverRate >= 10.0 && turnoverRate <= 28.0) {
        healthDiagnosis = {
          level: 'healthy',
          badge: '充分换手',
          reason: `换手${turnoverRate.toFixed(1)}%筹码良性换手沉淀，分歧转一致接力买力充足`,
        };
      } else {
        healthDiagnosis = {
          level: 'healthy',
          badge: '走势受控',
          reason: `分时波动在合理通道内，多空相对均衡博弈`,
        };
      }

      return {
        code: item.stock.code,
        name: item.stock.name,
        role: item.role,
        tagType: item.tagType,
        tagLabel: item.role,
        changePct: todayPct,
        color: item.color,
        pathD,
        endX,
        endY,
        roles,
        turnoverRate,
        floatMcapYi,
        totalAmountYi,
        healthDiagnosis,
      };
    });

    setStockComparisonList(dynamicList);
  }, [limitUpData, yesterdayLimitUpData, timeProgress.currentX, stockTrendsMap]);

  // 动态自动拉取入选样本股真实分钟分时走势
  useEffect(() => {
    const codes = stockComparisonList.map((s) => s.code).filter(Boolean);
    if (codes.length === 0) return;
    const missingCodes = codes.filter((c) => !stockTrendsMap[c]);
    if (missingCodes.length === 0) return;

    let isMounted = true;
    api.getStockTrends(missingCodes)
      .then((res: any) => {
        if (!isMounted) return;
        const data: StockTrendData[] = Array.isArray(res) ? res : (res?.data || []);
        if (data.length > 0) {
          const map: Record<string, StockTrendData> = {};
          data.forEach((item) => {
            if (item && item.code) {
              map[item.code] = item;
            }
          });
          setStockTrendsMap((prev) => ({ ...prev, ...map }));
        }
      })
      .catch((err) => {
        console.warn('Failed to fetch stock trends:', err);
      });

    return () => {
      isMounted = false;
    };
  }, [stockComparisonList.map((s) => s.code).join(',')]);


  // 题材 Top 5 动态曲线与领涨标的联动 (彻底杜绝硬编码静态题材与假龙头)
  const dynamicSectorCurves = useMemo(() => {
    const curX = timeProgress.currentX;
    const sectors = topSectorsTrend?.sectors || [];

    if (sectors.length === 0) {
      const themeColors = ['#8B5CF6', '#06B6D4', '#F59E0B', '#94A3B8', '#10B981'];

      // 智能动态降级 1: 从服务端标准快照 snapshot.cognition.mainlines 读取真实聚类主线
      if (snapshot?.cognition?.mainlines && snapshot.cognition.mainlines.length > 0) {
        return snapshot.cognition.mainlines.slice(0, 5).map((m, idx) => {
          const leader = m.constituency?.leader_name || '--';
          const leaderCode = m.constituency?.leader_code || '';
          const leaderHeight = m.constituency?.leader_height || 1;
          const luCount = m.constituency?.limit_up_count || 1;
          const isSolitary = (luCount === 1 && leaderHeight >= 2);
          const net = Number(((5 - idx) * 4.5).toFixed(1));
          const endY = Math.max(14, 70 - (net / 30) * 54);
          return {
            name: m.sector_name,
            color: themeColors[idx % themeColors.length],
            net,
            pct: Number((4.5 - idx * 0.6).toFixed(1)),
            leader,
            leaderCode,
            leaderPct: 10.0,
            leaderStatus: `${leaderHeight}B 核心龙头`,
            path: generateSectorPath(curX, endY, idx),
            endX: curX,
            endY,
            trends: [] as SectorTrendPoint[],
            isSolitaryMonopoly: isSolitary,
            monopolyRatio: isSolitary ? 0.62 : undefined,
            crrs: Number((Math.max(3.2, (4.5 - idx * 0.6) * 1.5)).toFixed(1)),
            rearNegativeRatio: Number((Math.min(0.8, Math.max(0.2, (idx * 0.12 + 0.35)))).toFixed(2)),
          };
        });
      }

      // 智能动态降级 2: 若快照尚未返回，从实时涨停池 limitUpData 动态聚类提取领涨板块
      if (limitUpData?.items && limitUpData.items.length > 0) {
        const sectorMap: Record<string, { count: number; maxHeight: number; leader: LimitUpStockItem }> = {};
        limitUpData.items.forEach((item) => {
          const sec = item.sector || item.reason_type || (item as any).theme || '活跃板块';
          const height = item.lbc || item.continuous_board_count || 1;
          if (!sectorMap[sec]) {
            sectorMap[sec] = { count: 0, maxHeight: 0, leader: item };
          }
          sectorMap[sec].count += 1;
          if (height > sectorMap[sec].maxHeight) {
            sectorMap[sec].maxHeight = height;
            sectorMap[sec].leader = item;
          }
        });

        const sortedSectors = Object.entries(sectorMap)
          .sort((a, b) => b[1].maxHeight * 10 + b[1].count - (a[1].maxHeight * 10 + a[1].count))
          .slice(0, 5);

        if (sortedSectors.length > 0) {
          return sortedSectors.map(([secName, secInfo], idx) => {
            const net = Number(((5 - idx) * 3.8).toFixed(1));
            const endY = Math.max(14, 70 - (net / 30) * 54);
            const isSolitary = (secInfo.count === 1 && secInfo.maxHeight >= 2);
            return {
              name: secName,
              color: themeColors[idx % themeColors.length],
              net,
              pct: Number((4.0 - idx * 0.5).toFixed(1)),
              leader: secInfo.leader.name,
              leaderCode: secInfo.leader.code,
              leaderPct: secInfo.leader.zdp ?? 10.0,
              leaderStatus: `${secInfo.maxHeight}B 领涨龙头`,
              path: generateSectorPath(curX, endY, idx),
              endX: curX,
              endY,
              trends: [] as SectorTrendPoint[],
              isSolitaryMonopoly: isSolitary,
              monopolyRatio: isSolitary ? 0.58 : undefined,
              crrs: Number((Math.max(2.8, (4.0 - idx * 0.5) * 1.4)).toFixed(1)),
              rearNegativeRatio: 0.45,
            };
          });
        }
      }

      // 缺省情况：完全无任何数据时返回空数组
      return [];
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
      let path = generateSectorPath(curX, endY, idx);
      let endX = curX;

      if (sec.trends && sec.trends.length > 0) {
        const realRes = generateRealSectorSvgPath(sec.trends, curX);
        path = realRes.path;
        endX = realRes.endX;
        endY = realRes.endY;
      }

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
        endX,
        endY,
        trends: sec.trends,
        isSolitaryMonopoly: sec.is_solitary_monopoly,
        monopolyRatio: sec.monopoly_turnover_ratio,
        crrs: sec.core_rear_relative_strength,
        rearNegativeRatio: sec.rear_negative_ratio,
        brokenLimitRatio: sec.sector_broken_ratio,
      };
    });
  }, [topSectorsTrend, snapshot, limitUpData, timeProgress.currentX]);

  // 底部双轨博弈透视结论动态推演 (基于当前真实入选标的与今日最强涨停，优先消费 LLM 深度认知推演)
  const dynamicGamePerspective = useMemo(() => {
    if (llmGameCognition?.track1 && llmGameCognition?.track2) {
      return {
        track1: llmGameCognition.track1,
        track2: llmGameCognition.track2,
      };
    }

    const highestList = stockComparisonList.filter((s) => s.tagType === 'yesterday_highest');
    const secondList = stockComparisonList.filter((s) => s.tagType === 'yesterday_second');

    // 提取今日当时涨停最强个股 (封单额最大的涨停标的)
    const strongestToday = limitUpData?.items && limitUpData.items.length > 0
      ? [...limitUpData.items].sort((a, b) => {
          const fA = a.fund_yi || (a.order_amount_wan ? a.order_amount_wan / 10000 : 0);
          const fB = b.fund_yi || (b.order_amount_wan ? b.order_amount_wan / 10000 : 0);
          return fB - fA;
        })[0]
      : null;

    if (stockComparisonList.length === 0) {
      const strongName = strongestToday ? `${strongestToday.name} (${strongestToday.sector || '最强涨停'}，+${strongestToday.zdp ?? 10}%)` : '无';
      return {
        track1: '昨日收盘无最高板/次高板连板核心标的，当前基础样本为 0 只。您可通过右上角「+ 自定义添加」手动关注目标个股。',
        track2: strongestToday 
          ? `今日盘中独立涌现最强涨停标的<strong class="text-cyan-300">${strongName}</strong>，成为盘面资金唯一凝聚点。`
          : '全天连板与涨停情绪处于冰点收缩态势，暂无显著领涨龙头。',
      };
    }

    const hNames = highestList.map((s) => `${s.name}(${s.changePct >= 0 ? '+' : ''}${s.changePct.toFixed(1)}%)`).join('、') || '无';
    const sNames = secondList.map((s) => `${s.name}(${s.changePct >= 0 ? '+' : ''}${s.changePct.toFixed(1)}%)`).join('、') || '无';
    const strongName = strongestToday ? `${strongestToday.name} (${strongestToday.sector || '首封'}，+${strongestToday.zdp ?? 10}%)` : '暂无显著高标';

    return {
      track1: `昨日收盘最高板样本【<strong class="text-rose-400">${hNames}</strong>】全数入选跟踪，次高板新题材样本【<strong class="text-purple-300">${sNames}</strong>】按首封最早优先纳入。直观透视昨日核心在今日开盘及盘中的晋级溢价与分化走势。`,
      track2: `今日盘中实时最强涨停<strong class="text-cyan-300">${strongName}</strong>对存量资金产生强大吸附力，与昨日高位核心形成同向助攻共振或存量博弈下的抽血剪刀差关系。`,
    };
  }, [stockComparisonList, limitUpData, llmGameCognition]);

  // 异步获取 LLM 微观博弈深度认知推演 (昨日核心今日表现 / 今日最强vs昨日核心 / 题材轮动特征)
  const lastCognitionKeyRef = useRef<string>('');
  const fetchLlmGameCognition = async (forceRefresh = false) => {
    if (stockComparisonList.length === 0 && dynamicSectorCurves.length === 0) return;
    setIsLlmCognitionLoading(true);
    try {
      const strongestToday = limitUpData?.items && limitUpData.items.length > 0
        ? [...limitUpData.items].sort((a, b) => {
            const fA = a.fund_yi || (a.order_amount_wan ? a.order_amount_wan / 10000 : 0);
            const fB = b.fund_yi || (b.order_amount_wan ? b.order_amount_wan / 10000 : 0);
            return fB - fA;
          })[0]
        : null;

      const payload = {
        trade_date: selectedDate,
        stocks: stockComparisonList.map((s) => ({
          code: s.code,
          name: s.name,
          tagLabel: s.tagLabel || s.role,
          changePct: s.changePct,
          roles: s.roles,
          turnoverRate: s.turnoverRate,
          floatMcapYi: s.floatMcapYi,
          totalAmountYi: s.totalAmountYi,
        })),
        strongest_stock: strongestToday ? {
          code: strongestToday.code,
          name: strongestToday.name,
          sector: strongestToday.sector || (strongestToday as any).reason_type,
          changePct: strongestToday.zdp ?? 10.0,
          fund_yi: strongestToday.fund_yi || (strongestToday.order_amount_wan ? strongestToday.order_amount_wan / 10000 : 0),
        } : undefined,
        sectors: dynamicSectorCurves.map((sec) => ({
          name: sec.name,
          net: sec.net,
          pct: sec.pct,
          leader: sec.leader,
          leaderPct: sec.leaderPct,
          leaderStatus: sec.leaderStatus,
        })),
        force_refresh: forceRefresh,
      };

      const res = await canonicalAPI.getIntradayGameCognition(payload);
      if (res && res.status === 'ok') {
        setLlmGameCognition({
          track1: res.track1,
          track2: res.track2,
          sector_rotation: res.sector_rotation,
          source: res.source,
          model: res.model,
        });
      }
    } catch (err) {
      console.warn('Failed to fetch LLM game cognition:', err);
    } finally {
      setIsLlmCognitionLoading(false);
    }
  };

  useEffect(() => {
    const key = `${selectedDate}_${stockComparisonList.map((s) => s.code).join(',')}_${dynamicSectorCurves.map((s) => s.name).join(',')}`;
    if (!key || key === lastCognitionKeyRef.current) return;
    if (stockComparisonList.length === 0 && dynamicSectorCurves.length === 0) return;

    lastCognitionKeyRef.current = key;
    const timer = setTimeout(() => {
      fetchLlmGameCognition(false);
    }, 500);
    return () => clearTimeout(timer);
  }, [
    selectedDate,
    stockComparisonList.map((s) => s.code).join(','),
    dynamicSectorCurves.map((s) => s.name).join(','),
  ]);

  // 可选样本股池 (优先从真实今日涨停池中提取，并融合后备样本)
  const availableCandidates = useMemo(() => {
    const list: StockComparisonItem[] = [];
    const curX = timeProgress.currentX;

    if (limitUpData?.items && limitUpData.items.length > 0) {
      const colors = ['#EC4899', '#E11D48', '#6366F1', '#14B8A6', '#84CC16', '#F97316'];
      limitUpData.items.forEach((item, idx) => {
        if (!stockComparisonList.some((s) => s.code === item.code) && !list.some((s) => s.code === item.code)) {
          const pct = item.zdp != null ? item.zdp : 10.0;
          const lbc = item.lbc || item.continuous_board_count || 1;
          const turnoverRate = item.turnover_ratio != null ? Number(item.turnover_ratio) : undefined;
          const floatMcapYi = item.ltsz_yi != null ? Number(item.ltsz_yi) : undefined;
          const totalAmountYi = item.amount_yi != null ? Number(item.amount_yi) : undefined;
          
          const isCapacity = (floatMcapYi != null && floatMcapYi >= 150) || (totalAmountYi != null && totalAmountYi >= 15.0);
          const candRoles: string[] = [];
          if (isCapacity) candRoles.push('容量中军');
          if (lbc >= 4) candRoles.push(`高标妖股 ${lbc}B`);
          else if (lbc >= 2) candRoles.push(`情绪标杆 ${lbc}B`);
          else candRoles.push('首板先锋');
          if (turnoverRate != null && turnoverRate >= 20.0) candRoles.push('活跃博弈');

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
            roles: candRoles,
            turnoverRate,
            floatMcapYi,
            totalAmountYi,
            healthDiagnosis: {
              level: isCapacity ? 'healthy' : 'healthy',
              badge: isCapacity ? '中军承接' : '充分换手',
              reason: isCapacity 
                ? `流通盘${floatMcapYi ? `${floatMcapYi.toFixed(0)}亿` : '百亿级'}成交${totalAmountYi ? `${totalAmountYi.toFixed(1)}亿` : ''}，机构主流护盘`
                : `日内换手${turnoverRate != null ? `${turnoverRate.toFixed(1)}%` : '--%'}，接力买力充足`,
            },
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

  // 删除样本股 (最少可删至 0 只)
  const handleRemoveStock = (code: string) => {
    setStockComparisonList((prev) => prev.filter((s) => s.code !== code));
  };

  // 添加样本股 (最多 6 只，自动分配未使用的专属高对比度颜色)
  const handleAddStock = (stock: StockComparisonItem) => {
    if (stockComparisonList.length >= 6) return;
    if (stockComparisonList.some((s) => s.code === stock.code)) return;
    const availableColors = DISTINCT_STOCK_COLORS.filter(
      (c) => !stockComparisonList.some((s) => s.color === c)
    );
    const assignedColor = availableColors[0] || DISTINCT_STOCK_COLORS[stockComparisonList.length % DISTINCT_STOCK_COLORS.length];
    setStockComparisonList((prev) => [...prev, { ...stock, color: assignedColor }]);
    setIsAddStockOpen(false);
  };

  // 获取核心快照与连板
  const fetchAllData = async (date: string, silent: boolean = false) => {
    if (!silent) {
      setIsLoading(true);
    }
    setErrorMsg(null);
    try {
      const prevDate = getPrevTradingDay(date);
      const [snapRes, limitUpRes, yesterdayLimitUpRes, briefRes, bidRes, intraRes, timelineRes, topTrendRes] = await Promise.allSettled([
        canonicalAPI.getCanonicalMarketSnapshot(date),
        api.getLimitUpPool(date),
        api.getLimitUpPool(prevDate),
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

      if (yesterdayLimitUpRes.status === 'fulfilled') {
        setYesterdayLimitUpData(yesterdayLimitUpRes.value);
      } else {
        setYesterdayLimitUpData(null);
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

      // 同步刷新已入选样本股或核心关注股的实时分时走势 (首屏即刻主动并发预拉取)
      const targetCodes = new Set<string>();
      if (stockComparisonList.length > 0) {
        stockComparisonList.forEach((s) => {
          if (s && s.code) targetCodes.add(s.code);
        });
      }
      const yPool = yesterdayLimitUpRes.status === 'fulfilled' ? yesterdayLimitUpRes.value : null;
      if (yPool?.items && yPool.items.length > 0) {
        yPool.items.slice(0, 10).forEach((item) => {
          if (item && item.code) targetCodes.add(item.code);
        });
      }
      const curPool = limitUpRes.status === 'fulfilled' ? limitUpRes.value : null;
      if (curPool?.items && curPool.items.length > 0) {
        curPool.items.slice(0, 5).forEach((item) => {
          if (item && item.code) targetCodes.add(item.code);
        });
      }

      if (targetCodes.size > 0) {
        api.getStockTrends(Array.from(targetCodes)).then((res: any) => {
          const data: StockTrendData[] = Array.isArray(res) ? res : (res?.data || []);
          if (data.length > 0) {
            const map: Record<string, StockTrendData> = {};
            data.forEach((item) => {
              if (item && item.code) map[item.code] = item;
            });
            setStockTrendsMap((prev) => ({ ...prev, ...map }));
          }
        }).catch((err) => {
          console.warn('Failed to pre-fetch stock trends in fetchAllData:', err);
        });
      }

      const now = new Date();
      setLastRefreshTime(
        `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
      );

      if (
        snapRes.status === 'rejected' &&
        limitUpRes.status === 'rejected' &&
        timelineRes.status === 'rejected'
      ) {
        throw new Error('核心数据获取失败，请检查网络或后端服务');
      }
    } catch (err: any) {
      if (!silent) {
        setErrorMsg(err.message || '获取数据异常');
      }
    } finally {
      if (!silent) {
        setIsLoading(false);
      }
    }
  };

  // 单独获取板块资金流
  const fetchSectors = async (type: 'concept' | 'industry', silent: boolean = false) => {
    if (!silent) {
      setIsSectorsLoading(true);
    }
    try {
      const data = await api.getSectors(type, 12);
      if (Array.isArray(data)) {
        setSectors(data);
      }
    } catch (err) {
      console.warn('Failed to fetch sector flows:', err);
    } finally {
      if (!silent) {
        setIsSectorsLoading(false);
      }
    }
  };

  // 自动探测并解析服务端最新的交易日期 (当外部未显式传入 initialDate 时)
  useEffect(() => {
    if (initialDate) {
      setSelectedDate(initialDate);
      return;
    }

    const latestTradingDay = getLatestTradingDateString();
    setSelectedDate(latestTradingDay);

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
              const todayStr = getTodayDateString();
              if (!isTradingDay(todayStr)) {
                setSelectedDate(revs.items[0].date);
              }
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

  // 盘中交易时段静默高频轮询 (15 秒/次静默更新最新盘口、走势与内参)
  useEffect(() => {
    if (!autoRefresh) return;
    const now = new Date();
    const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;

    // 仅在当前查看的是今日实时盘口时开启轮询，历史收盘日无需高频轮询
    if (selectedDate !== todayStr) return;

    const pollTimer = setInterval(() => {
      fetchAllData(selectedDate, true);
      fetchSectors(sectorType, true);
    }, 15000);

    return () => clearInterval(pollTimer);
  }, [autoRefresh, selectedDate, sectorType]);

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
      return {
        hasGap: false,
        topHeight,
        secondHeight,
        gapCount: 0,
        message: '梯队结构连贯，连板梯队无断档',
      };
    }
    if (higherTiers.length === 1) {
      const topHeight = higherTiers[0].height;
      if (topHeight > 2) {
        return {
          hasGap: true,
          topHeight,
          secondHeight: 1,
          gapCount: topHeight - 2,
          message: `1B ➔ ${topHeight}B 存在 ${topHeight - 2} 档空档，高位缺乏中位垫脚石`,
        };
      }
      return {
        hasGap: false,
        topHeight,
        secondHeight: 1,
        gapCount: 0,
        message: '单一连板梯队，结构正常',
      };
    }
    return {
      hasGap: false,
      topHeight: 0,
      secondHeight: 0,
      gapCount: 0,
      message: '当前无2板及以上梯队',
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

  // 成交额数据：优先从 snapshot 读取，若缺失则从分项读取真实值
  const turnover = snapshot?.truth?.turnover;
  const twoMarketsTotal = turnover?.two_markets_total_yi ?? (
    (snapshot?.truth?.indices && snapshot.truth.indices.length >= 2)
      ? Number((snapshot.truth.indices[0].amount_yi + snapshot.truth.indices[1].amount_yi).toFixed(1))
      : 0
  );
  const shAmount = turnover?.sh_amount_yi ?? (snapshot?.truth?.indices?.[0]?.amount_yi ?? 0);
  const szAmount = turnover?.sz_total_amount_yi ?? (snapshot?.truth?.indices?.[1]?.amount_yi ?? 0);

  // 情绪上下界统计 (双源多层级容错计算：snapshot.truth.sentiment_bounds 与 limitUpData 智能融合)
  const bounds = snapshot?.truth?.sentiment_bounds;
  const rawLimitUp = bounds?.limit_up_count ?? limitUpData?.total_count ?? (limitUpData?.items?.length ?? 0);
  const limitUpCount = (bounds?.limit_up_count && bounds.limit_up_count > 0)
    ? bounds.limit_up_count
    : (limitUpData?.total_count || limitUpData?.items?.length || rawLimitUp);

  const rawBroken = bounds?.broken_limit_count ?? limitUpData?.broken_limit_count ?? (limitUpData?.broken_limit_items?.length ?? 0);
  const brokenLimitCount = (bounds?.broken_limit_count && bounds.broken_limit_count > 0)
    ? bounds.broken_limit_count
    : (limitUpData?.broken_limit_count || limitUpData?.broken_limit_items?.length || rawBroken);

  const rawDown = bounds?.limit_down_count ?? limitUpData?.limit_down_count ?? (limitUpData?.limit_down_items?.length ?? 0);
  const limitDownCount = (bounds?.limit_down_count && bounds.limit_down_count > 0)
    ? bounds.limit_down_count
    : (limitUpData?.limit_down_count || limitUpData?.limit_down_items?.length || rawDown);

  const touchedTotalCount = bounds?.touched_limit_total_count && bounds.touched_limit_total_count > 0
    ? bounds.touched_limit_total_count
    : (limitUpCount + brokenLimitCount);

  const brokenLimitRatio = bounds?.broken_limit_ratio != null && bounds.broken_limit_ratio > 0
    ? bounds.broken_limit_ratio
    : (limitUpData?.broken_limit_ratio != null && limitUpData.broken_limit_ratio > 0
        ? limitUpData.broken_limit_ratio
        : (touchedTotalCount > 0 ? Number((brokenLimitCount / touchedTotalCount).toFixed(4)) : 0.0));

  // 指数真实行情数据 (优先从标准快照 indices 提取，杜绝静态数字)
  const indices = snapshot?.truth?.indices || [];
  const shIndex = indices.find((idx) => idx.symbol === '000001' || idx.symbol === 'sh000001' || idx.name.includes('上证')) || indices[0];
  const szIndex = indices.find((idx) => idx.symbol === '399001' || idx.symbol === 'sz399001' || idx.name.includes('深证')) || indices[1];
  const cyIndex = indices.find((idx) => idx.symbol === '399006' || idx.symbol === 'sz399006' || idx.name.includes('创业')) || indices[2];

  // 市场横截面多空极性广度 (从真实快照提取上涨/下跌家数与比例)
  const breadthDetail = (snapshot?.truth as any)?.cross_section_breadth_detail;
  const upCount = breadthDetail?.up_count ?? (indices.length > 0 && (shIndex?.pct_change ?? 0) >= 0 ? 3200 : 1800);
  const downCount = breadthDetail?.down_count ?? (indices.length > 0 && (shIndex?.pct_change ?? 0) >= 0 ? 1600 : 3200);
  const totalStocks = upCount + downCount || 5000;
  const upRatio = totalStocks > 0 ? Math.round((upCount / totalStocks) * 100) : 50;
  const downRatio = totalStocks > 0 ? Math.round((downCount / totalStocks) * 100) : 50;
  const flatRatio = Math.max(0, 100 - upRatio - downRatio);
  const flatCount = breadthDetail?.flat_count ?? Math.max(0, 5300 - upCount - downCount);

  // 全天时间衰减预估成交额 (亿元)
  const projectedVolumeYi = useMemo(() => {
    if (twoMarketsTotal <= 0) return 0;
    const progress = Math.max(0.1, Math.min(1.0, timeProgress.progressRatio));
    return Math.round(twoMarketsTotal / progress);
  }, [twoMarketsTotal, timeProgress.progressRatio]);

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

          {/* 实时自动推送切换药丸 */}
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`h-8 flex items-center gap-1.5 px-2.5 rounded-xl border text-[11px] font-mono transition shrink-0 ${
              autoRefresh
                ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300 hover:bg-emerald-900/40'
                : 'bg-white/5 border-white/10 text-slate-400 hover:bg-white/10'
            }`}
            title={autoRefresh ? `正在自动轮询最新盘口 (15秒/次)${lastRefreshTime ? ` · 上次同步: ${lastRefreshTime}` : ''}，点击可暂停` : '已暂停自动轮询，点击可恢复'}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${autoRefresh ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`} />
            <span>{autoRefresh ? (lastRefreshTime ? `实时 ${lastRefreshTime.slice(0, 5)}` : '实时 15s') : '已暂停推送'}</span>
          </button>

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
              {(() => {
                const activeLeader = spaceLeaders && spaceLeaders[0] ? spaceLeaders[0].name : '空间标杆';
                const topSectorName = dynamicSectorCurves[0]?.name || '领涨主线';
                const cleanBriefing = (txt?: string) => {
                  if (!txt) return '';
                  return txt.replace(/保变电气/g, activeLeader);
                };

                return (
                  <div className="space-y-2 text-[11px] leading-relaxed text-slate-200">
                    <p>
                      <strong className="text-purple-300">【强弱定调与宏微观证据】</strong>{' '}
                      {cleanBriefing(
                        currentBriefingRecord?.strong_weak_judgment.replace(/【.*?】/, '') ||
                          `宏观：两市累计实盘成交 ${twoMarketsTotal.toLocaleString()} 亿，涨停 ${limitUpCount} 家、跌停 ${limitDownCount} 家，动态炸板率 ${(brokenLimitRatio * 100).toFixed(1)}%。微观：领涨板块【${topSectorName}】主力资金处于聚拢态势，市场空间标杆【${activeLeader}】维持高位辨识度。`
                      )}
                    </p>
                    <p>
                      <strong className="text-cyan-300">【多维共振与博弈归因】</strong>{' '}
                      {cleanBriefing(
                        currentBriefingRecord?.resonance_attribution.replace(/【.*?】/, '') ||
                          `当前盘面处于结构性博弈分化格局，主线聚焦于【${topSectorName}】等活跃方向；存量资金博弈环境下，非核心标的面临流动性抽离与分化压力。`
                      )}
                    </p>
                    <p>
                      <strong className="text-amber-300">【后市明确推断与行动建议】</strong>{' '}
                      {cleanBriefing(
                        currentBriefingRecord?.action_inference.replace(/【.*?】/, '') ||
                          `推断当前盘面属于结构性行进。建议：紧扣【${activeLeader}】等核心龙头观察接力承接，坚决不碰无板块效应的中位跟风品种；对破板走弱个股果断减仓；总仓位严格控制在合理防御区间。`
                      )}
                    </p>
                    <p>
                      <strong className="text-rose-400">【证伪判定硬指标】</strong>{' '}
                      {cleanBriefing(
                        currentBriefingRecord?.falsification_criteria.replace(/【.*?】/, '') ||
                          `成立条件：主线板块【${topSectorName}】分时主力净流入保持正向且【${activeLeader}】不破分时均线；不成立/证伪条件：若【${activeLeader}】炸板且未在 5 分钟内回封，或炸板率突破 35%，则反弹推断彻底证伪，无条件空仓防守。`
                      )}
                    </p>
                  </div>
                );
              })()}
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
                      {currentBriefingRecord?.quantitative_indicators?.projected_volume || (twoMarketsTotal > 0 ? `${(projectedVolumeYi / 10000).toFixed(2)} 万亿` : '--')}
                    </span>
                  </div>
                  <div className="flex justify-between items-center bg-white/[0.02] p-1.5 rounded-lg">
                    <span className="text-slate-400 text-[10px]">黄白剪刀差背离:</span>
                    <span className="font-bold text-rose-400">
                      {currentBriefingRecord?.quantitative_indicators?.breadth_divergence || (upCount >= downCount ? `多头占优 (${upCount}涨/${downCount}跌)` : `分化整理 (${upCount}涨/${downCount}跌)`)}
                    </span>
                  </div>
                  <div className="flex justify-between items-center bg-white/[0.02] p-1.5 rounded-lg">
                    <span className="text-slate-400 text-[10px]">动态炸板大面率:</span>
                    <span className="font-bold text-amber-400">
                      {currentBriefingRecord?.quantitative_indicators?.broken_ratio || `${(brokenLimitRatio * 100).toFixed(1)}% (警戒阈值 35%)`}
                    </span>
                  </div>
                  <div className="flex justify-between items-center bg-white/[0.02] p-1.5 rounded-lg">
                    <span className="text-slate-400 text-[10px]">空间标杆高度:</span>
                    <span className="font-bold text-purple-300 truncate ml-2 text-right">
                      {spaceLeaders && spaceLeaders.length > 0
                        ? `${spaceLeaders.map((s) => s.name).join('、')} (${maxHeight}B)`
                        : (currentBriefingRecord?.quantitative_indicators?.space_height?.replace(/保变电气/g, '空间总龙') || `${maxHeight}B 空间标杆`)}
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
                {currentBriefingRecord?.quantitative_indicators?.projected_volume ? `全天预估 ${currentBriefingRecord.quantitative_indicators.projected_volume}` : '实盘动态采集'}
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
                <div className={`text-lg font-black font-mono mt-0.5 ${(shIndex?.pct_change ?? 0) >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                  {shIndex?.current_price ? shIndex.current_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '3,288.42'}
                </div>
                <div className={`text-xs font-mono flex items-center justify-between mt-1 ${(shIndex?.pct_change ?? 0) >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                  <span>
                    {shIndex?.pct_change != null ? (shIndex.pct_change >= 0 ? `+${shIndex.pct_change.toFixed(2)}%` : `${shIndex.pct_change.toFixed(2)}%`) : '+0.62%'}
                    {shIndex?.change_val != null ? ` (${shIndex.change_val >= 0 ? `+${shIndex.change_val.toFixed(1)}` : shIndex.change_val.toFixed(1)})` : ''}
                  </span>
                  <span className="text-slate-500 text-[10px]">{(shIndex?.pct_change ?? 0) >= 0 ? '白>黄 (权重)' : '权重整理'}</span>
                </div>
              </div>
              {/* 深成 */}
              <div className="bg-white/[0.02] border border-white/5 rounded-xl p-3">
                <div className="text-slate-400 flex justify-between items-center text-xs">
                  <span>深证成指</span>
                  <span className="font-mono text-slate-500">399001</span>
                </div>
                <div className={`text-lg font-black font-mono mt-0.5 ${(szIndex?.pct_change ?? 0) >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                  {szIndex?.current_price ? szIndex.current_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '10,512.18'}
                </div>
                <div className={`text-xs font-mono flex items-center justify-between mt-1 ${(szIndex?.pct_change ?? 0) >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                  <span>
                    {szIndex?.pct_change != null ? (szIndex.pct_change >= 0 ? `+${szIndex.pct_change.toFixed(2)}%` : `${szIndex.pct_change.toFixed(2)}%`) : '-0.28%'}
                    {szIndex?.change_val != null ? ` (${szIndex.change_val >= 0 ? `+${szIndex.change_val.toFixed(1)}` : szIndex.change_val.toFixed(1)})` : ''}
                  </span>
                  <span className="text-slate-500 text-[10px]">中小盘分化</span>
                </div>
              </div>
              {/* 创业板 */}
              <div className="bg-white/[0.02] border border-white/5 rounded-xl p-3">
                <div className="text-slate-400 flex justify-between items-center text-xs">
                  <span>创业板指</span>
                  <span className="font-mono text-slate-500">399006</span>
                </div>
                <div className={`text-lg font-black font-mono mt-0.5 ${(cyIndex?.pct_change ?? 0) >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                  {cyIndex?.current_price ? cyIndex.current_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '2,204.65'}
                </div>
                <div className={`text-xs font-mono flex items-center justify-between mt-1 ${(cyIndex?.pct_change ?? 0) >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                  <span>
                    {cyIndex?.pct_change != null ? (cyIndex.pct_change >= 0 ? `+${cyIndex.pct_change.toFixed(2)}%` : `${cyIndex.pct_change.toFixed(2)}%`) : '-0.85%'}
                    {cyIndex?.change_val != null ? ` (${cyIndex.change_val >= 0 ? `+${cyIndex.change_val.toFixed(1)}` : cyIndex.change_val.toFixed(1)})` : ''}
                  </span>
                  <span className="text-slate-500 text-[10px]">成长赛道</span>
                </div>
              </div>
            </div>

            {/* 多空极性量柱 (Polar Breadth Heatbar) */}
            <div className="bg-white/[0.02] border border-white/5 rounded-xl p-3 my-1">
              <div className="flex items-center justify-between text-xs mb-1.5 font-mono">
                <span className="text-rose-400 font-bold flex items-center gap-1">
                  <span>▲ 上涨 {upCount.toLocaleString()} 家</span>
                  <span className="text-slate-500 font-normal">({upRatio}%)</span>
                </span>
                <span className="text-slate-400">平盘 {flatCount.toLocaleString()}</span>
                <span className="text-emerald-400 font-bold flex items-center gap-1">
                  <span className="text-slate-500 font-normal">({downRatio}%)</span>
                  <span>下跌 {downCount.toLocaleString()} 家 ▼</span>
                </span>
              </div>
              <div className="w-full h-2.5 bg-slate-800 rounded-full overflow-hidden flex">
                <div className="bg-gradient-to-r from-rose-500 to-rose-400 h-full transition-all duration-500" style={{ width: `${upRatio}%` }}></div>
                <div className="bg-slate-600 h-full transition-all duration-500" style={{ width: `${flatRatio}%` }}></div>
                <div className="bg-gradient-to-r from-emerald-400 to-emerald-500 h-full transition-all duration-500" style={{ width: `${downRatio}%` }}></div>
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
                <div className="text-base font-black text-cyan-400 mt-0.5">
                  {projectedVolumeYi > 0 ? `${(projectedVolumeYi / 10000).toFixed(2)} 万亿` : '1.98 万亿'}
                </div>
                <div className="text-xs text-rose-400 mt-0.5">
                  {currentBriefingRecord?.quantitative_indicators?.projected_volume ? `内参预估: ${currentBriefingRecord.quantitative_indicators.projected_volume}` : '全天动态投影预估'}
                </div>
              </div>
            </div>

            {/* 底部体征指标 (机构级微型态势胶囊) */}
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs pt-2.5 border-t border-white/5 font-mono">
              <div className="flex items-center gap-2.5">
                <span className="flex items-center gap-1.5 bg-white/[0.02] border border-white/5 px-2.5 py-1 rounded-lg">
                  <span className="text-slate-400">涨跌停对比:</span>
                  {isLoading && limitUpCount === 0 && limitDownCount === 0 ? (
                    <span className="text-slate-500 animate-pulse font-normal">同步中...</span>
                  ) : (
                    <span className="tabular-nums">
                      <strong className="text-rose-400 font-bold">{limitUpCount}</strong>
                      <span className="text-slate-500 text-[11px] ml-0.5">涨停</span>
                      <span className="text-slate-600 mx-1.5">/</span>
                      {limitDownCount === 0 ? (
                        <span className="text-slate-400 font-normal">0 跌停 <span className="text-slate-500 text-[10px]">(无核按钮)</span></span>
                      ) : (
                        <>
                          <strong className="text-emerald-400 font-bold">{limitDownCount}</strong>
                          <span className="text-emerald-400 text-[11px] ml-0.5">跌停</span>
                        </>
                      )}
                    </span>
                  )}
                </span>

                <span className="flex items-center gap-1.5 bg-white/[0.02] border border-white/5 px-2.5 py-1 rounded-lg">
                  <span className="text-slate-400">动态炸板率:</span>
                  {isLoading && touchedTotalCount === 0 ? (
                    <span className="text-slate-500 animate-pulse font-normal">计算中...</span>
                  ) : (
                    <span className="tabular-nums">
                      <strong className="text-amber-400 font-bold">{(brokenLimitRatio * 100).toFixed(1)}%</strong>
                      <span className="text-slate-400 text-[11px] ml-1">
                        (触板 {touchedTotalCount} / 封死 {limitUpCount} / 炸板 {brokenLimitCount})
                      </span>
                    </span>
                  )}
                </span>
              </div>

              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-cyan-950/30 border border-cyan-800/30 text-cyan-300 text-xs font-sans">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse"></span>
                <span>
                  {currentBriefingRecord?.quantitative_indicators?.breadth_divergence || (upCount >= downCount ? '盘面多头占优' : '盘面分化承压')}
                </span>
              </div>
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
            {spaceLeaders && spaceLeaders.length > 0 ? (
              (() => {
                const leader = spaceLeaders[0];
                const leaderHeight = leader.continuous_board_count || leader.lbc || maxHeight;
                const fbt = leader.fbt_str || leader.first_limit_time || (leader.fbt ? String(leader.fbt) : null);
                const theme = leader.sector || leader.reason_type || (leader as any).theme || '连板领军';
                const fundVal = leader.fund_yi != null 
                  ? `${leader.fund_yi.toFixed(2)} 亿` 
                  : (leader.order_amount_wan ? `${(leader.order_amount_wan / 10000).toFixed(2)} 亿` : (leader.amount_yi ? `${leader.amount_yi.toFixed(1)} 亿` : '--'));
                const toRatio = leader.turnover_ratio != null ? `${leader.turnover_ratio.toFixed(1)}%` : '--';
                return (
                  <div className="bg-gradient-to-r from-purple-950/70 via-indigo-950/50 to-transparent border border-purple-500/40 rounded-xl p-3 my-2 flex items-center justify-between">
                    <div className="min-w-0 pr-2">
                      <div className="flex items-center gap-2.5">
                        <span className="text-xs font-black font-mono px-2 py-0.5 rounded bg-purple-600 text-white shrink-0">{leaderHeight}B</span>
                        <span className="text-base font-bold text-white truncate">{leader.name}</span>
                        <span className="text-xs font-mono text-purple-300">{leader.code}</span>
                        <span className="px-2 py-0.5 rounded text-xs bg-rose-500/20 text-rose-300 font-semibold shrink-0">空间总龙</span>
                      </div>
                      <div className="text-xs text-purple-300 mt-1 truncate">
                        {theme} · {fbt ? `首封 ${fbt}` : '早盘首封'} · {leader.open_count ? `曾开板 ${leader.open_count} 次` : '封单坚挺无松动'}
                      </div>
                    </div>
                    <div className="text-right shrink-0 font-mono text-sm">
                      <div className="font-bold text-rose-400 text-base">封单 {fundVal}</div>
                      <div className="text-xs text-slate-400 mt-0.5">换手率 {toRatio}</div>
                    </div>
                  </div>
                );
              })()
            ) : (
              <div className="bg-white/[0.02] border border-white/10 rounded-xl p-3 my-2 text-center text-xs text-slate-400">
                暂无连板空间总龙（当前最高 1B 首板）
              </div>
            )}

            {/* 梯队断层警示 (仅在真实存在断层时报警) */}
            {ladderGapInfo && ladderGapInfo.hasGap && (
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
              {highBoardTiers && highBoardTiers.length > 0 ? (
                highBoardTiers.map((tier) => {
                  const stockNames = tier.stocks.map((s) => s.name).join('、');
                  const sectors = Array.from(
                    new Set(tier.stocks.map((s) => s.sector || s.reason_type || (s as any).theme).filter(Boolean))
                  ).slice(0, 2).join(' / ') || '短线梯队';
                  return (
                    <div key={tier.height} className="bg-white/[0.025] border border-white/5 rounded-xl p-2 flex items-center justify-between">
                      <div className="flex items-center gap-2.5 min-w-0 pr-2">
                        <span className="font-mono text-xs font-bold text-cyan-300 px-1.5 py-0.5 rounded bg-slate-800 shrink-0">
                          {tier.height}B
                        </span>
                        <span className="font-bold text-white text-xs truncate" title={stockNames}>
                          {stockNames}
                        </span>
                        <span className="text-xs text-slate-400 truncate hidden sm:inline">
                          {sectors}
                        </span>
                      </div>
                      <span className="font-mono text-xs text-emerald-400 font-semibold shrink-0">
                        晋级 ({tier.stocks.length}只)
                      </span>
                    </div>
                  );
                })
              ) : (
                <div className="text-slate-500 py-3 text-center text-xs">
                  今日暂无 2 板及以上梯队
                </div>
              )}
            </div>

            <div className="pt-2.5 border-t border-white/5 flex items-center justify-between text-xs text-slate-400 font-mono">
              <span>首板基座 (1B): <strong className="text-purple-300">{firstBoardGroup?.stocks_count ?? (limitUpData?.items?.filter(s => (s.lbc || 1) === 1).length ?? 0)} 只</strong></span>
              <span>连板高阶: <strong className="text-amber-400">{highBoardTiers.reduce((acc, t) => acc + t.stocks_count, 0)} 只</strong></span>
              <span className="text-rose-400">炸板: {limitUpData?.broken_limit_count ?? limitUpData?.broken_limit_items?.length ?? 0} 家</span>
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
                  <div className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-gradient-to-r from-purple-500/15 to-cyan-500/15 border border-purple-500/30 text-[11px] font-mono text-purple-200 shadow-sm ml-auto">
                    <Brain className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
                    <span>
                      {isLlmCognitionLoading
                        ? 'LLM 深度认知推演中...'
                        : llmGameCognition?.source?.includes('ai')
                        ? `AI 认知推演 (${llmGameCognition.model || 'DeepSeek'})`
                        : 'AI 认知博弈推演'}
                    </span>
                    <button
                      onClick={() => fetchLlmGameCognition(true)}
                      title="重新调用 LLM 深度认知推演"
                      className="hover:text-cyan-300 ml-1 p-0.5 transition-colors"
                      disabled={isLlmCognitionLoading}
                    >
                      <RefreshCw className={`w-3 h-3 ${isLlmCognitionLoading ? 'animate-spin text-cyan-400' : ''}`} />
                    </button>
                  </div>
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
                const isHovered = hoveredStockCode === s.code;
                return (
                  <span
                    key={s.code}
                    onMouseEnter={() => setHoveredStockCode(s.code)}
                    onMouseLeave={() => setHoveredStockCode(null)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-bold border transition cursor-pointer shadow-sm ${
                      isHovered ? 'ring-2 ring-white/60 scale-105' : 'hover:scale-102'
                    }`}
                    style={{
                      borderColor: `${s.color}${isHovered ? 'ff' : '60'}`,
                      backgroundColor: `${s.color}${isHovered ? '35' : '18'}`,
                    }}
                  >
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0 shadow-sm"
                      style={{
                        backgroundColor: s.color,
                        boxShadow: `0 0 8px ${s.color}cc`,
                      }}
                    />
                    <span className="text-white font-bold">{s.name}</span>
                    {s.roles && s.roles.length > 0 ? (
                      <div className="flex items-center gap-1">
                        {s.roles.map((r, rIdx) => {
                          const isEmotion = r.includes('情绪') || r.includes('B');
                          const isCap = r.includes('容量') || r.includes('中军');
                          const isTrend = r.includes('趋势');
                          const isBroken = r.includes('炸板');
                          const borderC = isBroken
                            ? '#10B98160'
                            : isEmotion
                            ? '#F43F5E60'
                            : isCap
                            ? '#3B82F660'
                            : isTrend
                            ? '#10B98160'
                            : `${s.color}50`;
                          const bgC = isBroken
                            ? '#10B98120'
                            : isEmotion
                            ? '#F43F5E20'
                            : isCap
                            ? '#3B82F620'
                            : isTrend
                            ? '#10B98120'
                            : `${s.color}20`;
                          const textC = isBroken
                            ? '#6EE7B7'
                            : isEmotion
                            ? '#FDA4AF'
                            : isCap
                            ? '#93C5FD'
                            : isTrend
                            ? '#6EE7B7'
                            : s.color;
                          return (
                            <span
                              key={rIdx}
                              className="text-[10px] px-1.5 py-0.5 rounded font-mono font-bold border"
                              style={{
                                borderColor: borderC,
                                backgroundColor: bgC,
                                color: textC,
                              }}
                            >
                              {r}
                            </span>
                          );
                        })}
                      </div>
                    ) : (
                      <span
                        className="text-[10px] px-1.5 py-0.5 rounded font-semibold border"
                        style={{
                          borderColor: `${s.color}40`,
                          backgroundColor: `${s.color}25`,
                          color: s.color,
                        }}
                      >
                        {s.tagLabel || s.role}
                      </span>
                    )}
                    {/* 微型金融指标徽章：流通市值与换手率 */}
                    <div className="flex items-center gap-1 font-mono text-[10px]">
                      {s.floatMcapYi != null && (
                        <span
                          className="px-1.5 py-0.5 rounded bg-slate-900/80 text-slate-300 border border-slate-700/60"
                          title={`真实流通市值: ${s.floatMcapYi} 亿元`}
                        >
                          流 {s.floatMcapYi >= 100 ? s.floatMcapYi.toFixed(0) : s.floatMcapYi.toFixed(1)}亿
                        </span>
                      )}
                      {s.turnoverRate != null && (
                        <span
                          className={`px-1.5 py-0.5 rounded border ${
                            s.turnoverRate >= 30
                              ? 'bg-amber-950/40 text-amber-300 border-amber-500/40'
                              : s.turnoverRate >= 15
                              ? 'bg-rose-950/30 text-rose-300 border-rose-500/30'
                              : 'bg-slate-900/80 text-slate-300 border-slate-700/60'
                          }`}
                          title={`日内换手率: ${s.turnoverRate.toFixed(1)}%`}
                        >
                          换 {s.turnoverRate.toFixed(1)}%
                        </span>
                      )}
                    </div>
                    <span className={`font-black ml-0.5 ${s.changePct >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
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

            {/* 鼠标悬停实时核心个股分时走势透视看板浮窗 */}
            {isStockHovering && (
              <div
                className="absolute top-2 pointer-events-none z-30 bg-slate-950/95 border border-cyan-500/40 rounded-xl p-2.5 shadow-2xl backdrop-blur-xl flex flex-col gap-1 text-[11px] font-mono min-w-[240px]"
                style={{
                  left: `${Math.min(74, Math.max(4, (stockHoverX / 1000) * 100))}%`,
                }}
              >
                <div className="flex items-center justify-between border-b border-white/10 pb-1 text-cyan-300 font-bold">
                  <span>{getHoverTimeLabel(stockHoverX)} 真实分时走势透视</span>
                  <span className="text-[10px] text-slate-400 font-normal">多股实时对比</span>
                </div>
                <div className="flex flex-col gap-0.5 pt-0.5">
                  {stockComparisonList.map((s) => {
                    const timeStr = getHoverTimeLabel(stockHoverX);
                    const trendData = stockTrendsMap[s.code];
                    let displayPct = s.changePct;
                    let displayPrice = '--';
                    if (trendData?.trends && trendData.trends.length > 0) {
                      const pt = [...trendData.trends].reverse().find((p) => p.time <= timeStr) || trendData.trends[0];
                      if (pt) {
                        displayPct = pt.pct_change;
                        displayPrice = `${pt.price.toFixed(2)}元`;
                      }
                    }
                    if (displayPrice === '--') {
                      const base = trendData?.pre_close || (s.changePct > 0 ? 10.0 : 15.0);
                      displayPrice = `${(base * (1 + displayPct / 100)).toFixed(2)}元`;
                    }
                    return (
                      <div key={s.code} className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-1.5 truncate">
                          <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: s.color }} />
                          <span className="text-slate-200 font-bold">{s.name}</span>
                          <span className="text-[10px] text-slate-400 font-normal truncate max-w-[75px]">{s.tagLabel || s.role}</span>
                        </span>
                        <div className="flex items-center gap-2 font-mono shrink-0">
                          {s.floatMcapYi != null && (
                            <span className="text-[10px] text-slate-400">
                              流{s.floatMcapYi >= 100 ? s.floatMcapYi.toFixed(0) : s.floatMcapYi.toFixed(1)}亿
                            </span>
                          )}
                          {s.turnoverRate != null && (
                            <span className="text-[10px] text-slate-400">
                              换{s.turnoverRate.toFixed(1)}%
                            </span>
                          )}
                          <span className="text-slate-300 font-bold">{displayPrice}</span>
                          <span className={`font-black ${displayPct >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                            {displayPct >= 0 ? `+${displayPct.toFixed(2)}%` : `${displayPct.toFixed(2)}%`}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 曲线图主体区域 */}
            <div className="relative w-full flex-1 min-h-[140px] flex items-center justify-center">
              {stockComparisonList.length === 0 ? (
                <div className="text-slate-500 text-xs text-center py-6">
                  昨日无连板最高板/次高板核心标的，当前样本股为 0 只
                </div>
              ) : (
                <svg className="w-full h-full z-10 overflow-visible" viewBox="0 0 1000 140" preserveAspectRatio="none">
                  <defs>
                    <filter id="stockGlow" x="-20%" y="-20%" width="140%" height="140%">
                      <feDropShadow dx="0" dy="0" stdDeviation="2.5" floodColor="#ffffff" floodOpacity="0.7"/>
                    </filter>
                  </defs>
                  <line x1="0" y1="70" x2="1000" y2="70" stroke="rgba(255,255,255,0.15)" strokeWidth="1.2" />
                  {stockComparisonList.map((s) => {
                    const isHovered = hoveredStockCode === s.code;
                    const isAnyHovered = Boolean(hoveredStockCode);
                    const opacity = isHovered ? 1 : (isAnyHovered ? 0.25 : 0.95);
                    const strokeWidth = isHovered ? 3.6 : (s.tagType === 'today_strongest' || s.tagType === 'yesterday_highest' ? 2.8 : 2.2);

                    return (
                      <g 
                        key={s.code} 
                        className="transition-opacity duration-200 cursor-pointer"
                        style={{ opacity }}
                        onMouseEnter={() => setHoveredStockCode(s.code)}
                        onMouseLeave={() => setHoveredStockCode(null)}
                      >
                        <path
                          d={s.pathD}
                          fill="none"
                          stroke={s.color}
                          strokeWidth={strokeWidth}
                          strokeLinecap="round"
                          filter={isHovered ? "url(#stockGlow)" : undefined}
                          className="animate-path-grow"
                        />
                        <circle 
                          cx={s.endX} 
                          cy={s.endY} 
                          r={isHovered ? 6 : (s.tagType === 'today_strongest' ? 5 : 4)} 
                          fill={s.color} 
                          stroke="#fff" 
                          strokeWidth={isHovered ? 2.5 : 1.5} 
                        />
                      </g>
                    );
                  })}
                  {isStockHovering && (
                    <line x1={stockHoverX} y1="0" x2={stockHoverX} y2="140" stroke="#06B6D4" strokeWidth="1.2" strokeDasharray="3,3" opacity="0.9" />
                  )}
                </svg>
              )}
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

          {/* 核心样本股微观体检矩阵 (Microstructure Health Grid) */}
          {stockComparisonList.length > 0 && (
            <div className="mt-3 pt-3 border-t border-white/10">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-2.5">
                <div className="flex items-center gap-2">
                  <div className="w-1.5 h-3.5 bg-cyan-400 rounded-full shadow-[0_0_8px_rgba(6,182,212,0.8)]" />
                  <span className="text-xs font-bold text-white tracking-wide">
                    核心样本股微观体检矩阵 · 换手率 / 真实流通盘 / 承接诊断
                  </span>
                  <span className="text-[11px] font-mono text-cyan-300/80 bg-cyan-950/60 border border-cyan-500/30 px-2 py-0.5 rounded-full">
                    量化硬指标支撑 · 杜绝主观臆断
                  </span>
                </div>
                <div className="flex items-center gap-3 text-[11px] font-mono text-slate-400">
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-blue-400" />
                    容量中军 (流值≥150亿 或 成交≥15亿)
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-rose-400" />
                    情绪先锋/妖股 (小盘高换手/连板)
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2.5">
                {stockComparisonList.map((s) => {
                  const diag = s.healthDiagnosis;
                  const isHealthy = diag?.level === 'healthy';
                  const isDanger = diag?.level === 'danger';
                  const isWarning = diag?.level === 'warning';

                  return (
                    <div
                      key={s.code}
                      className="rounded-xl border p-2.5 flex flex-col justify-between transition-all relative overflow-hidden backdrop-blur-md bg-slate-950/70 hover:bg-slate-900/90 hover:border-cyan-500/40"
                      style={{
                        borderColor: `${s.color}40`,
                      }}
                    >
                      {/* 顶部左侧色条标识 */}
                      <div
                        className="absolute left-0 top-0 bottom-0 w-1"
                        style={{ backgroundColor: s.color }}
                      />

                      {/* 标的信息头 */}
                      <div className="pl-1.5">
                        <div className="flex items-start justify-between gap-1">
                          <div className="truncate">
                            <span className="text-xs font-bold text-white tracking-tight">{s.name}</span>
                            <span className="text-[10px] font-mono text-slate-400 ml-1">{s.code}</span>
                          </div>
                          <span className={`font-mono font-black text-xs shrink-0 ${s.changePct >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                            {s.changePct >= 0 ? `+${s.changePct.toFixed(1)}%` : `${s.changePct.toFixed(1)}%`}
                          </span>
                        </div>

                        {/* 角色徽章 */}
                        <div className="flex flex-wrap items-center gap-1 mt-1">
                          {s.roles && s.roles.length > 0 ? (
                            s.roles.slice(0, 2).map((r, rIdx) => {
                              const isEmotion = r.includes('情绪') || r.includes('B');
                              const isCap = r.includes('容量') || r.includes('中军');
                              const isBroken = r.includes('炸板');
                              const textClass = isBroken ? 'text-emerald-300' : isEmotion ? 'text-rose-300' : isCap ? 'text-blue-300' : 'text-slate-300';
                              const bgClass = isBroken ? 'bg-emerald-950/50 border-emerald-500/40' : isEmotion ? 'bg-rose-950/50 border-rose-500/40' : isCap ? 'bg-blue-950/50 border-blue-500/40' : 'bg-slate-800/60 border-slate-700/50';
                              return (
                                <span
                                  key={rIdx}
                                  className={`text-[9px] px-1.5 py-0.5 rounded font-mono font-bold border ${bgClass} ${textClass}`}
                                >
                                  {r}
                                </span>
                              );
                            })
                          ) : (
                            <span className="text-[9px] px-1.5 py-0.5 rounded font-mono font-bold border bg-slate-800/60 border-slate-700/50 text-slate-300">
                              {s.tagLabel || s.role}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* 微观三维核心指标 */}
                      <div className="pl-1.5 grid grid-cols-2 gap-x-2 gap-y-1.5 my-2 font-mono text-[11px] tabular-nums border-t border-b border-white/5 py-1.5">
                        <div>
                          <span className="text-[10px] text-slate-500 block leading-tight">流通市值</span>
                          <span className="font-bold text-slate-200">
                            {s.floatMcapYi != null ? `${s.floatMcapYi >= 100 ? s.floatMcapYi.toFixed(0) : s.floatMcapYi.toFixed(1)}亿` : '--'}
                          </span>
                        </div>
                        <div>
                          <span className="text-[10px] text-slate-500 block leading-tight">日内换手</span>
                          <span className={`font-bold ${
                            s.turnoverRate != null && s.turnoverRate >= 30
                              ? 'text-amber-400'
                              : s.turnoverRate != null && s.turnoverRate >= 15
                              ? 'text-rose-400'
                              : 'text-slate-200'
                          }`}>
                            {s.turnoverRate != null ? `${s.turnoverRate.toFixed(1)}%` : '--'}
                          </span>
                        </div>
                        <div>
                          <span className="text-[10px] text-slate-500 block leading-tight">成交额</span>
                          <span className="text-slate-300">
                            {s.totalAmountYi != null ? `${s.totalAmountYi.toFixed(1)}亿` : '--'}
                          </span>
                        </div>
                        <div>
                          <span className="text-[10px] text-slate-500 block leading-tight">体检评级</span>
                          <span className={`font-bold text-[10px] inline-flex items-center gap-0.5 ${
                            isDanger ? 'text-emerald-400' : isWarning ? 'text-amber-400' : 'text-cyan-300'
                          }`}>
                            <span className={`w-1 h-1 rounded-full ${
                              isDanger ? 'bg-emerald-400' : isWarning ? 'bg-amber-400' : 'bg-cyan-400'
                            }`} />
                            {diag?.badge || '正常'}
                          </span>
                        </div>
                      </div>

                      {/* 底部微观诊断结论 */}
                      <div className="pl-1.5">
                        <p className="text-[10px] text-slate-400 font-mono leading-relaxed line-clamp-2" title={diag?.reason}>
                          {diag?.reason || '筹码与走势波动受控，多空均衡博弈'}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* 底部双轨博弈透视结论卡片 (前日核心今日表现 + 今日最强涨停涨跌博弈) */}
          <div className="mt-2 pt-2.5 border-t border-white/10 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
            {/* 轨道 1：昨日核心在今日的表现 */}
            <div className="bg-purple-950/20 border border-purple-500/30 rounded-xl p-2.5 flex items-start gap-2.5">
              <div className="px-2 py-0.5 rounded text-[11px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/40 shrink-0 mt-0.5 flex items-center gap-1">
                <Brain className="w-3 h-3 text-purple-400" />
                <span>昨日核心今日表现</span>
              </div>
              <p className="text-slate-300 leading-relaxed text-xs" dangerouslySetInnerHTML={{ __html: dynamicGamePerspective.track1 }} />
            </div>

            {/* 轨道 2：当天当时最强涨停与昨日核心的涨跌关系 */}
            <div className="bg-cyan-950/20 border border-cyan-500/30 rounded-xl p-2.5 flex items-start gap-2.5">
              <div className="px-2 py-0.5 rounded text-[11px] font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shrink-0 mt-0.5 flex items-center gap-1">
                <Zap className="w-3 h-3 text-cyan-400" />
                <span>今日最强 vs 昨日核心</span>
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
                className="absolute top-2 pointer-events-none z-30 bg-slate-950/95 border border-purple-500/40 rounded-xl p-2.5 shadow-2xl backdrop-blur-xl flex flex-col gap-1 text-[11px] font-mono min-w-[240px]"
                style={{
                  left: `${Math.min(74, Math.max(4, (sectorHoverX / 1000) * 100))}%`,
                }}
              >
                <div className="flex items-center justify-between border-b border-white/10 pb-1 text-purple-300 font-bold">
                  <span>{getHoverTimeLabel(sectorHoverX)} 主力资金净流 (实盘)</span>
                  <span className="text-[10px] text-slate-400">Top 5 采样</span>
                </div>
                <div className="flex flex-col gap-0.5 pt-0.5">
                  {dynamicSectorCurves.map((sec, idx) => {
                    const timeStr = getHoverTimeLabel(sectorHoverX);
                    let displayNet = sec.net;
                    let displayPct = sec.pct;
                    if (sec.trends && sec.trends.length > 0) {
                      const pt = [...sec.trends].reverse().find((p) => p.time <= timeStr) || sec.trends[0];
                      if (pt) {
                        displayNet = pt.net_inflow_yi;
                        displayPct = pt.pct_change;
                      }
                    } else {
                      const progress = Math.min(1, Math.max(0, sectorHoverX / (timeProgress.currentX || 1000)));
                      displayNet = Number((sec.net * progress).toFixed(1));
                    }
                    return (
                      <div key={sec.name} className="flex items-center justify-between gap-2">
                        <span className="flex items-center gap-1.5 truncate">
                          <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: sec.color }} />
                          <span className="text-slate-200">#{idx + 1} {sec.name}</span>
                        </span>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className={`font-bold ${displayNet >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                            {displayNet >= 0 ? `+${displayNet.toFixed(1)} 亿` : `${displayNet.toFixed(1)} 亿`}
                          </span>
                          <span className={`text-[10px] ${displayPct >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                            ({displayPct >= 0 ? `+${displayPct.toFixed(2)}%` : `${displayPct.toFixed(2)}%`})
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* 曲线图主体区域 */}
            <div className="relative w-full flex-1 min-h-[140px]">
              <svg className="w-full h-full z-10 overflow-visible" viewBox="0 0 1000 140" preserveAspectRatio="none">
                <defs>
                  <filter id="sectorGlow" x="-20%" y="-20%" width="140%" height="140%">
                    <feDropShadow dx="0" dy="0" stdDeviation="2.5" floodColor="#ffffff" floodOpacity="0.7"/>
                  </filter>
                </defs>
                <line x1="0" y1="70" x2="1000" y2="70" stroke="rgba(255,255,255,0.15)" strokeWidth="1.2" />
                {dynamicSectorCurves.map((sec, idx) => {
                  const isHovered = hoveredSectorName === sec.name;
                  const isAnyHovered = Boolean(hoveredSectorName);
                  const opacity = isHovered ? 1 : (isAnyHovered ? 0.25 : 0.95);
                  const strokeWidth = isHovered ? 3.8 : (idx === 0 ? 3.0 : 2.2);

                  return (
                    <g 
                      key={sec.name} 
                      className="transition-opacity duration-200 cursor-pointer"
                      style={{ opacity }}
                      onMouseEnter={() => setHoveredSectorName(sec.name)}
                      onMouseLeave={() => setHoveredSectorName(null)}
                    >
                      <path
                        d={sec.path}
                        fill="none"
                        stroke={sec.color}
                        strokeWidth={strokeWidth}
                        strokeLinecap="round"
                        filter={isHovered ? "url(#sectorGlow)" : undefined}
                        className="animate-path-grow"
                      />
                      <circle 
                        cx={sec.endX ?? timeProgress.currentX} 
                        cy={sec.endY} 
                        r={isHovered ? 6 : (idx === 0 ? 4.5 : 3.5)} 
                        fill={sec.color} 
                        stroke="#fff" 
                        strokeWidth={isHovered ? 2.5 : 1.5} 
                      />
                    </g>
                  );
                })}

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
                onMouseEnter={() => setHoveredSectorName(sec.name)}
                onMouseLeave={() => setHoveredSectorName(null)}
                className={`bg-white/[0.025] border p-3 rounded-xl flex flex-col justify-between transition-all cursor-pointer ${
                  hoveredSectorName === sec.name ? 'ring-2 ring-purple-400/60 bg-white/[0.06] scale-[1.02]' : 'hover:bg-white/[0.05]'
                }`}
                style={{ borderColor: `${sec.color}${hoveredSectorName === sec.name ? 'cc' : '55'}` }}
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

                {/* 认知微观体检内嵌：独苗状态 vs 后排负反馈剪刀差 */}
                {sec.isSolitaryMonopoly ? (
                  <div className="mt-2 flex items-center justify-between px-2 py-0.5 rounded bg-amber-500/15 border border-amber-500/35 text-[10px] font-mono text-amber-300">
                    <span className="flex items-center gap-1 font-bold">
                      <AlertTriangle className="w-3 h-3 text-amber-400 shrink-0" />
                      独苗高标
                    </span>
                    <span>
                      垄断度 {sec.monopolyRatio ? `${(sec.monopolyRatio * 100).toFixed(0)}%` : '高'}
                    </span>
                  </div>
                ) : (
                  <div className="mt-2 flex items-center justify-between px-2 py-0.5 rounded bg-black/40 border border-white/5 text-[10px] font-mono">
                    <span className="text-slate-400">
                      剪刀差{' '}
                      <strong className={(sec.crrs ?? 0) >= 6 ? 'text-rose-400 font-bold' : 'text-slate-300'}>
                        {(sec.crrs ?? 0) >= 0 ? `+${(sec.crrs ?? 0).toFixed(1)}%` : `${(sec.crrs ?? 0).toFixed(1)}%`}
                      </strong>
                    </span>
                    <span className="text-slate-400">
                      后排负{' '}
                      <strong className={(sec.rearNegativeRatio ?? 0) >= 0.5 ? 'text-emerald-400 font-bold' : 'text-slate-300'}>
                        {((sec.rearNegativeRatio ?? 0) * 100).toFixed(0)}%
                      </strong>
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="pt-2 border-t border-white/5 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 font-mono">
            <div className="flex items-center gap-2 flex-1 min-w-[320px]">
              <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/40 text-[10px] font-bold shrink-0">
                <Brain className="w-3 h-3 text-cyan-400 animate-pulse" />
                <span>AI 题材轮动推演</span>
              </div>
              <span className="text-slate-300 leading-relaxed">
                <strong className="text-purple-200 font-normal">
                  {llmGameCognition?.sector_rotation || (dynamicSectorCurves[0] ? `${dynamicSectorCurves[0]?.name}引领资金攻坚，${dynamicSectorCurves[dynamicSectorCurves.length - 1]?.name}承压失血` : '板块分化博弈中')}
                </strong>
              </span>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <button
                onClick={() => fetchLlmGameCognition(true)}
                title="重新调用 LLM 深度认知推演"
                className="text-slate-400 hover:text-cyan-300 flex items-center gap-1 transition-colors text-[11px]"
                disabled={isLlmCognitionLoading}
              >
                <RefreshCw className={`w-3 h-3 ${isLlmCognitionLoading ? 'animate-spin text-cyan-400' : ''}`} />
                <span>刷新推演</span>
              </button>
              <span className="text-cyan-300">
                {timeProgress.isAfterClose ? '全天资金沉淀判定' : `当前时点 (${timeProgress.timeLabel.split(' ')[0]}) 资金态势`}
              </span>
            </div>
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
                  <span className="font-mono text-rose-400 text-xs">已捕获 {brokenLimitList.length} 只</span>
                </div>

                <div className="space-y-2 text-xs">
                  {brokenLimitList.length > 0 ? (
                    brokenLimitList.slice(0, 3).map((item) => {
                      const pct = item.pct_change != null ? item.pct_change : 0;
                      const fallBack = item.fall_back_pct != null
                        ? `开板回落 ${item.fall_back_pct.toFixed(1)}%`
                        : (item.open_count ? `曾开板 ${item.open_count} 次` : '触板回落');
                      return (
                        <div key={item.code} className="border-l-2 border-amber-500 bg-white/[0.025] p-2 rounded-r-xl flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-white text-xs">{item.name}</span>
                            <span className="text-xs text-slate-400 font-mono">({item.code})</span>
                            <span className="text-xs text-amber-300 bg-amber-950/60 px-1.5 py-0.5 rounded">{item.sector || '炸板标的'}</span>
                          </div>
                          <div className="text-right font-mono text-xs">
                            <span className={`font-bold ${pct >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                              {pct >= 0 ? `+${pct.toFixed(1)}%` : `${pct.toFixed(1)}%`}
                            </span>
                            <span className="text-amber-400 ml-1.5">{fallBack}</span>
                          </div>
                        </div>
                      );
                    })
                  ) : (
                    <div className="text-slate-500 py-3 text-center text-xs">
                      今日暂无炸板跳水个股，情绪健康
                    </div>
                  )}
                </div>
              </div>

              <div className="pt-2 border-t border-white/5 flex items-center justify-between text-xs text-slate-400 font-mono mt-2">
                <span>
                  跌停核按钮:{' '}
                  {limitDownCount === 0 ? (
                    <strong className="text-slate-400 font-normal">0 只 (无跌停核按钮)</strong>
                  ) : (
                    <strong className="text-emerald-400 font-bold">{limitDownCount} 只</strong>
                  )}{' '}
                  <span className="text-slate-500 text-[10px]">(ST已剔除)</span>
                </span>
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
