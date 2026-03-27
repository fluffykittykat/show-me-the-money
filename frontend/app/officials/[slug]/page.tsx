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

function fmtDate(d: string | null | undefined): string {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return '—'; }
}

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
      .then(d => {
        // If this person has no official data (no donors, no trails, no committees),
        // redirect to the entity page which shows all relationship types
        const isEmpty = !d.top_donors?.length && !d.money_trails?.length && !d.committees?.length;
        const meta = (d.entity?.metadata || d.entity?.metadata_) as Record<string, unknown> | undefined;
        const isNotOfficial = !meta?.bioguide_id;
        if (isEmpty && isNotOfficial) {
          router.replace(`/entities/${d.entity?.entity_type || 'person'}/${slug}`);
          return;
        }
        setData(d);
        setBriefing(d.briefing);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [slug, router]);

  if (loading) return <div className="max-w-[900px] mx-auto p-6"><LoadingState variant="profile" /></div>;
  if (error || !data) return (
    <div className="max-w-[900px] mx-auto p-6 text-center">
      <p className="text-zinc-500 mb-4">Official not found.</p>
      <Link href="/search" className="text-amber-400 hover:underline">Search for officials →</Link>
    </div>
  );

  const { entity, overall_verdict, total_dots, money_trails, top_donors, middlemen, committees, briefing: dataBriefing, freshness, stock_trades, fec_cycles, total_all_cycles } = data;
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
        {fec_cycles && fec_cycles.length > 0 ? (
          <div className="text-sm text-zinc-400 mt-2">
            Total raised (all cycles): <span className="text-amber-400 font-semibold text-base">{formatMoney(Math.round(total_all_cycles * 100))}</span>
          </div>
        ) : campaignTotal != null && campaignTotal > 0 ? (
          <div className="text-sm text-zinc-400 mt-2">
            Campaign total: <span className="text-amber-400 font-semibold text-base">{formatMoney(Math.round(campaignTotal * 100))}</span>
            {fecCycle && <span className="text-zinc-500"> (best cycle: {fecCycle})</span>}
          </div>
        ) : null}
        <FreshnessBar freshness={freshness} />
      </div>

      {/* Page Controls */}
      <PageControls
        slug={slug}
        entityName={entity.name}
        onBriefingUpdate={(text) => setBriefing(text)}
        onDataRefresh={() => {
          getV2Official(slug).then(d => { setData(d); setBriefing(d.briefing); }).catch(() => {});
        }}
      />

      {/* AI Briefing */}
      <AIBriefing briefing={briefing ?? dataBriefing} />

      {/* Campaign Finance Trend */}
      {fec_cycles && fec_cycles.length > 0 && (() => {
        const sorted = [...fec_cycles].sort((a, b) => a.cycle - b.cycle);
        const maxReceipts = Math.max(...sorted.map(c => c.receipts), 1);
        const totalRaised = sorted.reduce((s, c) => s + c.receipts, 0);
        const totalSpent = sorted.reduce((s, c) => s + c.disbursements, 0);
        // Trend: compare most recent to previous
        const recent = sorted[sorted.length - 1];
        const previous = sorted.length > 1 ? sorted[sorted.length - 2] : null;
        const trendPct = previous && previous.receipts > 0
          ? Math.round(((recent.receipts - previous.receipts) / previous.receipts) * 100)
          : null;

        return (
          <div className="mb-8">
            <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">
              Campaign Finance Trend
            </h2>

            {/* Summary row */}
            <div className="flex flex-wrap gap-6 mb-5">
              <div>
                <div className="text-xs text-zinc-500 uppercase tracking-wide">Total Raised</div>
                <div className="text-2xl font-bold text-amber-400">{formatMoney(Math.round(totalRaised * 100))}</div>
              </div>
              <div>
                <div className="text-xs text-zinc-500 uppercase tracking-wide">Total Spent</div>
                <div className="text-2xl font-bold text-zinc-400">{formatMoney(Math.round(totalSpent * 100))}</div>
              </div>
              <div>
                <div className="text-xs text-zinc-500 uppercase tracking-wide">Cycles</div>
                <div className="text-2xl font-bold text-zinc-300">{sorted.length}</div>
              </div>
              {trendPct !== null && (
                <div>
                  <div className="text-xs text-zinc-500 uppercase tracking-wide">Trend ({previous?.cycle}→{recent.cycle})</div>
                  <div className={`text-2xl font-bold ${trendPct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {trendPct >= 0 ? '+' : ''}{trendPct}%
                  </div>
                </div>
              )}
            </div>

            {/* Bar chart */}
            <div className="flex items-end gap-2 h-40 mb-4">
              {sorted.map((c) => {
                const heightPct = Math.max((c.receipts / maxReceipts) * 100, 2);
                const spentPct = c.disbursements > 0 ? Math.min((c.disbursements / c.receipts) * 100, 100) : 0;
                return (
                  <div key={c.cycle} className="flex-1 flex flex-col items-center gap-1">
                    <div className="text-[10px] text-amber-400 font-semibold">
                      {formatMoney(Math.round(c.receipts * 100))}
                    </div>
                    <div className="w-full relative rounded-t" style={{ height: `${heightPct}%` }}>
                      <div className="absolute inset-0 bg-amber-500/30 rounded-t" />
                      <div
                        className="absolute bottom-0 left-0 right-0 bg-amber-500/60 rounded-t"
                        style={{ height: `${spentPct}%` }}
                        title={`Spent: ${formatMoney(Math.round(c.disbursements * 100))}`}
                      />
                    </div>
                    <div className="text-xs font-mono text-zinc-500">{c.cycle}</div>
                  </div>
                );
              })}
            </div>

            {/* Legend */}
            <div className="flex items-center gap-4 text-xs text-zinc-500 mb-4">
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded bg-amber-500/30" />
                <span>Raised</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-3 rounded bg-amber-500/60" />
                <span>Spent</span>
              </div>
            </div>

            {/* Detail table */}
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-zinc-500 uppercase tracking-wide">
                  <th className="pb-2 px-3">Cycle</th>
                  <th className="pb-2 px-3 text-right">Raised</th>
                  <th className="pb-2 px-3 text-right">Spent</th>
                  <th className="pb-2 px-3 text-right">Net</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((c) => (
                  <tr key={c.cycle} className="border-t border-zinc-900">
                    <td className="py-2 px-3 font-mono">{c.cycle}</td>
                    <td className="py-2 px-3 text-right text-amber-400 font-semibold">{formatMoney(Math.round(c.receipts * 100))}</td>
                    <td className="py-2 px-3 text-right text-zinc-400">{formatMoney(Math.round(c.disbursements * 100))}</td>
                    <td className={`py-2 px-3 text-right font-semibold ${c.receipts - c.disbursements >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatMoney(Math.round((c.receipts - c.disbursements) * 100))}
                    </td>
                  </tr>
                ))}
                <tr className="border-t-2 border-zinc-700 font-bold">
                  <td className="py-2 px-3">Total</td>
                  <td className="py-2 px-3 text-right text-amber-400">{formatMoney(Math.round(totalRaised * 100))}</td>
                  <td className="py-2 px-3 text-right text-zinc-400">{formatMoney(Math.round(totalSpent * 100))}</td>
                  <td className={`py-2 px-3 text-right font-semibold ${totalRaised - totalSpent >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    {formatMoney(Math.round((totalRaised - totalSpent) * 100))}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        );
      })()}

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

      {/* Stock Trades */}
      {stock_trades && stock_trades.length > 0 && (
        <div className="mb-8">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">Stock Trades ({stock_trades.length})</h2>
          <table className="w-full">
            <thead>
              <tr className="text-left text-xs text-zinc-500 uppercase tracking-wide">
                <th className="pb-2 px-3">Date</th>
                <th className="pb-2 px-3">Ticker</th>
                <th className="pb-2 px-3">Type</th>
                <th className="pb-2 px-3 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {stock_trades.map((t, i) => (
                <tr key={i} className="border-t border-zinc-900">
                  <td className="py-2.5 px-3 text-zinc-500 text-sm">{fmtDate(t.date)}</td>
                  <td className="py-2.5 px-3 font-mono font-bold">{t.ticker}</td>
                  <td className="py-2.5 px-3">
                    <span className={t.transaction_type.toLowerCase().includes('purchase') ? 'text-green-400' : 'text-red-400'}>
                      {t.transaction_type}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-right text-zinc-300">{t.amount_range}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
                <th className="pb-2 px-3">Last Donation</th>
                <th className="pb-2 px-3 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {top_donors.map((d, i) => {
                const dn = (d.name || '').toLowerCase().replace(/[^a-z]/g, '');
                const on = (entity.name || '').toLowerCase().replace(/[^a-z]/g, '');
                const slugParts = slug.split('-');
                const isSelf = (dn.length > 5 && on.length > 5 && (dn.includes(on.slice(0, 6)) || on.includes(dn.slice(0, 6))))
                  || (slugParts[0] && dn.includes(slugParts[0]) && (dn.includes('victory') || dn.includes('forcongress') || dn.includes('forsenate') || dn.includes('fund') || dn.includes('committee') || (slugParts[1] && dn.includes(slugParts[1]))));
                return (
                <tr key={i} className="border-t border-zinc-900 cursor-pointer hover:bg-zinc-800/60 transition-colors" onClick={() => router.push(`/entities/${d.entity_type}/${d.slug}`)}>
                  <td className="py-2.5 px-3">
                    <div className="flex items-center gap-2">
                      <Link href={`/entities/${d.entity_type}/${d.slug}`} className="hover:text-amber-400 transition-colors">{d.name}</Link>
                      {isSelf && <span className="text-[10px] font-medium text-blue-400 bg-blue-500/10 px-1.5 py-0.5 rounded">SELF-FUNDED</span>}
                    </div>
                  </td>
                  <td className="py-2.5 px-3 text-zinc-500 text-sm">{d.entity_type}</td>
                  <td className="py-2.5 px-3 text-zinc-600 text-xs">{fmtDate(d.latest_date)}</td>
                  <td className="py-2.5 px-3 text-right text-amber-400 font-semibold">{formatMoney(d.total_donated)}</td>
                </tr>
                );
              })}
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
                <div className="flex items-center gap-2 text-xs text-zinc-500">
                  <span>{m.entity_type}</span>
                  {m.latest_date && <span className="text-zinc-600">{fmtDate(m.latest_date)}</span>}
                </div>
              </div>
              <div className="text-amber-400 font-semibold">{formatMoney(m.total_donated)}</div>
            </div>
          ))}
        </div>
      )}

    </div>
  );
}
