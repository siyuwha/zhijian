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
  "2026-10-03": "国庆休市",
  "2026-10-04": "国庆休市",
  "2026-10-05": "国庆休市",
  "2026-10-06": "国庆休市",
  "2026-10-07": "国庆休市",
};

/**
 * 获取本地当前日期的 YYYY-MM-DD 字符串（避免 UTC 跨时区偏差）
 */
export function getTodayDateString(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

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

/**
 * 获取最新的交易日日期字符串（YYYY-MM-DD）。
 * 如果当天是周末或法定节假日休市，则自动往前推导至最近的上一个交易日。
 */
export function getLatestTradingDateString(): string {
  const now = new Date();
  // 最多往前倒推 30 天，防止异常死循环
  for (let i = 0; i < 30; i++) {
    const d = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const dStr = `${year}-${month}-${day}`;
    if (isTradingDay(dStr)) {
      return dStr;
    }
  }
  return getTodayDateString();
}

/**
 * 获取指定日期的前一个有效交易日（YYYY-MM-DD）
 */
export function getPrevTradingDay(dateStr: string): string {
  if (!dateStr) return '';
  const pure = dateStr.split('T')[0].split(' ')[0];
  const parts = pure.split('-');
  if (parts.length !== 3) return pure;
  const d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
  for (let i = 0; i < 20; i++) {
    d.setDate(d.getDate() - 1);
    const yr = d.getFullYear();
    const mo = String(d.getMonth() + 1).padStart(2, '0');
    const da = String(d.getDate()).padStart(2, '0');
    const checkStr = `${yr}-${mo}-${da}`;
    if (isTradingDay(checkStr)) {
      return checkStr;
    }
  }
  return pure;
}

/**
 * 格式化盘前简报生成时间：若原时间为 00:00:00 或无具体时间，保底显示当天交易日早上 08:30:00
 */
export function formatBriefingTime(generated_at?: string | null, date?: string): string {
  if (!generated_at && date) return `${date} 08:30:00`;
  if (!generated_at) return '--';
  const clean = generated_at.replace('T', ' ').slice(0, 19);
  if (clean.endsWith('00:00:00') && date) {
    return `${date} 08:30:00`;
  }
  return clean;
}

/**
 * 格式化集合竞价生成时间：如果包含 UTC 01:26:00 则校准为北京时间 09:26:00；若为 00:00:00 则保底为 09:26:00
 */
export function formatAuctionTime(generated_at?: string | null, date?: string): string {
  if (!generated_at && date) return `${date} 09:26:00`;
  if (!generated_at) return '--';
  const clean = generated_at.replace('T', ' ').slice(0, 19);
  if (clean.includes('01:26:00') || clean.endsWith('00:00:00')) {
    const d = clean.slice(0, 10);
    return `${d} 09:26:00`;
  }
  return clean;
}



