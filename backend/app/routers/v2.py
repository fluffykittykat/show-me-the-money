"""V2 API — single response per page.

Each endpoint serves ALL data the frontend needs for a given page,
eliminating waterfall fetches.
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AppConfig, Entity, MoneyTrail, Relationship
from app.schemas import (
    EntityResponse,
    V2BillResponse,
    V2EntityResponse,
    V2HomepageResponse,
    V2MoneyTrail,
    V2OfficialResponse,
)

router = APIRouter(tags=["v2"])


# ---------------------------------------------------------------------------
# GET /v2/official/{slug}
# ---------------------------------------------------------------------------


@router.get("/official/{slug}", response_model=V2OfficialResponse)
async def v2_official(slug: str, db: AsyncSession = Depends(get_db)):
    """Return everything the Official page needs in one response."""

    entity = (
        await db.execute(select(Entity).where(Entity.slug == slug))
    ).scalar_one_or_none()

    if not entity or entity.entity_type != "person":
        raise HTTPException(status_code=404, detail="Official not found")

    meta = entity.metadata_ or {}

    # --- Money trails (pre-computed) ---
    trails_result = await db.execute(
        select(MoneyTrail)
        .where(MoneyTrail.official_id == entity.id)
        .order_by(MoneyTrail.dot_count.desc())
    )
    trails = trails_result.scalars().all()

    money_trails = []
    for t in trails:
        chain_data = t.chain or {}
        dots = chain_data.get("dots", [])
        # Ensure dots is a list of strings
        if not isinstance(dots, list):
            dots = []
        money_trails.append(
            V2MoneyTrail(
                industry=t.industry,
                verdict=t.verdict,
                dot_count=t.dot_count,
                dots=dots,
                narrative=t.narrative,
                total_amount=t.total_amount or 0,
                chain=chain_data,
            )
        )

    # --- Overall verdict from entity metadata ---
    overall_verdict = meta.get("v2_verdict", "NORMAL")
    total_dots = meta.get("v2_dot_count", 0)

    # --- Top donors: aggregate donated_to where to_entity = official ---
    donor_q = (
        select(
            Relationship.from_entity_id,
            func.sum(Relationship.amount_usd).label("total"),
        )
        .where(Relationship.to_entity_id == entity.id)
        .where(Relationship.relationship_type == "donated_to")
        .group_by(Relationship.from_entity_id)
        .order_by(func.sum(Relationship.amount_usd).desc())
        .limit(15)
    )
    donor_rows = (await db.execute(donor_q)).all()

    # Load donor entities
    donor_ids = [r[0] for r in donor_rows]
    donor_entities = {}
    if donor_ids:
        de_result = await db.execute(
            select(Entity).where(Entity.id.in_(donor_ids))
        )
        donor_entities = {e.id: e for e in de_result.scalars().all()}

    top_donors = []
    middlemen = []
    for donor_id, total_donated in donor_rows:
        de = donor_entities.get(donor_id)
        if not de:
            continue
        entry = {
            "slug": de.slug,
            "name": de.name,
            "entity_type": de.entity_type,
            "total_donated": total_donated or 0,
        }
        top_donors.append(entry)
        if de.entity_type == "pac":
            middlemen.append(entry)

    # --- Committees from committee_member relationships ---
    committee_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.to_entity_id)
        .where(Relationship.from_entity_id == entity.id)
        .where(Relationship.relationship_type == "committee_member")
    )
    committee_rows = (await db.execute(committee_q)).all()

    committees = []
    for rel, committee_entity in committee_rows:
        rel_meta = rel.metadata_ or {}
        committees.append({
            "slug": committee_entity.slug,
            "name": committee_entity.name,
            "role": rel_meta.get("role", "Member"),
        })

    # --- Briefing ---
    briefing = meta.get("fbi_briefing")

    # --- Freshness ---
    has_donors = len(top_donors) > 0
    has_committees = len(committees) > 0
    freshness = {
        "fec_cycle": meta.get("best_fec_cycle"),
        "last_refreshed": meta.get("last_refreshed"),
        "has_donors": has_donors,
        "has_committees": has_committees,
    }

    return V2OfficialResponse(
        entity=EntityResponse.model_validate(entity),
        overall_verdict=overall_verdict,
        total_dots=total_dots,
        money_trails=money_trails,
        top_donors=top_donors,
        middlemen=middlemen,
        committees=committees,
        briefing=briefing,
        freshness=freshness,
    )


# ---------------------------------------------------------------------------
# GET /v2/bill/{slug}
# ---------------------------------------------------------------------------


_STATUS_MAP = {
    "became_law": "BECAME LAW",
    "becamelaw": "BECAME LAW",
    "enacted": "BECAME LAW",
    "in_committee": "IN COMMITTEE",
    "committee": "IN COMMITTEE",
    "passed": "PASSED",
    "failed": "FAILED",
    "vetoed": "FAILED",
    "introduced": "INTRODUCED",
}


def _parse_bill_status(raw: str | None) -> str:
    if not raw:
        return "INTRODUCED"
    key = raw.lower().replace(" ", "_").replace("-", "_")
    return _STATUS_MAP.get(key, raw.upper())


@router.get("/bill/{slug}", response_model=V2BillResponse)
async def v2_bill(slug: str, db: AsyncSession = Depends(get_db)):
    """Return everything the Bill page needs in one response."""

    entity = (
        await db.execute(select(Entity).where(Entity.slug == slug))
    ).scalar_one_or_none()

    if not entity or entity.entity_type != "bill":
        raise HTTPException(status_code=404, detail="Bill not found")

    meta = entity.metadata_ or {}
    status_label = _parse_bill_status(meta.get("status"))

    # --- Sponsors / cosponsors ---
    sponsor_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.to_entity_id == entity.id)
        .where(
            Relationship.relationship_type.in_(["sponsored", "cosponsored"])
        )
    )
    sponsor_rows = (await db.execute(sponsor_q)).all()

    sponsors = []
    for rel, sponsor_entity in sponsor_rows:
        s_meta = sponsor_entity.metadata_ or {}
        sponsors.append({
            "slug": sponsor_entity.slug,
            "name": sponsor_entity.name,
            "party": s_meta.get("party", ""),
            "state": s_meta.get("state", ""),
            "role": rel.relationship_type,  # "sponsored" or "cosponsored"
            "top_donor": s_meta.get("top_donor"),
            "verdict": s_meta.get("v2_verdict"),
        })

    briefing = meta.get("fbi_briefing")

    return V2BillResponse(
        entity=EntityResponse.model_validate(entity),
        status_label=status_label,
        sponsors=sponsors,
        briefing=briefing,
    )


# ---------------------------------------------------------------------------
# GET /v2/entity/{slug}
# ---------------------------------------------------------------------------


@router.get("/entity/{slug}", response_model=V2EntityResponse)
async def v2_entity(slug: str, db: AsyncSession = Depends(get_db)):
    """Return everything an Entity page needs in one response."""

    entity = (
        await db.execute(select(Entity).where(Entity.slug == slug))
    ).scalar_one_or_none()

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    meta = entity.metadata_ or {}

    # --- Money in: donated_to where this entity is to_entity ---
    money_in_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.to_entity_id == entity.id)
        .where(Relationship.relationship_type == "donated_to")
        .order_by(Relationship.amount_usd.desc().nullslast())
        .limit(50)
    )
    money_in_rows = (await db.execute(money_in_q)).all()

    money_in = []
    for rel, from_entity in money_in_rows:
        money_in.append({
            "slug": from_entity.slug,
            "name": from_entity.name,
            "entity_type": from_entity.entity_type,
            "amount_usd": rel.amount_usd or 0,
            "amount_label": rel.amount_label,
        })

    # --- Money out: donated_to where this entity is from_entity ---
    money_out_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.to_entity_id)
        .where(Relationship.from_entity_id == entity.id)
        .where(Relationship.relationship_type == "donated_to")
        .order_by(Relationship.amount_usd.desc().nullslast())
        .limit(50)
    )
    money_out_rows = (await db.execute(money_out_q)).all()

    money_out = []
    for rel, to_entity in money_out_rows:
        money_out.append({
            "slug": to_entity.slug,
            "name": to_entity.name,
            "entity_type": to_entity.entity_type,
            "amount_usd": rel.amount_usd or 0,
            "amount_label": rel.amount_label,
        })

    briefing = meta.get("fbi_briefing")

    return V2EntityResponse(
        entity=EntityResponse.model_validate(entity),
        money_in=money_in,
        money_out=money_out,
        briefing=briefing,
    )


# ---------------------------------------------------------------------------
# GET /v2/homepage
# ---------------------------------------------------------------------------


@router.get("/homepage", response_model=V2HomepageResponse)
async def v2_homepage(db: AsyncSession = Depends(get_db)):
    """Return everything the homepage needs in one response."""

    # --- Top stories from app_config (pre-computed) ---
    top_stories: list[dict] = []
    story_row = (
        await db.execute(
            select(AppConfig).where(AppConfig.key == "v2_story_feed")
        )
    ).scalar_one_or_none()
    if story_row and story_row.value:
        try:
            top_stories = json.loads(story_row.value)
        except (json.JSONDecodeError, TypeError):
            pass

    # --- Stats ---
    officials_count = (
        await db.execute(
            select(func.count())
            .select_from(Entity)
            .where(Entity.entity_type == "person")
        )
    ).scalar() or 0

    bills_count = (
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

    relationship_count = (
        await db.execute(
            select(func.count()).select_from(Relationship)
        )
    ).scalar() or 0

    stats = {
        "officials_count": officials_count,
        "bills_count": bills_count,
        "donations_total": donations_total,
        "relationship_count": relationship_count,
    }

    # --- Top officials by v2_dot_count ---
    # Filter entities that have v2_verdict in metadata
    officials_q = (
        select(Entity)
        .where(Entity.entity_type == "person")
        .where(Entity.metadata_.has_key("v2_verdict"))
        .limit(100)
    )
    officials_result = (await db.execute(officials_q)).scalars().all()

    # Sort by v2_dot_count descending in Python (JSONB sort is tricky)
    officials_sorted = sorted(
        officials_result,
        key=lambda e: (e.metadata_ or {}).get("v2_dot_count", 0),
        reverse=True,
    )[:10]

    top_officials = []
    for o in officials_sorted:
        m = o.metadata_ or {}
        top_officials.append({
            "slug": o.slug,
            "name": o.name,
            "party": m.get("party", ""),
            "state": m.get("state", ""),
            "verdict": m.get("v2_verdict", "NORMAL"),
            "dot_count": m.get("v2_dot_count", 0),
        })

    # --- Top influencers (same logic as dashboard) ---
    influencer_q = (
        select(
            Relationship.from_entity_id,
            func.sum(Relationship.amount_usd).label("total_donated"),
            func.count(func.distinct(Relationship.to_entity_id)).label(
                "officials_funded"
            ),
        )
        .where(Relationship.relationship_type == "donated_to")
        .group_by(Relationship.from_entity_id)
        .having(func.count(func.distinct(Relationship.to_entity_id)) >= 2)
        .order_by(func.sum(Relationship.amount_usd).desc())
        .limit(20)
    )
    inf_rows = (await db.execute(influencer_q)).all()

    inf_ids = [r[0] for r in inf_rows]
    inf_entities = {}
    if inf_ids:
        ie_result = await db.execute(
            select(Entity).where(Entity.id.in_(inf_ids))
        )
        inf_entities = {e.id: e for e in ie_result.scalars().all()}

    top_influencers = []
    for entity_id, total_donated, officials_funded in inf_rows:
        ie = inf_entities.get(entity_id)
        if not ie:
            continue
        if ie.entity_type == "person" and not (ie.metadata_ or {}).get(
            "donor_type"
        ) == "pac":
            continue
        top_influencers.append({
            "slug": ie.slug,
            "name": ie.name,
            "entity_type": ie.entity_type,
            "total_donated": total_donated or 0,
            "officials_funded": officials_funded,
        })
        if len(top_influencers) >= 10:
            break

    # --- Revolving door (same logic as dashboard) ---
    rd_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.to_entity_id)
        .where(Relationship.relationship_type == "revolving_door_lobbyist")
        .where(Entity.entity_type == "person")
        .where(Entity.metadata_.has_key("bioguide_id"))
        .limit(15)
    )
    rd_rows = (await db.execute(rd_q)).all()

    lobbyist_ids = [r[0].from_entity_id for r in rd_rows]
    lobbyist_map = {}
    if lobbyist_ids:
        lb_result = await db.execute(
            select(Entity).where(Entity.id.in_(lobbyist_ids))
        )
        lobbyist_map = {e.id: e for e in lb_result.scalars().all()}

    revolving_door = []
    seen_lobbyists: set[str] = set()
    for rel, official in rd_rows:
        lobbyist = lobbyist_map.get(rel.from_entity_id)
        if not lobbyist or lobbyist.slug in seen_lobbyists:
            continue
        seen_lobbyists.add(lobbyist.slug)
        r_meta = rel.metadata_ or {}
        o_meta = official.metadata_ or {}
        l_meta = lobbyist.metadata_ or {}
        revolving_door.append({
            "lobbyist_name": lobbyist.name,
            "lobbyist_slug": lobbyist.slug,
            "former_position": (
                r_meta.get("former_position", l_meta.get("covered_position", ""))
                or ""
            )[:200],
            "current_employer": r_meta.get(
                "current_employer", l_meta.get("current_employer", "")
            ),
            "official_name": official.name,
            "official_slug": official.slug,
            "official_party": o_meta.get("party", ""),
            "official_state": o_meta.get("state", ""),
        })

    return V2HomepageResponse(
        top_stories=top_stories,
        stats=stats,
        top_officials=top_officials,
        top_influencers=top_influencers,
        revolving_door=revolving_door,
    )
