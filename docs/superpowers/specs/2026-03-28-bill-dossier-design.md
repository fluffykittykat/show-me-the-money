# Bill Dossier: Statistical Correlation Engine + UI

**Date:** 2026-03-28
**Status:** Approved

## Vision

Transform bill pages from sparse metadata displays into comprehensive dossiers that use statistical correlation to surface influence signals. Every claim is fact-based, sourced from public government databases, and compared against a baseline of similar bills.

## Core Principle

**State the fact. Show how rare it is. Link to the source. Let the reader decide.**

We never say "corrupt." We say "this pattern occurs in 2% of agriculture bills." The math is real. The data is public. The conclusion is the reader's.

## Page Structure (Top to Bottom)

### 1. Bill Header
- Status badge (IN COMMITTEE / PASSED / BECAME LAW / FAILED)
- Policy area tag
- Bill number, congress, introduced date
- Plain English summary: what this bill does, who it affects, written so anyone can understand
- Links: Congress.gov, Full Text

### 2. Compared to Similar Bills
- Percentile rank among bills in the same policy area
- "More influence signals than 94% of agriculture bills"
- Ring chart showing percentile visually
- Comparison count: "Compared against 842 agriculture bills in database"

### 3. Influence Signal Cards (2-column grid)

Five signals, each in its own card. Cards are color-coded by finding:
- **Red glow + "RARE" badge** — signal found, statistically unusual
- **Amber + multiplier badge** — signal found, above baseline
- **Gray + "EXPECTED" badge** — signal found but normal for this context
- **Green accent + "CLEAR" badge** — signal NOT found (counter-evidence)

#### Signal 1: Lobby + Donate (weight: highest)
- **Test:** Did any entity BOTH file an LDA lobbying disclosure listing this bill AND donate to the bill's sponsors?
- **Data:** Senate LDA filings (parse bill numbers from lobbying_activities.description) cross-referenced with FEC donated_to relationships
- **Rarity:** Compare against all bills in same policy area. "Found in X% of [policy area] bills"
- **Display:** Entity name, lobbying filing reference, donation amount, sponsor name, source links

#### Signal 2: Timing Spike (weight: high)
- **Test:** Did same-industry donations to sponsors spike in the 90 days before bill introduction?
- **Data:** FEC donation dates + bill introduced_date from Congress.gov + industry keyword matching
- **Statistical test:** Compare observed count of same-industry donations within 90 days to the baseline rate for this policy area. Report as multiplier (e.g., "4.2x above baseline") with p-value.
- **Time decay:** Donations closer to intro date weighted higher. 30 days = strong, 60 days = moderate, 90 days = weak.
- **Display:** Mini timeline visualization showing donation dots relative to bill intro date
- **Filter out:** Platform PACs (WINRED, ActBlue) — they donate to everyone and are not industry-specific signals

#### Signal 3: Committee Jurisdiction (weight: low, context only)
- **Test:** Does the sponsor sit on a committee with jurisdiction over this bill's policy area?
- **Data:** Committee assignments from Congress.gov + bill policy_area
- **Display:** Always shown but marked "EXPECTED" — this is normal for committee members
- **Note:** This alone is NOT evidence of influence. Only meaningful when combined with Signal 1 or 2.

#### Signal 4: Stock Trades (weight: high when found)
- **Test:** Did any sponsor trade stocks in companies that would be affected by this bill within 60 days of introduction or committee action?
- **Data:** House Clerk periodic transaction reports (stock_trade relationships) + bill policy area industry matching
- **Display:** Ticker, buy/sell, amount range, date, days relative to bill action
- **Note:** Senate stock trades not yet integrated — disclose this limitation

#### Signal 5: Revolving Door (weight: moderate)
- **Test:** Are any registered lobbyists who lobby on this bill's policy area former staffers of the bill's sponsors?
- **Data:** revolving_door_lobbyist relationships + LDA lobbying issue areas
- **Display:** Lobbyist name, former position, current lobbying client

### 4. Who Wrote This Bill (Sponsor Cards)

Layered card design per sponsor:

**Top tier: "Verified Connections to This Bill"**
- Only shows money where we have a PROVEN lobby+donate match
- Red dot + entity name + "lobbied + donated" + amount
- Source links to LDA filing and FEC record

**Bottom tier: "Broader Context"**
- Same-industry donations within 90 days (with amount)
- Career total PAC money (clearly labeled as career total, not bill-specific)
- Committee membership
- "Full investigation →" link to official's dossier page

Expandable list for cosponsors: "Show all 147 cosponsors →"

### 5. AI Analysis Card
- Gold-bordered card at bottom
- The AI prompt receives the computed signal data and MUST:
  - Start with a plain English summary of what the bill does
  - Reference actual statistics: "2% of agriculture bills", "4.2x above baseline", "p = 0.03"
  - Note what was NOT found (counter-evidence shows balance)
  - Never say "corrupt" — say "statistically unusual" or "this pattern is rare"
  - End with a bottom line that states facts and lets the reader decide
- Regenerate button

