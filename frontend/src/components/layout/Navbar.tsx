"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import {
  Home,
  FileText,
  Newspaper,
  Clock,
  MonitorPlay,
  TrendingUp,
  Compass,
  PlaySquare,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { APP_VERSION, STAGE_NAME, GIT_COMMIT } from "@/config/version";

const navItems = [
  { name: "驾驶舱", href: "/cockpit", icon: Compass },
  { name: "简报", href: "/briefing", icon: Newspaper },
  { name: "竞价", href: "/auction", icon: Clock },
  { name: "盯盘", href: "/monitor", icon: MonitorPlay },
  { name: "复盘", href: "/review", icon: FileText },
  { name: "交易", href: "/trading", icon: TrendingUp, tag: "实盘" },
  { name: "策略", href: "/strategy", icon: Compass },
  { name: "模拟", href: "/simulation", icon: PlaySquare, tag: "沙盒" },
  { name: "系统状态", href: "/settings", icon: Settings },
];

export function Navbar() {
  const pathname = usePathname();
  const activeItemRef = useRef<HTMLAnchorElement | null>(null);

  useEffect(() => {
    if (activeItemRef.current) {
      activeItemRef.current.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
        inline: "center",
      });
    }
  }, [pathname]);

  return (
    <>
      {/* Desktop Navigation (物理固定方案，不随二级/三级内容滚动) */}
      <nav className="hidden md:flex flex-col w-64 bg-[#07090E]/95 backdrop-blur-2xl border-r border-white/10 text-white h-screen select-none shrink-0 z-40 sticky top-0 left-0">
        {/* 顶部品牌头：系统唯一统一橙色 Logo 徽标“知” + 标题 */}
        <div className="p-5 border-b border-white/5 flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-400 via-amber-500 to-amber-600 flex items-center justify-center font-black text-black text-base shadow-lg shadow-amber-500/25 ring-1 ring-amber-300/40 shrink-0">
            知
          </div>
          <div className="flex flex-col min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="font-bold text-sm tracking-wide text-white truncate">
                知见 · 交易认知
              </span>
            </div>
            <span className="text-[10px] text-amber-400/80 leading-tight truncate font-medium">
              A股个人量化复盘 · 极光暗夜版
            </span>
          </div>
        </div>

        {/* 菜单项 */}
        <div className="flex-1 px-3 py-4 space-y-1 overflow-y-auto no-scrollbar">
          {navItems.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href !== "/" && pathname.startsWith(item.href));
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "group flex items-center gap-3 px-3.5 py-2.5 rounded-xl transition-all duration-200 text-sm",
                  isActive
                    ? "bg-gradient-to-r from-amber-500/20 via-amber-600/10 to-transparent border-l-2 border-amber-400 text-white font-semibold shadow-sm"
                    : "text-slate-400 hover:bg-white/[0.04] hover:text-white border-l-2 border-transparent font-medium"
                )}
              >
                <Icon
                  className={cn(
                    "w-4 h-4 shrink-0 transition-colors",
                    isActive
                      ? "text-amber-400"
                      : "text-slate-400 group-hover:text-slate-200"
                  )}
                />
                <span className="truncate flex-1">{item.name}</span>
                {item.tag && (
                  <span
                    className={cn(
                      "text-[10px] px-1.5 py-0.5 rounded font-mono font-medium",
                      item.tag === "实盘"
                        ? "bg-purple-950/80 text-purple-300 border border-purple-800/60"
                        : "bg-cyan-950/80 text-cyan-300 border border-cyan-800/60"
                    )}
                  >
                    {item.tag}
                  </span>
                )}
              </Link>
            );
          })}
        </div>

        {/* 底部状态栏 */}
        <div className="p-4 border-t border-white/10 text-xs text-slate-400 flex flex-col gap-2 bg-black/20">
          {/* 安全药丸指示 */}
          <div
            className="flex items-center gap-2 px-2.5 py-1.5 rounded-full bg-emerald-950/40 border border-emerald-500/20 text-emerald-300 text-[11px]"
            title="纯客观分析，未接入实盘委托"
          >
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" />
            </span>
            <span className="truncate font-medium">仅分析 · 未接入委托</span>
          </div>

          {/* 版本与提交 */}
          <div className="flex items-center justify-between text-[11px] pt-1">
            <span className="font-medium text-slate-400">Cognition Radar</span>
            <span
              className="px-2 py-0.5 rounded-full bg-purple-950/60 text-purple-300 border border-purple-700/50 font-mono text-[10px]"
              title={`Git Commit: ${GIT_COMMIT}`}
            >
              {APP_VERSION}
            </span>
          </div>
          <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
            <span>{STAGE_NAME}</span>
            <span className="text-slate-500">#{GIT_COMMIT}</span>
          </div>
        </div>
      </nav>

      {/* Mobile Bottom Navigation (Horizontal Scrollable) */}
      <nav
        aria-label="移动端底部导航"
        className="md:hidden fixed bottom-0 left-0 right-0 bg-[#07090E]/90 backdrop-blur-2xl border-t border-white/10 text-white z-50 pb-[env(safe-area-inset-bottom,0px)]"
      >
        <div className="flex items-center gap-1.5 px-3 py-2 overflow-x-auto no-scrollbar scroll-smooth">
          {navItems.map((item) => {
            const isActive =
              pathname === item.href ||
              (item.href !== "/" && pathname.startsWith(item.href));
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                ref={isActive ? activeItemRef : null}
                className={cn(
                  "flex flex-col items-center justify-center min-w-[4.25rem] px-2 py-1.5 rounded-xl transition-all flex-shrink-0 select-none text-[11px]",
                  isActive
                    ? "bg-amber-500/20 text-white font-semibold border border-amber-500/30 shadow-sm"
                    : "text-slate-400 hover:text-slate-200 active:bg-white/[0.04] border border-transparent"
                )}
              >
                <Icon
                  className={cn(
                    "w-5 h-5 mb-1 flex-shrink-0 transition-colors",
                    isActive ? "text-amber-400" : "text-slate-400"
                  )}
                />
                <span className="whitespace-nowrap leading-none tracking-tight">
                  {item.name}
                </span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
