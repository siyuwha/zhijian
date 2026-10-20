import { ApiResponse } from '@/types/common';
import { 
  DailyReviewSummaryItem, 
  DailyReviewDetail, 
  PremarketBriefingDetail,
  PremarketBriefingSummaryItem,
  AuctionReportDetail,
  AuctionReportSummaryItem
} from '@/types/report';
import { 
  MonitorRealtimeResponse,
  MacroSnapshotItem,
  IntradayAnomalyEventItem
} from '@/types/monitor';
import { IndexData } from '@/types/market';
import { EnrichedLimitUpPoolData, SectorFlowItem } from '@/types/canonical';

const BACKEND_HOST = process.env.NEXT_PUBLIC_API_URL || 
  (typeof window !== 'undefined' ? `${window.location.protocol}//${window.location.hostname}:8000` : 'http://localhost:8000');
const BASE_URL = `${BACKEND_HOST}/api/v1`;

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = endpoint.startsWith('http') 
    ? endpoint 
    : endpoint.startsWith('/health')
    ? `${BACKEND_HOST}${endpoint}`
    : `${BASE_URL}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let errorDetail = '';
    try {
      const errJson = await response.json();
      if (errJson) {
        errorDetail = errJson.detail || errJson.message || '';
        if (typeof errorDetail === 'object') {
          errorDetail = JSON.stringify(errorDetail);
        }
      }
    } catch {
      // fallback
    }
    if (!errorDetail || errorDetail === response.statusText) {
      if (response.status === 400) {
        errorDetail = `请求参数有误或触发交易日防线拦截 (400 Bad Request)`;
      } else if (response.status === 404) {
        errorDetail = `未找到对应数据 (404 Not Found)`;
      } else if (response.status === 500) {
        errorDetail = `后端服务内部错误 (500 Internal Server Error)`;
      } else {
        errorDetail = `请求失败 (${response.status}: ${response.statusText || '未知错误'})`;
      }
    }
    throw new Error(errorDetail);
  }

  const data: any = await response.json();
  if (data && typeof data === 'object' && 'code' in data) {
    if (data.code !== 200 && data.status !== 'ok') {
      throw new Error(data.message || 'Unknown API Error');
    }
    return data.data !== undefined ? data.data : data;
  }

  return data as T;
}

export const api = {
  health: () => fetchAPI<{ status: string }>('/health'),
  getMarketIndices: (codes?: string) => 
    fetchAPI<IndexData[]>(`/market/indices${codes ? `?codes=${codes}` : ''}`),
  getLimitUpPool: (date?: string) => 
    fetchAPI<EnrichedLimitUpPoolData>(`/market/limit-up${date ? `?date=${date}` : ''}`),
  getStockTrends: (codes: string[]) =>
    fetchAPI<import('@/types/canonical').StockTrendData[]>(`/market/stock-trends?codes=${codes.join(',')}`),
  getSectors: (sectorType: 'industry' | 'concept' = 'industry', limit: number = 15) =>
    fetchAPI<SectorFlowItem[]>(`/market/sectors?sector_type=${sectorType}&limit=${limit}`),
  getDailyReviews: (limit?: number, offset?: number) =>
    fetchAPI<{ items: DailyReviewSummaryItem[]; total: number }>(
      `/reports/daily-review?limit=${limit ?? 30}&offset=${offset ?? 0}`
    ),
  getDailyReview: (date: string) => 
    fetchAPI<DailyReviewDetail>(`/reports/daily-review/${date}`),
  generateDailyReview: (date?: string, force: boolean = false) => 
    fetchAPI<any>(`/reports/daily-review/generate${date ? `?date=${date}&force=${force}` : `?force=${force}`}`, { method: 'POST' }),
  chatDailyReview: (date: string, query: string, chapter?: string, history?: any[]) =>
    fetchAPI<{ query: string; answer: string; date: string }>(`/reports/daily-review/chat`, {
      method: 'POST',
      body: JSON.stringify({ date, query, chapter, history }),
    }),
  getPremarketBriefings: (limit?: number, offset?: number) =>
    fetchAPI<{ items: PremarketBriefingSummaryItem[]; total: number }>(
      `/reports/premarket?limit=${limit ?? 30}&offset=${offset ?? 0}`
    ),
  getPremarketBriefing: (date: string) => 
    fetchAPI<PremarketBriefingDetail>(`/reports/premarket/${date}`),
  generatePremarketBriefing: (date?: string) => 
    fetchAPI<any>(`/reports/premarket/generate${date ? `?date=${date}` : ''}`, { method: 'POST' }),
  getAuctionReports: (limit?: number, offset?: number) =>
    fetchAPI<{ items: AuctionReportSummaryItem[]; total: number }>(
      `/reports/auction?limit=${limit ?? 30}&offset=${offset ?? 0}`
    ),
  getAuctionReport: (date: string) => 
    fetchAPI<AuctionReportDetail>(`/reports/auction/${date}`),
  generateAuctionReport: (date?: string) => 
    fetchAPI<any>(`/reports/auction/generate${date ? `?date=${date}` : ''}`, { method: 'POST' }),
  getMarketState: (date: string) => 
    fetchAPI<any>(`/cognition/market-state/${date}`),
  // M4 盘中动态监控端点
  getMonitorRealtime: (date?: string) =>
    fetchAPI<MonitorRealtimeResponse>(`/monitor/realtime${date ? `?date=${date}` : ''}`),
  getMonitorSeries: (date?: string) =>
    fetchAPI<MacroSnapshotItem[]>(`/monitor/series${date ? `?date=${date}` : ''}`),
  getMonitorEvents: (date?: string, severity?: string, limit?: number) => {
    const params = new URLSearchParams();
    if (date) params.append('date', date);
    if (severity) params.append('severity', severity);
    if (limit) params.append('limit', limit.toString());
    const qs = params.toString();
    return fetchAPI<IntradayAnomalyEventItem[]>(`/monitor/events${qs ? `?${qs}` : ''}`);
  },
  getMonitorWatchlist: (date?: string) =>
    fetchAPI<{ symbols: string[]; count: number }>(`/monitor/watchlist${date ? `?date=${date}` : ''}`),
  triggerMonitorScan: (date?: string) =>
    fetchAPI<any>(`/monitor/trigger-scan${date ? `?date=${date}` : ''}`, { method: 'POST' }),
  getClassicStrategies: (date?: string) =>
    fetchAPI<any>(`/strategy/classic-evaluation${date ? `?date=${date}` : ''}`),

  // G1-M3 交易记录与持仓管理端点
  getPositions: (refreshQuote: boolean = true) =>
    fetchAPI<import('@/types/trading').Position[]>(`/trading/positions?refresh_quote=${refreshQuote}`),
  getTradeRecords: (params?: { code?: string; direction?: string; record_type?: string; page?: number; limit?: number }) => {
    const sp = new URLSearchParams();
    if (params?.code) sp.append('code', params.code);
    if (params?.direction) sp.append('direction', params.direction);
    if (params?.record_type) sp.append('record_type', params.record_type);
    if (params?.page) sp.append('page', params.page.toString());
    if (params?.limit) sp.append('limit', params.limit.toString());
    const qs = sp.toString();
    return fetchAPI<{ items: import('@/types/trading').TradeRecord[]; total: number; page: number; limit: number }>(`/trading/records${qs ? `?${qs}` : ''}`);
  },
  getTradeRecordDetail: (id: number) =>
    fetchAPI<import('@/types/trading').TradeRecord>(`/trading/records/${id}`),
  addTradeRecord: (payload: import('@/types/trading').TradeRecordCreatePayload) =>
    fetchAPI<import('@/types/trading').TradeRecord>('/trading/records', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  reverseTradeRecord: (payload: import('@/types/trading').ReversalTradeCreatePayload) =>
    fetchAPI<import('@/types/trading').TradeRecord>('/trading/records/reverse', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getTradeStats: () =>
    fetchAPI<import('@/types/trading').TradeStats>('/trading/stats'),
  saveTradeNote: (payload: import('@/types/trading').TradeNoteCreatePayload) =>
    fetchAPI<import('@/types/trading').TradeNote>('/trading/notes', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getTradeNote: (tradeId: number) =>
    fetchAPI<import('@/types/trading').TradeNote>(`/trading/notes/${tradeId}`),
  reconcilePositions: (code?: string) =>
    fetchAPI<any>(`/trading/reconcile${code ? `?code=${code}` : ''}`, { method: 'POST' }),
  searchSecurities: (q: string, limit: number = 10) =>
    fetchAPI<import('@/types/trading').SecuritySearchResult[]>(`/trading/security/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  correctTradeRecord: (payload: import('@/types/trading').CorrectTradeRecordPayload) =>
    fetchAPI<{ reversal: import('@/types/trading').TradeRecord; corrected: import('@/types/trading').TradeRecord }>('/trading/records/correct', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getBrokerStatus: () =>
    fetchAPI<{
      connected: boolean;
      status: string;
      status_label: string;
      broker_name: string | null;
      channel_type: string | null;
      account_id: string | null;
      message: string;
      supported_channels: string[];
    }>('/trading/broker/status'),
  purgeSimulationFromTruthLedger: () =>
    fetchAPI<{ purged_records_count: number; affected_codes: string[] }>('/trading/purge-sim', { method: 'POST' }),

  // =========================================================================
  // 策略实盘模拟交易沙盒接口 (与真实券商账户物理隔离)
  // =========================================================================
  getSimAccount: () =>
    fetchAPI<import('@/types/simulation').SimAccount>('/simulation/account'),
  getSimPositions: (refreshQuote: boolean = true) =>
    fetchAPI<import('@/types/simulation').SimPosition[]>(`/simulation/positions?refresh_quote=${refreshQuote}`),
  getSimRecords: (limit: number = 50) =>
    fetchAPI<{ items: import('@/types/simulation').SimTrade[]; total: number }>(`/simulation/records?limit=${limit}`),
  executeSimTrade: (payload: import('@/types/simulation').SimTradeCreatePayload) =>
    fetchAPI<import('@/types/simulation').SimTrade>('/simulation/trades', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getSimStats: () =>
    fetchAPI<import('@/types/simulation').SimStats>('/simulation/stats'),
  resetSimAccount: () =>
    fetchAPI<{ status: string; message: string }>('/simulation/reset', { method: 'POST' }),


  // =========================================================================
  // G1-Cognition 验证闭环增强接口
  // =========================================================================
  triggerTradeDiagnosis: (tradeId: number) =>
    fetchAPI<import('@/types/cognition').CognitiveTradeDiagnosis>(`/cognition/diagnosis/trade/${tradeId}`, { method: 'POST' }),
  getTradeDiagnosis: (tradeId: number) =>
    fetchAPI<import('@/types/cognition').CognitiveTradeDiagnosis>(`/cognition/diagnosis/trade/${tradeId}`),
  confirmTradeDiagnosis: (tradeId: number, payload: { human_status: 'CONFIRMED' | 'MODIFIED'; human_comment?: string }) =>
    fetchAPI<any>(`/cognition/diagnosis/trade/${tradeId}/confirm`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),
  getWeeklyAudit: (weekOffset: number = 0) =>
    fetchAPI<import('@/types/cognition').WeeklyAuditResponse>(`/cognition/audit/weekly?week_offset=${weekOffset}`),
  createMarketHypothesis: (payload: import('@/types/cognition').MarketHypothesisCreatePayload) =>
    fetchAPI<import('@/types/cognition').MarketHypothesis>('/cognition/hypotheses', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  getMarketHypotheses: (params?: { target_date?: string; status?: string; page?: number; limit?: number }) => {
    const sp = new URLSearchParams();
    if (params?.target_date) sp.append('target_date', params.target_date);
    if (params?.status) sp.append('status', params.status);
    if (params?.page) sp.append('page', params.page.toString());
    if (params?.limit) sp.append('limit', params.limit.toString());
    const qs = sp.toString();
    return fetchAPI<{ items: import('@/types/cognition').MarketHypothesis[]; total: number; page: number; limit: number }>(
      `/cognition/hypotheses${qs ? `?${qs}` : ''}`
    );
  },
  verifyMarketHypothesis: (id: number, stage: 'AUCTION_0925' | 'CLOSE_1530') =>
    fetchAPI<import('@/types/cognition').HypothesisVerification>(`/cognition/hypotheses/${id}/verify?stage=${stage}`, {
      method: 'POST',
    }),

  // =========================================================================
  // Phase 2B.3: 认知闭环三卡片聚合接口
  // =========================================================================
  getCognitionReviewLoop: (date: string) =>
    fetchAPI<import('@/types/cognition').CognitionReviewLoopData>(`/cognition/review-loop/${date}`),
  proposeTodayHypothesis: (payload: { market_date: string; target_date?: string }) =>
    fetchAPI<any>('/cognition/hypotheses/propose-today', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // =========================================================================
  // 系统 LLM 与兼容 OpenAI 中转站 API 配置与测试
  // =========================================================================
  getLLMConfig: () => fetchAPI<LLMConfigData>('/system/llm-config'),
  updateLLMConfig: (data: LLMConfigUpdatePayload) =>
    fetchAPI<LLMConfigData>('/system/llm-config', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  testLLMConnection: (data: LLMTestPayload) =>
    fetchAPI<LLMTestResult>('/system/llm-config/test', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  resetLLMConfig: () =>
    fetchAPI<LLMConfigData>('/system/llm-config/reset', {
      method: 'POST',
    }),
};

export interface LLMConfigData {
  provider_type: string;
  base_url: string;
  model: string;
  api_key_masked: string;
  has_api_key: boolean;
  temperature: number;
  max_tokens: number;
  timeout_seconds: number;
  is_customized: boolean;
  updated_at?: string | null;
}

export interface LLMConfigUpdatePayload {
  provider_type?: string;
  base_url: string;
  model: string;
  api_key?: string | null;
  temperature?: number;
  max_tokens?: number;
  timeout_seconds?: number;
}

export interface LLMTestPayload {
  base_url: string;
  api_key?: string | null;
  model: string;
  timeout_seconds?: number;
}

export interface LLMTestResult {
  success: boolean;
  latency_ms: number;
  message: string;
  model_used?: string | null;
  reply_preview?: string | null;
  error?: string | null;
}

// =========================================================================
// Phase 2D.0 / 2D.1: Canonical Market Truth & Cognition 统一信封消费接口
// =========================================================================
export const canonicalAPI = {
  getLatestDate: () =>
    fetchAPI<{ latest_date: string }>('/canonical/latest-date'),
  getInstantSnapshot: (date?: string, forceRefresh: boolean = false) => {
    const params = new URLSearchParams();
    if (date) params.append('date', date);
    if (forceRefresh) params.append('force_refresh', 'true');
    const qs = params.toString();
    return fetchAPI<any>(`/canonical/instant-snapshot${qs ? `?${qs}` : ''}`);
  },
  getCanonicalMarketSnapshot: (date: string) =>
    fetchAPI<import('@/types/canonical').CanonicalMarketSnapshot>(`/canonical/market-snapshot/${date}`),
  getTacticalBriefing: (date: string) =>
    fetchAPI<import('@/types/canonical').TacticalBriefingReport>(`/canonical/tactical-briefing/${date}`),
  getAuctionFalsification: (date: string) =>
    fetchAPI<import('@/types/canonical').BiddingFalsificationVerdict>(`/canonical/auction-falsification/${date}`),
  getIntradayDrift: (date: string, timeStr?: string) =>
    fetchAPI<import('@/types/canonical').IntradayDriftVerdict>(
      `/canonical/intraday-drift/${date}${timeStr ? `?time=${timeStr}` : ''}`
    ),
  getIntradayBriefings: (date: string, timeStr?: string) =>
    fetchAPI<import('@/types/canonical').IntradayBriefingTimelineResponse>(
      `/canonical/intraday-briefings/${date}${timeStr ? `?time=${timeStr}` : ''}`
    ),
  getTopSectorsTrend: (date?: string) =>
    fetchAPI<import('@/types/canonical').TopSectorsTrendResponse>(
      `/canonical/intraday-top-sectors-trend${date ? `?date=${date}` : ''}`
    ),
  getIntradayGameCognition: (params: {
    trade_date: string;
    stocks: any[];
    strongest_stock?: any;
    sectors: any[];
    force_refresh?: boolean;
  }) =>
    fetchAPI<{
      status: string;
      source: string;
      model?: string;
      track1: string;
      track2: string;
      sector_rotation: string;
    }>('/canonical/intraday-game-cognition', {
      method: 'POST',
      body: JSON.stringify(params),
    }),
};


