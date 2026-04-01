"""Ingest the full money trail through party committees.

Traces: Big Donor -> Party Committee -> Official -> Bills

Phase 1: Create party committee entities, fetch their top 50 donors, create relationships.
Phase 2: Verify party committee -> official relationships already exist.
Phase 3: Create "money_flows_through" relationships linking original donors to officials
         through party committees.

Rate-limited to 3 seconds between FEC API calls.
"""

import asyncio
import logging
import re
import uuid
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import aliased

from app.database import async_session
from app.models import Entity, IngestionJob, Relationship

logger = logging.getLogger("ingest_party_money")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

FEC_BASE_URL = "https://api.open.fec.gov/v1"
FEC_API_KEY = "Fs8xrx9MhdRYufNFFUmoi1NBg2Xa5xIfrgezy8sb"
DELAY_BETWEEN_API_CALLS = 3  # seconds
DONORS_PER_COMMITTEE = 50
TIMEOUT = 30.0

# Major party committees
PARTY_COMMITTEES = [
    {
        "fec_id": "C00042366",
        "name": "Democratic Senatorial Campaign Committee",
        "short_name": "DSCC",
        "slug": "dscc-national",
        "party": "Democratic",
        "chamber": "Senate",
    },
    {
        "fec_id": "C00075820",
        "name": "National Republican Senatorial Committee",
        "short_name": "NRSC",
        "slug": "nrsc-national",
        "party": "Republican",
        "chamber": "Senate",
    },
    {
        "fec_id": "C00000935",
        "name": "Democratic Congressional Campaign Committee",
        "short_name": "DCCC",
        "slug": "dccc-national",
        "party": "Democratic",
        "chamber": "House",
    },
    {
        "fec_id": "C00003418",
        "name": "National Republican Congressional Committee",
        "short_name": "NRCC",
        "slug": "nrcc-national",
        "party": "Republican",
        "chamber": "House",
    },
]


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


