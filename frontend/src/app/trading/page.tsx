'use client';

import { useEffect, useState, useMemo } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { Position, TradeRecord, TradeStats, TradeRecordCreatePayload, ReversalTradeCreatePayload, TradeNoteCreatePayload, SecuritySearchResult } from '@/types/trading';
import { formatDateWithWeekday } from '@/lib/utils';
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
  X,
  Brain,
  BarChart2,
  CheckCheck,
  PlaySquare
} from 'lucide-react';
import { CognitiveTradeDiagnosis, WeeklyAuditResponse } from '@/types/cognition';

export default function TradingPage() {
  // 核心状态
  const [positions, setPositions] = useState<Position[]>([]);
  const [records, setRecords] = useState<TradeRecord[]>([]);
  const [stats, setStats] = useState<TradeStats | null>(null);
  const [brokerStatus, setBrokerStatus] = useState<any>(null);
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
  const [isCorrectionModalOpen, setIsCorrectionModalOpen] = useState(false);
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
  const [correctionTarget, setCorrectionTarget] = useState<TradeRecord | null>(null);
  const [correctionReason, setCorrectionReason] = useState('数据录入修正');
  const [correctionForm, setCorrectionForm] = useState<TradeRecordCreatePayload>({
    code: '',
    name: '',
    direction: 'buy',
    price: 0,
    quantity: 100,
    trade_time: '',
    trade_reason: '',
  });

  // 标的代码与名称联动搜索状态
  const [searchResults, setSearchResults] = useState<SecuritySearchResult[]>([]);
  const [showSearchResults, setShowSearchResults] = useState(false);
  const [searchTargetModal, setSearchTargetModal] = useState<'trade' | 'correction' | null>(null);

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

  // G1-Cognition 认知诊断与周度复盘状态
  const [isDiagnosisDrawerOpen, setIsDiagnosisDrawerOpen] = useState(false);
  const [selectedRecordForDiag, setSelectedRecordForDiag] = useState<TradeRecord | null>(null);
  const [diagnosisData, setDiagnosisData] = useState<CognitiveTradeDiagnosis | null>(null);
  const [diagLoading, setDiagLoading] = useState(false);
  const [diagSubmitting, setDiagSubmitting] = useState(false);
  const [diagComment, setDiagComment] = useState('');

  const [isWeeklyAuditOpen, setIsWeeklyAuditOpen] = useState(false);
  const [weeklyAuditData, setWeeklyAuditData] = useState<WeeklyAuditResponse | null>(null);
  const [weeklyAuditLoading, setWeeklyAuditLoading] = useState(false);
  const [weeklyOffset, setWeeklyOffset] = useState(0);

  // 加载全量数据
  const loadData = async (refreshQuote: boolean = true) => {
    try {
      if (refreshQuote) setRefreshing(true);
      const [posRes, statsRes, recRes, bStatus] = await Promise.all([
        api.getPositions(refreshQuote).catch(() => []),
        api.getTradeStats().catch(() => null),
        api.getTradeRecords({
          code: searchCode.trim() || undefined,
          direction: filterDirection !== 'all' && filterDirection !== 'reversal' ? filterDirection : undefined,
          record_type: filterDirection === 'reversal' ? 'REVERSAL' : undefined,
          page: currentPage,
          limit: 20
        }).catch(() => ({ items: [], total: 0, page: 1, limit: 20 })),
        api.getBrokerStatus().catch(() => null)
      ]);

      setPositions(posRes || []);
      setStats(statsRes);
      setRecords(recRes.items || []);
      setTotalRecords(recRes.total || 0);
      setBrokerStatus(bStatus);
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

  // 股票代码与名称联动搜索处理
  const handleCodeInputChange = async (val: string, targetModal: 'trade' | 'correction') => {
    const cleanCode = val.trim();
    if (targetModal === 'trade') {
      setTradeForm(f => ({ ...f, code: cleanCode }));
    } else {
      setCorrectionForm(f => ({ ...f, code: cleanCode }));
    }

    if (/^\d{6}$/.test(cleanCode)) {
      try {
        const results = await api.searchSecurities(cleanCode, 5);
        const match = results?.find(r => r.code === cleanCode) || results?.[0];
        if (match && match.code === cleanCode) {
          if (targetModal === 'trade') {
            setTradeForm(f => ({ ...f, code: match.code, name: match.name }));
          } else {
            setCorrectionForm(f => ({ ...f, code: match.code, name: match.name }));
          }
        }
      } catch (err) {
        console.error('标的代码联想失败:', err);
      }
    }
  };

  const handleNameInputChange = async (val: string, targetModal: 'trade' | 'correction') => {
    if (targetModal === 'trade') {
      setTradeForm(f => ({ ...f, name: val }));
    } else {
      setCorrectionForm(f => ({ ...f, name: val }));
    }

    const query = val.trim();
    if (query.length >= 1) {
      try {
        setSearchTargetModal(targetModal);
        const results = await api.searchSecurities(query, 8);
        setSearchResults(results || []);
        setShowSearchResults((results && results.length > 0) || false);
      } catch (err) {
        setSearchResults([]);
        setShowSearchResults(false);
      }
    } else {
      setSearchResults([]);
      setShowSearchResults(false);
      setSearchTargetModal(null);
    }
  };

  const handleSelectSecurity = (item: SecuritySearchResult, targetModal: 'trade' | 'correction') => {
    if (targetModal === 'trade') {
      setTradeForm(f => ({ ...f, code: item.code, name: item.name }));
    } else {
      setCorrectionForm(f => ({ ...f, code: item.code, name: item.name }));
    }
    setShowSearchResults(false);
    setSearchTargetModal(null);
  };

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
    setShowSearchResults(false);
    setSearchTargetModal(null);
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
      if (tradeForm.quantity < 100 || tradeForm.quantity % 100 !== 0) {
        throw new Error('A股买卖数量必须大于等于100且为100的整数倍（整手）');
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

  // 打开纠错弹窗
  const handleOpenCorrectionModal = (record: TradeRecord) => {
    setCorrectionTarget(record);
    setCorrectionReason('数据录入修正');
    setCorrectionForm({
      code: record.code,
      name: record.name || '',
      direction: record.direction,
      price: record.price,
      quantity: record.quantity,
      trade_time: record.trade_time,
      trade_reason: record.trade_reason || '',
    });
    setShowSearchResults(false);
    setSearchTargetModal(null);
    setActionError(null);
    setIsCorrectionModalOpen(true);
  };

  // 提交纠错
  const handleSubmitCorrection = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!correctionTarget || isSubmitting) return;
    setActionError(null);

    if (!correctionForm.code || !/^\d{6}$/.test(correctionForm.code)) {
      setActionError('股票代码必须为6位纯数字');
      return;
    }
    if (correctionForm.price <= 0) {
      setActionError('成交单价必须大于0');
      return;
    }
    if (correctionForm.quantity < 100 || correctionForm.quantity % 100 !== 0) {
      setActionError('A股买卖数量必须大于等于100且为100的整数倍（整手）');
      return;
    }

    setIsSubmitting(true);
    try {
      await api.correctTradeRecord({
        target_record_id: correctionTarget.id,
        reason: correctionReason.trim() || '数据录入修正',
        corrected_data: {
          ...correctionForm,
          idempotency_key: `corr_${correctionTarget.id}_${Date.now()}`
        }
      });

      setActionSuccess(`流水 #${correctionTarget.id} 纠错成功！已生成冲正流水并录入新交易流水。`);
      setIsCorrectionModalOpen(false);
      setCorrectionTarget(null);
      await loadData(true);
      setTimeout(() => setActionSuccess(null), 3000);
    } catch (err: any) {
      setActionError(err?.message || '纠错操作失败');
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

  // 清洗沙盒模拟数据并对账
  const handlePurgeSim = async () => {
    try {
      setReconciling(true);
      const res = await api.purgeSimulationFromTruthLedger();
      setActionSuccess(`真实账本已校验，成功清洗 ${res.purged_records_count} 笔沙盒数据并重算持仓！`);
      await loadData(true);
      setTimeout(() => setActionSuccess(null), 3500);
    } catch (err: any) {
      setActionError(err?.message || '清洗沙盒数据失败');
    } finally {
      setReconciling(false);
    }
  };

  // 打开单笔交易认知诊断抽屉
  const handleOpenDiagnosisModal = async (record: TradeRecord) => {
    setSelectedRecordForDiag(record);
    setIsDiagnosisDrawerOpen(true);
    setDiagLoading(true);
    setDiagnosisData(null);
    setDiagComment('');
    setActionError(null);
    try {
      let diag: CognitiveTradeDiagnosis;
      try {
        diag = await api.getTradeDiagnosis(record.id);
      } catch (e: any) {
        // 若尚无诊断记录，主动触发一次对撞诊断
        diag = await api.triggerTradeDiagnosis(record.id);
      }
      setDiagnosisData(diag);
      setDiagComment(diag.human_comment || '');
    } catch (err: any) {
      console.error('加载认知诊断失败:', err);
      setActionError(err?.message || '获取认知诊断失败');
    } finally {
      setDiagLoading(false);
    }
  };

  // 确认或修正单笔认知诊断
  const handleConfirmDiagnosis = async (status: 'CONFIRMED' | 'MODIFIED') => {
    if (!selectedRecordForDiag || !diagnosisData || diagSubmitting) return;
    setDiagSubmitting(true);
    setActionError(null);
    try {
      await api.confirmTradeDiagnosis(selectedRecordForDiag.id, {
        human_status: status,
        human_comment: diagComment.trim() || undefined,
      });
      setDiagnosisData({
        ...diagnosisData,
        human_status: status,
        human_comment: diagComment.trim() || null,
      });
      setActionSuccess(status === 'CONFIRMED' ? '已确认采纳该笔交易的 AI 认知诊断！' : '已成功录入人工修正意见！');
      setTimeout(() => setActionSuccess(null), 3000);
    } catch (err: any) {
      console.error('确认诊断失败:', err);
      setActionError(err?.message || '确认诊断操作失败');
    } finally {
      setDiagSubmitting(false);
    }
  };

  // 打开周度认知复盘抽屉
  const handleOpenWeeklyAudit = async (offset: number = 0) => {
    setIsWeeklyAuditOpen(true);
    setWeeklyOffset(offset);
    setWeeklyAuditLoading(true);
    setActionError(null);
    try {
      const res = await api.getWeeklyAudit(offset);
      setWeeklyAuditData(res);
    } catch (err: any) {
      console.error('加载周度认知复盘失败:', err);
      setActionError(err?.message || '加载周度复盘数据失败');
    } finally {
      setWeeklyAuditLoading(false);
    }
  };

  return (
    <div className="container mx-auto px-4 py-6 max-w-7xl space-y-6">
      {/* 顶部标题栏与全局操作 */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
              <Layers className="w-6 h-6 text-purple-400" />
              交易记录与持仓管理看板
            </h1>
            <span className="text-sm px-2.5 py-0.5 rounded-full bg-purple-950 text-purple-300 border border-purple-800 font-mono">
              G1-M3 Truth Ledger
            </span>
          </div>
          <p className="text-base text-slate-400 mt-1">
            严格遵循不可篡改事实账本与派生持仓架构，客观核算胜率与盈亏，绑定主观心路反思。
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => handleOpenTradeModal('buy')}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-medium text-sm transition shadow-lg shadow-purple-900/30"
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
          <button
            onClick={() => handleOpenWeeklyAudit(0)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-950/80 hover:bg-indigo-900/80 text-indigo-300 text-sm border border-indigo-800 transition"
            title="查看周度三维客观认知复盘与未确认样本隔离度量"
          >
            <BarChart2 className="w-3.5 h-3.5" />
            周度认知复盘
          </button>
        </div>
      </div>

      {/* 提示消息 */}
      {actionSuccess && (
        <div className="flex items-center gap-2 p-3 bg-emerald-950/70 border border-emerald-800 text-emerald-300 rounded-lg text-base">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{actionSuccess}</span>
        </div>
      )}
      {actionError && (
        <div className="flex items-center gap-2 p-3 bg-rose-950/70 border border-rose-800 text-rose-300 rounded-lg text-base">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          <span>{actionError}</span>
        </div>
      )}

      {/* 真实券商接入状态与沙盒物理隔离防护栏 */}
      <div className="rounded-xl border border-amber-500/20 bg-amber-950/10 p-3.5 flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
        <div className="flex items-start sm:items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center shrink-0 text-amber-400">
            <ShieldAlert className="w-4 h-4" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-bold text-amber-300">
                真实券商委托通道：{brokerStatus?.broker_name || '未接入实盘券商'}
              </span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-amber-900/40 text-amber-400 border border-amber-800">
                {brokerStatus?.message || '待接入 QMT / PTrade 自动化委托'}
              </span>
              <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 border border-emerald-800">
                沙盒物理隔离已激活
              </span>
            </div>
            <p className="text-sm text-slate-400 mt-0.5">
              本看板为用户真实账户不可篡改交割账本（Truth Ledger）。策略自动跟单与推演交易已在【<Link href="/simulation" className="text-purple-400 underline hover:text-purple-300">实盘模拟沙盒</Link>】独立核算，严禁交叉污染。
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 self-end md:self-center">
          <Link
            href="/simulation"
            className="flex items-center gap-1 px-2.5 py-1 text-sm rounded bg-purple-950/50 hover:bg-purple-900/60 text-purple-300 border border-purple-800/80 transition"
          >
            <PlaySquare className="w-3.5 h-3.5" />
            查看策略实盘模拟
          </Link>
          <button
            onClick={handlePurgeSim}
            disabled={reconciling}
            className="flex items-center gap-1 px-2.5 py-1 text-sm rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition disabled:opacity-50"
            title="一键清洗可能误入真实账本的策略模拟测试数据并重算对齐持仓"
          >
            <RotateCcw className={`w-3 h-3 ${reconciling ? 'animate-spin' : ''}`} />
            对账校验与沙盒清洗
          </button>
        </div>
      </div>

      {/* 核心指标卡片矩阵 (Top Metrics) */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Card className="bg-slate-900/80 border-white/10">
          <CardContent className="p-4">
            <div className="text-sm text-slate-400 font-medium">总持仓市值</div>
            <div className="text-2xl font-bold font-mono text-slate-100 mt-1">
              {stats?.total_market_value != null ? `¥${stats.total_market_value.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}` : '--'}
            </div>
            <div className="text-xs text-slate-500 mt-1">有效持仓数量: {positions.length} 只</div>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/80 border-white/10">
          <CardContent className="p-4">
            <div className="text-sm text-slate-400 font-medium flex items-center justify-between">
              <span>持仓总浮动盈亏</span>
              {positions.some(p => p.price_type === 'PREV_CLOSE') && (
                <span className="text-xs text-slate-400 bg-slate-800 px-1 rounded">昨收参考</span>
              )}
            </div>
            <div className={`text-2xl font-bold font-mono mt-1 ${
              (stats?.total_floating_pnl ?? 0) > 0 ? 'text-red-400' : (stats?.total_floating_pnl ?? 0) < 0 ? 'text-emerald-400' : 'text-slate-300'
            }`}>
              {stats?.total_floating_pnl != null ? `${stats.total_floating_pnl > 0 ? '+' : ''}¥${stats.total_floating_pnl.toFixed(2)}` : '--'}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {stats?.quote_status === 'PARTIAL' ? '⚠️ 部分行情断流' : '现价实时/收盘派生'}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/80 border-white/10">
          <CardContent className="p-4">
            <div className="text-sm text-slate-400 font-medium">累计已实现盈亏</div>
            <div className={`text-2xl font-bold font-mono mt-1 ${
              (stats?.total_realized_pnl ?? 0) > 0 ? 'text-red-400' : (stats?.total_realized_pnl ?? 0) < 0 ? 'text-emerald-400' : 'text-slate-300'
            }`}>
              {stats?.total_realized_pnl != null ? `${stats.total_realized_pnl > 0 ? '+' : ''}¥${stats.total_realized_pnl.toFixed(2)}` : '¥0.00'}
            </div>
            <div className="text-xs text-slate-500 mt-1">平仓出场累计净盈亏</div>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/80 border-white/10">
          <CardContent className="p-4">
            <div className="text-sm text-slate-400 font-medium">单笔卖出胜率</div>
            <div className="text-2xl font-bold font-mono text-cyan-300 mt-1">
              {stats?.closed_leg_win_rate != null ? `${stats.closed_leg_win_rate.toFixed(1)}%` : '--'}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              盈利出场: {stats?.win_trades ?? 0} / 平仓: {stats?.closed_trades ?? 0}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/80 border-white/10">
          <CardContent className="p-4">
            <div className="text-sm text-slate-400 font-medium">盈亏比 (Payoff Ratio)</div>
            <div className="text-2xl font-bold font-mono text-purple-300 mt-1">
              {stats?.payoff_ratio != null ? stats.payoff_ratio.toFixed(2) : '--'}
            </div>
            <div className="text-xs text-slate-500 mt-1">平均每笔盈利 / 平均亏损</div>
          </CardContent>
        </Card>
      </div>

      {/* 视图切换 Tabs */}
      <div className="flex border-b border-white/10">
        <button
          onClick={() => setActiveTab('positions')}
          className={`px-4 py-2.5 text-base font-medium border-b-2 transition flex items-center gap-2 ${
            activeTab === 'positions'
              ? 'border-purple-500 text-purple-400 bg-purple-950/20'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <TrendingUp className="w-4 h-4" />
          当前持仓台账 ({positions.length})
        </button>
        <button
          onClick={() => setActiveTab('ledger')}
          className={`px-4 py-2.5 text-base font-medium border-b-2 transition flex items-center gap-2 ${
            activeTab === 'ledger'
              ? 'border-purple-500 text-purple-400 bg-purple-950/20'
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
            <div className="bg-slate-900/50 border border-dashed border-white/10 rounded-xl p-12 text-center text-slate-400">
              <Layers className="w-12 h-12 mx-auto mb-3 text-slate-600" />
              <div className="text-lg font-semibold text-slate-300">真实账户暂无持仓</div>
              <p className="text-base text-slate-500 mt-1 max-w-lg mx-auto">
                用户当前尚未接入实盘券商委托接口（如 QMT / PTrade 自动化通道）。此处仅保留用户手工录入或券商对账单导入的真实交割流水，与策略实盘模拟（Paper Trading）实现 100% 物理隔离。
              </p>
              <div className="flex items-center justify-center gap-3 mt-4">
                <button
                  onClick={() => handleOpenTradeModal('buy')}
                  className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white text-sm font-medium rounded-lg inline-flex items-center gap-2 shadow-lg shadow-purple-900/30 transition-all"
                >
                  <PlusCircle className="w-4 h-4" />
                  手工录入真实交易
                </button>
                <Link
                  href="/simulation"
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-purple-300 text-sm font-medium rounded-lg inline-flex items-center gap-2 border border-purple-800/50 transition-all"
                >
                  <PlaySquare className="w-4 h-4" />
                  前往策略实盘模拟
                </Link>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-white/10 bg-slate-900/60">
              <table className="w-full text-left text-sm text-slate-300">
                <thead className="bg-slate-800/80 text-sm font-semibold text-slate-400 uppercase tracking-wider">
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
                          <div className="text-sm text-slate-500 font-mono">{pos.code}</div>
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
                              <div className="text-sm">
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
                        <td className="py-3 px-4 text-sm">
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
                            <div className="text-xs text-slate-500 mt-0.5 font-mono">{pos.quote_time.split(' ')[1] || pos.quote_time}</div>
                          )}
                        </td>
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => handleOpenTradeModal('sell', pos)}
                            className="px-2.5 py-1 text-sm font-medium rounded bg-rose-900/40 hover:bg-rose-900/70 text-rose-300 border border-rose-800/80 transition"
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
          <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-slate-900/80 border border-white/10">
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-slate-400" />
              <span className="text-sm text-slate-400">流水过滤:</span>
              <select
                value={filterDirection}
                onChange={(e) => {
                  setFilterDirection(e.target.value);
                  setCurrentPage(1);
                }}
                className="bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded px-2.5 py-1"
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
                className="bg-slate-800 border border-slate-700 text-slate-200 text-sm rounded px-2.5 py-1 font-mono w-40"
              />
            </div>
          </div>

          {/* 流水明细列表 */}
          {records.length === 0 ? (
            <div className="bg-slate-900/50 border border-dashed border-white/10 rounded-xl p-12 text-center text-slate-400">
              <FileText className="w-12 h-12 mx-auto mb-3 text-slate-600" />
              <div className="text-lg font-semibold text-slate-300">真实账本暂无流水记录</div>
              <p className="text-base text-slate-500 mt-1 max-w-md mx-auto">
                真实不可篡改交割账本（Truth Ledger）暂无符合条件的交易记录。策略自动化测试交易已被严格隔离至实盘模拟沙盒。
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
                        : 'bg-slate-900/70 border-white/10 hover:border-white/20'
                    }`}
                  >
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                      {/* 左侧：基本事实 */}
                      <div className="flex items-start gap-3">
                        <span className={`text-sm px-2 py-1 rounded font-bold uppercase tracking-wider shrink-0 mt-0.5 ${
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
                            <span className="text-sm font-mono text-slate-400">{r.code}</span>
                            <span className="text-sm text-slate-500 font-mono">#{r.id}</span>
                          </div>

                          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-400 mt-1 font-mono">
                            <span>单价: ¥{r.price.toFixed(2)}</span>
                            <span>数量: {r.quantity.toLocaleString()} 股</span>
                            <span className="text-slate-200 font-semibold">总金额: ¥{r.amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}</span>
                            <span className="text-slate-500 flex items-center gap-1">
                              <Clock className="w-3.5 h-3.5" />
                              {r.trade_time}
                            </span>
                          </div>

                          {r.trade_reason && (
                            <div className="text-sm text-slate-400 mt-1.5 bg-slate-950/60 p-2 rounded border border-white/10">
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
                          className={`flex items-center gap-1 px-2.5 py-1 text-sm rounded border transition ${
                            hasNote
                              ? 'bg-purple-950/60 text-purple-300 border-purple-800 hover:bg-purple-900/60'
                              : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200'
                          }`}
                        >
                          <BookOpen className="w-3.5 h-3.5" />
                          {hasNote ? '查看/追加反思' : '写复盘反思'}
                        </button>

                        {!isReversal && (
                          <button
                            onClick={() => handleOpenDiagnosisModal(r)}
                            className="flex items-center gap-1 px-2.5 py-1 text-sm rounded bg-indigo-950/60 hover:bg-indigo-900/70 text-indigo-300 border border-indigo-800/80 transition"
                            title="对撞市场状态D1~D6，生成双层物理隔离的单笔认知诊断"
                          >
                            <Brain className="w-3.5 h-3.5" />
                            认知诊断
                          </button>
                        )}

                        {!isReversal && (
                          <button
                            onClick={() => handleOpenCorrectionModal(r)}
                            className="flex items-center gap-1 px-2.5 py-1 text-sm rounded bg-amber-950/60 hover:bg-amber-900/70 text-amber-300 border border-amber-800/80 transition"
                            title="修正交易记录（原子化执行：冲销原交易 + 录入新交易 + 迁移笔记）"
                          >
                            <RotateCcw className="w-3.5 h-3.5" />
                            纠错
                          </button>
                        )}

                        {!isReversal && (
                          <button
                            onClick={() => handleOpenReversalModal(r)}
                            className="flex items-center gap-1 px-2.5 py-1 text-sm rounded bg-slate-800/80 hover:bg-rose-950/50 text-slate-400 hover:text-rose-300 border border-slate-700 hover:border-rose-800 transition"
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
                      <div className="mt-3 pt-3 border-t border-white/10 text-sm space-y-1.5">
                        <div className="flex items-center gap-1.5 text-purple-400 font-medium">
                          <BookOpen className="w-3.5 h-3.5" />
                          <span>认知复盘笔记</span>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-slate-400">
                          {r.note?.mental_state && (
                            <div className="bg-slate-950/40 p-2 rounded border border-white/10">
                              <span className="text-slate-500 font-semibold">心理状态: </span>
                              {r.note.mental_state}
                            </div>
                          )}
                          {r.note?.decision_logic && (
                            <div className="bg-slate-950/40 p-2 rounded border border-white/10">
                              <span className="text-slate-500 font-semibold">决策逻辑: </span>
                              {r.note.decision_logic}
                            </div>
                          )}
                        </div>
                        {r.note?.reflection && (
                          <div className="bg-slate-950/40 p-2 rounded border border-white/10 whitespace-pre-line text-slate-300">
                            <span className="text-slate-500 font-semibold">事后反思演化: </span>
                            {r.note.reflection}
                          </div>
                        )}
                        {r.note?.lessons && (
                          <div className="bg-slate-950/40 p-2 rounded border border-white/10 text-amber-300/90">
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
            <div className="flex items-center justify-between text-sm text-slate-400 pt-2">
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
          <div className="bg-slate-900 border border-white/10 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <PlusCircle className="w-5 h-5 text-purple-400" />
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

              <div className="grid grid-cols-2 gap-3 relative">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">股票代码 *</label>
                  <input
                    type="text"
                    required
                    placeholder="600519"
                    value={tradeForm.code}
                    onChange={(e) => handleCodeInputChange(e.target.value, 'trade')}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 font-mono text-sm"
                  />
                </div>
                <div className="relative">
                  <label className="block text-sm text-slate-400 mb-1">股票名称 (支持拼音/汉字联想)</label>
                  <input
                    type="text"
                    placeholder="例如 茅台 / gzmt"
                    value={tradeForm.name || ''}
                    onChange={(e) => handleNameInputChange(e.target.value, 'trade')}
                    onFocus={() => {
                      if (searchResults.length > 0 && searchTargetModal === 'trade') {
                        setShowSearchResults(true);
                      }
                    }}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 text-sm"
                  />
                  {showSearchResults && searchTargetModal === 'trade' && searchResults.length > 0 && (
                    <div className="absolute left-0 right-0 top-full mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-50 max-h-48 overflow-y-auto">
                      {searchResults.map((item) => (
                        <div
                          key={item.code}
                          onClick={() => handleSelectSecurity(item, 'trade')}
                          className="px-3 py-2 text-sm hover:bg-purple-900/40 cursor-pointer flex items-center justify-between border-b border-slate-700/50 last:border-b-0"
                        >
                          <span className="font-semibold text-slate-200">{item.name}</span>
                          <span className="text-slate-400 font-mono">{item.code} ({item.market})</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">成交单价 (元) *</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    required
                    value={tradeForm.price || ''}
                    onChange={(e) => setTradeForm(f => ({ ...f, price: parseFloat(e.target.value) || 0 }))}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 font-mono text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">成交数量 (股) * (整手 ≥ 100)</label>
                  <input
                    type="number"
                    step="100"
                    min="100"
                    required
                    value={tradeForm.quantity || ''}
                    onChange={(e) => setTradeForm(f => ({ ...f, quantity: parseInt(e.target.value, 10) || 0 }))}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 font-mono text-sm"
                  />
                  {tradeForm.quantity > 0 && (tradeForm.quantity < 100 || tradeForm.quantity % 100 !== 0) && (
                    <p className="text-sm text-rose-400 mt-1">数量必须 ≥ 100 且为 100 的整数倍</p>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">成交时间 (YYYY-MM-DD HH:MM:SS) *</label>
                <input
                  type="text"
                  required
                  value={tradeForm.trade_time}
                  onChange={(e) => setTradeForm(f => ({ ...f, trade_time: e.target.value }))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 font-mono text-sm"
                />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">交易理由简述</label>
                <textarea
                  rows={2}
                  placeholder="记录本次买卖的事实理由、市场信号或逻辑支撑..."
                  value={tradeForm.trade_reason || ''}
                  onChange={(e) => setTradeForm(f => ({ ...f, trade_reason: e.target.value }))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 text-sm"
                />
              </div>

              <div className="bg-slate-950 p-2.5 rounded border border-white/10 text-sm font-mono flex justify-between text-slate-400">
                <span>预估成交总额:</span>
                <span className="font-bold text-slate-100">
                  ¥{(tradeForm.price * tradeForm.quantity).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                </span>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsTradeModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 text-sm font-medium"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm font-bold transition shadow-lg shadow-purple-900/30 disabled:opacity-50"
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
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <h3 className="text-lg font-bold text-rose-300 flex items-center gap-2">
                <ShieldAlert className="w-5 h-5 text-rose-400" />
                申请会计红字冲正
              </h3>
              <button onClick={() => setIsReversalModalOpen(false)} className="text-slate-400 hover:text-slate-200">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="bg-rose-950/30 border border-rose-900/60 rounded p-3 text-sm text-rose-200/90 leading-relaxed">
              <strong>硬隔离安全机制提醒：</strong> 冲正将生成一条反向对冲流水抵消错账，并在状态机回放中成对抹除，持仓成本将完全复原，且绝不污染平仓胜率与已实现盈亏。
            </div>

            <div className="bg-slate-950 p-3 rounded border border-white/10 text-sm space-y-1 font-mono text-slate-400">
              <div>目标流水: #{reversalTarget.id} ({reversalTarget.direction.toUpperCase()})</div>
              <div>标的: {reversalTarget.name || reversalTarget.code} ({reversalTarget.code})</div>
              <div>单价: ¥{reversalTarget.price.toFixed(2)} | 数量: {reversalTarget.quantity} 股</div>
              <div>金额: ¥{reversalTarget.amount.toFixed(2)}</div>
            </div>

            <form onSubmit={handleSubmitReversal} className="space-y-3">
              <div>
                <label className="block text-sm text-slate-400 mb-1">冲正原因说明 *</label>
                <textarea
                  required
                  rows={3}
                  value={reversalReason}
                  onChange={(e) => setReversalReason(e.target.value)}
                  placeholder="例如：录错买卖方向 / 输入价格笔误 / 连击重复录入..."
                  className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-slate-100 text-sm"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsReversalModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 text-sm font-medium"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 bg-rose-700 hover:bg-rose-600 text-white rounded-lg text-sm font-bold transition shadow-sm disabled:opacity-50"
                >
                  {isSubmitting ? '正在对冲...' : '确认生成冲正对冲'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 弹窗 4: 交易记录纠错弹窗 (Correction Modal) */}
      {isCorrectionModalOpen && correctionTarget && (
        <div className="fixed inset-0 bg-black/75 flex items-center justify-center p-4 z-50 animate-in fade-in">
          <div className="bg-slate-900 border border-amber-900/60 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <h3 className="text-lg font-bold text-amber-300 flex items-center gap-2">
                <RotateCcw className="w-5 h-5 text-amber-400" />
                交易记录纠错 (Truth Ledger Correction)
              </h3>
              <button onClick={() => setIsCorrectionModalOpen(false)} className="text-slate-400 hover:text-slate-200">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="bg-amber-950/30 border border-amber-900/60 rounded p-3 text-sm text-amber-200/90 leading-relaxed">
              <strong>审计不可篡改闭环保障：</strong> 系统将原子化自动生成一条冲正流水（REVERSAL）抵消原记录 #{correctionTarget.id}，同时生成一条全新正确的交易事实流水，并自动迁移复盘反思笔记及重新核算对齐持仓。
            </div>

            <div className="bg-slate-950 p-2.5 rounded border border-white/10 text-sm space-y-1 font-mono text-slate-400">
              <div className="text-slate-500 font-sans font-semibold">原错误流水事实快照:</div>
              <div>流水 #{correctionTarget.id} | {correctionTarget.name || correctionTarget.code} ({correctionTarget.code}) | {correctionTarget.direction.toUpperCase()}</div>
              <div>单价: ¥{correctionTarget.price.toFixed(2)} | 数量: {correctionTarget.quantity.toLocaleString()} 股 | 总额: ¥{correctionTarget.amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}</div>
            </div>

            <form onSubmit={handleSubmitCorrection} className="space-y-4 text-sm">
              <div>
                <label className="block text-sm text-slate-400 mb-1">纠错原因 / 修正说明 *</label>
                <input
                  type="text"
                  required
                  placeholder="例如：成交单价录入笔误 / 调整成交数量..."
                  value={correctionReason}
                  onChange={(e) => setCorrectionReason(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 text-sm"
                />
              </div>

              {/* 方向切换 */}
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setCorrectionForm(f => ({ ...f, direction: 'buy' }))}
                  className={`flex-1 py-1.5 text-center rounded-lg font-bold text-sm transition border ${
                    correctionForm.direction === 'buy'
                      ? 'bg-red-950 text-red-300 border-red-700'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`}
                >
                  买入 (Buy)
                </button>
                <button
                  type="button"
                  onClick={() => setCorrectionForm(f => ({ ...f, direction: 'sell' }))}
                  className={`flex-1 py-1.5 text-center rounded-lg font-bold text-sm transition border ${
                    correctionForm.direction === 'sell'
                      ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`}
                >
                  卖出 (Sell)
                </button>
              </div>

              {/* 股票代码与名称联动 */}
              <div className="grid grid-cols-2 gap-3 relative">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">股票代码 *</label>
                  <input
                    type="text"
                    required
                    placeholder="600519"
                    value={correctionForm.code}
                    onChange={(e) => handleCodeInputChange(e.target.value, 'correction')}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 font-mono text-sm"
                  />
                </div>
                <div className="relative">
                  <label className="block text-sm text-slate-400 mb-1">股票名称 (支持拼音/汉字联想)</label>
                  <input
                    type="text"
                    placeholder="例如 茅台 / gzmt"
                    value={correctionForm.name || ''}
                    onChange={(e) => handleNameInputChange(e.target.value, 'correction')}
                    onFocus={() => {
                      if (searchResults.length > 0 && searchTargetModal === 'correction') {
                        setShowSearchResults(true);
                      }
                    }}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 text-sm"
                  />
                  {showSearchResults && searchTargetModal === 'correction' && searchResults.length > 0 && (
                    <div className="absolute left-0 right-0 top-full mt-1 bg-slate-800 border border-slate-700 rounded-lg shadow-xl z-50 max-h-48 overflow-y-auto">
                      {searchResults.map((item) => (
                        <div
                          key={item.code}
                          onClick={() => handleSelectSecurity(item, 'correction')}
                          className="px-3 py-2 text-sm hover:bg-purple-900/40 cursor-pointer flex items-center justify-between border-b border-slate-700/50 last:border-b-0"
                        >
                          <span className="font-semibold text-slate-200">{item.name}</span>
                          <span className="text-slate-400 font-mono">{item.code} ({item.market})</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* 单价与数量 */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">修正单价 (元) *</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    required
                    value={correctionForm.price || ''}
                    onChange={(e) => setCorrectionForm(f => ({ ...f, price: parseFloat(e.target.value) || 0 }))}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 font-mono text-sm"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">修正数量 (股) * (整手 ≥ 100)</label>
                  <input
                    type="number"
                    step="100"
                    min="100"
                    required
                    value={correctionForm.quantity || ''}
                    onChange={(e) => setCorrectionForm(f => ({ ...f, quantity: parseInt(e.target.value, 10) || 0 }))}
                    className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 font-mono text-sm"
                  />
                  {correctionForm.quantity > 0 && (correctionForm.quantity < 100 || correctionForm.quantity % 100 !== 0) && (
                    <p className="text-sm text-rose-400 mt-1">数量必须 ≥ 100 且为 100 的整数倍</p>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">成交时间 (YYYY-MM-DD HH:MM:SS) *</label>
                <input
                  type="text"
                  required
                  value={correctionForm.trade_time}
                  onChange={(e) => setCorrectionForm(f => ({ ...f, trade_time: e.target.value }))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 font-mono text-sm"
                />
              </div>

              <div>
                <label className="block text-sm text-slate-400 mb-1">交易理由说明</label>
                <textarea
                  rows={2}
                  value={correctionForm.trade_reason || ''}
                  onChange={(e) => setCorrectionForm(f => ({ ...f, trade_reason: e.target.value }))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 text-sm"
                />
              </div>

              <div className="bg-slate-950 p-2.5 rounded border border-white/10 text-sm font-mono flex justify-between text-slate-400">
                <span>修正后成交总额:</span>
                <span className="font-bold text-amber-300">
                  ¥{(correctionForm.price * correctionForm.quantity).toLocaleString('zh-CN', { minimumFractionDigits: 2 })}
                </span>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCorrectionModalOpen(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 text-sm font-medium"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 bg-amber-600 hover:bg-amber-500 text-slate-950 rounded-lg text-sm font-bold transition shadow-sm disabled:opacity-50"
                >
                  {isSubmitting ? '正在纠错重算...' : '确认执行纠错'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 弹窗 3: 复盘反思抽屉 (Trade Note Drawer) */}
      {isNoteDrawerOpen && selectedRecordForNote && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50 animate-in fade-in">
          <div className="bg-slate-900 border border-white/10 rounded-xl max-w-xl w-full p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <h3 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <BookOpen className="w-5 h-5 text-purple-400" />
                交易认知复盘反思笔记
              </h3>
              <button onClick={() => setIsNoteDrawerOpen(false)} className="text-slate-400 hover:text-slate-200">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="bg-slate-950 p-2.5 rounded border border-white/10 text-sm font-mono text-slate-400">
              流水 #{selectedRecordForNote.id} | {selectedRecordForNote.name || selectedRecordForNote.code} ({selectedRecordForNote.direction.toUpperCase()}) | {selectedRecordForNote.trade_time}
            </div>

            <form onSubmit={handleSubmitNote} className="space-y-3 text-sm">
              <div>
                <label className="block text-slate-400 mb-1">交易时心理状态 (Mental State)</label>
                <input
                  type="text"
                  placeholder="例如：冷静执行预案 / 恐慌急躁 / 侥幸跟风..."
                  value={noteForm.mental_state}
                  onChange={(e) => setNoteForm(f => ({ ...f, mental_state: e.target.value }))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 text-sm"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">决策逻辑 (Decision Logic)</label>
                <textarea
                  rows={2}
                  placeholder="例如：5日均线企稳回踩确认，板块放量共振..."
                  value={noteForm.decision_logic}
                  onChange={(e) => setNoteForm(f => ({ ...f, decision_logic: e.target.value }))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 text-sm"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-slate-400">事后反思 (Reflection)</label>
                  <label className="flex items-center gap-1.5 cursor-pointer text-purple-400 text-xs">
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
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 text-sm"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1">沉淀经验教训 (Lessons)</label>
                <textarea
                  rows={2}
                  placeholder="例如：跌破止损线决不心存侥幸，果断出局..."
                  value={noteForm.lessons}
                  onChange={(e) => setNoteForm(f => ({ ...f, lessons: e.target.value }))}
                  className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-1.5 text-slate-100 text-amber-300 text-sm"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsNoteDrawerOpen(false)}
                  className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 text-sm font-medium"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-5 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-sm font-bold transition shadow-lg shadow-purple-900/30 disabled:opacity-50"
                >
                  {isSubmitting ? '正在保存...' : '保存反思笔记'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 弹窗 4: 单笔认知诊断抽屉 (Cognitive Diagnosis Drawer) */}
      {isDiagnosisDrawerOpen && selectedRecordForDiag && (
        <div className="fixed inset-0 bg-black/75 flex items-center justify-center p-4 z-50 animate-in fade-in">
          <div className="bg-slate-900 border border-indigo-900/60 rounded-xl max-w-2xl w-full p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            {/* 标题栏 */}
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <div className="flex items-center gap-2">
                <Brain className="w-5 h-5 text-indigo-400" />
                <h3 className="text-lg font-bold text-slate-100">
                  单笔交易认知诊断与人机核准
                </h3>
              </div>
              <button onClick={() => setIsDiagnosisDrawerOpen(false)} className="text-slate-400 hover:text-slate-200">
                <X className="w-5 h-5" />
              </button>
            </div>

            {diagLoading ? (
              <div className="py-12 text-center text-slate-400 flex flex-col items-center justify-center gap-3">
                <RefreshCw className="w-8 h-8 animate-spin text-indigo-400" />
                <p className="text-base">正在对撞成交当日客观环境状态 (D1~D6) 并生成认知诊断...</p>
              </div>
            ) : diagnosisData ? (
              <div className="space-y-4 text-sm">
                {/* 1. 物理层 A: 事实层 (Ground Truth Layer) */}
                <div className="rounded-lg bg-slate-950 p-3.5 border border-slate-800 space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-300 flex items-center gap-1.5 uppercase tracking-wider text-xs">
                      <span className="w-2 h-2 rounded-full bg-slate-400"></span>
                      【事实层】成交与环境对撞快照 (Ground Truth)
                    </span>
                    <span className="font-mono text-slate-500 text-xs">流水 #{selectedRecordForDiag.id}</span>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono text-slate-300 pt-1">
                    <div className="bg-slate-900/80 p-2 rounded">
                      <div className="text-xs text-slate-500">标的资产</div>
                      <div className="font-bold text-slate-200">{selectedRecordForDiag.name || selectedRecordForDiag.code} ({selectedRecordForDiag.code})</div>
                    </div>
                    <div className="bg-slate-900/80 p-2 rounded">
                      <div className="text-xs text-slate-500">方向 / 单价</div>
                      <div className={selectedRecordForDiag.direction === 'buy' ? 'text-red-300 font-bold' : 'text-emerald-300 font-bold'}>
                        {selectedRecordForDiag.direction.toUpperCase()} @ ¥{selectedRecordForDiag.price.toFixed(2)}
                      </div>
                    </div>
                    <div className="bg-slate-900/80 p-2 rounded">
                      <div className="text-xs text-slate-500">股数 / 总额</div>
                      <div>{selectedRecordForDiag.quantity} 股 / ¥{selectedRecordForDiag.amount.toFixed(2)}</div>
                    </div>
                    <div className="bg-slate-900/80 p-2 rounded">
                      <div className="text-xs text-slate-500">成交时间</div>
                      <div>{selectedRecordForDiag.trade_time}</div>
                    </div>
                  </div>

                  {/* 对撞的环境测量快照 */}
                  <div className="bg-slate-900/60 p-2.5 rounded border border-white/10 mt-2">
                    <div className="text-xs text-slate-400 font-medium mb-1">
                      当日市场客观测度 ({formatDateWithWeekday(diagnosisData.market_d1_d6_snapshot.date || diagnosisData.date)}):
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-cyan-300 font-medium text-xs border border-slate-700">
                        状态: {diagnosisData.market_d1_d6_snapshot.state_label || '未分类 / 缺失'}
                      </span>
                      {diagnosisData.market_d1_d6_snapshot.composite_score != null && (
                        <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-xs border border-slate-700">
                          综合测度: {diagnosisData.market_d1_d6_snapshot.composite_score.toFixed(1)}
                        </span>
                      )}
                      {diagnosisData.market_d1_d6_snapshot.indicators && diagnosisData.market_d1_d6_snapshot.indicators.length > 0 && (
                        <span className="text-xs text-slate-400">
                          (D1~D6 已加载 {diagnosisData.market_d1_d6_snapshot.indicators.length} 项度量)
                        </span>
                      )}
                    </div>
                    {diagnosisData.market_d1_d6_snapshot.note && (
                      <p className="text-xs text-slate-500 mt-1 italic">
                        {diagnosisData.market_d1_d6_snapshot.note}
                      </p>
                    )}
                  </div>
                </div>

                {/* 2. 物理层 B: AI 解释层与人机审定状态 (Cognitive Interpretation Layer) */}
                <div className="rounded-lg bg-indigo-950/20 p-3.5 border border-indigo-900/50 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-indigo-300 flex items-center gap-1.5 uppercase tracking-wider text-xs">
                      <Brain className="w-3.5 h-3.5" />
                      【认知解释层】AI 诊断分析 (Cognitive Interpretation)
                    </span>
                    {/* 治理胶囊徽章 */}
                    {diagnosisData.human_status === 'UNCONFIRMED' && (
                      <span className="px-2 py-0.5 rounded-full bg-amber-950/80 text-amber-300 border border-amber-800/80 font-semibold text-xs flex items-center gap-1">
                        <AlertCircle className="w-3 text-amber-400" />
                        [AI 诊断 / 待人工确认]
                      </span>
                    )}
                    {diagnosisData.human_status === 'CONFIRMED' && (
                      <span className="px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-300 border border-emerald-800/80 font-semibold text-xs flex items-center gap-1">
                        <CheckCheck className="w-3.5 h-3.5 text-emerald-400" />
                        [已人工确认采纳]
                      </span>
                    )}
                    {diagnosisData.human_status === 'MODIFIED' && (
                      <span className="px-2 py-0.5 rounded-full bg-cyan-950/80 text-cyan-300 border border-cyan-800/80 font-semibold text-xs flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400" />
                        [人工已修正]
                      </span>
                    )}
                  </div>

                  <div className="grid grid-cols-2 gap-2">
                    <div className="bg-slate-900/70 p-2.5 rounded border border-white/10">
                      <div className="text-xs text-slate-500 font-medium">环境匹配类型 (Environment Match)</div>
                      <div className="text-slate-200 font-bold mt-0.5 text-sm">
                        {diagnosisData.env_match_type === 'HIGH_MATCH' && '🟢 顺应主线环境 (High Match)'}
                        {diagnosisData.env_match_type === 'LOW_MATCH' && '🔴 逆势/弱匹配环境 (Low Match)'}
                        {diagnosisData.env_match_type === 'EMO_DRIVEN' && '⚠️ 情绪驱动/盲目上头 (Emo Driven)'}
                        {diagnosisData.env_match_type === 'AMBIGUOUS' && '⚪ 震荡模糊/中性 (Ambiguous)'}
                        {!['HIGH_MATCH', 'LOW_MATCH', 'EMO_DRIVEN', 'AMBIGUOUS'].includes(diagnosisData.env_match_type) && diagnosisData.env_match_type}
                      </div>
                    </div>
                    <div className="bg-slate-900/70 p-2.5 rounded border border-white/10">
                      <div className="text-xs text-slate-500 font-medium">逻辑兑现度 (Logic Realization)</div>
                      <div className="text-slate-200 font-bold mt-0.5 text-sm">
                        {diagnosisData.logic_realization === 'REALIZED' && '✅ 逻辑按预期兑现 (Realized)'}
                        {diagnosisData.logic_realization === 'UNREALIZED' && '❌ 逻辑未兑现/逻辑落空 (Unrealized)'}
                        {diagnosisData.logic_realization === 'ACCIDENTAL' && '⚡ 意外扰动/运气盈亏 (Accidental)'}
                        {!['REALIZED', 'UNREALIZED', 'ACCIDENTAL'].includes(diagnosisData.logic_realization) && diagnosisData.logic_realization}
                      </div>
                    </div>
                  </div>

                  <div className="bg-slate-900/70 p-2.5 rounded border border-white/10 space-y-1">
                    <div className="text-xs text-indigo-300 font-semibold">认知偏离与根因剖析 (Cognitive Gap Analysis)</div>
                    <div className="text-slate-300 leading-relaxed whitespace-pre-line text-sm">
                      {diagnosisData.cognitive_gap_analysis}
                    </div>
                  </div>

                  {diagnosisData.human_comment && (
                    <div className="bg-cyan-950/20 p-2.5 rounded border border-cyan-900/50 space-y-1">
                      <div className="text-xs text-cyan-400 font-semibold">既有人工审定批注 (Human Comment)</div>
                      <div className="text-cyan-200/90 leading-relaxed text-sm">
                        {diagnosisData.human_comment}
                      </div>
                    </div>
                  )}
                </div>

                {/* 3. 人机审定与主权回环操作栏 (HITL Review Actions) */}
                <div className="rounded-lg bg-slate-950 p-3.5 border border-white/10 space-y-2.5">
                  <div className="text-sm font-bold text-slate-300 flex items-center justify-between">
                    <span>人工审定与修正 (Human-In-The-Loop Confirmation)</span>
                    <span className="text-xs text-amber-400 font-normal">
                      * 未经确认的诊断绝对不计入周报与量化统计
                    </span>
                  </div>

                  <textarea
                    rows={2}
                    value={diagComment}
                    onChange={(e) => setDiagComment(e.target.value)}
                    placeholder="输入审定意见、同意/修正理由，或补充心理盲区反思..."
                    className="w-full bg-slate-900 border border-slate-700 rounded p-2 text-slate-100 text-sm focus:outline-none focus:border-indigo-500"
                  />

                  <div className="flex items-center justify-end gap-2 pt-1">
                    <button
                      type="button"
                      disabled={diagSubmitting}
                      onClick={() => handleConfirmDiagnosis('MODIFIED')}
                      className="px-3.5 py-1.5 rounded bg-cyan-900/40 hover:bg-cyan-900/70 text-cyan-300 border border-cyan-800/80 font-medium text-sm transition disabled:opacity-50"
                      title="保留诊断并附加人工修正批注"
                    >
                      {diagSubmitting ? '提交中...' : '人工修正并入库 (Modify)'}
                    </button>
                    <button
                      type="button"
                      disabled={diagSubmitting}
                      onClick={() => handleConfirmDiagnosis('CONFIRMED')}
                      className="px-4 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white font-bold text-sm transition shadow-sm disabled:opacity-50 flex items-center gap-1.5"
                      title="采纳AI诊断结论并标记为人工确认"
                    >
                      <CheckCheck className="w-3.5 h-3.5" />
                      {diagSubmitting ? '确认中...' : '确认采纳 (Confirm)'}
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="py-8 text-center text-slate-400 text-sm">
                暂未获取到诊断数据。
              </div>
            )}
          </div>
        </div>
      )}

      {/* 弹窗 5: 周度认知复盘抽屉 (Weekly Audit Drawer) */}
      {isWeeklyAuditOpen && (
        <div className="fixed inset-0 bg-black/75 flex items-center justify-center p-4 z-50 animate-in fade-in">
          <div className="bg-slate-900 border border-indigo-900/60 rounded-xl max-w-3xl w-full p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            {/* 标题栏与周期切换 */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-white/10 pb-3">
              <div className="flex items-center gap-2">
                <BarChart2 className="w-5 h-5 text-indigo-400" />
                <h3 className="text-lg font-bold text-slate-100">
                  周度客观认知复盘看板
                </h3>
                <span className="text-sm px-2 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800 font-mono">
                  {weeklyAuditData?.week_label || '当前周期'}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <div className="flex items-center rounded border border-slate-700 bg-slate-800 text-sm">
                  <button
                    onClick={() => handleOpenWeeklyAudit(0)}
                    className={`px-2.5 py-1 transition ${weeklyOffset === 0 ? 'bg-indigo-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
                  >
                    本周
                  </button>
                  <button
                    onClick={() => handleOpenWeeklyAudit(1)}
                    className={`px-2.5 py-1 transition ${weeklyOffset === 1 ? 'bg-indigo-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
                  >
                    上周
                  </button>
                  <button
                    onClick={() => handleOpenWeeklyAudit(2)}
                    className={`px-2.5 py-1 transition ${weeklyOffset === 2 ? 'bg-indigo-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
                  >
                    上上周
                  </button>
                </div>
                <button onClick={() => setIsWeeklyAuditOpen(false)} className="text-slate-400 hover:text-slate-200">
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* 未确认隔离铁律提示 */}
            <div className="rounded-lg bg-indigo-950/30 border border-indigo-800/60 p-3 text-sm text-indigo-200 flex items-start gap-2">
              <ShieldAlert className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
              <div>
                <strong>治理铁律生效中：</strong> 仅计入经由人工审定（CONFIRMED / MODIFIED）的真实样本。未确认样本已被严格物理隔离；当有效样本为空时，指标严格留白渲染为 <code className="text-amber-300">--</code>，绝无零填充伪造数据。
              </div>
            </div>

            {weeklyAuditLoading ? (
              <div className="py-12 text-center text-slate-400 flex flex-col items-center justify-center gap-3">
                <RefreshCw className="w-8 h-8 animate-spin text-indigo-400" />
                <p className="text-base">正在聚合核算周度三维客观认知度量...</p>
              </div>
            ) : weeklyAuditData ? (
              <div className="space-y-4">
                {/* 1. 三维核心客观度量矩阵 */}
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="bg-slate-950/80 p-4 rounded-xl border border-white/10">
                    <div className="text-sm text-slate-400 font-medium">环境匹配度 (EMD)</div>
                    <div className="text-2xl font-bold font-mono text-cyan-400 mt-1">
                      {weeklyAuditData.metrics.env_match_degree != null 
                        ? `${weeklyAuditData.metrics.env_match_degree.toFixed(1)}%` 
                        : '--'}
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      顺应主流环境交易笔数占比
                    </div>
                  </div>

                  <div className="bg-slate-950/80 p-4 rounded-xl border border-white/10">
                    <div className="text-sm text-slate-400 font-medium">逻辑兑现度 (LRD)</div>
                    <div className="text-2xl font-bold font-mono text-indigo-400 mt-1">
                      {weeklyAuditData.metrics.logic_realization_degree != null 
                        ? `${weeklyAuditData.metrics.logic_realization_degree.toFixed(1)}%` 
                        : '--'}
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      建仓依据真实兑现比例
                    </div>
                  </div>

                  <div className="bg-slate-950/80 p-4 rounded-xl border border-white/10">
                    <div className="text-sm text-slate-400 font-medium">结果偏离度 (ODD)</div>
                    <div className="text-2xl font-bold font-mono text-amber-400 mt-1">
                      {weeklyAuditData.metrics.outcome_deviation_degree != null 
                        ? `${weeklyAuditData.metrics.outcome_deviation_degree.toFixed(1)}%` 
                        : '--'}
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      逻辑兑现与实际盈亏的偏差度
                    </div>
                  </div>
                </div>

                {/* 2. 样本统计分布 */}
                <div className="bg-slate-950/60 p-4 rounded-xl border border-white/10 space-y-3">
                  <div className="flex items-center justify-between text-sm text-slate-300 font-medium">
                    <span>交易诊断样本治理画像</span>
                    <div className="flex items-center gap-3 font-mono text-xs">
                      <span>周总交易: <strong className="text-slate-100">{weeklyAuditData.total_trades}</strong> 笔</span>
                      <span>已确认样本: <strong className="text-emerald-400">{weeklyAuditData.confirmed_samples_count}</strong> 笔</span>
                      <span>隔离未确认: <strong className="text-amber-400">{weeklyAuditData.total_trades - weeklyAuditData.confirmed_samples_count}</strong> 笔</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 text-sm">
                    <div className="bg-slate-900 p-2.5 rounded border border-white/10">
                      <div className="text-xs text-slate-500">高匹配交易 (High Match)</div>
                      <div className="text-lg font-bold text-emerald-400 font-mono mt-0.5">
                        {weeklyAuditData.trade_sample_summary.high_match} 笔
                      </div>
                    </div>
                    <div className="bg-slate-900 p-2.5 rounded border border-white/10">
                      <div className="text-xs text-slate-500">低匹配交易 (Low Match)</div>
                      <div className="text-lg font-bold text-rose-400 font-mono mt-0.5">
                        {weeklyAuditData.trade_sample_summary.low_match} 笔
                      </div>
                    </div>
                    <div className="bg-slate-900 p-2.5 rounded border border-white/10">
                      <div className="text-xs text-slate-500">情绪驱动 (Emo Driven)</div>
                      <div className="text-lg font-bold text-amber-400 font-mono mt-0.5">
                        {weeklyAuditData.trade_sample_summary.emo_driven} 笔
                      </div>
                    </div>
                    <div className="bg-slate-900 p-2.5 rounded border border-white/10">
                      <div className="text-xs text-slate-500">模糊/中性 (Ambiguous)</div>
                      <div className="text-lg font-bold text-slate-400 font-mono mt-0.5">
                        {weeklyAuditData.trade_sample_summary.ambiguous} 笔
                      </div>
                    </div>
                  </div>
                </div>

                {/* 3. 实证观察与认知洞察 */}
                {weeklyAuditData.empirical_observations && weeklyAuditData.empirical_observations.length > 0 && (
                  <div className="bg-slate-950/60 p-4 rounded-xl border border-white/10 space-y-2 text-sm">
                    <div className="font-medium text-slate-300">实证观察与周期认知反思洞察</div>
                    <ul className="space-y-1.5 text-slate-400">
                      {weeklyAuditData.empirical_observations.map((obs, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <span className="text-indigo-400 font-mono">•</span>
                          <span>{obs}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : null}
          </div>
        </div>
      )}
    </div>
  );
}
