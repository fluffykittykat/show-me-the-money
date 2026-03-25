'use client';

const VERDICT_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  NORMAL:     { bg: 'bg-emerald-500/15', text: 'text-emerald-400', border: 'border-emerald-500/40' },
  CONNECTED:  { bg: 'bg-amber-500/15',   text: 'text-amber-300',   border: 'border-amber-500/40' },
  INFLUENCED: { bg: 'bg-red-500/15',     text: 'text-red-400',     border: 'border-red-500/40' },
  OWNED:      { bg: 'bg-black/50',       text: 'text-zinc-100',    border: 'border-zinc-500' },
};

interface VerdictPillProps {
  verdict: string;
  dotCount: number;
  maxDots?: number;
  className?: string;
}

export default function VerdictPill({ verdict, dotCount, maxDots = 5, className = '' }: VerdictPillProps) {
  const style = VERDICT_STYLES[verdict] || VERDICT_STYLES.NORMAL;
  return (
    <div className={`inline-flex items-center gap-2 px-4 py-1.5 rounded-full border-2 font-bold text-base ${style.bg} ${style.text} ${style.border} ${className}`}>
      <span className="flex gap-1 tracking-widest">
        {Array.from({ length: maxDots }, (_, i) => (
          <span key={i} className={i < dotCount ? 'opacity-100' : 'opacity-30'}>●</span>
        ))}
      </span>
      {verdict}
    </div>
  );
}
