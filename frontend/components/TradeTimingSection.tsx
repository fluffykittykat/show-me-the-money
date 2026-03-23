'use client';

import { useState } from 'react';
import {
  ChevronDown,
  ChevronUp,
  TrendingUp,
  TrendingDown,
  Clock,
  AlertTriangle,
  BarChart3,
  Activity,
  Loader2,
} from 'lucide-react';
import clsx from 'clsx';
import type { TradeTimingItem, TradeTimingSummary, InsiderTimingResponse } from '@/lib/types';
import { formatDate } from '@/lib/utils';
import DidYouKnow from '@/components/DidYouKnow';

interface TradeTimingSectionProps {
  data?: InsiderTimingResponse | null;
  trades?: TradeTimingItem[];
  summary?: TradeTimingSummary | null;
  loading?: boolean;
  entityName?: string;
}

function getScoreColor(score: number): string {
  if (score >= 8) return 'text-red-400';
  if (score >= 6) return 'text-orange-400';
  if (score >= 4) return 'text-amber-400';
  return 'text-zinc-400';
}

function getScoreBg(score: number): string {
  if (score >= 8) return 'bg-red-500';
  if (score >= 6) return 'bg-orange-500';
  if (score >= 4) return 'bg-amber-500';
  return 'bg-zinc-500';
}

function ScoreMeter({ score, size = 'sm' }: { score: number; size?: 'sm' | 'lg' }) {
  const dots = 10;
  const isLarge = size === 'lg';

  return (
    <div className="flex items-center gap-1">
      {Array.from({ length: dots }).map((_, i) => (
        <div
          key={i}
          className={clsx(
            'rounded-full',
            isLarge ? 'h-3 w-3' : 'h-2 w-2',
            i < Math.round(score) ? getScoreBg(score) : 'bg-zinc-700'
          )}
        />
      ))}
      <span className={clsx('ml-1 font-bold', isLarge ? 'text-sm' : 'text-xs', getScoreColor(score))}>
        {score.toFixed(1)}/10
      </span>
    </div>
  );
}

