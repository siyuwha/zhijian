/**
 * Phase 2D.0 / 2D.1: Canonical Market Truth & Cognition 前端类型定义
 * 严格对应后端 L0~L5 分层契约：
 * - MarketTruthSnapshot (FACT + DERIVED)
 * - CognitionSnapshot (COGNITION)
 * - CanonicalMarketSnapshot (顶层统一数据信封)
 */

export type TruthSource =
  | 'SINA_HQ_STREAM'
  | 'EASTMONEY_PUSH'
  | 'EASTMONEY_PRICE_ANOMALY'
  | 'EASTMONEY_CONCEPT_BLOCKS'
  | 'TONGHUASHUN_LIMIT_UP'
  | 'DERIVED_COMMERCIAL_MATCH'
  | 'INTERNAL_CANONICAL_AGGREGATE'
  | 'COGNITION_ELIGIBILITY_ENGINE'
  | 'UNKNOWN';

export type DataQualityGrade = 'FULL' | 'PARTIAL' | 'DEGRADED' | 'UNAVAILABLE';

export interface ProvenanceEnvelope {
  source: TruthSource;
  observed_time: string;
  quality: DataQualityGrade;
  is_degraded: boolean;
  degradation_reason?: string | null;
}

export interface CanonicalIndexQuote {
  symbol: string;
  name: string;
  current_price: number;
  pre_close: number;
  change_val: number;
  pct_change: number;
  amount_yi: number;
  trade_date: string;
  envelope: ProvenanceEnvelope;
}

export interface CanonicalTurnoverBreakdown {
  trade_date: string;
  sh_amount_yi: number;
  sz_total_amount_yi: number;
  chinext_slice_amount_yi: number;
  chinext_ratio_in_sz: number;
  bse_amount_yi: number;
  two_markets_total_yi: number;
  all_markets_total_yi: number;
  envelope: ProvenanceEnvelope;
}

export interface CanonicalSecurityIdentity {
  security_id: string;
  stock_code: string;
  canonical_name: string;
  exchange: 'SH' | 'SZ' | 'BJ' | string;
}

export interface LimitUpStockItem {
  code: string;
  name: string;
  security_id?: string | null;
  board_type: 'MAIN' | 'GEM' | 'STAR' | 'BSE' | string;
  continuous_board_count: number;
  limit_up_type: 'FIRST_LIMIT' | 'CONTINUED' | string;
  first_limit_time?: string | null;
  last_limit_time?: string | null;
  reason_type: string;
  order_amount_wan?: number | null;
}

export interface BrokenLimitUniverseContract {
  trade_date: string;
  limit_up_count: number;
  broken_limit_count: number;
  touched_limit_total_count: number;
  broken_limit_ratio: number;
  limit_down_count: number;
  max_ladder_height: number;
  universe_criteria: Record<string, boolean>;
  envelope: ProvenanceEnvelope;
}

export interface RegulatoryAnomalyItem {
  symbol: string;
  name: string;
  rule_id: number;
  rule_name: string;
  deviation_pct: number;
  status_flag: number;
  provenance_nature: string;
}

export interface LadderGroup {
  height: number;
  stocks_count: number;
  stocks: LimitUpStockItem[];
  is_space_leader: boolean;
}

export interface MarketTruthSnapshot {
  schema_version: string;
  producer: string;
  trade_date: string;
  generated_at: string;
  indices: CanonicalIndexQuote[];
  turnover: CanonicalTurnoverBreakdown;
  sentiment_bounds: BrokenLimitUniverseContract;
  regulatory_anomalies: RegulatoryAnomalyItem[];
  ladder_tree: LadderGroup[];
  cross_section_breadth_status: DataQualityGrade;
  cross_section_breadth_detail?: {
    message?: string;
    heuristic_warning?: string;
  } | null;
  provenance: ProvenanceEnvelope;
  truth_fingerprint: string;
}

export type SemanticType =
  | 'CONCEPT'
  | 'INDUSTRY'
  | 'STATISTICAL_TAG'
  | 'TRADING_FEATURE'
  | 'RANKING_TAG'
  | 'PROVIDER_META_TAG'
  | 'REGION';

export interface ConstituencyEvidence {
  leader_code: string;
  leader_name: string;
  leader_security_id?: string | null;
  leader_height: number;
  limit_up_count: number;
  ladder_distribution: Record<string, number>;
  first_board_diffusion_count: number;
  constituent_symbols: string[];
}

