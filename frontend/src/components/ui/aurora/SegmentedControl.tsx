"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface SegmentedItem<T extends string = string> {
  value: T;
  label: React.ReactNode;
  icon?: React.ReactNode;
  badge?: React.ReactNode;
  disabled?: boolean;
}

export type SegmentedSize = "sm" | "md" | "lg";

export interface SegmentedControlProps<T extends string = string> {
  items: SegmentedItem<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: SegmentedSize;
  fullWidth?: boolean;
  className?: string;
  itemClassName?: string;
  activeItemClassName?: string;
  "aria-label"?: string;
}

const SIZE_STYLES: Record<
  SegmentedSize,
  { container: string; item: string; text: string }
> = {
  sm: {
    container: "p-0.5 gap-0.5",
    item: "px-2.5 py-1",
    text: "text-xs",
  },
  md: {
    container: "p-1 gap-1",
    item: "px-4 py-1.5",
    text: "text-xs font-medium",
  },
  lg: {
    container: "p-1.5 gap-1.5",
    item: "px-5 py-2",
    text: "text-sm font-semibold",
  },
};

export function SegmentedControl<T extends string = string>({
  items,
  value,
  onChange,
  size = "md",
  fullWidth = false,
  className,
  itemClassName,
  activeItemClassName,
  "aria-label": ariaLabel = "分段控制器",
}: SegmentedControlProps<T>) {
  const currentSize = SIZE_STYLES[size];

  const handleKeyDown = (
    e: React.KeyboardEvent<HTMLButtonElement>,
    currentIndex: number
  ) => {
    const enabledItems = items.filter((item) => !item.disabled);
    const enabledCurrentIndex = enabledItems.findIndex(
      (item) => item.value === items[currentIndex].value
    );

    let nextIndex = -1;

    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      nextIndex = (enabledCurrentIndex + 1) % enabledItems.length;
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      nextIndex =
        (enabledCurrentIndex - 1 + enabledItems.length) % enabledItems.length;
    } else if (e.key === "Home") {
      e.preventDefault();
      nextIndex = 0;
    } else if (e.key === "End") {
      e.preventDefault();
      nextIndex = enabledItems.length - 1;
    }

    if (nextIndex !== -1 && enabledItems[nextIndex]) {
      onChange(enabledItems[nextIndex].value);
    }
  };

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={cn(
        "inline-flex items-center rounded-full bg-black/40 border border-white/10 backdrop-blur-md shadow-inner transition-colors",
        currentSize.container,
        fullWidth && "w-full flex",
        className
      )}
    >
      {items.map((item, index) => {
        const isSelected = item.value === value;
        return (
          <button
            key={item.value}
            role="tab"
            aria-selected={isSelected}
            aria-disabled={item.disabled}
            disabled={item.disabled}
            tabIndex={isSelected ? 0 : -1}
            onClick={() => !item.disabled && onChange(item.value)}
            onKeyDown={(e) => handleKeyDown(e, index)}
            className={cn(
              "relative flex items-center justify-center rounded-full transition-all duration-200 select-none outline-none focus-visible:ring-2 focus-visible:ring-purple-400 focus-visible:ring-offset-1 focus-visible:ring-offset-black",
              currentSize.item,
              currentSize.text,
              fullWidth && "flex-1",
              isSelected
                ? cn(
                    "bg-white/15 text-white shadow-sm font-semibold border border-white/10",
                    activeItemClassName
                  )
                : "text-slate-400 hover:text-white hover:bg-white/[0.04] font-medium",
              item.disabled && "opacity-40 cursor-not-allowed",
              itemClassName
            )}
          >
            {item.icon && <span className="mr-1.5 inline-flex shrink-0">{item.icon}</span>}
            <span>{item.label}</span>
            {item.badge && <span className="ml-1.5 shrink-0">{item.badge}</span>}
          </button>
        );
      })}
    </div>
  );
}
