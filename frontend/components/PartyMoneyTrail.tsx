'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { getConnections } from '@/lib/api';
import type { Relationship } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import { Building2, ChevronDown, ChevronUp } from 'lucide-react';

interface PartyMoneyTrailProps {
  slug: string;
  officialName: string;
  donations: Relationship[];
}

// These are the big national party committees — shown with extra context
const NATIONAL_PARTY_COMMITTEES = ['dscc', 'nrsc', 'dccc', 'nrcc'];

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
    // Find ALL PAC/committee donors — each one is a potential middleman
    const committeeMap = new Map<string, { name: string; slug: string; id: string; total: number; isNational: boolean }>();

    for (const d of donations) {
      const ce = d.connected_entity;
      if (!ce) continue;
      // Include any PAC or organization that donated — they're all middlemen
      if (ce.entity_type !== 'pac' && ce.entity_type !== 'organization') continue;
      // Skip tiny donations
      if ((d.amount_usd ?? 0) < 100000) continue; // $1,000 minimum

      const slugLower = ce.slug.toLowerCase();
      const isNational = NATIONAL_PARTY_COMMITTEES.some((pc) => slugLower.includes(pc));

      const existing = committeeMap.get(ce.slug);
      if (existing) {
        existing.total += d.amount_usd ?? 0;
      } else {
        committeeMap.set(ce.slug, {
          name: ce.name,
          slug: ce.slug,
          id: ce.id,
          total: d.amount_usd ?? 0,
          isNational,
        });
      }
    }

    // Sort: national party committees first, then by amount
    const sortedCommittees = Array.from(committeeMap.values())
      .sort((a, b) => (b.isNational ? 1 : 0) - (a.isNational ? 1 : 0) || b.total - a.total)
      .slice(0, 5); // Top 5 middlemen

    if (sortedCommittees.length === 0) {
      setLoading(false);
      return;
    }

    const fetchChains = async () => {
      const results: CommitteeChain[] = [];

      for (const committee of sortedCommittees) {
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
              topFunders: Array.from(donorMap.values()),
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
        <ChainSection key={chain.committeeSlug} chain={chain} officialName={officialName} />
      ))}
    </div>
  );
}

function ChainSection({ chain, officialName }: { chain: CommitteeChain; officialName: string }) {
  const [expanded, setExpanded] = useState(false);
  const visibleFunders = expanded ? chain.topFunders : chain.topFunders.slice(0, 6);
  const hasMore = chain.topFunders.length > 6;

  return (
        <div
          className="rounded-xl border-2 border-red-500/30 bg-zinc-900/80 p-5 mb-4 last:mb-0"
        >
          {/* Clear headline telling the story */}
          <h3 className="flex items-center gap-2 text-base font-bold text-red-400 mb-1">
            <Building2 className="h-5 w-5" />
            {formatMoney(chain.totalToOfficial)} came through{' '}
            <Link
              href={`/entities/pac/${chain.committeeSlug}`}
              className="text-red-300 hover:text-red-200 underline decoration-red-500/30"
            >
              {chain.committeeName}
            </Link>
          </h3>
          <p className="text-sm text-zinc-400 mb-4">
            {chain.totalFunders > 0
              ? `This PAC collected money from ${chain.totalFunders} donors and passed ${formatMoney(chain.totalToOfficial)} to ${officialName}. Click the PAC name to see all its donors and where else it sends money.`
              : `This committee gave ${formatMoney(chain.totalToOfficial)} to ${officialName}. Click to investigate who funds this committee.`
            }
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
              {visibleFunders.map((funder) => (
                <Link
                  key={funder.slug}
                  href={`/entities/organization/${funder.slug}`}
                  className="truncate text-sm text-zinc-300 hover:text-money-gold"
                >
                  {funder.name}
                </Link>
              ))}
            </div>
            {hasMore && (
              <button
                onClick={() => setExpanded(!expanded)}
                className="mt-2 flex items-center gap-1 text-xs font-medium text-money-gold hover:text-money-gold-hover"
              >
                {expanded ? (
                  <>
                    <ChevronUp className="h-3 w-3" />
                    Show less
                  </>
                ) : (
                  <>
                    <ChevronDown className="h-3 w-3" />
                    Show all {chain.totalFunders} funders
                  </>
                )}
              </button>
            )}
          </div>
        </div>
  );
}
