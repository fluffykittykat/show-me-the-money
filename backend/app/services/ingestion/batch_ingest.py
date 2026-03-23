"""Batch ingestion of all 535 Congress members from Congress.gov and FEC APIs."""

import asyncio
import gc
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
import psutil
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import async_session
from app.models import DataSource, Entity, IngestionJob, Relationship
from app.services.ingestion.congress_client import CongressClient
from app.services.ingestion.fec_client import FECClient
from app.services.rate_limiter import SmartRateLimiter

logger = logging.getLogger("batch_ingest")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

# Module-level state for tracking running tasks
_running_tasks: dict[str, asyncio.Task] = {}

BATCH_SIZE = 10
CONGRESS_API_BASE = "https://api.congress.gov/v3"
TIMEOUT = 30.0

_STATE_ABBREV = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
    "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "District of Columbia": "DC", "American Samoa": "AS", "Guam": "GU",
    "Northern Mariana Islands": "MP", "Puerto Rico": "PR",
    "U.S. Virgin Islands": "VI",
}


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


def _generate_fallback_briefing(member_data: dict) -> str:
    """Generate a fallback briefing from available member data (no AI needed)."""
    name = member_data.get("name", "Unknown")
    party = member_data.get("party", "Unknown")
    state = member_data.get("state", "Unknown")
    chamber = member_data.get("chamber", "")

    role = "Senator" if chamber == "Senate" else "Representative" if chamber == "House of Representatives" else "Member of Congress"

    # Extract committee names from member_detail
    member_detail = member_data.get("member_detail", {})
    committees = []
    if isinstance(member_detail, dict):
        committees = member_detail.get("committees", [])
        if not committees:
            terms = member_detail.get("terms", [])
            if isinstance(terms, dict):
                terms = terms.get("item", [])
            for term in (terms if isinstance(terms, list) else []):
                if isinstance(term, dict):
                    committees.extend(term.get("committees", []))
    comm_names = [c.get("name", c) if isinstance(c, dict) else str(c) for c in committees[:5]]
    committee_str = ", ".join(comm_names) if comm_names else "no listed committee assignments"

    para1 = f"{name} ({party}-{state}) serves as a United States {role} with assignments on {committee_str}."

    # Campaign finance
    fec = member_data.get("fec_data") or {}
    totals = fec.get("totals", {})
    total_raised = totals.get("receipts", 0) or 0
    total_spent = totals.get("disbursements", 0) or 0
    donors = fec.get("top_donors", [])

    if total_raised or total_spent:
        donor_str = ""
        if donors:
            top_names = ", ".join(
                d.get("contributor_name", "Unknown") for d in donors[:5]
            )
            donor_str = f" Top contributors include {top_names}."
        para2 = f"Campaign finance records show ${total_raised:,.2f} raised and ${total_spent:,.2f} spent.{donor_str}"
    else:
        para2 = "No campaign finance data is currently available for this member."

    # Legislative record
    sponsored = member_data.get("sponsored_bills", [])
    cosponsored = member_data.get("cosponsored_bills", [])
    if sponsored:
        bill_titles = "; ".join(b.get("title", "Untitled") for b in sponsored[:3])
        para3 = f"Sponsored {len(sponsored)} bills including: {bill_titles}."
    else:
        para3 = "No sponsored legislation is recorded in the available data."
    if cosponsored:
        para3 += f" Also cosponsored {len(cosponsored)} bills."

    # Votes
    votes = member_data.get("votes", [])
    if votes:
        para4 = f"Recent voting record includes {len(votes)} recorded votes."
    else:
        para4 = "No recent voting data is available."

    return f"{para1}\n\n{para2}\n\n{para3}\n\n{para4}"


async def _fetch_all_current_members(api_key: str, limiter: SmartRateLimiter) -> list:
    """Fetch all current Congress members via two paginated requests."""
    all_members = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for offset in (0, 250):
            url = (
                f"{CONGRESS_API_BASE}/member"
                f"?currentMember=true&limit=250&offset={offset}"
                f"&api_key={api_key}&format=json"
            )
            async with limiter.acquire("congress_gov"):
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                members = data.get("members", [])
                all_members.extend(members)
                logger.info(
                    "Fetched %d members (offset=%d, total=%d)",
                    len(members), offset, len(all_members),
                )
    return all_members


