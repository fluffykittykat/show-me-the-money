import type {
  Entity,
  ConnectionsResponse,
  BriefingResponse,
  SearchResponse,
  GraphResponse,
  ConfigEntry,
  RevolvingDoorItem,
  FamilyConnectionItem,
  OutsideIncomeItem,
  ContractorDonorItem,
  InsiderTimingResponse,
  HiddenConnectionsSummary,
  HiddenConnectionsFeedItem,
} from './types';

const API_BASE = '/api';

class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });

  if (!res.ok) {
    throw new ApiError(
      `API request failed: ${res.status} ${res.statusText}`,
      res.status
    );
  }

  return res.json() as Promise<T>;
}

export async function getEntity(slug: string): Promise<Entity> {
  return apiFetch<Entity>(`/entities/${encodeURIComponent(slug)}`);
}

export async function getConnections(
  slug: string,
  params?: { type?: string; limit?: number; offset?: number }
): Promise<ConnectionsResponse> {
  const searchParams = new URLSearchParams();
  if (params?.type) searchParams.set('type', params.type);
  if (params?.limit != null) searchParams.set('limit', String(params.limit));
  if (params?.offset != null) searchParams.set('offset', String(params.offset));
  const qs = searchParams.toString();
  return apiFetch<ConnectionsResponse>(
    `/entities/${encodeURIComponent(slug)}/connections${qs ? `?${qs}` : ''}`
  );
}

export async function getBriefing(slug: string, refresh?: boolean): Promise<BriefingResponse> {
  return apiFetch<BriefingResponse>(
    `/entities/${encodeURIComponent(slug)}/briefing${refresh ? '?refresh=true' : ''}`
  );
}

export async function searchEntities(
  q: string,
  type?: string
): Promise<SearchResponse> {
  const searchParams = new URLSearchParams({ q });
  if (type) searchParams.set('type', type);
  return apiFetch<SearchResponse>(`/search?${searchParams.toString()}`);
}

export async function listEntities(
  type?: string,
  limit = 50,
  offset = 0
): Promise<{ results: Entity[]; total: number; limit: number; offset: number }> {
  const searchParams = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (type) searchParams.set('type', type);
  return apiFetch(`/browse?${searchParams.toString()}`);
}

export async function getGraph(
  slug: string,
  depth?: number
): Promise<GraphResponse> {
  const searchParams = new URLSearchParams();
  if (depth != null) searchParams.set('depth', String(depth));
  const qs = searchParams.toString();
  return apiFetch<GraphResponse>(
    `/graph/${encodeURIComponent(slug)}${qs ? `?${qs}` : ''}`
  );
}

export async function getConfig(): Promise<ConfigEntry[]> {
  return apiFetch<ConfigEntry[]>('/config');
}

export async function setConfigValue(key: string, value: string): Promise<void> {
  await apiFetch(`/config/${encodeURIComponent(key)}`, {
    method: 'POST',
    body: JSON.stringify({ value }),
  });
}

export async function clearConfigValue(key: string): Promise<void> {
  await apiFetch(`/config/${encodeURIComponent(key)}`, {
    method: 'DELETE',
  });
}

// ---------------------------------------------------------------------------
// Cross-reference types
// ---------------------------------------------------------------------------

export interface StockHolderInfo {
  slug: string;
  name: string;
  party: string;
  state: string;
  amount_label: string | null;
  amount_usd: number | null;
}

export interface DonorRecipientInfo {
  slug: string;
  name: string;
  party: string;
  state: string;
  amount_usd: number | null;
  amount_label: string | null;
}

export interface CommitteeMemberInfo {
  slug: string;
  name: string;
  party: string;
  state: string;
  role: string;
}

export interface CommitteeJurisdiction {
  industries: string[];
  topics: string[];
}

export interface CommitteeDetailData {
  entity: Entity;
  members: CommitteeMemberInfo[];
  jurisdiction: CommitteeJurisdiction;
  member_count: number;
}

export interface IndustryEntityBrief {
  slug: string;
  name: string;
  entity_type: string;
}

