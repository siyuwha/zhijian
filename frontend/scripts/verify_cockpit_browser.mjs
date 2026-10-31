/**
 * Headless Chrome Browser Real React 19 Component Verification Script
 * 真实无头 Chrome 浏览器真实 React 19 组件挂载与质量治理状态机端到端验收脚本
 *
 * 执行方式: node frontend/scripts/verify_cockpit_browser.mjs
 * 核心验证机制:
 * 1. 使用 esbuild 将真实 AuroraCockpitView.tsx 及其 React 19 依赖编译为浏览器 bundle
 * 2. 真实启动本地 Chrome 进程 (chrome.exe --headless=new)，在真实 DOM 环境中挂载组件
 * 3. 在浏览器中拦截 fetch 请求，向组件注入严格的各场景标准契约数据
 * 4. 验证真实 DOM 渲染：实测标签、算法拟合估算标签、STALE 缓存标签与来源时间格式化
 * 5. 验证真实 8 秒重试恢复：依赖 Chrome 虚拟时间前进，验证真实 setTimeout(..., 8000) 触发重试、
 *    接收恢复数据、组件重新渲染并将 UNAVAILABLE 错误占位动态恢复为真实走势 SVG
 */

import { execFileSync } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CHROME_PATH = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

if (!fs.existsSync(CHROME_PATH)) {
  console.error(`Chrome binary not found at ${CHROME_PATH}`);
  process.exit(1);
}

// 每次执行均严格重新构建 bundle，确保被测产物与最新组件源码完全一致
const bundlePath = path.join(__dirname, 'dist', 'cockpit_real_bundle.js');
console.log('Unconditionally re-compiling cockpit_real_bundle.js from source...');
execFileSync('node', [path.join(__dirname, 'build_cockpit_bundle.mjs')], { stdio: 'inherit' });
const bundleContent = fs.readFileSync(bundlePath, 'utf-8');

function runHeadlessChrome(scenario, virtualBudget = 3000) {
  const harnessHtml = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>Aurora Cockpit Real Component Runner - ${scenario}</title>
  <style>
    body { background-color: #020617; color: #f8fafc; font-family: monospace; margin: 0; padding: 20px; }
  </style>
</head>
<body>
  <div id="root"></div>
  <div id="debug"></div>
  <script>
    window.process = { env: { NODE_ENV: "production" } };
    window.__TEST_SCENARIO__ = "${scenario}";
    window.onerror = function(msg, url, line, col, err) {
      document.getElementById("debug").innerText = "ERR: " + msg;
    };
  <\/script>
  <script>${bundleContent}<\/script>
</body>
</html>`;

  const tmpHtmlPath = path.join(__dirname, `tmp_harness_${scenario}.html`);
  fs.writeFileSync(tmpHtmlPath, harnessHtml, 'utf-8');

  try {
    const rawDom = execFileSync(CHROME_PATH, [
      '--headless=new',
      '--disable-gpu',
      '--no-sandbox',
      `--virtual-time-budget=${virtualBudget}`,
      '--dump-dom',
      `file:///${tmpHtmlPath.replace(/\\/g, '/')}`,
    ], { encoding: 'utf-8', timeout: 30000, maxBuffer: 50 * 1024 * 1024 });

    // 剥离 <script> 源码部分，只保留真实渲染出的 DOM 内容进行断言
    const scriptIdx = rawDom.indexOf('<script>');
    const bodyContent = scriptIdx !== -1 ? rawDom.slice(0, scriptIdx) : rawDom;
    return { rawDom, bodyContent };
  } finally {
    try {
      if (fs.existsSync(tmpHtmlPath)) fs.unlinkSync(tmpHtmlPath);
    } catch (_) {}
  }
}

let passedCount = 0;
let totalCount = 0;

function assert(condition, message) {
  totalCount++;
  if (!condition) {
    console.error(`❌ [FAIL] ${message}`);
    process.exitCode = 1;
  } else {
    passedCount++;
    console.log(`✅ [PASS] ${message}`);
  }
}

console.log("=== 启动真实无头 Chrome 浏览器执行真实 React 19 组件 (AuroraCockpitView) 验收 ===\n");

