'use client';

import Link from 'next/link';
import {
  TrendingUp,
  Megaphone,
  Vote,
  FileText,
  DollarSign,
  ChevronDown,
  AlertTriangle,
  Shield,
} from 'lucide-react';
import clsx from 'clsx';
import type { ChainLink } from '@/lib/api';

interface EvidenceChainProps {
  chain: ChainLink[];
  severity: string;
  narrative: string;
  officialSlug: string;
  companySlug: string;
}

const TYPE_CONFIG: Record<string, { color: string; bgColor: string; icon: React.ReactNode; label: string }> = {
  stock_holding: {
    color: 'border-blue-500 text-blue-400',
    bgColor: 'bg-blue-500',
    icon: <TrendingUp className="h-4 w-4" />,
    label: 'STOCK HOLDING',
  },
  lobbying: {
    color: 'border-orange-500 text-orange-400',
    bgColor: 'bg-orange-500',
    icon: <Megaphone className="h-4 w-4" />,
    label: 'LOBBYING',
  },
  vote: {
    color: 'border-red-500 text-red-400',
    bgColor: 'bg-red-500',
    icon: <Vote className="h-4 w-4" />,
    label: 'VOTE',
  },
  bill_outcome: {
    color: 'border-money-gold text-money-gold',
    bgColor: 'bg-money-gold',
    icon: <FileText className="h-4 w-4" />,
    label: 'BILL OUTCOME',
  },
  financial_impact: {
    color: 'border-yellow-500 text-yellow-400',
    bgColor: 'bg-yellow-500',
    icon: <DollarSign className="h-4 w-4" />,
    label: 'FINANCIAL IMPACT',
  },
  donation: {
    color: 'border-emerald-500 text-emerald-400',
    bgColor: 'bg-emerald-500',
    icon: <DollarSign className="h-4 w-4" />,
    label: 'DONATION',
  },
  committee: {
    color: 'border-purple-500 text-purple-400',
    bgColor: 'bg-purple-500',
    icon: <Shield className="h-4 w-4" />,
    label: 'COMMITTEE',
  },
};

const SEVERITY_CONFIG: Record<string, { badge: string; label: string }> = {
  high_concern: {
    badge: 'bg-red-500/20 text-red-400 border-red-500/30',
    label: 'HIGH CONCERN',
  },
  notable_pattern: {
    badge: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    label: 'NOTABLE PATTERN',
  },
  structural_relationship: {
    badge: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    label: 'STRUCTURAL RELATIONSHIP',
  },
  connection_noted: {
    badge: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    label: 'CONNECTION NOTED',
  },
  critical: {
    badge: 'bg-red-500/20 text-red-400 border-red-500/30',
    label: 'HIGH CONCERN',
  },
  high: {
    badge: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    label: 'NOTABLE PATTERN',
  },
  medium: {
    badge: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    label: 'STRUCTURAL RELATIONSHIP',
  },
  low: {
    badge: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    label: 'CONNECTION NOTED',
  },
};

function getTypeConfig(type: string) {
  const key = type.toLowerCase().replace(/\s+/g, '_');
  return TYPE_CONFIG[key] || {
    color: 'border-zinc-500 text-zinc-400',
    bgColor: 'bg-zinc-500',
    icon: <Shield className="h-4 w-4" />,
    label: type.toUpperCase().replace(/_/g, ' '),
  };
}

export default function EvidenceChain({
  chain,
  severity,
  narrative,
  officialSlug,
  companySlug,
}: EvidenceChainProps) {
  const severityConfig = SEVERITY_CONFIG[severity.toLowerCase()] || SEVERITY_CONFIG.connection_noted;
  const sortedChain = [...chain].sort((a, b) => a.step - b.step);

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-5">
      {/* Chain header */}
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Link
            href={`/officials/${officialSlug}`}
            className="text-sm font-medium text-zinc-300 hover:text-money-gold transition-colors"
          >
            {officialSlug.replace(/-/g, ' ')}
          </Link>
          <span className="text-zinc-600">&rarr;</span>
          <Link
            href={`/entities/company/${companySlug}`}
            className="text-sm font-medium text-zinc-300 hover:text-money-gold transition-colors"
          >
            {companySlug.replace(/-/g, ' ')}
          </Link>
        </div>
        <span className="text-xs text-zinc-500">{sortedChain.length} steps</span>
      </div>

      {/* Chain steps */}
      <div className="relative ml-4">
        {sortedChain.map((link, index) => {
          const config = getTypeConfig(link.type);
          const isLast = index === sortedChain.length - 1;

          return (
            <div key={link.step} className="relative">
              {/* Connecting line */}
              {!isLast && (
                <div className="absolute left-4 top-10 h-[calc(100%-8px)] w-px bg-zinc-700" />
              )}

              {/* Step card */}
              <div
                className={clsx(
                  'relative rounded-lg border border-zinc-800 bg-zinc-950/50 p-4 border-l-4',
                  config.color.split(' ')[0]
                )}
              >
                <div className="flex items-start gap-3">
                  {/* Step number circle */}
                  <div
                    className={clsx(
                      'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold text-zinc-950',
                      config.bgColor
                    )}
                  >
                    {link.step}
                  </div>

                  <div className="min-w-0 flex-1">
                    {/* Type label */}
                    <div className="mb-1 flex items-center gap-2">
                      <span className={clsx('flex items-center gap-1', config.color.split(' ')[1])}>
                        {config.icon}
                      </span>
                      <span className={clsx('text-[10px] font-bold uppercase tracking-widest', config.color.split(' ')[1])}>
                        {config.label}
                      </span>
                    </div>

                    {/* Description */}
                    <p className="text-sm text-zinc-300">{link.description}</p>

                    {/* Entity */}
                    {link.entity && (
                      <p className="mt-1 text-xs text-zinc-400">
                        Entity: <span className="font-medium text-zinc-300">{link.entity}</span>
                      </p>
                    )}

                    {/* Amount + Date row */}
                    <div className="mt-1 flex flex-wrap items-center gap-3">
                      {link.amount && (
                        <span className="text-xs font-medium text-money-gold">{link.amount}</span>
                      )}
                      {link.date && (
                        <span className="text-xs text-zinc-500">{link.date}</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Arrow between steps */}
              {!isLast && (
                <div className="flex justify-center py-1">
                  <ChevronDown className="h-4 w-4 text-zinc-600" />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Narrative */}
      {narrative && (
        <div className="mt-5 border-t border-zinc-800 pt-4">
          <p className="text-sm italic leading-relaxed text-zinc-300">{narrative}</p>
        </div>
      )}

      {/* Severity badge */}
      <div className="mt-4 flex items-center gap-2">
        <AlertTriangle className="h-3.5 w-3.5 text-zinc-500" />
        <span
          className={clsx(
            'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide',
            severityConfig.badge
          )}
        >
          {severityConfig.label}
        </span>
      </div>
    </div>
  );
}
