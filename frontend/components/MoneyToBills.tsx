'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { getMoneyToBills } from '@/lib/api';
import type { MoneyToBillsResponse, MoneyToBillChain } from '@/lib/api';
import { formatMoney } from '@/lib/utils';
import { ArrowRight, FileText } from 'lucide-react';

interface MoneyToBillsProps {
  slug: string;
}

function ChainCard({ chain }: { chain: MoneyToBillChain }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
      {/* Policy area header */}
      <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-money-gold">
        {chain.policy_area}
      </h4>

      {/* Narrative */}
      <p className="mb-4 text-sm leading-relaxed text-zinc-400">
        {chain.narrative}
      </p>

      {/* Top Donors */}
      {chain.top_donors.length > 0 && (
        <div className="mb-4">
          <span className="mb-2 block text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
            Top Donors
          </span>
          <div className="space-y-1.5">
            {chain.top_donors.map((donor) => (
              <div key={donor.slug} className="flex items-center justify-between">
                <Link
                  href={`/entities/organization/${donor.slug}`}
                  className="truncate text-sm text-zinc-300 hover:text-money-gold"
                >
                  {donor.name}
                </Link>
                <div className="ml-3 flex shrink-0 items-center gap-2">
                  <span className="text-sm font-semibold text-money-success">
                    {formatMoney(donor.amount)}
                  </span>
                  <ArrowRight className="h-3 w-3 text-zinc-600" />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Related Bills */}
      {chain.related_bills.length > 0 && (
        <div className="mb-3">
          <span className="mb-2 block text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
            Related Bills
          </span>
          <ul className="space-y-1.5">
            {chain.related_bills.map((bill) => (
              <li key={bill.slug} className="flex items-center gap-2">
                <FileText className="h-3.5 w-3.5 shrink-0 text-zinc-600" />
                <Link
                  href={`/bills/${bill.slug}`}
                  className="truncate text-sm text-zinc-300 hover:text-money-gold"
                >
                  {bill.name}
                </Link>
                <ArrowRight className="ml-auto h-3 w-3 shrink-0 text-zinc-600" />
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Total */}
      <div className="mt-3 flex items-center justify-between border-t border-zinc-800 pt-3">
        <span className="text-xs text-zinc-500">
          {chain.donor_count} donor{chain.donor_count !== 1 ? 's' : ''} &middot;{' '}
          {chain.bill_count} bill{chain.bill_count !== 1 ? 's' : ''}
        </span>
        <span className="text-sm font-bold text-money-success">
          {formatMoney(chain.total_donated)}
        </span>
      </div>
    </div>
  );
}

export default function MoneyToBills({ slug }: MoneyToBillsProps) {
  const [data, setData] = useState<MoneyToBillsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    getMoneyToBills(slug)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, [slug]);

  if (loading) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
        <h3 className="mb-3 text-sm font-bold uppercase tracking-wider text-zinc-400">
          Money &rarr; Bills
        </h3>
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-money-gold" />
          Tracing money to legislation&hellip;
        </div>
      </div>
    );
  }

  if (error || !data || data.chains.length === 0) {
    return null;
  }

  return (
    <div className="mb-6">
      <div className="mb-4 rounded-xl border-2 border-money-gold/30 bg-zinc-900/80 p-5">
        <h3 className="flex items-center gap-2 text-lg font-bold text-money-gold">
          <span className="text-xl">&#128176;</span>
          Follow the Money
        </h3>
        <p className="mt-1 text-sm text-zinc-400">
          These donors gave money to this official, who then sponsored or cosponsored legislation
          in the same policy areas. Does the money influence the bills? You decide.
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {data.chains.map((chain) => (
          <ChainCard key={chain.policy_area} chain={chain} />
        ))}
      </div>
    </div>
  );
}
