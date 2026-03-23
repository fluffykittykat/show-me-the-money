# Project Jerry Maguire — Design Principles & Architecture

## Core Thesis
> "Follow the Money" — In politics, if it's important, the money trail will prove it.

---

## Performance Contract (Non-Negotiable)

**Every page must be lightning fast. No exceptions.**

### Rules
1. **O(1) lookups wherever possible** — all primary lookups go through indexed columns
2. **Max 2 DB queries per page render** — entity + connections. That's it.
3. **No nested loops in application code** — if you need to group/filter, do it in SQL or in a single O(n) pass
4. **No N+1 queries** — ever. Use JOINs or preloaded data
5. **No sequential async fetches** — use `Promise.all()` for parallel requests
6. **Cache aggressively** — entity profiles and AI briefings change rarely; cache them

### Required Indexes

```sql
-- Primary lookups (already exist via UNIQUE constraint)
CREATE UNIQUE INDEX idx_entities_slug ON entities(slug);

-- Type filtering
CREATE INDEX idx_entities_type ON entities(entity_type);

-- Connection lookups (the most frequent query pattern)
CREATE INDEX idx_rel_from ON relationships(from_entity_id);
CREATE INDEX idx_rel_to ON relationships(to_entity_id);
CREATE INDEX idx_rel_from_type ON relationships(from_entity_id, relationship_type);
CREATE INDEX idx_rel_to_type ON relationships(to_entity_id, relationship_type);

-- Full-text search (GIN index for speed)
CREATE INDEX idx_entities_fts ON entities
  USING gin(to_tsvector('english', name || ' ' || coalesce(summary, '')));

-- Config table
CREATE INDEX idx_config_key ON app_config(key);
```

### Caching Strategy (Redis)
- Entity profiles: cache for 1 hour (TTL=3600)
- Connection lists: cache for 1 hour
- AI briefings: cache for 24 hours (expensive to generate)
- Search results: cache for 15 minutes
- Cache key pattern: `ftm:{entity_type}:{slug}`
- Invalidate on admin seed or data update

### Query Patterns

**Entity lookup** — O(1):
```sql
SELECT * FROM entities WHERE slug = $1;  -- indexed UNIQUE
```

**Connections** — O(log n) with index scan:
```sql
SELECT r.*, e.* FROM relationships r
JOIN entities e ON e.id = r.to_entity_id
WHERE r.from_entity_id = $1
AND r.relationship_type = ANY($2)
ORDER BY r.amount_usd DESC NULLS LAST
LIMIT $3;
```

**Full-text search** — O(log n) with GIN:
```sql
SELECT * FROM entities
WHERE to_tsvector('english', name || ' ' || coalesce(summary, ''))
@@ plainto_tsquery('english', $1)
ORDER BY ts_rank(...) DESC
LIMIT 20;
```

---

## Architecture

### Stack
- **Frontend:** Next.js 16 (App Router, TypeScript strict)
- **Backend:** FastAPI + async SQLAlchemy
- **Database:** PostgreSQL 16
- **Cache:** Redis (to be added)
- **Process manager:** pm2
- **Proxy:** nginx on :8060

### Data Model

Everything is an **entity** with **relationships**. No special tables per entity type.

```
entities         — every node: person, company, bill, org, PAC, industry
relationships    — every edge: invests_in, donated_by, sponsored, voted_for, etc.
app_config       — runtime configuration (API keys, endpoints)
data_sources     — provenance tracking (which API call produced which data)
```

### Entity Types
- `person` — elected officials
- `company` — corporations, ETFs, funds
- `bill` — legislation
- `organization` — unions, NGOs, trade groups
- `pac` — political action committees
- `industry` — sector categories
- `committee` — congressional committees

### Relationship Types
- `invests_in` / `holds_stock`
- `donated_to` / `donated_by`
- `sponsored` / `cosponsored`
- `voted_yes` / `voted_no` / `voted_present`
- `committee_member`
- `endorsed_by` / `endorsed`
- `lobbied_for`

---

## API Design

### Endpoints
```
GET  /entities/{slug}                    — entity profile
GET  /entities/{slug}/connections        — all relationships (filterable, paginated)
GET  /entities/{slug}/briefing           — AI-generated intelligence briefing
GET  /graph/{slug}?depth=2              — graph nodes + edges for visualization
GET  /search?q=...&type=...             — full-text search
GET  /config                            — platform config (keys masked)
POST /config/{key}                      — update a config value
DEL  /config/{key}                      — clear a config value
```

### Response Shape Philosophy
- Flat objects — no deeply nested JSON
- Include `connected_entity` inline on relationships (single JOIN, not a second query)
- Paginate everything with `limit` / `offset` + `total` count

---

## Data Sources

All data is public record. No scraping — APIs only.

| Source | Data | API Docs | Key Required |
|--------|------|----------|--------------|
| Congress.gov | Bills, votes, members, committees | api.congress.gov | Yes (free) |
| FEC (open.fec.gov) | Campaign finance, donors, PACs | api.open.fec.gov | Yes (free) |
| Senate eFD | Financial disclosures (stock holdings) | efts.senate.gov | No |
| OpenSecrets | Donor industry breakdowns | opensecrets.org/api | Yes (paid) |

### Mock Data First
All seed data mirrors the exact payload shape of real API responses.
Swapping from mock → real data = changing one config value, not rewriting code.

---

## Frontend Rules

1. **Wikipedia-style UX** — summaries with hyperlinked key terms
2. **FBI briefing format** — analyst narrative, factual, cited
3. **Every entity is clickable** — names, companies, bills, orgs all link to their entity page
4. **Dark theme, gold accents** — "Follow the Money" aesthetic
5. **Typography first** — this is a reading app, not a dashboard
6. **No markdown tables** — use HTML tables or lists
7. **Mobile responsive** — journalists use phones

---

## Scalability Path

**Phase 1 (current):** Single senator (Fetterman), mock data, no auth
**Phase 2:** All 535 members of Congress, real API data, Redis cache
**Phase 3:** State legislators, local officials (where data exists)
**Phase 4:** Historical data, time-series, trend analysis
**Phase 5:** AI-powered "would X support Y?" prediction engine

---

## What We Never Do

- No hardcoded API keys (config table + env var fallback)
- No nested loops over large datasets
- No sequential DB queries where JOINs work
- No blocking sync code in async handlers
- No returning raw secret values through the API
- No deeply nested JSON responses
- No client-side data transformation that could be done in SQL
