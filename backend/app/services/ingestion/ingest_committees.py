"""Ingest congressional committee assignments from unitedstates/congress-legislators data.

Fetches committee definitions and membership from the GitHub-hosted YAML files
maintained by the @unitedstates project. Creates committee entities and
committee_member relationships linking officials to their committees.

Data sources:
  - committees-current.yaml: committee definitions (name, type, thomas_id)
  - committee-membership-current.yaml: membership keyed by thomas_id with bioguide IDs
"""

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone

import httpx
import yaml
from sqlalchemy import select, update

from app.database import async_session
from app.models import Entity, IngestionJob, Relationship

logger = logging.getLogger("ingest_committees")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

COMMITTEES_YAML_URL = (
    "https://raw.githubusercontent.com/unitedstates/congress-legislators/"
    "refs/heads/main/committees-current.yaml"
)
MEMBERSHIP_YAML_URL = (
    "https://raw.githubusercontent.com/unitedstates/congress-legislators/"
    "refs/heads/main/committee-membership-current.yaml"
)

RATE_LIMIT_SECONDS = 0.6
TIMEOUT = 30.0


def _slugify(name: str) -> str:
    """Convert a name to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _ascii_safe(obj):
    """Recursively strip non-ASCII characters for SQL_ASCII database."""
    if isinstance(obj, str):
        return obj.encode("ascii", "replace").decode("ascii")
    if isinstance(obj, dict):
        return {k: _ascii_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ascii_safe(i) for i in obj]
    return obj


async def _fetch_yaml(url: str) -> dict | list:
    """Fetch and parse a YAML file from a URL."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(url)
        response.raise_for_status()
        return yaml.safe_load(response.text)


def _build_committee_lookup(committees_yaml: list) -> dict:
    """Build a lookup dict from thomas_id -> committee info.

    The committees YAML is a list of committee objects. Each has a thomas_id,
    name, and type (house/senate/joint). Subcommittees are nested and have
    their own thomas_id values.

    Returns a flat dict mapping thomas_id (e.g. "SSAF", "HSAG15") to:
      {"name": ..., "chamber": ..., "thomas_id": ..., "parent_name": ...}
    """
    lookup = {}
    for committee in committees_yaml:
        thomas_id = committee.get("thomas_id", "")
        name = committee.get("name", "")
        chamber = committee.get("type", "")  # "house", "senate", "joint"

        if not thomas_id:
            continue

        lookup[thomas_id] = {
            "name": name,
            "chamber": chamber,
            "thomas_id": thomas_id,
            "parent_name": None,
            "url": committee.get("url", ""),
        }

        # Add subcommittees
        for sub in committee.get("subcommittees", []):
            sub_thomas_id = thomas_id + sub.get("thomas_id", "")
            sub_name = sub.get("name", "")
            lookup[sub_thomas_id] = {
                "name": sub_name,
                "chamber": chamber,
                "thomas_id": sub_thomas_id,
                "parent_name": name,
                "url": "",
            }

    return lookup


async def _update_job_progress(
    job_id: uuid.UUID, progress: int, total: int, errors: list
) -> None:
    """Update the ingestion job progress in the database."""
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job_id)
                .values(
                    progress=progress,
                    total=total,
                    errors=errors,
                )
            )


async def _get_officials_by_bioguide(session) -> dict:
    """Load all person entities that have a bioguide_id in their metadata.

    Returns a dict mapping bioguide_id -> (entity_id, entity_name).
    """
    result = await session.execute(
        select(Entity).where(Entity.entity_type == "person")
    )
    officials = {}
    for entity in result.scalars().all():
        meta = entity.metadata_ or {}
        bioguide = meta.get("bioguide_id", "")
        if bioguide:
            officials[bioguide] = (entity.id, entity.name)
    return officials


