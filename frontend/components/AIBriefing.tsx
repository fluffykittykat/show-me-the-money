'use client';

import { Zap } from 'lucide-react';

interface AIBriefingProps {
  briefing: string | null;
  className?: string;
}

export default function AIBriefing({ briefing, className = '' }: AIBriefingProps) {
  return (
    <div className={`rounded-xl border border-amber-500/20 p-5 mb-8 ${className}`}
         style={{ background: 'linear-gradient(135deg, rgba(245,158,11,0.08), rgba(245,158,11,0.02))' }}>
      <div className="flex items-center gap-2 mb-3 text-amber-400 font-semibold text-sm uppercase tracking-wide">
        <Zap className="w-4 h-4" />
        AI Assessment
      </div>
      {briefing ? (
        <div className="text-zinc-300 leading-relaxed text-[0.95rem] space-y-3">
          {briefing.split('\n').map((line, i) => {
            const trimmed = line.trim();
            if (!trimmed) return null;
            if (trimmed.startsWith('*') || trimmed.startsWith('-')) {
              const bullet = trimmed.replace(/^[*\-]\s*/, '');
              return (
                <div key={i} className="flex gap-2 pl-1">
                  <span className="text-amber-500 mt-0.5 flex-shrink-0">•</span>
                  <span>{bullet}</span>
                </div>
              );
            }
            if (trimmed === trimmed.toUpperCase() && trimmed.length > 3 && trimmed.endsWith(':')) {
              return (
                <div key={i} className="text-amber-400 font-semibold text-xs uppercase tracking-wide mt-2">
                  {trimmed}
                </div>
              );
            }
            return <p key={i}>{trimmed}</p>;
          })}
        </div>
      ) : (
        <p className="text-zinc-500 italic">No briefing generated yet. Use &quot;Regenerate Briefing&quot; above.</p>
      )}
    </div>
  );
}
