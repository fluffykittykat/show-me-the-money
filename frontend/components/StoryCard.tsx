'use client';

import Link from 'next/link';
import type { V2StoryCard } from '@/lib/types';
import VerdictBadge from './VerdictBadge';

export default function StoryCard({ story }: { story: V2StoryCard }) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 mb-3.5 hover:border-zinc-700 transition-colors">
      <div className="flex justify-between items-start gap-3 mb-2.5">
        <div className="text-[1.05rem] font-semibold leading-snug">{story.headline}</div>
        <VerdictBadge verdict={story.verdict} className="flex-shrink-0" />
      </div>
      <p className="text-zinc-400 text-sm leading-relaxed mb-2.5">
        {story.narrative.split(/(\$[\d,.]+[KMB]?)/).map((part, i) =>
          part.startsWith('$') ? <span key={i} className="text-amber-400 font-semibold">{part}</span> : <span key={i}>{part}</span>
        )}
      </p>
      {story.officials.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {story.officials.map((o, i) => (
            <Link key={i} href={`/officials/${o.slug}`} className="text-xs bg-zinc-800 px-2.5 py-1 rounded-md text-zinc-300 hover:text-amber-400 transition-colors">
              {o.name} {o.party && `(${o.party.charAt(0)})`}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