export interface IndustryConnectionData {
  industry: string;
  entity_count: number;
  official_count: number;
  total_donated: number;
  donations_to_officials: DonorRecipientInfo[];
  related_entities: IndustryEntityBrief[];
}

export interface SharedInterestsData {
  shared_stocks: Array<{ slug: string; name: string; overlap_count: number }>;
  shared_donors: Array<{ slug: string; name: string; shared_count: number; total_amount: number }>;
  legislative_allies: Array<{ slug: string; name: string; shared_bills: number }>;
  industry_network: Array<{ industry: string; connected_officials: number; total_money: number }>;
}

// ---------------------------------------------------------------------------
// Investigation types
// ---------------------------------------------------------------------------

export interface ConflictEvidence {
  type: string;
  entity?: string;
  name?: string;
  amount?: number;
  detail?: string;
  source?: string;
}

export interface ConflictSignal {
  conflict_type: string;
  severity: string;
  description: string;
  evidence: ConflictEvidence[];
  related_entities: string[];
  why_this_matters?: string;
}

export interface ConflictData {
  entity: Entity;
  conflicts: ConflictSignal[];
  conflict_score: string;
  total_conflicts: number;
}

export interface TimelineEvent {
  event_type: string;
  date: string | null;
  description: string;
  amount_usd: number | null;
  days_before_vote: number | null;
  related_entity_slug: string | null;
}

export interface DonationTimeline {
  entity: Entity;
  events: TimelineEvent[];
  suspicious_pairs: number;
}

export interface SharedDonorNetworkEntry {
  senator_slug: string;
  senator_name: string;
  shared_donors: string[];
  total_shared_amount: number;
}

export interface SharedDonorNetwork {
  entity: Entity | null;
  network: SharedDonorNetworkEntry[];
  total_shared_donors: number;
}

export interface BillMoneyTrailIndustry {
  industry: string;
  amount: number;
  pct_of_total: number;
  senators: string[];
}

export interface BillVoter {
  slug: string;
  name: string;
  party: string;
  top_donor_industries: string[];
}

export interface BillMoneyTrail {
  bill: {
    slug: string;
    name: string;
    summary: string | null;
    metadata: Record<string, unknown>;
  };
  yes_voters: BillVoter[];
  no_voters: BillVoter[];
  money_trail: {
    total_to_yes_voters: number;
    by_industry: BillMoneyTrailIndustry[];
    conflict_score: string;
    narrative: string;
  };
}

// ---------------------------------------------------------------------------
// Badge types
// ---------------------------------------------------------------------------

export interface StockBadgeResponse {
  holder_count: number;
}

export interface DonorBadgeResponse {
  recipient_count: number;
}

export interface BillBadgeResponse {
  cosponsor_count: number;
  donor_industries: Array<{ industry: string; total: number }>;
}

// ---------------------------------------------------------------------------
// Donor Profile types
// ---------------------------------------------------------------------------

export interface DonorRecipientDetail {
  slug: string;
  name: string;
  party: string;
  state: string;
  amount_usd: number | null;
  amount_label: string | null;
  committees: string[];
  relevant_votes: string[];
}

export interface LegislationInfluenced {
  bill_slug: string;
  bill_name: string;
  yes_voters_funded: number;
  total_to_yes_voters: number;
}

export interface DonorProfileData {
  entity: Entity;
  total_political_spend: number;
  recipient_count: number;
  recipients: DonorRecipientDetail[];
  committees_covered: string[];
  legislation_influenced: LegislationInfluenced[];
  industry: string;
}

// ---------------------------------------------------------------------------
// Cross-reference API functions
// ---------------------------------------------------------------------------

export async function getStockHolders(companySlug: string): Promise<StockHolderInfo[]> {
  return apiFetch<StockHolderInfo[]>(`/xref/stock-holders/${encodeURIComponent(companySlug)}`);
}

export async function getDonorRecipients(donorSlug: string): Promise<DonorRecipientInfo[]> {
  return apiFetch<DonorRecipientInfo[]>(`/xref/donor-recipients/${encodeURIComponent(donorSlug)}`);
}

