import React from 'react';
import { createRoot } from 'react-dom/client';
import { AuroraCockpitView } from '../src/components/cockpit/AuroraCockpitView';

// 解析当前测试场景参数
const urlParams = new URLSearchParams(window.location.search);
const SCENARIO = (window as any).__TEST_SCENARIO__ || urlParams.get('scenario') || 'scenario_realtime_measured';

// 测试日志与状态收集器
(window as any).__REAL_TEST_LOGS__ = [];
(window as any).__SCENARIO_DONE__ = false;
(window as any).__TEST_RESULTS__ = {
  scenario: SCENARIO,
  snapshots: [] as any[],
  errors: [] as string[],
};

function log(msg: string) {
  console.log(`[CockpitRealRunner] ${msg}`);
  (window as any).__REAL_TEST_LOGS__.push(msg);
}

// 模拟行情走势点位 (09:30 - 10:30 有效交易时间，包含严格的 pct_change 浮点数)
function generateMockTrends(basePrice: number) {
  const points = [];
  let p = basePrice;
  for (let m = 30; m <= 59; m++) {
    p += (Math.random() - 0.48) * 0.05;
    const pct = parseFloat((((p - basePrice) / basePrice) * 100).toFixed(2));
    points.push({
      time: `09:${m}`,
      price: parseFloat(p.toFixed(2)),
      pct_change: pct,
      volume: 1000 + m * 20,
      turnover: 10000 + m * 200,
    });
  }
  for (let m = 0; m <= 30; m++) {
    const mm = m < 10 ? `0${m}` : `${m}`;
    p += (Math.random() - 0.48) * 0.05;
    const pct = parseFloat((((p - basePrice) / basePrice) * 100).toFixed(2));
    points.push({
      time: `10:${mm}`,
      price: parseFloat(p.toFixed(2)),
      pct_change: pct,
      volume: 2000 + m * 20,
      turnover: 20000 + m * 200,
    });
  }
  return points;
}

// 真实拦截 window.fetch，为 AuroraCockpitView 提供严格的契约报文
let stockTrendsFetchCount = 0;
let topSectorsTrendFetchCount = 0;
const originalFetch = window.fetch;

