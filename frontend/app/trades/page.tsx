'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  TrendingUp,
  AlertTriangle,
  Users,
  ChevronDown,
  ChevronUp,
  LayoutList,
  BarChart3,
  ArrowUpRight,
  ArrowDownRight,
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

interface PersonSummary {
  name: string;
  slug: string;
  tradeCount: number;
  amounts: string[];
  latestDate: string;
}

interface StockGroup {
  ticker: string;
  trades: TradeItem[];
  buyers: PersonSummary[];
  sellers: PersonSummary[];
  totalTrades: number;
}

function consolidateByPerson(trades: TradeItem[]): PersonSummary[] {
  const byPerson: Record<string, PersonSummary> = {};
  for (const t of trades) {
    const key = t.official_slug;
    if (!byPerson[key]) {
      byPerson[key] = { name: t.official_name, slug: t.official_slug, tradeCount: 0, amounts: [], latestDate: t.filed_date };
    }
    byPerson[key].tradeCount++;
    byPerson[key].amounts.push(t.amount_label);
    if (t.filed_date > byPerson[key].latestDate) byPerson[key].latestDate = t.filed_date;
  }
  return Object.values(byPerson).sort((a, b) => b.tradeCount - a.tradeCount);
}

function groupTradesByStock(trades: TradeItem[]): StockGroup[] {
  const grouped: Record<string, TradeItem[]> = {};
  for (const t of trades) {
    if (!t.ticker) continue;
    (grouped[t.ticker] ??= []).push(t);
  }
  return Object.entries(grouped)
    .map(([ticker, items]) => ({
      ticker,
      trades: items,
      buyers: consolidateByPerson(items.filter(t => t.transaction_type.toLowerCase() === 'purchase')),
      sellers: consolidateByPerson(items.filter(t => t.transaction_type.toLowerCase() === 'sale')),
      totalTrades: items.length,
    }))
    .sort((a, b) => b.totalTrades - a.totalTrades);
}

function StockGroupCard({ group }: { group: StockGroup }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <span className="font-mono text-xl font-bold text-money-gold">{group.ticker}</span>
            <span className="text-xs text-zinc-500">{group.totalTrades} trade{group.totalTrades !== 1 ? 's' : ''}</span>
          </div>
          <div className="mt-2 flex items-center gap-4 text-sm">
            {group.buyers.length > 0 && (
              <span className="flex items-center gap-1 text-emerald-400">
                <ArrowUpRight className="h-3.5 w-3.5" />
                {group.buyers.length} {group.buyers.length === 1 ? 'buyer' : 'buyers'}
              </span>
            )}
            {group.sellers.length > 0 && (
              <span className="flex items-center gap-1 text-red-400">
                <ArrowDownRight className="h-3.5 w-3.5" />
                {group.sellers.length} {group.sellers.length === 1 ? 'seller' : 'sellers'}
              </span>
            )}
          </div>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="shrink-0 rounded-md p-1 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200 transition-colors"
        >
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>
      </div>

      {expanded && (
        <div className="mt-4 space-y-3 border-t border-zinc-800 pt-3">
          {group.buyers.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-emerald-400 mb-2 flex items-center gap-1">
                <ArrowUpRight className="h-3 w-3" /> Buying
              </h4>
              <div className="space-y-1.5">
                {group.buyers.map((b) => (
                  <div key={b.slug} className="flex items-center justify-between rounded-md bg-zinc-950/50 px-3 py-2">
                    <div className="min-w-0">
                      <Link href={`/officials/${b.slug}`} className="text-sm font-medium text-zinc-300 hover:text-money-gold transition-colors">
                        {b.name}
                      </Link>
                      {b.tradeCount > 1 && (
                        <span className="ml-2 text-[10px] text-zinc-500">{b.tradeCount} trades</span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-zinc-500 shrink-0">
                      <span className="text-emerald-400">{b.amounts.length === 1 ? b.amounts[0] : b.amounts.join(', ')}</span>
                      <span>{formatDate(b.latestDate)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {group.sellers.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-red-400 mb-2 flex items-center gap-1">
                <ArrowDownRight className="h-3 w-3" /> Selling
              </h4>
              <div className="space-y-1.5">
                {group.sellers.map((s) => (
                  <div key={s.slug} className="flex items-center justify-between rounded-md bg-zinc-950/50 px-3 py-2">
                    <div className="min-w-0">
                      <Link href={`/officials/${s.slug}`} className="text-sm font-medium text-zinc-300 hover:text-money-gold transition-colors">
                        {s.name}
                      </Link>
                      {s.tradeCount > 1 && (
                        <span className="ml-2 text-[10px] text-zinc-500">{s.tradeCount} trades</span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-zinc-500 shrink-0">
                      <span className="text-red-400">{s.amounts.length === 1 ? s.amounts[0] : s.amounts.join(', ')}</span>
                      <span>{formatDate(s.latestDate)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
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
  const [viewMode, setViewMode] = useState<'timeline' | 'grouped'>('timeline');

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
                {viewMode === 'grouped' ? 'By Stock' : 'New Movements'}
              </h2>
            </div>
            <div className="flex items-center gap-3">
              {totalTrades > 0 && (
                <span className="text-xs text-zinc-500">
                  {totalTrades} total trade{totalTrades !== 1 ? 's' : ''}
                </span>
              )}
              <div className="flex rounded-lg border border-zinc-700 bg-zinc-800/50 p-0.5">
                <button
                  onClick={() => setViewMode('timeline')}
                  className={clsx(
                    'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                    viewMode === 'timeline'
                      ? 'bg-zinc-700 text-zinc-100'
                      : 'text-zinc-400 hover:text-zinc-200'
                  )}
                >
                  <LayoutList className="h-3.5 w-3.5" />
                  Timeline
                </button>
                <button
                  onClick={() => setViewMode('grouped')}
                  className={clsx(
                    'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                    viewMode === 'grouped'
                      ? 'bg-zinc-700 text-zinc-100'
                      : 'text-zinc-400 hover:text-zinc-200'
                  )}
                >
                  <BarChart3 className="h-3.5 w-3.5" />
                  By Stock
                </button>
              </div>
            </div>
          </div>

          {trades.length === 0 ? (
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 px-6 py-12 text-center">
              <TrendingUp className="mx-auto h-8 w-8 text-zinc-600" />
              <p className="mt-3 text-sm text-zinc-400">
                No recent trade disclosures found. Check back soon.
              </p>
            </div>
          ) : viewMode === 'timeline' ? (
            <div className="grid gap-4 sm:grid-cols-2">
              {trades.map((trade, i) => (
                <TradeCard key={i} trade={trade} />
              ))}
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {groupTradesByStock(trades).map((group) => (
                <StockGroupCard key={group.ticker} group={group} />
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
