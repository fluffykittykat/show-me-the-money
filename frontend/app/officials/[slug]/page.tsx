'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  getEntity,
  getConnections,
  getConflicts,
  getDonationTimeline,
  getSharedDonorNetwork,
  getSharedInterests,
  getRelationshipSpotlight,
  getHiddenConnectionsSummary,
  getRevolvingDoor,
  getFamilyConnections,
  getOutsideIncome,
  getContractorDonors,
  getTradeTimingAnalysis,
  getAllChains,
  getEntitySummary,
  getInfluenceMap,
} from '@/lib/api';
import type { InfluenceMap } from '@/lib/api';
import type {
  ConflictData,
  DonationTimeline as DonationTimelineType,
  SharedDonorNetwork as SharedDonorNetworkType,
  SharedInterestsData,
  RelationshipSpotlightData,
  EvidenceChainResponse,
  EntitySummaryData,
} from '@/lib/api';
import type {
  Entity,
  Relationship,
  HiddenConnectionsSummary,
  RevolvingDoorItem,
  FamilyConnectionItem,
  OutsideIncomeItem,
  ContractorDonorItem,
  InsiderTimingResponse,
} from '@/lib/types';
import { getInitials, formatMoney, formatDate } from '@/lib/utils';
import PartyBadge from '@/components/PartyBadge';
import ConflictBadge from '@/components/ConflictBadge';
import StatBar from '@/components/StatBar';
import InvestigatorSummary from '@/components/InvestigatorSummary';
import FBIBriefing from '@/components/FBIBriefing';
import TabNav from '@/components/TabNav';
import FinancialTable from '@/components/FinancialTable';
import DonorTable from '@/components/DonorTable';
import BillsTable from '@/components/BillsTable';
import CommitteeList from '@/components/CommitteeList';
import ConnectionsPanel from '@/components/ConnectionsPanel';
import ConflictCard from '@/components/ConflictCard';
import DonationTimeline from '@/components/DonationTimeline';
import RelationshipSpotlight from '@/components/RelationshipSpotlight';
import LobbyingTab from '@/components/LobbyingTab';
import MoneyToBills from '@/components/MoneyToBills';
import PartyMoneyTrail from '@/components/PartyMoneyTrail';
import LoadingState from '@/components/LoadingState';
import HiddenConnectionsCard from '@/components/HiddenConnectionsCard';
import RevolvingDoorSection from '@/components/RevolvingDoorSection';
import FamilyConnectionsSection from '@/components/FamilyConnectionsSection';
import OutsideIncomeSection from '@/components/OutsideIncomeSection';
import ContractorDonorsSection from '@/components/ContractorDonorsSection';
import TradeTimingSection from '@/components/TradeTimingSection';
import {
  ArrowLeft,
  AlertTriangle,
  Briefcase,
  CalendarDays,
  RefreshCcw,
  TrendingUp,
  DollarSign,
  ChevronDown,
} from 'lucide-react';
import clsx from 'clsx';

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'money', label: 'Money' },
  { id: 'hidden_connections', label: 'Hidden Connections' },
  { id: 'conflicts', label: 'Conflicts' },
  { id: 'legislative', label: 'Votes & Bills' },
  { id: 'connections', label: 'Connections' },
];

function categorizeConnections(connections: Relationship[]) {
  const holdings: Relationship[] = [];
  const donations: Relationship[] = [];
  const bills: Relationship[] = [];
  const votes: Relationship[] = [];
  const committees: Relationship[] = [];
  const other: Relationship[] = [];

  for (const conn of connections) {
    const type = conn.relationship_type.toLowerCase();
    if (type.includes('holds_stock') || type.includes('financial') || type.includes('owns') || type.includes('asset')) {
      holdings.push(conn);
    } else if (type.includes('donated') || type.includes('contribution') || type.includes('campaign')) {
      donations.push(conn);
    } else if (type.includes('sponsor') || type.includes('cosponsor') || type.includes('introduced')) {
      bills.push(conn);
    } else if (type.includes('voted') || type.includes('vote')) {
      votes.push(conn);
    } else if (type.includes('committee') || type.includes('member_of') || type.includes('serves_on')) {
      committees.push(conn);
    } else {
      other.push(conn);
    }
  }

  return { holdings, donations, bills, votes, committees, other };
}

/** Build evidence chain lookup map by related entity slug */
function buildChainMap(chains: EvidenceChainResponse[]): Map<string, EvidenceChainResponse> {
  const map = new Map<string, EvidenceChainResponse>();
  for (const chain of chains) {
    map.set(chain.company_slug, chain);
  }
  return map;
}

