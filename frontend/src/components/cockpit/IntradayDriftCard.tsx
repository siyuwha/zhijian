'use client';

import React from 'react';
import {
  IntradayDriftVerdict,
  DriftStateEnum,
  IntradayStageEnum,
  DriftEventCategoryEnum,
} from '@/types/canonical';
import {
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  Activity,
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
  Clock,
  Compass,
  Crown,
} from 'lucide-react';

interface IntradayDriftCardProps {
  verdict: IntradayDriftVerdict | null;
  isLoading?: boolean;
  errorMsg?: string | null;
  onRefresh?: () => void;
  compact?: boolean;
  onOpenDetailsModal?: () => void;
}

export const IntradayDriftCard: React.FC<IntradayDriftCardProps> = ({
  verdict,
  isLoading = false,
  errorMsg = null,
  onRefresh,
  compact = false,
  onOpenDetailsModal,
}) => {
  if (isLoading) {
    return (
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col items-center justify-center min-h-[240px] text-slate-400 gap-3">
        <RefreshCw className="w-6 h-6 animate-spin text-cyan-400" />
        <span className="text-xs font-mono tracking-wide">
          正在获取盘中微观行情切片并执行 4 阶段动态波普尔偏离判定...
        </span>
      </div>
    );
  }

  if (errorMsg) {
    const isSafetyInterception =
      errorMsg.includes('ERR_INTRADAY_SAFETY_INTERCEPTION') ||
      errorMsg.includes('compliance') ||
      errorMsg.includes('security');

    return (
      <div className="bg-slate-900/90 border border-rose-900/50 rounded-xl p-5 shadow-lg flex flex-col items-center justify-center min-h-[240px] text-slate-300 gap-3">
        {isSafetyInterception ? (
          <>
            <ShieldAlert className="w-9 h-9 text-rose-400" />
            <div className="text-center">
              <p className="text-sm font-bold text-rose-300 font-mono">
                安全合规审查物理拦截 (ERR_INTRADAY_SAFETY_INTERCEPTION)
              </p>
              <p className="text-xs text-rose-400/80 mt-1">
                检测到交易诱导指令或非法行动边界，已触发物理级脱敏拒止保护，零违规信息外泄。
              </p>
            </div>
          </>
        ) : (
          <>
            <AlertOctagon className="w-8 h-8 text-rose-400" />
            <p className="text-xs font-semibold text-rose-300">{errorMsg}</p>
          </>
        )}
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
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-lg flex flex-col items-center justify-center min-h-[240px] text-slate-500 gap-2">
        <HelpCircle className="w-7 h-7 text-slate-600" />
        <span className="text-xs">暂无盘中认知偏离判定数据 (请确认是否为有效交易时段)</span>
      </div>
    );
  }

  const {
    overall_drift_state,
    inconclusive_reason,
    verdict_headline,
    stage,
    elapsed_trading_minutes,
    detected_drift_events = [],
    assertion_results = [],
    preservation_boundaries = [],
    evaluated_at,
    trade_date,
    trace_id,
    hypothesis_id,
    rule_version,
    verdict_fingerprint,
    safety_audit_passed,
  } = verdict;

  const isMarketClosed = inconclusive_reason === 'MARKET_CLOSED';

  // 阶段显示与徽章
  const getStageInfo = (stg: IntradayStageEnum) => {
    switch (stg) {
      case 'STAGE_1_OPENING':
        return {
          label: '09:30-10:00 开盘分歧期',
          code: 'STAGE_1',
          badgeClass: 'bg-indigo-950/80 text-indigo-300 border-indigo-800/80',
        };
      case 'STAGE_2_MORNING':
        return {
          label: '10:00-11:30 主线定型期',
          code: 'STAGE_2',
          badgeClass: 'bg-cyan-950/80 text-cyan-300 border-cyan-800/80',
        };
      case 'LUNCH_BREAK':
        return {
          label: '11:30-13:00 午间休市',
          code: 'LUNCH',
          badgeClass: 'bg-slate-800/80 text-slate-300 border-slate-700/80',
        };
      case 'STAGE_3_AFTERNOON':
        return {
          label: '13:00-14:30 情绪拐点期',
          code: 'STAGE_3',
          badgeClass: 'bg-purple-950/80 text-purple-300 border-purple-800/80',
        };
      case 'STAGE_4_CLOSING':
        return {
          label: '14:30-15:00 尾盘博弈期',
          code: 'STAGE_4',
          badgeClass: 'bg-orange-950/80 text-orange-300 border-orange-800/80',
        };
      case 'OFF_MARKET':
      default:
        return {
          label: '非交易时段 / 休市',
          code: 'OFF_MARKET',
          badgeClass: 'bg-slate-800/80 text-slate-400 border-slate-700/80',
        };
    }
  };

  const stageInfo = getStageInfo(stage);

  // 综合定调徽章样式映射
  const getOutcomeBadge = () => {
    switch (overall_drift_state) {
      case 'NORMAL':
        return {
          icon: <CheckCircle2 className="w-4 h-4 text-emerald-400" />,
          label: '假说吻合 · NORMAL',
          subLabel: '盘面演进吻合预设',
          badgeClass: 'bg-emerald-950/80 text-emerald-300 border-emerald-800/80',
          borderClass: 'border-emerald-900/40',
        };
      case 'DRIFT_WARNING':
        return {
          icon: <AlertTriangle className="w-4 h-4 text-amber-400" />,
          label: '偏离预警 · DRIFT_WARNING',
          subLabel: '中度偏离 / 关注量能与主线',
          badgeClass: 'bg-amber-950/80 text-amber-300 border-amber-800/80',
          borderClass: 'border-amber-900/40',
        };
      case 'CRITICAL_BREACH':
        return {
          icon: <XCircle className="w-4 h-4 text-rose-400" />,
          label: '刚性破位 · CRITICAL_BREACH',
          subLabel: '空间标杆炸板 / 一票否决',
          badgeClass: 'bg-rose-950/80 text-rose-300 border-rose-800/80',
          borderClass: 'border-rose-900/50',
        };
      case 'INCONCLUSIVE':
      default:
        return {
          icon: <HelpCircle className="w-4 h-4 text-slate-400" />,
          label: isMarketClosed ? '休市停牌 · MARKET CLOSED' : '证据不足 · INCONCLUSIVE',
          subLabel: isMarketClosed ? '物理行情未开启' : '触发数据质量保护',
          badgeClass: 'bg-slate-800/80 text-slate-300 border-slate-700/80',
          borderClass: 'border-slate-800',
        };
    }
  };

  const badge = getOutcomeBadge();

  // 异动事件映射
  const getEventBadge = (event: DriftEventCategoryEnum) => {
    switch (event) {
      case 'SPACE_LEADER_COLLAPSE':
        return {
          icon: <Crown className="w-3.5 h-3.5 text-rose-400" />,
          label: '空间标杆崩塌 (CRITICAL_KILL)',
          badgeClass: 'bg-rose-950/70 text-rose-300 border-rose-800/70',
        };
      case 'MAINLINE_TOTAL_REVERSAL':
        return {
          icon: <Layers className="w-3.5 h-3.5 text-amber-400" />,
          label: '主线集体倒戈 (MODERATE)',
          badgeClass: 'bg-amber-950/70 text-amber-300 border-amber-800/70',
        };
      case 'LIQUIDITY_FLASH_DRY':
        return {
          icon: <Activity className="w-3.5 h-3.5 text-amber-400" />,
          label: '量能断崖衰减 (MODERATE)',
          badgeClass: 'bg-amber-950/70 text-amber-300 border-amber-800/70',
        };
      case 'BREADTH_PANIC_DIVERGENCE':
        return {
          icon: <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />,
          label: '炸板恐慌分化 (MODERATE)',
          badgeClass: 'bg-amber-950/70 text-amber-300 border-amber-800/70',
        };
      default:
        return {
          icon: <AlertTriangle className="w-3.5 h-3.5 text-slate-400" />,
          label: String(event),
          badgeClass: 'bg-slate-800 text-slate-300 border-slate-700',
        };
    }
  };

  return (
    <div
      className={`bg-slate-900/90 border ${badge.borderClass} rounded-xl p-5 shadow-lg flex flex-col justify-between transition-all`}
    >
      <div>
        {/* 卡片顶部标头 */}
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-3 mb-3">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-cyan-950/80 text-cyan-400 border border-cyan-800/80">
              <Compass className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-slate-200 tracking-wide">
                  盘中 4 阶段动态跟踪与认知偏离实时告警
                </span>
                <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/60 border border-cyan-800/60 px-1.5 py-0.2 rounded">
                  {trade_date}
                </span>
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded border font-semibold ${stageInfo.badgeClass}`}
                >
                  {stageInfo.label}
                </span>
                <span className="text-[10px] font-mono text-slate-400 bg-slate-800/80 px-1.5 py-0.2 rounded border border-slate-700">
                  已交易 {elapsed_trading_minutes} / 240 分钟
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {onRefresh && (
              <button
                onClick={onRefresh}
                className="p-1 text-slate-400 hover:text-slate-200 transition"
                title="刷新偏离判定"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
            )}
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md border text-xs font-bold font-mono ${badge.badgeClass}`}
            >
              {badge.icon}
              <span>{badge.label}</span>
            </div>
          </div>
        </div>

        {/* 综合全貌结论 Headline Banner */}
        <div className="mb-3.5 p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 flex items-start gap-2.5">
          <div className="mt-0.5 shrink-0">
            {overall_drift_state === 'CRITICAL_BREACH' ? (
              <XCircle className="w-4 h-4 text-rose-400" />
            ) : overall_drift_state === 'DRIFT_WARNING' ? (
              <AlertTriangle className="w-4 h-4 text-amber-400" />
            ) : (
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs text-slate-200 font-medium leading-relaxed">
              {verdict_headline}
            </p>
            <div className="flex items-center gap-2 mt-1 text-[10px] font-mono text-slate-500">
              <span>评估时点: {evaluated_at.replace('T', ' ')}</span>
              <span>·</span>
              <span>细分原因: {inconclusive_reason || 'N/A'}</span>
            </div>
          </div>
        </div>

        {/* 检测到的突发异动事件流 */}
        <div className="mb-3.5">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-semibold text-slate-400 flex items-center gap-1">
              <Flame className="w-3.5 h-3.5 text-rose-400" />
              突发偏离异动事件检测
            </span>
            <span className="text-[10px] font-mono text-slate-500">
              {detected_drift_events.length > 0
                ? `检测到 ${detected_drift_events.length} 项异动`
                : '盘中无突发异动'}
            </span>
          </div>
          {detected_drift_events.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {detected_drift_events.map((evt, idx) => {
                const eb = getEventBadge(evt);
                return (
                  <div
                    key={idx}
                    className={`flex items-center gap-1 px-2.5 py-1 rounded border text-xs font-mono font-medium ${eb.badgeClass}`}
                  >
                    {eb.icon}
                    <span>{eb.label}</span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="p-2 rounded bg-slate-950/40 border border-slate-800/60 text-center text-xs text-slate-500 font-mono">
              盘中微观指标均在预设公差容忍区间内，未触发阈值异动
            </div>
          )}
        </div>

        {/* 四大微观客观断言证据链 */}
        {!compact && assertion_results.length > 0 && (
          <div className="mb-3.5">
            <span className="text-[11px] font-semibold text-slate-400 flex items-center gap-1 mb-2">
              <Activity className="w-3.5 h-3.5 text-indigo-400" />
              四大微观客观断言裁判明细
            </span>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {assertion_results.map((rule, idx) => {
                const isViolated = rule.is_violated;
                const isCritical = rule.severity === 'CRITICAL_KILL';

                return (
                  <div
                    key={idx}
                    className={`p-2.5 rounded-lg border text-xs flex flex-col justify-between gap-1.5 ${
                      isViolated
                        ? isCritical
                          ? 'bg-rose-950/30 border-rose-900/50 text-rose-200'
                          : 'bg-amber-950/30 border-amber-900/50 text-amber-200'
                        : 'bg-slate-950/40 border-slate-800/60 text-slate-300'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold font-mono text-[11px] text-slate-200">
                        {rule.rule_name}
                      </span>
                      <span
                        className={`text-[10px] font-mono px-1.5 py-0.2 rounded border font-semibold ${
                          isViolated
                            ? isCritical
                              ? 'bg-rose-950 text-rose-300 border-rose-800'
                              : 'bg-amber-950 text-amber-300 border-amber-800'
                            : 'bg-emerald-950 text-emerald-300 border-emerald-800'
                        }`}
                      >
                        {isViolated ? (isCritical ? 'CRITICAL_KILL' : 'VIOLATED') : 'ALIGNED'}
                      </span>
                    </div>
                    <div className="text-[10px] font-mono text-slate-400 flex flex-col gap-0.5">
                      <div>标的/板块: {rule.target_entity}</div>
                      <div>观测事实: {rule.actual_observation}</div>
                      <div>预设门槛: {rule.expected_condition}</div>
                    </div>
                    <div className="text-[10px] text-slate-400/90 pt-1 border-t border-slate-800/60 leading-tight">
                      {rule.deviation_analysis}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* 封闭安全防守行动边界 */}
        <div className="mb-3">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-semibold text-slate-400 flex items-center gap-1">
              <Lock className="w-3.5 h-3.5 text-cyan-400" />
              客观防守行动边界 (封闭词库 · 严禁买卖诱导)
            </span>
            <span className="text-[10px] font-mono text-cyan-500/80">
              {preservation_boundaries.length} 项纪律
            </span>
          </div>
          <div className="space-y-1.5">
            {preservation_boundaries.map((boundary, idx) => (
              <div
                key={idx}
                className="p-2 rounded-md bg-slate-950/60 border border-slate-800/80 flex items-center gap-2 text-xs font-mono text-slate-300"
              >
                <ShieldCheck className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                <span className="leading-tight">{boundary}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 底部防伪水印栏 */}
      <div className="pt-2.5 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono text-slate-500">
        <div className="flex items-center gap-2">
          <Fingerprint className="w-3.5 h-3.5 text-slate-400" />
          <span>Trace: {trace_id.slice(0, 24)}...</span>
          <span>·</span>
          <span>指纹: {verdict_fingerprint.slice(0, 16)}...</span>
        </div>
        <div className="flex items-center gap-2">
          <span>假说: {hypothesis_id}</span>
          <span>·</span>
          <span>规则: {rule_version}</span>
          <span>·</span>
          <span className="text-emerald-500 font-semibold">
            {safety_audit_passed ? '安全守卫拦截审查通过' : '未通过审查'}
          </span>
        </div>
      </div>
    </div>
  );
};
