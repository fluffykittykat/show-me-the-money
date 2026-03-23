'use client';

import { useState, useEffect, useCallback } from 'react';
import { listEntities } from '@/lib/api';
import type { Entity } from '@/lib/types';
import EntityCard from '@/components/EntityCard';
import LoadingState from '@/components/LoadingState';
import { FileText } from 'lucide-react';

export default function BillsPage() {
  const [bills, setBills] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchBills = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listEntities('bill', 100);
      setBills(data.results);
    } catch {
      setError('Failed to load bills. Please try again later.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBills();
  }, [fetchBills]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3">
          <FileText className="h-6 w-6 text-money-gold" />
          <h1 className="text-3xl font-bold tracking-tight text-zinc-100">
            Bills
          </h1>
        </div>
        <p className="mt-2 text-sm text-zinc-500">
          Browse legislation and investigate money trails behind the votes
        </p>
      </div>

      {/* Results count */}
      {!loading && !error && (
        <p className="mb-4 text-xs text-zinc-500">
          Showing {bills.length} bill{bills.length !== 1 ? 's' : ''}
        </p>
      )}

      {/* Content */}
      {loading && <LoadingState variant="card" count={6} />}

      {error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-6 text-center">
          <p className="text-sm text-red-300">{error}</p>
          <button
            onClick={fetchBills}
            className="mt-3 rounded-md bg-zinc-800 px-4 py-2 text-xs text-zinc-300 hover:bg-zinc-700"
          >
            Try Again
          </button>
        </div>
      )}

      {!loading && !error && bills.length === 0 && (
        <div className="rounded-lg border border-zinc-800 bg-money-surface p-12 text-center">
          <FileText className="mx-auto h-8 w-8 text-zinc-600" />
          <p className="mt-3 text-sm text-zinc-500">
            No bills found.
          </p>
        </div>
      )}

      {!loading && !error && bills.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {bills.map((bill) => (
            <EntityCard key={bill.id} entity={bill} />
          ))}
        </div>
      )}
    </div>
  );
}