export async function getCommitteeDetails(committeeSlug: string): Promise<CommitteeDetailData> {
  return apiFetch<CommitteeDetailData>(`/xref/committee/${encodeURIComponent(committeeSlug)}`);
}

export async function getIndustryConnections(industry: string): Promise<IndustryConnectionData> {
  return apiFetch<IndustryConnectionData>(`/xref/industry/${encodeURIComponent(industry)}`);
}

export async function getSharedInterests(slug: string): Promise<SharedInterestsData> {
  return apiFetch<SharedInterestsData>(`/xref/shared-interests/${encodeURIComponent(slug)}`);
}

export interface EntitySummaryData {
  entity: Entity;
  connection_counts: Record<string, number>;
  connected_officials: number;
  total_money_in: number;
  total_money_out: number;
}

export async function getEntitySummary(slug: string): Promise<EntitySummaryData> {
  return apiFetch<EntitySummaryData>(`/xref/entity-summary/${encodeURIComponent(slug)}`);
}

export async function getDonorProfile(donorSlug: string): Promise<DonorProfileData> {
  return apiFetch<DonorProfileData>(`/xref/donor-profile/${encodeURIComponent(donorSlug)}`);
}

// ---------------------------------------------------------------------------
// Investigation API functions
// ---------------------------------------------------------------------------

export async function getConflicts(slug: string): Promise<ConflictData> {
  return apiFetch<ConflictData>(`/investigate/conflicts/${encodeURIComponent(slug)}`);
}

export async function getDonationTimeline(slug: string): Promise<DonationTimeline> {
  return apiFetch<DonationTimeline>(`/investigate/timeline/${encodeURIComponent(slug)}`);
}

export async function getSharedDonorNetwork(slug: string): Promise<SharedDonorNetwork> {
  return apiFetch<SharedDonorNetwork>(`/investigate/network/${encodeURIComponent(slug)}`);
}

export async function getBillMoneyTrail(slug: string): Promise<BillMoneyTrail> {
  return apiFetch<BillMoneyTrail>(`/investigate/bill/${encodeURIComponent(slug)}`);
}

// ---------------------------------------------------------------------------
// Badge API functions
// ---------------------------------------------------------------------------

export async function getBillBadges(billSlug: string): Promise<BillBadgeResponse> {
  return apiFetch<BillBadgeResponse>(`/xref/bill-badges/${encodeURIComponent(billSlug)}`);
}

export async function getStockBadge(companySlug: string): Promise<StockBadgeResponse> {
  return apiFetch<StockBadgeResponse>(`/xref/stock-badge/${encodeURIComponent(companySlug)}`);
}

export async function getDonorBadge(donorSlug: string): Promise<DonorBadgeResponse> {
  return apiFetch<DonorBadgeResponse>(`/xref/donor-badge/${encodeURIComponent(donorSlug)}`);
}

// ---------------------------------------------------------------------------
// Lobbying & Relationship Spotlight types
// ---------------------------------------------------------------------------

export interface LobbyingData {
  total_spend: number;
  filing_count: number;
  firm_count: number;
  lobbyist_count: number;
  issues: string[];
}

export interface RelationshipSpotlightData {
  entity_slug: string;
  entity_name: string;
  entity_type: string;
  signal_count: number;
  signals: Array<{ type: string; detail: string; source: string }>;
  severity: string;
  why_this_matters?: string;
}

export async function getCompanyLobbying(companySlug: string): Promise<LobbyingData> {
  return apiFetch<LobbyingData>(`/xref/lobbying/${encodeURIComponent(companySlug)}`);
}

export async function getRelationshipSpotlight(slug: string): Promise<RelationshipSpotlightData[]> {
  return apiFetch<RelationshipSpotlightData[]>(`/xref/relationship-spotlight/${encodeURIComponent(slug)}`);
}

// ---------------------------------------------------------------------------
// Dashboard types & API functions
// ---------------------------------------------------------------------------

export interface DashboardStats {
  officials_count: number;
  bills_count: number;
  donations_total: number;
  conflicts_count: number;
  lobbying_count: number;
}

export interface ActiveBill {
  title: string;
  number: string;
  congress: string | number;
  slug: string;
  status: string;
  latest_action: string;
  update_date: string;
  in_db: boolean;
  conflict_score: string;
}

