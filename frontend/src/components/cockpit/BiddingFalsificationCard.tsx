'use client';

import React from 'react';
import {
  BiddingFalsificationVerdict,
  FalsificationOutcomeEnum,
  AssertionItemVerdict,
  AssertionSeverityEnum,
} from '@/types/canonical';
import {
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Activity,
  Compass,
  Crown,
  Layers,
  Flame,
  ShieldAlert,
  Fingerprint,
  RefreshCw,
  Lock,
  ArrowRight,
  TrendingDown,
  TrendingUp,
  AlertOctagon,
} from 'lucide-react';

interface BiddingFalsificationCardProps {
  verdict: BiddingFalsificationVerdict | null;
  isLoading?: boolean;
  errorMsg?: string | null;
  onRefresh?: () => void;
  compact?: boolean;
  onOpenDetailsModal?: () => void;
}

export const BiddingFalsificationCard: React.FC<BiddingFalsificationCardProps> = ({
  verdict,
  isLoading = false,
  errorMsg = null,
  onRefresh,
  compact = false,
  onOpenDetailsModal,
}) => {
  if (isLoading) {
    return (
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col items-center justify-center min-h-[220px] text-slate-400 gap-3">
        <RefreshCw className="w-6 h-6 animate-spin text-indigo-400" />
        <span className="text-xs font-mono tracking-wide">
          正在核验 09:25 集合竞价物理快照并执行波普尔证伪对账...
        </span>
      </div>
    );
  }

  if (errorMsg) {
    return (
      <div className="bg-slate-900/90 border border-rose-900/50 rounded-xl p-5 shadow-lg flex flex-col items-center justify-center min-h-[220px] text-slate-300 gap-2">
        <AlertOctagon className="w-8 h-8 text-rose-400" />
        <p className="text-xs font-semibold text-rose-300">{errorMsg}</p>
        {onRefresh && (
          <button
            onClick={onRefresh}
            className="mt-2 px-3 py-1 bg-slate-800 hover:bg-slate-700 text-xs font-mono rounded text-slate-200 transition"
          >
            重试拉取
          </button>
        )}
      </div>
    );
  }

  if (!verdict) {
    return (
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col items-center justify-center min-h-[220px] text-slate-500 gap-2">
        <HelpCircle className="w-7 h-7 text-slate-600" />
        <span className="text-xs">暂无 09:25 竞价对账数据</span>
      </div>
    );
  }

  const {
    overall_verdict,
    inconclusive_reason,
    verdict_headline,
    assertion_results = [],
    action_boundaries = [],
    evaluated_at,
    trade_date,
    trace_id,
    hypothesis_id,
    rule_version,
    verdict_fingerprint,
    safety_audit_passed,
  } = verdict;

  const isMarketClosed = inconclusive_reason === 'MARKET_CLOSED';

  // 状态样式映射
  const getOutcomeBadge = () => {
    switch (overall_verdict) {
      case 'CONFIRMED':
        return {
          icon: <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
          label: '假设得到验证 · 龙头共振',
          subLabel: '竞价符合预期，按原计划推进',
          badgeClass: 'bg-emerald-950/80 text-emerald-300 border-emerald-800/80',
          borderClass: 'border-emerald-900/40',
        };
      case 'DIVERGENT':
        return {
          icon: <AlertTriangle className="w-4 h-4 text-amber-400" />,
          label: '盘前出现分歧 · 承接分化',
          subLabel: '量能或主线出现偏离，严控追高',
          badgeClass: 'bg-amber-950/80 text-amber-300 border-amber-800/80',
          borderClass: 'border-amber-900/40',
        };
      case 'FALSIFIED':
        return {
          icon: <XCircle className="w-4 h-4 text-rose-400" />,
          label: '核心假说被推翻 · 触发防守',
          subLabel: '标的开盘不及预期，坚决执行防守',
          badgeClass: 'bg-rose-950/80 text-rose-300 border-rose-800/80',
          borderClass: 'border-rose-900/50',
        };
      case 'INCONCLUSIVE':
      default:
        return {
          icon: <HelpCircle className="w-4 h-4 text-slate-400" />,
          label: isMarketClosed ? '休市未开盘' : '数据观察中',
          subLabel: isMarketClosed ? '非交易时段' : '待集合竞价撮合更新',
          badgeClass: 'bg-slate-800/80 text-slate-300 border-slate-700/80',
          borderClass: 'border-slate-800',
        };
    }
  };

  const badge = getOutcomeBadge();

  const getRuleIcon = (ruleId: string) => {
    switch (ruleId) {
      case 'RULE-SPACE-LEADER-PREMIUM':
        return <Crown className="w-3.5 h-3.5 text-rose-400" />;
      case 'RULE-MAINLINE-LEADER-ALIGNMENT':
        return <Layers className="w-3.5 h-3.5 text-indigo-400" />;
      case 'RULE-LIQUIDITY-INTENSITY':
        return <Activity className="w-3.5 h-3.5 text-cyan-400" />;
      case 'RULE-INDEX-SENTIMENT':
        return <Compass className="w-3.5 h-3.5 text-amber-400" />;
      default:
        return <Flame className="w-3.5 h-3.5 text-slate-400" />;
    }
  };

  return (
    <div
      className={`bg-slate-900/95 border ${badge.borderClass} rounded-xl p-4 shadow-xl flex flex-col justify-between transition-all select-none`}
    >
      {/* 1. 顶部控制栏与结论定调 */}
      <div className="pb-3 border-b border-slate-800/80 flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-indigo-950/70 border border-indigo-800/60 text-indigo-400">
              <Compass className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-black tracking-tight text-slate-100">
                  09:25 集合竞价波普尔证伪对账单
                </span>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-950 text-slate-400 border border-slate-800">
                  {trade_date}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* 核心定调徽章 */}
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-bold font-mono ${badge.badgeClass}`}
            >
              {badge.icon}
              <span>{badge.label}</span>
              <span className="text-[10px] font-normal opacity-80 hidden sm:inline">
                ({badge.subLabel})
              </span>
            </div>

            {onOpenDetailsModal && compact && (
              <button
                onClick={onOpenDetailsModal}
                className="text-[10px] text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-mono transition"
                title="展开全屏对账详情"
              >
                <span>详情</span>
                <ArrowRight className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>

        {/* 一句话客观全貌通报 */}
        <div className="bg-slate-950/70 border border-slate-800/80 rounded-lg px-3 py-2 flex items-start gap-2">
          <div className="pt-0.5 shrink-0">{badge.icon}</div>
          <p className="text-xs text-slate-200 font-medium leading-relaxed">
            {verdict_headline}
          </p>
        </div>
      </div>

      {/* 2. 四维断言客观对比网格 (非休市时完整渲染) */}
      {!isMarketClosed && assertion_results.length > 0 && (
        <div className="my-3 flex flex-col gap-2">
          <div className="flex items-center justify-between text-[11px] text-slate-400 font-semibold px-1">
            <span>四维物理事实断言比对</span>
            <span className="font-mono text-[10px] text-slate-500">
              {rule_version}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {assertion_results.map((item) => (
              <div
                key={item.rule_id}
                className={`bg-slate-950/70 border rounded-lg p-2.5 flex flex-col justify-between transition-colors ${
                  item.is_violated
                    ? item.severity === 'CRITICAL_KILL'
                      ? 'border-rose-900/80 bg-rose-950/20'
                      : 'border-amber-900/70 bg-amber-950/20'
                    : 'border-slate-800/80 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between pb-1.5 border-b border-slate-800/50">
                  <div className="flex items-center gap-1.5">
                    {getRuleIcon(item.rule_id)}
                    <span className="text-xs font-bold text-slate-200">
                      {item.rule_name}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {item.severity === 'CRITICAL_KILL' && (
                      <span className="text-[9px] font-mono font-bold px-1.5 py-0.2 rounded bg-rose-950 text-rose-300 border border-rose-800">
                        CRITICAL KILL
                      </span>
                    )}
                    <span
                      className={`text-[10px] font-mono font-bold px-1.5 py-0.2 rounded ${
                        item.is_violated
                          ? 'bg-rose-950/80 text-rose-300 border border-rose-800'
                          : 'bg-emerald-950/80 text-emerald-300 border border-emerald-800'
                      }`}
                    >
                      {item.is_violated ? '已违背' : '吻合'}
                    </span>
                  </div>
                </div>

                <div className="py-1.5 flex flex-col gap-1 text-[11px]">
                  <div className="flex justify-between items-baseline text-slate-400">
                    <span className="shrink-0 text-slate-500">标的/范围：</span>
                    <span className="font-mono text-slate-200 text-right truncate">
                      {item.target_entity}
                    </span>
                  </div>
                  <div className="flex justify-between items-baseline text-slate-400">
                    <span className="shrink-0 text-slate-500">实测观测：</span>
                    <span className="font-mono text-slate-200 text-right">
                      {item.actual_observation}
                    </span>
                  </div>
                  <div className="flex justify-between items-baseline text-slate-400">
                    <span className="shrink-0 text-slate-500">假说预期：</span>
                    <span className="font-mono text-slate-400 text-right">
                      {item.expected_condition}
                    </span>
                  </div>
                </div>

                <div className="pt-1.5 border-t border-slate-800/40 text-[10px] text-slate-400 italic">
                  {item.deviation_analysis}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 3. 盘前防守行动红线 */}
      {action_boundaries.length > 0 && (
        <div className="my-2 bg-slate-950/80 border border-white/5 rounded-xl p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-bold text-amber-300 flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5 text-amber-400" />
              盘前防守纪律与行动红线
            </span>
            <span className="text-[10px] font-mono text-rose-400 bg-rose-950/40 px-1.5 py-0.2 rounded border border-rose-800/40">
              触发条件严格执行
            </span>
          </div>
          <div className="flex flex-col gap-1.5">
            {action_boundaries.map((boundary, idx) => (
              <div
                key={idx}
                className="flex items-start gap-1.5 text-xs text-slate-300"
              >
                <Lock className="w-3 h-3 text-slate-400 mt-0.5 shrink-0" />
                <span className="font-medium text-[11px] leading-relaxed">
                  {boundary}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 4. 底栏核验状态与时间 */}
      <footer className="pt-2.5 border-t border-white/5 flex flex-wrap items-center justify-between text-[11px] text-slate-400 gap-2">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1 text-slate-300">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400"></span>
            <span>核验时点: 09:25:05 撮合完成</span>
          </span>
          <span className="text-slate-600">|</span>
          <span>
            监控项: <strong className="text-slate-200 font-mono">{assertion_results.length}</strong> 项重点标的
          </span>
        </div>

        <div className="flex items-center gap-2">
          {safety_audit_passed && (
            <span className="flex items-center gap-1 text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-2 py-0.5 rounded text-[10px]">
              <ShieldCheck className="w-3 h-3" />
              规则校验完毕
            </span>
          )}
        </div>
      </footer>
    </div>
  );
};
