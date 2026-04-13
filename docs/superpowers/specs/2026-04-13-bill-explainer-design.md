# Bill Explainer Feature Design

## Problem

Bill pages show CRS summaries (dense/technical) and FBI-style briefings (focused on money trails), but neither answers the basic question: "What does this bill actually do?" Users need a plain-English explainer before diving into influence analysis.

## Solution

Add a **Bill Explainer** — a short, structured plain-English summary for every bill that answers:

1. **What it does** — 1-2 sentences describing the bill's core action
2. **Why it matters** — 1-2 sentences on the problem it addresses or its significance
3. **Who it affects** — 1-2 sentences identifying who/what is impacted

## Architecture

### Data Storage

- Stored in `Entity.metadata_["bill_explainer"]` as a JSON object:
  ```json
  {
    "what_it_does": "...",
    "why_it_matters": "...",
    "who_it_affects": "..."
  }
  ```
- Follows the same caching pattern as `fbi_briefing` — generated once, served from cache

### Generation

- Uses Claude AI via the existing `_generate_via_claude()` function in `ai_service.py`
- Input: bill name + CRS summary + policy area + status
- Prompt instructs Claude to return structured JSON with the three fields
- Generated lazily on first bill page visit (same pattern as briefing)
- Can be regenerated via force refresh

### API

- Add `explainer: dict | None` field to `V2BillResponse` schema
- Populate from `metadata_["bill_explainer"]` in the `/v2/bill/{slug}` endpoint
- Add generation endpoint or piggyback on existing briefing generation

### Frontend

- New `BillExplainer.tsx` component
- Placed immediately after the bill header (before controls/signals) — this is the first thing users should read
- Clean card design with three labeled sections
- If no explainer exists, auto-generate on page load (non-blocking)

## Files to Modify

### Backend
- `backend/app/services/ai_service.py` — Add `generate_bill_explainer()` method
- `backend/app/schemas.py` — Add `explainer` field to `V2BillResponse`
- `backend/app/routers/v2.py` — Retrieve/generate explainer in bill endpoint

### Frontend
- `frontend/components/BillExplainer.tsx` — New component
- `frontend/app/bills/[slug]/page.tsx` — Integrate component after header
- `frontend/lib/api.ts` — Add explainer generation API call (if separate endpoint)
- `frontend/lib/types.ts` — Add explainer type

## Non-Goals

- Batch pre-generation of all explainers (lazy is fine)
- User editing of explainers
- Multiple explainer variants or versions
