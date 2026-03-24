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

export default function BillInvestigationPage() {
  const params = useParams();
  const slug = params.slug as string;

  const [entity, setEntity] = useState<Entity | null>(null);
  const [moneyTrail, setMoneyTrail] = useState<BillMoneyTrail | null>(null);
  const [connections, setConnections] = useState<Relationship[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('money');

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
    (metadata?.official_summary as string) || entity.summary || '';
  const fullTextUrl = (metadata?.full_text_url as string) || '';

  const policyArea = (metadata?.policy_area as string) || '';
  const congressUrl = (metadata?.congress_url as string) || '';

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
          <span className="text-zinc-600">&middot;</span>
          <span className="inline-flex items-center rounded-full bg-zinc-800 px-2.5 py-0.5 text-xs font-medium text-zinc-300">
            {status}
          </span>
        </div>

        {entity.summary && (
          <p className="mt-3 max-w-3xl text-sm leading-relaxed text-zinc-400">
            {entity.summary}
          </p>
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

      {/* Sponsors & Cosponsors */}
      {(sponsors.length > 0 || cosponsors.length > 0) && (
        <div className="mb-8 rounded-xl border border-zinc-800 bg-money-surface p-6">
          <div className="mb-4 flex items-center gap-2">
            <Users className="h-5 w-5 text-zinc-400" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-400">
              Sponsors
            </h2>
          </div>

          {sponsors.length > 0 && (
            <div className="mb-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                Sponsored by:
              </p>
              <div className="space-y-1">
                {sponsors.map((s) => {
                  const ce = s.connected_entity;
                  const ceMeta = getMeta(ce);
                  const party = (ceMeta?.party as string) || '';
                  const state = (ceMeta?.state as string) || '';
                  const displayName = ce?.name || s.from_entity_id;
                  const officialSlug = ce?.slug;

                  return (
                    <Link
                      key={s.id}
                      href={officialSlug ? `/officials/${officialSlug}` : '#'}
                      className="group flex items-center justify-between rounded-lg px-3 py-2 transition-colors hover:bg-zinc-800"
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
                  );
                })}
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
                {cosponsors.map((c) => {
                  const ce = c.connected_entity;
                  const ceMeta = getMeta(ce);
                  const party = (ceMeta?.party as string) || '';
                  const state = (ceMeta?.state as string) || '';
                  const displayName = ce?.name || c.from_entity_id;
                  const officialSlug = ce?.slug;

                  return (
                    <Link
                      key={c.id}
                      href={officialSlug ? `/officials/${officialSlug}` : '#'}
                      className="group flex items-center justify-between rounded-lg px-3 py-2 transition-colors hover:bg-zinc-800"
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
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Bill Status */}
      {(status || policyArea || fullTextUrl || congressUrl) && (
        <div className="mb-8 rounded-xl border border-zinc-800 bg-money-surface p-6">
          <h2 className="mb-4 text-sm font-bold uppercase tracking-wider text-zinc-400">
            Bill Status
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {status && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  Latest Action
                </p>
                <p className="mt-1 text-sm text-zinc-300">{status}</p>
              </div>
            )}
            {policyArea && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
                  Policy Area
                </p>
                <p className="mt-1 text-sm text-zinc-300">{policyArea}</p>
              </div>
            )}
          </div>
          {(fullTextUrl || congressUrl) && (
            <div className="mt-4 flex flex-wrap gap-3">
              {fullTextUrl && (
                <a
                  href={fullTextUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 transition-colors hover:border-zinc-500 hover:text-zinc-100"
                >
                  <FileText className="h-3.5 w-3.5" />
                  Full Text
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
              {congressUrl && (
                <a
                  href={congressUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 transition-colors hover:border-zinc-500 hover:text-zinc-100"
                >
                  Congress.gov
                  <ExternalLink className="h-3 w-3" />
                </a>
              )}
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
