'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  TrendingUp,
  AlertTriangle,
  Users,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import clsx from 'clsx';
import {
  getRecentTrades,
  getTradeCrossReference,
} from '@/lib/api';
import type {
  TradeItem,
  CrossReferenceTradeResponse,
} from '@/lib/api';
import TradeCard from '@/components/TradeCard';
import LoadingState from '@/components/LoadingState';
import { formatDate } from '@/lib/utils';

const ALERT_COLORS: Record<string, string> = {
  high: 'bg-red-500/20 text-red-400 border-red-500/30',
  medium: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  low: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  info: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
};

function CrossReferenceAlert({ alert }: { alert: CrossReferenceTradeResponse }) {
  const [expanded, setExpanded] = useState(false);
  const alertColor = ALERT_COLORS[alert.alert_level?.toLowerCase()] || ALERT_COLORS.info;

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-lg font-bold text-money-gold">
              {alert.ticker}
            </span>
            <span
              className={clsx(
                'inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                alertColor
              )}
            >
              {alert.alert_level}
            </span>
          </div>
          <div className="mt-1 flex items-center gap-3 text-sm text-zinc-400">
            <span className="flex items-center gap-1">
              <Users className="h-3.5 w-3.5" />
              {alert.officials_count} official{alert.officials_count !== 1 ? 's' : ''}
            </span>
            <span className="text-zinc-600">{alert.date_range}</span>
          </div>
        </div>

        <button
          onClick={() => setExpanded(!expanded)}
          className="shrink-0 rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
          aria-expanded={expanded}
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          {expanded ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </button>
      </div>

      {expanded && alert.officials.length > 0 && (
        <div className="mt-4 space-y-2 border-t border-zinc-800 pt-3">
          {alert.officials.map((official, i) => (
            <div key={i} className="flex items-center justify-between rounded-md bg-zinc-950/50 px-3 py-2">
              <Link
                href={`/officials/${official.slug}`}
                className="text-sm font-medium text-zinc-300 hover:text-money-gold transition-colors"
              >
                {official.name}
              </Link>
              <div className="flex items-center gap-3 text-xs text-zinc-500">
                <span className={clsx(
                  official.transaction_type.toLowerCase() === 'purchase' ? 'text-emerald-400' :
                  official.transaction_type.toLowerCase() === 'sale' ? 'text-red-400' : 'text-blue-400'
                )}>
                  {official.transaction_type}
                </span>
                <span>{official.amount_label}</span>
                <span>{formatDate(official.filed_date)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function TradesPage() {
  const [trades, setTrades] = useState<TradeItem[]>([]);
  const [totalTrades, setTotalTrades] = useState(0);
  const [crossRefs, setCrossRefs] = useState<CrossReferenceTradeResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    async function fetchData() {
      try {
        const [tradesData, crossRefData] = await Promise.all([
          getRecentTrades(50).catch(() => ({ trades: [], total: 0 })),
          getTradeCrossReference(20).catch(() => []),
        ]);
        setTrades(tradesData.trades);
        setTotalTrades(tradesData.total);
        setCrossRefs(crossRefData);
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <LoadingState variant="table-row" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950">
      {/* Hero */}
      <section className="border-b border-zinc-800">
        <div className="mx-auto max-w-7xl px-4 py-12 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3 mb-3">
            <TrendingUp className="h-6 w-6 text-money-gold" />
            <h1 className="font-mono text-3xl font-bold tracking-tight text-zinc-100">
              Recent Trade Activity
            </h1>
          </div>
          <p className="max-w-2xl text-sm text-zinc-400">
            Congressional financial disclosures and stock transactions.
            Members of Congress are required to report stock trades within 45 days.
            Cross-reference alerts flag when multiple officials trade the same stock
            within a 7-day window.
          </p>
        </div>
      </section>

      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-12">
        {/* Cross-Reference Alerts */}
        {crossRefs.length > 0 && (
          <section>
            <div className="mb-4 flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-money-gold" />
              <h2 className="font-mono text-lg font-bold uppercase tracking-wider text-money-gold">
                Cross-Reference Alerts
              </h2>
            </div>
            <p className="mb-4 text-xs text-zinc-500">
              Tickers where 2+ officials traded the same stock within the same week.
            </p>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {crossRefs.map((alert, i) => (
                <CrossReferenceAlert key={i} alert={alert} />
              ))}
            </div>
          </section>
        )}

        {/* New Movements */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-money-gold" />
              <h2 className="font-mono text-lg font-bold uppercase tracking-wider text-money-gold">
                New Movements
              </h2>
            </div>
            {totalTrades > 0 && (
              <span className="text-xs text-zinc-500">
                {totalTrades} total trade{totalTrades !== 1 ? 's' : ''}
              </span>
            )}
          </div>

          {trades.length === 0 ? (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-6 py-12 text-center">
              <TrendingUp className="mx-auto h-8 w-8 text-zinc-600" />
              <p className="mt-3 text-sm text-zinc-400">
                No recent trade disclosures found. Check back soon.
              </p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {trades.map((trade, i) => (
                <TradeCard key={i} trade={trade} />
              ))}
            </div>
          )}
        </section>
      </div>

      {/* Error banner */}
      {error && (
        <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 rounded-lg border border-red-500/30 bg-red-950/90 px-6 py-3 text-sm text-red-300 shadow-xl">
          Some trade data failed to load.
        </div>
      )}
    </div>
  );
}
