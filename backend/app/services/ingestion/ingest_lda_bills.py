"""
Ingestion script: parse bill numbers from LDA filings and create lobbied_on relationships.

Calls the Senate LDA API for filings in 2024 and 2025, extracts bill references
from lobbying_activities[].description via regex, matches them to existing bill
entities in the database, and creates lobbied_on relationships from the lobbying
client to the bill.

Usage:
    Trigger via admin endpoint: POST /admin/ingest/lda-bills
"""

import asyncio
import logging
import re
from datetime import datetime

import httpx
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Entity, IngestionJob, Relationship

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
LDA_BASE_URL = "https://lda.senate.gov/api/v1/filings/"
FILING_YEARS = [2024, 2025]
PER_PAGE = 50
MAX_PAGES_PER_YEAR = 5000  # ~250K filings per year at 50/page
REQUEST_DELAY = 0.5  # seconds between paginated requests — LDA API is generous
TIMEOUT = 30.0

# Maps filing year to the congress numbers to try (most recent first)
YEAR_TO_CONGRESS = {
    2025: [119, 118],
    2024: [118, 119],
    2023: [118, 117],
    2022: [117, 118],
}

# Regex: matches H.R. 1234, S. 567, H.Res. 89, S.Res. 12, etc.
BILL_PATTERN = re.compile(
    r'(?:H\.?\s*R\.?|S\.?|H\.?\s*Res\.?|S\.?\s*Res\.?)\s*(\d{1,5})',
    re.IGNORECASE,
)

