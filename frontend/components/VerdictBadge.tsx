'use client';

const BADGE_STYLES: Record<string, string> = {
  NORMAL:        'bg-emerald-500/15 text-emerald-400',
  CONNECTED:     'bg-amber-500/15 text-amber-300',
  INFLUENCED:    'bg-red-500/15 text-red-400',
  OWNED:         'bg-black/50 text-zinc-100 border border-zinc-500',
  MIDDLEMAN:     'bg-amber-500/15 text-amber-300',
  REVOLVING_DOOR:'bg-purple-500/15 text-purple-400',
  MISSING:       'bg-zinc-700 text-zinc-400',
};

interface VerdictBadgeProps {
  verdict: string;
  className?: string;
}

export default function VerdictBadge({ verdict, className = '' }: VerdictBadgeProps) {
  const style = BADGE_STYLES[verdict] || BADGE_STYLES.MISSING;
  return (
    <span className={`inline-block text-xs font-bold px-2 py-0.5 rounded ${style} ${className}`}>
      {verdict}
    </span>
  );
}
