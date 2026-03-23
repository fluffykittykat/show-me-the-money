'use client';

import { AlertTriangle, DollarSign, Vote } from 'lucide-react';
import { formatMoney, formatDate } from '@/lib/utils';
import type { TimelineEvent } from '@/lib/api';
import clsx from 'clsx';

interface DonationTimelineProps {
  events: TimelineEvent[];
  suspiciousPairs: number;
}

function getEventConfig(event: TimelineEvent) {
  const type = event.event_type.toLowerCase();
  if (type.includes('donat') || type.includes('contribut') || type.includes('campaign')) {
    return {
      icon: <DollarSign className="h-3.5 w-3.5" />,
      dotColor: 'bg-money-gold border-money-gold/50',
      label: 'Money received',
    };
  }
  if (type.includes('vote')) {
    const isYes = event.description.toLowerCase().includes('yes') || event.description.toLowerCase().includes('yea');
    return {
      icon: <Vote className="h-3.5 w-3.5" />,
      dotColor: isYes ? 'bg-blue-500 border-blue-500/50' : 'bg-red-500 border-red-500/50',
      label: isYes ? 'Voted Yes' : 'Voted No',
    };
  }
  return {
    icon: <DollarSign className="h-3.5 w-3.5" />,
    dotColor: 'bg-zinc-500 border-zinc-500/50',
    label: event.event_type,
  };
}

export default function DonationTimeline({
  events,
  suspiciousPairs,
}: DonationTimelineProps) {
  if (events.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-zinc-500">
        No donation-vote timeline data available.
      </p>
    );
  }

  // Sort events by date
  const sorted = [...events].sort((a, b) => {
    if (!a.date && !b.date) return 0;
    if (!a.date) return 1;
    if (!b.date) return -1;
    return new Date(a.date).getTime() - new Date(b.date).getTime();
  });

  return (
    <div>
      {/* Summary banner */}
      {suspiciousPairs > 0 && (
        <div className="mb-5 flex items-center gap-3 rounded-lg border border-orange-500/20 bg-orange-500/5 px-4 py-3">
          <AlertTriangle className="h-5 w-5 shrink-0 text-orange-400" />
          <div>
            <p className="text-sm font-semibold text-orange-300">
              {suspiciousPairs} notable donation-vote timing pattern{suspiciousPairs !== 1 ? 's' : ''} identified
            </p>
            <p className="mt-0.5 text-xs text-orange-400/70">
              Money received within 90 days before a related legislative vote
            </p>
          </div>
        </div>
      )}

      {/* Timeline */}
      <div className="relative ml-3 border-l border-zinc-700 pl-6 space-y-4">
        {sorted.map((event, i) => {
          const config = getEventConfig(event);
          const isNotable = event.days_before_vote != null && event.days_before_vote <= 90 && event.days_before_vote >= 0;

          return (
            <div key={i} className="relative">
              {/* Timeline dot */}
              <div
                className={clsx(
                  'absolute -left-[31px] top-1.5 h-3 w-3 rounded-full border-2',
                  config.dotColor
                )}
              />

              <div
                className={clsx(
                  'rounded-lg border p-3 transition-colors',
                  isNotable
                    ? 'border-orange-500/30 bg-orange-500/5'
                    : 'border-zinc-800/50 bg-money-surface'
                )}
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className={clsx(
                      'text-zinc-400',
                      isNotable && 'text-orange-400'
                    )}>
                      {config.icon}
                    </span>
                    <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                      {config.label}
                    </span>
                  </div>
                  <span className="text-xs text-zinc-500">
                    {formatDate(event.date)}
                  </span>
                </div>

                <p className="mt-1.5 text-sm text-zinc-300">
                  {event.description}
                </p>

                <div className="mt-2 flex flex-wrap items-center gap-3">
                  {event.amount_usd != null && event.amount_usd > 0 && (
                    <span className="text-sm font-semibold text-money-gold">
                      {formatMoney(event.amount_usd)}
                    </span>
                  )}

                  {isNotable && (
                    <span className="inline-flex items-center gap-1 rounded-full bg-orange-500/15 px-2 py-0.5 text-xs font-medium text-orange-400">
                      <AlertTriangle className="h-3 w-3" />
                      Notable timing pattern &mdash; {event.days_before_vote} days before vote
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