// 1. 真实逐笔实测模式 (FULL, is_estimated=False)
console.log("--- 场景 1: 真实逐笔实测模式 (FULL, is_estimated=False) ---");
{
  const { bodyContent } = runHeadlessChrome("scenario_realtime_measured", 3000);
  assert(bodyContent.includes("题材战场 · Top 5 分时主力资金争夺曲线与领涨核心龙头"), "Scene 1: 真实 React 组件成功挂载题材战场标题");
  assert(bodyContent.includes('data-testid="sector-curve-svg"'), "Scene 1: 真实 DOM 成功渲染板块分时资金曲线 SVG");
  assert(bodyContent.includes('data-testid="stock-curve-svg"'), "Scene 1: 真实 DOM 成功渲染核心个股分时走势对比曲线 SVG");
  assert(!bodyContent.includes('data-testid="sector-estimated-badge"'), "Scene 1: 实测模式下真实 DOM 严禁显示算法估算标签");
  assert(!bodyContent.includes('data-testid="sector-unavailable-badge"'), "Scene 1: 正常实测模式下无不可用降级警示");
  assert(bodyContent.includes("(逐笔实测)"), "Scene 1: 悬停浮窗正确呈现 '(逐笔实测)' 真实时态标签");
}

// 2. 算法拟合估算模式 (FULL, is_estimated=True)
console.log("\n--- 场景 2: 算法拟合估算模式 (FULL, is_estimated=True) ---");
{
  const { bodyContent } = runHeadlessChrome("scenario_estimated_flow", 3000);
  assert(bodyContent.includes('data-testid="sector-estimated-badge"'), "Scene 2: 真实 DOM 挂载算法估算测试标识");
  assert(bodyContent.includes("资金流为算法拟合估算 (非逐笔实测)"), "Scene 2: 真实 DOM 明确渲染算法拟合估算警示徽章");
  assert(bodyContent.includes('data-testid="sector-estimated-legend"'), "Scene 2: 真实图例区域渲染 '拟合估算' 徽章");
  assert(bodyContent.includes("基于分时量能与涨幅动态拟合资金流趋势 (算法估算)"), "Scene 2: 副标题明确标注算法估算口径");
  assert(bodyContent.includes("(算法估算)"), "Scene 2: 悬停浮窗正确呈现 '(算法估算)' 标签");
}

// 3. 快照缓存容忍期模式 (DEGRADED, freshness=STALE)
console.log("\n--- 场景 3: 快照缓存容忍期模式 (DEGRADED, freshness=STALE) ---");
{
  const { bodyContent } = runHeadlessChrome("scenario_stale_tolerance", 3000);
  assert(bodyContent.includes('data-testid="sector-stale-badge"'), "Scene 3: 真实 DOM 成功挂载缓存降级徽章");
  assert(bodyContent.includes("使用缓存，更新于 10:15"), "Scene 3: 真实 DOM 精准呈现数据源截止时点 10:15");
  assert(!bodyContent.includes('data-testid="sector-unavailable-badge"'), "Scene 3: 容忍期缓存模式不误判为不可用故障");
}

// 4. 物理源故障不可用降级模式 (UNAVAILABLE, status=EMPTY, error_code=TIMEOUT)
console.log("\n--- 场景 4: 物理源故障不可用降级模式 (UNAVAILABLE, status=EMPTY) ---");
{
  const { bodyContent } = runHeadlessChrome("scenario_unavailable_fault", 3000);
  assert(bodyContent.includes('data-testid="sector-unavailable-badge"'), "Scene 4: 真实 DOM 成功挂载不可用警示徽章");
  assert(bodyContent.includes("板块资金流暂不可用"), "Scene 4: 真实 DOM 呈现板块资金流暂不可用降级文案");
  assert(bodyContent.includes('data-testid="sector-empty-state"'), "Scene 4: 真实 DOM 挂载板块安全降级占位节点");
  assert(bodyContent.includes("暂无有效走势数据 (已安全降级)"), "Scene 4: 曲线区域呈现安全降级占位文案，严禁渲染虚假分时");
  assert(!bodyContent.includes('data-testid="sector-curve-svg"'), "Scene 4: 不可用模式下彻底杜绝渲染虚假分时曲线 SVG");
}

