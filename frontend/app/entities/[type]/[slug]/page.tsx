'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import {
  getEntity,
  getConnections,
  getStockHolders,
  getDonorRecipients,
  getCommitteeDetails,
  getIndustryConnections,
  getDonorProfile,
  getCompanyLobbying,
} from '@/lib/api';
import type {
  StockHolderInfo,
  DonorRecipientInfo,
  CommitteeDetailData,
  IndustryConnectionData,
  DonorProfileData,
  LobbyingData,
} from '@/lib/api';
import type { Entity, Relationship } from '@/lib/types';
import {
  capitalize,
  formatMoney,
  formatRelationshipType,
  getInitials,
} from '@/lib/utils';
import PartyBadge from '@/components/PartyBadge';
import MoneyAmount from '@/components/MoneyAmount';
import RelationshipTable from '@/components/RelationshipTable';
import LoadingState from '@/components/LoadingState';
import FBIBriefing from '@/components/FBIBriefing';
import PacDonors from '@/components/PacDonors';
import {
  ArrowLeft,
  ArrowRight,
  AlertTriangle,
  Building2,
  DollarSign,
  ExternalLink,
  FileText,
  Landmark,
  Briefcase,
  Scale,
  Users,
  TrendingUp,
  Gavel,
  Megaphone,
} from 'lucide-react';
import clsx from 'clsx';

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

function EntityTypeIcon({ type }: { type: string }) {
  switch (type) {
    case 'company':
      return <Building2 className="h-6 w-6" />;
    case 'bill':
      return <FileText className="h-6 w-6" />;
    case 'organization':
    case 'pac':
      return <Landmark className="h-6 w-6" />;
    case 'committee':
      return <Scale className="h-6 w-6" />;
    case 'industry':
      return <Briefcase className="h-6 w-6" />;
    default:
      return <Building2 className="h-6 w-6" />;
  }
}

function EntityTypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    company: 'bg-emerald-500/20 text-emerald-400',
    bill: 'bg-purple-500/20 text-purple-400',
    organization: 'bg-orange-500/20 text-orange-400',
    pac: 'bg-pink-500/20 text-pink-400',
    committee: 'bg-amber-500/20 text-amber-400',
    industry: 'bg-cyan-500/20 text-cyan-400',
  };

  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
        colors[type] || 'bg-zinc-700 text-zinc-300'
      )}
    >
      {capitalize(type)}
    </span>
  );
}

function StatCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string | number;
  icon?: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-money-surface px-4 py-3">
      <div className="flex items-center gap-2">
        {Icon && <Icon className="h-4 w-4 text-zinc-500" />}
        <span className="text-xs uppercase tracking-wider text-zinc-500">
          {label}
        </span>
      </div>
      <p className="mt-1 text-lg font-semibold text-money-gold">{value}</p>
    </div>
  );
}

function OfficialCard({
  slug,
  name,
  party,
  state,
  detail,
  subDetail,
}: {
  slug: string;
  name: string;
  party?: string;
  state?: string;
  detail?: React.ReactNode;
  subDetail?: string;
}) {
  return (
    <Link
      href={`/officials/${slug}`}
      className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-money-surface p-4 transition-colors hover:border-money-gold/30 hover:bg-money-surface-elevated"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-500/20 text-xs font-bold text-blue-400">
        {getInitials(name)}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium text-zinc-200">{name}</p>
          {party && <PartyBadge party={party} className="text-[10px]" />}
        </div>
        <div className="flex items-center gap-2">
          {state && <span className="text-xs text-zinc-500">{state}</span>}
          {detail}
          {subDetail && (
            <span className="text-xs text-zinc-500">{subDetail}</span>
          )}
        </div>
      </div>
      <ArrowRight className="h-4 w-4 shrink-0 text-zinc-600" />
    </Link>
  );
}

function SectionHeading({
  icon: Icon,
  children,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-zinc-200">
      {Icon && <Icon className="h-5 w-5 text-money-gold" />}
      {children}
    </h2>
  );
}

// ---------------------------------------------------------------------------
// Donor Profile Section — used by PAC, Organization, and Company types
// ---------------------------------------------------------------------------

