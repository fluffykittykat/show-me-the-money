interface FreshnessBarProps {
  freshness: {
    fec_cycle: string | null;
    last_refreshed: string | null;
    has_donors: boolean;
    has_committees: boolean;
  };
  className?: string;
}

export default function FreshnessBar({ freshness, className = '' }: FreshnessBarProps) {
  const items = [
    freshness.fec_cycle && `FEC: ${freshness.fec_cycle} cycle`,
    freshness.last_refreshed && `Last refreshed: ${freshness.last_refreshed}`,
    `Donors: ${freshness.has_donors ? '✓' : '—'}`,
    `Committees: ${freshness.has_committees ? '✓' : '—'}`,
  ].filter(Boolean);

  return (
    <div className={`flex flex-wrap gap-4 mt-2 ${className}`}>
      {items.map((item, i) => (
        <span key={i} className="text-xs text-zinc-500">{item}</span>
      ))}
    </div>
  );
}
