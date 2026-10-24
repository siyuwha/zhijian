'use client';

import React, { useState, useEffect } from 'react';
import {
  X,
  Brain,
  Clock,
  Sparkles,
  Flame,
  Zap,
  ArrowUpDown,
  Layers,
  ChevronDown,
  ChevronUp,
  Cpu,
  History,
} from 'lucide-react';
import { CognitionHistoryItem } from '@/lib/api';

interface IntradayCognitionHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  history: CognitionHistoryItem[];
  selectedDate: string;
  isLoading?: boolean;
}

export const IntradayCognitionHistoryModal: React.FC<IntradayCognitionHistoryModalProps> = ({
  isOpen,
  onClose,
  history,
  selectedDate,
  isLoading = false,
}) => {
  const [sortOrder, setSortOrder] = useState<'desc' | 'asc'>('desc');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // 监听 ESC 键关闭模态窗
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const sortedHistory = [...history].sort((a, b) => {
    if (sortOrder === 'desc') {
      return (b.time || '').localeCompare(a.time || '');
    }
    return (a.time || '').localeCompare(b.time || '');
  });

  const getEventBadge = (eventType: string) => {
    if (eventType.includes('开盘') || eventType.includes('初始')) {
      return {
        bg: 'bg-purple-950/80 border-purple-500/50 text-purple-300',
        icon: <Sparkles className="w-3 h-3 text-purple-400" />,
      };
    }
    if (eventType.includes('更替') || eventType.includes('接棒') || eventType.includes('主线')) {
      return {
        bg: 'bg-rose-950/80 border-rose-500/50 text-rose-300',
        icon: <Flame className="w-3 h-3 text-rose-400" />,
      };
    }
    if (eventType.includes('剪刀差') || eventType.includes('突变') || eventType.includes('异动')) {
      return {
        bg: 'bg-amber-950/80 border-amber-500/50 text-amber-300',
        icon: <Zap className="w-3 h-3 text-amber-400" />,
      };
    }
    if (eventType.includes('午盘') || eventType.includes('尾盘') || eventType.includes('定型')) {
      return {
        bg: 'bg-indigo-950/80 border-indigo-500/50 text-indigo-300',
        icon: <Clock className="w-3 h-3 text-cyan-400" />,
      };
    }
    return {
      bg: 'bg-slate-800/80 border-slate-600/50 text-slate-300',
      icon: <Layers className="w-3 h-3 text-slate-400" />,
    };
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-150"
      onClick={onClose}
    >
      <div
        className="w-full max-w-4xl bg-[#0b101c] border border-slate-700/80 rounded-2xl shadow-2xl flex flex-col max-h-[88vh] overflow-hidden select-none"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 顶部标题栏 */}
        <header className="px-6 py-4 bg-[#0e1526] border-b border-white/10 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-purple-500/15 text-purple-300 border border-purple-500/30 shadow-[0_0_15px_rgba(168,85,247,0.2)]">
              <Brain className="w-5 h-5 text-cyan-400 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2.5">
                <h2 className="text-base font-black tracking-tight text-slate-100 flex items-center gap-2">
                  <span>当日 AI 题材推演触发记录与博弈轨迹</span>
                </h2>
                <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-purple-950 text-purple-300 border border-purple-700/60 font-mono">
                  {selectedDate}
                </span>
                <span className="text-xs font-semibold px-2 py-0.5 rounded-md bg-cyan-950/60 text-cyan-300 border border-cyan-800/60 font-mono">
                  共 {history.length} 次触发
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                全自动盘面事件驱动（开盘定调、领涨主线轮动更替、资金剪刀差异动突变、午盘定型与尾盘沉淀），自动留痕可审计追溯
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {history.length > 1 && (
              <button
                type="button"
                onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800/80 hover:bg-slate-700 border border-white/10 text-xs text-slate-300 hover:text-white transition-colors"
                title="切换排序方式"
              >
                <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
                <span>{sortOrder === 'desc' ? '最新在前' : '时间正序'}</span>
              </button>
            )}
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 border border-transparent hover:border-white/10 transition-colors"
              title="关闭窗口 (ESC)"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </header>

        {/* 弹窗主体内容 */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4 custom-scrollbar">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-400">
              <Brain className="w-10 h-10 text-purple-400 animate-spin mb-3" />
              <p className="text-sm">正在加载当日认知推演轨迹...</p>
            </div>
          ) : sortedHistory.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center border border-dashed border-white/10 rounded-xl bg-slate-900/40 p-8">
              <History className="w-12 h-12 text-slate-600 mb-3" />
              <h3 className="text-sm font-bold text-slate-300">暂无触发记录</h3>
              <p className="text-xs text-slate-400 max-w-md mt-1 leading-relaxed">
                系统全天处于自动事件驱动监听中：在 09:25-09:30 产生开盘首次定调，
                盘中每当题材主线排名位移、主力资金剪刀差发生质变突变时，将自动调用 AI 进行深度推演并在此生成留痕轨迹。
              </p>
            </div>
          ) : (
            <div className="space-y-3.5">
              {sortedHistory.map((item, idx) => {
                const badge = getEventBadge(item.event_type || '');
                const isLatest = sortOrder === 'desc' ? idx === 0 : idx === sortedHistory.length - 1;
                const isExpanded = expandedId === item.id;
                const hasDetailedTracks = Boolean(item.track1 || item.track2);

                return (
                  <div
                    key={item.id || idx}
                    className={`relative rounded-xl border transition-all ${
                      isLatest
                        ? 'bg-gradient-to-br from-purple-950/20 via-[#0f172a] to-[#0c101c] border-purple-500/40 shadow-[0_0_20px_rgba(168,85,247,0.1)]'
                        : 'bg-slate-900/60 border-white/10 hover:border-slate-600/80'
                    } p-4`}
                  >
                    {/* 卡片头部信息 */}
                    <div className="flex flex-wrap items-center justify-between gap-2 pb-2.5 mb-2.5 border-b border-white/5">
                      <div className="flex items-center gap-2">
                        {/* 时间戳 */}
                        <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-cyan-300 font-mono text-xs font-bold tabular-nums">
                          <Clock className="w-3 h-3 text-cyan-400" />
                          <span>{item.time || '--:--:--'}</span>
                        </div>

                        {/* 事件类型标签 */}
                        <div
                          className={`flex items-center gap-1 px-2.5 py-0.5 rounded-full border text-[11px] font-bold ${badge.bg}`}
                        >
                          {badge.icon}
                          <span>{item.event_type || '盘中推演'}</span>
                        </div>

                        {/* 最新标旗 */}
                        {isLatest && (
                          <span className="px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 text-[10px] font-bold animate-pulse">
                            最新态势
                          </span>
                        )}
                      </div>

                      {/* 盘面资金攻防与模型 */}
                      <div className="flex items-center gap-2 text-xs font-mono">
                        {item.lead_sector && (
                          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-slate-800/80 border border-white/5">
                            <span className="text-slate-400 text-[11px]">主攻</span>
                            <span className="text-rose-400 font-bold">
                              {item.lead_sector}
                              {typeof item.lead_net === 'number' && (
                                <span className="ml-1 text-[11px] tabular-nums">
                                  ({item.lead_net >= 0 ? `+${item.lead_net.toFixed(1)}` : item.lead_net.toFixed(1)}亿)
                                </span>
                              )}
                            </span>
                            {item.tail_sector && (
                              <>
                                <span className="text-slate-600">/</span>
                                <span className="text-slate-400 text-[11px]">抽血</span>
                                <span className="text-emerald-400 font-bold">
                                  {item.tail_sector}
                                  {typeof item.tail_net === 'number' && (
                                    <span className="ml-1 text-[11px] tabular-nums">
                                      ({item.tail_net >= 0 ? `+${item.tail_net.toFixed(1)}` : item.tail_net.toFixed(1)}亿)
                                    </span>
                                  )}
                                </span>
                              </>
                            )}
                          </div>
                        )}

                        <div className="flex items-center gap-1 text-[11px] text-slate-400 px-2 py-0.5 rounded bg-white/5 border border-white/5">
                          <Cpu className="w-3 h-3 text-purple-400" />
                          <span>
                            {item.source === 'LLM_INFERRED'
                              ? `LLM (${item.model || 'DeepSeek'})`
                              : '量化专家引擎'}
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* 题材战场资金轮动本质 (核心推演结论) */}
                    <div className="border-l-2 border-purple-400/80 pl-3 py-1 bg-purple-500/5 rounded-r">
                      <div className="text-[11px] font-bold text-purple-300 uppercase tracking-wider mb-1 flex items-center gap-1">
                        <span>题材战场资金轮动推演结论</span>
                      </div>
                      <p className="text-xs text-slate-200 leading-relaxed font-sans">
                        {item.sector_rotation || '盘中题材快速轮动博弈中'}
                      </p>
                    </div>

                    {/* 伴随展开的个股博弈微观轨迹 (Track 1 & Track 2) */}
                    {hasDetailedTracks && (
                      <div className="mt-2.5 pt-2 border-t border-white/5">
                        <button
                          type="button"
                          onClick={() => setExpandedId(isExpanded ? null : item.id)}
                          className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-cyan-300 transition-colors"
                        >
                          {isExpanded ? (
                            <>
                              <ChevronUp className="w-3 h-3" />
                              <span>收起微观个股博弈详情</span>
                            </>
                          ) : (
                            <>
                              <ChevronDown className="w-3 h-3" />
                              <span>展开微观个股与连板高标动态博弈详情</span>
                            </>
                          )}
                        </button>

                        {isExpanded && (
                          <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs animate-in fade-in duration-100">
                            {item.track1 && (
                              <div className="p-2.5 rounded-lg bg-slate-950/60 border border-white/5">
                                <div className="text-[10px] font-bold text-amber-400/90 mb-1">
                                  昨日核心标的表现剖析
                                </div>
                                <p className="text-slate-300 text-[11px] leading-relaxed">
                                  {item.track1}
                                </p>
                              </div>
                            )}
                            {item.track2 && (
                              <div className="p-2.5 rounded-lg bg-slate-950/60 border border-white/5">
                                <div className="text-[10px] font-bold text-cyan-400/90 mb-1">
                                  日内最强先锋与高标动态博弈
                                </div>
                                <p className="text-slate-300 text-[11px] leading-relaxed">
                                  {item.track2}
                                </p>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* 底部状态栏 */}
        <footer className="px-6 py-3 bg-[#0e1526] border-t border-white/10 flex items-center justify-between text-xs text-slate-400 shrink-0">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            <span className="text-slate-300 text-[11px]">
              盘中智能事件驱动监听中 · 无需人工刷新，逢变盘自动触发推演并形成审计轨迹
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-white/10 transition-colors"
          >
            关闭窗口
          </button>
        </footer>
      </div>
    </div>
  );
};
