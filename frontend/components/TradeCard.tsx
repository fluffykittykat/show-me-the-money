'use client';

import Link from 'next/link';
import { AlertTriangle, ArrowUpRight, ArrowDownRight, RefreshCw, Info } from 'lucide-react';
import clsx from 'clsx';
import type { TradeItem } from '@/lib/api';
import { formatDate } from '@/lib/utils';

const TX_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  purchase: {
    label: 'PURCHASE',
    color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    icon: <ArrowUpRight className="h-3 w-3" />,
  },
  sale: {
    label: 'SALE',
    color: 'bg-red-500/20 text-red-400 border-red-500/30',
    icon: <ArrowDownRight className="h-3 w-3" />,
  },
  exchange: {
    label: 'EXCHANGE',
    color: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    icon: <RefreshCw className="h-3 w-3" />,
  },
};

interface TradeCardProps {
  trade: TradeItem;
}

export default function TradeCard({ trade }: TradeCardProps) {
  const txType = trade.transaction_type.toLowerCase();
  const config = TX_CONFIG[txType] || TX_CONFIG.exchange;

  return (
    <div
      className={clsx(
        'rounded-lg border border-zinc-800 bg-zinc-900 p-4 transition-colors hover:border-zinc-700',
        trade.is_flagged && 'border-l-4 border-l-money-gold'
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href={`/officials/${trade.official_slug}`}
              className="text-sm font-semibold text-zinc-200 hover:text-money-gold transition-colors"
            >
              {trade.official_name}
            </Link>
            <span
              className={clsx(
                'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                config.color
              )}
            >
              {config.icon}
              {config.label}
            </span>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-3">
            <span className="font-mono text-lg font-bold text-money-gold">
              {trade.ticker}
            </span>
            <span className="text-sm text-zinc-400">{trade.amount_label}</span>
          </div>
        </div>

        <div className="shrink-0 text-right">
          <p className="text-xs text-zinc-500">Filed</p>
          <p className="text-sm text-zinc-300">{formatDate(trade.filed_date)}</p>
          <p className="mt-1 text-xs text-zinc-500">
            {trade.days_to_file} day{trade.days_to_file !== 1 ? 's' : ''} to file
          </p>
        </div>
      </div>

      {trade.is_flagged && (
        <div className="mt-3 flex items-center gap-2 rounded-md bg-money-gold/10 px-3 py-1.5">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-money-gold" />
          <span className="text-xs font-medium text-money-gold">
            Cross-reference detected
          </span>
        </div>
      )}

      {trade.committee_relevance && (
        <div className="mt-2 flex items-start gap-2">
          <Info className="mt-0.5 h-3 w-3 shrink-0 text-zinc-500" />
          <span className="text-xs text-zinc-400">{trade.committee_relevance}</span>
        </div>
      )}
    </div>
  );
}
