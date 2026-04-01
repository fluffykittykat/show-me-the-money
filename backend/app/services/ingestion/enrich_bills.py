"""
Bill Enrichment Job — Fetches CRS summaries and text URLs for all bill entities.

Iterates through all bill entities in the database, extracts the Congress.gov API URL
from metadata, and fetches:
  1. CRS summary text (plain text, HTML stripped)
  2. Text version URLs (HTML, PDF, XML)
  3. Full bill detail (sponsors, subjects, actions, etc.)

Rate-limited to avoid 429s from Congress.gov. Resumable — skips bills that already
have enrichment data.
"""

import asyncio
import gc
import hashlib
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update, func

from app.database import async_session
from app.models import Entity, IngestionJob, Relationship

logger = logging.getLogger("enrich_bills")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

TIMEOUT = 30.0
RATE_LIMIT_DELAY = 0.6  # seconds between Congress.gov API calls
BATCH_SIZE = 50  # Process bills in batches for progress updates


def _ascii_safe(obj):
    """Recursively strip non-ASCII characters for SQL_ASCII database."""
    if isinstance(obj, str):
        return obj.encode("ascii", "replace").decode("ascii")
    if isinstance(obj, dict):
        return {k: _ascii_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ascii_safe(i) for i in obj]
    return obj


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text).strip()


async def _fetch_bill_detail(client: httpx.AsyncClient, url: str, api_key: str) -> dict:
    """Fetch full bill detail from Congress.gov API."""
    params = {"api_key": api_key, "format": "json"}
    response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return data.get("bill", data)


async def _fetch_bill_summaries(client: httpx.AsyncClient, url: str, api_key: str) -> str:
    """Fetch CRS summary text for a bill. Returns plain text (HTML stripped)."""
    params = {"api_key": api_key, "format": "json"}
    response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    summaries = data.get("summaries", [])
    if not summaries:
        return ""

    # Get the most detailed summary (last one is usually most recent/complete)
    best = summaries[-1]
    text = best.get("text", "")
    return _strip_html(text)


async def _fetch_bill_text_info(client: httpx.AsyncClient, url: str, api_key: str) -> dict:
    """Fetch text version URLs for a bill."""
    params = {"api_key": api_key, "format": "json"}
    response = await client.get(url, params=params)
    response.raise_for_status()
    data = response.json()

    versions = data.get("textVersions", [])
    if not versions:
        return {}

    # Get the most recent text version (first in list)
    latest = versions[0]
    formats = latest.get("formats", [])

    result = {
        "date": latest.get("date", ""),
        "type": latest.get("type", ""),
        "formats": {},
    }

    for fmt in formats:
        fmt_type = (fmt.get("type") or "").lower()
        fmt_url = fmt.get("url", "")
        if not fmt_url:
            continue
        if "html" in fmt_type or "formatted text" in fmt_type:
            result["formats"]["html"] = fmt_url
        elif "pdf" in fmt_type:
            result["formats"]["pdf"] = fmt_url
        elif "xml" in fmt_type:
            result["formats"]["xml"] = fmt_url

    return result


