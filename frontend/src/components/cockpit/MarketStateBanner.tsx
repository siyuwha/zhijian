'use client';

import React from 'react';
import {
  CanonicalIndexQuote,
  CanonicalTurnoverBreakdown,
  DataQualityGrade,
  CalibratedMarketState,
} from '@/types/canonical';
import { Activity, TrendingDown, TrendingUp, AlertCircle, ShieldCheck, Cpu, FileText } from 'lucide-react';

interface MarketStateBannerProps {
  summary: string;
  calibration?: CalibratedMarketState | null;
  turnover: CanonicalTurnoverBreakdown;
  indices: CanonicalIndexQuote[];
  breadthStatus: DataQualityGrade;
  degradationDetail?: { message?: string; heuristic_warning?: string } | null;
  provisionalDisclaimer?: string;
  onOpenBriefing?: () => void;
}

export const MarketStateBanner: React.FC<MarketStateBannerProps> = ({
  summary,
  calibration,
  turnover,
  indices,
  breadthStatus,
  degradationDetail,
  provisionalDisclaimer,
  onOpenBriefing,
}) => {
  // 状态机色系映射
  const getStateColorClass = (state?: string) => {
    switch (state) {
      case 'EXPANSION_ACCELERATION':
        return 'bg-red-500/20 text-red-400 border-red-500/40';
      case 'HIGH_DIVERGENCE_TOPPING':
        return 'bg-amber-500/20 text-amber-400 border-amber-500/40';
      case 'RECESSION_PANIC':
        return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40';
      case 'FREEZING_REVERSAL':
        return 'bg-cyan-500/20 text-cyan-400 border-cyan-500/40';
      case 'LOW_REBOUND':
        return 'bg-sky-500/20 text-sky-400 border-sky-500/40';
      default:
        return 'bg-slate-500/20 text-slate-300 border-slate-500/40';
    }
  };

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-lg flex flex-col gap-3">
      {/* 问 1：今天市场是什么状态？ (Phase 2D.2 有限状态机校准) */}
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
        <div className="flex flex-wrap items-center gap-2.5">
          <span className="px-2.5 py-1 text-xs font-bold rounded-md bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 flex items-center gap-1.5 shrink-0">
            <Activity className="w-3.5 h-3.5" />
            问 1 · 市场状态 (Market State)
          </span>

          {/* 结构化状态标签 (Phase 2D.2) */}
          {calibration && (
            <span
              className={`px-2 py-0.5 text-xs font-bold font-mono rounded border flex items-center gap-1 shrink-0 ${getStateColorClass(
                calibration.primary_state
              )}`}
            >
              <Cpu className="w-3 h-3 inline" />
              {calibration.state_display_name}
              <span className="text-xs opacity-75 font-normal">
                ({(calibration.state_confidence * 100).toFixed(0)}% 置信度)
              </span>
            </span>
          )}

          {/* 转移信号提示 */}
          {calibration?.transition_signal && (
            <span className="text-xs text-amber-300/90 bg-amber-950/40 border border-amber-800/50 px-2 py-0.5 rounded font-mono shrink-0">
              ⚡ {calibration.transition_signal}
            </span>
          )}

          <p className="text-base font-semibold text-slate-100 leading-snug">
            {summary}
          </p>
        </div>

        {/* 董事会强制免责标识与广度降级提示 */}
        <div className="flex items-center gap-2 shrink-0">
          {onOpenBriefing && (
            <button
              onClick={onOpenBriefing}
              className="flex items-center gap-1.5 bg-indigo-950/80 hover:bg-indigo-900 border border-indigo-700/60 px-2.5 py-1 rounded text-sm font-semibold text-indigo-300 transition"
              title="查看受约束 LLM 操盘内参实战战报"
            >
              <FileText className="w-3.5 h-3.5 text-indigo-400" />
              <span>操盘战报</span>
            </button>
          )}
          <span className="text-xs text-amber-300 font-mono bg-amber-950/60 border border-amber-800/80 px-2 py-0.5 rounded">
            PROVISIONAL 推断
          </span>
          {breadthStatus === 'UNAVAILABLE' && (
            <div className="flex items-center gap-2 text-sm bg-amber-950/40 text-amber-300 border border-amber-800/60 px-2.5 py-1 rounded-md">
              <AlertCircle className="w-3.5 h-3.5 text-amber-400" />
              <span>全市场广度单源 HTTP 502 (已安全降级，微观池正常)</span>
            </div>
          )}
        </div>
      </div>

      {/* 问 2：真实成交量能是多少？ (防重算真实口径) */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-3 pt-1">
        {/* 两市真实总额 (无二次累加) */}
        <div className="lg:col-span-2 bg-slate-950/60 border border-slate-800 rounded-lg p-2.5 flex flex-col justify-between">
          <div className="flex items-center justify-between text-sm text-slate-400 mb-1">
            <span className="font-medium text-slate-300 flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
              问 2 · 沪深两市真实总成交
            </span>
            <span className="text-xs text-emerald-400 bg-emerald-950/40 border border-emerald-800/50 px-1.5 py-0.5 rounded">
              防重算冻结口径
            </span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-black text-slate-100 font-mono tracking-tight">
              {(turnover.two_markets_total_yi / 10000).toFixed(2)}
            </span>
            <span className="text-sm text-slate-400 font-medium">万亿元</span>
            <span className="text-sm text-slate-400 font-mono">
              ({turnover.two_markets_total_yi.toLocaleString()} 亿)
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-1 flex items-center justify-between border-t border-slate-800/60 pt-1">
            <span>沪: {turnover.sh_amount_yi.toFixed(0)} 亿 | 深(含创): {turnover.sz_total_amount_yi.toFixed(0)} 亿</span>
            <span className="text-slate-400 font-mono">
              创占比 {(turnover.chinext_ratio_in_sz * 100).toFixed(1)}% (切片)
            </span>
          </div>
        </div>

        {/* 四大核心指数卡片 */}
        {indices.map((idx) => {
          const isUp = idx.pct_change >= 0;
          return (
            <div
              key={idx.symbol}
              className="bg-slate-950/40 border border-slate-800/80 rounded-lg p-2.5 flex flex-col justify-between"
            >
              <div className="flex items-center justify-between text-sm text-slate-400">
                <span className="font-medium text-slate-300">{idx.name}</span>
                <span className="text-xs font-mono text-slate-400">
                  {idx.amount_yi.toFixed(0)} 亿
                </span>
              </div>
              <div className="flex items-baseline justify-between mt-1">
                <span className="text-xl font-bold font-mono text-slate-100">
                  {idx.current_price.toFixed(2)}
                </span>
                <span
                  className={`text-sm font-bold font-mono flex items-center ${
                    isUp ? 'text-red-400' : 'text-emerald-400'
                  }`}
                >
                  {isUp ? (
                    <TrendingUp className="w-3.5 h-3.5 mr-0.5 inline" />
                  ) : (
                    <TrendingDown className="w-3.5 h-3.5 mr-0.5 inline" />
                  )}
                  {isUp ? '+' : ''}
                  {idx.pct_change.toFixed(2)}%
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
