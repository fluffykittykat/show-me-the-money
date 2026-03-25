# V2 Frontend: Story-First Redesign

**Date:** 2026-03-25
**Status:** Approved
**Depends on:** V2 Backend (pre-compute engine + v2 API endpoints) — ✅ Complete

## Overview

Full in-place rewrite of the Next.js frontend to implement the story-first, vertical-scroll design from the [V2 Redesign Spec](2026-03-25-v2-redesign-design.md). Every page tells a narrative backed by pre-computed data served via single v2 API calls. No tabs, no data dumps — scroll to investigate.

## Tech Stack (Unchanged)

- Next.js 16 (App Router), React 19, TypeScript 5.9
- Tailwind CSS v4 (custom dark theme with gold accent)
- Lucide React icons
- No new dependencies

## Architecture

### Data Flow

```
v2 API (single call) → page component → section components → UI primitives
```

Each page makes **one** fetch to its v2 endpoint. The response contains everything needed to render. No waterfalls, no lazy background fetches.

### API Client

Add v2 functions to existing `lib/api.ts`:

```typescript
// V2 API functions — single response per page
export async function getV2Official(slug: string): Promise<V2OfficialResponse>
export async function getV2Bill(slug: string): Promise<V2BillResponse>
export async function getV2Entity(slug: string): Promise<V2EntityResponse>
export async function getV2Homepage(): Promise<V2HomepageResponse>
```

### Types

Add v2 types to existing `lib/types.ts`:

```typescript
// --- Money trail (from MoneyTrail DB model) ---

interface V2MoneyTrail {
  industry: string
  verdict: 'NORMAL' | 'CONNECTED' | 'INFLUENCED' | 'OWNED'
  dot_count: number
  dots: string[]                // e.g. ["donor_from_industry", "regulating_committee", "sponsored_aligned_bills"]
  narrative: string
  total_amount: number          // cents
  chain: {                      // NOTE: chain sub-fields are optional — may be empty objects/arrays
    donors?: Array<{ name: string; slug: string; amount: number }>
    committees?: Array<{ name: string; slug: string }>
    bills?: Array<{ name: string; slug: string }>
    middlemen?: Array<{ name: string; slug: string; amount_in: number; amount_out: number }>
    lobbying?: Array<{ firm: string; client: string; issue: string }>
    dots?: string[]             // sometimes duplicated here from top-level dots
  }
}

// --- Official page (matches GET /v2/official/{slug}) ---

interface V2OfficialResponse {
  entity: Entity
  overall_verdict: string       // "NORMAL" | "CONNECTED" | "INFLUENCED" | "OWNED" | "MISSING"
  total_dots: number
  money_trails: V2MoneyTrail[]
  top_donors: Array<{
    slug: string
    name: string
    entity_type: string         // "pac", "company", "person", etc.
    total_donated: number       // cents
  }>
  middlemen: Array<{            // subset of top_donors where entity_type == "pac"
    slug: string
    name: string
    entity_type: string
    total_donated: number
  }>
  committees: Array<{
    slug: string
    name: string
    role: string                // "Member", "Chair", "Ranking Member", etc.
  }>
  briefing: string | null
  freshness: {
    fec_cycle: string | null
    last_refreshed: string | null
    has_donors: boolean
    has_committees: boolean
  }
}

// --- Bill page (matches GET /v2/bill/{slug}) ---

interface V2BillResponse {
  entity: Entity
  status_label: string          // "BECAME LAW" | "IN COMMITTEE" | "PASSED" | "FAILED" | "INTRODUCED"
  sponsors: Array<{
    slug: string
    name: string
    party: string
    state: string
    role: string                // "sponsored" or "cosponsored"
    top_donor: string | null
    verdict: string | null      // from entity metadata v2_verdict
  }>
  briefing: string | null
}

// --- Entity page (matches GET /v2/entity/{slug}) ---

interface V2EntityResponse {
  entity: Entity
  money_in: Array<{
    slug: string
    name: string
    entity_type: string
    amount_usd: number
    amount_label: string | null
  }>
  money_out: Array<{
    slug: string
    name: string
    entity_type: string
    amount_usd: number
    amount_label: string | null
  }>
  briefing: string | null
}

// --- Homepage (matches GET /v2/homepage) ---

interface StoryCard {
  story_type: string            // "owned" | "influenced" | "middleman" | "revolving_door"
  headline: string
  narrative: string
  verdict: string               // "OWNED" | "INFLUENCED" | "MIDDLEMAN" | "REVOLVING_DOOR"
  officials: Array<{ name: string; slug: string; party: string }>
  total_amount: number          // cents
  industry: string
}

interface V2HomepageResponse {
  top_stories: StoryCard[]
  stats: {
    officials_count: number
    bills_count: number
    donations_total: number     // cents (Decimal from DB, serialized as int)
    relationship_count: number
  }
  top_officials: Array<{
    slug: string
    name: string
    party: string
    state: string
    verdict: string             // "NORMAL" | "CONNECTED" | "INFLUENCED" | "OWNED"
    dot_count: number
  }>
  top_influencers: Array<{
    slug: string
    name: string
    entity_type: string         // "pac", "company", etc.
    total_donated: number       // cents
    officials_funded: number
  }>
  revolving_door: Array<{
    lobbyist_name: string
    lobbyist_slug: string
    former_position: string
    current_employer: string
    official_name: string
    official_slug: string
    official_party: string
    official_state: string
  }>
}
```

