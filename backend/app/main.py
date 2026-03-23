import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import async_session
from app.routers import briefings, config, cross_ref, dashboard, entities, graph, hidden_connections, investigation, search, trades
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

# Include routers
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
    else:
        return {"status": "error", "message": f"Ingestion not supported for '{slug}'"}
    return {"status": "ok", "message": f"Ingestion complete for {slug}"}


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


app.include_router(admin_router)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="healthy", version="0.1.0")
