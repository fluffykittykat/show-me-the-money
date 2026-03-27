'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { DollarSign, Users, ScrollText, ExternalLink, ChevronDown, ChevronUp } from 'lucide-react';
import { getV2Bill } from '@/lib/api';
import type { V2BillResponse } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import { Clock } from 'lucide-react';
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
  'ON FLOOR': 'bg-blue-500/20 text-blue-400 border-blue-500/40',
  'FAILED': 'bg-red-500/20 text-red-400 border-red-500/40',
};

function fmtDate(d: string | null | undefined): string {
  if (!d) return '';
  try {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return ''; }
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function SponsorCard({ s, expanded, onToggle }: { s: any; expanded: boolean; onToggle: () => void }) {
  const router = useRouter();
  const topDonors = s.top_donors || [];
  const moneyTrails = s.money_trails || [];
  const latestDonorDate = topDonors.length > 0
    ? topDonors.reduce((latest: string | null, d: { date?: string }) => {
        if (!d.date) return latest;
        if (!latest) return d.date;
        return d.date > latest ? d.date : latest;
      }, null as string | null)
    : null;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden hover:border-zinc-600 transition-colors">
      <div className="p-4 cursor-pointer" onClick={onToggle}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div>
              <Link
                href={`/officials/${s.slug}`}
                className="font-semibold hover:text-amber-400 transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                {s.name}
              </Link>
              <div className="flex items-center gap-2 mt-0.5">
                <PartyBadge party={s.party} />
                {s.state && <span className="text-xs text-zinc-500">{s.state}</span>}
                <span className="text-xs text-zinc-600">{s.role}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {s.donor_total > 0 && (
              <div className="flex flex-col items-end">
                <span className="text-amber-400 font-bold text-sm">{formatMoney(s.donor_total)}</span>
                {latestDonorDate && <span className="text-[0.6rem] text-zinc-600">{fmtDate(latestDonorDate)}</span>}
              </div>
            )}
            {s.verdict && <VerdictBadge verdict={s.verdict} />}
            {(topDonors.length > 0 || moneyTrails.length > 0) && (
              expanded ? <ChevronUp className="w-4 h-4 text-zinc-500" /> : <ChevronDown className="w-4 h-4 text-zinc-500" />
            )}
          </div>
        </div>
      </div>

      {expanded && (topDonors.length > 0 || moneyTrails.length > 0) && (
        <div className="border-t border-zinc-800 px-4 pb-4">
          {/* Top donors for this sponsor */}
          {topDonors.length > 0 && (
            <div className="mt-3">
              <div className="flex items-center gap-2 mb-2">
                <DollarSign className="w-3.5 h-3.5 text-emerald-500" />
                <span className="text-xs font-bold uppercase tracking-widest text-emerald-500">
                  Top Donors to {s.name.split(',')[0]}
                </span>
              </div>
              <div className="space-y-0.5">
                {topDonors.map((d: { name: string; slug: string; entity_type: string; amount: number; date?: string }, i: number) => (
                  <div
                    key={i}
                    className="flex items-center justify-between py-1.5 px-2 rounded-lg hover:bg-zinc-800/60 cursor-pointer transition-colors"
                    onClick={(e) => { e.stopPropagation(); router.push(`/entities/${d.entity_type}/${d.slug}`); }}
                  >
                    <span className="text-sm text-zinc-300 truncate mr-3">{d.name}</span>
                    <div className="flex items-center gap-3 flex-shrink-0">
                      {d.date && <span className="text-xs text-zinc-600">{fmtDate(d.date)}</span>}
                      <span className="text-amber-400 font-semibold text-sm">{formatMoney(d.amount)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Money trails (industry verdicts) for this sponsor */}
          {moneyTrails.length > 0 && (
            <div className="mt-3">
              <div className="flex items-center gap-2 mb-2">
                <ScrollText className="w-3.5 h-3.5 text-red-500" />
                <span className="text-xs font-bold uppercase tracking-widest text-red-500">
                  Industry Influence
                </span>
              </div>
              <div className="flex flex-wrap gap-2">
                {moneyTrails.map((t: { industry: string; verdict: string; dot_count: number; total_amount: number }, i: number) => (
                  <div key={i} className="flex items-center gap-2 bg-zinc-800/50 rounded-lg px-3 py-1.5">
                    <span className="text-sm text-zinc-300">{t.industry}</span>
                    <VerdictBadge verdict={t.verdict} />
                    <span className="text-xs text-amber-400">{formatMoney(t.total_amount)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function BillPage() {
  const { slug } = useParams<{ slug: string }>();
  const [data, setData] = useState<V2BillResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [briefing, setBriefing] = useState<string | null>(null);
  const [expandedSponsors, setExpandedSponsors] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    getV2Bill(slug)
      .then(d => { setData(d); setBriefing(d.briefing); })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [slug]);

  function toggleSponsor(i: number) {
    setExpandedSponsors(prev => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  if (loading) return <div className="max-w-[900px] mx-auto p-6"><LoadingState variant="profile" /></div>;
  if (error || !data) return (
    <div className="max-w-[900px] mx-auto p-6 text-center">
      <p className="text-zinc-500 mb-4">Bill not found.</p>
      <Link href="/search" className="text-amber-400 hover:underline">Search for bills →</Link>
    </div>
  );

  const { entity, status_label, sponsors, briefing: dataBriefing } = data;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const dataAny = data as any;
  const policyArea = dataAny.policy_area || '';
  const totalMoneyBehind = dataAny.total_money_behind || 0;
  const topDonorsAcross = (dataAny.top_donors_across || []) as Array<[string, number]>;
  const votes = (dataAny.votes || []) as Array<{
    chamber?: string; date?: string; result?: string;
    yea?: number; nay?: number; not_voting?: number; url?: string;
  }>;

  const meta = (entity.metadata || entity.metadata_ || {}) as Record<string, unknown>;
  const summary = (meta.crs_summary || meta.summary || entity.summary) as string | null;
  const congressUrl = meta.congress_url as string | undefined;
  const introducedDate = meta.introduced_date as string | undefined;
  const originChamber = meta.origin_chamber as string | undefined;
  const statusStyle = STATUS_COLORS[status_label] || STATUS_COLORS['INTRODUCED'];
  const primarySponsors = sponsors.filter(s => s.role === 'sponsored');
  const cosponsors = sponsors.filter(s => s.role === 'cosponsored');

  return (
    <div className="max-w-[900px] mx-auto px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2 flex-wrap">
          <span className={`text-xs font-bold px-2.5 py-1 rounded border ${statusStyle}`}>{status_label}</span>
          {policyArea && <span className="text-xs text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded">{policyArea}</span>}
          {originChamber && <span className="text-xs text-zinc-600">{originChamber}</span>}
          {introducedDate && <span className="text-xs text-zinc-600">Introduced {fmtDate(introducedDate) || introducedDate}</span>}
        </div>
        <h1 className="text-2xl font-bold mb-2">{entity.name}</h1>
        {summary ? (
          <p className="text-zinc-400 text-sm leading-relaxed">{summary}</p>
        ) : (
          <p className="text-zinc-500 text-sm italic leading-relaxed">
            {meta.status ? `Latest action: ${meta.status}` : 'No summary available for this bill yet. Click Refresh to fetch the latest data from Congress.gov.'}
          </p>
        )}
        {congressUrl && (
          <a href={congressUrl as string} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-amber-400 mt-2 transition-colors">
            <ExternalLink className="w-3 h-3" />
            View on Congress.gov
          </a>
        )}
      </div>

      <PageControls
        slug={slug}
        entityName={entity.name}
        onBriefingUpdate={(text) => setBriefing(text)}
        onDataRefresh={() => {
          getV2Bill(slug).then(d => { setData(d); setBriefing(d.briefing); }).catch(() => {});
        }}
      />

      {/* Page-level freshness */}
      <div className="flex flex-wrap items-center gap-4 mb-4 text-xs text-zinc-500">
        <div className="flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5" />
          <span>Last refreshed: {data.freshness?.last_refreshed ? fmtDate(data.freshness.last_refreshed) : (entity.updated_at ? fmtDate(entity.updated_at) : 'Unknown')}</span>
        </div>
      </div>

      <AIBriefing briefing={briefing ?? dataBriefing} />

      {/* Vote results */}
      {votes.length > 0 && (
        <div className="mb-6">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">Roll Call Votes</h2>
          <div className="space-y-3">
            {votes.map((vote, i) => {
              const yea = vote.yea || 0;
              const nay = vote.nay || 0;
              const total = yea + nay;
              const yeaPct = total > 0 ? (yea / total) * 100 : 0;
              return (
                <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      {vote.chamber && (
                        <span className="text-xs font-bold uppercase tracking-wide text-zinc-400">{vote.chamber}</span>
                      )}
                      {vote.date && <span className="text-xs text-zinc-600">{fmtDate(vote.date) || vote.date}</span>}
                    </div>
                    {vote.url && (
                      <a href={vote.url} target="_blank" rel="noopener noreferrer"
                        className="text-xs text-zinc-500 hover:text-amber-400 transition-colors flex items-center gap-1">
                        <ExternalLink className="w-3 h-3" />
                        Roll call
                      </a>
                    )}
                  </div>
                  {(yea > 0 || nay > 0) && (
                    <>
                      <div className="flex gap-1 h-6 rounded-lg overflow-hidden mb-2">
                        <div className="bg-emerald-500/80 flex items-center justify-center text-xs font-bold text-white"
                          style={{ width: `${yeaPct}%`, minWidth: yea > 0 ? '40px' : '0' }}>
                          {yea}
                        </div>
                        <div className="bg-red-500/80 flex items-center justify-center text-xs font-bold text-white"
                          style={{ width: `${100 - yeaPct}%`, minWidth: nay > 0 ? '40px' : '0' }}>
                          {nay}
                        </div>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-emerald-400">Yea: {yea}</span>
                        <span className="text-red-400">Nay: {nay}</span>
                        {vote.not_voting != null && vote.not_voting > 0 && (
                          <span className="text-zinc-500">Not Voting: {vote.not_voting}</span>
                        )}
                      </div>
                    </>
                  )}
                  {vote.result && (
                    <p className="text-xs text-zinc-400 mt-2">{vote.result}</p>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Money summary bar */}
      {(totalMoneyBehind > 0 || sponsors.length > 0) && (
        <div className="grid grid-cols-3 gap-px bg-zinc-800 rounded-xl overflow-hidden mb-6">
          <div className="bg-zinc-900 p-4 text-center">
            <div className="text-amber-400 text-xl font-bold">{formatMoney(totalMoneyBehind)}</div>
            <div className="text-xs text-zinc-500 uppercase tracking-wide mt-1">Donors → Sponsors</div>
            <div className="text-[0.6rem] text-zinc-600 mt-0.5">Campaign donations to officials who sponsored this bill</div>
          </div>
          <div className="bg-zinc-900 p-4 text-center">
            <div className="text-zinc-100 text-xl font-bold">{primarySponsors.length}</div>
            <div className="text-xs text-zinc-500 uppercase tracking-wide mt-1">Sponsor{primarySponsors.length !== 1 ? 's' : ''}</div>
          </div>
          <div className="bg-zinc-900 p-4 text-center">
            <div className="text-zinc-100 text-xl font-bold">{cosponsors.length}</div>
            <div className="text-xs text-zinc-500 uppercase tracking-wide mt-1">Cosponsor{cosponsors.length !== 1 ? 's' : ''}</div>
          </div>
        </div>
      )}

      {/* Top donors across all sponsors */}
      {topDonorsAcross.length > 0 && (
        <div className="mb-8">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800 flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-emerald-500" />
            Who Funded This Bill&apos;s Sponsors
          </h2>
          <p className="text-zinc-500 text-xs mb-3">These donors gave campaign money to the officials who sponsored this bill. Campaign funds are general — they support all of a sponsor&apos;s work, not just this bill.</p>
          <div className="space-y-0.5">
            {topDonorsAcross.map(([name, amount], i) => (
              <div key={i} className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-zinc-800/60 transition-colors">
                <div className="flex items-center gap-3">
                  <span className="text-zinc-600 font-bold w-5 text-sm">{i + 1}</span>
                  <span className="text-sm text-zinc-200">{name}</span>
                </div>
                <span className="text-amber-400 font-semibold text-sm">{formatMoney(amount)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sponsors with expandable donor/trail detail */}
      {primarySponsors.length > 0 && (
        <div className="mb-8">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800 flex items-center gap-2">
            <Users className="w-5 h-5 text-blue-500" />
            Sponsors
          </h2>
          <div className="space-y-3">
            {primarySponsors.map((s, i) => (
              <SponsorCard key={i} s={s} expanded={expandedSponsors.has(i)} onToggle={() => toggleSponsor(i)} />
            ))}
          </div>
        </div>
      )}

      {cosponsors.length > 0 && (
        <div className="mb-8">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800 flex items-center gap-2">
            <Users className="w-5 h-5 text-zinc-500" />
            Cosponsors ({cosponsors.length})
          </h2>
          <div className="space-y-2">
            {cosponsors.map((s, i) => (
              <SponsorCard
                key={i}
                s={s}
                expanded={expandedSponsors.has(i + 1000)}
                onToggle={() => toggleSponsor(i + 1000)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
