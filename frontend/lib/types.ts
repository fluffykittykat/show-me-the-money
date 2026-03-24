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
