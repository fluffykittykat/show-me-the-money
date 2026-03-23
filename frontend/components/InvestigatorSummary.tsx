'use client';

import Link from 'next/link';
import { Shield, AlertTriangle } from 'lucide-react';
import type { ConflictData } from '@/lib/api';
import type { Relationship } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import clsx from 'clsx';

interface InvestigatorSummaryProps {
  entitySlug: string;
  entityName: string;
  conflicts: ConflictData['conflicts'];
  conflictScore: string;
  committees?: Relationship[];
  holdings?: Relationship[];
  donations?: Relationship[];
  bills?: Relationship[];
  votes?: Relationship[];
}

const SEVERITY_ORDER: Record<string, number> = {
  critical: 4,
  high_concern: 4,
  high: 3,
  notable_pattern: 3,
  medium: 2,
  structural_relationship: 2,
  low: 1,
  connection_noted: 1,
};

const SEVERITY_LABEL: Record<string, string> = {
  critical: 'HIGH CONCERN',
  high_concern: 'HIGH CONCERN',
  high: 'NOTABLE PATTERN',
  notable_pattern: 'NOTABLE PATTERN',
  medium: 'STRUCTURAL RELATIONSHIP',
  structural_relationship: 'STRUCTURAL RELATIONSHIP',
  low: 'CONNECTION NOTED',
  connection_noted: 'CONNECTION NOTED',
  none: 'NO CONCERNS',
};

function generateNarrative(
  entityName: string,
  conflicts: ConflictData['conflicts'],
  conflictScore: string
): string {
  if (conflicts.length === 0) {
    return `Preliminary analysis of ${entityName} reveals no flagged structural relationships based on currently available financial disclosure, voting record, and campaign finance data. This assessment is limited to indexed records and should not be considered exhaustive.`;
  }

  const sorted = [...conflicts].sort(
    (a, b) =>
      (SEVERITY_ORDER[b.severity.toLowerCase()] || 0) -
      (SEVERITY_ORDER[a.severity.toLowerCase()] || 0)
  );

  const topConflicts = sorted.slice(0, 3);
  const totalEvidence = conflicts.reduce((sum, c) => sum + c.evidence.length, 0);

  const scoreLabel = SEVERITY_LABEL[conflictScore.toLowerCase()] || conflictScore.toUpperCase();

  const findings = topConflicts
    .map((c) => c.description)
    .join(' Additionally, ');

  return `Subject ${entityName} presents an overall assessment of ${scoreLabel}, with ${conflicts.length} potential conflict${conflicts.length !== 1 ? 's' : ''} of interest supported by ${totalEvidence} data points. ${findings}${sorted.length > 3 ? ` (${sorted.length - 3} additional relationships flagged.)` : ''}`;
}