window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const urlStr = typeof input === 'string' ? input : input instanceof URL ? input.toString() : (input as Request).url;
  log(`Intercepted fetch: ${urlStr}`);

  // 1. 涨停池接口
  if (urlStr.includes('/market/limit-up')) {
    const payload = {
      trade_date: '2026-10-31',
      items: [
        {
          code: '002696',
          name: '百洋股份',
          zdp: 10.02,
          amount_yi: 6.8,
          lbc: 4,
          continuous_board_count: 4,
          ltsz_yi: 45.0,
          turnover_ratio: 15.2,
          sector: '低空经济',
        },
        {
          code: '600519',
          name: '贵州茅台',
          zdp: 2.1,
          amount_yi: 45.0,
          lbc: 1,
          continuous_board_count: 1,
          ltsz_yi: 20000.0,
          turnover_ratio: 1.2,
          sector: '白酒',
        },
      ],
    };
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // 1.5 顶级板块分时资金争夺接口 (/canonical/intraday-top-sectors-trend)
  if (urlStr.includes('/canonical/intraday-top-sectors-trend')) {
    if (SCENARIO === 'scenario_unavailable_fault') {
      const payload = {
        trade_date: '2026-10-31',
        snapshot_time: '10:30:00',
        quality: 'UNAVAILABLE',
        freshness: 'UNAVAILABLE',
        status: 'UNAVAILABLE',
        error_code: 'TIMEOUT',
        degradation_reason: '板块资金流物理源超时无响应 (已安全降级)',
        source_timestamp: null,
        sectors: [],
      };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (SCENARIO === 'scenario_unknown_freshness_recovery') {
      topSectorsTrendFetchCount++;
      log(`Handling /canonical/intraday-top-sectors-trend (count: ${topSectorsTrendFetchCount}) for scenario_unknown_freshness_recovery`);
      if (topSectorsTrendFetchCount === 1) {
        // 在虚拟时间 3 秒后触发真实刷新按钮点击，模拟数据恢复
        setTimeout(() => {
          log('Scenario 10: Triggering refresh click to recover from unknown freshness');
          const btn = document.querySelector('[data-testid="cockpit-refresh-btn"]') as HTMLButtonElement | null;
          if (btn) btn.click();
        }, 3000);

        const payload = {
          trade_date: '2026-10-31',
          snapshot_time: '10:30:00',
          quality: 'DEGRADED',
          freshness: 'UNAVAILABLE',
          status: 'AVAILABLE',
          sector_quality: 'DEGRADED',
          sector_freshness: 'UNAVAILABLE',
          trends_quality: 'FULL',
          trends_freshness: 'REALTIME',
          source_timestamp: null,
          degradation_reason: '板块排行时效未知或不可用',
          is_estimated: false,
          sectors: [
            {
              name: '低空经济',
              current_net_inflow_yi: 18.5,
              current_pct_change: 3.4,
              color: '#8B5CF6',
              leader: { code: '002696', name: '百洋股份', pct_change: 10.02, status_desc: '4B 连板' },
              trends: [
                { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
                { time: '09:45', net_inflow_yi: 10.2, pct_change: 1.8 },
                { time: '10:00', net_inflow_yi: 18.5, pct_change: 3.4 },
              ],
            },
            {
              name: '半导体',
              current_net_inflow_yi: 12.2,
              current_pct_change: 2.1,
              color: '#06B6D4',
              leader: { code: '600519', name: '贵州茅台', pct_change: 2.1, status_desc: '中军核心' },
              trends: [
                { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
                { time: '09:45', net_inflow_yi: 6.5, pct_change: 1.2 },
                { time: '10:00', net_inflow_yi: 12.2, pct_change: 2.1 },
              ],
            },
          ],
        };
        return new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      // 恢复后正常数据 (topSectorsTrendFetchCount >= 2)
      const payload = {
        trade_date: '2026-10-31',
        snapshot_time: '10:30:00',
        quality: 'FULL',
        freshness: 'REALTIME',
        status: 'AVAILABLE',
        sector_quality: 'FULL',
        sector_freshness: 'REALTIME',
        trends_quality: 'FULL',
        trends_freshness: 'REALTIME',
        source_timestamp: '2026-10-31 10:30:00',
        degradation_reason: null,
        is_estimated: false,
        sectors: [
          {
            name: '低空经济',
            current_net_inflow_yi: 18.5,
            current_pct_change: 3.4,
            color: '#8B5CF6',
            leader: { code: '002696', name: '百洋股份', pct_change: 10.02, status_desc: '4B 连板' },
            trends: [
              { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
              { time: '09:45', net_inflow_yi: 10.2, pct_change: 1.8 },
              { time: '10:00', net_inflow_yi: 18.5, pct_change: 3.4 },
            ],
          },
          {
            name: '半导体',
            current_net_inflow_yi: 12.2,
            current_pct_change: 2.1,
            color: '#06B6D4',
            leader: { code: '600519', name: '贵州茅台', pct_change: 2.1, status_desc: '中军核心' },
            trends: [
              { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
              { time: '09:45', net_inflow_yi: 6.5, pct_change: 1.2 },
              { time: '10:00', net_inflow_yi: 12.2, pct_change: 2.1 },
            ],
          },
        ],
      };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (SCENARIO === 'scenario_unknown_freshness_masked_by_reason_recovery') {
      topSectorsTrendFetchCount++;
      log(`Handling /canonical/intraday-top-sectors-trend (count: ${topSectorsTrendFetchCount}) for scenario_unknown_freshness_masked_by_reason_recovery`);
      if (topSectorsTrendFetchCount === 1) {
        // 在虚拟时间 3 秒后触发真实刷新按钮点击，模拟数据恢复
        setTimeout(() => {
          log('Scenario 11: Triggering refresh click to recover from unknown freshness masked by other reason');
          const btn = document.querySelector('[data-testid="cockpit-refresh-btn"]') as HTMLButtonElement | null;
          if (btn) btn.click();
        }, 3000);

        // 真实后端路径：排行时效为 UNAVAILABLE 且分时缺失时，degradation_reason 为“板块分时走势缺失，仅提供静态排行”
        const payload = {
          trade_date: '2026-10-31',
          snapshot_time: '10:30:00',
          quality: 'DEGRADED',
          freshness: 'UNAVAILABLE',
          status: 'AVAILABLE',
          sector_quality: 'DEGRADED',
          sector_freshness: 'UNAVAILABLE',
          trends_quality: 'UNAVAILABLE',
          trends_freshness: 'UNAVAILABLE',
          source_timestamp: null,
          degradation_reason: '板块分时走势缺失，仅提供静态排行',
          is_estimated: false,
          sectors: [
            {
              name: '低空经济',
              current_net_inflow_yi: 18.5,
              current_pct_change: 3.4,
              color: '#8B5CF6',
              leader: { code: '002696', name: '百洋股份', pct_change: 10.02, status_desc: '4B 连板' },
              trends: [],
            },
            {
              name: '半导体',
              current_net_inflow_yi: 12.2,
              current_pct_change: 2.1,
              color: '#06B6D4',
              leader: { code: '600519', name: '贵州茅台', pct_change: 2.1, status_desc: '中军核心' },
              trends: [],
            },
          ],
        };
        return new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      // 恢复后正常数据 (topSectorsTrendFetchCount >= 2)
      const payload = {
        trade_date: '2026-10-31',
        snapshot_time: '10:30:00',
        quality: 'FULL',
        freshness: 'REALTIME',
        status: 'AVAILABLE',
        sector_quality: 'FULL',
        sector_freshness: 'REALTIME',
        trends_quality: 'FULL',
        trends_freshness: 'REALTIME',
        source_timestamp: '2026-10-31 10:30:00',
        degradation_reason: null,
        is_estimated: false,
        sectors: [
          {
            name: '低空经济',
            current_net_inflow_yi: 18.5,
            current_pct_change: 3.4,
            color: '#8B5CF6',
            leader: { code: '002696', name: '百洋股份', pct_change: 10.02, status_desc: '4B 连板' },
            trends: [
              { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
              { time: '09:45', net_inflow_yi: 10.2, pct_change: 1.8 },
              { time: '10:00', net_inflow_yi: 18.5, pct_change: 3.4 },
            ],
          },
          {
            name: '半导体',
            current_net_inflow_yi: 12.2,
            current_pct_change: 2.1,
            color: '#06B6D4',
            leader: { code: '600519', name: '贵州茅台', pct_change: 2.1, status_desc: '中军核心' },
            trends: [
              { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
              { time: '09:45', net_inflow_yi: 6.5, pct_change: 1.2 },
              { time: '10:00', net_inflow_yi: 12.2, pct_change: 2.1 },
            ],
          },
        ],
      };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (SCENARIO === 'scenario_market_sectors_alone_delayed') {
      // 场景 8: 独立验证 /market/sectors 质量链：Canonical 接口异常，页面降级消费 market/sectors
      return new Response(JSON.stringify({ detail: 'canonical endpoint unavailable (fallback to market sectors)' }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (SCENARIO === 'scenario_dual_stale_and_delayed') {
      // 场景 9: 排行 STALE 与分时 DELAYED 并存：双标签同时呈现，且单侧时间不伪装整体截止
      const payload = {
        trade_date: '2026-10-31',
        snapshot_time: '10:15:00',
        quality: 'DEGRADED',
        freshness: 'STALE',
        status: 'STALE',
        sector_quality: 'DEGRADED',
        sector_freshness: 'STALE',
        sector_source_timestamp: '2026-10-31 10:15:00',
        trends_quality: 'DEGRADED',
        trends_freshness: 'DELAYED',
        trends_source_timestamp: null,
        source_timestamp: null, // 整体截止未知，绝不冒充
        degradation_reason: '板块排行使用缓存快照，分时行情延迟',
        is_estimated: false,
        sectors: [
          {
            name: '低空经济',
            current_net_inflow_yi: 18.5,
            current_pct_change: 3.4,
            color: '#8B5CF6',
            leader: { code: '002696', name: '百洋股份', pct_change: 10.02, status_desc: '4B 连板' },
            trends: [
              { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
              { time: '09:45', net_inflow_yi: 10.2, pct_change: 1.8 },
              { time: '10:00', net_inflow_yi: 18.5, pct_change: 3.4 },
            ],
          },
        ],
      };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (SCENARIO === 'scenario_reverse_dual_delayed_and_stale') {
      // 反向场景: 排行 DELAYED 与分时 STALE 并存：双标签同时呈现，单侧时间明确归因于分时
      const payload = {
        trade_date: '2026-10-31',
        snapshot_time: '10:25:00',
        quality: 'DEGRADED',
        freshness: 'STALE',
        status: 'STALE',
        sector_quality: 'DEGRADED',
        sector_freshness: 'DELAYED',
        sector_source_timestamp: '2026-10-31 10:25:00',
        trends_quality: 'DEGRADED',
        trends_freshness: 'STALE',
        trends_source_timestamp: '2026-10-31 10:20:00',
        source_timestamp: null, // 整体截止未知，绝不冒充
        degradation_reason: '板块排行行情延迟，分时使用缓存快照',
        is_estimated: false,
        sectors: [
          {
            name: '低空经济',
            current_net_inflow_yi: 18.5,
            current_pct_change: 3.4,
            color: '#8B5CF6',
            leader: { code: '002696', name: '百洋股份', pct_change: 10.02, status_desc: '4B 连板' },
            trends: [
              { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
              { time: '09:45', net_inflow_yi: 10.2, pct_change: 1.8 },
              { time: '10:00', net_inflow_yi: 18.5, pct_change: 3.4 },
            ],
          },
        ],
      };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (SCENARIO === 'scenario_delayed_freshness') {
      const payload = {
        trade_date: '2026-10-31',
        snapshot_time: '10:15:00',
        quality: 'DEGRADED',
        sector_quality: 'DEGRADED',
        sector_freshness: 'DELAYED',
        sector_source_timestamp: '2026-10-31 10:15:00',
        trends_quality: 'DEGRADED',
        trends_freshness: 'DELAYED',
        trends_source_timestamp: '2026-10-31 10:15:00',
        freshness: 'DELAYED',
        status: 'AVAILABLE',
        source_timestamp: '2026-10-31 10:15:00',
        degradation_reason: '板块排行行情延迟',
        is_estimated: false,
        sectors: [
          {
            name: '低空经济',
            current_net_inflow_yi: 18.5,
            current_pct_change: 3.4,
            color: '#8B5CF6',
            leader: { code: '002696', name: '百洋股份', pct_change: 10.02, status_desc: '4B 连板' },
            trends: [
              { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
              { time: '09:45', net_inflow_yi: 10.2, pct_change: 1.8 },
              { time: '10:00', net_inflow_yi: 18.5, pct_change: 3.4 },
            ],
          },
          {
            name: '半导体',
            current_net_inflow_yi: 12.2,
            current_pct_change: 2.1,
            color: '#06B6D4',
            leader: { code: '600519', name: '贵州茅台', pct_change: 2.1, status_desc: '中军核心' },
            trends: [
              { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
              { time: '09:45', net_inflow_yi: 6.5, pct_change: 1.2 },
              { time: '10:00', net_inflow_yi: 12.2, pct_change: 2.1 },
            ],
          },
        ],
      };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (SCENARIO === 'scenario_stale_tolerance') {
      const payload = {
        trade_date: '2026-10-31',
        snapshot_time: '10:15:00',
        quality: 'DEGRADED',
        freshness: 'STALE',
        status: 'STALE',
        source_timestamp: '2026-10-31 10:15:00',
        degradation_reason: '主备数据源均不可用，提供 STALE 缓存快照',
        is_estimated: false,
        sectors: [
          {
            name: '低空经济',
            current_net_inflow_yi: 18.5,
            current_pct_change: 3.4,
            color: '#8B5CF6',
            leader: { code: '002696', name: '百洋股份', pct_change: 10.02, status_desc: '4B 连板' },
            trends: [
              { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
              { time: '09:45', net_inflow_yi: 10.2, pct_change: 1.8 },
              { time: '10:00', net_inflow_yi: 18.5, pct_change: 3.4 },
            ],
          },
          {
            name: '半导体',
            current_net_inflow_yi: 12.2,
            current_pct_change: 2.1,
            color: '#06B6D4',
            leader: { code: '600519', name: '贵州茅台', pct_change: 2.1, status_desc: '中军核心' },
            trends: [
              { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
              { time: '09:45', net_inflow_yi: 6.5, pct_change: 1.2 },
              { time: '10:00', net_inflow_yi: 12.2, pct_change: 2.1 },
            ],
          },
        ],
      };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    const isEstimated = SCENARIO === 'scenario_estimated_flow';
    const payload = {
      trade_date: '2026-10-31',
      snapshot_time: '10:30:00',
      quality: 'FULL',
      freshness: 'REALTIME',
      status: 'AVAILABLE',
      source_timestamp: '2026-10-31 10:30:00',
      is_estimated: isEstimated,
      sectors: [
        {
          name: '低空经济',
          current_net_inflow_yi: 25.8,
          current_pct_change: 4.5,
          color: '#8B5CF6',
          leader: { code: '002696', name: '百洋股份', pct_change: 10.02, status_desc: '4B 连板' },
          trends: [
            { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
            { time: '09:45', net_inflow_yi: 14.2, pct_change: 2.5 },
            { time: '10:00', net_inflow_yi: 25.8, pct_change: 4.5 },
          ],
        },
        {
          name: '华为昇腾',
          current_net_inflow_yi: 19.3,
          current_pct_change: 3.2,
          color: '#06B6D4',
          leader: { code: '600519', name: '贵州茅台', pct_change: 2.1, status_desc: '中军核心' },
          trends: [
            { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
            { time: '09:45', net_inflow_yi: 9.8, pct_change: 1.6 },
            { time: '10:00', net_inflow_yi: 19.3, pct_change: 3.2 },
          ],
        },
        {
          name: '人形机器人',
          current_net_inflow_yi: 14.1,
          current_pct_change: 2.8,
          color: '#F59E0B',
          leader: { code: '000001', name: '平安银行', pct_change: 1.5, status_desc: '趋势助攻' },
          trends: [
            { time: '09:30', net_inflow_yi: 0.0, pct_change: 0.0 },
            { time: '09:45', net_inflow_yi: 7.0, pct_change: 1.4 },
            { time: '10:00', net_inflow_yi: 14.1, pct_change: 2.8 },
          ],
        },
      ],
    };
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // 2. 板块资金流接口 (/market/sectors)
  if (urlStr.includes('/market/sectors')) {
    if (SCENARIO === 'scenario_market_sectors_alone_delayed') {
      const payload = {
        data: [
          { name: '低空经济', net: 18.5, change_pct: 3.4, heat: 92 },
          { name: '半导体', net: 12.2, change_pct: 2.1, heat: 85 },
        ],
        quality: 'DEGRADED',
        freshness: 'DELAYED',
        status: 'AVAILABLE',
        source_timestamp: '2026-10-31 10:15:00',
        trade_date: '2026-10-31',
        degradation_reason: '板块排行行情延迟',
        is_estimated: false,
      };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (SCENARIO === 'scenario_delayed_freshness') {
      const payload = {
        data: [
          { name: '低空经济', net: 18.5, change_pct: 3.4, heat: 92 },
          { name: '半导体', net: 12.2, change_pct: 2.1, heat: 85 },
        ],
        quality: 'DEGRADED',
        freshness: 'DELAYED',
        status: 'AVAILABLE',
        source_timestamp: '2026-10-31 10:15:00',
        trade_date: '2026-10-31',
        degradation_reason: '板块排行行情延迟',
        is_estimated: false,
      };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (SCENARIO === 'scenario_unavailable_fault') {
      const payload = {
        data: [],
        quality: 'UNAVAILABLE',
        freshness: 'UNAVAILABLE',
        status: 'EMPTY',
        error_code: 'TIMEOUT',
        degradation_reason: '物理数据源超时无响应 (已安全降级)',
        source_timestamp: null,
        trade_date: '2026-10-31',
      };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (SCENARIO === 'scenario_stale_tolerance') {
      const payload = {
        data: [
          { name: '低空经济', net: 18.5, change_pct: 3.4, heat: 92 },
          { name: '半导体', net: 12.2, change_pct: 2.1, heat: 85 },
          { name: '算力租赁', net: 8.7, change_pct: 1.8, heat: 78 },
        ],
        quality: 'DEGRADED',
        freshness: 'STALE',
        status: 'STALE',
        source_timestamp: '2026-10-31 10:15:00',
        trade_date: '2026-10-31',
        degradation_reason: '主备数据源均不可用，提供 STALE 缓存快照',
        is_estimated: false,
      };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    // 默认或 scenario_estimated_flow / scenario_realtime_measured
    const isEstimated = SCENARIO === 'scenario_estimated_flow';
    const payload = {
      data: [
        { name: '低空经济', net: 25.8, change_pct: 4.5, heat: 96 },
        { name: '华为昇腾', net: 19.3, change_pct: 3.2, heat: 89 },
        { name: '人形机器人', net: 14.1, change_pct: 2.8, heat: 82 },
      ],
      quality: 'FULL',
      freshness: 'REALTIME',
      status: 'AVAILABLE',
      source_timestamp: '2026-10-31 10:30:00',
      trade_date: '2026-10-31',
      is_estimated: isEstimated,
    };
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // 3. 个股分时走势接口 (/market/stock-trends)
  if (urlStr.includes('/market/stock-trends')) {
    stockTrendsFetchCount++;
    log(`Handling /market/stock-trends (count: ${stockTrendsFetchCount}) for scenario: ${SCENARIO}`);

    if (SCENARIO === 'scenario_unavailable_fault') {
      const payload = {
        data: [],
        quality: 'UNAVAILABLE',
        freshness: 'UNAVAILABLE',
        status: 'EMPTY',
        error_code: 'TIMEOUT',
        degradation_reason: '分时走势物理源超时',
      };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    updateDebugMetrics();

    if (SCENARIO === 'scenario_delayed_freshness') {
      updateDebugMetrics();
      const payload = {
        data: [
          {
            code: '002696',
            name: '百洋股份',
            pre_close: 11.18,
            trends: generateMockTrends(11.18),
            is_real: true,
            quality: 'FULL',
            freshness: 'DELAYED',
          },
          {
            code: '600519',
            name: '贵州茅台',
            pre_close: 1616.0,
            trends: generateMockTrends(1616.0),
            is_real: true,
            quality: 'FULL',
            freshness: 'DELAYED',
          },
        ],
        quality: 'DEGRADED',
        freshness: 'DELAYED',
        status: 'AVAILABLE',
        source_timestamp: '2026-10-31 10:15:00',
        degradation_reason: '分时行情延迟',
      };
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (SCENARIO === 'scenario_out_of_order_defense') {
      // 场景 6: A10 逆序时序防线 (较新成功先到，较旧失败迟到)
      if (stockTrendsFetchCount === 1) {
        log('Scenario 6: Emulating Request 1 for 2026-10-30 - holding response');
        (window as any).__req1Held = true;
        updateDebugMetrics();

        // 300ms 后切换交易日至 2026-10-31，触发较新的 Request 2
        setTimeout(() => {
          log('Scenario 6: Triggering Date switch to 2026-10-31');
          if ((window as any).__switchDate) {
            (window as any).__switchDate('2026-10-31');
          }
        }, 300);

        // 返回可控 Promise，并在 1000ms 后以迟到的 UNAVAILABLE 失败响应解决
        return new Promise<Response>((resolve) => {
          setTimeout(() => {
            log('Scenario 6: Emulating Late Arrival of Request 1 (Date 2026-10-30) -> UNAVAILABLE Failure');
            (window as any).__req1LateResolved = true;
            updateDebugMetrics();
            const latePayload = {
              data: [],
              quality: 'UNAVAILABLE',
              freshness: 'UNAVAILABLE',
              status: 'EMPTY',
              error_code: 'TIMEOUT',
              degradation_reason: '历史日期分时超时',
            };
            resolve(new Response(JSON.stringify(latePayload), {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            }));
          }, 1000);
        });
      } else {
        log('Scenario 6: Handling Newer Request 2 for 2026-10-31 - resolving immediately with FULL');
        (window as any).__req2Resolved = true;
        updateDebugMetrics();
        const payload2 = {
          data: [
            {
              code: '002696',
              name: '百洋股份',
              pre_close: 11.18,
              trends: generateMockTrends(11.18),
              is_real: true,
              quality: 'FULL',
              freshness: 'REALTIME',
            },
            {
              code: '600519',
              name: '贵州茅台',
              pre_close: 1616.0,
              trends: generateMockTrends(1616.0),
              is_real: true,
              quality: 'FULL',
              freshness: 'REALTIME',
            },
          ],
          quality: 'FULL',
          freshness: 'REALTIME',
          status: 'AVAILABLE',
          source_timestamp: '2026-10-31 10:30:00',
        };
        return new Response(JSON.stringify(payload2), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
    }

    if (SCENARIO === 'scenario_retry_recovery') {
      // 场景 5: 首次请求硬失败 UNAVAILABLE，触发真实 8s 重试；第 2 次重试请求恢复 FULL
      if (stockTrendsFetchCount === 1) {
        log('Scenario 5: Emulating First Fetch Hard Fault -> UNAVAILABLE');
        updateDebugMetrics();
        const payload = {
          data: [],
          quality: 'UNAVAILABLE',
          freshness: 'UNAVAILABLE',
          status: 'EMPTY',
          error_code: 'TIMEOUT',
          degradation_reason: '分时服务暂时不可用，等待自动重试',
        };
        return new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      } else {
        log('Scenario 5: Emulating Retry Recovery Fetch -> FULL Realtime');
        updateDebugMetrics();
        const payload = {
          data: [
            {
              code: '002696',
              name: '百洋股份',
              pre_close: 11.18,
              trends: generateMockTrends(11.18),
              is_real: true,
              quality: 'FULL',
              freshness: 'REALTIME',
            },
            {
              code: '600519',
              name: '贵州茅台',
              pre_close: 1616.0,
              trends: generateMockTrends(1616.0),
              is_real: true,
              quality: 'FULL',
              freshness: 'REALTIME',
            },
          ],
          quality: 'FULL',
          freshness: 'REALTIME',
          status: 'AVAILABLE',
          source_timestamp: '2026-10-31 10:30:08',
        };
        return new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
    }

    // 正常返回
    const payload = {
      data: [
        {
          code: '002696',
          name: '百洋股份',
          pre_close: 11.18,
          trends: generateMockTrends(11.18),
          is_real: true,
          quality: 'FULL',
          freshness: 'REALTIME',
        },
        {
          code: '600519',
          name: '贵州茅台',
          pre_close: 1616.0,
          trends: generateMockTrends(1616.0),
          is_real: true,
          quality: 'FULL',
          freshness: 'REALTIME',
        },
      ],
      quality: 'FULL',
      freshness: 'REALTIME',
      status: 'AVAILABLE',
      source_timestamp: '2026-10-31 10:30:00',
    };
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // 其他兜底空响应
  return new Response(JSON.stringify({ data: null }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
};

function updateDebugMetrics() {
  const dbg = document.getElementById('debug');
  if (dbg) {
    dbg.setAttribute('data-stock-fetch-count', String(stockTrendsFetchCount));
    dbg.setAttribute('data-req1-held', String(!!(window as any).__req1Held));
    dbg.setAttribute('data-req1-late-resolved', String(!!(window as any).__req1LateResolved));
    dbg.setAttribute('data-req2-resolved', String(!!(window as any).__req2Resolved));
  }
}

// 可控日期调度 Harness，确保在同一 React 组件挂载生命周期内执行交易日切换
function CockpitHarness() {
  const [currentDate, setCurrentDate] = React.useState(
    SCENARIO === 'scenario_out_of_order_defense' ? '2026-10-30' : '2026-10-31'
  );

  React.useEffect(() => {
    (window as any).__switchDate = (newDate: string) => {
      log(`[CockpitHarness] Dynamic date switch to ${newDate}`);
      setCurrentDate(newDate);
    };
  }, []);

  return React.createElement(AuroraCockpitView, { initialDate: currentDate });
}

// 挂载真实 React 19 组件
const container = document.getElementById('root');
if (!container) {
  throw new Error('Root container #root not found in document!');
}

const root = createRoot(container);
root.render(React.createElement(CockpitHarness));
log('AuroraCockpitView mounted via CockpitHarness to real DOM.');
setTimeout(updateDebugMetrics, 100);

// 自动模拟鼠标悬停以激活悬停浮窗
setTimeout(() => {
  const chartEl = document.querySelector('[data-testid="sector-chart-container"]');
  if (chartEl) {
    chartEl.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: 250, clientY: 100 }));
    log('Simulated mousemove hover on sector-chart-container.');
  }
}, 600);

// 暴露 DOM 快照记录函数供无头 Chrome 收集
(window as any).__recordSnapshot = (label: string) => {
  const estBadge = document.querySelector('[data-testid="sector-estimated-badge"]');
  const estLegend = document.querySelector('[data-testid="sector-estimated-legend"]');
  const staleBadge = document.querySelector('[data-testid="sector-stale-badge"]');
  const unavailBadge = document.querySelector('[data-testid="sector-unavailable-badge"]');
  const stockUnavailBadge = document.querySelector('[data-testid="stock-trends-unavailable-badge"]');
  const stockStaleBadge = document.querySelector('[data-testid="stock-trends-stale-badge"]');
  const stockPartialBadge = document.querySelector('[data-testid="stock-trends-partial-badge"]');

  const snapshot = {
    label,
    time: Date.now(),
    hasEstBadge: !!estBadge,
    estBadgeText: estBadge?.textContent?.trim() || null,
    hasEstLegend: !!estLegend,
    hasStaleBadge: !!staleBadge,
    staleBadgeText: staleBadge?.textContent?.trim() || null,
    hasUnavailBadge: !!unavailBadge,
    unavailBadgeText: unavailBadge?.textContent?.trim() || null,
    hasStockUnavailBadge: !!stockUnavailBadge,
    stockUnavailBadgeText: stockUnavailBadge?.textContent?.trim() || null,
    hasStockStaleBadge: !!stockStaleBadge,
    stockStaleBadgeText: stockStaleBadge?.textContent?.trim() || null,
    hasStockPartialBadge: !!stockPartialBadge,
    stockTrendsFetchCount,
  };
  (window as any).__TEST_RESULTS__.snapshots.push(snapshot);
  log(`Recorded snapshot: ${label} -> ${JSON.stringify(snapshot)}`);
  return snapshot;
};
