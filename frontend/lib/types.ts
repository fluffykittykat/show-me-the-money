export interface Entity {
  id: string;
  slug: string;
  entity_type: 'person' | 'company' | 'bill' | 'organization' | 'industry' | 'pac';
  name: string;
  summary: string | null;
  metadata: Record<string, unknown>;
  metadata_?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

/** Get metadata from an entity, handling both metadata and metadata_ field names */
export function getMeta(entity: Entity | Record<string, unknown> | null | undefined): Record<string, unknown> {
  if (!entity) return {};
  return (entity as Record<string, unknown>).metadata_ as Record<string, unknown>
    || (entity as Record<string, unknown>).metadata as Record<string, unknown>
    || {};
}

export interface Relationship {
  id: string;
  from_entity_id: string;
  to_entity_id: string;
  relationship_type: string;
  amount_usd: number | null;
  amount_label: string | null;
  date_start: string | null;
  date_end: string | null;
  source_url: string | null;
  source_label: string | null;
  metadata: Record<string, unknown>;
  connected_entity?: Entity;
}

export interface ConnectionsResponse {
  entity: Entity;
  connections: Relationship[];
  total: number;
}

export interface SearchResponse {
  results: Entity[];
  total: number;
  query: string;
}

export interface GraphNode {
  id: string;
  slug: string;
  name: string;
  entity_type: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relationship_type: string;
  amount_label: string | null;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  center_slug: string;
}

export interface BriefingResponse {
  entity_slug: string;
  entity_name: string;
  briefing_text: string;
  generated_at: string | null;
}

export interface ConfigEntry {
  key: string;
  description: string;
  is_secret: boolean;
  is_configured: boolean;
  masked_value: string | null;
  source: 'database' | 'env_var' | 'default' | 'not_set';
}

// === Hidden Connections Types ===

export interface RevolvingDoorItem {
  lobbyist_name: string;
  lobbyist_slug: string;
  former_position: string;
  current_role: string;
  current_employer: string;
  lobbies_committee: string;
  clients: string[];
  left_government: string | null;
  registration_url: string | null;
  why_this_matters: string;
  years_in_government: string | null;
  access_level: string | null;
  what_they_lobbied: string[] | null;
  conflict_score: number | null;
}

export interface FamilyConnectionItem {
  family_member: string;
  relationship: string;
  employer_name: string;
  employer_slug: string | null;
  role: string;
  annual_income: number | null;
  committee_overlap: string | null;
  why_this_matters: string;
  potential_benefit: string | null;
}

export interface OutsideIncomeItem {
  payer_name: string;
  payer_slug: string | null;
  income_type: string;
  amount_usd: number;
  date: string | null;
  event_description: string | null;
  is_regulated_industry: boolean;
  committee_overlap: string | null;
  why_this_matters: string;
}

export interface ContractorDonorItem {
  contractor_name: string;
  contractor_slug: string | null;
  state: string | null;
  donation_amount: number;
  donation_date: string | null;
  contract_amount: number;
  contract_date: string | null;
  contract_agency: string;
  contract_description: string;
  dollars_per_donation_dollar: number | null;
  why_this_matters: string;
}

export interface TradeTimingItem {
  stock_name: string;
  stock_slug: string | null;
  transaction_type: string;
  transaction_date: string;
  amount_range: string;
  days_before_committee_hearing: number | null;
  hearing_topic: string | null;
  hearing_date: string | null;
  days_before_related_vote: number | null;
  vote_topic: string | null;
  stock_movement_after: string | null;
  information_access_score: number;
  pattern_flag: string | null;
  pattern_description: string;
  why_this_matters: string;
}

export interface TradeTimingSummary {
  total_trades_analyzed: number;
  trades_within_30_days_of_hearing: number;
  trades_before_favorable_outcome: number;
  trades_before_unfavorable_outcome: number;
  average_information_access_score: number;
  overall_pattern: string;
  why_this_matters: string;
}

export interface InsiderTimingResponse {
  entity_slug: string;
  entity_name: string;
  trades: TradeTimingItem[];
  summary: TradeTimingSummary;
}

export interface HiddenConnectionsSummary {
  entity_slug: string;
  entity_name: string;
  revolving_door: RevolvingDoorItem[];
  revolving_door_count: number;
  revolving_door_highlight: string | null;
  family_connections: FamilyConnectionItem[];
  family_connections_count: number;
  family_highlight: string | null;
  outside_income: OutsideIncomeItem[];
  outside_income_total: number;
  outside_income_count: number;
  outside_income_highlight: string | null;
  contractor_donors: ContractorDonorItem[];
  contractor_donors_count: number;
  contractor_total_donations: number;
  contractor_total_contracts: number;
  contractor_donor_highlight: string | null;
  trade_timing: TradeTimingSummary | null;
  trade_timing_flagged_count: number;
  trade_timing_score: number;
  trade_timing_highlight: string | null;
  total_hidden_signals: number;
}

export interface HiddenConnectionsFeedItem {
  alert_type: string;
  icon: string;
  headline: string;
  description: string;
  plain_english: string | null;
  official_name: string | null;
  official_slug: string | null;
  entity_slug: string;
  entity_name: string;
  severity: string;
  timestamp: string | null;
}

// ─── V2 Types ────────────────────────────────────────────────────────

export interface V2MoneyTrail {
  industry: string;
  verdict: 'NORMAL' | 'CONNECTED' | 'INFLUENCED' | 'OWNED';
  dot_count: number;
  dots: string[];
  narrative: string;
  total_amount: number;
  computed_at?: string | null;
  date_range?: string | null;
  chain: {
    donors?: Array<{ name: string; slug: string; amount: number; date?: string | null }>;
    committees?: Array<{ name: string; slug: string }>;
    bills?: Array<{ name: string; slug: string; date?: string | null; role?: string }>;
    middlemen?: Array<{ name: string; slug: string; amount_in: number; amount_out: number }>;
    lobbying?: Array<{ firm: string; client: string; issue: string; date?: string | null }>;
    dots?: string[];
    donor_count?: number;
  };
}

export type Verdict = 'NORMAL' | 'CONNECTED' | 'INFLUENCED' | 'OWNED';

export interface V2Donor {
  slug: string;
  name: string;
  entity_type: string;
  total_donated: number;
  latest_date?: string | null;
}

export interface V2Committee {
  slug: string;
  name: string;
  role: string;
}

export interface V2StockTrade {
  ticker: string;
  transaction_type: string;
  amount_range: string;
  date: string | null;
  asset_name: string;
}

export interface V2FECCycle {
  cycle: number;
  receipts: number;
  disbursements: number;
}

export interface V2OfficialInfluenceSignalEvidence {
  matches?: Array<{
    entity_name?: string;
    donation_amount?: number;
    bill_name?: string;
    bill_slug?: string;
    lda_url?: string;
  }>;
  trades?: Array<{
    ticker?: string;
    transaction_type?: string;
    amount_range?: string;
    date?: string | null;
    committee?: string;
    asset_name?: string;
  }>;
  lobbyists?: Array<{
    name?: string;
    former_position?: string;
    current_clients?: string[];
  }>;
  [key: string]: unknown;
}

export interface V2OfficialInfluenceSignal {
  type: string;
  found: boolean;
  rarity_label: string;
  rarity_pct?: number;
  description?: string;
  evidence?: V2OfficialInfluenceSignalEvidence;
}

export interface V2OfficialResponse {
  entity: Entity;
  overall_verdict: string;
  total_dots: number;
  money_trails: V2MoneyTrail[];
  top_donors: V2Donor[];
  middlemen: V2Donor[];
  committees: V2Committee[];
  briefing: string | null;
  freshness: {
    fec_cycle: string | null;
    last_refreshed: string | null;
    has_donors: boolean;
    has_committees: boolean;
  };
  stock_trades: V2StockTrade[];
  fec_cycles: V2FECCycle[];
  total_all_cycles: number;
  influence_signals?: V2OfficialInfluenceSignal[];
  percentile_rank?: number | null;
  peer_count?: number;
  peer_group?: string;
}

export interface V2BillInfluenceSignalEvidence {
  trades?: Array<{
    ticker?: string;
    transaction_type?: string;
    amount_range?: string;
    date?: string | null;
    asset_name?: string;
  }>;
  [key: string]: unknown;
}

export interface V2BillInfluenceSignal {
  type: string;
  found: boolean;
  rarity_label: string;
  rarity_pct?: number;
  description?: string;
  evidence?: V2BillInfluenceSignalEvidence;
}

export interface V2BillSponsorConnection {
  entity: string;
  type: string;
  amount: number;
}

export interface V2BillSponsorContext {
  industry_donations_90d?: number;
  career_pac_total?: number;
  committee?: string;
}

export interface V2Sponsor {
  slug: string;
  name: string;
  party: string;
  state: string;
  role: string;
  top_donor?: string | null;
  verdict?: string | null;
  verified_connections?: V2BillSponsorConnection[];
  context?: V2BillSponsorContext;
}

export interface V2BillDataLimitations {
  fec_threshold?: string;
  senate_stocks?: boolean;
  [key: string]: unknown;
}

export interface V2BillResponse {
  entity: Entity;
  summary?: string;
  status_label: string;
  policy_area?: string | null;
  percentile_rank?: number | null;
  similar_bill_count?: number | null;
  influence_signals?: V2BillInfluenceSignal[];
  sponsors: V2Sponsor[];
  briefing: string | null;
  data_limitations?: V2BillDataLimitations | null;
  freshness?: {
    last_refreshed: string | null;
    introduced_date: string | null;
  };
}

export interface V2MoneyFlow {
  slug: string;
  name: string;
  entity_type: string;
  amount_usd: number;
  amount_label: string | null;
}

export interface V2EntityResponse {
  entity: Entity;
  money_in: V2MoneyFlow[];
  money_out: V2MoneyFlow[];
  briefing: string | null;
  freshness?: {
    last_refreshed: string | null;
    fec_cycle: string | null;
  };
}

export interface V2StoryCard {
  story_type: string;
  headline: string;
  narrative: string;
  verdict: string;
  officials: Array<{ name: string; slug: string; party: string }>;
  total_amount: number;
  industry: string;
  computed_at?: string | null;
  fec_cycle?: string | null;
}

export interface V2HomepageStats {
  officials_count: number;
  bills_count: number;
  donations_total: number;
  relationship_count: number;
}

export interface V2TopOfficial {
  slug: string;
  name: string;
  party: string;
  state: string;
  verdict: string;
  dot_count: number;
  fec_cycle?: string | null;
}

export interface V2TopInfluencer {
  slug: string;
  name: string;
  entity_type: string;
  total_donated: number;
  officials_funded: number;
}

export interface V2RevolvingDoor {
  lobbyist_name: string;
  lobbyist_slug: string;
  former_position: string;
  current_employer: string;
  official_name: string;
  official_slug: string;
  official_party: string;
  official_state: string;
}

export interface V2HomepageResponse {
  top_stories: V2StoryCard[];
  stats: V2HomepageStats;
  top_officials: V2TopOfficial[];
  top_influencers: V2TopInfluencer[];
  revolving_door: V2RevolvingDoor[];
  recent_activity?: Record<string, string>[];
  data_as_of?: string | null;
  fec_cycle?: string | null;
}
