"""
Vote ingestion — scrape roll call votes from Senate.gov and House Clerk XML.

Creates voted_yes / voted_no relationships between officials and bill entities.
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Entity, Relationship

logger = logging.getLogger(__name__)

SENATE_VOTE_URL = (
    "https://www.senate.gov/legislative/LIS/roll_call_votes/"
    "vote{congress}{session}/vote_{congress}_{session}_{number}.xml"
)
HOUSE_VOTE_URL = "https://clerk.house.gov/evs/{year}/roll{number}.xml"
TIMEOUT = 30.0
DELAY = 1.0


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


async def _fetch_xml(url: str) -> ET.Element | None:
    """Fetch and parse XML from a URL, return root element or None."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            # Check if it's actually XML
            text = resp.text
            if not text.strip().startswith("<?xml"):
                return None
            return ET.fromstring(text)
    except Exception as exc:
        logger.debug("Failed to fetch %s: %s", url[:80], exc)
        return None


async def ingest_senate_votes(
    congress: int = 119,
    sessions: list[int] | None = None,
    max_votes_per_session: int = 200,
) -> dict:
    """Scrape Senate roll call votes and create relationships."""
    sessions = sessions or [1, 2]
    stats = {"votes_scraped": 0, "relationships_created": 0, "skipped_no_bill": 0}

    async with async_session() as session:
        # Pre-load bioguide -> entity mapping for senators
        result = await session.execute(
            select(Entity).where(
                Entity.entity_type == "person",
                Entity.metadata_["chamber"].astext.ilike("%senate%"),
            )
        )
        senators = {
            (e.metadata_ or {}).get("bioguide_id"): e
            for e in result.scalars().all()
            if (e.metadata_ or {}).get("bioguide_id")
        }
        # Also build name-based lookup for Senate (no bioguide in their XML)
        senator_by_name = {}
        for e in senators.values():
            name = e.name.lower().replace(",", "").strip()
            parts = name.split()
            if parts:
                senator_by_name[parts[0]] = e  # last name lookup

        # Pre-load bill entities for matching
        bill_result = await session.execute(
            select(Entity.slug, Entity.id).where(Entity.entity_type == "bill")
        )
        bill_lookup = {row[0]: row[1] for row in bill_result.all()}

        for sess in sessions:
            for vote_num in range(1, max_votes_per_session + 1):
                num_str = f"{vote_num:05d}"
                url = SENATE_VOTE_URL.format(
                    congress=congress, session=sess, number=num_str
                )
                await asyncio.sleep(DELAY)
                root = await _fetch_xml(url)
                if root is None:
                    break  # No more votes in this session

                stats["votes_scraped"] += 1
                # Extract vote info
                question = root.findtext("vote_question_text", "")
                doc_text = root.findtext("vote_document_text", "")
                vote_date_str = root.findtext("vote_date", "")

                # Try to match to a bill
                bill_id = _match_vote_to_bill(question, doc_text, bill_lookup, congress)
                if not bill_id:
                    stats["skipped_no_bill"] += 1
                    continue

                # Parse individual votes
                members = root.find("members")
                if members is None:
                    continue

                for member in members:
                    last_name = (member.findtext("last_name") or "").lower()
                    vote_cast = (member.findtext("vote_cast") or "").strip()

                    if vote_cast not in ("Yea", "Nay"):
                        continue  # Skip "Not Voting", "Present"

                    # Find senator entity
                    senator = senator_by_name.get(last_name)
                    if not senator:
                        continue

                    rel_type = "voted_yes" if vote_cast == "Yea" else "voted_no"

                    # Dedup check
                    existing = (await session.execute(
                        select(Relationship).where(
                            Relationship.from_entity_id == senator.id,
                            Relationship.to_entity_id == bill_id,
                            Relationship.relationship_type == rel_type,
                        ).limit(1)
                    )).scalar_one_or_none()

                    if not existing:
                        session.add(Relationship(
                            from_entity_id=senator.id,
                            to_entity_id=bill_id,
                            relationship_type=rel_type,
                            source_label="Senate.gov Roll Call",
                            source_url=url,
                            metadata_={
                                "vote_number": vote_num,
                                "congress": congress,
                                "session": sess,
                                "question": question[:200],
                            },
                        ))
                        stats["relationships_created"] += 1

                if stats["votes_scraped"] % 10 == 0:
                    await session.commit()
                    logger.info(
                        "[votes] Senate %d-%d: %d votes, %d relationships",
                        congress, sess, stats["votes_scraped"],
                        stats["relationships_created"],
                    )

        await session.commit()

    logger.info("[votes] Senate ingestion complete: %s", stats)
    return stats


