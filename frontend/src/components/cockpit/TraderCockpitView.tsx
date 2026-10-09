'use client';

import React, { useState, useEffect } from 'react';
import {
  CanonicalMarketSnapshot,
  TacticalBriefingReport,
  BiddingFalsificationVerdict,
  IntradayDriftVerdict,
} from '@/types/canonical';
import { canonicalAPI } from '@/lib/api';
import { MarketStateBanner } from './MarketStateBanner';
import { LadderTreeCard } from './LadderTreeCard';
import { MainlineMatrixCard } from './MainlineMatrixCard';
import { RiskAndFalsificationCard } from './RiskAndFalsificationCard';
import { BiddingFalsificationCard } from './BiddingFalsificationCard';
import { BiddingFalsificationModal } from './BiddingFalsificationModal';
import { IntradayDriftCard } from './IntradayDriftCard';
import { AuditDrawer } from './AuditDrawer';
import { TacticalBriefingModal } from './TacticalBriefingModal';
import {
  Calendar,
  Shield,
  RefreshCw,
  AlertCircle,
  Compass,
  FileText,
  Activity,
} from 'lucide-react';

interface TraderCockpitViewProps {
  initialDate?: string;
}

export const TraderCockpitView: React.FC<TraderCockpitViewProps> = ({
  initialDate = '2026-10-08',
}) => {
  const [selectedDate, setSelectedDate] = useState<string>(initialDate);
  const [snapshot, setSnapshot] = useState<CanonicalMarketSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isAuditOpen, setIsAuditOpen] = useState<boolean>(false);
  const [briefing, setBriefing] = useState<TacticalBriefingReport | null>(null);
  const [isBriefingOpen, setIsBriefingOpen] = useState<boolean>(false);
  const [isBriefingLoading, setIsBriefingLoading] = useState<boolean>(false);

  // Phase 2E: 09:25 集合竞价对账单状态
  const [biddingVerdict, setBiddingVerdict] = useState<BiddingFalsificationVerdict | null>(null);
  const [isBiddingLoading, setIsBiddingLoading] = useState<boolean>(false);
  const [biddingErrorMsg, setBiddingErrorMsg] = useState<string | null>(null);
  const [isBiddingModalOpen, setIsBiddingModalOpen] = useState<boolean>(false);

  // Phase 3A: 盘中 4 阶段动态跟踪与认知偏离状态
  const [intradayVerdict, setIntradayVerdict] = useState<IntradayDriftVerdict | null>(null);
  const [isIntradayLoading, setIsIntradayLoading] = useState<boolean>(false);
  const [intradayErrorMsg, setIntradayErrorMsg] = useState<string | null>(null);

  const [activeBottomTab, setActiveBottomTab] = useState<
    'RISK_FALSIFICATION' | 'BIDDING_AUCTION' | 'INTRADAY_DRIFT'
  >('RISK_FALSIFICATION');

  const fetchSnapshot = async (date: string) => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const data = await canonicalAPI.getCanonicalMarketSnapshot(date);
      setSnapshot(data);
    } catch (err: any) {
      setErrorMsg(err.message || '获取市场真相与认知快照失败');
    } finally {
      setIsLoading(false);
    }
  };

  const fetchBriefing = async (date: string) => {
    setIsBriefingLoading(true);
    try {
      const data = await canonicalAPI.getTacticalBriefing(date);
      setBriefing(data);
    } catch (err: any) {
      console.error('Failed to fetch tactical briefing:', err);
    } finally {
      setIsBriefingLoading(false);
    }
  };

  const fetchBiddingVerdict = async (date: string) => {
    setIsBiddingLoading(true);
    setBiddingErrorMsg(null);
    try {
      const data = await canonicalAPI.getAuctionFalsification(date);
      setBiddingVerdict(data);
    } catch (err: any) {
      console.warn('Failed to fetch bidding falsification verdict:', err);
      setBiddingErrorMsg(err.message || '获取 09:25 竞价对账单失败');
    } finally {
      setIsBiddingLoading(false);
    }
  };

  const fetchIntradayVerdict = async (date: string) => {
    setIsIntradayLoading(true);
    setIntradayErrorMsg(null);
    try {
      const data = await canonicalAPI.getIntradayDrift(date);
      setIntradayVerdict(data);
    } catch (err: any) {
      console.warn('Failed to fetch intraday drift verdict:', err);
      setIntradayErrorMsg(err.message || '获取盘中认知偏离判定失败');
    } finally {
      setIsIntradayLoading(false);
    }
  };

  useEffect(() => {
    fetchSnapshot(selectedDate);
    fetchBriefing(selectedDate);
    fetchBiddingVerdict(selectedDate);
    fetchIntradayVerdict(selectedDate);
  }, [selectedDate]);

  return (
    <div className="h-screen w-full bg-slate-950 text-slate-100 flex flex-col overflow-hidden select-none">
      {/* 顶部工具栏 (h-14) */}
      <header className="h-14 shrink-0 bg-slate-900 border-b border-slate-800 px-6 flex items-center justify-between z-10">
        <div className="flex items-center gap-3">
          <div className="p-1.5 rounded-lg bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
            <Compass className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-black tracking-tight text-slate-100 flex items-center gap-2">
              交易员驾驶舱 · Trader Cockpit
              <span className="text-[10px] font-mono font-normal text-amber-400 bg-amber-950/60 border border-amber-800/60 px-1.5 py-0.5 rounded">
                PROVISIONAL 实验性认知绑定
              </span>
            </h1>
            <p className="text-[10px] text-slate-400">
              三层倒金字塔架构 · L0~L2 物理事实严密呈现 · L3 认知假说推断仅供交叉核验
            </p>
          </div>
        </div>

        {/* 顶部右侧控制项 */}
        <div className="flex items-center gap-3">
          {/* 日期选择器 */}
          <div className="flex items-center gap-2 bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1 text-xs">
            <Calendar className="w-3.5 h-3.5 text-slate-400" />
            <input
              type="date"
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="bg-transparent border-none text-xs font-mono text-slate-200 focus:outline-none"
            />
          </div>

          <button
            onClick={() => fetchSnapshot(selectedDate)}
            className="p-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-750 text-slate-300 hover:text-slate-100 transition"
            title="刷新数据"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </button>

          {/* 09:25 集合竞价对账按钮 */}
          <button
            onClick={() => setIsBiddingModalOpen(true)}
            className="flex items-center gap-1.5 bg-slate-900/90 hover:bg-slate-800 border border-slate-750 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-200 transition"
            title="查看 09:25 集合竞价自动对账单"
          >
            <Compass className="w-3.5 h-3.5 text-indigo-400" />
            <span>09:25 竞价对账</span>
            {biddingVerdict && (
              <span
                className={`text-[10px] font-mono font-bold px-1.5 py-0.2 rounded border ${
                  biddingVerdict.overall_verdict === 'CONFIRMED'
                    ? 'bg-emerald-950/80 text-emerald-300 border-emerald-800'
                    : biddingVerdict.overall_verdict === 'DIVERGENT'
                    ? 'bg-amber-950/80 text-amber-300 border-amber-800'
                    : biddingVerdict.overall_verdict === 'FALSIFIED'
                    ? 'bg-rose-950/80 text-rose-300 border-rose-800'
                    : 'bg-slate-800 text-slate-400 border-slate-700'
                }`}
              >
                {biddingVerdict.overall_verdict}
              </span>
            )}
          </button>

          {/* 操盘内参战报按钮 */}
          <button
            onClick={() => setIsBriefingOpen(true)}
            className="flex items-center gap-1.5 bg-indigo-950/70 hover:bg-indigo-900/80 border border-indigo-700/60 px-3 py-1.5 rounded-lg text-xs font-semibold text-indigo-200 transition"
          >
            <FileText className="w-3.5 h-3.5 text-indigo-400" />
            <span>操盘内参 (Briefing)</span>
          </button>

          {/* 审计抽屉按钮 */}
          <button
            onClick={() => setIsAuditOpen(true)}
            className="flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 px-3 py-1.5 rounded-lg text-xs font-medium text-slate-200 transition"
          >
            <Shield className="w-3.5 h-3.5 text-indigo-400" />
            <span>审计抽屉 (Audit)</span>
          </button>
        </div>
      </header>

      {/* 主工作区 (100vh 倒金字塔布局) */}
      <main className="flex-1 min-h-0 p-4 flex flex-col gap-3 overflow-hidden">
        {isLoading ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-slate-400">
            <RefreshCw className="w-8 h-8 animate-spin text-indigo-500" />
            <p className="text-sm font-mono tracking-wide">
              正在加载并验证 {selectedDate} Canonical Market Snapshot...
            </p>
          </div>
        ) : errorMsg ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3">
            <div className="p-3 rounded-full bg-rose-950/60 border border-rose-800 text-rose-400">
              <AlertCircle className="w-8 h-8" />
            </div>
            <p className="text-sm text-slate-300 font-medium">{errorMsg}</p>
            <button
              onClick={() => fetchSnapshot(selectedDate)}
              className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-xs font-semibold rounded-lg transition"
            >
              重新加载
            </button>
          </div>
        ) : snapshot ? (
          <div className="flex-1 min-h-0 flex flex-col gap-3 overflow-hidden">
            {/* 第一层：大盘宏观事实与状态一句话 (~25% 高度) */}
            <section className="shrink-0">
              <MarketStateBanner
                summary={snapshot.cognition.market_state_summary}
                calibration={snapshot.cognition.market_state_calibration}
                turnover={snapshot.truth.turnover}
                indices={snapshot.truth.indices}
                breadthStatus={snapshot.truth.cross_section_breadth_status}
                degradationDetail={snapshot.truth.cross_section_breadth_detail}
                provisionalDisclaimer={snapshot.cognition.provisional_disclaimer}
                onOpenBriefing={() => setIsBriefingOpen(true)}
              />
            </section>

            {/* 第二层：主线与连板微观结构核心梯队 (~45% 高度) */}
            <section className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-12 gap-3 overflow-hidden">
              {/* 空间标杆与天梯树 (5 cols) */}
              <div className="lg:col-span-5 h-full min-h-0">
                <LadderTreeCard
                  ladderTree={snapshot.truth.ladder_tree}
                  maxHeight={snapshot.truth.sentiment_bounds.max_ladder_height}
                />
              </div>

              {/* 主线候选矩阵与正反方证据 (7 cols) */}
              <div className="lg:col-span-7 h-full min-h-0">
                <MainlineMatrixCard
                  mainlines={snapshot.cognition.mainlines}
                  lineage={snapshot.cognition.lineage_accounting}
                  onOpenAudit={() => setIsAuditOpen(true)}
                />
              </div>
            </section>

            {/* 第三层：亏钱效应、监管风险与 09:25 次日波普尔证伪闭环 (~30% 高度) */}
            <section className="shrink-0 flex flex-col gap-2">
              <div className="flex items-center justify-between px-1">
                <div className="flex items-center gap-1 bg-slate-900/90 border border-slate-800 rounded-lg p-0.5 text-xs font-semibold">
                  <button
                    onClick={() => setActiveBottomTab('RISK_FALSIFICATION')}
                    className={`px-3 py-1 rounded-md transition ${
                      activeBottomTab === 'RISK_FALSIFICATION'
                        ? 'bg-slate-800 text-indigo-300 shadow-sm'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    问 5~7 · 情绪极值与主线证伪 (收盘复盘)
                  </button>
                  <button
                    onClick={() => setActiveBottomTab('BIDDING_AUCTION')}
                    className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition ${
                      activeBottomTab === 'BIDDING_AUCTION'
                        ? 'bg-slate-800 text-indigo-300 shadow-sm'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <span>09:25 集合竞价波普尔对账 (次晨开盘)</span>
                    {biddingVerdict && (
                      <span
                        className={`text-[10px] font-mono px-1.5 py-0.2 rounded font-bold border ${
                          biddingVerdict.overall_verdict === 'CONFIRMED'
                            ? 'bg-emerald-950 text-emerald-300 border-emerald-800'
                            : biddingVerdict.overall_verdict === 'DIVERGENT'
                            ? 'bg-amber-950 text-amber-300 border-amber-800'
                            : biddingVerdict.overall_verdict === 'FALSIFIED'
                            ? 'bg-rose-950 text-rose-300 border-rose-800'
                            : 'bg-slate-800 text-slate-300 border-slate-700'
                        }`}
                      >
                        {biddingVerdict.overall_verdict}
                      </span>
                    )}
                  </button>
                  <button
                    onClick={() => setActiveBottomTab('INTRADAY_DRIFT')}
                    className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition ${
                      activeBottomTab === 'INTRADAY_DRIFT'
                        ? 'bg-slate-800 text-cyan-300 shadow-sm'
                        : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <span>盘中 4 阶段偏离告警 (动态追踪)</span>
                    {intradayVerdict && (
                      <span
                        className={`text-[10px] font-mono px-1.5 py-0.2 rounded font-bold border ${
                          intradayVerdict.overall_drift_state === 'NORMAL'
                            ? 'bg-emerald-950 text-emerald-300 border-emerald-800'
                            : intradayVerdict.overall_drift_state === 'DRIFT_WARNING'
                            ? 'bg-amber-950 text-amber-300 border-amber-800'
                            : intradayVerdict.overall_drift_state === 'CRITICAL_BREACH'
                            ? 'bg-rose-950 text-rose-300 border-rose-800'
                            : 'bg-slate-800 text-slate-300 border-slate-700'
                        }`}
                      >
                        {intradayVerdict.overall_drift_state}
                      </span>
                    )}
                  </button>
                </div>

                {activeBottomTab === 'BIDDING_AUCTION' && (
                  <button
                    onClick={() => setIsBiddingModalOpen(true)}
                    className="text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-mono transition"
                  >
                    <span>全屏详情</span>
                    <Compass className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              {activeBottomTab === 'RISK_FALSIFICATION' ? (
                <RiskAndFalsificationCard
                  sentiment={snapshot.truth.sentiment_bounds}
                  anomalies={snapshot.truth.regulatory_anomalies}
                  primaryMainline={snapshot.cognition.mainlines[0]}
                />
              ) : activeBottomTab === 'BIDDING_AUCTION' ? (
                <BiddingFalsificationCard
                  verdict={biddingVerdict}
                  isLoading={isBiddingLoading}
                  errorMsg={biddingErrorMsg}
                  onRefresh={() => fetchBiddingVerdict(selectedDate)}
                  onOpenDetailsModal={() => setIsBiddingModalOpen(true)}
                  compact={true}
                />
              ) : (
                <IntradayDriftCard
                  verdict={intradayVerdict}
                  isLoading={isIntradayLoading}
                  errorMsg={intradayErrorMsg}
                  onRefresh={() => fetchIntradayVerdict(selectedDate)}
                  compact={true}
                />
              )}
            </section>
          </div>
        ) : null}
      </main>

      {/* 审计透明抽屉 */}
      {snapshot && (
        <AuditDrawer
          isOpen={isAuditOpen}
          onClose={() => setIsAuditOpen(false)}
          snapshot={snapshot}
        />
      )}

      {/* 操盘手内参实战战报弹窗 */}
      <TacticalBriefingModal
        isOpen={isBriefingOpen}
        onClose={() => setIsBriefingOpen(false)}
        briefing={briefing}
        isLoading={isBriefingLoading}
        onOpenBiddingFalsification={() => setIsBiddingModalOpen(true)}
      />

      {/* 09:25 集合竞价对账单弹窗 */}
      <BiddingFalsificationModal
        isOpen={isBiddingModalOpen}
        onClose={() => setIsBiddingModalOpen(false)}
        verdict={biddingVerdict}
        isLoading={isBiddingLoading}
        errorMsg={biddingErrorMsg}
        onRefresh={() => fetchBiddingVerdict(selectedDate)}
      />
    </div>
  );
};
