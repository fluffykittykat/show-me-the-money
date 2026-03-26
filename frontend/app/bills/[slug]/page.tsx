'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { getV2Bill } from '@/lib/api';
import type { V2BillResponse } from '@/lib/types';
import LoadingState from '@/components/LoadingState';
import PartyBadge from '@/components/PartyBadge';
import VerdictBadge from '@/components/VerdictBadge';
import AIBriefing from '@/components/AIBriefing';
import PageControls from '@/components/PageControls';

const STATUS_COLORS: Record<string, string> = {
  'BECAME LAW': 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
  'PASSED': 'bg-blue-500/20 text-blue-400 border-blue-500/40',
  'IN COMMITTEE': 'bg-amber-500/20 text-amber-400 border-amber-500/40',
  'INTRODUCED': 'bg-zinc-700 text-zinc-300 border-zinc-600',
  'FAILED': 'bg-red-500/20 text-red-400 border-red-500/40',
};

export default function BillPage() {
  const { slug } = useParams<{ slug: string }>();
  const [data, setData] = useState<V2BillResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [briefing, setBriefing] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    getV2Bill(slug)
      .then(d => { setData(d); setBriefing(d.briefing); })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <div className="max-w-[900px] mx-auto p-6"><LoadingState variant="profile" /></div>;
  if (error || !data) return (
    <div className="max-w-[900px] mx-auto p-6 text-center">
      <p className="text-zinc-500 mb-4">Bill not found.</p>
      <Link href="/search" className="text-amber-400 hover:underline">Search for bills →</Link>
    </div>
  );

  const { entity, status_label, sponsors, briefing } = data;
  const meta = (entity.metadata || entity.metadata_ || {}) as Record<string, unknown>;
  const summary = (meta.crs_summary || meta.summary || entity.summary) as string | null;
  const statusStyle = STATUS_COLORS[status_label] || STATUS_COLORS['INTRODUCED'];
  const primarySponsors = sponsors.filter(s => s.role === 'sponsored');
  const cosponsors = sponsors.filter(s => s.role === 'cosponsored');

  return (
    <div className="max-w-[900px] mx-auto px-4 py-6">
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <span className={`text-xs font-bold px-2.5 py-1 rounded border ${statusStyle}`}>{status_label}</span>
        </div>
        <h1 className="text-2xl font-bold mb-2">{entity.name}</h1>
        {summary && <p className="text-zinc-400 text-sm leading-relaxed">{summary}</p>}
      </div>

      {/* Page Controls */}
      <PageControls
        slug={slug}
        onBriefingUpdate={(text) => setBriefing(text)}
        onDataRefresh={() => {
          getV2Bill(slug).then(setData).catch(() => {});
        }}
      />

      <AIBriefing briefing={briefing ?? data.briefing} />

      {primarySponsors.length > 0 && (
        <div className="mb-8">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">Sponsors</h2>
          <div className="grid gap-3">
            {primarySponsors.map((s, i) => (
              <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div>
                    <Link href={`/officials/${s.slug}`} className="font-semibold hover:text-amber-400 transition-colors">{s.name}</Link>
                    <div className="flex items-center gap-2 mt-0.5">
                      <PartyBadge party={s.party} />
                      {s.state && <span className="text-xs text-zinc-500">{s.state}</span>}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {s.top_donor && <span className="text-xs text-zinc-500">Top donor: {s.top_donor}</span>}
                  {s.verdict && <VerdictBadge verdict={s.verdict} />}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {cosponsors.length > 0 && (
        <div className="mb-8">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">Cosponsors</h2>
          <div className="grid gap-2">
            {cosponsors.map((s, i) => (
              <div key={i} className="flex items-center justify-between py-2 border-b border-zinc-900 last:border-0">
                <div className="flex items-center gap-3">
                  <Link href={`/officials/${s.slug}`} className="font-medium hover:text-amber-400 transition-colors text-sm">{s.name}</Link>
                  <PartyBadge party={s.party} />
                  {s.state && <span className="text-xs text-zinc-500">{s.state}</span>}
                </div>
                <div className="flex items-center gap-2">
                  {s.verdict && <VerdictBadge verdict={s.verdict} />}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
