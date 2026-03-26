'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { getV2Entity } from '@/lib/api';
import type { V2EntityResponse } from '@/lib/types';
import LoadingState from '@/components/LoadingState';
import AIBriefing from '@/components/AIBriefing';
import MoneyAmount from '@/components/MoneyAmount';
import PageControls from '@/components/PageControls';

export default function EntityPage() {
  const { slug } = useParams<{ type: string; slug: string }>();
  const [data, setData] = useState<V2EntityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [briefing, setBriefing] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    setLoading(true);
    getV2Entity(slug)
      .then(d => { setData(d); setBriefing(d.briefing); })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [slug]);

  if (loading) return <div className="max-w-[900px] mx-auto p-6"><LoadingState variant="profile" /></div>;
  if (error || !data) return (
    <div className="max-w-[900px] mx-auto p-6 text-center">
      <p className="text-zinc-500 mb-4">Entity not found.</p>
      <Link href="/search" className="text-amber-400 hover:underline">Search →</Link>
    </div>
  );

  const { entity, money_in, money_out, briefing: dataBriefing } = data;
  const entityType = entity.entity_type || 'organization';

  const TYPE_BADGES: Record<string, string> = {
    pac: 'bg-amber-500/15 text-amber-300',
    company: 'bg-blue-500/15 text-blue-400',
    organization: 'bg-purple-500/15 text-purple-400',
    industry: 'bg-emerald-500/15 text-emerald-400',
  };

  function MoneyList({ items, label }: { items: typeof money_in; label: string }) {
    if (items.length === 0) return <p className="text-zinc-600 text-sm">No {label.toLowerCase()} data.</p>;
    return (
      <div className="space-y-1">
        {items.map((item, i) => (
          <div key={i} className="flex items-center justify-between py-2 border-b border-zinc-900 last:border-0">
            <div>
              <Link href={item.entity_type === 'person' ? `/officials/${item.slug}` : `/entities/${item.entity_type}/${item.slug}`}
                className="text-sm font-medium hover:text-amber-400 transition-colors">{item.name}</Link>
              <span className="text-xs text-zinc-600 ml-2">{item.entity_type}</span>
            </div>
            <MoneyAmount amount={item.amount_usd} label={item.amount_label} />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-[900px] mx-auto px-4 py-6">
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <span className={`text-xs font-bold px-2.5 py-1 rounded ${TYPE_BADGES[entityType] || 'bg-zinc-700 text-zinc-300'}`}>
            {entityType.toUpperCase()}
          </span>
        </div>
        <h1 className="text-2xl font-bold">{entity.name}</h1>
      </div>

      {/* Page Controls */}
      <PageControls
        slug={slug}
        onBriefingUpdate={(text) => setBriefing(text)}
        onDataRefresh={() => {
          getV2Entity(slug).then(setData).catch(() => {});
        }}
      />

      <AIBriefing briefing={briefing ?? dataBriefing} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">Money In <span className="text-sm font-normal text-zinc-500">({money_in.length})</span></h2>
          <MoneyList items={money_in} label="Money In" />
        </div>
        <div>
          <h2 className="text-xl font-bold mb-4 pb-2 border-b border-zinc-800">Money Out <span className="text-sm font-normal text-zinc-500">({money_out.length})</span></h2>
          <MoneyList items={money_out} label="Money Out" />
        </div>
      </div>
    </div>
  );
}