export interface FalsificationCondition {
  invalidation_rules: string[];
  critical_observation_symbols: string[];
}

export interface SharedEvidenceAffiliate {
  target_sector_name: string;
  target_sector_code: string;
  overlap_stocks_count: number;
  shared_evidence_ratio: number;
  relationship: 'PARENT_INDUSTRY' | 'SUBTHEME_CATALYST' | 'CO_DRIVER_AFFILIATE';
  audit_note: string;
}

export interface SubthemeCatalyst {
  sector_name: string;
  sector_code: string;
  catalyst_leader: string;
  catalyst_height: number;
  stocks_count: number;
  thematic_role: string;
  overlap_ratio_with_master: number;
}

export interface MainlineCandidate {
  rank: number;
  sector_code: string;
  sector_name: string;
  semantic_type: 'CONCEPT' | 'INDUSTRY';
  constituency: ConstituencyEvidence;
  supporting_evidence: string[];
  counter_evidence: string[];
  falsification_condition: FalsificationCondition;
  structural_role: 'CORE_MAINLINE' | 'BRANCH_ROTATION' | 'WEAK_ROTATION_OR_ISOLATED';
  thematic_tier: 'TIER_1_CORE' | 'TIER_2_BRANCH' | 'TIER_3_WEAK_OR_ISOLATED';
  is_thematic_frontier?: boolean;
  shared_evidence_affiliates?: SharedEvidenceAffiliate[];
  conviction_summary: string;
  market_narrative?: string | null;
  static_taxonomy_name?: string | null;
  subtheme_catalysts?: SubthemeCatalyst[];
}

export interface LineageAccountingReport {
  total_raw_evaluated: number;
  admission_rejected_count: number;
  admission_admitted_count: number;
  excluded_meta_tags_count: number;
  excluded_regions_count: number;
  solitary_leader_noise_count: number;
  pulse_noise_count: number;
  deduplicated_clusters_count: number;
  eligible_candidates_count: number;
  top_mainlines_count: number;
  folded_eligible_remainder_count: number;
  is_mathematically_closed: boolean;
  lineage_formula: string;
}

export type MarketStateEnum =
  | 'EXPANSION_ACCELERATION'
  | 'HIGH_DIVERGENCE_TOPPING'
  | 'RECESSION_PANIC'
  | 'FREEZING_REVERSAL'
  | 'CHAOTIC_ROTATION'
  | 'LOW_REBOUND';

export interface IndexVector {
  total_turnover_yi: number;
  turnover_change_ratio?: number | null;
  dispersion_pct: number;
  star_divergence_pct: number;
}

export interface LadderVector {
  max_ladder_height: number;
  limit_up_count: number;
  limit_down_count: number;
  leader_ratio: number;
}

export interface RiskVector {
  broken_limit_ratio: number;
  broken_limit_count: number;
  extreme_loss_ratio: number;
}

export interface RegulatoryVector {
  anomaly_count: number;
  has_leader_warning: boolean;
}

export interface StateFeatureVector {
  index_vector: IndexVector;
  ladder_vector: LadderVector;
  risk_vector: RiskVector;
  regulatory_vector: RegulatoryVector;
}

export interface CalibratedMarketState {
  primary_state: MarketStateEnum;
  state_display_name: string;
  state_confidence: number;
  driving_factors: string[];
  transition_signal?: string | null;
  feature_vector?: StateFeatureVector | null;
}

export interface CognitionSnapshot {
  schema_version: string;
  producer: string;
  trade_date: string;
  generated_at: string;
  mainlines: MainlineCandidate[];
  lineage_accounting: LineageAccountingReport;
  market_state_summary: string;
  market_state_calibration?: CalibratedMarketState | null;
  provisional_disclaimer?: string;
  provenance: ProvenanceEnvelope;
  cognition_fingerprint: string;
}

export interface CanonicalMarketSnapshot {
  snapshot_version: string;
  trade_date: string;
  generated_at: string;
  truth: MarketTruthSnapshot;
  cognition: CognitionSnapshot;
  envelope_fingerprint: string;
}

export interface TacticalBriefingReport {
  schema_version: string;
  producer_version: string;
  trade_date: string;
  generated_at: string;
  market_state_label: string;
  tactical_briefing_text: string;
  key_battlegrounds: string[];
  risk_warnings: string[];
  next_day_observation_posts: string[];
  is_fallback_mode: boolean;
  fallback_reason?: string | null;
  safety_audit_passed: boolean;
  source_context_fingerprint: string;
  briefing_fingerprint: string;
}

