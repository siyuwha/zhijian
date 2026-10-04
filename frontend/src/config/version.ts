import pkg from "../../package.json";

/**
 * 前端工程化动态版本与环境标识
 * 版本号源于 package.json，Git Commit 与构建时间于构建期动态注入
 */
export const APP_VERSION = `v${pkg.version}`;
export const STAGE_NAME = "Wave 1 事实底盘扩容版";
export const BUILD_DATE = process.env.NEXT_PUBLIC_BUILD_DATE || "2026.10.04";
export const GIT_COMMIT = process.env.NEXT_PUBLIC_GIT_COMMIT || "36855d2";

export const FULL_VERSION_STRING = `${APP_VERSION} (${GIT_COMMIT})`;
