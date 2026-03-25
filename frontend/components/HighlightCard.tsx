'use client';

import Link from 'next/link';
import VerdictBadge from './VerdictBadge';

interface HighlightCardProps {
  label: string;
  name: string;
  href: string;
  detail: string;
  verdict?: string;
  borderColor?: string;
}

export default function HighlightCard({ label, name, href, detail, verdict, borderColor = 'border-zinc-800' }: HighlightCardProps) {
  return (
    <div className={`bg-zinc-900 border ${borderColor} rounded-xl p-4 text-center`}>
      <div className="text-[0.65rem] uppercase tracking-widest text-zinc-500 mb-2">{label}</div>
      <Link href={href} className="block text-[0.95rem] font-semibold hover:text-amber-400 transition-colors mb-1">{name}</Link>
      <div className="text-sm text-zinc-400">{detail}</div>
      {verdict && <VerdictBadge verdict={verdict} className="mt-1.5" />}
    </div>
  );
}