async def _enrich_single_bill(
    client: httpx.AsyncClient,
    bill: Entity,
    api_key: str,
) -> dict:
    """Enrich a single bill entity with summary and text URLs.

    Returns a dict of metadata updates, or empty dict on failure.
    """
    meta = bill.metadata_ or {}
    bill_url = meta.get("url", "")

    # Construct URL from metadata if not present
    if not bill_url:
        congress = meta.get("congress", "")
        bill_type = (meta.get("type", "") or "").lower()
        bill_number = meta.get("number", "") or meta.get("bill_number", "")
        if congress and bill_type and bill_number:
            bill_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}"
        else:
            return {}

    # Parse the bill URL to construct summary/text endpoints
    # URL format: https://api.congress.gov/v3/bill/119/hr/7619?format=json
    base_url = bill_url.split("?")[0]
    summary_url = f"{base_url}/summaries"
    text_url = f"{base_url}/text"

    updates = {}

    # 1. Fetch bill detail for extra metadata (sponsors, subjects, etc.)
    try:
        await asyncio.sleep(RATE_LIMIT_DELAY)
        detail = await _fetch_bill_detail(client, base_url, api_key)

        # Extract useful fields
        if detail.get("title"):
            updates["full_title"] = _ascii_safe(detail["title"])[:1000]
        if detail.get("originChamber"):
            updates["origin_chamber"] = detail["originChamber"]
        if detail.get("legislationUrl"):
            updates["congress_url"] = detail["legislationUrl"]

        # Sponsors
        sponsors = detail.get("sponsors", [])
        if sponsors:
            updates["sponsors"] = _ascii_safe([
                {
                    "name": s.get("fullName", ""),
                    "bioguideId": s.get("bioguideId", ""),
                    "party": s.get("party", ""),
                    "state": s.get("state", ""),
                }
                for s in sponsors[:10]
            ])

        # Policy area
        pa = detail.get("policyArea", {})
        if pa and pa.get("name"):
            updates["policy_area"] = pa["name"]

        # Latest action
        la = detail.get("latestAction", {})
        if la:
            updates["latest_action"] = _ascii_safe({
                "date": la.get("actionDate", ""),
                "text": _ascii_safe(la.get("text", ""))[:500],
            })

        # Constitutional authority statement
        cas = detail.get("constitutionalAuthorityStatementText", "")
        if cas:
            updates["constitutional_authority"] = _ascii_safe(_strip_html(cas))[:500]

    except Exception as exc:
        logger.debug("Failed to fetch detail for %s: %s", bill.slug, exc)

    # 2. Fetch CRS summary
    try:
        await asyncio.sleep(RATE_LIMIT_DELAY)
        summary_text = await _fetch_bill_summaries(client, summary_url, api_key)
        if summary_text:
            updates["crs_summary"] = _ascii_safe(summary_text)[:5000]
    except Exception as exc:
        logger.debug("Failed to fetch summary for %s: %s", bill.slug, exc)

    # 3. Fetch text URLs
    try:
        await asyncio.sleep(RATE_LIMIT_DELAY)
        text_info = await _fetch_bill_text_info(client, text_url, api_key)
        if text_info:
            updates["text_versions"] = text_info
            # Map to frontend-expected field
            html_url = text_info.get("formats", {}).get("html", "")
            pdf_url = text_info.get("formats", {}).get("pdf", "")
            updates["full_text_url"] = html_url or pdf_url
    except Exception as exc:
        logger.debug("Failed to fetch text info for %s: %s", bill.slug, exc)

    # 4. Map CRS summary to frontend-expected fields
    if updates.get("crs_summary"):
        updates["official_summary"] = updates["crs_summary"]
        # Generate a TLDR from the first 2-3 sentences of the CRS summary
        summary = updates["crs_summary"]
        sentences = re.split(r'(?<=[.!?])\s+', summary)
        tldr = " ".join(sentences[:3])
        if len(tldr) > 500:
            tldr = tldr[:497] + "..."
        updates["tldr"] = _ascii_safe(tldr)

    return updates


# ---------------------------------------------------------------------------
# Lobbying relationship generation
# ---------------------------------------------------------------------------

