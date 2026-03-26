import { Clock, Database, Users, Building2 } from 'lucide-react';

interface FreshnessBarProps {
  freshness: {
    fec_cycle: string | null;
    last_refreshed: string | null;
    has_donors: boolean;
    has_committees: boolean;
  };
  className?: string;
}

function formatRefreshDate(iso: string | null): string {
  if (!iso) return 'Never';
  try {
    const date = new Date(iso);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
    });
  } catch {
    return 'Unknown';
  }
}

export default function FreshnessBar({ freshness, className = '' }: FreshnessBarProps) {
  const refreshLabel = formatRefreshDate(freshness.last_refreshed);
  const isStale = !freshness.last_refreshed;
  const isOld = (() => {
    if (!freshness.last_refreshed) return true;
    try {
      const diff = Date.now() - new Date(freshness.last_refreshed).getTime();
      return diff > 7 * 24 * 60 * 60 * 1000; // older than 7 days
    } catch { return true; }
  })();

  return (
    <div className={`flex flex-wrap items-center gap-4 py-2 ${className}`}>
      <div className={`flex items-center gap-1.5 text-xs ${isStale ? 'text-amber-500' : isOld ? 'text-zinc-500' : 'text-emerald-500'}`}>
        <Clock className="w-3.5 h-3.5" />
        <span>Data: {refreshLabel}</span>
      </div>
      {freshness.fec_cycle && (
        <div className="flex items-center gap-1.5 text-xs text-zinc-500">
          <Database className="w-3.5 h-3.5" />
          <span>FEC {freshness.fec_cycle}</span>
        </div>
      )}
      <div className="flex items-center gap-1.5 text-xs text-zinc-500">
        <Users className="w-3.5 h-3.5" />
        <span>Donors: {freshness.has_donors ? '✓' : '—'}</span>
      </div>
      <div className="flex items-center gap-1.5 text-xs text-zinc-500">
        <Building2 className="w-3.5 h-3.5" />
        <span>Committees: {freshness.has_committees ? '✓' : '—'}</span>
      </div>
    </div>
  );
}
