'use client';

import { BookOpen, Target, Users, Lightbulb } from 'lucide-react';
import { V2BillExplainer } from '@/lib/types';

interface BillExplainerProps {
  explainer: V2BillExplainer | null | undefined;
  className?: string;
}

export default function BillExplainer({ explainer, className = '' }: BillExplainerProps) {
  if (!explainer) return null;

  const sections = [
    { icon: Target, label: 'What it does', text: explainer.what_it_does, color: 'text-blue-400' },
    { icon: Lightbulb, label: 'Why it matters', text: explainer.why_it_matters, color: 'text-amber-400' },
    { icon: Users, label: 'Who it affects', text: explainer.who_it_affects, color: 'text-emerald-400' },
  ];

  return (
    <div className={`rounded-xl border border-blue-500/20 p-5 mb-6 ${className}`}
         style={{ background: 'linear-gradient(135deg, rgba(59,130,246,0.08), rgba(59,130,246,0.02))' }}>
      <div className="flex items-center gap-2 mb-4 text-blue-400 font-semibold text-sm uppercase tracking-wide">
        <BookOpen className="w-4 h-4" />
        Bill Explainer
      </div>
      <div className="space-y-3">
        {sections.map(({ icon: Icon, label, text, color }) => (
          <div key={label} className="flex gap-3">
            <Icon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${color}`} />
            <div>
              <span className={`text-xs font-semibold uppercase tracking-wide ${color}`}>{label}</span>
              <p className="text-zinc-300 text-[0.95rem] leading-relaxed mt-0.5">{text}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
