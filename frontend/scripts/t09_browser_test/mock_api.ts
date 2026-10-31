export interface CognitionHistoryItem {
  id: string;
  time: string;
  state_label: string;
  score: number;
}

export function getSnapshot() {
  const customTurnover = (typeof window !== 'undefined' && (window as any).__CUSTOM_TURNOVER__ !== undefined)
    ? (window as any).__CUSTOM_TURNOVER__
    : null;

  return {
    date: "2026-10-30",
    timestamp: "2026-10-30T15:00:00",
    truth: {
      turnover: {
        two_markets_total_yi: customTurnover,
        all_markets_total_yi: customTurnover != null ? customTurnover + 50.0 : null,
        two_markets_quality: customTurnover != null ? "FULL" : "DEGRADED",
        all_markets_quality: customTurnover != null ? "FULL" : "PARTIAL",
        sh_amount_yi: 6000.0,
        sz_total_amount_yi: customTurnover != null ? 12500.0 : null,
        chinext_slice_amount_yi: 3000.0,
        chinext_ratio_in_sz: 0.24,
        degradation_reason: customTurnover != null ? null : "历史黄金快照数据源口径待核准，正式总额强制置空为 None"
      },
      indices: [
        { symbol: "sh000001", code: "000001", name: "上证指数", current_price: 3200.0, pct_change: 0.45, amount_yi: 6000.0 },
        { symbol: "sz399001", code: "399001", name: "深证成指", current_price: 10500.0, pct_change: -0.85, amount_yi: customTurnover != null ? 12500.0 : null }
      ],
      sentiment_bounds: {
        limit_up_count: 35,
        broken_limit_count: 8,
        limit_down_count: 2,
        touched_limit_total_count: 43
      },
      ladder_tree: [],
      cross_section_breadth_detail: {
        up_count: 2800,
        down_count: 2000,
        flat_count: 500
      }
    },
    cognition: {
      market_state_label: "分化震荡",
      market_state_summary: customTurnover != null ? "指数平稳，两市成交额已核准" : "指数分化，两市总成交额口径待核准",
      space_leader_symbol: "无连板梯队（数据缺失）"
    },
    environment: {}
  };
}

export const mockTimelineResponse = {
  trade_date: "2026-10-30",
  current_active_stage: "afternoon_close",
  stages: [
    {
      stage: "afternoon_close",
      stage_label: "尾盘博弈",
      status_badge: "收盘总评",
      status_color: "bg-indigo-500/20 text-indigo-300 border-indigo-500/30",
      timing: "采集研判时效: 15:00:00",
      confidence: "置信度 92%",
      strong_weak_judgment: "【盘面强弱】多空震荡分化",
      resonance_attribution: "【共振归因】高位分歧",
      action_inference: "【推演动作】防守观望",
      falsification_criteria: "【证伪线】两市放量",
      content_html: "<p>内参正文</p>",
      quantitative_indicators: {
        projected_volume: "2.50万亿", // 注入旧内参预测值
        breadth_divergence: "多头占优",
        space_height: "最高8B",
        action_advice: "控制仓位"
      },
      evaluated_at: "2026-10-30T15:00:00",
      trade_date: "2026-10-30",
      trace_id: "trace_mock_001",
      fingerprint: "fp_mock_001"
    }
  ]
};

const canonicalAPIBase: any = {
  getInstantSnapshot: async () => ({ snapshot: getSnapshot() }),
  getCanonicalMarketSnapshot: async () => getSnapshot(),
  getTacticalBriefing: async () => ({
    date: "2026-10-30",
    core_summary: "量能口径测试",
    quantitative_indicators: {
      projected_volume: "2.50万亿"
    }
  }),
  getAuctionFalsification: async () => ({ verdict: "NORMAL", details: {} }),
  getIntradayDrift: async () => ({ verdict: "NORMAL", details: {} }),
  getIntradayBriefings: async () => mockTimelineResponse,
  getTopSectorsTrend: async () => ({ sectors: [] }),
  getIntradayGameCognition: async () => ({ status: 'ok', decisions: [] }),
  getIntradayGameCognitionHistory: async () => ({ history: [] }),
  getLimitUpPool: async () => ({ total_count: 35, broken_limit_count: 8, limit_down_count: 2, items: [] })
};

const apiBase: any = {
  getCognitionHistory: async () => [],
  getCognitionReplay: async () => ({}),
  getStockTrends: async () => ({ trends: [] }),
  getLimitUpPool: async () => ({ total_count: 35, broken_limit_count: 8, limit_down_count: 2, items: [] }),
  getSectors: async () => []
};

const proxyHandler = {
  get: (target: any, prop: string) => {
    if (prop in target) return target[prop];
    return async () => ({});
  }
};

export const canonicalAPI = new Proxy(canonicalAPIBase, proxyHandler);
export const api = new Proxy(apiBase, proxyHandler);
