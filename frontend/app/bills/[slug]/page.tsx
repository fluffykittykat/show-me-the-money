'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { getEntity, getBillMoneyTrail, getConnections } from '@/lib/api';
import type { BillMoneyTrail } from '@/lib/api';
import type { Entity, Relationship } from '@/lib/types';
import { getMeta } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import ConflictBadge from '@/components/ConflictBadge';
import MoneyTrail from '@/components/MoneyTrail';
import BillVoteBreakdown from '@/components/BillVoteBreakdown';
import BillTextPanel from '@/components/BillTextPanel';
import FBIBriefing from '@/components/FBIBriefing';
import LoadingState from '@/components/LoadingState';
import PartyBadge from '@/components/PartyBadge';
import {
  ArrowLeft,
  AlertTriangle,
  DollarSign,
  BarChart3,
  FileText,
  Scale,
  Users,
  ExternalLink,
  ChevronRight,
  ChevronDown,
  Clock,
  Tag,
} from 'lucide-react';

type Tab = 'money' | 'votes' | 'industries' | 'text';

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  {
    id: 'money',
    label: 'Follow the Money',
    icon: <DollarSign className="h-4 w-4" />,
  },
  {
    id: 'votes',
    label: 'Vote Breakdown',
    icon: <Scale className="h-4 w-4" />,
  },
  {
    id: 'industries',
    label: 'Industry Money',
    icon: <BarChart3 className="h-4 w-4" />,
  },
  {
    id: 'text',
    label: 'Bill Text',
    icon: <FileText className="h-4 w-4" />,
  },
];

// --- Bill status badge parser ---

interface StatusBadge {
  label: string;
  colorClass: string;
}

function parseBillStatus(status: string): StatusBadge {
  const lower = status.toLowerCase();

  if (lower.includes('became public law') || lower.includes('became law') || lower.includes('signed by president')) {
    return { label: 'BECAME LAW', colorClass: 'bg-green-900/60 text-green-300 border-green-700/50' };
  }
  if (lower.includes('vetoed') || lower.includes('failed') || lower.includes('pocket vetoed')) {
    return { label: 'FAILED', colorClass: 'bg-red-900/60 text-red-300 border-red-700/50' };
  }
  if (lower.includes('passed house') && lower.includes('passed senate')) {
    return { label: 'PASSED BOTH', colorClass: 'bg-blue-900/60 text-blue-300 border-blue-700/50' };
  }
  if (lower.includes('passed house') || lower.includes('passed senate') || lower.includes('agreed to in')) {
    return { label: 'PASSED', colorClass: 'bg-blue-900/60 text-blue-300 border-blue-700/50' };
  }
  if (lower.includes('referred to') || lower.includes('committee')) {
    return { label: 'IN COMMITTEE', colorClass: 'bg-yellow-900/60 text-yellow-300 border-yellow-700/50' };
  }
  if (lower.includes('introduced')) {
    return { label: 'INTRODUCED', colorClass: 'bg-zinc-800 text-zinc-300 border-zinc-700' };
  }
  if (lower.includes('resolving differences') || lower.includes('conference')) {
    return { label: 'IN CONFERENCE', colorClass: 'bg-purple-900/60 text-purple-300 border-purple-700/50' };
  }
  if (lower.includes('sent to president') || lower.includes('presented to president')) {
    return { label: 'AT PRESIDENT', colorClass: 'bg-blue-900/60 text-blue-300 border-blue-700/50' };
  }

  return { label: 'PENDING', colorClass: 'bg-zinc-800 text-zinc-300 border-zinc-700' };
}

// --- Policy area color mapping ---

