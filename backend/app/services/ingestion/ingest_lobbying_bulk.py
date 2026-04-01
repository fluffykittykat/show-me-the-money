"""
Bulk ingestion of lobbying filings from the Senate LDA API.

Fetches recent lobbying filings (2024-2025), creates entities for:
- Registrants (lobbying firms) — entity_type="organization"
- Clients (who hired lobbyists) — entity_type="organization"
- Lobbyists with covered_position (revolving door) — entity_type="person"

Creates relationships:
- lobbies_on_behalf_of: firm → client
- revolving_door_lobbyist: lobbyist → firm
- Attempts to match former officials via covered_position

Tracks progress via IngestionJob. Rate limited at ~1s between API calls.

Usage:
    cd /home/mansona/workspace/jerry-maguire/backend
    python -m app.services.ingestion.ingest_lobbying_bulk
"""

import asyncio
import logging
import re
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import DataSource, Entity, IngestionJob, Relationship

logger = logging.getLogger("ingest_lobbying_bulk")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LDA_API_BASE = "https://lda.senate.gov/api/v1"
FILING_YEARS = [2024, 2025]
PAGE_SIZE = 25  # LDA default, max is 25
MAX_FILINGS = 500  # Process at most this many per run
REQUEST_DELAY = 1.0  # seconds between API calls (be polite)
HTTP_TIMEOUT = 30.0
MAX_RETRIES = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert a name to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:195]


def _sanitize_str(s) -> str:
    """Strip non-ASCII characters (DB uses SQL_ASCII encoding)."""
    if not isinstance(s, str):
        return str(s) if s is not None else ""
    return s.encode("ascii", errors="ignore").decode("ascii")


def _sanitize_dict(d) -> dict:
    """Recursively sanitize all string values in a dict."""
    if not isinstance(d, dict):
        return d
    out = {}
    for k, v in d.items():
        if isinstance(v, str):
            out[k] = _sanitize_str(v)
        elif isinstance(v, dict):
            out[k] = _sanitize_dict(v)
        elif isinstance(v, list):
            out[k] = [
                _sanitize_dict(i) if isinstance(i, dict)
                else _sanitize_str(i) if isinstance(i, str)
                else i
                for i in v
            ]
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# LDA API fetching
# ---------------------------------------------------------------------------

