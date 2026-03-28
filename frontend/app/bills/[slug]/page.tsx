'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ExternalLink, AlertTriangle, ShieldCheck, TrendingUp, Clock } from 'lucide-react';
import { getV2Bill } from '@/lib/api';
import type { V2BillResponse, V2BillInfluenceSignal, V2Sponsor } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import LoadingState from '@/components/LoadingState';
import PartyBadge from '@/components/PartyBadge';
import AIBriefing from '@/components/AIBriefing';
import PageControls from '@/components/PageControls';
import InvestigateChat from '@/components/InvestigateChat';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<string, string> = {
  'BECAME LAW': 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40',
  'PASSED': 'bg-blue-500/20 text-blue-400 border-blue-500/40',
  'IN COMMITTEE': 'bg-amber-500/20 text-amber-400 border-amber-500/40',
  'INTRODUCED': 'bg-zinc-700 text-zinc-300 border-zinc-600',
  'ON FLOOR': 'bg-blue-500/20 text-blue-400 border-blue-500/40',
  'FAILED': 'bg-red-500/20 text-red-400 border-red-500/40',
};

const SIGNAL_LABELS: Record<string, string> = {
  lobby_donate: 'Lobby + Donate Match',
  timing_spike: 'Donation Timing Spike',
  committee_overlap: 'Committee Overlap',
  stock_trade: 'Stock Trades',
  revolving_door: 'Revolving Door',
};

