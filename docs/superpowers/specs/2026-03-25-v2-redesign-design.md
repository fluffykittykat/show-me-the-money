# V2 Redesign: "Follow the Money" — Story-First Political Intelligence

**Date:** 2026-03-25
**Status:** Approved
**Branch:** v2

## Vision

Reimagine the UI around **stories, not data dumps**. Every page tells a narrative: who gave money, where it went, what legislation resulted, and how bought the official is. The algorithm counts connected dots — not opinions — to determine influence levels. Everything is fact-based, sourced from public government databases, and verifiable by the user.

## Target Audience (Priority Order)

1. **Journalists** investigating corruption stories — need evidence chains they can cite
2. **Voters** researching candidates — need plain English conclusions
3. **Activists/watchdogs** tracking systemic influence — need patterns across officials

## Core Design Decisions

### 1. Story-First Money Trails (not data tables)

Each official's page tells **stories grouped by industry** with clear verdicts. No tabs, no hunting — scroll to investigate. Each money trail is a self-contained, shareable story card with:
- Color-coded verdict (NORMAL / CONNECTED / INFLUENCED / CAPTURED)
- The full chain visualization: SOURCE → MIDDLEMAN → OFFICIAL → COMMITTEE → LEGISLATION
- Plain English narrative
- Every entity name clickable for deeper investigation

### 2. The "Gotcha" Detection Algorithm — 4 Levels

The algorithm doesn't guess — it counts connected dots from verified public data.

**🟢 NORMAL (1 dot)**
- Official receives campaign donations
- Required: Donor → Official (FEC Schedule A)
- This alone means nothing. Everyone gets donations.

**🟡 CONNECTED (2 dots)**
- Donor operates in industry the official's committee regulates, OR donor also lobbies Congress
- Required: Donor → Official (FEC) AND Official on regulating committee (Congress.gov) or Donor lobbies (Senate LDA)
- The structural relationship exists. Worth noting.

**🔴 INFLUENCED (3+ dots)**
- Money trail connects through to legislation. Money in, favorable bills out.
- Required: Donor → Official (FEC) AND regulating committee (Congress.gov) AND official sponsors aligned bills (Congress.gov)
- Bonus severity: donor lobbies those bills (LDA), money via middleman PAC, multiple donors same industry
- The chain is complete.

**⚫ CAPTURED (4+ dots, multi-industry)**
- Full machine visible across multiple industries. Same playbook repeated.
- Required: Full INFLUENCED chain AND pattern repeats across 2+ industries
- When multiple industries run the same play, the official isn't leading — they're being led.

**Key principle:** The AI (Sonnet) narrates the pattern in plain English. But the verdict comes from the data, not the AI. The AI makes it readable.

### 3. Homepage: Search + Story Feed

- **Top:** Big search bar for journalists who know what they're looking for
- **Below:** Story feed showing the most compelling money trails — like a news feed
- **Each story:** Complete narrative with verdict, chain visualization, and affected officials
- **4 highlight cards:** Most Bought, Biggest Middleman, Darkest Trail, Revolving Door
- No clutter. Fast load. Draws users in with stories.

### 4. Official Page: Vertical Scroll Investigation

No tabs. Everything scrolls vertically:

1. **Header** — Name, party, state, committees, campaign total (with FEC cycle year)
2. **AI Assessment** — Compact gold-accented summary (the hook). Regenerate button.
3. **Money Trails** — Color-coded story cards with verdicts and chain visualizations
4. **Top Donors** — Table with verdict tags per donor, amounts, aggregated
5. **Middleman Section** — PACs that funnel money, who funds them, how much reached the official
6. **Refresh Investigation** — Live progress panel showing each step

### 5. Bill Page: Who Benefits

- Status badge (BECAME LAW / IN COMMITTEE / PASSED / FAILED)
- TLDR + expandable CRS summary
- Who supports this bill — sponsors with party badges + their top donors + verdicts
- AI assessment connecting sponsors' funding to the bill's policy area
- Every sponsor clickable → their profile

### 6. Entity Page (PAC/Company): Money In vs Money Out

- Split view: **Money In** (who funds it) | **Money Out** (who it funds)
- The middleman story told visually
- "THE QUESTION" — provocative framing of what the pattern suggests
- Auto-fetch PAC donors from FEC on first visit, cache for future
- AI assessment

