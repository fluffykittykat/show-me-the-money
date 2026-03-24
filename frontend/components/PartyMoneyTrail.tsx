'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { getConnections } from '@/lib/api';
import type { Relationship } from '@/lib/types';
import { formatMoney } from '@/lib/utils';
import { ArrowRight, Building2 } from 'lucide-react';

interface PartyMoneyTrailProps {
  slug: string;
  donations: Relationship[];
}

const PARTY_COMMITTEES = ['dscc', 'nrsc', 'dccc', 'nrcc'];

interface CommitteeChain {
  committeeName: string;
  committeeSlug: string;
  amountToOfficial: number;
  topDonors: { name: string; slug: string; amount: number }[];
}

export default function PartyMoneyTrail({ slug, donations }: PartyMoneyTrailProps) {
  const [chains, setChains] = useState<CommitteeChain[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Find party committee donations to this official
    const partyDonations = donations.filter((d) => {
      const ce = d.connected_entity;
      if (!ce) return false;
      const slugLower = ce.slug.toLowerCase();
      return PARTY_COMMITTEES.some((pc) => slugLower.includes(pc));
    });

    if (partyDonations.length === 0) {
      setLoading(false);
      return;
    }

    // For each party committee, fetch who donates TO them
    const fetchChains = async () => {
      const results: CommitteeChain[] = [];

      for (const donation of partyDonations) {
        const ce = donation.connected_entity;
        if (!ce) continue;

        try {
          const connections = await getConnections(ce.slug, { limit: 100 });
          // Find donations TO this committee (where committee is the to_entity)
          const incomingDonors = connections.connections
            .filter((c) => c.relationship_type === 'donated_to' && c.to_entity_id === ce.id)
            .sort((a, b) => (b.amount_usd ?? 0) - (a.amount_usd ?? 0))
            .slice(0, 5)
            .map((c) => ({
              name: c.connected_entity?.name || 'Unknown',
              slug: c.connected_entity?.slug || '',
              amount: c.amount_usd ?? 0,
            }));

          if (incomingDonors.length > 0) {
            results.push({
              committeeName: ce.name,
              committeeSlug: ce.slug,
              amountToOfficial: donation.amount_usd ?? 0,
              topDonors: incomingDonors,
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
          These companies and organizations fund the party committee, which then distributes
          money to this official. The party committee is the middleman that launders the
          transactional relationship into what looks like ordinary party support.
        </p>

        {chains.map((chain) => (
          <div key={chain.committeeSlug} className="mb-4 last:mb-0">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-sm font-semibold text-zinc-200">
                Via{' '}
                <Link
                  href={`/entities/pac/${chain.committeeSlug}`}
                  className="text-money-gold hover:text-money-gold-hover"
                >
                  {chain.committeeName}
                </Link>
              </span>
              <span className="text-xs text-zinc-500">
                ({formatMoney(chain.amountToOfficial)} to this official)
              </span>
            </div>

            {/* The chain visualization */}
            <div className="space-y-2">
              {chain.topDonors.map((donor) => (
                <div
                  key={donor.slug}
                  className="flex items-center gap-2 rounded-lg bg-zinc-800/50 px-3 py-2 text-sm"
                >
                  <Link
                    href={`/entities/organization/${donor.slug}`}
                    className="font-medium text-zinc-200 hover:text-money-gold"
                  >
                    {donor.name}
                  </Link>
                  <span className="text-money-success font-semibold">
                    {formatMoney(donor.amount)}
                  </span>
                  <ArrowRight className="h-3 w-3 text-zinc-600" />
                  <Link
                    href={`/entities/pac/${chain.committeeSlug}`}
                    className="text-zinc-400 hover:text-money-gold"
                  >
                    {chain.committeeName}
                  </Link>
                  <ArrowRight className="h-3 w-3 text-zinc-600" />
                  <span className="text-zinc-300">This Official</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