export interface TopConflict {
  slug: string;
  name: string;
  party: string;
  state: string;
  conflict_score: string;
  total_conflicts: number;
  top_conflict: string;
}

export interface FeaturedStory {
  headline: string;
  narrative: string;
  entity_slug: string | null;
}

export async function getDashboardStats(): Promise<DashboardStats> {
  return apiFetch<DashboardStats>('/dashboard/stats');
}

export interface StateMapData {
  state: string;
  senators: Array<{ name: string; slug: string; party: string }>;
  dominantParty: 'Democratic' | 'Republican' | 'Split' | 'Independent';
}

export async function getDashboardStates(): Promise<StateMapData[]> {
  return apiFetch<StateMapData[]>('/dashboard/states');
}

export async function getActiveBills(): Promise<ActiveBill[]> {
  return apiFetch<ActiveBill[]>('/dashboard/active-bills');
}

export async function getTopConflicts(): Promise<TopConflict[]> {
  return apiFetch<TopConflict[]>('/dashboard/top-conflicts');
}

export async function getFeaturedStory(): Promise<FeaturedStory> {
  return apiFetch<FeaturedStory>('/dashboard/featured-story');
}

export interface DualInfluenceItem {
  donor_name: string;
  donor_slug: string;
  donation_amount: number;
  lobby_client_name: string;
}

export interface InfluenceMap {
  entity: string;
  entity_name: string;
  dual_influence: DualInfluenceItem[];
  total: number;
  total_donors: number;
}

export async function getInfluenceMap(slug: string): Promise<InfluenceMap> {
  return apiFetch<InfluenceMap>(`/entities/${encodeURIComponent(slug)}/influence-map`);
}

export interface TopInfluencer {
  slug: string;
  name: string;
  entity_type: string;
  total_donated: number;
  officials_funded: number;
}

export async function getTopInfluencers(): Promise<TopInfluencer[]> {
  return apiFetch<TopInfluencer[]>('/dashboard/top-influencers');
}

// ---------------------------------------------------------------------------
// Hidden Connections API
// ---------------------------------------------------------------------------

export async function getRevolvingDoor(slug: string): Promise<RevolvingDoorItem[]> {
  return apiFetch<RevolvingDoorItem[]>(`/hidden/${encodeURIComponent(slug)}/revolving-door`);
}

export async function getFamilyConnections(slug: string): Promise<FamilyConnectionItem[]> {
  return apiFetch<FamilyConnectionItem[]>(`/hidden/${encodeURIComponent(slug)}/family-connections`);
}

export async function getOutsideIncome(slug: string): Promise<OutsideIncomeItem[]> {
  return apiFetch<OutsideIncomeItem[]>(`/hidden/${encodeURIComponent(slug)}/outside-income`);
}

export async function getContractorDonors(slug: string): Promise<ContractorDonorItem[]> {
  return apiFetch<ContractorDonorItem[]>(`/hidden/${encodeURIComponent(slug)}/contractor-donors`);
}

export async function getTradeTimingAnalysis(slug: string): Promise<InsiderTimingResponse> {
  return apiFetch<InsiderTimingResponse>(`/hidden/${encodeURIComponent(slug)}/trade-timing`);
}

export async function getHiddenConnectionsSummary(slug: string): Promise<HiddenConnectionsSummary> {
  return apiFetch<HiddenConnectionsSummary>(`/hidden/${encodeURIComponent(slug)}/summary`);
}

export async function getHiddenConnectionsFeed(): Promise<HiddenConnectionsFeedItem[]> {
  return apiFetch<HiddenConnectionsFeedItem[]>(`/hidden/feed`);
}

// ---------------------------------------------------------------------------
// Trade types
// ---------------------------------------------------------------------------

export interface TradeItem {
  official_name: string;
  official_slug: string;
  ticker: string;
  transaction_type: string;
  amount_label: string;
  filed_date: string;
  days_to_file: number;
  is_flagged: boolean;
  committee_relevance: string | null;
}

export interface RecentTradesResponse {
  trades: TradeItem[];
  total: number;
}