async def _upsert_committee_entity(
    session, slug: str, name: str, metadata: dict
) -> uuid.UUID:
    """Create or update a committee entity. Returns the entity ID."""
    safe_name = _ascii_safe(name)
    safe_metadata = _ascii_safe(metadata)
    chamber = metadata.get("chamber", "")
    parent = metadata.get("parent_name")

    if parent:
        summary = f"Subcommittee of {parent} ({chamber.title()})"
    else:
        summary = f"{chamber.title()} committee" if chamber else "Congressional committee"
    safe_summary = _ascii_safe(summary)

    existing = (
        await session.execute(select(Entity).where(Entity.slug == slug))
    ).scalar_one_or_none()

    if existing:
        existing.name = safe_name
        existing.summary = safe_summary
        existing.metadata_ = safe_metadata
        await session.flush()
        return existing.id
    else:
        entity = Entity(
            slug=slug,
            entity_type="committee",
            name=safe_name,
            summary=safe_summary,
            metadata_=safe_metadata,
        )
        session.add(entity)
        await session.flush()
        return entity.id


async def _create_membership_relationship(
    session,
    official_id: uuid.UUID,
    committee_id: uuid.UUID,
    member_info: dict,
) -> bool:
    """Create a committee_member relationship if it doesn't exist.

    Returns True if a new relationship was created, False if it already existed.
    """
    existing = (
        await session.execute(
            select(Relationship).where(
                Relationship.from_entity_id == official_id,
                Relationship.to_entity_id == committee_id,
                Relationship.relationship_type == "committee_member",
            ).limit(1)
        )
    ).scalar_one_or_none()

    if existing:
        return False

    metadata = {}
    if member_info.get("title"):
        metadata["title"] = member_info["title"]
    if member_info.get("party"):
        metadata["party"] = member_info["party"]
    if member_info.get("rank"):
        metadata["rank"] = member_info["rank"]

    session.add(
        Relationship(
            from_entity_id=official_id,
            to_entity_id=committee_id,
            relationship_type="committee_member",
            source_label="unitedstates/congress-legislators",
            source_url="https://github.com/unitedstates/congress-legislators",
            metadata_=_ascii_safe(metadata) if metadata else {},
        )
    )
    return True


