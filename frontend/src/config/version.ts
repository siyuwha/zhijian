import pkg from "../../package.json";

/**
 * 前端工程化动态版本与环境标识
 * 版本号源于 package.json，Git Commit 与构建时间于构建期动态注入
 */
export const APP_VERSION = `v${pkg.version}`;
export const STAGE_NAME = "知见·AI认知复盘与全景驾驶舱版";
export const BUILD_DATE = process.env.NEXT_PUBLIC_BUILD_DATE || "2026.10.12";
export const GIT_COMMIT = process.env.NEXT_PUBLIC_GIT_COMMIT || "v0.4.0";

export const FULL_VERSION_STRING = `${APP_VERSION} (${GIT_COMMIT})`;
