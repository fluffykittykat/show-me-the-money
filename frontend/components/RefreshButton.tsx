'use client';

import { useState } from 'react';
import { RefreshCw } from 'lucide-react';

interface RefreshButtonProps {
  slug: string;
  onComplete?: () => void;
}

export default function RefreshButton({ slug, onComplete }: RefreshButtonProps) {
  const [refreshing, setRefreshing] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  const handleRefresh = async () => {
    setRefreshing(true);
    setResult(null);
    try {
      const res = await fetch(`/api/refresh/${encodeURIComponent(slug)}`, { method: 'POST' });
      if (!res.ok) throw new Error('Refresh failed');
      const data = await res.json();
      const actions = data.actions || [];
      setResult(`Updated: ${actions.join(', ')}`);
      // Reload the page after a brief delay to show the result
      setTimeout(() => {
        if (onComplete) {
          onComplete();
        } else {
          window.location.reload();
        }
      }, 1500);
    } catch {
      setResult('Refresh failed. Try again.');
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="inline-flex items-center gap-2">
      <button
        onClick={handleRefresh}
        disabled={refreshing}
        className="inline-flex items-center gap-1.5 rounded-md border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:border-money-gold hover:text-money-gold disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
        {refreshing ? 'Refreshing...' : 'Refresh Investigation'}
      </button>
      {result && (
        <span className="text-xs text-zinc-500">{result}</span>
      )}
    </div>
  );
}
