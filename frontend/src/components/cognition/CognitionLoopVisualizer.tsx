'use client';

import React, { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import {
  ShieldAlert,
  ShieldCheck,
  AlertOctagon,
  HelpCircle,
  Sparkles,
  RefreshCw,
  Fingerprint,
  Calendar,
  Layers,
  Activity,
  ArrowRight,
  TrendingUp,
  TrendingDown,
  Info,
  CheckCircle2,
  XCircle,
  MinusCircle
} from 'lucide-react';
import { api } from '@/lib/api';
import {
  CognitionReviewLoopData,
  TodayFactsDTO,
  TodayHypothesisDTO,
  YesterdayAdjudicationDTO,
  AssertionDTO,
  AdjudicationComparisonItem
} from '@/types/cognition';
import { formatDateWithWeekday } from '@/lib/utils';

interface CognitionLoopVisualizerProps {
  marketDate: string;
}

export function CognitionLoopVisualizer({ marketDate }: CognitionLoopVisualizerProps) {
  const [loopData, setLoopData] = useState<CognitionReviewLoopData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [proposing, setProposing] = useState<boolean>(false);
  const [proposeMsg, setProposeMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const fetchLoopData = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getCognitionReviewLoop(marketDate);
      setLoopData(res);
    } catch (err: any) {
      console.error('获取认知复盘闭环失败:', err);
      setError(err.message || '获取认知闭环数据失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (marketDate) {
      fetchLoopData();
    }
  }, [marketDate]);

  const handleProposeToday = async () => {
    if (proposing) return;
    try {
      setProposing(true);
      setProposeMsg(null);
      await api.proposeTodayHypothesis({ market_date: marketDate });
      setProposeMsg({ type: 'success', text: '收盘 AI 假说推演成功已生成并锁定 WORM' });
      await fetchLoopData();
    } catch (err: any) {
      console.error('推演假说失败:', err);
      setProposeMsg({ type: 'error', text: err.message || '假说生成失败' });
    } finally {
      setProposing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 rounded-xl bg-slate-900/40 border border-slate-800">
        <RefreshCw className="w-5 h-5 animate-spin text-cyan-400 mr-2" />
        <span className="text-sm text-slate-400">正在聚合认知闭环数据...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 rounded-xl bg-rose-950/30 border border-rose-800/50 flex items-center justify-between text-rose-300 text-sm">
        <div className="flex items-center gap-2">
          <AlertOctagon className="w-4 h-4 text-rose-400" />
          <span>{error}</span>
        </div>
        <button
          onClick={fetchLoopData}
          className="text-xs px-2.5 py-1 rounded bg-rose-900/60 hover:bg-rose-900 text-white transition flex items-center gap-1"
        >
          <RefreshCw className="w-3 h-3" /> 重试
        </button>
      </div>
    );
  }

  if (!loopData) return null;

  const { today_facts, today_hypothesis, yesterday_adjudication } = loopData;

  return (
    <div className="space-y-6">
      {/* 顶部标题与科学免责声明 */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-2 border-b border-slate-800 gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse" />
            <h3 className="text-lg font-bold text-slate-100">
              认知复盘闭环实验场 (Cognition Review Loop)
            </h3>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800/60">
              Phase 2B.3 Baseline
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            严守事实与假说边界：客观事实不可篡改，推演假说刚性受限，次日数据驱动自动证伪裁决。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchLoopData}
            className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition flex items-center gap-1.5 border border-slate-700"
          >
            <RefreshCw className="w-3.5 h-3.5" /> 刷新闭环
          </button>
        </div>
      </div>

      {proposeMsg && (
        <div
          className={`p-3 rounded-lg text-xs flex items-center justify-between border ${
            proposeMsg.type === 'success'
              ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300'
              : 'bg-rose-950/40 border-rose-800/60 text-rose-300'
          }`}
        >
          <span>{proposeMsg.text}</span>
          <button onClick={() => setProposeMsg(null)} className="text-slate-400 hover:text-white">✕</button>
        </div>
      )}

      {/* 三核心卡片网格布局 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 卡片 ①：今日事实卡 (Today's Facts) */}
        <TodayFactsCard facts={today_facts} marketDate={marketDate} />

        {/* 卡片 ②：今日 AI 假说卡 (Today's AI Hypothesis) */}
        <TodayHypothesisCard
          hypothesis={today_hypothesis}
          marketDate={marketDate}
          onPropose={handleProposeToday}
          proposing={proposing}
        />

        {/* 卡片 ③：昨日假说裁决卡 (Yesterday's Adjudication) */}
        <YesterdayAdjudicationCard adjudication={yesterday_adjudication} marketDate={marketDate} />
      </div>
    </div>
  );
}

