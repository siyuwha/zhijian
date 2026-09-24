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
  indicators?: IndicatorValue[];
  indicators_detail?: IndicatorValue[];
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

export interface OvernightIndexItem {
  code: string;
  symbol: string;
  name: string;
  price: number | null;
  pct_change: number | null;
  change_pct?: number | null;
  change_val?: number | null;
  time?: string | null;
}

export interface NewsDigestItem {
  title: string;
  brief?: string;
  content?: string;
  publish_time?: string;
  time?: string;
  source?: string;
  url?: string;
}

export interface YesterdayReviewSnapshot {
  date: string | null;
  state_label: string;
  data_quality?: string;
  composite_score?: number | null;
  total_amount?: number | null;
  breadth?: {
    up_count?: number | null;
    down_count?: number | null;
    up_down_ratio?: number | null;
  };
  sub_a_structure?: {
    max_board_height?: number | null;
    promotion_rate?: number | null;
    score?: number | null;
  };
  sub_b_extremes?: {
    limit_up_count?: number | null;
    limit_down_count?: number | null;
    limit_diff?: number | null;
    broken_limit_ratio?: number | null;
    score?: number | null;
  };
  dimensions?: Record<string, SubDimensionState>;
  narrative?: string;
}

export interface TodayFocusItem {
  dimension: string;
  title: string;
  observation_point: string;
  analysis: string;
  disclaimer: string;
}

export interface PremarketBriefingDetail {
  id?: number;
  date: string;
  overnight_summary: OvernightIndexItem[];
  news_digest: NewsDigestItem[];
  yesterday_review_summary: YesterdayReviewSnapshot | null;
  today_focus: TodayFocusItem[];
  generated_at?: string | null;
}

export interface PremarketBriefingSummaryItem {
  id: number;
  date: string;
  overnight_summary: OvernightIndexItem[];
  yesterday_state_label: string;
  generated_at: string | null;
}

export type PremarketBriefing = PremarketBriefingDetail;

export interface AuctionReport {
  date: string;
  status: string;
}
