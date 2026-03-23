'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  ChevronDown,
  ChevronUp,
  Mic,
  AlertTriangle,
  Building2,
  Loader2,
} from 'lucide-react';
import clsx from 'clsx';
import type { OutsideIncomeItem } from '@/lib/types';
import { formatMoney, formatDate } from '@/lib/utils';
import DidYouKnow from '@/components/DidYouKnow';

interface OutsideIncomeSectionProps {
  items: OutsideIncomeItem[];
  loading?: boolean;
  entityName?: string;
}

function getIncomeTypeBadge(type: string): { bg: string; text: string } {
  const t = type.toLowerCase();
  if (t.includes('speaking')) return { bg: 'bg-purple-500/20 text-purple-400', text: 'Speaking Fee' };
  if (t.includes('book')) return { bg: 'bg-blue-500/20 text-blue-400', text: 'Book Deal' };
  if (t.includes('honorar')) return { bg: 'bg-teal-500/20 text-teal-400', text: 'Honorarium' };
  if (t.includes('consult')) return { bg: 'bg-orange-500/20 text-orange-400', text: 'Consulting' };
  return { bg: 'bg-zinc-700 text-zinc-300', text: type };
}

function IncomeCard({ item }: { item: OutsideIncomeItem }) {
  const [expanded, setExpanded] = useState(false);
  const badge = getIncomeTypeBadge(item.income_type);

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 sm:p-5 transition-colors hover:border-zinc-700">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 mb-2">
        {item.payer_slug ? (
          <Link
            href={`/entities/company/${item.payer_slug}`}
            className="text-sm font-semibold text-zinc-200 hover:text-amber-400 transition-colors"
          >
            {item.payer_name}
          </Link>
        ) : (
          <span className="text-sm font-semibold text-zinc-200">{item.payer_name}</span>
        )}
        <span className={clsx('rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider', badge.bg)}>
          {badge.text}
        </span>
        {item.is_regulated_industry && (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-500/20 px-2 py-0.5 text-[10px] font-bold uppercase text-red-400">
            <AlertTriangle className="h-2.5 w-2.5" />
            Regulated industry
          </span>
        )}
      </div>

      {/* Amount + date */}
      <div className="mb-2 flex flex-wrap items-baseline gap-3">
        <span className="text-xl font-bold text-amber-400">
          {formatMoney(item.amount_usd)}
        </span>
        {item.date && (
          <span className="text-xs text-zinc-500">{formatDate(item.date)}</span>
        )}
      </div>

      {/* Event description */}
      {item.event_description && (
        <p className="text-sm text-zinc-400 mb-2">{item.event_description}</p>
      )}

      {/* Committee overlap */}
      {item.committee_overlap && (
        <div className="flex items-center gap-2 mb-2">
          <Building2 className="h-3.5 w-3.5 text-amber-500" />
          <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-0.5 text-xs font-medium text-amber-400">
            Payer regulated by: {item.committee_overlap}
          </span>
        </div>
      )}

      {/* WHY THIS MATTERS */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-zinc-400 hover:text-zinc-200 transition-colors"
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

export default function OutsideIncomeSection({ items, loading, entityName }: OutsideIncomeSectionProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
        <span className="ml-2 text-sm text-zinc-500">Loading outside income data...</span>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 px-6 py-8 text-center">
        <Mic className="mx-auto h-8 w-8 text-zinc-600" />
        <p className="mt-3 text-sm text-zinc-500">
          No outside income records found{entityName ? ` for ${entityName}` : ''}.
        </p>
      </div>
    );
  }

  const totalIncome = items.reduce((sum, item) => sum + item.amount_usd, 0);
  const governmentSalary = 174000;
  const maxVal = Math.max(totalIncome, governmentSalary);
  const outsidePct = maxVal > 0 ? (totalIncome / maxVal) * 100 : 0;
  const salaryPct = maxVal > 0 ? (governmentSalary / maxVal) * 100 : 0;

  return (
    <div>
      {/* Section header */}
      <div className="mb-4">
        <h3 className="flex items-center gap-2 text-base font-bold text-zinc-100">
          <span className="text-lg">&#127908;</span>
          Outside Income
        </h3>
        <p className="mt-1 text-sm text-zinc-400">
          Who else is paying them &mdash; and what do they want?
        </p>
      </div>

      {/* Visual bar comparison */}
      <div className="mb-4 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
        <div className="space-y-3">
          {/* Outside income bar */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                Outside income
              </span>
              <span className="text-sm font-bold text-amber-400">{formatMoney(totalIncome)}</span>
            </div>
            <div className="h-4 w-full rounded-full bg-zinc-800 overflow-hidden">
              <div
                className="h-full rounded-full bg-amber-500 transition-all duration-500"
                style={{ width: `${outsidePct}%` }}
              />
            </div>
          </div>

          {/* Government salary bar */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                Government salary
              </span>
              <span className="text-sm font-bold text-zinc-400">{formatMoney(governmentSalary)}</span>
            </div>
            <div className="h-4 w-full rounded-full bg-zinc-800 overflow-hidden">
              <div
                className="h-full rounded-full bg-zinc-600 transition-all duration-500"
                style={{ width: `${salaryPct}%` }}
              />
            </div>
          </div>
        </div>

        {totalIncome > governmentSalary && (
          <div className="mt-3 flex items-center gap-1.5">
            <AlertTriangle className="h-4 w-4 text-amber-500" />
            <span className="text-xs font-medium text-amber-400">
              Outside income exceeds government salary by {formatMoney(totalIncome - governmentSalary)}
            </span>
          </div>
        )}
      </div>

      {/* Cards */}
      <div className="space-y-3">
        {items.map((item, i) => (
          <IncomeCard key={`${item.payer_name}-${i}`} item={item} />
        ))}
      </div>

      <DidYouKnow fact="Major corporations pay politicians $50,000+ for a single speech. The corporations that pay the most are often regulated by those same politicians." />

      {/* Compare to Average benchmark */}
      <div className="mt-4 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
        <p className="text-xs text-zinc-400">
          <span className="font-semibold text-zinc-300">Compare to average:</span>{' '}
          Average senator receives $45,000 in outside income.{' '}
          {entityName || 'This official'} receives{' '}
          <span className="font-semibold text-amber-400">{formatMoney(totalIncome)}</span>
          {' — '}
          <span className={totalIncome > 45000 ? 'text-amber-400 font-semibold' : 'text-zinc-400'}>
            {totalIncome > 45000 ? 'above' : 'below'} average
          </span>
        </p>
      </div>

      {/* Disclaimer */}
      <p className="mt-3 text-[10px] text-zinc-600 italic">
        Outside income is publicly disclosed and often legal. The question is whether it creates a conflict with their official duties.
      </p>
    </div>
  );
}
