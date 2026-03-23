import clsx from 'clsx';

interface ConflictBadgeProps {
  severity: string;
  size?: 'sm' | 'md' | 'lg';
}

const SEVERITY_CONFIG: Record<string, { label: string; colors: string }> = {
  // New severity values
  high_concern: { label: 'High Concern', colors: 'bg-red-500/20 text-red-400 border-red-500/30' },
  notable_pattern: { label: 'Notable Pattern', colors: 'bg-orange-500/20 text-orange-400 border-orange-500/30' },
  structural_relationship: { label: 'Structural Relationship', colors: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' },
  connection_noted: { label: 'Connection Noted', colors: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
  // Backwards compat with old values
  critical: { label: 'High Concern', colors: 'bg-red-500/20 text-red-400 border-red-500/30' },
  high: { label: 'Notable Pattern', colors: 'bg-orange-500/20 text-orange-400 border-orange-500/30' },
  medium: { label: 'Structural Relationship', colors: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' },
  low: { label: 'Connection Noted', colors: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
  none: { label: 'No Concerns', colors: 'bg-zinc-700 text-zinc-400' },
};

const SIZE_STYLES: Record<string, string> = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-3 py-1 text-sm',
  lg: 'px-4 py-1.5 text-base',
};

export default function ConflictBadge({
  severity,
  size = 'md',
}: ConflictBadgeProps) {
  const normalised = severity.toLowerCase();
  const config = SEVERITY_CONFIG[normalised] ?? SEVERITY_CONFIG.connection_noted;
  const sizeClasses = SIZE_STYLES[size];

  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full border font-semibold uppercase tracking-wide',
        config.colors,
        sizeClasses
      )}
    >
      {(normalised === 'critical' || normalised === 'high_concern') && (
        <span className="mr-1" aria-hidden="true">
          !!
        </span>
      )}
      {config.label}
    </span>
  );
}
