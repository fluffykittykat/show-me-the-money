"""
Fix FEC totals to use the BEST cycle (highest receipts), not just 2024.

Senators in off-years show very low totals because they're not actively
fundraising. This script checks cycles 2024, 2022, 2020, 2018 and
stores the highest.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.database import async_session
from app.models import Entity, IngestionJob
from app.services.ingestion.fec_client import FECClient

logger = logging.getLogger("fix_totals_best")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

CYCLES = [2024, 2022, 2020, 2018]
DELAY = 2


async def run_fix_totals_best_cycle() -> str:
    fec_api_key = os.getenv("FEC_API_KEY", "")
    if not fec_api_key:
        return "error: FEC_API_KEY not set"

    fec_client = FECClient(fec_api_key)

    # Load all officials with FEC candidate IDs
    async with async_session() as session:
        result = await session.execute(
            select(Entity)
            .where(Entity.entity_type == "person")
            .where(Entity.metadata_.has_key("bioguide_id"))
            .where(Entity.metadata_["fec_candidate_id"].astext != "")
        )
        officials = result.scalars().all()

    total = len(officials)
    logger.info("Checking best cycle totals for %d officials", total)

    async with async_session() as session:
        async with session.begin():
            job = IngestionJob(
                job_type="fix_totals_best_cycle",
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
        current_total = float(meta.get("total_receipts", 0) or 0)

        if not candidate_id:
            continue

        best_receipts = current_total
        best_cycle = None
        best_totals = {}

        for cycle in CYCLES:
            await asyncio.sleep(DELAY)
            try:
                totals = await fec_client.fetch_candidate_totals(candidate_id, cycle=cycle)
                if totals:
                    receipts = totals.get("receipts", 0) or 0
                    if receipts > best_receipts:
                        best_receipts = receipts
                        best_cycle = cycle
                        best_totals = totals
            except Exception:
                continue

        if best_cycle and best_receipts > current_total:
            async with async_session() as session:
                async with session.begin():
                    ent = await session.get(Entity, official.id)
                    if ent:
                        new_meta = dict(ent.metadata_ or {})
                        new_meta["total_receipts"] = best_receipts
                        new_meta["total_disbursements"] = best_totals.get("disbursements", 0)
                        new_meta["individual_contributions"] = best_totals.get("individual_contributions", 0)
                        new_meta["best_fec_cycle"] = best_cycle
                        ent.metadata_ = new_meta
            updated += 1
            logger.info("[%d/%d] %s: $%s → $%s (cycle %d)",
                        i+1, total, official.name,
                        f"{current_total:,.0f}", f"{best_receipts:,.0f}", best_cycle)

        if (i + 1) % 10 == 0:
            async with async_session() as session:
                async with session.begin():
                    await session.execute(
                        update(IngestionJob).where(IngestionJob.id == job_id)
                        .values(progress=i+1)
                    )
            logger.info("Progress: %d/%d, updated: %d", i+1, total, updated)

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

    logger.info("Done: %d/%d updated to better cycle", updated, total)
    return f"Updated {updated}/{total}"