const SIGNAL_ICONS: Record<string, string> = {
  lobby_donate: '\u{1F4B0}',
  timing_spike: '\u{23F1}',
  committee_overlap: '\u{1F3DB}',
  stock_trade: '\u{1F4C8}',
  revolving_door: '\u{1F6AA}',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDate(d: string | null | undefined): string {
  if (!d) return '';
  try {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return ''; }
}

function getSignalStyle(signal: V2BillInfluenceSignal) {
  if (signal.found && signal.rarity_label === 'Rare') {
    return {
      border: '1px solid rgba(239, 68, 68, 0.21)',
      background: 'linear-gradient(135deg, #0f0808, #0a0505)',
      glow: 'radial-gradient(ellipse at 30% 30%, rgba(239,68,68,0.07), transparent 70%)',
      badge: 'bg-red-500/20 text-red-400 border-red-500/40',
      badgeText: 'RARE',
    };
  }
  if (signal.found && (signal.rarity_label === 'Unusual' || signal.rarity_label === 'Above Baseline')) {
    return {
      border: '1px solid rgba(245, 158, 11, 0.21)',
      background: 'linear-gradient(135deg, #0f0a02, #0a0702)',
      glow: '',
      badge: 'bg-amber-500/20 text-amber-400 border-amber-500/40',
      badgeText: signal.rarity_pct ? `${signal.rarity_pct.toFixed(0)}x` : 'ABOVE',
    };
  }
  if (signal.found && signal.rarity_label === 'Expected') {
    return {
      border: '1px solid rgba(34, 34, 34, 0.50)',
      background: '#09090b',
      glow: '',
      badge: 'bg-zinc-700 text-zinc-400 border-zinc-600',
      badgeText: 'EXPECTED',
    };
  }
  // not found / clear
  return {
    border: '1px solid rgba(34, 197, 94, 0.125)',
    background: '#09090b',
    glow: '',
    badge: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
    badgeText: 'CLEAR',
  };
}

// ---------------------------------------------------------------------------
// Percentile Ring
// ---------------------------------------------------------------------------

function PercentileRing({ pct, policyArea, similarCount }: { pct: number; policyArea: string; similarCount: number }) {
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;

  let strokeColor = '#22c55e'; // green
  if (pct >= 80) strokeColor = '#ef4444'; // red
  else if (pct >= 50) strokeColor = '#f59e0b'; // amber

  return (
    <div className="flex items-center gap-6 bg-zinc-900 border border-zinc-800 rounded-[14px] p-5">
      <div className="relative flex-shrink-0" style={{ width: 128, height: 128 }}>
        <svg width="128" height="128" viewBox="0 0 128 128" className="-rotate-90">
          <circle cx="64" cy="64" r={radius} fill="none" stroke="#27272a" strokeWidth="8" />
          <circle
            cx="64" cy="64" r={radius} fill="none"
            stroke={strokeColor} strokeWidth="8" strokeLinecap="round"
            strokeDasharray={circumference} strokeDashoffset={offset}
            style={{ transition: 'stroke-dashoffset 1s ease-out' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold" style={{ color: strokeColor }}>{pct}</span>
          <span className="text-[0.6rem] text-zinc-500 uppercase tracking-wider">percentile</span>
        </div>
      </div>
      <div>
        <p className="text-zinc-200 text-sm font-medium leading-snug">
          More influence signals than <span className="font-bold" style={{ color: strokeColor }}>{pct}%</span> of{' '}
          {policyArea ? <>{policyArea} bills</> : <>similar bills</>}
        </p>
        {similarCount > 0 && (
          <p className="text-zinc-500 text-xs mt-1">Compared against {similarCount.toLocaleString()} bills</p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Influence Signal Card
// ---------------------------------------------------------------------------

function SignalCard({ signal }: { signal: V2BillInfluenceSignal }) {
  const style = getSignalStyle(signal);
  const label = SIGNAL_LABELS[signal.type] || signal.type.replace(/_/g, ' ');
  const icon = SIGNAL_ICONS[signal.type] || '\u{1F50D}';
  const trades = signal.evidence?.trades;

  return (
    <div
      className="rounded-[14px] p-4 relative overflow-hidden"
      style={{ border: style.border, background: style.background }}
    >
      {style.glow && (
        <div className="absolute inset-0 pointer-events-none" style={{ background: style.glow }} />
      )}
      <div className="relative">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-base">{icon}</span>
            <span className="text-sm font-semibold text-zinc-200">{label}</span>
          </div>
          <span className={`text-[0.65rem] font-bold px-2 py-0.5 rounded border uppercase tracking-wide ${style.badge}`}>
            {style.badgeText}
          </span>
        </div>
        {signal.description && (
          <p className="text-zinc-400 text-xs leading-relaxed">{signal.description}</p>
        )}
        {/* Stock trade evidence */}
        {trades && trades.length > 0 && (
          <div className="mt-3 space-y-1">
            {trades.slice(0, 5).map((t, i) => (
              <div key={i} className="flex items-center justify-between text-xs bg-zinc-950/50 rounded-lg px-2.5 py-1.5">
                <span className="text-zinc-300">{t.asset_name || t.ticker}</span>
                <div className="flex items-center gap-2 text-zinc-500">
                  <span>{t.transaction_type}</span>
                  <span className="text-zinc-400">{t.amount_range}</span>
                  {t.date && <span>{fmtDate(t.date)}</span>}
                </div>
              </div>
            ))}
            {trades.length > 5 && (
              <p className="text-zinc-600 text-xs pl-2">+{trades.length - 5} more trades</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sponsor Card
// ---------------------------------------------------------------------------

function SponsorCard({ sponsor }: { sponsor: V2Sponsor }) {
  const verifiedConnections = sponsor.verified_connections || [];
  const ctx = sponsor.context || {};

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-[14px] overflow-hidden hover:border-zinc-600 transition-colors">
      {/* Header */}
      <div className="p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div>
              <Link
                href={`/officials/${sponsor.slug}`}
                className="font-semibold text-zinc-100 hover:text-amber-400 transition-colors"
              >
                {sponsor.name}
              </Link>
              <div className="flex items-center gap-2 mt-0.5">
                <PartyBadge party={sponsor.party} />
                {sponsor.state && <span className="text-xs text-zinc-500">{sponsor.state}</span>}
                <span className="text-xs text-zinc-600">{sponsor.role}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Verified Connections */}
      {verifiedConnections.length > 0 && (
        <div className="border-t border-zinc-800 px-4 py-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="w-2 h-2 rounded-full bg-red-500 flex-shrink-0" />
            <span className="text-xs font-bold uppercase tracking-widest text-red-400">
              Verified Connections
            </span>
          </div>
          <div className="space-y-1">
            {verifiedConnections.map((c, i) => (
              <div key={i} className="flex items-center justify-between text-sm py-1 px-2 rounded-lg hover:bg-zinc-800/60">
                <div className="flex items-center gap-2">
                  <span className="text-zinc-300">{c.entity}</span>
                  <span className="text-[0.6rem] text-zinc-600 uppercase">{c.type.replace(/_/g, ' ')}</span>
                </div>
                <span className="text-amber-400 font-semibold text-sm">{formatMoney(c.amount)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Broader Context */}
      {(ctx.industry_donations_90d || ctx.career_pac_total || ctx.committee) && (
        <div className="border-t border-zinc-800 px-4 py-3">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-3.5 h-3.5 text-zinc-500" />
            <span className="text-xs font-bold uppercase tracking-widest text-zinc-500">
              Broader Context
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {ctx.career_pac_total != null && (
              <div className="bg-zinc-950/60 rounded-lg px-3 py-2">
                <div className="text-amber-400 font-bold text-sm">{formatMoney(ctx.career_pac_total)}</div>
                <div className="text-[0.6rem] text-zinc-600 uppercase">Career PAC Total</div>
              </div>
            )}
            {ctx.industry_donations_90d != null && (
              <div className="bg-zinc-950/60 rounded-lg px-3 py-2">
                <div className="text-amber-400 font-bold text-sm">{formatMoney(ctx.industry_donations_90d)}</div>
                <div className="text-[0.6rem] text-zinc-600 uppercase">Industry (90 days)</div>
              </div>
            )}
            {ctx.committee && (
              <div className="bg-zinc-950/60 rounded-lg px-3 py-2">
                <div className="text-zinc-300 text-sm font-medium">{ctx.committee}</div>
                <div className="text-[0.6rem] text-zinc-600 uppercase">Committee</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Data Limitations Footer
// ---------------------------------------------------------------------------

function DataLimitations({ limitations }: { limitations: Record<string, unknown> }) {
  const items: string[] = [];
  if (limitations.fec_threshold) items.push(`FEC only reports individual donations above ${limitations.fec_threshold}`);
  if (limitations.senate_stocks === false) items.push('Senate stock trades are self-reported with delays up to 45 days');
  // surface any other keys
  for (const [k, v] of Object.entries(limitations)) {
    if (k === 'fec_threshold' || k === 'senate_stocks') continue;
    if (typeof v === 'string') items.push(v);
    if (typeof v === 'boolean' && !v) items.push(`${k.replace(/_/g, ' ')}: not available`);
  }
  if (items.length === 0) return null;

  return (
    <div className="border-t border-zinc-800 pt-6 mt-8">
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle className="w-4 h-4 text-zinc-600" />
        <span className="text-xs font-bold uppercase tracking-widest text-zinc-600">Data Limitations</span>
      </div>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="text-xs text-zinc-500 flex gap-2">
            <span className="text-zinc-700 mt-0.5 flex-shrink-0">&bull;</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page Component
// ---------------------------------------------------------------------------

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
      <Link href="/search" className="text-amber-400 hover:underline">Search for bills</Link>
    </div>
  );

  const { entity, status_label, sponsors, summary, policy_area, percentile_rank, similar_bill_count, influence_signals, data_limitations, briefing: dataBriefing } = data;

  const meta = (entity.metadata || entity.metadata_ || {}) as Record<string, unknown>;
  const plainSummary = summary || (meta.crs_summary as string | undefined) || (meta.summary as string | undefined) || entity.summary;
  const congressUrl = meta.congress_url as string | undefined;
  const introducedDate = (data.freshness?.introduced_date || meta.introduced_date) as string | undefined;
  const statusStyle = STATUS_COLORS[status_label] || STATUS_COLORS['INTRODUCED'];

  const foundSignals = (influence_signals || []).filter(s => s.found);
  const clearSignals = (influence_signals || []).filter(s => !s.found);

  return (
    <div className="max-w-[900px] mx-auto px-4 py-6">

      {/* ── 1. Header ─────────────────────────────────────────────────── */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2 flex-wrap">
          <span className={`text-xs font-bold px-2.5 py-1 rounded border ${statusStyle}`}>{status_label}</span>
          {policy_area && <span className="text-xs text-zinc-500 bg-zinc-800 px-2 py-0.5 rounded">{policy_area}</span>}
          {introducedDate && <span className="text-xs text-zinc-600">Introduced {fmtDate(introducedDate) || introducedDate}</span>}
        </div>
        <h1 className="text-2xl font-bold mb-2">{entity.name}</h1>
        {plainSummary ? (
          <p className="text-zinc-400 text-sm leading-relaxed">{plainSummary}</p>
        ) : (
          <p className="text-zinc-500 text-sm italic">No summary available. Click Refresh to fetch the latest data.</p>
        )}
        {congressUrl && (
          <a href={congressUrl as string} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-zinc-500 hover:text-amber-400 mt-2 transition-colors">
            <ExternalLink className="w-3 h-3" />
            View on Congress.gov
          </a>
        )}
      </div>

      {/* Controls (refresh + regen briefing) */}
      <PageControls
        slug={slug}
        entityName={entity.name}
        onBriefingUpdate={(text) => setBriefing(text)}
        onDataRefresh={() => {
          getV2Bill(slug).then(d => { setData(d); setBriefing(d.briefing); }).catch(() => {});
        }}
      />

      {/* Freshness indicator */}
      <div className="flex flex-wrap items-center gap-4 mb-6 text-xs text-zinc-500">
        <div className="flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5" />
          <span>Last refreshed: {data.freshness?.last_refreshed ? fmtDate(data.freshness.last_refreshed) : (entity.updated_at ? fmtDate(entity.updated_at) : 'Unknown')}</span>
        </div>
      </div>

      {/* ── 2. Compared to Similar Bills ──────────────────────────────── */}
      {percentile_rank != null && (
        <div className="mb-8">
          <PercentileRing
            pct={percentile_rank}
            policyArea={policy_area || ''}
            similarCount={similar_bill_count || 0}
          />
        </div>
      )}

      {/* ── 3. Influence Signal Cards ─────────────────────────────────── */}
      {influence_signals && influence_signals.length > 0 && (
        <div className="mb-8">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800 flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-amber-500" />
            Influence Signals
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Found signals first (rare > unusual > expected), then clear */}
            {foundSignals.map((s, i) => <SignalCard key={`found-${i}`} signal={s} />)}
            {clearSignals.map((s, i) => <SignalCard key={`clear-${i}`} signal={s} />)}
          </div>
        </div>
      )}

      {/* ── 4. Who Wrote This Bill ────────────────────────────────────── */}
      {sponsors.length > 0 && (
        <div className="mb-8">
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">
            Who Wrote This Bill
          </h2>
          <div className="space-y-3">
            {sponsors.map((s, i) => <SponsorCard key={i} sponsor={s} />)}
          </div>
        </div>
      )}

      {/* ── 5. AI Analysis ────────────────────────────────────────────── */}
      <AIBriefing briefing={briefing ?? dataBriefing} />

      {/* ── 6. Data Limitations ───────────────────────────────────────── */}
      {data_limitations && Object.keys(data_limitations).length > 0 && (
        <DataLimitations limitations={data_limitations} />
      )}

      <InvestigateChat slug={slug} entityName={entity.name} />
    </div>
  );
}
