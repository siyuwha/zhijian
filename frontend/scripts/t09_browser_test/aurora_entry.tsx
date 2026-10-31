import React from 'react';
import { createRoot } from 'react-dom/client';
import { AuroraCockpitView } from '@/components/cockpit/AuroraCockpitView';

try {
  const container = document.getElementById('root');
  if (container) {
    const root = createRoot(container);
    root.render(
      React.createElement('div', { id: 'aurora-test-wrapper' },
        React.createElement(AuroraCockpitView, { initialDate: "2026-10-30" })
      )
    );

    // 等待异步数据加载与 React 重新渲染完成
    const checkInterval = setInterval(() => {
      // 检查是否已渲染出成交额区域或待核准文本
      const text = container.innerText || '';
      if (text.includes('口径待核准') || text.includes('实盘累计成交') || text.includes('时间衰减')) {
        clearInterval(checkInterval);
        const marker = document.createElement('div');
        marker.id = 'mount-marker';
        marker.innerText = 'AURORA_CLIENT_MOUNT_DONE';
        document.body.appendChild(marker);
      }
    }, 100);

    // 最大超时保护 3 秒
    setTimeout(() => {
      clearInterval(checkInterval);
      if (!document.getElementById('mount-marker')) {
        const marker = document.createElement('div');
        marker.id = 'mount-marker';
        marker.innerText = 'AURORA_CLIENT_MOUNT_TIMEOUT';
        document.body.appendChild(marker);
      }
    }, 3000);
  }
} catch (e: any) {
  const errDiv = document.createElement('div');
  errDiv.id = 'actual-catch-error';
  errDiv.innerText = 'EXCEPTION: ' + e.message + ' stack: ' + e.stack;
  document.body.appendChild(errDiv);
}
