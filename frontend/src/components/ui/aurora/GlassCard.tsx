import * as React from "react";
import { cn } from "@/lib/utils";

export type GlassGlowVariant =
  | "none"
  | "purple"
  | "cyan"
  | "rose"
  | "amber"
  | "emerald";

export type GlassRounding = "xl" | "2xl" | "3xl" | "full";
export type GlassPadding = "none" | "sm" | "md" | "lg" | "xl";

export interface GlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  /** 发光光晕颜色变体 */
  glow?: GlassGlowVariant;
  /** 圆角大小，默认 3xl (24px Squircle 质感) */
  rounded?: GlassRounding;
  /** 内边距，默认 md (p-5) */
  padding?: GlassPadding;
  /** 是否启用悬浮光效与微浮动反馈，默认 true */
  hoverEffect?: boolean;
  /** 是否强制背景更加透明或加深 */
  intensity?: "subtle" | "default" | "solid";
}

const GLOW_CLASSES: Record<GlassGlowVariant, string> = {
  none: "",
  purple: "glow-purple border-purple-500/30",
  cyan: "glow-cyan border-cyan-500/30",
  rose: "glow-rose border-rose-500/30",
  amber: "glow-amber border-amber-500/30",
  emerald: "glow-emerald border-emerald-500/30",
};

const ROUNDING_CLASSES: Record<GlassRounding, string> = {
  xl: "rounded-xl",
  "2xl": "rounded-2xl",
  "3xl": "rounded-3xl",
  full: "rounded-full",
};

const PADDING_CLASSES: Record<GlassPadding, string> = {
  none: "p-0",
  sm: "p-3",
  md: "p-5",
  lg: "p-6 md:p-8",
  xl: "p-8 md:p-10",
};

const INTENSITY_CLASSES = {
  subtle: "bg-white/[0.02] backdrop-blur-xl border-white/[0.05]",
  default: "glass-card",
  solid: "bg-aurora-card/90 backdrop-blur-2xl border-white/10",
};

export const GlassCard = React.forwardRef<HTMLDivElement, GlassCardProps>(
  (
    {
      className,
      glow = "none",
      rounded = "3xl",
      padding = "md",
      hoverEffect = true,
      intensity = "default",
      children,
      ...props
    },
    ref
  ) => {
    return (
      <div
        ref={ref}
        className={cn(
          "relative overflow-hidden transition-all duration-300",
          INTENSITY_CLASSES[intensity],
          ROUNDING_CLASSES[rounded],
          PADDING_CLASSES[padding],
          GLOW_CLASSES[glow],
          hoverEffect &&
            "hover:border-white/20 hover:shadow-2xl hover:-translate-y-0.5 group",
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);

GlassCard.displayName = "GlassCard";
