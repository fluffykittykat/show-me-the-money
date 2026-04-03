import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import async_session
from app.routers import alerts, briefings, chat, config, cross_ref, dashboard, entities, graph, hidden_connections, investigation, refresh, search, trades, v2
from app.schemas import HealthResponse, IngestionJobResponse
from app.services.seed_service import is_database_empty, seed_database


def _run_migrations():
    """Run alembic migrations to head."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config(
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")
    )
    alembic_cfg.set_main_option(
        "script_location",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic"),
    )
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run migrations on startup
    _run_migrations()

    # Mark any stale in_progress ingestion jobs as interrupted
    from app.services.ingestion.batch_ingest import mark_stale_jobs_interrupted
    stale_count = await mark_stale_jobs_interrupted()
    if stale_count:
        print(f"Marked {stale_count} stale ingestion job(s) as interrupted.")

    # Auto-seed if database is empty
    async with async_session() as session:
        if await is_database_empty(session):
            print("Database is empty, auto-seeding...")
            await seed_database(session)
            print("Auto-seed complete.")

    # Start the scheduler
    from app.services.scheduler import start_scheduler, shutdown_scheduler

    start_scheduler(app)

    yield

    shutdown_scheduler()


app = FastAPI(
    title="Follow the Money",
    description="Political intelligence platform - Project Jerry Maguire",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CacheMiddleware(BaseHTTPMiddleware):
    """Add Cache-Control headers to GET requests for fast responses."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if request.method == "GET" and response.status_code == 200:
            path = request.url.path
            # Long cache for entity data (changes rarely)
            if path.startswith("/entities/") or path.startswith("/browse"):
                response.headers["Cache-Control"] = "public, max-age=300"  # 5 min
            elif path.startswith("/dashboard/"):
                response.headers["Cache-Control"] = "public, max-age=120"  # 2 min
            elif path.startswith("/search"):
                response.headers["Cache-Control"] = "public, max-age=60"  # 1 min
        return response


app.add_middleware(CacheMiddleware)

# Include routers
app.include_router(alerts.router)
app.include_router(entities.router)
app.include_router(search.router)
app.include_router(briefings.router)
app.include_router(graph.router)
app.include_router(config.router)
app.include_router(cross_ref.router)
app.include_router(investigation.router)
app.include_router(dashboard.router)
app.include_router(trades.router)
app.include_router(hidden_connections.router)
app.include_router(refresh.router)
app.include_router(chat.router)
app.include_router(v2.router, prefix="/v2")


# Admin seed endpoint
from fastapi import APIRouter

admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.post("/seed")
async def admin_seed():
    from app.services.seed_service import run_seed

    await run_seed()
    return {"status": "ok", "message": "Database seeded successfully"}


@admin_router.post("/ingest/batch")
async def admin_ingest_batch(force: bool = False):
    """Start batch ingestion of all Congress members via asyncio.create_task."""
    import asyncio
    from app.services.ingestion.batch_ingest import run_batch_ingestion, _running_tasks

    async def _run(force_flag: bool):
        try:
            return await run_batch_ingestion(force=force_flag)
        except Exception as exc:
            print(f"[batch_ingest] Background task error: {exc}")

    task = asyncio.create_task(_run(force))
    # Store task reference so it isn't garbage collected
    task_id = str(id(task))
    _running_tasks[task_id] = task
    return {"status": "started", "message": "Batch ingestion started in background"}


@admin_router.get("/ingest/status")
async def admin_ingest_status():
    """Return current ingestion status from ingestion_jobs table."""
    from sqlalchemy import select
    from app.models import IngestionJob
    from app.services.ingestion.batch_ingest import get_running_tasks

    running = get_running_tasks()
    async with async_session() as session:
        result = await session.execute(
            select(IngestionJob).order_by(IngestionJob.created_at.desc()).limit(10)
        )
        jobs = result.scalars().all()

    return {
        "running_tasks": running,
        "recent_jobs": [IngestionJobResponse.model_validate(j).model_dump() for j in jobs],
    }


@admin_router.get("/ingest/status/{job_id}")
async def admin_ingest_status_by_id(job_id: str):
    """Return status of a specific ingestion job."""
    import uuid as _uuid
    from sqlalchemy import select
    from app.models import IngestionJob

    try:
        parsed_id = _uuid.UUID(job_id)
    except ValueError:
        return {"error": "Invalid job ID format"}

    async with async_session() as session:
        result = await session.execute(
            select(IngestionJob).where(IngestionJob.id == parsed_id)
        )
        job = result.scalars().first()

    if not job:
        return {"error": "Job not found"}

    return IngestionJobResponse.model_validate(job).model_dump()


@admin_router.get("/scheduler/status")
async def admin_scheduler_status():
    """Return current scheduler status."""
    from app.services.scheduler import get_scheduler_status

    return get_scheduler_status()


@admin_router.post("/scheduler/run/{job_id}")
async def admin_scheduler_run_job(job_id: str):
    """Manually trigger a scheduler job by ID."""
    from app.services.scheduler import run_job_now

    return await run_job_now(job_id)


