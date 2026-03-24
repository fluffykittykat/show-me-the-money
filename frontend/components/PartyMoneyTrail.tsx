'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { getConnections } from '@/lib/api';
import type { Relationship } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import { ArrowRight, Building2 } from 'lucide-react';

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
    // Find and DEDUPLICATE party committee donations to this official
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
          // Find unique donors TO this committee
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
              topFunders: Array.from(donorMap.values()).slice(0, 5),
              totalFunders: donorMap.size,
            });
          }
        } catch {
          // Silently skip
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
      <div className="rounded-xl border-2 border-red-500/30 bg-zinc-900/80 p-5">
        <h3 className="flex items-center gap-2 text-base font-bold text-red-400">
          <Building2 className="h-5 w-5" />
          The Middleman: Party Committee Money
        </h3>
        <p className="mt-1 mb-4 text-sm text-zinc-400">
          These organizations fund the party committee, which then distributes
          money to {officialName}. The party committee makes a transactional
          relationship look like ordinary party support.
        </p>

        {chains.map((chain) => (
          <div key={chain.committeeSlug} className="mb-4 last:mb-0">
            <div className="flex items-stretch gap-0 rounded-xl overflow-hidden border border-zinc-800">
              {/* Left: Who funds the committee */}
              <div className="flex-1 bg-zinc-900 p-4">
                <span className="block text-[10px] font-bold uppercase tracking-wider text-zinc-500 mb-2">
                  Who funds the {chain.committeeName.replace('Democratic ', '').replace('National ', '').replace('Republican ', '').split(' Committee')[0]}
                </span>
                <div className="space-y-1.5">
                  {chain.topFunders.map((funder) => (
                    <Link
                      key={funder.slug}
                      href={`/entities/organization/${funder.slug}`}
                      className="block truncate text-sm text-zinc-300 hover:text-money-gold"
                    >
                      {funder.name}
                    </Link>
                  ))}
                  {chain.totalFunders > 5 && (
                    <span className="text-[10px] text-zinc-600">
                      + {chain.totalFunders - 5} more
                    </span>
                  )}
                </div>
              </div>

              {/* Middle: Committee */}
              <div className="flex flex-col items-center justify-center bg-zinc-800/50 px-4">
                <ArrowRight className="h-4 w-4 text-red-400" />
                <Link
                  href={`/entities/pac/${chain.committeeSlug}`}
                  className="mt-1 text-xs font-bold text-red-400 hover:text-red-300 text-center"
                >
                  {chain.committeeName.replace('Democratic ', 'Dem. ').replace('National ', '').replace('Republican ', 'Rep. ').replace('Congressional ', '').replace('Campaign Committee', '').replace('Senatorial ', 'Sen. ').trim()}
                </Link>
                <ArrowRight className="h-4 w-4 text-red-400 mt-1" />
              </div>

              {/* Right: Official + amount received */}
              <div className="flex flex-col items-center justify-center bg-zinc-900 px-4 py-3">
                <span className="text-sm font-semibold text-zinc-200">{officialName}</span>
                <span className="mt-1 text-lg font-bold text-money-success">
                  {formatMoney(chain.totalToOfficial)}
                </span>
                <span className="text-[10px] text-zinc-500">received</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
