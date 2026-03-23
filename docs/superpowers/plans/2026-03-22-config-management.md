# Config Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a database-backed config management system with admin UI, replacing hardcoded env vars, plus performance indexes.

**Architecture:** New `app_config` table stores key-value config. A config service reads DB → env var → default. A new router exposes CRUD endpoints. The frontend admin page at `/admin/config` manages entries via API calls. Two Alembic migrations: one for the config table, one for performance indexes.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic v2, Next.js 16, React 19, Tailwind CSS v4, TypeScript 5.9

---

## File Map

**Backend — Create:**
- `backend/alembic/versions/002_add_config_table.py` — migration for app_config table
- `backend/alembic/versions/003_add_performance_indexes.py` — migration for composite + GIN indexes
- `backend/app/services/config_service.py` — config read/write/list logic
- `backend/app/routers/config.py` — REST endpoints for config CRUD

**Backend — Modify:**
- `backend/app/models.py` — add `AppConfig` model
- `backend/app/schemas.py` — add config Pydantic schemas
- `backend/app/main.py` — register config router
- `backend/alembic/env.py` — import AppConfig model
- `backend/app/services/ai_service.py` — add config plumbing (keep mock)

**Frontend — Create:**
- `frontend/app/admin/config/page.tsx` — admin config page

**Frontend — Modify:**
- `frontend/lib/types.ts` — add `ConfigEntry` type
- `frontend/lib/api.ts` — add config API functions
- `frontend/components/Header.tsx` — add admin nav link

---

### Task 1: Alembic Migration — Config Table

**Files:**
- Create: `backend/alembic/versions/002_add_config_table.py`

- [ ] **Step 1: Create migration file**

```python
"""Add app_config table

Revision ID: 002_add_config_table
Revises: 001_initial
Create Date: 2026-03-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "002_add_config_table"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_config",
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_secret", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_config")
```

- [ ] **Step 2: Commit**

```bash
git add backend/alembic/versions/002_add_config_table.py
git commit -m "feat: add migration 002 for app_config table"
```

---

### Task 2: Alembic Migration — Performance Indexes

**Files:**
- Create: `backend/alembic/versions/003_add_performance_indexes.py`

- [ ] **Step 1: Create migration file**

```python
"""Add performance indexes: composite relationship indexes + GIN full-text search

Revision ID: 003_add_performance_indexes
Revises: 002_add_config_table
Create Date: 2026-03-22
"""

from typing import Sequence, Union

from alembic import op

revision: str = "003_add_performance_indexes"
down_revision: Union[str, None] = "002_add_config_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Composite indexes for relationship queries filtered by type
    op.create_index(
        "ix_rel_from_type",
        "relationships",
        ["from_entity_id", "relationship_type"],
    )
    op.create_index(
        "ix_rel_to_type",
        "relationships",
        ["to_entity_id", "relationship_type"],
    )

    # GIN full-text search index on entities
    op.execute(
        "CREATE INDEX ix_entities_fts ON entities "
        "USING gin(to_tsvector('english', name || ' ' || coalesce(summary, '')))"
    )


def downgrade() -> None:
    op.drop_index("ix_entities_fts", table_name="entities")
    op.drop_index("ix_rel_to_type", table_name="relationships")
    op.drop_index("ix_rel_from_type", table_name="relationships")
```

- [ ] **Step 2: Commit**

```bash
git add backend/alembic/versions/003_add_performance_indexes.py
git commit -m "feat: add migration 003 for composite + GIN full-text indexes"
```

---

### Task 3: AppConfig Model + Schemas

**Files:**
- Modify: `backend/app/models.py` — add AppConfig class
- Modify: `backend/app/schemas.py` — add config schemas
- Modify: `backend/alembic/env.py` — import AppConfig

- [ ] **Step 1: Add AppConfig model to `backend/app/models.py`**

Append after the `DataSource` class:

```python
class AppConfig(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_secret: Mapped[bool] = mapped_column(
        server_default=text("true"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()")
    )
```

- [ ] **Step 2: Add config schemas to `backend/app/schemas.py`**

Append after `HealthResponse`:

```python
class ConfigEntryResponse(BaseModel):
    key: str
    description: str
    is_secret: bool
    is_configured: bool
    masked_value: Optional[str] = None
    source: str  # "database", "env_var", "default", "not_set"


class ConfigSetRequest(BaseModel):
    value: str
```

- [ ] **Step 3: Update `backend/alembic/env.py` import**

Add `AppConfig` to the existing model import line:

```python
from app.models import AppConfig, DataSource, Entity, Relationship  # noqa: F401 - ensure models loaded
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py backend/alembic/env.py
git commit -m "feat: add AppConfig model and config Pydantic schemas"
```

---

### Task 4: Config Service

**Files:**
- Create: `backend/app/services/config_service.py`

- [ ] **Step 1: Create config service**

```python
"""
Config service: reads from DB first, falls back to env vars.
Never returns raw secret values through the API — masked only.
"""

import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppConfig

# TODO: Add encryption at rest for secret values (future enhancement)

KNOWN_KEYS: dict[str, dict] = {
    "ANTHROPIC_API_KEY": {
        "description": "Anthropic Claude API key for AI briefing generation",
        "is_secret": True,
        "env_fallback": "ANTHROPIC_API_KEY",
    },
    "CONGRESS_GOV_API_KEY": {
        "description": "Congress.gov API key (api.congress.gov/sign-up)",
        "is_secret": True,
        "env_fallback": "CONGRESS_GOV_API_KEY",
    },
    "FEC_API_KEY": {
        "description": "FEC Open Data API key (api.data.gov/signup)",
        "is_secret": True,
        "env_fallback": "FEC_API_KEY",
    },
    "OPENSECRETS_API_KEY": {
        "description": "OpenSecrets API key (opensecrets.org/api)",
        "is_secret": True,
        "env_fallback": "OPENSECRETS_API_KEY",
    },
    "CONGRESS_GOV_BASE_URL": {
        "description": "Congress.gov API base URL",
        "is_secret": False,
        "default": "https://api.congress.gov/v3",
        "env_fallback": "CONGRESS_GOV_BASE_URL",
    },
    "FEC_BASE_URL": {
        "description": "FEC API base URL",
        "is_secret": False,
        "default": "https://api.open.fec.gov/v1",
        "env_fallback": "FEC_BASE_URL",
    },
    "OPENSECRETS_BASE_URL": {
        "description": "OpenSecrets API base URL",
        "is_secret": False,
        "default": "https://www.opensecrets.org/api",
        "env_fallback": "OPENSECRETS_BASE_URL",
    },
}


def _mask_value(value: str) -> str:
    """Mask a secret value, showing only last 4 chars."""
    if len(value) <= 4:
        return "****"
    return f"****...{value[-4:]}"


async def get_config_value(session: AsyncSession, key: str) -> Optional[str]:
    """Get config value: DB first, then env var, then default."""
    # Check DB
    result = await session.execute(
        select(AppConfig.value).where(AppConfig.key == key)
    )
    db_value = result.scalar_one_or_none()
    if db_value is not None:
        return db_value

    # Check env var
    key_info = KNOWN_KEYS.get(key, {})
    env_key = key_info.get("env_fallback", key)
    env_value = os.getenv(env_key)
    if env_value:
        return env_value

    # Return default if available
    return key_info.get("default")


async def set_config_value(session: AsyncSession, key: str, value: str) -> None:
    """Set/update a config value in the DB."""
    key_info = KNOWN_KEYS.get(key)
    if key_info is None:
        raise ValueError(f"Unknown config key: {key}")

    result = await session.execute(
        select(AppConfig).where(AppConfig.key == key)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.value = value
    else:
        entry = AppConfig(
            key=key,
            value=value,
            description=key_info["description"],
            is_secret=key_info["is_secret"],
        )
        session.add(entry)

    await session.commit()


async def delete_config_value(session: AsyncSession, key: str) -> bool:
    """Delete a config value from DB (falls back to env var)."""
    result = await session.execute(
        select(AppConfig).where(AppConfig.key == key)
    )
    existing = result.scalar_one_or_none()
    if existing:
        await session.delete(existing)
        await session.commit()
        return True
    return False


async def get_all_config(session: AsyncSession) -> list[dict]:
    """Return all config entries with masked values and source info."""
    # Fetch all DB entries
    result = await session.execute(select(AppConfig))
    db_entries = {row.key: row for row in result.scalars().all()}

    configs = []
    for key, info in KNOWN_KEYS.items():
        db_entry = db_entries.get(key)
        env_key = info.get("env_fallback", key)
        env_value = os.getenv(env_key)
        default_value = info.get("default")

        # Determine source and value
        if db_entry and db_entry.value is not None:
            source = "database"
            raw_value = db_entry.value
            is_configured = True
        elif env_value:
            source = "env_var"
            raw_value = env_value
            is_configured = True
        elif default_value:
            source = "default"
            raw_value = default_value
            is_configured = True
        else:
            source = "not_set"
            raw_value = None
            is_configured = False

        # Mask secret values
        if raw_value and info["is_secret"]:
            masked_value = _mask_value(raw_value)
        elif raw_value and not info["is_secret"]:
            masked_value = raw_value
        else:
            masked_value = None

        configs.append({
            "key": key,
            "description": info["description"],
            "is_secret": info["is_secret"],
            "is_configured": is_configured,
            "masked_value": masked_value,
            "source": source,
        })

    return configs
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/config_service.py
git commit -m "feat: add config service with DB/env/default fallback chain"
```

