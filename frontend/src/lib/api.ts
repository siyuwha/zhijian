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
    throw new Error(`API Error: ${response.statusText}`);
  }

  const data: ApiResponse<T> = await response.json();
  if (data.code !== 200 && (data as any).status !== 'ok') {
    throw new Error(data.message || 'Unknown API Error');
  }

  return data.data !== undefined ? data.data : (data as unknown as T);
}

export const api = {
  health: () => fetchAPI<{ status: string }>('/health'),
  getMarketIndices: (codes?: string) => 
    fetchAPI<IndexData[]>(`/market/indices${codes ? `?codes=${codes}` : ''}`),
  getLimitUpPool: (date?: string) => 
    fetchAPI<any>(`/market/limit-up${date ? `?date=${date}` : ''}`),
  getDailyReviews: (limit?: number, offset?: number) =>
    fetchAPI<{ items: DailyReviewSummaryItem[]; total: number }>(
      `/reports/daily-review?limit=${limit ?? 30}&offset=${offset ?? 0}`
    ),
  getDailyReview: (date: string) => 
    fetchAPI<DailyReviewDetail>(`/reports/daily-review/${date}`),
  generateDailyReview: (date?: string) => 
    fetchAPI<any>(`/reports/daily-review/generate${date ? `?date=${date}` : ''}`, { method: 'POST' }),
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
};