async def _process_member(
    member_summary: dict,
    congress_client: CongressClient,
    fec_client: Optional[FECClient],
    limiter: SmartRateLimiter,
    force: bool = False,
) -> dict:
    """Process a single Congress member: fetch details, legislation, FEC data.

    Returns a dict with all fetched data, or raises on unrecoverable error.
    """
    bioguide_id = member_summary.get("bioguideId", "")
    name = member_summary.get("name", "")
    state = member_summary.get("state", "")
    party = member_summary.get("partyName", "")
    chamber = member_summary.get("terms", {})

    # Determine chamber from terms
    terms_item = chamber.get("item", []) if isinstance(chamber, dict) else []
    member_chamber = ""
    if terms_item:
        last_term = terms_item[-1] if isinstance(terms_item, list) else terms_item
        if isinstance(last_term, dict):
            member_chamber = last_term.get("chamber", "")

    slug = _slugify(name)
    result = {
        "bioguide_id": bioguide_id,
        "name": name,
        "slug": slug,
        "state": state,
        "party": party,
        "chamber": member_chamber,
        "member_detail": {},
        "sponsored_bills": [],
        "cosponsored_bills": [],
        "votes": [],
        "fec_data": None,
    }

    # Skip if already ingested (unless force)
    if not force:
        async with async_session() as session:
            existing = await session.execute(
                select(DataSource).join(Entity).where(
                    Entity.slug == slug,
                    DataSource.source_type == "congress_gov",
                )
            )
            if existing.scalars().first() is not None:
                logger.info("Skipping %s (already ingested)", name)
                result["skipped"] = True
                return result

    # Fetch member detail
    async with limiter.acquire("congress_gov"):
        try:
            result["member_detail"] = await congress_client.fetch_member(bioguide_id)
        except Exception as exc:
            logger.warning("Failed to fetch member detail for %s: %s", name, exc)

    # Fetch sponsored legislation
    async with limiter.acquire("congress_gov"):
        try:
            result["sponsored_bills"] = await congress_client.fetch_sponsored_legislation(
                bioguide_id, limit=50
            )
        except Exception as exc:
            logger.warning("Failed to fetch sponsored bills for %s: %s", name, exc)

    # Fetch cosponsored legislation
    async with limiter.acquire("congress_gov"):
        try:
            result["cosponsored_bills"] = await congress_client.fetch_cosponsored_legislation(
                bioguide_id, limit=50
            )
        except Exception as exc:
            logger.warning("Failed to fetch cosponsored bills for %s: %s", name, exc)

    # Note: Congress.gov API v3 does not support /member/{id}/votes endpoint.
    # Votes would require parsing Senate.gov XML feeds — skipped for now.

    # Try to resolve FEC data
    if fec_client:
        try:
            # Convert "Last, First M." to "First Last" for FEC search
            fec_search_name = name
            if "," in name:
                parts = name.split(",", 1)
                fec_search_name = f"{parts[1].strip()} {parts[0].strip()}"

            # Convert full state name to abbreviation for FEC API
            fec_state = _STATE_ABBREV.get(state, state) if len(state) > 2 else state

            async with limiter.acquire("fec"):
                fec_candidate = await fec_client.search_candidate(
                    fec_search_name, state=fec_state
                )
            if fec_candidate:
                candidate_id = fec_candidate.get("candidate_id", "")
                committees = fec_candidate.get("principal_committees", [])
                committee_id = ""
                if committees:
                    committee_id = committees[0].get("committee_id", "")

                if candidate_id:
                    async with limiter.acquire("fec"):
                        try:
                            totals = await fec_client.fetch_candidate_totals(
                                candidate_id
                            )
                        except Exception:
                            totals = {}

                    donors = []
                    if committee_id:
                        async with limiter.acquire("fec"):
                            try:
                                donors = await fec_client.fetch_top_contributors(
                                    committee_id, per_page=20
                                )
                            except Exception:
                                donors = []

                    result["fec_data"] = {
                        "candidate_id": candidate_id,
                        "committee_id": committee_id,
                        "totals": totals,
                        "top_donors": donors,
                    }
        except Exception as exc:
            logger.warning("FEC lookup failed for %s: %s", name, exc)

    return result


