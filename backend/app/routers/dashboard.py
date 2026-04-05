"""Dashboard API — powers the homepage intelligence dashboard."""

import json
import os
import re

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AppConfig, Entity, MoneyTrail, Relationship
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


import time as _time

# Simple in-memory cache for top-conflicts (expensive query)
_top_conflicts_cache: dict[str, tuple[float, list]] = {}
_CACHE_TTL = 300  # 5 minutes


@router.get("/top-conflicts", response_model=list[TopConflictItem])
async def top_conflicts(db: AsyncSession = Depends(get_db)):
    """Return officials with the most multi-factor conflict signals.

    Cached for 5 minutes to avoid re-scanning all 500 officials on every page load.
    """
    cache_key = "top_conflicts"
    if cache_key in _top_conflicts_cache:
        cached_at, cached_data = _top_conflicts_cache[cache_key]
        if _time.time() - cached_at < _CACHE_TTL:
            return cached_data
    try:
        from app.services.conflict_engine import detect_conflicts
    except ImportError:
        return []

    # Scan all officials, not just first 50
    persons = (
        await db.execute(
            select(Entity)
            .where(Entity.entity_type == "person")
            .where(Entity.metadata_.has_key("bioguide_id"))
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

        # Combine all signals into a single summary per official
        top = max(
            conflicts,
            key=lambda c: severity_rank.get(c.severity.lower(), 0),
        )
        meta = person.metadata_ or {}

        # Build a combined description from all conflict signals
        all_committees = set()
        all_donors = {}  # name -> amount
        for c in conflicts:
            for ev in (c.evidence or []):
                if ev.get("type") == "committee":
                    all_committees.add(ev.get("name", ""))
                elif ev.get("type") == "donation":
                    name = ev.get("name", "")
                    amt = ev.get("amount", 0) or 0
                    if name not in all_donors or amt > all_donors[name]:
                        all_donors[name] = amt

        total_conflict_dollars = sum(all_donors.values())

        if all_committees and all_donors:
            committees_str = ", ".join(list(all_committees)[:3])
            if len(all_committees) > 3:
                committees_str += f" (+{len(all_committees) - 3} more)"
            # Name the top donors by amount
            top_donor_names = sorted(all_donors.keys(), key=lambda n: -all_donors[n])[:3]
            dollars_str = f"${total_conflict_dollars / 100:,.0f}" if total_conflict_dollars else ""
            combined_desc = (
                f"Sits on {committees_str}. "
                f"Receives {dollars_str + ' from ' if dollars_str else 'donations from '}"
                f"{len(all_donors)} regulated-industry donor{'s' if len(all_donors) != 1 else ''}"
                f" including {', '.join(top_donor_names[:2])}."
            )
        else:
            combined_desc = top.description

        results.append((
            total_conflict_dollars,
            TopConflictItem(
                slug=person.slug,
                name=person.name,
                party=meta.get("party", ""),
                state=meta.get("state", ""),
                conflict_score=top.severity.upper(),
                total_conflicts=len(all_donors) if all_donors else len(conflicts),
                top_conflict=combined_desc,
            ),
        ))

    # Sort by severity first, then by dollar amount, then by donor count
    score_rank = {
        "HIGH_CONCERN": 4, "NOTABLE_PATTERN": 3,
        "STRUCTURAL_RELATIONSHIP": 2, "CONNECTION_NOTED": 1,
    }
    results.sort(
        key=lambda x: (score_rank.get(x[1].conflict_score, 0), x[0], x[1].total_conflicts),
        reverse=True,
    )
    # Unwrap tuples
    results = [item for _, item in results]

    # If conflict engine found results, cache and return
    if results:
        final = results[:10]
        _top_conflicts_cache[cache_key] = (_time.time(), final)
        return final

    # Fallback: rank officials by total donations received (most funded = most to investigate)
    from sqlalchemy import desc
    top_funded_q = (
        select(
            Relationship.to_entity_id,
            func.sum(Relationship.amount_usd).label("total"),
            func.count(func.distinct(Relationship.from_entity_id)).label("donor_count"),
        )
        .where(Relationship.relationship_type == "donated_to")
        .group_by(Relationship.to_entity_id)
        .order_by(desc("total"))
        .limit(10)
    )
    funded_rows = (await db.execute(top_funded_q)).all()

    if not funded_rows:
        return []

    entity_ids = [r[0] for r in funded_rows]
    entities_result = await db.execute(
        select(Entity).where(Entity.id.in_(entity_ids))
    )
    entities_map = {e.id: e for e in entities_result.scalars().all()}

    # For each top-funded official, categorize the type of money trail
    # Check for different relationship types to vary the badge
    fallback_results = []
    for entity_id, total_donated, donor_count in funded_rows:
        entity = entities_map.get(entity_id)
        if not entity or entity.entity_type != "person":
            continue
        meta = entity.metadata_ or {}
        if not meta.get("bioguide_id"):
            continue

        dollars = (total_donated or 0) / 100

        # Check what types of connections this official has
        rel_types_q = (
            select(Relationship.relationship_type, func.count().label("cnt"))
            .where(
                (Relationship.from_entity_id == entity_id) |
                (Relationship.to_entity_id == entity_id)
            )
            .where(Relationship.relationship_type.notin_(["sponsored", "cosponsored"]))
            .group_by(Relationship.relationship_type)
        )
        rel_rows = (await db.execute(rel_types_q)).all()
        rel_map = {r[0]: r[1] for r in rel_rows}

        # Determine the most interesting conflict type and description
        if rel_map.get("holds_stock", 0) > 0 and rel_map.get("donated_to", 0) > 0:
            score = "HIGH_CONCERN"
            desc = f"Holds stock in companies while receiving ${dollars:,.0f} from {donor_count} donors. Are their investments influencing their votes?"
        elif rel_map.get("holds_stock", 0) > 0:
            score = "NOTABLE_PATTERN"
            desc = f"Holds stock in companies their committees may regulate. Financial interests and public duties overlap."
        elif rel_map.get("book_deal_with", 0) > 0 or rel_map.get("speaking_fee_from", 0) > 0:
            score = "NOTABLE_PATTERN"
            desc = f"Receives outside income (book deals, speaking fees) from organizations with policy interests, plus ${dollars:,.0f} in campaign donations."
        elif rel_map.get("spouse_income_from", 0) > 0 or rel_map.get("family_employed_by", 0) > 0:
            score = "NOTABLE_PATTERN"
            desc = f"Family members earn income from companies with policy interests. Also received ${dollars:,.0f} from {donor_count} campaign donors."
        elif donor_count >= 15:
            score = "NOTABLE_PATTERN"
            desc = f"Received ${dollars:,.0f} from {donor_count} donors — one of the most heavily funded officials. Who are they, and what do they want?"
        elif dollars >= 100000000:  # $1M+ in cents
            score = "STRUCTURAL_RELATIONSHIP"
            desc = f"Received ${dollars:,.0f} in campaign contributions from {donor_count} donors. Heavy funding warrants a closer look."
        else:
            score = "CONNECTION_NOTED"
            desc = f"Received ${dollars:,.0f} from {donor_count} donors. Click to see who funds this official."

        fallback_results.append(
            TopConflictItem(
                slug=entity.slug,
                name=entity.name,
                party=meta.get("party", ""),
                state=meta.get("state", ""),
                conflict_score=score,
                total_conflicts=donor_count,
                top_conflict=desc,
            )
        )

    final = fallback_results[:10]
    _top_conflicts_cache[cache_key] = (_time.time(), final)
    return final


# ---------------------------------------------------------------------------
# 2b. Top Influencers — entities with the most political reach
# ---------------------------------------------------------------------------


@router.get("/top-influencers")
async def top_influencers(db: AsyncSession = Depends(get_db)):
    """Return entities (companies, PACs, orgs) ranked by political influence.

    Influence = total donations + number of officials funded.
    """
    # Find entities that have donated_to relationships (they are the from_entity)
    query = (
        select(
            Relationship.from_entity_id,
            func.sum(Relationship.amount_usd).label("total_donated"),
            func.count(func.distinct(Relationship.to_entity_id)).label("officials_funded"),
        )
        .where(Relationship.relationship_type == "donated_to")
        .group_by(Relationship.from_entity_id)
        .having(func.count(func.distinct(Relationship.to_entity_id)) >= 2)
        .order_by(func.sum(Relationship.amount_usd).desc())
        .limit(20)
    )
    rows = (await db.execute(query)).all()

    if not rows:
        return []

    # Load the entity details
    entity_ids = [r[0] for r in rows]
    entities_result = await db.execute(
        select(Entity).where(Entity.id.in_(entity_ids))
    )
    entities_map = {e.id: e for e in entities_result.scalars().all()}

    results = []
    for entity_id, total_donated, officials_funded in rows:
        entity = entities_map.get(entity_id)
        if not entity:
            continue
        # Skip individual person donors — only show orgs/companies/PACs
        if entity.entity_type == "person" and not (entity.metadata_ or {}).get("donor_type") == "pac":
            continue
        results.append({
            "slug": entity.slug,
            "name": entity.name,
            "entity_type": entity.entity_type,
            "total_donated": total_donated or 0,
            "officials_funded": officials_funded,
        })

    return results[:10]


# ---------------------------------------------------------------------------
# 2c. Revolving Door — former staffers now lobbying (real LDA data)
# ---------------------------------------------------------------------------


@router.get("/revolving-door")
async def dashboard_revolving_door(db: AsyncSession = Depends(get_db)):
    """Return recent revolving door connections from real LDA data."""
    # Find revolving_door_lobbyist relationships with connected officials
    rels_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.to_entity_id)
        .where(Relationship.relationship_type == "revolving_door_lobbyist")
        .where(Entity.entity_type == "person")
        .where(Entity.metadata_.has_key("bioguide_id"))
        .limit(15)
    )
    rows = (await db.execute(rels_q)).all()

    if not rows:
        return []

    # Load lobbyist entities
    lobbyist_ids = [r[0].from_entity_id for r in rows]
    lobbyist_result = await db.execute(
        select(Entity).where(Entity.id.in_(lobbyist_ids))
    )
    lobbyists = {e.id: e for e in lobbyist_result.scalars().all()}

    results = []
    seen = set()
    for rel, official in rows:
        lobbyist = lobbyists.get(rel.from_entity_id)
        if not lobbyist:
            continue
        # Deduplicate by lobbyist
        if lobbyist.slug in seen:
            continue
        seen.add(lobbyist.slug)

        meta = rel.metadata_ or {}
        official_meta = official.metadata_ or {}
        lobbyist_meta = lobbyist.metadata_ or {}

        former_position = meta.get("former_position", lobbyist_meta.get("covered_position", ""))
        current_employer = meta.get("current_employer", lobbyist_meta.get("current_employer", ""))

        results.append({
            "lobbyist_name": lobbyist.name,
            "lobbyist_slug": lobbyist.slug,
            "former_position": former_position[:200] if former_position else "",
            "current_employer": current_employer,
            "official_name": official.name,
            "official_slug": official.slug,
            "official_party": official_meta.get("party", ""),
            "official_state": official_meta.get("state", ""),
        })

    return results