// =========================================================================
// 卡片 ①: 今日事实卡组件
// =========================================================================
function TodayFactsCard({ facts, marketDate }: { facts: TodayFactsDTO; marketDate: string }) {
  const { fact_layer, derived_state } = facts;

  return (
    <Card className="bg-slate-900/80 border-slate-800 shadow-md flex flex-col justify-between">
      <div>
        <CardHeader className="pb-3 border-b border-slate-800/80">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-md bg-blue-500/20 text-blue-400 flex items-center justify-center text-xs font-bold font-mono">
                1
              </span>
              <CardTitle className="text-base text-slate-100">今日事实卡</CardTitle>
            </div>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-blue-950/80 text-blue-300 border border-blue-800/50">
              {formatDateWithWeekday(marketDate)} 收盘
            </span>
          </div>
          <div className="text-[11px] text-slate-400 flex items-center gap-1 mt-1">
            <ShieldCheck className="w-3.5 h-3.5 text-blue-400" />
            客观数据事实层 · 严禁主观加工
          </div>
        </CardHeader>

        <CardContent className="pt-4 space-y-4">
          {/* 1. 客观指数事实 (Fact Layer - Indices) */}
          <div>
            <div className="text-xs font-semibold text-slate-400 mb-2 flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-blue-400" />
              核心指数物理表现
            </div>
            {fact_layer.indices && fact_layer.indices.length > 0 ? (
              <div className="grid grid-cols-2 gap-2">
                {fact_layer.indices.map((idx) => {
                  const pct = idx.pct_change;
                  const isUp = pct !== null && pct > 0;
                  const isDown = pct !== null && pct < 0;
                  return (
                    <div
                      key={idx.code}
                      className="p-2 rounded-lg bg-slate-950/60 border border-slate-800 flex flex-col justify-between"
                    >
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-slate-300 font-medium truncate">{idx.name}</span>
                        <span className="text-[10px] text-slate-500 font-mono">{idx.code}</span>
                      </div>
                      <div className="flex items-baseline justify-between mt-1">
                        <span className="text-xs font-mono text-slate-300">
                          {idx.price !== null ? idx.price.toFixed(2) : <span className="text-slate-500">N/A</span>}
                        </span>
                        <span
                          className={`text-xs font-mono font-bold ${
                            isUp ? 'text-rose-400' : isDown ? 'text-emerald-400' : 'text-slate-400'
                          }`}
                        >
                          {pct !== null ? `${pct > 0 ? '+' : ''}${pct.toFixed(2)}%` : <span className="text-slate-500">N/A</span>}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="p-3 rounded-lg bg-slate-950/40 border border-dashed border-slate-800 text-center text-xs text-slate-500">
                暂无指数行情数据 (Missing)
              </div>
            )}
          </div>

          {/* 2. 市场情绪物理统计 (Fact Layer - Sentiment) */}
          <div>
            <div className="text-xs font-semibold text-slate-400 mb-2 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-blue-400" />
              极端博弈与空间高度
            </div>
            <div className="grid grid-cols-3 gap-2">
              <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800 text-center">
                <div className="text-[10px] text-slate-400">涨停家数</div>
                <div className="text-sm font-mono font-bold text-rose-400 mt-0.5">
                  {fact_layer.sentiment.limit_up_count !== null ? `${fact_layer.sentiment.limit_up_count} 家` : <span className="text-slate-500">N/A</span>}
                </div>
              </div>
              <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800 text-center">
                <div className="text-[10px] text-slate-400">跌停家数</div>
                <div className="text-sm font-mono font-bold text-emerald-400 mt-0.5">
                  {fact_layer.sentiment.limit_down_count !== null ? `${fact_layer.sentiment.limit_down_count} 家` : <span className="text-slate-500">N/A</span>}
                </div>
              </div>
              <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800 text-center">
                <div className="text-[10px] text-slate-400">最高连板</div>
                <div className="text-sm font-mono font-bold text-amber-400 mt-0.5">
                  {fact_layer.sentiment.max_board_height !== null ? `${fact_layer.sentiment.max_board_height} 板` : <span className="text-slate-500">N/A</span>}
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 mt-2">
              <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800 flex items-center justify-between text-xs">
                <span className="text-slate-400 text-[11px]">炸板家数</span>
                <span className="font-mono text-slate-200">
                  {fact_layer.sentiment.broken_limit_count !== null ? `${fact_layer.sentiment.broken_limit_count} 家` : <span className="text-slate-500">N/A</span>}
                </span>
              </div>
              <div className="p-2 rounded-lg bg-slate-950/60 border border-slate-800 flex items-center justify-between text-xs">
                <span className="text-slate-400 text-[11px]">炸板率</span>
                <span className="font-mono text-amber-300">
                  {fact_layer.sentiment.broken_ratio !== null ? `${(fact_layer.sentiment.broken_ratio * 100).toFixed(1)}%` : <span className="text-slate-500">N/A</span>}
                </span>
              </div>
            </div>
          </div>

          {/* 3. 市场广度 (Fact Layer - Breadth) */}
          <div>
            <div className="text-xs font-semibold text-slate-400 mb-1.5 flex items-center justify-between">
              <span>全市场涨跌广度</span>
              <span className="text-[10px] font-mono text-slate-500">
                {fact_layer.breadth.up_count !== null && fact_layer.breadth.down_count !== null
                  ? `${fact_layer.breadth.up_count}涨 / ${fact_layer.breadth.down_count}跌`
                  : 'N/A'}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-1.5 text-center text-xs font-mono">
              <div className="p-1.5 rounded bg-rose-950/30 border border-rose-900/40 text-rose-300">
                涨 {fact_layer.breadth.up_count !== null ? fact_layer.breadth.up_count : 'N/A'}
              </div>
              <div className="p-1.5 rounded bg-slate-800/50 border border-slate-700/50 text-slate-400">
                平 {fact_layer.breadth.flat_count !== null ? fact_layer.breadth.flat_count : 'N/A'}
              </div>
              <div className="p-1.5 rounded bg-emerald-950/30 border border-emerald-900/40 text-emerald-300">
                跌 {fact_layer.breadth.down_count !== null ? fact_layer.breadth.down_count : 'N/A'}
              </div>
            </div>
          </div>

          {/* 4. 派生状态层 (Derived State Layer - 视觉明确隔离) */}
          <div className="p-3 rounded-lg bg-indigo-950/20 border border-indigo-800/40 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold font-mono px-1.5 py-0.5 rounded bg-indigo-900/60 text-indigo-300">
                DERIVED STATE (派生状态)
              </span>
              <span className="text-[10px] font-mono text-slate-400">
                算法配置: {derived_state.config_version}
              </span>
            </div>
            <div className="flex items-center justify-between pt-1">
              <span className="text-xs text-slate-300">市场状态标签</span>
              <span className="text-xs font-bold text-indigo-200 px-2 py-0.5 rounded bg-indigo-950 border border-indigo-700/50">
                {derived_state.state_label}
              </span>
            </div>
            <div className="text-[10px] text-slate-500 pt-0.5">
              * 注：派生状态系模型规则推导标签，非物理事实；第一版不包含未冻结综合评分。
            </div>
          </div>
        </CardContent>
      </div>

      {/* 5. 事实层最小审计底栏 (Audit Footer) */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-950/40 text-[10px] font-mono text-slate-500 space-y-1">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1">
            <Fingerprint className="w-3 h-3 text-slate-400" />
            快照指纹: {facts.fact_snapshot_hash || 'N/A'}
          </span>
          <span>质量: {facts.data_quality || 'GOOD'}</span>
        </div>
        <div className="flex items-center justify-between text-slate-500">
          <span>观测时间: {facts.observation_timestamp || `${marketDate}T15:00:00`}</span>
          <span>完整度: {facts.completeness !== null && facts.completeness !== undefined ? `${(facts.completeness * 100).toFixed(0)}%` : '100%'}</span>
        </div>
      </div>
    </Card>
  );
}

// =========================================================================
// 卡片 ②: 今日 AI 假说卡组件
// =========================================================================
function TodayHypothesisCard({
  hypothesis,
  marketDate,
  onPropose,
  proposing
}: {
  hypothesis: TodayHypothesisDTO | null;
  marketDate: string;
  onPropose: () => void;
  proposing: boolean;
}) {
  return (
    <Card className="bg-slate-900/80 border-slate-800 shadow-md flex flex-col justify-between">
      <div>
        <CardHeader className="pb-3 border-b border-slate-800/80">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-md bg-purple-500/20 text-purple-400 flex items-center justify-center text-xs font-bold font-mono">
                2
              </span>
              <CardTitle className="text-base text-slate-100">今日 AI 假说卡</CardTitle>
            </div>
            {hypothesis ? (
              <span className="text-[11px] font-bold px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                待验证 (PENDING)
              </span>
            ) : (
              <span className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                未生成
              </span>
            )}
          </div>
          <div className="text-[11px] text-amber-400/90 flex items-center gap-1 mt-1 bg-amber-950/20 px-2 py-1 rounded border border-amber-900/40">
            <Info className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" />
            <span>可证伪认知假说 · 严禁视为投资建议或交易信号</span>
          </div>
        </CardHeader>

        <CardContent className="pt-4 space-y-4">
          {hypothesis ? (
            <>
              {/* 假说主体信息 */}
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">假说类型</span>
                  <span className="font-mono font-semibold text-purple-300">
                    {hypothesis.hypothesis_type}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">观察目标</span>
                  <span className="text-slate-200">{hypothesis.target_asset}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">推演剧本</span>
                  <span className="px-1.5 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-800/50 text-[11px] font-mono">
                    {hypothesis.expected_scenario}
                  </span>
                </div>
                <div className="text-xs pt-1 border-t border-slate-800/60">
                  <div className="text-[11px] text-slate-400 mb-0.5">推演前提逻辑 (Premise):</div>
                  <div className="text-slate-200 text-xs bg-slate-900/90 p-2 rounded border border-slate-800/60">
                    {hypothesis.premise_logic}
                  </div>
                </div>
              </div>

              {/* 预期满足断言 (Expected Assertions) */}
              <div>
                <div className="text-xs font-semibold text-slate-300 mb-1.5 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-purple-400" />
                  预期满足条件 (Expected Assertions)
                </div>
                {hypothesis.expected_assertions && hypothesis.expected_assertions.length > 0 ? (
                  <div className="space-y-1.5">
                    {hypothesis.expected_assertions.map((a) => (
                      <div
                        key={a.assertion_id}
                        className="p-2 rounded-lg bg-slate-950/60 border border-slate-800 text-xs font-mono flex items-center justify-between"
                      >
                        <div className="flex items-center gap-1.5">
                          <span className="text-purple-300 font-semibold">{a.metric_type}</span>
                          <span className="text-slate-500">({a.target_code})</span>
                        </div>
                        <div className="text-slate-200">
                          {a.operator} {String(a.threshold)}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-slate-500 italic p-2 bg-slate-950/40 rounded border border-slate-800">
                    {hypothesis.expected_phenomenon || '无结构化断言'}
                  </div>
                )}
              </div>

              {/* 刚性证伪红线 (Invalidation Assertions - 核心高亮警示) */}
              <div className="p-3 rounded-lg bg-rose-950/20 border-2 border-rose-800/70 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-rose-300">
                    <ShieldAlert className="w-4 h-4 text-rose-400" />
                    刚性证伪红线 (Invalidation Boundary)
                  </div>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-rose-900/60 text-rose-200">
                    触碰即判假
                  </span>
                </div>
                {hypothesis.invalidation_assertions && hypothesis.invalidation_assertions.length > 0 ? (
                  <div className="space-y-1.5">
                    {hypothesis.invalidation_assertions.map((a) => (
                      <div
                        key={a.assertion_id}
                        className="p-2 rounded bg-rose-950/50 border border-rose-900/50 text-xs font-mono flex items-center justify-between text-rose-200"
                      >
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-rose-300">{a.metric_type}</span>
                          <span className="text-rose-400/60">({a.target_code})</span>
                        </div>
                        <div className="font-bold">
                          {a.operator} {String(a.threshold)}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-xs text-rose-300/80 p-2 bg-rose-950/40 rounded border border-rose-900/30">
                    {hypothesis.invalidation_condition}
                  </div>
                )}
                <div className="text-[10px] text-rose-400/70 pt-0.5">
                  次日收盘时若满足上述任一条件，假说立即被 FalsificationEngine 证伪短路。
                </div>
              </div>
            </>
          ) : (
            <div className="py-8 text-center space-y-3">
              <div className="w-12 h-12 rounded-full bg-purple-950/60 text-purple-400 flex items-center justify-center mx-auto border border-purple-800/50">
                <Sparkles className="w-6 h-6" />
              </div>
              <div className="space-y-1">
                <div className="text-sm font-semibold text-slate-200">
                  今日尚未生成 AI 认知假说
                </div>
                <div className="text-xs text-slate-400 max-w-xs mx-auto">
                  可基于今日收盘物理事实与 PromptSpec v1.1.0 契约触发受约束模型提议生成。
                </div>
              </div>
              <button
                onClick={onPropose}
                disabled={proposing}
                className="text-xs px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-medium transition flex items-center gap-1.5 mx-auto shadow-sm"
              >
                {proposing ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    大模型推演校验中...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5" />
                    触发收盘 AI 推演 (Sandbox)
                  </>
                )}
              </button>
            </div>
          )}
        </CardContent>
      </div>

      {/* 假说审计元数据底栏 */}
      {hypothesis && (
        <div className="p-3 border-t border-slate-800/80 bg-slate-950/40 text-[10px] font-mono text-slate-500 space-y-1">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1">
              <Calendar className="w-3 h-3 text-slate-400" />
              目标验证日: {formatDateWithWeekday(hypothesis.target_date)}
            </span>
            <span>模型: {hypothesis.meta.model_name}</span>
          </div>
          <div className="flex items-center justify-between text-slate-500">
            <span className="truncate max-w-[180px]">
              指纹: {hypothesis.meta.hypothesis_hash || `hypo-${hypothesis.id}`}
            </span>
            <span>契约: {hypothesis.meta.prompt_spec_version}</span>
          </div>
        </div>
      )}
    </Card>
  );
}

// =========================================================================
// 卡片 ③: 昨日假说裁决卡组件
// =========================================================================
function YesterdayAdjudicationCard({
  adjudication,
  marketDate
}: {
  adjudication: YesterdayAdjudicationDTO | null;
  marketDate: string;
}) {
  return (
    <Card className="bg-slate-900/80 border-slate-800 shadow-md flex flex-col justify-between">
      <div>
        <CardHeader className="pb-3 border-b border-slate-800/80">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-md bg-emerald-500/20 text-emerald-400 flex items-center justify-center text-xs font-bold font-mono">
                3
              </span>
              <CardTitle className="text-base text-slate-100">昨日假说裁决卡</CardTitle>
            </div>
            {adjudication ? (
              <OutcomeBadge outcome={adjudication.outcome} />
            ) : (
              <span className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                无昨日假说
              </span>
            )}
          </div>
          <div className="text-[11px] text-slate-400 flex items-center gap-1 mt-1">
            <Activity className="w-3.5 h-3.5 text-emerald-400" />
            认知记忆单元 · 昨日预期 vs 今日客观事实裁决
          </div>
        </CardHeader>

        <CardContent className="pt-4 space-y-4">
          {adjudication ? (
            <>
              {/* 假说溯源信息 */}
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">昨日假说提出日</span>
                  <span className="font-mono text-slate-200">{formatDateWithWeekday(adjudication.created_date)}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">假说类型</span>
                  <span className="font-mono text-purple-300">{adjudication.hypothesis_type}</span>
                </div>
                <div className="text-xs pt-1 border-t border-slate-800/60">
                  <div className="text-[11px] text-slate-400 mb-0.5">昨日提出的逻辑:</div>
                  <div className="text-slate-200 text-xs bg-slate-900/90 p-2 rounded border border-slate-800/60">
                    {adjudication.premise_logic}
                  </div>
                </div>
              </div>

              {/* 裁决细节或打脸证据链 */}
              <div
                className={`p-3 rounded-lg border text-xs ${
                  adjudication.outcome === 'CONFIRMED'
                    ? 'bg-emerald-950/20 border-emerald-800/50 text-emerald-300'
                    : adjudication.outcome === 'FALSIFIED'
                    ? 'bg-rose-950/30 border-rose-800/60 text-rose-200'
                    : 'bg-slate-950/40 border-slate-800 text-slate-300'
                }`}
              >
                <div className="font-semibold mb-1 flex items-center gap-1">
                  {adjudication.outcome === 'FALSIFIED' ? (
                    <>
                      <AlertOctagon className="w-4 h-4 text-rose-400" />
                      证伪红线已触发 (Falsified Triggered)
                    </>
                  ) : adjudication.outcome === 'CONFIRMED' ? (
                    <>
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      预期达成确证 (Hypothesis Confirmed)
                    </>
                  ) : (
                    <>
                      <HelpCircle className="w-4 h-4 text-slate-400" />
                      证据未决或数据缺失 (Inconclusive)
                    </>
                  )}
                </div>
                <p className="text-[11px] leading-relaxed opacity-90">
                  {adjudication.details || '系统已完成客观指标对比求值'}
                </p>
              </div>

              {/* 指标对比矩阵 (Comparison Matrix) */}
              <div>
                <div className="text-xs font-semibold text-slate-300 mb-2 flex items-center justify-between">
                  <span>指标比对矩阵 (Comparison Matrix)</span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {adjudication.comparison_matrix.length} 项断言
                  </span>
                </div>
                {adjudication.comparison_matrix.length > 0 ? (
                  <div className="space-y-1.5">
                    {adjudication.comparison_matrix.map((item, idx) => (
                      <ComparisonItemRow key={`${item.assertion_id}-${idx}`} item={item} />
                    ))}
                  </div>
                ) : (
                  <div className="p-3 text-center text-xs text-slate-500 bg-slate-950/40 rounded border border-slate-800">
                    暂无比对指标项 (Missing Data)
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="py-12 text-center space-y-2">
              <div className="w-10 h-10 rounded-full bg-slate-800/80 text-slate-500 flex items-center justify-center mx-auto">
                <MinusCircle className="w-5 h-5" />
              </div>
              <div className="text-xs text-slate-400">
                前一交易日尚未建立针对今日 ({marketDate}) 的推演假说
              </div>
              <div className="text-[11px] text-slate-500">
                今日无法生成事后证伪裁决。系统将在次日收盘后裁决今日假说。
              </div>
            </div>
          )}
        </CardContent>
      </div>

      {/* 裁决底栏 */}
      {adjudication && (
        <div className="p-3 border-t border-slate-800/80 bg-slate-950/40 text-[10px] font-mono text-slate-500 flex items-center justify-between">
          <span>假说单据: #{adjudication.hypothesis_id}</span>
          <span>验证时点: 收盘 15:30 (CLOSE)</span>
        </div>
      )}
    </Card>
  );
}

// 裁决状态徽章 (严格保持三态)
function OutcomeBadge({ outcome }: { outcome: 'CONFIRMED' | 'FALSIFIED' | 'INCONCLUSIVE' }) {
  switch (outcome) {
    case 'CONFIRMED':
      return (
        <span className="text-xs font-bold font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 flex items-center gap-1">
          <CheckCircle2 className="w-3 h-3" /> CONFIRMED
        </span>
      );
    case 'FALSIFIED':
      return (
        <span className="text-xs font-bold font-mono px-2 py-0.5 rounded bg-rose-500/20 text-rose-400 border border-rose-500/40 flex items-center gap-1">
          <XCircle className="w-3 h-3" /> FALSIFIED
        </span>
      );
    case 'INCONCLUSIVE':
    default:
      return (
        <span className="text-xs font-bold font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 flex items-center gap-1">
          <HelpCircle className="w-3 h-3" /> INCONCLUSIVE
        </span>
      );
  }
}

// 对比矩阵单行组件
function ComparisonItemRow({ item }: { item: AdjudicationComparisonItem }) {
  const isInvalidation = item.kind === 'INVALIDATION';
  const hasActual = item.actual_value !== null && item.actual_value !== undefined;

  return (
    <div
      className={`p-2 rounded-lg border text-xs font-mono flex items-center justify-between ${
        isInvalidation
          ? 'bg-rose-950/20 border-rose-900/40'
          : 'bg-slate-950/60 border-slate-800'
      }`}
    >
      <div className="flex items-center gap-2">
        <span
          className={`text-[10px] px-1 py-0.5 rounded font-bold ${
            isInvalidation
              ? 'bg-rose-900/60 text-rose-300'
              : 'bg-purple-900/60 text-purple-300'
          }`}
        >
          {item.kind}
        </span>
        <span className="text-slate-300 font-medium">{item.metric_type}</span>
      </div>

      <div className="flex items-center gap-3">
        <div className="text-slate-400 text-[11px]">
          门槛: {item.operator} {String(item.threshold)}
        </div>
        <div className="flex items-center gap-1">
          <span className="text-slate-500">实际:</span>
          <span
            className={`font-bold ${
              !hasActual
                ? 'text-slate-500'
                : item.is_satisfied
                ? isInvalidation
                  ? 'text-rose-400'
                  : 'text-emerald-400'
                : 'text-slate-300'
            }`}
          >
            {hasActual ? item.actual_value : 'N/A'}
          </span>
        </div>
        <div>
          {item.is_satisfied ? (
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                isInvalidation
                  ? 'bg-rose-500/20 text-rose-400'
                  : 'bg-emerald-500/20 text-emerald-400'
              }`}
            >
              {isInvalidation ? '触发证伪' : '满足预期'}
            </span>
          ) : (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
              未触发
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
