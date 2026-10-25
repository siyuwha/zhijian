"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { SegmentedControl, type SegmentedItem } from "./SegmentedControl";

export interface NavItemDef {
  key: string;
  label: string;
  href?: string;
  badge?: string | number;
}

export interface FloatingPillNavProps extends React.HTMLAttributes<HTMLElement> {
  /** @deprecated 左侧系统名称（细分页面已统一取消展示，由左侧栏全局呈现） */
  brandName?: string;
  /** @deprecated 品牌角标 */
  brandBadge?: string;
  /** @deprecated 副标题 */
  subtitle?: string;
  /** @deprecated 品牌 Logo 内容 */
  logoContent?: React.ReactNode;
  /** 左侧自定义插槽（如细分页面面包屑或图标） */
  leftSlot?: React.ReactNode;
  /** 导航选项列表 */
  navItems?: NavItemDef[];
  /** 当前选中的导航项 key */
  activeNav?: string;
  /** 导航切换回调 */
  onNavChange?: (key: string) => void;
  /** 右侧委托安全状态文本，默认“仅分析 · 未接入委托” */
  safetyStatusText?: string;
  /** 显式传递日期文本，如“2026.10.08”，未传递时不渲染占位 */
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
  brandName,
  brandBadge,
  subtitle,
  logoContent,
  leftSlot,
  navItems = DEFAULT_NAV_ITEMS,
  activeNav = "overview",
  onNavChange,
  safetyStatusText = "仅分析 · 未接入委托",
  dateText,
  userBadge = "SY",
  rightSlot,
  ...props
}: FloatingPillNavProps) {
  const router = useRouter();
  const [internalActive, setInternalActive] = React.useState<string>(activeNav);

  const currentActive = onNavChange ? activeNav : internalActive;

  const currentActiveItem = React.useMemo(() => {
    return navItems.find((item) => item.key === currentActive) || navItems[0];
  }, [navItems, currentActive]);

  const handleSelect = (key: string) => {
    if (onNavChange) {
      onNavChange(key);
      return;
    }

    setInternalActive(key);

    // 内置路由与平滑锚点跳转逻辑
    if (key === "overview") {
      if (typeof window !== "undefined" && window.location.pathname === "/") {
        window.scrollTo({ top: 0, behavior: "smooth" });
      } else {
        router.push("/");
      }
    } else if (key === "review") {
      if (typeof window !== "undefined" && window.location.pathname === "/cockpit") {
        window.scrollTo({ top: 0, behavior: "smooth" });
      } else {
        router.push("/cockpit");
      }
    } else if (key === "battleground") {
      const el = typeof document !== "undefined" ? document.getElementById("bento-battleground") : null;
      if (el) {
        el.scrollIntoView({ behavior: "smooth" });
      } else {
        router.push("/cockpit#bento-battleground");
      }
    } else if (key === "ladder") {
      const el = typeof document !== "undefined" ? document.getElementById("bento-ladder") : null;
      if (el) {
        el.scrollIntoView({ behavior: "smooth" });
      } else {
        router.push("/cockpit#bento-ladder");
      }
    } else if (key === "audit") {
      const el = typeof document !== "undefined" ? document.getElementById("bento-audit") : null;
      if (el) {
        el.scrollIntoView({ behavior: "smooth" });
      } else {
        router.push("/cockpit#bento-audit");
      }
    } else {
      router.push(`/${key}`);
    }
  };

  const segmentedItems: SegmentedItem<string>[] = React.useMemo(() => {
    return navItems.map((item) => ({
      value: item.key,
      label: item.label,
      badge: item.badge ? (
        <span className="text-xs font-mono px-1.5 py-0.5 rounded-full bg-purple-500/30 text-purple-200">
          {item.badge}
        </span>
      ) : undefined,
    }));
  }, [navItems]);

  return (
    <header
      className={cn(
        "glass-pill max-w-7xl mx-auto w-full rounded-full px-3 sm:px-4 md:px-5 py-2 flex items-center justify-between z-30 sticky top-4 shadow-2xl transition select-none",
        className
      )}
      {...props}
    >
      {/* 左侧导航区：取消细分页面重复的系统名称，直接展示等宽分段导航控制器（或自定义 leftSlot） */}
      <div className="flex items-center gap-2 sm:gap-3 shrink-0">
        {leftSlot}

        {/* 移动端/窄屏：优雅展示当前页面定位标签 */}
        <div className="flex lg:hidden items-center gap-1.5 px-3 py-1 rounded-full bg-white/5 border border-white/10 text-xs font-semibold text-white">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
          <span>{currentActiveItem?.label}</span>
        </div>

        {/* 桌面端：标准等宽 5 键分段导航控制器 */}
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
      </div>

      {/* 右侧：交易安全绿灯药丸、日期指示器、操作插槽、用户头像 */}
      <div className="flex items-center justify-end gap-1.5 sm:gap-2 shrink-0 ml-auto">
        {safetyStatusText && (
          <div
            className="h-8 flex items-center gap-1.5 px-2.5 xl:px-3 rounded-full bg-emerald-950/50 border border-emerald-500/30 text-emerald-300 text-sm shadow-sm shrink-0"
            title="纯客观研究，无实盘委托风险"
          >
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" />
            </span>
            <span className="hidden xl:inline font-medium whitespace-nowrap">
              {safetyStatusText}
            </span>
          </div>
        )}

        {/* 仅当显式传入 dateText 时才渲染日期药丸，杜绝与日期选择器重复 */}
        {dateText && (
          <div className="h-8 flex items-center px-2.5 rounded-full bg-white/5 border border-white/10 text-xs font-mono text-slate-300 shadow-inner whitespace-nowrap shrink-0">
            {dateText}
          </div>
        )}

        {rightSlot}

        {userBadge && (
          <div className="w-8 h-8 rounded-full bg-purple-600/30 border border-purple-400/40 text-purple-200 flex items-center justify-center text-xs font-bold font-mono shadow-sm cursor-pointer hover:bg-purple-600/40 transition shrink-0">
            {userBadge}
          </div>
        )}
      </div>
    </header>
  );
}
