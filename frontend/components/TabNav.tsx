'use client';

import clsx from 'clsx';

interface Tab {
  id: string;
  label: string;
  count?: number;
}

interface TabNavProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
}

export default function TabNav({ tabs, activeTab, onTabChange }: TabNavProps) {
  return (
    <div
      className="sticky top-0 z-10 bg-zinc-950/95 backdrop-blur-sm border-b border-zinc-800"
      role="tablist"
      aria-label="Content sections"
    >
      <div className="flex gap-1 overflow-x-auto scrollbar-thin scrollbar-thumb-zinc-700">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`tabpanel-${tab.id}`}
            onClick={() => onTabChange(tab.id)}
            className={clsx(
              'whitespace-nowrap border-b-2 px-4 py-3 text-sm font-medium transition-colors',
              activeTab === tab.id
                ? 'border-amber-500 text-amber-500'
                : 'border-transparent text-zinc-500 hover:border-zinc-600 hover:text-zinc-300'
            )}
          >
            {tab.label}
            {tab.count != null && (
              <span
                className={clsx(
                  'ml-2 rounded-full px-1.5 py-0.5 text-xs',
                  activeTab === tab.id
                    ? 'bg-amber-500/20 text-amber-500'
                    : 'bg-zinc-800 text-zinc-500'
                )}
              >
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
