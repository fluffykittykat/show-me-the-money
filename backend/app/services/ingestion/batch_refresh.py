"""
Batch refresh — run the refresh pipeline for all politicians missing donor data.

Iterates through all person entities with bioguide_id but no donated_to
relationships, and triggers the refresh endpoint for each.
"""

import asyncio
import logging

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Entity, Relationship

logger = logging.getLogger(__name__)


async def run_batch_refresh(max_concurrent: int = 1) -> str:
    """Refresh all politicians missing donor data."""
    logger.info("[batch_refresh] Starting batch refresh for politicians missing donors")

    async with async_session() as session:
        # Find politicians with bioguide_id but no donors
        subq = (
            select(Relationship.to_entity_id)
            .where(Relationship.relationship_type == "donated_to")
            .distinct()
        )
        result = await session.execute(
            select(Entity.slug, Entity.name).where(
                Entity.entity_type == "person",
                Entity.metadata_["bioguide_id"].astext.isnot(None),
                Entity.id.notin_(subq),
            ).order_by(Entity.name)
        )
        missing = list(result.all())

    logger.info("[batch_refresh] Found %d politicians missing donor data", len(missing))

    stats = {"total": len(missing), "success": 0, "failed": 0, "skipped": 0}

    for idx, (slug, name) in enumerate(missing, 1):
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(f"http://localhost:8000/refresh/{slug}")
                if resp.status_code == 200:
                    data = resp.json()
                    actions = data.get("actions", [])
                    donors_action = [a for a in actions if "donor" in a.lower()]
                    logger.info(
                        "[batch_refresh] [%d/%d] %s — %s",
                        idx, len(missing), name,
                        donors_action[0] if donors_action else "refreshed",
                    )
                    stats["success"] += 1
                else:
                    logger.warning(
                        "[batch_refresh] [%d/%d] %s — HTTP %d",
                        idx, len(missing), name, resp.status_code,
                    )
                    stats["failed"] += 1
        except Exception as exc:
            logger.warning(
                "[batch_refresh] [%d/%d] %s — error: %s",
                idx, len(missing), name, exc,
            )
            stats["failed"] += 1

        # Small delay between refreshes to avoid hammering APIs
        await asyncio.sleep(2)

    summary = (
        f"Batch refresh complete: {stats['success']}/{stats['total']} succeeded, "
        f"{stats['failed']} failed"
    )
    logger.info("[batch_refresh] %s", summary)
    return summary
