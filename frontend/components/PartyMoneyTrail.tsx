'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { getConnections } from '@/lib/api';
import type { Relationship } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import { Building2 } from 'lucide-react';

interface PartyMoneyTrailProps {
  slug: string;
  officialName: string;
  donations: Relationship[];
}

const PARTY_COMMITTEES = ['dscc', 'nrsc', 'dccc', 'nrcc'];

interface CommitteeChain {
  committeeName: string;
  committeeSlug: string;
  committeeId: string;
  totalToOfficial: number;
  topFunders: { name: string; slug: string }[];
  totalFunders: number;
}

export default function PartyMoneyTrail({ slug, officialName, donations }: PartyMoneyTrailProps) {
  const [chains, setChains] = useState<CommitteeChain[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Deduplicate party committee donations
    const committeeMap = new Map<string, { name: string; slug: string; id: string; total: number }>();

    for (const d of donations) {
      const ce = d.connected_entity;
      if (!ce) continue;
      const slugLower = ce.slug.toLowerCase();
      if (!PARTY_COMMITTEES.some((pc) => slugLower.includes(pc))) continue;

      const existing = committeeMap.get(ce.slug);
      if (existing) {
        existing.total += d.amount_usd ?? 0;
      } else {
        committeeMap.set(ce.slug, {
          name: ce.name,
          slug: ce.slug,
          id: ce.id,
          total: d.amount_usd ?? 0,
        });
      }
    }

    if (committeeMap.size === 0) {
      setLoading(false);
      return;
    }

    const fetchChains = async () => {
      const results: CommitteeChain[] = [];

      for (const [, committee] of committeeMap) {
        try {
          const connections = await getConnections(committee.slug, { limit: 100 });
          const donorMap = new Map<string, { name: string; slug: string }>();
          for (const c of connections.connections) {
            if (c.relationship_type === 'donated_to' && c.to_entity_id === committee.id) {
              const ce = c.connected_entity;
              if (ce && !donorMap.has(ce.slug)) {
                donorMap.set(ce.slug, { name: ce.name, slug: ce.slug });
              }
            }
          }

          if (donorMap.size > 0) {
            results.push({
              committeeName: committee.name,
              committeeSlug: committee.slug,
              committeeId: committee.id,
              totalToOfficial: committee.total,
              topFunders: Array.from(donorMap.values()).slice(0, 6),
              totalFunders: donorMap.size,
            });
          }
        } catch {
          // skip
        }
      }

      setChains(results);
      setLoading(false);
    };

    fetchChains();
  }, [slug, donations]);

  if (loading || chains.length === 0) return null;

  return (
    <div className="mb-6">
      {chains.map((chain) => (
        <div
          key={chain.committeeSlug}
          className="rounded-xl border-2 border-red-500/30 bg-zinc-900/80 p-5 mb-4 last:mb-0"
        >
          {/* Clear headline telling the story */}
          <h3 className="flex items-center gap-2 text-base font-bold text-red-400 mb-1">
            <Building2 className="h-5 w-5" />
            {officialName} received {formatMoney(chain.totalToOfficial)} through a middleman
          </h3>
          <p className="text-sm text-zinc-400 mb-4">
            The middleman is the{' '}
            <Link
              href={`/entities/pac/${chain.committeeSlug}`}
              className="font-semibold text-red-400 hover:text-red-300"
            >
              {chain.committeeName}
            </Link>
            . These {chain.totalFunders} organizations fund the {chain.committeeName.split(' ')[0]} party committee,
            which then distributes money to candidates like {officialName}.
            This makes it look like ordinary party support instead of a direct
            relationship between donor and politician.
          </p>

          {/* Funders list */}
          <div className="rounded-lg bg-zinc-800/50 p-3">
            <span className="block text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">
              Organizations funding the{' '}
              <Link
                href={`/entities/pac/${chain.committeeSlug}`}
                className="text-red-400 hover:text-red-300"
              >
                {chain.committeeName.replace('Democratic ', '').replace('National ', '').replace('Republican ', '').split(' Campaign')[0]}
              </Link>
            </span>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {chain.topFunders.map((funder) => (
                <Link
                  key={funder.slug}
                  href={`/entities/organization/${funder.slug}`}
                  className="truncate text-sm text-zinc-300 hover:text-money-gold"
                >
                  {funder.name}
                </Link>
              ))}
            </div>
            {chain.totalFunders > 6 && (
              <Link
                href={`/entities/pac/${chain.committeeSlug}`}
                className="mt-2 block text-xs text-money-gold hover:text-money-gold-hover"
              >
                See all {chain.totalFunders} funders &rarr;
              </Link>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
