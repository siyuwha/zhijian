"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { SegmentedControl, type SegmentedItem } from "./SegmentedControl";

export interface NavItemDef {
  key: string;
  label: string;
  href?: string;
  badge?: string | number;
}

export interface FloatingPillNavProps extends React.HTMLAttributes<HTMLElement> {
  /** 品牌名称，默认“知见 · 交易认知” */
  brandName?: string;
  /** 品牌角标，默认“BENTO iOS 18” */
  brandBadge?: string;
  /** 副标题或系统环境说明，默认“A股个人量化复盘 · 极光暗夜版” */
  subtitle?: string;
  /** 品牌首字/Logo 图标内容，默认“知” */
  logoContent?: React.ReactNode;
  /** 导航选项列表 */
  navItems?: NavItemDef[];
  /** 当前选中的导航项 key */
  activeNav?: string;
  /** 导航切换回调 */
  onNavChange?: (key: string) => void;
  /** 右侧委托安全状态文本，默认“仅分析 · 未接入委托” */
  safetyStatusText?: string;
  /** 显式传递日期文本，如“2026.10.08” */
  dateText?: string;
  /** 用户头像文字或自定义节点，默认“SY” */
  userBadge?: React.ReactNode;
  /** 自定义右侧额外操作区插槽 */
  rightSlot?: React.ReactNode;
}

const DEFAULT_NAV_ITEMS: NavItemDef[] = [
  { key: "overview", label: "认知总览" },
  { key: "review", label: "交易复盘" },
  { key: "battleground", label: "题材战场" },
  { key: "ladder", label: "空间天梯" },
  { key: "audit", label: "审计留痕" },
];

export function FloatingPillNav({
  className,
  brandName = "知见 · 交易认知",
  brandBadge = "BENTO iOS 18",
  subtitle = "A股个人量化复盘 · 极光暗夜版",
  logoContent = "知",
  navItems = DEFAULT_NAV_ITEMS,
  activeNav = "overview",
  onNavChange,
  safetyStatusText = "仅分析 · 未接入委托",
  dateText,
  userBadge = "SY",
  rightSlot,
  ...props
}: FloatingPillNavProps) {
  const [internalActive, setInternalActive] = React.useState<string>(activeNav);

  const currentActive = onNavChange ? activeNav : internalActive;

  const handleSelect = (key: string) => {
    if (onNavChange) {
      onNavChange(key);
    } else {
      setInternalActive(key);
    }
  };

  const segmentedItems: SegmentedItem<string>[] = React.useMemo(() => {
    return navItems.map((item) => ({
      value: item.key,
      label: item.label,
      badge: item.badge ? (
        <span className="text-[10px] font-mono px-1.5 py-0.2 rounded-full bg-purple-500/30 text-purple-200">
          {item.badge}
        </span>
      ) : undefined,
    }));
  }, [navItems]);

  const displayDate = React.useMemo(() => {
    if (dateText) return dateText;
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, "0");
    const d = String(now.getDate()).padStart(2, "0");
    return `${y}.${m}.${d}`;
  }, [dateText]);

  return (
    <header
      className={cn(
        "glass-pill max-w-7xl mx-auto w-full rounded-full px-4 md:px-6 py-2.5 flex items-center justify-between z-30 sticky top-4 shadow-2xl transition select-none",
        className
      )}
      {...props}
    >
      {/* 左侧：品牌与系统环境说明 */}
      <div className="flex items-center gap-3 shrink-0">
        <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-purple-600 via-indigo-500 to-cyan-400 flex items-center justify-center font-black text-white text-sm shadow-md ring-1 ring-white/20 shrink-0">
          {logoContent}
        </div>
        <div className="hidden sm:block">
          <div className="flex items-center gap-2">
            <span className="font-bold text-sm tracking-wide text-white">
              {brandName}
            </span>
            {brandBadge && (
              <span className="text-[10px] font-mono text-purple-300 bg-purple-950/60 border border-purple-800/80 px-2 py-0.5 rounded-full">
                {brandBadge}
              </span>
            )}
          </div>
          {subtitle && (
            <div className="text-[10px] text-slate-400 leading-tight">
              {subtitle}
            </div>
          )}
        </div>
      </div>

      {/* 中部：iOS 灵动分段控制器导航 */}
      {navItems.length > 0 && (
        <nav className="hidden lg:flex items-center">
          <SegmentedControl
            items={segmentedItems}
            value={currentActive}
            onChange={handleSelect}
            size="md"
          />
        </nav>
      )}

      {/* 右侧：交易安全绿灯药丸、日期指示器、用户态 */}
      <div className="flex items-center gap-2 md:gap-2.5 shrink-0">
        {safetyStatusText && (
          <div
            className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-950/50 border border-emerald-500/30 text-emerald-300 text-xs shadow-sm"
            title="纯客观研究，无实盘委托风险"
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" />
            </span>
            <span className="hidden md:inline font-medium">
              {safetyStatusText}
            </span>
          </div>
        )}

        <div className="px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-xs font-mono text-slate-300 shadow-inner">
          {displayDate}
        </div>

        {rightSlot}

        {userBadge && (
          <div className="w-7 h-7 rounded-full bg-purple-600/30 border border-purple-400/40 text-purple-200 flex items-center justify-center text-xs font-bold font-mono shadow-sm cursor-pointer hover:bg-purple-600/40 transition">
            {userBadge}
          </div>
        )}
      </div>
    </header>
  );
}
