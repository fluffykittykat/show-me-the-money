import Link from 'next/link';
import PartyBadge from '@/components/PartyBadge';
import { ThumbsUp, ThumbsDown } from 'lucide-react';

interface Voter {
  slug: string;
  name: string;
  party: string;
  top_donor_industries: string[];
}

interface BillVoteBreakdownProps {
  yesVoters: Voter[];
  noVoters: Voter[];
}

function VoterCard({ voter }: { voter: Voter }) {
  return (
    <div className="flex items-start justify-between gap-2 rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2.5">
      <div className="min-w-0 flex-1">
        <Link
          href={`/officials/${voter.slug}`}
          className="text-sm font-medium text-zinc-200 transition-colors hover:text-money-gold"
        >
          {voter.name}
        </Link>
        <div className="mt-1 flex items-center gap-1.5">
          <PartyBadge party={voter.party} className="text-[10px]" />
        </div>
        {voter.top_donor_industries.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {voter.top_donor_industries.slice(0, 3).map((industry) => (
              <span
                key={industry}
                className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-500"
              >
                {industry}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function BillVoteBreakdown({
  yesVoters,
  noVoters,
}: BillVoteBreakdownProps) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      {/* YES column */}
      <div>
        <div className="mb-3 flex items-center gap-2 rounded-t-md bg-emerald-500/10 px-4 py-2">
          <ThumbsUp className="h-4 w-4 text-emerald-400" />
          <h3 className="text-sm font-bold uppercase tracking-wider text-emerald-400">
            Yes Votes
          </h3>
          <span className="ml-auto text-sm font-semibold text-emerald-400">
            {yesVoters.length}
          </span>
        </div>
        <div className="space-y-2">
          {yesVoters.length === 0 && (
            <p className="px-4 py-6 text-center text-sm text-zinc-600">
              No YES votes recorded
            </p>
          )}
          {yesVoters.map((voter) => (
            <VoterCard key={voter.slug} voter={voter} />
          ))}
        </div>
      </div>

      {/* NO column */}
      <div>
        <div className="mb-3 flex items-center gap-2 rounded-t-md bg-red-500/10 px-4 py-2">
          <ThumbsDown className="h-4 w-4 text-red-400" />
          <h3 className="text-sm font-bold uppercase tracking-wider text-red-400">
            No Votes
          </h3>
          <span className="ml-auto text-sm font-semibold text-red-400">
            {noVoters.length}
          </span>
        </div>
        <div className="space-y-2">
          {noVoters.length === 0 && (
            <p className="px-4 py-6 text-center text-sm text-zinc-600">
              No NO votes recorded
            </p>
          )}
          {noVoters.map((voter) => (
            <VoterCard key={voter.slug} voter={voter} />
          ))}
        </div>
      </div>
    </div>
  );
}
