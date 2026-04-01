"""Fetch ALL FEC cycle totals for every official and cache in metadata."""

import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.database import async_session
from app.models import Entity, IngestionJob
from app.services.ingestion.fec_client import FECClient

logger = logging.getLogger("fetch_all_cycles")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

CYCLES = [2026, 2024, 2022, 2020, 2018]
DELAY = 1.5


async def run_fetch_all_cycles() -> str:
    fec_api_key = os.getenv("FEC_API_KEY", "")
    if not fec_api_key:
        return "error: FEC_API_KEY not set"

    fec_client = FECClient(fec_api_key)

    async with async_session() as session:
        result = await session.execute(
            select(Entity)
            .where(Entity.entity_type == "person")
            .where(Entity.metadata_.has_key("bioguide_id"))
            .where(Entity.metadata_["fec_candidate_id"].astext != "")
        )
        officials = result.scalars().all()

    total = len(officials)
    logger.info("Fetching all FEC cycles for %d officials", total)

    async with async_session() as session:
        async with session.begin():
            job = IngestionJob(
                job_type="fetch_all_cycles",
                status="in_progress",
                total=total, progress=0,
                started_at=datetime.now(timezone.utc),
            )
            session.add(job)
            await session.flush()
            job_id = job.id

    updated = 0
    for i, official in enumerate(officials):
        meta = official.metadata_ or {}
        candidate_id = meta.get("fec_candidate_id", "")
        if not candidate_id:
            continue

        # Skip if already cached
        if meta.get("fec_all_cycles"):
            continue

        all_cycles = []
        for cycle in CYCLES:
            await asyncio.sleep(DELAY)
            try:
                totals = await fec_client.fetch_candidate_totals(candidate_id, cycle=cycle)
                if totals and totals.get("receipts", 0):
                    all_cycles.append({
                        "cycle": cycle,
                        "receipts": totals["receipts"],
                        "disbursements": totals.get("disbursements", 0),
                    })
            except Exception:
                continue

        if all_cycles:
            # Also update total_receipts to best cycle
            best = max(all_cycles, key=lambda c: c["receipts"])
            async with async_session() as session:
                async with session.begin():
                    ent = await session.get(Entity, official.id)
                    if ent:
                        new_meta = dict(ent.metadata_ or {})
                        new_meta["fec_all_cycles"] = all_cycles
                        new_meta["total_receipts"] = best["receipts"]
                        new_meta["best_fec_cycle"] = best["cycle"]
                        new_meta["campaign_total"] = best["receipts"]
                        ent.metadata_ = new_meta
            updated += 1
            total_raised = sum(c["receipts"] for c in all_cycles)
            logger.info("[%d/%d] %s: %d cycles, total $%s",
                        i+1, total, official.name, len(all_cycles), f"{total_raised:,.0f}")

        if (i + 1) % 20 == 0:
            async with async_session() as session:
                async with session.begin():
                    await session.execute(
                        update(IngestionJob).where(IngestionJob.id == job_id)
                        .values(progress=i+1)
                    )

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

    logger.info("Done: %d/%d updated with all cycles", updated, total)
    return f"Updated {updated}/{total}"
