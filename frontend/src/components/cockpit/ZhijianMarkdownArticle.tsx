'use client';

import React from 'react';
import { ShieldCheck, AlertCircle, Compass, Zap, Flame, Scale, TrendingUp, TrendingDown, Target, HelpCircle, CheckCircle2, ChevronRight } from 'lucide-react';

interface ZhijianMarkdownArticleProps {
  markdownContent: string;
  onStockClick?: (stockName: string) => void;
  selectedStockName?: string;
}

interface ParsedChapter {
  id: string;
  num: string;
  title: string;
  category: string;
  rawContent: string;
}

const KNOWN_STOCKS = [
  '慈文传媒', '新经典', '龙版传媒', '丽人丽妆', '百洋股份',
  '东百集团', '农心科技', '醋化股份', '广电网络', '海欣股份',
  '远程股份', '超声电子', '福建水泥', '内蒙新华', '金奥博',
  '亚邦股份', '荣丰控股', '皇台酒业', '理工能科', '海得控制'
];

export function ZhijianMarkdownArticle({
  markdownContent,
  onStockClick,
  selectedStockName
}: ZhijianMarkdownArticleProps) {
  if (!markdownContent || markdownContent.trim().length === 0) {
    return (
      <div className="p-8 text-center bg-[#0B0E17] border border-white/10 rounded-2xl text-slate-400">
        <p>暂无 Markdown 深度研报全文数据</p>
      </div>
    );
  }

  // 1. 分割章节
  const chapters: ParsedChapter[] = [];
  const rawSections = markdownContent.split(/(?=^## 第 \d+ 章)/m);

  const CATEGORY_MAP: Record<string, string> = {
    '0': '假说审计与归因',
    '1': '宏观流动性与量能',
    '2': '市场宽度与短线生态',
    '3': '板块攻防与资金归因',
    '4': '资金流向与真伪辨析',
    '5': '微观机制极值样本',
    '6': '情绪周期五阶段状态机',
    '7': '机构与游资博弈心理',
    '8': '次日推演与交易计划',
    '9': '波普尔刚性证伪闭环',
    '10': '复盘结论与开盘探针'
  };

  for (const sec of rawSections) {
    const match = sec.match(/^## 第 (\d+) 章[：: ]*(.*)/m);
    if (match) {
      const num = match[1];
      const title = match[2].trim();
      const content = sec.replace(/^## 第 \d+ 章[：: ]*.*\n?/, '').trim();
      chapters.push({
        id: `ch${num}`,
        num: num.padStart(2, '0'),
        title,
        category: CATEGORY_MAP[num] || '深度认知研报',
        rawContent: content
      });
    }
  }

  // 辅助渲染内联文本：高亮标签、数字红绿、股票可点击
  const renderInlineFormattedText = (text: string) => {
    // 替换特殊标签
    const parts = text.split(/(\*\*【[^】]+】\*\*|\*\*[^*]+\*\*|“[^”]+”)/g);

    return parts.map((part, pIdx) => {
      if (!part) return null;

      // 1. 特殊标记 【物理事实】 / 【交易推断】 / 【认知校准】 / 【证伪红线】 / 【数据边界】
      if (part.startsWith('**【') && part.endsWith('】**')) {
        const tag = part.slice(3, -3);
        if (tag.includes('物理事实')) {
          return (
            <span key={pIdx} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800/80 font-bold text-xs mr-1 align-baseline shadow-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
              {tag}
            </span>
          );
        }
        if (tag.includes('交易推断')) {
          return (
            <span key={pIdx} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-800/80 font-bold text-xs mr-1 align-baseline shadow-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
              {tag}
            </span>
          );
        }
        if (tag.includes('认知校准')) {
          return (
            <span key={pIdx} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-800/80 font-bold text-xs mr-1 align-baseline shadow-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              {tag}
            </span>
          );
        }
        if (tag.includes('证伪') || tag.includes('红线')) {
          return (
            <span key={pIdx} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-950/80 text-rose-300 border border-rose-800/80 font-bold text-xs mr-1 align-baseline shadow-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
              {tag}
            </span>
          );
        }
        if (tag.includes('数据边界')) {
          return (
            <span key={pIdx} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-800/80 font-bold text-xs mr-1 align-baseline shadow-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-purple-400" />
              {tag}
            </span>
          );
        }
        return (
          <span key={pIdx} className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-white/10 text-slate-200 border border-white/10 font-bold text-xs mr-1 align-baseline">
            {tag}
          </span>
        );
      }

      // 2. 加粗文本 **...**
      if (part.startsWith('**') && part.endsWith('**')) {
        const rawBold = part.slice(2, -2);
        // 检查加粗内容中是否有股票名字
        return (
          <strong key={pIdx} className="font-bold text-white tracking-wide">
            {renderStockChipsInString(rawBold)}
          </strong>
        );
      }

      // 3. 引言 “...”
      if (part.startsWith('“') && part.endsWith('”')) {
        return (
          <span key={pIdx} className="text-amber-200/90 font-medium italic">
            {part}
          </span>
        );
      }

      // 4. 普通文本：检测股票名字与红绿涨跌数字
      return <span key={pIdx}>{renderStockChipsInString(part)}</span>;
    });
  };

  // 检测字符串中的个股并替换为可点击的标的徽章
  const renderStockChipsInString = (str: string) => {
    // 正则拆分已知个股
    const regex = new RegExp(`(${KNOWN_STOCKS.join('|')})`, 'g');
    const tokens = str.split(regex);

    return tokens.map((token, tIdx) => {
      if (KNOWN_STOCKS.includes(token)) {
        const isSelected = selectedStockName?.includes(token);
        return (
          <button
            key={tIdx}
            type="button"
            onClick={() => onStockClick && onStockClick(token)}
            className={`inline-flex items-center px-1.5 py-0.5 mx-0.5 rounded text-xs font-mono font-bold transition cursor-pointer ${
              isSelected
                ? 'bg-amber-500 text-black shadow-md ring-2 ring-amber-300'
                : 'bg-amber-950/40 text-amber-300 hover:bg-amber-900/60 hover:text-amber-100 border border-amber-800/40'
            }`}
            title={`点击在伴随证据栏联动查看 ${token}`}
          >
            <span>{token}</span>
          </button>
        );
      }

      // 处理 A 股红涨绿跌百分比数字
      const subTokens = token.split(/([+-]?\d+(?:\.\d+)?%|[+-]\d+(?:\.\d+)?)/g);
      return subTokens.map((sub, sIdx) => {
        if (/^\+\d+(?:\.\d+)?%?$/.test(sub)) {
          return (
            <span key={sIdx} className="text-rose-400 font-mono font-bold">
              {sub}
            </span>
          );
        }
        if (/^-\d+(?:\.\d+)?%?$/.test(sub)) {
          return (
            <span key={sIdx} className="text-emerald-400 font-mono font-bold">
              {sub}
            </span>
          );
        }
        return sub;
      });
    });
  };

  // 渲染 Markdown 表格
  const renderTable = (tableLines: string[], tableKey: number) => {
    if (tableLines.length < 2) return null;

    const parseRow = (line: string) =>
      line
        .trim()
        .replace(/^\|/, '')
        .replace(/\|$/, '')
        .split('|')
        .map(cell => cell.trim());

    const headers = parseRow(tableLines[0]);
    // tableLines[1] 通常是 |--|--| 分隔符
    const rows = tableLines.slice(2).map(parseRow);

    return (
      <div key={tableKey} className="my-4 rounded-xl border border-white/10 bg-black/40 overflow-hidden shadow-2xl">
        <div className="overflow-x-auto no-scrollbar">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-white/[0.04] border-b border-white/10 text-slate-300 font-bold uppercase tracking-wider">
                {headers.map((h, i) => (
                  <th key={i} className="py-3 px-4 font-mono whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {rows.map((row, rIdx) => (
                <tr
                  key={rIdx}
                  className="hover:bg-white/[0.03] transition-colors group"
                >
                  {row.map((cell, cIdx) => {
                    // 判断单元格内容类型
                    const isVerdict =
                      cell.includes('客观校准') ||
                      cell.includes('未证伪') ||
                      cell.includes('待验证') ||
                      cell.includes('假说成立');
                    const isFalsified = cell.includes('证伪') && !cell.includes('未证伪');

                    return (
                      <td key={cIdx} className="py-2.5 px-4 font-mono text-slate-300 group-hover:text-white transition-colors">
                        {isVerdict ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded bg-amber-950/70 text-amber-300 border border-amber-700/60 text-[11px] font-bold shadow-sm">
                            {cell.replace(/\*\*/g, '')}
                          </span>
                        ) : isFalsified ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded bg-rose-950/70 text-rose-300 border border-rose-700/60 text-[11px] font-bold shadow-sm">
                            {cell.replace(/\*\*/g, '')}
                          </span>
                        ) : (
                          renderInlineFormattedText(cell)
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  // 解析章节内容流（处理表格、H3、引言、列表、段落）
  const renderChapterContent = (rawContent: string) => {
    const lines = rawContent.split('\n');
    const elements: React.ReactNode[] = [];

    let inTable = false;
    let tableBuffer: string[] = [];
    let tableCounter = 0;

    const flushTable = () => {
      if (tableBuffer.length > 0) {
        elements.push(renderTable(tableBuffer, tableCounter++));
        tableBuffer = [];
      }
      inTable = false;
    };

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const trimmed = line.trim();

      // 判断是否是表格行
      if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
        inTable = true;
        tableBuffer.push(trimmed);
        continue;
      } else {
        if (inTable) {
          flushTable();
        }
      }

      if (!trimmed) {
        continue;
      }

      // H3 子标题
      if (trimmed.startsWith('### ')) {
        const h3Title = trimmed.replace(/^###\s*/, '');
        elements.push(
          <div key={`h3-${i}`} className="pt-4 pb-1 border-b border-white/5 flex items-center gap-2">
            <span className="w-1.5 h-3.5 rounded-full bg-amber-400" />
            <h3 className="text-sm md:text-base font-bold text-white tracking-wide">
              {h3Title}
            </h3>
          </div>
        );
        continue;
      }

      // 杂志级引用块 / 强调块
      if (trimmed.startsWith('“') || trimmed.startsWith('>')) {
        const quoteText = trimmed.replace(/^>\s*/, '');
        elements.push(
          <div
            key={`quote-${i}`}
            className="my-3 p-4 rounded-xl border-l-4 border-l-amber-500 bg-amber-950/15 italic text-sm text-slate-200 leading-relaxed shadow-md"
          >
            {renderInlineFormattedText(quoteText)}
          </div>
        );
        continue;
      }

      // 列表项
      if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        const itemText = trimmed.replace(/^[-*]\s+/, '');
        elements.push(
          <div key={`li-${i}`} className="flex items-start gap-2.5 text-xs text-slate-300 leading-relaxed pl-1 py-0.5">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400/80 mt-1.5 shrink-0" />
            <div className="flex-1">{renderInlineFormattedText(itemText)}</div>
          </div>
        );
        continue;
      }

      // 数字编号项 (如 1. 2.)
      const numMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
      if (numMatch) {
        const numStr = numMatch[1];
        const itemText = numMatch[2];
        elements.push(
          <div key={`num-${i}`} className="flex items-start gap-2.5 text-xs text-slate-300 leading-relaxed pl-1 py-1">
            <span className="w-4 h-4 rounded-full bg-white/10 text-slate-300 font-mono text-[10px] font-bold flex items-center justify-center shrink-0 mt-0.5">
              {numStr}
            </span>
            <div className="flex-1">{renderInlineFormattedText(itemText)}</div>
          </div>
        );
        continue;
      }

      // 普通段落
      elements.push(
        <p key={`p-${i}`} className="text-xs md:text-sm text-slate-300 leading-relaxed py-1">
          {renderInlineFormattedText(trimmed)}
        </p>
      );
    }

    if (inTable) {
      flushTable();
    }

    return elements;
  };

  return (
    <div className="space-y-10">
      {chapters.map((chapter) => (
        <section
          key={chapter.id}
          id={chapter.id}
          className="scroll-mt-24 bg-[#0B0E17]/90 border border-white/10 rounded-2xl p-6 lg:p-8 space-y-4 shadow-xl hover:border-white/15 transition-colors"
        >
          {/* 章节机构眉标 */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-white/5 pb-4">
            <div className="flex items-center gap-3">
              <span className="font-mono font-black text-lg md:text-xl text-amber-400 bg-amber-950/40 px-2.5 py-0.5 rounded-lg border border-amber-800/40">
                {chapter.num}
              </span>
              <div>
                <span className="text-[10px] font-mono font-semibold tracking-widest text-slate-500 uppercase block">
                  {chapter.category}
                </span>
                <h2 className="text-base md:text-lg font-black text-white tracking-tight flex items-center gap-2">
                  {chapter.title}
                </h2>
              </div>
            </div>

            <div className="flex items-center gap-2 self-start sm:self-center">
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white/5 text-slate-400 border border-white/5">
                波普尔闭环
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 font-bold">
                深度研报
              </span>
            </div>
          </div>

          {/* 章节正文流 */}
          <div className="space-y-3 pt-1">
            {renderChapterContent(chapter.rawContent)}
          </div>
        </section>
      ))}
    </div>
  );
}