async def run_committee_ingestion() -> uuid.UUID:
    """Run committee assignment ingestion.

    Fetches committee definitions and membership data from the
    unitedstates/congress-legislators GitHub repository, creates committee
    entities, and links officials to their committees.

    Returns the IngestionJob ID.
    """
    # Create ingestion job
    job_id: uuid.UUID
    async with async_session() as session:
        async with session.begin():
            job = IngestionJob(
                job_type="committee_assignments",
                status="in_progress",
                started_at=datetime.now(timezone.utc),
                metadata_={},
            )
            session.add(job)
            await session.flush()
            job_id = job.id

    logger.info("Created ingestion job %s", job_id)
    errors: list[dict] = []

    try:
        # Step 1: Fetch committee definitions
        logger.info("Fetching committee definitions...")
        committees_yaml = await _fetch_yaml(COMMITTEES_YAML_URL)
        await asyncio.sleep(RATE_LIMIT_SECONDS)

        # Step 2: Fetch membership data
        logger.info("Fetching committee membership data...")
        membership_yaml = await _fetch_yaml(MEMBERSHIP_YAML_URL)

        # Step 3: Build committee lookup
        committee_lookup = _build_committee_lookup(committees_yaml)
        logger.info(
            "Loaded %d committees/subcommittees, %d membership entries",
            len(committee_lookup),
            len(membership_yaml),
        )

        # Step 4: Load existing officials by bioguide ID
        async with async_session() as session:
            officials = await _get_officials_by_bioguide(session)
        logger.info("Found %d officials with bioguide IDs in database", len(officials))

        # Count total work items (committees with membership data)
        total_committees = len(membership_yaml)
        await _update_job_progress(job_id, 0, total_committees, errors)

        committees_created = 0
        committees_updated = 0
        relationships_created = 0
        members_not_found = 0
        processed = 0

        # Step 5: Process each committee's membership
        for thomas_id, members in membership_yaml.items():
            processed += 1

            # Look up committee info
            committee_info = committee_lookup.get(thomas_id)
            if not committee_info:
                # Membership entry with no matching committee definition -- skip
                logger.debug("No committee definition for %s, skipping", thomas_id)
                continue

            committee_name = committee_info["name"]
            chamber = committee_info["chamber"]
            parent_name = committee_info.get("parent_name")

            # Build slug: "committee-{chamber}-{slugified-name}"
            if parent_name:
                slug = f"committee-{chamber}-{_slugify(parent_name)}-{_slugify(committee_name)}"
            else:
                slug = f"committee-{chamber}-{_slugify(committee_name)}"

            # Truncate slug if too long (max 200 chars in DB)
            if len(slug) > 195:
                slug = slug[:195]

            committee_metadata = {
                "thomas_id": thomas_id,
                "chamber": chamber,
                "parent_name": parent_name,
                "url": committee_info.get("url", ""),
                "member_count": len(members),
            }

            try:
                async with async_session() as session:
                    async with session.begin():
                        # Check if entity already exists to track created vs updated
                        existing_check = (
                            await session.execute(
                                select(Entity).where(Entity.slug == slug)
                            )
                        ).scalar_one_or_none()

                        committee_entity_id = await _upsert_committee_entity(
                            session, slug, committee_name, committee_metadata
                        )

                        if existing_check:
                            committees_updated += 1
                        else:
                            committees_created += 1

                        # Create membership relationships
                        for member in members:
                            bioguide = member.get("bioguide", "")
                            if not bioguide:
                                continue

                            official_info = officials.get(bioguide)
                            if not official_info:
                                members_not_found += 1
                                continue

                            official_id, official_name = official_info

                            created = await _create_membership_relationship(
                                session,
                                official_id,
                                committee_entity_id,
                                member,
                            )
                            if created:
                                relationships_created += 1

            except Exception as exc:
                error_entry = {
                    "committee": committee_name,
                    "thomas_id": thomas_id,
                    "error": str(exc),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                errors.append(error_entry)
                logger.error(
                    "Error processing committee %s (%s): %s",
                    committee_name, thomas_id, exc,
                )

            # Update progress periodically
            if processed % 20 == 0 or processed == total_committees:
                await _update_job_progress(job_id, processed, total_committees, errors)
                logger.info(
                    "Progress: %d/%d committees | Created: %d | Relationships: %d | Errors: %d",
                    processed, total_committees, committees_created,
                    relationships_created, len(errors),
                )

        # Mark job as completed
        final_metadata = {
            "committees_created": committees_created,
            "committees_updated": committees_updated,
            "relationships_created": relationships_created,
            "members_not_found_in_db": members_not_found,
            "total_committees_processed": processed,
        }

        async with async_session() as session:
            async with session.begin():
                await session.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job_id)
                    .values(
                        status="completed",
                        progress=processed,
                        total=total_committees,
                        completed_at=datetime.now(timezone.utc),
                        errors=errors,
                        metadata_=final_metadata,
                    )
                )

        logger.info(
            "Committee ingestion completed: %d committees (%d created, %d updated), "
            "%d relationships created, %d members not found in DB, %d errors",
            processed, committees_created, committees_updated,
            relationships_created, members_not_found, len(errors),
        )

    except Exception as exc:
        logger.error("Committee ingestion failed: %s", exc)
        async with async_session() as session:
            async with session.begin():
                await session.execute(
                    update(IngestionJob)
                    .where(IngestionJob.id == job_id)
                    .values(
                        status="failed",
                        completed_at=datetime.now(timezone.utc),
                        errors=errors + [{"fatal": str(exc)}],
                    )
                )
        raise

    return job_id
