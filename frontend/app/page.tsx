'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { RefreshCw, Loader2 } from 'lucide-react';
import { getV2Homepage } from '@/lib/api';
import type { V2HomepageResponse } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import SearchBar from '@/components/SearchBar';
import LoadingState from '@/components/LoadingState';
import StoryCard from '@/components/StoryCard';
import HighlightCard from '@/components/HighlightCard';
import VerdictBadge from '@/components/VerdictBadge';

export default function HomePage() {
  const router = useRouter();
  const [data, setData] = useState<V2HomepageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadedAt] = useState(() => new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }));

  useEffect(() => {
    getV2Homepage()
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function handleRefresh() {
    setRefreshing(true);
    getV2Homepage()
      .then(setData)
      .catch(() => {})
      .finally(() => setRefreshing(false));
  }

  if (loading) return <div className="max-w-[900px] mx-auto p-6"><LoadingState variant="profile" /></div>;
  if (!data) return <div className="max-w-[900px] mx-auto p-6 text-center text-zinc-500">Failed to load homepage data.</div>;

  const { top_stories, stats, top_officials, top_influencers, revolving_door } = data;
  const mostBought = top_officials[0];
  const biggestTrail = top_stories.find(s => s.story_type === 'influenced');
  const biggestMiddleman = top_stories.find(s => s.story_type === 'middleman');

  return (
    <div className="max-w-[900px] mx-auto px-4 py-6">
      {/* Hero */}
      <div className="text-center py-12 pb-10 relative">
        <div className="absolute inset-0 pointer-events-none" style={{ background: 'radial-gradient(ellipse at center, rgba(245,158,11,0.06) 0%, transparent 70%)' }} />
        <h1 className="text-4xl font-extrabold mb-2 relative">
          Follow the <span className="text-amber-500">Money</span>
        </h1>
        <p className="text-zinc-400 mb-7 relative">See what they don&apos;t want you to see.</p>
        <div className="max-w-[560px] mx-auto relative">
          <SearchBar size="large" />
        </div>
        <div className="text-xs text-zinc-600 mt-3 relative">
          Try:{' '}
          <Link href="/officials/fetterman-john" className="text-zinc-400 hover:text-amber-400">John Fetterman</Link>{' · '}
          <Link href="/entities/organization/banking-committee" className="text-zinc-400 hover:text-amber-400">Banking Committee</Link>{' · '}
          <Link href="/entities/company/jpmorgan-chase" className="text-zinc-400 hover:text-amber-400">JPMorgan Chase</Link>
        </div>
        <div className="mt-4 relative">
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-zinc-700 text-zinc-400 text-sm hover:border-amber-500/50 hover:text-amber-400 disabled:opacity-50 transition-all duration-200"
          >
            {refreshing ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
          <span className="text-xs text-zinc-600 ml-3">Updated {loadedAt}</span>
        </div>
      </div>

      {/* Highlight Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-10">
        {mostBought && (
          <HighlightCard label="Most Bought" name={mostBought.name} href={`/officials/${mostBought.slug}`}
            detail={`${mostBought.dot_count} dots`} verdict={mostBought.verdict} borderColor="border-zinc-600/50" />
        )}
        {biggestTrail && (
          <HighlightCard label="Biggest Trail" name={biggestTrail.headline.split(':')[0] || biggestTrail.headline}
            href={biggestTrail.officials[0] ? `/officials/${biggestTrail.officials[0].slug}` : '#'}
            detail={formatMoney(biggestTrail.total_amount)} verdict="INFLUENCED" borderColor="border-red-500/30" />
        )}
        {biggestMiddleman && (
          <HighlightCard label="Biggest Middleman" name={biggestMiddleman.headline.split(' funneled')[0] || biggestMiddleman.headline}
            href="#" detail={formatMoney(biggestMiddleman.total_amount)} verdict="MIDDLEMAN" borderColor="border-amber-500/30" />
        )}
        <HighlightCard label="Revolving Door" name={`${revolving_door.length} Lobbyists`}
          href="#revolving-door" detail="Former staff now lobbying" verdict="REVOLVING_DOOR" borderColor="border-purple-500/30" />
      </div>

      {/* Story Feed */}
      {top_stories.length > 0 && (
        <div className="mb-10">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">Latest Stories</h2>
          {top_stories.map((story, i) => (
            <StoryCard key={i} story={story} />
          ))}
        </div>
      )}

      {/* Stats Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-zinc-800 rounded-xl overflow-hidden mb-10">
        {[
          { n: stats.officials_count.toLocaleString(), label: 'Officials' },
          { n: stats.bills_count.toLocaleString(), label: 'Bills' },
          { n: formatMoney(stats.donations_total), label: 'Donations' },
          { n: stats.relationship_count.toLocaleString(), label: 'Relationships' },
        ].map((s, i) => (
          <div key={i} className="bg-zinc-900 p-4 text-center">
            <div className="text-xl font-bold text-amber-400">{s.n}</div>
            <div className="text-[0.7rem] text-zinc-500 uppercase tracking-wide mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Two-Column */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">Top Officials by Verdict</h2>
          {top_officials.map((o, i) => (
            <div key={o.slug} onClick={() => router.push(`/officials/${o.slug}`)} className="flex items-center justify-between py-3 border-b border-zinc-900 last:border-0 cursor-pointer hover:bg-zinc-800/60 rounded-lg px-2 -mx-2 transition-all duration-200">
              <div className="flex items-center gap-3">
                <span className="text-zinc-600 font-bold w-6">{i + 1}</span>
                <div>
                  <span className="font-semibold">{o.name}</span>
                  <div className="text-xs text-zinc-500">{o.party?.charAt(0)} · {o.state}</div>
                </div>
              </div>
              <VerdictBadge verdict={o.verdict} />
            </div>
          ))}
        </div>
        <div>
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">Top Influencers</h2>
          {top_influencers.map((inf, i) => (
            <div key={inf.slug} onClick={() => router.push(`/entities/${inf.entity_type}/${inf.slug}`)} className="flex items-center justify-between py-3 border-b border-zinc-900 last:border-0 cursor-pointer hover:bg-zinc-800/60 rounded-lg px-2 -mx-2 transition-all duration-200">
              <div className="flex items-center gap-3">
                <span className="text-zinc-600 font-bold w-6">{i + 1}</span>
                <div>
                  <span className="font-semibold">{inf.name}</span>
                  <div className="text-xs text-zinc-500">{inf.entity_type} · {inf.officials_funded} recipients</div>
                </div>
              </div>
              <span className="text-amber-400 font-semibold text-sm">{formatMoney(inf.total_donated)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
