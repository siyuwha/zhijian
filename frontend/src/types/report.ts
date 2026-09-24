export interface IndicatorValue {
  name: string;
  value: number | string | null;
  score: number | null;
  weight: number;
  contribution: number;
  raw_data?: Record<string, any>;
}

export interface SubDomainMetric {
  raw: any;
  score: number | null;
  weight: number;
}

export interface SubDomainState {
  subdomain_id: string;
  name: string;
  score: number | null;
  quality: string;
  metrics: Record<string, SubDomainMetric>;
}

export interface SubDimensionState {
  dimension_id: string;
  name: string;
  score: number | null;
  reference_score?: number | null;
  quality: string;
  state_label: string;
  metric_polarity: string;
  semantics_desc: string;
  metrics: Record<string, any>;
  sub_domains?: Record<string, SubDomainState> | null;
  indicators: IndicatorValue[];
}

export interface MarketStateVector {
  composite_score: number | null;
  state_label: string;
  data_quality: string;
  missing_metrics: string[];
  dimensions: Record<string, SubDimensionState>;
}

export interface DailyReviewSummaryItem {
  id: number;
  date: string;
  state_label: string;
  composite_score: number | null;
  data_quality: string;
  generated_at: string | null;
}

export interface DailyReviewDetail {
  id: number;
  date: string;
  market_overview: any[];
  limit_up_analysis: Record<string, any>;
  market_state: MarketStateVector | null;
  report_content: Record<string, any>;
  data_quality: string;
  generated_at: string | null;
}

export interface PremarketBriefing {
  date: string;
  overnightMarkets?: string;
  newsDigest?: string;
  yesterdayReview?: string;
  todayFocus?: string;
}

export interface AuctionReport {
  date: string;
  status: string;
}
