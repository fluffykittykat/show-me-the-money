'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  TrendingUp,
  Building2,
  Vote,
  DollarSign,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  AlertTriangle,
  Shield,
  HelpCircle,
} from 'lucide-react';
import clsx from 'clsx';
import type { ChainLink } from '@/lib/api';
import EvidenceChain from '@/components/EvidenceChain';

interface EvidenceChainData {
  chain: ChainLink[];
  severity: string;
  narrative: string;
  officialSlug: string;
  companySlug: string;
}

interface ConflictCardProps {
  severity: string;
  conflictType: string;
  description: string;
  evidence: Array<{ type: string; entity?: string; name?: string; amount?: number; detail?: string; source?: string }>;
  relatedEntities: string[];
  whyThisMatters?: string;
  evidenceChain?: EvidenceChainData | null;
}

const SEVERITY_CONFIG: Record<string, { border: string; bg: string; badge: string; label: string }> = {
  high_concern: {
    border: 'border-l-red-500',
    bg: 'bg-red-500/5',
    badge: 'bg-red-500/20 text-red-400 border-red-500/30',
    label: 'HIGH CONCERN',
  },
  notable_pattern: {
    border: 'border-l-orange-500',
    bg: 'bg-orange-500/5',
    badge: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    label: 'NOTABLE PATTERN',
  },
  structural_relationship: {
    border: 'border-l-yellow-500',
    bg: 'bg-yellow-500/5',
    badge: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    label: 'STRUCTURAL RELATIONSHIP',
  },
  connection_noted: {
    border: 'border-l-blue-500',
    bg: 'bg-blue-500/5',
    badge: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    label: 'CONNECTION NOTED',
  },
  critical: {
    border: 'border-l-red-500',
    bg: 'bg-red-500/5',
    badge: 'bg-red-500/20 text-red-400 border-red-500/30',
    label: 'HIGH CONCERN',
  },
  high: {
    border: 'border-l-orange-500',
    bg: 'bg-orange-500/5',
    badge: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
    label: 'NOTABLE PATTERN',
  },
  medium: {
    border: 'border-l-yellow-500',
    bg: 'bg-yellow-500/5',
    badge: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
    label: 'STRUCTURAL RELATIONSHIP',
  },
  low: {
    border: 'border-l-blue-500',
    bg: 'bg-blue-500/5',
    badge: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
    label: 'CONNECTION NOTED',
  },
};

function getEvidenceIcon(type: string) {
  const t = type.toLowerCase();
  if (t.includes('stock') || t.includes('financial') || t.includes('holding') || t.includes('trend')) {
    return <TrendingUp className="h-4 w-4" />;
  }
  if (t.includes('committee') || t.includes('building')) {
    return <Building2 className="h-4 w-4" />;
  }
  if (t.includes('vote') || t.includes('legislative')) {
    return <Vote className="h-4 w-4" />;
  }
  if (t.includes('donat') || t.includes('contribut') || t.includes('money') || t.includes('campaign')) {
    return <DollarSign className="h-4 w-4" />;
  }
  return <Shield className="h-4 w-4" />;
}

function formatConflictType(type: string): string {
  return type
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
}

/** Generate a plain-English "what we don't know" based on conflict type */
function getWhatWeDontKnow(conflictType: string): string {
  const t = conflictType.toLowerCase();
  if (t.includes('stock') || t.includes('financial') || t.includes('holding')) {
    return 'We cannot confirm if the official made trading decisions based on non-public information, or if the timing is coincidental.';
  }
  if (t.includes('lobby') || t.includes('revolving')) {
    return 'We cannot confirm whether lobbying contacts actually influenced any legislative decisions.';
  }
  if (t.includes('donat') || t.includes('campaign') || t.includes('contribution')) {
    return 'We cannot confirm whether donations influenced votes, or if donors simply supported someone who already shared their position.';
  }
  if (t.includes('committee')) {
    return 'We cannot determine if committee assignments drove these relationships or if they developed independently.';
  }
  return 'We cannot determine causation from public records alone. These are structural patterns, not proof of coordination.';
}

/** Generate a follow-up question worth asking */
function getQuestionWorthAsking(conflictType: string): string {
  const t = conflictType.toLowerCase();
  if (t.includes('stock') || t.includes('financial') || t.includes('holding')) {
    return 'Did this official recuse themselves from votes affecting companies they hold stock in?';
  }
  if (t.includes('lobby') || t.includes('revolving')) {
    return 'Did former staffers-turned-lobbyists have direct meetings with their former boss on behalf of clients?';
  }
  if (t.includes('donat') || t.includes('campaign') || t.includes('contribution')) {
    return 'How does this official\'s voting pattern on donor-related bills compare to colleagues who didn\'t receive these donations?';
  }
  if (t.includes('committee')) {
    return 'Were financial interests in committee-regulated industries acquired before or after the committee assignment?';
  }
  return 'What additional public records could help clarify whether this structural pattern reflects an actual conflict?';
}

