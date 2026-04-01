'use client';

import { useState, useEffect } from 'react';
import { RefreshCw } from 'lucide-react';

interface IngestionJob {
  job_type: string;
  status: string;
  progress: number;
  total: number;
}

export default function IngestionBanner() {
  const [jobs, setJobs] = useState<IngestionJob[]>([]);

  useEffect(() => {
    let interval: NodeJS.Timeout;

    async function checkStatus() {
      try {
        const res = await fetch('/api/admin/ingest/status');
        if (!res.ok) return;
        const data = await res.json();
        const active = (data.recent_jobs || []).filter(
          (j: IngestionJob) => j.status === 'in_progress'
        );
        setJobs(active);
      } catch {
        // Silently fail — banner just won't show
      }
    }

    checkStatus();
    // Poll every 15 seconds while active
    interval = setInterval(checkStatus, 15000);

    return () => clearInterval(interval);
  }, []);

  if (jobs.length === 0) return null;

  // Summarize active jobs
  const summaries = jobs.map((j) => {
    const pct = j.total > 0 ? Math.round((j.progress / j.total) * 100) : 0;
    const label =
      j.job_type === 'batch_congress_members'
        ? 'Officials'
        : j.job_type === 'enrich_bills'
          ? 'Bills'
          : j.job_type;
    return `${label}: ${j.progress}/${j.total} (${pct}%)`;
  });

  return (
    <div className="border-b border-amber-500/20 bg-amber-500/10 px-4 py-2">
      <div className="mx-auto flex max-w-7xl items-center gap-2 text-xs text-amber-300">
        <RefreshCw className="h-3 w-3 animate-spin" />
        <span>
          Data refresh in progress. Some profiles may be incomplete.{' '}
          <span className="text-amber-400/70">{summaries.join(' · ')}</span>
        </span>
      </div>
    </div>
  );
}
