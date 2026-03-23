# Investigative Framework Design

**Date:** 2026-03-22
**Status:** Approved
**Scope:** Conflict detection engine, money trail analysis, bill investigation pages, voting record ingestion, profile redesign with conflict alerts

## Overview

Build the core investigative engine for Jerry Maguire. The primary question: **"Who paid for this?"**

Every page helps pull the thread: `Bill → YES voters → Their donors → Industries → Did those industries benefit? → Flag`

## Scope Decision

**Data scope:** Fetterman + all members of his 3 committees (Banking, Agriculture, Joint Economic). This gives us ~40-60 senators with overlapping donors/committees for meaningful conflict detection and shared donor networks.

## Backend Changes

### 1. Voting Record Ingestion (Sub-agent B)

For each member in `entities` where `entity_type = 'person'`, fetch votes from Congress.gov:
```
GET /v3/member/{bioguideId}/votes?api_key={KEY}&format=json&limit=50
```

For each bill entity, fetch actions:
```
GET /v3/bill/{congress}/{type}/{number}/actions?api_key={KEY}&format=json
```

**Bill metadata enrichment:**
- `tldr`: 1-2 sentence plain English summary via `claude` CLI subprocess
- `full_text_url`: From `GET /v3/bill/{congress}/{type}/{number}/text` — prefer HTML over PDF
- `official_summary`: From `GET /v3/bill/{congress}/{type}/{number}/summaries` — CRS summary text

**Committee member ingestion:**
- For each of Fetterman's 3 committees, fetch members from Congress.gov
- Create person entities for each member
- Ingest their: Congress.gov data, FEC contributions, stock holdings (Senate eFD)
- Store votes as relationships: `voted_yes`, `voted_no`, `voted_present`

Use upsert pattern — idempotent, safe to rerun.

### 2. Conflict Detection Engine (Sub-agent A)

New file: `backend/app/services/conflict_engine.py`

**ConflictSignal dataclass:**
- entity_slug, conflict_type, severity, description, evidence[], related_entities[]

**Conflict types:**
- `committee_donor`: Senator on committee regulating industries that donated to them
- `stock_vote`: Senator holds stock in companies they voted to benefit
- `donor_vote`: Industry donated before a key vote, senator voted in their favor
- `full_alignment`: All signals present — committee + stock + donor + vote

**Severity scoring:**
- 1 signal = LOW
- 2 signals = MEDIUM
- 3 signals = HIGH
- 4 signals = CRITICAL

**Key functions:**
- `detect_conflicts(session, entity_slug)` → list[ConflictSignal]
- `get_bill_money_trail(session, bill_slug)` → money trail dict
- `get_industry_legislation(session, industry)` → industry funding dict

**Narrative generation:** Uses `claude` CLI subprocess:
```python
subprocess.run(["claude", "-p", "--dangerously-skip-permissions", prompt], capture_output=True, text=True, timeout=60)
```

### 3. New API Endpoints

New router: `backend/app/routers/investigation.py`

```
GET /investigate/bill/{slug}          — full money trail for a bill
GET /investigate/conflicts/{slug}     — conflict signals for a person
GET /investigate/industry/{industry}  — what legislation did this industry fund
GET /investigate/timeline/{slug}      — donation → vote timeline for a senator
GET /investigate/network/{slug}       — shared donor network
```

Response shapes as specified in the original requirements (see project prompt).

### 4. Database Changes

Add to relationships metadata:
- `conflict_flagged: boolean` — pre-computed conflict flag
- `days_before_vote: integer` — for donations, days before related vote

New SQL view `money_trail` joining bills → votes → donors for efficient queries.

New migration for the view + any new indexes needed.

## Frontend Changes

### 5. Bill Investigation Page (Sub-agent C)

New page: `frontend/app/bills/[slug]/page.tsx`

**Sections:**
1. Bill header: title, number, congress, status badge, conflict score badge
2. "Follow the Money" hero panel: dark card with gold border, total money to YES voters, donation timing
3. Vote breakdown: YES/NO columns with senator cards showing donor industries
4. Industry money flow: ranked list of industries funding YES votes
5. "Why This Matters": AI narrative (2-3 sentences, FBI analyst voice)
6. **Bill Text tab**: TLDR prominently at top, official CRS summary, link to full text on congress.gov

### 6. Profile Redesign + Conflict Alerts (Sub-agent D)

**Redesign `frontend/app/officials/[slug]/page.tsx`:**

New first tab: "Conflicts & Alerts"
- Conflict alert cards with severity badges (LOW=gray, MEDIUM=yellow, HIGH=orange, CRITICAL=red)
- Evidence chains: Stock → Committee → Vote → Donation
- Source citations

"Investigator's Summary" section replacing current briefing — FBI analyst perspective.

**Money Timeline component:** Donation dates → vote dates, flag donations within 90 days before vote.

**Shared Donor Network:** Other senators receiving money from same sources.

**Updated existing tabs:**
- Financial: "Potential Conflict" flags next to holdings
- Campaign Finance: "Pre-Vote Donations" section (within 90 days)
- Legislative: "Donor Beneficiary" flags

### 7. New Components

- `ConflictCard.tsx` — severity-colored alert card
- `MoneyTrail.tsx` — vertical chain: industry → senator → bill → beneficiary
- `DonationTimeline.tsx` — chronological donation → vote timeline
- `InvestigatorSummary.tsx` — FBI-style briefing with citations
- `SharedDonorNetwork.tsx` — shared donor connections
- `ConflictBadge.tsx` — reusable severity indicator
- `BillVoteBreakdown.tsx` — YES/NO columns with donor context
- `BillTextPanel.tsx` — TLDR + official summary + full text link

### 8. Navigation Updates

- Header: add "Investigate" nav item linking to bills/investigations
- Homepage: "Active Investigations" section with featured conflict

## Tone & Copy Guidelines

Investigator's lens throughout:
- "Money received from" not "Campaign contributions"
- "Financial interests in" not "Stock holdings"
- "Intelligence Summary" not "Briefing"
- Factual, documented, cited — not accusatory

## Quality Standards

- All queries use indexed columns
- Max 2 DB queries per page load (use joins)
- O(1) or O(log n) lookups
- Conflict detection pre-computed on ingestion
- Dark theme, gold accents
- Mobile responsive
