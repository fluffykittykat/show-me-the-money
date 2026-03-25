'use client';

import { useState } from 'react';
import { RefreshCw, Zap } from 'lucide-react';
import { getBriefing } from '@/lib/api';

interface AIBriefingProps {
  briefing: string | null;
  slug: string;
  className?: string;
}

export default function AIBriefing({ briefing, slug, className = '' }: AIBriefingProps) {
  const [text, setText] = useState(briefing);
  const [loading, setLoading] = useState(false);

  async function handleRegenerate() {
    setLoading(true);
    try {
      const res = await getBriefing(slug, true);
      setText(res.briefing_text);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={`rounded-xl border border-amber-500/20 p-5 mb-8 ${className}`}
         style={{ background: 'linear-gradient(135deg, rgba(245,158,11,0.08), rgba(245,158,11,0.02))' }}>
      <div className="flex items-center gap-2 mb-3 text-amber-400 font-semibold text-sm uppercase tracking-wide">
        <Zap className="w-4 h-4" />
        AI Assessment
      </div>
      {text ? (
        <div className="text-zinc-300 leading-relaxed text-[0.95rem] space-y-3">
          {text.split('\n').map((line, i) => {
            const trimmed = line.trim();
            if (!trimmed) return null;
            // Bullet point lines (starting with * or -)
            if (trimmed.startsWith('*') || trimmed.startsWith('-')) {
              const bullet = trimmed.replace(/^[*\-]\s*/, '');
              return (
                <div key={i} className="flex gap-2 pl-1">
                  <span className="text-amber-500 mt-0.5 flex-shrink-0">•</span>
                  <span>{bullet}</span>
                </div>
              );
            }
            // Section headers (all caps lines like "KEY FINDINGS:")
            if (trimmed === trimmed.toUpperCase() && trimmed.length > 3 && trimmed.endsWith(':')) {
              return (
                <div key={i} className="text-amber-400 font-semibold text-xs uppercase tracking-wide mt-2">
                  {trimmed}
                </div>
              );
            }
            // Regular paragraph
            return <p key={i}>{trimmed}</p>;
          })}
        </div>
      ) : (
        <p className="text-zinc-500 italic">No briefing generated yet.</p>
      )}
      <button
        onClick={handleRegenerate}
        disabled={loading}
        className="mt-3 inline-flex items-center gap-1.5 px-3 py-1 rounded-md border border-amber-500/30 text-amber-400 text-xs hover:bg-amber-500/10 disabled:opacity-50 transition-colors"
      >
        <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
        {loading ? 'Generating...' : text ? 'Regenerate' : 'Generate briefing'}
      </button>
    </div>
  );
}
