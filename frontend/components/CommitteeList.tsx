'use client';

import Link from 'next/link';
import type { Relationship } from '@/lib/types';
import { Users } from 'lucide-react';

interface CommitteeListProps {
  committees: Relationship[];
}

function slugify(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

const COMMITTEE_INDUSTRIES: Record<string, string[]> = {
  'banking': ['Finance', 'Banking', 'Insurance', 'Real Estate'],
  'agriculture': ['Agriculture', 'Food', 'Farming'],
  'joint economic': ['Finance', 'Economics', 'Trade'],
  'armed services': ['Defense', 'Aerospace', 'Military'],
  'commerce': ['Technology', 'Telecommunications', 'Consumer Protection'],
  'energy': ['Energy', 'Oil & Gas', 'Nuclear'],
  'environment': ['Environment', 'Conservation', 'Climate'],
  'finance': ['Finance', 'Tax', 'Trade'],
  'foreign relations': ['Defense', 'Diplomacy', 'Trade'],
  'health': ['Healthcare', 'Pharmaceuticals', 'Insurance'],
  'homeland security': ['Defense', 'Cybersecurity', 'Immigration'],
  'judiciary': ['Law', 'Civil Rights', 'Immigration'],
  'appropriations': ['Federal Spending', 'Budget'],
  'intelligence': ['Defense', 'Cybersecurity', 'Intelligence'],
  'veterans': ['Veterans', 'Healthcare', 'Defense'],
  'transportation': ['Transportation', 'Infrastructure', 'Aviation'],
  'education': ['Education', 'Labor', 'Workforce'],
  'small business': ['Small Business', 'Entrepreneurship'],
  'budget': ['Budget', 'Federal Spending', 'Economics'],
  'rules': ['Congressional Procedure'],
  'indian affairs': ['Tribal Affairs', 'Land Management'],
};

function getCommitteeIndustries(committeeName: string): string[] {
  const lower = committeeName.toLowerCase();
  for (const [keyword, industries] of Object.entries(COMMITTEE_INDUSTRIES)) {
    if (lower.includes(keyword)) {
      return industries;
    }
  }
  return [];
}

export default function CommitteeList({ committees }: CommitteeListProps) {
  if (committees.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500">
        No committee memberships on record.
      </p>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {committees.map((committee) => {
        const meta = committee.metadata as Record<string, unknown>;
        const role = (meta?.role as string) || 'Member';
        const memberCount = meta?.member_count as number | undefined;
        const entity = committee.connected_entity;
        const href = entity
          ? `/entities/committee/${entity.slug}`
          : null;
        const industries = entity ? getCommitteeIndustries(entity.name) : [];

        return (
          <div
            key={committee.id}
            className="rounded-lg border border-zinc-800 bg-money-surface p-4 transition-colors hover:border-zinc-700"
          >
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-zinc-800">
                <Users className="h-5 w-5 text-zinc-400" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  {href && entity ? (
                    <Link
                      href={href}
                      className="text-sm font-semibold text-zinc-200 hover:text-money-gold"
                    >
                      {entity.name}
                    </Link>
                  ) : (
                    <span className="text-sm font-semibold text-zinc-200">
                      Unknown Committee
                    </span>
                  )}
                  {memberCount != null && memberCount > 0 && (
                    <span className="inline-flex items-center rounded-full bg-zinc-700 px-2 py-0.5 text-[10px] font-medium text-zinc-300">
                      {memberCount} members
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-xs text-zinc-500">{role}</p>
                {industries.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {industries.map((industry) => (
                      <Link
                        key={industry}
                        href={`/entities/industry/${slugify(industry)}`}
                        className="inline-flex items-center rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-400 hover:bg-zinc-700 hover:text-money-gold"
                      >
                        {industry}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
