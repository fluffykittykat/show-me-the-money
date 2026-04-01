# V2 Backend: Pre-Compute Engine + Verdict Algorithm

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pre-compute money trails and verdicts (NORMAL/CONNECTED/INFLUENCED/OWNED) for all officials, store them in the DB, and serve them via a single fast API call per page.

**Architecture:** New `verdict_engine.py` replaces the ad-hoc conflict detection. Background job computes verdicts for all 499 officials and stores results in a new `money_trails` DB table. New v2 API endpoints serve pre-computed data in a single response. AI briefings pre-generated and cached.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy (async), PostgreSQL 16, Anthropic SDK (Sonnet)

**Spec:** `docs/superpowers/specs/2026-03-25-v2-redesign-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `backend/app/services/verdict_engine.py` | The algorithm: counts dots, assigns NORMAL/CONNECTED/INFLUENCED/OWNED per industry per official |
| `backend/app/services/precompute.py` | Background job: runs verdict engine for all officials, stores results, pre-generates briefings |
| `backend/app/routers/v2.py` | New v2 API endpoints: single-response per page with all pre-computed data |
| `backend/app/models.py` (modify) | Add `MoneyTrail` model for pre-computed trail storage |
| `backend/app/schemas.py` (modify) | Add v2 response schemas |
| `backend/alembic/versions/xxxx_add_money_trails.py` | DB migration for new table |

### Existing Files Modified
| File | Changes |
|------|---------|
| `backend/app/main.py` | Register v2 router, add precompute admin endpoint |
| `backend/app/services/ai_service.py` | Add batch briefing generation method |

---

### Task 1: MoneyTrail Database Model

**Files:**
- Modify: `backend/app/models.py`
- Create: `backend/alembic/versions/` (auto-generated migration)

- [ ] **Step 1: Add MoneyTrail model to models.py**

```python
class MoneyTrail(Base):
    """Pre-computed money trail for an official, grouped by industry."""
    __tablename__ = "money_trails"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    official_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), index=True
    )
    industry: Mapped[str] = mapped_column(String(200))
    verdict: Mapped[str] = mapped_column(String(20))  # NORMAL, CONNECTED, INFLUENCED, OWNED
    dot_count: Mapped[int] = mapped_column(Integer, default=0)
    narrative: Mapped[str] = mapped_column(Text, nullable=True)
    chain: Mapped[dict] = mapped_column(
        "chain_data", JSONB, server_default=text("'{}'::jsonb")
    )
    # chain_data contains: {donors: [], committees: [], bills: [], middlemen: [], lobbying: []}
    total_amount: Mapped[int] = mapped_column(BigInteger, default=0)  # cents
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

- [ ] **Step 2: Generate and run migration**

```bash
cd backend
alembic revision --autogenerate -m "add money_trails table"
alembic upgrade head
```

- [ ] **Step 3: Verify table exists**

```bash
PGPASSWORD=maguire psql -h localhost -U jerry -d followthemoney -c "\d money_trails"
```
Expected: Table with columns id, official_id, industry, verdict, dot_count, narrative, chain_data, total_amount, computed_at

- [ ] **Step 4: Commit**

```bash
git add backend/app/models.py backend/alembic/
git commit -m "feat(v2): add money_trails table for pre-computed verdicts"
```

---

### Task 2: Verdict Engine — The Algorithm

**Files:**
- Create: `backend/app/services/verdict_engine.py`

- [ ] **Step 1: Create verdict_engine.py with the 4-level algorithm**

The engine takes an official entity and all their relationships, then:
1. Groups donors by industry (using committee jurisdiction mapping)
2. For each industry, counts dots:
   - Dot 1: Donor from this industry donated (FEC)
   - Dot 2: Official sits on committee regulating this industry (Congress.gov)
   - Dot 3: Official sponsored bills in this industry's policy area (Congress.gov)
   - Dot 4: Donor also lobbies on related bills (Senate LDA)
   - Dot 5: Money flows through middleman PAC (FEC)
   - Bonus: Multiple donors from same industry show same pattern
3. Assigns verdict: 1 dot = NORMAL, 2 = CONNECTED, 3 = INFLUENCED, 4+ multi-industry = OWNED
4. Generates chain data: {donors, committees, bills, middlemen, lobbying links}

