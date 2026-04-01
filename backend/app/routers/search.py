from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text, or_, Float
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Entity
from app.schemas import EntityBrief, EntityResponse, SearchResponse

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search_entities(
    q: str = Query(..., min_length=1, description="Search query"),
    type: Optional[str] = Query(None, description="Filter by entity_type"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    q_clean = q.strip()

    # Build the search vector column expression (matches the GIN index)
    search_vector = func.to_tsvector(
        "english",
        Entity.name + " " + func.coalesce(Entity.summary, ""),
    )
    ts_query = func.plainto_tsquery("english", q_clean)

    # Rank by relevance: ts_rank uses the GIN index, O(log n)
    rank_expr = func.ts_rank(search_vector, ts_query).label("rank")

    # Full-text match (uses GIN ix_entities_fts index)
    fts_match = search_vector.bool_op("@@")(ts_query)

    # Prefix match on name — uses ix_entities_name_lower btree index (O log n)
    prefix_match = func.lower(Entity.name).like(f"{q_clean.lower()}%")

    # Substring/contains match — only for short queries where FTS won't help
    # For longer queries (3+ words), FTS handles it; contains is too slow on large tables
    if len(q_clean.split()) <= 2:
        contains_match = func.lower(Entity.name).contains(q_clean.lower())
        where_clause = or_(fts_match, prefix_match, contains_match)
    else:
        where_clause = or_(fts_match, prefix_match)
    if type:
        where_clause = where_clause.where(Entity.entity_type == type) if False else where_clause

    base_q = select(Entity).where(where_clause)
    if type:
        base_q = base_q.where(Entity.entity_type == type)

    # Count total
    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch with relevance ranking — FTS results come first, prefix matches after
    results_q = (
        select(Entity, rank_expr)
        .where(where_clause)
        .order_by(
            # FTS matches rank by relevance; prefix-only matches rank by name
            fts_match.desc(),
            rank_expr.desc(),
            Entity.name,
        )
        .offset(offset)
        .limit(limit)
    )
    if type:
        results_q = results_q.where(Entity.entity_type == type)

    result = await db.execute(results_q)
    rows = result.all()
    entities = [row[0] for row in rows]

    return SearchResponse(
        query=q,
        entity_type=type,
        results=[EntityResponse.model_validate(e) for e in entities],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/search/autocomplete")
async def autocomplete(
    q: str = Query(..., min_length=1),
    limit: int = Query(8, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Lightning-fast autocomplete — substring match on name."""
    q_clean = q.strip()
    result = await db.execute(
        select(Entity.slug, Entity.name, Entity.entity_type)
        .where(Entity.name.ilike(f"%{q_clean}%"))
        .order_by(Entity.name)
        .limit(limit)
    )
    rows = result.all()
    return {
        "query": q,
        "results": [
            {"slug": r.slug, "name": r.name, "type": r.entity_type}
            for r in rows
        ],
    }


@router.get("/browse")
async def list_entities(
    type: Optional[str] = Query(None, description="Filter by entity_type"),
    limit: int = Query(50, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Browse all entities by type — used for Officials page, Bills page, etc."""
    base_q = select(Entity)
    if type:
        base_q = base_q.where(Entity.entity_type == type)
        # For person type, only return actual officials (not donors/lobbyists)
        if type == "person":
            base_q = base_q.where(
                Entity.metadata_.has_key("bioguide_id")
            )

    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    results_q = base_q.order_by(Entity.name).offset(offset).limit(limit)
    result = await db.execute(results_q)
    entities = result.scalars().all()

    return {
        "results": [EntityResponse.model_validate(e) for e in entities],
        "total": total,
        "limit": limit,
        "offset": offset,
        "type": type,
    }