### 7. Everything Clickable (OLAP Principle)

Every data point is a doorway:
- Official name → their full profile with money trails
- Donor/company name → entity page showing all officials they fund
- Bill name → bill investigation page with sponsors and their donors
- Committee name → committee page showing members and jurisdiction
- Dollar amount → the specific FEC filing
- Industry label → all money flowing from that industry
- PAC name → who funds the PAC and who it funds

## Performance Architecture

### The Problem (v1)
- 10+ sequential API calls per official page
- AI briefing blocks rendering (10s on first visit)
- Homepage conflict scan takes 4s uncached
- PAC donor lookups hit FEC live (2s+ spinner)

### The Solution: Pre-Compute Everything

**Background Jobs (every 6 hours):**
- Compute money trails for all officials
- Generate verdicts (NORMAL/CONNECTED/INFLUENCED/CAPTURED)
- Pre-generate AI briefings via Sonnet
- Build homepage story feed
- Cache conflict scores
- Resolve and cache PAC donors

**Fast API (< 50ms per page):**
- Single API call per page: GET /v2/official/{slug} returns everything
- All data pre-joined and pre-computed
- No live FEC calls at page load
- No AI generation at page load
- Skeleton → content rendering (no layout shift)

**Result: Every page loads in < 100ms**

### Live Refresh (User-Initiated)

The "Refresh Investigation" button triggers a live investigation with step-by-step progress via Server-Sent Events (SSE):

1. ✓ Resolving FEC Committee ID → C00213512
2. ✓ Fetching campaign totals (2024, 2022, 2020, 2018) → $10.2M
3. ✓ Fetching 2024 cycle donors → 23 donors
4. ✓ Fetching 2022 cycle donors → 18 donors
5. ● Tracing middleman PAC donors... → Nancy Pelosi Victory Fund
6. ○ Computing money trails & verdicts
7. ○ Detecting conflict patterns
8. ○ Generating AI assessment (Sonnet)

After completion: green toast with summary + freshness badges per data source.

## Data Sources — All Public, All Verifiable

| Source | Data | API |
|--------|------|-----|
| FEC.gov | Campaign donations, PAC contributions, committee transfers, candidate totals | api.open.fec.gov |
| Congress.gov | Committee assignments, sponsored bills, bill text & status | api.congress.gov/v3 |
| Senate LDA | Lobbying filings, revolving door disclosures, client-lobbyist relationships | lda.senate.gov/api |
| congress-legislators | Bioguide → FEC ID crosswalk (100% match accuracy) | GitHub YAML |

**Every claim on the site links to its source.** Dollar amounts link to FEC filings. Committee assignments link to Congress.gov. Lobbying data links to Senate LDA records.

## Data Freshness Strategy

- FEC totals: Check cycles 2024, 2022, 2020, 2018 — use highest (best cycle)
- Donors: Fetch 2024 + 2022 cycles, store dates on each record
- Bills: Enriched from Congress.gov with CRS summaries and text URLs
- Lobbying: 2024-2025 filings from Senate LDA
- Committees: Current assignments from congress-legislators YAML
- Show cycle year on all totals for context
- "Incomplete data" indicator when coverage gaps exist
- Refresh button on every page for user-initiated updates

## Tech Stack (Unchanged)

- Frontend: Next.js 14, TypeScript, Tailwind CSS
- Backend: FastAPI + async SQLAlchemy
- Database: PostgreSQL 16
- AI: Claude Sonnet 4 via Anthropic SDK
- Orchestration: pm2, nginx

## What Carries Forward from V1

- AI-generated FBI-style briefings (Sonnet)
- Refresh Investigation button (enhanced with live progress)
- All data: 499 officials, 15K+ bills, 6.5K+ donor records, 53K+ relationships
- FEC/Congress.gov/LDA integrations
- PAC donor auto-fetch
- Party committee money trail (middleman detection)
- Revolving door data
- OLAP click-through navigation

## What Changes in V2

- Tabs → single vertical scroll
- Generic conflict labels → 4-level verdict system (NORMAL/CONNECTED/INFLUENCED/CAPTURED)
- Data tables → story cards with chain visualizations
- Multiple API calls → single pre-computed response per page
- Loading spinners → skeleton → instant content
- Stale data → freshness badges + live refresh with progress
- "Everyone looks corrupt" → graduated levels showing where money trails get dark
