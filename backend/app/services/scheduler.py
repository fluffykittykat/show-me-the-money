"""
APScheduler-based daily scheduler for automated data ingestion.

Runs periodic jobs to fetch new trades, votes, bills, FEC filings,
lobbying disclosures, and refresh conflict detection.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.database import async_session
from app.models import AppConfig, DataSource, Entity, Relationship

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_last_run(session, job_id: str) -> Optional[datetime]:
    """Read last run timestamp from app_config."""
    from sqlalchemy import select

    key = f"scheduler_last_run_{job_id}"
    result = await session.execute(
        select(AppConfig.value).where(AppConfig.key == key)
    )
    value = result.scalar_one_or_none()
    if value:
        try:
            return datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return None
    return None


async def _set_last_run(session, job_id: str, ts: Optional[datetime] = None):
    """Write last run timestamp to app_config."""
    from sqlalchemy import select

    ts = ts or datetime.now(timezone.utc)
    key = f"scheduler_last_run_{job_id}"
    result = await session.execute(
        select(AppConfig).where(AppConfig.key == key)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = ts.isoformat()
    else:
        entry = AppConfig(
            key=key,
            value=ts.isoformat(),
            description=f"Last run time for scheduler job: {job_id}",
            is_secret=False,
        )
        session.add(entry)
    await session.commit()


async def _record_ingestion_job(
    session, job_id: str, status: str, records_fetched: int = 0,
    records_created: int = 0, error_message: str = "",
):
    """Record an ingestion job run."""
    try:
        from app.models import IngestionJob
        from datetime import datetime, timezone

        job = IngestionJob(
            job_type=job_id,
            status=status,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc) if status in ("completed", "failed", "skipped") else None,
            metadata_={
                "records_fetched": records_fetched,
                "records_created": records_created,
            },
            errors=[{"message": error_message}] if error_message else [],
        )
        session.add(job)
        await session.commit()
    except Exception as exc:
        logger.warning("Failed to record ingestion job %s: %s", job_id, exc)
        try:
            await session.rollback()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Job implementations
# ---------------------------------------------------------------------------


async def _fetch_new_trades():
    """Poll Senate eFD for new Periodic Transaction Reports."""
    job_id = "fetch_new_trades"
    logger.info("[Scheduler] Running %s", job_id)

    async with async_session() as session:
        last_run = await _get_last_run(session, job_id)
        from_date = (last_run.date() if last_run else date.today() - timedelta(days=7))
        to_date = date.today()

        records_fetched = 0
        records_created = 0

        try:
            # Fetch PTRs via Senate eFD (efdsearch.senate.gov)
            from app.services.ingestion.efd_client import EFDClient

            efd = EFDClient()
            results = await efd.fetch_ptr_reports(
                start_date=from_date.strftime("%m/%d/%Y"),
                end_date=to_date.strftime("%m/%d/%Y"),
            )

            records_fetched = len(results)
            for record in results:
                await _process_ptr_record(session, record)
                records_created += 1

            # Clear stale is_new flags
            from app.services.trade_alerts import clear_stale_new_flags

            await clear_stale_new_flags(session)

            await _set_last_run(session, job_id)
            await _record_ingestion_job(
                session, job_id, "completed",
                records_fetched=records_fetched,
                records_created=records_created,
            )
            logger.info(
                "[Scheduler] %s complete: fetched=%d, created=%d",
                job_id, records_fetched, records_created,
            )

        except Exception as exc:
            logger.error("[Scheduler] %s failed: %s", job_id, exc)
            await _record_ingestion_job(
                session, job_id, "failed", error_message=str(exc)
            )


async def _process_ptr_record(session, record: dict):
    """Process a single PTR record from eFD and create/update entities + relationships."""
    from sqlalchemy import select

    # Support both old format (senator, date) and new format (first_name, last_name, date_received)
    first = record.get("first_name", "")
    last = record.get("last_name", "")
    senator_name = record.get("senator") or f"{first} {last}".strip() or "Unknown"
    slug = senator_name.lower().replace(" ", "-").replace(",", "").replace(".", "")
    description = record.get("description", "")
    report_date = record.get("date_received", record.get("date", ""))
    transaction_type = record.get("transaction_type", "")
    amount = record.get("amount", "")
    ticker = record.get("ticker", "")

    # Try to extract ticker from description if not provided
    if not ticker and description:
        import re

        match = re.search(r"\(([A-Z]{1,5})\)", description)
        if match:
            ticker = match.group(1)

    # Find or skip if no entity found
    result = await session.execute(
        select(Entity).where(Entity.slug == slug)
    )
    official = result.scalar_one_or_none()

    if not official:
        # Try partial match
        result = await session.execute(
            select(Entity).where(
                Entity.name.ilike(f"%{senator_name}%"),
                Entity.entity_type == "person",
            )
        )
        official = result.scalar_one_or_none()

    if not official:
        logger.debug("No entity found for senator: %s", senator_name)
        return

    # Find or create the stock entity
    stock_name = ticker or description[:100] if description else "Unknown Asset"
    stock_slug = f"stock-{ticker.lower()}" if ticker else f"asset-{slug}-{report_date}"

    result = await session.execute(
        select(Entity).where(Entity.slug == stock_slug)
    )
    stock_entity = result.scalar_one_or_none()

    if not stock_entity:
        stock_entity = Entity(
            slug=stock_slug,
            entity_type="stock",
            name=stock_name,
            summary=f"Stock: {ticker}" if ticker else f"Asset: {description[:200]}" if description else "",
            metadata_={"ticker": ticker} if ticker else {},
        )
        session.add(stock_entity)
        await session.flush()

    # Create the trade relationship
    meta = {
        "ticker": ticker,
        "transaction_type": transaction_type or "Unknown",
        "is_new": True,
        "filed_date": report_date,
        "description": description[:500] if description else "",
        "raw_record": record,
    }

    trade_date = None
    if report_date:
        from app.services.trade_alerts import _parse_date_safe

        trade_date = _parse_date_safe(report_date)

    rel = Relationship(
        from_entity_id=official.id,
        to_entity_id=stock_entity.id,
        relationship_type="holds_stock",
        amount_label=amount or None,
        date_start=trade_date,
        source_url=record.get("report_url", "https://efdsearch.senate.gov/search/"),
        source_label="Senate eFD PTR",
        metadata_=meta,
    )
    session.add(rel)
    await session.commit()

    # Cross-reference: detect trade patterns
    if ticker and trade_date:
        try:
            from app.services.trade_alerts import detect_trade_pattern

            await detect_trade_pattern(session, ticker, trade_date, official.slug)
        except Exception as exc:
            logger.warning("Trade pattern detection failed for %s: %s", ticker, exc)


async def _fetch_new_votes():
    """Check Congress.gov for new floor votes.

    NOTE: The Congress.gov API v3 does NOT support per-member vote endpoints
    (/member/{id}/votes returns 404). Instead we poll the chamber-level
    recent-votes endpoint and match members from the vote rolls.
    """
    job_id = "fetch_new_votes"
    logger.info("[Scheduler] Running %s", job_id)

    async with async_session() as session:
        last_run = await _get_last_run(session, job_id)
        records_fetched = 0
        records_created = 0

        try:
            from app.services.config_service import get_config_value

            api_key = await get_config_value(session, "CONGRESS_GOV_API_KEY")
            if not api_key:
                logger.warning("[Scheduler] %s skipped: no CONGRESS_GOV_API_KEY", job_id)
                await _record_ingestion_job(
                    session, job_id, "skipped",
                    error_message="No CONGRESS_GOV_API_KEY configured",
                )
                return

            import asyncio
            import httpx

            # Congress.gov v3 supports house-vote/{congress}/{session} but
            # has no equivalent senate-vote endpoint.
            congress_num = 119
            session_num = 1
            base_params = {"api_key": api_key, "format": "json", "limit": 50}

            # --- House votes via Congress.gov v3 API ---
            url = f"https://api.congress.gov/v3/house-vote/{congress_num}/{session_num}"
            try:
                async with httpx.AsyncClient(timeout=30.0) as http:
                    await asyncio.sleep(0.5)
                    resp = await http.get(url, params=base_params)
                    resp.raise_for_status()
                    data = resp.json()
                    votes = data.get("houseRollCallVotes", [])
                    records_fetched += len(votes)

                    for vote in votes:
                        vote_date_str = vote.get("startDate", "")
                        if vote_date_str and last_run:
                            from app.services.trade_alerts import _parse_date_safe

                            vote_date = _parse_date_safe(vote_date_str[:10])
                            if vote_date and vote_date < last_run.date():
                                continue
                        records_created += 1

                    logger.info(
                        "[Scheduler] House votes: fetched %d roll calls", len(votes)
                    )
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "[Scheduler] Failed to fetch house votes: HTTP %s",
                    exc.response.status_code,
                )
            except Exception as exc:
                logger.warning("[Scheduler] Failed to fetch house votes: %s", exc)

            # --- Senate votes: not available in Congress.gov v3 API ---
            # Senate roll-call data requires scraping senate.gov XML feeds.
            # Skipped for now; logged as known gap.
            logger.info(
                "[Scheduler] Senate votes: skipped (no Congress.gov v3 endpoint)"
            )

            await _set_last_run(session, job_id)
            await _record_ingestion_job(
                session, job_id, "completed",
                records_fetched=records_fetched,
                records_created=records_created,
            )
            logger.info(
                "[Scheduler] %s complete: fetched=%d, created=%d",
                job_id, records_fetched, records_created,
            )

        except Exception as exc:
            logger.error("[Scheduler] %s failed: %s", job_id, exc)
            await _record_ingestion_job(
                session, job_id, "failed", error_message=str(exc)
            )


async def _fetch_new_bills():
    """Fetch new/updated bills from Congress.gov."""
    job_id = "fetch_new_bills"
    logger.info("[Scheduler] Running %s", job_id)

    async with async_session() as session:
        records_fetched = 0
        records_created = 0

        try:
            from app.services.config_service import get_config_value

            api_key = await get_config_value(session, "CONGRESS_GOV_API_KEY")
            if not api_key:
                logger.warning("[Scheduler] %s skipped: no CONGRESS_GOV_API_KEY", job_id)
                await _record_ingestion_job(
                    session, job_id, "skipped",
                    error_message="No CONGRESS_GOV_API_KEY configured",
                )
                return

            from app.services.ingestion.congress_client import CongressClient
            from sqlalchemy import select

            client = CongressClient(api_key)

            # Fetch bills for all tracked officials
            stmt = select(Entity).where(
                Entity.entity_type == "person",
                Entity.metadata_["bioguide_id"].astext.isnot(None),
            )
            result = await session.execute(stmt)
            officials = result.scalars().all()

            for official in officials:
                bioguide_id = (official.metadata_ or {}).get("bioguide_id")
                if not bioguide_id:
                    continue

                try:
                    bills = await client.fetch_sponsored_legislation(
                        bioguide_id, limit=20
                    )
                    records_fetched += len(bills)

                    cosponsored = await client.fetch_cosponsored_legislation(
                        bioguide_id, limit=20
                    )
                    records_fetched += len(cosponsored)

                except Exception as exc:
                    logger.warning(
                        "Failed to fetch bills for %s: %s", bioguide_id, exc
                    )

            records_created = records_fetched  # Simplified
            await _set_last_run(session, job_id)
            await _record_ingestion_job(
                session, job_id, "completed",
                records_fetched=records_fetched,
                records_created=records_created,
            )
            logger.info("[Scheduler] %s complete: fetched=%d", job_id, records_fetched)

        except Exception as exc:
            logger.error("[Scheduler] %s failed: %s", job_id, exc)
            await _record_ingestion_job(
                session, job_id, "failed", error_message=str(exc)
            )


async def _fetch_fec_updates():
    """Check FEC for new filings."""
    job_id = "fetch_fec_updates"
    logger.info("[Scheduler] Running %s", job_id)

    async with async_session() as session:
        records_fetched = 0
        records_created = 0

        try:
            from app.services.config_service import get_config_value

            api_key = await get_config_value(session, "FEC_API_KEY")
            if not api_key:
                logger.warning("[Scheduler] %s skipped: no FEC_API_KEY", job_id)
                await _record_ingestion_job(
                    session, job_id, "skipped",
                    error_message="No FEC_API_KEY configured",
                )
                return

            import httpx
            from app.services.ingestion.fec_client import FECClient
            from sqlalchemy import select

            fec = FECClient(api_key)

            # Get officials with FEC candidate IDs
            stmt = select(Entity).where(
                Entity.entity_type == "person",
                Entity.metadata_["fec_candidate_id"].astext.isnot(None),
            )
            result = await session.execute(stmt)
            officials = result.scalars().all()

            import asyncio

            DELAY_BETWEEN_OFFICIALS = 2  # seconds — FEC rate limit is ~1000 req/hr

            for idx, official in enumerate(officials, 1):
                meta = official.metadata_ or {}
                candidate_id = meta.get("fec_candidate_id")
                committee_id = meta.get("fec_committee_id")
                if not candidate_id:
                    continue

                try:
                    await asyncio.sleep(DELAY_BETWEEN_OFFICIALS)
                    totals = await fec.fetch_candidate_totals(candidate_id)
                    if totals:
                        records_fetched += 1

                    if committee_id:
                        await asyncio.sleep(DELAY_BETWEEN_OFFICIALS)
                        contributors = await fec.fetch_top_contributors(
                            committee_id
                        )
                        records_fetched += len(contributors)
                        records_created += len(contributors)

                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        logger.warning(
                            "[Scheduler] FEC rate limited at official %d/%d, backing off 60s",
                            idx, len(officials),
                        )
                        await asyncio.sleep(60)
                    else:
                        logger.warning(
                            "Failed to fetch FEC data for %s: %s", candidate_id, exc
                        )
                except Exception as exc:
                    logger.warning(
                        "Failed to fetch FEC data for %s: %s", candidate_id, exc
                    )

            await _set_last_run(session, job_id)
            await _record_ingestion_job(
                session, job_id, "completed",
                records_fetched=records_fetched,
                records_created=records_created,
            )
            logger.info("[Scheduler] %s complete: fetched=%d", job_id, records_fetched)

        except Exception as exc:
            logger.error("[Scheduler] %s failed: %s", job_id, exc)
            await _record_ingestion_job(
                session, job_id, "failed", error_message=str(exc)
            )


async def _refresh_conflicts():
    """Re-run conflict detection on updated officials."""
    job_id = "refresh_conflicts"
    logger.info("[Scheduler] Running %s", job_id)

    async with async_session() as session:
        records_processed = 0

        try:
            from app.services.conflict_engine import detect_conflicts
            from sqlalchemy import select

            stmt = select(Entity).where(Entity.entity_type == "person")
            result = await session.execute(stmt)
            officials = result.scalars().all()

            for official in officials:
                try:
                    await detect_conflicts(session, official.slug)
                    records_processed += 1
                except Exception as exc:
                    logger.warning(
                        "Conflict detection failed for %s: %s", official.slug, exc
                    )

            await _set_last_run(session, job_id)
            await _record_ingestion_job(
                session, job_id, "completed",
                records_fetched=records_processed,
                records_created=0,
            )
            logger.info(
                "[Scheduler] %s complete: processed %d officials",
                job_id, records_processed,
            )

        except Exception as exc:
            logger.error("[Scheduler] %s failed: %s", job_id, exc)
            await _record_ingestion_job(
                session, job_id, "failed", error_message=str(exc)
            )


async def _weekly_lobbying():
    """Update lobbying disclosures (weekly)."""
    job_id = "weekly_lobbying"
    logger.info("[Scheduler] Running %s", job_id)

    async with async_session() as session:
        try:
            # Try to use existing lobbying ingestion if available
            try:
                from app.services.ingestion.ingest_lobbying import run_lobbying_ingestion

                await run_lobbying_ingestion()
            except ImportError:
                logger.info(
                    "[Scheduler] Lobbying ingestion module not available; skipping"
                )

            await _set_last_run(session, job_id)
            await _record_ingestion_job(session, job_id, "completed")
            logger.info("[Scheduler] %s complete", job_id)

        except Exception as exc:
            logger.error("[Scheduler] %s failed: %s", job_id, exc)
            await _record_ingestion_job(
                session, job_id, "failed", error_message=str(exc)
            )


async def _run_precompute():
    """Re-compute verdicts + briefings for all officials."""
    try:
        from app.services.precompute import run_precompute
        logger.info("[Scheduler] Starting precompute job")
        result = await run_precompute()
        logger.info(f"[Scheduler] Precompute complete: {result}")
    except Exception as exc:
        logger.error(f"[Scheduler] precompute failed: {exc}")


async def _weekly_top_refresh():
    """Full refresh of top 50 politicians by dot count + all OWNED/COMPROMISED."""
    job_id = "weekly_top_refresh"
    logger.info("[Scheduler] Running %s", job_id)

    async with async_session() as session:
        try:
            from sqlalchemy import select, text

            # Get top 50 by dot count + all OWNED/COMPROMISED
            result = await session.execute(
                select(Entity.slug, Entity.name).where(
                    Entity.entity_type == "person",
                    Entity.metadata_["chamber"].astext.isnot(None),
                ).order_by(
                    text("(metadata->>'v2_dot_count')::int DESC NULLS LAST")
                ).limit(50)
            )
            top_politicians = list(result.all())

            # Also grab any OWNED/COMPROMISED not already in the top 50
            top_slugs = {slug for slug, _ in top_politicians}
            owned_result = await session.execute(
                select(Entity.slug, Entity.name).where(
                    Entity.entity_type == "person",
                    Entity.metadata_["v2_verdict"].astext.in_(["OWNED", "COMPROMISED"]),
                    Entity.slug.notin_(top_slugs),
                )
            )
            for slug, name in owned_result.all():
                top_politicians.append((slug, name))

            logger.info(
                "[Scheduler] Weekly top refresh: %d politicians to refresh",
                len(top_politicians),
            )

            import httpx
            success = 0
            failed = 0
            for idx, (slug, name) in enumerate(top_politicians, 1):
                try:
                    async with httpx.AsyncClient(timeout=180.0) as client:
                        resp = await client.post(
                            f"http://localhost:8000/refresh/{slug}"
                        )
                        if resp.status_code == 200:
                            success += 1
                        else:
                            failed += 1
                except Exception as exc:
                    logger.warning(
                        "[Scheduler] Weekly refresh failed for %s: %s", name, exc
                    )
                    failed += 1

                # Rate limit between refreshes
                import asyncio as _asyncio
                await _asyncio.sleep(3)

                if idx % 10 == 0:
                    logger.info(
                        "[Scheduler] Weekly refresh progress: %d/%d",
                        idx, len(top_politicians),
                    )

            await _set_last_run(session, job_id)
            await _record_ingestion_job(
                session, job_id, "completed",
                records_fetched=len(top_politicians),
                records_created=success,
                error_message=f"{failed} failed" if failed else "",
            )
            logger.info(
                "[Scheduler] %s complete: %d/%d refreshed, %d failed",
                job_id, success, len(top_politicians), failed,
            )

        except Exception as exc:
            logger.error("[Scheduler] %s failed: %s", job_id, exc)
            await _record_ingestion_job(
                session, job_id, "failed", error_message=str(exc),
            )


# ---------------------------------------------------------------------------
# Job registry
# ---------------------------------------------------------------------------

JOB_REGISTRY = {
    "fetch_new_trades": {
        "func": _fetch_new_trades,
        "trigger": IntervalTrigger(hours=4),
        "description": "Poll Senate eFD for new PTRs",
    },
    "fetch_new_votes": {
        "func": _fetch_new_votes,
        "trigger": IntervalTrigger(hours=4),
        "description": "Check Congress.gov for new floor votes (by chamber)",
    },
    "fetch_new_bills": {
        "func": _fetch_new_bills,
        "trigger": CronTrigger(hour=6, minute=0),
        "description": "Fetch new/updated bills",
    },
    "fetch_fec_updates": {
        "func": _fetch_fec_updates,
        "trigger": CronTrigger(hour=3, minute=0),
        "description": "Check FEC for new filings",
    },
    "refresh_conflicts": {
        "func": _refresh_conflicts,
        "trigger": CronTrigger(hour=7, minute=0),
        "description": "Re-run conflict detection on updated officials",
    },
    "weekly_lobbying": {
        "func": _weekly_lobbying,
        "trigger": CronTrigger(day_of_week="sun", hour=2, minute=0),
        "description": "Update lobbying disclosures",
    },
    "weekly_top_refresh": {
        "func": _weekly_top_refresh,
        "trigger": CronTrigger(day_of_week="sat", hour=4, minute=0),
        "description": "Full refresh of top 50 + OWNED/COMPROMISED politicians (weekly)",
    },
    "precompute_verdicts": {
        "func": _run_precompute,
        "trigger": IntervalTrigger(hours=1),
        "description": "Re-compute money trail verdicts and briefings (hourly)",
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start_scheduler(app=None):
    """Create, configure, and start the AsyncIOScheduler."""
    global _scheduler

    if _scheduler is not None:
        logger.warning("[Scheduler] Scheduler already running")
        return

    _scheduler = AsyncIOScheduler(timezone="UTC")

    for job_id, job_info in JOB_REGISTRY.items():
        _scheduler.add_job(
            job_info["func"],
            trigger=job_info["trigger"],
            id=job_id,
            name=job_info["description"],
            replace_existing=True,
            misfire_grace_time=3600,  # 1 hour grace period
        )

    _scheduler.start()
    logger.info("[Scheduler] Started with %d jobs", len(JOB_REGISTRY))


def shutdown_scheduler():
    """Shut down the scheduler gracefully."""
    global _scheduler

    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Shut down")
        _scheduler = None


def get_scheduler_status() -> dict:
    """Return status information for all scheduled jobs."""
    if _scheduler is None:
        return {"jobs": [], "scheduler_running": False}

    jobs = []
    for job in _scheduler.get_jobs():
        job_info = JOB_REGISTRY.get(job.id, {})
        trigger = job.trigger

        # Format the trigger description
        trigger_str = str(trigger)
        if isinstance(trigger, IntervalTrigger):
            trigger_str = f"interval: {trigger.interval}"
        elif isinstance(trigger, CronTrigger):
            # Build a human-readable cron description
            fields = {f.name: str(f) for f in trigger.fields}
            trigger_str = f"cron: {fields}"

        jobs.append({
            "id": job.id,
            "trigger": trigger_str,
            "description": job_info.get("description", job.name),
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "last_run_time": None,  # APScheduler 3.x doesn't track this; we use app_config
            "status": "scheduled" if job.next_run_time else "paused",
        })

    return {"jobs": jobs, "scheduler_running": _scheduler.running}


async def run_job_now(job_id: str) -> dict:
    """Manually trigger a job by ID. Returns status info."""
    if job_id not in JOB_REGISTRY:
        return {"status": "error", "message": f"Unknown job: {job_id}"}

    job_info = JOB_REGISTRY[job_id]

    # Run the job function directly
    try:
        await job_info["func"]()
        return {
            "status": "ok",
            "message": f"Job '{job_id}' executed successfully",
            "job_id": job_id,
        }
    except Exception as exc:
        logger.error("[Scheduler] Manual run of %s failed: %s", job_id, exc)
        return {
            "status": "error",
            "message": f"Job '{job_id}' failed: {exc}",
            "job_id": job_id,
        }
