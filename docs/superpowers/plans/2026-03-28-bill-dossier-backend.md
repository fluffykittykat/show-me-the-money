# Bill Dossier Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the statistical correlation engine that detects influence signals on bills, stores results in a pre-computed table, and serves them via a fast v2 API endpoint.

**Architecture:** New `bill_signals.py` service computes 5 influence signals per bill using cross-referenced public data (LDA lobbying + FEC donations + Congress.gov). Results stored in `bill_influence_signals` DB table. Updated `/v2/bill/{slug}` endpoint serves all data in one response. LDA filings re-ingested with bill number parsing.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (async), PostgreSQL 16, scipy (for p-values)

**Spec:** `docs/superpowers/specs/2026-03-28-bill-dossier-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `backend/app/services/bill_signals.py` | Computes all 5 influence signals for a bill |
| `backend/app/services/ingestion/ingest_lda_bills.py` | Re-ingests LDA filings, parses bill numbers, creates lobbied_on relationships |
| `backend/app/services/bill_baselines.py` | Computes per-policy-area baseline rates for statistical comparison |

### Modified Files
| File | Changes |
|------|---------|
| `backend/app/models.py` | Add `BillInfluenceSignal` model |
| `backend/app/schemas.py` | Add v2 bill response schemas with signals |
| `backend/app/routers/v2.py` | Update `/v2/bill/{slug}` to return influence signals |
| `backend/app/main.py` | Add admin endpoints for LDA ingestion + bill signal computation |

---

### Task 1: BillInfluenceSignal Database Model

**Files:**
- Modify: `backend/app/models.py`
- Create: alembic migration (auto-generated)

- [ ] **Step 1: Add BillInfluenceSignal model**

Add to `/home/mansona/workspace/jerry-maguire/backend/app/models.py` after the `MoneyTrail` model:

```python
class BillInfluenceSignal(Base):
    """Pre-computed influence signal for a bill."""
    __tablename__ = "bill_influence_signals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), index=True
    )
    signal_type: Mapped[str] = mapped_column(String(30))
    found: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rarity_pct: Mapped[float] = mapped_column(Float, nullable=True)
    rarity_label: Mapped[str] = mapped_column(String(20), nullable=True)
    p_value: Mapped[float] = mapped_column(Float, nullable=True)
    baseline_rate: Mapped[float] = mapped_column(Float, nullable=True)
    observed_rate: Mapped[float] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict] = mapped_column(
        "evidence_data", JSONB, server_default=text("'{}'::jsonb")
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

Add `Boolean, Float` to SQLAlchemy imports if not already present.

- [ ] **Step 2: Generate and run migration**

```bash
cd /home/mansona/workspace/jerry-maguire/backend
DATABASE_URL=postgresql+asyncpg://jerry:maguire@localhost:5432/followthemoney alembic revision --autogenerate -m "add bill_influence_signals table"
DATABASE_URL=postgresql+asyncpg://jerry:maguire@localhost:5432/followthemoney alembic upgrade head
```

- [ ] **Step 3: Verify table**

```bash
PGPASSWORD=maguire psql -h localhost -U jerry -d followthemoney -c "\d bill_influence_signals"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models.py backend/alembic/
git commit -m "feat(bills): add bill_influence_signals table"
```

---

### Task 2: LDA Bill Number Parsing + lobbied_on Relationships

**Files:**
- Create: `backend/app/services/ingestion/ingest_lda_bills.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create ingest_lda_bills.py**

This script:
1. Calls Senate LDA API for filings (2024 + 2025)
2. For each filing, parses bill numbers from `lobbying_activities[].description` using regex
3. Matches bill numbers to bill entities in DB (e.g., "H.R. 1107" → slug "1107-119")
4. Creates `lobbied_on` relationships: lobbying_client → bill
5. Stores the LDA filing URL and lobbying description in relationship metadata

Key implementation details:
- Bill number regex: `r'(?:H\.?\s*R\.?|S\.?|H\.?\s*Res\.?|S\.?\s*Res\.?)\s*(\d{1,5})'`
- Normalize extracted numbers: "H.R. 1107" → try matching slug patterns like "1107-119", "1107-118"
- Rate limit LDA API calls: 1 second between requests
- Track progress via IngestionJob (job_type="lda_bills")

```python
async def run_ingest_lda_bills() -> str:
    """Parse bill numbers from LDA filings and create lobbied_on relationships."""
```

- [ ] **Step 2: Add admin endpoint**

In `backend/app/main.py`, add to the slug handler:

```python
elif slug == "lda-bills":
    import asyncio as _aio
    from app.services.ingestion.ingest_lda_bills import run_ingest_lda_bills
    _aio.create_task(run_ingest_lda_bills())
    return {"status": "started", "message": "Parsing bill numbers from LDA filings"}
```

- [ ] **Step 3: Syntax check and commit**

```bash
cd /home/mansona/workspace/jerry-maguire/backend
python3 -c "import ast; ast.parse(open('app/services/ingestion/ingest_lda_bills.py').read()); print('OK')"
git add backend/app/services/ingestion/ingest_lda_bills.py backend/app/main.py
git commit -m "feat(bills): LDA bill number parser — creates lobbied_on relationships"
```

---

### Task 3: Bill Signals Engine — All 5 Signals

**Files:**
- Create: `backend/app/services/bill_signals.py`

- [ ] **Step 1: Create bill_signals.py**

The engine computes all 5 influence signals for a given bill. Each signal returns a dict matching the `BillInfluenceSignal` model fields.

```python
PLATFORM_PACS = {"winred", "actblue", "anedot"}  # Filter these out

async def compute_bill_signals(session: AsyncSession, bill_id: uuid.UUID) -> list[dict]:
    """Compute all influence signals for a bill. Returns list of signal dicts."""

async def _signal_lobby_donate(session, bill_id, sponsors, bill_policy) -> dict:
    """Signal 1: Did any entity lobby for this bill AND donate to its sponsors?"""

async def _signal_timing_spike(session, bill_id, sponsors, bill_intro_date, bill_policy) -> dict:
    """Signal 2: Did same-industry donations spike before bill introduction?"""

async def _signal_committee_overlap(session, sponsors, bill_policy) -> dict:
    """Signal 3: Does sponsor sit on committee with jurisdiction?"""

async def _signal_stock_trades(session, sponsors, bill_intro_date, bill_policy) -> dict:
    """Signal 4: Did sponsors trade stocks in affected companies near bill dates?"""

async def _signal_revolving_door(session, sponsors, bill_policy) -> dict:
    """Signal 5: Are former staffers of sponsors lobbying on this policy area?"""
```

Signal 1 (lobby_donate) implementation:
- Query `lobbied_on` relationships pointing to this bill → get client entities
- For each client, check if they (or a PAC with similar name) have `donated_to` relationships to any sponsor
- If match found: `found=True`, include entity name, donation amount, LDA filing URL, FEC URL

Signal 2 (timing_spike) implementation:
- Get bill's introduced_date from metadata
- Get all `donated_to` relationships to sponsors with date_start within 90 days before introduced_date
- Filter to same-industry donors using `_extract_industry_keywords` from conflict_engine
- Filter out PLATFORM_PACS
- Count observed same-industry donations in window
- Compare to baseline (from bill_baselines, or default 1.2)
- Compute p-value using scipy.stats.poisson.sf(observed - 1, baseline) if scipy available, else approximate
- Apply time decay: 0-30 days = weight 1.0, 31-60 = 0.6, 61-90 = 0.3

Signal 3 (committee_overlap):
- For each sponsor, get their committee_member relationships
- Check if any committee's jurisdiction keywords match bill's policy_area
- Always `found=True` if match, but `rarity_label="Expected"`

Signal 4 (stock_trades):
- For each sponsor, get their stock_trade relationships
- Filter to trades within 60 days of bill introduced_date
- Match trade ticker/industry against bill policy_area keywords
- If match found: include ticker, transaction_type, amount_range, date, days_relative

Signal 5 (revolving_door):
- For each sponsor, get revolving_door_lobbyist relationships
- Check if the lobbyist (now) lobbies on issues matching this bill's policy_area
- If match: include lobbyist name, former position, current client

- [ ] **Step 2: Syntax check and commit**

```bash
python3 -c "import ast; ast.parse(open('app/services/bill_signals.py').read()); print('OK')"
git add backend/app/services/bill_signals.py
git commit -m "feat(bills): influence signal engine — 5 statistical correlation detectors"
```

---

### Task 4: Baseline Computation

**Files:**
- Create: `backend/app/services/bill_baselines.py`

- [ ] **Step 1: Create bill_baselines.py**

Pre-computes per-policy-area baseline rates for statistical comparison.

```python
async def compute_baselines(session: AsyncSession) -> dict[str, dict]:
    """Compute baseline rates per policy area.

    Returns: {
        "Agriculture and Food": {
            "lobby_donate_rate": 0.02,  # 2% of ag bills have lobby+donate
            "timing_90d_avg": 1.2,      # avg same-industry donations within 90d
            "total_bills": 842,
        },
        ...
    }
    """
```

Implementation:
- Query all bills grouped by policy_area
- For each policy area, count how many bills have lobbied_on relationships where the client also donated to sponsors (lobby_donate_rate)
- For each policy area, compute average same-industry donations within 90 days of introduction (timing_90d_avg)
- Store results in app_config table as JSON (key="bill_baselines")
- Add admin endpoint to trigger: `POST /admin/ingest/compute-baselines`

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/bill_baselines.py backend/app/main.py
git commit -m "feat(bills): baseline computation per policy area"
```

---

### Task 5: Pre-compute All Bill Signals

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create pre-compute job**

Add a function that iterates all bills with sponsors and computes signals:

```python
async def run_precompute_bill_signals() -> str:
    """Pre-compute influence signals for all bills with sponsors."""
    # 1. Load baselines from app_config
    # 2. Query all bills that have sponsored/cosponsored relationships
    # 3. For each bill: compute_bill_signals(), store in bill_influence_signals table
    # 4. Compute percentile rank within policy area
    # 5. Store percentile in bill entity metadata as 'influence_percentile'
    # 6. Track via IngestionJob
```

Add admin endpoint: `POST /admin/ingest/precompute-bill-signals`

- [ ] **Step 2: Commit**

```bash
git add backend/app/main.py backend/app/services/bill_signals.py
git commit -m "feat(bills): pre-compute job for all bill influence signals"
```

---

### Task 6: Update V2 Bill API Endpoint

**Files:**
- Modify: `backend/app/routers/v2.py`
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Add schemas**

In `backend/app/schemas.py`:

```python
class V2InfluenceSignal(BaseModel):
    type: str
    found: bool
    rarity_label: str | None
    rarity_pct: float | None = None
    p_value: float | None = None
    baseline_rate: float | None = None
    observed_rate: float | None = None
    description: str | None
    evidence: dict

class V2SponsorVerifiedConnection(BaseModel):
    entity: str
    type: str
    amount: int

class V2SponsorContext(BaseModel):
    industry_donations_90d: int
    career_pac_total: int
    committee: str | None

class V2BillSponsor(BaseModel):
    name: str
    slug: str
    party: str
    state: str
    role: str
    verified_connections: list[V2SponsorVerifiedConnection]
    context: V2SponsorContext
```

Update `V2BillResponse` to include:
```python
class V2BillResponse(BaseModel):
    entity: EntityResponse
    summary: str | None
    status_label: str
    policy_area: str
    percentile_rank: int | None
    similar_bill_count: int
    influence_signals: list[V2InfluenceSignal]
    sponsors: list[V2BillSponsor]
    briefing: str | None
    data_limitations: dict
```

- [ ] **Step 2: Update v2_bill endpoint**

In `backend/app/routers/v2.py`, update the `/v2/bill/{slug}` endpoint to:
1. Load bill entity
2. Load pre-computed signals from `bill_influence_signals` table
3. Load sponsors with their verified connections and context
4. Load percentile rank from entity metadata
5. Return complete V2BillResponse

For sponsors, compute verified_connections by checking if any lobbied_on client for this bill also has donated_to relationships to this sponsor. Context includes: industry-specific donations within 90 days, career PAC total, committee name.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/v2.py backend/app/schemas.py
git commit -m "feat(bills): v2 bill endpoint with influence signals + layered sponsors"
```

---

### Task 7: Trigger Pipeline + Verify

- [ ] **Step 1: Restart backend**

```bash
pm2 restart jerry-backend
sleep 5
```

- [ ] **Step 2: Ingest LDA bill numbers**

```bash
curl -s -X POST "http://localhost:8000/admin/ingest/lda-bills"
# Wait for completion
sleep 60
curl -s "http://localhost:8000/admin/ingest/status" | python3 -c "import json,sys; [print(f'{j[\"job_type\"]}: {j[\"status\"]} ({j[\"progress\"]}/{j[\"total\"]})') for j in json.load(sys.stdin)['recent_jobs'][:3]]"
```

- [ ] **Step 3: Compute baselines**

```bash
curl -s -X POST "http://localhost:8000/admin/ingest/compute-baselines"
sleep 10
```

- [ ] **Step 4: Pre-compute bill signals**

```bash
curl -s -X POST "http://localhost:8000/admin/ingest/precompute-bill-signals"
# This will take a while — processes thousands of bills
```

- [ ] **Step 5: Verify**

```bash
# Check signals table
PGPASSWORD=maguire psql -h localhost -U jerry -d followthemoney -c "
SELECT signal_type, found, COUNT(*) FROM bill_influence_signals GROUP BY signal_type, found ORDER BY signal_type, found;"

# Test v2 API
curl -s "http://localhost:8000/v2/bill/1107-119" | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(f'Signals: {len(d.get(\"influence_signals\",[]))}')
for s in d.get('influence_signals',[]):
    print(f'  {s[\"type\"]}: found={s[\"found\"]} rarity={s.get(\"rarity_label\",\"?\")}')
print(f'Sponsors: {len(d.get(\"sponsors\",[]))}')
print(f'Percentile: {d.get(\"percentile_rank\",\"?\")}')"
```

- [ ] **Step 6: Commit verification**

```bash
git commit --allow-empty -m "verify(bills): influence signals computed, v2 API serving"
```

---

## Execution Order

Tasks 1-7 are sequential. After Task 7, the backend is ready for the frontend card UI (Plan B).