async def _fetch_page(
    client: httpx.AsyncClient,
    url: str,
    params: dict | None = None,
) -> dict:
    """Fetch a single page from the LDA API with retry logic."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            logger.warning(
                "LDA API timeout (attempt %d/%d): %s",
                attempt + 1, MAX_RETRIES + 1, url,
            )
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 * (attempt + 1))
        except httpx.HTTPStatusError as exc:
            logger.warning("LDA API HTTP %s: %s", exc.response.status_code, url)
            return {}
        except Exception as exc:
            logger.warning("LDA API error: %s — %s", type(exc).__name__, exc)
            return {}
    return {}


async def fetch_filings_paginated(
    filing_year: int,
    max_filings: int = MAX_FILINGS,
) -> list[dict]:
    """Fetch filings for a given year, paginating up to max_filings."""
    filings: list[dict] = []
    url = f"{LDA_API_BASE}/filings/"
    params = {
        "filing_year": filing_year,
        "format": "json",
        "page_size": PAGE_SIZE,
    }

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        page_num = 0
        next_url: str | None = None

        while len(filings) < max_filings:
            page_num += 1

            if next_url:
                # next_url is a full URL with query params already embedded
                data = await _fetch_page(client, next_url)
            else:
                data = await _fetch_page(client, url, params)

            if not data:
                logger.warning("Empty response on page %d for year %d", page_num, filing_year)
                break

            results = data.get("results", [])
            if not results:
                break

            filings.extend(results)
            logger.info(
                "Year %d page %d: got %d filings (total: %d/%d)",
                filing_year, page_num, len(results), len(filings), max_filings,
            )

            next_url = data.get("next")
            if not next_url:
                break

            # Rate limit: wait between requests
            await asyncio.sleep(REQUEST_DELAY)

    return filings[:max_filings]


# ---------------------------------------------------------------------------
# Entity upsert helpers
# ---------------------------------------------------------------------------

async def _upsert_entity(
    session: AsyncSession,
    slug: str,
    entity_type: str,
    name: str,
    summary: str | None = None,
    metadata: dict | None = None,
) -> Entity:
    """Insert or update an entity by slug. Returns the entity."""
    name = _sanitize_str(name)[:490]
    summary = _sanitize_str(summary) if summary else summary
    slug = slug[:195]
    metadata = _sanitize_dict(metadata) if metadata else metadata

    result = await session.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()

    if entity:
        entity.name = name
        entity.entity_type = entity_type
        if summary:
            entity.summary = summary
        if metadata:
            merged = {**(entity.metadata_ or {}), **metadata}
            entity.metadata_ = _sanitize_dict(merged)
        entity.updated_at = datetime.now(tz=None)
    else:
        entity = Entity(
            slug=slug,
            entity_type=entity_type,
            name=name,
            summary=summary,
            metadata_=metadata or {},
        )
        session.add(entity)

    await session.flush()
    return entity


async def _find_existing_relationship(
    session: AsyncSession,
    from_id,
    to_id,
    rel_type: str,
) -> Relationship | None:
    """Check if a relationship already exists to avoid duplicates."""
    result = await session.execute(
        select(Relationship).where(
            Relationship.from_entity_id == from_id,
            Relationship.to_entity_id == to_id,
            Relationship.relationship_type == rel_type,
        )
    )
    return result.scalar_one_or_none()


async def _create_relationship(
    session: AsyncSession,
    from_id,
    to_id,
    rel_type: str,
    amount_usd: int | None = None,
    amount_label: str | None = None,
    source_url: str | None = None,
    source_label: str | None = None,
    metadata: dict | None = None,
    date_start: date | None = None,
    date_end: date | None = None,
) -> Relationship | None:
    """Create a relationship if it doesn't already exist."""
    existing = await _find_existing_relationship(session, from_id, to_id, rel_type)
    if existing:
        # Update amount if we have a bigger one
        if amount_usd and (not existing.amount_usd or amount_usd > existing.amount_usd):
            existing.amount_usd = amount_usd
            if amount_label:
                existing.amount_label = _sanitize_str(amount_label)
        if metadata:
            existing.metadata_ = _sanitize_dict({
                **(existing.metadata_ or {}),
                **metadata,
            })
        return existing

    rel = Relationship(
        from_entity_id=from_id,
        to_entity_id=to_id,
        relationship_type=rel_type,
        amount_usd=amount_usd,
        amount_label=_sanitize_str(amount_label) if amount_label else None,
        source_url=_sanitize_str(source_url) if source_url else None,
        source_label=_sanitize_str(source_label) if source_label else None,
        metadata_=_sanitize_dict(metadata) if metadata else {},
        date_start=date_start,
        date_end=date_end,
    )
    session.add(rel)
    return rel


# ---------------------------------------------------------------------------
# Official matching for revolving door
# ---------------------------------------------------------------------------

async def _try_match_official(
    session: AsyncSession,
    first_name: str,
    last_name: str,
    covered_position: str,
) -> Entity | None:
    """Try to match a lobbyist's former position to an existing official entity.

    Uses a fuzzy name match against person entities in the database.
    """
    # Normalize names for matching
    first_lower = first_name.strip().lower()
    last_lower = last_name.strip().lower()

    if not last_lower:
        return None

    # Search for person entities whose slug or name contains the last name
    result = await session.execute(
        select(Entity).where(
            Entity.entity_type == "person",
            Entity.slug.ilike(f"%{last_lower}%"),
        )
    )
    candidates = result.scalars().all()

    for candidate in candidates:
        cand_name = candidate.name.lower()
        # Check if first name initial or full first name matches
        if first_lower and (
            first_lower in cand_name
            or (len(first_lower) >= 1 and cand_name.startswith(first_lower[0]))
        ):
            # Good enough match — same last name + first name/initial match
            if last_lower in cand_name:
                return candidate

    return None


