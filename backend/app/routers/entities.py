from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Entity, Relationship
from app.schemas import (
    ConnectionsResponse,
    EntityBrief,
    EntityResponse,
    FlatConnectionItem,
)

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("/{slug}", response_model=EntityResponse)
async def get_entity(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.get("/{slug}/connections", response_model=ConnectionsResponse)
async def get_entity_connections(
    slug: str,
    type: Optional[str] = Query(None, description="Filter by relationship type"),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Build query for relationships where this entity is either from or to
    base_q = select(Relationship).where(
        or_(
            Relationship.from_entity_id == entity.id,
            Relationship.to_entity_id == entity.id,
        )
    )
    if type:
        base_q = base_q.where(Relationship.relationship_type == type)

    # Count
    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar()

    # Fetch page
    rels_q = base_q.offset(offset).limit(limit)
    rels_result = await db.execute(rels_q)
    rels = rels_result.scalars().all()

    # Gather connected entity IDs
    connected_ids = set()
    for r in rels:
        if r.from_entity_id == entity.id:
            connected_ids.add(r.to_entity_id)
        else:
            connected_ids.add(r.from_entity_id)

    # Fetch connected entities
    entities_map = {}
    if connected_ids:
        ent_result = await db.execute(
            select(Entity).where(Entity.id.in_(connected_ids))
        )
        for e in ent_result.scalars().all():
            entities_map[e.id] = e

    # Build flat connection items
    connections = []
    for r in rels:
        connected_id = (
            r.to_entity_id if r.from_entity_id == entity.id else r.from_entity_id
        )
        connected = entities_map.get(connected_id)
        connections.append(
            FlatConnectionItem(
                id=r.id,
                from_entity_id=r.from_entity_id,
                to_entity_id=r.to_entity_id,
                relationship_type=r.relationship_type,
                amount_usd=r.amount_usd,
                amount_label=r.amount_label,
                date_start=r.date_start,
                date_end=r.date_end,
                source_url=r.source_url,
                source_label=r.source_label,
                metadata=r.metadata_,
                connected_entity=EntityBrief.model_validate(connected)
                if connected
                else None,
            )
        )

    return ConnectionsResponse(
        entity=EntityResponse.model_validate(entity),
        connections=connections,
        total=total,
    )


@router.get("/{slug}/money-to-bills")
async def get_money_to_bills(slug: str, db: AsyncSession = Depends(get_db)):
    """Trace the chain: Donor → gave money → Official → sponsored Bill.

    Groups by policy area to show where donor industries align with
    the official's legislative activity.
    """
    result = await db.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Find donor→official→bill chains
    from sqlalchemy import text as sql_text
    chains_query = sql_text("""
        SELECT
            donor.name as donor_name,
            donor.slug as donor_slug,
            donor_rel.amount_usd as donation_amount,
            bill.name as bill_name,
            bill.slug as bill_slug,
            bill.metadata->>'policy_area' as policy_area,
            bill.metadata->>'status' as bill_status,
            bill_rel.relationship_type as bill_rel_type
        FROM relationships donor_rel
        JOIN entities donor ON donor.id = donor_rel.from_entity_id
        JOIN relationships bill_rel ON bill_rel.from_entity_id = :entity_id
        JOIN entities bill ON bill.id = bill_rel.to_entity_id
        WHERE donor_rel.to_entity_id = :entity_id
        AND donor_rel.relationship_type = 'donated_to'
        AND bill_rel.relationship_type IN ('sponsored', 'cosponsored')
        AND bill.metadata->>'policy_area' IS NOT NULL
        AND bill.metadata->>'policy_area' != ''
        AND donor_rel.amount_usd > 10000
        ORDER BY donor_rel.amount_usd DESC
        LIMIT 200
    """)

    rows = (await db.execute(chains_query, {"entity_id": entity.id})).fetchall()

    # Group by policy area to find patterns
    from collections import defaultdict
    by_area: dict[str, dict] = defaultdict(lambda: {"donors": {}, "bills": set(), "total_donated": 0})

    for row in rows:
        area = row.policy_area or "Other"
        donor_key = row.donor_name
        if donor_key not in by_area[area]["donors"]:
            by_area[area]["donors"][donor_key] = {
                "name": row.donor_name,
                "slug": row.donor_slug,
                "amount": row.donation_amount or 0,
            }
        by_area[area]["bills"].add((row.bill_name, row.bill_slug, row.bill_rel_type))
        by_area[area]["total_donated"] = max(by_area[area]["total_donated"],
            sum(d["amount"] for d in by_area[area]["donors"].values()))

    # Format results
    results = []
    for area, data in sorted(by_area.items(), key=lambda x: -x[1]["total_donated"]):
        donors = sorted(data["donors"].values(), key=lambda d: -d["amount"])[:5]
        bills = [{"name": b[0], "slug": b[1], "type": b[2]} for b in list(data["bills"])[:5]]
        if donors and bills:
            results.append({
                "policy_area": area,
                "total_donated": data["total_donated"],
                "donor_count": len(data["donors"]),
                "bill_count": len(data["bills"]),
                "top_donors": donors,
                "related_bills": bills,
                "narrative": (
                    f"{len(data['donors'])} donor{'s' if len(data['donors']) > 1 else ''} "
                    f"from the {area} sector gave money to this official, who then "
                    f"{'sponsored' if bills[0]['type'] == 'sponsored' else 'cosponsored'} "
                    f"{len(data['bills'])} bill{'s' if len(data['bills']) > 1 else ''} "
                    f"in {area}."
                ),
            })

    return {
        "entity": slug,
        "entity_name": entity.name,
        "chains": results[:10],
        "total_chains": len(results),
    }


@router.get("/{slug}/influence-map")
async def get_influence_map(slug: str, db: AsyncSession = Depends(get_db)):
    """Find entities that both donate to AND lobby related to this official.

    These are the strongest influence signals: an entity gives money to
    your campaign AND pays lobbyists to influence legislation.
    """
    result = await db.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Find all donors to this official
    donor_rels = (await db.execute(
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(
            Relationship.to_entity_id == entity.id,
            Relationship.relationship_type == "donated_to",
        )
    )).all()

    if not donor_rels:
        return {"entity": slug, "dual_influence": [], "total": 0}

    # Get all lobbying clients
    lobby_clients = (await db.execute(
        select(Entity.name, Entity.slug, Entity.id)
        .join(Relationship, Relationship.to_entity_id == Entity.id)
        .where(Relationship.relationship_type == "lobbies_on_behalf_of")
    )).all()

    # Build a lookup of lobby client names (lowercased) -> slug
    lobby_lookup: dict[str, str] = {}
    for name, client_slug, client_id in lobby_clients:
        lobby_lookup[name.lower()] = client_slug

    # Match donors to lobby clients
    dual_influence = []
    for rel, donor_entity in donor_rels:
        donor_name = donor_entity.name.lower()
        # Check if this donor (or part of their name) matches a lobbying client
        matched_client = None
        for lobby_name, lobby_slug in lobby_lookup.items():
            # Match if donor name contains the lobby client name or vice versa
            donor_key = donor_name.split(",")[0].strip() if "," in donor_name else donor_name
            if len(donor_key) > 5 and (donor_key in lobby_name or lobby_name in donor_key):
                matched_client = lobby_name
                break

        if matched_client:
            dual_influence.append({
                "donor_name": donor_entity.name,
                "donor_slug": donor_entity.slug,
                "donor_type": donor_entity.entity_type,
                "donation_amount": rel.amount_usd or 0,
                "also_lobbies": True,
                "lobby_client_name": matched_client.title(),
            })

    dual_influence.sort(key=lambda x: x["donation_amount"], reverse=True)

    return {
        "entity": slug,
        "entity_name": entity.name,
        "dual_influence": dual_influence,
        "total": len(dual_influence),
        "total_donors": len(donor_rels),
    }
