# Perfect Fetterman Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make John Fetterman's complete experience bulletproof — every page renders, every entity is clickable, FBI briefings work on every entity type, hidden connections pull from real graph data, evidence chains connect the dots.

**Architecture:** Native stack (no Docker). PostgreSQL on localhost, FastAPI backend on :8000, Next.js frontend on :3000. AI briefings via Anthropic Python SDK replacing the fragile subprocess call. All hidden connection endpoints already query real DB data (confirmed during audit). Focus is on: getting it running, fixing AI service, and ensuring end-to-end polish.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy async / PostgreSQL 16 / Next.js 16.2 / React 19 / Tailwind v4 / Anthropic SDK

---

### Task 1: Get Backend Running and Verify API

**Files:**
- Modify: `backend/requirements.txt` (add anthropic SDK)
- Read: `backend/start.sh`

- [ ] **Step 1: Install anthropic SDK**

```bash
cd /home/mansona/workspace/jerry-maguire/backend
source venv/bin/activate
pip install anthropic
```

- [ ] **Step 2: Add anthropic to requirements.txt**

Add this line to `backend/requirements.txt`:
```
anthropic>=0.40.0
```

- [ ] **Step 3: Start backend and test health endpoint**

```bash
cd /home/mansona/workspace/jerry-maguire/backend
source venv/bin/activate
export DATABASE_URL="postgresql+asyncpg://jerry:maguire@localhost:5432/followthemoney"
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s http://localhost:8000/health | python -m json.tool
```

Expected: `{"status": "healthy", "version": "0.1.0"}`

- [ ] **Step 4: Test key API endpoints**

```bash
curl -s http://localhost:8000/entities/john-fetterman | python -m json.tool | head -20
curl -s http://localhost:8000/hidden/john-fetterman/revolving-door | python -m json.tool | head -20
curl -s http://localhost:8000/hidden/john-fetterman/family-connections | python -m json.tool | head -20
curl -s http://localhost:8000/dashboard/stats | python -m json.tool
```

Expected: JSON responses with real data for each endpoint.

- [ ] **Step 5: Fix any errors found, then commit**

```bash
git add backend/requirements.txt
git commit -m "feat: add anthropic SDK dependency"
```

---

### Task 2: Switch AI Service from CLI Subprocess to Anthropic SDK

**Files:**
- Modify: `backend/app/services/ai_service.py`

The current `_generate_via_claude()` function shells out to `claude` CLI via subprocess. Replace it with the Anthropic Python SDK for reliability.

- [ ] **Step 1: Replace `_generate_via_claude` with SDK call**

Replace the entire `_generate_via_claude` function in `backend/app/services/ai_service.py`:

```python
import os
import anthropic

def _generate_via_claude(system_prompt: str, data_prompt: str) -> str:
    """Call Anthropic API to generate the briefing."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Try reading from DB config (sync fallback)
        return _generate_fallback_briefing(data_prompt)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": data_prompt}],
        )
        text = message.content[0].text
        return _sanitize(text)
    except Exception as e:
        print(f"[AIService] Anthropic SDK error: {e}")
        return _generate_fallback_briefing(data_prompt)
```

- [ ] **Step 2: Remove subprocess import**

Remove `import subprocess` from the top of the file (no longer needed).

- [ ] **Step 3: Test briefing endpoint**

```bash
curl -s http://localhost:8000/entities/john-fetterman/briefing | python -m json.tool | head -30
```

