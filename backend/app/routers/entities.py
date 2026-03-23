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
