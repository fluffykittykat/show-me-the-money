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
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ActivityEvent

logger = logging.getLogger(__name__)

# Activity events are user-facing — strip implementation noise so error
# detail blurbs don't show raw URLs, MDN reference links, or 5-line
# stack traces. Keep the human signal, drop the developer noise.
_URL_RE = re.compile(r"https?://\S+")
_MDN_RE = re.compile(
    r"\s*For more information check:?\s*https?://\S+", re.IGNORECASE,
)


def _humanize_error(msg: str) -> str:
    if not msg:
        return ""
    msg = _MDN_RE.sub("", msg)
    msg = _URL_RE.sub("[link]", msg)
    msg = re.sub(r"\s+", " ", msg).strip()
    if len(msg) > 280:
        msg = msg[:277] + "…"
    return msg


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


# Human-readable label for each scheduler job. Keeps the activity feed
# user-facing rather than logging job_id internals.
_JOB_LABELS: dict[str, str] = {
    "fetch_new_trades": "Stock trades",
    "fetch_new_votes": "Congressional votes",
    "fetch_new_bills": "Bills",
    "fetch_fec_updates": "Campaign finance (FEC)",
    "refresh_conflicts": "Conflict detection",
    "weekly_lobbying": "Lobbying disclosures",
    "weekly_top_refresh": "Top-officials refresh",
    "precompute_verdicts": "Verdict computation",
}


async def emit_job_event(
    session: AsyncSession,
    job_id: str,
    status: str,
    fetched: int = 0,
    created: int = 0,
    detail_extra: str = "",
    error: str = "",
) -> ActivityEvent | None:
    """Emit a single activity_event summarising a scheduler job run.

    Called by the scheduler at the end of every job. Successful runs that
    didn't create anything new still emit a `data_refresh` event so the
    user-facing feed can show "system is alive, just no new data." Failures
    emit a `system` event so the activity page surfaces broken pipelines.

    Returns the created event, or None if emission failed (errors are
    swallowed — never break the calling job).
    """
    try:
        label = _JOB_LABELS.get(job_id, job_id)
        if status == "completed":
            if created > 0:
                event_type = "new_trade" if job_id == "fetch_new_trades" else "data_refresh"
                headline = f"{label}: {created} new"
            else:
                event_type = "data_refresh"
                headline = f"{label}: refreshed ({fetched} checked, 0 new)"
            detail = detail_extra or f"Fetched {fetched}, created {created}."
        elif status == "failed":
            event_type = "system"
            headline = f"{label}: ingestion failed"
            detail = _humanize_error(error) or "Job failed with no error message."
        elif status == "skipped":
            event_type = "system"
            headline = f"{label}: skipped"
            detail = _humanize_error(error) or "Job skipped."
        else:
            return None

        event = await record_event(
            session,
            event_type=event_type,
            headline=headline,
            detail=detail,
            metadata={
                "job_id": job_id,
                "status": status,
                "fetched": fetched,
                "created": created,
            },
        )
        await session.commit()
        return event
    except Exception as exc:
        logger.warning("[activity_feed] emit_job_event(%s) failed: %s", job_id, exc)
        try:
            await session.rollback()
        except Exception:
            pass
        return None


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
            "detail": e.detail or "",
            "entity_slug": e.entity_slug,
            "entity_name": e.entity_name,
            "metadata": e.metadata_ or {},
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]
