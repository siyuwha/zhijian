'use client';

import { useEffect, useState, useMemo } from 'react';
import { api } from '@/lib/api';
import { Position, TradeRecord, TradeStats, TradeRecordCreatePayload, ReversalTradeCreatePayload, TradeNoteCreatePayload } from '@/types/trading';
import { Card, CardContent } from '@/components/ui/card';
import { 
  TrendingUp, 
  TrendingDown, 
  PlusCircle, 
  RefreshCw, 
  RotateCcw, 
  BookOpen, 
  AlertCircle, 
  CheckCircle2, 
  ShieldAlert, 
  ArrowUpDown,
  History,
  FileText,
  Clock,
  Layers,
  Search,
  Filter,
  X
} from 'lucide-react';

export default function TradingPage() {
  // 核心状态
  const [positions, setPositions] = useState<Position[]>([]);
  const [records, setRecords] = useState<TradeRecord[]>([]);
  const [stats, setStats] = useState<TradeStats | null>(null);
  const [totalRecords, setTotalRecords] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [reconciling, setReconciling] = useState(false);
  const [activeTab, setActiveTab] = useState<'positions' | 'ledger'>('positions');
  const [filterDirection, setFilterDirection] = useState<string>('all');
  const [searchCode, setSearchCode] = useState('');

  // 弹窗状态
  const [isTradeModalOpen, setIsTradeModalOpen] = useState(false);
  const [isReversalModalOpen, setIsReversalModalOpen] = useState(false);
  const [isNoteDrawerOpen, setIsNoteDrawerOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 表单状态
  const [tradeForm, setTradeForm] = useState<TradeRecordCreatePayload>({
    code: '',
    name: '',
    direction: 'buy',
    price: 0,
    quantity: 100,
    trade_time: '',
    trade_reason: '',
  });
  const [reversalTarget, setReversalTarget] = useState<TradeRecord | null>(null);
  const [reversalReason, setReversalReason] = useState('');
  const [selectedRecordForNote, setSelectedRecordForNote] = useState<TradeRecord | null>(null);
  const [noteForm, setNoteForm] = useState({
    mental_state: '',
    decision_logic: '',
    reflection: '',
    lessons: '',
    append_mode: true,
  });
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // 加载全量数据
  const loadData = async (refreshQuote: boolean = true) => {
    try {
      if (refreshQuote) setRefreshing(true);
      const [posRes, statsRes, recRes] = await Promise.all([
        api.getPositions(refreshQuote).catch(() => []),
        api.getTradeStats().catch(() => null),
        api.getTradeRecords({
          code: searchCode.trim() || undefined,
          direction: filterDirection !== 'all' && filterDirection !== 'reversal' ? filterDirection : undefined,
          record_type: filterDirection === 'reversal' ? 'REVERSAL' : undefined,
          page: currentPage,
          limit: 20
        }).catch(() => ({ items: [], total: 0, page: 1, limit: 20 }))
      ]);

      setPositions(posRes || []);
      setStats(statsRes);
      setRecords(recRes.items || []);
      setTotalRecords(recRes.total || 0);
    } catch (err: any) {
      console.error('加载交易数据失败:', err);
      setActionError(err?.message || '加载交易数据失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData(true);
  }, [currentPage, filterDirection, searchCode]);

  // 打开新建交易弹窗
  const handleOpenTradeModal = (defaultDirection: 'buy' | 'sell' = 'buy', prefillPosition?: Position) => {
    const nowStr = new Date().toISOString().replace('T', ' ').substring(0, 19);
    setTradeForm({
      code: prefillPosition?.code || '',
      name: prefillPosition?.name || '',
      direction: defaultDirection,
      price: prefillPosition?.current_price || prefillPosition?.avg_cost || 0,
      quantity: defaultDirection === 'sell' && prefillPosition ? prefillPosition.quantity : 100,
      trade_time: nowStr,
      trade_reason: '',
    });
    setActionError(null);
    setIsTradeModalOpen(true);
  };

  // 提交交易记录
  const handleSubmitTrade = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;
    setActionError(null);
    setIsSubmitting(true);
    try {
      if (!tradeForm.code || !/^\d{6}$/.test(tradeForm.code)) {
        throw new Error('股票代码必须为6位纯数字');
      }
      if (tradeForm.price <= 0) {
        throw new Error('成交单价必须大于0');
      }
      if (tradeForm.quantity <= 0) {
        throw new Error('成交股数必须为正整数');
      }

      await api.addTradeRecord({
        ...tradeForm,
        idempotency_key: `trade_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`
      });

      setActionSuccess('交易记录录入成功！');
      setIsTradeModalOpen(false);
      await loadData(true);
      setTimeout(() => setActionSuccess(null), 3000);
    } catch (err: any) {
      setActionError(err?.message || '录入交易失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  // 打开冲正弹窗
  const handleOpenReversalModal = (record: TradeRecord) => {
    setReversalTarget(record);
    setReversalReason('录入笔误，发起会计红字冲正对冲');
    setActionError(null);
    setIsReversalModalOpen(true);
  };

  // 提交冲正
  const handleSubmitReversal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reversalTarget || isSubmitting) return;
    setActionError(null);
    setIsSubmitting(true);
    try {
      await api.reverseTradeRecord({
        target_record_id: reversalTarget.id,
        reason: reversalReason.trim() || '录入笔误，红字冲正',
        idempotency_key: `rev_${reversalTarget.id}_${Date.now()}`
      });

      setActionSuccess(`流水 #${reversalTarget.id} 冲正成功，已自动对冲复原持仓！`);
      setIsReversalModalOpen(false);
      setReversalTarget(null);
      await loadData(true);
      setTimeout(() => setActionSuccess(null), 3000);
    } catch (err: any) {
      setActionError(err?.message || '发起冲正失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  // 打开反思抽屉
  const handleOpenNoteDrawer = (record: TradeRecord) => {
    setSelectedRecordForNote(record);
    const existing = record.note;
    setNoteForm({
      mental_state: existing?.mental_state || '',
      decision_logic: existing?.decision_logic || '',
      reflection: '',
      lessons: existing?.lessons || '',
      append_mode: true,
    });
    setActionError(null);
    setIsNoteDrawerOpen(true);
  };

  // 提交反思笔记
  const handleSubmitNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedRecordForNote || isSubmitting) return;
    setActionError(null);
    setIsSubmitting(true);
    try {
      await api.saveTradeNote({
        trade_id: selectedRecordForNote.id,
        date: selectedRecordForNote.trade_time.split(' ')[0],
        mental_state: noteForm.mental_state || undefined,
        decision_logic: noteForm.decision_logic || undefined,
        reflection: noteForm.reflection || undefined,
        lessons: noteForm.lessons || undefined,
        append_mode: noteForm.append_mode,
      });

      setActionSuccess('交易复盘反思笔记已保存！');
      setIsNoteDrawerOpen(false);
      setSelectedRecordForNote(null);
      await loadData(false);
      setTimeout(() => setActionSuccess(null), 3000);
    } catch (err: any) {
      setActionError(err?.message || '保存反思笔记失败');
    } finally {
      setIsSubmitting(false);
    }
  };

  // 执行对账重算
  const handleReconcile = async () => {
    try {
      setReconciling(true);
      await api.reconcilePositions();
      setActionSuccess('全量历史流水对账完成，派生持仓快照已重构对齐！');
      await loadData(true);
      setTimeout(() => setActionSuccess(null), 3000);
    } catch (err: any) {
      setActionError(err?.message || '对账重算失败');
    } finally {
      setReconciling(false);
    }
  };

  return (
    <div className="container mx-auto px-4 py-6 max-w-7xl space-y-6">
      {/* 顶部标题栏与全局操作 */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
              <Layers className="w-6 h-6 text-teal-400" />
              交易记录与持仓管理看板
            </h1>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-teal-950 text-teal-300 border border-teal-800 font-mono">
              G1-M3 Truth Ledger
            </span>
          </div>
          <p className="text-sm text-slate-400 mt-1">
            严格遵循不可篡改事实账本与派生持仓架构，客观核算胜率与盈亏，绑定主观心路反思。
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => handleOpenTradeModal('buy')}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-teal-600 hover:bg-teal-500 text-white font-medium text-sm transition shadow-sm"
          >
            <PlusCircle className="w-4 h-4" />
            录入交易事实
          </button>
          <button
            onClick={() => loadData(true)}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm border border-slate-700 transition disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            刷新行情
          </button>
          <button
            onClick={handleReconcile}
            disabled={reconciling}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm border border-slate-700 transition disabled:opacity-50"
            title="按时间正序回放全量流水，排除冲正对，重算派生持仓"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${reconciling ? 'animate-spin' : ''}`} />
            对账重算
          </button>
        </div>
      </div>

      {/* 提示消息 */}
      {actionSuccess && (
        <div className="flex items-center gap-2 p-3 bg-emerald-950/70 border border-emerald-800 text-emerald-300 rounded-lg text-sm">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{actionSuccess}</span>
        </div>
      )}
      {actionError && (
        <div className="flex items-center gap-2 p-3 bg-rose-950/70 border border-rose-800 text-rose-300 rounded-lg text-sm">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {/* 核心指标卡片矩阵 (Top Metrics) */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Card className="bg-slate-900/80 border-slate-800">
          <CardContent className="p-4">
            <div className="text-xs text-slate-400 font-medium">总持仓市值</div>
            <div className="text-xl font-bold font-mono text-slate-100 mt-1">
              {stats?.total_market_value != null ? `¥${stats.total_market_value.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` : '--'}
            </div>
            <div className="text-[11px] text-slate-500 mt-1">有效持仓数量: {positions.length} 只</div>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/80 border-slate-800">
          <CardContent className="p-4">
            <div className="text-xs text-slate-400 font-medium flex items-center justify-between">
              <span>持仓总浮动盈亏</span>
              {positions.some(p => p.price_type === 'PREV_CLOSE') && (
                <span className="text-[10px] text-slate-400 bg-slate-800 px-1 rounded">昨收参考</span>
              )}
            </div>
            <div className={`text-xl font-bold font-mono mt-1 ${
              (stats?.total_floating_pnl ?? 0) > 0 ? 'text-red-400' : (stats?.total_floating_pnl ?? 0) < 0 ? 'text-emerald-400' : 'text-slate-300'
            }`}>
              {stats?.total_floating_pnl != null ? `${stats.total_floating_pnl > 0 ? '+' : ''}¥${stats.total_floating_pnl.toFixed(2)}` : '--'}
            </div>
            <div className="text-[11px] text-slate-500 mt-1">
              {stats?.quote_status === 'PARTIAL' ? '⚠️ 部分行情断流' : '现价实时/收盘派生'}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/80 border-slate-800">
          <CardContent className="p-4">
            <div className="text-xs text-slate-400 font-medium">累计已实现盈亏</div>
            <div className={`text-xl font-bold font-mono mt-1 ${
              (stats?.total_realized_pnl ?? 0) > 0 ? 'text-red-400' : (stats?.total_realized_pnl ?? 0) < 0 ? 'text-emerald-400' : 'text-slate-300'
            }`}>
              {stats?.total_realized_pnl != null ? `${stats.total_realized_pnl > 0 ? '+' : ''}¥${stats.total_realized_pnl.toFixed(2)}` : '¥0.00'}
            </div>
            <div className="text-[11px] text-slate-500 mt-1">平仓出场累计净盈亏</div>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/80 border-slate-800">
          <CardContent className="p-4">
            <div className="text-xs text-slate-400 font-medium">单笔卖出胜率</div>
            <div className="text-xl font-bold font-mono text-cyan-300 mt-1">
              {stats?.closed_leg_win_rate != null ? `${stats.closed_leg_win_rate.toFixed(1)}%` : '--'}
            </div>
            <div className="text-[11px] text-slate-500 mt-1">
              盈利出场: {stats?.win_trades ?? 0} / 平仓: {stats?.closed_trades ?? 0}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/80 border-slate-800">
          <CardContent className="p-4">
            <div className="text-xs text-slate-400 font-medium">盈亏比 (Payoff Ratio)</div>
            <div className="text-xl font-bold font-mono text-purple-300 mt-1">
              {stats?.payoff_ratio != null ? stats.payoff_ratio.toFixed(2) : '--'}
            </div>
            <div className="text-[11px] text-slate-500 mt-1">平均每笔盈利 / 平均亏损</div>
          </CardContent>
        </Card>
      </div>

      {/* 视图切换 Tabs */}
      <div className="flex border-b border-slate-800">
        <button
          onClick={() => setActiveTab('positions')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition flex items-center gap-2 ${
            activeTab === 'positions'
              ? 'border-teal-500 text-teal-400 bg-teal-950/20'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <TrendingUp className="w-4 h-4" />
          当前持仓台账 ({positions.length})
        </button>
        <button
          onClick={() => setActiveTab('ledger')}
          className={`px-4 py-2.5 text-sm font-medium border-b-2 transition flex items-center gap-2 ${
            activeTab === 'ledger'
              ? 'border-teal-500 text-teal-400 bg-teal-950/20'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <History className="w-4 h-4" />
          交易事实流水与复盘 ({totalRecords})
        </button>
      </div>

      {/* 视图 1: 当前持仓台账 (Active Positions) */}
      {activeTab === 'positions' && (
        <div className="space-y-4">
          {positions.length === 0 ? (
            <div className="bg-slate-900/50 border border-dashed border-slate-800 rounded-xl p-12 text-center text-slate-400">
              <Layers className="w-12 h-12 mx-auto mb-3 text-slate-600" />
              <div className="text-base font-semibold text-slate-300">当前账户无持仓</div>
              <p className="text-sm text-slate-500 mt-1 max-w-md mx-auto">
                暂无有效持仓记录。点击上方【录入交易事实】按钮录入首笔买入交易，系统将自动派生并核算持仓。
              </p>
              <button
                onClick={() => handleOpenTradeModal('buy')}
                className="mt-4 px-4 py-2 bg-teal-600/80 hover:bg-teal-500 text-white text-sm font-medium rounded-lg inline-flex items-center gap-2"
              >
                <PlusCircle className="w-4 h-4" />
                立即建仓
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
              <table className="w-full text-left text-sm text-slate-300">
                <thead className="bg-slate-800/80 text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  <tr>
                    <th className="py-3 px-4">标的代码/名称</th>
                    <th className="py-3 px-4">持仓数量</th>
                    <th className="py-3 px-4">成本均价</th>
                    <th className="py-3 px-4">最新现价</th>
                    <th className="py-3 px-4">浮动盈亏</th>
                    <th className="py-3 px-4">当前市值</th>
                    <th className="py-3 px-4">行情状态</th>
                    <th className="py-3 px-4 text-right">操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {positions.map((pos) => {
                    const isUp = (pos.floating_pnl ?? 0) > 0;
                    const isDown = (pos.floating_pnl ?? 0) < 0;
                    const pnlColor = isUp ? 'text-red-400' : isDown ? 'text-emerald-400' : 'text-slate-300';

                    return (
                      <tr key={pos.code} className="hover:bg-slate-800/30 transition">
                        <td className="py-3 px-4">
                          <div className="font-semibold text-slate-100">{pos.name || pos.code}</div>
                          <div className="text-xs text-slate-500 font-mono">{pos.code}</div>
                        </td>
                        <td className="py-3 px-4 font-mono font-medium">{pos.quantity.toLocaleString()} 股</td>
                        <td className="py-3 px-4 font-mono">¥{pos.avg_cost.toFixed(3)}</td>
                        <td className="py-3 px-4 font-mono">
                          {pos.current_price != null ? (
                            <span className="font-semibold text-slate-100">¥{pos.current_price.toFixed(2)}</span>
                          ) : (
                            <span className="text-slate-500">--</span>
                          )}
                        </td>
                        <td className="py-3 px-4 font-mono">
                          {pos.floating_pnl != null ? (
                            <div className={pnlColor}>
                              <div className="font-semibold">
                                {isUp ? '+' : ''}¥{pos.floating_pnl.toFixed(2)}
                              </div>
                              <div className="text-xs">
                                {isUp ? '+' : ''}{pos.floating_pnl_pct?.toFixed(2)}%
                              </div>
                            </div>
                          ) : (
                            <span className="text-slate-500">--</span>
                          )}
                        </td>
                        <td className="py-3 px-4 font-mono">
                          {pos.market_value != null ? `¥${pos.market_value.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` : '--'}
                        </td>
                        <td className="py-3 px-4 text-xs">
                          {pos.price_type === 'REALTIME' && (
                            <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 flex items-center gap-1 w-max">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                              实时行情
                            </span>
                          )}
                          {pos.price_type === 'PREV_CLOSE' && (
                            <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 w-max inline-block" title="非交易时段，以上一交易日结算收盘价计算">
                              昨收参考*
                            </span>
                          )}
                          {pos.price_type === 'UNAVAILABLE' && (
                            <span className="px-2 py-0.5 rounded bg-rose-950/60 text-rose-400 border border-rose-800 w-max inline-block">
                              未就绪 / 断流
                            </span>
                          )}
                          {pos.quote_time && (
                            <div className="text-[10px] text-slate-500 mt-0.5 font-mono">{pos.quote_time.split(' ')[1] || pos.quote_time}</div>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => handleOpenTradeModal('sell', pos)}
                            className="px-2.5 py-1 text-xs font-medium rounded bg-rose-900/40 hover:bg-rose-900/70 text-rose-300 border border-rose-800/80 transition"
                          >
                            卖出减仓
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* 视图 2: 历史交易流水与复盘台账 (Truth Ledger) */}
      {activeTab === 'ledger' && (
        <div className="space-y-4">
          {/* 筛选工具栏 */}
          <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-slate-900/80 border border-slate-800">
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-slate-400" />
              <span className="text-xs text-slate-400">流水过滤:</span>
              <select
                value={filterDirection}
                onChange={(e) => {
                  setFilterDirection(e.target.value);
                  setCurrentPage(1);
                }}
                className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2.5 py-1"
              >
                <option value="all">全部类型</option>
                <option value="buy">仅买入 (Buy)</option>
                <option value="sell">仅卖出 (Sell)</option>
                <option value="reversal">仅冲正对冲 (Reversal)</option>
              </select>
            </div>

            <div className="flex items-center gap-2">
              <Search className="w-4 h-4 text-slate-400" />
              <input
                type="text"
                placeholder="搜索6位股票代码..."
                value={searchCode}
                onChange={(e) => {
                  setSearchCode(e.target.value);
                  setCurrentPage(1);
                }}
                className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2.5 py-1 font-mono w-36"
              />
            </div>
          </div>

          {/* 流水明细列表 */}
          {records.length === 0 ? (
            <div className="bg-slate-900/50 border border-dashed border-slate-800 rounded-xl p-12 text-center text-slate-400">
              <FileText className="w-12 h-12 mx-auto mb-3 text-slate-600" />
              <div className="text-base font-semibold text-slate-300">暂无交易流水记录</div>
              <p className="text-sm text-slate-500 mt-1">
                没有匹配当前筛选条件的交易事实记录。
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {records.map((r) => {
                const isBuy = r.direction === 'buy';
                const isReversal = r.record_type === 'REVERSAL';
                const hasNote = !!r.note;

                return (
                  <div
                    key={r.id}
                    className={`rounded-xl border p-4 transition ${
                      isReversal 
                        ? 'bg-purple-950/20 border-purple-900/50' 
                        : 'bg-slate-900/70 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                      {/* 左侧：基本事实 */}
                      <div className="flex items-start gap-3">
                        <span className={`text-xs px-2 py-1 rounded font-bold uppercase tracking-wider shrink-0 mt-0.5 ${
                          isReversal
                            ? 'bg-purple-950 text-purple-300 border border-purple-800'
                            : isBuy
                            ? 'bg-red-950/80 text-red-300 border border-red-800'
                            : 'bg-emerald-950/80 text-emerald-300 border border-emerald-800'
                        }`}>
                          {isReversal ? '🔴 冲正对冲' : isBuy ? '买入' : '卖出'}
                        </span>

                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-slate-100">{r.name || r.code}</span>
                            <span className="text-xs font-mono text-slate-400">{r.code}</span>
                            <span className="text-xs text-slate-500 font-mono">#{r.id}</span>
                          </div>

                          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400 mt-1 font-mono">
                            <span>单价: ¥{r.price.toFixed(2)}</span>
                            <span>数量: {r.quantity.toLocaleString()} 股</span>
                            <span className="text-slate-200 font-semibold">总金额: ¥{r.amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}</span>
                            <span className="text-slate-500 flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              {r.trade_time}
                            </span>
                          </div>

                          {r.trade_reason && (
                            <div className="text-xs text-slate-400 mt-1.5 bg-slate-950/60 p-2 rounded border border-slate-800/80">
                              <span className="text-slate-500">交易理由: </span>
                              {r.trade_reason}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* 右侧：操作与笔记按钮 */}
                      <div className="flex items-center gap-2 shrink-0 self-end md:self-center">
                        <button
                          onClick={() => handleOpenNoteDrawer(r)}
                          className={`flex items-center gap-1 px-2.5 py-1 text-xs rounded border transition ${
                            hasNote
                              ? 'bg-teal-950/60 text-teal-300 border-teal-800 hover:bg-teal-900/60'
                              : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200'
                          }`}
                        >
                          <BookOpen className="w-3.5 h-3.5" />
                          {hasNote ? '查看/追加反思' : '写复盘反思'}
                        </button>

                        {!isReversal && (
                          <button
                            onClick={() => handleOpenReversalModal(r)}
                            className="flex items-center gap-1 px-2.5 py-1 text-xs rounded bg-slate-800/80 hover:bg-rose-950/50 text-slate-400 hover:text-rose-300 border border-slate-700 hover:border-rose-800 transition"
                            title="对错账生成等量反向对冲记录，成对排除在胜率盈亏核算之外"
                          >
                            <ShieldAlert className="w-3.5 h-3.5" />
                            申请冲正
                          </button>
                        )}
                      </div>
                    </div>

                    {/* 挂载的复盘反思卡片 */}
                    {hasNote && (
                      <div className="mt-3 pt-3 border-t border-slate-800/60 text-xs space-y-1.5">
                        <div className="flex items-center gap-1.5 text-teal-400 font-medium">
                          <BookOpen className="w-3.5 h-3.5" />
                          <span>认知复盘笔记</span>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-slate-400">
                          {r.note?.mental_state && (
                            <div className="bg-slate-950/40 p-2 rounded border border-slate-800/60">
                              <span className="text-slate-500 font-semibold">心理状态: </span>
                              {r.note.mental_state}
                            </div>
                          )}
                          {r.note?.decision_logic && (
                            <div className="bg-slate-950/40 p-2 rounded border border-slate-800/60">
                              <span className="text-slate-500 font-semibold">决策逻辑: </span>
                              {r.note.decision_logic}
                            </div>
                          )}
                        </div>
                        {r.note?.reflection && (
                          <div className="bg-slate-950/40 p-2 rounded border border-slate-800/60 whitespace-pre-line text-slate-300">
                            <span className="text-slate-500 font-semibold">事后反思演化: </span>
                            {r.note.reflection}
                          </div>
                        )}
                        {r.note?.lessons && (
                          <div className="bg-slate-950/40 p-2 rounded border border-slate-800/60 text-amber-300/90">
                            <span className="text-amber-500 font-semibold">固化经验教训: </span>
                            {r.note.lessons}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* 分页控制 */}
          {totalRecords > 20 && (
            <div className="flex items-center justify-between text-xs text-slate-400 pt-2">
              <div>
                共 {totalRecords} 笔流水，当前第 {currentPage} 页
              </div>
              <div className="flex items-center gap-2">
                <button
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  className="px-3 py-1 bg-slate-800 rounded border border-slate-700 disabled:opacity-40"
                >
                  上一页
                </button>
                <button
                  disabled={currentPage * 20 >= totalRecords}
                  onClick={() => setCurrentPage((p) => p + 1)}
                  className="px-3 py-1 bg-slate-800 rounded border border-slate-700 disabled:opacity-40"
                >
                  下一页
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 弹窗 1: 录入买卖事实弹窗 (Trade Entry Modal) */}
      {isTradeModalOpen && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50 animate-in fade-in">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <PlusCircle className="w-5 h-5 text-teal-400" />
                录入交易事实流水
              </h3>
              <button onClick={() => setIsTradeModalOpen(false)} className="text-slate-400 hover:text-slate-200">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmitTrade} className="space-y-4 text-sm">
              {/* 方向切换 */}
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setTradeForm(f => ({ ...f, direction: 'buy' }))}
                  className={`flex-1 py-2 text-center rounded-lg font-bold text-sm transition border ${
                    tradeForm.direction === 'buy'
                      ? 'bg-red-950 text-red-300 border-red-700'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`}
                >
                  买入 (Buy)
                </button>
                <button
                  type="button"
                  onClick={() => setTradeForm(f => ({ ...f, direction: 'sell' }))}
                  className={`flex-1 py-2 text-center rounded-lg font-bold text-sm transition border ${
                    tradeForm.direction === 'sell'
                      ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`}
                >
                  卖出 (Sell)
                </button>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">股票代码 *</label>
                  <input
                    type="text"
                    required
                    placeholder="600519"
                    value={tradeForm.code}
                    onChange={(e) => setTradeForm(f => ({ ...f, code: e.target.value.trim() }))}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">股票名称</label>
                  <input
                    type="text"
                    placeholder="贵州茅台"
                    value={tradeForm.name || ''}
                    onChange={(e) => setTradeForm(f => ({ ...f, name: e.target.value }))}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">成交单价 (元) *</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    required
                    value={tradeForm.price || ''}
                    onChange={(e) => setTradeForm(f => ({ ...f, price: parseFloat(e.target.value) || 0 }))}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">成交数量 (股) *</label>
                  <input
                    type="number"
                    step="100"
                    min="1"
                    required
                    value={tradeForm.quantity || ''}
                    onChange={(e) => setTradeForm(f => ({ ...f, quantity: parseInt(e.target.value, 10) || 0 }))}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 font-mono"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">成交时间 (YYYY-MM-DD HH:MM:SS) *</label>
                <input
                  type="text"
                  required
                  value={tradeForm.trade_time}
                  onChange={(e) => setTradeForm(f => ({ ...f, trade_time: e.target.value }))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 font-mono"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">交易理由简述</label>
                <textarea
                  rows={2}
                  placeholder="记录本次买卖的事实理由、市场信号或逻辑支撑..."
                  value={tradeForm.trade_reason || ''}
                  onChange={(e) => setTradeForm(f => ({ ...f, trade_reason: e.target.value }))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 text-xs"
                />
              </div>

              <div className="bg-slate-950 p-2.5 rounded border border-slate-800 text-xs font-mono flex justify-between text-slate-400">
                <span>预估成交总额:</span>
                <span className="font-bold text-slate-100">
                  ¥{(tradeForm.price * tradeForm.quantity).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                </span>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsTradeModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 text-xs font-medium"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 bg-teal-600 hover:bg-teal-500 text-white rounded-lg text-xs font-bold transition shadow-sm disabled:opacity-50"
                >
                  {isSubmitting ? '正在录入...' : '确认录入事实'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 弹窗 2: 红字冲正确认弹窗 (Reversal Modal) */}
      {isReversalModalOpen && reversalTarget && (
        <div className="fixed inset-0 bg-black/75 flex items-center justify-center p-4 z-50 animate-in fade-in">
          <div className="bg-slate-900 border border-rose-900/60 rounded-xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-lg font-bold text-rose-300 flex items-center gap-2">
                <ShieldAlert className="w-5 h-5 text-rose-400" />
                申请会计红字冲正
              </h3>
              <button onClick={() => setIsReversalModalOpen(false)} className="text-slate-400 hover:text-slate-200">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="bg-rose-950/30 border border-rose-900/60 rounded p-3 text-xs text-rose-200/90 leading-relaxed">
              <strong>硬隔离安全机制提醒：</strong> 冲正将生成一条反向对冲流水抵消错账，并在状态机回放中成对抹除，持仓成本将完全复原，且绝不污染平仓胜率与已实现盈亏。
            </div>

            <div className="bg-slate-950 p-3 rounded border border-slate-800 text-xs space-y-1 font-mono text-slate-400">
              <div>目标流水: #{reversalTarget.id} ({reversalTarget.direction.toUpperCase()})</div>
              <div>标的: {reversalTarget.name || reversalTarget.code} ({reversalTarget.code})</div>
              <div>单价: ¥{reversalTarget.price.toFixed(2)} | 数量: {reversalTarget.quantity} 股</div>
              <div>金额: ¥{reversalTarget.amount.toFixed(2)}</div>
            </div>

            <form onSubmit={handleSubmitReversal} className="space-y-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">冲正原因说明 *</label>
                <textarea
                  required
                  rows={3}
                  value={reversalReason}
                  onChange={(e) => setReversalReason(e.target.value)}
                  placeholder="例如：录错买卖方向 / 输入价格笔误 / 连击重复录入..."
                  className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-slate-100 text-xs"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsReversalModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 text-xs font-medium"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 bg-rose-700 hover:bg-rose-600 text-white rounded-lg text-xs font-bold transition shadow-sm disabled:opacity-50"
                >
                  {isSubmitting ? '正在对冲...' : '确认生成冲正对冲'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 弹窗 3: 复盘反思抽屉 (Trade Note Drawer) */}
      {isNoteDrawerOpen && selectedRecordForNote && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50 animate-in fade-in">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-xl w-full p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <BookOpen className="w-5 h-5 text-teal-400" />
                交易认知复盘反思笔记
              </h3>
              <button onClick={() => setIsNoteDrawerOpen(false)} className="text-slate-400 hover:text-slate-200">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="bg-slate-950 p-2.5 rounded border border-slate-800 text-xs font-mono text-slate-400">
              流水 #{selectedRecordForNote.id} | {selectedRecordForNote.name || selectedRecordForNote.code} ({selectedRecordForNote.direction.toUpperCase()}) | {selectedRecordForNote.trade_time}
            </div>

            <form onSubmit={handleSubmitNote} className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 mb-1">交易时心理状态 (Mental State)</label>
                <input
                  type="text"
                  placeholder="例如：冷静执行预案 / 恐慌急躁 / 侥幸跟风..."
                  value={noteForm.mental_state}
                  onChange={(e) => setNoteForm(f => ({ ...f, mental_state: e.target.value }))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">决策逻辑 (Decision Logic)</label>
                <textarea
                  rows={2}
                  placeholder="例如：5日均线企稳回踩确认，板块放量共振..."
                  value={noteForm.decision_logic}
                  onChange={(e) => setNoteForm(f => ({ ...f, decision_logic: e.target.value }))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-slate-400">事后反思 (Reflection)</label>
                  <label className="flex items-center gap-1.5 cursor-pointer text-teal-400 text-[11px]">
                    <input
                      type="checkbox"
                      checked={noteForm.append_mode}
                      onChange={(e) => setNoteForm(f => ({ ...f, append_mode: e.target.checked }))}
                    />
                    增量时间戳追加模式 ([HH:MM 追加])
                  </label>
                </div>
                <textarea
                  rows={3}
                  placeholder="输入事后反思、得失剖析..."
                  value={noteForm.reflection}
                  onChange={(e) => setNoteForm(f => ({ ...f, reflection: e.target.value }))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">沉淀经验教训 (Lessons)</label>
                <textarea
                  rows={2}
                  placeholder="例如：跌破止损线决不心存侥幸，果断出局..."
                  value={noteForm.lessons}
                  onChange={(e) => setNoteForm(f => ({ ...f, lessons: e.target.value }))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 text-amber-300"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsNoteDrawerOpen(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 font-medium"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 bg-teal-600 hover:bg-teal-500 text-white rounded-lg font-bold transition shadow-sm disabled:opacity-50"
                >
                  {isSubmitting ? '正在保存...' : '保存反思笔记'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
