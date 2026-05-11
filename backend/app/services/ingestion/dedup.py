"""Freshness-based dedup for ingestion clients.

Each fetched payload should be written to `data_sources` with the source_type
(e.g. "fec_candidate_totals") and external_id (e.g. the candidate_id). Before
fetching, callers ask `recently_fetched()` whether they already have a fresh
copy and can skip the API call.

This is the single mechanism that prevents the scheduler from re-hammering
upstream APIs for data we already have.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DataSource


async def recently_fetched(
    session: AsyncSession,
    source_type: str,
    external_id: str,
    max_age_hours: int,
) -> bool:
    """Return True if a DataSource row for (source_type, external_id) was
    written within the last `max_age_hours`."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    stmt = (
        select(DataSource.fetched_at)
        .where(
            DataSource.source_type == source_type,
            DataSource.external_id == external_id,
            DataSource.fetched_at >= cutoff,
        )
        .limit(1)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def record_fetch(
    session: AsyncSession,
    entity_id,
    source_type: str,
    external_id: str,
    payload: dict,
) -> None:
    """Insert a DataSource row marking a successful fetch. Commit is the
    caller's responsibility."""
    ds = DataSource(
        entity_id=entity_id,
        source_type=source_type,
        external_id=external_id,
        raw_payload=payload or {},
        fetched_at=datetime.now(timezone.utc),
    )
    session.add(ds)
