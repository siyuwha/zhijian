'use client';

import React, { useState, useEffect } from 'react';
import { CanonicalMarketSnapshot, TacticalBriefingReport } from '@/types/canonical';
import { canonicalAPI } from '@/lib/api';
import { MarketStateBanner } from './MarketStateBanner';
import { LadderTreeCard } from './LadderTreeCard';
import { MainlineMatrixCard } from './MainlineMatrixCard';
import { RiskAndFalsificationCard } from './RiskAndFalsificationCard';
import { AuditDrawer } from './AuditDrawer';
import { TacticalBriefingModal } from './TacticalBriefingModal';
import { Calendar, Shield, RefreshCw, AlertCircle, Compass, FileText } from 'lucide-react';

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

  useEffect(() => {
    fetchSnapshot(selectedDate);
    fetchBriefing(selectedDate);
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

            {/* 第三层：亏钱效应、监管风险与次日证伪闭环 (~30% 高度) */}
            <section className="shrink-0">
              <RiskAndFalsificationCard
                sentiment={snapshot.truth.sentiment_bounds}
                anomalies={snapshot.truth.regulatory_anomalies}
                primaryMainline={snapshot.cognition.mainlines[0]}
              />
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
      />
    </div>
  );
};
