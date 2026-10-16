import pkg from "../../package.json";

/**
 * 前端工程化动态版本与环境标识
 * 版本号源于 package.json，Git Commit 与构建时间于构建期动态注入
 */
export const APP_VERSION = `v${pkg.version}`;
export const STAGE_NAME = "知见·短线核心认知微观体检与极光驾驶舱实战版";
export const BUILD_DATE = process.env.NEXT_PUBLIC_BUILD_DATE || "2026.10.16";
const rawCommit = process.env.NEXT_PUBLIC_GIT_COMMIT || "v0.5.1";
export const GIT_COMMIT = rawCommit.length > 7 ? rawCommit.slice(0, 7) : rawCommit;

export const FULL_VERSION_STRING = `${APP_VERSION} (${GIT_COMMIT})`;
