'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { getMoneyToBills } from '@/lib/api';
import type { MoneyToBillsResponse } from '@/lib/api';
import { formatMoney } from '@/lib/utils';
import { ArrowRight, FileText } from 'lucide-react';

interface MoneyToBillsProps {
  slug: string;
}

interface DonorWithBills {
  name: string;
  slug: string;
  amount: number;
  policyAreas: string[];
  bills: { name: string; slug: string }[];
}

export default function MoneyToBills({ slug }: MoneyToBillsProps) {
  const [donors, setDonors] = useState<DonorWithBills[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError(false);
    getMoneyToBills(slug)
      .then((res) => {
        // Regroup: instead of policy area → donors, flip to donor → policy areas + bills
        const donorMap = new Map<string, DonorWithBills>();

        for (const chain of res.chains) {
          for (const donor of chain.top_donors) {
            if (!donorMap.has(donor.slug)) {
              donorMap.set(donor.slug, {
                name: donor.name,
                slug: donor.slug,
                amount: donor.amount,
                policyAreas: [],
                bills: [],
              });
            }
            const entry = donorMap.get(donor.slug)!;
            if (!entry.policyAreas.includes(chain.policy_area)) {
              entry.policyAreas.push(chain.policy_area);
            }
            for (const bill of chain.related_bills) {
              if (!entry.bills.find((b) => b.slug === bill.slug)) {
                entry.bills.push({ name: bill.name, slug: bill.slug });
              }
            }
          }
        }

        const sorted = Array.from(donorMap.values()).sort((a, b) => b.amount - a.amount);
        setDonors(sorted);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
      });
  }, [slug]);

  if (loading) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 mb-6">
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-600 border-t-money-gold" />
          Tracing money to legislation&hellip;
        </div>
      </div>
    );
  }

  if (error || donors.length === 0) {
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
          These donors gave money to this official, who then sponsored or cosponsored
          legislation in policy areas that could benefit those donors.
        </p>
      </div>

      <div className="space-y-3">
        {donors.map((donor) => (
          <div
            key={donor.slug}
            className="rounded-xl border border-zinc-800 bg-zinc-900 p-4"
          >
            {/* Donor header: name + single amount */}
            <div className="flex items-center justify-between mb-3">
              <Link
                href={`/entities/organization/${donor.slug}`}
                className="text-sm font-semibold text-zinc-200 hover:text-money-gold"
              >
                {donor.name}
              </Link>
              <span className="text-sm font-bold text-money-success">
                {formatMoney(donor.amount)}
              </span>
            </div>

            {/* Policy areas this money touches */}
            <div className="flex flex-wrap gap-1.5 mb-3">
              {donor.policyAreas.map((area) => (
                <span
                  key={area}
                  className="inline-flex items-center rounded-full bg-money-gold/10 px-2 py-0.5 text-[10px] font-medium text-money-gold"
                >
                  {area}
                </span>
              ))}
            </div>

            {/* Bills connected to this donor's money */}
            <div className="space-y-1">
              {donor.bills.slice(0, 4).map((bill) => (
                <Link
                  key={bill.slug}
                  href={`/bills/${bill.slug}`}
                  className="flex items-center gap-2 text-xs text-zinc-400 hover:text-money-gold"
                >
                  <FileText className="h-3 w-3 shrink-0 text-zinc-600" />
                  <span className="truncate">{bill.name}</span>
                  <ArrowRight className="ml-auto h-3 w-3 shrink-0 text-zinc-700" />
                </Link>
              ))}
              {donor.bills.length > 4 && (
                <span className="text-[10px] text-zinc-600">
                  + {donor.bills.length - 4} more bills
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
