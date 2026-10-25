'use client';

import React from 'react';
import { TacticalBriefingReport } from '@/types/canonical';
import {
  X,
  ShieldCheck,
  AlertTriangle,
  Compass,
  Swords,
  AlertOctagon,
  Eye,
  FileCheck2,
  RefreshCw,
  Cpu,
} from 'lucide-react';

interface TacticalBriefingModalProps {
  isOpen: boolean;
  onClose: () => void;
  briefing: TacticalBriefingReport | null;
  isLoading?: boolean;
  onOpenBiddingFalsification?: () => void;
}

export const TacticalBriefingModal: React.FC<TacticalBriefingModalProps> = ({
  isOpen,
  onClose,
  briefing,
  isLoading = false,
  onOpenBiddingFalsification,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-150">
      <div
        className="w-full max-w-4xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden select-none"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 顶部标题栏 */}
        <header className="px-6 py-4 bg-slate-850 border-b border-slate-800 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-indigo-600/20 text-indigo-400 border border-indigo-500/30">
              <Compass className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-black tracking-tight text-slate-100">
                  AI 战术内参 · 全天定调与次日部署
                </h2>
                {briefing && (
                  <>
                    <span className="text-sm font-bold px-2 py-0.5 rounded-full bg-purple-950 text-purple-300 border border-purple-700/60 font-mono">
                      {briefing.trade_date}
                    </span>
                    <span className="text-sm font-semibold px-2 py-0.5 rounded-md bg-rose-950/60 text-rose-300 border border-rose-800/60">
                      {briefing.market_state_label}
                    </span>
                  </>
                )}
              </div>
              <p className="text-sm text-slate-400 mt-0.5">
                多空博弈定调 · 核心战场梯队 · 盘面负反馈预警与次日观察哨
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {briefing && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm font-medium border bg-slate-950/80 border-white/10">
                <span className="flex items-center gap-1 text-purple-300">
                  <ShieldCheck className="w-3.5 h-3.5 text-purple-400" />
                  盘后官方归档
                </span>
              </div>
            )}

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-100 transition"
              title="关闭"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* 内容主体区 */}
        <div className="p-6 overflow-y-auto flex-1 flex flex-col gap-5">
          {isLoading ? (
            <div className="h-64 flex flex-col items-center justify-center gap-3 text-slate-400">
              <RefreshCw className="w-8 h-8 animate-spin text-indigo-500" />
              <p className="text-sm font-mono tracking-wide">
                正在通过 BriefingSafetyGuard 双轨审查并生成战报...
              </p>
            </div>
          ) : briefing ? (
            <>
              {/* 核心战报正文 (操盘内参风格) */}
              <div className="p-5 rounded-xl bg-slate-950 border border-slate-800 shadow-inner">
                <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800/80">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
                    <FileCheck2 className="w-4 h-4 text-purple-400" />
                    <span>核心战术研判与定调结论</span>
                  </div>
                  <span className="text-xs font-mono text-slate-400">
                    时点: {briefing.trade_date} 15:00
                  </span>
                </div>
                <p className="text-base leading-relaxed text-slate-200 font-sans tracking-wide indent-0">
                  {briefing.tactical_briefing_text}
                </p>
              </div>

              {/* 三大结构化事实卡片 */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {/* 核心战场 */}
                <div className="p-4 rounded-xl bg-slate-850/60 border border-slate-800 flex flex-col gap-2">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-indigo-300">
                    <Swords className="w-4 h-4 text-indigo-400" />
                    <span>核心战场与梯队</span>
                  </div>
                  <ul className="flex flex-col gap-1.5 text-sm text-slate-300">
                    {briefing.key_battlegrounds.map((bg, idx) => (
                      <li key={idx} className="flex items-start gap-1.5">
                        <span className="text-indigo-500 font-mono text-xs mt-0.5">▸</span>
                        <span>{bg}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* 风险预警 */}
                <div className="p-4 rounded-xl bg-slate-850/60 border border-slate-800 flex flex-col gap-2">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-rose-300">
                    <AlertOctagon className="w-4 h-4 text-rose-400" />
                    <span>盘面负反馈与风险</span>
                  </div>
                  <ul className="flex flex-col gap-1.5 text-sm text-slate-300">
                    {briefing.risk_warnings.map((rw, idx) => (
                      <li key={idx} className="flex items-start gap-1.5">
                        <span className="text-rose-500 font-mono text-xs mt-0.5">▸</span>
                        <span>{rw}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* 次日竞价观察哨 */}
                <div className="p-4 rounded-xl bg-slate-850/60 border border-slate-800 flex flex-col gap-2">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-amber-300">
                    <Eye className="w-4 h-4 text-amber-400" />
                    <span>明日观察哨与证伪</span>
                  </div>
                  <ul className="flex flex-col gap-1.5 text-sm text-slate-300">
                    {briefing.next_day_observation_posts.map((ob, idx) => (
                      <li key={idx} className="flex items-start gap-1.5">
                        <span className="text-amber-500 font-mono text-xs mt-0.5">▸</span>
                        <span>{ob}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* 底部导航与行动链接 */}
              <div className="p-3.5 rounded-xl bg-slate-950/80 border border-white/5 flex flex-wrap items-center justify-between text-sm text-slate-400 gap-3">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
                  <span>客观事实与研报已归档</span>
                  <span className="text-slate-600">|</span>
                  <span className="text-slate-400">样本覆盖: A股全市场</span>
                </div>
                {onOpenBiddingFalsification && (
                  <button
                    onClick={() => {
                      onClose();
                      onOpenBiddingFalsification();
                    }}
                    className="flex items-center gap-1.5 text-sm font-semibold text-purple-300 hover:text-purple-200 bg-purple-950/70 hover:bg-purple-900/80 border border-purple-700/60 px-3 py-1.5 rounded-lg transition"
                  >
                    <Compass className="w-3.5 h-3.5 text-purple-400" />
                    <span>查看次日 09:25 竞价对账回执 &rarr;</span>
                  </button>
                )}
              </div>
            </>
          ) : (
            <div className="h-48 flex items-center justify-center text-slate-500 text-sm">
              暂无可用的操盘手战报数据
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
