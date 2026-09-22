export interface IndexData {
  name: string;
  price: number;
  changePercent: number;
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
