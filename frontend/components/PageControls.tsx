'use client';

import { useState } from 'react';
import { RefreshCw, Zap, Loader2, Check, AlertCircle, Shield } from 'lucide-react';
import { getBriefing } from '@/lib/api';

type StepStatus = 'pending' | 'running' | 'done' | 'error';

interface Step {
  label: string;
  detail?: string;
  status: StepStatus;
}

interface PageControlsProps {
  slug: string;
  entityName?: string;
  onBriefingUpdate?: (text: string) => void;
  onDataRefresh?: () => void;
  className?: string;
}

export default function PageControls({ slug, entityName, onBriefingUpdate, onDataRefresh, className = '' }: PageControlsProps) {
  const [briefingLoading, setBriefingLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [steps, setSteps] = useState<Step[]>([]);
  const [showPanel, setShowPanel] = useState(false);
  const [completed, setCompleted] = useState(false);

  function updateStep(index: number, updates: Partial<Step>) {
    setSteps(prev => {
      const next = [...prev];
      next[index] = { ...next[index], ...updates };
      return next;
    });
  }

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
    setShowPanel(true);
    setCompleted(false);

    const initialSteps: Step[] = [
      { label: 'Resolving FEC Committee ID', detail: 'Looking up official campaign committee...', status: 'running' },
      { label: 'Fetching ALL campaign cycles', detail: '2026, 2024, 2022, 2020, 2018...', status: 'pending' },
      { label: 'Fetching top donors', detail: '2024 + 2022 cycle donors from FEC...', status: 'pending' },
      { label: 'Tracing middleman PACs', detail: 'Who funds the PACs that fund this official...', status: 'pending' },
      { label: 'Computing money trails', detail: 'Connecting dots: donors → committees → bills...', status: 'pending' },
      { label: 'Running verdict algorithm', detail: 'NORMAL / CONNECTED / INFLUENCED / OWNED...', status: 'pending' },
      { label: 'Generating AI assessment', detail: 'Claude Sonnet analyzing patterns...', status: 'pending' },
      { label: 'Finalizing dossier', status: 'pending' },
    ];
    setSteps(initialSteps);

    try {
      // Animate through steps while the single API call runs in background
      // The backend processes in a known order, so we simulate step progression
      updateStep(0, { status: 'running', detail: 'Connecting to FEC...' });

      // Start the API call (non-blocking)
      const refreshPromise = fetch(`/api/refresh/${encodeURIComponent(slug)}`, { method: 'POST' });

      // Simulate step progression while waiting (backend takes 2-3 minutes)
      const stepTimings = [
        { idx: 0, delay: 2000, detail: 'Querying FEC API...' },
        { idx: 0, delay: 5000, status: 'done' as const, detail: 'FEC Committee ID confirmed' },
        { idx: 1, delay: 6000, status: 'running' as const, detail: 'Checking 2026, 2024, 2022, 2020, 2018...' },
        { idx: 1, delay: 15000, status: 'done' as const, detail: 'All cycles fetched' },
        { idx: 2, delay: 16000, status: 'running' as const, detail: 'Fetching PAC + committee donors from FEC...' },
        { idx: 2, delay: 40000, status: 'done' as const, detail: 'Donors retrieved' },
        { idx: 3, delay: 41000, status: 'running' as const, detail: 'Tracing middleman PAC chains...' },
        { idx: 3, delay: 55000, status: 'done' as const, detail: 'PAC chains traced' },
        { idx: 4, delay: 56000, status: 'running' as const, detail: 'Connecting donors → committees → bills...' },
        { idx: 4, delay: 80000, status: 'done' as const, detail: 'Money trails computed' },
        { idx: 5, delay: 81000, status: 'running' as const, detail: 'Counting dots across all industries...' },
        { idx: 5, delay: 95000, status: 'done' as const, detail: 'Verdict computed' },
        { idx: 6, delay: 96000, status: 'running' as const, detail: 'Claude Sonnet analyzing all evidence...' },
      ];

      const timers: ReturnType<typeof setTimeout>[] = [];
      for (const step of stepTimings) {
        timers.push(setTimeout(() => {
          updateStep(step.idx, { status: step.status || 'running', detail: step.detail });
        }, step.delay));
      }

      // Wait for the actual API response
      const refreshRes = await refreshPromise;

      // Clear timers — real results are in
      timers.forEach(t => clearTimeout(t));

      if (!refreshRes.ok) {
        const errorText = await refreshRes.text().catch(() => 'Unknown error');
        throw new Error(`Refresh failed (${refreshRes.status}): ${errorText}`);
      }
      const refreshData = await refreshRes.json();
      const actions: string[] = refreshData.actions || [];

      // Now update ALL steps with real results from the API
      const findAction = (keyword: string) => actions.find(a => a.toLowerCase().includes(keyword.toLowerCase())) || '';

      updateStep(0, { status: 'done', detail: findAction('committee') || findAction('resolved') || 'Committee ID confirmed' });
      updateStep(1, { status: 'done', detail: findAction('FEC cycles') || findAction('totals') || 'Cycle data fetched' });
      updateStep(2, { status: 'done', detail: findAction('donors') || 'Donor data current' });

      const pacActions = actions.filter(a => a.includes('donors for PAC'));
      updateStep(3, { status: 'done', detail: pacActions.length > 0 ? `${pacActions.length} PAC chains traced` : 'No PAC middlemen found' });

      updateStep(4, { status: 'done', detail: findAction('money trails') || findAction('trail') || 'Money trails computed' });
      updateStep(5, { status: 'done', detail: findAction('verdict') || 'Verdict assigned' });

      const briefingAction = findAction('briefing');
      if (briefingAction.includes('generated')) {
        updateStep(6, { status: 'done', detail: briefingAction });
      } else {
        try {
        const briefRes = await getBriefing(slug, true);
        onBriefingUpdate?.(briefRes.briefing_text);
        const charCount = briefRes.briefing_text?.length || 0;
        updateStep(3, { status: 'done', detail: `${charCount} character assessment generated` });
      } catch {
        updateStep(6, { status: 'done', detail: 'Briefing unchanged (generation unavailable)' });
      }
      }
      updateStep(7, { status: 'running' });

      // Step 8: Finalize — reload page data
      await new Promise(r => setTimeout(r, 500));
      onDataRefresh?.();
      updateStep(7, { status: 'done', detail: 'Investigation complete — all data refreshed' });

      setCompleted(true);
      setRefreshing(false);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      // Mark the currently running step as error
      setSteps(prev => {
        const next = [...prev];
        const running = next.find(s => s.status === 'running');
        if (running) {
          running.status = 'error';
          running.detail = msg;
        }
        return next;
      });
      setRefreshing(false);
    }
  }

  const StatusIcon = ({ status }: { status: StepStatus }) => {
    switch (status) {
      case 'running': return <Loader2 className="w-4 h-4 text-amber-400 animate-spin flex-shrink-0" />;
      case 'done': return <Check className="w-4 h-4 text-emerald-400 flex-shrink-0" />;
      case 'error': return <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0" />;
      default: return <div className="w-4 h-4 rounded-full border border-zinc-700 flex-shrink-0" />;
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
          {briefingLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
          {briefingLoading ? 'Generating...' : 'Regenerate Briefing'}
        </button>
        <button
          data-refresh-investigation
          onClick={handleRefresh}
          disabled={refreshing || briefingLoading}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-zinc-700 text-zinc-300 text-sm font-medium hover:border-amber-500/50 hover:text-amber-400 disabled:opacity-50 transition-all duration-200"
        >
          {refreshing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Shield className="w-4 h-4" />}
          {refreshing ? 'Investigation in progress...' : 'Run Full Investigation'}
        </button>
      </div>

      {/* Investigation panel */}
      {showPanel && steps.length > 0 && (
        <div className="mt-4 bg-zinc-950 border border-zinc-800 rounded-xl overflow-hidden">
          {/* Header */}
          <div className="px-4 py-3 border-b border-zinc-800 flex items-center gap-2">
            <Shield className="w-4 h-4 text-amber-500" />
            <span className="text-xs font-bold uppercase tracking-widest text-amber-500">
              Investigation Dossier
            </span>
            {entityName && (
              <span className="text-xs text-zinc-500 ml-2">— {entityName}</span>
            )}
            {completed && !refreshing && (
              <button
                onClick={() => setShowPanel(false)}
                className="ml-auto text-xs text-zinc-600 hover:text-zinc-400 transition-colors"
              >
                Dismiss
              </button>
            )}
          </div>

          {/* Steps */}
          <div className="p-4 space-y-3">
            {steps.map((step, i) => (
              <div key={i} className="flex items-start gap-3">
                <div className="mt-0.5">
                  <StatusIcon status={step.status} />
                </div>
                <div className="min-w-0">
                  <div className={`text-sm font-medium ${
                    step.status === 'done' ? 'text-zinc-400' :
                    step.status === 'running' ? 'text-zinc-100' :
                    step.status === 'error' ? 'text-red-400' :
                    'text-zinc-600'
                  }`}>
                    {step.label}
                  </div>
                  {step.detail && (
                    <div className={`text-xs mt-0.5 ${
                      step.status === 'error' ? 'text-red-400/70' : 'text-zinc-600'
                    }`}>
                      {step.detail}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Completion bar */}
          {completed && (
            <div className="px-4 py-2.5 border-t border-zinc-800 bg-emerald-950/20">
              <span className="text-xs text-emerald-400 font-medium">
                ✓ Investigation complete — all data refreshed
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
