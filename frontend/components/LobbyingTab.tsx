'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import type { Relationship } from '@/lib/types';
import { getCompanyLobbying } from '@/lib/api';
import type { LobbyingData } from '@/lib/api';
import { formatMoney } from '@/lib/utils';
import {
  AlertTriangle,
  Megaphone,
  Building2,
  DollarSign,
  Loader2,
} from 'lucide-react';
import clsx from 'clsx';
import DidYouKnow from '@/components/DidYouKnow';

interface LobbyingTabProps {
  entitySlug: string;
  entityName: string;
  committees: Relationship[];
  donations: Relationship[];
}

interface CompanyLobbyingInfo {
  slug: string;
  name: string;
  lobbyingData: LobbyingData | null;
  donationAmount: number;
  isDonor: boolean;
}

export default function LobbyingTab({
  entitySlug,
  entityName,
  committees,
  donations,
}: LobbyingTabProps) {
  const [companyLobbyingMap, setCompanyLobbyingMap] = useState<Map<string, LobbyingData | null>>(new Map());
  const [loading, setLoading] = useState(true);

  // Get unique donor company slugs
  const donorCompanies = donations
    .filter((d) => {
      const t = d.connected_entity?.entity_type ?? '';
      return t === 'company' || t === 'organization' || t === 'pac';
    })
    .reduce<Map<string, { slug: string; name: string; amount: number }>>((map, d) => {
      const slug = d.connected_entity?.slug ?? '';
      const name = d.connected_entity?.name ?? '';
      if (!slug) return map;
      const existing = map.get(slug);
      if (existing) {
        existing.amount += d.amount_usd ?? 0;
      } else {
        map.set(slug, { slug, name, amount: d.amount_usd ?? 0 });
      }
      return map;
    }, new Map());

  useEffect(() => {
    let cancelled = false;
    async function fetchLobbyingData() {
      setLoading(true);
      const results = new Map<string, LobbyingData | null>();
      const slugs = Array.from(donorCompanies.keys());

      // Fetch lobbying data for each donor company (limited to first 20)
      const fetches = slugs.slice(0, 20).map(async (slug) => {
        try {
          const data = await getCompanyLobbying(slug);
          results.set(slug, data);
        } catch {
          results.set(slug, null);
        }
      });

      await Promise.all(fetches);
      if (!cancelled) {
        setCompanyLobbyingMap(results);
        setLoading(false);
      }
    }

    fetchLobbyingData();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entitySlug]);

  // Build company info list
  const companyInfos: CompanyLobbyingInfo[] = Array.from(donorCompanies.values()).map((dc) => ({
    slug: dc.slug,
    name: dc.name,
    lobbyingData: companyLobbyingMap.get(dc.slug) ?? null,
    donationAmount: dc.amount,
    isDonor: true,
  }));

  // Cross-reference: companies that BOTH donate AND lobby
  const crossRefCompanies = companyInfos.filter(
    (c) => c.isDonor && c.lobbyingData && c.lobbyingData.total_spend > 0
  );

  // Companies with lobbying data
  const lobbyers = companyInfos.filter(
    (c) => c.lobbyingData && c.lobbyingData.total_spend > 0
  );

  const hasAnyData = lobbyers.length > 0 || committees.length > 0;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
        <span className="ml-2 text-sm text-zinc-500">Loading lobbying data...</span>
      </div>
    );
  }

  if (!hasAnyData && donorCompanies.size === 0) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-money-surface px-6 py-8 text-center">
        <Megaphone className="mx-auto h-8 w-8 text-zinc-600" />
        <p className="mt-3 text-sm text-zinc-400">
          Lobbying data ingestion in progress. Check back soon.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <DidYouKnow fact="Committee chairs have enormous power to schedule (or block) hearings, markup sessions, and votes. A chair who receives industry donations can simply never schedule a hearing on legislation that would hurt that industry." />

      {/* Header summary */}
      {lobbyers.length > 0 && (
        <div className="rounded-lg border border-zinc-800 bg-money-surface p-4">
          <h3 className="flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-wider text-zinc-400">
            <Megaphone className="h-4 w-4 text-money-gold" />
            Lobbying Overview
          </h3>
          <p className="mt-2 text-sm text-zinc-300">
            <span className="font-semibold text-money-gold">{lobbyers.length}</span>{' '}
            {lobbyers.length === 1 ? 'company has' : 'companies have'} active lobbying
            {committees.length > 0 && ' on issues within committee jurisdiction'}
          </p>
        </div>
      )}

      {/* Cross-Reference Section */}
      {crossRefCompanies.length > 0 && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-4">
          <h3 className="mb-3 flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-wider text-red-400">
            <AlertTriangle className="h-4 w-4" />
            Cross-Reference: Donate AND Lobby
          </h3>
          <p className="mb-4 text-xs text-zinc-500">
            Companies that both donate to {entityName} and actively lobby on legislative issues
          </p>
          <div className="space-y-3">
            {crossRefCompanies.map((company) => (
              <div
                key={company.slug}
                className="rounded-lg border border-red-500/20 bg-zinc-900/50 p-4"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Link
                    href={`/entities/company/${company.slug}`}
                    className="text-sm font-semibold text-zinc-200 hover:text-money-gold transition-colors"
                  >
                    {company.name}
                  </Link>
                  <span className="inline-flex items-center gap-1 rounded-full bg-red-500/20 px-2 py-0.5 text-[10px] font-bold uppercase text-red-400">
                    <AlertTriangle className="h-2.5 w-2.5" />
                    Donor + Lobbyist
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-4 text-xs text-zinc-400">
                  <span className="flex items-center gap-1">
                    <DollarSign className="h-3 w-3 text-money-gold" />
                    Donated: <span className="text-money-gold font-semibold">{formatMoney(company.donationAmount)}</span>
                  </span>
                  {company.lobbyingData && (
                    <>
                      <span className="flex items-center gap-1">
                        <Megaphone className="h-3 w-3 text-purple-400" />
                        Lobbying spend: <span className="text-purple-400 font-semibold">{formatMoney(company.lobbyingData.total_spend, { fromCents: true })}</span>
                      </span>
                      <span>
                        {company.lobbyingData.firm_count} firm{company.lobbyingData.firm_count !== 1 ? 's' : ''},{' '}
                        {company.lobbyingData.lobbyist_count} lobbyist{company.lobbyingData.lobbyist_count !== 1 ? 's' : ''}
                      </span>
                    </>
                  )}
                </div>
                {company.lobbyingData && company.lobbyingData.issues.length > 0 && (
                  <div className="mt-2">
                    <span className="text-[10px] uppercase tracking-wider text-zinc-500">
                      Lobbying issues:
                    </span>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {company.lobbyingData.issues.slice(0, 6).map((issue) => (
                        <span
                          key={issue}
                          className="rounded-full border border-purple-500/20 bg-purple-500/10 px-2 py-0.5 text-[10px] text-purple-300"
                        >
                          {issue}
                        </span>
                      ))}
                      {company.lobbyingData.issues.length > 6 && (
                        <span className="text-[10px] text-zinc-500">
                          +{company.lobbyingData.issues.length - 6} more
                        </span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Committees and jurisdiction */}
      {committees.length > 0 && (
        <div>
          <h3 className="mb-3 flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-wider text-zinc-400">
            <Building2 className="h-4 w-4 text-amber-400" />
            Committee Jurisdiction
          </h3>
          <div className="space-y-3">
            {committees.map((committee) => {
              const meta = committee.metadata as Record<string, unknown>;
              const industries = (meta?.industries as string[]) || [];
              const connSlug = committee.connected_entity?.slug ?? '';
              const connName = committee.connected_entity?.name ?? 'Unknown Committee';

              // Find companies lobbying on committee issues
              const relevantLobbyers = lobbyers.filter((c) => {
                if (!c.lobbyingData) return false;
                // Simple text match of lobbying issues with committee industries/name
                const lobbyIssuesText = c.lobbyingData.issues.join(' ').toLowerCase();
                const committeeText = (connName + ' ' + industries.join(' ')).toLowerCase();
                const words = committeeText.split(/\s+/).filter((w) => w.length > 3);
                return words.some((word) => lobbyIssuesText.includes(word));
              });

              return (
                <div
                  key={committee.id}
                  className="rounded-lg border border-zinc-800 bg-money-surface p-4"
                >
                  <div className="flex items-center gap-2">
                    <Link
                      href={connSlug ? `/entities/committee/${connSlug}` : '#'}
                      className="text-sm font-semibold text-zinc-200 hover:text-money-gold transition-colors"
                    >
                      {connName}
                    </Link>
                  </div>
                  {industries.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {industries.map((ind) => (
                        <span
                          key={ind}
                          className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-400"
                        >
                          {ind}
                        </span>
                      ))}
                    </div>
                  )}
                  {relevantLobbyers.length > 0 && (
                    <div className="mt-3 border-t border-zinc-800 pt-3">
                      <span className="text-[10px] uppercase tracking-wider text-zinc-500">
                        Companies lobbying on related issues:
                      </span>
                      <div className="mt-2 space-y-2">
                        {relevantLobbyers.map((company) => (
                          <div
                            key={company.slug}
                            className="flex flex-wrap items-center gap-2 text-xs"
                          >
                            <Link
                              href={`/entities/company/${company.slug}`}
                              className="text-zinc-300 hover:text-money-gold transition-colors"
                            >
                              {company.name}
                            </Link>
                            {company.lobbyingData && (
                              <span className="text-zinc-500">
                                {formatMoney(company.lobbyingData.total_spend, { fromCents: true })} in lobbying
                              </span>
                            )}
                            {company.isDonor && (
                              <span className="inline-flex items-center gap-1 rounded-full bg-red-500/20 px-1.5 py-0.5 text-[10px] text-red-400">
                                <AlertTriangle className="h-2.5 w-2.5" />
                                Also donates
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* All donor companies with lobbying info */}
      {companyInfos.length > 0 && lobbyers.length === 0 && crossRefCompanies.length === 0 && (
        <div className="rounded-lg border border-zinc-800 bg-money-surface px-6 py-8 text-center">
          <Megaphone className="mx-auto h-8 w-8 text-zinc-600" />
          <p className="mt-3 text-sm text-zinc-400">
            Lobbying data ingestion in progress. Check back soon.
          </p>
          <p className="mt-1 text-xs text-zinc-500">
            {donorCompanies.size} donor {donorCompanies.size === 1 ? 'company' : 'companies'} identified, lobbying records pending.
          </p>
        </div>
      )}

      {/* Individual company lobbying details (non-cross-ref) */}
      {lobbyers.filter((c) => !crossRefCompanies.includes(c)).length > 0 && (
        <div>
          <h3 className="mb-3 flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-wider text-zinc-400">
            <Megaphone className="h-4 w-4 text-purple-400" />
            Company Lobbying Activity
          </h3>
          <div className="space-y-3">
            {lobbyers
              .filter((c) => !crossRefCompanies.includes(c))
              .map((company) => (
                <div
                  key={company.slug}
                  className="rounded-lg border border-zinc-800 bg-money-surface p-4"
                >
                  <div className="flex items-center gap-2">
                    <Link
                      href={`/entities/company/${company.slug}`}
                      className="text-sm font-semibold text-zinc-200 hover:text-money-gold transition-colors"
                    >
                      {company.name}
                    </Link>
                  </div>
                  {company.lobbyingData && (
                    <div className="mt-2 flex flex-wrap gap-4 text-xs text-zinc-400">
                      <span>
                        Lobbying spend:{' '}
                        <span className="text-purple-400 font-semibold">
                          {formatMoney(company.lobbyingData.total_spend, { fromCents: true })}
                        </span>
                      </span>
                      <span>
                        {company.lobbyingData.filing_count} filing{company.lobbyingData.filing_count !== 1 ? 's' : ''}
                      </span>
                      <span>
                        {company.lobbyingData.firm_count} firm{company.lobbyingData.firm_count !== 1 ? 's' : ''}
                      </span>
                    </div>
                  )}
                  {company.lobbyingData && company.lobbyingData.issues.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {company.lobbyingData.issues.slice(0, 5).map((issue) => (
                        <span
                          key={issue}
                          className="rounded-full border border-purple-500/20 bg-purple-500/10 px-2 py-0.5 text-[10px] text-purple-300"
                        >
                          {issue}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
