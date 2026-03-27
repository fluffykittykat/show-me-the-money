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
      // All steps happen in one API call — we simulate progress from the response
      updateStep(0, { status: 'running' });

      const refreshRes = await fetch(`/api/refresh/${encodeURIComponent(slug)}`, { method: 'POST' });
      if (!refreshRes.ok) {
        const errorText = await refreshRes.text().catch(() => 'Unknown error');
        throw new Error(`Refresh failed (${refreshRes.status}): ${errorText}`);
      }
      const refreshData = await refreshRes.json();
      const actions: string[] = refreshData.actions || [];

      // Parse actions to update steps with real results
      const findAction = (keyword: string) => actions.find(a => a.toLowerCase().includes(keyword.toLowerCase())) || '';

      // Step 1: Committee ID
      const committeeAction = findAction('committee') || findAction('resolved');
      updateStep(0, { status: 'done', detail: committeeAction || 'Committee ID confirmed' });

      // Step 2: Cycle totals
      updateStep(1, { status: 'done', detail: findAction('FEC cycles') || findAction('totals') || 'Cycle data fetched' });

      // Step 3: Donors
      const donorAction = findAction('donors');
      updateStep(2, { status: 'done', detail: donorAction || 'Donor data current' });

      // Step 4: PAC middlemen
      const pacActions = actions.filter(a => a.includes('donors for PAC'));
      updateStep(3, { status: 'done', detail: pacActions.length > 0 ? `${pacActions.length} PAC chains traced` : 'No PAC middlemen found' });

      // Step 5: Money trails
      const trailAction = findAction('money trails') || findAction('trail');
      updateStep(4, { status: 'done', detail: trailAction || 'Money trails computed' });

      // Step 6: Verdict
      const verdictAction = findAction('verdict');
      updateStep(5, { status: 'done', detail: verdictAction || 'Verdict assigned' });

      // Step 7: AI briefing
      updateStep(6, { status: 'running' });
      const briefingAction = findAction('briefing');
      if (briefingAction.includes('generated')) {
        updateStep(6, { status: 'done', detail: briefingAction });
      } else {
        // Briefing may have been generated as part of refresh — fetch it
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
