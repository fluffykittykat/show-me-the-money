'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { getV2Official } from '@/lib/api';
import PageControls from '@/components/PageControls';
import type { V2OfficialResponse } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import LoadingState from '@/components/LoadingState';
import PartyBadge from '@/components/PartyBadge';
import VerdictPill from '@/components/VerdictPill';
import AIBriefing from '@/components/AIBriefing';
import MoneyTrailCard from '@/components/MoneyTrailCard';
import VerdictBadge from '@/components/VerdictBadge';
import FreshnessBar from '@/components/FreshnessBar';

export default function OfficialPage() {
  const { slug } = useParams<{ slug: string }>();
  const router = useRouter();
  const [data, setData] = useState<V2OfficialResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [briefing, setBriefing] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    getV2Official(slug)
      .then(d => { setData(d); setBriefing(d.briefing); })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <div className="max-w-[900px] mx-auto p-6"><LoadingState variant="profile" /></div>;
  if (error || !data) return (
    <div className="max-w-[900px] mx-auto p-6 text-center">
      <p className="text-zinc-500 mb-4">Official not found.</p>
      <Link href="/search" className="text-amber-400 hover:underline">Search for officials →</Link>
    </div>
  );

  const { entity, overall_verdict, total_dots, money_trails, top_donors, middlemen, committees, briefing, freshness } = data;
  const meta = (entity.metadata || entity.metadata_ || {}) as Record<string, unknown>;
  const party = (meta.party as string) || '';
  const state = (meta.state as string) || '';
  const chamber = (meta.chamber as string) || '';
  const campaignTotal = meta.campaign_total as number | undefined;
  const fecCycle = meta.best_fec_cycle as string | undefined;

  return (
    <div className="max-w-[900px] mx-auto px-4 py-6">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-1">{entity.name}</h1>
        <div className="flex flex-wrap items-center gap-3 text-sm text-zinc-400 mb-3">
          <PartyBadge party={party} />
          {state && <span>{state}</span>}
          {chamber && <span>{chamber}</span>}
          {committees.length > 0 && <span>{committees.map(c => c.name).join(' · ')}</span>}
        </div>
        <VerdictPill verdict={overall_verdict} dotCount={total_dots} />
        {campaignTotal != null && (
          <div className="text-sm text-zinc-400 mt-2">
            Campaign total: <span className="text-amber-400 font-semibold text-base">{formatMoney(campaignTotal)}</span>
            {fecCycle && <span> ({fecCycle} cycle)</span>}
          </div>
        )}
      </div>

      {/* Page Controls */}
      <PageControls
        slug={slug}
        onBriefingUpdate={(text) => setBriefing(text)}
        onDataRefresh={() => {
          getV2Official(slug).then(setData).catch(() => {});
        }}
      />

      {/* AI Briefing */}
      <AIBriefing briefing={briefing ?? data.briefing} />

      {/* Money Trails */}
      {money_trails.length > 0 ? (
        <div className="mb-8">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">Money Trails</h2>
          {money_trails.map((trail, i) => (
            <MoneyTrailCard key={i} trail={trail} officialName={entity.name} officialSlug={slug} />
          ))}
        </div>
      ) : (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 mb-8 text-center">
          <p className="text-zinc-500">No money trails computed yet. Try refreshing the investigation.</p>
        </div>
      )}

      {/* Top Donors */}
      {top_donors.length > 0 && (
        <div className="mb-8">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">Top Donors</h2>
          <table className="w-full">
            <thead>
              <tr className="text-left text-xs text-zinc-500 uppercase tracking-wide">
                <th className="pb-2 px-3">Donor</th>
                <th className="pb-2 px-3">Type</th>
                <th className="pb-2 px-3 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {top_donors.map((d, i) => (
                <tr key={i} className="border-t border-zinc-900 cursor-pointer hover:bg-zinc-800/60 transition-colors" onClick={() => router.push(`/entities/${d.entity_type}/${d.slug}`)}>
                  <td className="py-2.5 px-3">
                    <Link href={`/entities/${d.entity_type}/${d.slug}`} className="hover:text-amber-400 transition-colors">{d.name}</Link>
                  </td>
                  <td className="py-2.5 px-3 text-zinc-500 text-sm">{d.entity_type}</td>
                  <td className="py-2.5 px-3 text-right text-amber-400 font-semibold">{formatMoney(d.total_donated)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Middlemen */}
      {middlemen.length > 0 && (
        <div className="mb-8">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">Middlemen</h2>
          {middlemen.map((m, i) => (
            <div key={i} onClick={() => router.push(`/entities/pac/${m.slug}`)} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 mb-3 flex justify-between items-center cursor-pointer hover:border-amber-500/50 hover:bg-zinc-800/80 transition-all duration-200">
              <div>
                <span className="font-semibold">{m.name}</span>
                <div className="text-xs text-zinc-500">{m.entity_type}</div>
              </div>
              <div className="text-amber-400 font-semibold">{formatMoney(m.total_donated)}</div>
            </div>
          ))}
        </div>
      )}

      <FreshnessBar freshness={freshness} />
    </div>
  );
}
