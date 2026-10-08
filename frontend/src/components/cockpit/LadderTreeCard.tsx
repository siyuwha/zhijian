'use client';

import React, { useState } from 'react';
import { LadderGroup, LimitUpStockItem } from '@/types/canonical';
import { Crown, Layers, ChevronDown, ChevronUp, Sparkles } from 'lucide-react';

interface LadderTreeCardProps {
  ladderTree: LadderGroup[];
  maxHeight: number;
}

export const LadderTreeCard: React.FC<LadderTreeCardProps> = ({ ladderTree, maxHeight }) => {
  const [expandFirstBoards, setExpandFirstBoards] = useState(false);

  // 空间标杆标的
  const spaceLeaderGroup = ladderTree.find((g) => g.is_space_leader || g.height === maxHeight);
  const spaceLeaderStock = spaceLeaderGroup?.stocks[0];

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 shadow-lg flex flex-col h-full">
      {/* 标题与空间标杆问答 */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <span className="p-1 rounded bg-indigo-500/20 text-indigo-400">
            <Layers className="w-4 h-4" />
          </span>
          <span className="text-sm font-bold text-slate-200">
            问 3 · 空间标杆与连板天梯
          </span>
        </div>

        {spaceLeaderStock && (
          <div className="flex items-center gap-1.5 bg-gradient-to-r from-amber-950/60 to-amber-900/40 border border-amber-600/40 px-2.5 py-1 rounded-md text-xs font-semibold text-amber-300">
            <Crown className="w-3.5 h-3.5 text-amber-400" />
            <span>标杆: {spaceLeaderStock.name}</span>
            <span className="font-mono text-amber-200 font-bold ml-1">{maxHeight}B</span>
            <span className="text-[10px] text-amber-400/80 ml-0.5">({spaceLeaderStock.reason_type})</span>
          </div>
        )}
      </div>

      {/* 天梯递降阶梯树 (8 -> 4 -> 3 -> 2 -> 1) */}
      <div className="flex-1 overflow-y-auto space-y-2 mt-3 pr-1 text-xs">
        {ladderTree.map((group) => {
          const isSpace = group.is_space_leader;
          const isFirstBoard = group.height === 1;

          if (isFirstBoard) {
            // 首板特殊处理：支持折叠与展示总数
            return (
              <div
                key={group.height}
                className="bg-slate-950/40 border border-slate-800/80 rounded-lg p-2.5"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded font-mono font-bold text-slate-300 bg-slate-800/80">
                      1B 基座
                    </span>
                    <span className="text-slate-400 font-mono">
                      共 {group.stocks_count} 只首板
                    </span>
                  </div>
                  <button
                    onClick={() => setExpandFirstBoards(!expandFirstBoards)}
                    className="text-indigo-400 hover:text-indigo-300 flex items-center gap-1 text-[11px] font-medium transition"
                  >
                    {expandFirstBoards ? (
                      <>
                        收起名单 <ChevronUp className="w-3.5 h-3.5" />
                      </>
                    ) : (
                      <>
                        展开标的 <ChevronDown className="w-3.5 h-3.5" />
                      </>
                    )}
                  </button>
                </div>

                {expandFirstBoards && (
                  <div className="mt-2.5 pt-2 border-t border-slate-800/60 flex flex-wrap gap-1.5 max-h-40 overflow-y-auto">
                    {group.stocks.map((st) => (
                      <span
                        key={st.code}
                        className="bg-slate-900 border border-slate-800 text-slate-300 px-2 py-0.5 rounded text-[11px] font-mono flex items-center gap-1"
                      >
                        <span>{st.name}</span>
                        <span className="text-[10px] text-slate-400 font-sans">
                          {st.reason_type}
                        </span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          }

          // 连板层 (>= 2B)
          return (
            <div
              key={group.height}
              className={`rounded-lg p-2.5 border transition ${
                isSpace
                  ? 'bg-amber-950/20 border-amber-600/30'
                  : group.height >= 3
                  ? 'bg-indigo-950/20 border-indigo-700/30'
                  : 'bg-slate-950/60 border-slate-800/80'
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2 py-0.5 rounded font-mono font-black text-xs ${
                      isSpace
                        ? 'bg-amber-500/30 text-amber-300 border border-amber-500/40'
                        : group.height >= 3
                        ? 'bg-indigo-500/30 text-indigo-300 border border-indigo-500/40'
                        : 'bg-slate-800 text-slate-300'
                    }`}
                  >
                    {group.height}B 梯队
                  </span>
                  <span className="text-slate-400 font-mono text-[11px]">
                    ({group.stocks_count} 只)
                  </span>
                </div>
                {isSpace && (
                  <span className="text-[10px] text-amber-400 bg-amber-950/60 border border-amber-800 px-1.5 py-0.2 rounded font-semibold flex items-center gap-1">
                    <Sparkles className="w-3 h-3" /> 市场空间总高度
                  </span>
                )}
              </div>

              {/* 标的徽章列表 */}
              <div className="flex flex-wrap gap-1.5">
                {group.stocks.map((st) => (
                  <div
                    key={st.code}
                    className={`px-2 py-1 rounded border text-xs flex items-center gap-1.5 ${
                      isSpace
                        ? 'bg-amber-900/30 border-amber-600/50 text-amber-200'
                        : 'bg-slate-900 border-slate-700 text-slate-200'
                    }`}
                  >
                    <span className="font-bold">{st.name}</span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      {st.code}
                    </span>
                    <span className="text-[10px] text-indigo-400 bg-indigo-950/60 px-1 rounded">
                      {st.reason_type}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
