'use client';

import React from 'react';
import { CanonicalMarketSnapshot } from '@/types/canonical';
import { X, CheckCircle, Copy, Shield, FileCode, Check, Filter, Layers, Database } from 'lucide-react';

interface AuditDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  snapshot: CanonicalMarketSnapshot;
}

export const AuditDrawer: React.FC<AuditDrawerProps> = ({
  isOpen,
  onClose,
  snapshot,
}) => {
  const [copied, setCopied] = React.useState(false);
  const [showTechnicalDetails, setShowTechnicalDetails] = React.useState(false);

  if (!isOpen) return null;

  const la = snapshot.cognition.lineage_accounting;

  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(snapshot, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="w-full max-w-xl bg-slate-900 border-l border-white/10 h-full flex flex-col shadow-2xl p-6 text-slate-200 overflow-y-auto">
        {/* 标题栏 */}
        <div className="flex items-center justify-between pb-4 border-b border-white/10">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-purple-400" />
            <h2 className="text-base font-bold text-slate-100">
              主线题材准入与事实追溯
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 1. 数据来源与官方时点 */}
        <div className="mt-4 space-y-2.5">
          <h3 className="text-xs font-bold text-slate-400 tracking-wider flex items-center gap-1.5">
            <Database className="w-3.5 h-3.5 text-purple-400" />
            一、官方数据来源与核验时点
          </h3>

          <div className="bg-slate-950/80 border border-white/5 rounded-xl p-3 space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-slate-400">统计日期与时点</span>
              <span className="font-mono text-purple-300 font-semibold">{snapshot.trade_date} 15:00 官方收盘结算</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">样本覆盖范围</span>
              <span className="font-mono text-slate-200">沪深京 A股全市场标的</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">数据质量状态</span>
              <span className="font-medium text-emerald-400 flex items-center gap-1">
                <CheckCircle className="w-3 h-3" /> 官方数据源核验完整
              </span>
            </div>

            {/* 可折叠的技术追溯底稿 */}
            <div className="pt-2 border-t border-white/5">
              <button
                onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
                className="text-[10px] text-slate-500 hover:text-slate-400 flex items-center justify-between w-full"
              >
                <span>底层数字校验指纹</span>
                <span>{showTechnicalDetails ? '收起 ▴' : '展开 ▾'}</span>
              </button>
              {showTechnicalDetails && (
                <div className="mt-2 space-y-1.5 font-mono text-[10px] text-slate-400 bg-black/40 p-2 rounded">
                  <div className="truncate">Truth 指纹: {snapshot.truth.truth_fingerprint}</div>
                  <div className="truncate">Cognition 指纹: {snapshot.cognition.cognition_fingerprint}</div>
                  <div className="truncate">Envelope 指纹: {snapshot.envelope_fingerprint}</div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 2. 主线题材准入与过滤漏斗 */}
        <div className="mt-5 space-y-2.5">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-slate-400 tracking-wider flex items-center gap-1.5">
              <Filter className="w-3.5 h-3.5 text-cyan-400" />
              二、主线题材准入与过滤漏斗
            </h3>
            {la.is_mathematically_closed && (
              <span className="text-[11px] text-emerald-400 font-semibold flex items-center gap-1 bg-emerald-950/40 border border-emerald-800/40 px-2 py-0.5 rounded">
                <CheckCircle className="w-3 h-3" /> 筛选逻辑闭环
              </span>
            )}
          </div>

          <div className="bg-slate-950/80 border border-white/5 rounded-xl p-3 space-y-2 text-xs">
            <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
              <div className="p-2 bg-slate-900/60 rounded-lg border border-white/5">
                <span className="text-slate-400 block text-[10px]">全市场评估题材数</span>
                <span className="text-base font-bold text-slate-200 mt-0.5 block">{la.total_raw_evaluated}</span>
              </div>
              <div className="p-2 bg-slate-900/60 rounded-lg border border-white/5">
                <span className="text-slate-400 block text-[10px]">通过初步准入题材</span>
                <span className="text-base font-bold text-purple-300 mt-0.5 block">{la.admission_admitted_count}</span>
              </div>
              <div className="p-2 bg-slate-900/60 rounded-lg border border-white/5">
                <span className="text-slate-400 block text-[10px]">排除统计/区域非交易概念</span>
                <span className="text-base font-bold text-amber-400 mt-0.5 block">{la.excluded_meta_tags_count}</span>
              </div>
              <div className="p-2 bg-slate-900/60 rounded-lg border border-white/5">
                <span className="text-slate-400 block text-[10px]">排除单票寄生概念</span>
                <span className="text-base font-bold text-amber-400 mt-0.5 block">{la.solitary_leader_noise_count}</span>
              </div>
              <div className="p-2 bg-slate-900/60 rounded-lg border border-white/5">
                <span className="text-slate-400 block text-[10px]">过滤日内弱脉冲杂音</span>
                <span className="text-base font-bold text-slate-400 mt-0.5 block">{la.pulse_noise_count}</span>
              </div>
              <div className="p-2 bg-slate-900/60 rounded-lg border border-white/5">
                <span className="text-slate-400 block text-[10px]">重合成分聚类去重</span>
                <span className="text-base font-bold text-indigo-400 mt-0.5 block">{la.deduplicated_clusters_count}</span>
              </div>
              <div className="p-2 bg-slate-900/60 rounded-lg border border-white/5">
                <span className="text-slate-400 block text-[10px]">有效主线候选池</span>
                <span className="text-base font-bold text-cyan-300 mt-0.5 block">{la.eligible_candidates_count}</span>
              </div>
              <div className="p-2 bg-slate-900/60 rounded-lg border border-purple-500/20 bg-purple-950/20">
                <span className="text-purple-300 block text-[10px] font-semibold">驾驶舱重点聚焦展示</span>
                <span className="text-base font-bold text-purple-300 mt-0.5 block">{la.top_mainlines_count} 个核心方向</span>
              </div>
            </div>
          </div>
        </div>

        {/* 3. 原始数据快照 */}
        <div className="mt-5 flex-1 flex flex-col min-h-0">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-bold text-slate-400 tracking-wider flex items-center gap-1.5">
              <FileCode className="w-3.5 h-3.5 text-slate-400" />
              三、原始行情事实数据快照 (JSON)
            </h3>
            <button
              onClick={handleCopyJson}
              className="text-xs font-medium text-purple-400 hover:text-purple-300 flex items-center gap-1 transition"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-400" /> 已复制
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" /> 复制快照
                </>
              )}
            </button>
          </div>

          <pre className="flex-1 bg-slate-950 p-3 rounded-xl border border-white/5 font-mono text-[10px] text-slate-400 overflow-auto max-h-52">
            {JSON.stringify(snapshot, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
};
