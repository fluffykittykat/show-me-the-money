"""
Pre-Compute Background Job — Verdict Engine + AI Briefings

Runs the verdict engine for ALL officials, stores results in money_trails,
and pre-generates AI briefings so the frontend loads instantly.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.database import async_session
from app.models import Entity, IngestionJob, MoneyTrail
from app.services.verdict_engine import compute_overall_verdict, compute_verdicts

logger = logging.getLogger(__name__)


async def run_precompute(force: bool = False) -> str:
    """Pre-compute verdicts + briefings for all officials.

    Steps:
    1. Load all officials with bioguide_id
    2. For each: run verdict_engine.compute_verdicts()
    3. Store results in money_trails table (delete old, insert new per official)
    4. Compute overall verdict and store in entity metadata as 'v2_verdict' and 'v2_dot_count'
    5. Pre-generate AI briefing if not cached (or force=True)
    6. Track progress via IngestionJob (job_type="precompute")
    """
    async with async_session() as session:
        # ── Create tracking job ──────────────────────────────────────
        job = IngestionJob(
            id=uuid.uuid4(),
            job_type="precompute",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.commit()

        # ── Load all officials with bioguide_id ──────────────────────
        officials_q = (
            select(Entity)
            .where(Entity.entity_type == "official")
        )
        result = await session.execute(officials_q)
        officials = result.scalars().all()

        # Filter to those with bioguide_id in metadata
        officials = [
            o for o in officials
            if (o.metadata_ or {}).get("bioguide_id")
        ]

        total = len(officials)
        job.total = total
        await session.commit()

        logger.info("Precompute started: %d officials to process", total)

        errors: list[dict] = []
        processed = 0

        for i, official in enumerate(officials, 1):
            try:
                # ── Step 2: Compute verdicts ─────────────────────────
                trails = await compute_verdicts(session, official.id)

                # ── Step 3: Store in money_trails table ──────────────
                # Delete old trails for this official
                await session.execute(
                    delete(MoneyTrail).where(
                        MoneyTrail.official_id == official.id
                    )
                )

                # Insert new trails
                now = datetime.now(timezone.utc)
                for trail in trails:
                    mt = MoneyTrail(
                        id=uuid.uuid4(),
                        official_id=official.id,
                        industry=trail["industry"],
                        verdict=trail["verdict"],
                        dot_count=trail["dot_count"],
                        narrative=trail.get("narrative"),
                        chain=trail.get("chain", {}),
                        total_amount=trail.get("total_amount", 0),
                        computed_at=now,
                    )
                    session.add(mt)

                # ── Step 4: Compute overall verdict ──────────────────
                overall_verdict, total_dots = compute_overall_verdict(trails)
                meta = dict(official.metadata_ or {})
                meta["v2_verdict"] = overall_verdict
                meta["v2_dot_count"] = total_dots
                official.metadata_ = meta

                await session.commit()

                # ── Step 5: Pre-generate AI briefing ─────────────────
                try:
                    cached_briefing = (official.metadata_ or {}).get("fbi_briefing")
                    if force or not cached_briefing:
                        from app.services.ai_service import ai_briefing_service

                        await ai_briefing_service.generate_briefing(
                            entity_slug=official.slug,
                            context_data={},
                            session=session,
                            force_refresh=force,
                        )
                except Exception as briefing_err:
                    logger.warning(
                        "Briefing generation failed for %s: %s",
                        official.slug,
                        briefing_err,
                    )

                processed += 1

            except Exception as exc:
                logger.error(
                    "Precompute failed for %s: %s", official.slug, exc
                )
                errors.append({
                    "slug": official.slug,
                    "error": str(exc),
                })
                # Rollback the failed transaction and continue
                await session.rollback()

            # ── Update progress ──────────────────────────────────────
            if i % 25 == 0 or i == total:
                logger.info(
                    "Precompute progress: %d/%d (%d errors)",
                    i,
                    total,
                    len(errors),
                )
                try:
                    job.progress = i
                    job.errors = errors
                    await session.commit()
                except Exception:
                    await session.rollback()

        # ── Mark job complete ────────────────────────────────────────
        try:
            job.status = "completed"
            job.progress = total
            job.completed_at = datetime.now(timezone.utc)
            job.errors = errors
            job.metadata_ = {
                "processed": processed,
                "errors_count": len(errors),
                "force": force,
            }
            await session.commit()
        except Exception:
            await session.rollback()

        summary = (
            f"Precompute complete: {processed}/{total} officials, "
            f"{len(errors)} errors"
        )
        logger.info(summary)
        return summary