def _parse_date(date_str: str | None) -> date | None:
    """Parse an FEC date string like '2022-03-15T00:00:00' into a date."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
    except (ValueError, AttributeError):
        return None


async def _fec_get(url: str, params: dict) -> dict:
    """Make a rate-limited GET request to the FEC API."""
    params["api_key"] = FEC_API_KEY
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


async def _fetch_schedule_a_donors(committee_id: str, per_page: int = 50) -> list[dict]:
    """Fetch top donors from FEC Schedule A for a committee."""
    url = f"{FEC_BASE_URL}/schedules/schedule_a/"
    params = {
        "committee_id": committee_id,
        "per_page": per_page,
        "sort": "-contribution_receipt_amount",
        "min_amount": 10000,
    }

    logger.info("Fetching Schedule A donors for committee %s", committee_id)
    all_results = []

    # Up to 3 pages of results
    for page_num in range(1, 4):
        logger.info("  Fetching page %d...", page_num)
        try:
            data = await _fec_get(url, dict(params))
            results = data.get("results", [])
            all_results.extend(results)

            if not results:
                break

            pagination = data.get("pagination", {})
            last_indexes = pagination.get("last_indexes")
            if not last_indexes:
                break

            # Apply cursor params for next page
            for key, value in last_indexes.items():
                params[key] = value

        except Exception as e:
            logger.warning("Error fetching page %d for %s: %s", page_num, committee_id, e)
            break

        await asyncio.sleep(DELAY_BETWEEN_API_CALLS)

    logger.info("  Got %d total donors for %s", len(all_results), committee_id)
    return all_results[:per_page]  # cap at requested amount


def _classify_donor(name: str) -> str:
    """Classify a donor name as pac, company, or person."""
    name_upper = name.upper()
    pac_keywords = [
        "PAC", "FUND", "VICTORY", "COMMITTEE", "DSCC", "DCCC", "NRSC", "NRCC",
        "EMILY", "ACTION", "SENATE", "HOUSE", "POLITICAL", "CAMPAIGN",
    ]
    company_keywords = [
        "LLC", "INC", "CORP", "LTD", "LP", "PARTNERS", "HOLDINGS",
        "GROUP", "CAPITAL", "ASSOCIATES", "MANAGEMENT", "BANK",
        "INSURANCE", "INDUSTRIES", "ENTERPRISES",
    ]
    if any(kw in name_upper for kw in pac_keywords):
        return "pac"
    if any(kw in name_upper for kw in company_keywords):
        return "company"
    return "person"


# ── Phase 1: Ingest party committee entities and their top donors ──────────


async def _ensure_committee_entity(committee_info: dict) -> uuid.UUID:
    """Create or find the entity for a party committee. Returns entity ID."""
    async with async_session() as session:
        async with session.begin():
            existing = (await session.execute(
                select(Entity).where(Entity.slug == committee_info["slug"])
            )).scalar_one_or_none()

            if existing:
                logger.info("Committee entity already exists: %s", committee_info["slug"])
                return existing.id

            entity = Entity(
                slug=committee_info["slug"],
                entity_type="pac",
                name=committee_info["name"],
                metadata_=_ascii_safe({
                    "fec_committee_id": committee_info["fec_id"],
                    "short_name": committee_info["short_name"],
                    "party": committee_info["party"],
                    "chamber": committee_info["chamber"],
                    "committee_type": "party_committee",
                }),
            )
            session.add(entity)
            await session.flush()
            logger.info("Created committee entity: %s (id=%s)", committee_info["slug"], entity.id)
            return entity.id


async def _create_committee_donors(
    committee_id: uuid.UUID,
    committee_name: str,
    donors: list[dict],
) -> int:
    """Create donor entities and donated_to relationships for a party committee."""
    created = 0
    async with async_session() as session:
        async with session.begin():
            for donor_data in donors:
                donor_name = _ascii_safe(donor_data.get("contributor_name", "") or "")
                if not donor_name or len(donor_name) < 2:
                    continue
                donor_slug = _slugify(donor_name)
                if not donor_slug:
                    continue

                amount = (
                    donor_data.get("contribution_receipt_amount", 0) or 0
                )

                donor_type = _classify_donor(donor_name)

                # Find or create donor entity
                donor_ent = (await session.execute(
                    select(Entity).where(Entity.slug == donor_slug)
                )).scalar_one_or_none()

                if not donor_ent:
                    donor_ent = Entity(
                        slug=donor_slug,
                        entity_type=donor_type,
                        name=donor_name,
                        metadata_=_ascii_safe({
                            "donor_type": donor_type,
                            "source": "fec_schedule_a",
                        }),
                    )
                    session.add(donor_ent)
                    await session.flush()

                # Check for existing relationship
                existing_rel = (await session.execute(
                    select(Relationship).where(
                        Relationship.from_entity_id == donor_ent.id,
                        Relationship.to_entity_id == committee_id,
                        Relationship.relationship_type == "donated_to",
                    ).limit(1)
                )).scalar_one_or_none()

                if not existing_rel:
                    amount_cents = int(float(amount) * 100) if amount else 0
                    receipt_date = _parse_date(
                        donor_data.get("contribution_receipt_date")
                    )
                    session.add(Relationship(
                        from_entity_id=donor_ent.id,
                        to_entity_id=committee_id,
                        relationship_type="donated_to",
                        amount_usd=amount_cents,
                        date_start=receipt_date,
                        source_label="FEC",
                        metadata_=_ascii_safe({
                            "committee_target": committee_name,
                            "fec_transaction_id": donor_data.get("transaction_id", ""),
                        }),
                    ))
                    created += 1

    return created


async def _run_phase1() -> dict:
    """Phase 1: Ingest party committee entities and their top donors."""
    logger.info("=== PHASE 1: Ingest party committees and their donors ===")
    results = {}

    for committee_info in PARTY_COMMITTEES:
        short = committee_info["short_name"]
        logger.info("Processing committee: %s (%s)", short, committee_info["fec_id"])

        # Create/find entity
        committee_entity_id = await _ensure_committee_entity(committee_info)

        # Fetch top donors from FEC
        donors = await _fetch_schedule_a_donors(
            committee_info["fec_id"], per_page=DONORS_PER_COMMITTEE
        )
        await asyncio.sleep(DELAY_BETWEEN_API_CALLS)

        # Create donor entities and relationships
        created = await _create_committee_donors(
            committee_entity_id, committee_info["name"], donors
        )

        results[short] = {
            "entity_id": str(committee_entity_id),
            "donors_fetched": len(donors),
            "relationships_created": created,
        }
        logger.info(
            "  %s: %d donors fetched, %d relationships created",
            short, len(donors), created,
        )

    return results


# ── Phase 2: Verify party committee → official relationships ───────────────


async def _run_phase2() -> dict:
    """Phase 2: Verify that party committee → official donated_to relationships exist."""
    logger.info("=== PHASE 2: Verify committee → official relationships ===")

    stats = {}
    async with async_session() as session:
        for committee_info in PARTY_COMMITTEES:
            short = committee_info["short_name"]

            # Find committee entity
            committee_ent = (await session.execute(
                select(Entity).where(Entity.slug == committee_info["slug"])
            )).scalar_one_or_none()

            if not committee_ent:
                logger.warning("Committee entity not found: %s", committee_info["slug"])
                stats[short] = {"status": "entity_not_found"}
                continue

            # Count outgoing donated_to relationships from this committee
            outgoing = (await session.execute(
                select(Relationship).where(
                    Relationship.from_entity_id == committee_ent.id,
                    Relationship.relationship_type == "donated_to",
                )
            )).scalars().all()

            # Count how many go to officials (persons with bioguide_id)
            official_count = 0
            for rel in outgoing:
                target = (await session.execute(
                    select(Entity).where(Entity.id == rel.to_entity_id)
                )).scalar_one_or_none()
                if target and target.entity_type == "person":
                    meta = target.metadata_ or {}
                    if meta.get("bioguide_id"):
                        official_count += 1

            stats[short] = {
                "total_outgoing_donations": len(outgoing),
                "donations_to_officials": official_count,
            }
            logger.info(
                "  %s: %d outgoing donations, %d to officials",
                short, len(outgoing), official_count,
            )

    return stats


# ── Phase 3: Create money_flows_through relationships ──────────────────────


async def _run_phase3() -> dict:
    """Phase 3: Create money_flows_through relationships.

    For each chain: Big Donor → Party Committee → Official,
    create a relationship from donor to official with via metadata.
    """
    logger.info("=== PHASE 3: Create money_flows_through relationships ===")

    total_created = 0
    total_skipped = 0

    async with async_session() as session:
        for committee_info in PARTY_COMMITTEES:
            short = committee_info["short_name"]
            logger.info("Processing money trails through %s", short)

            # Find committee entity
            committee_ent = (await session.execute(
                select(Entity).where(Entity.slug == committee_info["slug"])
            )).scalar_one_or_none()

            if not committee_ent:
                logger.warning("Committee entity not found: %s", committee_info["slug"])
                continue

            # Get all donors TO this committee (incoming donated_to)
            incoming_rels = (await session.execute(
                select(Relationship).where(
                    Relationship.to_entity_id == committee_ent.id,
                    Relationship.relationship_type == "donated_to",
                )
            )).scalars().all()

            # Get all officials this committee donated TO (outgoing donated_to)
            outgoing_rels = (await session.execute(
                select(Relationship).where(
                    Relationship.from_entity_id == committee_ent.id,
                    Relationship.relationship_type == "donated_to",
                )
            )).scalars().all()

            # Filter outgoing to only officials
            official_rels = []
            for rel in outgoing_rels:
                target = (await session.execute(
                    select(Entity).where(Entity.id == rel.to_entity_id)
                )).scalar_one_or_none()
                if target and target.entity_type == "person":
                    meta = target.metadata_ or {}
                    if meta.get("bioguide_id"):
                        official_rels.append((rel, target))

            if not incoming_rels or not official_rels:
                logger.info(
                    "  %s: %d incoming donors, %d official recipients — skipping",
                    short, len(incoming_rels), len(official_rels),
                )
                continue

            logger.info(
                "  %s: creating chains for %d donors × %d officials",
                short, len(incoming_rels), len(official_rels),
            )

            # Build donor name cache
            donor_cache: dict[uuid.UUID, Entity] = {}
            for rel in incoming_rels:
                if rel.from_entity_id not in donor_cache:
                    donor_ent = (await session.execute(
                        select(Entity).where(Entity.id == rel.from_entity_id)
                    )).scalar_one_or_none()
                    if donor_ent:
                        donor_cache[rel.from_entity_id] = donor_ent

            # Create money_flows_through for each donor → official pair
            for donor_rel in incoming_rels:
                donor_ent = donor_cache.get(donor_rel.from_entity_id)
                if not donor_ent:
                    continue

                for official_rel, official_ent in official_rels:
                    # Check if relationship already exists
                    async with async_session() as check_session:
                        existing = (await check_session.execute(
                            select(Relationship).where(
                                Relationship.from_entity_id == donor_ent.id,
                                Relationship.to_entity_id == official_ent.id,
                                Relationship.relationship_type == "money_flows_through",
                            ).limit(1)
                        )).scalar_one_or_none()

                    if existing:
                        total_skipped += 1
                        continue

                    # Create the money_flows_through relationship
                    donor_amount = donor_rel.amount_usd or 0
                    distributed_amount = official_rel.amount_usd or 0

                    metadata = _ascii_safe({
                        "via": short,
                        "via_entity_id": str(committee_ent.id),
                        "original_amount": donor_amount,
                        "distributed_amount": distributed_amount,
                        "chain": [
                            donor_ent.name,
                            committee_info["name"],
                            official_ent.name,
                        ],
                    })

                    async with async_session() as write_session:
                        async with write_session.begin():
                            write_session.add(Relationship(
                                from_entity_id=donor_ent.id,
                                to_entity_id=official_ent.id,
                                relationship_type="money_flows_through",
                                amount_usd=donor_amount,
                                source_label="FEC (derived)",
                                metadata_=metadata,
                            ))

                    total_created += 1

            logger.info(
                "  %s: %d money_flows_through created, %d skipped (already exist)",
                short, total_created, total_skipped,
            )

    return {
        "total_created": total_created,
        "total_skipped": total_skipped,
    }


# ── Main entry point ──────────────────────────────────────────────────────


async def run_party_money_ingestion() -> str:
    """Main entry point: full party committee money trail ingestion."""

    # Create ingestion job
    job_id: uuid.UUID
    async with async_session() as session:
        async with session.begin():
            job = IngestionJob(
                job_type="party_money_trail",
                status="in_progress",
                total=3,  # 3 phases
                progress=0,
                started_at=datetime.now(timezone.utc),
                metadata_={"phases": ["committee_donors", "verify_links", "money_flows"]},
            )
            session.add(job)
            await session.flush()
            job_id = job.id
    logger.info("Created ingestion job %s", job_id)

    errors: list[dict] = []

    # Phase 1: Ingest party committees and their donors
    try:
        phase1_results = await _run_phase1()
    except Exception as e:
        logger.error("Phase 1 error: %s", e)
        phase1_results = {"error": str(e)}
        errors.append({"phase": 1, "error": str(e)})

    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job_id)
                .values(progress=1, errors=errors)
            )

    # Phase 2: Verify committee → official links
    try:
        phase2_results = await _run_phase2()
    except Exception as e:
        logger.error("Phase 2 error: %s", e)
        phase2_results = {"error": str(e)}
        errors.append({"phase": 2, "error": str(e)})

    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job_id)
                .values(progress=2, errors=errors)
            )

    # Phase 3: Create money_flows_through relationships
    try:
        phase3_results = await _run_phase3()
    except Exception as e:
        logger.error("Phase 3 error: %s", e)
        phase3_results = {"error": str(e)}
        errors.append({"phase": 3, "error": str(e)})

    # Mark job complete
    final_metadata = {
        "phase1_committee_donors": phase1_results,
        "phase2_verify_links": phase2_results,
        "phase3_money_flows": phase3_results,
        "errors_count": len(errors),
    }

    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job_id)
                .values(
                    status="completed",
                    progress=3,
                    completed_at=datetime.now(timezone.utc),
                    errors=errors,
                    metadata_=final_metadata,
                )
            )

    summary = (
        f"Party money trail ingestion complete. "
        f"Phase 1: {phase1_results}. "
        f"Phase 2: {phase2_results}. "
        f"Phase 3: {phase3_results}. "
        f"Errors: {len(errors)}"
    )
    logger.info(summary)
    return summary
