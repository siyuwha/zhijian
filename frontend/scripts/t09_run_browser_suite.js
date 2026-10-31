const fs = require('fs');
const path = require('path');
const { execSync, execFileSync } = require('child_process');

console.log('================================================================');
console.log('T09-01 ISOLATED REAL BROWSER HARNESS (HEADLESS CHROME + REACT 19)');
console.log('================================================================');

const projectRoot = path.resolve(__dirname, '../..');
const distDir = path.join(__dirname, 'dist');
const evidenceDir = path.join(projectRoot, 'evidence');
const screenshotsDir = path.join(evidenceDir, 'screenshots');
const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

if (!fs.existsSync(distDir)) {
  fs.mkdirSync(distDir, { recursive: true });
}
if (!fs.existsSync(screenshotsDir)) {
  fs.mkdirSync(screenshotsDir, { recursive: true });
}

// 1. 严格从当前集成工作区源码重新编译所有组件 Bundle (使用本地 esbuild)
console.log('Unconditionally rebuilding all real browser bundles from current integration source...');
execFileSync('node', [path.join(__dirname, 'build_cockpit_bundle.mjs')], { stdio: 'inherit', cwd: projectRoot });

let allPassed = true;
function assertCheck(desc, condition) {
  if (condition) {
    console.log(`  [PASS] ${desc}`);
  } else {
    console.error(`  [FAIL] ${desc}`);
    allPassed = false;
  }
}

// -------------------------------------------------------------
// Suite 1: MarketStateBanner
// -------------------------------------------------------------
console.log('\n[Suite 1] MarketStateBanner Client Mount & Degradation Verification');
const bannerHtmlPath = path.join(distDir, 'test_banner_null.html');
const bannerScreenshotPath = path.join(screenshotsDir, 'market_state_banner_null.png');
const bannerHtml = `<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>MarketStateBanner Test</title></head>
<body>
  <div id="root">RootInit</div>
  <script>
    window.process = { env: { NODE_ENV: "production" } };
    window.onerror = function(msg, url, lineNo, columnNo, error) {
      var d = document.createElement('div');
      d.id = 'window-onerror';
      d.innerText = 'WINDOW_ERROR: ' + msg + ' line: ' + lineNo + ' col: ' + columnNo;
      document.body.appendChild(d);
    };
  </script>
  <script src="./banner_bundle.js"></script>
</body>
</html>`;
fs.writeFileSync(bannerHtmlPath, bannerHtml, 'utf-8');

const bannerCmd = `"${chromePath}" --headless=new --window-size=1280,400 --screenshot="${bannerScreenshotPath}" --dump-dom "file:///${bannerHtmlPath.replace(/\\/g, '/')}"`;
const bannerDom = execSync(bannerCmd, { encoding: 'utf8', maxBuffer: 15 * 1024 * 1024 });

assertCheck('Mounted in real browser without uncaught exceptions', !bannerDom.includes('id="actual-catch-error"') && !bannerDom.includes('id="window-onerror"'));
assertCheck('DOM contains client mount marker (#mount-marker == CLIENT_MOUNT_DONE)', bannerDom.includes('id="mount-marker">CLIENT_MOUNT_DONE</div>'));
assertCheck('Turnover displays "-- 万亿元 (口径待核准)"', bannerDom.includes('class="text-2xl font-black text-slate-100 font-mono tracking-tight">--</span>') && bannerDom.includes('(口径待核准)'));
assertCheck('Badge displays "口径待核准"', bannerDom.includes('口径待核准'));
assertCheck('Shanghai sub-turnover displays "沪: 6000 亿"', bannerDom.includes('沪: 6000 亿'));
assertCheck('Missing Shenzhen is safely suppressed (NOT displayed as 0)', !bannerDom.includes('深: 0'));