// 5. 真实定时重试恢复 (UNAVAILABLE -> 8s retry -> FULL Realtime)
console.log("\n--- 场景 5: 真实 8 秒定时重试动态恢复模式 (UNAVAILABLE -> 8s retry -> FULL) ---");
{
  // 5.1 故障期 (T=2s, 8秒定时器未到期)
  const { rawDom: phase1Raw, bodyContent: phase1Dom } = runHeadlessChrome("scenario_retry_recovery", 2000);
  const p1FetchMatch = phase1Raw.match(/data-stock-fetch-count="(\d+)"/);
  const p1FetchCount = p1FetchMatch ? parseInt(p1FetchMatch[1], 10) : 0;
  assert(p1FetchCount === 1, "Scene 5.1: 故障期请求计数严格为 1 次 (初次故障请求)");
  assert(phase1Dom.includes('data-testid="stock-trends-unavailable-badge"'), "Scene 5.1: 初次请求故障后真实 DOM 呈现分时不可用警示");
  assert(phase1Dom.includes("分时走势暂不可用"), "Scene 5.1: 初次请求故障后真实 DOM 渲染不可用文案");
  assert(phase1Dom.includes('data-testid="stock-trends-empty-state"'), "Scene 5.1: 故障期真实 DOM 呈现空态占位");

  // 5.2 恢复期 (T=12s, 8秒真实定时器在虚拟时间中到期触发重试并成功恢复)
  const { rawDom: phase2Raw, bodyContent: phase2Dom } = runHeadlessChrome("scenario_retry_recovery", 12000);
  const p2FetchMatch = phase2Raw.match(/data-stock-fetch-count="(\d+)"/);
  const p2FetchCount = p2FetchMatch ? parseInt(p2FetchMatch[1], 10) : 0;
  assert(p2FetchCount === 2, "Scene 5.2: 8秒定时器触发重试后请求计数严格递增为 2 次 (重试请求发出)");
  assert(!phase2Dom.includes('data-testid="stock-trends-unavailable-badge"'), "Scene 5.2: 8秒重试恢复后不可用警示徽章已从真实 DOM 中完全卸载移除");
  assert(phase2Dom.includes('data-testid="stock-curve-svg"'), "Scene 5.2: 8秒重试恢复后真实 DOM 动态挂载恢复后的分时走势曲线 SVG");
  assert(!phase2Dom.includes('data-testid="stock-trends-empty-state"'), "Scene 5.2: 恢复后空态占位已完全卸载移除");
}

// 6. A10 逆序时序防线 (较新成功先到，较旧失败迟到)
console.log("\n--- 场景 6: 真实组件 A10 逆序时序防线 (较新成功先到，较旧失败迟到) ---");
{
  const { rawDom, bodyContent } = runHeadlessChrome("scenario_out_of_order_defense", 3000);
  const fetchCountMatch = rawDom.match(/data-stock-fetch-count="(\d+)"/);
  const fetchCount = fetchCountMatch ? parseInt(fetchCountMatch[1], 10) : 0;
  const req1Held = rawDom.includes('data-req1-held="true"');
  const req1LateResolved = rawDom.includes('data-req1-late-resolved="true"');
  const req2Resolved = rawDom.includes('data-req2-resolved="true"');

  assert(fetchCount === 2, "Scene 6: 逆序防线场景下组件共发起 2 次真实请求 (初始日期请求与切日请求)");
  assert(req1Held, "Scene 6: 旧请求 (Req 1, 2026-10-30) 成功被拦截并延迟保持");
  assert(req2Resolved, "Scene 6: 新请求 (Req 2, 2026-10-31) 立即成功交付并挂载");
  assert(req1LateResolved, "Scene 6: 旧请求在较新请求交付后迟到返回失败响应");
  assert(bodyContent.includes('data-testid="stock-curve-svg"'), "Scene 6: 较新请求成功渲染的真实分时走势 SVG 曲线严格保持在 DOM 中");
  assert(!bodyContent.includes('data-testid="stock-trends-unavailable-badge"'), "Scene 6: 迟到的旧失败响应被请求序号与交易日防线丢弃，绝未误触发不可用降级警示");
  assert(!bodyContent.includes('data-testid="stock-trends-empty-state"'), "Scene 6: 真实 DOM 杜绝被迟到失败改写为空态占位");
}