@admin_router.post("/ingest/{slug}")
async def admin_ingest(slug: str):
    """Trigger real data ingestion for a given official or group."""
    if slug == "john-fetterman":
        from app.services.ingestion.ingest_fetterman import run_ingestion
        await run_ingestion()
    elif slug in ("all", "committee-members"):
        from app.services.ingestion.ingest_all import run_full_ingestion
        await run_full_ingestion()
    elif slug == "lobbying":
        from app.services.ingestion.ingest_lobbying import run_lobbying_ingestion
        await run_lobbying_ingestion()
    elif slug == "committees":
        import asyncio as _aio
        from app.services.ingestion.ingest_committees import run_committee_ingestion
        _aio.create_task(run_committee_ingestion())
        return {"status": "started", "message": "Committee ingestion started"}
    elif slug == "link-revolving-door":
        import asyncio as _aio
        from app.services.ingestion.link_revolving_door import run_link_revolving_door
        _aio.create_task(run_link_revolving_door())
        return {"status": "started", "message": "Revolving door linking started"}
    elif slug == "lobbying-bulk":
        import asyncio as _aio
        from app.services.ingestion.ingest_lobbying_bulk import run_lobbying_bulk_ingestion
        _aio.create_task(run_lobbying_bulk_ingestion())
        return {"status": "started", "message": "Lobbying bulk ingestion started"}
    elif slug == "fetch-donors":
        import asyncio as _aio
        from app.services.ingestion.fetch_donors import run_fetch_donors
        _aio.create_task(run_fetch_donors())
        return {"status": "started", "message": "Donor fetch started (slow mode)"}
    elif slug == "fetch-totals":
        import asyncio as _aio
        from app.services.ingestion.fetch_totals import run_fetch_totals
        _aio.create_task(run_fetch_totals())
        return {"status": "started", "message": "FEC totals fetch started for 137 officials"}
    elif slug == "fix-all":
        import asyncio as _aio
        from app.services.ingestion.fix_all_data import run_fix_all_data
        _aio.create_task(run_fix_all_data())
        return {"status": "started", "message": "Fixing ALL data gaps — committee IDs, totals, donors"}
    elif slug == "fix-totals-best":
        import asyncio as _aio
        from app.services.ingestion.fix_totals_best_cycle import run_fix_totals_best_cycle
        _aio.create_task(run_fix_totals_best_cycle())
        return {"status": "started", "message": "Fixing totals to use best FEC cycle (2018-2024)"}
    elif slug == "fetch-all-cycles":
        import asyncio as _aio
        from app.services.ingestion.fetch_all_cycles import run_fetch_all_cycles
        _aio.create_task(run_fetch_all_cycles())
        return {"status": "started", "message": "Fetching ALL FEC cycles for all officials"}
    elif slug == "house-trades":
        import asyncio as _aio
        from app.services.ingestion.house_trades import ingest_house_trades
        async def _run_house_trades():
            await ingest_house_trades(2024)
            await ingest_house_trades(2025)
        _aio.create_task(_run_house_trades())
        return {"status": "started", "message": "Ingesting House stock trades for 2024+2025"}
    elif slug == "votes":
        import asyncio as _aio
        from app.services.ingestion.ingest_votes import run_full_vote_ingestion
        _aio.create_task(run_full_vote_ingestion())
        return {"status": "started", "message": "Scraping roll call votes from Senate.gov + House Clerk"}
    elif slug == "batch-refresh":
        import asyncio as _aio
        from app.services.ingestion.batch_refresh import run_batch_refresh
        _aio.create_task(run_batch_refresh())
        return {"status": "started", "message": "Batch refreshing all politicians missing donor data"}
    elif slug == "precompute":
        import asyncio as _aio
        from app.services.precompute import run_precompute
        _aio.create_task(run_precompute())
        return {"status": "started", "message": "Pre-computing verdicts + briefings for all officials"}
    elif slug == "party-money":
        import asyncio as _aio
        from app.services.ingestion.ingest_party_money import run_party_money_ingestion
        _aio.create_task(run_party_money_ingestion())
        return {"status": "started", "message": "Party committee money trail ingestion started"}
    elif slug == "lda-bills":
        import asyncio as _aio
        from app.services.ingestion.ingest_lda_bills import run_ingest_lda_bills
        _aio.create_task(run_ingest_lda_bills())
        return {"status": "started", "message": "Parsing bill numbers from LDA filings"}
    elif slug == "compute-baselines":
        import asyncio as _aio
        import logging as _logging
        _log = _logging.getLogger(__name__)
        from app.services.bill_baselines import compute_baselines
        from app.database import async_session
        async def _run():
            try:
                async with async_session() as session:
                    result = await compute_baselines(session)
                    await session.commit()
                    _log.info("Baselines computed: %d areas", len(result))
                    return result
            except Exception as e:
                _log.error("compute-baselines FAILED: %s", e, exc_info=True)
        _aio.create_task(_run())
        return {"status": "started", "message": "Computing bill baselines per policy area"}
    elif slug == "precompute-bill-signals":
        import asyncio as _aio
        from app.services.bill_signals import run_precompute_bill_signals
        _aio.create_task(run_precompute_bill_signals())
        return {"status": "started", "message": "Pre-computing influence signals for all bills"}
    elif slug == "precompute-official-signals":
        import asyncio as _aio
        from app.services.official_signals import run_precompute_official_signals
        _aio.create_task(run_precompute_official_signals())
        return {"status": "started", "message": "Pre-computing influence signals for all officials"}
    else:
        return {"status": "error", "message": f"Ingestion not supported for '{slug}'"}
    return {"status": "ok", "message": f"Ingestion complete for {slug}"}