---

### Task 5: Config Router

**Files:**
- Create: `backend/app/routers/config.py`
- Modify: `backend/app/main.py` — register router

- [ ] **Step 1: Create config router**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import ConfigEntryResponse, ConfigSetRequest
from app.services import config_service

router = APIRouter(prefix="/config", tags=["config"])


@router.get("", response_model=list[ConfigEntryResponse])
async def list_config(db: AsyncSession = Depends(get_db)):
    return await config_service.get_all_config(db)


@router.post("/{key}")
async def set_config(
    key: str, body: ConfigSetRequest, db: AsyncSession = Depends(get_db)
):
    if key not in config_service.KNOWN_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown config key: {key}")
    await config_service.set_config_value(db, key, body.value)
    return {"status": "ok", "key": key}


@router.delete("/{key}")
async def clear_config(key: str, db: AsyncSession = Depends(get_db)):
    if key not in config_service.KNOWN_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown config key: {key}")
    deleted = await config_service.delete_config_value(db, key)
    return {
        "status": "ok",
        "key": key,
        "was_set": deleted,
    }


@router.get("/{key}/test")
async def test_config(key: str, db: AsyncSession = Depends(get_db)):
    if key not in config_service.KNOWN_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown config key: {key}")
    value = await config_service.get_config_value(db, key)
    return {
        "key": key,
        "is_set": value is not None,
    }
```

- [ ] **Step 2: Register config router in `backend/app/main.py`**

Add import and include_router:

```python
from app.routers import briefings, config, entities, graph, search
```

And add after the existing router includes:

```python
app.include_router(config.router)
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/config.py backend/app/main.py
git commit -m "feat: add config CRUD router and register in app"
```

---

### Task 6: Update AI Service (Plumbing Only)

**Files:**
- Modify: `backend/app/services/ai_service.py`

- [ ] **Step 1: Add config plumbing, keep mock return**

Replace the entire file with:

```python
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.config_service import get_config_value