// 7. 真实延迟时态模式 (DEGRADED, freshness=DELAYED)
console.log("\n--- 场景 7: 真实延迟时态模式 (DEGRADED, freshness=DELAYED) ---");
{
  const { bodyContent } = runHeadlessChrome("scenario_delayed_freshness", 3000);
  assert(bodyContent.includes('data-testid="stock-trends-delayed-badge"'), "Scene 7: 真实 DOM 成功挂载分时行情延迟徽章");
  assert(bodyContent.includes("分时行情延迟"), "Scene 7: 真实 DOM 明确渲染 '分时行情延迟' 警示文案");
  assert(bodyContent.includes('data-testid="sector-delayed-badge"'), "Scene 7: 真实 DOM 成功挂载板块行情延迟徽章");
  assert(bodyContent.includes("板块行情延迟"), "Scene 7: 真实 DOM 明确渲染 '板块行情延迟' 警示文案");
  assert(bodyContent.includes('data-testid="stock-curve-svg"'), "Scene 7: 延迟行情下真实 DOM 正常渲染个股分时走势 SVG 曲线");
  assert(bodyContent.includes('data-testid="sector-curve-svg"'), "Scene 7: 延迟行情下真实 DOM 正常渲染板块分时资金曲线 SVG");
  assert(!bodyContent.includes('data-testid="stock-trends-unavailable-badge"'), "Scene 7: 延迟行情绝不误报为分时不可用故障");
  assert(!bodyContent.includes('data-testid="sector-unavailable-badge"'), "Scene 7: 延迟行情绝不误报为板块不可用故障");
  assert(!bodyContent.includes('data-testid="stock-trends-stale-badge"'), "Scene 7: 延迟行情不混淆误报为缓存快照");
}

// 8. 独立验证 /market/sectors 质量链与组件消费 (Canonical 异常回退至 market/sectors)
console.log("\n--- 场景 8: 独立验证 /market/sectors 质量链与组件消费 (market/sectors 独立 DELAYED) ---");
{
  const { bodyContent } = runHeadlessChrome("scenario_market_sectors_alone_delayed", 3000);
  assert(bodyContent.includes('data-testid="sector-delayed-badge"'), "Scene 8: Canonical 异常时，market/sectors DELAYED 质量驱动真实 DOM 挂载板块延迟徽章");
  assert(bodyContent.includes("板块行情延迟"), "Scene 8: 真实 DOM 明确渲染 '板块行情延迟' 警示文案");
  assert(bodyContent.includes('data-testid="sector-curve-svg"'), "Scene 8: 降级消费 market/sectors 时真实 DOM 正常渲染板块分时资金曲线 SVG");
  assert(!bodyContent.includes('data-testid="sector-unavailable-badge"'), "Scene 8: 延迟状态不误报为不可用故障");
}

// 9. 双时态并存与单侧时间防冒充防线 (排行 STALE + 分时 DELAYED 并存)
console.log("\n--- 场景 9: 双时态并存与单侧时间防冒充防线 (排行 STALE + 分时 DELAYED 并存) ---");
{
  const { bodyContent } = runHeadlessChrome("scenario_dual_stale_and_delayed", 3000);
  assert(bodyContent.includes('data-testid="sector-stale-badge"'), "Scene 9: 真实 DOM 成功挂载缓存降级徽章 (STALE 不被 DELAYED 隐藏)");
  assert(bodyContent.includes("排行使用缓存，更新于 10:15"), "Scene 9: 单侧截止时间明确标注为 '排行使用缓存'，杜绝冒充整体截止");
  assert(bodyContent.includes('data-testid="sector-delayed-badge"'), "Scene 9: 真实 DOM 同时挂载板块分时延迟徽章 (双时态并存展示)");
  assert(bodyContent.includes("板块分时行情延迟"), "Scene 9: 真实 DOM 明确渲染 '板块分时行情延迟' 警示文案");
}

// 9.2 反向双时态并存场景 (排行 DELAYED + 分时 STALE 并存)
console.log("\n--- 场景 9.2: 反向双时态并存场景 (排行 DELAYED + 分时 STALE 并存) ---");
{
  const { bodyContent } = runHeadlessChrome("scenario_reverse_dual_delayed_and_stale", 3000);
  assert(bodyContent.includes('data-testid="sector-stale-badge"'), "Scene 9.2: 真实 DOM 成功挂载缓存降级徽章 (STALE 不被 DELAYED 隐藏)");
  assert(bodyContent.includes("分时使用缓存，更新于 10:20"), "Scene 9.2: 单侧截止时间明确标注为 '分时使用缓存'，杜绝冒充整体截止");
  assert(bodyContent.includes('data-testid="sector-delayed-badge"'), "Scene 9.2: 真实 DOM 同时挂载板块排行延迟徽章 (双时态并存展示)");
  assert(bodyContent.includes("板块排行行情延迟"), "Scene 9.2: 真实 DOM 明确渲染 '板块排行行情延迟' 警示文案");
  assert(bodyContent.includes('data-testid="sector-curve-svg"'), "Scene 9.2: 反向双时态下真实 DOM 正常渲染板块分时资金曲线 SVG");
  assert(bodyContent.includes('data-testid="stock-curve-svg"'), "Scene 9.2: 反向双时态下真实 DOM 正常渲染个股分时走势 SVG 曲线");
  assert(!bodyContent.includes('data-testid="sector-unavailable-badge"'), "Scene 9.2: 反向双时态绝不误报为板块不可用故障");
}

