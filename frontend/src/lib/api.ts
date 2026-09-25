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

const BACKEND_HOST = 'http://localhost:8000';
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
};