export default function OfficialProfilePage() {
  const params = useParams();
  const slug = params.slug as string;

  const [entity, setEntity] = useState<Entity | null>(null);
  const [connections, setConnections] = useState<Relationship[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Read initial tab from URL hash (e.g. #hidden_connections)
  const [activeTab, setActiveTab] = useState(() => {
    if (typeof window !== 'undefined') {
      const hash = window.location.hash.replace('#', '');
      const validTabs = TABS.map(t => t.id);
      if (hash && validTabs.includes(hash)) return hash;
    }
    return 'overview';
  });
  const [totalConnections, setTotalConnections] = useState(0);
  const [conflictData, setConflictData] = useState<ConflictData | null>(null);
  const [timelineData, setTimelineData] = useState<DonationTimelineType | null>(null);
  const [networkData, setNetworkData] = useState<SharedDonorNetworkType | null>(null);
  const [sharedInterests, setSharedInterests] = useState<SharedInterestsData | null>(null);
  const [spotlightData, setSpotlightData] = useState<RelationshipSpotlightData[]>([]);
  const [hiddenSummary, setHiddenSummary] = useState<HiddenConnectionsSummary | null>(null);
  const [hiddenSummaryLoading, setHiddenSummaryLoading] = useState(true);
  const [influenceMap, setInfluenceMap] = useState<InfluenceMap | null>(null);
  const [revolvingDoorData, setRevolvingDoorData] = useState<RevolvingDoorItem[] | null>(null);
  const [familyData, setFamilyData] = useState<FamilyConnectionItem[] | null>(null);
  const [outsideIncomeData, setOutsideIncomeData] = useState<OutsideIncomeItem[] | null>(null);
  const [contractorData, setContractorData] = useState<ContractorDonorItem[] | null>(null);
  const [tradeTimingData, setTradeTimingData] = useState<InsiderTimingResponse | null>(null);
  const [evidenceChains, setEvidenceChains] = useState<EvidenceChainResponse[]>([]);
  const [entitySummary, setEntitySummary] = useState<EntitySummaryData | null>(null);
  const [tabDataLoading, setTabDataLoading] = useState<Record<string, boolean>>({});

  const fetchData = useCallback(async () => {
    setLoading(true);
    setHiddenSummaryLoading(true);
    setError(null);
    try {
      // FAST PATH: Load entity + connections first (2 calls, renders page immediately)
      const [entityData, connectionsData] = await Promise.all([
        getEntity(slug),
        getConnections(slug, { limit: 500 }),
      ]);
      setEntity(entityData);
      setConnections(connectionsData.connections);
      setTotalConnections(connectionsData.total);
      setLoading(false); // Page renders NOW with basic data

      // LAZY PATH: Load enrichment data in background (non-blocking)
      Promise.all([
        getConflicts(slug).catch(() => null),
        getDonationTimeline(slug).catch(() => null),
        getSharedDonorNetwork(slug).catch(() => null),
        getSharedInterests(slug).catch(() => null),
        getRelationshipSpotlight(slug).catch(() => [] as RelationshipSpotlightData[]),
        getEntitySummary(slug).catch(() => null),
        getHiddenConnectionsSummary(slug).catch(() => null),
        getAllChains(slug).then(r => Array.isArray(r) ? r : (r as { chains: EvidenceChainResponse[] }).chains || []).catch(() => [] as EvidenceChainResponse[]),
        getInfluenceMap(slug).catch(() => null),
      ]).then(([conflicts, timeline, network, interests, spotlights, summary, hiddenSum, chains, influence]) => {
        setConflictData(conflicts);
        setTimelineData(timeline);
        setNetworkData(network);
        setSharedInterests(interests);
        setSpotlightData(spotlights);
        setEntitySummary(summary);
        setHiddenSummary(hiddenSum);
        setHiddenSummaryLoading(false);
        setEvidenceChains(chains as EvidenceChainResponse[]);
        setInfluenceMap(influence);
      });
    } catch (err) {
      if (err instanceof Error && 'status' in err && (err as Record<string, unknown>).status === 404) {
        setError('Official not found. They may not be in our database yet.');
      } else {
        setError('Failed to load profile. Please try again later.');
      }
      setHiddenSummaryLoading(false);
    } finally {
      setLoading(false);
    }
  }, [slug]);

  // Track whether hidden connections have been fetched to prevent re-fetching
  const [hiddenFetched, setHiddenFetched] = useState(false);

  // Lazy-load tab data when hidden connections tab is selected
  const fetchTabData = useCallback(async (tabId: string) => {
    if (tabId !== 'hidden_connections' || hiddenFetched) return;

    setHiddenFetched(true);
    const sections = ['revolving_door', 'family', 'outside_income', 'contractors', 'trade_timing'];
    setTabDataLoading((prev) => {
      const next = { ...prev };
      for (const s of sections) next[s] = true;
      return next;
    });

    // Load all hidden connection data in parallel, once
    const [rd, fc, oi, cd, tt] = await Promise.all([
      getRevolvingDoor(slug).catch(() => []),
      getFamilyConnections(slug).catch(() => []),
      getOutsideIncome(slug).catch(() => []),
      getContractorDonors(slug).catch(() => []),
      getTradeTimingAnalysis(slug).catch(() => null),
    ]);

    setRevolvingDoorData(rd);
    setFamilyData(fc);
    setOutsideIncomeData(oi);
    setContractorData(cd);
    setTradeTimingData(tt);

    setTabDataLoading((prev) => {
      const next = { ...prev };
      for (const s of sections) next[s] = false;
      return next;
    });
  }, [slug, hiddenFetched]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Lazy-load hidden connections tab data on tab switch
  useEffect(() => {
    const hiddenTabs = ['hidden_connections', 'revolving_door', 'family', 'outside_income', 'contractors', 'trade_timing'];
    if (hiddenTabs.includes(activeTab)) {
      fetchTabData(activeTab);
    }
  }, [activeTab, fetchTabData]);

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <LoadingState variant="profile" />
      </div>
    );
  }

  if (error || !entity) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-md text-center">
          <AlertTriangle className="mx-auto h-12 w-12 text-zinc-600" />
          <h1 className="mt-4 text-xl font-bold text-zinc-200">
            {error || 'Something went wrong'}
          </h1>
          <div className="mt-6 flex justify-center gap-3">
            <Link
              href="/officials"
              className="inline-flex items-center gap-2 rounded-md border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:border-zinc-600"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Officials
            </Link>
            <button
              onClick={fetchData}
              className="rounded-md bg-amber-500 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-amber-400"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  const metadata = entity.metadata as Record<string, unknown>;
  const party = (metadata?.party as string) || undefined;
  const state = (metadata?.state as string) || '';
  const chamber = (metadata?.chamber as string) || '';
  const yearsInOffice = (metadata?.years_in_office as string) || (metadata?.term_start as string) || '--';
  const rawCommittees = (metadata?.committees as Array<string | { name?: string; code?: string; role?: string }>) || [];
  const committeesList: string[] = rawCommittees.map((c) =>
    typeof c === 'string' ? c : (c?.name || c?.code || 'Unknown Committee')
  );

  const categorized = categorizeConnections(connections);

  // Build evidence chain map
  const chainMap = buildChainMap(evidenceChains);

  const tabsWithCounts = TABS.map((tab) => {
    let count: number | undefined;
    switch (tab.id) {
      case 'conflicts':
        count = conflictData?.total_conflicts ?? 0;
        break;
      case 'hidden_connections': {
        const hc = (hiddenSummary?.revolving_door_count ?? 0) +
          (hiddenSummary?.family_connections_count ?? 0) +
          (hiddenSummary?.contractor_donors_count ?? 0) +
          (hiddenSummary?.trade_timing_flagged_count ?? 0) +
          (hiddenSummary?.outside_income?.length ?? 0);
        count = hc > 0 ? hc : undefined;
        break;
      }
      case 'money':
        count = categorized.holdings.length + categorized.donations.length;
        break;
      case 'legislative':
        count = categorized.bills.length + categorized.votes.length;
        break;
      case 'connections':
        count = totalConnections;
        break;
    }
    return { ...tab, count };
  });

  // Compute stats
  const totalCampaign = categorized.donations.reduce(
    (sum, d) => sum + (d.amount_usd ?? 0),
    0
  );

  const stats = [
    { label: 'Years in Office', value: yearsInOffice },
    { label: 'Committees', value: entitySummary?.connection_counts?.committees ?? categorized.committees.length },
    { label: 'Conflicts', value: conflictData?.total_conflicts ?? 0 },
    { label: 'Stock Holdings', value: entitySummary?.connection_counts?.holdings ?? categorized.holdings.length },
    { label: 'Donors', value: entitySummary?.connection_counts?.donations ?? categorized.donations.length },
    {
      label: 'Total Campaign $',
      value: totalCampaign > 0 ? formatMoney(totalCampaign) : '--',
    },
  ];

  // Get party-based avatar color
  const avatarColor = party?.toLowerCase().includes('democrat')
    ? 'bg-blue-500/20 text-blue-400'
    : party?.toLowerCase().includes('republican')
      ? 'bg-red-500/20 text-red-400'
      : 'bg-zinc-700 text-zinc-300';

  // Check for holdings that might have vote-related conflicts
  const voteEntitySlugs = new Set(
    categorized.votes
      .map((v) => v.connected_entity?.slug)
      .filter(Boolean) as string[]
  );
  const conflictEntitySlugs = new Set(
    conflictData?.conflicts.flatMap((c) => c.related_entities) ?? []
  );

  // Pre-vote donations from timeline
  const preVoteDonations = timelineData?.events.filter(
    (e) =>
      e.days_before_vote != null &&
      e.days_before_vote >= 0 &&
      e.days_before_vote <= 90 &&
      e.event_type.toLowerCase().includes('donat')
  ) ?? [];

  // Determine party abbreviation
  const partyAbbrev = party?.toLowerCase().includes('democrat')
    ? 'D'
    : party?.toLowerCase().includes('republican')
      ? 'R'
      : party?.toLowerCase().includes('independent')
        ? 'I'
        : '';

  // Title line
  const titleLine = [
    chamber?.toUpperCase(),
    entity.name.toUpperCase(),
    partyAbbrev && state ? `(${partyAbbrev}-${state})` : partyAbbrev ? `(${partyAbbrev})` : state ? `(${state})` : '',
  ].filter(Boolean).join(' ');

  // Committees display
  const displayCommittees = committeesList.length > 0
    ? committeesList
    : categorized.committees.map((c) => c.connected_entity?.name).filter(Boolean) as string[];

  // Conflict count
  const totalConflictsCount = conflictData?.total_conflicts ?? 0;

  // Generate quick summary — connect the dots, don't just count
  const meta = entity.metadata as Record<string, unknown>;
  const officialParty = (meta?.party as string) || '';
  const officialState = (meta?.state as string) || '';
  const officialChamber = (meta?.chamber as string) || '';
  const role = officialChamber === 'Senate' ? 'Senator' : officialChamber?.includes('House') ? 'Representative' : 'Member of Congress';

  // Get top 3 donor names and total
  const topDonors = [...categorized.donations]
    .sort((a, b) => (b.amount_usd ?? 0) - (a.amount_usd ?? 0))
    .slice(0, 3)
    .map((d) => d.connected_entity?.name || 'Unknown');
  const totalDonated = categorized.donations.reduce((s, d) => s + (d.amount_usd ?? 0), 0);
  const fecTotal = (meta?.total_receipts as number) || 0;
  const displayTotal = fecTotal ? formatMoney(fecTotal * 100, { fromCents: true }) : formatMoney(totalDonated);

  // Build a narrative summary
  const summaryLines: string[] = [];

  // Line 1: Who they are and what committees they sit on
  if (displayCommittees.length > 0) {
    const commStr = displayCommittees.slice(0, 3).join(', ');
    summaryLines.push(`${role} from ${officialState} (${officialParty}). Sits on ${commStr}${displayCommittees.length > 3 ? ` and ${displayCommittees.length - 3} more` : ''}.`);
  } else {
    summaryLines.push(`${role} from ${officialState} (${officialParty}).`);
  }

  // Line 2: Donors — name the top ones
  if (categorized.donations.length > 0) {
    summaryLines.push(`Has raised ${displayTotal} in campaign contributions. Top donors include ${topDonors.join(', ')}.`);
  }

  // Line 3: Revolving door
  if (hiddenSummary?.revolving_door_count && hiddenSummary.revolving_door_count > 0) {
    const highlight = hiddenSummary.revolving_door_highlight || '';
    summaryLines.push(`${hiddenSummary.revolving_door_count} former staffer${hiddenSummary.revolving_door_count !== 1 ? 's' : ''} now lobby for private clients. ${highlight}`);
  }

  // Line 4: Stock holdings
  if (categorized.holdings.length > 0) {
    const stockNames = categorized.holdings.slice(0, 3).map((h) => h.connected_entity?.name || '?').join(', ');
    summaryLines.push(`Holds stock in ${stockNames}${categorized.holdings.length > 3 ? ` and ${categorized.holdings.length - 3} more` : ''}.`);
  }

  // Line 5: Dual influence — the money shot
  if (influenceMap && influenceMap.total > 0) {
    const topInfluencers = influenceMap.dual_influence.slice(0, 3).map((d) => d.lobby_client_name);
    summaryLines.push(
      `${influenceMap.total} of their donors also lobby Congress — including ${topInfluencers.join(', ')}. They gave money AND paid lobbyists to influence legislation.`
    );
  }

  // Line 6: Conflict tease
  if (totalConflictsCount > 0) {
    summaryLines.push(`We identified ${totalConflictsCount} potential conflict${totalConflictsCount !== 1 ? 's' : ''} of interest worth investigating.`);
  }

  const quickSummaryText = summaryLines.length > 0
    ? summaryLines.join(' ')
    : `No significant connections have been identified in our current data for ${entity.name}.`;

  // Scroll to section helper
  const scrollToTab = (tabId: string) => {
    setActiveTab(tabId);
    // Scroll to tab content after a short delay for render
    setTimeout(() => {
      const el = document.getElementById('tab-content-area');
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }, 100);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Breadcrumb */}
      <div className="mb-6">
        <Link
          href="/officials"
          className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-300"
        >
          <ArrowLeft className="h-3 w-3" />
          Officials
        </Link>
      </div>

      {/* Top Section: Avatar + Name */}
      <div className="mb-8 flex flex-col gap-6 sm:flex-row sm:items-start">
        {/* Avatar */}
        <div
          className={clsx(
            'flex h-24 w-24 shrink-0 items-center justify-center rounded-full text-2xl font-bold',
            avatarColor
          )}
          aria-hidden="true"
        >
          {getInitials(entity.name)}
        </div>

        {/* Info */}
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight text-zinc-100">
              {entity.name}
            </h1>
            <PartyBadge party={party} />
            {conflictData && conflictData.conflict_score !== 'NONE' && conflictData.conflict_score.toLowerCase() !== 'none' && (
              <ConflictBadge severity={conflictData.conflict_score} />
            )}
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-zinc-400">
            {state && <span>{state}</span>}
            {chamber && (
              <>
                <span className="text-zinc-600">&middot;</span>
                <span>{chamber}</span>
              </>
            )}
          </div>

          {/* Committees */}
          {displayCommittees.length > 0 && (
            <p className="mt-2 text-xs text-zinc-500">
              {displayCommittees.join(' \u2022 ')}
            </p>
          )}

          {entity.summary && (
            <p className="mt-3 max-w-2xl text-sm leading-relaxed text-zinc-400">
              {entity.summary}
            </p>
          )}
        </div>
      </div>

      {/* ==========================================
          INTELLIGENCE SUMMARY CARD
          ========================================== */}
      <div className="mb-8">
        <div className="rounded-xl border-2 border-amber-500/40 bg-zinc-900 p-5 sm:p-6 shadow-[0_0_20px_rgba(245,158,11,0.08)]">
          {/* Title */}
          <div className="mb-3">
            <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-300">
              {titleLine}
            </h2>
            {displayCommittees.length > 0 && (
              <p className="mt-1 text-xs text-zinc-500">
                {displayCommittees.join(' \u2022 ')}
              </p>
            )}
          </div>

          {/* Conflict count */}
          {totalConflictsCount > 0 ? (
            <div className="mb-3 flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-500" />
              <span className="text-sm font-bold text-amber-400">
                {totalConflictsCount} POTENTIAL CONFLICT{totalConflictsCount !== 1 ? 'S' : ''} DETECTED
              </span>
            </div>
          ) : (
            <div className="mb-3 flex items-center gap-2">
              <span className="text-sm font-medium text-zinc-500">
                No significant conflicts detected in current data
              </span>
            </div>
          )}

          {/* Quick Summary */}
          <div className="mb-4">
            <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-1">
              Quick Summary (plain English)
            </p>
            <p className="text-sm leading-relaxed text-zinc-300">
              {quickSummaryText}
            </p>
          </div>

          {/* Data completeness indicator */}
          {(() => {
            const hasDonors = categorized.donations.length > 0;
            const hasCommittees = categorized.committees.length > 0;
            const hasHoldings = categorized.holdings.length > 0;
            const hasBills = categorized.bills.length > 0;
            const dataPoints = [hasDonors, hasCommittees, hasBills, hasHoldings];
            const completeness = dataPoints.filter(Boolean).length;
            const isIncomplete = completeness < 3;

            if (isIncomplete) {
              const missing: string[] = [];
              if (!hasDonors) missing.push('campaign donors');
              if (!hasCommittees) missing.push('committee assignments');
              if (!hasHoldings) missing.push('stock holdings');

              return (
                <div className="mb-4 rounded-md border border-amber-500/20 bg-amber-500/5 px-3 py-2">
                  <p className="text-xs text-amber-400">
                    <span className="font-bold">Incomplete data.</span>{' '}
                    {missing.length > 0 && `Missing: ${missing.join(', ')}. `}
                    This does not mean this official is free of conflicts — it means our data coverage is limited.
                    We are actively working to fill gaps from public records.
                  </p>
                </div>
              );
            }
            return null;
          })()}

          {/* CTA buttons */}
          <div className="flex flex-wrap gap-2">
            {totalConflictsCount > 0 && (
              <button
                onClick={() => scrollToTab('conflicts')}
                className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 border border-amber-500/30 px-3 py-1.5 text-xs font-medium text-amber-400 hover:bg-amber-500/20 transition-colors"
              >
                SEE ALL CONFLICTS
                <ChevronDown className="h-3 w-3" />
              </button>
            )}
            <button
              onClick={() => scrollToTab('hidden_connections')}
              className="inline-flex items-center gap-1 rounded-md bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-700 transition-colors"
            >
              SEE HIDDEN CONNECTIONS
              <ChevronDown className="h-3 w-3" />
            </button>
            <button
              onClick={() => scrollToTab('connections')}
              className="inline-flex items-center gap-1 rounded-md bg-zinc-800 border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-700 transition-colors"
            >
              COMPARE TO PEERS
              <ChevronDown className="h-3 w-3" />
            </button>
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="mb-6">
        <StatBar stats={stats} />
      </div>

      {/* Hidden Connections Summary Card */}
      <div className="mb-8">
        <HiddenConnectionsCard
          summary={hiddenSummary}
          loading={hiddenSummaryLoading}
          entityName={entity.name}
          onViewDetails={(section) => setActiveTab(section)}
        />
      </div>

      {/* ==========================================
          TABBED CONTENT
          ========================================== */}
      <div id="tab-content-area">
        <TabNav tabs={tabsWithCounts} activeTab={activeTab} onTabChange={(tab) => {
          setActiveTab(tab);
          window.history.replaceState(null, '', `#${tab}`);
        }} />

        <div className="mt-6">
          {/* ===== OVERVIEW TAB ===== */}
          {activeTab === 'overview' && (
            <div role="tabpanel" id="tabpanel-overview" aria-labelledby="overview">
              {/* AI Briefing — the first thing users see */}
              <div className="mb-6">
                <FBIBriefing
                  entitySlug={slug}
                  entityName={entity.name}
                  entityType="person"
                />
              </div>

              {/* FOLLOW THE MONEY — the main story, front and center */}
              <MoneyToBills slug={slug} />

              {/* PARTY COMMITTEE MONEY TRAIL — who funds the middleman */}
              <PartyMoneyTrail slug={slug} officialName={entity.name} donations={categorized.donations} />

              {/* Investigator Summary — conflict analysis */}
              <div className="mb-6">
                <InvestigatorSummary
                  entitySlug={slug}
                  entityName={entity.name}
                  conflicts={conflictData?.conflicts ?? []}
                  conflictScore={conflictData?.conflict_score ?? 'NONE'}
                  committees={categorized.committees}
                  holdings={categorized.holdings}
                  donations={categorized.donations}
                  bills={categorized.bills}
                  votes={categorized.votes}
                />
              </div>

              {/* Fast Facts Cards */}
              <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <Briefcase className="h-4 w-4 text-amber-500" />
                    <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Committees</span>
                  </div>
                  {displayCommittees.length > 0 ? (
                    <ul className="space-y-1">
                      {displayCommittees.map((c, i) => (
                        <li key={i} className="text-xs text-zinc-300">{c}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs text-zinc-500">--</p>
                  )}
                </div>

                <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <CalendarDays className="h-4 w-4 text-amber-500" />
                    <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">In Office Since</span>
                  </div>
                  <p className="text-lg font-bold text-zinc-200">{yearsInOffice}</p>
                </div>

                <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <RefreshCcw className="h-4 w-4 text-amber-500" />
                    <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Former Staffers Lobbying</span>
                  </div>
                  <p className="text-lg font-bold text-zinc-200">
                    {hiddenSummary?.revolving_door_count ?? '--'}
                  </p>
                </div>

                <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <TrendingUp className="h-4 w-4 text-amber-500" />
                    <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Stock Holdings</span>
                  </div>
                  <p className="text-lg font-bold text-zinc-200">{categorized.holdings.length}</p>
                </div>

                <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <DollarSign className="h-4 w-4 text-amber-500" />
                    <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">Campaign Donors</span>
                  </div>
                  <p className="text-lg font-bold text-zinc-200">{categorized.donations.length}</p>
                </div>
              </div>

              {/* Bio */}
              {entity.summary && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 mb-6">
                  <h3 className="text-sm font-bold uppercase tracking-wider text-zinc-400 mb-2">About</h3>
                  <p className="text-sm leading-relaxed text-zinc-300">{entity.summary}</p>
                </div>
              )}

              {/* Committees section */}
              {categorized.committees.length > 0 && (
                <div className="mb-6">
                  <CommitteeList committees={categorized.committees} />
                </div>
              )}

              {/* Quick stat bar */}
              <StatBar stats={stats} />
            </div>
          )}

          {/* ===== HIDDEN CONNECTIONS TAB ===== */}
          {activeTab === 'hidden_connections' && (
            <div role="tabpanel" id="tabpanel-hidden_connections" aria-labelledby="hidden_connections">
              {/* Plain English intro */}
              <div className="mb-6 rounded-xl border border-zinc-800 bg-zinc-900 p-5">
                <p className="text-sm leading-relaxed text-zinc-300">
                  Here are the connections that rarely appear in news coverage. Each one is documented
                  from public records. None of this is an accusation &mdash; it&apos;s structural
                  information you have a right to know.
                </p>
              </div>

              {/* Revolving Door */}
              <div className="mb-8">
                <RevolvingDoorSection
                  items={revolvingDoorData ?? []}
                  loading={tabDataLoading['revolving_door'] ?? false}
                  entityName={entity.name}
                />
              </div>

              {/* Family Connections */}
              <div className="mb-8">
                <FamilyConnectionsSection
                  items={familyData ?? []}
                  loading={tabDataLoading['family'] ?? false}
                  entityName={entity.name}
                  officialName={entity.name}
                />
              </div>

              {/* Outside Income */}
              <div className="mb-8">
                <OutsideIncomeSection
                  items={outsideIncomeData ?? []}
                  loading={tabDataLoading['outside_income'] ?? false}
                  entityName={entity.name}
                />
              </div>

              {/* Contractor Donors */}
              <div className="mb-8">
                <ContractorDonorsSection
                  items={contractorData ?? []}
                  loading={tabDataLoading['contractors'] ?? false}
                  entityName={entity.name}
                />
              </div>

              {/* Trade Timing */}
              <div className="mb-8">
                <TradeTimingSection
                  data={tradeTimingData}
                  loading={tabDataLoading['trade_timing'] ?? false}
                  entityName={entity.name}
                />
              </div>
            </div>
          )}

          {/* ===== CONFLICTS TAB ===== */}
          {activeTab === 'conflicts' && (
            <div role="tabpanel" id="tabpanel-conflicts" aria-labelledby="conflicts">
              <div className="space-y-6">
                {/* Relationship Spotlights */}
                {spotlightData.length > 0 && (
                  <RelationshipSpotlight spotlights={spotlightData} officialName={entity.name} />
                )}

                {/* Conflict Summary — consolidated view */}
                {conflictData && conflictData.conflicts.length > 0 ? (() => {
                  // Group conflicts by committee to avoid repetition
                  const byCommittee = new Map<string, { committee: string; donors: { name: string; slug: string; amount: number }[]; severity: string }>();
                  for (const conflict of conflictData.conflicts) {
                    const evidence = conflict.evidence || [];
                    const committee = evidence.find((e: Record<string, unknown>) => e.type === 'committee');
                    const donors = evidence.filter((e: Record<string, unknown>) => e.type === 'donation');
                    const key = (committee as Record<string, unknown>)?.name as string || conflict.description.slice(0, 50);

                    if (!byCommittee.has(key)) {
                      byCommittee.set(key, { committee: key, donors: [], severity: conflict.severity });
                    }
                    const entry = byCommittee.get(key)!;
                    for (const d of donors) {
                      const dd = d as Record<string, unknown>;
                      if (!entry.donors.find((x) => x.name === dd.name)) {
                        entry.donors.push({ name: dd.name as string, slug: dd.entity as string, amount: (dd.amount as number) || 0 });
                      }
                    }
                  }

                  const groups = Array.from(byCommittee.values())
                    .sort((a, b) => b.donors.length - a.donors.length);

                  return (
                    <div className="space-y-4">
                      <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-zinc-400">
                        <AlertTriangle className="h-4 w-4 text-amber-500" />
                        Conflicts of Interest
                      </h3>
                      <p className="text-xs text-zinc-500">
                        Officials who receive money from industries they regulate. Each row shows a committee and the donors from that industry.
                      </p>
                      <div className="space-y-3">
                        {groups.map((group) => (
                          <div key={group.committee} className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                            <div className="flex items-center justify-between mb-2">
                              <h4 className="text-sm font-semibold text-zinc-200">{group.committee}</h4>
                              <ConflictBadge severity={group.severity} size="sm" />
                            </div>
                            <p className="text-xs text-zinc-500 mb-3">
                              {group.donors.length} donor{group.donors.length !== 1 ? 's' : ''} from industries this committee regulates:
                            </p>
                            <div className="space-y-1.5">
                              {group.donors.sort((a, b) => b.amount - a.amount).slice(0, 5).map((donor) => (
                                <div key={donor.name} className="flex items-center justify-between text-xs">
                                  <Link
                                    href={`/entities/person/${donor.slug}`}
                                    className="text-zinc-300 hover:text-money-gold truncate"
                                  >
                                    {donor.name}
                                  </Link>
                                  {donor.amount > 0 && (
                                    <span className="ml-2 shrink-0 text-money-success font-medium">
                                      {formatMoney(donor.amount)}
                                    </span>
                                  )}
                                </div>
                              ))}
                              {group.donors.length > 5 && (
                                <p className="text-xs text-zinc-600">+ {group.donors.length - 5} more donors</p>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })() : (
                  <div className="rounded-xl border border-zinc-800 bg-zinc-900 px-6 py-8 text-center">
                    <p className="text-sm text-zinc-400">
                      No conflicts of interest identified in current data.
                    </p>
                  </div>
                )}

                {/* Donation Timeline */}
                {timelineData && timelineData.events.length > 0 && (
                  <div>
                    <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-zinc-400">
                      Money Flow Timeline
                    </h3>
                    <DonationTimeline
                      events={timelineData.events}
                      suspiciousPairs={timelineData.suspicious_pairs}
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ===== MONEY TAB ===== */}
          {activeTab === 'money' && (
            <div role="tabpanel" id="tabpanel-money" aria-labelledby="money">
              {/* Financial Holdings section */}
              <div className="mb-8">
                <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-zinc-400">
                  <TrendingUp className="h-4 w-4 text-amber-500" />
                  Stock Holdings ({categorized.holdings.length})
                </h3>

                {categorized.holdings.length > 0 && (
                  <div className="mb-5 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                    <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-zinc-400">
                      Holdings Overview
                    </h4>
                    <ul className="space-y-1.5 text-sm">
                      <li className="text-zinc-300">
                        <span className="text-amber-500">&bull;</span>{' '}
                        {categorized.holdings.length} disclosed financial interest{categorized.holdings.length !== 1 ? 's' : ''}
                      </li>
                      {categorized.holdings
                        .filter((h) => {
                          const s = h.connected_entity?.slug;
                          return s && (conflictEntitySlugs.has(s) || voteEntitySlugs.has(s));
                        })
                        .slice(0, 3)
                        .map((h) => (
                          <li key={h.id} className="text-orange-300">
                            <AlertTriangle className="mr-1 inline-block h-3 w-3 text-orange-400" />
                            Financial interest in{' '}
                            <span className="font-semibold">{h.connected_entity?.name}</span>{' '}
                            <span className="text-zinc-500">({h.amount_label || 'undisclosed'})</span>
                            {' '}&mdash; overlaps with committee jurisdiction or voted legislation
                          </li>
                        ))}
                    </ul>
                  </div>
                )}
                <FinancialTable holdings={categorized.holdings} />
              </div>

              {/* Campaign Finance section */}
              <div>
                <h3 className="mb-4 flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-zinc-400">
                  <DollarSign className="h-4 w-4 text-amber-500" />
                  Campaign Finance ({categorized.donations.length} sources)
                </h3>

                {/* Pre-Vote Donations */}
                {preVoteDonations.length > 0 && (
                  <div className="mb-5 rounded-xl border border-red-500/20 bg-red-500/5 p-4">
                    <h4 className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-red-400">
                      <AlertTriangle className="h-3.5 w-3.5" />
                      Pre-Vote Donations
                    </h4>
                    <p className="mb-2 text-xs text-zinc-500">
                      Money received within 90 days before a related legislative vote
                    </p>
                    <ul className="space-y-1.5 text-sm">
                      {preVoteDonations.map((event, i) => (
                        <li key={i} className="text-orange-300">
                          <span className="text-red-400">&bull;</span>{' '}
                          {event.description}
                          {event.amount_usd != null && event.amount_usd > 0 && (
                            <span className="ml-1 text-amber-500">({formatMoney(event.amount_usd)})</span>
                          )}
                          {event.days_before_vote != null && (
                            <span className="ml-1 text-red-400">
                              &mdash; {event.days_before_vote} days before vote
                            </span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <DonorTable
                  donations={categorized.donations}
                  fecTotalReceipts={(entity.metadata as Record<string, unknown>)?.total_receipts as number | undefined}
                />
              </div>
            </div>
          )}

          {/* ===== VOTES & BILLS TAB ===== */}
          {activeTab === 'legislative' && (
            <div role="tabpanel" id="tabpanel-legislative" aria-labelledby="legislative">
              {(categorized.bills.length > 0 || categorized.votes.length > 0) && (
                <div className="mb-5 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
                  <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-zinc-400">
                    Legislative Activity Overview
                  </h4>
                  <ul className="space-y-1.5 text-sm">
                    <li className="text-zinc-300">
                      <span className="text-amber-500">&bull;</span>{' '}
                      {categorized.bills.length} bill{categorized.bills.length !== 1 ? 's' : ''} sponsored,{' '}
                      {categorized.votes.length} recorded vote{categorized.votes.length !== 1 ? 's' : ''}
                    </li>
                    {categorized.bills.slice(0, 3).map((b) => {
                      const meta = b.metadata as Record<string, unknown>;
                      const status = (meta?.status as string) || '';
                      const policyArea = (meta?.policyArea as string) || '';
                      const connectedEntity = b.connected_entity;
                      const isDonorBeneficiary = connectedEntity?.slug && conflictEntitySlugs.has(connectedEntity.slug);
                      return (
                        <li key={b.id} className={isDonorBeneficiary ? 'text-orange-300' : 'text-zinc-300'}>
                          {isDonorBeneficiary ? (
                            <AlertTriangle className="mr-1 inline-block h-3 w-3 text-orange-400" />
                          ) : (
                            <span className="text-amber-500">&bull;</span>
                          )}{' '}
                          {connectedEntity?.name || 'Unknown Bill'}
                          {status && (
                            <span className="ml-1 text-zinc-500">({status})</span>
                          )}
                          {policyArea && (
                            <span className="ml-1 text-zinc-600">&mdash; {policyArea}</span>
                          )}
                          {isDonorBeneficiary && (
                            <span className="ml-1 text-orange-400">&mdash; donor beneficiary</span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
              <BillsTable bills={categorized.bills} votes={categorized.votes} />
            </div>
          )}

          {/* ===== CONNECTIONS TAB ===== */}
          {activeTab === 'connections' && (
            <div role="tabpanel" id="tabpanel-connections" aria-labelledby="connections">
              <ConnectionsPanel
                connections={connections}
                committees={categorized.committees}
                holdings={categorized.holdings}
                donations={categorized.donations}
                entitySlug={slug}
                entityName={entity.name}
                networkData={networkData}
                sharedInterests={sharedInterests}
              />
            </div>
          )}

          {/* Lobbying and AI Briefing merged into Overview tab */}
        </div>
      </div>
    </div>
  );
}