```python
# Core function signature
async def compute_verdicts(session: AsyncSession, official_id: uuid.UUID) -> list[dict]:
    """Compute money trail verdicts for an official, grouped by industry.

    Returns list of dicts, each representing one industry trail:
    {
        "industry": "Finance",
        "verdict": "INFLUENCED",
        "dot_count": 3,
        "dots": ["donor_from_industry", "regulating_committee", "sponsored_aligned_bills"],
        "chain": {
            "donors": [{"name": "ABA PAC", "slug": "aba-pac", "amount": 500000}],
            "committees": [{"name": "Banking Committee", "slug": "..."}],
            "bills": [{"name": "Credit Card Act", "slug": "..."}],
            "middlemen": [{"name": "DSCC", "slug": "...", "amount_in": 2000000000, "amount_out": 110000000}],
            "lobbying": [{"firm": "...", "client": "...", "issue": "..."}],
        },
        "narrative": "ABA PAC donated $5K to this official who sits on Banking and sponsored 3 finance bills.",
        "total_amount": 500000,
    }
    """
```

Key implementation details:
- Use `_industries_for_committee()` from existing conflict_engine.py for committee→industry mapping
- Use `_extract_industry_keywords()` for donor→industry matching
- Check `lobbies_on_behalf_of` relationships for lobbying dot
- Check `donated_to` with PAC entity types for middleman dot
- For OWNED: check if 2+ industries each score INFLUENCED or higher

- [ ] **Step 2: Add helper to determine overall official verdict**

```python
def compute_overall_verdict(trails: list[dict]) -> tuple[str, int]:
    """Given all industry trails, compute the official's overall verdict.

    OWNED = 2+ industries at INFLUENCED level
    INFLUENCED = any industry at 3+ dots
    CONNECTED = any industry at 2 dots
    NORMAL = all industries at 1 dot or less

    Returns (verdict, total_dots_across_all_industries)
    """
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/verdict_engine.py
git commit -m "feat(v2): verdict engine — 4-level dot-counting algorithm"
```

---

### Task 3: Pre-Compute Background Job

**Files:**
- Create: `backend/app/services/precompute.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create precompute.py**

```python
async def run_precompute(force: bool = False) -> str:
    """Pre-compute verdicts + briefings for all officials.

    Steps:
    1. Load all officials with bioguide_id
    2. For each: run verdict_engine.compute_verdicts()
    3. Store results in money_trails table (delete old, insert new)
    4. Compute overall verdict and store in entity metadata
    5. Pre-generate AI briefing if not cached (or force=True)
    6. Build homepage story feed (top stories across all officials)
    7. Track progress via IngestionJob
    """
```

- [ ] **Step 2: Add admin endpoint in main.py**

```python
elif slug == "precompute":
    import asyncio as _aio
    from app.services.precompute import run_precompute
    _aio.create_task(run_precompute())
    return {"status": "started", "message": "Pre-computing verdicts + briefings for all officials"}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/precompute.py backend/app/main.py
git commit -m "feat(v2): precompute job — verdicts + briefings for all officials"
```

---

### Task 4: V2 API Endpoints — Single Response Per Page

**Files:**
- Create: `backend/app/routers/v2.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add v2 response schemas to schemas.py**

```python
class V2MoneyTrail(BaseModel):
    industry: str
    verdict: str  # NORMAL, CONNECTED, INFLUENCED, OWNED
    dot_count: int
    dots: list[str]
    narrative: str
    total_amount: int
    chain: dict  # {donors, committees, bills, middlemen, lobbying}

class V2OfficialResponse(BaseModel):
    """Single response with everything needed to render an official page."""
    entity: EntityResponse
    overall_verdict: str
    total_dots: int
    money_trails: list[V2MoneyTrail]
    top_donors: list[dict]  # aggregated, sorted by amount
    middlemen: list[dict]  # PACs with money_in and money_out
    committees: list[dict]
    briefing: str | None
    freshness: dict  # {fec_cycle, last_refreshed, data_completeness}

class V2BillResponse(BaseModel):
    """Single response for bill page."""
    entity: EntityResponse
    status_label: str
    sponsors: list[dict]  # with party, state, verdict, top_donor
    briefing: str | None

class V2EntityResponse(BaseModel):
    """Single response for PAC/company/org page."""
    entity: EntityResponse
    money_in: list[dict]
    money_out: list[dict]
    briefing: str | None

class V2HomepageResponse(BaseModel):
    """Single response for homepage."""
    top_stories: list[dict]  # pre-computed story feed
    stats: dict
    top_officials: list[dict]  # by verdict severity
    top_influencers: list[dict]
    revolving_door: list[dict]
```

