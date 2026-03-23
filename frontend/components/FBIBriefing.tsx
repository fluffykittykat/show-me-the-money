'use client';

import { useState, useEffect } from 'react';
import { Shield, Loader2, AlertTriangle } from 'lucide-react';
import { getBriefing } from '@/lib/api';
import type { BriefingResponse } from '@/lib/types';
import { formatDate, capitalize } from '@/lib/utils';

interface FBIBriefingProps {
  entitySlug: string;
  entityName: string;
  entityType: string;
}

/**
 * Parse the pre-formatted briefing text from the backend into styled sections.
 */
function BriefingContent({ text }: { text: string }) {
  const lines = text.split('\n');
  const elements: React.ReactNode[] = [];
  let inAssessment = false;
  let assessmentLines: string[] = [];
  let bulletGroup: string[] = [];

  function flushBullets() {
    if (bulletGroup.length === 0) return;
    elements.push(
      <ul key={`bullets-${elements.length}`} className="my-2 space-y-1 pl-4">
        {bulletGroup.map((b, i) => (
          <li key={i} className="flex items-start gap-2 text-zinc-300">
            <span className="mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-money-gold" />
            <span>{b.replace(/^[•\-]\s*/, '')}</span>
          </li>
        ))}
      </ul>
    );
    bulletGroup = [];
  }

  function flushAssessment() {
    if (assessmentLines.length === 0) return;
    elements.push(
      <div
        key={`assessment-${elements.length}`}
        className="mt-4 rounded-md border border-amber-500/20 bg-amber-500/5 p-4"
      >
        <h4 className="mb-2 font-mono text-xs font-bold uppercase tracking-wider text-amber-400">
          Investigative Assessment
        </h4>
        <div className="space-y-2 text-sm leading-relaxed text-zinc-300">
          {assessmentLines.map((line, i) => {
            const trimmed = line.trim();
            if (!trimmed) return null;
            if (trimmed.startsWith('•') || trimmed.startsWith('- ')) {
              return (
                <div key={i} className="flex items-start gap-2 pl-2">
                  <span className="mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                  <span>{trimmed.replace(/^[•\-]\s*/, '')}</span>
                </div>
              );
            }
            return <p key={i}>{trimmed}</p>;
          })}
        </div>
      </div>
    );
    assessmentLines = [];
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Skip empty lines
    if (!trimmed) {
      if (inAssessment) {
        assessmentLines.push('');
      } else {
        flushBullets();
      }
      continue;
    }

    // INVESTIGATIVE ASSESSMENT section
    if (trimmed.toUpperCase().startsWith('INVESTIGATIVE ASSESSMENT')) {
      flushBullets();
      inAssessment = true;
      continue;
    }

    if (inAssessment) {
      assessmentLines.push(trimmed);
      continue;
    }

    // CLASSIFICATION line
    if (trimmed.toUpperCase().startsWith('CLASSIFICATION:')) {
      flushBullets();
      elements.push(
        <p
          key={`class-${elements.length}`}
          className="font-mono text-[11px] uppercase tracking-wider text-zinc-600"
        >
          {trimmed}
        </p>
      );
      continue;
    }

    // SUBJECT line
    if (trimmed.toUpperCase().startsWith('SUBJECT:')) {
      flushBullets();
      elements.push(
        <p
          key={`subject-${elements.length}`}
          className="mt-1 font-mono text-xs font-semibold uppercase tracking-wider text-zinc-400"
        >
          {trimmed}
        </p>
      );
      continue;
    }

    // KEY FINDINGS header
    if (trimmed.toUpperCase().startsWith('KEY FINDINGS')) {
      flushBullets();
      elements.push(
        <h4
          key={`kf-${elements.length}`}
          className="mb-1 mt-3 font-mono text-xs font-bold uppercase tracking-wider text-money-gold"
        >
          {trimmed}
        </h4>
      );
      continue;
    }

    // Bullet points
    if (trimmed.startsWith('•') || trimmed.startsWith('- ')) {
      bulletGroup.push(trimmed);
      continue;
    }

    // Regular paragraph
    flushBullets();
    elements.push(
      <p key={`p-${elements.length}`} className="my-1.5 text-zinc-300">
        {trimmed}
      </p>
    );
  }

  // Flush remaining
  flushBullets();
  if (inAssessment) {
    flushAssessment();
  }

  return <>{elements}</>;
}

export default function FBIBriefing({
  entitySlug,
  entityName,
  entityType,
}: FBIBriefingProps) {
  const [briefing, setBriefing] = useState<BriefingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getBriefing(entitySlug)
      .then((data) => {
        setBriefing(data);
      })
      .catch(() => {
        setError('Briefing generation unavailable');
      })
      .finally(() => {
        setLoading(false);
      });
  }, [entitySlug]);

  return (
    <div className="relative overflow-hidden rounded-lg border border-zinc-700 bg-zinc-950/80">
      {/* Gold top border accent */}
      <div className="h-1 bg-gradient-to-r from-money-gold via-money-gold/60 to-transparent" />

      {/* Watermark */}
      <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-[0.02]">
        <span className="select-none text-6xl font-black uppercase tracking-[0.3em] text-white rotate-[-15deg]">
          FOLLOW THE MONEY
        </span>
      </div>

      <div className="relative p-5 sm:p-6">
        {/* Header */}
        <div className="mb-4 flex items-center justify-between border-b border-dashed border-zinc-700 pb-3">
          <div className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-money-gold" />
            <span className="font-mono text-xs font-bold uppercase tracking-[0.2em] text-money-gold">
              FBI Special Agent Briefing // Follow The Money
            </span>
          </div>
          <span className="hidden font-mono text-xs text-zinc-600 sm:inline">
            {capitalize(entityType)} // {entitySlug}
          </span>
        </div>

        {/* Classification line */}
        <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-600">
          Classification: Unclassified // For Official Use Only
        </p>
        <p className="mb-4 font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-600">
          Prepared By: Financial Crimes &amp; Public Corruption Unit
        </p>

        {/* Subject */}
        <div className="mb-4 border-b border-dashed border-zinc-800 pb-3">
          <span className="font-mono text-xs uppercase tracking-wider text-zinc-500">
            Subject:
          </span>
          <span className="ml-2 font-mono text-sm font-semibold text-zinc-200">
            {entityName}
          </span>
        </div>

        {/* Loading state */}
        {loading && (
          <div className="flex items-center gap-3 py-8">
            <Loader2 className="h-5 w-5 animate-spin text-money-gold" />
            <span className="font-mono text-sm text-zinc-400">
              Generating intelligence briefing...
            </span>
          </div>
        )}

        {/* Error state */}
        {error && !loading && (
          <div className="flex items-center gap-3 rounded-md border border-yellow-500/20 bg-yellow-500/5 px-4 py-3">
            <AlertTriangle className="h-4 w-4 shrink-0 text-yellow-500" />
            <span className="font-mono text-sm text-yellow-200">{error}</span>
          </div>
        )}

        {/* Briefing content */}
        {briefing && !loading && (
          <div className="space-y-0 font-mono text-sm leading-relaxed">
            <BriefingContent text={briefing.briefing_text} />

            {briefing.generated_at && (
              <p className="mt-4 text-[10px] text-zinc-600">
                Intelligence generated {formatDate(briefing.generated_at)}
              </p>
            )}
          </div>
        )}

        {/* Classification footer */}
        <div className="mt-5 border-t border-dashed border-zinc-800 pt-3 text-center">
          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.3em] text-zinc-700">
            Follow The Money // End Briefing
          </span>
        </div>
      </div>
    </div>
  );
}
