'use client';

import Link from 'next/link';
import type { Relationship } from '@/lib/types';
import MoneyAmount from './MoneyAmount';
import { formatDate, formatRelationshipType } from '@/lib/utils';

interface RelationshipTableProps {
  relationships: Relationship[];
  showType?: boolean;
  entityId?: string; // The entity whose page we're on — used to show direction
}

function getDirectionalLabel(rel: Relationship, entityId?: string): string {
  const type = rel.relationship_type;
  const isOutgoing = entityId ? rel.from_entity_id === entityId : true;

  if (type === 'donated_to') {
    return isOutgoing ? 'Funded' : 'Received from';
  }
  if (type === 'sponsored' || type === 'cosponsored') {
    return isOutgoing ? formatRelationshipType(type) : `${formatRelationshipType(type)} by`;
  }
  if (type === 'committee_member') {
    return isOutgoing ? 'Member of' : 'Has member';
  }
  if (type === 'lobbies_on_behalf_of') {
    return isOutgoing ? 'Lobbies for' : 'Lobbied by';
  }
  if (type === 'revolving_door_lobbyist') {
    return isOutgoing ? 'Former staffer of' : 'Has former staffer';
  }
  if (type === 'holds_stock') {
    return isOutgoing ? 'Holds stock in' : 'Stock held by';
  }
  return formatRelationshipType(type);
}

export default function RelationshipTable({
  relationships,
  showType = true,
  entityId,
}: RelationshipTableProps) {
  if (relationships.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-zinc-500">
        No connections found.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-xs uppercase tracking-wider text-zinc-500">
            <th className="px-4 py-3 font-medium">Entity</th>
            {showType && <th className="px-4 py-3 font-medium">Relationship</th>}
            <th className="px-4 py-3 font-medium">Amount</th>
            <th className="px-4 py-3 font-medium">Date</th>
            <th className="px-4 py-3 font-medium">Source</th>
          </tr>
        </thead>
        <tbody>
          {relationships.map((rel) => {
            const entity = rel.connected_entity;
            const href = entity
              ? entity.entity_type === 'person'
                ? `/officials/${entity.slug}`
                : `/entities/${entity.entity_type}/${entity.slug}`
              : null;

            return (
              <tr
                key={rel.id}
                className="border-b border-zinc-800/50 transition-colors hover:bg-zinc-800/30"
              >
                <td className="px-4 py-3">
                  {href && entity ? (
                    <Link
                      href={href}
                      className="font-medium text-zinc-200 hover:text-money-gold"
                    >
                      {entity.name}
                    </Link>
                  ) : (
                    <span className="text-zinc-400">Unknown entity</span>
                  )}
                </td>
                {showType && (
                  <td className="px-4 py-3 text-zinc-400">
                    {getDirectionalLabel(rel, entityId)}
                  </td>
                )}
                <td className="px-4 py-3">
                  {(rel.amount_usd != null || rel.amount_label) ? (
                    <MoneyAmount amount={rel.amount_usd} label={rel.amount_label} />
                  ) : (
                    <span className="text-zinc-600">--</span>
                  )}
                </td>
                <td className="px-4 py-3 text-zinc-400">
                  {formatDate(rel.date_start)}
                </td>
                <td className="px-4 py-3">
                  {rel.source_url ? (
                    <a
                      href={rel.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-money-gold hover:underline"
                    >
                      {rel.source_label || 'Source'}
                    </a>
                  ) : (
                    <span className="text-zinc-600">--</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
