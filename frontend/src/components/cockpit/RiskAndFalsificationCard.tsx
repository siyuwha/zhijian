'use client';

import React from 'react';
import {
  BrokenLimitUniverseContract,
  RegulatoryAnomalyItem,
  MainlineCandidate,
} from '@/types/canonical';
import { AlertOctagon, Flame, Eye, ShieldAlert, Zap } from 'lucide-react';

interface RiskAndFalsificationCardProps {
  sentiment: BrokenLimitUniverseContract;
  anomalies: RegulatoryAnomalyItem[];
  primaryMainline?: MainlineCandidate;
}

export const RiskAndFalsificationCard: React.FC<RiskAndFalsificationCardProps> = ({
  sentiment,
  anomalies,
  primaryMainline,
}) => {
  const isHighRisk = sentiment.broken_limit_ratio >= 0.35;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
      {/* 问 5：亏钱效应有多强？ (情绪极端边界与炸板率) */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3.5 shadow-lg flex flex-col justify-between">
        <div className="flex items-center justify-between pb-2 border-b border-slate-800">
          <span className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
            <Flame className="w-4 h-4 text-orange-400" />
            问 5 · 亏钱效应与炸板率
          </span>
          <span
            className={`text-[10px] font-bold px-2 py-0.5 rounded ${
              isHighRisk
                ? 'bg-rose-950/80 text-rose-300 border border-rose-800'
                : 'bg-emerald-950/80 text-emerald-300 border border-emerald-800'
            }`}
          >
            {isHighRisk ? '高危分歧 / 退潮预警' : '情绪可控'}
          </span>
        </div>

        <div className="grid grid-cols-3 gap-2 my-2 text-center">
          <div className="bg-slate-950/60 p-2 rounded-lg border border-slate-800/80">
            <span className="text-[11px] text-slate-400 block">涨停 / 跌停</span>
            <span className="text-base font-black font-mono text-slate-100">
              <span className="text-red-400">{sentiment.limit_up_count}</span>
              <span className="text-slate-400 mx-0.5">/</span>
              <span className="text-emerald-400">{sentiment.limit_down_count}</span>
            </span>
          </div>

          <div className="bg-slate-950/60 p-2 rounded-lg border border-slate-800/80">
            <span className="text-[11px] text-slate-400 block">炸板家数</span>
            <span className="text-base font-black font-mono text-orange-400">
              {sentiment.broken_limit_count}
              <span className="text-[10px] text-slate-400 font-normal ml-0.5">只</span>
            </span>
          </div>

          <div className="bg-slate-950/60 p-2 rounded-lg border border-slate-800/80">
            <span className="text-[11px] text-slate-400 block">真实炸板率</span>
            <span className="text-base font-black font-mono text-rose-400">
              {(sentiment.broken_limit_ratio * 100).toFixed(1)}%
            </span>
          </div>
        </div>

        <p className="text-[11px] text-slate-400 leading-tight">
          日内曾触及涨停总家数 {sentiment.touched_limit_total_count} 只，极高炸板率表明追高胜率骤降，日内踩踏大面频发。
        </p>
      </div>

      {/* 问 6：当前最大的监管/异常风险是什么？ (交易所异动雷达) */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3.5 shadow-lg flex flex-col justify-between">
        <div className="flex items-center justify-between pb-2 border-b border-slate-800">
          <span className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
            <ShieldAlert className="w-4 h-4 text-amber-400" />
            问 6 · 监管与严重异动风险
          </span>
          <span className="text-[10px] text-amber-400 font-mono bg-amber-950/40 border border-amber-800/60 px-1.5 py-0.5 rounded">
            共捕获 {anomalies.length} 项异动
          </span>
        </div>

        <div className="my-2 space-y-1.5 max-h-24 overflow-y-auto pr-1 text-xs">
          {anomalies.slice(0, 3).map((anom, idx) => (
            <div
              key={idx}
              className="bg-slate-950/60 border border-slate-800/80 p-1.5 rounded flex items-center justify-between"
            >
              <div className="flex items-center gap-1.5">
                <span className="font-bold text-slate-200">{anom.name}</span>
                <span className="text-[10px] text-slate-400 font-mono">
                  {anom.symbol}
                </span>
              </div>
              <span className="text-[10px] text-rose-400 font-mono font-bold">
                偏离 {anom.deviation_pct.toFixed(1)}%
              </span>
            </div>
          ))}
        </div>

        <p className="text-[10px] text-slate-400 flex items-center gap-1">
          <Zap className="w-3 h-3 text-amber-400 shrink-0" />
          定性：依交易所规则商业撮合匹配，核心龙头触碰特停降温红线。
        </p>
      </div>

      {/* 问 7：次日最重要的证伪观察点是什么？ (闭环证伪条件) */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-3.5 shadow-lg flex flex-col justify-between">
        <div className="flex items-center justify-between pb-2 border-b border-slate-800">
          <span className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
            <Eye className="w-4 h-4 text-cyan-400" />
            问 7 · 次日核心证伪观察点
          </span>
          <span className="text-[10px] text-cyan-400 bg-cyan-950/40 border border-cyan-800/60 px-1.5 py-0.5 rounded">
            波普尔判据
          </span>
        </div>

        <div className="my-2 space-y-1 text-xs">
          {primaryMainline?.falsification_condition.invalidation_rules.map((rule, idx) => (
            <div key={idx} className="flex items-start gap-1.5 text-slate-300 text-[11px]">
              <span className="text-rose-400 font-bold shrink-0">⚠️ 判定 {idx + 1}:</span>
              <span>{rule}</span>
            </div>
          ))}
        </div>

        <div className="pt-1.5 border-t border-slate-800/60 flex items-center justify-between text-[11px] text-slate-400">
          <span>次日竞价核心标的:</span>
          <div className="flex gap-1">
            {primaryMainline?.falsification_condition.critical_observation_symbols.map((sym, idx) => (
              <span
                key={idx}
                className="bg-slate-950 text-cyan-300 font-bold px-1.5 py-0.5 rounded border border-cyan-900/60"
              >
                {sym}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
