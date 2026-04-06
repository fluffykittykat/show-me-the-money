'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { Activity, TrendingUp, AlertTriangle, DollarSign, RefreshCw, Server, Filter } from 'lucide-react';
import clsx from 'clsx';
import { getActivityFeed, type ActivityEventItem } from '@/lib/api';

type ActivityEvent = ActivityEventItem;

const EVENT_ICONS: Record<string, typeof TrendingUp> = {
  new_trade: TrendingUp,
  verdict_change: AlertTriangle,
  new_conflict: AlertTriangle,
  new_donation: DollarSign,
  data_refresh: RefreshCw,
  system: Server,
};

const EVENT_COLORS: Record<string, string> = {
  new_trade: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
  verdict_change: 'text-red-400 bg-red-500/10 border-red-500/30',
  new_conflict: 'text-orange-400 bg-orange-500/10 border-orange-500/30',
  new_donation: 'text-money-gold bg-amber-500/10 border-amber-500/30',
  data_refresh: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
  system: 'text-zinc-400 bg-zinc-500/10 border-zinc-500/30',
};

const EVENT_LABELS: Record<string, string> = {
  new_trade: 'New Trade',
  verdict_change: 'Verdict Change',
  new_conflict: 'Conflict',
  new_donation: 'Donation',
  data_refresh: 'Data Refresh',
  system: 'System',
};

type FilterType = 'all' | string;

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export default function ActivityPage() {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterType>('all');

  const fetchEvents = useCallback(async () => {
    try {
      const data = await getActivityFeed({
        limit: 100,
        days: 30,
        event_type: filter !== 'all' ? filter : undefined,
      });
      setEvents(data.events);
      setTotal(data.total);
    } catch {
      // silently handle
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    fetchEvents();
    const interval = setInterval(fetchEvents, 30000);
    return () => clearInterval(interval);
  }, [fetchEvents]);

  const filters = [
    { label: 'All', value: 'all' },
    { label: 'Trades', value: 'new_trade' },
    { label: 'Verdicts', value: 'verdict_change' },
    { label: 'Conflicts', value: 'new_conflict' },
    { label: 'System', value: 'system' },
  ];

  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <Activity className="h-6 w-6 text-money-gold" />
          <h1 className="font-mono text-2xl font-bold text-zinc-100">
            Activity Feed
          </h1>
        </div>
        <p className="mt-1 text-sm text-zinc-400">
          What&apos;s happening — new trades, verdict changes, conflicts, and data updates.
          {total > 0 && ` ${total} events in the last 30 days.`}
        </p>
      </div>

      {/* Filters */}
      <div className="mb-6 flex items-center gap-2">
        <Filter className="h-4 w-4 text-zinc-500" />
        {filters.map((f) => (
          <button
            key={f.value}
            onClick={() => { setFilter(f.value); setLoading(true); }}
            className={clsx(
              'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
              filter === f.value
                ? 'border-money-gold/50 bg-money-gold/10 text-money-gold'
                : 'border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-600'
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg bg-zinc-800/50" />
          ))}
        </div>
      ) : events.length === 0 ? (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-12 text-center">
          <Activity className="mx-auto mb-3 h-10 w-10 text-zinc-600" />
          <p className="text-sm text-zinc-400">
            No activity events yet. Events will appear here as the system detects
            new trades, verdict changes, and data updates.
          </p>
          <p className="mt-2 text-xs text-zinc-500">
            The system polls for new data every 15 minutes.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {events.map((event) => {
            const Icon = EVENT_ICONS[event.event_type] || Activity;
            const colors = EVENT_COLORS[event.event_type] || EVENT_COLORS.system;
            const label = EVENT_LABELS[event.event_type] || event.event_type;

            return (
              <div
                key={event.id}
                className="flex items-start gap-4 rounded-lg border border-zinc-800 bg-zinc-900 p-4"
              >
                <div className={clsx('mt-0.5 rounded-lg border p-2', colors)}>
                  <Icon className="h-4 w-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                      {label}
                    </span>
                    {event.created_at && (
                      <span className="text-[10px] text-zinc-600">
                        {timeAgo(event.created_at)}
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 text-sm font-medium text-zinc-200">
                    {event.headline}
                  </p>
                  {event.detail && (
                    <p className="mt-1 text-xs text-zinc-400 line-clamp-2">
                      {event.detail}
                    </p>
                  )}
                  {event.entity_slug && (
                    <Link
                      href={`/officials/${event.entity_slug}`}
                      className="mt-1 inline-block text-xs text-money-gold hover:underline"
                    >
                      {event.entity_name || event.entity_slug}
                    </Link>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </main>
  );
}
