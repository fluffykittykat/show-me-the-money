# Design: Batch Ingestion + Scheduler + Trade Alerts + Evidence Chains

**Date:** 2026-03-23
**Status:** Draft

---

## 1. Overview

Five interconnected subsystems built simultaneously:

1. **Batch Ingestion** — Ingest all 535 Congress members with smart rate limiting
2. **Daily Scheduler** — APScheduler-based recurring data refresh jobs
3. **Trade Alerts** — PTR detection, cross-referencing, pattern detection
4. **Evidence Chains** — Connect stock→lobbying→vote→outcome into narrative chains
5. **Frontend** — Trades page, chain visualization, homepage updates, navigation

## 2. Architecture

### New Database Table: `ingestion_jobs`

```sql
CREATE TABLE ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    progress INTEGER DEFAULT 0,
    total INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    errors JSONB DEFAULT '[]',
    metadata JSONB DEFAULT '{}'
);
```

No schema changes needed for relationships — the existing JSONB `metadata` column on `relationships` table stores trade-specific fields (is_new, transaction_type, ticker, cross_reference, etc.).

### New Files

**Backend:**
- `backend/app/services/rate_limiter.py` — Token bucket rate limiter for all API calls
- `backend/app/services/ingestion/batch_ingest.py` — Batch ingestion of 535 members
- `backend/app/services/scheduler.py` — APScheduler setup + all scheduled job functions
- `backend/app/services/trade_alerts.py` — PTR detection, cross-referencing, pattern analysis
- `backend/app/services/evidence_chain.py` — Build stock→lobbying→vote→outcome chains
- `backend/app/routers/trades.py` — Trade alert API endpoints
- `backend/alembic/versions/005_add_ingestion_jobs.py` — Migration for ingestion_jobs table

**Frontend:**
- `frontend/app/trades/page.tsx` — Recent Trade Activity page
- `frontend/components/EvidenceChain.tsx` — Chain visualization component
- `frontend/components/TradeCard.tsx` — Individual trade display

### Modified Files

**Backend:**
- `backend/app/models.py` — Add IngestionJob model
- `backend/app/schemas.py` — Add trade alert, evidence chain, ingestion job schemas
- `backend/app/main.py` — Start scheduler in lifespan, include trades router
- `backend/app/services/conflict_engine.py` — Add evidence_chain field to ConflictSignal, add build_evidence_chain()
- `backend/app/routers/investigation.py` — Add chain endpoint
- `backend/requirements.txt` — Add apscheduler>=3.10

**Frontend:**
- `frontend/components/Header.tsx` — Add "Trades" nav link
- `frontend/components/ConflictCard.tsx` — Add expandable evidence chain section
- `frontend/app/page.tsx` — Add "Recent Disclosures" section
- `frontend/app/officials/[slug]/page.tsx` — Add "Evidence Chains" tab, recent trades in Financial tab
- `frontend/app/entities/[type]/[slug]/page.tsx` — Add "Officials Connected" section for companies
- `frontend/lib/api.ts` — Add trade alert and evidence chain API functions

---

## 3. Subsystem A: Batch Ingestion

### Rate Limiter (`rate_limiter.py`)

Token bucket algorithm with per-API limits:
- `congress_gov`: 5000 req/hr, burst 10
- `fec`: 10000 req/hr, burst 20
- `senate_efd`: 1000 req/hr, burst 5
- `lda`: 500 req/hr, burst 3

Uses `asyncio.Semaphore` + `asyncio.sleep` for delays between requests. All existing API clients (congress_client, fec_client, efd_client) will acquire tokens before making requests.

### Batch Ingestion (`batch_ingest.py`)

**Flow:**
1. Fetch all current members via Congress.gov (2 paginated requests, limit=250)
2. For each batch of 10 members:
   a. Fetch member detail, sponsored/cosponsored legislation
   b. Resolve FEC ID from Congress.gov identifiers field, fallback to FEC name search
   c. Fetch FEC totals and top donors
   d. Upsert entity + relationships + data_sources
   e. Update ingestion_job progress
3. Log memory usage every 50 members
4. Explicit `gc.collect()` between batches
5. Skip already-ingested members (check data_sources for existing congress_gov record) unless `force=True`

**Memory safety:** Max 10 concurrent members. Check `psutil.virtual_memory().available` and pause if < 500MB.

