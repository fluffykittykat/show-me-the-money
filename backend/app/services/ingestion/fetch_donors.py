"""Fetch FEC donor data for officials that have FEC IDs but no donor relationships yet.

Rate-limited to ~1 official every 3 seconds to stay well under FEC's ~1000 req/hour limit.
"""

import asyncio
import logging
import os
import re
import uuid
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.orm import aliased

from app.database import async_session
from app.models import Entity, IngestionJob, Relationship
from app.services.ingestion.fec_client import FECClient

logger = logging.getLogger("fetch_donors")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

DELAY_BETWEEN_OFFICIALS = 3  # seconds between each official's API calls
DELAY_BETWEEN_API_CALLS = 3  # seconds between individual API calls
DONORS_PER_OFFICIAL = 30


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


def _parse_date(date_str: str | None) -> date | None:
    """Parse an FEC date string like '2022-03-15T00:00:00' into a date."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


async def _resolve_committee_id(fec_client: FECClient, candidate_id: str) -> str | None:
    """Look up a candidate's principal committee ID from the FEC candidate endpoint."""
    url = f"{fec_client.base_url}/candidate/{candidate_id}/"
    params = {"api_key": fec_client.api_key}
    logger.info("Looking up committee_id for candidate %s", candidate_id)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if results:
                committees = results[0].get("principal_committees", [])
                if committees:
                    cid = committees[0].get("committee_id", "")
                    if cid:
                        logger.info("Resolved committee_id %s for candidate %s", cid, candidate_id)
                        return cid
            logger.info("No committee found for candidate %s", candidate_id)
            return None
    except Exception as e:
        logger.warning("Failed to resolve committee for candidate %s: %s", candidate_id, e)
        return None


async def _find_officials_needing_donors() -> list[dict]:
    """Find officials with FEC IDs but no donated_to relationships."""
    async with async_session() as session:
        # Subquery: officials that already have at least one donated_to relationship
        has_donors_subq = (
            select(Relationship.to_entity_id)
            .where(Relationship.relationship_type == "donated_to")
            .distinct()
            .subquery()
        )

        # Officials with fec_committee_id or fec_candidate_id in metadata
        # but NOT in the has_donors set
        stmt = (
            select(Entity)
            .where(
                Entity.entity_type == "person",
                Entity.metadata_.has_key("bioguide_id"),
                Entity.id.notin_(select(has_donors_subq.c.to_entity_id)),
            )
        )
        result = await session.execute(stmt)
        officials = result.scalars().all()

        # Filter to those with FEC IDs in metadata
        officials_data = []
        for off in officials:
            meta = off.metadata_ or {}
            committee_id = meta.get("fec_committee_id", "")
            candidate_id = meta.get("fec_candidate_id", "")
            if committee_id or candidate_id:
                officials_data.append({
                    "id": off.id,
                    "name": off.name,
                    "slug": off.slug,
                    "committee_id": committee_id,
                    "candidate_id": candidate_id,
                })

        return officials_data


async def _create_donor_relationships(
    official_id: uuid.UUID,
    official_name: str,
    contributors: list[dict],
) -> int:
    """Create donor entities and donated_to relationships for an official."""
    created = 0
    async with async_session() as session:
        async with session.begin():
            for donor in contributors[:DONORS_PER_OFFICIAL]:
                donor_name = _ascii_safe(donor.get("contributor_name", "") or "")
                if not donor_name or len(donor_name) < 2:
                    continue
                donor_slug = _slugify(donor_name)
                if not donor_slug:
                    continue

                amount = (
                    donor.get("total", 0)
                    or donor.get("contribution_receipt_amount", 0)
                    or 0
                )

                # Detect PACs vs individuals
                name_upper = donor_name.upper()
                is_pac = any(kw in name_upper for kw in [
                    "PAC", "FUND", "VICTORY", "COMMITTEE", "DSCC", "DCCC",
                    "EMILY", "ACTION", "SENATE", "HOUSE", " FUND",
                ])
                donor_type = "pac" if is_pac else "person"

                # Find or create donor entity
                donor_ent = (await session.execute(
                    select(Entity).where(Entity.slug == donor_slug)
                )).scalar_one_or_none()

                if not donor_ent:
                    donor_ent = Entity(
                        slug=donor_slug,
                        entity_type=donor_type,
                        name=donor_name,
                        metadata_=_ascii_safe({
                            "donor_type": "pac" if is_pac else "individual",
                        }),
                    )
                    session.add(donor_ent)
                    await session.flush()

                # Check for existing relationship
                existing_rel = (await session.execute(
                    select(Relationship).where(
                        Relationship.from_entity_id == donor_ent.id,
                        Relationship.to_entity_id == official_id,
                        Relationship.relationship_type == "donated_to",
                    ).limit(1)
                )).scalar_one_or_none()

                if not existing_rel:
                    amount_cents = int(float(amount) * 100) if amount else 0
                    receipt_date = _parse_date(
                        donor.get("contribution_receipt_date")
                    )
                    session.add(Relationship(
                        from_entity_id=donor_ent.id,
                        to_entity_id=official_id,
                        relationship_type="donated_to",
                        amount_usd=amount_cents,
                        date_start=receipt_date,
                        source_label="FEC",
                    ))
                    created += 1

    return created


