'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import type { Relationship } from '@/lib/types';
import MoneyAmount from './MoneyAmount';
import { formatDate, formatMoney } from '@/lib/utils';
import { getDonorBadge } from '@/lib/api';
import DidYouKnow from '@/components/DidYouKnow';

interface DonorTableProps {
  donations: Relationship[];
  fecTotalReceipts?: number | null;
}

function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function RecipientBadge({ slug }: { slug: string }) {
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    getDonorBadge(slug).then(d => setCount(d.recipient_count)).catch(() => {});
  }, [slug]);
  if (count == null || count <= 1) return null;
  return (
    <span className="ml-2 inline-flex items-center rounded-full bg-zinc-700 px-2 py-0.5 text-[10px] font-medium text-zinc-300">
      Also donates to {count - 1} other{count - 1 !== 1 ? 's' : ''}
    </span>
  );
}

export default function DonorTable({ donations, fecTotalReceipts }: DonorTableProps) {
  if (donations.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500">
        No campaign finance data available.
      </p>
    );
  }

  // Aggregate multiple donations from the same donor into one line
  const aggregated = new Map<string, Relationship>();
  for (const d of donations) {
    const key = d.connected_entity?.slug || d.from_entity_id;
    const existing = aggregated.get(key);
    if (existing) {
      existing.amount_usd = (existing.amount_usd ?? 0) + (d.amount_usd ?? 0);
    } else {
      aggregated.set(key, { ...d, amount_usd: d.amount_usd ?? 0 });
    }
  }

  // Sort by amount descending
  const sorted = Array.from(aggregated.values()).sort((a, b) => {
    return (b.amount_usd ?? 0) - (a.amount_usd ?? 0);
  });

  // Use FEC total receipts if available (more accurate), else sum captured donors
  const capturedTotal = sorted.reduce((sum, d) => sum + (d.amount_usd ?? 0), 0);
  // fecTotalReceipts is in dollars from the API, convert to cents for consistency
  const totalRaised = fecTotalReceipts ? Math.round(fecTotalReceipts * 100) : capturedTotal;

  // Top 10 for the bar chart
  const top10 = sorted.slice(0, 10);
  const maxAmount = top10[0]?.amount_usd ?? 1;

  return (
    <div>
      {/* Total raised */}
      <div className="mb-6 rounded-lg border border-zinc-800 bg-money-surface px-6 py-4">
        <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
          Total Campaign Contributions (FEC)
        </span>
        <div className="mt-1 text-2xl font-bold text-money-success">
          {formatMoney(totalRaised)}
        </div>
        {fecTotalReceipts && capturedTotal > 0 && capturedTotal !== totalRaised && (
          <p className="mt-1 text-xs text-zinc-500">
            Showing top {sorted.length} donors ({formatMoney(capturedTotal)} of {formatMoney(totalRaised)} total).
            The rest comes from hundreds of smaller contributions.
          </p>
        )}
      </div>

      {/* Top 10 donors bar chart */}
      {top10.length > 0 && (
        <div className="mb-6">
          <h4 className="mb-3 text-sm font-semibold text-zinc-300">
            Top Donors
          </h4>
          <div className="space-y-2">
            {top10.map((donation) => {
              const entity = donation.connected_entity;
              const amount = donation.amount_usd ?? 0;
              const widthPercent = maxAmount > 0 ? (amount / maxAmount) * 100 : 0;
              const href = entity
                ? entity.entity_type === 'person'
                  ? `/officials/${entity.slug}`
                  : `/entities/${entity.entity_type}/${entity.slug}`
                : null;

              return (
                <div key={donation.id} className="flex items-center gap-3">
                  <div className="w-36 shrink-0 truncate text-xs text-zinc-300">
                    {href && entity ? (
                      <Link href={href} className="hover:text-money-gold">
                        {entity.name}
                      </Link>
                    ) : (
                      entity?.name || 'Unknown'
                    )}
                  </div>
                  <div className="flex-1">
                    <div
                      className="h-6 rounded-sm bg-money-gold/30 transition-all"
                      style={{ width: `${Math.max(widthPercent, 2)}%` }}
                    >
                      <div
                        className="h-full rounded-sm bg-money-gold/70"
                        style={{ width: '100%' }}
                      />
                    </div>
                  </div>
                  <div className="w-24 shrink-0 text-right text-xs font-medium text-money-success">
                    {formatMoney(amount)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <DidYouKnow fact="PAC donations are limited to $5,000/election. But there's no limit on &quot;independent expenditures&quot; that support a candidate without coordinating with them." />

      {/* Full table */}
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
              <th className="px-4 py-3 font-medium">Donor</th>
              <th className="px-4 py-3 font-medium">Type</th>
              <th className="px-4 py-3 font-medium">Industry</th>
              <th className="px-4 py-3 font-medium">Amount</th>
              <th className="px-4 py-3 font-medium">Date</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((donation) => {
              const meta = donation.metadata as Record<string, unknown>;
              const donorType = (meta?.contributor_type as string) || '--';
              const industry = (meta?.industry_label as string) || '--';
              const entity = donation.connected_entity;
              const href = entity
                ? entity.entity_type === 'person'
                  ? `/officials/${entity.slug}`
                  : `/entities/${entity.entity_type}/${entity.slug}`
                : null;

              return (
                <tr
                  key={donation.id}
                  className="border-b border-zinc-800/50 transition-colors hover:bg-zinc-800/30"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center flex-wrap">
                      {href && entity ? (
                        <Link
                          href={href}
                          className="font-medium text-zinc-200 hover:text-money-gold"
                        >
                          {entity.name}
                        </Link>
                      ) : (
                        <span className="text-zinc-300">Unknown</span>
                      )}
                      {entity?.slug && <RecipientBadge slug={entity.slug} />}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-zinc-400">{donorType}</td>
                  <td className="px-4 py-3">
                    {industry !== '--' ? (
                      <Link
                        href={`/entities/industry/${slugify(industry)}`}
                        className="text-zinc-400 hover:text-money-gold"
                      >
                        {industry}
                      </Link>
                    ) : (
                      <span className="text-zinc-400">--</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <MoneyAmount
                      amount={donation.amount_usd}
                      label={donation.amount_label}
                    />
                  </td>
                  <td className="px-4 py-3 text-zinc-400">
                    {formatDate(donation.date_start)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