function TradeCard({ trade }: { trade: TradeTimingItem }) {
  const [expanded, setExpanded] = useState(false);
  const isBuy = trade.transaction_type.toLowerCase().includes('buy') || trade.transaction_type.toLowerCase().includes('purchase');
  const isSell = trade.transaction_type.toLowerCase().includes('sell') || trade.transaction_type.toLowerCase().includes('sale');

  const movement = trade.stock_movement_after;
  const movementPositive = movement && (movement.startsWith('+') || parseFloat(movement) > 0);
  const movementNegative = movement && (movement.startsWith('-') || parseFloat(movement) < 0);

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 sm:p-5 transition-colors hover:border-zinc-700">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 mb-2">
        {isBuy ? (
          <TrendingUp className="h-4 w-4 text-green-400" />
        ) : isSell ? (
          <TrendingDown className="h-4 w-4 text-red-400" />
        ) : (
          <Activity className="h-4 w-4 text-zinc-400" />
        )}
        <span className="text-sm font-semibold text-zinc-200">
          {trade.stock_name}
        </span>
        <span
          className={clsx(
            'rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider',
            isBuy
              ? 'bg-green-500/20 text-green-400'
              : isSell
                ? 'bg-red-500/20 text-red-400'
                : 'bg-zinc-700 text-zinc-300'
          )}
        >
          {trade.transaction_type}
        </span>
        {trade.pattern_flag && (
          <span className="inline-flex items-center gap-1 rounded-full bg-orange-500/20 px-2 py-0.5 text-[10px] font-bold uppercase text-orange-400">
            <AlertTriangle className="h-2.5 w-2.5" />
            {trade.pattern_flag}
          </span>
        )}
      </div>

      {/* Amount range + date */}
      <div className="flex flex-wrap items-center gap-3 mb-3 text-sm">
        <span className="font-medium text-amber-400">{trade.amount_range}</span>
        <span className="text-xs text-zinc-500">{formatDate(trade.transaction_date)}</span>
      </div>

      {/* Timeline visualization */}
      {(trade.days_before_committee_hearing != null || trade.days_before_related_vote != null) && (
        <div className="mb-3 rounded-lg border border-zinc-700/50 bg-zinc-950/50 p-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <div className="rounded bg-zinc-700 px-2 py-1 text-zinc-300">
              <Clock className="inline h-3 w-3 mr-1" />
              Trade: {formatDate(trade.transaction_date)}
            </div>

            {trade.days_before_committee_hearing != null && (
              <>
                <div className="flex items-center gap-1 text-amber-400">
                  <span className="border-t border-dashed border-amber-500/50 w-8" />
                  <span className="font-medium">{trade.days_before_committee_hearing} days</span>
                  <span className="border-t border-dashed border-amber-500/50 w-8" />
                </div>
                <div className="rounded bg-amber-500/20 px-2 py-1 text-amber-400">
                  Hearing: {trade.hearing_topic || formatDate(trade.hearing_date)}
                </div>
              </>
            )}

            {trade.days_before_related_vote != null && (
              <>
                <div className="flex items-center gap-1 text-blue-400">
                  <span className="border-t border-dashed border-blue-500/50 w-8" />
                  <span className="font-medium">{trade.days_before_related_vote} days</span>
                  <span className="border-t border-dashed border-blue-500/50 w-8" />
                </div>
                <div className="rounded bg-blue-500/20 px-2 py-1 text-blue-400">
                  Vote: {trade.vote_topic || 'Related vote'}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Score + stock movement */}
      <div className="flex flex-wrap items-center gap-4 mb-2">
        <div>
          <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 block mb-1">
            Information access score
          </span>
          <ScoreMeter score={trade.information_access_score} />
        </div>

        {movement && (
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 block mb-1">
              Stock moved after
            </span>
            <span
              className={clsx(
                'text-sm font-bold',
                movementPositive ? 'text-green-400' : movementNegative ? 'text-red-400' : 'text-zinc-400'
              )}
            >
              {movement}
            </span>
          </div>
        )}
      </div>

      {/* Pattern description */}
      {trade.pattern_description && (
        <p className="text-xs text-zinc-400 mb-2">{trade.pattern_description}</p>
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
            {trade.why_this_matters}
          </p>
        </div>
      )}
    </div>
  );
}

export default function TradeTimingSection({ data, trades: tradesProp, summary: summaryProp, loading, entityName }: TradeTimingSectionProps) {
  // Support both the new `data` prop and legacy `trades`/`summary` props
  const trades = data?.trades ?? tradesProp ?? [];
  const summary = data?.summary ?? summaryProp ?? null;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
        <span className="ml-2 text-sm text-zinc-500">Loading trade timing data...</span>
      </div>
    );
  }

  if (trades.length === 0 && !summary) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 px-6 py-8 text-center">
        <BarChart3 className="mx-auto h-8 w-8 text-zinc-600" />
        <p className="mt-3 text-sm text-zinc-500">
          No trade timing data available{entityName ? ` for ${entityName}` : ''}.
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Section header */}
      <div className="mb-4">
        <h3 className="flex items-center gap-2 text-base font-bold text-zinc-100">
          <span className="text-lg">&#9201;</span>
          Trade Timing Analysis
        </h3>
        <p className="mt-1 text-sm text-zinc-400">
          When they traded stock vs. when they had inside information
        </p>
      </div>

      {/* Pattern summary at top */}
      {summary && (
        <div className="mb-4 rounded-xl border border-zinc-800 bg-zinc-900 p-4">
          {/* Key stat callout */}
          <div className="mb-3 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2.5">
            <p className="text-sm font-semibold text-amber-400">
              {summary.trades_within_30_days_of_hearing} of {summary.total_trades_analyzed} trades
              occurred within 30 days of related committee activity
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-6 mb-3">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                Before favorable outcome
              </span>
              <p className="text-xl font-bold text-green-400">
                {summary.trades_before_favorable_outcome}
              </p>
            </div>
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                Before unfavorable outcome
              </span>
              <p className="text-xl font-bold text-red-400">
                {summary.trades_before_unfavorable_outcome}
              </p>
            </div>
          </div>

          <div className="mb-3">
            <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 block mb-1">
              Average information access score
            </span>
            <ScoreMeter score={summary.average_information_access_score} size="lg" />
          </div>

          {summary.overall_pattern && (
            <div className="rounded-md border border-zinc-700/50 bg-zinc-800/30 px-3 py-2.5">
              <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-1">
                Overall Pattern
              </p>
              <p className="text-sm text-zinc-300">{summary.overall_pattern}</p>
            </div>
          )}
        </div>
      )}

      {/* Trade cards */}
      <div className="space-y-3">
        {trades.map((trade, i) => (
          <TradeCard key={`${trade.stock_name}-${trade.transaction_date}-${i}`} trade={trade} />
        ))}
      </div>

      {/* Summary why this matters at bottom */}
      {summary?.why_this_matters && (
        <div className="mt-4 rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
          <p className="text-xs font-semibold uppercase tracking-wider text-amber-400 mb-1">
            Bottom Line
          </p>
          <p className="text-sm text-zinc-300">{summary.why_this_matters}</p>
        </div>
      )}

      <DidYouKnow fact="Members of Congress can legally trade individual stocks. Some trades happen suspiciously close to private committee briefings." />

      {/* Disclaimer */}
      <p className="mt-3 text-[10px] text-zinc-600 italic">
        Members of Congress are allowed to trade stocks, though rules require timely disclosure. Suspicious timing is not proof of insider trading.
      </p>
    </div>
  );
}
