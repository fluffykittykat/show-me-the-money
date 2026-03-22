import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import async_session
from app.routers import briefings, config, entities, graph, search
from app.schemas import HealthResponse
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

    # Auto-seed if database is empty
    async with async_session() as session:
        if await is_database_empty(session):
            print("Database is empty, auto-seeding...")
            await seed_database(session)
            print("Auto-seed complete.")

    yield


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


# Admin seed endpoint
from fastapi import APIRouter

admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.post("/seed")
async def admin_seed():
    from app.services.seed_service import run_seed

    await run_seed()
    return {"status": "ok", "message": "Database seeded successfully"}


@admin_router.post("/ingest/{slug}")
async def admin_ingest(slug: str):
    """Trigger real data ingestion for a given official."""
    from fastapi import BackgroundTasks
    from app.services.ingestion.ingest_fetterman import run_ingestion

    if slug != "john-fetterman":
        return {"status": "error", "message": f"Ingestion not yet supported for '{slug}'"}

    # Run synchronously for now (can be backgrounded later)
    await run_ingestion()
    return {"status": "ok", "message": f"Ingestion complete for {slug}"}


app.include_router(admin_router)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="healthy", version="0.1.0")