async def run_fetch_donors() -> str:
    """Main entry point: fetch donors for all officials missing donor data."""
    # Get FEC API key
    fec_api_key = os.getenv("FEC_API_KEY", "")
    if not fec_api_key:
        from app.services.config_service import get_config_value
        async with async_session() as cfg_session:
            fec_api_key = await get_config_value(cfg_session, "FEC_API_KEY") or ""
    if not fec_api_key:
        logger.error("FEC_API_KEY not configured")
        return "error: FEC_API_KEY not configured"

    fec_client = FECClient(fec_api_key)

    # Find officials needing donors
    officials = await _find_officials_needing_donors()
    total = len(officials)
    logger.info("Found %d officials needing donor data", total)

    if total == 0:
        logger.info("No officials need donor data — nothing to do")
        return "No officials need donor data"

    # Create ingestion job
    job_id: uuid.UUID
    async with async_session() as session:
        async with session.begin():
            job = IngestionJob(
                job_type="fetch_donors",
                status="in_progress",
                total=total,
                progress=0,
                started_at=datetime.now(timezone.utc),
                metadata_={"total_officials": total},
            )
            session.add(job)
            await session.flush()
            job_id = job.id
    logger.info("Created ingestion job %s for %d officials", job_id, total)

    errors: list[dict] = []
    total_donors_created = 0

    for i, official in enumerate(officials):
        name = official["name"]
        committee_id = official["committee_id"]
        candidate_id = official["candidate_id"]

        logger.info(
            "[%d/%d] Processing %s (committee=%s, candidate=%s)",
            i + 1, total, name, committee_id or "none", candidate_id or "none",
        )

        try:
            # If no committee_id, try to resolve from candidate_id
            if not committee_id and candidate_id:
                committee_id = await _resolve_committee_id(fec_client, candidate_id)
                await asyncio.sleep(DELAY_BETWEEN_API_CALLS)

                # Store resolved committee_id back to metadata
                if committee_id:
                    async with async_session() as session:
                        async with session.begin():
                            ent = await session.get(Entity, official["id"])
                            if ent:
                                meta = dict(ent.metadata_ or {})
                                meta["fec_committee_id"] = committee_id
                                ent.metadata_ = meta

            if not committee_id:
                logger.warning("No committee_id for %s — skipping", name)
                errors.append({"official": name, "error": "no committee_id"})
                continue

            # Fetch top contributors for recent cycles (2024 first, then 2022)
            contributors = []
            for cycle in [2024, 2022]:
                cycle_donors = await fec_client.fetch_top_contributors(
                    committee_id, cycle=cycle, per_page=DONORS_PER_OFFICIAL
                )
                contributors.extend(cycle_donors)
                if cycle_donors:
                    logger.info("  Got %d contributors for %s (cycle %d)", len(cycle_donors), name, cycle)
                await asyncio.sleep(DELAY_BETWEEN_API_CALLS)

            # Create donor entities and relationships
            created = await _create_donor_relationships(
                official["id"], name, contributors
            )
            total_donors_created += created
            logger.info("  Created %d new donor relationships for %s", created, name)

        except Exception as e:
            logger.error("Error processing %s: %s", name, e)
            errors.append({"official": name, "error": str(e)})

        # Update job progress
        async with async_session() as session:
            async with session.begin():
                await session.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job_id)
                    .values(progress=i + 1, errors=errors)
                )

        # Rate limit: sleep between officials
        if i < total - 1:
            logger.info("  Sleeping %ds before next official...", DELAY_BETWEEN_OFFICIALS)
            await asyncio.sleep(DELAY_BETWEEN_OFFICIALS)

    # Mark job complete
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job_id)
                .values(
                    status="completed",
                    progress=total,
                    completed_at=datetime.now(timezone.utc),
                    errors=errors,
                    metadata_={
                        "total_officials": total,
                        "total_donors_created": total_donors_created,
                        "errors_count": len(errors),
                    },
                )
            )

    summary = (
        f"Donor fetch complete: {total} officials processed, "
        f"{total_donors_created} donor relationships created, "
        f"{len(errors)} errors"
    )
    logger.info(summary)
    return summary
