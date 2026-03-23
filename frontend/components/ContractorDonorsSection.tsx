'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  ChevronDown,
  ChevronUp,
  ArrowRight,
  Building2,
  DollarSign,
  AlertTriangle,
  MapPin,
  Loader2,
} from 'lucide-react';
import type { ContractorDonorItem } from '@/lib/types';
import { formatMoney, formatDate } from '@/lib/utils';
import DidYouKnow from '@/components/DidYouKnow';

interface ContractorDonorsSectionProps {
  items: ContractorDonorItem[];
  loading?: boolean;
  entityName?: string;
  totalDonations?: number;
  totalContracts?: number;
}

function ContractorCard({ item }: { item: ContractorDonorItem }) {
  const [expanded, setExpanded] = useState(false);
  const multiple = item.dollars_per_donation_dollar != null && item.dollars_per_donation_dollar > 0
    ? Math.round(item.dollars_per_donation_dollar)
    : null;

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 sm:p-5 transition-colors hover:border-zinc-700">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <Building2 className="h-4 w-4 text-amber-500" />
        {item.contractor_slug ? (
          <Link
            href={`/entities/company/${item.contractor_slug}`}
            className="text-sm font-semibold text-zinc-200 hover:text-amber-400 transition-colors"
          >
            {item.contractor_name}
          </Link>
        ) : (
          <span className="text-sm font-semibold text-zinc-200">{item.contractor_name}</span>
        )}
        {item.state && (
          <span className="inline-flex items-center gap-1 rounded-full bg-zinc-700 px-2 py-0.5 text-[10px] font-medium text-zinc-400">
            <MapPin className="h-2.5 w-2.5" />
            {item.state}
          </span>
        )}
        {multiple != null && multiple > 1 && (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-500/20 px-2 py-0.5 text-[10px] font-bold uppercase text-red-400">
            {multiple}x return
          </span>
        )}
      </div>

      {/* Donation -> Contract flow */}
      <div className="ml-6 flex flex-wrap items-center gap-3 mb-3">
        <div className="rounded-lg border border-zinc-700 bg-zinc-950 px-4 py-3 text-center min-w-[120px]">
          <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 block">
            Donated
          </span>
          <span className="text-lg font-bold text-amber-400">
            {formatMoney(item.donation_amount)}
          </span>
          {item.donation_date && (
            <span className="block text-[10px] text-zinc-500">{formatDate(item.donation_date)}</span>
          )}
        </div>

        <div className="flex flex-col items-center">
          <ArrowRight className="h-5 w-5 text-amber-500/60" />
        </div>

        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-center min-w-[120px]">
          <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 block">
            Received in contracts
          </span>
          <span className="text-lg font-bold text-green-400">
            {formatMoney(item.contract_amount)}
          </span>
          {item.contract_date && (
            <span className="block text-[10px] text-zinc-500">{formatDate(item.contract_date)}</span>
          )}
        </div>
      </div>

      {/* Contract details */}
      <div className="ml-6 space-y-1.5 mb-2">
        <div className="flex items-center gap-2 text-xs text-zinc-400">
          <span className="font-medium text-zinc-500">Agency:</span>
          <span>{item.contract_agency}</span>
        </div>
        <div className="text-xs text-zinc-400">
          <span className="font-medium text-zinc-500">Contract:</span>{' '}
          {item.contract_description}
        </div>
      </div>

      {/* WHY THIS MATTERS */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-zinc-400 hover:text-zinc-200 transition-colors"
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronUp className="h-3.5 w-3.5" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5" />
        )}
        Why this matters
      </button>

      {expanded && (
        <div className="mt-2 rounded-md border border-zinc-700/50 bg-zinc-800/30 px-3 py-2.5">
          <p className="text-xs leading-relaxed text-zinc-400">
            {item.why_this_matters}
          </p>
        </div>
      )}
    </div>
  );
}

