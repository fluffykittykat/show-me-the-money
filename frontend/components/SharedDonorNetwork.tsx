'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Users, ChevronDown, ChevronUp, DollarSign } from 'lucide-react';
import { formatMoney } from '@/lib/utils';
import type { SharedDonorNetwork as SharedDonorNetworkType } from '@/lib/api';

interface SharedDonorNetworkProps {
  network: SharedDonorNetworkType['network'];
  totalSharedDonors: number;
  entityName: string;
}

function SenatorRow({
  senator,
}: {
  senator: SharedDonorNetworkType['network'][number];
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-zinc-800/50 bg-money-surface">
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3 min-w-0">
          <Users className="h-4 w-4 shrink-0 text-zinc-500" />
          <div className="min-w-0">
            <Link
              href={`/officials/${senator.senator_slug}`}
              className="text-sm font-medium text-zinc-200 hover:text-money-gold transition-colors"
            >
              {senator.senator_name}
            </Link>
            <div className="flex items-center gap-3 mt-0.5">
              <span className="text-xs text-zinc-500">
                {senator.shared_donors.length} shared donor{senator.shared_donors.length !== 1 ? 's' : ''}
              </span>
              <span className="text-xs font-medium text-money-gold">
                {formatMoney(senator.total_shared_amount)}
              </span>
            </div>
          </div>
        </div>

        {senator.shared_donors.length > 0 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="ml-2 rounded-md p-1.5 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300 transition-colors"
            aria-expanded={expanded}
            aria-label={expanded ? 'Hide shared donors' : 'Show shared donors'}
          >
            {expanded ? (
              <ChevronUp className="h-4 w-4" />
            ) : (
              <ChevronDown className="h-4 w-4" />
            )}
          </button>
        )}
      </div>

      {expanded && senator.shared_donors.length > 0 && (
        <div className="border-t border-zinc-800/50 px-4 py-3">
          <p className="mb-2 text-xs font-medium uppercase tracking-wider text-zinc-500">
            Shared Donors
          </p>
          <div className="flex flex-wrap gap-1.5">
            {senator.shared_donors.map((donor) => (
              <span
                key={donor}
                className="inline-flex items-center gap-1 rounded-md bg-zinc-800/80 px-2 py-0.5 text-xs text-zinc-400"
              >
                <DollarSign className="h-3 w-3 text-money-gold/60" />
                {donor}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default function SharedDonorNetwork({
  network,
  totalSharedDonors,
  entityName,
}: SharedDonorNetworkProps) {
  if (network.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-zinc-500">
        No shared donor network data available.
      </p>
    );
  }

  // Sort by total shared amount descending
  const sorted = [...network].sort(
    (a, b) => b.total_shared_amount - a.total_shared_amount
  );

  return (
    <div>
      {/* Header */}
      <div className="mb-4 flex items-center gap-3 rounded-lg border border-zinc-800 bg-money-surface px-4 py-3">
        <Users className="h-5 w-5 shrink-0 text-money-gold" />
        <div>
          <p className="text-sm font-medium text-zinc-200">
            These officials received money from the same sources as {entityName}
          </p>
          <p className="mt-0.5 text-xs text-zinc-500">
            {totalSharedDonors} shared donor{totalSharedDonors !== 1 ? 's' : ''} identified across {network.length} official{network.length !== 1 ? 's' : ''}
          </p>
        </div>
      </div>

      {/* Senator list */}
      <div className="space-y-2">
        {sorted.map((senator) => (
          <SenatorRow key={senator.senator_slug} senator={senator} />
        ))}
      </div>
    </div>
  );
}