// 10. 时效未知降级与恢复验证 (Round 9 P1: freshness=UNAVAILABLE -> 时效未知提示 -> 恢复后提示消失)
console.log("\n--- 场景 10: 时效未知降级与恢复模式 (freshness=UNAVAILABLE -> 时效未知提示 -> 恢复后提示消失) ---");
{
  // 10.1 降级期 (T=2s, 刷新未触发)
  const { bodyContent: phase1Dom } = runHeadlessChrome("scenario_unknown_freshness_recovery", 2000);
  assert(phase1Dom.includes('data-testid="sector-freshness-unknown-badge"'), "Scene 10.1: 时效未知模式下真实 DOM 挂载时效未知降级徽章");
  assert(phase1Dom.includes("时效未知"), "Scene 10.1: 真实 DOM 明确渲染 '时效未知' 或等义风险警示文案");
  assert(phase1Dom.includes('data-testid="sector-curve-svg"'), "Scene 10.1: 时效未知但 status=AVAILABLE 时正常渲染分时资金曲线 SVG");
  assert(!phase1Dom.includes('data-testid="sector-unavailable-badge"'), "Scene 10.1: 时效未知降级不误报为板块暂不可用故障");

  // 10.2 恢复期 (T=6s, 刷新触发并成功返回正常响应)
  const { bodyContent: phase2Dom } = runHeadlessChrome("scenario_unknown_freshness_recovery", 6000);
  assert(!phase2Dom.includes('data-testid="sector-freshness-unknown-badge"'), "Scene 10.2: 恢复正常响应后真实 DOM 成功卸载移除时效未知徽章");
  assert(!phase2Dom.includes("时效未知"), "Scene 10.2: 恢复正常响应后 '时效未知' 警示文案彻底消失");
  assert(phase2Dom.includes('data-testid="sector-curve-svg"'), "Scene 10.2: 恢复后正常渲染分时资金曲线 SVG");
}

// 11. 时效未知防掩盖与恢复验证 (Round 10 P1: 排行 UNAVAILABLE + 分时缺失，degradation_reason 为“板块分时走势缺失，仅提供静态排行”)
console.log("\n--- 场景 11: 时效未知防掩盖与恢复模式 (排行 UNAVAILABLE + 分时缺失，防时效未知被其他原因掩盖) ---");
{
  // 11.1 降级期 (T=2s, 刷新未触发)
  const { bodyContent: phase1Dom } = runHeadlessChrome("scenario_unknown_freshness_masked_by_reason_recovery", 2000);
  assert(phase1Dom.includes('data-testid="sector-freshness-unknown-badge"'), "Scene 11.1: 真实 DOM 成功挂载时效未知降级徽章");
  assert(phase1Dom.includes("时效未知"), "Scene 11.1: 时效未知警示文案明确呈现，绝未被其他降级原因掩盖");
  assert(phase1Dom.includes("板块分时走势缺失，仅提供静态排行"), "Scene 11.1: 同时完整保留并呈现具体降级原因 (板块分时走势缺失，仅提供静态排行)");
  assert(!phase1Dom.includes('data-testid="sector-unavailable-badge"'), "Scene 11.1: 时效未知且分时缺失不误报为板块暂不可用故障");

  // 11.2 恢复期 (T=6s, 刷新触发并成功返回正常响应)
  const { bodyContent: phase2Dom } = runHeadlessChrome("scenario_unknown_freshness_masked_by_reason_recovery", 6000);
  assert(!phase2Dom.includes('data-testid="sector-freshness-unknown-badge"'), "Scene 11.2: 恢复正常响应后真实 DOM 成功卸载移除时效未知徽章");
  assert(!phase2Dom.includes("时效未知"), "Scene 11.2: 恢复正常响应后 '时效未知' 警示文案彻底消失");
  assert(!phase2Dom.includes("板块分时走势缺失，仅提供静态排行"), "Scene 11.2: 恢复正常响应后分时缺失降级文案彻底消失");
  assert(phase2Dom.includes('data-testid="sector-curve-svg"'), "Scene 11.2: 恢复后正常渲染分时资金曲线 SVG");
}

console.log(`\n========================================`);
console.log(`无头 Chrome 浏览器真实组件验收结果: ${passedCount}/${totalCount} 项断言通过!`);
console.log(`========================================\n`);

if (passedCount !== totalCount) {
  process.exit(1);
}
