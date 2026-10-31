const path = require('path');
const w = require('D:/项目库/AI认知复盘交易系统/frontend/node_modules/next/dist/compiled/webpack/webpack.js');
w.init();
const webpack = w.webpack;

const srcDir = 'C:/Users/siyuw/.gemini/antigravity/worktrees/AI认知复盘交易系统/market_turnover_audit/frontend/src';
const scratchDir = 'C:/Users/siyuw/.gemini/antigravity/brain/2085c03f-289e-4cba-912b-4bdb4eae7d04/scratch/browser_test';

const compiler = webpack({
  mode: 'development',
  devtool: false,
  optimization: {
    minimize: false
  },
  entry: path.join(scratchDir, 'banner_entry.tsx'),
  output: {
    path: scratchDir,
    filename: 'banner_bundle.js'
  },
  resolve: {
    extensions: ['.ts', '.tsx', '.js', '.jsx'],
    alias: {
      '@': srcDir,
    },
    modules: ['D:/项目库/AI认知复盘交易系统/frontend/node_modules']
  },
  module: {
    rules: [
      {
        test: /\.[jt]sx?$/,
        exclude: /node_modules/,
        loader: 'C:/Users/siyuw/.gemini/antigravity/brain/2085c03f-289e-4cba-912b-4bdb4eae7d04/scratch/ts_loader.js'
      }
    ]
  }
});

compiler.run((err, stats) => {
  if (err || stats.hasErrors()) {
    console.error('Error:', err || stats.toJson().errors);
  } else {
    console.log('Banner bundle succeeded in development mode!');
  }
});