async def _upsert_member_data(member_data: dict) -> None:
    """Upsert a member's entity and data source records."""
    if member_data.get("skipped"):
        return

    slug = member_data["slug"]
    name = member_data["name"]
    bioguide_id = member_data["bioguide_id"]

    # All Congress members are entity_type "person" — chamber is in metadata
    entity_type = "person"

    metadata = {
        "bioguide_id": bioguide_id,
        "state": member_data.get("state", ""),
        "party": member_data.get("party", ""),
        "chamber": member_data.get("chamber", ""),
        "sponsored_bill_count": len(member_data.get("sponsored_bills", [])),
        "cosponsored_bill_count": len(member_data.get("cosponsored_bills", [])),
    }

    if member_data.get("fec_data"):
        fec = member_data["fec_data"]
        metadata["fec_candidate_id"] = fec.get("candidate_id", "")
        metadata["fec_committee_id"] = fec.get("committee_id", "")
        totals = fec.get("totals", {})
        if totals:
            metadata["total_receipts"] = totals.get("receipts", 0)
            metadata["total_disbursements"] = totals.get("disbursements", 0)
            metadata["individual_contributions"] = totals.get(
                "individual_contributions", 0
            )

    party = member_data.get("party", "")
    state = member_data.get("state", "")
    chamber = member_data.get("chamber", "")

    # Generate a descriptive summary
    role = "Senator" if chamber == "Senate" else "Representative" if chamber == "House of Representatives" else "Member of Congress"
    summary = f"United States {role} from {state} ({party[0] if party else '?'})" if party and state else None

    # Generate a fallback briefing from available data
    briefing = _generate_fallback_briefing(member_data)
    if briefing:
        metadata["mock_briefing"] = briefing

    logger.info("Storing member: %s (%s, %s)", name, entity_type, slug)
    async with async_session() as session:
        async with session.begin():
            # Upsert entity
            # Use ORM upsert to avoid metadata column name clash
            existing = (await session.execute(
                select(Entity).where(Entity.slug == slug)
            )).scalar_one_or_none()

            safe_name = _ascii_safe(name)
            safe_summary = _ascii_safe(summary) if summary else None
            safe_metadata = _ascii_safe(metadata)

            if existing:
                existing.name = safe_name
                existing.entity_type = entity_type
                existing.summary = safe_summary
                existing.metadata_ = safe_metadata
            else:
                existing = Entity(
                    slug=slug,
                    entity_type=entity_type,
                    name=safe_name,
                    summary=safe_summary,
                    metadata_=safe_metadata,
                )
                session.add(existing)
            await session.flush()

            # Get the entity id
            entity_row = await session.execute(
                select(Entity.id).where(Entity.slug == slug)
            )
            entity_id = entity_row.scalar_one()

            # Upsert data source for congress_gov
            raw_payload = {
                "member_detail": member_data.get("member_detail", {}),
                "sponsored_bills_count": len(member_data.get("sponsored_bills", [])),
                "cosponsored_bills_count": len(member_data.get("cosponsored_bills", [])),
            }

            ds_stmt = pg_insert(DataSource).values(
                entity_id=entity_id,
                source_type="congress_gov",
                external_id=bioguide_id,
                raw_payload=_ascii_safe(raw_payload),
                fetched_at=datetime.now(timezone.utc),
            )
            # If data_source already exists for this entity+source_type, update it
            # There's no unique constraint on (entity_id, source_type), so just insert
            await session.execute(ds_stmt)

            # If FEC data exists, add a data source for it
            if member_data.get("fec_data"):
                fec_ds_stmt = pg_insert(DataSource).values(
                    entity_id=entity_id,
                    source_type="fec",
                    external_id=member_data["fec_data"].get("candidate_id", ""),
                    raw_payload=_ascii_safe(member_data["fec_data"]),
                    fetched_at=datetime.now(timezone.utc),
                )
                await session.execute(fec_ds_stmt)

            # ---- Create bill entities and relationships ----
            for bill_list, rel_type in [
                (member_data.get("sponsored_bills", []), "sponsored"),
                (member_data.get("cosponsored_bills", []), "cosponsored"),
            ]:
                for bill in bill_list[:50]:  # Cap at 50 per type
                    bill_number = bill.get("number", "") or ""
                    bill_title = bill.get("title", "") or bill_number
                    bill_congress = bill.get("congress", "")
                    if not bill_title:
                        continue
                    bill_slug = _slugify(f"{bill_number}-{bill_congress}" if bill_number else bill_title)
                    if not bill_slug:
                        continue

                    # Upsert bill entity
                    bill_ent = (await session.execute(
                        select(Entity).where(Entity.slug == bill_slug)
                    )).scalar_one_or_none()
                    if not bill_ent:
                        bill_ent = Entity(
                            slug=bill_slug,
                            entity_type="bill",
                            name=_ascii_safe(bill_title)[:500],
                            summary=_ascii_safe(bill.get("latestAction", {}).get("text", ""))[:500] if bill.get("latestAction") else None,
                            metadata_=_ascii_safe({
                                "bill_number": bill_number,
                                "congress": bill_congress,
                                "policy_area": bill.get("policyArea", {}).get("name", "") if bill.get("policyArea") else "",
                                "status": bill.get("latestAction", {}).get("text", "")[:200] if bill.get("latestAction") else "",
                                "introduced_date": bill.get("introducedDate", ""),
                                "url": bill.get("url", ""),
                            }),
                        )
                        session.add(bill_ent)
                        await session.flush()

                    # Create member -> bill relationship (avoid duplicates)
                    existing_rel = (await session.execute(
                        select(Relationship).where(
                            Relationship.from_entity_id == entity_id,
                            Relationship.to_entity_id == bill_ent.id,
                            Relationship.relationship_type == rel_type,
                        ).limit(1)
                    )).scalar_one_or_none()
                    if not existing_rel:
                        session.add(Relationship(
                            from_entity_id=entity_id,
                            to_entity_id=bill_ent.id,
                            relationship_type=rel_type,
                            source_label="Congress.gov",
                            source_url=bill.get("url", ""),
                        ))

            # ---- Create donor entities and relationships from FEC data ----
            fec = member_data.get("fec_data") or {}
            for donor in fec.get("top_donors", [])[:30]:
                donor_name = _ascii_safe(donor.get("contributor_name", "") or "")
                if not donor_name or len(donor_name) < 2:
                    continue
                donor_slug = _slugify(donor_name)
                if not donor_slug:
                    continue
                amount = donor.get("total", 0) or donor.get("contribution_receipt_amount", 0) or 0

                # Detect PACs vs individuals
                name_upper = donor_name.upper()
                is_pac = any(kw in name_upper for kw in [
                    "PAC", "FUND", "VICTORY", "COMMITTEE", "DSCC", "DCCC",
                    "EMILY", "ACTION", "SENATE", "HOUSE", " FUND",
                ])
                donor_type = "pac" if is_pac else "person"

                donor_ent = (await session.execute(
                    select(Entity).where(Entity.slug == donor_slug)
                )).scalar_one_or_none()
                if not donor_ent:
                    donor_ent = Entity(
                        slug=donor_slug,
                        entity_type=donor_type,
                        name=donor_name,
                        metadata_=_ascii_safe({
                            "donor_type": "pac" if is_pac else "individual",
                        }),
                    )
                    session.add(donor_ent)
                    await session.flush()

                # Create donor -> member relationship
                existing_rel = (await session.execute(
                    select(Relationship).where(
                        Relationship.from_entity_id == donor_ent.id,
                        Relationship.to_entity_id == entity_id,
                        Relationship.relationship_type == "donated_to",
                    ).limit(1)
                )).scalar_one_or_none()
                if not existing_rel:
                    amount_cents = int(float(amount) * 100) if amount else 0
                    session.add(Relationship(
                        from_entity_id=donor_ent.id,
                        to_entity_id=entity_id,
                        relationship_type="donated_to",
                        amount_usd=amount_cents,
                        source_label="FEC",
                    ))

            # ---- Create committee entities and relationships ----
            member_detail = member_data.get("member_detail", {})
            committees = []
            if isinstance(member_detail, dict):
                # Congress.gov API v3 may have committees in different locations
                committees = member_detail.get("committees", [])
                if not committees:
                    terms = member_detail.get("terms", [])
                    if isinstance(terms, dict):
                        terms = terms.get("item", [])
                    for term in (terms if isinstance(terms, list) else []):
                        if isinstance(term, dict):
                            committees.extend(term.get("committees", []))

            for comm in committees[:10]:  # Cap at 10 committees
                comm_name = ""
                if isinstance(comm, dict):
                    comm_name = comm.get("name", "")
                elif isinstance(comm, str):
                    comm_name = comm
                if not comm_name or len(comm_name) < 3:
                    continue
                comm_slug = _slugify(comm_name)
                if not comm_slug:
                    continue

                comm_ent = (await session.execute(
                    select(Entity).where(Entity.slug == comm_slug)
                )).scalar_one_or_none()
                if not comm_ent:
                    comm_ent = Entity(
                        slug=comm_slug,
                        entity_type="committee",
                        name=_ascii_safe(comm_name)[:500],
                        metadata_=_ascii_safe({
                            "chamber": member_data.get("chamber", ""),
                            "code": comm.get("code", "") if isinstance(comm, dict) else "",
                        }),
                    )
                    session.add(comm_ent)
                    await session.flush()

                # Create member -> committee relationship (avoid duplicates)
                existing_rel = (await session.execute(
                    select(Relationship).where(
                        Relationship.from_entity_id == entity_id,
                        Relationship.to_entity_id == comm_ent.id,
                        Relationship.relationship_type == "committee_member",
                    ).limit(1)
                )).scalar_one_or_none()
                if not existing_rel:
                    session.add(Relationship(
                        from_entity_id=entity_id,
                        to_entity_id=comm_ent.id,
                        relationship_type="committee_member",
                        source_label="Congress.gov",
                    ))

            # ---- Create vote entities and relationships ----
            for vote in member_data.get("votes", [])[:20]:  # Cap at 20 votes
                question = vote.get("question", "") or vote.get("description", "")
                if not question:
                    continue
                roll_num = vote.get("rollNumber", "")
                congress_num = vote.get("congress", "")
                session_num = vote.get("session", "")
                vote_slug = _slugify(f"vote-{roll_num}-{congress_num}-{session_num}")
                if not vote_slug or len(vote_slug) < 3:
                    continue

                vote_ent = (await session.execute(
                    select(Entity).where(Entity.slug == vote_slug)
                )).scalar_one_or_none()
                if not vote_ent:
                    vote_ent = Entity(
                        slug=vote_slug,
                        entity_type="bill",
                        name=_ascii_safe(question)[:500],
                        metadata_=_ascii_safe({
                            "congress": congress_num,
                            "session": session_num,
                            "rollNumber": roll_num,
                            "result": vote.get("result", ""),
                            "date": vote.get("date", ""),
                        }),
                    )
                    session.add(vote_ent)
                    await session.flush()

                # Determine vote type
                member_vote = str(vote.get("memberVote", vote.get("vote", "Yes")))
                if member_vote.lower() in ("yes", "yea", "aye"):
                    rel_type = "voted_yes"
                elif member_vote.lower() in ("no", "nay"):
                    rel_type = "voted_no"
                else:
                    rel_type = "voted_present"

                existing_rel = (await session.execute(
                    select(Relationship).where(
                        Relationship.from_entity_id == entity_id,
                        Relationship.to_entity_id == vote_ent.id,
                        Relationship.relationship_type == rel_type,
                    ).limit(1)
                )).scalar_one_or_none()
                if not existing_rel:
                    session.add(Relationship(
                        from_entity_id=entity_id,
                        to_entity_id=vote_ent.id,
                        relationship_type=rel_type,
                        source_label="Congress.gov",
                    ))

            # Hidden connections (revolving door, family, outside income) are
            # no longer generated from mock data. When real LDA/eFD APIs are
            # integrated, they will be ingested here.


