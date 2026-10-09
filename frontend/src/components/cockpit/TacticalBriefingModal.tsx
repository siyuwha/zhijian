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
                  操盘内参 · 实战战报
                </h2>
                {briefing && (
                  <>
                    <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-700/60 font-mono">
                      {briefing.trade_date}
                    </span>
                    <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-rose-950/60 text-rose-300 border border-rose-800/60">
                      {briefing.market_state_label}
                    </span>
                  </>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Phase 2D.3 受约束 LLM 实战定调 · 双轨制后置审查与 3ms 确定性保底
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {briefing && (
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border bg-slate-950/80">
                {briefing.is_fallback_mode ? (
                  <span className="flex items-center gap-1 text-amber-400 border-amber-800">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    确定性保底模式
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-emerald-400 border-emerald-800">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    100% 审查通过
                  </span>
                )}
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
              {/* 核心战报正文 (冷峻操盘内参风格) */}
              <div className="p-5 rounded-xl bg-slate-950 border border-slate-800 shadow-inner">
                <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800/80">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
                    <FileCheck2 className="w-4 h-4 text-indigo-400" />
                    <span>操盘手内参实战定调正文 (250~350字穿透)</span>
                  </div>
                  <span className="text-[11px] font-mono text-slate-500">
                    字数: {briefing.tactical_briefing_text.length} 字符
                  </span>
                </div>
                <p className="text-sm leading-relaxed text-slate-200 font-sans tracking-wide indent-0">
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
                  <ul className="flex flex-col gap-1.5 text-xs text-slate-300">
                    {briefing.key_battlegrounds.map((bg, idx) => (
                      <li key={idx} className="flex items-start gap-1.5">
                        <span className="text-indigo-500 font-mono text-[10px] mt-0.5">▸</span>
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
                  <ul className="flex flex-col gap-1.5 text-xs text-slate-300">
                    {briefing.risk_warnings.map((rw, idx) => (
                      <li key={idx} className="flex items-start gap-1.5">
                        <span className="text-rose-500 font-mono text-[10px] mt-0.5">▸</span>
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
                  <ul className="flex flex-col gap-1.5 text-xs text-slate-300">
                    {briefing.next_day_observation_posts.map((ob, idx) => (
                      <li key={idx} className="flex items-start gap-1.5">
                        <span className="text-amber-500 font-mono text-[10px] mt-0.5">▸</span>
                        <span>{ob}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* 来源防伪与全链路 Trace 水印 */}
              <div className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-850 flex flex-col gap-2 text-[11px] font-mono text-slate-500">
                <div className="flex flex-col sm:flex-row items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Cpu className="w-3.5 h-3.5 text-indigo-400" />
                    <span>引擎: {briefing.producer_version}</span>
                    <span>|</span>
                    <span>战报指纹: {briefing.briefing_fingerprint.slice(0, 16)}...</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                    <span>BriefingSafetyGuard 物理拦截通过 · 零 L5 指令泄露</span>
                  </div>
                </div>
                {briefing.trace_id && (
                  <div className="flex flex-col sm:flex-row items-center justify-between gap-2 pt-2 border-t border-slate-900 text-[10px] text-slate-600">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-400">Trace ID:</span>
                      <span className="text-indigo-400/90 select-all">{briefing.trace_id}</span>
                    </div>
                    {briefing.source_snapshot_hash && (
                      <div className="flex items-center gap-2">
                        <span className="text-slate-400">快照 SHA:</span>
                        <span className="text-slate-400 select-all">{briefing.source_snapshot_hash.slice(0, 16)}...</span>
                      </div>
                    )}
                  </div>
                )}
                {onOpenBiddingFalsification && (
                  <div className="pt-2.5 border-t border-slate-900 flex justify-end">
                    <button
                      onClick={() => {
                        onClose();
                        onOpenBiddingFalsification();
                      }}
                      className="flex items-center gap-1.5 text-xs font-semibold text-indigo-300 hover:text-indigo-200 bg-indigo-950/70 hover:bg-indigo-900/80 border border-indigo-700/60 px-3 py-1.5 rounded-lg transition"
                    >
                      <Compass className="w-3.5 h-3.5 text-indigo-400" />
                      <span>查看次日 09:25 竞价对账回执 &rarr;</span>
                    </button>
                  </div>
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
