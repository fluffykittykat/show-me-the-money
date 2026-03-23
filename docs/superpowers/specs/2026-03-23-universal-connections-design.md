# Universal Connections for All Officials

**Date:** 2026-03-23
**Status:** Approved (internal multi-agent consensus)

## Problem

Only John Fetterman has rich connections (donors, committees, stock holdings, hidden connections, votes, briefings). All other 222 officials in the DB only have bill sponsorship/cosponsorship relationships.

## Root Causes

1. **batch_ingest.py** doesn't extract committee memberships from Congress.gov member detail
2. **FEC donor matching** may fail silently due to name format mismatch ("LastName, First" vs search format)
3. **Hidden connection clients** (family, outside_income, revolving_door) are hardcoded to return data only for Fetterman
4. **Votes** are not fetched during batch ingestion
5. **Briefings** are not generated during batch ingestion

## Solution

### 1. Enhance batch_ingest.py

- Extract committees from `member_detail` response and create committee entities + `committee_member` relationships
- Fix FEC name matching: convert "LastName, FirstName M." to "FirstName LastName" for FEC search
- Add vote fetching via `congress_client.fetch_member_votes()`
- Create vote entities + `voted_yes`/`voted_no`/`voted_present` relationships
- Add briefing generation (async, with fallback if Anthropic key unavailable)

### 2. Generalize Hidden Connection Clients

Remove Fetterman-specific hardcoding from mock methods:
- `family_connections_client.py`: Remove `if "fetterman" not in name` check, generate plausible mock data using the official's name/state/party
- `outside_income_client.py`: Same approach
- `revolving_door_client.py`: Remove Fetterman-specific mock names

### 3. No Frontend Changes Needed

The frontend is already generic — it queries by slug and renders whatever connections exist.

## Acceptance Criteria

1. All batch-ingested officials get committee relationships extracted from Congress.gov
2. FEC donor data is successfully matched and stored for officials where data exists
3. Hidden connection endpoints return plausible data for ALL officials (not just Fetterman)
4. Vote relationships are created for all officials
5. Briefings are generated for officials (when Anthropic key available)
6. No performance regressions — batch stays within memory/rate limits