Expected: Either a real AI briefing (if ANTHROPIC_API_KEY is set) or the fallback message. No crash.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/ai_service.py
git commit -m "feat: switch AI briefing service from CLI subprocess to Anthropic SDK"
```

---

### Task 3: Get Frontend Running and Verify Pages Render

**Files:**
- Read: `frontend/package.json`
- Possibly modify: `frontend/next.config.ts` (if API proxy needed)

- [ ] **Step 1: Check Next.js config for API proxy**

Read `frontend/next.config.ts` to see if API calls proxy to backend. If not, check how `frontend/lib/api.ts` constructs URLs — it likely uses `NEXT_PUBLIC_API_URL` or defaults to `localhost:8000`.

- [ ] **Step 2: Start frontend dev server**

```bash
cd /home/mansona/workspace/jerry-maguire/frontend
npm run dev &
sleep 5
curl -s http://localhost:3000 | head -20
```

Expected: HTML response from Next.js.

- [ ] **Step 3: Open in browser and verify homepage renders**

Navigate to `http://localhost:3000` in browser. Check:
- Hero section loads
- Dashboard stats show real numbers (93 people, 876 bills, etc.)
- Active bills section populates
- No console errors

- [ ] **Step 4: Navigate to Fetterman's profile**

Go to `http://localhost:3000/officials/john-fetterman`. Check:
- Profile header with name, party, state
- Overview tab with stats
- Hidden Connections tab loads revolving door, family, outside income, contractor-donors, trade timing data
- Conflicts tab shows conflict cards
- Money tab shows donors, financial holdings

- [ ] **Step 5: Fix any rendering issues found**

Common issues to check:
- API URL mismatch (frontend calling wrong host/port)
- CORS errors (backend should allow all origins — already configured)
- Missing data fields causing component crashes

- [ ] **Step 6: Commit any fixes**

---

### Task 4: Ensure Every Entity Name is a Clickable Link

**Files:**
- Audit and modify components in: `frontend/components/`

The `EntityCard` component already links correctly. But entity names appearing in tables, lists, and relationship displays may be plain text. Audit each component and wrap entity references in `<Link>` tags.

- [ ] **Step 1: Audit components for unlinked entity names**

Search all components for entity names rendered as plain text. Key components to check:
- `DonorTable.tsx` — donor names should link to their entity pages
- `FinancialTable.tsx` — company names should link to company pages
- `BillsTable.tsx` — bill names should link to bill pages
- `CommitteeList.tsx` — committee names should link to committee pages
- `ConnectionsPanel.tsx` — connected entity names should be links
- `RelationshipTable.tsx` — entity names should be links
- `ConflictCard.tsx` — mentioned entities should be links
- `EvidenceChain.tsx` — each chain link entity should be clickable
- `TradeCard.tsx` — ticker/company should link to company page
- `RevolvingDoorSection.tsx` — lobbyist names, client names should link
- `FamilyConnectionsSection.tsx` — employer name should link
- `OutsideIncomeSection.tsx` — payer should link
- `ContractorDonorsSection.tsx` — company should link
- `RelationshipSpotlight.tsx` — entity names should link
- `SharedDonorNetwork.tsx` — donor/official names should link
- `DonationTimeline.tsx` — donor names should link

- [ ] **Step 2: For each component with unlinked names, add Link imports and wrap names**

Pattern to use:
```tsx
import Link from 'next/link';

// For entities with slugs:
<Link href={`/entities/${entity.entity_type}/${entity.slug}`} className="text-money-gold hover:underline">
  {entity.name}
</Link>

// For persons:
<Link href={`/officials/${entity.slug}`} className="text-money-gold hover:underline">
  {entity.name}
</Link>
```

Use the same `getEntityHref` pattern from `EntityCard.tsx`.

- [ ] **Step 3: Test by navigating Fetterman's profile and clicking through**

Every entity name on every tab should be a link that navigates to that entity's page. Click through at least:
- A donor → company/org page
- A stock holding → company page
- A bill → bill page
- A committee → committee page

- [ ] **Step 4: Commit**

```bash
git add frontend/components/
git commit -m "feat: make all entity names clickable links throughout the UI"
```

---

### Task 5: Add FBI Briefing to All Entity Page Types

