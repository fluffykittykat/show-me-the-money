'use client';

import type { V2MoneyTrail } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import VerdictBadge from './VerdictBadge';
import ChainVisualization from './ChainVisualization';

interface MoneyTrailCardProps {
  trail: V2MoneyTrail;
  officialName: string;
  officialSlug: string;
}

export default function MoneyTrailCard({ trail, officialName, officialSlug }: MoneyTrailCardProps) {
  const chain = trail.chain || {};
  const donorCount = (chain as Record<string, unknown>).donor_count as number || chain.donors?.length || 0;

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 mb-4 transition-all duration-200 hover:border-zinc-600 hover:bg-zinc-800/60">
      {/* Header: industry + amount + dots + verdict */}
      <div className="flex justify-between items-start mb-3">
        <div>
          <div className="text-lg font-semibold">{trail.industry}</div>
          <div className="flex items-center gap-3 mt-1">
            <div className="flex gap-1">
              {Array.from({ length: 7 }, (_, i) => (
                <div key={i} className={`w-2 h-2 rounded-full ${i < trail.dot_count ? 'bg-amber-500' : 'bg-zinc-700'}`} />
              ))}
            </div>
            <span className="text-amber-400 font-semibold text-sm">{formatMoney(trail.total_amount)}</span>
            {donorCount > 1 && (
              <span className="text-zinc-500 text-xs">from {donorCount} donors</span>
            )}
          </div>
        </div>
        <VerdictBadge verdict={trail.verdict} />
      </div>

      {/* Chain visualization */}
      {chain && Object.keys(chain).length > 0 && (
        <ChainVisualization chain={chain} officialName={officialName} officialSlug={officialSlug} className="my-4" />
      )}

      {/* Narrative */}
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
