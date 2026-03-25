'use client';

import type { V2MoneyTrail } from '@/lib/types';
import VerdictBadge from './VerdictBadge';
import ChainVisualization from './ChainVisualization';

interface MoneyTrailCardProps {
  trail: V2MoneyTrail;
  officialName: string;
  officialSlug: string;
}

export default function MoneyTrailCard({ trail, officialName, officialSlug }: MoneyTrailCardProps) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 mb-4">
      <div className="flex justify-between items-start mb-3">
        <div>
          <div className="text-lg font-semibold">{trail.industry}</div>
          <div className="flex gap-1 mt-1">
            {Array.from({ length: 5 }, (_, i) => (
              <div key={i} className={`w-2 h-2 rounded-full ${i < trail.dot_count ? 'bg-amber-500' : 'bg-zinc-700'}`} />
            ))}
          </div>
        </div>
        <VerdictBadge verdict={trail.verdict} />
      </div>

      {trail.chain && Object.keys(trail.chain).length > 0 && (
        <ChainVisualization chain={trail.chain} officialName={officialName} officialSlug={officialSlug} className="my-4" />
      )}

      {trail.narrative && (
        <p className="text-zinc-400 text-sm leading-relaxed">
          {trail.narrative.split(/(\$[\d,.]+[KMB]?)/).map((part, i) =>
            part.startsWith('$') ? <span key={i} className="text-amber-400 font-semibold">{part}</span> : <span key={i}>{part}</span>
          )}
        </p>
      )}
    </div>
  );
}
