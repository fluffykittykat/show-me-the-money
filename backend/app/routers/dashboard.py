"""Dashboard API — powers the homepage intelligence dashboard."""

import json
import os
import re

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AppConfig, Entity, Relationship
from app.schemas import (
    ActiveBillItem,
    DashboardStats,
    FeaturedStory,
    TopConflictItem,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _slugify(text: str) -> str:
    """Minimal slugify: lowercase, replace non-alphanum with hyphens, collapse."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _bill_status(action_text: str) -> str:
    """Derive a simple bill status from the latest action text."""
    lower = action_text.lower()
    if "passed" in lower:
        return "PASSED"
    if "floor" in lower or "vote" in lower:
        return "ON FLOOR"
    if "failed" in lower or "vetoed" in lower:
        return "FAILED"
    return "IN COMMITTEE"


# ---------------------------------------------------------------------------
# 1. Active Bills — fetches recent bills from Congress.gov, enriched w/ DB data
# ---------------------------------------------------------------------------


@router.get("/active-bills", response_model=list[ActiveBillItem])
async def active_bills(db: AsyncSession = Depends(get_db)):
    """Fetch 10 most recently updated bills from Congress.gov, with conflict scores."""
    api_key = os.getenv(
        "CONGRESS_GOV_API_KEY",
        "LTYOWxgldVxWjxPzFhKnNYNMggjmF85tadkQham1",
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.congress.gov/v3/bill",
                params={
                    "sort": "updateDate",
                    "direction": "desc",
                    "limit": 10,
                    "api_key": api_key,
                    "format": "json",
                },
            )
            resp.raise_for_status()
            bills_data = resp.json().get("bills", [])
    except Exception:
        # Graceful degradation — return empty list on API failure
        return []

    results: list[ActiveBillItem] = []
    for bill in bills_data:
        title = bill.get("title", "")
        number = bill.get("number", "")
        bill_type = bill.get("type", "")
        congress = bill.get("congress", "")
        latest_action = bill.get("latestAction", {})
        action_text = latest_action.get("text", "")

        slug = _slugify(f"{bill_type}-{number}-{congress}")

        # Check if we already track this bill in our DB
        entity = (
            await db.execute(select(Entity).where(Entity.slug == slug))
        ).scalar_one_or_none()

        conflict_score = "NONE"
        if entity and entity.metadata_:
            conflict_score = entity.metadata_.get("conflict_score", "NONE")

        results.append(
            ActiveBillItem(
                title=title,
                number=f"{bill_type}.{number}",
                congress=congress,
                slug=slug,
                status=_bill_status(action_text),
                latest_action=action_text,
                update_date=bill.get("updateDate", ""),
                in_db=entity is not None,
                conflict_score=conflict_score,
            )
        )

    return results


# ---------------------------------------------------------------------------
# 2. Top Conflicts — officials with the most conflict signals
# ---------------------------------------------------------------------------


@router.get("/top-conflicts", response_model=list[TopConflictItem])
async def top_conflicts(db: AsyncSession = Depends(get_db)):
    """Return officials with the most conflict signals."""
    try:
        from app.services.conflict_engine import detect_conflicts
    except ImportError:
        # conflict_engine not yet available — return empty
        return []

    persons = (
        await db.execute(
            select(Entity).where(Entity.entity_type == "person").limit(50)
        )
    ).scalars().all()

    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}

    results: list[TopConflictItem] = []
    for person in persons:
        try:
            conflicts = await detect_conflicts(db, person.slug)
        except Exception:
            continue
        if not conflicts:
            continue

        top = max(
            conflicts,
            key=lambda c: severity_rank.get(c.severity.lower(), 0),
        )
        meta = person.metadata_ or {}
        results.append(
            TopConflictItem(
                slug=person.slug,
                name=person.name,
                party=meta.get("party", ""),
                state=meta.get("state", ""),
                conflict_score=top.severity.upper(),
                total_conflicts=len(conflicts),
                top_conflict=top.description,
            )
        )

    results.sort(key=lambda x: x.total_conflicts, reverse=True)
    return results[:5]


# ---------------------------------------------------------------------------
# 3. Stats — quick DB stats for the homepage
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=DashboardStats)
async def dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Return quick stats for the homepage."""
    officials = (
        await db.execute(
            select(func.count())
            .select_from(Entity)
            .where(Entity.entity_type == "person")
        )
    ).scalar() or 0

    bills = (
        await db.execute(
            select(func.count())
            .select_from(Entity)
            .where(Entity.entity_type == "bill")
        )
    ).scalar() or 0

    donations_total = (
        await db.execute(
            select(func.sum(Relationship.amount_usd)).where(
                Relationship.relationship_type == "donated_to"
            )
        )
    ).scalar() or 0

    lobbying = (
        await db.execute(
            select(func.count())
            .select_from(Relationship)
            .where(
                Relationship.relationship_type.in_(
                    [
                        "lobbied_for",
                        "lobbies_on_behalf_of",
                        "registered_lobbyist_for",
                    ]
                )
            )
        )
    ).scalar() or 0

    return DashboardStats(
        officials_count=officials,
        bills_count=bills,
        donations_total=donations_total,
        conflicts_count=0,  # Computed later when conflict engine is fully integrated
        lobbying_count=lobbying,
    )


# ---------------------------------------------------------------------------
# 4. Featured Story — AI-generated investigation story, cached in app_config
# ---------------------------------------------------------------------------

_DEFAULT_STORY = FeaturedStory(
    headline="Investigation data loading...",
    narrative="Check back soon for featured investigations.",
    entity_slug=None,
)


@router.get("/featured-story", response_model=FeaturedStory)
async def featured_story(db: AsyncSession = Depends(get_db)):
    """Return featured investigation story. Generated via claude CLI, cached."""
    cached = (
        await db.execute(
            select(AppConfig).where(AppConfig.key == "featured_story")
        )
    ).scalar_one_or_none()

    if cached and cached.value:
        try:
            data = json.loads(cached.value)
            return FeaturedStory(**data)
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

    return _DEFAULT_STORY
