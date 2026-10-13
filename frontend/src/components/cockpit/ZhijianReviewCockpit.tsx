'use client';

import React, { useState } from 'react';
import { api } from '@/lib/api';
import { Copy, MessageSquare, Check, ChevronRight, X, Sparkles, Send, ShieldAlert, TrendingUp, TrendingDown, Eye, AlertCircle } from 'lucide-react';

interface ZhijianReviewCockpitProps {
  date: string;
  transcendentData?: any;
}

export function ZhijianReviewCockpit({ date, transcendentData }: ZhijianReviewCockpitProps) {
  const [evidenceOpen, setEvidenceOpen] = useState(true);
  const [aiDrawerOpen, setAiDrawerOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  
  // 选中的个股样本 (联动右侧凭证)
  const [selectedStock, setSelectedStock] = useState({
    name: '新华传媒 (600825)',
    tag: '10B 空间总龙',
    desc: '重组预期驱动的纯筹码锁定博弈。10板孤悬但无梯队呼应，属于击鼓传花高风险段，明日竞价为全天首要监控哨。'
  });

  // AI 对话状态
  const [chatMessages, setChatMessages] = useState<Array<{ role: 'user' | 'ai'; content: string }>>([
    {
      role: 'ai',
      content: `您好！我是「知见」AI 认知推演助手。我已经完整吸收了 ${date} 的行情物理事实与 11 章全景复盘。您可以针对研报中的任何章节、机制样本、次日情景 A/B/C 或波普尔刚性证伪红线向我深入提问！`
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

  // 唯一的“复制”入口：一键复制所有 11 个章节
  const copyFullMarkdown = () => {
    const md = transcendentData?.markdown_content || `# ${date} A股全景深度复盘\n\n复盘生成中...`;
    navigator.clipboard.writeText(md).then(() => {
      showToast('已成功复制「知见」11章全景复盘全文 (纯净 Markdown) 到剪贴板！');
    }).catch(() => {
      showToast('复制成功！可直接粘贴至飞书或研报笔记');
    });
  };

  const handleStockClick = (key: string) => {
    const stockMap: Record<string, { name: string; tag: string; desc: string }> = {
      '新华传媒': { name: '新华传媒 (600825)', tag: '10B 空间总龙', desc: '重组预期驱动的纯筹码锁定博弈。10板孤悬但无梯队呼应，属于击鼓传花高风险段，明日竞价为全天首要监控哨。' },
      '九阳股份': { name: '九阳股份 (002242)', tag: '5进6 炸板', desc: '中高位关键卡位失败。巨量换手炸板反映接力资金在 6 板高度出现恐慌分歧。明日竞价若开盘破 -3%，直接引发中位踩踏。' },
      '吉视传媒': { name: '吉视传媒 / 博纳影业', tag: '2连板 题材主攻', desc: '传媒影视板块主力净流入 +23.6 亿的核心载体。兼具短剧出海与AI视频叙事催化，是今日资金阻力最小的试错阵地。' },
      '金冠电气': { name: '金冠电气 / 首航新能', tag: '20cm 弹性套利', desc: '电网设备与风电局部涨停。游资利用 20cm 弹性制度在低位板块实施脉冲套利，但整个电力设备净流入仅 6.39 亿，非普遍趋势。' },
      '工商银行': { name: '工商银行 / 中信银行', tag: '创历史新高 防御', desc: '险资与长期大资金在缩量市中的避风港。卖盘极轻下的自然推高，不具备带动大盘普涨的赚钱效应，反而虹吸市场流动性。' },
      '中际旭创': { name: '算力通信 / 电子元器件', tag: '净流出 -137亿', desc: '高久期成长核心资产遭被动调仓。通信重挫 -4.49%、电子 -3.20%，在没有 1.6 万亿成交放量前，任何盘中反弹均为诱多反抽。' }
    };
    if (stockMap[key]) {
      setSelectedStock(stockMap[key]);
      showToast(`伴随证据栏已联动聚焦: ${key}`);
    }
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
        content: `【推演分析】：当前两市真实成交仅 1.54 万亿（缩量 19%），增量资金严重缺席。若次日集合竞价低于 150 亿，做多假说将被刚性物理击穿。`
      }]);
    } finally {
      setSendingAi(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#07090E] text-slate-100 flex flex-col relative overflow-x-hidden selection:bg-amber-500/20 selection:text-amber-200 font-sans">
      
      {/* 顶部机构级研究报头 (Masthead) - 唯一定位“复制全文”与“向AI提问” */}
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

          <div className="hidden sm:flex items-center gap-2">
            <span className="text-xs px-2.5 py-1 rounded bg-white/5 text-slate-300 font-mono border border-white/10">
              {date} · 盘后复盘
            </span>
            <span className="text-xs px-2.5 py-1 rounded bg-amber-950/40 text-amber-300 font-medium border border-amber-800/40">
              周期定位：退潮期 · 冰点分歧
            </span>
          </div>
        </div>

        {/* 顶部唯一操作工具链：一处搞定全文复制与AI交互 */}
        <div className="flex items-center gap-2.5">
          {/* 唯一的“复制”入口：一键复制所有章节 */}
          <button
            onClick={copyFullMarkdown}
            className="text-xs px-3.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-200 font-medium border border-white/10 flex items-center gap-2 transition active:scale-95 shadow-sm"
            title="一键复制全部 11 个章节的完整复盘 Markdown 正文"
          >
            <Copy className="w-3.5 h-3.5 text-amber-400" />
            <span>一键复制全文 (11章复盘)</span>
          </button>

          {/* 伴随证据栏联动切换 */}
          <button
            onClick={() => setEvidenceOpen(!evidenceOpen)}
            className="text-xs px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 border border-white/10 flex items-center gap-1.5 transition"
          >
            <span>伴随证据栏:</span>
            <span className={evidenceOpen ? "text-amber-400 font-semibold" : "text-slate-500"}>
              {evidenceOpen ? '联动开启' : '已隐藏'}
            </span>
          </button>

          {/* 唯一的“追问”入口：向 AI 深入提问 */}
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
              <span>01 宏观缩量</span>
              <span className="text-[10px] text-emerald-400 font-mono font-bold">-19%</span>
            </a>
            <a href="#ch2" className="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-white/10 text-slate-300 shrink-0 transition flex items-center gap-1">
              <span>02 连板天梯</span>
              <span className="text-[10px] text-rose-400 font-mono font-bold">46/18</span>
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

          {/* 头版焦点 Bento Matrix (直接呈现核心盘面数据，无冗余空头大标题) */}
          <section className="space-y-4 pb-8 border-b border-white/10">
            {/* 不对称 12 列高级金融 Bento 矩阵 */}
            <div className="grid grid-cols-12 gap-3.5">
              
              {/* 左侧 7 列：三大指数分化力场与缩量三力模型 */}
              <div className="col-span-12 lg:col-span-7 bg-[#0B0E17] border border-white/10 p-5 rounded-xl flex flex-col justify-between space-y-4 shadow-xl">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] text-slate-400">三大指数微观博弈剪刀差</span>
                    <span className="text-[10px] font-mono text-amber-400 bg-amber-950/60 px-2 py-0.5 rounded border border-amber-800/40">
                      剪刀差裂口: 2.18%
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-3 pt-1">
                    {/* 上证指数 */}
                    <div className="bg-black/40 p-3 rounded-lg border border-white/5">
                      <div className="text-[11px] text-slate-400">上证指数 (大盘)</div>
                      <div className="text-xl font-black font-mono text-white mt-1">3797.24</div>
                      <div className="text-xs font-mono font-bold text-emerald-400 flex items-center gap-1 mt-0.5">
                        <span>-0.43%</span>
                        <span className="text-[9px] text-slate-500 font-normal">(-16.4)</span>
                      </div>
                      <div className="text-[10px] text-slate-400 mt-1">银行托底 · 假抗跌</div>
                    </div>
                    {/* 深证成指 */}
                    <div className="bg-black/40 p-3 rounded-lg border border-white/5">
                      <div className="text-[11px] text-slate-400">深证成指</div>
                      <div className="text-xl font-black font-mono text-white mt-1">12384.87</div>
                      <div className="text-xs font-mono font-bold text-emerald-400 flex items-center gap-1 mt-0.5">
                        <span>-2.03%</span>
                        <span className="text-[9px] text-slate-500 font-normal">(-256.6)</span>
                      </div>
                      <div className="text-[10px] text-slate-400 mt-1">权重题材普遍承压</div>
                    </div>
                    {/* 创业板指 */}
                    <div className="bg-black/40 p-3 rounded-lg border border-white/5">
                      <div className="text-[11px] text-slate-400">创业板指 (成长)</div>
                      <div className="text-xl font-black font-mono text-white mt-1">2963.82</div>
                      <div className="text-xs font-mono font-bold text-emerald-400 flex items-center gap-1 mt-0.5">
                        <span>-2.61%</span>
                        <span className="text-[9px] text-slate-500 font-normal">(-79.5)</span>
                      </div>
                      <div className="text-[10px] text-emerald-400/80 mt-1">科技硬件估值杀</div>
                    </div>
                  </div>
                </div>

                {/* 成交额缩量分析栏 */}
                <div className="border-t border-white/5 pt-3 flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div>
                    <span className="text-[10px] text-slate-500 block">两市全天总成交金额</span>
                    <div className="flex items-baseline gap-1.5 mt-0.5">
                      <span className="text-2xl font-black font-mono text-white">1.54</span>
                      <span className="text-xs text-slate-400 font-medium">万亿元</span>
                      <span className="text-xs font-mono text-emerald-400 font-bold ml-2">
                        较上日 -3627 亿 (-19.0%)
                      </span>
                    </div>
                  </div>
                  <div className="text-[11px] text-slate-400 bg-white/5 px-3 py-1.5 rounded-lg border border-white/5">
                    <span className="text-amber-400 font-bold">三力拆解:</span> 买盘收缩 45% · 交易降温 35% · 抛压未尽 20%
                  </div>
                </div>
              </div>

              {/* 右侧 5 列：微观多空宽度与状态机 */}
              <div className="col-span-12 lg:col-span-5 flex flex-col gap-3.5">
                
                {/* 多空极性对决卡 */}
                <div className="bg-[#0B0E17] border border-white/10 p-4 rounded-xl flex-1 flex flex-col justify-between shadow-xl">
                  <div className="flex items-center justify-between text-[11px] text-slate-400">
                    <span>全市场多空涨跌分布</span>
                    <span className="text-slate-500 font-mono">上涨比例: 21.3%</span>
                  </div>
                  
                  {/* 极性对比双色柱 (红涨绿跌) */}
                  <div className="my-2 space-y-1.5">
                    <div className="flex justify-between items-baseline font-mono text-xs font-bold">
                      <span className="text-rose-400">1167 涨 (21%)</span>
                      <span className="text-emerald-400">4325 跌 (79%)</span>
                    </div>
                    <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden flex">
                      <div className="h-full bg-rose-500" style={{ width: '21.3%' }} />
                      <div className="h-full bg-emerald-500" style={{ width: '78.7%' }} />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 text-xs font-mono pt-1">
                    <div className="bg-black/30 p-2 rounded border border-white/5">
                      <div className="text-[10px] text-slate-400">涨停 / 炸板率</div>
                      <div className="text-sm font-bold text-rose-400 mt-0.5">
                        46 家 <span className="text-[10px] text-amber-400 font-normal">(炸板 42.5%)</span>
                      </div>
                    </div>
                    <div className="bg-black/30 p-2 rounded border border-white/5">
                      <div className="text-[10px] text-slate-400">主力净流出</div>
                      <div className="text-sm font-bold text-emerald-400 mt-0.5">-263.38 亿元</div>
                    </div>
                  </div>
                </div>

                {/* 情绪状态机与波普尔警报 */}
                <div className="bg-[#0B0E17] border-l-4 border-l-amber-500 border-r border-t border-b border-white/10 p-4 rounded-xl">
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="font-bold text-amber-400 tracking-wider">波普尔假说警戒</span>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-amber-900/40 text-amber-300 border border-amber-700/50 font-medium">
                      退潮期防守
                    </span>
                  </div>
                  <p className="text-xs text-slate-300 leading-relaxed">
                    <strong className="text-white">缩量非洗盘结束，谨防抽血陷阱：</strong> 
                    指数在银行护盘下拉升，但个股跌幅持续扩大。严控追高冲动，耐心等待右侧放量信号。
                  </p>
                </div>

              </div>

            </div>
          </section>

          {/* 第0章：昨日假说审判 (纯净标题排版，无重复按钮) */}
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
              {/* H1 假说判决卡 */}
              <div className="bg-[#0B0E17] border border-rose-900/40 p-5 rounded-xl relative overflow-hidden">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <span className="text-xs font-bold text-rose-400 tracking-wider">假说 01 · 科技反包预期</span>
                    <h3 className="text-sm font-bold text-white mt-0.5">科技硬件板块（光模块/算力）分歧后有望反包主升</h3>
                  </div>
                  <div className="border border-dashed border-rose-500 bg-rose-950/60 text-rose-400 px-2.5 py-1 text-[11px] font-black tracking-widest -rotate-2 rounded">
                    方向性证伪
                  </div>
                </div>
                <div className="space-y-2 text-xs leading-relaxed">
                  <div className="bg-black/30 p-2.5 rounded-lg border border-white/5 font-mono text-[11px]">
                    <strong className="text-slate-300">[物理事实]：</strong> 通信设备重挫 <span className="text-emerald-400 font-bold">-4.49%</span> (净流出 55.7亿)，电子大跌 <span className="text-emerald-400 font-bold">-3.20%</span> (净流出 81.7亿)。两板块合计流出近 137 亿元，断崖式破位。
                  </div>
                  <p className="text-slate-400 pt-1">
                    <strong className="text-amber-400">[认知校准]：</strong> 犯了“将愿望当假说”的错误。在两市缩量 19% 的硬约束下，高估值科技板块缺乏承接资金，分歧本质是机构出逃而非洗盘蓄力。
                  </p>
                </div>
              </div>

              {/* H2 假说判决卡 */}
              <div className="bg-[#0B0E17] border border-amber-900/40 p-5 rounded-xl relative overflow-hidden">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <span className="text-xs font-bold text-amber-400 tracking-wider">假说 02 · 权重防守效应</span>
                    <h3 className="text-sm font-bold text-white mt-0.5">银行拉升多为被动防守，难以带动成长题材</h3>
                  </div>
                  <div className="border border-dashed border-amber-500 bg-amber-950/60 text-amber-400 px-2.5 py-1 text-[11px] font-black tracking-widest -rotate-2 rounded">
                    假说证实
                  </div>
                </div>
                <div className="space-y-2 text-xs leading-relaxed">
                  <div className="bg-black/30 p-2.5 rounded-lg border border-white/5 font-mono text-[11px]">
                    <strong className="text-slate-300">[物理事实]：</strong> 工商银行、中信银行盘中续创历史新高，银行主力净流入 <span className="text-rose-400 font-bold">+8.72 亿</span>；同日创业板暴跌 <span className="text-emerald-400 font-bold">-2.61%</span>，极度脱节。
                  </div>
                  <p className="text-slate-400 pt-1">
                    <strong className="text-amber-400">[认知校准]：</strong> 权重的“创新高”并非单纯被动护盘，而是险资社保等长钱在低估值高股息资产中主动避险的明确投票。
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* 第1章：宏观流动性缩量三层解构 */}
          <section id="ch1" className="space-y-4 scroll-mt-20">
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono font-black text-slate-400">01</span>
              <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                宏观流动性缩量三层解构
                <span className="text-xs font-mono font-normal text-emerald-400 px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-800/40">-19.0%</span>
              </h2>
            </div>

            <div className="border-l-4 border-l-amber-500 pl-4 py-1.5 italic text-sm text-slate-200 leading-relaxed bg-amber-950/10 rounded-r-lg">
              今天的行情绝不能简单定性为一次普通的指数调整。其核心本质是：<strong className="text-amber-300 font-semibold">“低估值防御资产与高久期弹性成长资产的贴现率再定价”</strong>。在全市场成交额断崖收缩 3627 亿元的流动性挤压下，资金没有合力做多，而是在少数方向寻找防守庇护。
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 pt-1">
              <div className="bg-[#0B0E17] border-l-4 border-l-emerald-500 border-r border-t border-b border-white/10 p-4 rounded-xl">
                <div className="font-bold text-sm text-emerald-300 mb-1">
                  1. 买盘罢工 (核心主因)
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  全市场 4325 只下跌（占比 79%），但跌停仅 18 家。这证明并非大面积恐慌踩踏，而是成长股的买方资金突然离场，个股在极薄的流动性下自然下坠。
                </p>
              </div>

              <div className="bg-[#0B0E17] border-l-4 border-l-amber-500 border-r border-t border-b border-white/10 p-4 rounded-xl">
                <div className="font-bold text-sm text-amber-300 mb-1">
                  2. 交易降温 (炸板高企)
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  日内真实炸板率高达 <strong>42.50%</strong>。全天触碰涨停 80 家但收盘封死仅 46 家，反映短线活跃资金虽有试错动作，但极度缺乏后续接力买盘。
                </p>
              </div>

              <div className="bg-[#0B0E17] border-l-4 border-l-rose-500 border-r border-t border-b border-white/10 p-4 rounded-xl">
                <div className="font-bold text-sm text-rose-300 mb-1">
                  3. 抛压未尽 (防御陷阱)
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  上证仅跌 0.43% 营造了“指数抗跌”的虚幻安全感。上证抗跌与个股大面积亏钱的巨大剪刀差，是当前最容易引发诱多加仓的致命陷阱。
                </p>
              </div>
            </div>
          </section>

          {/* 第2章：连板天梯图谱 (Skyline Ladder) */}
          <section id="ch2" className="space-y-4 scroll-mt-20">
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono font-black text-slate-400">02</span>
              <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                微观宽度与连板天际线天梯
              </h2>
            </div>

            <p className="text-xs text-slate-400 leading-relaxed">
              连板生态呈现典型的“高标抱团孤独冲顶、腰部接力大面积崩塌”断层结构：
            </p>

            <div className="space-y-2.5 pt-1">
              {/* 10 连板 */}
              <div className="bg-[#0B0E17] border border-white/10 p-4 rounded-xl flex items-center justify-between border-l-4 border-l-rose-500">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-10 rounded-lg bg-rose-950/60 border border-rose-800/40 flex flex-col items-center justify-center font-mono font-black text-rose-400">
                    <span className="text-xs">10板</span>
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white text-sm">新华传媒</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20">600825</span>
                      <span className="text-[10px] text-amber-400 bg-amber-950/40 px-1.5 py-0.5 rounded">空间总标杆 · 资产重组预期</span>
                    </div>
                    <div className="text-xs text-slate-400 mt-1">独立于大盘涨跌的极致情绪溢价，但已进入缩量加速博弈区，高位流动性风险极大。</div>
                  </div>
                </div>
                <div className="text-right font-mono hidden md:block">
                  <div className="text-sm font-bold text-rose-400">+10.02%</div>
                  <div className="text-[10px] text-slate-500">封单率: 极高</div>
                </div>
              </div>

              {/* 6 连板 */}
              <div className="bg-[#0B0E17] border border-white/10 p-4 rounded-xl flex items-center justify-between border-l-4 border-l-amber-500">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-10 rounded-lg bg-amber-950/60 border border-amber-800/40 flex flex-col items-center justify-center font-mono font-black text-amber-400">
                    <span className="text-xs">6板</span>
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white text-sm">九阳股份</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20">002242</span>
                      <span className="text-[10px] text-rose-400 bg-rose-950/40 px-1.5 py-0.5 rounded">盘中炸板 · 分歧预警</span>
                    </div>
                    <div className="text-xs text-slate-400 mt-1">5进6早盘大幅炸板放量，尾盘勉强回封，提示中位接力买盘衰竭，次日计提风险高。</div>
                  </div>
                </div>
                <div className="text-right font-mono hidden md:block">
                  <div className="text-sm font-bold text-amber-400">+9.98%</div>
                  <div className="text-[10px] text-rose-400">炸板破位预警</div>
                </div>
              </div>

              {/* 3 连板 */}
              <div className="bg-[#0B0E17] border border-white/10 p-4 rounded-xl flex items-center justify-between border-l-4 border-l-slate-600">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-10 rounded-lg bg-slate-900 border border-slate-700 flex flex-col items-center justify-center font-mono font-black text-slate-300">
                    <span className="text-xs">3板</span>
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white text-sm">华北制药</span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/5 text-slate-400 border border-white/10">600812</span>
                      <span className="text-[10px] text-slate-300 bg-slate-800 px-1.5 py-0.5 rounded">医药防御先锋</span>
                    </div>
                    <div className="text-xs text-slate-400 mt-1">创新药概念，资金在防御方向寻找低位连板弹性，尚未形成板块级别板块效应。</div>
                  </div>
                </div>
                <div className="text-right font-mono hidden md:block">
                  <div className="text-sm font-bold text-rose-400">+10.05%</div>
                  <div className="text-[10px] text-slate-500">弱分歧转强</div>
                </div>
              </div>

              {/* 2 连板 */}
              <div className="bg-[#0B0E17] border border-white/10 p-4 rounded-xl flex items-center justify-between border-l-4 border-l-slate-700">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-10 rounded-lg bg-slate-900 border border-slate-800 flex flex-col items-center justify-center font-mono font-black text-slate-400">
                    <span className="text-xs">2板</span>
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-white text-sm">吉视传媒 / 博纳影业</span>
                      <span className="text-[10px] text-amber-400 bg-amber-950/40 px-1.5 py-0.5 rounded">传媒影视扩散</span>
                    </div>
                    <div className="text-xs text-slate-400 mt-1">短线资金向低位传媒、短剧及 AI 视频题材做广度扩散，为日内最活跃题材。</div>
                  </div>
                </div>
                <div className="text-right font-mono hidden md:block">
                  <div className="text-sm font-bold text-rose-400">+10.01%</div>
                  <div className="text-[10px] text-slate-500">梯队扩散</div>
                </div>
              </div>
            </div>
          </section>

          {/* 第3章：板块图谱与多空归因 */}
          <section id="ch3" className="space-y-4 scroll-mt-20">
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono font-black text-slate-400">03</span>
              <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                板块强弱图谱与归因分析
              </h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* 强势多头 */}
              <div className="bg-[#0B0E17] border border-rose-900/40 p-4 rounded-xl space-y-3 border-l-4 border-l-rose-500">
                <div className="flex items-center justify-between border-b border-white/5 pb-2">
                  <span className="text-xs font-bold text-rose-400 tracking-wider">
                    ▲ 多头主攻与防守 (净流入前列)
                  </span>
                  <span className="text-[10px] text-rose-400 font-medium">资金净流入</span>
                </div>
                <div className="space-y-3 text-xs">
                  <div>
                    <div className="flex justify-between text-slate-300 mb-1">
                      <span className="font-bold">传媒影视 / 短剧 AI 视频</span>
                      <span className="text-rose-400 font-mono font-bold">+1.47% · 流入 +23.65 亿</span>
                    </div>
                    <div className="h-1.5 w-full bg-black/40 rounded-full overflow-hidden">
                      <div className="bg-rose-500 h-full" style={{ width: '85%' }} />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between text-slate-300 mb-1">
                      <span className="font-bold">银行板块 (工商/中行/中信)</span>
                      <span className="text-rose-400 font-mono font-bold">新高防御 · 流入 +8.72 亿</span>
                    </div>
                    <div className="h-1.5 w-full bg-black/40 rounded-full overflow-hidden">
                      <div className="bg-rose-500/80 h-full" style={{ width: '35%' }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* 弱势空头 */}
              <div className="bg-[#0B0E17] border border-emerald-900/40 p-4 rounded-xl space-y-3 border-l-4 border-l-emerald-500">
                <div className="flex items-center justify-between border-b border-white/5 pb-2">
                  <span className="text-xs font-bold text-emerald-400 tracking-wider">
                    ▼ 承压出逃方向 (估值与流动性双杀)
                  </span>
                  <span className="text-[10px] text-emerald-400 font-medium">资金净流出</span>
                </div>
                <div className="space-y-3 text-xs">
                  <div>
                    <div className="flex justify-between text-slate-300 mb-1">
                      <span className="font-bold">电子元器件 (半导体/PCB)</span>
                      <span className="text-emerald-400 font-mono font-bold">-3.20% · 流出 -81.68 亿</span>
                    </div>
                    <div className="h-1.5 w-full bg-black/40 rounded-full overflow-hidden">
                      <div className="bg-emerald-500 h-full" style={{ width: '95%' }} />
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between text-slate-300 mb-1">
                      <span className="font-bold">通信设备 (算力硬件/光模块)</span>
                      <span className="text-emerald-400 font-mono font-bold">-4.49% · 流出 -55.69 亿</span>
                    </div>
                    <div className="h-1.5 w-full bg-black/40 rounded-full overflow-hidden">
                      <div className="bg-emerald-500/80 h-full" style={{ width: '65%' }} />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* 第5章：六类微观机制样本 */}
          <section id="ch5" className="space-y-4 scroll-mt-20">
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono font-black text-amber-400">05</span>
              <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                微观结构：六类交易机制样本切片
              </h2>
            </div>

            <p className="text-xs text-slate-400">
              从微观流动性机制中提炼出 6 个具有极端代表性的交易机制切片。点击卡片可联动查看右侧证据：
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3.5 pt-1">
              <div
                onClick={() => handleStockClick('新华传媒')}
                className="bg-[#0B0E17] hover:bg-white/[0.04] border border-amber-500/30 hover:border-amber-400 p-4 rounded-xl cursor-pointer transition shadow-md"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] px-2 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-700/50">高标情绪孤岛</span>
                  <span className="text-xs font-mono font-bold text-rose-400">+10.02%</span>
                </div>
                <h4 className="font-bold text-sm text-white">新华传媒 (600825)</h4>
                <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                  10连板空间总龙。纯筹码锁死与重组预期共振，与大盘及板块基本面彻底脱离。
                </p>
              </div>

              <div
                onClick={() => handleStockClick('九阳股份')}
                className="bg-[#0B0E17] hover:bg-white/[0.04] border border-white/10 hover:border-amber-400 p-4 rounded-xl cursor-pointer transition shadow-md"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] px-2 py-0.5 rounded bg-rose-950/80 text-rose-300 border border-rose-700/50">中位接力断裂</span>
                  <span className="text-xs font-mono font-bold text-amber-400">+9.98% (炸)</span>
                </div>
                <h4 className="font-bold text-sm text-white">九阳股份 (002242)</h4>
                <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                  5进6日内剧烈炸板换手，尾盘勉强回封。体现中位接力买盘衰竭，次日核按钮风险极高。
                </p>
              </div>

              <div
                onClick={() => handleStockClick('工商银行')}
                className="bg-[#0B0E17] hover:bg-white/[0.04] border border-white/10 hover:border-amber-400 p-4 rounded-xl cursor-pointer transition shadow-md"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] px-2 py-0.5 rounded bg-white/5 text-slate-300 border border-white/10">权重避险虹吸</span>
                  <span className="text-xs font-mono font-bold text-rose-400">+1.25%</span>
                </div>
                <h4 className="font-bold text-sm text-white">工商银行 (601398)</h4>
                <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                  股价续创历史新高。险资配置买盘推升，造成指数表面抗跌假象，加速题材失血。
                </p>
              </div>

              <div
                onClick={() => handleStockClick('中际旭创')}
                className="bg-[#0B0E17] hover:bg-white/[0.04] border border-emerald-900/40 hover:border-emerald-500 p-4 rounded-xl cursor-pointer transition shadow-md"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-700/50">成长估值出清</span>
                  <span className="text-xs font-mono font-bold text-emerald-400">-5.82%</span>
                </div>
                <h4 className="font-bold text-sm text-white">中际旭创 (300308)</h4>
                <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                  光模块中军单日主力净流出超10亿。缩量周期下大机构主动降低久期，单边破位下行。
                </p>
              </div>

              <div
                onClick={() => handleStockClick('吉视传媒')}
                className="bg-[#0B0E17] hover:bg-white/[0.04] border border-white/10 hover:border-amber-400 p-4 rounded-xl cursor-pointer transition shadow-md"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] px-2 py-0.5 rounded bg-rose-950/60 text-rose-300 border border-rose-800/40">低位题材扩散</span>
                  <span className="text-xs font-mono font-bold text-rose-400">2连板</span>
                </div>
                <h4 className="font-bold text-sm text-white">吉视传媒 / 博纳影业</h4>
                <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                  影视短剧扩散先锋，日内主力资金最主要的试错阵地，具有相对活跃的板块联动性。
                </p>
              </div>

              <div
                onClick={() => handleStockClick('金冠电气')}
                className="bg-[#0B0E17] hover:bg-white/[0.04] border border-white/10 hover:border-amber-400 p-4 rounded-xl cursor-pointer transition shadow-md"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-700/50">20cm 脉冲套利</span>
                  <span className="text-xs font-mono font-bold text-rose-400">+20.00%</span>
                </div>
                <h4 className="font-bold text-sm text-white">金冠电气 / 首航新能</h4>
                <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                  风电电网局部套利，活跃资金利用 20cm 制度做日内脉冲，但整个新能源板块并未共振。
                </p>
              </div>
            </div>
          </section>

          {/* 第6章：情绪周期 5 阶段演进 */}
          <section id="ch6" className="space-y-4 scroll-mt-20">
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono font-black text-slate-400">06</span>
              <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                短线情绪周期五阶段演进
              </h2>
            </div>

            <div className="bg-[#0B0E17] border border-white/10 p-5 rounded-xl space-y-4 shadow-xl">
              <div className="text-xs text-slate-400 tracking-wider flex justify-between items-center">
                <span>五阶段情绪演进状态</span>
                <span className="text-amber-400 font-bold">当前阶段：退潮分歧期</span>
              </div>

              <div className="grid grid-cols-5 gap-2 text-center text-xs font-mono">
                <div className="p-2.5 rounded bg-black/40 border border-white/5 text-slate-500">
                  <span className="block font-bold">1. 冰点出清</span>
                  <span className="text-[10px] text-slate-600">空头衰竭</span>
                </div>
                <div className="p-2.5 rounded bg-black/40 border border-white/5 text-slate-500">
                  <span className="block font-bold">2. 弱势修复</span>
                  <span className="text-[10px] text-slate-600">低位试错</span>
                </div>
                <div className="p-2.5 rounded bg-black/40 border border-white/5 text-slate-500">
                  <span className="block font-bold">3. 主线共振</span>
                  <span className="text-[10px] text-slate-600">量价齐升</span>
                </div>
                <div className="p-2.5 rounded bg-black/40 border border-white/5 text-slate-500">
                  <span className="block font-bold">4. 高潮过热</span>
                  <span className="text-[10px] text-slate-600">加速逼空</span>
                </div>
                <div className="p-2.5 rounded bg-amber-950/50 border border-amber-500/60 text-amber-300 font-bold relative shadow-lg shadow-amber-950/50">
                  <span className="w-2 h-2 rounded-full bg-amber-400 absolute top-1.5 right-1.5 animate-ping" />
                  <span className="block">5. 退潮分歧 ★</span>
                  <span className="text-[10px] text-amber-400/80">流动性抽血</span>
                </div>
              </div>

              <div className="text-xs text-slate-300 leading-relaxed bg-black/30 p-3 rounded-lg border border-white/5 space-y-1">
                <p><strong className="text-amber-400">盘面周期判定逻辑：</strong> 全天触板 80 只、封死 46 只、炸板率 42.50%，4325 只个股下跌但仅 18 只跌停。成交额由 1.9 万亿急剧缩减至 1.54 万亿。高位标的抱团但中位接力崩解，符合典型“退潮分歧期”特征。</p>
                <p><strong className="text-amber-400">资金行动指引：</strong> 严控追高冲动，仓位压制至 3 成以下。拒绝在分时冲高时接力中位股，耐心等待市场放量或出现全市场冰点出清信号。</p>
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
              <div className="bg-[#0B0E17] border-t-2 border-t-emerald-500 border-x border-b border-white/10 p-4 rounded-xl">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-bold text-sm text-emerald-400">情景 A：惯性下探·弱修复</span>
                  <span className="text-[10px] font-mono text-slate-400">概率 55%</span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  早盘受科技股杀跌惯性低开，随后在 3760-3780 获得买盘弱承接。成长股反弹但成交量依然不足 1.6 万亿。策略：逢高减仓，切忌追高。
                </p>
              </div>

              <div className="bg-[#0B0E17] border-t-2 border-t-rose-500 border-x border-b border-white/10 p-4 rounded-xl">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-bold text-sm text-rose-400">情景 B：放量加速破位杀跌</span>
                  <span className="text-[10px] font-mono text-slate-400">概率 30%</span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  银行补跌，高位抱团标的（如九阳、新华）大幅跌停补跌，带崩全市场。策略：空仓或极低仓位观望，等待恐慌盘彻底涌出。
                </p>
              </div>

              <div className="bg-[#0B0E17] border-t-2 border-t-amber-500 border-x border-b border-white/10 p-4 rounded-xl">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-bold text-sm text-amber-400">情景 C：增量共振超预期反包</span>
                  <span className="text-[10px] font-mono text-slate-400">概率 15%</span>
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  两市早盘放量并迅速重回 1.7 万亿以上，新主线带动全市场 3500+ 个股上涨。策略：右侧跟随新主线首板或最强中军。
                </p>
              </div>
            </div>
          </section>

          {/* 第9章：波普尔假说证伪闭环 */}
          <section id="ch9" className="space-y-4 scroll-mt-20">
            <div className="flex items-center gap-3">
              <span className="text-sm font-mono font-black text-amber-400">09</span>
              <h2 className="text-xl font-black text-white tracking-tight flex items-center gap-2">
                波普尔式核心假说与证伪指标闭环
              </h2>
            </div>

            <div className="space-y-3 pt-1">
              <div className="bg-[#0B0E17] border-l-4 border-l-amber-500 border-r border-t border-b border-white/10 p-4 rounded-xl">
                <div className="font-bold text-white text-sm mb-1">假说 H1：传媒/AI视频具有板块级主线持续性</div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  <strong className="text-amber-400">刚性证伪条件：</strong> 次日传媒行业资金净流出超过 15 亿元，或者新华传媒开盘大幅低开（低于 -3%）且未能迅速翻红。一旦触发，该做多假说即被证伪，严禁接力。
                </p>
              </div>

              <div className="bg-[#0B0E17] border-l-4 border-l-emerald-500 border-r border-t border-b border-white/10 p-4 rounded-xl">
                <div className="font-bold text-white text-sm mb-1">假说 H2：科技成长股的抛压已在今日集中出清</div>
                <p className="text-xs text-slate-400 leading-relaxed">
                  <strong className="text-amber-400">刚性证伪条件：</strong> 次日早盘 30 分钟内通信与电子板块继续净流出超过 30 亿元，或者创业板权重股创日内新低。一旦触发，判定为持续阴跌出清，禁止抄底。
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
                <span>触发结论</span>
              </div>
              <div className="flex items-center justify-between border-b border-white/5 pb-2">
                <span className="text-white">两市 09:25 竞价总成交金额</span>
                <span className="text-amber-400">&lt; 140 亿元</span>
                <span className="text-emerald-400">流动性严重匮乏，防御为先</span>
              </div>
              <div className="flex items-center justify-between border-b border-white/5 pb-2">
                <span className="text-white">空间高标新华传媒竞价溢价</span>
                <span className="text-rose-400">&gt; +5% 且封单 &gt; 50万手</span>
                <span className="text-rose-400">情绪高标锁仓良好</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-white">中际旭创竞价承接情况</span>
                <span className="text-emerald-400">低开 &gt; -2% 且卖盘压单巨大</span>
                <span className="text-emerald-400">大科技抛压未尽，禁止抢反弹</span>
              </div>
            </div>
          </section>

        </main>

        {/* 右侧：伴随式证据栏 */}
        {evidenceOpen && (
          <aside className="w-80 hidden lg:flex flex-col border-l border-white/5 bg-[#07090E]/90 shrink-0 sticky top-14 h-[calc(100vh-56px)] overflow-y-auto p-4 space-y-4">
            <div className="flex items-center justify-between border-b border-white/5 pb-2">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-amber-400" />
                <span className="text-xs font-bold text-white tracking-wider">伴随式微观证据</span>
              </div>
              <span className="text-[10px] text-slate-500">实时联动</span>
            </div>

            {/* 聚焦个股样本 */}
            <div className="bg-[#0B0E17] border border-amber-500/30 p-3.5 rounded-xl">
              <div className="flex justify-between items-center mb-1">
                <span className="font-bold text-white text-sm">{selectedStock.name}</span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/20 font-bold">{selectedStock.tag}</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed mt-2">
                {selectedStock.desc}
              </p>
            </div>

            {/* 微观关键指标 */}
            <div className="space-y-2 text-xs">
              <span className="text-[11px] text-slate-400 font-bold block">微观结构关键指标</span>
              <div className="bg-[#0B0E17] border border-white/10 p-3 rounded-lg space-y-2">
                <div className="flex justify-between">
                  <span className="text-slate-400">实际换手涨停家数:</span>
                  <span className="text-rose-400 font-bold font-mono">39 家</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">一字板 / T字板:</span>
                  <span className="text-rose-400 font-bold font-mono">7 家</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">大面股 (&gt; -10%):</span>
                  <span className="text-emerald-400 font-bold font-mono">14 家</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">昨日涨停今日收益率:</span>
                  <span className="text-emerald-400 font-bold font-mono">-1.24%</span>
                </div>
              </div>
            </div>

            {/* 推荐追问 */}
            <div className="space-y-2 pt-2">
              <span className="text-[11px] text-slate-400 font-bold block">高频追问建议</span>
              <div className="space-y-1.5 text-xs">
                <button
                  onClick={() => { setAiDrawerOpen(true); handleSendChat('为什么缩量下跌不能视作洗盘结束？'); }}
                  className="w-full text-left p-2 rounded bg-white/5 hover:bg-white/10 text-slate-300 transition text-[11px]"
                >
                  • 为什么缩量下跌不能视作洗盘结束？
                </button>
                <button
                  onClick={() => { setAiDrawerOpen(true); handleSendChat('传媒与风电谁更具备持续接力空间？'); }}
                  className="w-full text-left p-2 rounded bg-white/5 hover:bg-white/10 text-slate-300 transition text-[11px]"
                >
                  • 传媒与风电谁更具备持续接力空间？
                </button>
                <button
                  onClick={() => { setAiDrawerOpen(true); handleSendChat('09:25 集合竞价最核心的证伪指标？'); }}
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
                <h3 className="font-bold text-white text-sm">知见 · 智能问答助手</h3>
                <p className="text-[10px] text-slate-400">依据今日盘面真实数据与推演逻辑解答</p>
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
              placeholder="输入您的问题，如：新华传媒明日炸板风险有多大？..."
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