### 6. Data Limitations Footer
Always visible, never hidden:
- FEC donations over $200 only
- Senate stock trades not yet integrated
- Industry matching via keyword analysis (may misclassify)
- Lobbying data from Senate LDA quarterly filings (some may not yet be available)
- Link to full methodology page

## New Data Pipeline: LDA Bill Number Parsing

### What needs to be built

The Senate LDA API returns lobbying filings with `lobbying_activities[].description` fields that contain bill numbers as free text (e.g., "H.R. 7521", "S. 3689"). We need to:

1. **Re-ingest LDA filings** with bill number extraction
2. **Parse bill numbers** from description text using regex: `(?:H\.?R\.?|S\.?|H\.?\s*Res\.?|S\.?\s*Res\.?)\s*\d{1,5}`
3. **Create relationships:** `lobbied_on` from lobbying_client entity → bill entity
4. **Cross-reference:** For each `lobbied_on` relationship, check if the same client (or their PAC) has a `donated_to` relationship with any of the bill's sponsors
5. **Store results** in a new `bill_influence_signals` table for fast serving

### bill_influence_signals Table

```
id: UUID
bill_id: UUID (FK → entities)
signal_type: VARCHAR (lobby_donate, timing_spike, committee_overlap, stock_trade, revolving_door)
confidence: FLOAT (0.0–1.0, based on statistical test)
rarity_pct: FLOAT (what % of same-policy bills show this pattern)
evidence: JSONB (entities involved, amounts, dates, source URLs)
computed_at: TIMESTAMP
```

### Statistical Baseline Computation

For each policy area, pre-compute:
- Baseline rate of lobby+donate matches
- Baseline rate of same-industry donations within 90 days
- Average number of same-industry donations per bill
- These baselines are used to compute rarity percentages and p-values

## V2 API Endpoint

`GET /v2/bill/{slug}` should return:

```json
{
  "entity": { ... },
  "summary": "Plain English description",
  "status_label": "IN COMMITTEE",
  "policy_area": "Agriculture and Food",
  "percentile_rank": 94,
  "similar_bill_count": 842,
  "influence_signals": [
    {
      "type": "lobby_donate",
      "found": true,
      "rarity_label": "Rare",
      "rarity_pct": 2.0,
      "description": "Same entity lobbied for this bill AND donated to its sponsor",
      "evidence": {
        "entity_name": "American Farm Bureau Federation",
        "lobbied_bill": "HR 1107",
        "donated_amount": 1500000,
        "donated_to": "Rep. Curtis (R-UT)",
        "lda_filing_url": "...",
        "fec_url": "..."
      }
    },
    {
      "type": "timing_spike",
      "found": true,
      "rarity_label": "4.2x",
      "rarity_pct": null,
      "p_value": 0.03,
      "baseline_rate": 1.2,
      "observed_rate": 5,
      "description": "Agriculture PAC donations spiked before bill introduction",
      "evidence": {
        "donations": [
          {"donor": "...", "amount": 1500000, "date": "2024-12-15", "days_before": 31}
        ]
      }
    },
    {
      "type": "committee_overlap",
      "found": true,
      "rarity_label": "Expected",
      "description": "Sponsor sits on Agriculture Committee"
    },
    {
      "type": "stock_trade",
      "found": false,
      "rarity_label": "Clear",
      "description": "No suspicious stock trades detected"
    },
    {
      "type": "revolving_door",
      "found": false,
      "rarity_label": "Clear",
      "description": "No revolving door connections found"
    }
  ],
  "sponsors": [
    {
      "name": "John Curtis",
      "slug": "curtis-john-r",
      "party": "R",
      "state": "UT",
      "role": "Primary Sponsor",
      "verified_connections": [
        {"entity": "Am. Farm Bureau", "type": "lobby_donate", "amount": 1500000}
      ],
      "context": {
        "industry_donations_90d": 2300000,
        "career_pac_total": 30200000,
        "committee": "Agriculture Committee"
      }
    }
  ],
  "briefing": "...",
  "data_limitations": {
    "fec_threshold": "$200",
    "senate_stocks": false,
    "industry_matching": "keyword",
    "lda_coverage": "quarterly"
  }
}
```

## Implementation Phases

### Phase 1: LDA Bill Number Parsing + lobby_donate Signal
- Re-ingest LDA filings with bill number extraction
- Create lobbied_on relationships
- Cross-reference with donations
- Build the lobby+donate signal cards

### Phase 2: Timing Analysis + Baseline Computation
- Compute baseline rates per policy area
- Implement timing spike detection with p-values
- Filter platform PACs

### Phase 3: Stock Trade + Revolving Door Signals
- Cross-reference stock trades with bill timelines
- Match revolving door lobbyists to bill policy areas

### Phase 4: Pre-compute + Fast API
- bill_influence_signals table
- Pre-compute all signals for all bills
- Percentile ranking within policy area
- Single fast API response

### Phase 5: Frontend
- Card-based signal UI
- Layered sponsor cards (verified + context)
- Comparison ring chart
- Mini timeline visualization
- AI analysis card
- Data limitations footer
