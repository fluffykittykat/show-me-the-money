'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import type { Relationship } from '@/lib/types';
import { getStockBadge } from '@/lib/api';
import clsx from 'clsx';
import DidYouKnow from '@/components/DidYouKnow';
import { formatMoney } from '@/lib/utils';

interface FinancialTableProps {
  holdings: Relationship[];
  entityName?: string;
}

function getValueColor(label: string | null): string {
  if (!label) return 'text-zinc-400';
  // Higher value ranges get more gold coloring
  if (label.includes('$50,000,000') || label.includes('Over')) {
    return 'text-money-gold font-bold';
  }
  if (label.includes('$5,000,000') || label.includes('$1,000,000')) {
    return 'text-money-gold';
  }
  if (label.includes('$500,000') || label.includes('$100,000')) {
    return 'text-amber-400/80';
  }
  return 'text-zinc-300';
}

function HolderBadge({ slug }: { slug: string }) {
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    getStockBadge(slug).then(d => setCount(d.holder_count)).catch(() => {});
  }, [slug]);
  if (count == null || count <= 1) return null;
  return (
    <span className="ml-2 inline-flex items-center rounded-full bg-zinc-700 px-2 py-0.5 text-[10px] font-medium text-zinc-300">
      {count - 1} other official{count - 1 !== 1 ? 's' : ''} hold this
    </span>
  );
}

export default function FinancialTable({ holdings, entityName = 'This official' }: FinancialTableProps) {
  if (holdings.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500">
        No financial disclosures available.
      </p>
    );
  }

  // Sort by value_max from metadata, fallback to amount_usd
  const sorted = [...holdings].sort((a, b) => {
    const aMeta = a.metadata as Record<string, unknown>;
    const bMeta = b.metadata as Record<string, unknown>;
    const aVal = (aMeta?.value_max as number) ?? a.amount_usd ?? 0;
    const bVal = (bMeta?.value_max as number) ?? b.amount_usd ?? 0;
    return bVal - aVal;
  });

  // Calculate estimated total holdings for benchmark comparison
  const AVERAGE_SENATOR_HOLDINGS = 2100000;
  const estimatedMin = sorted.reduce((sum, h) => {
    const meta = h.metadata as Record<string, unknown>;
    return sum + ((meta?.value_min as number) ?? h.amount_usd ?? 0);
  }, 0);
  const estimatedMax = sorted.reduce((sum, h) => {
    const meta = h.metadata as Record<string, unknown>;
    return sum + ((meta?.value_max as number) ?? h.amount_usd ?? 0);
  }, 0);
  const holdingsLabel = estimatedMax > 0
    ? `${formatMoney(estimatedMin)} - ${formatMoney(estimatedMax)}`
    : 'undisclosed range';
  const aboveAverage = estimatedMax > AVERAGE_SENATOR_HOLDINGS;

  return (
    <div className="overflow-x-auto">
      {/* Compare to Average benchmark */}
      {estimatedMax > 0 && (
        <div className="mb-4 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <p className="text-xs text-zinc-400">
            <span className="font-semibold text-zinc-300">Compare to average:</span>{' '}
            Average senator holds $2.1M in stocks.{' '}
            {entityName} holds{' '}
            <span className="font-semibold text-amber-400">{holdingsLabel}</span>
            {' — '}
            <span className={aboveAverage ? 'text-amber-400 font-semibold' : 'text-zinc-400'}>
              {aboveAverage ? 'above' : 'below'} average
            </span>
          </p>
        </div>
      )}

      <DidYouKnow fact="Members of Congress aren't required to report exact stock values — only ranges like &quot;$15,001 - $50,000&quot;. The real number could be anywhere in that range." />

      <div className="mt-4" />
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
            <th className="px-4 py-3 font-medium">Asset</th>
            <th className="px-4 py-3 font-medium">Ticker</th>
            <th className="px-4 py-3 font-medium">Type</th>
            <th className="px-4 py-3 font-medium">Value Range</th>
            <th className="px-4 py-3 font-medium">Income Type</th>
            <th className="px-4 py-3 font-medium">Income Range</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((holding) => {
            const meta = holding.metadata as Record<string, unknown>;
            const ticker = (meta?.ticker as string) || '--';
            const assetType = (meta?.asset_type as string) || (meta?.type as string) || 'Stock';
            const incomeType = (meta?.income_type as string) || '--';
            const incomeMin = meta?.income_min as number | undefined;
            const incomeMax = meta?.income_max as number | undefined;
            const incomeRange = incomeMin != null && incomeMax != null
              ? `$${incomeMin.toLocaleString()}-$${incomeMax.toLocaleString()}`
              : '--';
            const entity = holding.connected_entity;
            const href = entity
              ? `/entities/${entity.entity_type}/${entity.slug}`
              : null;

            return (
              <tr
                key={holding.id}
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
                      <span className="text-zinc-300">
                        {(meta?.asset_name as string) || 'Unknown'}
                      </span>
                    )}
                    {entity?.slug && <HolderBadge slug={entity.slug} />}
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs text-zinc-300">
                    {ticker}
                  </span>
                </td>
                <td className="px-4 py-3 text-zinc-400">{assetType}</td>
                <td className={clsx('px-4 py-3', getValueColor(holding.amount_label))}>
                  {holding.amount_label || '--'}
                </td>
                <td className="px-4 py-3 text-zinc-400">{incomeType}</td>
                <td className="px-4 py-3 text-zinc-400">{incomeRange}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
