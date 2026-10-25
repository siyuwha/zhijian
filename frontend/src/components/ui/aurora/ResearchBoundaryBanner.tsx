"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface ResearchBoundaryBannerProps
  extends React.HTMLAttributes<HTMLDivElement> {
  /** 横幅前缀标题，默认“研究边界法则：” */
  title?: string;
  /** 核心边界陈述文本 */
  statement?: string;
  /** 右侧审计标牌文字，默认“ZERO_POLLUTION” */
  badgeText?: string;
  /** 是否支持用户手动关闭/折叠 */
  closable?: boolean;
  /** 关闭时的回调 */
  onClose?: () => void;
}

export function ResearchBoundaryBanner({
  className,
  title = "研究边界法则：",
  statement = "本工作台只呈现纯客观事实与归因结论，严禁作为实盘追高买卖建议；所有指标可随时回溯至不可变审计凭证。",
  badgeText = "ZERO_POLLUTION",
  closable = false,
  onClose,
  ...props
}: ResearchBoundaryBannerProps) {
  const [visible, setVisible] = React.useState(true);

  if (!visible) return null;

  const handleClose = () => {
    setVisible(false);
    onClose?.();
  };

  return (
    <div
      role="alert"
      className={cn(
        "max-w-7xl mx-auto w-full bg-amber-950/25 border border-amber-500/30 rounded-2xl p-3 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2.5 text-sm text-amber-200 backdrop-blur-md transition-all shadow-sm",
        className
      )}
      {...props}
    >
      <div className="flex items-center gap-2.5 min-w-0">
        <span
          className="w-1.5 h-5 md:h-6 rounded-full bg-amber-400 shrink-0 shadow-sm"
          aria-hidden="true"
        />
        <div className="leading-relaxed">
          <span className="font-bold text-amber-300 mr-1 shrink-0">{title}</span>
          <span className="text-amber-200/90">{statement}</span>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto ml-auto">
        {badgeText && (
          <span className="text-xs font-mono tracking-wider bg-amber-900/40 px-2.5 py-0.5 rounded-full border border-amber-600/40 text-amber-300 select-none shadow-sm">
            {badgeText}
          </span>
        )}
        {closable && (
          <button
            type="button"
            onClick={handleClose}
            className="text-amber-400/70 hover:text-amber-200 p-0.5 rounded-md hover:bg-amber-900/30 transition-colors"
            aria-label="关闭横幅"
          >
            <svg
              className="w-3.5 h-3.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        )}
      </div>
    </div>
  );
}
