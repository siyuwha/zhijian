'use client';

import { useEffect, useState, useRef, useMemo } from 'react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api } from '@/lib/api';
import { 
  MonitorRealtimeResponse, 
  MacroSnapshotItem, 
  IntradayAnomalyEventItem,
  TradingSessionState,
  AnomalyCategory,
  AnomalySeverity,
  WatchlistItem
} from '@/types/monitor';
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowDownRight,
  ArrowUp,
  ArrowUpDown,
  ArrowUpRight,
  BarChart3,
  Bell,
  BellOff,
  CheckCircle2,
  Clock,
  ExternalLink,
  Flame,
  Layers,
  Lock,
  Pause,
  Play,
  Radio,
  RefreshCw,
  ShieldAlert,
  TrendingDown,
  TrendingUp,
  Unlock,
  Zap
} from 'lucide-react';

export default function MonitorPage() {
  const [realtime, setRealtime] = useState<MonitorRealtimeResponse | null>(null);
  const [series, setSeries] = useState<MacroSnapshotItem[]>([]);
  const [events, setEvents] = useState<IntradayAnomalyEventItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [severityFilter, setSeverityFilter] = useState<string | null>(null);
  const [triggeringScan, setTriggeringScan] = useState<boolean>(false);
  const [hoveredPoint, setHoveredPoint] = useState<MacroSnapshotItem | null>(null);

  // 重点监控池三态排序状态 (P1-E: 默认 -> 降序 -> 升序 -> 默认，纯前端内存排序，0网络开销)
  type WatchlistSortField = 'open_pct' | 'current_pct' | 'amount_yi' | null;
  type WatchlistSortOrder = 'asc' | 'desc' | null;
  const [sortField, setSortField] = useState<WatchlistSortField>(null);
  const [sortOrder, setSortOrder] = useState<WatchlistSortOrder>(null);

  const handleWatchlistSort = (field: 'open_pct' | 'current_pct' | 'amount_yi') => {
    if (sortField !== field) {
      setSortField(field);
      setSortOrder('desc'); // 第一击：降序
    } else if (sortOrder === 'desc') {
      setSortOrder('asc');  // 第二击：升序
    } else {
      setSortField(null);   // 第三击：重置默认
      setSortOrder(null);
    }
  };

  const sortedWatchlist = useMemo(() => {
    const list = realtime?.watchlist ? [...realtime.watchlist] : [];
    if (!sortField || !sortOrder) return list;

    return list.sort((a, b) => {
      const valA = a[sortField] ?? -999999;
      const valB = b[sortField] ?? -999999;
      return sortOrder === 'desc' ? valB - valA : valA - valB;
    });
  }, [realtime?.watchlist, sortField, sortOrder]);

  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // 加载全量数据
  const loadData = async (isManual = false) => {
    try {
      if (isManual) setRefreshing(true);
      setError(null);

      const [rtRes, seriesRes, eventsRes] = await Promise.all([
        api.getMonitorRealtime(),
        api.getMonitorSeries(),
        api.getMonitorEvents(undefined, severityFilter || undefined, 60)
      ]);

      setRealtime(rtRes);
      setSeries(seriesRes || []);
      setEvents(eventsRes || []);
    } catch (err: any) {
      console.error('获取盘中监控数据失败:', err);
      setError(err.message || '获取盘中监控数据失败');
    } finally {
      setLoading(false);
      if (isManual) setRefreshing(false);
    }
  };

  // 初始加载与轮询机制
  useEffect(() => {
    loadData();

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [severityFilter]);

  // 动态自动刷新间隔 (ACTIVE: 5秒; 其他状态: 15秒)
  useEffect(() => {
    if (timerRef.current) clearInterval(timerRef.current);

    if (autoRefresh) {
      const intervalMs = realtime?.session_state === 'ACTIVE' ? 5000 : 15000;
      timerRef.current = setInterval(() => {
        loadData(false);
      }, intervalMs);
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [autoRefresh, realtime?.session_state, severityFilter]);

  // 手动触发快照与异动扫描
  const handleTriggerScan = async () => {
    try {
      setTriggeringScan(true);
      await api.triggerMonitorScan();
      await loadData(true);
    } catch (err: any) {
      console.error('触发盘中扫描失败:', err);
      alert('触发盘中扫描失败: ' + err.message);
    } finally {
      setTriggeringScan(false);
    }
  };

  // 盘中状态标签与样式
  const getSessionBadge = (state?: TradingSessionState) => {
    switch (state) {
      case 'ACTIVE':
        return {
          text: '连续竞价中',
          sub: '实时时序采集',
          className: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30 animate-pulse',
          dot: 'bg-emerald-400'
        };
      case 'PRE_MARKET':
        return {
          text: '盘前准备',
          sub: '等待 09:30 开盘',
          className: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30',
          dot: 'bg-cyan-400'
        };
      case 'NOON_BREAK':
        return {
          text: '午间休市',
          sub: '时序冻结中',
          className: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
          dot: 'bg-amber-400'
        };
      case 'CLOSED':
        return {
          text: '已闭市',
          sub: '盘后静止观测',
          className: 'bg-slate-700/40 text-slate-400 border-slate-600/40',
          dot: 'bg-slate-400'
        };
      default:
        return {
          text: '准备就绪',
          sub: '--',
          className: 'bg-slate-800 text-slate-400 border-slate-700',
          dot: 'bg-slate-400'
        };
    }
  };

  // 事件类别字典 (严格对齐技术设计单 v1.1 规范枚举)
  const getEventCategoryMeta = (cat: AnomalyCategory) => {
    switch (cat) {
      case 'LIMIT_UP_LOCK':
        return { label: '涨停封板', badge: 'bg-rose-500/20 text-rose-400 border-rose-500/40', icon: Lock };
      case 'LIMIT_UP_BREAK':
        return { label: '突发炸板', badge: 'bg-amber-500/20 text-amber-400 border-amber-500/40', icon: Unlock };
      case 'LIMIT_DOWN':
        return { label: '触及跌停', badge: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40', icon: AlertTriangle };
      case 'VOLUME_SURGE':
        return { label: '量能脉冲', badge: 'bg-blue-500/20 text-blue-400 border-blue-500/40', icon: Zap };
      case 'VELOCITY_SPIKE':
        return { label: '动量突变', badge: 'bg-purple-500/20 text-purple-400 border-purple-500/40', icon: TrendingUp };
      case 'RESONANCE':
        return { label: '系统共振', badge: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/40', icon: Radio };
      default:
        return { label: cat, badge: 'bg-slate-700 text-slate-300 border-slate-600', icon: Activity };
    }
  };

  const getSeverityBadge = (level: AnomalySeverity) => {
    switch (level) {
      case 'CRITICAL':
        return 'bg-rose-500/20 text-rose-400 border-rose-500/30';
      case 'TRANSITION':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
      case 'INFO':
        return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
      default:
        return 'bg-slate-800 text-slate-400 border-slate-700';
    }
  };

  // 分时图绘制计算 (SVG Polyline)
  const chartPoints = useMemo(() => {
    if (!series || series.length === 0) return { pctPoints: '', minPct: -2, maxPct: 2, points: [] };

    const validItems = series.filter(s => s.sh_pct !== null);
    if (validItems.length === 0) return { pctPoints: '', minPct: -2, maxPct: 2, points: [] };

    let min = -1.5;
    let max = 1.5;
    validItems.forEach(s => {
      const p = s.sh_pct!;
      if (p < min) min = p;
      if (p > max) max = p;
    });

    const bound = Math.max(Math.abs(min), Math.abs(max)) * 1.15;
    const finalMin = -bound;
    const finalMax = bound;

    // SVG 坐标系: viewBox 0 0 600 160
    const w = 600;
    const h = 160;
    const padding = 15;

    const mapped = validItems.map(item => {
      // 0~240 分钟映射到 x: 0 ~ w
      const x = (item.minute_index / 240) * (w - padding * 2) + padding;
      // y 轴翻转，中间为 0 轴
      const normY = (item.sh_pct! - finalMin) / (finalMax - finalMin);
      const y = h - (normY * (h - padding * 2) + padding);
      return { x, y, item };
    });

    const polyline = mapped.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    return { pctPoints: polyline, minPct: finalMin, maxPct: finalMax, points: mapped };
  }, [series]);

  const macro = realtime?.macro;
  const sessionInfo = getSessionBadge(realtime?.session_state);

  const shPrice = typeof macro?.sh_price === 'number' ? macro.sh_price.toFixed(2) : '--';
  const shPct = typeof macro?.sh_pct === 'number' ? macro.sh_pct : null;
  const minuteIndex = typeof macro?.minute_index === 'number' ? macro.minute_index : null;
  const totalAmountYi = typeof macro?.total_amount_yi === 'number' ? `${macro.total_amount_yi.toFixed(0)} 亿元` : '--';
  const volumeProjYi = typeof macro?.volume_proj_yi === 'number' ? `${macro.volume_proj_yi.toFixed(0)} 亿元` : null;
  const upCount = typeof macro?.up_count === 'number' ? macro.up_count : null;
  const downCount = typeof macro?.down_count === 'number' ? macro.down_count : null;
  const limitUpCount = typeof macro?.limit_up_count === 'number' ? macro.limit_up_count : null;
  const limitDownCount = typeof macro?.limit_down_count === 'number' ? macro.limit_down_count : null;
  const brokenCount = typeof macro?.broken_count === 'number' ? macro.broken_count : null;
  const maxHeight = typeof macro?.max_height === 'number' ? `${macro.max_height} 板` : '--';
  const leaderStock = macro?.leader_stock || '--';

  const netUpStr = (upCount !== null && downCount !== null)
    ? `${upCount - downCount > 0 ? '+' : ''}${upCount - downCount}`
    : '--';

  const totalBreadth = (upCount ?? 0) + (downCount ?? 0);
  const upRatioPct = totalBreadth > 0 ? ((upCount ?? 0) / totalBreadth) * 100 : 50;
  const downRatioPct = 100 - upRatioPct;

  return (
    <div className="space-y-6 pb-12">
      {/* 1. 顶部控制栏与态势抬头 */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-900/60 p-5 rounded-xl border border-white/10 backdrop-blur-sm shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-slate-100 flex items-center gap-2">
              <Activity className="h-6 w-6 text-purple-400" />
              盘中动态监控与异动感知 (M4)
            </h1>
            <div className={`px-2.5 py-1 rounded-full text-sm font-medium border flex items-center gap-1.5 ${sessionInfo.className}`}>
              <span className={`w-2 h-2 rounded-full ${sessionInfo.dot}`} />
              {sessionInfo.text}
            </div>
          </div>
          <p className="text-base text-slate-400">
            热内存环形时序感知引擎 · 连续分钟度量 · 边沿跃迁检测 · 绝无交易信号
          </p>
        </div>

        {/* 交互控制组 */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800/80 rounded-lg border border-slate-700/60 text-sm text-slate-300">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>时钟: <span className="font-mono text-cyan-400 font-semibold">{realtime?.timestamp || '--:--:--'}</span></span>
            <span className="text-slate-500">|</span>
            <span className="text-slate-400">延迟: {realtime?.freshness_seconds ?? 3}s</span>
          </div>

          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`px-3 py-1.5 rounded-lg border text-sm font-medium flex items-center gap-1.5 transition-all ${
              autoRefresh 
                ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 hover:bg-cyan-500/30' 
                : 'bg-slate-800 text-slate-400 border-slate-700 hover:bg-slate-700'
            }`}
            title={autoRefresh ? '点击暂停自动轮询' : '点击开启自动轮询'}
          >
            {autoRefresh ? <Play className="w-3.5 h-3.5 text-cyan-400 fill-cyan-400" /> : <Pause className="w-3.5 h-3.5 text-slate-400" />}
            {autoRefresh ? '自动轮询中' : '已暂停'}
          </button>

          <button
            onClick={() => setIsMuted(!isMuted)}
            className={`p-2 rounded-lg border text-sm font-medium transition-all ${
              isMuted 
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40' 
                : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
            }`}
            title={isMuted ? '提示静音开启' : '声音提醒开启'}
          >
            {isMuted ? <BellOff className="w-4 h-4 text-amber-400" /> : <Bell className="w-4 h-4 text-slate-400" />}
          </button>

          <button
            onClick={handleTriggerScan}
            disabled={triggeringScan}
            className="px-3.5 py-1.5 bg-indigo-600/30 text-indigo-200 border border-indigo-500/50 hover:bg-indigo-600/50 rounded-lg text-sm font-medium flex items-center gap-1.5 transition-all disabled:opacity-50"
            title="手动触发全市场盘中异动与时序扫描"
          >
            <Zap className={`w-3.5 h-3.5 text-indigo-400 ${triggeringScan ? 'animate-spin' : ''}`} />
            {triggeringScan ? '正在扫描...' : '采集快照'}
          </button>

          <button
            onClick={() => loadData(true)}
            disabled={refreshing}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg text-sm font-medium flex items-center gap-1.5 transition-all disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-slate-400 ${refreshing ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800/80 rounded-xl text-rose-300 text-base flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-rose-400 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 2. 核心宏观 4 大指标切片卡片 (严格执行 None 零填充防伪) */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 卡片 1: 上证指数分时 */}
        <Card className="bg-slate-900/60 border-white/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-slate-400 flex items-center justify-between">
              <span>上证指数实时分时</span>
              <span className="text-xs font-mono text-slate-500">
                Minute #{minuteIndex ?? '--'} / 240
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-baseline justify-between">
              <span className="text-3xl font-bold font-mono text-slate-100">
                {shPrice}
              </span>
              <span className={`text-lg font-bold font-mono flex items-center ${
                shPct !== null && shPct >= 0 ? 'text-rose-400' : 'text-emerald-400'
              }`}>
                {shPct !== null ? (
                  <>
                    {shPct >= 0 ? <TrendingUp className="w-4 h-4 mr-0.5 inline" /> : <TrendingDown className="w-4 h-4 mr-0.5 inline" />}
                    {shPct >= 0 ? '+' : ''}{shPct.toFixed(2)}%
                  </>
                ) : '--'}
              </span>
            </div>
            {/* 日内时钟进度条 */}
            <div className="mt-3 w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
              <div 
                className="bg-cyan-500 h-1.5 rounded-full transition-all duration-500" 
                style={{ width: `${Math.min(100, Math.max(0, ((minuteIndex ?? 0) / 240) * 100))}%` }}
              />
            </div>
          </CardContent>
        </Card>

        {/* 卡片 2: 成交量能与 W(T) 全天投影 */}
        <Card className="bg-slate-900/60 border-white/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-slate-400 flex items-center justify-between">
              <span>两市成交额与全天投影</span>
              {(macro?.is_proj_estimated || macro?.volume_proj_status === 'ESTIMATED') && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">
                  ESTIMATED 估算
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-1.5">
              <div className="flex items-baseline justify-between">
                <span className="text-sm text-slate-400">当前成交额:</span>
                <span className="text-xl font-bold font-mono text-cyan-300">
                  {totalAmountYi}
                </span>
              </div>
              <div className="flex items-baseline justify-between border-t border-slate-800/80 pt-1.5">
                <span className="text-sm text-slate-400">W(T) 全天投影:</span>
                <span className="text-base font-semibold font-mono text-amber-300">
                  {volumeProjYi !== null ? volumeProjYi : <span className="text-xs text-slate-500 font-normal">-- (09:45后测算)</span>}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 卡片 3: 市场全景涨跌分布 */}
        <Card className="bg-slate-900/60 border-white/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-slate-400 flex items-center justify-between">
              <span>全市场普适涨跌分布</span>
              <span className="text-xs text-slate-500">
                净涨: {netUpStr}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between mb-2">
              <div className="text-left">
                <div className="text-sm text-slate-400">上涨家数</div>
                <div className="text-xl font-bold font-mono text-rose-400">
                  {upCount !== null ? upCount : '--'}
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm text-slate-400">下跌家数</div>
                <div className="text-xl font-bold font-mono text-emerald-400">
                  {downCount !== null ? downCount : '--'}
                </div>
              </div>
            </div>
            {/* 涨跌比例条 */}
            <div className="w-full bg-slate-800 rounded-full h-1.5 flex overflow-hidden">
              <div 
                className="bg-rose-500 h-1.5 transition-all duration-500" 
                style={{ width: `${upRatioPct}%` }}
              />
              <div 
                className="bg-emerald-500 h-1.5 transition-all duration-500" 
                style={{ width: `${downRatioPct}%` }}
              />
            </div>
          </CardContent>
        </Card>

        {/* 卡片 4: 极端生态与高度空间 */}
        <Card className="bg-slate-900/60 border-white/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-medium text-slate-400 flex items-center justify-between">
              <span>短线极端生态与最高高度</span>
              <span className="text-xs text-slate-500">炸板: {brokenCount ?? '--'}</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-slate-400">涨停 / 跌停</div>
                <div className="text-xl font-bold font-mono">
                  <span className="text-rose-400">{limitUpCount ?? '--'}</span>
                  <span className="text-slate-600 mx-1">/</span>
                  <span className="text-emerald-400">{limitDownCount ?? '--'}</span>
                </div>
              </div>
              <div className="text-right">
                <div className="text-sm text-slate-400">最高空间</div>
                <div className="text-xl font-bold font-mono text-amber-400">
                  {maxHeight}
                </div>
              </div>
            </div>
            <div className="mt-2 text-xs text-slate-400 truncate">
              空间龙头: <span className="font-semibold text-slate-200">{leaderStock}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 3. 中间走势与重点池 / 异动事件栅格 */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* 左侧 (7 列): 分时宏观走势图 + 核心监控池 */}
        <div className="lg:col-span-7 space-y-6">
          {/* 分时指数走势图 */}
          <Card className="bg-slate-900/60 border-white/10">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-cyan-400" />
                  上证日内分时时序曲线
                </CardTitle>
                <div className="text-sm text-slate-400">
                  {hoveredPoint ? (
                    <span className="font-mono text-cyan-300">
                      #{hoveredPoint.minute_index}m ({hoveredPoint.timestamp}): {hoveredPoint.sh_pct !== null ? `${hoveredPoint.sh_pct >= 0 ? '+' : ''}${hoveredPoint.sh_pct.toFixed(2)}%` : '--'} | 成交: {hoveredPoint.total_amount_yi ?? '--'}亿
                    </span>
                  ) : (
                    <span>采样点: {series.length} 个</span>
                  )}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="w-full h-44 bg-slate-950/60 rounded-lg p-2 border border-white/10 relative flex flex-col justify-between">
                {/* SVG 分时曲线 */}
                <svg viewBox="0 0 600 160" className="w-full h-full overflow-visible">
                  {/* 网格参考线 */}
                  <line x1="15" y1="80" x2="585" y2="80" stroke="#334155" strokeDasharray="3 3" strokeWidth="1" />
                  <line x1="15" y1="20" x2="585" y2="20" stroke="#1e293b" strokeWidth="1" />
                  <line x1="15" y1="140" x2="585" y2="140" stroke="#1e293b" strokeWidth="1" />
                  {/* 午休垂直分割线 */}
                  <line x1="300" y1="15" x2="300" y2="145" stroke="#334155" strokeWidth="1" />

                  {/* 折线图 */}
                  {chartPoints.pctPoints && (
                    <polyline
                      fill="none"
                      stroke="#06b6d4"
                      strokeWidth="2"
                      points={chartPoints.pctPoints}
                    />
                  )}

                  {/* 数据圆点 */}
                  {chartPoints.points.map((p, idx) => (
                    <circle
                      key={idx}
                      cx={p.x}
                      cy={p.y}
                      r={hoveredPoint?.minute_index === p.item.minute_index ? 4.5 : 2}
                      className="cursor-pointer transition-all fill-cyan-400 hover:fill-amber-400"
                      onMouseEnter={() => setHoveredPoint(p.item)}
                      onMouseLeave={() => setHoveredPoint(null)}
                    />
                  ))}
                </svg>

                {/* X 轴时间标签 */}
                <div className="flex justify-between text-xs text-slate-500 font-mono pt-1 border-t border-slate-800/60">
                  <span>09:30</span>
                  <span>10:30</span>
                  <span>11:30 / 13:00</span>
                  <span>14:00</span>
                  <span>15:00</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 重点监控池雷达 (领涨行业龙头与千亿中军) */}
          <Card className="bg-slate-900/60 border-white/10">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <Flame className="w-4 h-4 text-amber-400" />
                  重点监控池盘中追踪 (领涨龙头 & 千亿中军)
                </CardTitle>
                <span className="text-sm text-slate-500">
                  共计 {realtime?.watchlist?.length ?? 0} 只核心标的 (已排除ST/退市)
                </span>
              </div>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead className="bg-slate-800/50 text-slate-400 border-b border-white/10">
                    <tr>
                      <th className="py-2.5 px-3">代码 / 名称</th>
                      <th className="py-2.5 px-2">盘中状态</th>
                      <th 
                        className="py-2.5 px-2 text-right cursor-pointer select-none hover:text-cyan-300 transition-colors"
                        onClick={() => handleWatchlistSort('open_pct')}
                        title="点击按竞价开盘排序 (默认/降序/升序)"
                      >
                        <div className="inline-flex items-center gap-1 justify-end">
                          <span>竞价开盘</span>
                          {sortField === 'open_pct' ? (
                            sortOrder === 'desc' ? (
                              <ArrowDown className="w-3 h-3 text-cyan-400" />
                            ) : (
                              <ArrowUp className="w-3 h-3 text-cyan-400" />
                            )
                          ) : (
                            <ArrowUpDown className="w-3 h-3 text-slate-600 opacity-60" />
                          )}
                        </div>
                      </th>
                      <th 
                        className="py-2.5 px-2 text-right cursor-pointer select-none hover:text-cyan-300 transition-colors"
                        onClick={() => handleWatchlistSort('current_pct')}
                        title="点击按当前涨幅排序 (默认/降序/升序)"
                      >
                        <div className="inline-flex items-center gap-1 justify-end">
                          <span>当前涨幅</span>
                          {sortField === 'current_pct' ? (
                            sortOrder === 'desc' ? (
                              <ArrowDown className="w-3 h-3 text-cyan-400" />
                            ) : (
                              <ArrowUp className="w-3 h-3 text-cyan-400" />
                            )
                          ) : (
                            <ArrowUpDown className="w-3 h-3 text-slate-600 opacity-60" />
                          )}
                        </div>
                      </th>
                      <th 
                        className="py-2.5 px-3 text-right cursor-pointer select-none hover:text-cyan-300 transition-colors"
                        onClick={() => handleWatchlistSort('amount_yi')}
                        title="点击按成交额排序 (默认/降序/升序)"
                      >
                        <div className="inline-flex items-center gap-1 justify-end">
                          <span>成交额</span>
                          {sortField === 'amount_yi' ? (
                            sortOrder === 'desc' ? (
                              <ArrowDown className="w-3 h-3 text-cyan-400" />
                            ) : (
                              <ArrowUp className="w-3 h-3 text-cyan-400" />
                            )
                          ) : (
                            <ArrowUpDown className="w-3 h-3 text-slate-600 opacity-60" />
                          )}
                        </div>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono">
                    {sortedWatchlist && sortedWatchlist.length > 0 ? (
                      sortedWatchlist.map((item, idx) => (
                        <tr key={idx} className="hover:bg-slate-800/40 transition-colors">
                          <td className="py-2 px-3 font-medium text-slate-200">
                            <div>{item.name}</div>
                            <div className="text-xs text-slate-500">{item.symbol}</div>
                          </td>
                          <td className="py-2 px-2">
                            {item.status === 'SEALED' ? (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-rose-500/20 text-rose-300 border border-rose-500/30">
                                <Lock className="w-2.5 h-2.5" /> 封板
                              </span>
                            ) : item.status === 'BROKEN' ? (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-amber-500/20 text-amber-300 border border-amber-500/30">
                                <Unlock className="w-2.5 h-2.5" /> 炸板
                              </span>
                            ) : item.status === 'HALTED' ? (
                              <span className="px-1.5 py-0.5 rounded text-xs bg-slate-700 text-slate-400">
                                停牌
                              </span>
                            ) : (
                              <span className="px-1.5 py-0.5 rounded text-xs bg-slate-800 text-slate-300">
                                正常
                              </span>
                            )}
                          </td>
                          <td className="py-2 px-2 text-right font-mono">
                            {item.open_pct !== null && item.open_pct !== undefined ? (
                              <span className={item.open_pct >= 0 ? 'text-rose-400' : 'text-emerald-400'}>
                                {item.open_pct >= 0 ? '+' : ''}{item.open_pct.toFixed(2)}%
                              </span>
                            ) : '--'}
                          </td>
                          <td className="py-2 px-2 text-right font-mono font-bold">
                            {item.current_pct !== null && item.current_pct !== undefined ? (
                              <span className={item.current_pct >= 0 ? 'text-rose-400' : 'text-emerald-400'}>
                                {item.current_pct >= 0 ? '+' : ''}{item.current_pct.toFixed(2)}%
                              </span>
                            ) : '--'}
                          </td>
                          <td className="py-2 px-3 text-right text-slate-300">
                            {item.amount_yi !== null && item.amount_yi !== undefined ? `${item.amount_yi.toFixed(1)} 亿` : '--'}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={5} className="py-8 text-center text-slate-500">
                          暂无重点池数据 (盘前或网络采集中)
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* 右侧 (5 列): 客观异动与相变事件流 (Edge Trigger 边沿跃迁流水) */}
        <div className="lg:col-span-5 space-y-4">
          <Card className="bg-slate-900/60 border-white/10 h-full flex flex-col">
            <CardHeader className="pb-3 border-b border-white/10">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                  <Radio className="w-4 h-4 text-purple-400 animate-pulse" />
                  盘中客观异动与相变流水
                </CardTitle>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => setSeverityFilter(null)}
                    className={`px-2 py-0.5 rounded text-xs font-medium transition-all ${
                      severityFilter === null 
                        ? 'bg-slate-700 text-white' 
                        : 'bg-slate-800/80 text-slate-400 hover:bg-slate-700'
                    }`}
                  >
                    全部
                  </button>
                  <button
                    onClick={() => setSeverityFilter('CRITICAL')}
                    className={`px-2 py-0.5 rounded text-xs font-medium transition-all ${
                      severityFilter === 'CRITICAL' 
                        ? 'bg-rose-950 text-rose-300 border border-rose-800' 
                        : 'bg-slate-800/80 text-slate-400 hover:bg-slate-700'
                    }`}
                  >
                    CRITICAL
                  </button>
                  <button
                    onClick={() => setSeverityFilter('TRANSITION')}
                    className={`px-2 py-0.5 rounded text-xs font-medium transition-all ${
                      severityFilter === 'TRANSITION' 
                        ? 'bg-amber-950 text-amber-300 border border-amber-800' 
                        : 'bg-slate-800/80 text-slate-400 hover:bg-slate-700'
                    }`}
                  >
                    TRANSITION
                  </button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="pt-4 flex-1 overflow-y-auto max-h-[640px] space-y-3">
              {events && events.length > 0 ? (
                events.map((ev, idx) => {
                  const catMeta = getEventCategoryMeta(ev.event_category);
                  const Icon = catMeta.icon;
                  return (
                    <div 
                      key={idx} 
                      className="p-3 bg-slate-950/70 rounded-lg border border-slate-800/80 hover:border-slate-700 transition-all text-sm space-y-1.5"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className={`px-2 py-0.5 rounded text-xs font-medium border flex items-center gap-1 ${catMeta.badge}`}>
                            <Icon className="w-3 h-3" />
                            {catMeta.label}
                          </span>
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono border ${getSeverityBadge(ev.severity_level)}`}>
                            {ev.severity_level}
                          </span>
                        </div>
                        <span className="font-mono text-slate-500 text-xs">
                          {ev.timestamp} (#{ev.minute_index}m)
                        </span>
                      </div>

                      <div className="flex items-baseline justify-between pt-1">
                        <div className="font-semibold text-slate-200">
                          {ev.name || '--'} <span className="text-slate-500 font-mono font-normal">({ev.symbol || '--'})</span>
                        </div>
                        <div className="font-mono font-bold">
                          {ev.pct_change !== null && ev.pct_change !== undefined ? (
                            <span className={ev.pct_change >= 0 ? 'text-rose-400' : 'text-emerald-400'}>
                              {ev.pct_change >= 0 ? '+' : ''}{ev.pct_change.toFixed(2)}%
                            </span>
                          ) : '--'}
                        </div>
                      </div>

                      {/* 量化指标遥测四元组 */}
                      {(ev.window_delta_pct !== null || ev.window_amount_wan !== null || ev.surge_ratio !== null) && (
                        <div className="flex flex-wrap items-center gap-2 pt-1 font-mono text-xs text-slate-400 bg-slate-900/60 p-1.5 rounded">
                          {ev.window_delta_pct !== null && (
                            <span>ΔP(5m): <strong className={ev.window_delta_pct >= 0 ? 'text-rose-400' : 'text-emerald-400'}>{ev.window_delta_pct >= 0 ? '+' : ''}{ev.window_delta_pct.toFixed(2)}%</strong></span>
                          )}
                          {ev.window_amount_wan !== null && (
                            <span>V(5m): <strong className="text-cyan-300">{ev.window_amount_wan.toFixed(0)}万</strong></span>
                          )}
                          {ev.surge_ratio !== null && (
                            <span>R_vol: <strong className="text-amber-300">{ev.surge_ratio.toFixed(1)}x</strong></span>
                          )}
                        </div>
                      )}

                      {/* 结构化客观明细 */}
                      {ev.details && (
                        <div className="text-xs text-slate-400 font-sans pt-0.5 leading-relaxed">
                          {typeof ev.details === 'string' ? ev.details : JSON.stringify(ev.details)}
                        </div>
                      )}
                    </div>
                  );
                })
              ) : (
                <div className="py-16 text-center text-slate-500 space-y-2">
                  <ShieldAlert className="w-8 h-8 mx-auto text-slate-600" />
                  <p>当前暂未感知到达到阈值的边沿相变异动</p>
                  <p className="text-xs text-slate-600">系统持续以 15 分钟降噪过滤并防刷屏</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* 4. 底部客观物理事实测量提示与免责隔离横幅 (7+1 铁律必修项) */}
      <div className="p-4 rounded-xl bg-slate-950/80 border border-white/10 text-sm text-slate-400 flex items-start gap-3 shadow-lg">
        <ShieldAlert className="w-5 h-5 text-purple-400 shrink-0 mt-0.5" />
        <div className="space-y-1">
          <div className="font-semibold text-slate-300 flex items-center gap-2">
            客观物理事实测量提示与边界隔离
            <span className="text-xs px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 border border-purple-500/30">
              纯客观度量
            </span>
          </div>
          <p className="leading-relaxed">
            {realtime?.disclaimer || "【客观物理事实测量提示】本看板仅对盘中市场量价与流动性数据进行客观时间序列观测与统计记录，非买卖建议，不构成任何投资建议或交易执行指令。市场有风险，决策须自主。"}
          </p>
        </div>
      </div>
    </div>
  );
}
