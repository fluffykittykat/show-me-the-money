'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  ChevronDown,
  ChevronUp,
  ExternalLink,
  DoorOpen,
  Users,
  Loader2,
} from 'lucide-react';
import type { RevolvingDoorItem } from '@/lib/types';
import { formatDate } from '@/lib/utils';
import DidYouKnow from '@/components/DidYouKnow';

interface RevolvingDoorSectionProps {
  items: RevolvingDoorItem[];
  loading?: boolean;
  entityName?: string;
}

function RevolvingDoorCard({ item }: { item: RevolvingDoorItem }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-4 sm:p-5 transition-colors hover:border-zinc-700">
      {/* Name */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <DoorOpen className="h-4 w-4 text-amber-500" />
        {item.lobbyist_slug ? (
          <Link
            href={`/entities/person/${item.lobbyist_slug}`}
            className="text-sm font-bold text-zinc-100 hover:text-amber-400 transition-colors uppercase tracking-wide"
          >
            {item.lobbyist_name}
          </Link>
        ) : (
          <span className="text-sm font-bold text-zinc-100 uppercase tracking-wide">
            {item.lobbyist_name}
          </span>
        )}
      </div>

      {/* THEN / NOW layout */}
      <div className="space-y-2 ml-6">
        <div className="flex items-start gap-2">
          <span className="shrink-0 rounded bg-zinc-700 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-zinc-400">
            Then
          </span>
          <p className="text-sm text-zinc-300">
            {item.former_position}
            {item.left_government && (
              <span className="ml-1 text-xs text-zinc-500">
                (left {formatDate(item.left_government)})
              </span>
            )}
          </p>
        </div>
        <div className="flex items-start gap-2">
          <span className="shrink-0 rounded bg-amber-500/20 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-400">
            Now
          </span>
          <p className="text-sm text-zinc-300">
            {item.current_role} at{' '}
            <span className="font-medium text-zinc-200 hover:text-amber-400 transition-colors">{item.current_employer}</span>
          </p>
        </div>
      </div>

      {/* Client list */}
      {item.clients.length > 0 && (
        <div className="mt-3 ml-6">
          <p className="text-xs text-zinc-400 mb-1.5">
            His clients include:
          </p>
          <div className="flex flex-wrap gap-1.5">
            {item.clients.map((client) => (
              <span
                key={client}
                className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-400"
              >
                {client}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Lobbies committee */}
      {item.lobbies_committee && (
        <div className="mt-3 ml-6 flex items-center gap-2">
          <Users className="h-3.5 w-3.5 text-zinc-500" />
          <span className="text-xs text-zinc-500">
            Lobbies:{' '}
            <span className="text-zinc-400">{item.lobbies_committee}</span>
          </span>
        </div>
      )}

      {/* Why this matters (expanded by default) */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-zinc-400 hover:text-zinc-200 transition-colors"
        aria-expanded={expanded}
      >
        {expanded ? (
          <ChevronUp className="h-3.5 w-3.5" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5" />
        )}
        Why this matters
      </button>

      {expanded && (
        <div className="mt-2 rounded-md border border-zinc-700/50 bg-zinc-800/30 px-3 py-2.5">
          <p className="text-xs leading-relaxed text-zinc-400">
            {item.why_this_matters}
          </p>
        </div>
      )}

      {/* Registration link */}
      {item.registration_url && (
        <div className="mt-2 ml-6">
          <a
            href={item.registration_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-amber-400 transition-colors"
          >
            <ExternalLink className="h-3 w-3" />
            View lobbying registration
          </a>
        </div>
      )}

      {/* Disclaimer */}
      <p className="mt-3 text-[10px] text-zinc-600 italic border-t border-zinc-800 pt-2">
        Disclaimer: Structural information from public records, not proof of wrongdoing.
      </p>
    </div>
  );
}

export default function RevolvingDoorSection({ items, loading, entityName }: RevolvingDoorSectionProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-zinc-500" />
        <span className="ml-2 text-sm text-zinc-500">Loading revolving door data...</span>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 px-6 py-8 text-center">
        <DoorOpen className="mx-auto h-8 w-8 text-zinc-600" />
        <p className="mt-3 text-sm text-zinc-500">
          No revolving door connections found{entityName ? ` for ${entityName}` : ''}.
        </p>
      </div>
    );
  }

  return (
    <div>
      {/* Section header */}
      <div className="mb-4">
        <h3 className="flex items-center gap-2 text-base font-bold text-zinc-100">
          <span className="text-lg">&#128682;</span>
          Revolving Door
        </h3>
        <p className="mt-1 text-sm text-zinc-400">
          Former government insiders who now lobby your representative&apos;s office
        </p>
      </div>

      {/* Cards */}
      <div className="space-y-3">
        {items.map((item, i) => (
          <RevolvingDoorCard key={`${item.lobbyist_slug}-${i}`} item={item} />
        ))}
      </div>

      <DidYouKnow fact="Former senior government officials must wait 1-2 years before lobbying their former agency — but can often lobby Congress immediately." />

      {/* Disclaimer */}
      <p className="mt-3 text-[10px] text-zinc-600 italic">
        Revolving door activity is legal but raises questions about access and influence. These are public records, not accusations.
      </p>
    </div>
  );
}
