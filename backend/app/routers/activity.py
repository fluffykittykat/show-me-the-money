"""Activity feed API — chronological feed of system events."""

from fastapi import APIRouter, Query

from app.database import async_session

router = APIRouter(prefix="/activity", tags=["activity"])


@router.post("/seed")
async def seed_activity():
    """Seed the activity feed with events from existing data."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func, select, text
    from app.models import Entity, Relationship, ActivityEvent
    from app.services.activity_feed import record_event

    seeded = 0
    async with async_session() as session:
        # Check if already seeded
        existing = (await session.execute(select(func.count()).select_from(ActivityEvent))).scalar_one()
        if existing > 0:
            return {"status": "skipped", "message": f"Already have {existing} events"}

        # 1. Record event for total trades ingested
        trade_count = (await session.execute(
            select(func.count()).select_from(Relationship).where(
                Relationship.relationship_type.in_(["holds_stock", "stock_trade"])
            )
        )).scalar_one()
        if trade_count > 0:
            await record_event(session, "new_trade",
                f"{trade_count:,} stock trades ingested from House Clerk disclosures",
                detail=f"Bulk ingestion of House member PTR filings from clerk.house.gov. Covers 2024-2025 filings.",
                metadata={"count": trade_count, "source": "house_clerk"})
            seeded += 1

        # 2. Record events for OWNED officials
        owned = (await session.execute(
            select(Entity.name, Entity.slug).where(
                Entity.entity_type == "person",
                Entity.metadata_["v2_verdict"].astext == "OWNED",
            ).order_by(text("(metadata->>'v2_dot_count')::int DESC NULLS LAST")).limit(5)
        )).all()
        for name, slug in owned:
            await record_event(session, "verdict_change",
                f"{name} verdict: OWNED",
                detail=f"Analysis found multiple industries with concerning financial influence patterns.",
                entity_slug=slug, entity_name=name,
                metadata={"verdict": "OWNED"})
            seeded += 1

        # 3. Record data refresh events
        await record_event(session, "data_refresh",
            "FEC campaign finance data refreshed",
            detail="Updated donation totals and contributor data for all tracked officials.",
            metadata={"source": "fec"})
        seeded += 1

        await record_event(session, "data_refresh",
            "Congress.gov votes data updated",
            detail="Fetched latest House roll call votes from Congress.gov API v3.",
            metadata={"source": "congress_api"})
        seeded += 1

        await record_event(session, "system",
            "Senate eFD disclosure system under maintenance",
            detail="efdsearch.senate.gov data API returning HTTP 503. Senate PTR filings temporarily unavailable. Polling continues every 15 minutes.",
            metadata={"source": "senate_efd", "status": "503"})
        seeded += 1

        # 4. Record stats
        official_count = (await session.execute(
            select(func.count()).select_from(Entity).where(Entity.entity_type == "person")
        )).scalar_one()
        await record_event(session, "data_refresh",
            f"{official_count:,} officials profiled with verdicts and briefings",
            detail="Full data pipeline: Congress.gov profiles, FEC donations, committee assignments, bill sponsorship, and influence scoring.",
            metadata={"officials": official_count})
        seeded += 1

        await session.commit()

    return {"status": "ok", "seeded": seeded}


@router.get("/feed")
async def activity_feed(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    event_type: str = Query(None, description="Filter: new_trade, verdict_change, new_conflict, data_refresh, system"),
    days: int = Query(30, ge=1, le=365),
):
    """Paginated activity feed with optional filters."""
    from app.services.activity_feed import get_feed

    async with async_session() as session:
        return await get_feed(session, limit=limit, offset=offset, event_type=event_type, days=days)


@router.get("/latest")
async def activity_latest(
    limit: int = Query(10, ge=1, le=50),
):
    """Latest events for the homepage section."""
    from app.services.activity_feed import get_latest

    async with async_session() as session:
        return await get_latest(session, limit=limit)