export default function ContractorDonorsSection({
  items,
  loading,
  entityName,
  totalDonations,
  totalContracts,
}: ContractorDonorsSectionProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
        <span className="ml-2 text-sm text-zinc-500">Loading contractor donor data...</span>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 px-6 py-8 text-center">
        <Building2 className="mx-auto h-8 w-8 text-zinc-600" />
        <p className="mt-3 text-sm text-zinc-500">
          No contractor-donor connections found{entityName ? ` for ${entityName}` : ''}.
        </p>
      </div>
    );
  }

  const calcTotalDonations = totalDonations ?? items.reduce((sum, i) => sum + i.donation_amount, 0);
  const calcTotalContracts = totalContracts ?? items.reduce((sum, i) => sum + i.contract_amount, 0);

  return (
    <div>
      {/* Section header */}
      <div className="mb-4">
        <h3 className="flex items-center gap-2 text-base font-bold text-zinc-100">
          <span className="text-lg">&#127959;</span>
          Contractor Connections
        </h3>
        <p className="mt-1 text-sm text-zinc-400">
          These companies donated to the campaign AND received federal contracts.
        </p>
      </div>

      {/* Summary table */}
      <div className="mb-4 rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800">
              <th className="px-4 py-2 text-left text-[10px] font-bold uppercase tracking-wider text-zinc-500">Company</th>
              <th className="px-4 py-2 text-right text-[10px] font-bold uppercase tracking-wider text-zinc-500">Donated</th>
              <th className="px-4 py-2 text-right text-[10px] font-bold uppercase tracking-wider text-zinc-500">Received</th>
              <th className="px-4 py-2 text-right text-[10px] font-bold uppercase tracking-wider text-zinc-500">Multiple</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, i) => {
              const multiple = item.dollars_per_donation_dollar != null && item.dollars_per_donation_dollar > 0
                ? Math.round(item.dollars_per_donation_dollar)
                : null;
              return (
                <tr key={`${item.contractor_name}-${i}`} className="border-b border-zinc-800/50 last:border-0">
                  <td className="px-4 py-2 text-zinc-300 font-medium">
                    {item.contractor_slug ? (
                      <Link
                        href={`/entities/company/${item.contractor_slug}`}
                        className="hover:text-amber-400 transition-colors"
                      >
                        {item.contractor_name}
                      </Link>
                    ) : (
                      item.contractor_name
                    )}
                  </td>
                  <td className="px-4 py-2 text-right text-amber-400">{formatMoney(item.donation_amount)}</td>
                  <td className="px-4 py-2 text-right text-green-400">{formatMoney(item.contract_amount)}</td>
                  <td className="px-4 py-2 text-right">
                    {multiple != null && multiple > 1 ? (
                      <span className="text-red-400 font-bold">{multiple}x</span>
                    ) : (
                      <span className="text-zinc-500">--</span>
                    )}
                  </td>
                </tr>
              );
            })}
            <tr className="bg-zinc-800/30">
              <td className="px-4 py-2 text-zinc-400 font-bold">Total ({items.length} companies)</td>
              <td className="px-4 py-2 text-right text-amber-400 font-bold">{formatMoney(calcTotalDonations)}</td>
              <td className="px-4 py-2 text-right text-green-400 font-bold">{formatMoney(calcTotalContracts)}</td>
              <td className="px-4 py-2"></td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Detailed cards */}
      <div className="space-y-3">
        {items.map((item, i) => (
          <ContractorCard key={`${item.contractor_name}-${i}`} item={item} />
        ))}
      </div>

      <DidYouKnow fact="Companies that donate to campaigns sometimes later receive millions in government contracts. The connection is public record — just never shown together." />

      {/* Disclaimer */}
      <p className="mt-3 text-[10px] text-zinc-600 italic">
        Campaign donations and federal contracts are both legal. The pattern of donating and then receiving contracts raises questions worth asking.
      </p>
    </div>
  );
}