export default function ConflictCard({
  severity,
  conflictType,
  description,
  evidence,
  relatedEntities,
  whyThisMatters,
  evidenceChain,
}: ConflictCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [chainExpanded, setChainExpanded] = useState(false);
  const config = SEVERITY_CONFIG[severity.toLowerCase()] || SEVERITY_CONFIG.connection_noted;

  return (
    <div
      className={clsx(
        'rounded-xl border border-zinc-800 border-l-4',
        config.border,
        config.bg
      )}
    >
      <div className="p-4 sm:p-5">
        {/* Header: severity badge + "YOU DECIDE" */}
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span
            className={clsx(
              'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide',
              config.badge
            )}
          >
            {(severity.toLowerCase() === 'critical' || severity.toLowerCase() === 'high_concern') && (
              <AlertTriangle className="mr-1 h-3 w-3" />
            )}
            {config.label}
          </span>
          <span className="text-xs font-bold uppercase tracking-wider text-zinc-400">
            POTENTIAL CONFLICT &mdash; YOU DECIDE
          </span>
        </div>

        {/* What happened (plain English) */}
        <div className="mb-3">
          <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-1">
            What happened
          </p>
          <p className="text-sm leading-relaxed text-zinc-200">
            {description}
          </p>
        </div>

        {/* Why it could matter */}
        {whyThisMatters && (
          <div className="mb-3">
            <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-1">
              Why it could matter
            </p>
            <p className="text-xs leading-relaxed text-zinc-400">
              {whyThisMatters}
            </p>
          </div>
        )}

        {/* What we don't know */}
        <div className="mb-3">
          <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-1">
            What we don&apos;t know
          </p>
          <p className="text-xs leading-relaxed text-zinc-500">
            {getWhatWeDontKnow(conflictType)}
          </p>
        </div>

        {/* Question worth asking */}
        <div className="mb-3 rounded-md border border-zinc-700/50 bg-zinc-800/30 px-3 py-2.5">
          <div className="flex items-start gap-2">
            <HelpCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-amber-500 mb-0.5">
                The question worth asking
              </p>
              <p className="text-xs leading-relaxed text-zinc-300 italic">
                {getQuestionWorthAsking(conflictType)}
              </p>
            </div>
          </div>
        </div>

        {/* Evidence Chain Visualization (inline) */}
        {evidenceChain && evidenceChain.chain.length > 0 && (
          <div className="mb-3">
            <button
              onClick={() => setChainExpanded(!chainExpanded)}
              className="inline-flex items-center gap-1 text-xs font-medium text-amber-500 hover:text-amber-400 transition-colors"
              aria-expanded={chainExpanded}
            >
              {chainExpanded ? (
                <ChevronUp className="h-3.5 w-3.5" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5" />
              )}
              {chainExpanded ? 'Hide' : 'Show'} Evidence Chain ({evidenceChain.chain.length} steps)
            </button>
            {chainExpanded && (
              <div className="mt-3">
                <EvidenceChain
                  chain={evidenceChain.chain}
                  severity={evidenceChain.severity}
                  narrative={evidenceChain.narrative}
                  officialSlug={evidenceChain.officialSlug}
                  companySlug={evidenceChain.companySlug}
                />
              </div>
            )}
          </div>
        )}

        {/* Evidence toggle */}
        {evidence.length > 0 && (
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
            {evidence.length} piece{evidence.length !== 1 ? 's' : ''} of supporting evidence
          </button>
        )}

        {/* Evidence chain timeline */}
        {expanded && evidence.length > 0 && (
          <div className="mt-4 ml-1 border-l border-zinc-700 pl-4 space-y-3">
            {evidence.map((item, i) => (
              <div key={i} className="relative">
                <div className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border-2 border-zinc-600 bg-zinc-900" />
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 text-zinc-500">
                    {getEvidenceIcon(item.type)}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-zinc-300 leading-relaxed">
                      {item.detail || item.name || item.type}
                    </p>
                    {item.source && (
                      <a
                        href={item.source.startsWith('http') ? item.source : undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-0.5 inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-amber-500 transition-colors"
                      >
                        <ExternalLink className="h-3 w-3" />
                        {item.source.startsWith('http')
                          ? new URL(item.source).hostname.replace('www.', '')
                          : item.source}
                      </a>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Related entities */}
        {relatedEntities.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <span className="text-xs text-zinc-500">Related:</span>
            {relatedEntities.map((slug) => (
              <Link
                key={slug}
                href={`/officials/${slug}`}
                className="rounded-md bg-zinc-800/80 px-2 py-0.5 text-xs text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200 transition-colors"
              >
                {slug.replace(/-/g, ' ')}
              </Link>
            ))}
          </div>
        )}

        {/* Disclaimer */}
        <p className="mt-3 text-[10px] text-zinc-600 italic border-t border-zinc-800 pt-2">
          Disclaimer: This shows a structural relationship, not proof of wrongdoing. Review the evidence and draw your own conclusions.
        </p>
      </div>
    </div>
  );
}
