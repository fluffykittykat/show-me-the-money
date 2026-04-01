'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import type { Relationship } from '@/lib/types';
import { formatDate, formatMoney } from '@/lib/utils';
import { getBillBadges } from '@/lib/api';
import clsx from 'clsx';

interface BillsTableProps {
  bills: Relationship[];
  votes?: Relationship[];
}

function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

function StatusBadge({ status }: { status: string }) {
  let colorClass = 'text-zinc-400';
  const lower = status.toLowerCase();

  if (lower.includes('passed') || lower.includes('enacted') || lower.includes('signed') || lower.includes('became')) {
    colorClass = 'text-emerald-400';
  } else if (lower.includes('failed') || lower.includes('vetoed')) {
    colorClass = 'text-red-400';
  } else if (lower.includes('introduced') || lower.includes('pending')) {
    colorClass = 'text-yellow-400';
  } else if (lower.includes('committee')) {
    colorClass = 'text-zinc-400';
  }

  return (
    <span className={clsx('text-xs', colorClass)}>
      {status}
    </span>
  );
}

function VoteBadge({ position }: { position: string }) {
  const lower = position.toLowerCase();
  const isYes = lower === 'yes' || lower === 'yea' || lower === 'aye';
  const isNo = lower === 'no' || lower === 'nay';

  return (
    <span
      className={clsx(
        'rounded px-2 py-0.5 text-xs font-bold uppercase',
        isYes && 'bg-emerald-500/20 text-emerald-400',
        isNo && 'bg-red-500/20 text-red-400',
        !isYes && !isNo && 'bg-zinc-700 text-zinc-300'
      )}
    >
      {position}
    </span>
  );
}

function BillBadges({ slug }: { slug: string }) {
  const [data, setData] = useState<{ cosponsor_count: number; donor_industries: Array<{ industry: string; total: number }> } | null>(null);
  useEffect(() => {
    getBillBadges(slug).then(setData).catch(() => {});
  }, [slug]);
  if (!data) return null;
  const totalIndustryMoney = data.donor_industries.reduce((s, d) => s + d.total, 0);
  return (
    <div className="mt-1 flex flex-wrap gap-1.5">
      {data.cosponsor_count > 1 && (
        <span className="inline-flex items-center rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-medium text-blue-400">
          {data.cosponsor_count} co-sponsors
        </span>
      )}
      {totalIndustryMoney > 0 && (
        <span className="inline-flex items-center rounded-full bg-money-gold/10 px-2 py-0.5 text-[10px] font-medium text-money-gold">
          Backed by {data.donor_industries.length} industries ({formatMoney(totalIndustryMoney)})
        </span>
      )}
    </div>
  );
}

