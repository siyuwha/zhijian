export interface DailyReview {
  date: string;
  indexOverview: string;
  limitUpAnalysis: string;
  sectorAttribution: string;
  marketState: string;
}

export interface PremarketBriefing {
  date: string;
  overnightMarkets: string;
  newsDigest: string;
  yesterdayReview: string;
  todayFocus: string;
}

export interface AuctionReport {
  date: string;
  status: string;
}