const POLICY_AREA_COLORS: Record<string, string> = {
  'health': 'bg-rose-900/50 text-rose-300 border-rose-700/40',
  'defense': 'bg-slate-800 text-slate-300 border-slate-600/40',
  'education': 'bg-indigo-900/50 text-indigo-300 border-indigo-700/40',
  'energy': 'bg-amber-900/50 text-amber-300 border-amber-700/40',
  'environment': 'bg-emerald-900/50 text-emerald-300 border-emerald-700/40',
  'finance': 'bg-green-900/50 text-green-300 border-green-700/40',
  'taxation': 'bg-green-900/50 text-green-300 border-green-700/40',
  'immigration': 'bg-orange-900/50 text-orange-300 border-orange-700/40',
  'crime': 'bg-red-900/50 text-red-300 border-red-700/40',
  'technology': 'bg-cyan-900/50 text-cyan-300 border-cyan-700/40',
  'agriculture': 'bg-lime-900/50 text-lime-300 border-lime-700/40',
  'transportation': 'bg-sky-900/50 text-sky-300 border-sky-700/40',
  'labor': 'bg-violet-900/50 text-violet-300 border-violet-700/40',
};

function getPolicyAreaColor(area: string): string {
  const lower = area.toLowerCase();
  for (const [key, value] of Object.entries(POLICY_AREA_COLORS)) {
    if (lower.includes(key)) return value;
  }
  return 'bg-zinc-800 text-zinc-300 border-zinc-700';
}

// --- Sponsor donor data type ---
interface SponsorDonors {
  [sponsorSlug: string]: { name: string; amount: number }[];
}

