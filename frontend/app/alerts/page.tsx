'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { Bell, ChevronDown, ChevronUp, Eye, Filter } from 'lucide-react';
import clsx from 'clsx';
import {
  getAlertsFeed,
  markAlertSeen,
  markAllAlertsSeen,
  type AlertItem,
} from '@/lib/api';

const LEVEL_COLORS: Record<string, string> = {
  HIGH_CONCERN: 'border-red-500/30 bg-red-950/40 text-red-400',
  NOTABLE_PATTERN: 'border-orange-500/30 bg-orange-950/40 text-orange-400',
  ROUTINE: 'border-zinc-700 bg-zinc-900 text-zinc-400',
};

const LEVEL_BADGE: Record<string, string> = {
  HIGH_CONCERN: 'bg-red-500/20 text-red-400 border-red-500/30',
  NOTABLE_PATTERN: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  ROUTINE: 'bg-zinc-700/40 text-zinc-400 border-zinc-600/30',
};

type FilterLevel = 'all' | 'HIGH_CONCERN' | 'NOTABLE_PATTERN' | 'ROUTINE';

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [total, setTotal] = useState(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filterLevel, setFilterLevel] = useState<FilterLevel>('all');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchAlerts = useCallback(async () => {
    try {
      const params: Record<string, string> = { limit: '100' };
      if (filterLevel !== 'all') params.alert_level = filterLevel;
      const data = await getAlertsFeed(params);
      setAlerts(data.alerts);
      setTotal(data.total);
      setUnreadCount(data.unread_count);
    } catch {
      // silently handle — alerts may not exist yet
    } finally {
      setLoading(false);
    }
  }, [filterLevel]);

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 30000);
    return () => clearInterval(interval);
  }, [fetchAlerts]);

  async function handleMarkSeen(id: string) {
    await markAlertSeen(id);
    setAlerts((prev) =>
      prev.map((a) => (a.id === id ? { ...a, status: 'seen' } : a))
    );
    setUnreadCount((c) => Math.max(0, c - 1));
  }

  async function handleMarkAllSeen() {
    await markAllAlertsSeen();
    setAlerts((prev) => prev.map((a) => ({ ...a, status: 'seen' })));
    setUnreadCount(0);
  }

  const filters: { label: string; value: FilterLevel }[] = [
    { label: 'All', value: 'all' },
    { label: 'High Concern', value: 'HIGH_CONCERN' },
    { label: 'Notable', value: 'NOTABLE_PATTERN' },
    { label: 'Routine', value: 'ROUTINE' },
  ];

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <Bell className="h-6 w-6 text-money-gold" />
            <h1 className="font-mono text-2xl font-bold text-zinc-100">
              Trade Alerts
            </h1>
            {unreadCount > 0 && (
              <span className="rounded-full bg-red-500 px-2 py-0.5 text-xs font-bold text-white">
                {unreadCount}
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-zinc-400">
            Real-time notifications when politicians file new stock trades.
            {total > 0 && ` ${total} total alerts.`}
          </p>
        </div>
        {unreadCount > 0 && (
          <button
            onClick={handleMarkAllSeen}
            className="flex items-center gap-1 rounded-md border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-700"
          >
            <Eye className="h-3 w-3" />
            Mark all read
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="mb-6 flex items-center gap-2">
        <Filter className="h-4 w-4 text-zinc-500" />
        {filters.map((f) => (
          <button
            key={f.value}
            onClick={() => { setFilterLevel(f.value); setLoading(true); }}
            className={clsx(
              'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
              filterLevel === f.value
                ? 'border-money-gold/50 bg-money-gold/10 text-money-gold'
                : 'border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-600'
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Alert List */}
      {loading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-zinc-800/50" />
          ))}
        </div>
      ) : alerts.length === 0 ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-12 text-center">
          <Bell className="mx-auto mb-3 h-10 w-10 text-zinc-600" />
          <p className="text-sm text-zinc-400">
            No trade alerts yet. Alerts will appear here when politicians file new stock trades.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className={clsx(
                'rounded-lg border p-4 transition-colors',
                alert.status === 'new'
                  ? LEVEL_COLORS[alert.alert_level] || LEVEL_COLORS.ROUTINE
                  : 'border-zinc-800 bg-zinc-900/60 opacity-75'
              )}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      href={`/official/${alert.official_slug}`}
                      className="font-mono text-sm font-semibold text-zinc-100 hover:text-money-gold"
                    >
                      {alert.official_name}
                    </Link>
                    <span
                      className={clsx(
                        'rounded border px-1.5 py-0.5 text-[10px] font-bold uppercase',
                        LEVEL_BADGE[alert.alert_level] || LEVEL_BADGE.ROUTINE
                      )}
                    >
                      {alert.alert_level.replace('_', ' ')}
                    </span>
                    {alert.status === 'new' && (
                      <span className="h-2 w-2 rounded-full bg-red-500" />
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-3 text-sm">
                    <span className="font-mono font-bold text-money-gold">
                      {alert.ticker}
                    </span>
                    <span
                      className={clsx(
                        'text-xs font-medium',
                        alert.transaction_type?.toLowerCase().includes('purchase')
                          ? 'text-emerald-400'
                          : alert.transaction_type?.toLowerCase().includes('sale')
                            ? 'text-red-400'
                            : 'text-blue-400'
                      )}
                    >
                      {alert.transaction_type}
                    </span>
                    {alert.amount_label && (
                      <span className="text-xs text-zinc-400">
                        {alert.amount_label}
                      </span>
                    )}
                  </div>
                  <div className="mt-1 text-xs text-zinc-500">
                    {alert.trade_date && `Traded: ${alert.trade_date}`}
                    {alert.filed_date && ` | Filed: ${alert.filed_date}`}
                    {alert.source && ` | ${alert.source}`}
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {alert.status === 'new' && (
                    <button
                      onClick={() => handleMarkSeen(alert.id)}
                      className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
                      title="Mark as read"
                    >
                      <Eye className="h-4 w-4" />
                    </button>
                  )}
                  <button
                    onClick={() =>
                      setExpandedId(expandedId === alert.id ? null : alert.id)
                    }
                    className="rounded p-1 text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300"
                  >
                    {expandedId === alert.id ? (
                      <ChevronUp className="h-4 w-4" />
                    ) : (
                      <ChevronDown className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>

              {expandedId === alert.id && (
                <div className="mt-3 border-t border-zinc-700/50 pt-3">
                  {alert.narrative && (
                    <p className="mb-2 text-sm text-zinc-300">{alert.narrative}</p>
                  )}
                  {alert.signals.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {alert.signals.map((sig, i) => (
                        <span
                          key={i}
                          className="rounded border border-zinc-700 bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400"
                        >
                          {String(sig)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
