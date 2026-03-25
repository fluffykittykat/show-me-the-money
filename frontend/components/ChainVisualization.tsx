'use client';

import Link from 'next/link';
import { formatMoney } from '@/lib/utils';

interface ChainVisualizationProps {
  chain: {
    donors?: Array<{ name: string; slug: string; amount: number }>;
    committees?: Array<{ name: string; slug: string }>;
    bills?: Array<{ name: string; slug: string }>;
    middlemen?: Array<{ name: string; slug: string; amount_in: number; amount_out: number }>;
    lobbying?: Array<{ firm: string; client: string; issue: string }>;
  };
  officialName: string;
  officialSlug: string;
  className?: string;
}

interface ChainNode {
  label: string;
  name: string;
  href: string;
  amount?: string;
  color: {
    bg: string;
    border: string;
    label: string;
    accent: string;
  };
}

const NODE_COLORS = {
  Donor:       { bg: 'bg-emerald-950/50', border: 'border-emerald-700/50', label: 'text-emerald-500', accent: 'text-emerald-400' },
  Middleman:   { bg: 'bg-amber-950/50',   border: 'border-amber-700/50',   label: 'text-amber-500',   accent: 'text-amber-400' },
  Official:    { bg: 'bg-blue-950/50',     border: 'border-blue-700/50',    label: 'text-blue-500',    accent: 'text-blue-400' },
  Committee:   { bg: 'bg-purple-950/50',   border: 'border-purple-700/50',  label: 'text-purple-500',  accent: 'text-purple-400' },
  Legislation: { bg: 'bg-red-950/50',      border: 'border-red-700/50',     label: 'text-red-500',     accent: 'text-red-400' },
};

export default function ChainVisualization({ chain, officialName, officialSlug, className = '' }: ChainVisualizationProps) {
  const nodes: ChainNode[] = [];

  const donors = chain.donors || [];
  if (donors.length > 0) {
    const d = donors[0];
    nodes.push({ label: 'Donor', name: d.name, href: `/entities/pac/${d.slug}`, amount: formatMoney(d.amount), color: NODE_COLORS.Donor });
  }

  const middlemen = chain.middlemen || [];
  if (middlemen.length > 0) {
    const m = middlemen[0];
    nodes.push({ label: 'Middleman', name: m.name, href: `/entities/pac/${m.slug}`, amount: `${formatMoney(m.amount_in)} in → ${formatMoney(m.amount_out)} out`, color: NODE_COLORS.Middleman });
  }

  nodes.push({ label: 'Official', name: officialName, href: `/officials/${officialSlug}`, color: NODE_COLORS.Official });

  const committees = chain.committees || [];
  if (committees.length > 0) {
    nodes.push({ label: 'Committee', name: committees[0].name, href: `/entities/organization/${committees[0].slug}`, color: NODE_COLORS.Committee });
  }

  const bills = chain.bills || [];
  if (bills.length > 0) {
    nodes.push({ label: 'Legislation', name: bills[0].name, href: `/bills/${bills[0].slug}`, color: NODE_COLORS.Legislation });
  }

  if (nodes.length === 0) return null;

  return (
    <div className={`grid gap-2 py-2 ${className}`}
         style={{ gridTemplateColumns: `repeat(${nodes.length * 2 - 1}, auto)`, alignItems: 'stretch' }}>
      {nodes.map((node, i) => (
        <>
          {i > 0 && (
            <div key={`arrow-${i}`} className="flex items-center justify-center">
              <span className="text-zinc-600 text-lg">→</span>
            </div>
          )}
          <div
            key={i}
            className={`${node.color.bg} border ${node.color.border} rounded-lg px-3 py-2.5 text-center flex flex-col justify-center`}
            style={{ minWidth: '120px', maxWidth: '160px' }}
          >
            <span className={`block text-[0.6rem] uppercase tracking-widest font-semibold ${node.color.label}`}>
              {node.label}
            </span>
            <Link
              href={node.href}
              className="block text-sm font-medium text-zinc-100 hover:text-amber-300 transition-colors mt-0.5 leading-snug"
              style={{ wordBreak: 'break-word' }}
            >
              {node.name}
            </Link>
            {node.amount && (
              <span className={`block text-xs mt-1 font-medium ${node.color.accent}`}>{node.amount}</span>
            )}
          </div>
        </>
      ))}
    </div>
  );
}
