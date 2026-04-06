"""
Activity feed service — records and queries system events for the
user-facing activity feed and homepage "Latest Updates" section.

Event types:
  new_trade       — A new stock trade was detected
  verdict_change  — An official's verdict changed (e.g. NORMAL → OWNED)
  new_conflict    — A new conflict of interest was detected
  new_donation    — New donation data ingested
  data_refresh    — A scheduled data refresh completed
  system          — System status event (eFD back online, etc.)
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActivityEvent

logger = logging.getLogger(__name__)


async def record_event(
    session: AsyncSession,
    event_type: str,
    headline: str,
    detail: str = "",
    entity_slug: str = None,
    entity_name: str = None,
    metadata: dict = None,
) -> ActivityEvent:
    """Record a new activity event."""
    event = ActivityEvent(
        event_type=event_type,
        headline=headline,
        detail=detail or "",
        entity_slug=entity_slug,
        entity_name=entity_name,
        metadata_=metadata or {},
    )
    session.add(event)
    await session.flush()
    return event


async def get_feed(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    event_type: str = None,
    days: int = 30,
) -> dict:
    """Get paginated activity feed."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    query = select(ActivityEvent).where(ActivityEvent.created_at >= cutoff)
    if event_type:
        query = query.where(ActivityEvent.event_type == event_type)

    total = (await session.execute(
        select(func.count()).select_from(query.subquery())
    )).scalar_one()

    result = await session.execute(
        query.order_by(ActivityEvent.created_at.desc()).offset(offset).limit(limit)
    )
    events = result.scalars().all()

    return {
        "events": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "headline": e.headline,
                "detail": e.detail or "",
                "entity_slug": e.entity_slug,
                "entity_name": e.entity_name,
                "metadata": e.metadata_ or {},
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
        "total": total,
    }


async def get_latest(session: AsyncSession, limit: int = 10) -> list[dict]:
    """Get the latest N events for the homepage section."""
    result = await session.execute(
        select(ActivityEvent)
        .order_by(ActivityEvent.created_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()

    return [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "headline": e.headline,
            "entity_slug": e.entity_slug,
            "entity_name": e.entity_name,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]
