import Link from 'next/link';
import type { Entity } from '@/lib/types';
import { getInitials, capitalize, truncate, timeAgo } from '@/lib/utils';
import PartyBadge from './PartyBadge';
import clsx from 'clsx';

interface EntityCardProps {
  entity: Entity;
}

function getEntityHref(entity: Entity): string {
  if (entity.entity_type === 'person') {
    return `/officials/${entity.slug}`;
  }
  return `/entities/${entity.entity_type}/${entity.slug}`;
}

function getEntityTypeColor(type: string): string {
  switch (type) {
    case 'person':
      return 'bg-blue-500/20 text-blue-400';
    case 'company':
      return 'bg-emerald-500/20 text-emerald-400';
    case 'bill':
      return 'bg-purple-500/20 text-purple-400';
    case 'organization':
      return 'bg-orange-500/20 text-orange-400';
    case 'pac':
      return 'bg-pink-500/20 text-pink-400';
    case 'industry':
      return 'bg-cyan-500/20 text-cyan-400';
    default:
      return 'bg-zinc-700/50 text-zinc-400';
  }
}

function getInitialsBgColor(type: string): string {
  switch (type) {
    case 'person':
      return 'bg-blue-500/20 text-blue-400';
    case 'company':
      return 'bg-emerald-500/20 text-emerald-400';
    case 'bill':
      return 'bg-purple-500/20 text-purple-400';
    default:
      return 'bg-zinc-700 text-zinc-300';
  }
}

export default function EntityCard({ entity }: EntityCardProps) {
  const metadata = entity.metadata as Record<string, unknown>;
  const party = metadata?.party as string | undefined;
  const state = metadata?.state as string | undefined;
  const chamber = metadata?.chamber as string | undefined;

  return (
    <Link
      href={getEntityHref(entity)}
      className="group block rounded-lg border border-zinc-800 bg-money-surface p-6 transition-all hover:border-zinc-700 hover:bg-money-surface-elevated"
    >
      <div className="flex items-start gap-4">
        {/* Avatar / initials */}
        <div
          className={clsx(
            'flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-sm font-bold',
            getInitialsBgColor(entity.entity_type)
          )}
          aria-hidden="true"
        >
          {getInitials(entity.name)}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-base font-semibold text-zinc-100 group-hover:text-money-gold transition-colors">
              {entity.name}
            </h3>
          </div>

          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span
              className={clsx(
                'inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium',
                getEntityTypeColor(entity.entity_type)
              )}
            >
              {capitalize(entity.entity_type)}
            </span>
            {party && <PartyBadge party={party} />}
            {state && (
              <span className="text-xs text-zinc-500">
                {state}
                {chamber ? ` \u00b7 ${chamber}` : ''}
              </span>
            )}
          </div>

          {entity.summary && (
            <p className="mt-2 text-sm leading-relaxed text-zinc-400">
              {truncate(entity.summary, 120)}
            </p>
          )}

          <div className="mt-2 flex items-center gap-2">
            {entity.entity_type === 'person' && !!metadata?.bioguide_id && !metadata?.fec_candidate_id && (
              <span className="text-[10px] text-amber-500/70">Incomplete data</span>
            )}
            {entity.updated_at && (
              <span className="text-xs text-zinc-600">
                Updated {timeAgo(entity.updated_at)}
              </span>
            )}
          </div>
        </div>
      </div>
    </Link>
  );
}
