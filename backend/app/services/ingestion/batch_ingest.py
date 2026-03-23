"""Batch ingestion of all 535 Congress members from Congress.gov and FEC APIs."""

import asyncio
import gc
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
import psutil
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import async_session
from app.models import DataSource, Entity, IngestionJob
from app.services.ingestion.congress_client import CongressClient
from app.services.ingestion.fec_client import FECClient
from app.services.rate_limiter import SmartRateLimiter

logger = logging.getLogger("batch_ingest")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

# Module-level state for tracking running tasks
_running_tasks: dict[str, asyncio.Task] = {}

BATCH_SIZE = 10
CONGRESS_API_BASE = "https://api.congress.gov/v3"
TIMEOUT = 30.0


def _slugify(name: str) -> str:
    """Convert a name to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _ascii_safe(obj):
    """Recursively strip non-ASCII characters for SQL_ASCII database."""
    if isinstance(obj, str):
        return obj.encode("ascii", "replace").decode("ascii")
    if isinstance(obj, dict):
        return {k: _ascii_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ascii_safe(i) for i in obj]
    return obj


async def _fetch_all_current_members(api_key: str, limiter: SmartRateLimiter) -> list:
    """Fetch all current Congress members via two paginated requests."""
    all_members = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for offset in (0, 250):
            url = (
                f"{CONGRESS_API_BASE}/member"
                f"?currentMember=true&limit=250&offset={offset}"
                f"&api_key={api_key}&format=json"
            )
            async with limiter.acquire("congress_gov"):
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                members = data.get("members", [])
                all_members.extend(members)
                logger.info(
                    "Fetched %d members (offset=%d, total=%d)",
                    len(members), offset, len(all_members),
                )
    return all_members


async def _process_member(
    member_summary: dict,
    congress_client: CongressClient,
    fec_client: Optional[FECClient],
    limiter: SmartRateLimiter,
    force: bool = False,
) -> dict:
    """Process a single Congress member: fetch details, legislation, FEC data.

    Returns a dict with all fetched data, or raises on unrecoverable error.
    """
    bioguide_id = member_summary.get("bioguideId", "")
    name = member_summary.get("name", "")
    state = member_summary.get("state", "")
    party = member_summary.get("partyName", "")
    chamber = member_summary.get("terms", {})

    # Determine chamber from terms
    terms_item = chamber.get("item", []) if isinstance(chamber, dict) else []
    member_chamber = ""
    if terms_item:
        last_term = terms_item[-1] if isinstance(terms_item, list) else terms_item
        if isinstance(last_term, dict):
            member_chamber = last_term.get("chamber", "")

    slug = _slugify(name)
    result = {
        "bioguide_id": bioguide_id,
        "name": name,
        "slug": slug,
        "state": state,
        "party": party,
        "chamber": member_chamber,
        "member_detail": {},
        "sponsored_bills": [],
        "cosponsored_bills": [],
        "fec_data": None,
    }

    # Skip if already ingested (unless force)
    if not force:
        async with async_session() as session:
            existing = await session.execute(
                select(DataSource).join(Entity).where(
                    Entity.slug == slug,
                    DataSource.source_type == "congress_gov",
                )
            )
            if existing.scalars().first() is not None:
                logger.info("Skipping %s (already ingested)", name)
                result["skipped"] = True
                return result

    # Fetch member detail
    async with limiter.acquire("congress_gov"):
        try:
            result["member_detail"] = await congress_client.fetch_member(bioguide_id)
        except Exception as exc:
            logger.warning("Failed to fetch member detail for %s: %s", name, exc)

    # Fetch sponsored legislation
    async with limiter.acquire("congress_gov"):
        try:
            result["sponsored_bills"] = await congress_client.fetch_sponsored_legislation(
                bioguide_id, limit=50
            )
        except Exception as exc:
            logger.warning("Failed to fetch sponsored bills for %s: %s", name, exc)

    # Fetch cosponsored legislation
    async with limiter.acquire("congress_gov"):
        try:
            result["cosponsored_bills"] = await congress_client.fetch_cosponsored_legislation(
                bioguide_id, limit=50
            )
        except Exception as exc:
            logger.warning("Failed to fetch cosponsored bills for %s: %s", name, exc)

    # Try to resolve FEC data
    if fec_client:
        try:
            async with limiter.acquire("fec"):
                fec_candidate = await fec_client.search_candidate(
                    name, state=state
                )
            if fec_candidate:
                candidate_id = fec_candidate.get("candidate_id", "")
                committees = fec_candidate.get("principal_committees", [])
                committee_id = ""
                if committees:
                    committee_id = committees[0].get("committee_id", "")

                if candidate_id:
                    async with limiter.acquire("fec"):
                        try:
                            totals = await fec_client.fetch_candidate_totals(
                                candidate_id
                            )
                        except Exception:
                            totals = {}

                    donors = []
                    if committee_id:
                        async with limiter.acquire("fec"):
                            try:
                                donors = await fec_client.fetch_top_contributors(
                                    committee_id, per_page=20
                                )
                            except Exception:
                                donors = []

                    result["fec_data"] = {
                        "candidate_id": candidate_id,
                        "committee_id": committee_id,
                        "totals": totals,
                        "top_donors": donors,
                    }
        except Exception as exc:
            logger.warning("FEC lookup failed for %s: %s", name, exc)

    return result


async def _upsert_member_data(member_data: dict) -> None:
    """Upsert a member's entity and data source records."""
    if member_data.get("skipped"):
        return

    slug = member_data["slug"]
    name = member_data["name"]
    bioguide_id = member_data["bioguide_id"]

    # All Congress members are entity_type "person" — chamber is in metadata
    entity_type = "person"

    metadata = {
        "bioguide_id": bioguide_id,
        "state": member_data.get("state", ""),
        "party": member_data.get("party", ""),
        "chamber": member_data.get("chamber", ""),
        "sponsored_bill_count": len(member_data.get("sponsored_bills", [])),
        "cosponsored_bill_count": len(member_data.get("cosponsored_bills", [])),
    }

    if member_data.get("fec_data"):
        fec = member_data["fec_data"]
        metadata["fec_candidate_id"] = fec.get("candidate_id", "")
        metadata["fec_committee_id"] = fec.get("committee_id", "")
        totals = fec.get("totals", {})
        if totals:
            metadata["total_receipts"] = totals.get("receipts", 0)
            metadata["total_disbursements"] = totals.get("disbursements", 0)
            metadata["individual_contributions"] = totals.get(
                "individual_contributions", 0
            )

    party = member_data.get("party", "")
    state = member_data.get("state", "")
    summary = f"{party} {entity_type.title()} from {state}" if party and state else None

    logger.info("Storing member: %s (%s, %s)", name, entity_type, slug)
    async with async_session() as session:
        async with session.begin():
            # Upsert entity
            # Use ORM upsert to avoid metadata column name clash
            existing = (await session.execute(
                select(Entity).where(Entity.slug == slug)
            )).scalar_one_or_none()

            safe_name = _ascii_safe(name)
            safe_summary = _ascii_safe(summary) if summary else None
            safe_metadata = _ascii_safe(metadata)

            if existing:
                existing.name = safe_name
                existing.entity_type = entity_type
                existing.summary = safe_summary
                existing.metadata_ = safe_metadata
            else:
                existing = Entity(
                    slug=slug,
                    entity_type=entity_type,
                    name=safe_name,
                    summary=safe_summary,
                    metadata_=safe_metadata,
                )
                session.add(existing)
            await session.flush()

            # Get the entity id
            entity_row = await session.execute(
                select(Entity.id).where(Entity.slug == slug)
            )
            entity_id = entity_row.scalar_one()

            # Upsert data source for congress_gov
            raw_payload = {
                "member_detail": member_data.get("member_detail", {}),
                "sponsored_bills_count": len(member_data.get("sponsored_bills", [])),
                "cosponsored_bills_count": len(member_data.get("cosponsored_bills", [])),
            }

            ds_stmt = pg_insert(DataSource).values(
                entity_id=entity_id,
                source_type="congress_gov",
                external_id=bioguide_id,
                raw_payload=_ascii_safe(raw_payload),
                fetched_at=datetime.now(timezone.utc),
            )
            # If data_source already exists for this entity+source_type, update it
            # There's no unique constraint on (entity_id, source_type), so just insert
            await session.execute(ds_stmt)

            # If FEC data exists, add a data source for it
            if member_data.get("fec_data"):
                fec_ds_stmt = pg_insert(DataSource).values(
                    entity_id=entity_id,
                    source_type="fec",
                    external_id=member_data["fec_data"].get("candidate_id", ""),
                    raw_payload=_ascii_safe(member_data["fec_data"]),
                    fetched_at=datetime.now(timezone.utc),
                )
                await session.execute(fec_ds_stmt)


