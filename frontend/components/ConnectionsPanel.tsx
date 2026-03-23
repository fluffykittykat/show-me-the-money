'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import type { Relationship, RevolvingDoorItem, FamilyConnectionItem } from '@/lib/types';
import type {
  SharedDonorNetwork as SharedDonorNetworkType,
  SharedInterestsData,
} from '@/lib/api';
import { getRevolvingDoor, getFamilyConnections } from '@/lib/api';
import { formatMoney, getPartyBgColor } from '@/lib/utils';
import {
  AlertCircle,
  DollarSign,
  Building2,
  Scale,
  Users,
  TrendingUp,
  Landmark,
  Factory,
  Star,
  DoorOpen,
  Heart,
} from 'lucide-react';
import MoneyAmount from './MoneyAmount';
import { formatRelationshipType } from '@/lib/utils';
import clsx from 'clsx';

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

const SUBTABS = [
  { id: 'stocks', label: 'Shared Stocks', icon: TrendingUp },
  { id: 'donors', label: 'Shared Donors', icon: Users },
  { id: 'allies', label: 'Legislative Allies', icon: Landmark },
  { id: 'industry', label: 'Industry Network', icon: Factory },
  { id: 'revolving_door', label: 'Revolving Door', icon: DoorOpen },
  { id: 'family', label: 'Family Ties', icon: Heart },
  { id: 'notable', label: 'Notable', icon: Star },
] as const;

type SubTabId = (typeof SUBTABS)[number]['id'];

interface ConnectionsPanelProps {
  connections: Relationship[];
  committees: Relationship[];
  holdings: Relationship[];
  donations: Relationship[];
  entitySlug: string;
  entityName: string;
  networkData: SharedDonorNetworkType | null;
  sharedInterests: SharedInterestsData | null;
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-money-surface px-6 py-8 text-center">
      <p className="text-sm text-zinc-400">{message}</p>
    </div>
  );
}

function PartyDot({ party }: { party?: string }) {
  const bgClass = getPartyBgColor(party);
  return (
    <span
      className={clsx('inline-block h-2.5 w-2.5 shrink-0 rounded-full', bgClass)}
      title={party || 'Unknown party'}
    />
  );
}

