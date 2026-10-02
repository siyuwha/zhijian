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

// =========================================================================
// Phase 2B.3: 认知闭环三卡片聚合 DTO
// =========================================================================

export interface FactIndexItem {
  code: string;
  name: string;
  price: number | null;
  pct_change: number | null;
}

export interface FactSentiment {
  limit_up_count: number | null;
  limit_down_count: number | null;
  max_board_height: number | null;
  broken_limit_count: number | null;
  broken_ratio: number | null;
}

export interface FactBreadth {
  up_count: number | null;
  down_count: number | null;
  flat_count: number | null;
}

export interface FactLayer {
  indices: FactIndexItem[];
  sentiment: FactSentiment;
  breadth: FactBreadth;
}

export interface DerivedStateLayer {
  state_label: string;
  config_version: string;
}

export interface TodayFactsDTO {
  fact_layer: FactLayer;
  derived_state: DerivedStateLayer;
  observation_timestamp?: string | null;
  fact_snapshot_hash?: string | null;
  data_quality?: string | null;
  completeness?: number | null;
}

export interface AssertionDTO {
  assertion_id: string;
  metric_type: string;
  target_code: string;
  operator: string;
  threshold: any;
  description?: string | null;
}

export interface HypothesisMetaDTO {
  model_name: string;
  prompt_spec_version: string;
  hypothesis_hash?: string | null;
}

export interface TodayHypothesisDTO {
  id: number;
  status: string;
  created_date: string;
  target_date: string;
  hypothesis_type: string;
  target_asset: string;
  expected_scenario: string;
  premise_logic: string;
  expected_phenomenon: string;
  expected_assertions: AssertionDTO[];
  invalidation_condition: string;
  invalidation_assertions: AssertionDTO[];
  meta: HypothesisMetaDTO;
}

export interface AdjudicationComparisonItem {
  assertion_id: string;
  kind: 'EXPECTED' | 'INVALIDATION';
  metric_type: string;
  operator: string;
  threshold: any;
  actual_value?: number | null;
  is_satisfied: boolean;
}

export interface YesterdayAdjudicationDTO {
  hypothesis_id: number;
  created_date: string;
  target_date: string;
  hypothesis_type: string;
  premise_logic: string;
  outcome: 'CONFIRMED' | 'FALSIFIED' | 'INCONCLUSIVE';
  falsification_triggered: boolean;
  details: string;
  comparison_matrix: AdjudicationComparisonItem[];
}

export interface CognitionReviewLoopData {
  market_date: string;
  today_facts: TodayFactsDTO;
  today_hypothesis: TodayHypothesisDTO | null;
  yesterday_adjudication: YesterdayAdjudicationDTO | null;
}
