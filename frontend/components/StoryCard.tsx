'use client';

import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Clock } from 'lucide-react';
import type { V2StoryCard } from '@/lib/types';
import VerdictBadge from './VerdictBadge';

function fmtDate(d: string | null | undefined): string {
  if (!d) return '';
  try {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return ''; }
}

export default function StoryCard({ story }: { story: V2StoryCard }) {
  const router = useRouter();
  const primaryOfficial = story.officials[0];
  const cardHref = primaryOfficial ? `/officials/${primaryOfficial.slug}` : undefined;
  const storyDate = (story as unknown as Record<string, unknown>).date as string | undefined;

  return (
    <div
      onClick={cardHref ? () => router.push(cardHref) : undefined}
      className={`bg-zinc-900 border border-zinc-800 rounded-xl p-5 mb-3.5 transition-all duration-200 ${
        cardHref ? 'cursor-pointer hover:border-amber-500/50 hover:bg-zinc-800/80' : ''
      }`}
    >
      <div className="flex justify-between items-start gap-3 mb-2.5">
        <div className="text-[1.05rem] font-semibold leading-snug">{story.headline}</div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {storyDate && (
            <span className="flex items-center gap-1 text-xs text-zinc-600">
              <Clock className="w-3 h-3" />
              {fmtDate(storyDate)}
            </span>
          )}
          <VerdictBadge verdict={story.verdict} />
        </div>
      </div>
      <p className="text-zinc-400 text-sm leading-relaxed mb-2.5">
        {story.narrative.split(/(\$[\d,.]+[KMB]?)/).map((part, i) =>
          part.startsWith('$') ? <span key={i} className="text-amber-400 font-semibold">{part}</span> : <span key={i}>{part}</span>
        )}
      </p>
      {story.officials.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {story.officials.map((o, i) => (
            <Link
              key={i}
              href={`/officials/${o.slug}`}
              onClick={(e) => e.stopPropagation()}
              className="text-xs bg-zinc-700/50 px-2.5 py-1 rounded-md text-zinc-300 hover:text-amber-400 hover:bg-zinc-700 transition-colors"
            >
              {o.name} {o.party && `(${o.party.charAt(0)})`}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
