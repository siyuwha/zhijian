import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const WEEKDAY_NAMES = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

export const HOLIDAY_LABELS: Record<string, string> = {
  // 元旦
  "2026-01-01": "元旦休市",
  "2026-01-02": "元旦休市",
  // 春节
  "2026-02-16": "春节休市",
  "2026-02-17": "春节休市",
  "2026-02-18": "春节休市",
  "2026-02-19": "春节休市",
  "2026-02-20": "春节休市",
  // 清明节
  "2026-04-03": "清明休市",
  "2026-04-06": "清明休市",
  // 劳动节
  "2026-05-01": "劳动节休市",
  "2026-05-04": "劳动节休市",
  "2026-05-05": "劳动节休市",
  // 端午节
  "2026-06-19": "端午休市",
  // 中秋节
  "2026-09-25": "中秋休市",
  // 国庆节
  "2026-10-01": "国庆休市",
  "2026-10-02": "国庆休市",
  "2026-10-05": "国庆休市",
  "2026-10-06": "国庆休市",
  "2026-10-07": "国庆休市",
};

/**
 * 判断是否为交易日（排除周末与A股法定休市日）
 */
export function isTradingDay(dateStr: string | null | undefined): boolean {
  if (!dateStr) return false;
  const pure = dateStr.split("T")[0].split(" ")[0];
  const parts = pure.split("-");
  if (parts.length !== 3) return false;
  const year = parseInt(parts[0], 10);
  const month = parseInt(parts[1], 10) - 1;
  const day = parseInt(parts[2], 10);
  const d = new Date(year, month, day);
  if (isNaN(d.getTime())) return false;
  if (d.getDay() === 0 || d.getDay() === 6) return false;
  if (HOLIDAY_LABELS[pure]) return false;
  return true;
}

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
 * 获取日期的交易日/休市状态标签（如“国庆休市”、“周末休市”，正常交易日返回空字符串）
 */
export function getHolidayLabel(dateStr: string | null | undefined): string {
  if (!dateStr) return "";
  const pure = dateStr.split("T")[0].split(" ")[0];
  if (HOLIDAY_LABELS[pure]) return HOLIDAY_LABELS[pure];
  const parts = pure.split("-");
  if (parts.length === 3) {
    const year = parseInt(parts[0], 10);
    const month = parseInt(parts[1], 10) - 1;
    const day = parseInt(parts[2], 10);
    const d = new Date(year, month, day);
    if (!isNaN(d.getTime()) && (d.getDay() === 0 || d.getDay() === 6)) {
      return "周末休市";
    }
  }
  return "";
}

/**
 * 格式化日期字符串，附加星期几与休市标注
 * 示例:
 * - "2026-09-30 (周三)"
 * - "2026-10-01 (周四·国庆休市)"
 * - "2026-09-26 (周六·周末休市)"
 */
export function formatDateWithWeekday(dateStr: string | null | undefined): string {
  if (!dateStr) return "";
  const pure = dateStr.split("T")[0].split(" ")[0];
  const wd = getWeekday(pure);
  if (!wd) return pure;
  const hLabel = getHolidayLabel(pure);
  if (hLabel) {
    return `${pure} (${wd}·${hLabel})`;
  }
  return `${pure} (${wd})`;
}