// --- Sub-section: Shared Financial Interests ---
function SharedStocksSection({
  sharedInterests,
  entityName,
}: {
  sharedInterests: SharedInterestsData | null;
  entityName: string;
}) {
  const stocks = sharedInterests?.shared_stocks ?? [];

  if (stocks.length === 0) {
    return (
      <EmptyState message="No shared financial interests detected in current data." />
    );
  }

  const sorted = [...stocks].sort((a, b) => b.overlap_count - a.overlap_count);

  return (
    <div>
      <div className="mb-4 rounded-lg border border-zinc-800 bg-money-surface px-4 py-3">
        <p className="text-sm text-zinc-300">
          <TrendingUp className="mr-2 inline-block h-4 w-4 text-money-gold" />
          Officials who hold the same stocks as{' '}
          <span className="font-semibold text-zinc-100">{entityName}</span>
        </p>
      </div>
      <div className="space-y-2">
        {sorted.map((official) => (
          <div
            key={official.slug}
            className="flex items-center justify-between rounded-lg border border-zinc-800/50 bg-money-surface px-4 py-3"
          >
            <div className="flex items-center gap-3">
              <TrendingUp className="h-4 w-4 shrink-0 text-zinc-600" />
              <Link
                href={`/officials/${official.slug}`}
                className="text-sm font-medium text-zinc-200 hover:text-money-gold transition-colors"
              >
                {official.name}
              </Link>
            </div>
            <span className="rounded-full bg-money-gold/10 px-2.5 py-0.5 text-xs font-medium text-money-gold">
              {official.overlap_count} stock{official.overlap_count !== 1 ? 's' : ''} in common
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Sub-section: Shared Donors ---
function SharedDonorsSection({
  sharedInterests,
  networkData,
  entityName,
}: {
  sharedInterests: SharedInterestsData | null;
  networkData: SharedDonorNetworkType | null;
  entityName: string;
}) {
  // Merge data from both sources, preferring sharedInterests
  const interestsDonors = sharedInterests?.shared_donors ?? [];
  const networkEntries = networkData?.network ?? [];

  // Build a map keyed by slug
  const donorMap = new Map<
    string,
    { slug: string; name: string; sharedCount: number; totalAmount: number }
  >();

  for (const d of interestsDonors) {
    donorMap.set(d.slug, {
      slug: d.slug,
      name: d.name,
      sharedCount: d.shared_count,
      totalAmount: d.total_amount,
    });
  }

  // Add network data entries not already covered
  for (const n of networkEntries) {
    if (!donorMap.has(n.senator_slug)) {
      donorMap.set(n.senator_slug, {
        slug: n.senator_slug,
        name: n.senator_name,
        sharedCount: n.shared_donors.length,
        totalAmount: n.total_shared_amount,
      });
    }
  }

  const merged = Array.from(donorMap.values()).sort(
    (a, b) => b.sharedCount - a.sharedCount
  );

  if (merged.length === 0) {
    return (
      <EmptyState message="No shared donor data available." />
    );
  }

  return (
    <div>
      <div className="mb-4 rounded-lg border border-zinc-800 bg-money-surface px-4 py-3">
        <p className="text-sm text-zinc-300">
          <Users className="mr-2 inline-block h-4 w-4 text-money-gold" />
          Officials funded by the same sources as{' '}
          <span className="font-semibold text-zinc-100">{entityName}</span>
        </p>
      </div>
      <div className="space-y-2">
        {merged.map((official) => (
          <div
            key={official.slug}
            className="flex items-center justify-between rounded-lg border border-zinc-800/50 bg-money-surface px-4 py-3"
          >
            <div className="flex items-center gap-3 min-w-0">
              <DollarSign className="h-4 w-4 shrink-0 text-zinc-600" />
              <div className="min-w-0">
                <Link
                  href={`/officials/${official.slug}`}
                  className="text-sm font-medium text-zinc-200 hover:text-money-gold transition-colors"
                >
                  {official.name}
                </Link>
                <p className="text-xs text-zinc-500">
                  {official.sharedCount} shared donor{official.sharedCount !== 1 ? 's' : ''}
                </p>
              </div>
            </div>
            <span className="text-sm font-medium text-money-gold">
              {formatMoney(official.totalAmount)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Sub-section: Legislative Allies ---
function LegislativeAlliesSection({
  sharedInterests,
  entityName,
}: {
  sharedInterests: SharedInterestsData | null;
  entityName: string;
}) {
  const allies = sharedInterests?.legislative_allies ?? [];

  if (allies.length === 0) {
    return (
      <EmptyState message="No legislative co-sponsorship data available." />
    );
  }

  const sorted = [...allies].sort((a, b) => b.shared_bills - a.shared_bills);

  return (
    <div>
      <div className="mb-4 rounded-lg border border-zinc-800 bg-money-surface px-4 py-3">
        <p className="text-sm text-zinc-300">
          <Landmark className="mr-2 inline-block h-4 w-4 text-money-gold" />
          Officials who co-sponsor legislation with{' '}
          <span className="font-semibold text-zinc-100">{entityName}</span>
        </p>
      </div>
      <div className="space-y-2">
        {sorted.map((ally) => (
          <div
            key={ally.slug}
            className="flex items-center justify-between rounded-lg border border-zinc-800/50 bg-money-surface px-4 py-3"
          >
            <div className="flex items-center gap-3">
              <Landmark className="h-4 w-4 shrink-0 text-zinc-600" />
              <Link
                href={`/officials/${ally.slug}`}
                className="text-sm font-medium text-zinc-200 hover:text-money-gold transition-colors"
              >
                {ally.name}
              </Link>
            </div>
            <span className="rounded-full bg-zinc-800 px-2.5 py-0.5 text-xs font-medium text-zinc-300">
              {ally.shared_bills} bill{ally.shared_bills !== 1 ? 's' : ''} co-sponsored together
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Sub-section: Industry Network ---
function IndustryNetworkSection({
  sharedInterests,
  donations,
  entityName,
}: {
  sharedInterests: SharedInterestsData | null;
  donations: Relationship[];
  entityName: string;
}) {
  let industries = sharedInterests?.industry_network ?? [];

  // If no cross-reference data, derive from donations
  if (industries.length === 0 && donations.length > 0) {
    const byIndustry = new Map<string, { total: number; count: number }>();
    for (const d of donations) {
      const meta = d.metadata as Record<string, unknown>;
      const label = (meta?.industry_label as string) || null;
      if (label) {
        const existing = byIndustry.get(label) || { total: 0, count: 0 };
        existing.total += d.amount_usd ?? 0;
        existing.count += 1;
        byIndustry.set(label, existing);
      }
    }
    industries = Array.from(byIndustry.entries())
      .sort(([, a], [, b]) => b.total - a.total)
      .slice(0, 10)
      .map(([industry, data]) => ({
        industry,
        connected_officials: data.count,
        total_money: data.total,
      }));
  }

  if (industries.length === 0) {
    return (
      <EmptyState message="No industry network data available." />
    );
  }

  return (
    <div>
      <div className="mb-4 rounded-lg border border-zinc-800 bg-money-surface px-4 py-3">
        <p className="text-sm text-zinc-300">
          <Factory className="mr-2 inline-block h-4 w-4 text-money-gold" />
          Industries connecting{' '}
          <span className="font-semibold text-zinc-100">{entityName}</span>{' '}
          to other officials
        </p>
      </div>
      <div className="space-y-2">
        {industries.map((item) => (
          <div
            key={item.industry}
            className="flex items-center justify-between rounded-lg border border-zinc-800/50 bg-money-surface px-4 py-3"
          >
            <div className="flex items-center gap-3 min-w-0">
              <Factory className="h-4 w-4 shrink-0 text-zinc-600" />
              <div className="min-w-0">
                <Link
                  href={`/entities/industry/${slugify(item.industry)}`}
                  className="text-sm font-medium text-zinc-200 hover:text-money-gold transition-colors"
                >
                  {item.industry}
                </Link>
                <p className="text-xs text-zinc-500">
                  Connects to {item.connected_officials} other official{item.connected_officials !== 1 ? 's' : ''}
                </p>
              </div>
            </div>
            <span className="text-sm font-medium text-money-gold">
              {formatMoney(item.total_money)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Sub-section: Notable Relationships ---
function NotableRelationshipsSection({
  connections,
  committees,
  holdings,
}: {
  connections: Relationship[];
  committees: Relationship[];
  holdings: Relationship[];
}) {
  interface NotableItem {
    icon: React.ReactNode;
    title: string;
    description: string;
    href: string | null;
    amount: number | null;
  }

  const items: NotableItem[] = [];

  // Large donations (> $10,000 from single source)
  const largeDonations = connections
    .filter(
      (c) =>
        c.relationship_type.toLowerCase().includes('donat') &&
        (c.amount_usd ?? 0) > 10000
    )
    .sort((a, b) => (b.amount_usd ?? 0) - (a.amount_usd ?? 0))
    .slice(0, 5);

  for (const donation of largeDonations) {
    const entity = donation.connected_entity;
    const href = entity
      ? entity.entity_type === 'person'
        ? `/officials/${entity.slug}`
        : `/entities/${entity.entity_type}/${entity.slug}`
      : null;
    items.push({
      icon: <DollarSign className="h-5 w-5 text-money-success" />,
      title: 'Large Contribution',
      description: `Received ${donation.amount_label || formatMoney(donation.amount_usd)} from ${entity?.name || 'Unknown'}`,
      href,
      amount: donation.amount_usd,
    });
  }

  // Committee overlaps where holdings intersect with committee jurisdiction
  const committeeNames = committees
    .map((c) => ({
      name: c.connected_entity?.name?.toLowerCase() || '',
      displayName: c.connected_entity?.name || '',
    }))
    .filter((c) => c.name);

  for (const holding of holdings) {
    const entityName = holding.connected_entity?.name || '';
    for (const committee of committeeNames) {
      const committeeWords = committee.name
        .split(/\s+/)
        .filter((w) => w.length > 4);
      const holdingWords = entityName.toLowerCase().split(/\s+/);
      const overlap = committeeWords.some((cw) =>
        holdingWords.some((hw) => hw.includes(cw) || cw.includes(hw))
      );
      if (overlap) {
        items.push({
          icon: <AlertCircle className="h-5 w-5 text-money-gold" />,
          title: 'Potential Conflict of Interest',
          description: `Holds financial interest in ${entityName} while serving on ${committee.displayName}`,
          href: holding.connected_entity
            ? `/entities/${holding.connected_entity.entity_type}/${holding.connected_entity.slug}`
            : null,
          amount: holding.amount_usd,
        });
      }
    }
  }

  // Top connections by amount (that aren't already shown)
  const shownDescriptions = new Set(items.map((i) => i.description));
  const topConnections = [...connections]
    .filter((c) => c.amount_usd != null && c.amount_usd > 0)
    .sort((a, b) => (b.amount_usd ?? 0) - (a.amount_usd ?? 0))
    .slice(0, 10);

  for (const conn of topConnections) {
    const entity = conn.connected_entity;
    const desc = `${formatRelationshipType(conn.relationship_type)}: ${entity?.name || 'Unknown'}`;
    if (shownDescriptions.has(desc)) continue;
    if (items.length >= 15) break;

    const href = entity
      ? entity.entity_type === 'person'
        ? `/officials/${entity.slug}`
        : `/entities/${entity.entity_type}/${entity.slug}`
      : null;
    items.push({
      icon: <Scale className="h-5 w-5 text-zinc-500" />,
      title: formatRelationshipType(conn.relationship_type),
      description: entity?.name || 'Unknown',
      href,
      amount: conn.amount_usd,
    });
  }

  if (items.length === 0) {
    return (
      <EmptyState message="No notable connections found." />
    );
  }

  return (
    <div>
      <div className="mb-4 rounded-lg border border-zinc-800 bg-money-surface px-4 py-3">
        <p className="text-sm text-zinc-300">
          <Star className="mr-2 inline-block h-4 w-4 text-money-gold" />
          Notable Connections
        </p>
      </div>
      <div className="space-y-3">
        {items.map((item, i) => (
          <div
            key={i}
            className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-start gap-3 min-w-0">
                {item.icon}
                <div className="min-w-0">
                  <p className="text-sm font-medium text-zinc-200">
                    {item.title}
                  </p>
                  {item.href ? (
                    <Link
                      href={item.href}
                      className="mt-0.5 block text-sm leading-relaxed text-zinc-400 hover:text-money-gold transition-colors"
                    >
                      {item.description}
                    </Link>
                  ) : (
                    <p className="mt-0.5 text-sm leading-relaxed text-zinc-400">
                      {item.description}
                    </p>
                  )}
                </div>
              </div>
              {item.amount != null && item.amount > 0 && (
                <span className="shrink-0 text-sm font-medium text-money-gold">
                  {formatMoney(item.amount)}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Sub-section: Revolving Door ---
function RevolvingDoorSubSection({
  items,
  loading,
  entityName,
}: {
  items: RevolvingDoorItem[];
  loading: boolean;
  entityName: string;
}) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-16 animate-pulse rounded-lg bg-zinc-800/50" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <EmptyState message="No revolving door connections found in current data." />
    );
  }

  return (
    <div>
      <div className="mb-4 rounded-lg border border-zinc-800 bg-money-surface px-4 py-3">
        <p className="text-sm text-zinc-300">
          <DoorOpen className="mr-2 inline-block h-4 w-4 text-money-gold" />
          Former government employees now lobbying{' '}
          <span className="font-semibold text-zinc-100">{entityName}</span> or their committees
        </p>
      </div>
      <div className="space-y-2">
        {items.map((item, i) => (
          <div
            key={`${item.lobbyist_slug}-${i}`}
            className="rounded-lg border border-zinc-800/50 bg-money-surface px-4 py-3"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-zinc-200">{item.lobbyist_name}</p>
                <p className="mt-0.5 text-xs text-zinc-500">
                  Formerly: {item.former_position} &rarr; Now: {item.current_role} at {item.current_employer}
                </p>
                {item.lobbies_committee && (
                  <p className="mt-0.5 text-xs text-amber-400">
                    Lobbies: {item.lobbies_committee}
                  </p>
                )}
              </div>
            </div>
            <p className="mt-2 text-xs text-zinc-400">{item.why_this_matters}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Sub-section: Family Ties ---
function FamilyTiesSubSection({
  items,
  loading,
  entityName,
}: {
  items: FamilyConnectionItem[];
  loading: boolean;
  entityName: string;
}) {
  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-16 animate-pulse rounded-lg bg-zinc-800/50" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <EmptyState message="No family financial connections found in current data." />
    );
  }

  return (
    <div>
      <div className="mb-4 rounded-lg border border-zinc-800 bg-money-surface px-4 py-3">
        <p className="text-sm text-zinc-300">
          <Heart className="mr-2 inline-block h-4 w-4 text-money-gold" />
          Family members of{' '}
          <span className="font-semibold text-zinc-100">{entityName}</span>{' '}
          with financial ties to regulated industries
        </p>
      </div>
      <div className="space-y-2">
        {items.map((item, i) => (
          <div
            key={`${item.family_member}-${i}`}
            className="rounded-lg border border-zinc-800/50 bg-money-surface px-4 py-3"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium text-zinc-200">
                  {item.family_member}
                  <span className="ml-2 text-xs text-zinc-500">({item.relationship})</span>
                </p>
                <p className="mt-0.5 text-xs text-zinc-500">
                  {item.role} at {item.employer_name}
                </p>
                {item.committee_overlap && (
                  <p className="mt-0.5 text-xs text-amber-400">
                    Committee overlap: {item.committee_overlap}
                  </p>
                )}
              </div>
              {item.annual_income != null && (
                <span className="shrink-0 text-sm font-medium text-money-gold">
                  {formatMoney(item.annual_income)}/yr
                </span>
              )}
            </div>
            <p className="mt-2 text-xs text-zinc-400">{item.why_this_matters}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Main ConnectionsPanel ---
export default function ConnectionsPanel({
  connections,
  committees,
  holdings,
  donations,
  entitySlug,
  entityName,
  networkData,
  sharedInterests,
}: ConnectionsPanelProps) {
  const [activeSubTab, setActiveSubTab] = useState<SubTabId>('stocks');
  const [revolvingDoorItems, setRevolvingDoorItems] = useState<RevolvingDoorItem[]>([]);
  const [familyItems, setFamilyItems] = useState<FamilyConnectionItem[]>([]);
  const [revolvingDoorLoading, setRevolvingDoorLoading] = useState(false);
  const [familyLoading, setFamilyLoading] = useState(false);

  // Lazy-load revolving door data when sub-tab is selected
  useEffect(() => {
    if (activeSubTab === 'revolving_door' && revolvingDoorItems.length === 0 && !revolvingDoorLoading) {
      setRevolvingDoorLoading(true);
      getRevolvingDoor(entitySlug)
        .then((data) => setRevolvingDoorItems(data))
        .catch(() => setRevolvingDoorItems([]))
        .finally(() => setRevolvingDoorLoading(false));
    }
  }, [activeSubTab, entitySlug, revolvingDoorItems.length, revolvingDoorLoading]);

  // Lazy-load family data when sub-tab is selected
  useEffect(() => {
    if (activeSubTab === 'family' && familyItems.length === 0 && !familyLoading) {
      setFamilyLoading(true);
      getFamilyConnections(entitySlug)
        .then((data) => setFamilyItems(data))
        .catch(() => setFamilyItems([]))
        .finally(() => setFamilyLoading(false));
    }
  }, [activeSubTab, entitySlug, familyItems.length, familyLoading]);

  return (
    <div className="space-y-6">
      {/* Mini-tab navigation */}
      <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
        <div className="flex gap-2" role="tablist" aria-label="Connections sub-sections">
          {SUBTABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeSubTab === tab.id;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={isActive}
                aria-controls={`subtabpanel-${tab.id}`}
                id={`subtab-${tab.id}`}
                onClick={() => setActiveSubTab(tab.id)}
                className={clsx(
                  'inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-3 py-1 text-xs font-medium transition-colors',
                  isActive
                    ? 'bg-money-gold text-zinc-950'
                    : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200'
                )}
              >
                <Icon className="h-3 w-3" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Sub-tab panels */}
      {activeSubTab === 'stocks' && (
        <div role="tabpanel" id="subtabpanel-stocks" aria-labelledby="subtab-stocks">
          <SharedStocksSection
            sharedInterests={sharedInterests}
            entityName={entityName}
          />
        </div>
      )}

      {activeSubTab === 'donors' && (
        <div role="tabpanel" id="subtabpanel-donors" aria-labelledby="subtab-donors">
          <SharedDonorsSection
            sharedInterests={sharedInterests}
            networkData={networkData}
            entityName={entityName}
          />
        </div>
      )}

      {activeSubTab === 'allies' && (
        <div role="tabpanel" id="subtabpanel-allies" aria-labelledby="subtab-allies">
          <LegislativeAlliesSection
            sharedInterests={sharedInterests}
            entityName={entityName}
          />
        </div>
      )}

      {activeSubTab === 'industry' && (
        <div role="tabpanel" id="subtabpanel-industry" aria-labelledby="subtab-industry">
          <IndustryNetworkSection
            sharedInterests={sharedInterests}
            donations={donations}
            entityName={entityName}
          />
        </div>
      )}

      {activeSubTab === 'revolving_door' && (
        <div role="tabpanel" id="subtabpanel-revolving_door" aria-labelledby="subtab-revolving_door">
          <RevolvingDoorSubSection
            items={revolvingDoorItems}
            loading={revolvingDoorLoading}
            entityName={entityName}
          />
        </div>
      )}

      {activeSubTab === 'family' && (
        <div role="tabpanel" id="subtabpanel-family" aria-labelledby="subtab-family">
          <FamilyTiesSubSection
            items={familyItems}
            loading={familyLoading}
            entityName={entityName}
          />
        </div>
      )}

      {activeSubTab === 'notable' && (
        <div role="tabpanel" id="subtabpanel-notable" aria-labelledby="subtab-notable">
          <NotableRelationshipsSection
            connections={connections}
            committees={committees}
            holdings={holdings}
          />
        </div>
      )}
    </div>
  );
}
