"""
Deep health check service — verifies all external API connections and
scheduler jobs are functional. Run after every deploy or on-demand via
the /admin/health/deep endpoint.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.database import async_session

logger = logging.getLogger(__name__)

TIMEOUT = 15.0


async def _check_database() -> dict:
    """Verify database connectivity and basic query execution."""
    start = time.monotonic()
    try:
        from sqlalchemy import text

        async with async_session() as session:
            result = await session.execute(text("SELECT 1"))
            result.scalar_one()

            # Check entity count as sanity
            result = await session.execute(text("SELECT count(*) FROM entities"))
            count = result.scalar_one()

        elapsed = round(time.monotonic() - start, 3)
        return {
            "status": "ok",
            "latency_s": elapsed,
            "entity_count": count,
        }
    except Exception as exc:
        elapsed = round(time.monotonic() - start, 3)
        return {"status": "error", "latency_s": elapsed, "error": str(exc)}


async def _check_congress_api() -> dict:
    """Verify Congress.gov API v3 is reachable and key is valid."""
    start = time.monotonic()
    try:
        from app.services.config_service import get_config_value

        async with async_session() as session:
            api_key = await get_config_value(session, "CONGRESS_GOV_API_KEY")

        if not api_key:
            return {"status": "skipped", "reason": "No CONGRESS_GOV_API_KEY configured"}

        # Test member list endpoint (lightest call)
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://api.congress.gov/v3/member",
                params={"api_key": api_key, "format": "json", "limit": 1},
            )
            resp.raise_for_status()
            data = resp.json()
            members = data.get("members", [])

        # Test house-vote endpoint (the one that was broken)
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp2 = await client.get(
                "https://api.congress.gov/v3/house-vote/119/1",
                params={"api_key": api_key, "format": "json", "limit": 1},
            )
            resp2.raise_for_status()
            votes_data = resp2.json()
            votes = votes_data.get("houseRollCallVotes", [])

        elapsed = round(time.monotonic() - start, 3)
        return {
            "status": "ok",
            "latency_s": elapsed,
            "member_endpoint": "ok" if members else "empty",
            "house_vote_endpoint": "ok" if votes else "empty",
        }
    except httpx.HTTPStatusError as exc:
        elapsed = round(time.monotonic() - start, 3)
        return {
            "status": "error",
            "latency_s": elapsed,
            "error": f"HTTP {exc.response.status_code}",
        }
    except Exception as exc:
        elapsed = round(time.monotonic() - start, 3)
        return {"status": "error", "latency_s": elapsed, "error": str(exc)}


async def _check_fec_api() -> dict:
    """Verify FEC API is reachable, key is valid, and rate limiting works."""
    start = time.monotonic()
    try:
        from app.services.config_service import get_config_value

        async with async_session() as session:
            api_key = await get_config_value(session, "FEC_API_KEY")

        if not api_key:
            return {"status": "skipped", "reason": "No FEC_API_KEY configured"}

        # Test candidate endpoint with a known ID (Fetterman)
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://api.open.fec.gov/v1/candidate/S2PA00661/totals/",
                params={"api_key": api_key, "cycle": 2024},
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])

        elapsed = round(time.monotonic() - start, 3)
        return {
            "status": "ok",
            "latency_s": elapsed,
            "candidate_totals_endpoint": "ok" if results else "empty",
        }
    except httpx.HTTPStatusError as exc:
        elapsed = round(time.monotonic() - start, 3)
        code = exc.response.status_code
        if code == 429:
            return {
                "status": "warning",
                "latency_s": elapsed,
                "error": "Rate limited (429) — currently throttled by FEC",
            }
        return {
            "status": "error",
            "latency_s": elapsed,
            "error": f"HTTP {code}",
        }
    except Exception as exc:
        elapsed = round(time.monotonic() - start, 3)
        return {"status": "error", "latency_s": elapsed, "error": str(exc)}


async def _check_senate_efd() -> dict:
    """Verify Senate eFD system is reachable (DNS + HTTP)."""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(
                "https://efts.senate.gov/LATEST/search-results",
                params={"type": "ptr", "limit": "1"},
            )
            # Accept any HTTP response as "reachable"
            status_code = resp.status_code

        elapsed = round(time.monotonic() - start, 3)
        if status_code == 200:
            return {"status": "ok", "latency_s": elapsed}
        else:
            return {
                "status": "warning",
                "latency_s": elapsed,
                "http_status": status_code,
            }
    except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as exc:
        elapsed = round(time.monotonic() - start, 3)
        return {
            "status": "error",
            "latency_s": elapsed,
            "error": f"Unreachable: {exc}",
        }
    except Exception as exc:
        elapsed = round(time.monotonic() - start, 3)
        return {"status": "error", "latency_s": elapsed, "error": str(exc)}


async def _check_scheduler() -> dict:
    """Verify scheduler is running and all jobs are registered."""
    try:
        from app.services.scheduler import get_scheduler_status, JOB_REGISTRY

        status = get_scheduler_status()
        if not status.get("scheduler_running"):
            return {"status": "error", "error": "Scheduler not running"}

        registered = {j["id"] for j in status.get("jobs", [])}
        expected = set(JOB_REGISTRY.keys())
        missing = expected - registered

        if missing:
            return {
                "status": "error",
                "error": f"Missing jobs: {', '.join(sorted(missing))}",
                "registered_jobs": len(registered),
                "expected_jobs": len(expected),
            }

        # Check for stalled jobs (next_run_time is None = paused)
        paused = [j["id"] for j in status["jobs"] if j.get("status") == "paused"]

        return {
            "status": "ok" if not paused else "warning",
            "registered_jobs": len(registered),
            "paused_jobs": paused if paused else None,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


async def _check_recent_job_health() -> dict:
    """Check if recent scheduler jobs completed without errors."""
    try:
        from sqlalchemy import select, desc
        from app.models import IngestionJob

        async with async_session() as session:
            result = await session.execute(
                select(IngestionJob)
                .order_by(desc(IngestionJob.created_at))
                .limit(20)
            )
            jobs = result.scalars().all()

        if not jobs:
            return {"status": "warning", "reason": "No job history found"}

        failed = []
        for job in jobs:
            if job.status == "failed":
                failed.append({
                    "job_type": job.job_type,
                    "error": (job.errors[0].get("message", "") if job.errors else ""),
                    "at": job.created_at.isoformat() if job.created_at else "?",
                })

        return {
            "status": "ok" if not failed else "warning",
            "recent_jobs_checked": len(jobs),
            "failed_jobs": failed if failed else None,
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


async def run_deep_health_check() -> dict:
    """Run all health checks concurrently and return aggregated results."""
    start = time.monotonic()

    checks = await asyncio.gather(
        _check_database(),
        _check_congress_api(),
        _check_fec_api(),
        _check_senate_efd(),
        _check_scheduler(),
        _check_recent_job_health(),
        return_exceptions=True,
    )

    labels = [
        "database",
        "congress_api",
        "fec_api",
        "senate_efd",
        "scheduler",
        "recent_jobs",
    ]

    results = {}
    for label, check in zip(labels, checks):
        if isinstance(check, Exception):
            results[label] = {"status": "error", "error": str(check)}
        else:
            results[label] = check

    # Determine overall status
    statuses = [r.get("status", "error") for r in results.values()]
    if any(s == "error" for s in statuses):
        overall = "unhealthy"
    elif any(s == "warning" for s in statuses):
        overall = "degraded"
    else:
        overall = "healthy"

    total_elapsed = round(time.monotonic() - start, 3)

    return {
        "status": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_latency_s": total_elapsed,
        "checks": results,
    }