# ---------------------------------------------------------------------------
# Process a single filing
# ---------------------------------------------------------------------------

def _parse_income(filing: dict) -> int | None:
    """Parse income from a filing. Returns amount in dollars or None."""
    income = filing.get("income") or filing.get("expenses")
    if income is None:
        return None
    if isinstance(income, str):
        cleaned = income.replace(",", "").replace("$", "").strip()
        try:
            return int(float(cleaned)) if cleaned else None
        except ValueError:
            return None
    try:
        return int(float(income))
    except (ValueError, TypeError):
        return None


def _filing_period_dates(filing: dict) -> tuple[date | None, date | None]:
    """Extract approximate date range from filing period."""
    year = filing.get("filing_year", 2025)
    period = filing.get("filing_period", "")

    period_map = {
        "first_quarter": (f"{year}-01-01", f"{year}-03-31"),
        "second_quarter": (f"{year}-04-01", f"{year}-06-30"),
        "third_quarter": (f"{year}-07-01", f"{year}-09-30"),
        "fourth_quarter": (f"{year}-10-01", f"{year}-12-31"),
        "mid_year": (f"{year}-01-01", f"{year}-06-30"),
        "year_end": (f"{year}-07-01", f"{year}-12-31"),
    }

    if period in period_map:
        start_str, end_str = period_map[period]
        return date.fromisoformat(start_str), date.fromisoformat(end_str)
    return None, None