async def _ingest_hidden_connections(session, entity_id: str, name: str, state: str) -> None:
    """Create hidden connection entities and relationships from mock clients."""
    from app.services.ingestion.revolving_door_client import RevolvingDoorClient
    from app.services.ingestion.family_connections_client import FamilyConnectionsClient
    from app.services.ingestion.outside_income_client import OutsideIncomeClient

    # --- Revolving Door ---
    rd = RevolvingDoorClient()
    registrations = await rd.fetch_revolving_door_registrations(name)
    for reg in registrations[:3]:
        for lobbyist_info in reg.get("lobbyists", []):
            lobbyist_name = lobbyist_info.get("name", "")
            if not lobbyist_name:
                continue
            lobbyist_slug = _slugify(lobbyist_name)
            if not lobbyist_slug:
                continue

            lobbyist_ent = (await session.execute(
                select(Entity).where(Entity.slug == lobbyist_slug)
            )).scalar_one_or_none()
            if not lobbyist_ent:
                lobbyist_ent = Entity(
                    slug=lobbyist_slug,
                    entity_type="person",
                    name=_ascii_safe(lobbyist_name)[:500],
                    metadata_=_ascii_safe({
                        "role": "lobbyist",
                        "former_position": lobbyist_info.get("covered_official_position", ""),
                        "current_employer": reg.get("registrant", {}).get("name", ""),
                        "clients": [reg.get("client", {}).get("name", "")],
                    }),
                )
                session.add(lobbyist_ent)
                await session.flush()

            existing_rel = (await session.execute(
                select(Relationship).where(
                    Relationship.from_entity_id == lobbyist_ent.id,
                    Relationship.to_entity_id == entity_id,
                    Relationship.relationship_type == "revolving_door_lobbyist",
                ).limit(1)
            )).scalar_one_or_none()
            if not existing_rel:
                session.add(Relationship(
                    from_entity_id=lobbyist_ent.id,
                    to_entity_id=entity_id,
                    relationship_type="revolving_door_lobbyist",
                    amount_usd=int(reg.get("income", 0) * 100) if reg.get("income") else None,
                    source_label="LDA Senate",
                    source_url=reg.get("url", ""),
                    metadata_=_ascii_safe({
                        "former_position": lobbyist_info.get("covered_official_position", ""),
                        "current_role": "lobbyist",
                        "current_employer": reg.get("registrant", {}).get("name", ""),
                        "lobbies_committee": reg.get("specific_lobbying_issues", ""),
                        "clients": [reg.get("client", {}).get("name", "")],
                    }),
                ))

    # --- Family Connections ---
    fc = FamilyConnectionsClient()
    family_items = await fc.fetch_family_income(name)
    for item in family_items[:3]:
        employer_name = item.get("employer", "")
        if not employer_name:
            continue
        employer_slug = _slugify(employer_name)
        if not employer_slug:
            continue

        employer_ent = (await session.execute(
            select(Entity).where(Entity.slug == employer_slug)
        )).scalar_one_or_none()
        if not employer_ent:
            employer_ent = Entity(
                slug=employer_slug,
                entity_type="company",
                name=_ascii_safe(employer_name)[:500],
            )
            session.add(employer_ent)
            await session.flush()

        rel_type = "spouse_income_from" if item.get("relationship") == "spouse" else "family_employed_by"
        existing_rel = (await session.execute(
            select(Relationship).where(
                Relationship.from_entity_id == entity_id,
                Relationship.to_entity_id == employer_ent.id,
                Relationship.relationship_type == rel_type,
            ).limit(1)
        )).scalar_one_or_none()
        if not existing_rel:
            income = item.get("income_amount", 0) or 0
            session.add(Relationship(
                from_entity_id=entity_id,
                to_entity_id=employer_ent.id,
                relationship_type=rel_type,
                amount_usd=int(income * 100) if income else None,
                source_label="Senate eFD",
                source_url=item.get("source_url", ""),
                metadata_=_ascii_safe({
                    "family_member": item.get("family_member", ""),
                    "relationship_to_official": item.get("relationship", "family member"),
                    "role": item.get("position", ""),
                    "annual_income": income,
                }),
            ))

    # --- Outside Income ---
    oi = OutsideIncomeClient()
    income_items = await oi.fetch_outside_income(name)
    for item in income_items[:3]:
        payer_name = item.get("payer", "")
        if not payer_name:
            continue
        payer_slug = _slugify(payer_name)
        if not payer_slug:
            continue

        payer_ent = (await session.execute(
            select(Entity).where(Entity.slug == payer_slug)
        )).scalar_one_or_none()
        if not payer_ent:
            payer_ent = Entity(
                slug=payer_slug,
                entity_type="organization",
                name=_ascii_safe(payer_name)[:500],
                metadata_=_ascii_safe({
                    "industry": item.get("payer_industry", ""),
                }),
            )
            session.add(payer_ent)
            await session.flush()

        income_type = item.get("income_type", "outside_income")
        if income_type == "speaking_fee":
            rel_type = "speaking_fee_from"
        elif income_type == "book_advance":
            rel_type = "book_deal_with"
        else:
            rel_type = "outside_income_from"

        existing_rel = (await session.execute(
            select(Relationship).where(
                Relationship.from_entity_id == entity_id,
                Relationship.to_entity_id == payer_ent.id,
                Relationship.relationship_type == rel_type,
            ).limit(1)
        )).scalar_one_or_none()
        if not existing_rel:
            amount = item.get("amount", 0) or 0
            session.add(Relationship(
                from_entity_id=entity_id,
                to_entity_id=payer_ent.id,
                relationship_type=rel_type,
                amount_usd=int(amount * 100) if amount else None,
                amount_label=f"${amount:,.0f}" if amount else None,
                source_label="Senate eFD",
                source_url=item.get("source_url", ""),
                metadata_=_ascii_safe({
                    "income_type": income_type,
                    "description": item.get("description", ""),
                    "date": item.get("date", ""),
                    "payer_industry": item.get("payer_industry", ""),
                    "is_lobbying_org": item.get("is_lobbying_org", False),
                }),
            ))


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