async def _update_job_progress(
    job_id: uuid.UUID, progress: int, total: int, errors: list
) -> None:
    """Update the ingestion job progress in the database."""
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job_id)
                .values(
                    progress=progress,
                    total=total,
                    errors=errors,
                )
            )


async def run_batch_ingestion(force: bool = False) -> uuid.UUID:
    """Run batch ingestion for all current Congress members.

    Creates an IngestionJob record and processes members in batches.
    Returns the job ID.
    """
    # Try env vars first, then fall back to DB config
    congress_api_key = os.getenv("CONGRESS_GOV_API_KEY", "")
    fec_api_key = os.getenv("FEC_API_KEY", "")

    if not congress_api_key:
        from app.services.config_service import get_config_value
        async with async_session() as cfg_session:
            congress_api_key = await get_config_value(cfg_session, "CONGRESS_GOV_API_KEY") or ""
            fec_api_key = fec_api_key or await get_config_value(cfg_session, "FEC_API_KEY") or ""

    if not congress_api_key:
        raise ValueError("CONGRESS_GOV_API_KEY not set (env var or DB config)")

    # Create ingestion job
    job_id: uuid.UUID
    async with async_session() as session:
        async with session.begin():
            job = IngestionJob(
                job_type="batch_congress_members",
                status="in_progress",
                started_at=datetime.now(timezone.utc),
                metadata_={"force": force},
            )
            session.add(job)
            await session.flush()
            job_id = job.id

    logger.info("Created ingestion job %s", job_id)

    limiter = SmartRateLimiter()
    congress_client = CongressClient(congress_api_key)
    fec_client = FECClient(fec_api_key) if fec_api_key else None

    errors: list[dict] = []

    try:
        # Fetch all current members
        all_members = await _fetch_all_current_members(congress_api_key, limiter)
        total = len(all_members)
        logger.info("Found %d current Congress members", total)

        # Update job with total count
        await _update_job_progress(job_id, 0, total, errors)

        processed = 0

        # Process in batches
        for batch_start in range(0, total, BATCH_SIZE):
            batch = all_members[batch_start : batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            logger.info(
                "Processing batch %d (%d-%d of %d)",
                batch_num, batch_start + 1, batch_start + len(batch), total,
            )

            # Process each member in the batch concurrently
            tasks = []
            for member_summary in batch:
                task = _process_member(
                    member_summary, congress_client, fec_client, limiter, force=force
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                member_name = batch[i].get("name", "unknown")
                if isinstance(result, Exception):
                    error_entry = {
                        "member": member_name,
                        "error": str(result),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    errors.append(error_entry)
                    logger.error("Error processing %s: %s", member_name, result)
                else:
                    # Upsert the member data
                    try:
                        await _upsert_member_data(result)
                    except Exception as exc:
                        error_entry = {
                            "member": member_name,
                            "error": f"Upsert failed: {exc}",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        errors.append(error_entry)
                        logger.error("Upsert failed for %s: %s", member_name, exc)

                processed += 1

            # Update progress
            await _update_job_progress(job_id, processed, total, errors)

            # Memory safety: log and collect every 50 members
            if processed % 50 == 0 or processed == total:
                process = psutil.Process()
                mem_mb = process.memory_info().rss / (1024 * 1024)
                logger.info(
                    "Progress: %d/%d members | Memory: %.1f MB | Errors: %d",
                    processed, total, mem_mb, len(errors),
                )
                gc.collect()

        # Mark job as completed
        async with async_session() as session:
            async with session.begin():
                await session.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job_id)
                    .values(
                        status="completed",
                        progress=processed,
                        total=total,
                        completed_at=datetime.now(timezone.utc),
                        errors=errors,
                        metadata_={
                            "force": force,
                            "rate_limiter_stats": limiter.stats(),
                        },
                    )
                )

        logger.info("Batch ingestion completed: %d/%d members", processed, total)

    except Exception as exc:
        logger.error("Batch ingestion failed: %s", exc)
        async with async_session() as session:
            async with session.begin():
                await session.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job_id)
                    .values(
                        status="failed",
                        completed_at=datetime.now(timezone.utc),
                        errors=errors + [{"fatal": str(exc)}],
                    )
                )
        raise
    finally:
        # Clean up task reference
        task_key = str(job_id)
        _running_tasks.pop(task_key, None)

    return job_id


