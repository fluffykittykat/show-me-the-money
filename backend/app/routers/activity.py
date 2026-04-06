"""Activity feed API — chronological feed of system events."""

from fastapi import APIRouter, Query

from app.database import async_session

router = APIRouter(prefix="/activity", tags=["activity"])


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