async def ingest_house_votes(
    year: int = 2025,
    max_votes: int = 500,
) -> dict:
    """Scrape House roll call votes and create relationships."""
    stats = {"votes_scraped": 0, "relationships_created": 0, "skipped_no_bill": 0}

    async with async_session() as session:
        # Pre-load bioguide -> entity mapping for House members
        result = await session.execute(
            select(Entity).where(
                Entity.entity_type == "person",
                Entity.metadata_["chamber"].astext.ilike("%house%"),
            )
        )
        house_members = {}
        for e in result.scalars().all():
            bg = (e.metadata_ or {}).get("bioguide_id")
            if bg:
                house_members[bg] = e

        # Pre-load bill lookup
        bill_result = await session.execute(
            select(Entity.slug, Entity.id).where(Entity.entity_type == "bill")
        )
        bill_lookup = {row[0]: row[1] for row in bill_result.all()}

        congress = 119 if year >= 2025 else 118

        for vote_num in range(1, max_votes + 1):
            num_str = f"{vote_num:03d}"
            url = HOUSE_VOTE_URL.format(year=year, number=num_str)
            await asyncio.sleep(DELAY)
            root = await _fetch_xml(url)
            if root is None:
                break

            stats["votes_scraped"] += 1

            # Extract vote metadata
            meta_el = root.find("vote-metadata")
            if meta_el is None:
                continue

            legis_num = meta_el.findtext("legis-num", "")
            vote_question = meta_el.findtext("vote-question", "")
            vote_desc = meta_el.findtext("vote-desc", "")

            # Match to bill
            bill_id = _match_vote_to_bill(
                f"{legis_num} {vote_question}", vote_desc, bill_lookup, congress
            )
            if not bill_id:
                stats["skipped_no_bill"] += 1
                continue

            # Parse individual votes
            vote_data = root.find(".//vote-data")
            if vote_data is None:
                continue

            for recorded_vote in vote_data:
                legislator = recorded_vote.find("legislator")
                vote_el = recorded_vote.find("vote")
                if legislator is None or vote_el is None:
                    continue

                bioguide = legislator.get("name-id", "")
                vote_cast = (vote_el.text or "").strip()

                if vote_cast not in ("Yea", "Aye", "Nay", "No"):
                    continue

                member = house_members.get(bioguide)
                if not member:
                    continue

                rel_type = "voted_yes" if vote_cast in ("Yea", "Aye") else "voted_no"

                existing = (await session.execute(
                    select(Relationship).where(
                        Relationship.from_entity_id == member.id,
                        Relationship.to_entity_id == bill_id,
                        Relationship.relationship_type == rel_type,
                    ).limit(1)
                )).scalar_one_or_none()

                if not existing:
                    session.add(Relationship(
                        from_entity_id=member.id,
                        to_entity_id=bill_id,
                        relationship_type=rel_type,
                        source_label="House Clerk Roll Call",
                        source_url=url,
                        metadata_={
                            "vote_number": vote_num,
                            "congress": congress,
                            "year": year,
                            "question": vote_question[:200],
                        },
                    ))
                    stats["relationships_created"] += 1

            if stats["votes_scraped"] % 10 == 0:
                await session.commit()
                logger.info(
                    "[votes] House %d: %d votes, %d relationships",
                    year, stats["votes_scraped"], stats["relationships_created"],
                )

        await session.commit()

    logger.info("[votes] House ingestion complete: %s", stats)
    return stats


def _match_vote_to_bill(
    question: str, description: str, bill_lookup: dict, congress: int
) -> str | None:
    """Try to match a vote question/description to a bill entity in the DB."""
    text = f"{question} {description}"

    # Match patterns like H.R. 1234, S. 567, H.Res. 89
    patterns = [
        (r'H\.?\s*R\.?\s*(\d{1,5})', False),   # House bill
        (r'S\.?\s*(\d{1,5})', True),             # Senate bill
        (r'H\.?\s*Res\.?\s*(\d{1,5})', False),  # House resolution
        (r'S\.?\s*Res\.?\s*(\d{1,5})', True),   # Senate resolution
    ]

    for pattern, is_senate in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            number = match.group(1)
            if is_senate:
                slug = f"s-{number}-{congress}"
            else:
                slug = f"{number}-{congress}"
            bill_id = bill_lookup.get(slug)
            if bill_id:
                return bill_id

    return None


async def run_full_vote_ingestion() -> str:
    """Run both Senate and House vote ingestion."""
    logger.info("[votes] Starting full vote ingestion")

    senate_stats = await ingest_senate_votes(congress=119, sessions=[1, 2])
    house_stats_2025 = await ingest_house_votes(year=2025)
    house_stats_2026 = await ingest_house_votes(year=2026)

    summary = (
        f"Vote ingestion complete. "
        f"Senate: {senate_stats['votes_scraped']} votes, {senate_stats['relationships_created']} rels. "
        f"House 2025: {house_stats_2025['votes_scraped']} votes, {house_stats_2025['relationships_created']} rels. "
        f"House 2026: {house_stats_2026['votes_scraped']} votes, {house_stats_2026['relationships_created']} rels."
    )
    logger.info(summary)
    return summary
