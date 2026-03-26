'use client';

import { useState } from 'react';
import { RefreshCw, Zap, Loader2, Check, AlertCircle } from 'lucide-react';
import { getBriefing } from '@/lib/api';

type StepStatus = 'pending' | 'running' | 'done' | 'error';

interface Step {
  label: string;
  status: StepStatus;
}

interface PageControlsProps {
  slug: string;
  onBriefingUpdate?: (text: string) => void;
  onDataRefresh?: () => void;
  className?: string;
}

async function refreshEntityData(slug: string, onStep: (steps: Step[]) => void): Promise<boolean> {
  const steps: Step[] = [
    { label: 'Refreshing entity data from live APIs', status: 'running' },
    { label: 'Re-computing money trails & verdicts', status: 'pending' },
    { label: 'Updating cached data', status: 'pending' },
  ];
  onStep([...steps]);

  try {
    // Step 1: Call refresh endpoint
    const res = await fetch(`/api/refresh/${encodeURIComponent(slug)}`, { method: 'POST' });
    if (!res.ok) throw new Error('Refresh failed');
    steps[0].status = 'done';
    steps[1].status = 'running';
    onStep([...steps]);

    // Step 2: Trigger precompute for this official
    await fetch(`/api/admin/ingest/precompute`, { method: 'POST' });
    // Wait a bit for precompute to process this official
    await new Promise(r => setTimeout(r, 5000));
    steps[1].status = 'done';
    steps[2].status = 'running';
    onStep([...steps]);

    // Step 3: Done
    await new Promise(r => setTimeout(r, 1000));
    steps[2].status = 'done';
    onStep([...steps]);
    return true;
  } catch {
    const running = steps.find(s => s.status === 'running');
    if (running) running.status = 'error';
    onStep([...steps]);
    return false;
  }
}

export default function PageControls({ slug, onBriefingUpdate, onDataRefresh, className = '' }: PageControlsProps) {
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [showSteps, setShowSteps] = useState(false);

  async function handleRegenBriefing() {
    setBriefingLoading(true);
    try {
      const res = await getBriefing(slug, true);
      onBriefingUpdate?.(res.briefing_text);
    } catch {
      // silent
    } finally {
      setBriefingLoading(false);
    }
  }

  async function handleRefresh() {
    setRefreshing(true);
    setShowSteps(true);
    const ok = await refreshEntityData(slug, setSteps);
    if (ok) {
      // Wait a moment then reload page data
      setTimeout(() => {
        onDataRefresh?.();
        setRefreshing(false);
        // Hide steps after 3s
        setTimeout(() => setShowSteps(false), 3000);
      }, 500);
    } else {
      setRefreshing(false);
    }
  }

  const StatusIcon = ({ status }: { status: StepStatus }) => {
    switch (status) {
      case 'running': return <Loader2 className="w-3.5 h-3.5 text-amber-400 animate-spin" />;
      case 'done': return <Check className="w-3.5 h-3.5 text-emerald-400" />;
      case 'error': return <AlertCircle className="w-3.5 h-3.5 text-red-400" />;
      default: return <div className="w-3.5 h-3.5 rounded-full border border-zinc-600" />;
    }
  };

  return (
    <div className={`mb-6 ${className}`}>
      <div className="flex gap-3 flex-wrap">
        <button
          onClick={handleRegenBriefing}
          disabled={briefingLoading || refreshing}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-amber-500/30 text-amber-400 text-sm font-medium hover:bg-amber-500/10 disabled:opacity-50 transition-all duration-200"
        >
          {briefingLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Zap className="w-4 h-4" />
          )}
          {briefingLoading ? 'Generating...' : 'Regenerate Briefing'}
        </button>
        <button
          onClick={handleRefresh}
          disabled={refreshing || briefingLoading}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-zinc-700 text-zinc-300 text-sm font-medium hover:border-amber-500/50 hover:text-amber-400 disabled:opacity-50 transition-all duration-200"
        >
          {refreshing ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          {refreshing ? 'Refreshing...' : 'Refresh Data'}
        </button>
      </div>

      {/* Progress steps */}
      {showSteps && steps.length > 0 && (
        <div className="mt-4 bg-zinc-900 border border-zinc-800 rounded-lg p-4">
          <div className="space-y-2.5">
            {steps.map((step, i) => (
              <div key={i} className="flex items-center gap-3">
                <StatusIcon status={step.status} />
                <span className={`text-sm ${
                  step.status === 'done' ? 'text-zinc-400' :
                  step.status === 'running' ? 'text-zinc-200' :
                  step.status === 'error' ? 'text-red-400' :
                  'text-zinc-600'
                }`}>
                  {step.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