- [ ] **Step 2: Create v2.py router**

```python
@router.get("/official/{slug}", response_model=V2OfficialResponse)
async def v2_official(slug: str, db: AsyncSession = Depends(get_db)):
    """Single query, single response, < 50ms."""
    # 1. Load entity
    # 2. Load pre-computed money_trails from DB
    # 3. Load aggregated donors (from relationships)
    # 4. Load cached briefing (from metadata)
    # 5. Return everything in one response

@router.get("/bill/{slug}", response_model=V2BillResponse)
async def v2_bill(slug: str, db: AsyncSession = Depends(get_db)):
    """Bill page data in one response."""

@router.get("/entity/{slug}", response_model=V2EntityResponse)
async def v2_entity(slug: str, db: AsyncSession = Depends(get_db)):
    """PAC/company/org page data in one response."""

@router.get("/homepage", response_model=V2HomepageResponse)
async def v2_homepage(db: AsyncSession = Depends(get_db)):
    """Homepage data in one response, fully cached."""
```

- [ ] **Step 3: Register router in main.py**

```python
from app.routers import v2
app.include_router(v2.router, prefix="/v2")
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/v2.py backend/app/schemas.py backend/app/main.py
git commit -m "feat(v2): single-response API endpoints for all page types"
```

---

### Task 5: Homepage Story Feed Generator

**Files:**
- Modify: `backend/app/services/precompute.py`

- [ ] **Step 1: Add story feed generation to precompute.py**

The homepage story feed shows the most compelling money trails across all officials. Each story is a complete narrative:

```python
async def _build_story_feed(session: AsyncSession) -> list[dict]:
    """Build the homepage story feed from pre-computed money trails.

    Selects the most interesting trails across all officials:
    1. All OWNED officials (multi-industry capture)
    2. Top INFLUENCED trails by amount
    3. Biggest middleman chains
    4. Most connected revolving door lobbyists

    Returns list of story dicts ready to serve.
    """
```

- [ ] **Step 2: Store story feed in app_config for fast serving**

```python
# Store as JSON in app_config table
await session.execute(
    insert(AppConfig).values(key="v2_story_feed", value=json.dumps(stories))
    .on_conflict_do_update(index_elements=["key"], set_={"value": json.dumps(stories)})
)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/precompute.py
git commit -m "feat(v2): homepage story feed generator"
```

---

### Task 6: Trigger Precompute + Verify

**Files:**
- No new files

- [ ] **Step 1: Restart backend and trigger precompute**

```bash
pm2 restart jerry-backend
sleep 5
curl -s -X POST "http://localhost:8000/admin/ingest/precompute"
```

- [ ] **Step 2: Monitor progress**

```bash
# Wait for completion, check logs
pm2 logs jerry-backend --lines 20 --nostream | grep precompute
```

- [ ] **Step 3: Verify data**

```bash
# Check money_trails table
PGPASSWORD=maguire psql -h localhost -U jerry -d followthemoney -c "
SELECT verdict, COUNT(*) FROM money_trails GROUP BY verdict ORDER BY count DESC;"

# Check v2 API
curl -s "http://localhost:8000/v2/official/pelosi-nancy" | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(f'Verdict: {d[\"overall_verdict\"]}')
print(f'Trails: {len(d[\"money_trails\"])}')
print(f'Briefing: {len(d.get(\"briefing\",\"\") or \"\")} chars')"

# Check homepage
curl -s "http://localhost:8000/v2/homepage" | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(f'Stories: {len(d[\"top_stories\"])}')
print(f'Top officials: {len(d[\"top_officials\"])}')"
```

- [ ] **Step 4: Commit verification results**

```bash
git commit --allow-empty -m "verify(v2): precompute engine running, verdicts computed"
```

---

## Execution Order

Tasks 1-6 are sequential — each depends on the previous.

After Task 6 completes, the v2 backend is ready to serve the frontend. The frontend plan (Plan 2) can then build against the v2 API endpoints.
