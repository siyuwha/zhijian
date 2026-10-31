import React from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { MarketStateBanner } from '@/components/cockpit/MarketStateBanner';

try {
  const mockTurnover: any = {
    two_markets_total_yi: null,
    all_markets_total_yi: null,
    two_markets_quality: 'DEGRADED',
    all_markets_quality: 'PARTIAL',
    sh_amount_yi: 6000.0,
    sz_total_amount_yi: null, // 分项缺失：深市缺失
    chinext_amount_yi: null,
    chinext_ratio_in_sz: null,
    degradation_reason: "历史黄金快照数据源口径待核准，正式总额强制置空为 None"
  };

  const mockIndices: any = [
    { symbol: "sh000001", name: "上证指数", current_price: 3200.0, pct_change: 0.45, amount_yi: 6000.0 },
    { symbol: "sz399001", name: "深证成指", current_price: 10500.0, pct_change: -0.85, amount_yi: 9000.0 }
  ];

  const container = document.getElementById('root');
  if (container) {
    const root = createRoot(container);
    flushSync(() => {
      root.render(
        React.createElement('div', { id: 'test-mounted-wrapper' },
          React.createElement(MarketStateBanner, {
            summary: "指数分化，两市总成交额口径待核准",
            turnover: mockTurnover,
            indices: mockIndices,
            breadthStatus: 'FULL'
          })
        )
      );
    });
    const marker = document.createElement('div');
    marker.id = 'mount-marker';
    marker.innerText = 'CLIENT_MOUNT_DONE';
    document.body.appendChild(marker);
  }
} catch (e: any) {
  const errDiv = document.createElement('div');
  errDiv.id = 'actual-catch-error';
  errDiv.innerText = 'EXCEPTION: ' + e?.message + ' stack: ' + e?.stack;
  document.body.appendChild(errDiv);
}