export default function BillInvestigationPage() {
  const params = useParams();
  const slug = params.slug as string;

  const [entity, setEntity] = useState<Entity | null>(null);
  const [moneyTrail, setMoneyTrail] = useState<BillMoneyTrail | null>(null);
  const [connections, setConnections] = useState<Relationship[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('money');
  const [showFullSummary, setShowFullSummary] = useState(false);
  const [sponsorDonors, setSponsorDonors] = useState<SponsorDonors>({});

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [entityData, moneyTrailData, connectionsData] = await Promise.all([
        getEntity(slug),
        getBillMoneyTrail(slug),
        getConnections(slug, { limit: 100 }).catch(() => ({ entity: null as unknown as Entity, connections: [] as Relationship[], total: 0 })),
      ]);
      setEntity(entityData);
      setMoneyTrail(moneyTrailData);
      setConnections(connectionsData.connections);

      // Fetch top donors for each sponsor/cosponsor (fire-and-forget, non-blocking)
      const allSponsorConnections = connectionsData.connections.filter(
        (c) => c.relationship_type === 'sponsored' || c.relationship_type === 'cosponsored'
      );
      const sponsorSlugs = allSponsorConnections
        .map((c) => c.connected_entity?.slug)
        .filter((s): s is string => !!s);

      // Fetch donors for each sponsor in parallel (limit to first 10 to avoid overload)
      const donorPromises = sponsorSlugs.slice(0, 10).map(async (officialSlug) => {
        try {
          const donorData = await getConnections(officialSlug, { type: 'donated_to', limit: 3 });
          const topDonors = donorData.connections
            .filter((c) => c.amount_usd != null && c.amount_usd > 0)
            .sort((a, b) => (b.amount_usd || 0) - (a.amount_usd || 0))
            .slice(0, 3)
            .map((c) => ({
              name: c.connected_entity?.name || c.from_entity_id,
              amount: c.amount_usd || 0,
            }));
          return { slug: officialSlug, donors: topDonors };
        } catch {
          return { slug: officialSlug, donors: [] };
        }
      });

      Promise.all(donorPromises).then((results) => {
        const donorMap: SponsorDonors = {};
        for (const r of results) {
          if (r.donors.length > 0) {
            donorMap[r.slug] = r.donors;
          }
        }
        setSponsorDonors(donorMap);
      });
    } catch (err) {
      if (
        err instanceof Error &&
        'status' in err &&
        (err as Record<string, unknown>).status === 404
      ) {
        setError('Bill not found. It may not be in our database yet.');
      } else {
        setError('Failed to load bill investigation. Please try again later.');
      }
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

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
              href="/"
              className="inline-flex items-center gap-2 rounded-md border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:border-zinc-600"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Home
            </Link>
            <button
              onClick={fetchData}
              className="rounded-md bg-money-gold px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-money-gold-hover"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  const metadata = entity.metadata as Record<string, unknown>;
  const billNumber = (metadata?.bill_number as string) || '';
  const congress = (metadata?.congress as string) || '';
  const status = (metadata?.status as string) || 'Unknown';
  const tldr = (metadata?.tldr as string) || '';
  const officialSummary =
    (metadata?.official_summary as string) ||
    (metadata?.crs_summary as string) ||
    entity.summary ||
    '';
  const fullTextUrl = (metadata?.full_text_url as string) || '';
  const latestActionDate = (metadata?.latest_action_date as string) || (metadata?.status_date as string) || '';

  const policyArea = (metadata?.policy_area as string) || '';
  const congressUrl = (metadata?.congress_url as string) || '';

  const statusBadge = parseBillStatus(status);

  // Filter sponsors and cosponsors from connections
  const sponsors = connections.filter(
    (c) => c.relationship_type === 'sponsored'
  );
  const cosponsors = connections.filter(
    (c) => c.relationship_type === 'cosponsored'
  );

  const trail = moneyTrail?.money_trail;
  const conflictScore = trail?.conflict_score || 'low';
  const narrative = trail?.narrative || '';
  const industries = trail?.by_industry || [];
  const totalToYes = trail?.total_to_yes_voters || 0;
  const yesVoters = moneyTrail?.yes_voters || [];
  const noVoters = moneyTrail?.no_voters || [];

  // Find max industry amount for bar scaling
  const maxIndustryAmount = Math.max(
    ...industries.map((i) => i.amount),
    1
  );

  // Helper to render a sponsor row with inline donors
  function renderSponsorRow(rel: Relationship) {
    const ce = rel.connected_entity;
    const ceMeta = getMeta(ce);
    const party = (ceMeta?.party as string) || '';
    const state = (ceMeta?.state as string) || '';
    const displayName = ce?.name || rel.from_entity_id;
    const officialSlug = ce?.slug;
    const donors = officialSlug ? sponsorDonors[officialSlug] : undefined;

    return (
      <div key={rel.id} className="rounded-lg px-3 py-2 transition-colors hover:bg-zinc-800">
        <Link
          href={officialSlug ? `/officials/${officialSlug}` : '#'}
          className="group flex items-center justify-between"
        >
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-zinc-200 group-hover:text-zinc-100">
              {displayName}
            </span>
            <PartyBadge party={party} />
            {state && (
              <span className="text-xs text-zinc-500">{state}</span>
            )}
          </div>
          <ChevronRight className="h-4 w-4 text-zinc-600 group-hover:text-zinc-400" />
        </Link>
        {donors && donors.length > 0 && (
          <div className="mt-1 ml-1 flex flex-wrap items-center gap-1 text-xs text-zinc-500">
            <DollarSign className="h-3 w-3 text-money-gold/60" />
            <span className="text-zinc-600">Top donors:</span>
            {donors.map((d, i) => (
              <span key={d.name}>
                <span className="text-zinc-400">{d.name}</span>
                <span className="text-money-gold/80"> ({formatMoney(d.amount)})</span>
                {i < donors.length - 1 && <span className="text-zinc-700">, </span>}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Breadcrumb */}
      <div className="mb-6">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-300"
        >
          <ArrowLeft className="h-3 w-3" />
          Home
        </Link>
      </div>

      {/* Top Section: Bill header */}
      <div className="mb-8">
        <div className="flex flex-wrap items-start gap-3">
          <h1 className="text-3xl font-bold tracking-tight text-zinc-100">
            {entity.name}
          </h1>
          <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wider ${statusBadge.colorClass}`}>
            {statusBadge.label}
          </span>
          <ConflictBadge severity={conflictScore} size="md" />
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-zinc-400">
          {billNumber && <span className="font-mono">{billNumber}</span>}
          {congress && (
            <>
              <span className="text-zinc-600">&middot;</span>
              <span>{congress} Congress</span>
            </>
          )}
          {policyArea && (
            <>
              <span className="text-zinc-600">&middot;</span>
              <span className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium ${getPolicyAreaColor(policyArea)}`}>
                <Tag className="h-3 w-3" />
                {policyArea}
              </span>
            </>
          )}
        </div>

        {/* TLDR + Expandable Full Summary */}
        {(tldr || officialSummary) && (
          <div className="mt-4 max-w-4xl">
            {tldr && (
              <p className="text-sm leading-relaxed text-zinc-300">
                {tldr}
              </p>
            )}
            {officialSummary && officialSummary !== tldr && (
              <div className="mt-2">
                <button
                  onClick={() => setShowFullSummary(!showFullSummary)}
                  className="inline-flex items-center gap-1 text-xs font-medium text-money-gold hover:text-money-gold-hover transition-colors"
                >
                  <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showFullSummary ? 'rotate-180' : ''}`} />
                  {showFullSummary ? 'Hide full summary' : 'Read full CRS summary'}
                </button>
                {showFullSummary && (
                  <div className="mt-2 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
                    <p className="text-sm leading-relaxed text-zinc-400 whitespace-pre-line">
                      {officialSummary}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* External links row */}
        {(fullTextUrl || congressUrl) && (
          <div className="mt-4 flex flex-wrap gap-3">
            {congressUrl && (
              <a
                href={congressUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md bg-zinc-800 px-3 py-1.5 text-sm font-medium text-zinc-200 transition-colors hover:bg-zinc-700"
              >
                View on Congress.gov
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}
            {fullTextUrl && (
              <a
                href={fullTextUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 transition-colors hover:border-zinc-500 hover:text-zinc-100"
              >
                <FileText className="h-3.5 w-3.5" />
                Read Full Text
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        )}
      </div>

      {/* FBI Special Agent Briefing */}
      <div className="mb-8">
        <FBIBriefing
          entitySlug={slug}
          entityName={entity.name}
          entityType="bill"
        />
      </div>

      {/* Bill Status Timeline */}
      {status && status !== 'Unknown' && (
        <div className="mb-8 rounded-xl border border-zinc-800 bg-money-surface p-6">
          <div className="mb-4 flex items-center gap-2">
            <Clock className="h-5 w-5 text-zinc-400" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-400">
              Bill Status Timeline
            </h2>
          </div>
          <div className="flex items-start gap-4">
            {/* Timeline dot and line */}
            <div className="flex flex-col items-center pt-1">
              <div className={`h-3 w-3 rounded-full ${
                statusBadge.label === 'BECAME LAW' ? 'bg-green-500' :
                statusBadge.label === 'FAILED' ? 'bg-red-500' :
                statusBadge.label === 'PASSED' || statusBadge.label === 'PASSED BOTH' ? 'bg-blue-500' :
                statusBadge.label === 'IN COMMITTEE' ? 'bg-yellow-500' :
                'bg-zinc-500'
              }`} />
              <div className="mt-1 h-8 w-px bg-zinc-700" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${statusBadge.colorClass}`}>
                  {statusBadge.label}
                </span>
                {latestActionDate && (
                  <span className="text-xs text-zinc-500">{latestActionDate}</span>
                )}
              </div>
              <p className="mt-1 text-sm text-zinc-300">{status}</p>
            </div>
          </div>
        </div>
      )}

      {/* Sponsors & Cosponsors with top donors */}
      {(sponsors.length > 0 || cosponsors.length > 0) && (
        <div className="mb-8 rounded-xl border border-zinc-800 bg-money-surface p-6">
          <div className="mb-4 flex items-center gap-2">
            <Users className="h-5 w-5 text-zinc-400" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-400">
              Sponsors & Their Money
            </h2>
          </div>

          {sponsors.length > 0 && (
            <div className="mb-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                Sponsored by:
              </p>
              <div className="space-y-1">
                {sponsors.map((s) => renderSponsorRow(s))}
              </div>
            </div>
          )}

          {cosponsors.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                Cosponsored by:{' '}
                <span className="normal-case text-zinc-400">
                  {cosponsors.length} official{cosponsors.length !== 1 ? 's' : ''}
                </span>
              </p>
              <div className="space-y-1">
                {cosponsors.map((c) => renderSponsorRow(c))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Hero: Follow the Money panel */}
      <div className="mb-8 rounded-xl border border-money-gold/30 bg-zinc-900 p-6">
        <div className="mb-4 flex items-center gap-2">
          <DollarSign className="h-5 w-5 text-money-gold" />
          <h2 className="text-lg font-bold text-money-gold">
            Follow the Money
          </h2>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Total stat */}
          <div className="rounded-lg border border-zinc-800 bg-zinc-950 px-5 py-4 text-center">
            <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
              Total to YES Voters
            </p>
            <p className="mt-1 text-3xl font-bold text-money-success">
              {formatMoney(totalToYes)}
            </p>
            <p className="mt-1 text-xs text-zinc-500">
              from beneficiary industries
            </p>
          </div>

          {/* Narrative */}
          <div className="lg:col-span-2">
            {narrative ? (
              <p className="text-sm leading-relaxed text-zinc-300">
                {narrative}
              </p>
            ) : (
              <p className="text-sm text-zinc-600">
                No money trail narrative available for this bill.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Tab navigation */}
      <div className="mb-6 flex gap-1 overflow-x-auto rounded-lg border border-zinc-800 bg-money-surface p-1">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={
              'flex items-center gap-2 whitespace-nowrap rounded-md px-4 py-2 text-sm font-medium transition-colors ' +
              (activeTab === tab.id
                ? 'bg-zinc-800 text-money-gold'
                : 'text-zinc-400 hover:text-zinc-200')
            }
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div>
        {/* Follow the Money Trail */}
        {activeTab === 'money' && (
          <div className="rounded-lg border border-zinc-800 bg-money-surface p-6">
            <MoneyTrail
              industries={industries}
              voters={yesVoters}
              bill={{ slug, name: entity.name }}
              conflictScore={conflictScore}
            />
          </div>
        )}

        {/* Vote Breakdown */}
        {activeTab === 'votes' && (
          <div className="rounded-lg border border-zinc-800 bg-money-surface p-6">
            <BillVoteBreakdown yesVoters={yesVoters} noVoters={noVoters} />
          </div>
        )}

        {/* Industry Money Flow */}
        {activeTab === 'industries' && (
          <div className="rounded-lg border border-zinc-800 bg-money-surface p-6">
            <h3 className="mb-4 text-sm font-bold uppercase tracking-wider text-zinc-400">
              Industry Money to YES Voters
            </h3>
            {industries.length === 0 ? (
              <p className="py-8 text-center text-sm text-zinc-600">
                No industry data available.
              </p>
            ) : (
              <div className="space-y-3">
                {industries.map((ind) => (
                  <div key={ind.industry}>
                    <div className="mb-1 flex items-center justify-between">
                      <span className="text-sm text-zinc-300">
                        {ind.industry}
                      </span>
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-zinc-500">
                          {ind.pct_of_total.toFixed(1)}%
                        </span>
                        <span className="font-semibold text-money-success">
                          {formatMoney(ind.amount)}
                        </span>
                      </div>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
                      <div
                        className="h-full rounded-full bg-money-gold/70"
                        style={{
                          width: `${(ind.amount / maxIndustryAmount) * 100}%`,
                        }}
                      />
                    </div>
                    {ind.senators.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {ind.senators.slice(0, 5).map((senator) => (
                          <span
                            key={senator}
                            className="text-[10px] text-zinc-600"
                          >
                            {senator}
                          </span>
                        ))}
                        {ind.senators.length > 5 && (
                          <span className="text-[10px] text-zinc-600">
                            +{ind.senators.length - 5} more
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Bill Text */}
        {activeTab === 'text' && (
          <div className="rounded-lg border border-zinc-800 bg-money-surface p-6">
            <BillTextPanel
              tldr={tldr}
              officialSummary={officialSummary}
              fullTextUrl={fullTextUrl}
              billTitle={entity.name}
            />
          </div>
        )}
      </div>

      {/* Why This Matters */}
      {narrative && (
        <div className="mt-8 rounded-lg border border-zinc-800 bg-money-surface p-6">
          <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-money-gold">
            Why This Matters
          </h3>
          <p className="text-sm leading-relaxed text-zinc-300">{narrative}</p>
        </div>
      )}
    </div>
  );
}
