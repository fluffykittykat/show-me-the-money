"""Fetch FEC total receipts for all officials missing them."""

import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.database import async_session
from app.models import Entity, IngestionJob
from app.services.ingestion.fec_client import FECClient

logger = logging.getLogger("fetch_totals")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)


async def run_fetch_totals() -> str:
    """Fetch FEC total receipts for officials missing them."""
    fec_api_key = os.getenv("FEC_API_KEY", "")
    if not fec_api_key:
        return "error: FEC_API_KEY not set"

    fec_client = FECClient(fec_api_key)

    # Find officials with candidate_id but no total_receipts
    async with async_session() as session:
        result = await session.execute(
            select(Entity)
            .where(Entity.entity_type == "person")
            .where(Entity.metadata_.has_key("fec_candidate_id"))
            .where(Entity.metadata_["fec_candidate_id"].astext != "")
        )
        officials = result.scalars().all()

    # Filter to those missing totals
    needs_totals = []
    for off in officials:
        meta = off.metadata_ or {}
        total = meta.get("total_receipts")
        if not total or total == 0 or total == "0":
            needs_totals.append(off)

    total = len(needs_totals)
    logger.info("Found %d officials missing FEC totals", total)

    if total == 0:
        return "All officials have totals"

    # Create job
    async with async_session() as session:
        async with session.begin():
            job = IngestionJob(
                job_type="fetch_totals",
                status="in_progress",
                total=total,
                progress=0,
                started_at=datetime.now(timezone.utc),
            )
            session.add(job)
            await session.flush()
            job_id = job.id

    updated = 0
    for i, official in enumerate(needs_totals):
        meta = official.metadata_ or {}
        candidate_id = meta.get("fec_candidate_id", "")

        try:
            await asyncio.sleep(2)  # Rate limit
            totals = await fec_client.fetch_candidate_totals(candidate_id, cycle=2024)
            if not totals:
                # Try 2022
                await asyncio.sleep(2)
                totals = await fec_client.fetch_candidate_totals(candidate_id, cycle=2022)

            if totals:
                receipts = totals.get("receipts", 0)
                if receipts:
                    async with async_session() as session:
                        async with session.begin():
                            ent = await session.get(Entity, official.id)
                            if ent:
                                new_meta = dict(ent.metadata_ or {})
                                new_meta["total_receipts"] = receipts
                                new_meta["total_disbursements"] = totals.get("disbursements", 0)
                                new_meta["individual_contributions"] = totals.get("individual_contributions", 0)
                                ent.metadata_ = new_meta
                    updated += 1
                    logger.info("[%d/%d] %s: $%s", i+1, total, official.name, f"{receipts:,.0f}")

        except Exception as e:
            logger.warning("[%d/%d] %s failed: %s", i+1, total, official.name, e)

        if (i + 1) % 25 == 0:
            async with async_session() as session:
                async with session.begin():
                    await session.execute(
                        update(IngestionJob).where(IngestionJob.id == job_id)
                        .values(progress=i+1)
                    )

    # Complete
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob).where(IngestionJob.id == job_id)
                .values(
                    status="completed", progress=total,
                    completed_at=datetime.now(timezone.utc),
                    metadata_={"updated": updated},
                )
            )

    logger.info("Done: %d/%d updated", updated, total)
    return f"Updated {updated}/{total}"
