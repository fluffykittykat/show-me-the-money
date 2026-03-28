'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { getV2Official } from '@/lib/api';
import PageControls from '@/components/PageControls';
import type { V2OfficialResponse, V2OfficialInfluenceSignal } from '@/lib/types';
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

// ---------------------------------------------------------------------------
// Campaign Finance Trend with expandable cycle donors
// ---------------------------------------------------------------------------

interface CycleDonor {
  name: string;
  amount: number;
  date: string | null;
  employer: string;
}

function CycleTrend({ sorted, maxReceipts, totalRaised, totalSpent, trendPct, previous, recent, slug }: {
  sorted: { cycle: number; receipts: number; disbursements: number }[];
  maxReceipts: number;
  totalRaised: number;
  totalSpent: number;
  trendPct: number | null;
  previous: { cycle: number; receipts: number } | null;
  recent: { cycle: number; receipts: number };
  slug: string;
}) {
  const [expandedCycle, setExpandedCycle] = useState<number | null>(null);
  const [cycleDonors, setCycleDonors] = useState<CycleDonor[]>([]);
  const [loadingDonors, setLoadingDonors] = useState(false);

  const handleCycleClick = async (cycle: number) => {
    if (expandedCycle === cycle) {
      setExpandedCycle(null);
      return;
    }
    setExpandedCycle(cycle);
    setLoadingDonors(true);
    setCycleDonors([]);
    try {
      const res = await fetch(`/api/entities/${slug}/pac-donors?cycle=${cycle}`);
      if (res.ok) {
        const data = await res.json();
        setCycleDonors(data.donors || []);
      }
    } catch { /* ignore */ }
    setLoadingDonors(false);
  };

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

      {/* Bar chart — clickable bars */}
      <div className="flex items-end gap-3 mb-4" style={{ height: '120px' }}>
        {sorted.map((c) => {
          const sqrtMax = Math.sqrt(maxReceipts);
          const sqrtVal = Math.sqrt(c.receipts);
          const heightPct = Math.max((sqrtVal / sqrtMax) * 100, 8);
          const isExpanded = expandedCycle === c.cycle;
          return (
            <div
              key={c.cycle}
              className="flex-1 flex flex-col items-center justify-end h-full cursor-pointer group"
              onClick={() => handleCycleClick(c.cycle)}
            >
              <div className="text-[10px] text-amber-400 font-semibold mb-1">
                {formatMoney(Math.round(c.receipts * 100))}
              </div>
              <div
                className={`w-full rounded-t border border-b-0 transition-all ${
                  isExpanded
                    ? 'bg-gradient-to-t from-amber-500/80 to-amber-500/40 border-amber-400'
                    : 'bg-gradient-to-t from-amber-500/60 to-amber-500/20 border-amber-500/30 group-hover:border-amber-400/60'
                }`}
                style={{ height: `${heightPct}%`, minHeight: '8px' }}
              />
              <div className={`text-xs font-mono mt-1.5 border-t pt-1 w-full text-center ${
                isExpanded ? 'text-amber-400 border-amber-500/50' : 'text-zinc-400 border-zinc-800'
              }`}>
                {c.cycle}
              </div>
            </div>
          );
        })}
      </div>

      {/* Expanded cycle donors */}
      {expandedCycle !== null && (
        <div className="bg-zinc-900 border border-amber-500/30 rounded-xl p-4 mb-4">
          <h3 className="text-sm font-bold text-amber-400 mb-3">
            {expandedCycle} Cycle — Top Donors
          </h3>
          {loadingDonors ? (
            <div className="flex items-center gap-2 text-sm text-zinc-500 py-4">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-amber-400" />
              Fetching {expandedCycle} cycle donors from FEC...
            </div>
          ) : cycleDonors.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-zinc-500 uppercase tracking-wide">
                  <th className="pb-2 px-2">Donor</th>
                  <th className="pb-2 px-2">Employer</th>
                  <th className="pb-2 px-2 text-right">Amount</th>
                  <th className="pb-2 px-2">Date</th>
                </tr>
              </thead>
              <tbody>
                {cycleDonors.map((d, i) => (
                  <tr key={i} className="border-t border-zinc-800">
                    <td className="py-2 px-2 text-zinc-200">{d.name}</td>
                    <td className="py-2 px-2 text-zinc-500 text-xs">{d.employer || '--'}</td>
                    <td className="py-2 px-2 text-right text-amber-400 font-semibold">{formatMoney(d.amount)}</td>
                    <td className="py-2 px-2 text-zinc-500 text-xs">{fmtDate(d.date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-zinc-500 text-sm py-2">No donor details available for this cycle. Try refreshing the investigation.</p>
          )}
        </div>
      )}

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
            <tr key={c.cycle} className="border-t border-zinc-900 cursor-pointer hover:bg-zinc-800/50" onClick={() => handleCycleClick(c.cycle)}>
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
}

// ---------------------------------------------------------------------------
// Influence Signal Helpers
// ---------------------------------------------------------------------------

const OFFICIAL_SIGNAL_LABELS: Record<string, string> = {
  donors_lobby_bills: 'DONORS LOBBY HIS BILLS',
  timing_spike: 'DONATION TIMING',
  stock_committee: 'STOCK TRADES',
  committee_donors: 'COMMITTEE DONORS',
  revolving_door: 'REVOLVING DOOR',
};

function getOfficialSignalStyle(signal: V2OfficialInfluenceSignal) {
  if (signal.found && signal.rarity_label === 'Rare') {
    return {
      border: '1px solid rgba(239, 68, 68, 0.2)',
      background: 'linear-gradient(135deg, #0f0808, #0a0505)',
      glow: 'radial-gradient(ellipse at 30% 30%, rgba(239,68,68,0.07), transparent 70%)',
      dotColor: 'bg-red-500',
      badge: 'bg-red-500/20 text-red-400 border-red-500/40',
      badgeText: 'RARE',
    };
  }
  if (signal.found && (signal.rarity_label === 'Unusual' || signal.rarity_label === 'Above Baseline')) {
    return {
      border: '1px solid rgba(245, 158, 11, 0.2)',
      background: 'linear-gradient(135deg, #0f0a02, #0a0702)',
      glow: '',
      dotColor: 'bg-amber-500',
      badge: 'bg-amber-500/20 text-amber-400 border-amber-500/40',
      badgeText: signal.rarity_pct ? `${signal.rarity_pct.toFixed(1)}x` : 'ABOVE',
    };
  }
  if (signal.found && signal.rarity_label === 'Expected') {
    return {
      border: '1px solid rgba(34, 34, 34, 0.5)',
      background: '#09090b',
      glow: '',
      dotColor: 'bg-zinc-500',
      badge: 'bg-zinc-700 text-zinc-400 border-zinc-600',
      badgeText: 'EXPECTED',
    };
  }
  return {
    border: '1px solid rgba(34, 197, 94, 0.12)',
    background: '#09090b',
    glow: '',
    dotColor: 'bg-green-500',
    badge: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    badgeText: 'CLEAR',
  };
}

// ---------------------------------------------------------------------------
// Percentile Ring (Official variant)
// ---------------------------------------------------------------------------

function OfficialPercentileRing({ pct, peerGroup, peerCount }: { pct: number; peerGroup: string; peerCount: number }) {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;

  let strokeColor = '#22c55e';
  if (pct >= 75) strokeColor = '#ef4444';
  else if (pct >= 50) strokeColor = '#f59e0b';

  return (
    <div className="mb-8">
      <div
        style={{ background: 'linear-gradient(135deg,#111,#0a0a12)' }}
        className="border border-zinc-800 rounded-2xl p-5 flex justify-between items-center"
      >
        <div>
          <div className="text-zinc-500 text-xs uppercase tracking-widest">vs. Other {peerGroup}</div>
          <div className="text-white text-base font-bold mt-1">
            More influence signals than{' '}
            <span style={{ color: strokeColor }}>{pct}%</span>{' '}
            of {peerGroup}
          </div>
          <div className="text-zinc-600 text-xs mt-1">Compared against {peerCount} current {peerGroup}</div>
        </div>
        <div className="relative flex-shrink-0" style={{ width: 100, height: 100 }}>
          <svg width="100" height="100" viewBox="0 0 128 128" className="-rotate-90">
            <circle cx="64" cy="64" r={radius} fill="none" stroke="#27272a" strokeWidth="8" />
            <circle
              cx="64" cy="64" r={radius} fill="none"
              stroke={strokeColor} strokeWidth="8" strokeLinecap="round"
              strokeDasharray={circumference} strokeDashoffset={offset}
              style={{ transition: 'stroke-dashoffset 1s ease-out' }}
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-xl font-bold" style={{ color: strokeColor }}>{pct}</span>
            <span className="text-[0.5rem] text-zinc-500 uppercase tracking-wider">percentile</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Influence Signal Card (Official variant)
// ---------------------------------------------------------------------------

function OfficialSignalCard({ signal, peerGroup }: { signal: V2OfficialInfluenceSignal; peerGroup: string }) {
  const [expanded, setExpanded] = useState(false);
  const style = getOfficialSignalStyle(signal);
  const label = OFFICIAL_SIGNAL_LABELS[signal.type] || signal.type.replace(/_/g, ' ').toUpperCase();
  const evidence = signal.evidence;

  const hasEvidence = signal.found && evidence && (
    (evidence.matches && evidence.matches.length > 0) ||
    (evidence.trades && evidence.trades.length > 0) ||
    (evidence.lobbyists && evidence.lobbyists.length > 0)
  );

  return (
    <div
      className="rounded-2xl p-4 relative overflow-hidden"
      style={{ border: style.border, background: style.background }}
    >
      {style.glow && (
        <div className="absolute inset-0 pointer-events-none" style={{ background: style.glow }} />
      )}
      <div className="relative">
        {/* Header row */}
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${style.dotColor} flex-shrink-0`} />
            <span className="text-xs font-bold uppercase tracking-widest text-zinc-300">{label}</span>
          </div>
          <span className={`text-[0.65rem] font-bold px-2 py-0.5 rounded border uppercase tracking-wide ${style.badge}`}>
            {style.badgeText}
          </span>
        </div>

        {/* Description */}
        {signal.description && (
          <p className="text-zinc-400 text-xs leading-relaxed mb-2">{signal.description}</p>
        )}

        {/* Rarity stat */}
        {signal.found && signal.rarity_pct != null && (
          <div className="text-right">
            <span className="text-[0.6rem] text-zinc-600">{signal.rarity_pct}% of {peerGroup}</span>
          </div>
        )}

        {/* View evidence toggle */}
        {hasEvidence && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-amber-400 hover:text-amber-300 transition-colors mt-1"
          >
            {expanded ? 'Hide evidence' : 'View evidence'} →
          </button>
        )}

        {/* Expanded evidence */}
        {expanded && evidence && (
          <div className="mt-3 space-y-2">
            {/* donors_lobby_bills evidence */}
            {evidence.matches && evidence.matches.length > 0 && (
              <div className="space-y-1.5">
                {evidence.matches.map((m, i) => (
                  <div key={i} className="bg-zinc-950/50 rounded-lg px-3 py-2 text-xs">
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div className="text-zinc-300">
                        <span className="font-semibold text-zinc-200">{m.entity_name}</span>
                        {m.bill_name && m.bill_slug ? (
                          <span className="text-zinc-500 ml-2">
                            Lobbied for{' '}
                            <Link href={`/bills/${m.bill_slug}`} className="text-amber-400 hover:underline">
                              {m.bill_name}
                            </Link>
                          </span>
                        ) : m.bill_name ? (
                          <span className="text-zinc-500 ml-2">Lobbied for {m.bill_name}</span>
                        ) : null}
                      </div>
                      {m.donation_amount != null && (
                        <span className="text-amber-400 font-semibold">
                          Donated {formatMoney(m.donation_amount)}
                        </span>
                      )}
                    </div>
                    {m.lda_url && (
                      <a href={m.lda_url} target="_blank" rel="noopener noreferrer" className="text-zinc-600 hover:text-zinc-400 text-[0.6rem] mt-1 inline-block">
                        LDA filing →
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* stock_committee evidence */}
            {evidence.trades && evidence.trades.length > 0 && (
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-zinc-600 uppercase tracking-wide">
                    <th className="pb-1 px-2">Ticker</th>
                    <th className="pb-1 px-2">Type</th>
                    <th className="pb-1 px-2">Amount</th>
                    <th className="pb-1 px-2">Date</th>
                    {evidence.trades.some(t => t.committee) && <th className="pb-1 px-2">Committee</th>}
                  </tr>
                </thead>
                <tbody>
                  {evidence.trades.map((t, i) => (
                    <tr key={i} className="border-t border-zinc-900">
                      <td className="py-1.5 px-2 font-mono text-zinc-200">{t.ticker}</td>
                      <td className="py-1.5 px-2">
                        <span className={t.transaction_type?.toLowerCase().includes('purchase') ? 'text-green-400' : 'text-red-400'}>
                          {t.transaction_type}
                        </span>
                      </td>
                      <td className="py-1.5 px-2 text-zinc-300">{t.amount_range}</td>
                      <td className="py-1.5 px-2 text-zinc-500">{fmtDate(t.date)}</td>
                      {evidence.trades!.some(tr => tr.committee) && (
                        <td className="py-1.5 px-2 text-zinc-500">{t.committee || '--'}</td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {/* revolving_door evidence */}
            {evidence.lobbyists && evidence.lobbyists.length > 0 && (
              <div className="space-y-1.5">
                {evidence.lobbyists.map((l, i) => (
                  <div key={i} className="bg-zinc-950/50 rounded-lg px-3 py-2 text-xs">
                    <div className="text-zinc-200 font-semibold">{l.name}</div>
                    {l.former_position && (
                      <div className="text-zinc-500 mt-0.5">Former: {l.former_position}</div>
                    )}
                    {l.current_clients && l.current_clients.length > 0 && (
                      <div className="text-zinc-500 mt-0.5">
                        Current clients: {l.current_clients.join(', ')}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
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

      {/* Percentile Ring */}
      {data.percentile_rank != null && (
        <OfficialPercentileRing
          pct={data.percentile_rank}
          peerGroup={data.peer_group || 'peers'}
          peerCount={data.peer_count || 0}
        />
      )}

      {/* Influence Signal Cards */}
      {data.influence_signals && data.influence_signals.length > 0 && (() => {
        const foundSignals = data.influence_signals!.filter(s => s.found);
        const clearSignals = data.influence_signals!.filter(s => !s.found);
        return (
          <div className="mb-8">
            <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">
              Influence Signals
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {foundSignals.map((s, i) => (
                <OfficialSignalCard key={`found-${i}`} signal={s} peerGroup={data.peer_group || 'peers'} />
              ))}
              {clearSignals.map((s, i) => (
                <OfficialSignalCard key={`clear-${i}`} signal={s} peerGroup={data.peer_group || 'peers'} />
              ))}
            </div>
          </div>
        );
      })()}

      {/* Campaign Finance Trend */}
      {fec_cycles && fec_cycles.length > 0 && (() => {
        const sorted = [...fec_cycles].sort((a, b) => a.cycle - b.cycle);
        const maxReceipts = Math.max(...sorted.map(c => c.receipts), 1);
        const totalRaised = sorted.reduce((s, c) => s + c.receipts, 0);
        const totalSpent = sorted.reduce((s, c) => s + c.disbursements, 0);
        const recent = sorted[sorted.length - 1];
        const previous = sorted.length > 1 ? sorted[sorted.length - 2] : null;
        const trendPct = previous && previous.receipts > 0
          ? Math.round(((recent.receipts - previous.receipts) / previous.receipts) * 100)
          : null;

        return (<CycleTrend
          sorted={sorted}
          maxReceipts={maxReceipts}
          totalRaised={totalRaised}
          totalSpent={totalSpent}
          trendPct={trendPct}
          previous={previous}
          recent={recent}
          slug={slug}
        />);
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