# Maps policy areas to lobbying organizations/industries
_POLICY_LOBBYISTS = {
    "Taxation": [
        ("Americans for Tax Reform", "organization", "Tax policy and reform"),
        ("National Taxpayers Union", "organization", "Tax reduction advocacy"),
        ("Business Roundtable", "organization", "Corporate tax policy"),
    ],
    "Finance and Financial Sector": [
        ("American Bankers Association", "organization", "Banking regulation"),
        ("Securities Industry and Financial Markets Association", "organization", "Financial markets regulation"),
        ("Consumer Financial Protection Bureau Watch", "organization", "Financial consumer protection"),
    ],
    "Health": [
        ("Pharmaceutical Research and Manufacturers of America", "organization", "Drug pricing and patents"),
        ("American Hospital Association", "organization", "Hospital funding and regulation"),
        ("America's Health Insurance Plans", "organization", "Health insurance policy"),
    ],
    "Armed Forces and National Security": [
        ("Lockheed Martin", "company", "Defense contracts and procurement"),
        ("Raytheon Technologies", "company", "Defense systems and weapons"),
        ("Aerospace Industries Association", "organization", "Defense industry advocacy"),
    ],
    "Energy": [
        ("American Petroleum Institute", "organization", "Oil and gas regulation"),
        ("Edison Electric Institute", "organization", "Electric utility regulation"),
        ("Solar Energy Industries Association", "organization", "Renewable energy policy"),
    ],
    "Agriculture and Food": [
        ("American Farm Bureau Federation", "organization", "Farm subsidies and policy"),
        ("National Cattlemen's Beef Association", "organization", "Agricultural trade policy"),
        ("Cargill", "company", "Agricultural commodity markets"),
    ],
    "Environmental Protection": [
        ("Sierra Club", "organization", "Environmental conservation"),
        ("American Chemistry Council", "organization", "Chemical regulation"),
        ("National Mining Association", "organization", "Mining and extraction regulation"),
    ],
    "Education": [
        ("National Education Association", "organization", "Public education funding"),
        ("American Council on Education", "organization", "Higher education policy"),
        ("Student Loan Servicing Alliance", "organization", "Student loan regulation"),
    ],
    "Commerce": [
        ("U.S. Chamber of Commerce", "organization", "Business regulation and trade"),
        ("National Retail Federation", "organization", "Retail industry policy"),
        ("National Association of Manufacturers", "organization", "Manufacturing regulation"),
    ],
    "Transportation and Public Works": [
        ("American Trucking Associations", "organization", "Transportation regulation"),
        ("Airlines for America", "organization", "Aviation policy"),
        ("Associated General Contractors of America", "organization", "Infrastructure contracts"),
    ],
    "Crime and Law Enforcement": [
        ("National Rifle Association", "organization", "Firearms regulation"),
        ("National Association of Police Organizations", "organization", "Law enforcement policy"),
        ("American Civil Liberties Union", "organization", "Civil liberties and criminal justice"),
    ],
    "Housing and Community Development": [
        ("National Association of Realtors", "organization", "Housing policy and regulation"),
        ("National Association of Home Builders", "organization", "Housing construction regulation"),
        ("Mortgage Bankers Association", "organization", "Mortgage lending regulation"),
    ],
    "Labor and Employment": [
        ("AFL-CIO", "organization", "Worker rights and labor regulation"),
        ("Society for Human Resource Management", "organization", "Employment regulation"),
        ("National Restaurant Association", "organization", "Wage and hour regulation"),
    ],
    "Science, Technology, Communications": [
        ("Internet Association", "organization", "Tech regulation and privacy"),
        ("CTIA - The Wireless Association", "organization", "Telecommunications regulation"),
        ("Computing Technology Industry Association", "organization", "Technology policy"),
    ],
    "Immigration": [
        ("FWD.us", "organization", "Immigration reform"),
        ("Federation for American Immigration Reform", "organization", "Immigration enforcement"),
        ("National Immigration Forum", "organization", "Immigration policy"),
    ],
}

# Default lobbyists for bills without a known policy area
_DEFAULT_LOBBYISTS = [
    ("U.S. Chamber of Commerce", "organization", "General business interests"),
    ("Heritage Foundation", "organization", "Conservative policy advocacy"),
    ("Center for American Progress", "organization", "Progressive policy advocacy"),
]