@admin_router.post("/ingest/lobbying")
async def admin_ingest_lobbying(
    max_filings: int = 500,
    years: str = "2024,2025",
):
    """Start bulk lobbying ingestion from Senate LDA API.

    Args:
        max_filings: Max filings per year (default 500)
        years: Comma-separated filing years (default "2024,2025")
    """
    import asyncio
    from app.services.ingestion.ingest_lobbying_bulk import run_lobbying_bulk_ingestion

    year_list = [int(y.strip()) for y in years.split(",") if y.strip()]

    async def _run():
        try:
            return await run_lobbying_bulk_ingestion(
                years=year_list,
                max_filings=max_filings,
            )
        except Exception as exc:
            print(f"[ingest_lobbying_bulk] Error: {exc}")

    asyncio.create_task(_run())
    return {
        "status": "started",
        "message": f"Lobbying bulk ingestion started (years={year_list}, max={max_filings}/year)",
    }


@admin_router.post("/enrich/senators")
async def admin_enrich_senators():
    """Phase 2: Enrich all senators with LDA lobbying data."""
    import asyncio
    from app.services.ingestion.enrich_senators import enrich_all_senators

    async def _run():
        try:
            return await enrich_all_senators()
        except Exception as exc:
            print(f"[enrich] Error: {exc}")

    asyncio.create_task(_run())
    return {"status": "started", "message": "Senator enrichment started in background (LDA lobbying data)"}


@admin_router.post("/enrich/bills")
async def admin_enrich_bills(force: bool = False):
    """Enrich all bill entities with CRS summaries and full text URLs from Congress.gov."""
    import asyncio
    from app.services.ingestion.enrich_bills import run_bill_enrichment

    async def _run():
        try:
            return await run_bill_enrichment(force=force)
        except Exception as exc:
            print(f"[enrich_bills] Error: {exc}")

    asyncio.create_task(_run())
    return {"status": "started", "message": "Bill enrichment started in background (CRS summaries + text URLs)"}


@admin_router.post("/fec/rematch")
async def admin_fec_rematch():
    """Re-match FEC data for officials using bioguide→FEC crosswalk. 100% accuracy."""
    import asyncio
    from app.services.ingestion.fec_rematch import run_fec_rematch

    async def _run():
        try:
            return await run_fec_rematch()
        except Exception as exc:
            print(f"[fec_rematch] Error: {exc}")

    asyncio.create_task(_run())
    return {"status": "started", "message": "FEC re-match started using bioguide→FEC crosswalk (no name guessing)"}


@admin_router.post("/ingest/committees")
async def admin_ingest_committees():
    """Start committee assignment ingestion from congress-legislators data."""
    import asyncio
    from app.services.ingestion.ingest_committees import run_committee_ingestion

    async def _run():
        try:
            return await run_committee_ingestion()
        except Exception as exc:
            print(f"[committees] Error: {exc}")

    asyncio.create_task(_run())
    return {"status": "started", "message": "Committee ingestion started"}


@admin_router.post("/briefings/generate")
async def admin_generate_briefings(entity_type: str = "person", force: bool = False):
    """Pre-generate FBI briefings for all entities of a given type."""
    import asyncio
    from app.services.ai_service import ai_briefing_service

    async def _generate():
        async with async_session() as session:
            from sqlalchemy import select as sel
            from app.models import Entity as Ent
            result = await session.execute(
                sel(Ent).where(Ent.entity_type == entity_type)
            )
            entities = result.scalars().all()
            generated = 0
            skipped = 0
            for ent in entities:
                meta = ent.metadata_ or {}
                if not force and meta.get("fbi_briefing") and meta.get("fbi_briefing_fingerprint"):
                    skipped += 1
                    continue
                print(f"[briefings] Generating for {ent.slug}...")
                try:
                    await ai_briefing_service.generate_briefing(
                        entity_slug=ent.slug,
                        context_data={},
                        session=session,
                        force_refresh=force,
                    )
                    generated += 1
                except Exception as e:
                    print(f"[briefings] Error for {ent.slug}: {e}")
            return {"generated": generated, "skipped": skipped, "total": len(entities)}

    task = asyncio.create_task(_generate())
    return {"status": "started", "message": f"Generating briefings for all {entity_type} entities in background"}


@admin_router.get("/health/deep")
async def deep_health_check():
    """Run comprehensive health checks against all external APIs,
    database, and scheduler. Use after deploys or to diagnose issues."""
    from app.services.health_check import run_deep_health_check

    return await run_deep_health_check()


app.include_router(admin_router)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="healthy", version="0.1.0")
