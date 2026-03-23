"""
Ingestion script for lobbying data from the Senate LDA API.

For each company entity in the DB, searches the LDA for lobbying filings
and creates lobbying_firm and lobbyist entities with appropriate relationships.

Special handling for Bank of America (searches multiple name variants).

Usage:
    cd /home/mansona/workspace/jerry-maguire/backend
    python -m app.services.ingestion.ingest_lobbying
"""

import asyncio
import logging
import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Entity, Relationship
from app.services.ingestion.lda_client import LDAClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers (same patterns as ingest_fetterman.py)
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    s = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    return re.sub(r"-+", "-", s)


def sanitize_str(s) -> str:
    """Strip non-ASCII characters (DB uses SQL_ASCII encoding)."""
    if not isinstance(s, str):
        return s
    return s.encode("ascii", errors="ignore").decode("ascii")


def sanitize_dict(d) -> dict:
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


async def upsert_entity(
    session: AsyncSession, slug: str, entity_type: str,
    name: str, summary: str | None = None,
    metadata: dict | None = None,
) -> Entity:
    """Insert or update an entity by slug."""
    name = sanitize_str(name)[:490]
    summary = sanitize_str(summary) if summary else summary
    slug = slug[:195]
    metadata = sanitize_dict(metadata) if metadata else metadata

    result = await session.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()

    if entity:
        entity.name = name
        entity.entity_type = entity_type
        if summary:
            entity.summary = summary
        if metadata:
            entity.metadata_ = sanitize_dict({**(entity.metadata_ or {}), **metadata})
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


def make_relationship(**kwargs) -> Relationship:
    """Create a Relationship with sanitized string fields."""
    if "source_label" in kwargs:
        kwargs["source_label"] = sanitize_str(kwargs["source_label"])
    if "source_url" in kwargs:
        kwargs["source_url"] = sanitize_str(kwargs["source_url"])
    if "amount_label" in kwargs:
        kwargs["amount_label"] = sanitize_str(kwargs["amount_label"])
    if "metadata_" in kwargs:
        kwargs["metadata_"] = sanitize_dict(kwargs["metadata_"])
    return Relationship(**kwargs)


# ---------------------------------------------------------------------------
# Bank of America special search variants
# ---------------------------------------------------------------------------
BOFA_SEARCH_NAMES = ["bank of america", "bofa", "BAC"]
BOFA_PAC_COMMITTEE_ID = "C00009688"


# ---------------------------------------------------------------------------
# Core ingestion logic
# ---------------------------------------------------------------------------

