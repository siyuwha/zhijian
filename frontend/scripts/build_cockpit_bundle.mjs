import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, '../..');
const distDir = path.join(__dirname, 'dist');

if (!fs.existsSync(distDir)) {
  fs.mkdirSync(distDir, { recursive: true });
}

// 严格使用本地 node_modules 中的 esbuild，缺失时明确报错退出，严禁临时联网下载
let esbuild;
try {
  esbuild = await import('esbuild');
} catch (err) {
  console.error("FATAL: Local 'esbuild' dependency is missing in frontend/node_modules.");
  console.error("Please run 'npm ci' inside the frontend directory. Network download is strictly disabled.");
  process.exit(1);
}

console.log(`Building real browser test bundles using local esbuild (v${esbuild.version})...`);

const commonAliases = {
  'react': path.join(projectRoot, 'frontend/node_modules/react'),
  'react-dom': path.join(projectRoot, 'frontend/node_modules/react-dom'),
  'lucide-react': path.join(projectRoot, 'frontend/node_modules/lucide-react'),
  '@': path.join(projectRoot, 'frontend/src'),
};

try {
  // 1. T10 Cockpit Real Runner Bundle
  console.log('[1/3] Building cockpit_real_bundle.js from integration source...');
  const res1 = esbuild.buildSync({
    entryPoints: [path.join(__dirname, 'cockpit_real_runner.tsx')],
    bundle: true,
    outfile: path.join(distDir, 'cockpit_real_bundle.js'),
    define: { 'process.env.NODE_ENV': '"production"' },
    alias: {
      ...commonAliases,
      'next/navigation': path.join(__dirname, 'mock_next_navigation.ts'),
    },
  });
  if (res1.errors && res1.errors.length > 0) {
    throw new Error(`Failed to build cockpit_real_bundle.js: ${JSON.stringify(res1.errors)}`);
  }
  console.log('  -> dist/cockpit_real_bundle.js built successfully.');

  // 2. T09 Banner Bundle
  console.log('[2/3] Building banner_bundle.js from integration source...');
  const res2 = esbuild.buildSync({
    entryPoints: [path.join(__dirname, 't09_browser_test', 'banner_entry.tsx')],
    bundle: true,
    outfile: path.join(distDir, 'banner_bundle.js'),
    define: { 'process.env.NODE_ENV': '"production"' },
    alias: commonAliases,
  });
  if (res2.errors && res2.errors.length > 0) {
    throw new Error(`Failed to build banner_bundle.js: ${JSON.stringify(res2.errors)}`);
  }
  console.log('  -> dist/banner_bundle.js built successfully.');

  // 3. T09 Aurora Cockpit Turnover Bundle
  console.log('[3/3] Building aurora_bundle.js from integration source...');
  const res3 = esbuild.buildSync({
    entryPoints: [path.join(__dirname, 't09_browser_test', 'aurora_entry.tsx')],
    bundle: true,
    outfile: path.join(distDir, 'aurora_bundle.js'),
    define: { 'process.env.NODE_ENV': '"production"' },
    alias: {
      ...commonAliases,
      'next/navigation': path.join(__dirname, 'mock_next_navigation.ts'),
      '@/lib/api': path.join(__dirname, 't09_browser_test', 'mock_api.ts'),
    },
  });
  if (res3.errors && res3.errors.length > 0) {
    throw new Error(`Failed to build aurora_bundle.js: ${JSON.stringify(res3.errors)}`);
  }
  console.log('  -> dist/aurora_bundle.js built successfully.');

  console.log('All real browser test bundles successfully built from integration workspace source.');
} catch (error) {
  console.error('Bundle build failed:', error);
  process.exit(1);
}
