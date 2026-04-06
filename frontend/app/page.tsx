'use client';

import { useState, useEffect, FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Search, TrendingUp, Users, Shield, AlertTriangle, ArrowRight, Clock, Database, Activity } from 'lucide-react';
import { getV2Homepage } from '@/lib/api';
import type { V2HomepageResponse, V2StoryCard, V2TopOfficial } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import PartyBadge from '@/components/PartyBadge';

// ---------------------------------------------------------------------------
// Date helpers
// ---------------------------------------------------------------------------

function fmtDate(d: string | null | undefined): string {
  if (!d) return '';
  try {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return ''; }
}

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return '';
  try {
    const date = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return fmtDate(iso);
  } catch { return ''; }
}

// ---------------------------------------------------------------------------
// Verdict helpers
// ---------------------------------------------------------------------------

const VERDICT_CONFIG: Record<string, { dot: string; bg: string; text: string; border: string; label: string }> = {
  NORMAL: { dot: 'bg-green-500', bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/30', label: 'NORMAL' },
  CONNECTED: { dot: 'bg-yellow-500', bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30', label: 'CONNECTED' },
  INFLUENCED: { dot: 'bg-red-500', bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30', label: 'INFLUENCED' },
  OWNED: { dot: 'bg-red-800', bg: 'bg-red-900/30', text: 'text-red-300', border: 'border-red-800/50', label: 'OWNED' },
};

function getVerdict(v: string | undefined) {
  if (!v) return VERDICT_CONFIG.NORMAL;
  return VERDICT_CONFIG[v.toUpperCase()] ?? VERDICT_CONFIG.NORMAL;
}

const VERDICT_SEVERITY: Record<string, number> = { OWNED: 4, INFLUENCED: 3, CONNECTED: 2, NORMAL: 1 };

function verdictSeverity(v: string | undefined): number {
  if (!v) return 0;
  return VERDICT_SEVERITY[v.toUpperCase()] ?? 0;
}

const STORY_TYPE_LABELS: Record<string, { label: string; color: string }> = {
  owned: { label: 'OWNED', color: 'text-red-300 bg-red-900/30 border-red-800/50' },
  influenced: { label: 'INFLUENCED', color: 'text-red-400 bg-red-500/10 border-red-500/30' },
  middleman: { label: 'MIDDLEMAN', color: 'text-amber-400 bg-amber-500/10 border-amber-500/30' },
  revolving_door: { label: 'REVOLVING DOOR', color: 'text-purple-400 bg-purple-500/10 border-purple-500/30' },
};

// ---------------------------------------------------------------------------
// Skeleton components
// ---------------------------------------------------------------------------

function SkeletonBar({ className }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-zinc-800 ${className ?? ''}`} />;
}

function SkeletonStoryCard() {
  return (
    <div className="rounded-xl bg-zinc-900 border border-zinc-800 p-5 mb-4">
      <div className="flex items-center gap-2 mb-3">
        <SkeletonBar className="w-3 h-3 rounded-full" />
        <SkeletonBar className="h-5 w-3/4" />
      </div>
      <SkeletonBar className="h-4 w-full mb-2" />
      <SkeletonBar className="h-4 w-5/6 mb-4" />
      <div className="flex gap-2">
        <SkeletonBar className="h-6 w-20 rounded-full" />
        <SkeletonBar className="h-6 w-24 rounded-full" />
      </div>
    </div>
  );
}

function SkeletonOfficialCard() {
  return (
    <div className="rounded-xl bg-zinc-900 border border-zinc-800 p-4">
      <SkeletonBar className="h-5 w-2/3 mb-2" />
      <SkeletonBar className="h-4 w-1/3 mb-3" />
      <SkeletonBar className="h-6 w-24 rounded-full" />
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* Header skeleton */}
      <div className="text-center pt-16 pb-12 px-4">
        <SkeletonBar className="h-4 w-48 mx-auto mb-4" />
        <SkeletonBar className="h-10 w-96 mx-auto mb-8" />
        <SkeletonBar className="h-14 w-full max-w-xl mx-auto rounded-xl" />
      </div>

      <div className="max-w-6xl mx-auto px-4">
        {/* Stories skeleton */}
        <SkeletonBar className="h-7 w-48 mb-6" />
        <div className="space-y-4 mb-12">
          <SkeletonStoryCard />
          <SkeletonStoryCard />
          <SkeletonStoryCard />
        </div>

        {/* Officials skeleton */}
        <SkeletonBar className="h-7 w-64 mb-6" />
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-12">
          {Array.from({ length: 8 }).map((_, i) => (
            <SkeletonOfficialCard key={i} />
          ))}
        </div>

        {/* Stats skeleton */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-zinc-800 rounded-xl overflow-hidden">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="bg-zinc-900 p-6 text-center">
              <SkeletonBar className="h-8 w-24 mx-auto mb-2" />
              <SkeletonBar className="h-3 w-20 mx-auto" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Story Card
// ---------------------------------------------------------------------------

function StoryFeedCard({ story }: { story: V2StoryCard }) {
  const router = useRouter();
  const v = getVerdict(story.verdict);
  const storyType = STORY_TYPE_LABELS[story.story_type] ?? { label: story.story_type.toUpperCase(), color: 'text-zinc-400 bg-zinc-800 border-zinc-700' };

  const firstEntity = story.officials[0];
  const getEntityHref = (o: { slug: string; entity_type?: string }) => {
    const t = o.entity_type || 'person';
    if (t === 'person') return `/officials/${o.slug}`;
    return `/entities/${t}/${o.slug}`;
  };

  return (
    <div
      className="block rounded-xl bg-zinc-900 border border-zinc-800 p-5 mb-4 hover:border-zinc-700 transition-colors cursor-pointer"
      onClick={() => firstEntity && router.push(getEntityHref(firstEntity))}
    >
      {/* Header: verdict dot + headline */}
      <div className="flex items-start gap-3 mb-3">
        <span className={`mt-1.5 w-3 h-3 rounded-full shrink-0 ${v.dot}`} />
        <h3 className="font-bold text-lg leading-snug">{story.headline}</h3>
      </div>

      {/* Narrative */}
      <p className="text-zinc-400 text-sm leading-relaxed mb-4 ml-6">{story.narrative}</p>

      {/* Footer: officials, amount, type badge */}
      <div className="flex flex-wrap items-center gap-2 ml-6">
        {story.officials.map((o) => (
          <Link
            key={o.slug}
            href={getEntityHref(o)}
            className="inline-flex items-center gap-1.5 text-sm hover:text-[#d4a017] transition-colors"
            onClick={(e) => e.stopPropagation()}
          >
            <span className="font-medium">{o.name}</span>
            <PartyBadge party={o.party} className="text-[0.6rem] px-1.5 py-0" />
          </Link>
        ))}

        {story.total_amount > 0 && (
          <span className="text-money-success font-semibold text-sm ml-auto">
            {formatMoney(story.total_amount)}
          </span>
        )}

        <span className={`text-[0.65rem] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full border ${storyType.color}`}>
          {storyType.label}
        </span>

        {/* Date provenance */}
        {(story.fec_cycle || story.computed_at) && (
          <span className="text-[0.6rem] text-zinc-600 ml-auto flex items-center gap-1">
            <Database className="w-3 h-3" />
            {story.fec_cycle ? `${story.fec_cycle} cycle` : relativeTime(story.computed_at)}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Official Card
// ---------------------------------------------------------------------------

function OfficialCard({ official }: { official: V2TopOfficial }) {
  const v = getVerdict(official.verdict);

  return (
    <Link
      href={`/officials/${official.slug}`}
      className="block rounded-xl bg-zinc-900 border border-zinc-800 p-4 hover:border-zinc-600 transition-colors group"
    >
      <div className="font-semibold group-hover:text-[#d4a017] transition-colors mb-1">{official.name}</div>
      <div className="flex items-center gap-2 mb-3">
        <PartyBadge party={official.party} className="text-[0.65rem]" />
        <span className="text-xs text-zinc-500">{official.state}</span>
      </div>
      <div className="flex items-center justify-between">
        <span className={`text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded-full border ${v.bg} ${v.text} ${v.border}`}>
          {v.label}
        </span>
        <span className="text-xs text-zinc-500">{official.dot_count} dots</span>
      </div>
      {official.fec_cycle && (
        <div className="text-[0.6rem] text-zinc-600 mt-2 flex items-center gap-1">
          <Database className="w-3 h-3" />
          FEC {official.fec_cycle} cycle
        </div>
      )}
    </Link>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function HomePage() {
  const router = useRouter();
  const [data, setData] = useState<V2HomepageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    getV2Homepage()
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function handleSearch(e: FormEvent) {
    e.preventDefault();
    const q = searchQuery.trim();
    if (q) router.push(`/search?q=${encodeURIComponent(q)}`);
  }

  if (loading) return <LoadingSkeleton />;

  if (!data) {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="text-center text-zinc-500">
          <AlertTriangle className="w-10 h-10 mx-auto mb-3 text-zinc-600" />
          <p className="text-lg">Failed to load homepage data.</p>
        </div>
      </div>
    );
  }

  const { top_stories, stats, top_officials, recent_activity } = data;

  // Sort officials by verdict severity (worst first)
  const sortedOfficials = [...top_officials].sort((a, b) => verdictSeverity(b.verdict) - verdictSeverity(a.verdict));

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* ----------------------------------------------------------------- */}
      {/* HEADER                                                            */}
      {/* ----------------------------------------------------------------- */}
      <header className="relative text-center pt-16 pb-12 px-4 overflow-hidden">
        {/* Subtle radial glow */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{ background: 'radial-gradient(ellipse at center top, rgba(212,160,23,0.08) 0%, transparent 60%)' }}
        />

        <p className="relative text-xs font-bold uppercase tracking-[0.35em] text-[#d4a017] mb-4">
          Follow the Money
        </p>
        <h1 className="relative text-4xl md:text-5xl font-extrabold mb-8 leading-tight">
          Who Owns Your Representative?
        </h1>

        {/* Search bar */}
        <form onSubmit={handleSearch} className="relative max-w-xl mx-auto">
          <div className="flex items-center bg-zinc-900 border border-zinc-700 rounded-xl overflow-hidden focus-within:border-[#d4a017]/60 transition-colors">
            <Search className="w-5 h-5 text-zinc-500 ml-4 shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search officials, bills, companies..."
              className="w-full bg-transparent px-4 py-4 text-zinc-100 placeholder:text-zinc-500 outline-none text-base"
            />
            <button
              type="submit"
              className="shrink-0 bg-[#d4a017] hover:bg-[#b8891a] text-zinc-950 font-semibold px-6 py-4 transition-colors"
            >
              Search
            </button>
          </div>
        </form>
      </header>

      <div className="max-w-6xl mx-auto px-4 pb-16">
        {/* ----------------------------------------------------------------- */}
        {/* STORY FEED                                                        */}
        {/* ----------------------------------------------------------------- */}
        {top_stories.length > 0 && (
          <section className="mb-14">
            <div className="flex items-center gap-2 mb-6">
              <TrendingUp className="w-5 h-5 text-[#d4a017]" />
              <h2 className="text-xl font-bold">Top Money Trails</h2>
            </div>
            {top_stories.map((story, i) => (
              <StoryFeedCard key={i} story={story} />
            ))}
          </section>
        )}

        {/* ----------------------------------------------------------------- */}
        {/* TOP OFFICIALS BY VERDICT                                          */}
        {/* ----------------------------------------------------------------- */}
        {sortedOfficials.length > 0 && (
          <section className="mb-14">
            <div className="flex items-center gap-2 mb-6">
              <Shield className="w-5 h-5 text-[#d4a017]" />
              <h2 className="text-xl font-bold">Top Officials by Verdict</h2>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
              {sortedOfficials.map((o) => (
                <OfficialCard key={o.slug} official={o} />
              ))}
            </div>
          </section>
        )}

        {/* ----------------------------------------------------------------- */}
        {/* DATA FRESHNESS                                                    */}
        {/* ----------------------------------------------------------------- */}
        <div className="flex flex-wrap items-center gap-4 mb-8 text-xs text-zinc-500">
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5" />
            <span>Data as of: {data.data_as_of ? relativeTime(data.data_as_of) : fmtDate(new Date().toISOString())}</span>
          </div>
          {data.fec_cycle && (
            <div className="flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5" />
              <span>FEC {data.fec_cycle} cycle</span>
            </div>
          )}
        </div>

        {/* ----------------------------------------------------------------- */}
        {/* STATS BAR                                                         */}
        {/* ----------------------------------------------------------------- */}
        <section>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-zinc-800 rounded-xl overflow-hidden">
            {[
              { icon: Users, n: stats.officials_count.toLocaleString(), label: 'Officials Profiled' },
              { icon: Shield, n: stats.bills_count.toLocaleString(), label: 'Bills Tracked' },
              { icon: TrendingUp, n: formatMoney(stats.donations_total), label: 'Money Mapped' },
              { icon: ArrowRight, n: stats.relationship_count.toLocaleString(), label: 'Relationships' },
            ].map((s, i) => {
              const Icon = s.icon;
              return (
                <div key={i} className="bg-zinc-900 p-6 text-center">
                  <Icon className="w-5 h-5 text-zinc-600 mx-auto mb-2" />
                  <div className="text-2xl font-bold text-[#d4a017]">{s.n}</div>
                  <div className="text-[0.7rem] text-zinc-500 uppercase tracking-wide mt-1">{s.label}</div>
                </div>
              );
            })}
          </div>
        </section>

        {/* ----------------------------------------------------------------- */}
        {/* LATEST ACTIVITY                                                    */}
        {/* ----------------------------------------------------------------- */}
        <section className="mt-10">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Activity className="w-5 h-5 text-[#d4a017]" />
              <h2 className="text-xl font-bold">Latest Activity</h2>
            </div>
            <Link href="/activity" className="text-xs text-money-gold hover:underline">
              View all
            </Link>
          </div>
          {recent_activity && recent_activity.length > 0 ? (
            <div className="space-y-3">
              {recent_activity.slice(0, 5).map((event: Record<string, string>) => {
                const typeColors: Record<string, string> = {
                  new_trade: 'bg-emerald-500',
                  verdict_change: 'bg-red-500',
                  new_conflict: 'bg-orange-500',
                  data_refresh: 'bg-blue-500',
                  system: 'bg-zinc-500',
                };
                const typeBadge: Record<string, string> = {
                  new_trade: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
                  verdict_change: 'text-red-400 bg-red-500/10 border-red-500/30',
                  new_conflict: 'text-orange-400 bg-orange-500/10 border-orange-500/30',
                  data_refresh: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
                  system: 'text-zinc-400 bg-zinc-500/10 border-zinc-500/30',
                };
                const typeLabels: Record<string, string> = {
                  new_trade: 'Trade',
                  verdict_change: 'Verdict',
                  new_conflict: 'Conflict',
                  data_refresh: 'Update',
                  system: 'System',
                };
                const dotColor = typeColors[event.event_type] || 'bg-zinc-500';
                const badge = typeBadge[event.event_type] || typeBadge.system;
                const label = typeLabels[event.event_type] || event.event_type;
                const isClickable = !!event.entity_slug;

                const card = (
                  <div className={`rounded-lg border border-zinc-800 bg-zinc-900 p-4 transition-colors ${isClickable ? 'hover:border-zinc-600 hover:bg-zinc-800/80 cursor-pointer' : ''}`}>
                    <div className="flex items-start gap-3">
                      <div className={`mt-1.5 h-2.5 w-2.5 rounded-full flex-shrink-0 ${dotColor}`} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`rounded border px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${badge}`}>
                            {label}
                          </span>
                          {event.created_at && (
                            <span className="text-[10px] text-zinc-600">
                              {new Date(event.created_at).toLocaleDateString()}
                            </span>
                          )}
                        </div>
                        <p className="text-sm font-medium text-zinc-100">{event.headline}</p>
                        {event.detail && (
                          <p className="mt-1 text-xs text-zinc-400 line-clamp-2">{event.detail}</p>
                        )}
                        {event.entity_name && (
                          <span className="mt-1.5 inline-block text-xs font-medium text-money-gold">
                            {event.entity_name} &rarr;
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );

                return isClickable ? (
                  <Link key={event.id} href={`/officials/${event.entity_slug}`}>
                    {card}
                  </Link>
                ) : (
                  <div key={event.id}>{card}</div>
                );
              })}
            </div>
          ) : (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-6 text-center text-sm text-zinc-500">
              Activity feed will populate as the system detects new trades, verdict changes, and data updates.
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
