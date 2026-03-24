'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { formatMoney } from '@/lib/utils';
import { Users, ChevronDown, ChevronUp } from 'lucide-react';

interface PacDonor {
  name: string;
  slug: string;
  amount: number;
  date: string | null;
  employer: string;
}

interface PacDonorsResponse {
  entity_slug: string;
  entity_name: string;
  fec_committee_id: string | null;
  donors: PacDonor[];
  total_donors: number;
  source: 'cached' | 'fec_live';
}

interface PacDonorsProps {
  slug: string;
  entityName: string;
}

export default function PacDonors({ slug, entityName }: PacDonorsProps) {
  const [data, setData] = useState<PacDonorsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/entities/${encodeURIComponent(slug)}/pac-donors`)
      .then((res) => {
        if (!res.ok) throw new Error('Failed');
        return res.json();
      })
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch(() => {
        setLoading(false);
      });
  }, [slug]);

  if (loading) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-money-gold" />
          Looking up who funds {entityName}...
        </div>
      </div>
    );
  }

  if (!data || data.donors.length === 0) return null;

  const visibleDonors = expanded ? data.donors : data.donors.slice(0, 10);
  const hasMore = data.donors.length > 10;

  return (
    <section className="mb-8">
      <div className="mb-3 flex items-center gap-2">
        <Users className="h-5 w-5 text-money-gold" />
        <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-400">
          Who Funds This Committee
        </h2>
        {data.source === 'fec_live' && (
          <span className="rounded-full bg-green-500/10 px-2 py-0.5 text-[10px] font-medium text-green-400">
            Live from FEC
          </span>
        )}
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
              <th className="px-4 py-3 font-medium">Donor</th>
              <th className="px-4 py-3 font-medium">Employer</th>
              <th className="px-4 py-3 font-medium text-right">Amount</th>
              <th className="px-4 py-3 font-medium hidden sm:table-cell">Date</th>
            </tr>
          </thead>
          <tbody>
            {visibleDonors.map((donor, i) => (
              <tr
                key={`${donor.slug}-${i}`}
                className="border-b border-zinc-800/50 transition-colors hover:bg-zinc-800/30"
              >
                <td className="px-4 py-3">
                  <Link
                    href={`/entities/donor/${donor.slug}`}
                    className="font-medium text-zinc-200 hover:text-money-gold"
                  >
                    {donor.name}
                  </Link>
                </td>
                <td className="px-4 py-3 text-zinc-400 text-xs">
                  {donor.employer || '--'}
                </td>
                <td className="px-4 py-3 text-right font-semibold text-money-success">
                  {formatMoney(donor.amount)}
                </td>
                <td className="px-4 py-3 text-zinc-500 text-xs hidden sm:table-cell">
                  {donor.date || '--'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {hasMore && (
          <div className="border-t border-zinc-800 px-4 py-2">
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 text-xs font-medium text-money-gold hover:text-money-gold-hover"
            >
              {expanded ? (
                <>
                  <ChevronUp className="h-3 w-3" />
                  Show less
                </>
              ) : (
                <>
                  <ChevronDown className="h-3 w-3" />
                  Show all {data.total_donors} donors
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
