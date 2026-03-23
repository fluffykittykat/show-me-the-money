'use client';

import Link from 'next/link';
import type { Relationship } from '@/lib/types';
import { AlertCircle, DollarSign, Building2, Scale } from 'lucide-react';
import MoneyAmount from './MoneyAmount';
import { formatRelationshipType } from '@/lib/utils';

interface ConnectionsSummaryProps {
  connections: Relationship[];
  committees?: Relationship[];
  holdings?: Relationship[];
}

interface NotableConnection {
  icon: React.ReactNode;
  title: string;
  description: string;
  type: 'conflict' | 'financial' | 'political';
}

export default function ConnectionsSummary({
  connections,
  committees = [],
  holdings = [],
}: ConnectionsSummaryProps) {
  // Find notable connections - overlaps between committees and holdings/donors
  const notableConnections: NotableConnection[] = [];

  // Check for potential conflicts: holdings in companies related to committee work
  const committeeNames = committees
    .map((c) => c.connected_entity?.name?.toLowerCase() || '')
    .filter(Boolean);

  holdings.forEach((holding) => {
    const entityName = holding.connected_entity?.name || '';
    // Simple heuristic: check if any committee name words overlap with holding
    committeeNames.forEach((committeeName) => {
      const committeeWords = committeeName.split(/\s+/).filter((w) => w.length > 4);
      const holdingWords = entityName.toLowerCase().split(/\s+/);
      const overlap = committeeWords.some((cw) =>
        holdingWords.some((hw) => hw.includes(cw) || cw.includes(hw))
      );

      if (overlap) {
        notableConnections.push({
          icon: <AlertCircle className="h-5 w-5 text-money-gold" />,
          title: `Potential Conflict of Interest`,
          description: `Holds financial interest in ${entityName} while serving on ${committees.find((c) => c.connected_entity?.name?.toLowerCase() === committeeName)?.connected_entity?.name || 'related committee'}`,
          type: 'conflict',
        });
      }
    });
  });

  // Highlight large donations
  connections
    .filter((c) => c.relationship_type === 'donated_to' && (c.amount_usd ?? 0) > 10000)
    .slice(0, 5)
    .forEach((donation) => {
      const donorName = donation.connected_entity?.name || 'Unknown';
      notableConnections.push({
        icon: <DollarSign className="h-5 w-5 text-money-success" />,
        title: `Large Contribution`,
        description: `Received ${donation.amount_label || `$${(donation.amount_usd ?? 0).toLocaleString()}`} from ${donorName}`,
        type: 'financial',
      });
    });

  // Show top connections by amount
  const topConnections = [...connections]
    .filter((c) => c.amount_usd != null && c.amount_usd > 0)
    .sort((a, b) => (b.amount_usd ?? 0) - (a.amount_usd ?? 0))
    .slice(0, 10);

  return (
    <div className="space-y-6">
      {/* Notable connections */}
      {notableConnections.length > 0 && (
        <div>
          <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-300">
            <AlertCircle className="h-4 w-4 text-money-gold" />
            Notable Connections
          </h4>
          <div className="space-y-3">
            {notableConnections.map((nc, i) => (
              <div
                key={i}
                className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4"
              >
                <div className="flex items-start gap-3">
                  {nc.icon}
                  <div>
                    <p className="text-sm font-medium text-zinc-200">
                      {nc.title}
                    </p>
                    <p className="mt-0.5 text-sm leading-relaxed text-zinc-400">
                      {nc.description}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* All connections summary */}
      <div>
        <h4 className="mb-3 flex items-center gap-2 text-sm font-semibold text-zinc-300">
          <Building2 className="h-4 w-4 text-zinc-500" />
          Top Connections by Amount
        </h4>

        {topConnections.length === 0 ? (
          <p className="py-4 text-sm text-zinc-500">
            No monetary connections found.
          </p>
        ) : (
          <div className="space-y-2">
            {topConnections.map((conn) => {
              const entity = conn.connected_entity;
              const href = entity
                ? entity.entity_type === 'person'
                  ? `/officials/${entity.slug}`
                  : `/entities/${entity.entity_type}/${entity.slug}`
                : null;

              return (
                <div
                  key={conn.id}
                  className="flex items-center justify-between rounded-lg border border-zinc-800/50 bg-money-surface px-4 py-3"
                >
                  <div className="flex items-center gap-3">
                    <Scale className="h-4 w-4 text-zinc-600" />
                    <div>
                      {href && entity ? (
                        <Link
                          href={href}
                          className="text-sm font-medium text-zinc-200 hover:text-money-gold"
                        >
                          {entity.name}
                        </Link>
                      ) : (
                        <span className="text-sm text-zinc-300">Unknown</span>
                      )}
                      <p className="text-xs text-zinc-500">
                        {formatRelationshipType(conn.relationship_type)}
                      </p>
                    </div>
                  </div>
                  <MoneyAmount
                    amount={conn.amount_usd}
                    label={conn.amount_label}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
