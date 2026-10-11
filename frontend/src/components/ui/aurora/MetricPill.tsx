import * as React from "react";
import { cn } from "@/lib/utils";

export type MetricTrend = "up" | "down" | "flat" | "neutral" | "auto";
export type MetricVariant = "default" | "subtle" | "bordered" | "tag";
export type MetricSize = "xs" | "sm" | "md" | "lg";

export interface MetricPillProps
  extends Omit<React.HTMLAttributes<HTMLDivElement>, "prefix"> {
  /** 指标名称或标签（如 '上证指数', '主力净买'） */
  label?: React.ReactNode;
  /** 主数值展示（如 '3,326.46', '+42.5 亿'） */
  value: React.ReactNode;
  /** 变化率或差值（如 '-0.79%', '+4.82%'） */
  delta?: React.ReactNode;
  /** 涨跌趋势色彩（A股红涨绿跌），auto 时根据数值或 delta 字符串自动推断 */
  trend?: MetricTrend;
  /** 展示形态变体 */
  variant?: MetricVariant;
  /** 药丸尺寸 */
  size?: MetricSize;
  /** 前缀图标或标志 */
  prefix?: React.ReactNode;
  /** 单位或后缀文本 */
  suffix?: React.ReactNode;
}

function resolveTrend(
  trend: MetricTrend,
  delta?: React.ReactNode,
  value?: React.ReactNode
): "up" | "down" | "flat" {
  if (trend !== "auto") {
    if (trend === "neutral") return "flat";
    return trend;
  }

  const checkText = (text: unknown): "up" | "down" | "flat" | null => {
    if (typeof text === "number") {
      if (text > 0) return "up";
      if (text < 0) return "down";
      return "flat";
    }
    if (typeof text === "string") {
      const trimmed = text.trim();
      if (trimmed.startsWith("+")) return "up";
      if (trimmed.startsWith("-")) return "down";
      const num = parseFloat(trimmed);
      if (!isNaN(num)) {
        if (num > 0) return "up";
        if (num < 0) return "down";
        return "flat";
      }
    }
    return null;
  };

  const deltaResult = checkText(delta);
  if (deltaResult) return deltaResult;

  const valueResult = checkText(value);
  if (valueResult) return valueResult;

  return "flat";
}

const TREND_TEXT_STYLES = {
  up: "text-rose-400",
  down: "text-emerald-400",
  flat: "text-slate-300",
};

const VARIANT_CONTAINER_STYLES: Record<
  MetricVariant,
  Record<"up" | "down" | "flat", string>
> = {
  default: {
    up: "bg-rose-950/20 border-rose-500/25",
    down: "bg-emerald-950/20 border-emerald-500/25",
    flat: "bg-white/[0.03] border-white/10",
  },
  subtle: {
    up: "bg-rose-500/10 border-transparent",
    down: "bg-emerald-500/10 border-transparent",
    flat: "bg-white/[0.02] border-transparent",
  },
  bordered: {
    up: "bg-black/30 border-rose-500/40 shadow-sm",
    down: "bg-black/30 border-emerald-500/40 shadow-sm",
    flat: "bg-black/30 border-white/15 shadow-sm",
  },
  tag: {
    up: "bg-rose-950/40 border-rose-800/40",
    down: "bg-emerald-950/40 border-emerald-800/40",
    flat: "bg-slate-900/60 border-slate-700/40",
  },
};

const SIZE_STYLES: Record<
  MetricSize,
  {
    container: string;
    label: string;
    value: string;
    delta: string;
  }
> = {
  xs: {
    container: "px-2 py-0.5 rounded-lg gap-1.5 text-[11px]",
    label: "text-[10px] text-slate-400",
    value: "font-mono font-semibold",
    delta: "font-mono text-[10px]",
  },
  sm: {
    container: "px-2.5 py-1 rounded-xl gap-2 text-xs",
    label: "text-[11px] text-slate-400",
    value: "font-mono font-bold",
    delta: "font-mono text-[11px]",
  },
  md: {
    container: "px-3.5 py-2 rounded-2xl gap-2.5 text-sm",
    label: "text-xs text-slate-400 font-medium",
    value: "text-base font-mono font-bold",
    delta: "font-mono text-xs font-semibold",
  },
  lg: {
    container: "p-4 rounded-2xl gap-3 text-base",
    label: "text-xs text-slate-400 font-medium",
    value: "text-xl md:text-2xl font-mono font-extrabold",
    delta: "font-mono text-xs font-bold",
  },
};

export const MetricPill = React.forwardRef<HTMLDivElement, MetricPillProps>(
  (
    {
      className,
      label,
      value,
      delta,
      trend = "auto",
      variant = "default",
      size = "sm",
      prefix,
      suffix,
      ...props
    },
    ref
  ) => {
    const finalTrend = resolveTrend(trend, delta, value);
    const trendTextClass = TREND_TEXT_STYLES[finalTrend];
    const containerVariantClass = VARIANT_CONTAINER_STYLES[variant][finalTrend];
    const currentSize = SIZE_STYLES[size];

    return (
      <div
        ref={ref}
        className={cn(
          "inline-flex items-center justify-between border backdrop-blur-md transition-all select-none",
          containerVariantClass,
          currentSize.container,
          className
        )}
        {...props}
      >
        <div className="flex items-center gap-1.5 min-w-0">
          {prefix && <span className="inline-flex shrink-0">{prefix}</span>}
          {label && <span className={cn("truncate", currentSize.label)}>{label}</span>}
        </div>

        <div className="flex items-center gap-1.5 shrink-0 ml-auto">
          <span className={cn(trendTextClass, currentSize.value)}>
            {value}
            {suffix && <span className="text-slate-400 ml-0.5 text-xs font-normal font-sans">{suffix}</span>}
          </span>
          {delta && (
            <span className={cn(trendTextClass, currentSize.delta)}>
              {delta}
            </span>
          )}
        </div>
      </div>
    );
  }
);

MetricPill.displayName = "MetricPill";