function getTopDonorIndustries(donations: Relationship[]): Array<{ name: string; total: number }> {
  const byIndustry: Record<string, number> = {};
  for (const d of donations) {
    const meta = d.metadata as Record<string, unknown>;
    const industry = (meta?.industry_label as string) || (meta?.contributor_type as string) || 'Other';
    byIndustry[industry] = (byIndustry[industry] || 0) + (d.amount_usd ?? 0);
  }
  return Object.entries(byIndustry)
    .map(([name, total]) => ({ name, total }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 3);
}

export default function InvestigatorSummary({
  entitySlug,
  entityName,
  conflicts,
  conflictScore,
  committees = [],
  holdings = [],
  donations = [],
  bills = [],
  votes = [],
}: InvestigatorSummaryProps) {
  const narrative = generateNarrative(entityName, conflicts, conflictScore);
  const topDonorIndustries = getTopDonorIndustries(donations);

  // Sort conflicts by severity for the alert section
  const sortedConflicts = [...conflicts].sort(
    (a, b) =>
      (SEVERITY_ORDER[b.severity.toLowerCase()] || 0) -
      (SEVERITY_ORDER[a.severity.toLowerCase()] || 0)
  );

  // Key legislation: sponsored bills + notable votes (up to 3)
  const keyLegislation = [
    ...bills.slice(0, 2).map((b) => ({
      name: b.connected_entity?.name || 'Unknown Bill',
      slug: b.connected_entity?.slug,
      type: b.connected_entity?.entity_type,
      role: 'Sponsored',
    })),
    ...votes.slice(0, 1).map((v) => ({
      name: v.connected_entity?.name || 'Unknown',
      slug: v.connected_entity?.slug,
      type: v.connected_entity?.entity_type,
      role: v.relationship_type.includes('yes') ? 'Voted YES' : v.relationship_type.includes('no') ? 'Voted NO' : 'Voted',
    })),
  ];

  // Top holdings (up to 3, sorted by value)
  const topHoldings = [...holdings]
    .sort((a, b) => {
      const aMeta = a.metadata as Record<string, unknown>;
      const bMeta = b.metadata as Record<string, unknown>;
      return ((bMeta?.value_max as number) ?? b.amount_usd ?? 0) -
             ((aMeta?.value_max as number) ?? a.amount_usd ?? 0);
    })
    .slice(0, 3);

  const scoreLabel = SEVERITY_LABEL[conflictScore.toLowerCase()] || conflictScore.toUpperCase();

  return (
    <div className="relative overflow-hidden rounded-lg border border-zinc-700 bg-zinc-950/80">
      {/* Gold top border accent */}
      <div className="h-1 bg-gradient-to-r from-money-gold via-money-gold/60 to-transparent" />

      {/* Watermark */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-[0.02]">
        <span className="select-none text-6xl font-black uppercase tracking-[0.3em] text-white rotate-[-15deg]">
          FOLLOW THE MONEY
        </span>
      </div>

      <div className="relative p-5 sm:p-6">
        {/* Header */}
        <div className="mb-4 flex items-center justify-between border-b border-dashed border-zinc-700 pb-3">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-money-gold" />
            <span className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-money-gold">
              Intelligence Summary // Follow The Money
            </span>
          </div>
          <span className="font-mono text-xs text-zinc-600">
            REF: {entitySlug}
          </span>
        </div>

        {/* Subject + Score */}
        <div className="mb-5">
          <span className="font-mono text-xs uppercase tracking-wider text-zinc-500">
            Subject:
          </span>
          <span className="ml-2 font-mono text-sm font-semibold text-zinc-200">
            {entityName}
          </span>
          <span className="ml-3 font-mono text-xs text-zinc-500">
            Assessment:{' '}
            <span
              className={clsx(
                'font-semibold uppercase',
                (conflictScore.toLowerCase() === 'critical' || conflictScore.toLowerCase() === 'high_concern') && 'text-red-400',
                (conflictScore.toLowerCase() === 'high' || conflictScore.toLowerCase() === 'notable_pattern') && 'text-orange-400',
                (conflictScore.toLowerCase() === 'medium' || conflictScore.toLowerCase() === 'structural_relationship') && 'text-yellow-400',
                (conflictScore.toLowerCase() === 'low' || conflictScore.toLowerCase() === 'connection_noted') && 'text-blue-400',
                conflictScore.toLowerCase() === 'none' && 'text-zinc-500'
              )}
            >
              {scoreLabel}
            </span>
          </span>
        </div>

        {/* ========== 1. TOP SUMMARY BLOCK ========== */}
        <div className="mb-5 space-y-2.5 rounded-md border border-zinc-700/50 bg-zinc-900/50 p-4 font-mono text-xs leading-relaxed">
          {/* Committees */}
          {committees.length > 0 && (
            <div>
              <span className="font-bold uppercase tracking-wider text-zinc-400">
                Committees:
              </span>
              <ul className="mt-1 space-y-0.5 pl-4">
                {committees.map((c) => {
                  const meta = c.metadata as Record<string, unknown>;
                  const role = (meta?.role as string) || 'Member';
                  return (
                    <li key={c.id} className="text-zinc-300">
                      <span className="text-money-gold">&bull;</span>{' '}
                      {c.connected_entity?.slug ? (
                        <Link
                          href={`/entities/committee/${c.connected_entity.slug}`}
                          className="text-zinc-200 hover:text-money-gold"
                        >
                          {c.connected_entity.name}
                        </Link>
                      ) : (
                        c.connected_entity?.name || 'Unknown'
                      )}{' '}
                      <span className="text-zinc-500">({role})</span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {/* Key Legislation */}
          {keyLegislation.length > 0 && (
            <div>
              <span className="font-bold uppercase tracking-wider text-zinc-400">
                Key Legislation:
              </span>
              <ul className="mt-1 space-y-0.5 pl-4">
                {keyLegislation.map((bill, i) => (
                  <li key={i} className="text-zinc-300">
                    <span className="text-money-gold">&bull;</span>{' '}
                    {bill.slug && bill.type ? (
                      <Link
                        href={`/bills/${bill.slug}`}
                        className="text-zinc-200 hover:text-money-gold"
                      >
                        {bill.name}
                      </Link>
                    ) : (
                      bill.name
                    )}{' '}
                    <span className="text-zinc-500">({bill.role})</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Financial Interests */}
          {topHoldings.length > 0 && (
            <div>
              <span className="font-bold uppercase tracking-wider text-zinc-400">
                Financial Interests:
              </span>
              <ul className="mt-1 space-y-0.5 pl-4">
                {topHoldings.map((h) => (
                  <li key={h.id} className="text-zinc-300">
                    <span className="text-money-gold">&bull;</span>{' '}
                    {h.connected_entity?.slug ? (
                      <Link
                        href={`/entities/${h.connected_entity.entity_type || 'company'}/${h.connected_entity.slug}`}
                        className="text-zinc-200 hover:text-money-gold"
                      >
                        {h.connected_entity.name}
                      </Link>
                    ) : (
                      h.connected_entity?.name || 'Unknown'
                    )}{' '}
                    <span className="text-zinc-500">
                      ({h.amount_label || 'undisclosed value'})
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Top Donors */}
          {topDonorIndustries.length > 0 && (
            <div>
              <span className="font-bold uppercase tracking-wider text-zinc-400">
                Top Donors:
              </span>
              <ul className="mt-1 space-y-0.5 pl-4">
                {topDonorIndustries.map((ind, i) => (
                  <li key={i} className="text-zinc-300">
                    <span className="text-money-gold">&bull;</span>{' '}
                    {ind.name}{' '}
                    <span className="text-money-success">
                      ({formatMoney(ind.total)})
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Potential Conflicts of Interest */}
          {sortedConflicts.length > 0 && (
            <div>
              <span className="font-bold uppercase tracking-wider text-orange-400">
                <AlertTriangle className="mr-1 inline-block h-3 w-3" />
                Potential Conflicts of Interest:
              </span>
              <p className="text-xs text-zinc-500 mt-1">
                The following structural relationships have been identified. These are not accusations
                {' '}&mdash; they are public facts about financial and regulatory relationships the public has
                a right to know about.
              </p>
              <ul className="mt-1 space-y-0.5 pl-4">
                {sortedConflicts.slice(0, 3).map((c, i) => (
                  <li key={i} className="text-orange-300">
                    <span className="text-orange-400">&bull;</span>{' '}
                    {c.description}
                  </li>
                ))}
                {sortedConflicts.length > 3 && (
                  <li className="text-zinc-500">
                    ...and {sortedConflicts.length - 3} more
                  </li>
                )}
              </ul>
            </div>
          )}
        </div>

        {/* ========== 2. AI NARRATIVE (2 paragraphs max) ========== */}
        <div className="mb-4 whitespace-pre-wrap font-mono text-sm leading-relaxed text-zinc-300">
          {narrative}
        </div>

        {/* Classification footer */}
        <div className="mt-5 border-t border-dashed border-zinc-800 pt-3 text-center">
          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.3em] text-zinc-700">
            Classified // Follow The Money
          </span>
        </div>
      </div>
    </div>
  );
}