export default function BillsTable({ bills, votes = [] }: BillsTableProps) {
  return (
    <div className="space-y-8">
      {/* Sponsored bills */}
      <div>
        <h4 className="mb-3 text-sm font-semibold text-zinc-300">
          Bills Sponsored
          <span className="ml-2 text-xs text-zinc-500">({bills.length})</span>
        </h4>

        {bills.length === 0 ? (
          <p className="py-4 text-sm text-zinc-500">
            No sponsored bills on record.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
                  <th className="w-1/2 px-4 py-3 font-medium">Title</th>
                  <th className="w-[8%] px-4 py-3 font-medium">Bill #</th>
                  <th className="w-[12%] px-4 py-3 font-medium">Introduced</th>
                  <th className="w-[15%] px-4 py-3 font-medium">Status</th>
                  <th className="w-[15%] px-4 py-3 font-medium">Policy Area</th>
                </tr>
              </thead>
              <tbody>
                {[...bills]
                  .sort((a, b) => {
                    const aDate = (a.connected_entity as unknown as Record<string, unknown>)?.metadata_ as Record<string, unknown>;
                    const bDate = (b.connected_entity as unknown as Record<string, unknown>)?.metadata_ as Record<string, unknown>;
                    const aStr = (aDate?.introduced_date as string) || (aDate?.introducedDate as string) || a.date_start || '';
                    const bStr = (bDate?.introduced_date as string) || (bDate?.introducedDate as string) || b.date_start || '';
                    return bStr.localeCompare(aStr); // newest first
                  })
                  .map((bill) => {
                  const meta = bill.metadata as Record<string, unknown>;
                  const entity = bill.connected_entity;
                  // Get bill metadata from the connected entity (the bill) not the relationship
                  const billMeta = (entity as unknown as Record<string, unknown>)?.metadata_ as Record<string, unknown>
                    || (entity as unknown as Record<string, unknown>)?.metadata as Record<string, unknown>
                    || meta || {};
                  const billType = (billMeta?.type as string) || (meta?.type as string) || '';
                  const billNum = (billMeta?.number as string) || (billMeta?.bill_number as string) || (meta?.number as string) || '';
                  const billNumber = billType && billNum ? `${billType}.${billNum}` : '--';
                  const status = (billMeta?.status as string) || (meta?.status as string) || 'Unknown';
                  const policyArea = (billMeta?.policy_area as string) || (billMeta?.policyArea as string) || (meta?.policyArea as string) || '--';
                  const introducedDate = (billMeta?.introduced_date as string) || (billMeta?.introducedDate as string) || '';
                  const cosponsors = (meta?.cosponsors as Array<{ slug: string; name: string }>) || [];
                  const href = entity
                    ? `/bills/${entity.slug}`
                    : null;

                  return (
                    <tr
                      key={bill.id}
                      className="border-b border-zinc-800/50 transition-colors hover:bg-zinc-800/30"
                    >
                      <td className="px-4 py-3">
                        <div>
                          {href && entity ? (
                            <Link
                              href={href}
                              className="font-medium text-zinc-200 hover:text-money-gold"
                            >
                              {entity.name}
                            </Link>
                          ) : (
                            <span className="text-zinc-300">Unknown Bill</span>
                          )}
                          {cosponsors.length > 0 && (
                            <div className="mt-1 flex flex-wrap gap-1">
                              {cosponsors.slice(0, 3).map((cs) => (
                                <Link
                                  key={cs.slug}
                                  href={`/officials/${cs.slug}`}
                                  className="text-[10px] text-zinc-500 hover:text-money-gold"
                                >
                                  {cs.name}
                                </Link>
                              ))}
                              {cosponsors.length > 3 && (
                                <span className="text-[10px] text-zinc-600">
                                  +{cosponsors.length - 3} more
                                </span>
                              )}
                            </div>
                          )}
                          {entity?.slug && <BillBadges slug={entity.slug} />}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs text-zinc-400">
                          {billNumber}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-zinc-400">
                        {formatDate(introducedDate || bill.date_start)}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={status} />
                      </td>
                      <td className="px-4 py-3">
                        {policyArea !== '--' ? (
                          <Link
                            href={`/entities/industry/${slugify(policyArea)}`}
                            className="text-zinc-400 hover:text-money-gold"
                          >
                            {policyArea}
                          </Link>
                        ) : (
                          <span className="text-zinc-400">--</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Key votes */}
      {votes.length > 0 && (
        <div>
          <h4 className="mb-3 text-sm font-semibold text-zinc-300">
            Key Votes
            <span className="ml-2 text-xs text-zinc-500">({votes.length})</span>
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
                  <th className="px-4 py-3 font-medium">Vote Description</th>
                  <th className="px-4 py-3 font-medium">Position</th>
                  <th className="px-4 py-3 font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {votes.map((vote) => {
                  const meta = vote.metadata as Record<string, unknown>;
                  const position = (meta?.vote as string) || 'Unknown';
                  const entity = vote.connected_entity;
                  const voteHref = entity ? `/bills/${entity.slug}` : null;

                  return (
                    <tr
                      key={vote.id}
                      className="border-b border-zinc-800/50 transition-colors hover:bg-zinc-800/30"
                    >
                      <td className="max-w-sm px-4 py-3">
                        {voteHref && entity ? (
                          <Link
                            href={voteHref}
                            className="text-zinc-300 hover:text-money-gold"
                          >
                            {entity.name}
                          </Link>
                        ) : (
                          <span className="text-zinc-300">
                            {entity?.name || (meta?.description as string) || 'Unknown'}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <VoteBadge position={position} />
                      </td>
                      <td className="px-4 py-3 text-zinc-400">
                        {formatDate(vote.date_start)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