export interface TradeAlertOfficialInfo {
  name: string;
  slug: string;
  transaction_type: string;
  amount_label: string;
  filed_date: string;
  days_to_file: number;
  committee_relevance: string | null;
}

export interface TradeAlertResponse {
  ticker: string;
  trade_date_range: string;
  officials: TradeAlertOfficialInfo[];
  alert_level: string;
  narrative: string;
  related_legislation: Array<{ slug: string; title: string }>;
}

export interface CrossReferenceTradeResponse {
  ticker: string;
  officials_count: number;
  officials: TradeAlertOfficialInfo[];
  date_range: string;
  alert_level: string;
}

// ---------------------------------------------------------------------------
// Evidence chain types
// ---------------------------------------------------------------------------

export interface ChainLink {
  step: number;
  type: string;
  description: string;
  entity: string;
  amount: string;
  source_url: string;
  date: string;
}

export interface EvidenceChainResponse {
  official_slug: string;
  company_slug: string;
  chain: ChainLink[];
  severity: string;
  narrative: string;
  chain_depth: number;
}

export interface CompanyChainItem {
  official_name: string;
  official_slug: string;
  party: string | null;
  state: string | null;
  chain_depth: number;
  severity: string;
  top_chain_description: string;
}

export interface CompanyChainsResponse {
  company_slug: string;
  company_name: string;
  officials: CompanyChainItem[];
  total: number;
}

// ---------------------------------------------------------------------------
// Trade API functions
// ---------------------------------------------------------------------------

export async function getRecentTrades(limit = 50, offset = 0): Promise<RecentTradesResponse> {
  return apiFetch<RecentTradesResponse>(`/investigate/trades/recent?limit=${limit}&offset=${offset}`);
}

export async function getTradesByTicker(ticker: string, limit = 50, offset = 0): Promise<TradeAlertResponse> {
  return apiFetch<TradeAlertResponse>(`/investigate/trades/ticker/${encodeURIComponent(ticker)}?limit=${limit}&offset=${offset}`);
}

export async function getTradeAlerts(slug: string): Promise<TradeAlertResponse[]> {
  return apiFetch<TradeAlertResponse[]>(`/investigate/trades/alert/${encodeURIComponent(slug)}`);
}

export async function getTradeCrossReference(limit = 20, offset = 0): Promise<CrossReferenceTradeResponse[]> {
  return apiFetch<CrossReferenceTradeResponse[]>(`/investigate/trades/cross-reference?limit=${limit}&offset=${offset}`);
}

// ---------------------------------------------------------------------------
// Evidence chain API functions
// ---------------------------------------------------------------------------

export async function getEvidenceChain(officialSlug: string, companySlug: string): Promise<EvidenceChainResponse> {
  return apiFetch<EvidenceChainResponse>(`/investigate/chain/${encodeURIComponent(officialSlug)}/${encodeURIComponent(companySlug)}`);
}

export async function getAllChains(officialSlug: string): Promise<EvidenceChainResponse[]> {
  return apiFetch<EvidenceChainResponse[]>(`/investigate/chains/${encodeURIComponent(officialSlug)}`);
}

export async function getCompanyChains(companySlug: string): Promise<CompanyChainsResponse> {
  return apiFetch<CompanyChainsResponse>(`/investigate/chains/company/${encodeURIComponent(companySlug)}`);
}

// ---------------------------------------------------------------------------
// Money-to-Bills chain types & API
// ---------------------------------------------------------------------------

export interface MoneyToBillChain {
  policy_area: string;
  total_donated: number;
  donor_count: number;
  bill_count: number;
  top_donors: { name: string; slug: string; amount: number }[];
  related_bills: { name: string; slug: string; type: string }[];
  narrative: string;
}

export interface MoneyToBillsResponse {
  entity: string;
  entity_name: string;
  chains: MoneyToBillChain[];
  total_chains: number;
}

export async function getMoneyToBills(slug: string): Promise<MoneyToBillsResponse> {
  return apiFetch<MoneyToBillsResponse>(`/entities/${encodeURIComponent(slug)}/money-to-bills`);
}

export { ApiError };
