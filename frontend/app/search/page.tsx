'use client';

import { useState, useEffect, useCallback, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import SearchBar from '@/components/SearchBar';
import EntityCard from '@/components/EntityCard';
import LoadingState from '@/components/LoadingState';
import { searchEntities } from '@/lib/api';
import type { Entity } from '@/lib/types';
import { Search, Users, Building2, ScrollText, Landmark, Coins } from 'lucide-react';
import clsx from 'clsx';

const TYPE_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'person', label: 'People' },
  { id: 'company', label: 'Companies' },
  { id: 'bill', label: 'Bills' },
  { id: 'organization', label: 'Organizations' },
  { id: 'pac', label: 'PACs' },
] as const;

function SearchContent() {
  const searchParams = useSearchParams();
  const queryParam = searchParams.get('q') || '';

  const [results, setResults] = useState<Entity[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [hasSearched, setHasSearched] = useState(false);

  const doSearch = useCallback(async (q: string, type: string) => {
    if (!q.trim()) {
      setResults([]);
      setTotal(0);
      setHasSearched(false);
      return;
    }

    setLoading(true);
    setError(null);
    setHasSearched(true);

    try {
      const data = await searchEntities(q, type === 'all' ? undefined : type);
      setResults(data.results);
      setTotal(data.total);
    } catch {
      setError('Search failed. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    doSearch(queryParam, typeFilter);
  }, [queryParam, typeFilter, doSearch]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Search input */}
      <div className="mb-8">
        <h1 className="mb-4 text-2xl font-bold tracking-tight text-zinc-100">
          Search
        </h1>
        <SearchBar initialQuery={queryParam} size="large" />
      </div>

      {/* Type filters with count badges */}
      <div className="mb-6 flex flex-wrap gap-1">
        {TYPE_FILTERS.map((filter) => {
          const count = filter.id === 'all'
            ? results.length
            : results.filter((r) => r.entity_type === filter.id).length;
          return (
            <button
              key={filter.id}
              onClick={() => setTypeFilter(filter.id)}
              className={clsx(
                'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                typeFilter === filter.id
                  ? 'bg-money-gold text-zinc-950'
                  : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200'
              )}
            >
              {filter.label}
              {hasSearched && count > 0 && (
                <span
                  className={clsx(
                    'rounded-full px-1.5 py-0.5 text-[10px] font-bold',
                    typeFilter === filter.id
                      ? 'bg-zinc-950/20 text-zinc-950'
                      : 'bg-zinc-700 text-zinc-300'
                  )}
                >
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Results */}
      {loading && <LoadingState variant="card" count={6} />}

      {error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-6 text-center">
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}

      {!loading && !error && hasSearched && results.length === 0 && (
        <div className="rounded-lg border border-zinc-800 bg-money-surface p-12 text-center">
          <Search className="mx-auto h-8 w-8 text-zinc-600" />
          <p className="mt-3 text-sm text-zinc-400">
            No results found for &ldquo;{queryParam}&rdquo;
          </p>
          <p className="mt-1 text-xs text-zinc-600">
            Try adjusting your search terms or filters
          </p>
        </div>
      )}

      {!loading && !error && !hasSearched && (
        <div className="rounded-lg border border-zinc-800 bg-money-surface p-12 text-center">
          <Search className="mx-auto h-8 w-8 text-zinc-600" />
          <p className="mt-3 text-sm text-zinc-400">
            Enter a search term to find officials, companies, bills, and more
          </p>
        </div>
      )}

      {!loading && !error && results.length > 0 && (
        <>
          <p className="mb-4 text-xs text-zinc-500">
            {total} result{total !== 1 ? 's' : ''} for &ldquo;{queryParam}&rdquo;
          </p>

          {/* Grouped results when showing all types */}
          {typeFilter === 'all' ? (
            <div className="space-y-8">
              {(() => {
                const grouped: Record<string, Entity[]> = {};
                for (const entity of results) {
                  const t = entity.entity_type;
                  if (!grouped[t]) grouped[t] = [];
                  grouped[t].push(entity);
                }

                const sectionConfig: Record<string, { label: string; icon: React.ReactNode }> = {
                  person: { label: 'Officials', icon: <Users className="h-4 w-4 text-amber-400" /> },
                  company: { label: 'Companies', icon: <Building2 className="h-4 w-4 text-amber-400" /> },
                  bill: { label: 'Bills', icon: <ScrollText className="h-4 w-4 text-amber-400" /> },
                  organization: { label: 'Organizations', icon: <Landmark className="h-4 w-4 text-amber-400" /> },
                  pac: { label: 'PACs', icon: <Coins className="h-4 w-4 text-amber-400" /> },
                };

                const order = ['person', 'company', 'bill', 'organization', 'pac', 'industry'];

                return order
                  .filter((type) => grouped[type] && grouped[type].length > 0)
                  .map((type) => {
                    const config = sectionConfig[type] || { label: type, icon: null };
                    const entities = grouped[type];
                    // For company results, add a subheading about connected officials
                    const isCompany = type === 'company';

                    return (
                      <div key={type}>
                        <div className="mb-3 flex items-center gap-2">
                          {config.icon}
                          <h2 className="text-sm font-bold uppercase tracking-wider text-zinc-400">
                            {config.label}
                          </h2>
                          <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] font-medium text-zinc-400">
                            {entities.length}
                          </span>
                        </div>
                        {isCompany && queryParam && (
                          <p className="mb-3 text-xs text-zinc-500">
                            Officials connected to these companies may share financial interests
                          </p>
                        )}
                        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                          {entities.map((entity) => (
                            <EntityCard key={entity.id} entity={entity} />
                          ))}
                        </div>
                      </div>
                    );
                  });
              })()}
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {results
                .filter((entity) => entity.entity_type === typeFilter)
                .map((entity) => (
                  <EntityCard key={entity.id} entity={entity} />
                ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function SearchPage() {
  return (
    <Suspense
      fallback={
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          <LoadingState variant="card" count={6} />
        </div>
      }
    >
      <SearchContent />
    </Suspense>
  );
}
