export interface IndexData {
  code?: string;
  name: string;
  price: number | null;
  change?: number | null;
  pct_change?: number | null;
  changePercent?: number | null;
  amount_wan?: number | null;
}

export interface LimitUpData {
  symbol: string;
  name: string;
  price: number;
  limitUpTime: string;
  consecutiveBoards: number;
}

export interface LimitUpSummary {
  total: number;
  limitDown: number;
  consecutive: number;
  mainTheme: string;
}

export interface NewsItem {
  id: string;
  title: string;
  timestamp: string;
  source: string;
}
