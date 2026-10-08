'use client';

import React from 'react';
import { CanonicalMarketSnapshot } from '@/types/canonical';
import { X, CheckCircle, Copy, Shield, FileCode, Check } from 'lucide-react';

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

  if (!isOpen) return null;

  const la = snapshot.cognition.lineage_accounting;

  const handleCopyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(snapshot, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="w-full max-w-xl bg-slate-900 border-l border-slate-800 h-full flex flex-col shadow-2xl p-6 text-slate-200 overflow-y-auto">
        {/* 标题 */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-indigo-400" />
            <h2 className="text-lg font-bold text-slate-100">
              市场真相与认知审计抽屉 (Audit Drawer)
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 1. 防篡改数字指纹 */}
        <div className="mt-4 space-y-3">
          <h3 className="text-xs font-bold text-slate-400 tracking-wider uppercase">
            一、RFC 8785 JCS 防篡改数字指纹
          </h3>

          <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-3 space-y-2 text-xs font-mono">
            <div>
              <span className="text-slate-400 block text-[10px]">Truth Snapshot (FACT + DERIVED):</span>
              <span className="text-indigo-300 break-all">{snapshot.truth.truth_fingerprint}</span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px]">Cognition Snapshot (COGNITION):</span>
              <span className="text-teal-300 break-all">{snapshot.cognition.cognition_fingerprint}</span>
            </div>
            <div>
              <span className="text-slate-400 block text-[10px]">Top-level Unified Envelope:</span>
              <span className="text-emerald-300 break-all">{snapshot.envelope_fingerprint}</span>
            </div>
          </div>
        </div>

        {/* 2. 完整血缘解释与数学恒等式 */}
        <div className="mt-6 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-bold text-slate-400 tracking-wider uppercase">
              二、287 → 251 → Top-N 全血缘数学闭环
            </h3>
            {la.is_mathematically_closed && (
              <span className="text-xs text-emerald-400 font-semibold flex items-center gap-1 bg-emerald-950/50 border border-emerald-800/60 px-2 py-0.5 rounded">
                <CheckCircle className="w-3.5 h-3.5" /> 恒等式 100% 闭环
              </span>
            )}
          </div>

          <div className="bg-slate-950/80 border border-slate-800 rounded-lg p-3 space-y-2 text-xs">
            <div className="font-mono text-slate-300 p-2 bg-slate-900/60 rounded border border-slate-800 text-[11px] leading-relaxed">
              {la.lineage_formula}
            </div>

            <div className="grid grid-cols-2 gap-2 pt-1 font-mono text-[11px]">
              <div className="p-2 bg-slate-900 rounded border border-slate-800">
                <span className="text-slate-400 block">物理评估总数</span>
                <span className="text-base font-bold text-slate-200">{la.total_raw_evaluated}</span>
              </div>
              <div className="p-2 bg-slate-900 rounded border border-slate-800">
                <span className="text-slate-400 block">通过准入假说数</span>
                <span className="text-base font-bold text-slate-200">{la.admission_admitted_count}</span>
              </div>
              <div className="p-2 bg-slate-900 rounded border border-slate-800">
                <span className="text-slate-400 block">排除元标签/统计/特征</span>
                <span className="text-base font-bold text-amber-400">{la.excluded_meta_tags_count}</span>
              </div>
              <div className="p-2 bg-slate-900 rounded border border-slate-800">
                <span className="text-slate-400 block">排除孤立寄生单票标签</span>
                <span className="text-base font-bold text-amber-400">{la.solitary_leader_noise_count}</span>
              </div>
              <div className="p-2 bg-slate-900 rounded border border-slate-800">
                <span className="text-slate-400 block">日内弱脉冲杂音</span>
                <span className="text-base font-bold text-slate-400">{la.pulse_noise_count}</span>
              </div>
              <div className="p-2 bg-slate-900 rounded border border-slate-800">
                <span className="text-slate-400 block">成分重合聚类去重</span>
                <span className="text-base font-bold text-indigo-400">{la.deduplicated_clusters_count}</span>
              </div>
              <div className="p-2 bg-slate-900 rounded border border-slate-800">
                <span className="text-slate-400 block">合规主线候选池</span>
                <span className="text-base font-bold text-teal-400">{la.eligible_candidates_count}</span>
              </div>
              <div className="p-2 bg-slate-900 rounded border border-slate-800">
                <span className="text-slate-400 block">驾驶舱顶级呈现 (Top-N)</span>
                <span className="text-base font-bold text-emerald-400">{la.top_mainlines_count}</span>
              </div>
            </div>
          </div>
        </div>

        {/* 3. Raw JSON 导出 */}
        <div className="mt-6 flex-1 flex flex-col min-h-0">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xs font-bold text-slate-400 tracking-wider uppercase flex items-center gap-1.5">
              <FileCode className="w-4 h-4" /> 三、原始 Canonical JSON 快照
            </h3>
            <button
              onClick={handleCopyJson}
              className="text-xs font-medium text-indigo-400 hover:text-indigo-300 flex items-center gap-1 transition"
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

          <pre className="flex-1 bg-slate-950 p-3 rounded-lg border border-slate-800 font-mono text-[10px] text-slate-400 overflow-auto max-h-60">
            {JSON.stringify(snapshot, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
};
