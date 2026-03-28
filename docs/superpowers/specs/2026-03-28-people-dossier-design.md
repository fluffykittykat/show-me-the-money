# People Dossier: Statistical Influence Signals for Officials

**Date:** 2026-03-28
**Status:** Approved

## Vision

Apply the same rigorous statistical framework from bill dossiers to official pages. Each official gets influence signal cards with rarity context, a percentile comparison against peers, and evidence chains showing the exact government filings.

## Core Principle

Same as bills: **State the fact. Show how rare it is. Link to the source.**

## Page Structure (Top to Bottom)

### 1. Header
- Name, party badge, state, chamber
- Committee list
- Total raised across all cycles (with cycle count)

### 2. Compared to Peers
- Percentile ring: "More influence signals than X% of senators/representatives"
- Compared against same chamber (100 senators or 435 reps)

### 3. Influence Signal Cards (2-column grid)

Same card design as bills. 5 signals, color-coded:

**Signal 1: DONORS LOBBY HIS BILLS (strongest)**
- Test: Do any of this official's donors also appear in LDA lobbying disclosures referencing bills this official sponsored?
- Cross-reference: FEC donated_to → official ← sponsored → bill ← lobbied_on
- Evidence: entity name, donation amount (total + time-scoped within 90 days of bill intro), bill name, LDA filing link, FEC link
- Rarity: "X% of senators/reps show this pattern"

**Signal 2: DONATION TIMING SPIKES**
- Test: Do same-industry donations spike before this official introduces bills?
- Aggregate across ALL bills this official sponsored — compute overall timing pattern
- Compare to baseline for same chamber
- Show multiplier and p-value

**Signal 3: STOCK TRADES IN REGULATED INDUSTRIES**
- Test: Did this official trade stocks in industries their committees regulate?
- Cross-reference: stock_trade relationships → committee_member industry keywords
- Evidence: ticker, buy/sell, amount range, date, matching committee
- Timeline: trades vs committee hearings/bill votes

**Signal 4: COMMITTEE DONORS (context only)**
- Test: Do donors come from industries this official's committees regulate?
- Always marked "EXPECTED" — this is normal fundraising behavior
- Not evidence by itself

**Signal 5: REVOLVING DOOR**
- Test: Are former staffers of this official now registered lobbyists?
- Cross-reference: revolving_door_lobbyist relationships
- Evidence: lobbyist name, former position, current clients
- If lobbyist's clients also donated: elevated signal

### 4. Campaign Finance Trend
- Existing cycle bar chart (kept as-is)
- Clickable bars showing per-cycle donors

### 5. Top Donors
- Existing donor table with additions:
  - **LOBBY+DONATE** badge on donors that also lobbied for bills the official authored
  - **SELF-FUNDED** badge (existing)
  - Time-scoped amount column: "Within 90 days of bill intros"

### 6. Money Trails
- Existing industry-grouped verdict cards (NORMAL/CONNECTED/INFLUENCED/OWNED)
- Kept as-is — these show the broader industry picture

### 7. AI Analysis
- Gold-bordered card
- References statistical data from signals
- Regenerate button

### 8. Data Limitations Footer
- Same as bills

## Evidence View (Expandable)

When user clicks "View evidence" on a signal card, it expands to show:

### For Lobby+Donate:
- Side-by-side layout: "Lobbied for [BILL]" | **AND** | "Donated $X to [OFFICIAL]"
- Timeline: donation date → gap in days → bill introduction date
- Three-column breakdown: Total donated (all time) | Within 90 days of bill intro | Days to bill intro
- Source links: LDA filing, FEC record, bill page
- Everything clickable

### For Stock Trades:
- Trade table: Date, Ticker (mono bold), Company, Buy/Sell (green/red), Amount range, Committee match
- Timeline: trade dots vs committee hearing/bill vote markers
- Source: House Clerk PTR

### For Revolving Door:
- Lobbyist name, former position with official, current employer/clients
- If clients overlap with donors: highlight the connection

## Backend Changes

### New: Official Signal Engine

Create `backend/app/services/official_signals.py` — mirrors `bill_signals.py` but for officials.

```python
async def compute_official_signals(
    session: AsyncSession,
    official_id: uuid.UUID,
    baselines: dict | None = None,
) -> list[dict]:
```

5 signal functions:
- `_signal_donors_lobby_bills()` — cross-reference official's donors with lobbied_on relationships for bills they authored
- `_signal_timing_spike()` — aggregate timing analysis across all bills this official sponsored
- `_signal_stock_committee()` — stock trades in committee-regulated industries
- `_signal_committee_donors()` — committee jurisdiction overlap (always "Expected")
- `_signal_revolving_door()` — former staffers now lobbying

### New: Pre-compute Official Signals

Add to `precompute.py` or create new job that:
1. Computes signals for all 500 officials
2. Stores in `bill_influence_signals` table (reuse — signal_type distinguishes) OR new `official_influence_signals` table
3. Computes percentile rank within chamber

Decision: **Use separate table** `official_influence_signals` with same schema as `bill_influence_signals` but `official_id` instead of `bill_id`. This keeps queries clean.

### Update V2 Official API

`GET /v2/official/{slug}` adds:
```json
{
  ...existing fields...,
  "influence_signals": [...],
  "percentile_rank": 87,
  "peer_count": 100,
  "peer_group": "senators"
}
```

## Implementation Phases

### Phase 1: Official Signal Engine
- Create official_signals.py with all 5 detectors
- Create official_influence_signals DB table
- Pre-compute for all officials

### Phase 2: Update V2 API
- Add signals to /v2/official/{slug} response
- Add percentile rank

### Phase 3: Frontend
- Add signal cards to official page (same component as bills)
- Add percentile ring
- Add evidence expandable views
- Add LOBBY+DONATE badges to donor table
