'use client';

import React, { useState } from 'react';
import { MainlineCandidate, LineageAccountingReport } from '@/types/canonical';
import { Compass, CheckCircle2, Filter, AlertTriangle, Share2, Sparkles } from 'lucide-react';

interface MainlineMatrixCardProps {
  mainlines: MainlineCandidate[];
  lineage: LineageAccountingReport;
  onOpenAudit: () => void;
}

export const MainlineMatrixCard: React.FC<MainlineMatrixCardProps> = ({
  mainlines,
  lineage,
  onOpenAudit,
}) => {
  const [selectedRank, setSelectedRank] = useState<number>(1);
  const currentMainline = mainlines.find((m) => m.rank === selectedRank) || mainlines[0];

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-lg flex flex-col h-full">
      {/* 头部标题与语义契约声明 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
        <div className="flex items-center gap-2">
          <span className="p-1 rounded bg-teal-500/20 text-teal-400">
            <Compass className="w-4 h-4" />
          </span>
          <span className="text-sm font-bold text-slate-200">
            问 4 · 主线候选与证据契约 (Candidates)
          </span>
          <span className="text-xs font-mono text-amber-300 bg-amber-950/60 border border-amber-800/80 px-1.5 py-0.5 rounded">
            PROVISIONAL 候选
          </span>
        </div>

        {/* 语义类型收口血缘标签 */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-teal-400 bg-teal-950/40 border border-teal-800/60 px-2 py-0.5 rounded flex items-center gap-1">
            <Filter className="w-3 h-3" />
            已排除 {lineage.excluded_meta_tags_count} 元标签 / {lineage.solitary_leader_noise_count} 孤立单票
          </span>
          <button
            onClick={onOpenAudit}
            className="text-xs text-slate-400 hover:text-slate-200 underline transition"
          >
            血缘公式
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-3 mt-3 flex-1 overflow-hidden">
        {/* 左侧：Top 5 主线候选列表 (5 cols) */}
        <div className="md:col-span-5 flex flex-col gap-2 overflow-y-auto pr-1">
          {mainlines.map((m) => {
            const isSelected = m.rank === selectedRank;
            
            // 主线三级模型定性标签
            let tierBadgeText = 'Tier 2 分支轮动';
            let tierBadgeClass = 'bg-blue-950/60 text-blue-300 border-blue-800/60';
            if (m.thematic_tier === 'TIER_1_CORE' || m.structural_role === 'CORE_MAINLINE') {
              tierBadgeText = 'Tier 1 核心主线';
              tierBadgeClass = 'bg-red-950/60 text-red-300 border-red-800/60';
            } else if (m.thematic_tier === 'TIER_3_WEAK_OR_ISOLATED' || m.structural_role === 'WEAK_ROTATION_OR_ISOLATED') {
              tierBadgeText = 'Tier 3 弱轮动孤立';
              tierBadgeClass = 'bg-amber-950/60 text-amber-300 border-amber-800/60';
            } else if (m.is_thematic_frontier) {
              tierBadgeText = 'Tier 2 前沿催化';
              tierBadgeClass = 'bg-purple-950/60 text-purple-300 border-purple-800/60';
            }

            return (
              <button
                key={m.sector_code}
                onClick={() => setSelectedRank(m.rank)}
                className={`text-left p-2.5 rounded-lg border transition flex flex-col gap-1.5 ${
                  isSelected
                    ? 'bg-teal-950/30 border-teal-500/60 shadow-md ring-1 ring-teal-500/30'
                    : 'bg-slate-950/40 border-slate-800/80 hover:bg-slate-800/40'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-mono text-sm font-bold text-slate-400">
                      #{m.rank}
                    </span>
                    <span className="font-bold text-sm text-slate-100 flex items-center gap-1">
                      {m.market_narrative ? m.market_narrative.split(' ')[0] : m.sector_name}
                      {m.is_thematic_frontier && (
                        <span title="前沿细分催化题材保护">
                          <Sparkles className="w-3 h-3 text-purple-400 inline" />
                        </span>
                      )}
                    </span>
                    {m.market_narrative && m.market_narrative !== m.sector_name && (
                      <span className="text-xs text-slate-400 font-mono">
                        ({m.sector_name})
                      </span>
                    )}
                  </div>
                  <span className={`text-xs font-semibold px-1.5 py-0.5 rounded border whitespace-nowrap ${tierBadgeClass}`}>
                    {tierBadgeText}
                  </span>
                </div>

                <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
                  <span>
                    龙头: <span className="text-slate-200 font-semibold">{m.constituency.leader_name}</span> ({m.constituency.leader_height}B)
                  </span>
                  <span>共振 {m.constituency.limit_up_count} 只涨停</span>
                </div>
                {m.subtheme_catalysts && m.subtheme_catalysts.length > 0 && (
                  <div className="flex items-center gap-1 text-xs text-purple-300 bg-purple-950/40 border border-purple-800/40 px-1.5 py-0.5 rounded">
                    <Sparkles className="w-3 h-3 text-purple-400" />
                    <span>挂载: {m.subtheme_catalysts[0].sector_name} ({m.subtheme_catalysts[0].catalyst_height}B)</span>
                  </div>
                )}
              </button>
            );
          })}
        </div>

        {/* 右侧：所选主线候选正反方证据、成分穿透与重叠度审计 (7 cols) */}
        {currentMainline && (
          <div className="md:col-span-7 bg-slate-950/60 border border-slate-800 rounded-lg p-3 flex flex-col justify-between overflow-y-auto text-sm space-y-3">
            {/* 顶栏：成分与梯队 */}
            <div>
              <div className="flex items-center justify-between pb-2 border-b border-slate-800/60">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-base text-slate-100">
                    {currentMainline.market_narrative || currentMainline.sector_name}
                  </span>
                  <span className="text-xs text-slate-400 bg-slate-900 border border-slate-700 px-1.5 py-0.5 rounded font-mono">
                    底座行业: {currentMainline.static_taxonomy_name || `${currentMainline.sector_name} (${currentMainline.sector_code})`}
                  </span>
                  {currentMainline.is_thematic_frontier && (
                    <span className="text-xs text-purple-300 bg-purple-950/60 border border-purple-800/60 px-1.5 py-0.5 rounded flex items-center gap-1">
                      <Sparkles className="w-3 h-3" /> 前沿题材保护
                    </span>
                  )}
                </div>
                <div className="text-slate-400 text-xs font-mono">
                  梯队: {Object.entries(currentMainline.constituency.ladder_distribution).map(([k, v]) => `${k}:${v}`).join(' / ')}
                </div>
              </div>

              {/* 裁决综述 */}
              <p className="mt-2 text-sm text-slate-300 leading-relaxed font-medium">
                {currentMainline.conviction_summary}
              </p>
            </div>

            {/* 挂载的前沿技术催化分支 (Parent-Child Hierarchy) */}
            {currentMainline.subtheme_catalysts && currentMainline.subtheme_catalysts.length > 0 && (
              <div className="bg-purple-950/20 border border-purple-900/40 rounded-md p-2">
                <span className="text-purple-300 font-bold flex items-center gap-1 text-xs mb-1">
                  <Sparkles className="w-3.5 h-3.5 text-purple-400" /> 挂载前沿技术催化分支 (Subtheme Catalysts)
                </span>
                <div className="space-y-1">
                  {currentMainline.subtheme_catalysts.map((sub, idx) => (
                    <div
                      key={idx}
                      className="bg-slate-900/80 border border-slate-800 p-1.5 rounded flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center gap-1.5">
                        <span className="font-semibold text-purple-200">{sub.sector_name}</span>
                        <span className="text-xs text-slate-400 font-mono">({sub.sector_code})</span>
                        <span className="text-xs bg-purple-900/50 text-purple-300 px-1.5 py-0.5 rounded font-mono">
                          分支标杆: {sub.catalyst_leader} ({sub.catalyst_height}B)
                        </span>
                      </div>
                      <div className="flex items-center gap-2 font-mono">
                        <span className="text-slate-300">涨停 {sub.stocks_count} 只</span>
                        <span className="text-purple-300/90 font-bold">
                          母链重叠 {(sub.overlap_ratio_with_master * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* P0.1-1: 成分股重叠度 (Shared-Evidence Ratio) 审计 */}
            {currentMainline.shared_evidence_affiliates && currentMainline.shared_evidence_affiliates.length > 0 && (
              <div className="bg-amber-950/20 border border-amber-900/40 rounded-md p-2">
                <span className="text-amber-400 font-bold flex items-center gap-1 text-xs mb-1">
                  <Share2 className="w-3.5 h-3.5" /> 成分股重叠度审计 (Shared-Evidence Ratio)
                </span>
                <div className="space-y-1">
                  {currentMainline.shared_evidence_affiliates.map((aff, idx) => (
                    <div
                      key={idx}
                      className="bg-slate-900/80 border border-slate-800 p-1.5 rounded flex items-center justify-between text-xs"
                    >
                      <div className="flex items-center gap-1.5">
                        <span className="font-semibold text-slate-200">{aff.target_sector_name}</span>
                        <span className="text-xs text-slate-400">({aff.relationship})</span>
                      </div>
                      <div className="flex items-center gap-2 font-mono">
                        <span className="text-amber-300">
                          共享 {aff.overlap_stocks_count} 只
                        </span>
                        <span className="text-amber-400/90 font-bold">
                          重叠度 {(aff.shared_evidence_ratio * 100).toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 正向支撑证据 */}
            <div className="bg-emerald-950/20 border border-emerald-900/40 rounded-md p-2">
              <span className="text-emerald-400 font-bold flex items-center gap-1 text-xs mb-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> 正向支撑证据 (Constituency Support)
              </span>
              <ul className="list-disc list-inside text-slate-300 space-y-0.5 text-xs">
                {currentMainline.supporting_evidence.map((note, idx) => (
                  <li key={idx}>{note}</li>
                ))}
              </ul>
            </div>

            {/* 反方证据集 (波普尔批判) */}
            <div className="bg-rose-950/20 border border-rose-900/40 rounded-md p-2">
              <span className="text-rose-400 font-bold flex items-center gap-1 text-xs mb-1">
                <AlertTriangle className="w-3.5 h-3.5" /> 反方证据集 (Counter-Evidence Set 风险暴露)
              </span>
              <ul className="list-disc list-inside text-rose-200/90 space-y-0.5 text-xs">
                {currentMainline.counter_evidence.map((note, idx) => (
                  <li key={idx}>{note}</li>
                ))}
              </ul>
            </div>

            {/* 独立成分股清单 */}
            <div className="pt-2 border-t border-slate-800/60">
              <span className="text-slate-400 text-xs block mb-1">
                独立涨停成分 ({currentMainline.constituency.limit_up_count} 只):
              </span>
              <div className="flex flex-wrap gap-1">
                {currentMainline.constituency.constituent_symbols.map((sym, idx) => (
                  <span
                    key={idx}
                    className="bg-slate-900 text-slate-300 border border-slate-800 px-1.5 py-0.5 rounded text-xs"
                  >
                    {sym}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