## Pages

### 1. Homepage (`app/page.tsx`)

Replaces the current multi-section dashboard with a focused story feed.

**Sections (top to bottom):**

1. **Hero** — "Follow the Money" + search bar + quick links
2. **4 Highlight Cards** — Derived client-side from homepage response:
   - Most Bought: `top_officials[0]` (highest dot_count)
   - Biggest Trail: first `top_stories` item with `story_type == "influenced"` (highest amount)
   - Biggest Middleman: first `top_stories` item with `story_type == "middleman"`
   - Revolving Door: `revolving_door.length` count + first entry
3. **Story Feed** — Pre-computed story cards from `top_stories`, each with headline, verdict badge, narrative, and linked officials
4. **Stats Bar** — Officials, Bills, Donations, Relationships (from `stats` object)
5. **Two-Column** — Top Officials by Verdict (from `top_officials`) | Top Influencers by Amount (from `top_influencers`)

**Data source:** `GET /v2/homepage`

**Reused components:** SearchBar, MoneyAmount, LoadingState
**Deleted:** USMap, DidYouKnow, ActiveBills rotating carousel

### 2. Official Page (`app/officials/[slug]/page.tsx`)

Replaces the tabbed multi-fetch page with vertical scroll, single fetch.

**Sections (top to bottom):**

1. **Header** — Name, party badge, state, chamber, committees, overall verdict pill with dot indicators, campaign total with cycle year
2. **AI Assessment** — Gold-accented card with briefing text + regenerate button
3. **Money Trails** — Story cards per industry, each with:
   - Industry name + dot indicators + verdict badge
   - Chain visualization: SOURCE → MIDDLEMAN → OFFICIAL → COMMITTEE → LEGISLATION (styled nodes with arrows, every name clickable)
   - Plain English narrative with dollar amounts highlighted
4. **Top Donors** — Table with columns: Donor (clickable), Entity Type, Total Donated. Note: the backend returns `entity_type` and `total_donated` per donor but not industry or verdict — those can be cross-referenced client-side from `money_trails` chain data if needed, or displayed without them.
5. **Middlemen** — Subset of top_donors where `entity_type == "pac"`. Show as cards with PAC name and total donated amount. Note: the backend currently returns the same shape as top_donors for middlemen (no separate money_in/money_out). Display `total_donated` as the primary metric.
6. **Refresh Investigation** — Button + freshness badges (FEC cycle, last refreshed, data completeness)

**Data source:** `GET /v2/official/{slug}`

**Chain visualization approach:** Styled CSS nodes connected by arrows. Each node shows label (Donor/Middleman/Official/Committee/Legislation), name (clickable link), and amount. Horizontal layout, wraps on mobile. No external library needed.

**Reused components:** PartyBadge, MoneyAmount, LoadingState
**Deleted:** TabNav, ConflictCard, DonationTimeline, EvidenceChain, SharedDonorNetwork, all "Hidden Connections" section components

### 3. Bill Page (`app/bills/[slug]/page.tsx`)

**Sections:**

1. **Header** — Bill number, title, status badge (color-coded)
2. **AI Assessment** — Gold card with briefing
3. **Sponsors** — Cards for each sponsor showing: name (clickable), party badge, state, their top donor, their verdict badge
4. **Summary** — Bill description/CRS summary if available

**Data source:** `GET /v2/bill/{slug}`

### 4. Entity Page (`app/entities/[type]/[slug]/page.tsx`)

For PACs, companies, organizations. The `[type]` URL segment is cosmetic (for readable URLs) — the API call uses only `slug`.

**Sections:**

1. **Header** — Entity name, type badge (derived from `entity.entity_type`)
2. **AI Assessment** — Gold card with briefing (if `briefing` is non-null; otherwise show "Generate briefing" button)
3. **Split View** — Money In (who funds this entity) | Money Out (who this entity funds). Each side is a list of rows with name (clickable), amount (`amount_usd`), entity type badge. Use `amount_label` as fallback display when `amount_usd` is 0.

**Data source:** `GET /v2/entity/{slug}`

### 5. Supporting Pages

**Officials List (`app/officials/page.tsx`):**
- Keep existing browse/filter functionality
- Add verdict badge next to each official name
- Sort by verdict severity by default

**Bills List (`app/bills/page.tsx`):**
- Keep existing list
- Add sponsor verdict info

**Search (`app/search/page.tsx`):**
- Keep existing search, no changes needed