async def ingest_company_lobbying(
    session: AsyncSession,
    company_entity: Entity,
    company_name: str,
    search_names: list[str] | None = None,
) -> dict:
    """Ingest lobbying data for a company.

    Args:
        session: Active DB session
        company_entity: The company Entity record
        company_name: Primary name to search
        search_names: Additional name variants to search (e.g. for BofA)

    Returns:
        Summary dict of what was ingested
    """
    client = LDAClient()

    # Search primary name + any variants
    names_to_search = [company_name]
    if search_names:
        names_to_search.extend(search_names)

    # Aggregate results across all search variants
    all_firms: set[str] = set()
    all_lobbyists: set[str] = set()
    all_issues: list[str] = []
    total_spend = 0
    total_filings = 0
    total_registrations = 0

    for name in names_to_search:
        try:
            summary = await client.fetch_client_lobbying_summary(name)
            total_spend += summary.get("total_spend", 0)
            total_filings += summary.get("filing_count", 0)
            total_registrations += summary.get("registrations", 0)
            all_firms.update(summary.get("lobbying_firms", []))
            all_lobbyists.update(summary.get("lobbyists", []))
            all_issues.extend(summary.get("issues", []))
        except Exception as exc:
            logger.warning(
                "Error fetching lobbying data for '%s' (variant of %s): %s",
                name, company_name, exc,
            )

    # Deduplicate issues
    seen_issues: set[str] = set()
    unique_issues: list[str] = []
    for issue in all_issues:
        normalized = issue.strip().lower()
        if normalized not in seen_issues:
            seen_issues.add(normalized)
            unique_issues.append(sanitize_str(issue))
    unique_issues = unique_issues[:20]

    # Update company metadata with lobbying data
    lobbying_meta = {
        "total_spend": total_spend,
        "filing_count": total_filings,
        "firm_count": len(all_firms),
        "lobbyist_count": len(all_lobbyists),
        "issues": unique_issues,
        "registration_count": total_registrations,
        "last_ingested": datetime.now(tz=None).isoformat(),
    }

    company_entity.metadata_ = sanitize_dict({
        **(company_entity.metadata_ or {}),
        "lobbying": lobbying_meta,
    })
    company_entity.updated_at = datetime.now(tz=None)

    # Create lobbying firm entities + relationships
    firm_count = 0
    for firm_name in all_firms:
        if not firm_name.strip():
            continue
        firm_slug = slugify(firm_name)
        firm_entity = await upsert_entity(
            session, firm_slug, "lobbying_firm", firm_name,
            summary=f"Lobbying firm registered with the Senate LDA.",
            metadata={"source": "Senate LDA"},
        )
        rel = make_relationship(
            from_entity_id=firm_entity.id,
            to_entity_id=company_entity.id,
            relationship_type="lobbies_on_behalf_of",
            source_label="Senate LDA",
            source_url="https://lda.senate.gov/filings/",
            metadata_={"search_name": sanitize_str(company_name)},
        )
        session.add(rel)
        firm_count += 1

    # Create lobbyist entities + relationships
    lobbyist_count = 0
    for lobbyist_name in all_lobbyists:
        if not lobbyist_name.strip():
            continue
        lobbyist_slug = slugify(lobbyist_name)
        lobbyist_entity = await upsert_entity(
            session, lobbyist_slug, "lobbyist", lobbyist_name,
            summary=f"Registered lobbyist (Senate LDA).",
            metadata={"source": "Senate LDA"},
        )
        rel = make_relationship(
            from_entity_id=lobbyist_entity.id,
            to_entity_id=company_entity.id,
            relationship_type="registered_lobbyist_for",
            source_label="Senate LDA",
            source_url="https://lda.senate.gov/filings/",
            metadata_={"search_name": sanitize_str(company_name)},
        )
        session.add(rel)
        lobbyist_count += 1

    result_summary = {
        "company": company_name,
        "total_spend": total_spend,
        "filing_count": total_filings,
        "firms_created": firm_count,
        "lobbyists_created": lobbyist_count,
        "issues_found": len(unique_issues),
    }

    logger.info("Lobbying ingestion for %s: %s", company_name, result_summary)
    return result_summary


async def run_lobbying_ingestion():
    """Ingest lobbying data for all company entities in the database."""
    print("\n" + "#" * 60)
    print("# LOBBYING DATA INGESTION (Senate LDA)")
    print(f"# Time: {datetime.now(tz=None).isoformat()}")
    print("#" * 60 + "\n")

    async with async_session() as session:
        async with session.begin():
            # Find all company entities
            result = await session.execute(
                select(Entity).where(Entity.entity_type == "company")
            )
            companies = result.scalars().all()

            if not companies:
                print("No company entities found in database.")
                return

            print(f"Found {len(companies)} company entities.\n")

            for company in companies:
                company_name = company.name
                print(f"  Processing: {company_name} ({company.slug})")

                # Special handling for Bank of America
                name_lower = company_name.lower()
                search_names = None
                if "bank of america" in name_lower or "bofa" in name_lower:
                    search_names = BOFA_SEARCH_NAMES
                    print(f"    -> BofA detected, searching variants: {search_names}")
                    # Store PAC committee ID in metadata
                    company.metadata_ = sanitize_dict({
                        **(company.metadata_ or {}),
                        "pac_committee_id": BOFA_PAC_COMMITTEE_ID,
                    })

                try:
                    summary = await ingest_company_lobbying(
                        session, company, company_name, search_names
                    )
                    spend_dollars = summary["total_spend"] / 100
                    print(
                        f"    -> ${spend_dollars:,.0f} total spend, "
                        f"{summary['firms_created']} firms, "
                        f"{summary['lobbyists_created']} lobbyists"
                    )
                except Exception as exc:
                    logger.error("Failed to ingest lobbying for %s: %s", company_name, exc)
                    print(f"    -> ERROR: {exc}")

    print("\n" + "#" * 60)
    print("# LOBBYING INGESTION COMPLETE")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(run_lobbying_ingestion())
