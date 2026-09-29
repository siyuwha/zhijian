import { execSync } from 'child_process';

let gitCommit = 'e26031b';
try {
  gitCommit = execSync('git rev-parse --short HEAD', { stdio: ['ignore', 'pipe', 'ignore'] })
    .toString()
    .trim();
} catch (e) {
  try {
    gitCommit = execSync('git -C .. rev-parse --short HEAD', { stdio: ['ignore', 'pipe', 'ignore'] })
      .toString()
      .trim();
  } catch (err) {
    // Keep fallback commit
  }
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    NEXT_PUBLIC_GIT_COMMIT: gitCommit,
    NEXT_PUBLIC_BUILD_DATE: new Date().toISOString().slice(0, 10),
  },
};

export default nextConfig;