**Files:**
- Modify: `frontend/app/entities/[type]/[slug]/page.tsx`
- Modify: `frontend/app/bills/[slug]/page.tsx`

The `FBIBriefing` component already exists and is used on the official profile page. The generic entity page (`/entities/[type]/[slug]`) already imports `FBIBriefing` (confirmed in audit). Verify it's actually rendered. Add it to the bills page if missing.

- [ ] **Step 1: Check if FBIBriefing is rendered on the entity page**

Read `frontend/app/entities/[type]/[slug]/page.tsx` and search for `<FBIBriefing`. If it's imported but not rendered, add it.

- [ ] **Step 2: Check if FBIBriefing is rendered on the bills page**

Read `frontend/app/bills/[slug]/page.tsx` and search for `FBIBriefing`. If missing, add:

```tsx
import FBIBriefing from '@/components/FBIBriefing';

// In the JSX, add after the bill header section:
<FBIBriefing
  entitySlug={slug}
  entityName={entity.name}
  entityType="bill"
/>
```

- [ ] **Step 3: Test by visiting a company page and a bill page**

Navigate to:
- `http://localhost:3000/entities/company/microsoft` (or whatever MSFT's slug is)
- `http://localhost:3000/bills/{some-bill-slug}`

Verify FBI briefing panel appears on both.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/
git commit -m "feat: add FBI briefing panel to all entity type pages"
```

---

### Task 6: Verify Evidence Chains Work End-to-End

**Files:**
- Read: `backend/app/services/evidence_chain.py`
- Read: `backend/app/routers/investigation.py`
- Read: `frontend/components/EvidenceChain.tsx`

- [ ] **Step 1: Test evidence chain API for Fetterman**

```bash
curl -s http://localhost:8000/investigate/chains/john-fetterman | python -m json.tool | head -50
```

Expected: JSON array of evidence chains linking Fetterman's stock holdings to lobbying to votes.

- [ ] **Step 2: Test a specific chain**

Find a company slug from Fetterman's stock holdings:
```bash
curl -s "http://localhost:8000/entities/john-fetterman/connections?type=holds_stock" | python -m json.tool | head -30
```

Then test a specific chain:
```bash
curl -s http://localhost:8000/investigate/chain/john-fetterman/{company-slug} | python -m json.tool
```

- [ ] **Step 3: Verify evidence chains render on the frontend**

Navigate to Fetterman's profile → appropriate tab showing evidence chains. Verify:
- Chain visualization shows connected nodes
- Each node is clickable
- Severity badge displays correctly

- [ ] **Step 4: Fix any issues and commit**

---

### Task 7: End-to-End Smoke Test

**Files:** None (testing only)

- [ ] **Step 1: Full Fetterman walkthrough**

Navigate through every tab on Fetterman's profile:
1. Overview — stats, summary, key relationships
2. Hidden Connections — revolving door (3 items), family (2 items), outside income, contractor-donors, trade timing
3. Conflicts — conflict cards with evidence
4. Money — donors table, financial holdings
5. Lobbying — lobbying connections
6. Evidence Chains — dot-connecting visualizations
7. All Connections — paginated relationship list

- [ ] **Step 2: Click-through test**

From Fetterman's page, click on:
- A donor → verify company/org page loads with FBI briefing
- A stock holding company → verify company page loads
- A bill → verify bill page loads with money trail + FBI briefing
- A committee → verify committee page loads
- Back button works at each step

- [ ] **Step 3: Search test**

Use the search bar to search "Fetterman", "Microsoft", "Banking Committee". Verify results appear and are clickable.

- [ ] **Step 4: Homepage test**

Verify homepage shows:
- Real stats (not zeros)
- Active bills
- Top conflicts (Fetterman should appear)
- Hidden connections feed

- [ ] **Step 5: Document any remaining issues as TODOs**

Create a list of anything not working that needs future attention.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat: perfect Fetterman - all pages functional, clickable entities, FBI briefings"
```
