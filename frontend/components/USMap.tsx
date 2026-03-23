'use client';

import { useState } from 'react';
import Link from 'next/link';

// State abbreviation -> full name mapping
const STATE_NAMES: Record<string, string> = {
  AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas', CA: 'California',
  CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware', FL: 'Florida', GA: 'Georgia',
  HI: 'Hawaii', ID: 'Idaho', IL: 'Illinois', IN: 'Indiana', IA: 'Iowa',
  KS: 'Kansas', KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine', MD: 'Maryland',
  MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi', MO: 'Missouri',
  MT: 'Montana', NE: 'Nebraska', NV: 'Nevada', NH: 'New Hampshire', NJ: 'New Jersey',
  NM: 'New Mexico', NY: 'New York', NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio',
  OK: 'Oklahoma', OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina',
  SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah', VT: 'Vermont',
  VA: 'Virginia', WA: 'Washington', WV: 'West Virginia', WI: 'Wisconsin', WY: 'Wyoming',
};

const FULL_TO_ABBREV: Record<string, string> = Object.fromEntries(
  Object.entries(STATE_NAMES).map(([k, v]) => [v, k])
);

interface StateData {
  state: string;
  abbreviation: string;
  senators: Array<{
    name: string;
    slug: string;
    party: string;
  }>;
  dominantParty: 'Democratic' | 'Republican' | 'Split' | 'Independent';
}

interface USMapProps {
  stateData: StateData[];
}

function getPartyColor(party: string): string {
  switch (party) {
    case 'Democratic': return '#3b82f6'; // blue-500
    case 'Republican': return '#ef4444'; // red-500
    case 'Split': return '#a855f7'; // purple-500
    case 'Independent': return '#22c55e'; // green-500
    default: return '#71717a'; // zinc-500
  }
}

function getPartyBgClass(party: string): string {
  switch (party) {
    case 'Democratic': return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
    case 'Republican': return 'bg-red-500/20 text-red-400 border-red-500/30';
    case 'Split': return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
    case 'Independent': return 'bg-green-500/20 text-green-400 border-green-500/30';
    default: return 'bg-zinc-700 text-zinc-400 border-zinc-600';
  }
}

// Simple US state grid layout (not geographic but readable)
// Each cell is [row, col, abbreviation]
const STATE_GRID: [number, number, string][] = [
  // Row 0
  [0, 0, 'AK'], [0, 10, 'ME'],
  // Row 1
  [1, 1, 'WA'], [1, 2, 'MT'], [1, 3, 'ND'], [1, 4, 'MN'], [1, 6, 'WI'], [1, 7, 'MI'], [1, 9, 'NY'], [1, 10, 'VT'], [1, 11, 'NH'],
  // Row 2
  [2, 1, 'OR'], [2, 2, 'ID'], [2, 3, 'SD'], [2, 4, 'IA'], [2, 5, 'IL'], [2, 6, 'IN'], [2, 7, 'OH'], [2, 8, 'PA'], [2, 9, 'NJ'], [2, 10, 'CT'], [2, 11, 'MA'],
  // Row 3
  [3, 0, 'HI'], [3, 1, 'CA'], [3, 2, 'NV'], [3, 3, 'NE'], [3, 4, 'MO'], [3, 5, 'KY'], [3, 6, 'WV'], [3, 7, 'VA'], [3, 8, 'MD'], [3, 9, 'DE'], [3, 10, 'RI'],
  // Row 4
  [4, 1, 'AZ'], [4, 2, 'UT'], [4, 3, 'KS'], [4, 4, 'AR'], [4, 5, 'TN'], [4, 6, 'NC'], [4, 7, 'SC'],
  // Row 5
  [5, 1, 'NM'], [5, 2, 'CO'], [5, 3, 'OK'], [5, 4, 'LA'], [5, 5, 'MS'], [5, 6, 'AL'], [5, 7, 'GA'],
  // Row 6
  [6, 2, 'WY'], [6, 3, 'TX'], [6, 7, 'FL'],
];

export default function USMap({ stateData }: USMapProps) {
  const [hoveredState, setHoveredState] = useState<string | null>(null);

  // Build lookup from abbreviation
  const stateMap = new Map<string, StateData>();
  for (const sd of stateData) {
    const abbrev = FULL_TO_ABBREV[sd.state] || sd.abbreviation;
    if (abbrev) stateMap.set(abbrev, sd);
  }

  const hoveredData = hoveredState ? stateMap.get(hoveredState) : null;

  return (
    <div>
      {/* Legend */}
      <div className="mb-4 flex flex-wrap items-center justify-center gap-4 text-xs">
        <div className="flex items-center gap-1.5">
          <div className="h-3 w-3 rounded-sm bg-blue-500" />
          <span className="text-zinc-400">Democratic</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-3 w-3 rounded-sm bg-red-500" />
          <span className="text-zinc-400">Republican</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-3 w-3 rounded-sm bg-purple-500" />
          <span className="text-zinc-400">Split</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="h-3 w-3 rounded-sm bg-green-500" />
          <span className="text-zinc-400">Independent</span>
        </div>
      </div>

      {/* Grid map */}
      <div className="mx-auto" style={{ maxWidth: '600px' }}>
        <div
          className="grid gap-1"
          style={{
            gridTemplateColumns: 'repeat(12, 1fr)',
            gridTemplateRows: 'repeat(7, 1fr)',
          }}
        >
          {STATE_GRID.map(([row, col, abbrev]) => {
            const data = stateMap.get(abbrev);
            const color = data ? getPartyColor(data.dominantParty) : '#3f3f46';
            const isHovered = hoveredState === abbrev;

            return (
              <Link
                key={abbrev}
                href={`/officials?state=${encodeURIComponent(STATE_NAMES[abbrev] || abbrev)}`}
                className="relative flex items-center justify-center rounded-md border text-[10px] font-bold transition-all sm:text-xs"
                style={{
                  gridRow: row + 1,
                  gridColumn: col + 1,
                  backgroundColor: `${color}${isHovered ? '50' : '25'}`,
                  borderColor: `${color}${isHovered ? '80' : '40'}`,
                  aspectRatio: '1',
                }}
                onMouseEnter={() => setHoveredState(abbrev)}
                onMouseLeave={() => setHoveredState(null)}
              >
                <span style={{ color }}>{abbrev}</span>
              </Link>
            );
          })}
        </div>
      </div>

      {/* Hover tooltip */}
      <div className="mt-4 flex items-center justify-center">
        {hoveredData ? (
          <div className="rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 text-center">
            <p className="text-sm font-bold text-zinc-200">{hoveredData.state}</p>
            <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
              {hoveredData.senators.map((s) => (
                <Link
                  key={s.slug}
                  href={`/officials/${s.slug}`}
                  className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium hover:opacity-80"
                  style={{
                    borderColor: s.party === 'Democratic' ? '#3b82f680' : s.party === 'Republican' ? '#ef444480' : '#22c55e80',
                    color: s.party === 'Democratic' ? '#60a5fa' : s.party === 'Republican' ? '#f87171' : '#4ade80',
                    backgroundColor: s.party === 'Democratic' ? '#3b82f610' : s.party === 'Republican' ? '#ef444410' : '#22c55e10',
                  }}
                >
                  {s.name}
                </Link>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-xs text-zinc-600">Hover over a state to see its senators</p>
        )}
      </div>
    </div>
  );
}

export { STATE_NAMES, FULL_TO_ABBREV };
export type { StateData };
