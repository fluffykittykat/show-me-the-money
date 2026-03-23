import clsx from 'clsx';

interface PartyBadgeProps {
  party: string | undefined;
  className?: string;
}

export default function PartyBadge({ party, className }: PartyBadgeProps) {
  if (!party) return null;

  const lower = party.toLowerCase();
  let colorClasses = 'bg-zinc-700 text-zinc-300';
  let label = party;

  if (lower.includes('democrat')) {
    colorClasses = 'bg-money-democrat/20 text-money-democrat';
    label = 'Democrat';
  } else if (lower.includes('republican')) {
    colorClasses = 'bg-money-republican/20 text-money-republican';
    label = 'Republican';
  } else if (lower.includes('independent')) {
    colorClasses = 'bg-money-independent/20 text-money-independent';
    label = 'Independent';
  }

  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        colorClasses,
        className
      )}
    >
      {label}
    </span>
  );
}