async def process_filing(
    session: AsyncSession,
    filing: dict,
    stats: dict,
) -> None:
    """Process a single LDA filing, creating entities and relationships."""
    filing_uuid = filing.get("filing_uuid", "")
    registrant = filing.get("registrant") or {}
    client_data = filing.get("client") or {}

    registrant_name = registrant.get("name", "").strip()
    client_name = client_data.get("name", "").strip()

    if not registrant_name or not client_name:
        stats["skipped"] += 1
        return

    income = _parse_income(filing)
    date_start, date_end = _filing_period_dates(filing)
    filing_url = filing.get("filing_document_url", "")
    filing_type = filing.get("filing_type_display", "")
    filing_year = filing.get("filing_year", "")
    filing_period = filing.get("filing_period_display", "")

    # Collect issue areas from lobbying activities
    issue_codes: list[str] = []
    issue_descriptions: list[str] = []
    for activity in filing.get("lobbying_activities", []):
        code = activity.get("general_issue_code_display", "")
        if code and code not in issue_codes:
            issue_codes.append(_sanitize_str(code))
        desc = activity.get("description", "")
        if desc:
            issue_descriptions.append(_sanitize_str(desc)[:500])

    # ---- 1. Create/update registrant (lobbying firm) entity ----
    firm_slug = _slugify(f"lobby-{registrant_name}")
    firm_entity = await _upsert_entity(
        session,
        slug=firm_slug,
        entity_type="organization",
        name=registrant_name,
        summary=f"Lobbying firm registered with the Senate LDA.",
        metadata={
            "source": "Senate LDA",
            "lda_registrant_id": registrant.get("id"),
            "registrant_state": _sanitize_str(registrant.get("state_display", "")),
            "is_lobbying_firm": True,
        },
    )
    stats["firms_created"] += 1

    # ---- 2. Create/update client entity ----
    client_desc = client_data.get("general_description", "")
    client_state = client_data.get("state_display", "")
    client_slug = _slugify(f"client-{client_name}")
    client_entity = await _upsert_entity(
        session,
        slug=client_slug,
        entity_type="organization",
        name=client_name,
        summary=_sanitize_str(client_desc) if client_desc else f"Client of lobbying firm {registrant_name}.",
        metadata={
            "source": "Senate LDA",
            "lda_client_id": client_data.get("client_id"),
            "client_state": _sanitize_str(client_state),
            "is_lobbying_client": True,
        },
    )
    stats["clients_created"] += 1

    # ---- 3. Create lobbies_on_behalf_of relationship: firm → client ----
    await _create_relationship(
        session,
        from_id=firm_entity.id,
        to_id=client_entity.id,
        rel_type="lobbies_on_behalf_of",
        amount_usd=income,
        amount_label=f"${income:,}" if income else None,
        source_url=_sanitize_str(filing_url) if filing_url else "https://lda.senate.gov/filings/",
        source_label=f"Senate LDA {filing_type} ({filing_year} {filing_period})",
        metadata={
            "filing_uuid": _sanitize_str(filing_uuid),
            "filing_type": _sanitize_str(filing_type),
            "filing_year": filing_year,
            "filing_period": _sanitize_str(filing_period),
            "issue_codes": issue_codes[:10],
            "issue_descriptions": issue_descriptions[:5],
        },
        date_start=date_start,
        date_end=date_end,
    )
    stats["relationships_created"] += 1

    # ---- 4. Process lobbyists, especially revolving door ----
    for activity in filing.get("lobbying_activities", []):
        for lob_entry in activity.get("lobbyists", []):
            lobbyist_info = lob_entry.get("lobbyist", {})
            covered_position = lob_entry.get("covered_position")
            first_name = _sanitize_str(lobbyist_info.get("first_name", "")).strip()
            last_name = _sanitize_str(lobbyist_info.get("last_name", "")).strip()
            lobbyist_name = f"{first_name} {last_name}".strip()

            if not lobbyist_name:
                continue

            # Only create full entity records for revolving door lobbyists
            if covered_position:
                covered_position = _sanitize_str(covered_position).strip()
                lobbyist_slug = _slugify(f"lobbyist-{lobbyist_name}")

                lobbyist_entity = await _upsert_entity(
                    session,
                    slug=lobbyist_slug,
                    entity_type="person",
                    name=lobbyist_name.title(),
                    summary=(
                        f"Registered lobbyist (revolving door). "
                        f"Former position: {covered_position}."
                    ),
                    metadata={
                        "source": "Senate LDA",
                        "covered_position": covered_position,
                        "is_revolving_door": True,
                        "lda_lobbyist_id": lobbyist_info.get("id"),
                        "current_firm": _sanitize_str(registrant_name),
                    },
                )

                # revolving_door_lobbyist: lobbyist → firm
                await _create_relationship(
                    session,
                    from_id=lobbyist_entity.id,
                    to_id=firm_entity.id,
                    rel_type="revolving_door_lobbyist",
                    source_url=_sanitize_str(filing_url) if filing_url else "https://lda.senate.gov/filings/",
                    source_label="Senate LDA",
                    metadata={
                        "covered_position": covered_position,
                        "filing_uuid": _sanitize_str(filing_uuid),
                        "client": _sanitize_str(client_name),
                    },
                )
                stats["revolving_door"] += 1

                # Try to match to an existing official
                matched_official = await _try_match_official(
                    session, first_name, last_name, covered_position
                )
                if matched_official:
                    await _create_relationship(
                        session,
                        from_id=lobbyist_entity.id,
                        to_id=matched_official.id,
                        rel_type="former_official_now_lobbyist",
                        source_url=_sanitize_str(filing_url) if filing_url else "https://lda.senate.gov/filings/",
                        source_label="Senate LDA (matched)",
                        metadata={
                            "covered_position": covered_position,
                            "matched_official": _sanitize_str(matched_official.name),
                            "confidence": "name_match",
                        },
                    )
                    stats["officials_matched"] += 1
                    logger.info(
                        "Revolving door match: %s (%s) -> %s",
                        lobbyist_name, covered_position, matched_official.name,
                    )


