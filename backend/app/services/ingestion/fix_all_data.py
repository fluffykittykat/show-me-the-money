"""
Fix ALL data gaps — one script to resolve everything.

1. Resolve FEC committee IDs for all officials missing them
2. Fetch donors for all officials missing donor records
3. Fetch FEC totals for anyone still missing them
4. All with proper rate limiting
"""

import asyncio
import logging
import os
import re
import uuid
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select, update

from app.database import async_session
from app.models import Entity, IngestionJob, Relationship
from app.services.ingestion.fec_client import FECClient

logger = logging.getLogger("fix_all_data")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

FEC_TIMEOUT = 30.0
DELAY = 2  # seconds between API calls


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _ascii_safe(obj):
    if isinstance(obj, str):
        return obj.encode("ascii", "replace").decode("ascii")
    if isinstance(obj, dict):
        return {k: _ascii_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ascii_safe(i) for i in obj]
    return obj


def _parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError, TypeError):
        try:
            return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None


async def run_fix_all_data() -> str:
    """Fix all data gaps for all officials."""
    fec_api_key = os.getenv("FEC_API_KEY", "")
    if not fec_api_key:
        return "error: FEC_API_KEY not set"

    fec_client = FECClient(fec_api_key)

    # Load all officials
    async with async_session() as session:
        result = await session.execute(
            select(Entity)
            .where(Entity.entity_type == "person")
            .where(Entity.metadata_.has_key("bioguide_id"))
        )
        all_officials = result.scalars().all()

    logger.info("Loaded %d officials", len(all_officials))

    # Create job
    async with async_session() as session:
        async with session.begin():
            job = IngestionJob(
                job_type="fix_all_data",
                status="in_progress",
                total=len(all_officials),
                progress=0,
                started_at=datetime.now(timezone.utc),
            )
            session.add(job)
            await session.flush()
            job_id = job.id

    stats = {
        "committee_ids_resolved": 0,
        "totals_fetched": 0,
        "donors_fetched": 0,
        "officials_with_new_donors": 0,
        "errors": 0,
    }

    for i, official in enumerate(all_officials):
        meta = official.metadata_ or {}
        name = official.name
        candidate_id = meta.get("fec_candidate_id", "")
        committee_id = meta.get("fec_committee_id", "")
        has_totals = meta.get("total_receipts") and float(meta.get("total_receipts", 0)) > 0

        # Check if has donors
        async with async_session() as session:
            donor_count = (await session.execute(
                select(Relationship)
                .where(Relationship.to_entity_id == official.id)
                .where(Relationship.relationship_type == "donated_to")
                .limit(1)
            )).scalar_one_or_none()
        has_donors = donor_count is not None

        needs_work = not committee_id or not has_totals or not has_donors

        if not needs_work:
            if (i + 1) % 50 == 0:
                logger.info("[%d/%d] %s — already complete", i + 1, len(all_officials), name)
            continue

        logger.info("[%d/%d] %s — fixing: committee_id=%s totals=%s donors=%s",
                    i + 1, len(all_officials), name,
                    "OK" if committee_id else "MISSING",
                    "OK" if has_totals else "MISSING",
                    "OK" if has_donors else "MISSING")

        try:
            # Step 1: Resolve committee ID if missing
            if not committee_id and candidate_id:
                await asyncio.sleep(DELAY)
                try:
                    url = f"https://api.open.fec.gov/v1/candidate/{candidate_id}/committees/"
                    async with httpx.AsyncClient(timeout=FEC_TIMEOUT) as client:
                        resp = await client.get(url, params={"api_key": fec_api_key})
                        resp.raise_for_status()
                        committees = resp.json().get("results", [])
                        # Find principal campaign committee
                        for c in committees:
                            if c.get("designation") == "P" or "principal" in c.get("designation_full", "").lower():
                                committee_id = c["committee_id"]
                                break
                        if not committee_id and committees:
                            committee_id = committees[0]["committee_id"]
                        if committee_id:
                            async with async_session() as session:
                                async with session.begin():
                                    ent = await session.get(Entity, official.id)
                                    if ent:
                                        new_meta = dict(ent.metadata_ or {})
                                        new_meta["fec_committee_id"] = committee_id
                                        ent.metadata_ = new_meta
                            stats["committee_ids_resolved"] += 1
                            logger.info("  Resolved committee: %s", committee_id)
                except Exception as e:
                    logger.warning("  Committee lookup failed: %s", e)

            # Step 2: Fetch totals if missing
            if not has_totals and candidate_id:
                await asyncio.sleep(DELAY)
                try:
                    totals = await fec_client.fetch_candidate_totals(candidate_id, cycle=2024)
                    if not totals:
                        await asyncio.sleep(DELAY)
                        totals = await fec_client.fetch_candidate_totals(candidate_id, cycle=2022)
                    if totals and totals.get("receipts"):
                        async with async_session() as session:
                            async with session.begin():
                                ent = await session.get(Entity, official.id)
                                if ent:
                                    new_meta = dict(ent.metadata_ or {})
                                    new_meta["total_receipts"] = totals["receipts"]
                                    new_meta["total_disbursements"] = totals.get("disbursements", 0)
                                    new_meta["individual_contributions"] = totals.get("individual_contributions", 0)
                                    ent.metadata_ = new_meta
                        stats["totals_fetched"] += 1
                        logger.info("  Fetched totals: $%s", f"{totals['receipts']:,.0f}")
                except Exception as e:
                    logger.warning("  Totals fetch failed: %s", e)

            # Step 3: Fetch donors if missing
            if not has_donors and committee_id:
                for cycle in [2024, 2022]:
                    await asyncio.sleep(DELAY)
                    try:
                        contributors = await fec_client.fetch_top_contributors(
                            committee_id, cycle=cycle, per_page=20
                        )
                        if not contributors:
                            continue

                        created = 0
                        async with async_session() as session:
                            async with session.begin():
                                for donor in contributors[:25]:
                                    donor_name = _ascii_safe(donor.get("contributor_name", "") or "")
                                    if not donor_name or len(donor_name) < 2:
                                        continue
                                    donor_slug = _slugify(donor_name)
                                    if not donor_slug:
                                        continue

                                    amount = donor.get("total", 0) or donor.get("contribution_receipt_amount", 0) or 0
                                    name_upper = donor_name.upper()
                                    is_pac = any(kw in name_upper for kw in [
                                        "PAC", "FUND", "VICTORY", "COMMITTEE", "DSCC", "DCCC",
                                        "EMILY", "ACTION", "SENATE", "HOUSE",
                                    ])
                                    donor_type = "pac" if is_pac else "person"

                                    donor_ent = (await session.execute(
                                        select(Entity).where(Entity.slug == donor_slug)
                                    )).scalar_one_or_none()
                                    if not donor_ent:
                                        donor_ent = Entity(
                                            slug=donor_slug,
                                            entity_type=donor_type,
                                            name=donor_name,
                                            metadata_=_ascii_safe({"donor_type": "pac" if is_pac else "individual"}),
                                        )
                                        session.add(donor_ent)
                                        await session.flush()

                                    existing_rel = (await session.execute(
                                        select(Relationship).where(
                                            Relationship.from_entity_id == donor_ent.id,
                                            Relationship.to_entity_id == official.id,
                                            Relationship.relationship_type == "donated_to",
                                        ).limit(1)
                                    )).scalar_one_or_none()
                                    if not existing_rel:
                                        amount_cents = int(float(amount) * 100) if amount else 0
                                        receipt_date = _parse_date(donor.get("contribution_receipt_date"))
                                        session.add(Relationship(
                                            from_entity_id=donor_ent.id,
                                            to_entity_id=official.id,
                                            relationship_type="donated_to",
                                            amount_usd=amount_cents,
                                            date_start=receipt_date,
                                            source_label="FEC",
                                        ))
                                        created += 1

                        if created > 0:
                            stats["donors_fetched"] += created
                            stats["officials_with_new_donors"] += 1
                            logger.info("  Fetched %d donors (cycle %d)", created, cycle)
                            break  # Got donors, don't need to try older cycle

                    except Exception as e:
                        logger.warning("  Donor fetch failed (cycle %d): %s", cycle, e)

        except Exception as e:
            stats["errors"] += 1
            logger.error("  Error: %s", e)

        # Update progress
        if (i + 1) % 10 == 0:
            async with async_session() as session:
                async with session.begin():
                    await session.execute(
                        update(IngestionJob).where(IngestionJob.id == job_id)
                        .values(progress=i + 1, metadata_=stats)
                    )
            logger.info("Progress: %d/%d | Stats: %s", i + 1, len(all_officials), stats)

    # Complete
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob).where(IngestionJob.id == job_id)
                .values(
                    status="completed",
                    progress=len(all_officials),
                    completed_at=datetime.now(timezone.utc),
                    metadata_=stats,
                )
            )

    logger.info("FIX ALL DATA COMPLETE: %s", stats)
    return f"Complete: {stats}"
