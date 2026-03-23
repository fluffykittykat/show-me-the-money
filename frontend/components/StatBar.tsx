interface StatItem {
  label: string;
  value: string | number;
}

interface StatBarProps {
  stats: StatItem[];
}

export default function StatBar({ stats }: StatBarProps) {
  return (
    <div className="flex flex-wrap gap-6 rounded-lg border border-zinc-800 bg-money-surface px-6 py-4">
      {stats.map((stat, index) => (
        <div key={index} className="flex flex-col">
          <span className="text-xs font-medium uppercase tracking-wider text-zinc-500">
            {stat.label}
          </span>
          <span className="mt-0.5 text-lg font-bold text-zinc-100">
            {stat.value}
          </span>
        </div>
      ))}
    </div>
  );
}
