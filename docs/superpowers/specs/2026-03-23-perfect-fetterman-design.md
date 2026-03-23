# Perfect Fetterman — Blueprint Design Spec

## Goal

Make John Fetterman's complete profile the gold standard for the platform. Every page he touches should be fully functional, every entity clickable, every page carrying an FBI Special Agent intelligence briefing. Once Fetterman is perfect, the pattern scales to all 535 members.

## Current State

- **DB has:** 93 people, 876 bills, 16 companies, 19 orgs, 3 committees, 2 PACs
- **Fetterman relationships:** 319 outbound (sponsored, cosponsored, holds_stock, committee_member, family/spouse), 59 inbound (donated_to, contractor_donor, revolving_door_lobbyist, outside_income, book_deal, speaking_fee)
- **Backend:** 10 routers, 40+ endpoints, all core services complete
- **Frontend:** 10 pages, 30+ components, full API client
- **Running native:** PostgreSQL on localhost, Python venv, Next.js dev server

## What "Perfect" Means

### 1. App Boots and Renders (P0)

- Backend starts on port 8000, serves API
- Frontend starts on port 3000, renders homepage
- Homepage shows real dashboard stats, active bills, top conflicts
- No crashes, no unhandled errors

### 2. Every Entity is Clickable (P0)

Every entity name anywhere in the UI links to that entity's page:
- Officials → `/officials/{slug}`
- Bills → `/bills/{slug}`
- Companies → `/entities/company/{slug}`
- Organizations → `/entities/organization/{slug}`
- PACs → `/entities/pac/{slug}`
- Committees → `/entities/committee/{slug}`
- Industries → `/entities/industry/{slug}`

Each entity page shows: name, type, summary, all connections, and an FBI briefing.

### 3. FBI Special Agent Briefing on Every Page (P0)

Every entity page (official, bill, company, org, PAC, committee) gets a briefing panel styled as a classified intelligence document. The AI service generates these via Claude API (not CLI subprocess).

Format: FBI analyst investigating possible campaign finance violations, connecting dots between money flows and legislative actions.

### 4. Hidden Connections Work from Real Graph Data (P1)

The 4 stubbed services should query the entity graph instead of returning hardcoded mock data:
- **Revolving door** → query `revolving_door_lobbyist` relationships
- **Family connections** → query `family_employed_by`, `spouse_income_from` relationships
- **Outside income** → query `outside_income_from`, `speaking_fee_from`, `book_deal_with` relationships
- **Contractor-donors** → query `contractor_donor` relationships

The seed data already creates these relationship types. The services just need to read them.

### 5. Evidence Chains End-to-End (P1)

For Fetterman, show chains like:
- Holds MSFT stock → Microsoft lobbies Banking Committee → Fetterman on Banking Committee → votes on tech bills
- JPMorgan donates to Fetterman → JPMorgan lobbies for bill X → Fetterman votes YES on bill X

### 6. AI Service Fix (P0)

Current AI service calls `claude` CLI via subprocess. Switch to using the Anthropic Python SDK directly (`anthropic` package) for reliability.

## Architecture Decisions

- **No Docker** — run PostgreSQL, backend (uvicorn), and frontend (next dev) natively
- **AI service** — switch from subprocess to Anthropic SDK
- **Hidden connections** — query real relationships from DB, not mock data
- **Clickable entities** — ensure all entity references in components are wrapped in Next.js Links

## Tasks (Execution Order)

1. Verify backend boots and API responds
2. Verify frontend boots and homepage renders
3. Fix AI service to use Anthropic SDK
4. Wire hidden connection services to real DB queries
5. Ensure all entity names in components are clickable links
6. Add FBI briefing panel to bill, company, org, committee, PAC pages
7. Verify evidence chains work for Fetterman
8. End-to-end smoke test: navigate Fetterman's full profile