// -------------------------------------------------------------
// Suite 2: AuroraCockpitView - Case Null (降级与防泄露实验组)
// -------------------------------------------------------------
console.log('\n[Suite 2] AuroraCockpitView - Case Null (Degradation & Anti-Leak Experiment)');
const auroraNullHtmlPath = path.join(distDir, 'test_aurora_null.html');
const auroraNullScreenshotPath = path.join(screenshotsDir, 'aurora_cockpit_turnover_null.png');
const auroraNullHtml = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>AuroraCockpitView Test - Turnover null</title>
  <style>
    * { box-sizing: border-box; }
    body { background: #07090E; color: #f8fafc; font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; margin: 0; padding: 20px; }
  </style>
</head>
<body>
  <div id="root"></div>
  <script>
    window.process = { env: { NODE_ENV: "production" } };
    window.__CUSTOM_TURNOVER__ = null;
    window.onerror = function(msg, url, lineNo, columnNo, error) {
      var d = document.createElement('div');
      d.id = 'window-onerror';
      d.innerText = 'WINDOW_ERROR: ' + msg + ' line: ' + lineNo + ' col: ' + columnNo;
      document.body.appendChild(d);
    };
  </script>
  <script src="./aurora_bundle.js"></script>
</body>
</html>`;
fs.writeFileSync(auroraNullHtmlPath, auroraNullHtml, 'utf-8');

const auroraNullCmd = `"${chromePath}" --headless=new --virtual-time-budget=3000 --window-size=1440,1080 --screenshot="${auroraNullScreenshotPath}" --dump-dom "file:///${auroraNullHtmlPath.replace(/\\/g, '/')}"`;
const auroraNullDom = execSync(auroraNullCmd, { encoding: 'utf8', maxBuffer: 25 * 1024 * 1024 });

const auroraNullScriptIdx = auroraNullDom.indexOf('<script>');
const auroraNullRenderedDom = auroraNullDom.substring(0, auroraNullScriptIdx);

assertCheck('Mounted in real browser without uncaught exceptions', !auroraNullDom.includes('id="actual-catch-error"') && !auroraNullDom.includes('id="window-onerror"'));
assertCheck('Async data cycle completed (#mount-marker == AURORA_CLIENT_MOUNT_DONE)', auroraNullDom.includes('id="mount-marker">AURORA_CLIENT_MOUNT_DONE</div>'));
assertCheck('Timeline stage data confirmed loaded ("收盘总评" & "置信度 92%")', auroraNullRenderedDom.includes('收盘总评') && auroraNullRenderedDom.includes('置信度 92%'));
assertCheck('Formal turnover displays "-- 亿 (口径待核准)"', auroraNullRenderedDom.includes('-- 亿 (口径待核准)'));
assertCheck('Shanghai sub-turnover displays "沪 6,000亿"', auroraNullRenderedDom.includes('沪 6,000亿'));
assertCheck('Missing Shenzhen is safely suppressed (NOT displayed as 0)', !auroraNullRenderedDom.includes('深 0亿') && !auroraNullRenderedDom.includes('深 0.00'));
assertCheck('Historical briefing prediction ("2.50万亿") is strictly BLOCKED from leaking into DOM', !auroraNullRenderedDom.includes('2.50万亿') && !auroraNullRenderedDom.includes('2.50 万亿'));
assertCheck('Fallback prediction displays "-- 万亿 (待核准)"', auroraNullRenderedDom.includes('-- 万亿 (待核准)'));
assertCheck('Prediction description badge displays "量能口径待核准"', auroraNullRenderedDom.includes('量能口径待核准'));

// -------------------------------------------------------------
// Suite 3: AuroraCockpitView - Case Valid (正控对照组: 证明内参预测可正常消费)
// -------------------------------------------------------------
console.log('\n[Suite 3] AuroraCockpitView - Case Valid (Positive Control: Turnover 18,500 Yi)');
const auroraValidHtmlPath = path.join(distDir, 'test_aurora_valid.html');
const auroraValidScreenshotPath = path.join(screenshotsDir, 'aurora_cockpit_turnover_valid.png');
const auroraValidHtml = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>AuroraCockpitView Test - Turnover Valid</title>
  <style>
    * { box-sizing: border-box; }
    body { background: #07090E; color: #f8fafc; font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; margin: 0; padding: 20px; }
  </style>
</head>
<body>
  <div id="root"></div>
  <script>
    window.process = { env: { NODE_ENV: "production" } };
    window.__CUSTOM_TURNOVER__ = 18500.0;
    window.onerror = function(msg, url, lineNo, columnNo, error) {
      var d = document.createElement('div');
      d.id = 'window-onerror';
      d.innerText = 'WINDOW_ERROR: ' + msg + ' line: ' + lineNo + ' col: ' + columnNo;
      document.body.appendChild(d);
    };
  </script>
  <script src="./aurora_bundle.js"></script>
</body>
</html>`;
fs.writeFileSync(auroraValidHtmlPath, auroraValidHtml, 'utf-8');

const auroraValidCmd = `"${chromePath}" --headless=new --virtual-time-budget=3000 --window-size=1440,1080 --screenshot="${auroraValidScreenshotPath}" --dump-dom "file:///${auroraValidHtmlPath.replace(/\\/g, '/')}"`;
const auroraValidDom = execSync(auroraValidCmd, { encoding: 'utf8', maxBuffer: 25 * 1024 * 1024 });

const auroraValidScriptIdx = auroraValidDom.indexOf('<script>');
const auroraValidRenderedDom = auroraValidDom.substring(0, auroraValidScriptIdx);

assertCheck('Mounted in real browser without uncaught exceptions', !auroraValidDom.includes('id="actual-catch-error"') && !auroraValidDom.includes('id="window-onerror"'));
assertCheck('Async data cycle completed (#mount-marker == AURORA_CLIENT_MOUNT_DONE)', auroraValidDom.includes('id="mount-marker">AURORA_CLIENT_MOUNT_DONE</div>'));
assertCheck('Timeline stage data confirmed loaded ("收盘总评" & "置信度 92%")', auroraValidRenderedDom.includes('收盘总评') && auroraValidRenderedDom.includes('置信度 92%'));
assertCheck('Formal turnover displays valid amount "18,500 亿"', auroraValidRenderedDom.includes('18,500 亿'));
assertCheck('Positive control SUCCESS: Briefing prediction "2.50万亿" is displayed when turnover is valid', auroraValidRenderedDom.includes('2.50万亿'));

console.log('\n================================================================');
if (allPassed) {
  console.log('ALL BROWSER DOM ASSERTIONS PASSED (20/20 checks passed)');
  console.log(`Screenshots saved to: ${screenshotsDir}`);
} else {
  console.error('SOME CHECKS FAILED');
  process.exit(1);
}
console.log('================================================================');
