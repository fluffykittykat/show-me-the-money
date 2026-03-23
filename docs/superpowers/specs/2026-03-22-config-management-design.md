# Config Management System — Design Spec

## Overview

Replace hardcoded/env-var API keys with a database-backed config system. Add an admin UI page at `/admin/config` to manage keys. Add performance indexes for query optimization.

## Backend

### Migration 002: `app_config` table

```sql
CREATE TABLE app_config (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT,
    description TEXT,
    is_secret BOOLEAN DEFAULT true,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Migration 003: Performance indexes

New composite and GIN indexes (existing single-column indexes already present):

- `ix_rel_from_type` — `relationships(from_entity_id, relationship_type)`
- `ix_rel_to_type` — `relationships(to_entity_id, relationship_type)`
- `ix_entities_fts` — GIN index on `to_tsvector('english', name || ' ' || coalesce(summary, ''))`

### Config Service (`backend/app/services/config_service.py`)

- `KNOWN_KEYS` dict with 7 keys: ANTHROPIC_API_KEY, CONGRESS_GOV_API_KEY, FEC_API_KEY, OPENSECRETS_API_KEY, plus 3 base URLs
- `get_config_value(session, key)` — DB → env var → default → None
- `set_config_value(session, key, value)` — upsert into app_config
- `get_all_config(session)` — returns all known keys with masked values, source detection
- Masking: secrets show `****...{last4}`, non-secrets show full value

### Config Router (`backend/app/routers/config.py`)

- `GET /config` — list all config entries with masked values + source
- `POST /config/{key}` — set a value (body: `{"value": "..."}`)
- `DELETE /config/{key}` — clear DB value (falls back to env var)
- `GET /config/{key}/test` — check if key is set (no actual service ping for now)

### Config Model (`backend/app/models.py`)

Add `AppConfig` SQLAlchemy model.

### Config Schema (`backend/app/schemas.py`)

Add `ConfigEntryResponse` and `ConfigSetRequest` Pydantic models.

### AI Service update

Add `get_config_value` lookup for ANTHROPIC_API_KEY but keep returning mock data. Prepares the plumbing for when the real API call is wired up.

### Register router

Add config router to `main.py`.

## Frontend

### Types (`frontend/lib/types.ts`)

```typescript
export interface ConfigEntry {
  key: string;
  description: string;
  is_secret: boolean;
  is_configured: boolean;
  masked_value: string | null;
  source: 'database' | 'env_var' | 'default' | 'not_set';
}
```

### API client (`frontend/lib/api.ts`)

- `getConfig()` — GET /api/config
- `setConfigValue(key, value)` — POST /api/config/{key}
- `clearConfigValue(key)` — DELETE /api/config/{key}

### Admin page (`frontend/app/admin/config/page.tsx`)

- Sections: AI Configuration, Data Sources — API Keys, Data Sources — Base URLs
- Config cards with status badges, masked values, save/clear buttons
- Warning banners for unconfigured keys
- Dark theme (zinc-900 bg, gold accents) matching existing site

### Navigation

Add settings icon link to `/admin/config` in Header component.

## Decisions

- Two separate migrations (config table, then indexes)
- No encryption at rest (TODO for future)
- No Redis caching yet
- Mock AI service stays — config plumbing only
- `app_config` uses VARCHAR PK, no UUID