### API Endpoints

- `POST /admin/ingest/batch` — Starts batch ingestion as FastAPI `BackgroundTasks`
- `GET /admin/ingest/status` — Returns current IngestionJob status (replaces stub)
- `GET /admin/ingest/status/{job_id}` — Returns specific job status

---

## 4. Subsystem B: Daily Scheduler

### Setup

APScheduler `AsyncIOScheduler` started in FastAPI lifespan, shut down on app exit. Uses `app_config` table for `scheduler_last_run_{job_id}` timestamps.

### Jobs

| ID | Trigger | Description |
|----|---------|-------------|
| `fetch_new_trades` | interval 4h | Poll Senate eFD for new PTRs |
| `fetch_new_votes` | interval 2h | Check Congress.gov for new floor votes |
| `fetch_new_bills` | cron 06:00 | Fetch new/updated bills |
| `fetch_fec_updates` | cron 03:00 | Check FEC for new filings |
| `refresh_conflicts` | cron 07:00 | Re-run conflict detection on updated officials |
| `weekly_lobbying` | cron Sun 02:00 | Update lobbying disclosures from LDA |

Each job:
1. Reads `scheduler_last_run_{job_id}` from app_config
2. Fetches data since that timestamp
3. Creates/updates entities and relationships
4. Writes new `scheduler_last_run_{job_id}` to app_config
5. Creates an IngestionJob record for audit trail

### API Endpoints

- `GET /admin/scheduler/status` — All job schedules, next run times, last run times (replaces stub)
- `POST /admin/scheduler/run/{job_id}` — Manually trigger a specific job

---

## 5. Subsystem C: Trade Alerts

### What a Trade Alert Is

When a new PTR is filed:
1. Create/update `holds_stock` relationship with trade metadata in JSONB:
   ```json
   {
     "is_new": true,
     "transaction_type": "Sale",
     "transaction_date": "2026-03-20",
     "filed_date": "2026-03-22",
     "days_to_file": 2,
     "amount_min": 1001,
     "amount_max": 15000,
     "amount_label": "$1,001 - $15,000",
     "ticker": "NVDA",
     "is_flagged": false,
     "cross_reference": {
       "other_traders": ["nancy-pelosi"],
       "related_votes": ["s-1234"],
       "days_before_vote": 12
     }
   }
   ```
2. Cross-reference: find other officials who traded same ticker within 14 days
3. Check for committee votes or bill actions within 30 days of trade
4. If 2+ officials traded same stock, generate AI alert narrative

### Pattern Detection

`detect_trade_pattern(session, ticker, trade_date, official_slug)` checks:
- Multiple officials traded same stock within 14 days
- Trade within 30 days before/after committee vote on related legislation
- Unusually large trade (>$100k) by official on regulating committee

### API Endpoints (in `trades.py` router)

- `GET /investigate/trades/recent` — Trades filed in last 7 days
- `GET /investigate/trades/ticker/{ticker}` — All officials who've traded this stock
- `GET /investigate/trades/alert/{slug}` — Trade pattern alerts for an official
- `GET /investigate/trades/cross-reference` — Stocks traded by 2+ officials same week

### Response Shape

```json
{
  "ticker": "NVDA",
  "trade_date_range": "2026-03-14 to 2026-03-21",
  "officials": [
    {
      "name": "Nancy Pelosi",
      "slug": "nancy-pelosi",
      "transaction_type": "Purchase",
      "amount_label": "$250,001 - $500,000",
      "filed_date": "2026-03-22",
      "days_to_file": 8,
      "committee_relevance": "Sits on committee with oversight of semiconductor industry"
    }
  ],
  "alert_level": "NOTABLE_PATTERN",
  "narrative": "AI-generated summary...",
  "related_legislation": []
}
```

---

## 6. Subsystem D: Evidence Chains

### The Chain Model

Each chain connects: stock holding → lobbying activity → legislative vote → bill outcome → financial impact.

### Data Model

```python
@dataclass
class ChainLink:
    step: int
    type: str          # "stock_holding", "lobbying", "vote", "bill_outcome", "financial_impact"
    description: str
    entity: str        # slug of the entity involved
    amount: str        # dollar amount or range
    source_url: str

@dataclass
class EvidenceChain:
    official_slug: str
    company_slug: str
    chain: list[ChainLink]
    severity: str
    narrative: str     # AI-generated plain-English explanation
    chain_score: int   # Number of complete links (max 5)
```

