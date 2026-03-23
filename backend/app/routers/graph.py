from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Entity, Relationship
from app.schemas import GraphEdge, GraphNode, GraphResponse

router = APIRouter(tags=["graph"])


@router.get("/graph/{slug}", response_model=GraphResponse)
async def get_entity_graph(
    slug: str,
    depth: int = Query(1, ge=1, le=3),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Entity).where(Entity.slug == slug))
    root = result.scalar_one_or_none()
    if not root:
        raise HTTPException(status_code=404, detail="Entity not found")

    visited_ids = {root.id}
    all_edges = []
    frontier_ids = {root.id}

    for _ in range(depth):
        if not frontier_ids:
            break

        rels_q = select(Relationship).where(
            or_(
                Relationship.from_entity_id.in_(frontier_ids),
                Relationship.to_entity_id.in_(frontier_ids),
            )
        )
        rels_result = await db.execute(rels_q)
        rels = rels_result.scalars().all()

        next_frontier = set()
        for r in rels:
            all_edges.append(r)
            for eid in (r.from_entity_id, r.to_entity_id):
                if eid not in visited_ids:
                    visited_ids.add(eid)
                    next_frontier.add(eid)

        frontier_ids = next_frontier

    # Fetch all entities
    if visited_ids:
        ent_result = await db.execute(
            select(Entity).where(Entity.id.in_(visited_ids))
        )
        entities = ent_result.scalars().all()
    else:
        entities = [root]

    # Deduplicate edges by id
    seen_edge_ids = set()
    unique_edges = []
    for e in all_edges:
        if e.id not in seen_edge_ids:
            seen_edge_ids.add(e.id)
            unique_edges.append(e)

    nodes = [
        GraphNode(id=e.id, slug=e.slug, name=e.name, entity_type=e.entity_type)
        for e in entities
    ]
    edges = [
        GraphEdge(
            source=e.from_entity_id,
            target=e.to_entity_id,
            relationship_type=e.relationship_type,
            amount_label=e.amount_label,
        )
        for e in unique_edges
    ]

    return GraphResponse(nodes=nodes, edges=edges, center_slug=slug)