# Secondary pattern to determine bill type (senate vs house)
SENATE_BILL_PATTERN = re.compile(
    r'(?:S\.?|S\.?\s*Res\.?)\s*(\d{1,5})',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    s = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    return re.sub(r"-+", "-", s)


def sanitize_str(s) -> str:
    """Strip non-ASCII characters (DB uses SQL_ASCII encoding)."""
    if not isinstance(s, str):
        return str(s) if s is not None else ""
    return s.encode("ascii", errors="ignore").decode("ascii")


def sanitize_dict(d: dict) -> dict:
    """Recursively sanitize all string values in a dict."""
    if not isinstance(d, dict):
        return d
    out = {}
    for k, v in d.items():
        if isinstance(v, str):
            out[k] = sanitize_str(v)
        elif isinstance(v, dict):
            out[k] = sanitize_dict(v)
        elif isinstance(v, list):
            out[k] = [
                sanitize_dict(i) if isinstance(i, dict)
                else sanitize_str(i) if isinstance(i, str)
                else i
                for i in v
            ]
        else:
            out[k] = v
    return out


def extract_bill_refs(description: str, filing_year: int) -> list[dict]:
    """Extract bill references from a lobbying activity description.

    Returns a list of dicts: [{"slug": "1107-119", "is_senate": False}, ...]
    Each slug attempt includes congress numbers derived from the filing year.
    """
    if not description:
        return []

    congresses = YEAR_TO_CONGRESS.get(filing_year, [119, 118])
    refs = []
    seen_numbers = set()

    for match in BILL_PATTERN.finditer(description):
        number = match.group(1)
        if number in seen_numbers:
            continue
        seen_numbers.add(number)

        # Determine if it's a senate bill by checking the prefix
        prefix = match.group(0)
        is_senate = bool(SENATE_BILL_PATTERN.match(prefix))

        for congress in congresses:
            if is_senate:
                slug = f"s-{number}-{congress}"
            else:
                slug = f"{number}-{congress}"
            refs.append({"slug": slug, "is_senate": is_senate, "number": number, "congress": congress})

    return refs


async def fetch_page(client: httpx.AsyncClient, url: str, params: dict | None = None) -> dict:
    """Fetch a single page from the LDA API with retry."""
    for attempt in range(3):
        try:
            resp = await client.get(
                url,
                params=params,
                headers={"Accept": "application/json"},
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
            logger.warning("LDA API error (attempt %d): %s — %s", attempt + 1, type(exc).__name__, exc)
            if attempt < 2:
                await asyncio.sleep(2 * (attempt + 1))
        except Exception as exc:
            logger.warning("LDA API unexpected error: %s — %s", type(exc).__name__, exc)
            return {}
    return {}


# ---------------------------------------------------------------------------
# Core ingestion
# ---------------------------------------------------------------------------

async def run_ingest_lda_bills() -> str:
    """Parse bill numbers from LDA filings and create lobbied_on relationships."""
    start_time = datetime.now(tz=None)
    logger.info("Starting LDA bill parsing ingestion")
    print(f"\n{'#' * 60}")
    print("# LDA BILL NUMBER PARSING")
    print(f"# Time: {start_time.isoformat()}")
    print(f"{'#' * 60}\n")

    stats = {
        "filings_processed": 0,
        "bills_matched": 0,
        "relationships_created": 0,
        "relationships_skipped": 0,
        "clients_created": 0,
        "errors": [],
    }

    async with async_session() as session:
        async with session.begin():
            # Create ingestion job
            job = IngestionJob(
                job_type="lda_bills",
                status="running",
                started_at=start_time,
                metadata_={"years": FILING_YEARS},
            )
            session.add(job)
            await session.flush()

        # Pre-load bill slugs into a set for fast lookup
        async with session.begin():
            result = await session.execute(
                select(Entity.slug, Entity.id).where(Entity.entity_type == "bill")
            )
            bill_lookup = {row[0]: row[1] for row in result.all()}
            logger.info("Loaded %d bill entities for matching", len(bill_lookup))
            print(f"  Loaded {len(bill_lookup)} bill entities for matching")

        # Track existing client+bill pairs to avoid duplication
        seen_pairs: set[tuple[str, str]] = set()  # (client_slug, bill_slug)

        async with httpx.AsyncClient() as http_client:
            for year in FILING_YEARS:
                print(f"\n  --- Filing year {year} ---")
                url = LDA_BASE_URL
                params = {"filing_year": year, "per_page": PER_PAGE}
                page_count = 0

                while url and page_count < MAX_PAGES_PER_YEAR:
                    data = await fetch_page(http_client, url, params if page_count == 0 else None)
                    if not data:
                        logger.warning("Empty response for year %d page %d, stopping", year, page_count)
                        break

                    results = data.get("results", [])
                    if not results:
                        break

                    # Process filings in this page
                    for filing in results:
                        try:
                            await _process_filing(session, filing, year, bill_lookup, seen_pairs, stats)
                        except Exception as exc:
                            err_msg = f"Error processing filing {filing.get('filing_uuid', '?')}: {exc}"
                            logger.error(err_msg)
                            stats["errors"].append(err_msg)

                        stats["filings_processed"] += 1
                        if stats["filings_processed"] % 50 == 0:
                            print(
                                f"    Progress: {stats['filings_processed']} filings, "
                                f"{stats['bills_matched']} matches, "
                                f"{stats['relationships_created']} relationships"
                            )

                    page_count += 1
                    url = data.get("next")
                    # Clear params for subsequent pages (next URL has them built in)
                    params = None

                    if url:
                        await asyncio.sleep(REQUEST_DELAY)

                print(f"  Year {year}: processed {page_count} pages")

        # Finalize ingestion job
        async with session.begin():
            job.status = "completed"
            job.completed_at = datetime.now(tz=None)
            job.progress = stats["filings_processed"]
            job.total = stats["filings_processed"]
            job.metadata_ = sanitize_dict({
                "years": FILING_YEARS,
                "filings_processed": stats["filings_processed"],
                "bills_matched": stats["bills_matched"],
                "relationships_created": stats["relationships_created"],
                "relationships_skipped": stats["relationships_skipped"],
                "clients_created": stats["clients_created"],
                "errors": [sanitize_str(e) for e in stats["errors"][:50]],
            })

    summary = (
        f"LDA bill parsing complete: {stats['filings_processed']} filings, "
        f"{stats['bills_matched']} bill matches, "
        f"{stats['relationships_created']} relationships created, "
        f"{stats['relationships_skipped']} duplicates skipped"
    )
    print(f"\n  {summary}")
    print(f"{'#' * 60}\n")
    logger.info(summary)
    return summary


async def _process_filing(
    session: AsyncSession,
    filing: dict,
    year: int,
    bill_lookup: dict[str, any],
    seen_pairs: set[tuple[str, str]],
    stats: dict,
) -> None:
    """Process a single LDA filing: extract bills and create relationships."""
    filing_uuid = filing.get("filing_uuid", "")
    client_info = filing.get("client") or {}
    client_name = client_info.get("name", "").strip()
    if not client_name:
        return

    filing_period = filing.get("filing_period", "")
    activities = filing.get("lobbying_activities") or []
    client_entity = None  # lazily created
    client_slug = slugify(client_name)

    for activity in activities:
        description = activity.get("description", "")
        if not description:
            continue

        bill_refs = extract_bill_refs(description, year)
        for ref in bill_refs:
            bill_slug = ref["slug"]
            bill_id = bill_lookup.get(bill_slug)
            if not bill_id:
                continue

            stats["bills_matched"] += 1

            # Deduplicate: skip if we've already linked this client to this bill
            pair_key = (client_slug, bill_slug)
            if pair_key in seen_pairs:
                stats["relationships_skipped"] += 1
                continue
            seen_pairs.add(pair_key)

            # Lazily create/find client entity
            if client_entity is None:
                async with session.begin():
                    result = await session.execute(
                        select(Entity).where(Entity.slug == client_slug)
                    )
                    client_entity = result.scalar_one_or_none()

                    if not client_entity:
                        client_entity = Entity(
                            slug=client_slug[:195],
                            entity_type="organization",
                            name=sanitize_str(client_name)[:490],
                            summary="Lobbying client (from Senate LDA filings).",
                            metadata_={"source": "Senate LDA"},
                        )
                        session.add(client_entity)
                        await session.flush()
                        stats["clients_created"] += 1

            # Check for existing relationship in DB
            async with session.begin():
                existing = await session.execute(
                    select(Relationship.id).where(
                        and_(
                            Relationship.from_entity_id == client_entity.id,
                            Relationship.to_entity_id == bill_id,
                            Relationship.relationship_type == "lobbied_on",
                        )
                    ).limit(1)
                )
                if existing.scalar_one_or_none():
                    stats["relationships_skipped"] += 1
                    continue

                rel = Relationship(
                    from_entity_id=client_entity.id,
                    to_entity_id=bill_id,
                    relationship_type="lobbied_on",
                    source_label="Senate LDA",
                    source_url=f"https://lda.senate.gov/filings/{filing_uuid}/",
                    metadata_=sanitize_dict({
                        "lda_filing_url": f"https://lda.senate.gov/filings/{filing_uuid}/",
                        "description": sanitize_str(description[:500]),
                        "filing_year": year,
                        "filing_period": sanitize_str(str(filing_period)),
                    }),
                )
                session.add(rel)
                stats["relationships_created"] += 1

            # Only use the first matching congress for each bill number
            break


if __name__ == "__main__":
    asyncio.run(run_ingest_lda_bills())
