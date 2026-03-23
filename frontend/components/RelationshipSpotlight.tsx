'use client';

import Link from 'next/link';
import type { RelationshipSpotlightData } from '@/lib/api';
import {
  AlertTriangle,
  DollarSign,
  TrendingUp,
  Building2,
  Megaphone,
  Vote,
  ExternalLink,
} from 'lucide-react';
import clsx from 'clsx';

interface RelationshipSpotlightProps {
  spotlights: RelationshipSpotlightData[];
  officialName: string;
}

const SEVERITY_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  // New severity values
  high_concern: { bg: 'bg-red-500/20', text: 'text-red-400', label: 'HIGH CONCERN' },
  notable_pattern: { bg: 'bg-orange-500/20', text: 'text-orange-400', label: 'NOTABLE PATTERN' },
  structural_relationship: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', label: 'STRUCTURAL RELATIONSHIP' },
  connection_noted: { bg: 'bg-blue-500/20', text: 'text-blue-400', label: 'CONNECTION NOTED' },
  // Backwards compat
  critical: { bg: 'bg-red-500/20', text: 'text-red-400', label: 'HIGH CONCERN' },
  high: { bg: 'bg-orange-500/20', text: 'text-orange-400', label: 'NOTABLE PATTERN' },
  medium: { bg: 'bg-yellow-500/20', text: 'text-yellow-400', label: 'STRUCTURAL RELATIONSHIP' },
  low: { bg: 'bg-blue-500/20', text: 'text-blue-400', label: 'CONNECTION NOTED' },
};

const TYPE_BADGE: Record<string, string> = {
  company: 'bg-emerald-500/20 text-emerald-400',
  organization: 'bg-orange-500/20 text-orange-400',
  pac: 'bg-pink-500/20 text-pink-400',
  industry: 'bg-cyan-500/20 text-cyan-400',
};

function getSignalIcon(type: string) {
  const t = type.toLowerCase();
  if (t.includes('donat') || t.includes('contribut') || t.includes('campaign')) {
    return <DollarSign className="h-4 w-4 text-money-gold" />;
  }
  if (t.includes('stock') || t.includes('financial') || t.includes('holding')) {
    return <TrendingUp className="h-4 w-4 text-emerald-400" />;
  }
  if (t.includes('committee') || t.includes('regulat')) {
    return <Building2 className="h-4 w-4 text-amber-400" />;
  }
  if (t.includes('lobby')) {
    return <Megaphone className="h-4 w-4 text-purple-400" />;
  }
  if (t.includes('vote') || t.includes('legislat')) {
    return <Vote className="h-4 w-4 text-blue-400" />;
  }
  return <AlertTriangle className="h-4 w-4 text-zinc-400" />;
}

function getEntityHref(slug: string, entityType: string): string {
  if (entityType === 'person') return `/officials/${slug}`;
  return `/entities/${entityType}/${slug}`;
}

export default function RelationshipSpotlight({
  spotlights,
  officialName,
}: RelationshipSpotlightProps) {
  if (spotlights.length === 0) return null;

  return (
    <div className="space-y-4">
      <h3 className="flex items-center gap-2 font-mono text-sm font-semibold uppercase tracking-wider text-orange-400">
        <AlertTriangle className="h-4 w-4" />
        Relationship Spotlights for {officialName}
      </h3>

      {spotlights.map((spotlight) => {
        const sev = spotlight.severity.toLowerCase();
        const sevConfig = SEVERITY_BADGE[sev] || SEVERITY_BADGE.connection_noted;
        const typeBadge = TYPE_BADGE[spotlight.entity_type] || 'bg-zinc-700 text-zinc-300';

        return (
          <div
            key={spotlight.entity_slug}
            className="rounded-lg border border-zinc-800 border-l-4 border-l-orange-500 bg-orange-500/5"
          >
            <div className="p-4 sm:p-5">
              {/* Header */}
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <Link
                  href={getEntityHref(spotlight.entity_slug, spotlight.entity_type)}
                  className="text-base font-semibold text-zinc-100 hover:text-money-gold transition-colors"
                >
                  {spotlight.entity_name}
                </Link>
                <span
                  className={clsx(
                    'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium uppercase',
                    typeBadge
                  )}
                >
                  {spotlight.entity_type}
                </span>
                <span
                  className={clsx(
                    'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide',
                    sevConfig.bg,
                    sevConfig.text
                  )}
                >
                  {(sev === 'critical' || sev === 'high_concern') && <AlertTriangle className="mr-1 h-3 w-3" />}
                  {sevConfig.label}
                </span>
              </div>

              {/* Signal count */}
              <p className="mb-4 text-sm font-medium text-orange-400">
                {spotlight.signal_count} structural relationship{spotlight.signal_count !== 1 ? 's' : ''} identified
              </p>

              {/* Why This Matters */}
              {spotlight.why_this_matters && (
                <div className="mb-4 rounded-md border border-zinc-700/50 bg-zinc-800/30 px-3 py-2.5">
                  <p className="text-xs font-semibold uppercase tracking-wider text-zinc-500 mb-1">
                    Why This Matters
                  </p>
                  <p className="text-xs leading-relaxed text-zinc-400">
                    {spotlight.why_this_matters}
                  </p>
                </div>
              )}

              {/* Evidence chain */}
              {spotlight.signals.length > 0 && (
                <div className="ml-1 border-l-2 border-orange-500/30 pl-4 space-y-3">
                  {spotlight.signals.map((signal, i) => (
                    <div key={i} className="relative">
                      {/* Timeline dot */}
                      <div className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-orange-500/50 bg-zinc-900" />
                      <div className="flex items-start gap-2">
                        <span className="mt-0.5 shrink-0">
                          {getSignalIcon(signal.type)}
                        </span>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-zinc-300 leading-relaxed">
                            {signal.detail}
                          </p>
                          {signal.source && (
                            <a
                              href={signal.source.startsWith('http') ? signal.source : undefined}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="mt-0.5 inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-money-gold transition-colors"
                            >
                              <ExternalLink className="h-3 w-3" />
                              {signal.source.startsWith('http')
                                ? new URL(signal.source).hostname.replace('www.', '')
                                : signal.source}
                            </a>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