# ---------------------------------------------------------------------------
# Main ingestion runner
# ---------------------------------------------------------------------------

async def run_lobbying_bulk_ingestion(
    years: list[int] | None = None,
    max_filings: int = MAX_FILINGS,
) -> dict:
    """Run bulk lobbying data ingestion from the Senate LDA API.

    Args:
        years: Filing years to fetch (default: [2024, 2025])
        max_filings: Maximum filings to process per year

    Returns:
        Summary dict of ingestion results
    """
    if years is None:
        years = FILING_YEARS

    logger.info("=" * 60)
    logger.info("LOBBYING BULK INGESTION (Senate LDA)")
    logger.info("Years: %s | Max filings/year: %d", years, max_filings)
    logger.info("=" * 60)

    # Create ingestion job
    async with async_session() as session:
        job = IngestionJob(
            job_type="lobbying_bulk",
            status="in_progress",
            total=max_filings * len(years),
            started_at=datetime.now(timezone.utc),
            metadata_={"years": years, "max_filings": max_filings},
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    stats = {
        "filings_processed": 0,
        "firms_created": 0,
        "clients_created": 0,
        "relationships_created": 0,
        "revolving_door": 0,
        "officials_matched": 0,
        "skipped": 0,
        "errors": [],
    }

    try:
        for year in years:
            logger.info("--- Fetching filings for year %d ---", year)
            filings = await fetch_filings_paginated(year, max_filings)
            logger.info("Got %d filings for year %d", len(filings), year)

            for i, filing in enumerate(filings):
                try:
                    async with async_session() as session:
                        async with session.begin():
                            await process_filing(session, filing, stats)
                    stats["filings_processed"] += 1
                except Exception as exc:
                    error_msg = f"Filing {filing.get('filing_uuid', '?')}: {exc}"
                    logger.error("Error processing filing: %s", error_msg)
                    stats["errors"].append(_sanitize_str(error_msg)[:500])

                # Update job progress periodically
                if (i + 1) % 25 == 0 or i == len(filings) - 1:
                    async with async_session() as session:
                        job_obj = await session.get(IngestionJob, job_id)
                        if job_obj:
                            job_obj.progress = stats["filings_processed"]
                            job_obj.metadata_ = _sanitize_dict({
                                **job_obj.metadata_,
                                "stats": {k: v for k, v in stats.items() if k != "errors"},
                            })
                            await session.commit()

                    logger.info(
                        "Progress: %d/%d filings | %d firms | %d clients | %d revolving door | %d matched",
                        stats["filings_processed"], len(filings),
                        stats["firms_created"], stats["clients_created"],
                        stats["revolving_door"], stats["officials_matched"],
                    )

        # Mark job complete
        async with async_session() as session:
            job_obj = await session.get(IngestionJob, job_id)
            if job_obj:
                job_obj.status = "completed"
                job_obj.progress = stats["filings_processed"]
                job_obj.completed_at = datetime.now(timezone.utc)
                job_obj.errors = [_sanitize_str(e) for e in stats["errors"][:50]]
                job_obj.metadata_ = _sanitize_dict({
                    **job_obj.metadata_,
                    "stats": {k: v for k, v in stats.items() if k != "errors"},
                })
                await session.commit()

    except Exception as exc:
        logger.error("Fatal error in lobbying bulk ingestion: %s", exc)
        async with async_session() as session:
            job_obj = await session.get(IngestionJob, job_id)
            if job_obj:
                job_obj.status = "failed"
                job_obj.completed_at = datetime.now(timezone.utc)
                job_obj.errors = [_sanitize_str(str(exc))]
                await session.commit()
        raise

    logger.info("=" * 60)
    logger.info("LOBBYING BULK INGESTION COMPLETE")
    logger.info("Stats: %s", {k: v for k, v in stats.items() if k != "errors"})
    logger.info("Errors: %d", len(stats["errors"]))
    logger.info("=" * 60)

    return stats


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(run_lobbying_bulk_ingestion())
