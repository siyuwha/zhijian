import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const WEEKDAY_NAMES = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

/**
 * 解析日期字符串并返回中文星期名称（如“周一”、“周三”、“周日”）
 * 使用年月日整数解析以避免 UTC 时区偏移
 */
export function getWeekday(dateStr: string | null | undefined): string {
  if (!dateStr) return "";
  const pure = dateStr.split("T")[0].split(" ")[0];
  const parts = pure.split("-");
  if (parts.length !== 3) return "";
  const year = parseInt(parts[0], 10);
  const month = parseInt(parts[1], 10) - 1;
  const day = parseInt(parts[2], 10);
  const d = new Date(year, month, day);
  if (isNaN(d.getTime())) return "";
  return WEEKDAY_NAMES[d.getDay()];
}

/**
 * 格式化日期字符串，附加星期几标注，例如: "2026-09-30 (周三)"
 */
export function formatDateWithWeekday(dateStr: string | null | undefined): string {
  if (!dateStr) return "";
  const pure = dateStr.split("T")[0].split(" ")[0];
  const wd = getWeekday(pure);
  return wd ? `${pure} (${wd})` : pure;
}

