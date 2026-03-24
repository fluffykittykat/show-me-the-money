'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import SearchBar from '@/components/SearchBar';
import ConflictBadge from '@/components/ConflictBadge';
import PartyBadge from '@/components/PartyBadge';
import USMap from '@/components/USMap';
import type { StateData } from '@/components/USMap';
import { formatMoney, formatDate, truncate } from '@/lib/utils';
import {
  getDashboardStats,
  getDashboardStates,
  getActiveBills,
  getTopConflicts,
  getTopInfluencers,
} from '@/lib/api';
import type {
  DashboardStats,
  StateMapData,
  ActiveBill,
  TopConflict,
  TopInfluencer,
} from '@/lib/api';
// HiddenConnectionsFeedItem removed — replaced with real revolving door data
import {
  ArrowRight,
  Users,
  Shield,
  Activity,
  Eye,
  TrendingUp,
  BarChart3,
  AlertTriangle,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ROTATING_SUBTEXTS = [
  "A senator's staffer left government and now lobbies the same committee",
  '3 officials traded pharmaceutical stocks before a drug pricing vote',
  'A company donated $25,000. It received $14 million in contracts.',
  "His wife's employer is regulated by the committee he chairs",
];

const DID_YOU_KNOW_FACTS = [
  'Members of Congress are exempt from insider trading laws that apply to everyone else',
  'The average revolving door lobbyist earns 1,400% more than their government salary',
  'Federal officials are only required to disclose stock ranges, not exact amounts',
  'Some officials have 0 financial conflicts. They exist. We show that too.',
];

// Revelation cards removed — replaced by data-driven Conflict Risk + Influencer sections

const defaultStats: DashboardStats = {
  officials_count: 0,
  bills_count: 0,
  donations_total: 0,
  conflicts_count: 0,
  lobbying_count: 0,
};

const STATUS_COLORS: Record<string, string> = {
  'ON FLOOR': 'bg-green-500/20 text-green-400 border-green-500/30',
  PASSED: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  'IN COMMITTEE': 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  FAILED: 'bg-red-500/20 text-red-400 border-red-400/30',
};

// ---------------------------------------------------------------------------
// Small components
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: string }) {
  const upper = status.toUpperCase();
  const colors =
    STATUS_COLORS[upper] ?? 'bg-zinc-700 text-zinc-300 border-zinc-600';
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${colors}`}
    >
      {status}
    </span>
  );
}

function StatCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: string | number;
  icon?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/80 p-5 text-center transition-colors hover:border-zinc-700">
      {icon && (
        <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/10">
          {icon}
        </div>
      )}
      <div className="font-mono text-2xl font-bold text-money-gold">
        {typeof value === 'number' ? value.toLocaleString() : value}
      </div>
      <div className="mt-1 text-xs uppercase tracking-wider text-zinc-500">
        {label}
      </div>
    </div>
  );
}

function SkeletonRow() {
  return (
    <div className="flex h-16 animate-pulse items-center px-6">
      <div className="h-4 w-full rounded bg-zinc-800/50" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Revolving Door section (self-contained, fetches own data)
// ---------------------------------------------------------------------------

interface RevolvingDoorEntry {
  lobbyist_name: string;
  lobbyist_slug: string;
  former_position: string;
  current_employer: string;
  official_name: string;
  official_slug: string;
  official_party: string;
  official_state: string;
}

function RevolvingDoorSection() {
  const [data, setData] = useState<RevolvingDoorEntry[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    fetch('/api/dashboard/revolving-door')
      .then((r) => r.json())
      .then((d) => { setData(d); setLoaded(true); })
      .catch(() => setLoaded(true));
  }, []);

  if (!loaded || data.length === 0) return null;

  return (
    <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
      <div className="rounded-xl border border-amber-500/20 bg-zinc-900/80 overflow-hidden">
        <div className="flex items-center justify-between border-b border-amber-500/10 px-6 py-4">
          <div className="flex items-center gap-3">
            <Eye className="h-5 w-5 text-amber-400" />
            <h2 className="font-mono text-lg font-bold uppercase tracking-wider text-amber-400">
              The Revolving Door
            </h2>
          </div>
          <span className="hidden font-mono text-[10px] uppercase tracking-widest text-zinc-700 sm:inline">
            FORMER STAFFERS NOW LOBBYING // REAL LDA DATA
          </span>
        </div>
        <div className="divide-y divide-zinc-800/50">
          {data.slice(0, 10).map((item, i) => (
            <div key={`${item.lobbyist_slug}-${i}`} className="px-6 py-4 hover:bg-zinc-800/40 transition-colors">
              <div className="flex items-start gap-3">
                <span className="mt-0.5 text-xl" aria-hidden="true">&#128682;</span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-zinc-200">
                    <Link href={`/entities/person/${item.lobbyist_slug}`} className="font-semibold hover:text-amber-400">
                      {item.lobbyist_name}
                    </Link>
                    {' '}used to work for{' '}
                    <Link href={`/officials/${item.official_slug}`} className="font-semibold hover:text-amber-400">
                      {item.official_name}
                    </Link>
                    {' '}
                    <PartyBadge party={item.official_party} />
                    {' '}and now lobbies for private clients.
                  </p>
                  {item.former_position && (
                    <p className="mt-1 text-xs text-zinc-500 line-clamp-1">
                      Former role: {item.former_position}
                    </p>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function HomePage() {
  const [stats, setStats] = useState<DashboardStats>(defaultStats);
  const [activeBills, setActiveBills] = useState<ActiveBill[]>([]);
  const [topConflicts, setTopConflicts] = useState<TopConflict[]>([]);
  const [topInfluencers, setTopInfluencers] = useState<TopInfluencer[]>([]);
  const [stateData, setStateData] = useState<StateData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Rotating hero sub-text
  const [subTextIndex, setSubTextIndex] = useState(0);
  const [subTextFade, setSubTextFade] = useState(true);

  // Rotating "Did You Know?" factoid
  const [factIndex, setFactIndex] = useState(0);
  const [factFade, setFactFade] = useState(true);

  // ------ data fetch ------
  useEffect(() => {
    async function fetchAll() {
      try {
        const [s, ab, tc, sd, ti] = await Promise.all([
          getDashboardStats().catch(() => defaultStats),
          getActiveBills().catch(() => []),
          getTopConflicts().catch(() => []),
          getDashboardStates().catch(() => [] as StateMapData[]),
          getTopInfluencers().catch(() => [] as TopInfluencer[]),
        ]);
        setStats(s);
        setActiveBills(ab);
        setTopConflicts(tc);
        setTopInfluencers(ti);
        // Map API data to USMap component format
        setStateData((sd || []).map((s: StateMapData) => ({
          state: s.state,
          abbreviation: '',
          senators: s.senators,
          dominantParty: s.dominantParty,
        })));
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    }
    fetchAll();
  }, []);

  // ------ rotating hero sub-text (every 4s) ------
  useEffect(() => {
    const id = setInterval(() => {
      setSubTextFade(false);
      setTimeout(() => {
        setSubTextIndex((prev) => (prev + 1) % ROTATING_SUBTEXTS.length);
        setSubTextFade(true);
      }, 400);
    }, 4000);
    return () => clearInterval(id);
  }, []);

  // ------ rotating factoid (every 6s) ------
  useEffect(() => {
    const id = setInterval(() => {
      setFactFade(false);
      setTimeout(() => {
        setFactIndex((prev) => (prev + 1) % DID_YOU_KNOW_FACTS.length);
        setFactFade(true);
      }, 400);
    }, 6000);
    return () => clearInterval(id);
  }, []);

  // ========================================================================
  // RENDER
  // ========================================================================

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* ================================================================
          1. HERO SECTION
          ================================================================ */}
      <section className="hero-pattern relative overflow-hidden">
        <div className="hero-grid absolute inset-0" aria-hidden="true" />
        <div className="relative mx-auto max-w-7xl px-4 py-20 sm:px-6 sm:py-28 lg:px-8 lg:py-36">
          <div className="mx-auto max-w-3xl text-center">
            <h1 className="font-mono text-4xl font-black tracking-tighter text-zinc-100 sm:text-5xl lg:text-6xl">
              Follow the Money.{' '}
              <span className="block text-money-gold sm:inline">
                See What They Don&apos;t Want You To.
              </span>
            </h1>

            {/* Rotating sub-text */}
            <p
              className="mx-auto mt-6 h-14 max-w-2xl text-base italic text-zinc-400 transition-opacity duration-400 sm:text-lg"
              style={{ opacity: subTextFade ? 1 : 0 }}
            >
              &ldquo;{ROTATING_SUBTEXTS[subTextIndex]}&rdquo;
            </p>

            {/* Search bar */}
            <div className="mx-auto mt-8 max-w-2xl">
              <SearchBar size="large" />
            </div>

            {/* Quick links */}
            <div className="mt-5 flex flex-wrap items-center justify-center gap-x-1 gap-y-2 text-sm text-zinc-500">
              <span>Try:</span>
              <Link
                href="/officials/john-fetterman"
                className="rounded-md px-2 py-0.5 font-medium text-money-gold transition-colors hover:bg-money-gold/10 hover:text-money-gold-hover"
              >
                John Fetterman
              </Link>
              <span className="text-zinc-700">|</span>
              <Link
                href="/search?q=Banking+Committee"
                className="rounded-md px-2 py-0.5 font-medium text-money-gold transition-colors hover:bg-money-gold/10 hover:text-money-gold-hover"
              >
                Banking Committee
              </Link>
              <span className="text-zinc-700">|</span>
              <Link
                href="/search?q=JPMorgan+Chase"
                className="rounded-md px-2 py-0.5 font-medium text-money-gold transition-colors hover:bg-money-gold/10 hover:text-money-gold-hover"
              >
                JPMorgan Chase
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ================================================================
          2. BROWSE BY STATE — Interactive US Map
          ================================================================ */}
      {stateData.length > 0 && (
        <section className="border-t border-zinc-800 bg-zinc-950">
          <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
            <div className="mb-8 text-center">
              <h2 className="font-mono text-2xl font-bold uppercase tracking-wider text-zinc-100 sm:text-3xl">
                Browse by State
              </h2>
              <p className="mx-auto mt-3 max-w-xl text-sm text-zinc-500">
                Click any state to see its senators and their financial connections.
                Colors show the dominant party.
              </p>
            </div>
            <USMap stateData={stateData} />
          </div>
        </section>
      )}

      {/* ================================================================
          3. HIGHEST CONFLICT RISK — Officials with multi-factor conflicts
          ================================================================ */}
      <section className="border-t border-zinc-800 bg-zinc-950">
        <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
          <div className="mb-10 text-center">
            <h2 className="font-mono text-2xl font-bold uppercase tracking-wider text-zinc-100 sm:text-3xl">
              Highest Conflict Risk
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-sm text-zinc-500">
              Officials where the money trail connects multiple dots &mdash; donors,
              committees, votes, and stock holdings all pointing the same direction.
            </p>
          </div>

          {loading ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-36 animate-pulse rounded-xl bg-zinc-800/50" />
              ))}
            </div>
          ) : topConflicts.length === 0 ? (
            <div className="py-12 text-center text-sm text-zinc-600">
              Conflict analysis in progress. Check back soon.
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {topConflicts.map((official, index) => (
                <Link
                  key={official.slug}
                  href={`/officials/${official.slug}`}
                  className="group relative rounded-xl border border-zinc-800 bg-zinc-900 p-5 transition-all hover:border-orange-500/30 hover:bg-zinc-900/90"
                >
                  <div className="flex items-start gap-3">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-orange-500/10 font-mono text-sm font-bold text-orange-400">
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="truncate text-sm font-semibold text-zinc-200 group-hover:text-money-gold">
                          {official.name}
                        </h3>
                        <PartyBadge party={official.party} />
                      </div>
                      <span className="text-xs text-zinc-500">{official.state}</span>
                    </div>
                    <ConflictBadge severity={official.conflict_score} size="sm" />
                  </div>
                  <p className="mt-3 line-clamp-2 text-xs leading-relaxed text-zinc-400">
                    {official.top_conflict}
                  </p>
                  <div className="mt-3 flex items-center justify-between">
                    <span className="text-xs text-orange-400/70">
                      {official.total_conflicts} {official.total_conflicts > 20 ? 'donors' : 'conflict signal' + (official.total_conflicts !== 1 ? 's' : '')}
                    </span>
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-money-gold opacity-0 transition-opacity group-hover:opacity-100">
                      Investigate <ArrowRight className="h-3 w-3" />
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}

          <div className="mt-6 text-center">
            <Link
              href="/officials"
              className="inline-flex items-center gap-2 text-sm font-medium text-money-gold transition-colors hover:text-money-gold-hover"
            >
              Browse all officials <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      {/* ================================================================
          3b. MOST INFLUENTIAL ENTITIES — Who has the most political reach
          ================================================================ */}
      {topInfluencers.length > 0 && (
        <section className="border-t border-zinc-800 bg-zinc-950">
          <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
            <div className="mb-10 text-center">
              <h2 className="font-mono text-2xl font-bold uppercase tracking-wider text-zinc-100 sm:text-3xl">
                Most Influential Entities
              </h2>
              <p className="mx-auto mt-3 max-w-xl text-sm text-zinc-500">
                The organizations and PACs that fund the most officials.
                Click any name to see who they own.
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {topInfluencers.map((entity, index) => {
                const href = entity.entity_type === 'person'
                  ? `/officials/${entity.slug}`
                  : `/entities/${entity.entity_type}/${entity.slug}`;
                return (
                  <Link
                    key={entity.slug}
                    href={href}
                    className="group rounded-xl border border-zinc-800 bg-zinc-900 p-5 transition-all hover:border-emerald-500/30 hover:bg-zinc-900/90"
                  >
                    <div className="flex items-start gap-3">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-500/10 font-mono text-sm font-bold text-emerald-400">
                        {index + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <h3 className="truncate text-sm font-semibold text-zinc-200 group-hover:text-money-gold">
                          {entity.name}
                        </h3>
                        <span className="inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium bg-emerald-500/20 text-emerald-400 mt-1">
                          {entity.entity_type === 'pac' ? 'PAC' : entity.entity_type === 'organization' ? 'Organization' : 'Company'}
                        </span>
                      </div>
                    </div>
                    <div className="mt-3 flex items-center justify-between text-xs">
                      <span className="text-zinc-400">
                        <span className="font-semibold text-money-success">{formatMoney(entity.total_donated)}</span> donated
                      </span>
                      <span className="text-zinc-500">
                        {entity.officials_funded} official{entity.officials_funded !== 1 ? 's' : ''} funded
                      </span>
                    </div>
                    <span className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-money-gold opacity-0 transition-opacity group-hover:opacity-100">
                      See who they fund <ArrowRight className="h-3 w-3" />
                    </span>
                  </Link>
                );
              })}
            </div>
          </div>
        </section>
      )}

      {/* ================================================================
          3. DASHBOARD STATS
          ================================================================ */}
      <section className="border-t border-zinc-800 bg-zinc-950">
        <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
          <div className="mb-8 text-center">
            <h2 className="font-mono text-xl font-bold uppercase tracking-wider text-zinc-100">
              By the Numbers
            </h2>
          </div>
          {loading ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              {Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={i}
                  className="h-28 animate-pulse rounded-xl bg-zinc-800/50"
                />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              <StatCard
                label="Officials Profiled"
                value={stats.officials_count}
                icon={<Users className="h-5 w-5 text-money-gold" />}
              />
              <StatCard
                label="Bills Tracked"
                value={stats.bills_count}
                icon={<BarChart3 className="h-5 w-5 text-money-gold" />}
              />
              <StatCard
                label="Donations Mapped"
                value={formatMoney(stats.donations_total, { fromCents: true })}
                icon={<TrendingUp className="h-5 w-5 text-money-gold" />}
              />
              <StatCard
                label="Relationships Mapped"
                value={stats.conflicts_count}
                icon={<AlertTriangle className="h-5 w-5 text-money-gold" />}
              />
              <StatCard
                label="Lobbying Links"
                value={stats.lobbying_count}
                icon={<Shield className="h-5 w-5 text-money-gold" />}
              />
            </div>
          )}
        </div>
      </section>

      {/* ================================================================
          4. REVOLVING DOOR — Real LDA data
          ================================================================ */}
      <RevolvingDoorSection />

      {/* ================================================================
          5. ACTIVE INTELLIGENCE — Bills
          ================================================================ */}
      <section className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-xl border border-money-gold/20 bg-zinc-900/80">
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-[0.03]">
            <span className="rotate-[-15deg] select-none font-mono text-6xl font-black tracking-widest text-money-gold sm:text-8xl">
              UNCLASSIFIED
            </span>
          </div>

          <div className="relative">
            <div className="flex items-center justify-between border-b border-money-gold/10 px-6 py-4">
              <div className="flex items-center gap-3">
                <Activity className="h-5 w-5 text-money-gold" />
                <h2 className="font-mono text-lg font-bold uppercase tracking-wider text-money-gold">
                  Active Intelligence
                </h2>
              </div>
              <span className="hidden font-mono text-[10px] uppercase tracking-widest text-zinc-700 sm:inline">
                UNCLASSIFIED // FOR OFFICIAL USE ONLY
              </span>
            </div>

            <div className="divide-y divide-zinc-800/50">
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <div
                    key={i}
                    className="flex h-14 animate-pulse items-center px-6"
                  >
                    <div className="h-4 w-full rounded bg-zinc-800/50" />
                  </div>
                ))
              ) : activeBills.length === 0 ? (
                <div className="px-6 py-12 text-center text-sm text-zinc-600">
                  No active bills being tracked. Intelligence feed offline.
                </div>
              ) : (
                activeBills.slice(0, 10).map((bill) => (
                  <Link
                    key={bill.slug}
                    href={`/bills/${bill.slug}`}
                    className="group flex items-center gap-4 px-6 py-3 transition-colors hover:bg-zinc-800/40"
                  >
                    <StatusBadge status={bill.status} />
                    <span className="min-w-0 flex-1">
                      <span className="font-mono text-xs text-zinc-500">
                        {bill.number}
                      </span>{' '}
                      <span className="text-sm text-zinc-300 group-hover:text-zinc-100">
                        {truncate(bill.title, 80)}
                      </span>
                    </span>
                    <ConflictBadge severity={bill.conflict_score} size="sm" />
                    <span className="hidden font-mono text-xs text-zinc-600 sm:inline">
                      {formatDate(bill.update_date)}
                    </span>
                  </Link>
                ))
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Top Conflicts section moved to "Highest Conflict Risk" above */}

      {/* ================================================================
          7. "DID YOU KNOW?" FACTOID BAR
          ================================================================ */}
      <section className="border-t border-amber-500/20 bg-amber-500/5">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-center gap-3 text-center">
            <span className="hidden shrink-0 font-mono text-xs font-bold uppercase tracking-wider text-amber-500 sm:inline">
              Did you know?
            </span>
            <span className="text-zinc-700 hidden sm:inline">|</span>
            <p
              className="text-sm text-zinc-300 transition-opacity duration-400"
              style={{ opacity: factFade ? 1 : 0 }}
            >
              {DID_YOU_KNOW_FACTS[factIndex]}
            </p>
          </div>
        </div>
      </section>

      {/* ================================================================
          8. BROWSE LINKS
          ================================================================ */}
      <section className="border-t border-zinc-800 bg-zinc-900/30">
        <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
          <div className="grid gap-6 sm:grid-cols-3">
            <Link
              href="/officials"
              className="group flex items-center gap-4 rounded-xl border border-zinc-800 bg-zinc-900/80 p-6 transition-all hover:border-money-gold/30 hover:bg-zinc-800/60"
            >
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-money-gold/10">
                <Users className="h-6 w-6 text-money-gold" />
              </div>
              <div>
                <h3 className="font-semibold text-zinc-200 group-hover:text-money-gold">
                  Browse Officials
                </h3>
                <p className="mt-1 text-xs text-zinc-500">
                  All 535 members of Congress profiled
                </p>
              </div>
            </Link>

            <Link
              href="/trades"
              className="group flex items-center gap-4 rounded-xl border border-zinc-800 bg-zinc-900/80 p-6 transition-all hover:border-money-gold/30 hover:bg-zinc-800/60"
            >
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-money-gold/10">
                <TrendingUp className="h-6 w-6 text-money-gold" />
              </div>
              <div>
                <h3 className="font-semibold text-zinc-200 group-hover:text-money-gold">
                  Stock Trades
                </h3>
                <p className="mt-1 text-xs text-zinc-500">
                  Congressional trading activity and timing analysis
                </p>
              </div>
            </Link>

            <Link
              href="/search"
              className="group flex items-center gap-4 rounded-xl border border-zinc-800 bg-zinc-900/80 p-6 transition-all hover:border-money-gold/30 hover:bg-zinc-800/60"
            >
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-money-gold/10">
                <Shield className="h-6 w-6 text-money-gold" />
              </div>
              <div>
                <h3 className="font-semibold text-zinc-200 group-hover:text-money-gold">
                  Investigate
                </h3>
                <p className="mt-1 text-xs text-zinc-500">
                  Search politicians, companies, bills, PACs
                </p>
              </div>
            </Link>
          </div>
        </div>
      </section>

      {/* Error banner */}
      {error && (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-lg border border-red-500/30 bg-red-950/90 px-6 py-3 text-sm text-red-300 shadow-xl">
          Some dashboard data failed to load. Showing cached results.
        </div>
      )}
    </div>
  );
}
