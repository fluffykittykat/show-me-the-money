import Link from 'next/link';
import { formatMoney } from '@/lib/utils';
import ConflictBadge from '@/components/ConflictBadge';
import PartyBadge from '@/components/PartyBadge';
import { ArrowDown } from 'lucide-react';

interface MoneyTrailProps {
  industries: Array<{
    industry: string;
    amount: number;
    senators: string[];
  }>;
  voters: Array<{ slug: string; name: string; party: string }>;
  bill: { slug: string; name: string };
  conflictScore: string;
}

function TrailArrow({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center py-2">
      <ArrowDown className="h-5 w-5 text-money-gold/60" />
      <span className="mt-1 text-xs font-medium text-zinc-500">{label}</span>
    </div>
  );
}

function TrailCard({
  children,
  highlight,
}: {
  children: React.ReactNode;
  highlight?: boolean;
}) {
  return (
    <div
      className={
        'rounded-lg border bg-zinc-900 px-5 py-4 ' +
        (highlight
          ? 'border-money-gold/50 shadow-[0_0_12px_rgba(212,175,55,0.1)]'
          : 'border-zinc-700')
      }
    >
      {children}
    </div>
  );
}

export default function MoneyTrail({
  industries,
  voters,
  bill,
  conflictScore,
}: MoneyTrailProps) {
  const totalAmount = industries.reduce((sum, ind) => sum + ind.amount, 0);
  const topIndustries = industries.slice(0, 5);

  return (
    <div className="flex flex-col items-center">
      {/* Step 1: Industries */}
      <TrailCard>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
          Top Donor Industries
        </h4>
        <div className="flex flex-wrap gap-2">
          {topIndustries.map((ind) => (
            <span
              key={ind.industry}
              className="inline-flex items-center gap-1.5 rounded-md bg-zinc-800 px-2.5 py-1 text-sm"
            >
              <span className="text-zinc-300">{ind.industry}</span>
              <span className="font-semibold text-money-success">
                {formatMoney(ind.amount)}
              </span>
            </span>
          ))}
        </div>
      </TrailCard>

      <TrailArrow label={`${formatMoney(totalAmount)} donated`} />

      {/* Step 2: Voters */}
      <TrailCard>
        <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
          YES Voters Receiving Funds
        </h4>
        <div className="flex flex-wrap gap-2">
          {voters.slice(0, 10).map((voter) => (
            <Link
              key={voter.slug}
              href={`/officials/${voter.slug}`}
              className="inline-flex items-center gap-1.5 rounded-md bg-zinc-800 px-2.5 py-1 text-sm text-zinc-200 transition-colors hover:bg-zinc-700 hover:text-money-gold"
            >
              {voter.name}
              <PartyBadge party={voter.party} className="text-[10px]" />
            </Link>
          ))}
          {voters.length > 10 && (
            <span className="self-center text-xs text-zinc-500">
              +{voters.length - 10} more
            </span>
          )}
        </div>
      </TrailCard>

      <TrailArrow label="voted YES on" />

      {/* Step 3: Bill */}
      <TrailCard highlight>
        <Link
          href={`/bills/${bill.slug}`}
          className="text-lg font-bold text-money-gold transition-colors hover:text-money-gold-hover"
        >
          {bill.name}
        </Link>
      </TrailCard>

      {/* Conflict Score */}
      <div className="mt-4 flex items-center gap-3">
        <ConflictBadge severity={conflictScore} size="lg" />
        {conflictScore.toLowerCase() === 'critical' && (
          <span className="text-sm font-medium text-red-400">
            Full alignment detected
          </span>
        )}
      </div>
    </div>
  );
}
