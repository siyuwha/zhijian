import * as React from "react";
import { cn } from "@/lib/utils";

export type StatusBadgeVariant =
  | "bullish"   // 做多 / 涨停 / 强势多头 (荧光红/玫瑰红)
  | "bearish"   // 做空 / 跌停 / 弱势空头 (翡翠绿)
  | "warning"   // 警示 / 分歧 / 炸板风险 (琥珀金)
  | "spatial"   // 空间标杆 / 连板高标 / AI决策 (紫罗兰霓虹)
  | "neutral";  // 中性 / 观察 / 定义期望 (电光青)

export type StatusBadgeSize = "xs" | "sm" | "md";

export interface StatusBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** 状态多态变体 */
  variant?: StatusBadgeVariant;
  /** 药丸尺寸，默认 sm */
  size?: StatusBadgeSize;
  /** 是否展示左侧呼吸灯脉冲圆点 */
  pulse?: boolean;
  /** 是否开启极光微发光光晕 */
  glow?: boolean;
  /** 自定义圆点图标或 ReactNode */
  icon?: React.ReactNode;
}

const VARIANT_CONFIGS: Record<
  StatusBadgeVariant,
  {
    pill: string;
    dot: string;
    glowClass: string;
  }
> = {
  bullish: {
    pill: "bg-rose-950/50 text-rose-300 border-rose-500/30",
    dot: "bg-rose-400",
    glowClass: "glow-rose",
  },
  bearish: {
    pill: "bg-emerald-950/50 text-emerald-300 border-emerald-500/30",
    dot: "bg-emerald-400",
    glowClass: "glow-emerald",
  },
  warning: {
    pill: "bg-amber-950/50 text-amber-300 border-amber-500/30",
    dot: "bg-amber-400",
    glowClass: "glow-amber",
  },
  spatial: {
    pill: "bg-purple-950/60 text-purple-300 border-purple-500/40",
    dot: "bg-purple-400",
    glowClass: "glow-purple",
  },
  neutral: {
    pill: "bg-cyan-950/50 text-cyan-300 border-cyan-500/30",
    dot: "bg-cyan-400",
    glowClass: "glow-cyan",
  },
};

const SIZE_CONFIGS: Record<
  StatusBadgeSize,
  {
    pill: string;
    dot: string;
    text: string;
  }
> = {
  xs: {
    pill: "px-2 py-0.5 gap-1",
    dot: "w-1.5 h-1.5",
    text: "text-[10px] leading-tight font-mono",
  },
  sm: {
    pill: "px-2.5 py-1 gap-1.5",
    dot: "w-2 h-2",
    text: "text-xs font-mono font-medium",
  },
  md: {
    pill: "px-3 py-1.5 gap-2",
    dot: "w-2.5 h-2.5",
    text: "text-xs font-semibold",
  },
};

export const StatusBadge = React.forwardRef<HTMLSpanElement, StatusBadgeProps>(
  (
    {
      className,
      variant = "neutral",
      size = "sm",
      pulse = false,
      glow = false,
      icon,
      children,
      ...props
    },
    ref
  ) => {
    const variantStyle = VARIANT_CONFIGS[variant];
    const sizeStyle = SIZE_CONFIGS[size];

    return (
      <span
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center rounded-full border backdrop-blur-md transition-all select-none",
          variantStyle.pill,
          sizeStyle.pill,
          sizeStyle.text,
          glow && variantStyle.glowClass,
          className
        )}
        {...props}
      >
        {pulse && (
          <span className="relative flex shrink-0 items-center justify-center">
            <span
              className={cn(
                "animate-ping absolute inline-flex h-full w-full rounded-full opacity-75",
                variantStyle.dot
              )}
            />
            <span
              className={cn(
                "relative inline-flex rounded-full",
                sizeStyle.dot,
                variantStyle.dot
              )}
            />
          </span>
        )}
        {icon && !pulse && <span className="inline-flex shrink-0">{icon}</span>}
        <span>{children}</span>
      </span>
    );
  }
);

StatusBadge.displayName = "StatusBadge";
