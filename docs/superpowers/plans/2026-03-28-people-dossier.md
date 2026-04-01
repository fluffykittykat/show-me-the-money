# People Dossier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Add statistical influence signal cards to official pages — same framework as bill dossiers. Signal engine + DB table + API update + frontend cards.

**Architecture:** New `official_signals.py` computes 5 signals per official. Results stored in `official_influence_signals` table. V2 official API updated to include signals. Frontend adds card grid + evidence expandable views.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL 16, Next.js, TypeScript

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/app/services/official_signals.py` | NEW — 5 signal detectors for officials |
| `backend/app/models.py` | MODIFY — add OfficialInfluenceSignal model |
| `backend/app/routers/v2.py` | MODIFY — add signals to /v2/official endpoint |
| `backend/app/schemas.py` | MODIFY — add signal fields to V2OfficialResponse |
| `backend/app/main.py` | MODIFY — add admin endpoint for precompute |
| `frontend/app/officials/[slug]/page.tsx` | MODIFY — add signal cards + evidence views |

---

### Task 1: OfficialInfluenceSignal DB Model + Migration

**Files:** backend/app/models.py, alembic migration

Add model identical to BillInfluenceSignal but with `official_id`:

```python
class OfficialInfluenceSignal(Base):
    __tablename__ = "official_influence_signals"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    official_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("entities.id"), index=True)
    signal_type: Mapped[str] = mapped_column(String(30))
    found: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    rarity_pct: Mapped[float] = mapped_column(Float, nullable=True)
    rarity_label: Mapped[str] = mapped_column(String(20), nullable=True)
    p_value: Mapped[float] = mapped_column(Float, nullable=True)
    baseline_rate: Mapped[float] = mapped_column(Float, nullable=True)
    observed_rate: Mapped[float] = mapped_column(Float, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict] = mapped_column("evidence_data", JSONB, server_default=text("'{}'::jsonb"))
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

Generate + run alembic migration. Commit.

---

### Task 2: Official Signal Engine

**Files:** backend/app/services/official_signals.py (NEW)

Create with 5 signal detectors + main compute function + precompute job:

**Signal 1: donors_lobby_bills** — For each donor, check if they filed LDA lobbying disclosures referencing any bill this official sponsored. Cross-reference: donated_to → official ← sponsored → bill ← lobbied_on.

**Signal 2: timing_spike** — Across ALL bills this official sponsored, count same-industry donations arriving within 90 days before each bill's introduced_date. Compare aggregate rate to chamber baseline.

**Signal 3: stock_committee** — Check stock_trade relationships. Match trade entity industry keywords against committee jurisdiction keywords. Flag trades within 60 days of committee hearings or bill introductions.

**Signal 4: committee_donors** — Existing verdict engine logic. Mark as "Expected". Always found for officials with donors + committees.

**Signal 5: revolving_door** — Check revolving_door_lobbyist relationships pointing to this official. If found, check if the lobbyist's clients also donated.

Include `run_precompute_official_signals()` that iterates all 500 officials, computes signals, stores results, computes percentile rank within chamber (Senate/House).

Add admin endpoint: `POST /admin/ingest/precompute-official-signals`

Commit.

---

### Task 3: Update V2 Official API

**Files:** backend/app/routers/v2.py, backend/app/schemas.py

Add to V2OfficialResponse:
```python
influence_signals: list[V2InfluenceSignal] = []  # reuse bill signal schema
percentile_rank: int | None = None
peer_count: int = 0
peer_group: str = ""  # "senators" or "representatives"
```

In v2_official endpoint:
- Load OfficialInfluenceSignal records for this official
- Get percentile from entity metadata (official_influence_percentile)
- peer_count = 100 for senators, 435 for reps
- peer_group = "senators" or "representatives" based on chamber

Commit.

---

### Task 4: Frontend — Signal Cards + Evidence Views

**Files:** frontend/app/officials/[slug]/page.tsx

Add between the header and campaign finance trend sections:

1. **Percentile ring** — same component as bills, shows "More influence signals than X% of senators"
2. **Signal cards** — 2-column grid, same card design as bill dossier, color-coded by finding
3. **Evidence expandable** — click "View evidence" expands to show:
   - Side-by-side "Lobbied for [bill]" AND "Donated $X" cards
   - Timeline with donation date → bill intro
   - Three-column: total donated | within 90 days | days to bill
   - Source links
4. **LOBBY+DONATE badge** on donor table entries that match

Commit.

---

### Task 5: Trigger + Verify

Restart backend. Trigger precompute. Verify signals in DB. Test API. Test frontend.

Commit.
