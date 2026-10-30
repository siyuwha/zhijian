import pkg from "../../package.json";

/**
 * 前端工程静态版本与环境标识
 * 版本号源自 package.json，Git Commit 与构建时间在构建期动态注入
 */
export const APP_VERSION = `v${pkg.version}`;
export const STAGE_NAME = "知见·质量日志事务隔离与行情时态校验多源容灾闭环版";
export const BUILD_DATE = process.env.NEXT_PUBLIC_BUILD_DATE || "2026.10.30";
export const GIT_COMMIT = process.env.NEXT_PUBLIC_GIT_COMMIT || "v0.9.1";

export const FULL_VERSION_STRING = `${APP_VERSION} (${GIT_COMMIT})`;
