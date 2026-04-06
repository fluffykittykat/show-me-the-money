import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class EntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    entity_type: str
    name: str
    summary: Optional[str] = None
    metadata: dict = Field(default={}, validation_alias="metadata_")
    created_at: datetime
    updated_at: datetime


class EntityBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    entity_type: str
    name: str
    summary: Optional[str] = None
    metadata_: Optional[dict] = None


class FlatConnectionItem(BaseModel):
    """A relationship with the connected entity embedded — flat structure for frontend."""

    id: uuid.UUID
    from_entity_id: uuid.UUID
    to_entity_id: uuid.UUID
    relationship_type: str
    amount_usd: Optional[int] = None
    amount_label: Optional[str] = None
    date_start: Optional[date] = None
    date_end: Optional[date] = None
    source_url: Optional[str] = None
    source_label: Optional[str] = None
    metadata: dict = {}
    connected_entity: Optional[EntityBrief] = None


class ConnectionsResponse(BaseModel):
    entity: EntityResponse
    connections: list[FlatConnectionItem]
    total: int


class EntityListResponse(BaseModel):
    results: list[EntityBrief]
    total: int
    limit: int
    offset: int


class SearchResponse(BaseModel):
    query: str
    entity_type: Optional[str] = None
    results: list[EntityResponse]
    total: int
    limit: int
    offset: int


