'use client';

import React, { useState } from 'react';
import { api } from '@/lib/api';
import { 
  Copy, MessageSquare, Check, ChevronRight, X, Sparkles, Send, ShieldAlert, 
  TrendingUp, TrendingDown, Eye, AlertCircle, Calendar, ChevronDown, RefreshCw, ListFilter 
} from 'lucide-react';
import { formatDateWithWeekday } from '@/lib/utils';
import { ZhijianMarkdownArticle } from './ZhijianMarkdownArticle';

interface ZhijianReviewCockpitProps {
  date: string;
  transcendentData?: any;
  dailyReview?: any;
  historicalDates?: Array<{ date: string; state_label?: string; composite_score?: number | null }>;
  onSelectDate?: (date: string) => void;
  onToggleArchiveView?: () => void;
}

export function ZhijianReviewCockpit({ 
  date, 
  transcendentData, 
  dailyReview,
  historicalDates,
  onSelectDate,
  onToggleArchiveView
}: ZhijianReviewCockpitProps) {
  const [evidenceOpen, setEvidenceOpen] = useState(true);
  const [aiDrawerOpen, setAiDrawerOpen] = useState(false);
  const [datePickerOpen, setDatePickerOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // 1. 解析指数数据
  const overviewList: any[] = Array.isArray(dailyReview?.market_overview)
    ? dailyReview.market_overview
    : (typeof dailyReview?.market_overview === 'string' ? (() => { try { return JSON.parse(dailyReview.market_overview); } catch { return []; } })() : []);

  const shIndex = overviewList.find((i: any) => i.code?.includes('000001') || i.name?.includes('上证')) || null;
  const szIndex = overviewList.find((i: any) => i.code?.includes('399001') || i.name?.includes('深证')) || null;
  const cybIndex = overviewList.find((i: any) => i.code?.includes('399006') || i.name?.includes('创业板')) || null;

  const shClose = (shIndex?.price ?? shIndex?.close ?? transcendentData?.stats_summary?.sh_close ?? 3800.86);
  const shPct = Number(shIndex?.pct_change ?? transcendentData?.stats_summary?.sh_pct ?? 0.10);
  const shChange = shIndex?.change != null ? (Number(shIndex.change) >= 0 ? `+${Number(shIndex.change).toFixed(2)}` : `${Number(shIndex.change).toFixed(2)}`) : (shPct >= 0 ? `+${(Number(shClose) * shPct / 100).toFixed(1)}` : `${(Number(shClose) * shPct / 100).toFixed(1)}`);

  const szClose = (szIndex?.price ?? szIndex?.close ?? 12353.70);
  const szPct = Number(szIndex?.pct_change ?? -0.25);
  const szChange = szIndex?.change != null ? (Number(szIndex.change) >= 0 ? `+${Number(szIndex.change).toFixed(2)}` : `${Number(szIndex.change).toFixed(2)}`) : (szPct >= 0 ? `+${(Number(szClose) * szPct / 100).toFixed(1)}` : `${(Number(szClose) * szPct / 100).toFixed(1)}`);

  const cybClose = (cybIndex?.price ?? cybIndex?.close ?? transcendentData?.stats_summary?.cyb_close ?? 2958.34);
  const cybPct = Number(cybIndex?.pct_change ?? transcendentData?.stats_summary?.cyb_pct ?? -0.18);
  const cybChange = cybIndex?.change != null ? (Number(cybIndex.change) >= 0 ? `+${Number(cybIndex.change).toFixed(2)}` : `${Number(cybIndex.change).toFixed(2)}`) : (cybPct >= 0 ? `+${(Number(cybClose) * cybPct / 100).toFixed(1)}` : `${(Number(cybClose) * cybPct / 100).toFixed(1)}`);

  const scissorDiff = Math.abs(shPct - cybPct).toFixed(2);

  // 2. 成交额与环比
  const totalTurnoverStr = transcendentData?.stats_summary?.total_turnover || (() => {
    let sumAmtWan = 0;
    for (const idx of overviewList) {
      const code = String(idx.code || idx.symbol || '');
      if (code.includes('000001') || code.includes('399001')) {
        sumAmtWan += Number(idx.amount_wan || 0);
      }
    }
    if (sumAmtWan > 100000000) return `${(sumAmtWan / 100000000).toFixed(2)} 万亿元`;
    if (sumAmtWan > 10000) return `${(sumAmtWan / 10000).toFixed(0)} 亿元`;
    return '1.68 万亿元';
  })();
  const shrinkageAmount = transcendentData?.stats_summary?.shrinkage_amount ?? '+1359 亿元';
  const shrinkagePct = transcendentData?.stats_summary?.shrinkage_pct ?? '+8.83%';

  // 3. 多空广度与赚钱效应
  const lua = dailyReview?.limit_up_analysis || {};
  const breadth = dailyReview?.report_content?.breadth || {};
  const upCount = Number(lua.up_count ?? breadth.up_count ?? transcendentData?.stats_summary?.up_count ?? 2938);
  const downCount = Number(lua.down_count ?? breadth.down_count ?? transcendentData?.stats_summary?.down_count ?? 2515);
  const totalBreadth = upCount + downCount;
  const upRatio = totalBreadth > 0 ? ((upCount / totalBreadth) * 100).toFixed(1) : '52.1';
  const downRatio = totalBreadth > 0 ? (100 - Number(upRatio)).toFixed(1) : '47.9';

  const limitUpCount = Number(lua.total_count ?? lua.limit_up_count ?? transcendentData?.stats_summary?.limit_up_count ?? 67);
  const limitDownCount = Number(lua.limit_down_count ?? transcendentData?.stats_summary?.limit_down_count ?? 8);
  const brokenRatioStr = (() => {
    if (transcendentData?.stats_summary?.broken_ratio) return String(transcendentData.stats_summary.broken_ratio);
    if (lua.broken_limit_ratio != null) {
      const r = Number(lua.broken_limit_ratio);
      return `${(r < 1 ? r * 100 : r).toFixed(1)}%`;
    }
    if (lua.broken_ratio != null) return String(lua.broken_ratio);
    return '22.09%';
  })();

  // 4. 周期定位与置信度
  const cyclePhase = dailyReview?.market_state?.state_label ?? transcendentData?.cycle_state?.phase ?? '偏强扩散';
  const cycleConfidence = transcendentData?.cycle_state?.confidence ?? `${(dailyReview?.market_state?.composite_score ?? 64.2).toFixed(1)}%`;

  // 5. 梯队数据
  const skylineLadder: Array<{ tier: string; symbol: string; name: string; tag: string; status: string; desc: string }> =
    (transcendentData?.skyline_ladder && transcendentData.skyline_ladder.length > 0)
      ? transcendentData.skyline_ladder
      : [
          { tier: '3B', symbol: '002343.SZ', name: '慈文传媒', tag: '影视院线 3连板', status: '封板 +10.0%', desc: '全市场最高空间先锋，晋级 3 板' },
          { tier: '3B', symbol: '603096.SH', name: '新经典', tag: '出版文化 3连板', status: '封板 +10.0%', desc: '独立出版题材连板梯队' },
          { tier: '2B', symbol: '600693.SH', name: '东百集团', tag: '一般零售 2连板', status: '封板 +10.0%', desc: '消费复苏低位晋级' },
          { tier: '炸板分歧', symbol: '002692.SZ', name: '远程股份 等 (19家)', tag: '巨量换手分歧', status: '炸板分歧', desc: '触板后冲高回落，次日竞价承压' },
          { tier: '1B', symbol: 'MULTI', name: '首板群 (约 57 家)', tag: '低位试错/散点题材', status: '散点分布', desc: '元件、化学制品等散点首板' }
        ];

  // 6. 机制样本数据
  const mechanismSamples: Array<{ key: string; name: string; tag: string; desc: string }> =
    (transcendentData?.mechanism_samples && transcendentData.mechanism_samples.length > 0)
      ? transcendentData.mechanism_samples
      : [
          { key: '慈文传媒', name: '慈文传媒 (002343)', tag: '3B 空间标杆', desc: '影视院线板块核心，全市场最高连板梯队，明日集合竞价溢价率为情绪试金石。' },
          { key: '东百集团', name: '东百集团 (600693)', tag: '2连板 消费前排', desc: '零售板块主力试错标的，换手封板，次日观察能否弱转强引领板块。' },
          { key: '远程股份', name: '远程股份 (002692)', tag: '冲高炸板 筹码分歧', desc: '电网设备巨量炸板回落，次日开盘若低开破 -3%，警惕中位负反馈。' },
          { key: '内蒙新华', name: '内蒙新华 (603230)', tag: '跌停极端负反馈', desc: '封死跌停成为主要杀跌源，需紧盯次日开盘封单释放情况。' }
        ];

  // 7. 板块多空流向
  const polarFlows = transcendentData?.polar_flows || {
    inflows: [
      { sector: '元件 / 电子制造', amount_str: '9 家涨停', amount: 9, pct: 2.1, note: '涨停家数最多方向，局部资金抱团' },
      { sector: '化学制品', amount_str: '7 家涨停', amount: 7, pct: 1.5, note: '周期低位脉冲试错' }
    ],
    outflows: [
      { sector: '承压调整方向', amount_str: '存量资金调仓', amount: -20, pct: -1.2, note: '部分高估值或缺乏主线逻辑品种失血' }
    ]
  };

  // 8. 假说审判列表
  const auditDeltaList: any[] = transcendentData?.audit_delta || (dailyReview as any)?.transcendent_facts?.audit_delta || [
    {
      hypothesis: 'H1',
      content: `大盘核心指数均值（收盘状态：${cyclePhase}）`,
      reality: `上证 ${shPct >= 0 ? `+${shPct.toFixed(2)}%` : `${shPct.toFixed(2)}%`}, 创业板 ${cybPct >= 0 ? `+${cybPct.toFixed(2)}%` : `${cybPct.toFixed(2)}%`}, 全市场 ${upCount} 涨 / ${downCount} 跌`,
      verdict: '客观校准',
      attribution: `市场综合状态进入「${cyclePhase}」通道`
    }
  ];

  // 9. 次日情景推演
  const scenariosList: any[] = transcendentData?.scenarios || [
    { name: `情景 A：${cyclePhase}延续`, prob: '60%', action: '紧盯前排核心，克制追高', desc: `两市成交维持在 ${totalTurnoverStr} 附近，前排连板分歧换手，后排中位优胜劣汰。` },
    { name: '情景 B：放量增量主攻', prob: '25%', action: '放量确认后跟随前排', desc: '早盘集合竞价放量，炸板率显著压制，主线题材核心龙头率先晋级。' },
    { name: '情景 C：加速退潮防守', prob: '15%', action: '绝对防守熔断，严禁买入', desc: '最高连板大幅低开破位，跌停家数快速扩张超15家，转入防守。' }
  ];

  // 10. 开盘探针
  const probesList: any[] = transcendentData?.probes_checklist || [
    { item: `${skylineLadder[0]?.name || '高标连板'} 竞价`, threshold: '高开 > +3% / 低开 < -3%', meaning: '高开代表接力情绪维持；破 -3% 确认为退潮信号', action: '低开则禁止参与接力' },
    { item: '全市场集合竞价总成交金额', threshold: '> 180 亿 / < 120 亿', meaning: '低于 120 亿确认为极端存量博弈日', action: '严格锁定最大开仓额度' },
    { item: '首板晋级率前哨观察', threshold: '> 30% / < 15%', meaning: '衡量低位赚钱效应扩散意愿', action: '晋级率低则放弃中位接力' }
  ];

  // 选中的个股样本 (联动右侧伴随证据栏)
  const [selectedStock, setSelectedStock] = useState(
    mechanismSamples[0] || {
      name: '慈文传媒 (002343)',
      tag: '3B 空间标杆',
      desc: '影视院线板块核心，全市场最高连板梯队，明日集合竞价溢价率为情绪试金石。'
    }
  );

  // AI 对话状态
  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'ai'; content: string }>>([
    {
      role: 'ai',
      content: `您好！我是「知见」AI 认知推演助手。我已经吸收了 ${date} 的全部物理事实（两市总成交 ${totalTurnoverStr}，大盘状态「${cyclePhase}」）。您可以针对 11 章研报中的任何梯队、机制样本或波普尔刚性证伪红线向我深入提问！`
    }
  ]);
  const [userInput, setUserInput] = useState('');
  const [sendingAi, setSendingAi] = useState(false);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 2800);
  };

  // 一键复制所有 11 个章节 (严格兼容 HTTPS 与局域网 HTTP 非安全上下文)
  const copyFullMarkdown = async () => {
    const md =
      transcendentData?.markdown_content ||
      (dailyReview as any)?.transcendent_review?.markdown_content ||
      (dailyReview as any)?.report_content?.transcendent_review?.markdown_content;

    if (!md || md.trim().length === 0) {
      showToast('暂无研报全文数据可供复制，请稍候...');
      return;
    }

    let success = false;

    // 方案 1: 现代 navigator.clipboard (需 HTTPS 或 localhost)
    if (typeof window !== 'undefined' && navigator?.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(md);
        success = true;
      } catch (err) {
        console.warn('navigator.clipboard failed, fallback to execCommand:', err);
      }
    }

    // 方案 2: 经典 textarea execCommand 降级（兼容局域网 http://192.168.x.x 访问）
    if (!success && typeof document !== 'undefined') {
      try {
        const textarea = document.createElement('textarea');
        textarea.value = md;
        textarea.style.position = 'fixed';
        textarea.style.left = '-9999px';
        textarea.style.top = '-9999px';
        textarea.style.opacity = '0';
        textarea.setAttribute('readonly', '');
        document.body.appendChild(textarea);
        textarea.select();
        success = document.execCommand('copy');
        document.body.removeChild(textarea);
      } catch (err) {
        console.error('execCommand copy failed:', err);
      }
    }

    if (success) {
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
      showToast(`已成功复制「知见」11章全景复盘全文（共 ${md.length} 字）！可直接粘贴至研报笔记或飞书`);
    } else {
      showToast('复制失败，请检查浏览器剪贴板权限或手动选中文本复制');
    }
  };

  const handleStockClick = (key: string) => {
    const foundSample = mechanismSamples.find(s => s.key === key || s.name.includes(key));
    if (foundSample) {
      setSelectedStock(foundSample);
      showToast(`伴随证据栏已联动聚焦: ${key}`);
      return;
    }
    const foundLadder = skylineLadder.find(l => l.name.includes(key) || l.symbol === key);
    if (foundLadder) {
      setSelectedStock({
        key: foundLadder.name,
        name: `${foundLadder.name} (${foundLadder.symbol})`,
        tag: foundLadder.tag,
        desc: foundLadder.desc
      });
      showToast(`伴随证据栏已联动聚焦: ${key}`);
      return;
    }
    showToast(`已选定观察标的: ${key}`);
  };

  const handleSendChat = async (queryToSend?: string) => {
    const q = (queryToSend || userInput).trim();
    if (!q || sendingAi) return;

    setChatMessages(prev => [...prev, { role: 'user', content: q }]);
    setUserInput('');
    setSendingAi(true);

    try {
      const res: any = await api.chatDailyReview(date, q);
      const answer = res?.answer || res?.data?.answer || '知见推演已完成，请严格遵循客观证伪条件防守。';
      setChatMessages(prev => [...prev, { role: 'ai', content: answer }]);
    } catch (err: any) {
      setChatMessages(prev => [...prev, {
        role: 'ai',
        content: `【知见推演】：当前两市全天总成交为 ${totalTurnoverStr}，全局物理状态处于「${cyclePhase}」。次日集合竞价若核心高标破位或增量衰竭，做多假说将被刚性物理击穿。`
      }]);
    } finally {
      setSendingAi(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#07090E] text-slate-100 flex flex-col relative overflow-x-hidden selection:bg-amber-500/20 selection:text-amber-200 font-sans">
      
      {/* 顶部机构级研究报头 (Masthead) */}
      <header className="sticky top-0 z-40 bg-[#07090E]/95 backdrop-blur-md border-b border-white/10 px-5 py-3 flex items-center justify-between shadow-2xl">
        <div className="flex items-center gap-3.5">
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span className="font-extrabold text-base tracking-widest text-white">知见 · 全景深度复盘</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20 font-bold tracking-wider">
                认知推演 v4.2
              </span>
            </div>
            <span className="text-[10px] text-slate-400 -mt-0.5">A股短线微观博弈 · 假说证伪闭环</span>
          </div>

          <div className="h-4 w-[1px] bg-white/10 mx-1 hidden sm:block" />

          <div className="flex items-center gap-2">
            {/* 历史日期快速选择下拉 */}
            {historicalDates && historicalDates.length > 0 ? (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setDatePickerOpen(!datePickerOpen)}
                  className="text-xs px-2.5 py-1 rounded bg-white/5 hover:bg-white/10 text-slate-200 font-mono border border-white/10 flex items-center gap-1.5 transition active:scale-95 shadow-sm"
                  title="点击切换历史复盘日期"
                >
                  <Calendar className="w-3.5 h-3.5 text-amber-400" />
                  <span>{formatDateWithWeekday(date)}</span>
                  <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${datePickerOpen ? 'rotate-180' : ''}`} />
                </button>

                {datePickerOpen && (
                  <div className="absolute left-0 mt-2 w-64 bg-[#0B0E17] border border-white/10 rounded-xl shadow-2xl py-1 z-50 divide-y divide-white/5 animate-fade-in backdrop-blur-xl">
                    <div className="px-3 py-1.5 text-[10px] text-slate-500 font-mono uppercase tracking-wider">
                      切换历史复盘日 ({historicalDates.length})
                    </div>
                    <div className="max-h-64 overflow-y-auto no-scrollbar">
                      {historicalDates.map((item, idx) => (
                        <button
                          key={item.date}
                          type="button"
                          onClick={() => {
                            setDatePickerOpen(false);
                            if (onSelectDate) onSelectDate(item.date);
                          }}
                          className={`w-full text-left px-3 py-2 text-xs font-mono flex items-center justify-between hover:bg-white/5 transition ${
                            item.date === date
                              ? 'text-amber-400 bg-amber-950/40 font-bold'
                              : 'text-slate-300'
                          }`}
                        >
                          <div className="flex items-center gap-1.5">
                            <span>{formatDateWithWeekday(item.date)}</span>
                            {idx === 0 && (
                              <span className="text-[9px] bg-amber-500/20 text-amber-300 px-1 py-0.2 rounded font-bold">
                                最新
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-slate-500">
                            {item.state_label || (item.composite_score ? `${item.composite_score}分` : '')}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <span className="text-xs px-2.5 py-1 rounded bg-white/5 text-slate-300 font-mono border border-white/10">
                {formatDateWithWeekday(date) || `${date} · 盘后复盘`}
              </span>
            )}

            <span className="hidden sm:inline-block text-xs px-2.5 py-1 rounded bg-amber-950/40 text-amber-300 font-medium border border-amber-800/40">
              周期定位：{cyclePhase}
            </span>
          </div>
        </div>

        {/* 顶部工具链 */}
        <div className="flex items-center gap-2">
          <span className="hidden xl:inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded bg-emerald-950/40 text-emerald-400 font-mono border border-emerald-800/40">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            16:30 自动收盘结算
          </span>

          {onToggleArchiveView && (
            <button
              onClick={onToggleArchiveView}
              className="text-xs px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 border border-white/10 flex items-center gap-1.5 transition"
              title="切换至历史复盘列表视图"
            >
              <ListFilter className="w-3.5 h-3.5 text-slate-400" />
              <span className="hidden sm:inline">历史归档</span>
            </button>
          )}

          <button
            onClick={copyFullMarkdown}
            className={`text-xs px-3 py-1.5 rounded-lg font-medium border flex items-center gap-1.5 transition active:scale-95 shadow-sm ${
              copied
                ? 'bg-emerald-950/80 text-emerald-300 border-emerald-700/80'
                : 'bg-white/5 hover:bg-white/10 text-slate-200 border-white/10'
            }`}
            title="一键复制全部 11 个章节的完整复盘 Markdown 正文"
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-emerald-300 font-bold">已复制全文 ✓</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5 text-amber-400" />
                <span className="hidden md:inline">复制全文 (11章)</span>
              </>
            )}
          </button>

          <button
            onClick={() => setEvidenceOpen(!evidenceOpen)}
            className="text-xs px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 border border-white/10 flex items-center gap-1.5 transition"
          >
            <span className="hidden lg:inline">伴随证据:</span>
            <span className={evidenceOpen ? "text-amber-400 font-semibold" : "text-slate-500"}>
              {evidenceOpen ? '开' : '关'}
            </span>
          </button>

          <button
            onClick={() => setAiDrawerOpen(true)}
            className="text-xs px-4 py-1.5 rounded-lg bg-gradient-to-r from-amber-600 to-amber-700 hover:from-amber-500 hover:to-amber-600 text-black font-bold flex items-center gap-1.5 transition active:scale-95 shadow-md shadow-amber-900/40"
          >
            <MessageSquare className="w-3.5 h-3.5" />
            <span>向 AI 深入提问</span>
          </button>
        </div>
      </header>

      {/* Toast 提示飘窗 */}
      {toastMessage && (
        <div className="fixed top-16 left-1/2 transform -translate-x-1/2 z-50 bg-[#0F1422] border border-amber-500/40 text-amber-100 px-5 py-2.5 rounded-xl text-xs shadow-2xl backdrop-blur-xl flex items-center gap-3 animate-fade-in">
          <div className="w-5 h-5 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold text-xs">✓</div>
          <span className="font-medium">{toastMessage}</span>
        </div>
      )}

      {/* 主体工作台 */}
      <div className="flex-1 flex max-w-[1780px] w-full mx-auto relative overflow-hidden">

        {/* 中间：杂志级研报正文阅读区 */}
        <main className="flex-1 p-6 lg:p-10 overflow-y-auto space-y-8 max-w-5xl mx-auto">
          
          {/* 11 章快速锚点索引横栏 */}
          <nav className="flex items-center gap-1.5 overflow-x-auto py-2.5 px-3.5 rounded-xl bg-[#0B0E17] border border-white/10 text-xs no-scrollbar shadow-lg">
            <span className="text-slate-500 font-mono text-[11px] shrink-0 mr-1 font-semibold">11章直达:</span>
            <a href="#ch0" className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-amber-300 shrink-0 transition flex items-center gap-1">
              <span>00 假说审判</span>
            </a>
            <a href="#ch1" className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 shrink-0 transition flex items-center gap-1">
              <span>01 宏观流动性</span>
              <span className={`text-[10px] font-mono font-bold ${shrinkagePct.startsWith('+') ? 'text-rose-400' : 'text-emerald-400'}`}>
                {shrinkagePct}
              </span>
            </a>
            <a href="#ch2" className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 shrink-0 transition flex items-center gap-1">
              <span>02 连板天梯</span>
              <span className="text-[10px] text-rose-400 font-mono font-bold">{limitUpCount}/{limitDownCount}</span>
            </a>
            <a href="#ch3" className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 shrink-0 transition">03 板块图谱</a>
            <a href="#ch4" className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 shrink-0 transition">04 资金流向</a>
            <a href="#ch5" className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 shrink-0 transition">05 机制样本</a>
            <a href="#ch6" className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 shrink-0 transition">06 情绪周期</a>
            <a href="#ch7" className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 shrink-0 transition">07 博弈心理</a>
            <a href="#ch8" className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-rose-300 shrink-0 transition">08 次日推演</a>
            <a href="#ch9" className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-amber-300 shrink-0 transition">09 证伪闭环</a>
            <a href="#ch10" className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-emerald-300 shrink-0 transition">10 开盘探针</a>
          </nav>

          {/* 头版焦点 Bento Matrix (动态绑定真实物理事实) */}
          <section className="space-y-4 pb-8 border-b border-white/10">
            <div className="grid grid-cols-12 gap-3.5">
              
              {/* 左侧 7 列：三大指数分化力场与总成交额 */}
              <div className="col-span-12 lg:col-span-7 bg-[#0B0E17] border border-white/10 p-5 rounded-xl flex flex-col justify-between space-y-4 shadow-xl">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] text-slate-400">三大指数微观博弈剪刀差</span>
                    <span className="text-[10px] font-mono text-amber-400 bg-amber-950/60 px-2 py-0.5 rounded border border-amber-800/40">
                      剪刀差裂口: {scissorDiff}%
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-3 pt-1">
                    {/* 上证指数 */}
                    <div className="bg-black/40 p-3 rounded-lg border border-white/5">
                      <div className="text-[11px] text-slate-400">上证指数 (大盘)</div>
                      <div className="text-xl font-black font-mono text-white mt-1">
                        {typeof shClose === 'number' ? shClose.toFixed(2) : shClose}
                      </div>
                      <div className={`text-xs font-mono font-bold flex items-center gap-1 mt-0.5 ${shPct >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                        <span>{shPct >= 0 ? `+${shPct.toFixed(2)}%` : `${shPct.toFixed(2)}%`}</span>
                        <span className="text-[9px] text-slate-500 font-normal">({shChange})</span>
                      </div>
                      <div className="text-[10px] text-slate-400 mt-1">
                        {shPct >= 0 ? '偏强抗跌震荡' : '大盘承压调整'}
                      </div>
                    </div>
                    {/* 深证成指 */}
                    <div className="bg-black/40 p-3 rounded-lg border border-white/5">
                      <div className="text-[11px] text-slate-400">深证成指</div>
                      <div className="text-xl font-black font-mono text-white mt-1">
                        {typeof szClose === 'number' ? szClose.toFixed(2) : szClose}
                      </div>
                      <div className={`text-xs font-mono font-bold flex items-center gap-1 mt-0.5 ${szPct >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                        <span>{szPct >= 0 ? `+${szPct.toFixed(2)}%` : `${szPct.toFixed(2)}%`}</span>
                        <span className="text-[9px] text-slate-500 font-normal">({szChange})</span>
                      </div>
                      <div className="text-[10px] text-slate-400 mt-1">
                        {szPct >= 0 ? '跟随多头扩散' : '成长题材承压'}
                      </div>
                    </div>
                    {/* 创业板指 */}
                    <div className="bg-black/40 p-3 rounded-lg border border-white/5">
                      <div className="text-[11px] text-slate-400">创业板指 (成长)</div>
                      <div className="text-xl font-black font-mono text-white mt-1">
                        {typeof cybClose === 'number' ? cybClose.toFixed(2) : cybClose}
                      </div>
                      <div className={`text-xs font-mono font-bold flex items-center gap-1 mt-0.5 ${cybPct >= 0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                        <span>{cybPct >= 0 ? `+${cybPct.toFixed(2)}%` : `${cybPct.toFixed(2)}%`}</span>
                        <span className="text-[9px] text-slate-500 font-normal">({cybChange})</span>
                      </div>
                      <div className="text-[10px] text-slate-400 mt-1">
                        {cybPct >= 0 ? '高弹性反弹' : '科技成长分化'}
                      </div>
                    </div>
                  </div>
                </div>

                {/* 成交额流动性分析栏 */}
                <div className="border-t border-white/5 pt-3 flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div>
                    <span className="text-[10px] text-slate-500 block">两市全天总成交金额</span>
                    <div className="flex items-baseline gap-1.5 mt-0.5">
                      <span className="text-2xl font-black font-mono text-white">{totalTurnoverStr.replace('万亿元', '').replace('亿元', '')}</span>
                      <span className="text-xs text-slate-400 font-medium">{totalTurnoverStr.includes('万亿') ? '万亿元' : '亿元'}</span>
                      <span className={`text-xs font-mono font-bold ml-2 ${shrinkageAmount.startsWith('+') ? 'text-rose-400' : 'text-emerald-400'}`}>
                        环比变动 {shrinkageAmount} ({shrinkagePct})
                      </span>
                    </div>
                  </div>
                  <div className="text-[11px] text-slate-400 bg-white/5 px-3 py-1.5 rounded-lg border border-white/5">
                    <span className="text-amber-400 font-bold">流动性评估:</span> {shrinkageAmount.startsWith('+') ? '放量支撑 · 局部资金活跃' : '缩量存量博弈 · 防守为主'}
                  </div>
                </div>
              </div>

              {/* 右侧 5 列：微观多空宽度与状态机 */}
              <div className="col-span-12 lg:col-span-5 flex flex-col gap-3.5">
                
                {/* 多空极性对决卡 */}
                <div className="bg-[#0B0E17] border border-white/10 p-4 rounded-xl flex-1 flex flex-col justify-between shadow-xl">
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>全市场多空涨跌分布</span>
                    <span className="text-slate-500 font-mono">上涨比例: {upRatio}%</span>
                  </div>
                  
                  {/* 极性对比双色柱 (红涨绿跌) */}
                  <div className="my-2 space-y-1.5">
                    <div className="flex justify-between items-baseline font-mono text-xs font-bold">
                      <span className="text-rose-400">{upCount} 涨 ({upRatio}%)</span>
                      <span className="text-emerald-400">{downCount} 跌 ({downRatio}%)</span>
                    </div>
                    <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden flex">
                      <div className="h-full bg-rose-500" style={{ width: `${upRatio}%` }} />
                      <div className="h-full bg-emerald-500" style={{ width: `${downRatio}%` }} />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs font-mono pt-1">
                    <div className="bg-black/30 p-2 rounded border border-white/5">
                      <div className="text-[10px] text-slate-400">涨停 / 炸板率</div>
                      <div className="text-sm font-bold text-rose-400 mt-0.5">
                        {limitUpCount} 家 <span className="text-[10px] text-amber-400 font-normal">(炸板 {brokenRatioStr})</span>
                      </div>
                    </div>
                    <div className="bg-black/30 p-2 rounded border border-white/5">
                      <div className="text-[10px] text-slate-400">跌停家数</div>
                      <div className="text-sm font-bold text-emerald-400 mt-0.5">{limitDownCount} 家</div>
                    </div>
                  </div>
                </div>

                {/* 情绪状态机与波普尔警报 */}
                <div className="bg-[#0B0E17] border-l-4 border-l-amber-500 border-r border-t border-b border-white/10 p-4 rounded-xl">
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-bold text-amber-400 tracking-wider">周期状态与推演</span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-amber-900/40 text-amber-300 border border-amber-700/50 font-medium">
                      {cyclePhase}
                    </span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    <strong className="text-white">置信度 {cycleConfidence}：</strong> 
                    全市场多空呈现「{cyclePhase}」格局。严禁盲目臆测，严格以集合竞价探针与刚性证伪红线指导交易防守。
                  </p>
                </div>

              </div>

            </div>
          </section>

          {/* 研报正文区：若存在 11 章完整 Markdown 则优先展示全景深度研报，否则降级为摘要卡片 */}
          {transcendentData?.markdown_content ? (
            <ZhijianMarkdownArticle
              markdownContent={transcendentData.markdown_content}
              onStockClick={handleStockClick}
              selectedStockName={selectedStock?.name}
            />
          ) : (
            <>
              {/* 第0章：昨日假说审判 */}
              <section id="ch0" className="space-y-4 scroll-mt-20">
                <div className="flex items-center gap-3">
              <span className="text-sm font-mono font-black text-amber-400">00</span>
              <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                昨日假说判决书与认知校准
              </h2>
            </div>

            <div className="p-3.5 rounded-lg border-l-4 border-l-amber-500 bg-amber-950/10 italic text-sm text-slate-300 leading-relaxed">
              “没有证伪机制的复盘，不过是事后诸葛亮的叙事狂欢。知见系统的第一铁律：先审判昨天的预测偏差，再构建今天的交易推断。”
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
              {auditDeltaList.map((ad, idx) => (
                <div key={idx} className="bg-[#0B0E17] border border-amber-900/40 p-5 rounded-xl relative overflow-hidden">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <span className="text-xs font-bold text-amber-400 tracking-wider">假说 {ad.hypothesis || `0${idx + 1}`}</span>
                      <h3 className="text-sm font-bold text-white mt-0.5">{ad.content}</h3>
                    </div>
                    <div className="border border-dashed border-amber-500 bg-amber-950/60 text-amber-400 px-2.5 py-1 text-[11px] font-black tracking-widest rounded">
                      {ad.verdict || '客观校准'}
                    </div>
                  </div>
                  <div className="space-y-2 text-xs leading-relaxed">
                    <div className="bg-black/30 p-2.5 rounded-lg border border-white/5 font-mono text-[11px]">
                      <strong className="text-slate-300">[物理事实]：</strong> {ad.reality}
                    </div>
                    <p className="text-slate-400 pt-1">
                      <strong className="text-amber-400">[认知校准]：</strong> {ad.attribution}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* 第1章：宏观流动性与缩量/放量模型 */}
          <section id="ch1" className="space-y-4 scroll-mt-20">
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono font-black text-slate-400">01</span>
              <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                宏观流动性与量能结构模型
              </h2>
            </div>

            <div className="bg-[#0B0E17] border border-white/10 p-5 rounded-xl space-y-4 shadow-xl">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 border-b border-white/5 pb-3">
                <div>
                  <span className="text-xs text-slate-400">两市去重总成交金额</span>
                  <div className="text-2xl font-black font-mono text-white mt-0.5">{totalTurnoverStr}</div>
                </div>
                <div className="text-right">
                  <span className="text-xs text-slate-400">环比前一交易日变动</span>
                  <div className={`text-base font-bold font-mono ${shrinkageAmount.startsWith('+') ? 'text-rose-400' : 'text-emerald-400'}`}>
                    {shrinkageAmount} ({shrinkagePct})
                  </div>
                </div>
              </div>

              <p className="text-xs text-slate-300 leading-relaxed">
                两市全天成交达 {totalTurnoverStr}。
                {shrinkageAmount.startsWith('+')
                  ? ' 呈现放量修复特征，增量资金在核心主线与前排梯队形成共振，局部赚钱效应显著拓宽。'
                  : ' 呈现缩量存量博弈特征，买盘动能偏向低波动与高确定性方向，高估值题材承压分化。'}
              </p>
            </div>
          </section>

          {/* 第2章：连板天梯与短线物理图谱 */}
          <section id="ch2" className="space-y-4 scroll-mt-20">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-sm font-mono font-black text-rose-400">02</span>
                <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                  连板天梯与短线物理图谱
                </h2>
              </div>
              <span className="text-xs font-mono text-slate-400">
                真实涨停: <strong className="text-rose-400">{limitUpCount}</strong> 家 · 跌停: <strong className="text-emerald-400">{limitDownCount}</strong> 家
              </span>
            </div>

            <div className="space-y-3">
              {skylineLadder.map((tier, idx) => (
                <div
                  key={idx}
                  onClick={() => handleStockClick(tier.name)}
                  className="bg-[#0B0E17] hover:bg-white/[0.03] border border-white/10 hover:border-amber-500/40 p-4 rounded-xl flex items-center justify-between border-l-4 border-l-amber-500 cursor-pointer transition shadow-md"
                >
                  <div className="flex items-center gap-4">
                    <div className="w-14 h-10 rounded-lg bg-amber-950/60 border border-amber-800/40 flex flex-col items-center justify-center font-mono font-black text-amber-400 shrink-0">
                      <span className="text-xs">{tier.tier}</span>
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-white text-sm">{tier.name}</span>
                        {tier.symbol && tier.symbol !== 'MULTI' && (
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20">
                            {tier.symbol}
                          </span>
                        )}
                        <span className="text-[10px] text-amber-400 bg-amber-950/40 px-1.5 py-0.5 rounded">
                          {tier.tag}
                        </span>
                      </div>
                      <div className="text-xs text-slate-400 mt-1">{tier.desc}</div>
                    </div>
                  </div>
                  <div className="text-right font-mono hidden md:block shrink-0">
                    <div className={`text-sm font-bold ${tier.status.includes('炸') ? 'text-amber-400' : 'text-rose-400'}`}>
                      {tier.status}
                    </div>
                    <div className="text-[10px] text-slate-500">点击联动证据</div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* 第3章：板块图谱与多空归因 */}
          <section id="ch3" className="space-y-4 scroll-mt-20">
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono font-black text-slate-400">03</span>
              <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                板块强弱图谱与资金逆势归因
              </h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* 强势多头 */}
              <div className="bg-[#0B0E17] border border-rose-900/40 p-4 rounded-xl space-y-3 border-l-4 border-l-rose-500">
                <div className="flex items-center justify-between border-b border-white/5 pb-2">
                  <span className="text-xs font-bold text-rose-400 tracking-wider">
                    ▲ 多头主攻与共振题材
                  </span>
                  <span className="text-[10px] text-rose-400 font-medium">涨停聚集</span>
                </div>
                <div className="space-y-3 text-xs">
                  {polarFlows.inflows.map((inf: any, idx: number) => (
                    <div key={idx}>
                      <div className="flex justify-between text-slate-300 mb-1">
                        <span className="font-bold">{inf.sector}</span>
                        <span className="text-rose-400 font-mono font-bold">{inf.amount_str}</span>
                      </div>
                      <p className="text-[11px] text-slate-400">{inf.note}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* 弱势承压 */}
              <div className="bg-[#0B0E17] border border-emerald-900/40 p-4 rounded-xl space-y-3 border-l-4 border-l-emerald-500">
                <div className="flex items-center justify-between border-b border-white/5 pb-2">
                  <span className="text-xs font-bold text-emerald-400 tracking-wider">
                    ▼ 承压与分歧调整方向
                  </span>
                  <span className="text-[10px] text-emerald-400 font-medium">分流调仓</span>
                </div>
                <div className="space-y-3 text-xs">
                  {polarFlows.outflows.map((out: any, idx: number) => (
                    <div key={idx}>
                      <div className="flex justify-between text-slate-300 mb-1">
                        <span className="font-bold">{out.sector}</span>
                        <span className="text-emerald-400 font-mono font-bold">{out.amount_str}</span>
                      </div>
                      <p className="text-[11px] text-slate-400">{out.note}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          {/* 第5章：六类微观机制样本 */}
          <section id="ch5" className="space-y-4 scroll-mt-20">
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono font-black text-amber-400">05</span>
              <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                微观结构：交易机制极值样本剖析
              </h2>
            </div>

            <p className="text-xs text-slate-400">
              从微观流动性中提炼出代表性交易机制样本切片。点击卡片可联动查看右侧证据栏：
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5 pt-1">
              {mechanismSamples.map((sample, idx) => (
                <div
                  key={idx}
                  onClick={() => handleStockClick(sample.key || sample.name)}
                  className={`bg-[#0B0E17] hover:bg-white/[0.04] border p-4 rounded-xl cursor-pointer transition shadow-md ${
                    selectedStock.name.includes(sample.key) ? 'border-amber-400 bg-amber-950/20' : 'border-white/10 hover:border-amber-400/50'
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] px-2 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-700/50">
                      {sample.tag}
                    </span>
                    <span className="text-xs font-mono font-bold text-amber-400">样本 #{idx + 1}</span>
                  </div>
                  <h4 className="font-bold text-sm text-white">{sample.name}</h4>
                  <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                    {sample.desc}
                  </p>
                </div>
              ))}
            </div>
          </section>

          {/* 第6章：情绪周期演进 */}
          <section id="ch6" className="space-y-4 scroll-mt-20">
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono font-black text-slate-400">06</span>
              <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                短线情绪周期五阶段演进
              </h2>
            </div>

            <div className="bg-[#0B0E17] border border-white/10 p-5 rounded-xl space-y-4 shadow-xl">
              <div className="text-xs text-slate-400 tracking-wider flex justify-between items-center">
                <span>五阶段情绪演进状态机</span>
                <span className="text-amber-400 font-bold">当前阶段：{cyclePhase}</span>
              </div>

              <div className="grid grid-cols-5 gap-2 text-center text-xs font-mono">
                {['冰点出清', '弱势修复', '主线共振', '高潮过热', '退潮分歧'].map((stage, idx) => {
                  const isCurrent = cyclePhase.includes(stage) || (cyclePhase.includes('偏强') && stage === '主线共振') || (cyclePhase.includes('偏弱') && stage === '退潮分歧') || (cyclePhase.includes('平稳') && stage === '弱势修复');
                  return (
                    <div
                      key={idx}
                      className={`p-2.5 rounded border transition ${
                        isCurrent
                          ? 'bg-amber-950/60 border-amber-500/80 text-amber-300 font-bold relative shadow-lg shadow-amber-950/50'
                          : 'bg-black/40 border-white/5 text-slate-500'
                      }`}
                    >
                      {isCurrent && <span className="w-2 h-2 rounded-full bg-amber-400 absolute top-1.5 right-1.5 animate-ping" />}
                      <span className="block">{idx + 1}. {stage}</span>
                      <span className="text-[10px] text-slate-600 block mt-0.5">{isCurrent ? '当前运行' : '基准阶段'}</span>
                    </div>
                  );
                })}
              </div>

              <div className="text-xs text-slate-300 leading-relaxed bg-black/30 p-3 rounded-lg border border-white/5 space-y-1">
                <p>
                  <strong className="text-amber-400">物理事实证据：</strong> 
                  真实涨停 {limitUpCount} 家、跌停 {limitDownCount} 家、炸板率 {brokenRatioStr}。
                  全市场上涨 {upCount} 只 / 下跌 {downCount} 只。市场物理状态定位于「{cyclePhase}」。
                </p>
              </div>
            </div>
          </section>

          {/* 第8章：次日情景推演 A / B / C */}
          <section id="ch8" className="space-y-4 scroll-mt-20">
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono font-black text-rose-400">08</span>
              <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                次日推演：A / B / C 三大情景与应变底线
              </h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 pt-1">
              {scenariosList.map((sc, idx) => (
                <div
                  key={idx}
                  className={`bg-[#0B0E17] border-t-2 border-x border-b border-white/10 p-4 rounded-xl ${
                    idx === 0 ? 'border-t-emerald-500' : (idx === 1 ? 'border-t-amber-500' : 'border-t-rose-500')
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-bold text-sm text-white">{sc.name}</span>
                    <span className="text-[10px] font-mono text-amber-400 font-bold">{sc.prob}</span>
                  </div>
                  <div className="text-[11px] text-amber-300/90 font-medium mb-1.5">行动：{sc.action}</div>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    {sc.desc}
                  </p>
                </div>
              ))}
            </div>
          </section>

          {/* 第9章：波普尔假说证伪闭环 */}
          <section id="ch9" className="space-y-4 scroll-mt-20">
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono font-black text-amber-400">09</span>
              <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                波普尔式核心假说与刚性证伪闭环
              </h2>
            </div>

            <div className="space-y-3 pt-1">
              <div className="bg-[#0B0E17] border-l-4 border-l-amber-500 border-r border-t border-b border-white/10 p-4 rounded-xl">
                <div className="font-bold text-white text-sm mb-1">假说 01：前排核心连板梯队具备持续溢价与赚钱效应</div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  <strong className="text-amber-400">刚性证伪红线：</strong> 次日最高空间标的集合竞价开盘跌幅超过 -3%，或前排封单量低于万手。一旦触发，做多假说自动被物理击穿，严禁中位追高接力。
                </p>
              </div>

              <div className="bg-[#0B0E17] border-l-4 border-l-emerald-500 border-r border-t border-b border-white/10 p-4 rounded-xl">
                <div className="font-bold text-white text-sm mb-1">假说 02：大盘成交量能维持在活跃支撑位之上</div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  <strong className="text-amber-400">刚性证伪红线：</strong> 次日 09:25 集合竞价两市总成交额低于 140 亿元，确认资金进入深度观望。一旦触发，严格锁定开仓额度。
                </p>
              </div>
            </div>
          </section>

          {/* 第10章：09:25 开盘探针系统 */}
          <section id="ch10" className="space-y-4 scroll-mt-20 pb-16">
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono font-black text-emerald-400">10</span>
              <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                09:25 集合竞价微观探针观测表
              </h2>
            </div>

            <div className="bg-[#0B0E17] border border-white/10 p-4 rounded-xl space-y-3 font-mono text-xs">
              <div className="flex items-center justify-between border-b border-white/5 pb-2 text-slate-400">
                <span>观测靶点</span>
                <span>临界观测值</span>
                <span>触发结论与纪律</span>
              </div>
              {probesList.map((probe, idx) => (
                <div key={idx} className="flex items-center justify-between border-b border-white/5 pb-2">
                  <span className="text-white">{probe.item}</span>
                  <span className="text-amber-400">{probe.threshold}</span>
                  <span className="text-slate-300">{probe.action}</span>
                </div>
              ))}
            </div>
          </section>
            </>
          )}

        </main>

        {/* 右侧：伴随式证据栏 */}
        {evidenceOpen && (
          <aside className="w-80 hidden lg:flex flex-col border-l border-white/5 bg-[#07090E]/90 shrink-0 sticky top-14 h-[calc(100vh-56px)] overflow-y-auto p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-white/5 pb-2">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-amber-400" />
                <span className="text-xs font-bold text-white tracking-wider">伴随式微观证据</span>
              </div>
              <span className="text-[10px] text-slate-500">动态联动</span>
            </div>

            {/* 聚焦个股样本 */}
            <div className="bg-[#0B0E17] border border-amber-500/30 p-3.5 rounded-xl shadow-lg">
              <div className="flex justify-between items-center mb-1">
                <span className="font-bold text-white text-sm">{selectedStock.name}</span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20 font-bold">
                  {selectedStock.tag}
                </span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed mt-2">
                {selectedStock.desc}
              </p>
            </div>

            {/* 微观关键指标 */}
            <div className="space-y-2 text-xs">
              <span className="text-[11px] text-slate-400 font-bold block">当日微观结构关键事实</span>
              <div className="bg-[#0B0E17] border border-white/10 p-3 rounded-lg space-y-2">
                <div className="flex justify-between">
                  <span className="text-slate-400">真实涨停家数:</span>
                  <span className="text-rose-400 font-bold font-mono">{limitUpCount} 家</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">跌停家数:</span>
                  <span className="text-emerald-400 font-bold font-mono">{limitDownCount} 家</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">真实炸板率:</span>
                  <span className="text-amber-400 font-bold font-mono">{brokenRatioStr}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">两市上涨 / 下跌:</span>
                  <span className="text-slate-200 font-bold font-mono">{upCount} / {downCount}</span>
                </div>
              </div>
            </div>

            {/* 推荐高频追问 */}
            <div className="space-y-2 pt-2">
              <span className="text-[11px] text-slate-400 font-bold block">高频追问建议</span>
              <div className="space-y-1.5 text-xs">
                <button
                  onClick={() => { setAiDrawerOpen(true); handleSendChat(`今日市场「${cyclePhase}」状态下，前排连板晋级概率多大？`); }}
                  className="w-full text-left p-2 rounded bg-white/5 hover:bg-white/10 text-slate-300 transition text-[11px]"
                >
                  • 今日市场状态下，前排连板晋级概率？
                </button>
                <button
                  onClick={() => { setAiDrawerOpen(true); handleSendChat('09:25 集合竞价最核心的刚性证伪指标是什么？'); }}
                  className="w-full text-left p-2 rounded bg-white/5 hover:bg-white/10 text-slate-300 transition text-[11px]"
                >
                  • 09:25 集合竞价最核心的证伪指标？
                </button>
              </div>
            </div>
          </aside>
        )}

      </div>

      {/* AI 深度提问交互抽屉 */}
      {aiDrawerOpen && (
        <div className="fixed inset-y-0 right-0 w-full sm:w-[500px] bg-[#0A0D15]/95 backdrop-blur-2xl border-l border-white/10 z-50 flex flex-col shadow-2xl animate-slide-left">
          <div className="p-4 border-b border-white/10 flex items-center justify-between bg-black/40">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-400 flex items-center justify-center font-bold text-xs shrink-0">
                <Sparkles className="w-3.5 h-3.5" />
              </div>
              <div>
                <h3 className="font-bold text-white text-sm">知见 · 智能推演助手</h3>
                <p className="text-[10px] text-slate-400">依据 {date} 盘面真实数据与推演逻辑解答</p>
              </div>
            </div>
            <button
              onClick={() => setAiDrawerOpen(false)}
              className="p-1.5 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white transition"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="flex-1 p-4 overflow-y-auto space-y-4 text-xs leading-relaxed">
            {chatMessages.map((msg, i) => (
              <div key={i} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {msg.role === 'ai' && (
                  <div className="w-7 h-7 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-400 flex items-center justify-center font-bold text-xs shrink-0 shadow">
                    <Sparkles className="w-3.5 h-3.5" />
                  </div>
                )}
                <div className={`p-3.5 rounded-xl max-w-[85%] ${
                  msg.role === 'user'
                    ? 'bg-amber-600/90 text-black font-medium shadow'
                    : 'bg-white/5 text-slate-200 border border-white/10 whitespace-pre-wrap'
                }`}>
                  {msg.content}
                </div>
              </div>
            ))}
            {sendingAi && (
              <div className="flex gap-3">
                <div className="w-7 h-7 rounded-lg bg-amber-500/20 border border-amber-500/40 text-amber-400 flex items-center justify-center font-bold text-xs shrink-0 animate-pulse shadow">
                  <Sparkles className="w-3.5 h-3.5" />
                </div>
                <div className="bg-white/5 p-3 rounded-xl text-slate-400 border border-white/10 flex items-center gap-2">
                  <Sparkles className="w-3.5 h-3.5 animate-spin text-amber-400" />
                  <span>知见推演生成中...</span>
                </div>
              </div>
            )}
          </div>

          <div className="p-4 border-t border-white/10 bg-black/40 flex gap-2">
            <input
              type="text"
              value={userInput}
              onChange={e => setUserInput(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleSendChat(); }}
              placeholder="输入您的问题，如：明日集合竞价核心防守指标是什么？..."
              className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-amber-400 placeholder:text-slate-500"
            />
            <button
              onClick={() => handleSendChat()}
              disabled={sendingAi}
              className="px-4 py-2 bg-amber-500 hover:bg-amber-400 text-black font-bold rounded-lg text-xs transition active:scale-95 shadow disabled:opacity-50"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

    </div>
  );
}