def start_batch_ingestion(force: bool = False) -> uuid.UUID:
    """Start batch ingestion as a background asyncio task.

    Returns a job_id that can be used to query status.
    The task is tracked in the module-level _running_tasks dict.
    """
    # Generate job ID up front so we can return it immediately
    job_id = uuid.uuid4()

    async def _wrapper():
        return await run_batch_ingestion(force=force)

    task = asyncio.create_task(_wrapper())
    _running_tasks[str(job_id)] = task
    logger.info("Started batch ingestion task (tracking id: %s)", job_id)
    return job_id


def get_running_tasks() -> dict[str, str]:
    """Return status of all tracked tasks."""
    result = {}
    for task_id, task in list(_running_tasks.items()):
        if task.done():
            if task.exception():
                result[task_id] = f"failed: {task.exception()}"
            else:
                result[task_id] = "completed"
            # Clean up finished tasks
            _running_tasks.pop(task_id, None)
        else:
            result[task_id] = "running"
    return result


async def mark_stale_jobs_interrupted() -> int:
    """Mark any in_progress ingestion jobs as 'interrupted'.

    Called on startup to clean up jobs that were running when the server stopped.
    Returns the number of jobs marked.
    """
    async with async_session() as session:
        async with session.begin():
            result = await session.execute(
                update(IngestionJob)
                .where(IngestionJob.status == "in_progress")
                .values(
                    status="interrupted",
                    completed_at=datetime.now(timezone.utc),
                )
            )
            return result.rowcount