function DonorProfileSection({
  donorProfile,
}: {
  donorProfile: DonorProfileData;
}) {
  const topRecipient = donorProfile.recipients.length > 0
    ? donorProfile.recipients.reduce((top, r) =>
        (r.amount_usd ?? 0) > (top.amount_usd ?? 0) ? r : top
      , donorProfile.recipients[0])
    : null;

  return (
    <>
      {/* Stats row */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Political Spend"
          value={
            donorProfile.total_political_spend > 0
              ? formatMoney(donorProfile.total_political_spend, { fromCents: true })
              : 'N/A'
          }
          icon={DollarSign}
        />
        <StatCard
          label="Officials Funded"
          value={donorProfile.recipient_count}
          icon={Users}
        />
        <StatCard
          label="Top Recipient"
          value={topRecipient?.name ?? 'N/A'}
          icon={TrendingUp}
        />
        <StatCard
          label="Committees Covered"
          value={donorProfile.committees_covered.length}
          icon={Scale}
        />
      </div>

      {/* Who They Fund — PRIMARY section */}
      {donorProfile.recipients.length > 0 && (
        <section>
          <SectionHeading icon={DollarSign}>Who They Fund</SectionHeading>
          <div className="space-y-3">
            {donorProfile.recipients
              .sort((a, b) => (b.amount_usd ?? 0) - (a.amount_usd ?? 0))
              .map((recipient, idx) => (
                <div
                  key={`${recipient.slug}-${idx}`}
                  className="rounded-lg border border-zinc-800 bg-money-surface p-4 transition-colors hover:border-money-gold/30"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-500/20 text-xs font-bold text-blue-400">
                        {getInitials(recipient.name)}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <Link
                            href={`/officials/${recipient.slug}`}
                            className="text-sm font-medium text-zinc-200 hover:text-money-gold"
                          >
                            {recipient.name}
                          </Link>
                          <PartyBadge party={recipient.party} className="text-[10px]" />
                          {recipient.state && (
                            <span className="text-xs text-zinc-500">
                              {recipient.state}
                            </span>
                          )}
                        </div>
                        {/* Committees as small tags */}
                        {recipient.committees.length > 0 && (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {recipient.committees.map((committee) => {
                              const committeeSlug = committee
                                .toLowerCase()
                                .replace(/\s+/g, '-')
                                .replace(/[^a-z0-9-]/g, '');
                              return (
                                <Link
                                  key={committee}
                                  href={`/entities/committee/${committeeSlug}`}
                                  className="inline-flex items-center rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[10px] text-amber-400 transition-colors hover:bg-amber-500/20"
                                >
                                  {committee}
                                </Link>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    </div>
                    {recipient.amount_usd != null && (
                      <span className="shrink-0 font-mono text-sm font-semibold text-money-gold">
                        {formatMoney(recipient.amount_usd, { fromCents: true })}
                      </span>
                    )}
                  </div>
                  {/* Relevant votes */}
                  {recipient.relevant_votes.length > 0 && (
                    <div className="mt-2 border-t border-zinc-800 pt-2">
                      <span className="text-[10px] uppercase tracking-wider text-zinc-500">
                        Relevant votes:
                      </span>
                      <p className="mt-0.5 text-xs text-zinc-400">
                        {recipient.relevant_votes.join(' | ')}
                      </p>
                    </div>
                  )}
                </div>
              ))}
          </div>
        </section>
      )}

      {/* Legislation Influenced */}
      {donorProfile.legislation_influenced.length > 0 && (
        <section>
          <SectionHeading icon={Gavel}>Legislation Influenced</SectionHeading>
          <div className="space-y-2">
            {donorProfile.legislation_influenced.map((bill) => (
              <Link
                key={bill.bill_slug}
                href={`/bills/${bill.bill_slug}`}
                className="flex items-center justify-between rounded-lg border border-zinc-800 bg-money-surface px-4 py-3 transition-colors hover:border-money-gold/30 hover:bg-money-surface-elevated"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-zinc-200">
                    {bill.bill_name}
                  </p>
                  <p className="text-xs text-zinc-500">
                    {bill.yes_voters_funded} funded YES voter{bill.yes_voters_funded !== 1 ? 's' : ''}
                  </p>
                </div>
                <div className="ml-3 shrink-0 text-right">
                  <span className="font-mono text-sm font-semibold text-money-gold">
                    {formatMoney(bill.total_to_yes_voters, { fromCents: true })}
                  </span>
                  <p className="text-[10px] text-zinc-500">to YES voters</p>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Committees Covered */}
      {donorProfile.committees_covered.length > 0 && (
        <section>
          <SectionHeading icon={Scale}>Committees Covered</SectionHeading>
          <p className="mb-3 text-sm text-zinc-500">
            Their funded officials sit on these committees, giving them reach into government oversight.
          </p>
          <div className="flex flex-wrap gap-2">
            {donorProfile.committees_covered.map((committee) => {
              const committeeSlug = committee
                .toLowerCase()
                .replace(/\s+/g, '-')
                .replace(/[^a-z0-9-]/g, '');
              return (
                <Link
                  key={committee}
                  href={`/entities/committee/${committeeSlug}`}
                  className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-sm text-amber-400 transition-colors hover:bg-amber-500/20"
                >
                  <Scale className="h-3 w-3" />
                  {committee}
                </Link>
              );
            })}
          </div>
        </section>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Entity-type-specific content sections
// ---------------------------------------------------------------------------

function CompanyContent({
  entity,
  connections,
  stockHolders,
  donorProfile,
  lobbyingData,
}: {
  entity: Entity;
  connections: Relationship[];
  stockHolders: StockHolderInfo[] | null;
  donorProfile: DonorProfileData | null;
  lobbyingData: LobbyingData | null;
}) {
  const billConnections = connections.filter(
    (c) => c.connected_entity?.entity_type === 'bill'
  );
  const pacConnections = connections.filter(
    (c) =>
      c.connected_entity?.entity_type === 'pac' ||
      c.connected_entity?.entity_type === 'organization'
  );

  const totalStockValue =
    stockHolders
      ?.filter((h) => h.amount_usd != null)
      .reduce((sum, h) => sum + (h.amount_usd ?? 0), 0) ?? 0;

  return (
    <>
      {/* Donor Profile — who they fund */}
      {donorProfile && <DonorProfileSection donorProfile={donorProfile} />}

      {/* Stock holders stats — only if no donor profile or always show stock info */}
      {!donorProfile && (
        <div className="grid gap-3 sm:grid-cols-3">
          <StatCard
            label="Congressional Stock Holders"
            value={stockHolders?.length ?? 0}
            icon={Users}
          />
          <StatCard
            label="Total Stock Held"
            value={
              totalStockValue > 0
                ? formatMoney(totalStockValue, { fromCents: true })
                : 'N/A'
            }
            icon={DollarSign}
          />
          <StatCard
            label="Connected PACs"
            value={pacConnections.length}
            icon={Landmark}
          />
        </div>
      )}

      {/* Who in Congress holds this stock */}
      {stockHolders && stockHolders.length > 0 && (
        <section>
          <SectionHeading icon={DollarSign}>
            Who in Congress Holds This Stock
          </SectionHeading>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {stockHolders.map((holder) => (
              <OfficialCard
                key={holder.slug}
                slug={holder.slug}
                name={holder.name}
                party={holder.party}
                state={holder.state}
                detail={
                  <MoneyAmount
                    amount={holder.amount_usd}
                    label={holder.amount_label}
                    fromCents
                    className="text-xs"
                  />
                }
              />
            ))}
          </div>
        </section>
      )}

      {/* Legislation affecting this company */}
      {billConnections.length > 0 && (
        <section>
          <SectionHeading icon={FileText}>
            Legislation Affecting This Company
          </SectionHeading>
          <div className="space-y-2">
            {billConnections.slice(0, 10).map((conn) => {
              const bill = conn.connected_entity;
              if (!bill) return null;
              return (
                <Link
                  key={conn.id}
                  href={`/bills/${bill.slug}`}
                  className="flex items-center justify-between rounded-lg border border-zinc-800 bg-money-surface px-4 py-3 transition-colors hover:border-money-gold/30 hover:bg-money-surface-elevated"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-zinc-200">
                      {bill.name}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {formatRelationshipType(conn.relationship_type)}
                    </p>
                  </div>
                  <ExternalLink className="ml-2 h-4 w-4 shrink-0 text-zinc-600" />
                </Link>
              );
            })}
          </div>
        </section>
      )}

      {/* PACs connected */}
      {pacConnections.length > 0 && (
        <section>
          <SectionHeading icon={Landmark}>
            PACs Connected to This Company
          </SectionHeading>
          <div className="grid gap-3 sm:grid-cols-2">
            {pacConnections.slice(0, 8).map((conn) => {
              const pac = conn.connected_entity;
              if (!pac) return null;
              return (
                <Link
                  key={conn.id}
                  href={`/entities/${pac.entity_type}/${pac.slug}`}
                  className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-money-surface p-4 transition-colors hover:border-money-gold/30 hover:bg-money-surface-elevated"
                >
                  <Landmark className="h-5 w-5 shrink-0 text-pink-400" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-zinc-200">
                      {pac.name}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {formatRelationshipType(conn.relationship_type)}
                    </p>
                  </div>
                  {conn.amount_usd != null && conn.amount_usd > 0 && (
                    <MoneyAmount
                      amount={conn.amount_usd}
                      label={conn.amount_label}
                      className="text-xs"
                    />
                  )}
                </Link>
              );
            })}
          </div>
        </section>
      )}

      {/* Lobbying Activity */}
      {lobbyingData && lobbyingData.total_spend > 0 ? (
        <section>
          <SectionHeading icon={Megaphone}>Lobbying Activity</SectionHeading>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Total Lobbying Spend"
              value={formatMoney(lobbyingData.total_spend, { fromCents: true })}
              icon={DollarSign}
            />
            <StatCard
              label="Filings"
              value={lobbyingData.filing_count}
              icon={Megaphone}
            />
            <StatCard
              label="Lobbying Firms"
              value={lobbyingData.firm_count}
              icon={Building2}
            />
            <StatCard
              label="Lobbyists"
              value={lobbyingData.lobbyist_count}
              icon={Users}
            />
          </div>
          {lobbyingData.issues.length > 0 && (
            <div className="mt-4">
              <h4 className="mb-2 text-xs font-bold uppercase tracking-wider text-zinc-400">
                Lobbying Issues
              </h4>
              <div className="flex flex-wrap gap-2">
                {lobbyingData.issues.map((issue) => (
                  <span
                    key={issue}
                    className="rounded-full border border-purple-500/20 bg-purple-500/10 px-3 py-1 text-xs text-purple-300"
                  >
                    {issue}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
      ) : (
        <section>
          <SectionHeading icon={Megaphone}>Lobbying Activity</SectionHeading>
          <div className="rounded-lg border border-zinc-800 bg-money-surface px-6 py-6 text-center">
            <Megaphone className="mx-auto h-6 w-6 text-zinc-600" />
            <p className="mt-2 text-sm text-zinc-400">
              Lobbying data not yet available for this entity.
            </p>
          </div>
        </section>
      )}

      {/* Follow the Money */}
      <section className="rounded-lg border border-money-gold/30 bg-money-surface p-6">
        <SectionHeading icon={DollarSign}>Follow the Money</SectionHeading>
        <div className="space-y-3 text-sm text-zinc-400">
          {stockHolders && stockHolders.length > 0 && (
            <p>
              <span className="font-medium text-money-gold">
                {stockHolders.length}
              </span>{' '}
              members of Congress hold stock in {entity.name}
              {totalStockValue > 0 && (
                <>
                  , worth an estimated{' '}
                  <span className="font-medium text-money-gold">
                    {formatMoney(totalStockValue, { fromCents: true })}
                  </span>
                </>
              )}
              .
            </p>
          )}
          {donorProfile && donorProfile.recipient_count > 0 && (
            <p>
              {entity.name} has funded{' '}
              <span className="font-medium text-money-gold">
                {donorProfile.recipient_count}
              </span>{' '}
              officials with{' '}
              <span className="font-medium text-money-gold">
                {formatMoney(donorProfile.total_political_spend, { fromCents: true })}
              </span>{' '}
              in political contributions, covering{' '}
              <span className="font-medium text-money-gold">
                {donorProfile.committees_covered.length}
              </span>{' '}
              committees.
            </p>
          )}
          {pacConnections.length > 0 && (
            <p>
              <span className="font-medium text-money-gold">
                {pacConnections.length}
              </span>{' '}
              PACs or organizations are connected to this company.
            </p>
          )}
          {billConnections.length > 0 && (
            <p>
              <span className="font-medium text-money-gold">
                {billConnections.length}
              </span>{' '}
              pieces of legislation relate to this company.
            </p>
          )}
          {stockHolders?.length === 0 &&
            pacConnections.length === 0 &&
            billConnections.length === 0 &&
            !donorProfile && (
              <p>No direct financial connections found yet.</p>
            )}
        </div>
      </section>
    </>
  );
}

function DonorContent({
  entity,
  connections,
  recipients,
  donorProfile,
}: {
  entity: Entity;
  connections: Relationship[];
  recipients: DonorRecipientInfo[] | null;
  donorProfile: DonorProfileData | null;
}) {
  const metadata = entity.metadata as Record<string, unknown>;
  const billConnections = connections.filter(
    (c) => c.connected_entity?.entity_type === 'bill'
  );
  const orgConnections = connections.filter(
    (c) =>
      c.connected_entity?.entity_type === 'organization' ||
      c.connected_entity?.entity_type === 'pac'
  );

  const totalSpending =
    recipients
      ?.filter((r) => r.amount_usd != null)
      .reduce((sum, r) => sum + (r.amount_usd ?? 0), 0) ?? 0;

  // If donor profile is available, use it as the PRIMARY view
  if (donorProfile) {
    return (
      <>
        {/* Who they fund — outgoing donations */}
        <DonorProfileSection donorProfile={donorProfile} />

        {/* Legislation they've lobbied for */}
        {billConnections.length > 0 && (
          <section>
            <SectionHeading icon={FileText}>
              Legislation They&apos;ve Lobbied For
            </SectionHeading>
            <div className="space-y-2">
              {billConnections.slice(0, 10).map((conn) => {
                const bill = conn.connected_entity;
                if (!bill) return null;
                return (
                  <Link
                    key={conn.id}
                    href={`/bills/${bill.slug}`}
                    className="flex items-center justify-between rounded-lg border border-zinc-800 bg-money-surface px-4 py-3 transition-colors hover:border-money-gold/30 hover:bg-money-surface-elevated"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-zinc-200">
                        {bill.name}
                      </p>
                      <p className="text-xs text-zinc-500">
                        {formatRelationshipType(conn.relationship_type)}
                      </p>
                    </div>
                    <ExternalLink className="ml-2 h-4 w-4 shrink-0 text-zinc-600" />
                  </Link>
                );
              })}
            </div>
          </section>
        )}

        {/* Related PACs and Orgs */}
        {orgConnections.length > 0 && (
          <section>
            <SectionHeading icon={Landmark}>
              Related PACs and Organizations
            </SectionHeading>
            <div className="grid gap-3 sm:grid-cols-2">
              {orgConnections.slice(0, 8).map((conn) => {
                const org = conn.connected_entity;
                if (!org) return null;
                return (
                  <Link
                    key={conn.id}
                    href={`/entities/${org.entity_type}/${org.slug}`}
                    className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-money-surface p-4 transition-colors hover:border-money-gold/30 hover:bg-money-surface-elevated"
                  >
                    <Landmark className="h-5 w-5 shrink-0 text-orange-400" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-zinc-200">
                        {org.name}
                      </p>
                      <p className="text-xs text-zinc-500">
                        {formatRelationshipType(conn.relationship_type)}
                      </p>
                    </div>
                  </Link>
                );
              })}
            </div>
          </section>
        )}

        {/* Follow the Money */}
        <section className="rounded-lg border border-money-gold/30 bg-money-surface p-6">
          <SectionHeading icon={DollarSign}>Follow the Money</SectionHeading>
          <div className="space-y-3 text-sm text-zinc-400">
            <p>
              {entity.name} has funded{' '}
              <span className="font-medium text-money-gold">
                {donorProfile.recipient_count}
              </span>{' '}
              officials with{' '}
              <span className="font-medium text-money-gold">
                {formatMoney(donorProfile.total_political_spend, { fromCents: true })}
              </span>{' '}
              in political contributions, covering{' '}
              <span className="font-medium text-money-gold">
                {donorProfile.committees_covered.length}
              </span>{' '}
              committees.
            </p>
            {donorProfile.legislation_influenced.length > 0 && (
              <p>
                Their money influenced{' '}
                <span className="font-medium text-money-gold">
                  {donorProfile.legislation_influenced.length}
                </span>{' '}
                pieces of legislation through funded YES voters.
              </p>
            )}
          </div>
        </section>
      </>
    );
  }

  // Fallback: original donor content without enhanced profile
  return (
    <>
      {/* Stats row */}
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard
          label="Officials Funded"
          value={recipients?.length ?? 0}
          icon={Users}
        />
        <StatCard
          label="Total Political Spending"
          value={
            totalSpending > 0
              ? formatMoney(totalSpending, { fromCents: true })
              : 'N/A'
          }
          icon={DollarSign}
        />
        {metadata?.industry != null && (
          <StatCard
            label="Industry"
            value={String(metadata.industry)}
            icon={Briefcase}
          />
        )}
      </div>

      {/* Who they fund */}
      {recipients && recipients.length > 0 && (
        <section>
          <SectionHeading icon={DollarSign}>Who They Fund</SectionHeading>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {recipients.map((recipient) => (
              <OfficialCard
                key={recipient.slug}
                slug={recipient.slug}
                name={recipient.name}
                party={recipient.party}
                state={recipient.state}
                detail={
                  <MoneyAmount
                    amount={recipient.amount_usd}
                    label={recipient.amount_label}
                    fromCents
                    className="text-xs"
                  />
                }
              />
            ))}
          </div>
        </section>
      )}

      {/* Legislation they've lobbied for */}
      {billConnections.length > 0 && (
        <section>
          <SectionHeading icon={FileText}>
            Legislation They&apos;ve Lobbied For
          </SectionHeading>
          <div className="space-y-2">
            {billConnections.slice(0, 10).map((conn) => {
              const bill = conn.connected_entity;
              if (!bill) return null;
              return (
                <Link
                  key={conn.id}
                  href={`/bills/${bill.slug}`}
                  className="flex items-center justify-between rounded-lg border border-zinc-800 bg-money-surface px-4 py-3 transition-colors hover:border-money-gold/30 hover:bg-money-surface-elevated"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-zinc-200">
                      {bill.name}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {formatRelationshipType(conn.relationship_type)}
                    </p>
                  </div>
                  <ExternalLink className="ml-2 h-4 w-4 shrink-0 text-zinc-600" />
                </Link>
              );
            })}
          </div>
        </section>
      )}

      {/* Related PACs and Orgs */}
      {orgConnections.length > 0 && (
        <section>
          <SectionHeading icon={Landmark}>
            Related PACs and Organizations
          </SectionHeading>
          <div className="grid gap-3 sm:grid-cols-2">
            {orgConnections.slice(0, 8).map((conn) => {
              const org = conn.connected_entity;
              if (!org) return null;
              return (
                <Link
                  key={conn.id}
                  href={`/entities/${org.entity_type}/${org.slug}`}
                  className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-money-surface p-4 transition-colors hover:border-money-gold/30 hover:bg-money-surface-elevated"
                >
                  <Landmark className="h-5 w-5 shrink-0 text-orange-400" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-zinc-200">
                      {org.name}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {formatRelationshipType(conn.relationship_type)}
                    </p>
                  </div>
                </Link>
              );
            })}
          </div>
        </section>
      )}

      {/* Follow the Money */}
      <section className="rounded-lg border border-money-gold/30 bg-money-surface p-6">
        <SectionHeading icon={DollarSign}>Follow the Money</SectionHeading>
        <div className="space-y-3 text-sm text-zinc-400">
          {recipients && recipients.length > 0 && (
            <p>
              {entity.name} has funded{' '}
              <span className="font-medium text-money-gold">
                {recipients.length}
              </span>{' '}
              officials
              {totalSpending > 0 && (
                <>
                  {' '}
                  with a total of{' '}
                  <span className="font-medium text-money-gold">
                    {formatMoney(totalSpending, { fromCents: true })}
                  </span>{' '}
                  in political contributions
                </>
              )}
              .
            </p>
          )}
          {billConnections.length > 0 && (
            <p>
              Connected to{' '}
              <span className="font-medium text-money-gold">
                {billConnections.length}
              </span>{' '}
              pieces of legislation.
            </p>
          )}
        </div>
      </section>
    </>
  );
}

function IndustryContent({
  entity,
  connections,
  industryData,
}: {
  entity: Entity;
  connections: Relationship[];
  industryData: IndustryConnectionData | null;
}) {
  const billConnections = connections.filter(
    (c) => c.connected_entity?.entity_type === 'bill'
  );

  return (
    <>
      {/* Stats row */}
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard
          label="Officials Connected"
          value={industryData?.official_count ?? 0}
          icon={Users}
        />
        <StatCard
          label="Total Industry Donations"
          value={
            industryData?.total_donated
              ? formatMoney(industryData.total_donated, { fromCents: true })
              : 'N/A'
          }
          icon={DollarSign}
        />
        <StatCard
          label="Related Entities"
          value={industryData?.entity_count ?? 0}
          icon={Building2}
        />
      </div>

      {/* All donations from this sector */}
      {industryData?.donations_to_officials &&
        industryData.donations_to_officials.length > 0 && (
          <section>
            <SectionHeading icon={DollarSign}>
              All Donations From This Sector
            </SectionHeading>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {industryData.donations_to_officials.map((official) => (
                <OfficialCard
                  key={official.slug}
                  slug={official.slug}
                  name={official.name}
                  party={official.party}
                  state={official.state}
                  detail={
                    <MoneyAmount
                      amount={official.amount_usd}
                      label={official.amount_label}
                      fromCents
                      className="text-xs"
                    />
                  }
                />
              ))}
            </div>
          </section>
        )}

      {/* Related entities in this industry */}
      {industryData?.related_entities &&
        industryData.related_entities.length > 0 && (
          <section>
            <SectionHeading icon={Building2}>
              Related Entities in This Industry
            </SectionHeading>
            <div className="flex flex-wrap gap-2">
              {industryData.related_entities.map((re) => {
                const typePath = re.entity_type.toLowerCase();
                return (
                  <Link
                    key={re.slug}
                    href={`/entities/${typePath}/${re.slug}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-zinc-700 bg-money-surface px-3 py-1.5 text-sm text-zinc-300 transition-colors hover:border-money-gold/30 hover:text-zinc-100"
                  >
                    <EntityTypeIcon type={re.entity_type} />
                    <span className="max-w-[200px] truncate">{re.name}</span>
                  </Link>
                );
              })}
            </div>
          </section>
        )}

      {/* Bills with this policy area */}
      {billConnections.length > 0 && (
        <section>
          <SectionHeading icon={FileText}>
            Bills Related to This Industry
          </SectionHeading>
          <div className="space-y-2">
            {billConnections.slice(0, 10).map((conn) => {
              const bill = conn.connected_entity;
              if (!bill) return null;
              return (
                <Link
                  key={conn.id}
                  href={`/bills/${bill.slug}`}
                  className="flex items-center justify-between rounded-lg border border-zinc-800 bg-money-surface px-4 py-3 transition-colors hover:border-money-gold/30 hover:bg-money-surface-elevated"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-zinc-200">
                      {bill.name}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {formatRelationshipType(conn.relationship_type)}
                    </p>
                  </div>
                  <ExternalLink className="ml-2 h-4 w-4 shrink-0 text-zinc-600" />
                </Link>
              );
            })}
          </div>
        </section>
      )}

      {/* Follow the Money */}
      <section className="rounded-lg border border-money-gold/30 bg-money-surface p-6">
        <SectionHeading icon={DollarSign}>Follow the Money</SectionHeading>
        <div className="space-y-3 text-sm text-zinc-400">
          {industryData && (
            <p>
              The {entity.name} industry has donated{' '}
              <span className="font-medium text-money-gold">
                {industryData.total_donated
                  ? formatMoney(industryData.total_donated, { fromCents: true })
                  : '$0'}
              </span>{' '}
              to{' '}
              <span className="font-medium text-money-gold">
                {industryData.official_count}
              </span>{' '}
              officials, connecting through{' '}
              <span className="font-medium text-money-gold">
                {industryData.entity_count}
              </span>{' '}
              entities.
            </p>
          )}
        </div>
      </section>
    </>
  );
}

function CommitteeContent({
  connections,
  committeeData,
}: {
  connections: Relationship[];
  committeeData: CommitteeDetailData | null;
}) {
  const billConnections = connections.filter(
    (c) => c.connected_entity?.entity_type === 'bill'
  );

  return (
    <>
      {/* Stats row */}
      <div className="grid gap-3 sm:grid-cols-3">
        <StatCard
          label="Members"
          value={committeeData?.member_count ?? 0}
          icon={Users}
        />
        <StatCard
          label="Industries Overseen"
          value={committeeData?.jurisdiction?.industries?.length ?? 0}
          icon={Briefcase}
        />
        <StatCard
          label="Bills Referred"
          value={billConnections.length}
          icon={FileText}
        />
      </div>

      {/* Jurisdiction */}
      {committeeData?.jurisdiction && (
        <section>
          <SectionHeading icon={Scale}>Jurisdiction</SectionHeading>
          <div className="space-y-4">
            {/* Industries under oversight */}
            {committeeData.jurisdiction.industries.length > 0 && (
              <div>
                <h3 className="mb-2 text-sm font-medium text-zinc-400">
                  Industries Under Oversight
                </h3>
                <div className="flex flex-wrap gap-2">
                  {committeeData.jurisdiction.industries.map((industry) => (
                    <Link
                      key={industry}
                      href={`/entities/industry/${encodeURIComponent(industry.toLowerCase().replace(/\s+/g, '-'))}`}
                      className="inline-flex items-center gap-1 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-3 py-1 text-sm text-cyan-400 transition-colors hover:bg-cyan-500/20"
                    >
                      <Briefcase className="h-3 w-3" />
                      {industry}
                    </Link>
                  ))}
                </div>
              </div>
            )}

            {/* Topics */}
            {committeeData.jurisdiction.topics.length > 0 && (
              <div>
                <h3 className="mb-2 text-sm font-medium text-zinc-400">
                  Areas of Jurisdiction
                </h3>
                <ul className="list-inside list-disc space-y-1 text-sm text-zinc-300">
                  {committeeData.jurisdiction.topics.map((topic) => (
                    <li key={topic}>{topic}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Current Members */}
      {committeeData?.members && committeeData.members.length > 0 && (
        <section>
          <SectionHeading icon={Users}>Current Members</SectionHeading>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {committeeData.members.map((member) => (
              <OfficialCard
                key={member.slug}
                slug={member.slug}
                name={member.name}
                party={member.party}
                state={member.state}
                subDetail={member.role}
              />
            ))}
          </div>
        </section>
      )}

      {/* Bills referred to this committee */}
      {billConnections.length > 0 && (
        <section>
          <SectionHeading icon={FileText}>
            Bills Referred to This Committee
          </SectionHeading>
          <div className="space-y-2">
            {billConnections.slice(0, 10).map((conn) => {
              const bill = conn.connected_entity;
              if (!bill) return null;
              return (
                <Link
                  key={conn.id}
                  href={`/bills/${bill.slug}`}
                  className="flex items-center justify-between rounded-lg border border-zinc-800 bg-money-surface px-4 py-3 transition-colors hover:border-money-gold/30 hover:bg-money-surface-elevated"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-zinc-200">
                      {bill.name}
                    </p>
                    <p className="text-xs text-zinc-500">
                      {formatRelationshipType(conn.relationship_type)}
                    </p>
                  </div>
                  <ExternalLink className="ml-2 h-4 w-4 shrink-0 text-zinc-600" />
                </Link>
              );
            })}
          </div>
        </section>
      )}

      {/* Follow the Money */}
      <section className="rounded-lg border border-money-gold/30 bg-money-surface p-6">
        <SectionHeading icon={DollarSign}>Follow the Money</SectionHeading>
        <div className="space-y-3 text-sm text-zinc-400">
          {committeeData && committeeData.jurisdiction?.industries.length > 0 && (
            <p>
              This committee oversees{' '}
              <span className="font-medium text-money-gold">
                {committeeData.jurisdiction.industries.length}
              </span>{' '}
              industries. Track which of those industries donate to the{' '}
              <span className="font-medium text-money-gold">
                {committeeData.member_count}
              </span>{' '}
              committee members.
            </p>
          )}
          {(!committeeData ||
            committeeData.jurisdiction?.industries.length === 0) && (
            <p>No industry oversight data available yet.</p>
          )}
        </div>
      </section>
    </>
  );
}

function BillContent({ entity }: { entity: Entity }) {
  const metadata = entity.metadata as Record<string, unknown>;
  return (
    <section>
      <div className="mb-4 flex flex-wrap gap-4">
        {metadata?.status != null && (
          <StatCard label="Status" value={String(metadata.status)} />
        )}
        {metadata?.policy_area != null && (
          <StatCard label="Policy Area" value={String(metadata.policy_area)} />
        )}
        {metadata?.bill_number != null && (
          <StatCard label="Bill Number" value={String(metadata.bill_number)} />
        )}
      </div>
      <Link
        href={`/bills/${entity.slug}`}
        className="inline-flex items-center gap-2 rounded-md bg-money-gold px-4 py-2 text-sm font-medium text-zinc-950 transition-colors hover:bg-money-gold-hover"
      >
        <FileText className="h-4 w-4" />
        View Full Investigation
        <ArrowRight className="h-4 w-4" />
      </Link>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

type TypeSpecificData =
  | { kind: 'company'; stockHolders: StockHolderInfo[] | null; donorProfile: DonorProfileData | null; lobbyingData: LobbyingData | null }
  | { kind: 'donor'; recipients: DonorRecipientInfo[] | null; donorProfile: DonorProfileData | null }
  | { kind: 'industry'; data: IndustryConnectionData | null }
  | { kind: 'committee'; data: CommitteeDetailData | null }
  | { kind: 'bill' }
  | { kind: 'fallback' };

export default function EntityPage() {
  const params = useParams();
  const type = params.type as string;
  const slug = params.slug as string;

  const [entity, setEntity] = useState<Entity | null>(null);
  const [connections, setConnections] = useState<Relationship[]>([]);
  const [typeData, setTypeData] = useState<TypeSpecificData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Always fetch entity + connections
      const [entityData, connectionsData] = await Promise.all([
        getEntity(slug),
        getConnections(slug, { limit: 500 }),
      ]);

      setEntity(entityData);
      setConnections(connectionsData.connections);

      // Fetch type-specific cross-reference data with graceful fallbacks
      const entityType = entityData.entity_type;

      if (entityType === 'company') {
        const [stockHolders, donorProfile, lobbyingData] = await Promise.all([
          getStockHolders(slug).catch(() => null),
          getDonorProfile(slug).catch(() => null),
          getCompanyLobbying(slug).catch(() => null),
        ]);
        setTypeData({ kind: 'company', stockHolders, donorProfile, lobbyingData });
      } else if (
        entityType === 'pac' ||
        entityType === 'organization'
      ) {
        const [recipients, donorProfile] = await Promise.all([
          getDonorRecipients(slug).catch(() => null),
          getDonorProfile(slug).catch(() => null),
        ]);
        setTypeData({ kind: 'donor', recipients, donorProfile });
      } else if (entityType === 'industry') {
        const data = await getIndustryConnections(slug).catch(() => null);
        setTypeData({ kind: 'industry', data });
      } else if (type === 'committee') {
        const data = await getCommitteeDetails(slug).catch(() => null);
        setTypeData({ kind: 'committee', data });
      } else if (entityType === 'bill') {
        setTypeData({ kind: 'bill' });
      } else {
        setTypeData({ kind: 'fallback' });
      }
    } catch (err) {
      if (
        err instanceof Error &&
        'status' in err &&
        (err as Record<string, unknown>).status === 404
      ) {
        setError('Entity not found.');
      } else {
        setError('Failed to load data. Please try again later.');
      }
    } finally {
      setLoading(false);
    }
  }, [slug, type]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // --- Loading ---
  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <LoadingState variant="profile" />
      </div>
    );
  }

  // --- Error ---
  if (error || !entity) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-md text-center">
          <AlertTriangle className="mx-auto h-12 w-12 text-zinc-600" />
          <h1 className="mt-4 text-xl font-bold text-zinc-200">
            {error || 'Something went wrong'}
          </h1>
          <div className="mt-6 flex justify-center gap-3">
            <Link
              href="/"
              className="inline-flex items-center gap-2 rounded-md border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:border-zinc-600"
            >
              <ArrowLeft className="h-4 w-4" />
              Home
            </Link>
            <button
              onClick={fetchData}
              className="rounded-md bg-money-gold px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-money-gold-hover"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  // --- Categorize connections ---
  const connectedOfficials = connections.filter(
    (c) => c.connected_entity?.entity_type === 'person'
  );

  const metadata = entity.metadata as Record<string, unknown>;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      {/* Breadcrumb */}
      <div className="mb-6">
        <Link
          href="/search"
          className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-300"
        >
          <ArrowLeft className="h-3 w-3" />
          Search
        </Link>
      </div>

      {/* Header */}
      <div className="mb-8 flex items-start gap-5">
        <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-lg bg-zinc-800 text-zinc-400">
          <EntityTypeIcon type={entity.entity_type} />
        </div>
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight text-zinc-100">
              {entity.name}
            </h1>
            <EntityTypeBadge type={entity.entity_type} />
          </div>

          {entity.summary && (
            <p className="mt-3 max-w-3xl text-sm leading-relaxed text-zinc-400">
              {entity.summary}
            </p>
          )}

          {/* Metadata display */}
          {Object.keys(metadata).length > 0 && (
            <div className="mt-4 flex flex-wrap gap-4">
              {Object.entries(metadata)
                .filter(([key]) => !['id', 'slug', 'fbi_briefing', 'fbi_briefing_fingerprint', 'mock_briefing'].includes(key))
                .filter(([, value]) => typeof value === 'string' || typeof value === 'number')
                .slice(0, 6)
                .map(([key, value]) => (
                  <div key={key} className="text-sm">
                    <span className="text-zinc-500">
                      {formatRelationshipType(key)}:
                    </span>{' '}
                    <span className="text-zinc-300">{String(value)}</span>
                  </div>
                ))}
            </div>
          )}
        </div>
      </div>

      {/* Main content */}
      <div className="space-y-8">
        {/* FBI Briefing — shown on every entity page */}
        <div className="mb-8">
          <FBIBriefing
            entitySlug={slug}
            entityName={entity.name}
            entityType={entity.entity_type}
          />
        </div>

        {/* Family Ties Alert — prominently call out family connections */}
        {connections.filter(c =>
          ['family_employed_by', 'spouse_income_from'].includes(c.relationship_type)
        ).length > 0 && (
          <section>
            <div className="rounded-xl border-2 border-red-500/30 bg-red-950/20 p-5">
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="h-5 w-5 text-red-400" />
                <h3 className="font-mono text-sm font-bold uppercase tracking-wider text-red-400">
                  Family Ties Alert
                </h3>
              </div>
              <div className="space-y-2">
                {connections
                  .filter(c => ['family_employed_by', 'spouse_income_from'].includes(c.relationship_type))
                  .map((conn, i) => {
                    const official = conn.connected_entity;
                    if (!official) return null;
                    const meta = conn.metadata as Record<string, unknown>;
                    const familyMember = (meta?.family_member as string) || 'A family member';
                    const role = (meta?.role as string) || 'employee';
                    return (
                      <div key={i} className="flex items-start gap-3 rounded-lg border border-red-500/10 bg-zinc-900/50 p-3">
                        <span className="text-lg">&#128104;&#8205;&#128105;&#8205;&#128103;</span>
                        <div>
                          <p className="text-sm text-zinc-200">
                            <Link href={`/officials/${official.slug}`} className="font-semibold text-money-gold hover:underline">
                              {official.name}
                            </Link>
                            {conn.relationship_type === 'spouse_income_from'
                              ? "'s spouse receives income from this entity"
                              : "'s family member is employed by this entity"}
                          </p>
                          {familyMember && (
                            <p className="mt-1 text-xs text-zinc-400">
                              {familyMember} — {role}
                              {conn.amount_usd ? ` ($${(conn.amount_usd / 100).toLocaleString()}/year)` : ''}
                            </p>
                          )}
                          <p className="mt-1 text-xs text-red-400/80">
                            This creates a potential conflict of interest if {official.name} has legislative authority
                            over this entity&apos;s industry.
                          </p>
                        </div>
                      </div>
                    );
                  })}
              </div>
            </div>
          </section>
        )}

        {/* Who Funds This Entity — PAC donors auto-fetched from FEC */}
        {(entity.entity_type === 'pac' || entity.entity_type === 'organization' || entity.entity_type === 'company') && (
          <PacDonors slug={entity.slug} entityName={entity.name} />
        )}

        {/* Connected Officials */}
        {connectedOfficials.length > 0 && entity.entity_type !== 'committee' && (
          <section>
            <SectionHeading icon={Users}>Connected Officials</SectionHeading>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {connectedOfficials.map((conn) => {
                const official = conn.connected_entity;
                if (!official) return null;
                const officialMeta = official.metadata as Record<
                  string,
                  unknown
                >;
                return (
                  <Link
                    key={conn.id}
                    href={`/officials/${official.slug}`}
                    className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-money-surface p-4 transition-colors hover:border-money-gold/30 hover:bg-money-surface-elevated"
                  >
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-500/20 text-xs font-bold text-blue-400">
                      {getInitials(official.name)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="truncate text-sm font-medium text-zinc-200">
                          {official.name}
                        </p>
                        {officialMeta?.party != null && (
                          <PartyBadge
                            party={String(officialMeta.party)}
                            className="text-[10px]"
                          />
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <p className="text-xs text-zinc-500">
                          {formatRelationshipType(conn.relationship_type)}
                        </p>
                        {conn.amount_usd != null && conn.amount_usd > 0 && (
                          <MoneyAmount
                            amount={conn.amount_usd}
                            label={conn.amount_label}
                            className="text-xs"
                          />
                        )}
                      </div>
                    </div>
                    <ArrowRight className="h-4 w-4 shrink-0 text-zinc-600" />
                  </Link>
                );
              })}
            </div>
          </section>
        )}

        {/* Type-specific content */}
        {typeData?.kind === 'company' && (
          <CompanyContent
            entity={entity}
            connections={connections}
            stockHolders={typeData.stockHolders}
            donorProfile={typeData.donorProfile}
            lobbyingData={typeData.lobbyingData}
          />
        )}

        {typeData?.kind === 'donor' && (
          <DonorContent
            entity={entity}
            connections={connections}
            recipients={typeData.recipients}
            donorProfile={typeData.donorProfile}
          />
        )}

        {typeData?.kind === 'industry' && (
          <IndustryContent
            entity={entity}
            connections={connections}
            industryData={typeData.data}
          />
        )}

        {typeData?.kind === 'committee' && (
          <CommitteeContent
            connections={connections}
            committeeData={typeData.data}
          />
        )}

        {typeData?.kind === 'bill' && <BillContent entity={entity} />}

        {typeData?.kind === 'fallback' && (
          <section className="rounded-lg border border-zinc-800 bg-money-surface p-8 text-center">
            <Building2 className="mx-auto h-8 w-8 text-zinc-600" />
            <p className="mt-3 text-sm text-zinc-400">
              Data coming soon for this entity type.
            </p>
          </section>
        )}

        {/* All Connections table */}
        {connections.length > 0 && entity.entity_type !== 'committee' && (
          <section>
            <SectionHeading>All Connections</SectionHeading>
            <RelationshipTable relationships={connections} entityId={entity.id} />
          </section>
        )}

        {connections.length === 0 && (
          <div className="rounded-lg border border-zinc-800 bg-money-surface p-12 text-center">
            <Building2 className="mx-auto h-8 w-8 text-zinc-600" />
            <p className="mt-3 text-sm text-zinc-500">
              No connections found for this entity.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
