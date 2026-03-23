'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  ChevronDown,
  ChevronUp,
  Eye,
  AlertTriangle,
  Loader2,
} from 'lucide-react';
import clsx from 'clsx';
import type { HiddenConnectionsSummary } from '@/lib/types';
import { formatMoney } from '@/lib/utils';

interface HiddenConnectionsCardProps {
  summary: HiddenConnectionsSummary | null;
  loading?: boolean;
  entityName?: string;
  onViewDetails?: (section: string) => void;
  onSectionClick?: (section: string) => void;
}

function CountBadge({ count, label, color }: { count: number; label: string; color: string }) {
  if (count === 0) return null;
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold',
        color
      )}
    >
      {count} {label}
    </span>
  );
}

function SectionButton({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-md border border-zinc-700/50 bg-zinc-800/30 px-3 py-2.5 hover:border-amber-500/30 hover:bg-zinc-800/50 transition-colors group"
    >
      {children}
    </button>
  );
}

export default function HiddenConnectionsCard({
  summary,
  loading,
  entityName,
  onViewDetails,
  onSectionClick,
}: HiddenConnectionsCardProps) {
  const [expanded, setExpanded] = useState(false);

  const handleSectionClick = onViewDetails || onSectionClick;

  if (loading) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
        <div className="flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-zinc-500" />
          <span className="text-sm text-zinc-500">Loading hidden connections...</span>
        </div>
      </div>
    );
  }

  if (!summary) {
    return null;
  }

  const totalConnections =
    summary.revolving_door_count +
    summary.family_connections_count +
    summary.contractor_donors_count +
    summary.trade_timing_flagged_count +
    (summary.outside_income.length > 0 ? 1 : 0);

  const hasAny = totalConnections > 0 || summary.outside_income_total > 0;

  if (!hasAny) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4">
        <div className="flex items-center gap-2">
          <Eye className="h-4 w-4 text-zinc-500" />
          <span className="text-sm text-zinc-500">
            No hidden connections identified for {entityName || summary.entity_name}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border-2 border-amber-500/30 bg-zinc-900 shadow-[0_0_15px_rgba(245,158,11,0.05)]">
      {/* Collapsed header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full p-4 sm:p-5 text-left"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Eye className="h-5 w-5 text-amber-500" />
              <h3 className="text-sm font-bold uppercase tracking-wider text-amber-400">
                Hidden Connections
              </h3>
              <span className="text-[10px] text-zinc-500">
                &mdash; What you didn&apos;t know to look for
              </span>
            </div>

            {/* Count badges when collapsed */}
            {!expanded && (
              <div className="mt-2 flex flex-wrap gap-2">
                <CountBadge
                  count={summary.revolving_door_count}
                  label="revolving door"
                  color="bg-amber-500/20 text-amber-400"
                />
                <CountBadge
                  count={summary.family_connections_count}
                  label="family ties"
                  color="bg-pink-500/20 text-pink-400"
                />
                {summary.outside_income_total > 0 && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-purple-500/20 px-2.5 py-0.5 text-xs font-semibold text-purple-400">
                    {formatMoney(summary.outside_income_total)} outside income
                  </span>
                )}
                <CountBadge
                  count={summary.contractor_donors_count}
                  label="contractor donors"
                  color="bg-green-500/20 text-green-400"
                />
                <CountBadge
                  count={summary.trade_timing_flagged_count}
                  label="flagged trades"
                  color="bg-red-500/20 text-red-400"
                />
              </div>
            )}
          </div>

          <div className="shrink-0 mt-1">
            {expanded ? (
              <ChevronUp className="h-5 w-5 text-zinc-400" />
            ) : (
              <ChevronDown className="h-5 w-5 text-zinc-400" />
            )}
          </div>
        </div>
      </button>

      {/* Expanded intelligence briefing */}
      {expanded && (
        <div className="border-t border-zinc-800 px-4 sm:px-5 pb-4 sm:pb-5 pt-4 space-y-3">
          {/* Revolving Door */}
          {summary.revolving_door_count > 0 && (
            <SectionButton onClick={() => handleSectionClick?.('revolving_door')}>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-base">&#128682;</span>
                <span className="text-xs font-bold uppercase tracking-wider text-amber-400">
                  Revolving Door
                </span>
              </div>
              <ul className="ml-6 space-y-1">
                <li className="text-sm text-zinc-300">
                  {summary.revolving_door_count} former staffer{summary.revolving_door_count !== 1 ? 's' : ''} now lobby{summary.revolving_door_count === 1 ? 's' : ''} their committees
                </li>
                {summary.revolving_door[0] && (
                  <li className="text-xs text-zinc-400">
                    {summary.revolving_door[0].lobbyist_slug ? (
                      <Link href={`/entities/person/${summary.revolving_door[0].lobbyist_slug}`} className="text-zinc-300 hover:text-amber-400">
                        {summary.revolving_door[0].lobbyist_name}
                      </Link>
                    ) : summary.revolving_door[0].lobbyist_name}: {summary.revolving_door[0].former_position} &rarr; {summary.revolving_door[0].current_employer}
                  </li>
                )}
              </ul>
            </SectionButton>
          )}

          {/* Family Connections */}
          {summary.family_connections_count > 0 && (
            <SectionButton onClick={() => handleSectionClick?.('family')}>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-base">&#128104;&#8205;&#128105;&#8205;&#128103;</span>
                <span className="text-xs font-bold uppercase tracking-wider text-pink-400">
                  Family Connections
                </span>
              </div>
              <ul className="ml-6 space-y-1">
                {summary.family_connections.slice(0, 2).map((fc, i) => (
                  <li key={i} className="text-sm text-zinc-300">
                    {fc.family_member} ({fc.relationship}): employed by{' '}
                    {fc.employer_slug ? (
                      <Link href={`/entities/company/${fc.employer_slug}`} className="text-zinc-200 hover:text-amber-400">
                        {fc.employer_name}
                      </Link>
                    ) : fc.employer_name}
                    {fc.annual_income != null && (
                      <span className="text-amber-400 font-medium"> ({formatMoney(fc.annual_income)}/year)</span>
                    )}
                  </li>
                ))}
                {summary.family_connections[0]?.committee_overlap && (
                  <li className="text-xs text-amber-400">
                    Committee overlap: {summary.family_connections[0].committee_overlap}
                  </li>
                )}
              </ul>
            </SectionButton>
          )}

          {/* Outside Income */}
          {summary.outside_income.length > 0 && (
            <SectionButton onClick={() => handleSectionClick?.('outside_income')}>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-base">&#127908;</span>
                <span className="text-xs font-bold uppercase tracking-wider text-purple-400">
                  Outside Income
                </span>
              </div>
              <ul className="ml-6 space-y-1">
                <li className="text-sm text-zinc-300">
                  Total: <span className="font-medium text-amber-400">{formatMoney(summary.outside_income_total)}</span> from {summary.outside_income.length} source{summary.outside_income.length !== 1 ? 's' : ''}
                </li>
                {summary.outside_income.filter(oi => oi.is_regulated_industry).slice(0, 1).map((oi, i) => (
                  <li key={i} className="text-xs text-red-400">
                    <AlertTriangle className="inline h-3 w-3 mr-1" />
                    {formatMoney(oi.amount_usd)} from{' '}
                    {oi.payer_slug ? (
                      <Link href={`/entities/company/${oi.payer_slug}`} className="hover:text-amber-400">{oi.payer_name}</Link>
                    ) : oi.payer_name}{' '}
                    (regulated industry)
                  </li>
                ))}
              </ul>
            </SectionButton>
          )}

          {/* Contractor Connections */}
          {summary.contractor_donors_count > 0 && (
            <SectionButton onClick={() => handleSectionClick?.('contractors')}>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-base">&#127959;</span>
                <span className="text-xs font-bold uppercase tracking-wider text-green-400">
                  Contractor Connections
                </span>
              </div>
              <ul className="ml-6 space-y-1">
                <li className="text-sm text-zinc-300">
                  {summary.contractor_donors_count} compan{summary.contractor_donors_count !== 1 ? 'ies' : 'y'} donated + received contracts
                </li>
                <li className="text-sm text-zinc-300">
                  Total: <span className="text-amber-400 font-medium">{formatMoney(summary.contractor_total_donations)}</span> donated &rarr; <span className="text-green-400 font-medium">{formatMoney(summary.contractor_total_contracts)}</span> in contracts
                </li>
              </ul>
            </SectionButton>
          )}

          {/* Trade Timing */}
          {summary.trade_timing && (
            <SectionButton onClick={() => handleSectionClick?.('trade_timing')}>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-base">&#9201;</span>
                <span className="text-xs font-bold uppercase tracking-wider text-red-400">
                  Trade Timing
                </span>
              </div>
              <ul className="ml-6 space-y-1">
                <li className="text-sm text-zinc-300">
                  {summary.trade_timing.trades_within_30_days_of_hearing} of {summary.trade_timing.total_trades_analyzed} trades within 30 days of committee activity
                </li>
                <li className="text-sm text-zinc-300">
                  Average access score: <span className="font-medium text-amber-400">{summary.trade_timing.average_information_access_score.toFixed(1)}/10</span>
                </li>
              </ul>
            </SectionButton>
          )}

          {/* Disclaimer */}
          <p className="text-[10px] text-zinc-600 italic pt-2">
            These are patterns worth investigating, not proof of wrongdoing. All data comes from public records.
          </p>
        </div>
      )}
    </div>
  );
}
