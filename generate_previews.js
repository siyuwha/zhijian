const fs = require('fs');
const { execSync } = require('child_process');
const path = require('path');

const cwd = process.cwd();
const edge = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe';

const targets = [
  { html: 'strategy_preview_vA.html', img: 'strategy_preview_vA.png' },
  { html: 'strategy_preview_vB.html', img: 'strategy_preview_vB.png' },
  { html: 'strategy_preview_vC.html', img: 'strategy_preview_vC.png' },
];

for (const t of targets) {
  const htmlPath = path.join(cwd, t.html).replace(/\\/g, '/');
  const imgPath = path.join(cwd, t.img);
  const flags = [
    '--headless=new',
    '--disable-gpu',
    '--disable-background-networking',
    '--disable-default-apps',
    '--disable-extensions',
    '--disable-sync',
    '--no-first-run',
    '--hide-scrollbars',
    '--window-size=1600,1050',
    `--screenshot="${imgPath}"`,
    `"file:///${htmlPath}"`
  ].join(' ');

  const cmd = `"${edge}" ${flags}`;
  console.log(`Executing screenshot for ${t.html}...`);
  try {
    execSync(cmd, { stdio: 'ignore', timeout: 8000 });
    if (fs.existsSync(imgPath)) {
      const stat = fs.statSync(imgPath);
      console.log(`SUCCESS: ${t.img} (${stat.size} bytes)`);
    } else {
      console.error(`Not found: ${imgPath}`);
    }
  } catch (err) {
    console.error(`Error: ${err.message}`);
  }
}