class AIBriefingService:
    async def generate_briefing(
        self,
        entity_slug: str,
        context_data: dict,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """
        Generate an AI briefing for an entity.

        Config plumbing is in place — when ready to wire to Anthropic Claude API,
        use: api_key = await get_config_value(session, "ANTHROPIC_API_KEY")

        For now: return pre-written mock briefing from DB metadata.
        """
        if session:
            _api_key = await get_config_value(session, "ANTHROPIC_API_KEY")
            # TODO: Use api_key to call Anthropic Claude API when ready

        return context_data.get("metadata", {}).get(
            "mock_briefing", "Briefing not available."
        )


ai_briefing_service = AIBriefingService()
```

- [ ] **Step 2: Update briefings router to pass session**

In `backend/app/routers/briefings.py`, update the `generate_briefing` call to pass the db session:

```python
    briefing_text = await ai_briefing_service.generate_briefing(
        entity_slug=slug,
        context_data={"metadata": entity.metadata_},
        session=db,
    )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/ai_service.py backend/app/routers/briefings.py
git commit -m "feat: add config plumbing to AI service (mock retained)"
```

---

### Task 7: Frontend Types + API Client

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Add ConfigEntry type to `frontend/lib/types.ts`**

Append after `BriefingResponse`:

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

- [ ] **Step 2: Add config API functions to `frontend/lib/api.ts`**

Add import for `ConfigEntry`:

```typescript
import type {
  Entity,
  ConnectionsResponse,
  BriefingResponse,
  SearchResponse,
  GraphResponse,
  ConfigEntry,
} from './types';
```

Append before the `export { ApiError }` line:

```typescript
export async function getConfig(): Promise<ConfigEntry[]> {
  return apiFetch<ConfigEntry[]>('/config');
}

export async function setConfigValue(key: string, value: string): Promise<void> {
  await apiFetch(`/config/${encodeURIComponent(key)}`, {
    method: 'POST',
    body: JSON.stringify({ value }),
  });
}

export async function clearConfigValue(key: string): Promise<void> {
  await apiFetch(`/config/${encodeURIComponent(key)}`, {
    method: 'DELETE',
  });
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat: add config types and API client functions"
```

---

### Task 8: Admin Config Page

**Files:**
- Create: `frontend/app/admin/config/page.tsx`

- [ ] **Step 1: Create admin config page**

Full component implementing:
- Three sections: AI Configuration, Data Sources — API Keys, Data Sources — Base URLs
- Config cards with status badges (Configured DB / Configured env / Not configured)
- Save/Clear buttons per entry
- Warning banners for unconfigured Anthropic key and data source keys
- Dark theme with zinc-900 bg and gold accents
- `'use client'` directive for state management
- Uses `getConfig`, `setConfigValue`, `clearConfigValue` from `@/lib/api`

Key groupings:
```typescript
const AI_KEYS = ['ANTHROPIC_API_KEY'];
const DATA_SOURCE_KEYS = ['CONGRESS_GOV_API_KEY', 'FEC_API_KEY', 'OPENSECRETS_API_KEY'];
const URL_KEYS = ['CONGRESS_GOV_BASE_URL', 'FEC_BASE_URL', 'OPENSECRETS_BASE_URL'];
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/admin/config/page.tsx
git commit -m "feat: add admin config management page"
```

---

### Task 9: Header Nav Link

**Files:**
- Modify: `frontend/components/Header.tsx`

- [ ] **Step 1: Add settings icon link to Header**

Import `Settings` from lucide-react. Add a settings link in the desktop nav (before the search toggle) and in the mobile nav:

Desktop nav addition:
```tsx
<Link
  href="/admin/config"
  className="text-sm font-medium text-zinc-400 transition-colors hover:text-zinc-100"
  aria-label="Admin settings"
>
  <Settings className="h-4 w-4" />
</Link>
```

Mobile nav addition:
```tsx
<Link
  href="/admin/config"
  onClick={() => setMobileMenuOpen(false)}
  className="text-sm font-medium text-zinc-300"
>
  Admin
</Link>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/Header.tsx
git commit -m "feat: add admin settings link to header navigation"
```

---

### Task 10: Verify & Restart

- [ ] **Step 1: Run Alembic migrations to verify they apply cleanly**

```bash
cd /home/mansona/workspace/jerry-maguire/backend && python -c "from app.models import AppConfig; print('Model loads OK')"
```

- [ ] **Step 2: Restart services**

```bash
pm2 restart jerry-backend jerry-frontend
```

- [ ] **Step 3: Verify endpoints**

```bash
curl -s http://localhost:3001/config | python -m json.tool
```

- [ ] **Step 4: Send completion notification**

```bash
openclaw system event --text "Done: Config management page built for Project Jerry Maguire at /admin/config" --mode now
```
