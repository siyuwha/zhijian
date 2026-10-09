'use client';

import React from 'react';
import { BiddingFalsificationVerdict } from '@/types/canonical';
import { BiddingFalsificationCard } from './BiddingFalsificationCard';
import { X, Compass, RefreshCw } from 'lucide-react';

interface BiddingFalsificationModalProps {
  isOpen: boolean;
  onClose: () => void;
  verdict: BiddingFalsificationVerdict | null;
  isLoading?: boolean;
  errorMsg?: string | null;
  onRefresh?: () => void;
}

export const BiddingFalsificationModal: React.FC<BiddingFalsificationModalProps> = ({
  isOpen,
  onClose,
  verdict,
  isLoading = false,
  errorMsg = null,
  onRefresh,
}) => {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in duration-150"
      onClick={onClose}
    >
      <div
        className="w-full max-w-4xl bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col max-h-[92vh] overflow-hidden select-none"
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
                  09:25 集合竞价波普尔证伪自动对账单
                </h2>
                {verdict && (
                  <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-300 border border-indigo-700/60">
                    {verdict.trade_date}
                  </span>
                )}
              </div>
              <p className="text-[10px] text-slate-400 font-mono mt-0.5">
                昨晚假说 vs 今晨 09:25 物理实测 · 纯只读抗篡改权威裁决
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {onRefresh && (
              <button
                onClick={onRefresh}
                className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition"
                title="重新核验"
              >
                <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              </button>
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition"
              title="关闭"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </header>

        {/* 核心内容区 */}
        <div className="p-5 overflow-y-auto max-h-[calc(92vh-70px)]">
          <BiddingFalsificationCard
            verdict={verdict}
            isLoading={isLoading}
            errorMsg={errorMsg}
            onRefresh={onRefresh}
            compact={false}
          />
        </div>
      </div>
    </div>
  );
};