**Trades (`app/trades/page.tsx`):**
- Keep as-is (Phase 2 per spec)

## New Components

| Component | Purpose | Used By |
|-----------|---------|---------|
| `VerdictPill` | Color-coded verdict badge with dot indicators | Official page header, story cards |
| `VerdictBadge` | Small inline verdict tag (no dots) | Donor table, story feed, officials list |
| `MoneyTrailCard` | Story card for one industry trail | Official page |
| `ChainVisualization` | SOURCE → MIDDLEMAN → OFFICIAL → COMMITTEE → LEGISLATION | MoneyTrailCard |
| `StoryCard` | Homepage story feed card | Homepage |
| `HighlightCard` | Stat card with label, name, detail, verdict | Homepage |
| `AIBriefing` | Gold-accented briefing card with regenerate | All pages |
| `MiddlemanCard` | Money in → money out display | Official page, entity page |
| `FreshnessBar` | Data freshness badges | Official page |
| `MoneyFlow` | Split money in/out view | Entity page |

## Components Reused From V1

| Component | Changes |
|-----------|---------|
| `SearchBar` | No changes |
| `PartyBadge` | No changes |
| `MoneyAmount` | No changes |
| `LoadingState` | No changes |
| `Header` | Minor: update nav links |
| `Footer` | No changes |
| `StatBar` | Adapt for v2 stats shape |

## Components Deleted

These v1 components are replaced by the new story-first design:

- `TabNav` — replaced by vertical scroll
- `ConflictCard`, `ConflictBadge` — replaced by VerdictPill/VerdictBadge
- `DonationTimeline` — removed (may revisit in Phase 2)
- `EvidenceChain` — replaced by ChainVisualization
- `SharedDonorNetwork` — removed
- `USMap` — removed from homepage
- `DidYouKnow` — removed
- `RelatedInsights` — removed
- `ConnectionsPanel` — replaced by money trails
- `HiddenConnectionsCard` — removed
- `RevolvingDoorSection`, `FamilyConnectionsSection`, `OutsideIncomeSection`, `ContractorDonorsSection`, `TradeTimingSection` — removed (data now in money trails)
- `RelationshipSpotlight`, `LobbyingTab` — removed
- `FinancialTable`, `DonorTable`, `BillsTable`, `RelationshipTable` — replaced by simpler inline tables

## Visual Design

### Color System (Unchanged)

- Background: `#09090b` (zinc-950)
- Surface: `#18181b` (zinc-900)
- Elevated: `#27272a` (zinc-800)
- Text primary: `#f4f4f5`
- Text secondary: `#a1a1aa`
- Accent: `#f59e0b` (amber-500 / money-gold)
- Party: Democrat `#3b82f6`, Republican `#ef4444`, Independent `#a855f7`

### Verdict Colors

| Verdict | Background | Text | Border |
|---------|-----------|------|--------|
| NORMAL | `rgba(16,185,129,0.15)` | `#34d399` | `rgba(16,185,129,0.4)` |
| CONNECTED | `rgba(245,158,11,0.15)` | `#fbbf24` | `rgba(245,158,11,0.4)` |
| INFLUENCED | `rgba(239,68,68,0.15)` | `#f87171` | `rgba(239,68,68,0.4)` |
| OWNED | `rgba(0,0,0,0.5)` | `#f4f4f5` | `#71717a` |

### Typography

- Headings: System UI, weight 700-800
- Body: System UI, weight 400
- Amounts: Gold (#fbbf24), weight 600
- Labels: Uppercase, letter-spacing 0.05em, zinc-500

### Spacing

- Page max-width: 900px, centered
- Section gap: 32px
- Card padding: 20px
- Card border-radius: 12px

## Error, Loading, and Empty States

**Loading:** Each page shows a skeleton layout matching the final structure (header skeleton, card skeletons, table row skeletons). Use the existing `LoadingState` component pattern. No layout shift on content load.

**404 / Not Found:** If the v2 API returns 404, show a centered message: "Official not found" / "Bill not found" / "Entity not found" with a link back to search.

**Empty money_trails:** If `money_trails` is an empty array, show: "No money trails computed yet. Try refreshing the investigation." with the refresh button.

**Null briefing:** If `briefing` is null, show the AIBriefing card with a "Generate briefing" button instead of text. Clicking triggers a POST to regenerate.

**Empty top_stories:** If homepage `top_stories` is empty, hide the story feed section entirely and show the stats bar + two-column layout immediately.

## Naming Note

The fourth verdict level is called **OWNED** in the backend and throughout this spec. The original V2 redesign spec used "CAPTURED" in some places — these refer to the same concept. OWNED is canonical.

## What This Does NOT Include

- Stock trades page redesign (Phase 2)
- Real-time SSE refresh progress UI (keep simple button for now, add SSE later)
- Mobile-specific layouts beyond basic responsive (Tailwind breakpoints handle this)
- New data fetching for v1 endpoints (v2 API only)
- Admin page changes
