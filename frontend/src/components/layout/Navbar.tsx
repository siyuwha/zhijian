"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { Home, FileText, Newspaper, Clock, MonitorPlay, TrendingUp, Compass, PlaySquare, Settings } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { name: "总览", href: "/", icon: Home },
  { name: "复盘", href: "/review", icon: FileText },
  { name: "简报", href: "/briefing", icon: Newspaper },
  { name: "竞价", href: "/auction", icon: Clock },
  { name: "盯盘", href: "/monitor", icon: MonitorPlay },
  { name: "交易", href: "/trading", icon: TrendingUp },
  { name: "策略", href: "/strategy", icon: Compass },
  { name: "模拟", href: "/simulation", icon: PlaySquare },
  { name: "设置", href: "/settings", icon: Settings },
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
      {/* Desktop Navigation */}
      <nav className="hidden md:flex flex-col w-64 bg-slate-900 border-r border-slate-800 text-white min-h-screen">
        <div className="p-6">
          <h1 className="text-xl font-bold tracking-wider text-teal-400">AI认知复盘交易</h1>
        </div>
        <div className="flex-1 px-4 space-y-2">
          {navItems.map((item) => {
            const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-4 py-3 rounded-lg transition-colors",
                  isActive
                    ? "bg-teal-500/10 text-teal-400"
                    : "text-slate-400 hover:bg-slate-800 hover:text-white"
                )}
              >
                <Icon className="w-5 h-5" />
                <span>{item.name}</span>
              </Link>
            );
          })}
        </div>
        {/* Version Badge */}
        <div className="p-4 border-t border-slate-800/80 text-xs text-slate-500 flex flex-col gap-1">
          <div className="flex items-center justify-between">
            <span className="font-medium text-slate-400">Cognition MVP</span>
            <span className="px-1.5 py-0.5 rounded bg-teal-950 text-teal-400 border border-teal-800/50 font-mono text-[10px]">
              v0.1.0
            </span>
          </div>
          <span className="text-[10px] text-slate-600 font-mono">2026.09.28 首战版</span>
        </div>
      </nav>

      {/* Mobile Bottom Navigation (Horizontal Scrollable) */}
      <nav
        aria-label="移动端底部导航"
        className="md:hidden fixed bottom-0 left-0 right-0 bg-slate-900/95 backdrop-blur-md border-t border-slate-800 text-white z-50 pb-[env(safe-area-inset-bottom,0px)]"
      >
        <div className="flex items-center gap-1.5 px-3 py-2 overflow-x-auto no-scrollbar scroll-smooth">
          {navItems.map((item) => {
            const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                ref={isActive ? activeItemRef : null}
                className={cn(
                  "flex flex-col items-center justify-center min-w-[4.25rem] px-2 py-1.5 rounded-lg transition-colors flex-shrink-0 select-none",
                  isActive
                    ? "bg-teal-500/15 text-teal-400 font-medium border border-teal-500/30"
                    : "text-slate-400 hover:text-slate-200 active:bg-slate-800/80 border border-transparent"
                )}
              >
                <Icon className={cn("w-5 h-5 mb-1 flex-shrink-0", isActive ? "text-teal-400" : "text-slate-400")} />
                <span className="text-[11px] whitespace-nowrap leading-none tracking-tight">{item.name}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}

