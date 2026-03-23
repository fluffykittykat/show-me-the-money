"""
Phase 2 enrichment: Add stock holdings, lobbying connections, and revolving
door data to senators who have been batch-ingested (Phase 1).

Data sources:
- QuiverQuantitative API (free) — stock holdings and trades
- LDA API (free, no key) — lobbying filings, revolving door lobbyists
"""

import asyncio
import logging
import re
from typing import Optional

import httpx
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Entity, Relationship
from app.services.ingestion.lda_client import LDAClient

logger = logging.getLogger("enrich_senators")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

QUIVER_BASE = "https://api.quiverquant.com/beta"
QUIVER_TIMEOUT = 15.0


def _sanitize(s: str) -> str:
    if not isinstance(s, str):
        return str(s) if s is not None else ""
    return s.encode("ascii", errors="ignore").decode("ascii")


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


async def _get_or_create_entity(
    session: AsyncSession, slug: str, entity_type: str, name: str,
    summary: Optional[str] = None, metadata: Optional[dict] = None,
) -> Entity:
    """Get existing entity or create new one."""
    result = await session.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if entity:
        return entity
    entity = Entity(
        slug=slug,
        entity_type=entity_type,
        name=_sanitize(name),
        summary=_sanitize(summary) if summary else None,
        metadata_=metadata or {},
    )
    session.add(entity)
    await session.flush()
    return entity


async def _relationship_exists(
    session: AsyncSession, from_id, to_id, rel_type: str,
) -> bool:
    """Check if a relationship already exists."""
    result = await session.execute(
        select(Relationship).where(and_(
            Relationship.from_entity_id == from_id,
            Relationship.to_entity_id == to_id,
            Relationship.relationship_type == rel_type,
        )).limit(1)
    )
    return result.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# Stock Holdings from QuiverQuantitative
# ---------------------------------------------------------------------------

async def fetch_stock_holdings(bioguide_id: str) -> list[dict]:
    """Fetch stock holdings for a Congress member from QuiverQuantitative."""
    try:
        async with httpx.AsyncClient(timeout=QUIVER_TIMEOUT) as client:
            # QuiverQuantitative free endpoint for congress trading
            url = f"{QUIVER_BASE}/live/congresstrading"
            params = {"bioguide_id": bioguide_id}
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 403:
                logger.info("QuiverQuant requires API key — using fallback")
                return []
            else:
                logger.warning("QuiverQuant returned %d", resp.status_code)
                return []
    except Exception as e:
        logger.warning("QuiverQuant error: %s", e)
        return []


# ---------------------------------------------------------------------------
# LDA Lobbying Enrichment
# ---------------------------------------------------------------------------

async def enrich_with_lobbying(session: AsyncSession, official: Entity) -> int:
    """Find companies connected to this official and fetch their lobbying data.

    For each company that donated to or is held by the official:
    1. Query LDA API for that company's lobbying filings
    2. Extract bills lobbied on
    3. Create lobbies_on_behalf_of relationships (company -> bill)
    4. Extract lobbyists and check for revolving door (covered_official_position)

    Returns count of new relationships created.
    """
    lda = LDAClient()
    created = 0

    # Get companies connected to this official (donors + holdings)
    rels = await session.execute(
        select(Relationship, Entity).join(
            Entity, Entity.id == Relationship.to_entity_id
        ).where(and_(
            Relationship.from_entity_id == official.id,
            Relationship.relationship_type == "holds_stock",
        ))
    )
    stock_companies = [(r, e) for r, e in rels.all()]

    rels2 = await session.execute(
        select(Relationship, Entity).join(
            Entity, Entity.id == Relationship.from_entity_id
        ).where(and_(
            Relationship.to_entity_id == official.id,
            Relationship.relationship_type == "donated_to",
        ))
    )
    donor_companies = [(r, e) for r, e in rels2.all() if e.entity_type == "company"]

    companies = {}
    for _, entity in stock_companies + donor_companies:
        companies[entity.id] = entity

    if not companies:
        return 0

    # For top companies, fetch lobbying data
    for company in list(companies.values())[:15]:
        try:
            summary = await lda.fetch_client_lobbying_summary(company.name)
        except Exception as e:
            logger.warning("LDA error for %s: %s", company.name, e)
            continue

        if not summary or summary.get("filing_count", 0) == 0:
            continue

        # Store lobbying summary in company metadata
        company.metadata_ = {
            **(company.metadata_ or {}),
            "lobbying_summary": {
                "total_spend": summary["total_spend"],
                "filing_count": summary["filing_count"],
                "firms": summary["lobbying_firms"][:5],
                "top_issues": summary["issues"][:5],
            },
        }

        # Create lobbies_on_behalf_of relationships for specific bills
        for bill_ref in summary.get("bills_lobbied", []):
            bill_number = bill_ref.get("bill_number", "") if isinstance(bill_ref, dict) else str(bill_ref)
            if not bill_number:
                continue

            # Try to find this bill in our DB
            bill_slug_patterns = [
                _slugify(bill_number),
                bill_number.lower().replace(".", "-").replace(" ", "-"),
            ]
            bill_entity = None
            for pattern in bill_slug_patterns:
                result = await session.execute(
                    select(Entity).where(Entity.slug.ilike(f"%{pattern}%"))
                )
                bill_entity = result.scalar_one_or_none()
                if bill_entity:
                    break

            if bill_entity and not await _relationship_exists(
                session, company.id, bill_entity.id, "lobbies_on_behalf_of"
            ):
                rel = Relationship(
                    from_entity_id=company.id,
                    to_entity_id=bill_entity.id,
                    relationship_type="lobbies_on_behalf_of",
                    source_label="LDA Filing",
                    metadata_={"filing_count": summary["filing_count"]},
                )
                session.add(rel)
                created += 1

        # Check for revolving door lobbyists
        for lobbyist_name in summary.get("lobbyists", [])[:5]:
            if not lobbyist_name or len(lobbyist_name) < 3:
                continue
            lobbyist_slug = _slugify(lobbyist_name)
            # Don't create revolving door rels without evidence of former gov position
            # The LDA filings list covered positions — we'd need to parse those
            # For now, just ensure the lobbyist entity exists
            await _get_or_create_entity(
                session, lobbyist_slug, "person", lobbyist_name,
                metadata={"role": "lobbyist", "firms": summary["lobbying_firms"][:3]},
            )

        await asyncio.sleep(1)  # Be nice to the LDA API

    await session.commit()
    logger.info("Created %d lobbying relationships for %s", created, official.name)
    return created


# ---------------------------------------------------------------------------
# Main enrichment runner
# ---------------------------------------------------------------------------

async def enrich_all_senators() -> dict:
    """Enrich all senators with lobbying data from LDA.

    Returns summary of work done.
    """
    async with async_session() as session:
        # Get all senators
        result = await session.execute(
            select(Entity).where(
                Entity.entity_type == "person",
                Entity.metadata_["chamber"].astext == "Senate",
            )
        )
        senators = result.scalars().all()
        logger.info("Found %d senators to enrich", len(senators))

        total_created = 0
        enriched = 0
        errors = 0

        for i, senator in enumerate(senators):
            logger.info("[%d/%d] Enriching %s...", i + 1, len(senators), senator.name)
            try:
                count = await enrich_with_lobbying(session, senator)
                total_created += count
                enriched += 1
            except Exception as e:
                logger.error("Error enriching %s: %s", senator.name, e)
                errors += 1

        return {
            "senators_found": len(senators),
            "enriched": enriched,
            "errors": errors,
            "lobbying_relationships_created": total_created,
        }
