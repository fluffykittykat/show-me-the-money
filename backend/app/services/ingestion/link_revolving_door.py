"""
Link revolving door lobbyists to the officials they used to work for.

Scans all entities with is_revolving_door=true, parses their covered_position
text for official names, and creates revolving_door_lobbyist relationships
pointing from the lobbyist TO the official.
"""

import logging
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.database import async_session
from app.models import Entity, IngestionJob, Relationship

logger = logging.getLogger("link_revolving_door")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)


def _extract_official_names(covered_position: str) -> list[str]:
    """Extract official names from covered_position text.

    Examples:
    - "Chief of Staff, Senator Tillis" -> ["Tillis"]
    - "Legislative Director, Office of Sen. Warren" -> ["Warren"]
    - "Staff Director, Senate Banking Committee" -> [] (committee, not person)
    - "Senior Counsel, Rep. Duffy" -> ["Duffy"]
    """
    names = set()
    # Pattern: Senator/Sen./Rep./Representative + LastName
    for match in re.finditer(
        r'(?:Senator|Sen\.|Rep\.|Representative)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
        covered_position
    ):
        names.add(match.group(1).strip())

    # Pattern: "Office of Sen. X" or "Office of Rep. X"
    for match in re.finditer(
        r'Office of (?:Sen\.|Rep\.)\s+([A-Z][a-z]+)',
        covered_position
    ):
        names.add(match.group(1).strip())

    return list(names)


def _extract_committee_names(covered_position: str) -> list[str]:
    """Extract committee names from covered_position text."""
    committees = set()
    # Pattern: "Senate/House Committee on X" or "Senate/House X Committee"
    for match in re.finditer(
        r'(?:Senate|House)\s+(?:Committee\s+on\s+)?([A-Z][^;,]+?)(?:\s*[-;,]|\s+Subcom|\s+Committee|$)',
        covered_position
    ):
        name = match.group(1).strip().rstrip(".")
        if len(name) > 5:
            committees.add(name)

    # Pattern: "Senate Banking" etc (shortened names)
    for match in re.finditer(
        r'Senate\s+(Banking|Finance|Judiciary|Armed Services|Appropriations|Intelligence|Commerce|Foreign Relations)',
        covered_position
    ):
        committees.add(match.group(1))

    return list(committees)


async def run_link_revolving_door() -> uuid.UUID:
    """Link revolving door lobbyists to officials they used to work for."""

    # Create job
    async with async_session() as session:
        async with session.begin():
            job = IngestionJob(
                job_type="link_revolving_door",
                status="in_progress",
                started_at=datetime.now(timezone.utc),
            )
            session.add(job)
            await session.flush()
            job_id = job.id

    # Load all revolving door lobbyists
    async with async_session() as session:
        result = await session.execute(
            select(Entity)
            .where(Entity.entity_type == "person")
            .where(Entity.metadata_["is_revolving_door"].astext == "true")
        )
        lobbyists = result.scalars().all()

    # Load all officials for matching
    async with async_session() as session:
        result = await session.execute(
            select(Entity)
            .where(Entity.entity_type == "person")
            .where(Entity.metadata_.has_key("bioguide_id"))
        )
        officials = result.scalars().all()

    # Build lookup: last name -> list of officials
    name_lookup: dict[str, list[Entity]] = {}
    for official in officials:
        # Extract last name from "LastName, FirstName M." format
        name = official.name
        last_name = name.split(",")[0].strip() if "," in name else name.split()[-1]
        last_name_lower = last_name.lower()
        if last_name_lower not in name_lookup:
            name_lookup[last_name_lower] = []
        name_lookup[last_name_lower].append(official)

    total = len(lobbyists)
    logger.info("Processing %d revolving door lobbyists against %d officials", total, len(officials))

    # Update job total
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob).where(IngestionJob.id == job_id)
                .values(total=total, progress=0)
            )

    linked = 0
    processed = 0

    for lobbyist in lobbyists:
        meta = lobbyist.metadata_ or {}
        covered_position = meta.get("covered_position", "")
        if not covered_position:
            processed += 1
            continue

        # Extract official names from the covered_position text
        official_names = _extract_official_names(covered_position)

        for name in official_names:
            name_lower = name.lower()
            matched_officials = name_lookup.get(name_lower, [])

            for official in matched_officials:
                # Create revolving_door_lobbyist: lobbyist -> official
                async with async_session() as session:
                    async with session.begin():
                        existing = (await session.execute(
                            select(Relationship).where(
                                Relationship.from_entity_id == lobbyist.id,
                                Relationship.to_entity_id == official.id,
                                Relationship.relationship_type == "revolving_door_lobbyist",
                            ).limit(1)
                        )).scalar_one_or_none()

                        if not existing:
                            session.add(Relationship(
                                from_entity_id=lobbyist.id,
                                to_entity_id=official.id,
                                relationship_type="revolving_door_lobbyist",
                                source_label="LDA Senate",
                                metadata_={
                                    "former_position": covered_position[:500],
                                    "current_employer": meta.get("current_employer", ""),
                                    "lobbies_committee": ", ".join(_extract_committee_names(covered_position)),
                                },
                            ))
                            linked += 1
                            logger.info(
                                "Linked: %s (was: %s) -> %s",
                                lobbyist.name, covered_position[:60], official.name,
                            )

        processed += 1
        if processed % 100 == 0:
            logger.info("Progress: %d/%d processed, %d linked", processed, total, linked)
            async with async_session() as session:
                async with session.begin():
                    await session.execute(
                        update(IngestionJob).where(IngestionJob.id == job_id)
                        .values(progress=processed)
                    )

    # Complete
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob).where(IngestionJob.id == job_id)
                .values(
                    status="completed",
                    progress=processed,
                    total=total,
                    completed_at=datetime.now(timezone.utc),
                    metadata_={"linked": linked},
                )
            )

    logger.info("Revolving door linking complete: %d linked from %d lobbyists", linked, total)
    return job_id