# ---------------------------------------------------------------------------
# 3. States — senator data grouped by state for the map
# ---------------------------------------------------------------------------


@router.get("/states")
async def dashboard_states(db: AsyncSession = Depends(get_db)):
    """Return senators grouped by state for the interactive map."""
    result = await db.execute(
        select(Entity)
        .where(Entity.entity_type == "person")
        .where(Entity.metadata_["chamber"].astext == "Senate")
    )
    senators = result.scalars().all()

    state_map: dict[str, list] = {}
    for s in senators:
        meta = s.metadata_ or {}
        state = meta.get("state", "Unknown")
        party = meta.get("party", "Unknown")
        if state not in state_map:
            state_map[state] = []
        state_map[state].append({
            "name": s.name,
            "slug": s.slug,
            "party": party,
        })

    states = []
    for state_name, senators_list in sorted(state_map.items()):
        parties = set(s["party"] for s in senators_list)
        if len(parties) == 1:
            dominant = list(parties)[0]
        elif "Independent" in parties:
            other = parties - {"Independent"}
            dominant = "Split" if len(other) > 0 else "Independent"
        else:
            dominant = "Split"

        states.append({
            "state": state_name,
            "senators": senators_list,
            "dominantParty": dominant,
        })

    return states


# ---------------------------------------------------------------------------
# 4. Stats — quick DB stats for the homepage
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
        conflicts_count=(
            await db.execute(
                select(func.count())
                .select_from(MoneyTrail)
                .where(MoneyTrail.verdict.in_(["OWNED", "INFLUENCED"]))
            )
        ).scalar() or 0,
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