class GraphNode(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    entity_type: str


class GraphEdge(BaseModel):
    source: uuid.UUID
    target: uuid.UUID
    relationship_type: str
    amount_label: Optional[str] = None


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    center_slug: str


class BriefingResponse(BaseModel):
    entity_slug: str
    entity_name: str
    briefing_text: str
    generated_at: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str


class ConfigEntryResponse(BaseModel):
    key: str
    description: str
    is_secret: bool
    is_configured: bool
    masked_value: Optional[str] = None
    source: str  # "database", "env_var", "default", "not_set"


class ConfigSetRequest(BaseModel):
    value: str


# ---------------------------------------------------------------------------
# Cross-reference / badge schemas
# ---------------------------------------------------------------------------


class StockHolderInfo(BaseModel):
    slug: str
    name: str
    party: str = ""
    state: str = ""
    amount_label: str | None = None
    amount_usd: int | None = None


class DonorRecipientInfo(BaseModel):
    slug: str
    name: str
    party: str = ""
    state: str = ""
    amount_usd: int | None = None
    amount_label: str | None = None


class CommitteeMemberInfo(BaseModel):
    slug: str
    name: str
    party: str = ""
    state: str = ""
    role: str = "Member"


class CommitteeJurisdiction(BaseModel):
    industries: list[str] = []
    topics: list[str] = []


class CommitteeDetailResponse(BaseModel):
    entity: EntityResponse
    members: list[CommitteeMemberInfo]
    jurisdiction: CommitteeJurisdiction
    member_count: int


class IndustryEntityBrief(BaseModel):
    slug: str
    name: str
    entity_type: str


class IndustryConnectionResponse(BaseModel):
    industry: str
    entity_count: int
    official_count: int
    total_donated: int
    donations_to_officials: list[DonorRecipientInfo]
    related_entities: list[IndustryEntityBrief]


class SharedInterestsResponse(BaseModel):
    shared_stocks: list[dict]
    shared_donors: list[dict]
    legislative_allies: list[dict]
    industry_network: list[dict]


class StockBadgeResponse(BaseModel):
    holder_count: int


class DonorBadgeResponse(BaseModel):
    recipient_count: int


class BillBadgeResponse(BaseModel):
    cosponsor_count: int
    donor_industries: list[dict]


# ---------------------------------------------------------------------------
# Donor profile schemas
# ---------------------------------------------------------------------------


class DonorRecipientDetail(BaseModel):
    slug: str
    name: str
    party: str = ""
    state: str = ""
    amount_usd: int | None = None
    amount_label: str | None = None
    committees: list[str] = []
    relevant_votes: list[str] = []


class LegislationInfluenced(BaseModel):
    bill_slug: str
    bill_name: str
    yes_voters_funded: int
    total_to_yes_voters: int


class DonorProfileResponse(BaseModel):
    entity: EntityResponse
    total_political_spend: int
    recipient_count: int
    recipients: list[DonorRecipientDetail]
    committees_covered: list[str]
    legislation_influenced: list[LegislationInfluenced]
    industry: str


# ---------------------------------------------------------------------------
# Lobbying schemas
# ---------------------------------------------------------------------------


class LobbyingData(BaseModel):
    total_spend: int = 0
    filing_count: int = 0
    firm_count: int = 0
    lobbyist_count: int = 0
    issues: list[str] = []


class RelationshipSpotlight(BaseModel):
    entity_slug: str
    entity_name: str
    entity_type: str
    signal_count: int
    signals: list[dict]
    severity: str


# ---------------------------------------------------------------------------
# Dashboard schemas
# ---------------------------------------------------------------------------


class ActiveBillItem(BaseModel):
    title: str
    number: str
    congress: str | int
    slug: str
    status: str
    latest_action: str
    update_date: str
    in_db: bool
    conflict_score: str = "NONE"


class TopConflictItem(BaseModel):
    slug: str
    name: str
    party: str = ""
    state: str = ""
    conflict_score: str
    total_conflicts: int
    top_conflict: str


class DashboardStats(BaseModel):
    officials_count: int = 0
    bills_count: int = 0
    donations_total: int = 0
    conflicts_count: int = 0
    lobbying_count: int = 0


class FeaturedStory(BaseModel):
    headline: str
    narrative: str
    entity_slug: str | None = None


# ---------------------------------------------------------------------------
# Evidence chain schemas
# ---------------------------------------------------------------------------


class ChainLinkResponse(BaseModel):
    step: int
    type: str
    description: str
    entity: str
    amount: str
    source_url: str
    date: str


class EvidenceChainResponse(BaseModel):
    official_slug: str
    company_slug: str
    chain: list[ChainLinkResponse]
    severity: str
    narrative: str
    chain_depth: int


class CompanyChainItem(BaseModel):
    official_name: str
    official_slug: str
    party: str | None = None
    state: str | None = None
    chain_depth: int
    severity: str
    top_chain_description: str


class CompanyChainsResponse(BaseModel):
    company_slug: str
    company_name: str
    officials: list[CompanyChainItem]
    total: int


# ---------------------------------------------------------------------------
# Ingestion job schemas
# ---------------------------------------------------------------------------


class IngestionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_type: str
    status: str
    progress: int = 0
    total: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    errors: list = []
    metadata: dict = Field(default={}, validation_alias="metadata_")
    created_at: datetime


# ---------------------------------------------------------------------------
# Hidden Connections schemas
# ---------------------------------------------------------------------------


class RevolvingDoorItem(BaseModel):
    lobbyist_name: str
    lobbyist_slug: str
    former_position: str
    current_role: str
    current_employer: str
    lobbies_committee: str
    clients: list[str]
    left_government: str | None = None
    registration_url: str | None = None
    why_this_matters: str
    years_in_government: str | None = None
    access_level: str | None = None
    what_they_lobbied: list[str] | None = None
    conflict_score: int | None = None


class FamilyConnectionItem(BaseModel):
    family_member: str
    relationship: str  # "spouse", "dependent"
    employer_name: str
    employer_slug: str | None = None
    role: str
    annual_income: int | None = None
    committee_overlap: str | None = None
    why_this_matters: str
    potential_benefit: str | None = None


class OutsideIncomeItem(BaseModel):
    payer_name: str
    payer_slug: str | None = None
    income_type: str  # "speaking_fee", "book_deal", "honorarium", "consulting"
    amount_usd: int
    date: str | None = None
    event_description: str | None = None
    is_regulated_industry: bool = False
    committee_overlap: str | None = None
    why_this_matters: str


class ContractorDonorItem(BaseModel):
    contractor_name: str
    contractor_slug: str | None = None
    state: str | None = None
    donation_amount: int
    donation_date: str | None = None
    contract_amount: int
    contract_date: str | None = None
    contract_agency: str
    contract_description: str
    dollars_per_donation_dollar: float | None = None
    why_this_matters: str


class TradeTimingItem(BaseModel):
    stock_name: str
    stock_slug: str | None = None
    transaction_type: str  # "buy" or "sell"
    transaction_date: str
    amount_range: str
    days_before_committee_hearing: int | None = None
    hearing_topic: str | None = None
    hearing_date: str | None = None
    days_before_related_vote: int | None = None
    vote_topic: str | None = None
    stock_movement_after: str | None = None
    information_access_score: int  # 1-10
    pattern_flag: str | None = None
    pattern_description: str
    why_this_matters: str


class TradeTimingSummary(BaseModel):
    total_trades_analyzed: int
    trades_within_30_days_of_hearing: int
    trades_before_favorable_outcome: int
    trades_before_unfavorable_outcome: int
    average_information_access_score: float
    overall_pattern: str
    why_this_matters: str


class InsiderTimingResponse(BaseModel):
    entity_slug: str
    entity_name: str
    trades: list[TradeTimingItem]
    summary: TradeTimingSummary


class HiddenConnectionsSummary(BaseModel):
    entity_slug: str
    entity_name: str
    revolving_door: list[RevolvingDoorItem]
    revolving_door_count: int = 0
    revolving_door_highlight: str | None = None
    family_connections: list[FamilyConnectionItem]
    family_connections_count: int = 0
    family_highlight: str | None = None
    outside_income: list[OutsideIncomeItem]
    outside_income_total: int = 0
    outside_income_count: int = 0
    outside_income_highlight: str | None = None
    contractor_donors: list[ContractorDonorItem]
    contractor_donors_count: int = 0
    contractor_total_donations: int = 0
    contractor_total_contracts: int = 0
    contractor_donor_highlight: str | None = None
    trade_timing: TradeTimingSummary | None = None
    trade_timing_flagged_count: int = 0
    trade_timing_score: int = 0
    trade_timing_highlight: str | None = None
    total_hidden_signals: int = 0


class HiddenConnectionsFeedItem(BaseModel):
    alert_type: str  # "revolving_door", "trade_timing", "contractor_donor", "family_conflict", "speaking_fee"
    icon: str
    headline: str
    description: str
    plain_english: str | None = None
    official_name: str | None = None
    official_slug: str | None = None
    entity_slug: str
    entity_name: str
    severity: str  # "connection_noted", "structural_relationship", "notable_pattern", "high_concern"
    timestamp: str | None = None


# ---------------------------------------------------------------------------
# Trade alerts / scheduler schemas
# ---------------------------------------------------------------------------


class TradeItem(BaseModel):
    official_name: str
    official_slug: str
    ticker: str = ""
    transaction_type: str = "Unknown"
    amount_label: str = "Unknown"
    filed_date: Optional[str] = None
    days_to_file: Optional[int] = None
    is_flagged: bool = False
    committee_relevance: str = ""


class RecentTradesResponse(BaseModel):
    trades: list[TradeItem]
    total: int


class TradeAlertOfficialInfo(BaseModel):
    name: str
    slug: str
    transaction_type: str = "Unknown"
    amount_label: str = "Unknown"
    filed_date: Optional[str] = None
    days_to_file: Optional[int] = None
    committee_relevance: str = ""


class TradeAlertResponse(BaseModel):
    ticker: str
    trade_date_range: str
    officials: list[TradeAlertOfficialInfo]
    alert_level: str
    narrative: str
    related_legislation: list[dict] = []


class CrossReferenceTradeResponse(BaseModel):
    ticker: str
    officials_count: int
    officials: list[TradeAlertOfficialInfo]
    date_range: str
    alert_level: str


class SchedulerJobStatus(BaseModel):
    id: str
    trigger: str
    description: str
    next_run_time: Optional[str] = None
    last_run_time: Optional[str] = None
    status: str


class SchedulerStatusResponse(BaseModel):
    jobs: list[SchedulerJobStatus]
    scheduler_running: bool


# ---------------------------------------------------------------------------
# V2 single-response-per-page schemas
# ---------------------------------------------------------------------------


class V2MoneyTrail(BaseModel):
    industry: str
    verdict: str
    dot_count: int
    dots: list[str]
    narrative: str | None
    total_amount: int
    chain: dict


class V2InfluenceSignal(BaseModel):
    type: str
    found: bool
    rarity_label: str | None = None
    rarity_pct: float | None = None
    p_value: float | None = None
    baseline_rate: float | None = None
    observed_rate: float | None = None
    description: str | None = None
    evidence: dict = {}


class V2OfficialResponse(BaseModel):
    entity: EntityResponse
    overall_verdict: str
    total_dots: int
    money_trails: list[V2MoneyTrail]
    top_donors: list[dict]
    middlemen: list[dict]
    committees: list[dict]
    briefing: str | None
    freshness: dict
    stock_trades: list[dict] = []
    fec_cycles: list[dict] = []
    total_all_cycles: int = 0
    influence_signals: list[V2InfluenceSignal] = []
    percentile_rank: int | None = None
    peer_count: int = 0
    peer_group: str = ""


class V2SponsorVerifiedConnection(BaseModel):
    entity: str
    type: str
    amount: int = 0


class V2SponsorContext(BaseModel):
    industry_donations_90d: int = 0
    career_pac_total: int = 0
    committee: str | None = None


class V2BillSponsor(BaseModel):
    name: str
    slug: str
    party: str = ""
    state: str = ""
    role: str = ""
    verified_connections: list[V2SponsorVerifiedConnection] = []
    context: V2SponsorContext = V2SponsorContext()


class V2BillResponse(BaseModel):
    entity: EntityResponse
    status_label: str
    sponsors: list[V2BillSponsor]
    briefing: str | None
    summary: str | None = None
    policy_area: str | None = ""
    total_money_behind: int = 0
    top_donors_across: list = []
    votes: list = []
    percentile_rank: int | None = None
    similar_bill_count: int = 0
    influence_signals: list[V2InfluenceSignal] = []
    data_limitations: dict = {}


class V2EntityResponse(BaseModel):
    entity: EntityResponse
    money_in: list[dict]
    money_out: list[dict]
    money_trails: list[dict]  # traced forward: donor → PAC → official → legislation
    briefing: str | None
    connections: list[dict] = []  # all non-donation relationships
    dossier: dict = {}  # key metadata fields


class V2HomepageResponse(BaseModel):
    top_stories: list[dict]
    stats: dict
    top_officials: list[dict]
    top_influencers: list[dict]
    revolving_door: list[dict]
    last_computed: str | None = None
    recent_activity: list[dict] = []
