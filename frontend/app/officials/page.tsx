'use client';

import { useState, useEffect, useCallback } from 'react';
import { listEntities } from '@/lib/api';
import type { Entity } from '@/lib/types';
import EntityCard from '@/components/EntityCard';
import LoadingState from '@/components/LoadingState';
import { Users } from 'lucide-react';
import clsx from 'clsx';

const PARTY_FILTERS = ['All', 'Democrat', 'Republican', 'Independent'] as const;
const CHAMBER_FILTERS = ['All', 'Senate', 'House'] as const;

export default function OfficialsPage() {
  const [officials, setOfficials] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [partyFilter, setPartyFilter] = useState<string>('All');
  const [chamberFilter, setChamberFilter] = useState<string>('All');

  const fetchOfficials = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listEntities('person', 600);
      // Filter to only actual officials (have chamber in metadata)
      const actualOfficials = data.results.filter((e: Entity) => {
        const meta = e.metadata as Record<string, unknown>;
        return meta?.chamber;
      });
      setOfficials(actualOfficials);
    } catch {
      setError('Failed to load officials. Please try again later.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOfficials();
  }, [fetchOfficials]);

  const filtered = officials.filter((official) => {
    const meta = official.metadata as Record<string, unknown>;
    const party = (meta?.party as string) || '';
    const chamber = (meta?.chamber as string) || '';

    if (partyFilter !== 'All' && !party.toLowerCase().includes(partyFilter.toLowerCase())) {
      return false;
    }
    if (chamberFilter !== 'All' && !chamber.toLowerCase().includes(chamberFilter.toLowerCase())) {
      return false;
    }
    return true;
  });

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <Users className="h-6 w-6 text-money-gold" />
          <h1 className="text-3xl font-bold tracking-tight text-zinc-100">
            Officials
          </h1>
        </div>
        <p className="mt-2 text-sm text-zinc-500">
          Browse elected officials and explore their financial connections
        </p>
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap gap-6">
        {/* Party filter */}
        <div>
          <span className="mb-2 block text-xs font-medium uppercase tracking-wider text-zinc-500">
            Party
          </span>
          <div className="flex gap-1">
            {PARTY_FILTERS.map((party) => (
              <button
                key={party}
                onClick={() => setPartyFilter(party)}
                className={clsx(
                  'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                  partyFilter === party
                    ? 'bg-money-gold text-zinc-950'
                    : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200'
                )}
              >
                {party}
              </button>
            ))}
          </div>
        </div>

        {/* Chamber filter */}
        <div>
          <span className="mb-2 block text-xs font-medium uppercase tracking-wider text-zinc-500">
            Chamber
          </span>
          <div className="flex gap-1">
            {CHAMBER_FILTERS.map((chamber) => (
              <button
                key={chamber}
                onClick={() => setChamberFilter(chamber)}
                className={clsx(
                  'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                  chamberFilter === chamber
                    ? 'bg-money-gold text-zinc-950'
                    : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200'
                )}
              >
                {chamber}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Results count */}
      {!loading && !error && (
        <p className="mb-4 text-xs text-zinc-500">
          Showing {filtered.length} official{filtered.length !== 1 ? 's' : ''}
        </p>
      )}

      {/* Content */}
      {loading && <LoadingState variant="card" count={6} />}

      {error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-6 text-center">
          <p className="text-sm text-red-300">{error}</p>
          <button
            onClick={fetchOfficials}
            className="mt-3 rounded-md bg-zinc-800 px-4 py-2 text-xs text-zinc-300 hover:bg-zinc-700"
          >
            Try Again
          </button>
        </div>
      )}

      {!loading && !error && filtered.length === 0 && (
        <div className="rounded-lg border border-zinc-800 bg-money-surface p-12 text-center">
          <Users className="mx-auto h-8 w-8 text-zinc-600" />
          <p className="mt-3 text-sm text-zinc-500">
            No officials match your filters.
          </p>
        </div>
      )}

      {!loading && !error && filtered.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((official) => (
            <EntityCard key={official.id} entity={official} />
          ))}
        </div>
      )}
    </div>
  );
}
