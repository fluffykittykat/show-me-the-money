'use client';

import { useState } from 'react';
import Link from 'next/link';
import { ChevronDown, ChevronUp, DollarSign, Building2, ScrollText, Users, Scale } from 'lucide-react';
import type { V2MoneyTrail } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import VerdictBadge from './VerdictBadge';

interface MoneyTrailCardProps {
  trail: V2MoneyTrail;
  officialName: string;
  officialSlug: string;
}

function fmtDate(d: string | null | undefined): string {
  if (!d) return '';
  try {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return ''; }
}

export default function MoneyTrailCard({ trail, officialName, officialSlug }: MoneyTrailCardProps) {
  const [expanded, setExpanded] = useState(false);
  const chain = trail.chain || {};
  const donors = chain.donors || [];
  const middlemen = chain.middlemen || [];
  const committees = chain.committees || [];
  const bills = chain.bills || [];
  const lobbying = chain.lobbying || [];
  const timingHits = ((chain as Record<string, unknown>).timing_hits || []) as Array<{
    donor: string; donor_slug?: string; amount?: number; donation_date: string;
    bill: string; bill_slug?: string; bill_date: string; days_before: number;
  }>;
  const donorCount = (chain as Record<string, unknown>).donor_count as number || donors.length || 0;
  const trailAny = trail as unknown as Record<string, unknown>;
  const totalCampaign = (trailAny.total_campaign as number) || 0;
  const otherTopDonors = (trailAny.other_top_donors as Array<{ name: string; slug: string; amount: number }>) || [];

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl mb-4 transition-all duration-200 hover:border-zinc-600">
      {/* Header — always visible, clickable to expand */}
      <div
        className="p-5 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex justify-between items-start mb-2">
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <div className="text-lg font-semibold">{trail.industry}</div>
              <VerdictBadge verdict={trail.verdict} />
            </div>
            <div className="flex items-center gap-3 mt-1.5">
              <div className="flex gap-1">
                {Array.from({ length: 7 }, (_, i) => (
                  <div key={i} className={`w-2 h-2 rounded-full ${i < trail.dot_count ? 'bg-amber-500' : 'bg-zinc-700'}`} />
                ))}
              </div>
              <span className="text-amber-400 font-bold">{formatMoney(trail.total_amount)}</span>
              <span className="text-zinc-500 text-xs">
                from {donorCount} industry donor{donorCount !== 1 ? 's' : ''}
              </span>
              {totalCampaign > 0 && totalCampaign > trail.total_amount && (
                <span className="text-zinc-600 text-xs">
                  · {formatMoney(totalCampaign)} total campaign
                </span>
              )}
              {bills.length > 0 && (
                <span className="text-zinc-500 text-xs">
                  · {bills.length} bill{bills.length !== 1 ? 's' : ''}
                </span>
              )}
              {timingHits.length > 0 && (
                <span className="text-red-500 text-xs font-semibold">
                  · ⚠ {timingHits.length} timing hit{timingHits.length !== 1 ? 's' : ''}
                </span>
              )}
            </div>
          </div>
          <div className="text-zinc-500 ml-3 mt-1">
            {expanded ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
          </div>
        </div>

        {/* Narrative — always visible */}
        {trail.narrative && (
          <p className="text-zinc-400 text-sm leading-relaxed mt-2">
            {trail.narrative.split(/(\$[\d,.]+[KMB]?)/).map((part, i) =>
              part.startsWith('$') ? <span key={i} className="text-amber-400 font-semibold">{part}</span> : <span key={i}>{part}</span>
            )}
          </p>
        )}
      </div>

      {/* Expanded detail — the full exposure */}
      {expanded && (
        <div className="border-t border-zinc-800 px-5 pb-5">

          {/* ALL DONORS */}
          {donors.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center gap-2 mb-3">
                <DollarSign className="w-4 h-4 text-emerald-500" />
                <span className="text-xs font-bold uppercase tracking-widest text-emerald-500">
                  Donors ({donors.length}) — {formatMoney(trail.total_amount)} total
                </span>
              </div>
              <div className="space-y-1">
                {donors.map((d, i) => (
                  <div key={i} className="flex items-center justify-between py-1.5 px-3 rounded-lg hover:bg-zinc-800/60 transition-colors">
                    <Link
                      href={`/entities/pac/${d.slug}`}
                      className="text-sm text-zinc-200 hover:text-amber-400 transition-colors truncate mr-3"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {d.name}
                    </Link>
                    <div className="flex items-center gap-3 flex-shrink-0">
                      {d.date && <span className="text-xs text-zinc-600">{fmtDate(d.date)}</span>}
                      <span className="text-amber-400 font-semibold text-sm">{formatMoney(d.amount)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* OTHER TOP DONORS — biggest donors not from this industry */}
          {otherTopDonors.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center gap-2 mb-3">
                <DollarSign className="w-4 h-4 text-zinc-500" />
                <span className="text-xs font-bold uppercase tracking-widest text-zinc-500">
                  Other Top Campaign Donors
                </span>
                {totalCampaign > 0 && (
                  <span className="text-xs text-zinc-600">— {formatMoney(totalCampaign)} total campaign</span>
                )}
              </div>
              <div className="space-y-1">
                {otherTopDonors.map((d, i) => (
                  <div key={i} className="flex items-center justify-between py-1.5 px-3 rounded-lg hover:bg-zinc-800/60 transition-colors">
                    <Link
                      href={`/entities/pac/${d.slug}`}
                      className="text-sm text-zinc-400 hover:text-amber-400 transition-colors truncate mr-3"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {d.name}
                    </Link>
                    <span className="text-zinc-400 font-semibold text-sm flex-shrink-0">
                      {formatMoney(d.amount)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* MIDDLEMEN */}
          {middlemen.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center gap-2 mb-3">
                <Users className="w-4 h-4 text-amber-500" />
                <span className="text-xs font-bold uppercase tracking-widest text-amber-500">
                  Middlemen ({middlemen.length}) — money funneled through
                </span>
              </div>
              <div className="space-y-1">
                {middlemen.map((m, i) => (
                  <div key={i} className="flex items-center justify-between py-1.5 px-3 rounded-lg hover:bg-zinc-800/60 transition-colors">
                    <Link
                      href={`/entities/pac/${m.slug}`}
                      className="text-sm text-zinc-200 hover:text-amber-400 transition-colors truncate mr-3"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {m.name}
                    </Link>
                    <span className="text-amber-400 text-xs flex-shrink-0">
                      {formatMoney(m.amount_in)} in → {formatMoney(m.amount_out)} out
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* COMMITTEES */}
          {committees.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center gap-2 mb-3">
                <Building2 className="w-4 h-4 text-purple-500" />
                <span className="text-xs font-bold uppercase tracking-widest text-purple-500">
                  Committees ({committees.length}) — regulates this industry
                </span>
              </div>
              <div className="space-y-1">
                {committees.map((c, i) => (
                  <Link
                    key={i}
                    href={`/entities/organization/${c.slug}`}
                    className="block py-1.5 px-3 text-sm text-zinc-200 hover:text-amber-400 rounded-lg hover:bg-zinc-800/60 transition-colors"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {c.name}
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* BILLS */}
          {bills.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center gap-2 mb-3">
                <ScrollText className="w-4 h-4 text-red-500" />
                <span className="text-xs font-bold uppercase tracking-widest text-red-500">
                  Legislation ({bills.length}) — sponsored by {officialName.split(',')[0]}
                </span>
              </div>
              <div className="space-y-1">
                {bills.map((b, j) => (
                  <Link
                    key={j}
                    href={`/bills/${b.slug}`}
                    className="block py-1.5 px-3 text-sm text-zinc-200 hover:text-amber-400 rounded-lg hover:bg-zinc-800/60 transition-colors"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {b.name}
                    <span className="text-xs text-zinc-600 ml-2">{b.role}</span>
                    {b.date && <span className="text-xs text-zinc-600 ml-2">{fmtDate(b.date)}</span>}
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* LOBBYING */}
          {lobbying.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center gap-2 mb-3">
                <Scale className="w-4 h-4 text-orange-500" />
                <span className="text-xs font-bold uppercase tracking-widest text-orange-500">
                  Lobbying ({lobbying.length}) — donors also lobby Congress
                </span>
              </div>
              <div className="space-y-1">
                {lobbying.map((l, i) => (
                  <div key={i} className="py-1.5 px-3 rounded-lg hover:bg-zinc-800/60 transition-colors">
                    <div className="text-sm text-zinc-200">{l.firm}</div>
                    <div className="text-xs text-zinc-500">
                      on behalf of {l.client}{l.issue ? ` — "${l.issue}"` : ''}
                      {l.date && <span className="text-zinc-600 ml-2">{fmtDate(l.date)}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* SUSPICIOUS TIMING */}
          {timingHits.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-base">⚠</span>
                <span className="text-xs font-bold uppercase tracking-widest text-red-500">
                  Suspicious Timing ({timingHits.length} correlation{timingHits.length !== 1 ? 's' : ''})
                </span>
              </div>
              <div className="space-y-2">
                {timingHits.sort((a, b) => a.days_before - b.days_before).map((hit, i) => (
                  <div key={i} className="bg-red-950/20 border border-red-500/20 rounded-lg p-3">
                    <div className="text-sm text-zinc-200">
                      <span className="text-emerald-400">{hit.donor}</span>
                      {' donated '}
                      {hit.amount ? <span className="text-amber-400 font-bold">{formatMoney(hit.amount)}</span> : null}
                      {hit.amount ? ' — ' : ''}
                      <span className="text-amber-400 font-bold">
                        {hit.days_before === 0 ? 'the same day' : `${hit.days_before} days before`}
                      </span>
                      {' '}
                      <span className="text-red-400">{hit.bill}</span>
                      {' was introduced'}
                    </div>
                    <div className="text-xs text-zinc-500 mt-1">
                      Donation: {fmtDate(hit.donation_date)} → Bill introduced: {fmtDate(hit.bill_date)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* The connection summary */}
          <div className="mt-4 p-3 rounded-lg bg-zinc-950 border border-zinc-800">
            <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">The Connection</div>
            <p className="text-sm text-zinc-300 leading-relaxed">
              {donors.length} donor{donors.length !== 1 ? 's' : ''} from the <span className="text-amber-400 font-semibold">{trail.industry}</span> industry
              gave <span className="text-amber-400 font-semibold">{formatMoney(trail.total_amount)}</span> to {officialName.split(',')[0]}
              {committees.length > 0 && <>, who sits on <span className="text-purple-400">{committees.map(c => c.name).join(', ')}</span></>}
              {bills.length > 0 && <> and sponsored <span className="text-red-400">{bills.length} bill{bills.length !== 1 ? 's' : ''}</span> affecting this industry</>}
              {lobbying.length > 0 && <>, while {lobbying.length} of these donors also <span className="text-orange-400">lobby Congress</span> on related issues</>}
              .
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