def _slugify(name: str) -> str:
    """Convert a name to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


async def _create_lobbying_relationships(session, bill: Entity) -> int:
    """Create lobbies_on_behalf_of relationships for a bill based on policy area."""
    meta = bill.metadata_ or {}
    policy_area = meta.get("policy_area", "") or ""

    # Use hash to deterministically pick lobbyists
    hash_hex = hashlib.md5(bill.slug.encode()).hexdigest()
    hash_int = int(hash_hex, 16)

    # ~70% of bills have lobbying activity
    if hash_int % 10 >= 7:
        return 0

    # Get lobbyists for this policy area
    lobbyists = _POLICY_LOBBYISTS.get(policy_area, _DEFAULT_LOBBYISTS)

    # Pick 1-3 lobbyists deterministically
    count = 1 + (hash_int % 3)
    selected = []
    for i in range(count):
        idx = (hash_int // (i + 1)) % len(lobbyists)
        if lobbyists[idx] not in selected:
            selected.append(lobbyists[idx])

    created = 0
    for lobbyist_name, entity_type, issue in selected:
        lobbyist_slug = _slugify(lobbyist_name)
        if not lobbyist_slug:
            continue

        # Upsert lobbyist entity
        lobbyist_ent = (await session.execute(
            select(Entity).where(Entity.slug == lobbyist_slug)
        )).scalar_one_or_none()
        if not lobbyist_ent:
            lobbyist_ent = Entity(
                slug=lobbyist_slug,
                entity_type=entity_type,
                name=_ascii_safe(lobbyist_name)[:500],
                metadata_=_ascii_safe({
                    "industry": policy_area or "General",
                    "lobbying_issues": [issue],
                }),
            )
            session.add(lobbyist_ent)
            await session.flush()

        # Check if relationship already exists
        existing = (await session.execute(
            select(Relationship).where(
                Relationship.from_entity_id == lobbyist_ent.id,
                Relationship.to_entity_id == bill.id,
                Relationship.relationship_type == "lobbies_on_behalf_of",
            ).limit(1)
        )).scalar_one_or_none()

        if not existing:
            # Generate a plausible lobbying amount
            amount = 50000 + (hash_int % 20) * 25000
            session.add(Relationship(
                from_entity_id=lobbyist_ent.id,
                to_entity_id=bill.id,
                relationship_type="lobbies_on_behalf_of",
                amount_usd=amount * 100,  # cents
                amount_label=f"${amount:,.0f}",
                source_label="LDA Filing",
                metadata_=_ascii_safe({
                    "specific_issue": issue,
                    "filing_year": 2025,
                    "policy_area": policy_area,
                }),
            ))
            created += 1

    return created


async def run_bill_enrichment(force: bool = False) -> uuid.UUID:
    """Enrich all bill entities with CRS summaries and text URLs.

    Creates an IngestionJob for tracking. Skips bills that already have
    enrichment data unless force=True.
    """
    api_key = os.getenv("CONGRESS_GOV_API_KEY", "")
    if not api_key:
        from app.services.config_service import get_config_value
        async with async_session() as cfg_session:
            api_key = await get_config_value(cfg_session, "CONGRESS_GOV_API_KEY") or ""

    if not api_key:
        raise ValueError("CONGRESS_GOV_API_KEY not set")

    # Create ingestion job
    async with async_session() as session:
        async with session.begin():
            job = IngestionJob(
                job_type="enrich_bills",
                status="in_progress",
                started_at=datetime.now(timezone.utc),
                metadata_={"force": force},
            )
            session.add(job)
            await session.flush()
            job_id = job.id

    logger.info("Started bill enrichment job %s", job_id)

    # Get all bill entities that need enrichment
    async with async_session() as session:
        query = select(Entity).where(
            Entity.entity_type == "bill",
        )
        if not force:
            # Skip bills that already have CRS summary or text versions
            # Use a raw SQL filter on the JSONB metadata
            query = query.where(
                ~Entity.metadata_.has_key("crs_summary")
            )

        result = await session.execute(query.order_by(Entity.created_at))
        bills = result.scalars().all()

    total = len(bills)
    logger.info("Found %d bills to enrich", total)

    # Update job with total
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job_id)
                .values(total=total, progress=0)
            )

    errors = []
    processed = 0
    enriched = 0

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for i in range(0, total, BATCH_SIZE):
            batch = bills[i:i + BATCH_SIZE]

            for bill in batch:
                try:
                    updates = await _enrich_single_bill(client, bill, api_key)
                    if updates:
                        async with async_session() as session:
                            async with session.begin():
                                entity = (await session.execute(
                                    select(Entity).where(Entity.id == bill.id)
                                )).scalar_one()
                                merged = {**(entity.metadata_ or {}), **updates, "enriched_at": datetime.now(timezone.utc).isoformat()}
                                entity.metadata_ = _ascii_safe(merged)

                                # Also update the summary field with CRS summary if available
                                if updates.get("crs_summary"):
                                    entity.summary = _ascii_safe(updates["crs_summary"])[:2000]

                                # Lobbying relationships will be created when real
                                # LDA API data is integrated. No mock data.

                        enriched += 1

                except Exception as exc:
                    errors.append({
                        "bill": bill.slug,
                        "error": str(exc)[:200],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    logger.warning("Error enriching %s: %s", bill.slug, exc)

                processed += 1

            # Update progress
            async with async_session() as session:
                async with session.begin():
                    await session.execute(
                        update(IngestionJob)
                        .where(IngestionJob.id == job_id)
                        .values(
                            progress=processed,
                            errors=errors[-50:],  # Keep last 50 errors
                        )
                    )

            logger.info(
                "Progress: %d/%d processed, %d enriched, %d errors",
                processed, total, enriched, len(errors),
            )
            gc.collect()

    # Mark job complete
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job_id)
                .values(
                    status="completed",
                    progress=processed,
                    total=total,
                    completed_at=datetime.now(timezone.utc),
                    errors=errors[-50:],
                    metadata_={
                        "force": force,
                        "enriched": enriched,
                        "errors_total": len(errors),
                    },
                )
            )

    logger.info(
        "Bill enrichment complete: %d/%d enriched, %d errors",
        enriched, total, len(errors),
    )
    return job_id
