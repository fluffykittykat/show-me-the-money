"""
Bill Enrichment Job — Fetches CRS summaries and text URLs for all bill entities.

Iterates through all bill entities in the database, extracts the Congress.gov API URL
from metadata, and fetches:
  1. CRS summary text (plain text, HTML stripped)
  2. Text version URLs (HTML, PDF, XML)
  3. Full bill detail (sponsors, subjects, actions, etc.)

Rate-limited to avoid 429s from Congress.gov. Resumable — skips bills that already
have enrichment data.
"""

import asyncio
import gc
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update, func

from app.database import async_session
from app.models import Entity, IngestionJob

logger = logging.getLogger("enrich_bills")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

TIMEOUT = 30.0
RATE_LIMIT_DELAY = 0.6  # seconds between Congress.gov API calls
BATCH_SIZE = 50  # Process bills in batches for progress updates


def _ascii_safe(obj):
    """Recursively strip non-ASCII characters for SQL_ASCII database."""
    if isinstance(obj, str):
        return obj.encode("ascii", "replace").decode("ascii")
    if isinstance(obj, dict):
        return {k: _ascii_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ascii_safe(i) for i in obj]
    return obj


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text).strip()


async def _fetch_bill_detail(client: httpx.AsyncClient, url: str, api_key: str) -> dict:
    """Fetch full bill detail from Congress.gov API."""
    params = {"api_key": api_key, "format": "json"}
    response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return data.get("bill", data)


async def _fetch_bill_summaries(client: httpx.AsyncClient, url: str, api_key: str) -> str:
    """Fetch CRS summary text for a bill. Returns plain text (HTML stripped)."""
    params = {"api_key": api_key, "format": "json"}
    response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    summaries = data.get("summaries", [])
    if not summaries:
        return ""

    # Get the most detailed summary (last one is usually most recent/complete)
    best = summaries[-1]
    text = best.get("text", "")
    return _strip_html(text)


async def _fetch_bill_text_info(client: httpx.AsyncClient, url: str, api_key: str) -> dict:
    """Fetch text version URLs for a bill."""
    params = {"api_key": api_key, "format": "json"}
    response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    versions = data.get("textVersions", [])
    if not versions:
        return {}

    # Get the most recent text version (first in list)
    latest = versions[0]
    formats = latest.get("formats", [])

    result = {
        "date": latest.get("date", ""),
        "type": latest.get("type", ""),
        "formats": {},
    }

    for fmt in formats:
        fmt_type = (fmt.get("type") or "").lower()
        fmt_url = fmt.get("url", "")
        if not fmt_url:
            continue
        if "html" in fmt_type or "formatted text" in fmt_type:
            result["formats"]["html"] = fmt_url
        elif "pdf" in fmt_type:
            result["formats"]["pdf"] = fmt_url
        elif "xml" in fmt_type:
            result["formats"]["xml"] = fmt_url

    return result


async def _enrich_single_bill(
    client: httpx.AsyncClient,
    bill: Entity,
    api_key: str,
) -> dict:
    """Enrich a single bill entity with summary and text URLs.

    Returns a dict of metadata updates, or empty dict on failure.
    """
    meta = bill.metadata_ or {}
    bill_url = meta.get("url", "")

    # Construct URL from metadata if not present
    if not bill_url:
        congress = meta.get("congress", "")
        bill_type = (meta.get("type", "") or "").lower()
        bill_number = meta.get("number", "") or meta.get("bill_number", "")
        if congress and bill_type and bill_number:
            bill_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}"
        else:
            return {}

    # Parse the bill URL to construct summary/text endpoints
    # URL format: https://api.congress.gov/v3/bill/119/hr/7619?format=json
    base_url = bill_url.split("?")[0]
    summary_url = f"{base_url}/summaries"
    text_url = f"{base_url}/text"

    updates = {}

    # 1. Fetch bill detail for extra metadata (sponsors, subjects, etc.)
    try:
        await asyncio.sleep(RATE_LIMIT_DELAY)
        detail = await _fetch_bill_detail(client, base_url, api_key)

        # Extract useful fields
        if detail.get("title"):
            updates["full_title"] = _ascii_safe(detail["title"])[:1000]
        if detail.get("originChamber"):
            updates["origin_chamber"] = detail["originChamber"]
        if detail.get("legislationUrl"):
            updates["congress_url"] = detail["legislationUrl"]

        # Sponsors
        sponsors = detail.get("sponsors", [])
        if sponsors:
            updates["sponsors"] = _ascii_safe([
                {
                    "name": s.get("fullName", ""),
                    "bioguideId": s.get("bioguideId", ""),
                    "party": s.get("party", ""),
                    "state": s.get("state", ""),
                }
                for s in sponsors[:10]
            ])

        # Policy area
        pa = detail.get("policyArea", {})
        if pa and pa.get("name"):
            updates["policy_area"] = pa["name"]

        # Latest action
        la = detail.get("latestAction", {})
        if la:
            updates["latest_action"] = _ascii_safe({
                "date": la.get("actionDate", ""),
                "text": _ascii_safe(la.get("text", ""))[:500],
            })

        # Constitutional authority statement
        cas = detail.get("constitutionalAuthorityStatementText", "")
        if cas:
            updates["constitutional_authority"] = _ascii_safe(_strip_html(cas))[:500]

    except Exception as exc:
        logger.debug("Failed to fetch detail for %s: %s", bill.slug, exc)

    # 2. Fetch CRS summary
    try:
        await asyncio.sleep(RATE_LIMIT_DELAY)
        summary_text = await _fetch_bill_summaries(client, summary_url, api_key)
        if summary_text:
            updates["crs_summary"] = _ascii_safe(summary_text)[:5000]
    except Exception as exc:
        logger.debug("Failed to fetch summary for %s: %s", bill.slug, exc)

    # 3. Fetch text URLs
    try:
        await asyncio.sleep(RATE_LIMIT_DELAY)
        text_info = await _fetch_bill_text_info(client, text_url, api_key)
        if text_info:
            updates["text_versions"] = text_info
    except Exception as exc:
        logger.debug("Failed to fetch text info for %s: %s", bill.slug, exc)

    return updates


