'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  ChevronDown,
  ChevronUp,
  Heart,
  Building2,
  AlertTriangle,
  Loader2,
} from 'lucide-react';
import type { FamilyConnectionItem } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import DidYouKnow from '@/components/DidYouKnow';

interface FamilyConnectionsSectionProps {
  items: FamilyConnectionItem[];
  loading?: boolean;
  entityName?: string;
  officialName?: string;
}

function FamilyCard({ item, officialName }: { item: FamilyConnectionItem; officialName?: string }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 sm:p-5 transition-colors hover:border-zinc-700">
      {/* Header: SPOUSE/FAMILY INCOME */}
      <div className="mb-3">
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <Heart className="h-4 w-4 text-amber-500" />
          <span className="text-[10px] font-bold uppercase tracking-wider text-amber-400">
            {item.relationship} Income
          </span>
        </div>
        <p className="text-sm text-zinc-200 font-semibold">
          {item.family_member}
          <span className="ml-1 text-xs font-normal text-zinc-500">({item.relationship})</span>
        </p>
      </div>

      {/* Income from */}
      <div className="ml-6 space-y-3">
        <div>
          <p className="text-xs text-zinc-400 mb-1">
            receives income from:
          </p>
          <div className="flex items-start gap-2">
            <Building2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-zinc-500" />
            <div>
              {item.employer_slug ? (
                <Link
                  href={`/entities/company/${item.employer_slug}`}
                  className="text-sm font-medium text-zinc-200 hover:text-amber-400 transition-colors"
                >
                  {item.employer_name}
                </Link>
              ) : (
                <span className="text-sm font-medium text-zinc-200">{item.employer_name}</span>
              )}
              <p className="text-xs text-zinc-400">{item.role}</p>
            </div>
          </div>
        </div>

        {/* Annual income */}
        {item.annual_income != null && (
          <div>
            <span className="text-xl font-bold text-amber-400">
              {formatMoney(item.annual_income)}
            </span>
            <span className="text-xs font-normal text-zinc-500 ml-1">/year</span>
          </div>
        )}

        {/* Committee overlap warning */}
        {item.committee_overlap && (
          <div className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
              <p className="text-xs text-amber-400">
                {item.employer_name} is regulated by {item.committee_overlap}
                {officialName ? `, which ${officialName} sits on` : ''}
              </p>
            </div>
          </div>
        )}
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

export default function FamilyConnectionsSection({ items, loading, entityName, officialName }: FamilyConnectionsSectionProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
        <span className="ml-2 text-sm text-zinc-500">Loading family connections...</span>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 px-6 py-8 text-center">
        <Heart className="mx-auto h-8 w-8 text-zinc-600" />
        <p className="mt-3 text-sm text-zinc-500">
          No family financial connections found{entityName ? ` for ${entityName}` : ''}.
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Section header */}
      <div className="mb-4">
        <h3 className="flex items-center gap-2 text-base font-bold text-zinc-100">
          <span className="text-lg">&#128104;&#8205;&#128105;&#8205;&#128103;</span>
          Family Financial Interests
        </h3>
        <p className="mt-1 text-sm text-zinc-400">
          When your family&apos;s income comes from companies you regulate
        </p>
      </div>

      {/* Cards */}
      <div className="space-y-3">
        {items.map((item, i) => (
          <FamilyCard key={`${item.family_member}-${i}`} item={item} officialName={officialName || entityName} />
        ))}
      </div>

      <DidYouKnow fact="An official's spouse or child can legally work for companies the official regulates. Financial disclosures reveal this — but nobody puts it in one place." />

      {/* Disclaimer */}
      <p className="mt-3 text-[10px] text-zinc-600 italic">
        Family financial interests are disclosed publicly. These connections are worth knowing about, not proof of wrongdoing.
      </p>
    </div>
  );
}
