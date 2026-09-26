export interface CognitiveTradeDiagnosis {
  id: number;
  trade_id: number;
  date: string;
  // 事实层
  trade_price: number;
  trade_quantity: number;
  trade_amount: number;
  trade_direction: string;
  market_d1_d6_snapshot: {
    date?: string;
    state_label?: string;
    composite_score?: number;
    indicators?: Array<{
      dimension?: string;
      name?: string;
      score?: number;
      value?: number;
    }>;
    status?: string;
    note?: string;
  };
  post_trade_mdd?: number | null;
  post_trade_max_profit?: number | null;
  // 解释层
  env_match_type: 'HIGH_MATCH' | 'LOW_MATCH' | 'EMO_DRIVEN' | 'AMBIGUOUS' | string;
  env_match_score?: number | null;
  logic_realization: 'REALIZED' | 'UNREALIZED' | 'ACCIDENTAL' | string;
  cognitive_gap_analysis: string;
  // 人机审定状态
  human_status: 'UNCONFIRMED' | 'CONFIRMED' | 'MODIFIED';
  human_comment?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface WeeklyAuditMetrics {
  env_match_degree: number | null;
  logic_realization_degree: number | null;
  outcome_deviation_degree: number | null;
}

export interface WeeklyAuditResponse {
  week_label: string;
  total_trades: number;
  confirmed_samples_count: number;
  metrics: WeeklyAuditMetrics;
  market_state_distribution: Record<string, number>;
  trade_sample_summary: {
    high_match: number;
    low_match: number;
    emo_driven: number;
    ambiguous: number;
  };
  empirical_observations: string[];
}

export interface MarketHypothesisCreatePayload {
  target_date: string;
  hypothesis_type: 'INDEX_TREND' | 'SECTOR_LEADER' | 'SENTIMENT_CYCLE';
  target_asset: string;
  expected_scenario: 'ACCELERATION' | 'DIVERGENCE' | 'REBOUND' | 'ROTATION';
  premise_logic: string;
  expected_phenomenon: string;
  invalidation_condition: string;
  assertion_metrics?: Record<string, any>;
}

export interface HypothesisVerification {
  id: number;
  hypothesis_id: number;
  verification_stage: 'AUCTION_0925' | 'CLOSE_1530' | string;
  actual_data_snapshot: Record<string, any>;
  outcome: 'CONFIRMED' | 'FALSIFIED' | 'PARTIAL' | 'INVALID' | 'INCONCLUSIVE';
  accuracy_score?: number | null;
  deviation_analysis: string;
  gap_summary: string;
  verified_at?: string;
}

export interface MarketHypothesis {
  id: number;
  created_date: string;
  target_date: string;
  hypothesis_type: string;
  target_asset: string;
  expected_scenario: string;
  premise_logic: string;
  expected_phenomenon: string;
  invalidation_condition: string;
  assertion_metrics?: Record<string, any> | null;
  status: 'PENDING' | 'LOCKED' | 'VERIFYING' | 'CLOSED' | string;
  verifications: HypothesisVerification[];
  created_at?: string;
}