async def run_bill_enrichment(force: bool = False) -> uuid.UUID:
    """Enrich all bill entities with CRS summaries and text URLs.

    Creates an IngestionJob for tracking. Skips bills that already have
    enrichment data unless force=True.
    """
    api_key = os.getenv("CONGRESS_GOV_API_KEY", "")
    if not api_key:
        from app.services.config_service import get_config_value
        async with async_session() as cfg_session:
            api_key = await get_config_value(cfg_session, "CONGRESS_GOV_API_KEY") or ""

    if not api_key:
        raise ValueError("CONGRESS_GOV_API_KEY not set")

    # Create ingestion job
    async with async_session() as session:
        async with session.begin():
            job = IngestionJob(
                job_type="enrich_bills",
                status="in_progress",
                started_at=datetime.now(timezone.utc),
                metadata_={"force": force},
            )
            session.add(job)
            await session.flush()
            job_id = job.id

    logger.info("Started bill enrichment job %s", job_id)

    # Get all bill entities that need enrichment
    async with async_session() as session:
        query = select(Entity).where(
            Entity.entity_type == "bill",
        )
        if not force:
            # Skip bills that already have CRS summary or text versions
            # Use a raw SQL filter on the JSONB metadata
            query = query.where(
                ~Entity.metadata_.has_key("crs_summary")
            )

        result = await session.execute(query.order_by(Entity.created_at))
        bills = result.scalars().all()

    total = len(bills)
    logger.info("Found %d bills to enrich", total)

    # Update job with total
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job_id)
                .values(total=total, progress=0)
            )

    errors = []
    processed = 0
    enriched = 0

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for i in range(0, total, BATCH_SIZE):
            batch = bills[i:i + BATCH_SIZE]

            for bill in batch:
                try:
                    updates = await _enrich_single_bill(client, bill, api_key)
                    if updates:
                        async with async_session() as session:
                            async with session.begin():
                                entity = (await session.execute(
                                    select(Entity).where(Entity.id == bill.id)
                                )).scalar_one()
                                merged = {**(entity.metadata_ or {}), **updates, "enriched_at": datetime.now(timezone.utc).isoformat()}
                                entity.metadata_ = _ascii_safe(merged)

                                # Also update the summary field with CRS summary if available
                                if updates.get("crs_summary"):
                                    entity.summary = _ascii_safe(updates["crs_summary"])[:2000]

                        enriched += 1

                except Exception as exc:
                    errors.append({
                        "bill": bill.slug,
                        "error": str(exc)[:200],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    logger.warning("Error enriching %s: %s", bill.slug, exc)

                processed += 1

            # Update progress
            async with async_session() as session:
                async with session.begin():
                    await session.execute(
                        update(IngestionJob)
                        .where(IngestionJob.id == job_id)
                        .values(
                            progress=processed,
                            errors=errors[-50:],  # Keep last 50 errors
                        )
                    )

            logger.info(
                "Progress: %d/%d processed, %d enriched, %d errors",
                processed, total, enriched, len(errors),
            )
            gc.collect()

    # Mark job complete
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
                    errors=errors[-50:],
                    metadata_={
                        "force": force,
                        "enriched": enriched,
                        "errors_total": len(errors),
                    },
                )
            )

    logger.info(
        "Bill enrichment complete: %d/%d enriched, %d errors",
        enriched, total, len(errors),
    )
    return job_id