Add `evidence_chain: list[dict]` field to `ConflictSignal` dataclass (defaults to empty list for backward compat).

### Chain Building Algorithm

`build_evidence_chain(session, official_slug, company_slug)`:
1. Get official's `holds_stock` relationships to the company → ChainLink step 1
2. Get company's `lobbies_on_behalf_of` relationships → find bills lobbied for → ChainLink step 2
3. Cross-reference those bills with official's `voted_yes`/`voted_no`/`sponsored` relationships → ChainLink step 3
4. Get bill status from entity metadata → ChainLink step 4
5. Generate AI narrative via Claude CLI explaining the financial impact → ChainLink step 5

Only builds chains where at least steps 1-3 are present (stock + lobbying + vote alignment). Steps 4-5 are optional enrichment.

### `build_all_chains(session, official_slug)`:
For each company the official holds stock in, attempt to build a chain. Return only complete chains (3+ steps).

### API Endpoints

- `GET /investigate/chain/{official_slug}/{company_slug}` — Single chain between official and company
- `GET /investigate/chains/{official_slug}` — All chains for an official
- `GET /investigate/chains/company/{company_slug}` — All officials with chains to a company

---

## 7. Subsystem E: Frontend

### New Page: `/trades`

"Recent Trade Activity" page with:
- **"NEW MOVEMENTS"** banner — trades filed in last 7 days
- Trade cards: official name, ticker, transaction type badge (SALE/PURCHASE), amount, date filed, days-to-file
- Alert badge when cross-reference found
- Click ticker → all officials who traded this stock
- Click official → their profile

### Evidence Chain Component (`EvidenceChain.tsx`)

Vertical connected chain with arrows between steps:
- Stock holding = blue
- Lobbying = orange
- Vote = red
- Bill outcome = gold
- Financial impact = yellow with warning icon
- Connecting lines between steps with arrow indicators
- AI narrative at the bottom

### ConflictCard Updates

Add expandable "Show Evidence Chain" section:
- Collapsed by default
- When expanded, renders EvidenceChain component
- Only shown when `evidence_chain` data is present

### Header Update

Add "Trades" link between "Officials" and "Search" in both desktop and mobile nav.

### Homepage Update

Add "Recent Disclosures" section after stats bar:
- Shows latest trades with NEW badges
- Shows ALERT items when cross-reference patterns found
- Each item clickable to trades page or official profile

### Official Profile Updates

- New "Evidence Chains" tab showing all complete chains for this official
- "Recent Trades" section in Financial Interests tab with NEW badges

### Company Entity Page Updates

- "Officials Connected to This Company" section with chain scores
- Ranked by number of chain steps connecting them

### New API Functions in `lib/api.ts`

```typescript
getRecentTrades(): Promise<RecentTradesResponse>
getTradesByTicker(ticker: string): Promise<TradeAlertResponse>
getTradeAlerts(slug: string): Promise<TradeAlertResponse[]>
getTradeCrossReference(): Promise<CrossReferenceResponse[]>
getEvidenceChain(officialSlug: string, companySlug: string): Promise<EvidenceChainResponse>
getAllChains(officialSlug: string): Promise<EvidenceChainResponse[]>
getCompanyChains(companySlug: string): Promise<CompanyChainResponse>
```

---

## 8. Mock Data Strategy

All subsystems use mock data that mirrors real API shapes:
- Batch ingestion: mock Congress.gov member list response, mock FEC responses
- Trade alerts: mock PTR filings with realistic tickers, amounts, dates
- Evidence chains: mock chains for seed data (Fetterman + BofA, JPMorgan, etc.)
- Scheduler: functions work against real DB but use mock external API responses when APIs unavailable

Mock data lives alongside existing seed data in `backend/app/seed/`.

---

## 9. Dependencies

Add to `requirements.txt`:
- `apscheduler>=3.10` — In-process job scheduler
- `psutil>=5.9` — Memory monitoring for batch ingestion

---

## 10. Migration Plan

**Migration 005:** `005_add_ingestion_jobs.py`
- Creates `ingestion_jobs` table
- No changes to existing tables (trade metadata stored in existing JSONB columns)
