'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp, FileText, AlertTriangle } from 'lucide-react';
import { getBriefing } from '@/lib/api';
import type { BriefingResponse } from '@/lib/types';
import { formatDate } from '@/lib/utils';
import clsx from 'clsx';

interface BriefingPanelProps {
  entitySlug: string;
}

export default function BriefingPanel({ entitySlug }: BriefingPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [briefing, setBriefing] = useState<BriefingResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleToggle() {
    if (!isOpen && !briefing && !loading) {
      setLoading(true);
      setError(null);
      try {
        const data = await getBriefing(entitySlug);
        setBriefing(data);
      } catch {
        setError('Unable to load briefing. It may not be available yet.');
      } finally {
        setLoading(false);
      }
    }
    setIsOpen(!isOpen);
  }

  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900/80">
      <button
        onClick={handleToggle}
        className="flex w-full items-center justify-between px-6 py-4 text-left transition-colors hover:bg-zinc-800/50"
        aria-expanded={isOpen}
        aria-controls="briefing-content"
      >
        <div className="flex items-center gap-3">
          <FileText className="h-5 w-5 text-money-gold" />
          <span className="text-sm font-semibold uppercase tracking-wider text-money-gold">
            AI-Generated Intelligence Briefing
          </span>
        </div>
        {isOpen ? (
          <ChevronUp className="h-4 w-4 text-zinc-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-zinc-400" />
        )}
      </button>

      {isOpen && (
        <div
          id="briefing-content"
          role="region"
          aria-label="Intelligence briefing"
          className="border-t border-zinc-700"
        >
          <div className="px-6 py-5">
            {loading && (
              <div className="flex items-center gap-3 py-4">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-money-gold border-t-transparent" />
                <span className="text-sm text-zinc-400">
                  Generating briefing...
                </span>
              </div>
            )}

            {error && (
              <div className="flex items-center gap-3 rounded-md border border-yellow-500/20 bg-yellow-500/5 px-4 py-3">
                <AlertTriangle className="h-4 w-4 text-yellow-500" />
                <span className="text-sm text-yellow-200">{error}</span>
              </div>
            )}

            {briefing && (
              <div>
                <div
                  className={clsx(
                    'rounded-md border border-zinc-700/50 bg-zinc-950/50 p-5',
                    'font-mono text-sm leading-relaxed text-zinc-300'
                  )}
                >
                  <div className="mb-3 flex items-center justify-between border-b border-dashed border-zinc-700 pb-2">
                    <span className="text-xs font-bold uppercase tracking-widest text-zinc-500">
                      CLASSIFIED // FOLLOW THE MONEY
                    </span>
                    <span className="text-xs text-zinc-600">
                      Subject: {briefing.entity_name}
                    </span>
                  </div>
                  <div className="whitespace-pre-wrap">{briefing.briefing_text}</div>
                </div>
                {briefing.generated_at && (
                  <p className="mt-3 text-xs text-zinc-600">
                    Generated {formatDate(briefing.generated_at)}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
