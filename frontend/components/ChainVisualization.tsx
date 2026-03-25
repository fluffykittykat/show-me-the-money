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
}

export default function ChainVisualization({ chain, officialName, officialSlug, className = '' }: ChainVisualizationProps) {
  const nodes: ChainNode[] = [];

  const donors = chain.donors || [];
  if (donors.length > 0) {
    const d = donors[0];
    nodes.push({ label: 'Donor', name: d.name, href: `/entities/pac/${d.slug}`, amount: formatMoney(d.amount) });
  }

  const middlemen = chain.middlemen || [];
  if (middlemen.length > 0) {
    const m = middlemen[0];
    nodes.push({ label: 'Middleman', name: m.name, href: `/entities/pac/${m.slug}`, amount: `${formatMoney(m.amount_in)} in → ${formatMoney(m.amount_out)} out` });
  }

  nodes.push({ label: 'Official', name: officialName, href: `/officials/${officialSlug}` });

  const committees = chain.committees || [];
  if (committees.length > 0) {
    nodes.push({ label: 'Committee', name: committees[0].name, href: `/entities/organization/${committees[0].slug}` });
  }

  const bills = chain.bills || [];
  if (bills.length > 0) {
    nodes.push({ label: 'Legislation', name: bills[0].name, href: `/bills/${bills[0].slug}` });
  }

  if (nodes.length === 0) return null;

  return (
    <div className={`flex items-center gap-0 overflow-x-auto py-2 flex-wrap ${className}`}>
      {nodes.map((node, i) => (
        <div key={i} className="flex items-center">
          {i > 0 && <span className="text-zinc-500 text-lg px-1.5 flex-shrink-0">→</span>}
          <div className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-center min-w-0">
            <span className="block text-[0.65rem] uppercase tracking-wide text-zinc-500">{node.label}</span>
            <Link href={node.href} className="block text-sm font-medium text-zinc-100 hover:text-amber-400 transition-colors truncate">{node.name}</Link>
            {node.amount && <span className="block text-xs text-amber-400">{node.amount}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}
