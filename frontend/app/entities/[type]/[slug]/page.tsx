'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { ArrowDownLeft, ArrowUpRight, AlertTriangle } from 'lucide-react';
import { getV2Entity } from '@/lib/api';
import type { V2EntityResponse } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import LoadingState from '@/components/LoadingState';
import AIBriefing from '@/components/AIBriefing';
import MoneyAmount from '@/components/MoneyAmount';
import PageControls from '@/components/PageControls';

function fmtDate(d: string | null | undefined): string {
  if (!d) return '';
  try {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return ''; }
}

export default function EntityPage() {
  const { slug } = useParams<{ type: string; slug: string }>();
  const [data, setData] = useState<V2EntityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [briefing, setBriefing] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    getV2Entity(slug)
      .then(d => { setData(d); setBriefing(d.briefing); })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <div className="max-w-[900px] mx-auto p-6"><LoadingState variant="profile" /></div>;
  if (error || !data) return (
    <div className="max-w-[900px] mx-auto p-6 text-center">
      <p className="text-zinc-500 mb-4">Entity not found.</p>
      <Link href="/search" className="text-amber-400 hover:underline">Search →</Link>
    </div>
  );

  const { entity, money_in, money_out, briefing: dataBriefing } = data;
  const money_trails = (data as unknown as Record<string, unknown>).money_trails as Array<{
    official_name: string; official_slug: string; official_party: string;
    official_state: string; amount_received: number; verdict: string;
    via?: string; bills: Array<{ name: string; slug: string; role: string }>;
  }> || [];
  const entityType = entity.entity_type || 'organization';

  const TYPE_BADGES: Record<string, string> = {
    pac: 'bg-amber-500/15 text-amber-300',
    company: 'bg-blue-500/15 text-blue-400',
    organization: 'bg-purple-500/15 text-purple-400',
    industry: 'bg-emerald-500/15 text-emerald-400',
    donor: 'bg-emerald-500/15 text-emerald-400',
  };

  const totalIn = money_in.reduce((sum, x) => sum + (x.amount_usd || 0), 0);
  const totalOut = money_out.reduce((sum, x) => sum + (x.amount_usd || 0), 0);
  const gap = totalIn - totalOut;
  const hasGap = totalIn > 0 && totalOut > 0 && gap > 0;
  const nameLower = entity.name.toLowerCase();
  const isPac = entityType === 'pac' || nameLower.includes('pac') || nameLower.includes('fund') || nameLower.includes('committee') || nameLower.includes('victory');

  function MoneyList({ items, label }: { items: typeof money_in; label: string }) {
    if (items.length === 0) return <p className="text-zinc-600 text-sm">No {label.toLowerCase()} data tracked.</p>;
    return (
      <div className="space-y-0.5">
        {items.map((item, i) => (
          <Link
            key={i}
            href={item.entity_type === 'person' ? `/officials/${item.slug}` : `/entities/${item.entity_type}/${item.slug}`}
            className="flex items-center justify-between py-2 px-2 -mx-2 rounded-lg hover:bg-zinc-800/60 transition-colors cursor-pointer"
          >
            <div className="min-w-0 mr-3">
              <div className="text-sm font-medium truncate">{item.name}</div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-zinc-600">{item.entity_type}</span>
                {!!(item as unknown as Record<string, unknown>).date && (
                  <span className="text-xs text-zinc-700">{fmtDate((item as unknown as Record<string, unknown>).date as string)}</span>
                )}
              </div>
            </div>
            <MoneyAmount amount={item.amount_usd} label={item.amount_label} />
          </Link>
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-[900px] mx-auto px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <span className={`text-xs font-bold px-2.5 py-1 rounded ${TYPE_BADGES[entityType] || 'bg-zinc-700 text-zinc-300'}`}>
            {entityType.toUpperCase()}
          </span>
        </div>
        <h1 className="text-2xl font-bold">{entity.name}</h1>
        {isPac && (
          <p className="text-zinc-500 text-sm mt-1">
            Joint fundraising committees and PACs collect money from many sources and distribute to multiple candidates, party committees, and other PACs. Only tracked distributions are shown below.
          </p>
        )}
      </div>

      <PageControls
        slug={slug}
        entityName={entity.name}
        onBriefingUpdate={(text) => setBriefing(text)}
        onDataRefresh={() => {
          getV2Entity(slug).then(d => { setData(d); setBriefing(d.briefing); }).catch(() => {});
        }}
      />

      <AIBriefing briefing={briefing ?? dataBriefing} />

      {/* Money flow summary bar */}
      {(totalIn > 0 || totalOut > 0) && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-px bg-zinc-800 rounded-xl overflow-hidden mb-6">
          <div className="bg-zinc-900 p-4 text-center">
            <div className="text-emerald-400 text-xl font-bold">{formatMoney(totalIn)}</div>
            <div className="text-xs text-zinc-500 uppercase tracking-wide mt-1">Total In</div>
          </div>
          <div className="bg-zinc-900 p-4 text-center">
            <div className="text-red-400 text-xl font-bold">{formatMoney(totalOut)}</div>
            <div className="text-xs text-zinc-500 uppercase tracking-wide mt-1">Tracked Out</div>
          </div>
          {hasGap && (
            <div className="bg-zinc-900 p-4 text-center col-span-2 md:col-span-1">
              <div className="text-amber-400 text-xl font-bold">{formatMoney(gap)}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide mt-1">Untracked</div>
            </div>
          )}
        </div>
      )}

      {/* Gap explanation */}
      {hasGap && isPac && (
        <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-950/20 border border-amber-500/20 mb-6">
          <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
          <div>
            <div className="text-sm font-medium text-amber-400 mb-1">
              {formatMoney(gap)} untracked
            </div>
            <p className="text-xs text-zinc-400 leading-relaxed">
              This entity received {formatMoney(totalIn)} but we only track {formatMoney(totalOut)} going out.
              The remaining {formatMoney(gap)} likely went to other candidates, party committees (DNC/RNC, state parties),
              or operational expenses. Our data only shows distributions to officials we track.
              {money_out.length === 1 && (
                <> Only <span className="text-zinc-200">{money_out[0].name}</span> is in our database as a tracked recipient.</>
              )}
            </p>
          </div>
        </div>
      )}

      {/* Money In / Money Out split */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800 flex items-center gap-2">
            <ArrowDownLeft className="w-5 h-5 text-emerald-500" />
            Money In
            <span className="text-sm font-normal text-zinc-500">({money_in.length})</span>
          </h2>
          <MoneyList items={money_in} label="Money In" />
        </div>
        <div>
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800 flex items-center gap-2">
            <ArrowUpRight className="w-5 h-5 text-red-500" />
            Money Out
            <span className="text-sm font-normal text-zinc-500">({money_out.length})</span>
          </h2>
          <MoneyList items={money_out} label="Money Out" />
        </div>
      </div>

      {/* Follow the Money — where did it ultimately go? */}
      {money_trails.length > 0 && (
        <div className="mt-10">
          <h2 className="text-xl font-bold mb-2 pb-2 border-b border-zinc-800 flex items-center gap-2">
            <ArrowUpRight className="w-5 h-5 text-amber-500" />
            Follow the Money — Officials Funded
          </h2>
          <p className="text-zinc-500 text-sm mb-4">
            Tracing where this money ultimately reached elected officials and what legislation they worked on.
          </p>
          <div className="space-y-3">
            {money_trails.map((trail, i) => (
              <div key={i} className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 hover:border-zinc-600 transition-colors">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <Link
                      href={`/officials/${trail.official_slug}`}
                      className="font-semibold hover:text-amber-400 transition-colors"
                    >
                      {trail.official_name}
                    </Link>
                    {trail.official_party && (
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        trail.official_party.toLowerCase().includes('democrat') ? 'bg-blue-500/20 text-blue-400' :
                        trail.official_party.toLowerCase().includes('republican') ? 'bg-red-500/20 text-red-400' :
                        'bg-zinc-700 text-zinc-300'
                      }`}>
                        {trail.official_party}
                      </span>
                    )}
                    {trail.official_state && <span className="text-xs text-zinc-500">{trail.official_state}</span>}
                  </div>
                  <span className="text-amber-400 font-bold">{formatMoney(trail.amount_received)}</span>
                </div>
                {trail.via && (
                  <div className="text-xs text-zinc-500 mb-2">
                    via <span className="text-amber-400/70">{trail.via}</span>
                  </div>
                )}
                {trail.bills.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-zinc-800">
                    <div className="text-xs text-red-500 font-bold uppercase tracking-widest mb-1.5">
                      Legislation ({trail.bills.length})
                    </div>
                    <div className="space-y-1">
                      {trail.bills.map((b, j) => (
                        <Link
                          key={j}
                          href={`/bills/${b.slug}`}
                          className="block text-sm text-zinc-300 hover:text-amber-400 transition-colors py-0.5"
                        >
                          {b.name}
                          <span className="text-xs text-zinc-600 ml-2">{b.role}</span>
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
