'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { getSharedInterests } from '@/lib/api';
import type { SharedInterestsData } from '@/lib/api';
import { Users, Building2, ScrollText, Loader2 } from 'lucide-react';

interface RelatedInsightsProps {
  slug: string;
  entityName: string;
}

export default function RelatedInsights({ slug, entityName }: RelatedInsightsProps) {
  const [data, setData] = useState<SharedInterestsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    getSharedInterests(slug)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [slug]);

  if (loading) {
    return (
      <div className="mt-8 rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
        <div className="flex items-center gap-2 text-zinc-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">Loading related insights...</span>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const hasRelatedOfficials = data.shared_donors && data.shared_donors.length > 0;
  const hasIndustries = data.industry_network && data.industry_network.length > 0;
  const hasAllies = data.legislative_allies && data.legislative_allies.length > 0;

  if (!hasRelatedOfficials && !hasIndustries && !hasAllies) return null;

  return (
    <div className="mt-8 rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
      <h3 className="mb-5 text-sm font-bold uppercase tracking-wider text-zinc-400">
        You Might Also Want to Know
      </h3>

      <div className="space-y-6">
        {/* Related Officials */}
        {hasRelatedOfficials && (
          <div>
            <div className="mb-3 flex items-center gap-2">
              <Users className="h-4 w-4 text-amber-400" />
              <h4 className="text-xs font-bold uppercase tracking-wider text-zinc-500">
                Related Officials
              </h4>
            </div>
            <p className="mb-2 text-xs text-zinc-500">
              Officials who share donors with {entityName}:
            </p>
            <div className="space-y-1.5">
              {data.shared_donors.slice(0, 5).map((official) => (
                <div
                  key={official.slug}
                  className="flex items-center justify-between rounded-lg bg-zinc-800/40 px-3 py-2"
                >
                  <Link
                    href={`/officials/${official.slug}`}
                    className="text-sm text-amber-400 hover:text-amber-300 hover:underline"
                  >
                    {official.name}
                  </Link>
                  <span className="rounded-full bg-zinc-700 px-2 py-0.5 text-[10px] font-medium text-zinc-300">
                    {official.shared_count} shared donor{official.shared_count !== 1 ? 's' : ''}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Related Companies / Industries */}
        {hasIndustries && (
          <div>
            <div className="mb-3 flex items-center gap-2">
              <Building2 className="h-4 w-4 text-amber-400" />
              <h4 className="text-xs font-bold uppercase tracking-wider text-zinc-500">
                Related Companies
              </h4>
            </div>
            <p className="mb-2 text-xs text-zinc-500">
              Companies connected to multiple officials:
            </p>
            <div className="space-y-1.5">
              {data.industry_network.slice(0, 5).map((item) => {
                const industrySlug = item.industry
                  .toLowerCase()
                  .replace(/[^a-z0-9]+/g, '-')
                  .replace(/^-|-$/g, '');
                return (
                  <div
                    key={item.industry}
                    className="flex items-center justify-between rounded-lg bg-zinc-800/40 px-3 py-2"
                  >
                    <Link
                      href={`/entities/industry/${industrySlug}`}
                      className="text-sm text-amber-400 hover:text-amber-300 hover:underline"
                    >
                      {item.industry}
                    </Link>
                    <span className="rounded-full bg-zinc-700 px-2 py-0.5 text-[10px] font-medium text-zinc-300">
                      {item.connected_officials} official{item.connected_officials !== 1 ? 's' : ''}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Related Bills (legislative allies as proxy) */}
        {hasAllies && (
          <div>
            <div className="mb-3 flex items-center gap-2">
              <ScrollText className="h-4 w-4 text-amber-400" />
              <h4 className="text-xs font-bold uppercase tracking-wider text-zinc-500">
                Related Bills
              </h4>
            </div>
            <p className="mb-2 text-xs text-zinc-500">
              Bills where money and votes align:
            </p>
            <div className="space-y-1.5">
              {data.legislative_allies.slice(0, 5).map((ally) => (
                <div
                  key={ally.slug}
                  className="flex items-center justify-between rounded-lg bg-zinc-800/40 px-3 py-2"
                >
                  <Link
                    href={`/officials/${ally.slug}`}
                    className="text-sm text-amber-400 hover:text-amber-300 hover:underline"
                  >
                    {ally.name}
                  </Link>
                  <span className="rounded-full bg-zinc-700 px-2 py-0.5 text-[10px] font-medium text-zinc-300">
                    {ally.shared_bills} co-sponsored bill{ally.shared_bills !== 1 ? 's' : ''}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