async def run_batch_ingestion(force: bool = False) -> uuid.UUID:
    """Run batch ingestion for all current Congress members.

    Creates an IngestionJob record and processes members in batches.
    Returns the job ID.
    """
    # Try env vars first, then fall back to DB config
    congress_api_key = os.getenv("CONGRESS_GOV_API_KEY", "")
    fec_api_key = os.getenv("FEC_API_KEY", "")

    if not congress_api_key:
        from app.services.config_service import get_config_value
        async with async_session() as cfg_session:
            congress_api_key = await get_config_value(cfg_session, "CONGRESS_GOV_API_KEY") or ""
            fec_api_key = fec_api_key or await get_config_value(cfg_session, "FEC_API_KEY") or ""

    if not congress_api_key:
        raise ValueError("CONGRESS_GOV_API_KEY not set (env var or DB config)")

    # Create ingestion job
    job_id: uuid.UUID
    async with async_session() as session:
        async with session.begin():
            job = IngestionJob(
                job_type="batch_congress_members",
                status="in_progress",
                started_at=datetime.now(timezone.utc),
                metadata_={"force": force},
            )
            session.add(job)
            await session.flush()
            job_id = job.id

    logger.info("Created ingestion job %s", job_id)

    limiter = SmartRateLimiter()
    congress_client = CongressClient(congress_api_key)
    fec_client = FECClient(fec_api_key) if fec_api_key else None

    errors: list[dict] = []

    try:
        # Fetch all current members
        all_members = await _fetch_all_current_members(congress_api_key, limiter)
        total = len(all_members)
        logger.info("Found %d current Congress members", total)

        # Update job with total count
        await _update_job_progress(job_id, 0, total, errors)

        processed = 0

        # Process in batches
        for batch_start in range(0, total, BATCH_SIZE):
            batch = all_members[batch_start : batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            logger.info(
                "Processing batch %d (%d-%d of %d)",
                batch_num, batch_start + 1, batch_start + len(batch), total,
            )

            # Process each member in the batch concurrently
            tasks = []
            for member_summary in batch:
                task = _process_member(
                    member_summary, congress_client, fec_client, limiter, force=force
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                member_name = batch[i].get("name", "unknown")
                if isinstance(result, Exception):
                    error_entry = {
                        "member": member_name,
                        "error": str(result),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    errors.append(error_entry)
                    logger.error("Error processing %s: %s", member_name, result)
                else:
                    # Upsert the member data
                    try:
                        await _upsert_member_data(result)
                    except Exception as exc:
                        error_entry = {
                            "member": member_name,
                            "error": f"Upsert failed: {exc}",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        errors.append(error_entry)
                        logger.error("Upsert failed for %s: %s", member_name, exc)

                processed += 1

            # Update progress
            await _update_job_progress(job_id, processed, total, errors)

            # Memory safety: log and collect every 50 members
            if processed % 50 == 0 or processed == total:
                process = psutil.Process()
                mem_mb = process.memory_info().rss / (1024 * 1024)
                logger.info(
                    "Progress: %d/%d members | Memory: %.1f MB | Errors: %d",
                    processed, total, mem_mb, len(errors),
                )
                gc.collect()

        # Mark job as completed
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
                        errors=errors,
                        metadata_={
                            "force": force,
                            "rate_limiter_stats": limiter.stats(),
                        },
                    )
                )

        logger.info("Batch ingestion completed: %d/%d members", processed, total)

    except Exception as exc:
        logger.error("Batch ingestion failed: %s", exc)
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
    finally:
        # Clean up task reference
        task_key = str(job_id)
        _running_tasks.pop(task_key, None)

    return job_id


def start_batch_ingestion(force: bool = False) -> uuid.UUID:
    """Start batch ingestion as a background asyncio task.

    Returns a job_id that can be used to query status.
    The task is tracked in the module-level _running_tasks dict.
    """
    # Generate job ID up front so we can return it immediately
    job_id = uuid.uuid4()

    async def _wrapper():
        return await run_batch_ingestion(force=force)

    task = asyncio.create_task(_wrapper())
    _running_tasks[str(job_id)] = task
    logger.info("Started batch ingestion task (tracking id: %s)", job_id)
    return job_id


def get_running_tasks() -> dict[str, str]:
    """Return status of all tracked tasks."""
    result = {}
    for task_id, task in list(_running_tasks.items()):
        if task.done():
            if task.exception():
                result[task_id] = f"failed: {task.exception()}"
            else:
                result[task_id] = "completed"
            # Clean up finished tasks
            _running_tasks.pop(task_id, None)
        else:
            result[task_id] = "running"
    return result


async def mark_stale_jobs_interrupted() -> int:
    """Mark any in_progress ingestion jobs as 'interrupted'.

    Called on startup to clean up jobs that were running when the server stopped.
    Returns the number of jobs marked.
    """
    async with async_session() as session:
        async with session.begin():
            result = await session.execute(
                update(IngestionJob)
                .where(IngestionJob.status == "in_progress")
                .values(
                    status="interrupted",
                    completed_at=datetime.now(timezone.utc),
                )
            )
            return result.rowcount
