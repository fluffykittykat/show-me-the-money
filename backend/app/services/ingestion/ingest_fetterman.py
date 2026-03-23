"""
Orchestration script: fetches real data from Congress.gov, FEC, and Senate eFD,
then merges it into the database for John Fetterman.

Usage:
    cd /home/mansona/workspace/jerry-maguire/backend
    python -m app.services.ingestion.ingest_fetterman
"""

import asyncio
import json
import os
import re
from datetime import date, datetime

from sqlalchemy import delete, select, text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

# Ensure env vars are loaded
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

from app.database import async_session, engine
from app.models import Base, DataSource, Entity, Relationship


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BIOGUIDE_ID = "F000479"
FEC_CANDIDATE_ID = "S6PA00274"
FEC_COMMITTEE_ID = "C00765800"
SLUG = "john-fetterman"

CONGRESS_API_KEY = os.getenv("CONGRESS_GOV_API_KEY", "")
FEC_API_KEY = os.getenv("FEC_API_KEY", "")


def slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    s = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    # Collapse multiple dashes
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
            out[k] = [sanitize_dict(i) if isinstance(i, dict) else sanitize_str(i) if isinstance(i, str) else i for i in v]
        else:
            out[k] = v
    return out


def parse_date(d) -> date | None:
    if d is None:
        return None
    if isinstance(d, date):
        return d
    try:
        return date.fromisoformat(d[:10])
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Phase 1: Fetch data from APIs (writes to /tmp JSON files)
# ---------------------------------------------------------------------------
async def fetch_all_data():
    """Fetch data from Congress.gov, FEC, and eFD in parallel."""
    from app.services.ingestion.congress_client import CongressClient
    from app.services.ingestion.fec_client import FECClient
    from app.services.ingestion.efd_client import EFDClient

    congress = CongressClient(CONGRESS_API_KEY)
    fec = FECClient(FEC_API_KEY)
    efd = EFDClient()

    print("=" * 60)
    print("PHASE 1: Fetching data from live APIs")
    print("=" * 60)

    # Run all three fetches concurrently
    congress_data, fec_data, efd_data = await asyncio.gather(
        congress.fetch_all(BIOGUIDE_ID),
        fec.fetch_all(FEC_CANDIDATE_ID, FEC_COMMITTEE_ID),
        efd.fetch_all(BIOGUIDE_ID, CONGRESS_API_KEY),
        return_exceptions=True,
    )

    # Handle exceptions gracefully
    if isinstance(congress_data, Exception):
        print(f"ERROR fetching Congress data: {congress_data}")
        congress_data = {"member": {}, "sponsored_bills": [], "cosponsored_bills": [], "committees": []}
    if isinstance(fec_data, Exception):
        print(f"ERROR fetching FEC data: {fec_data}")
        fec_data = {"totals": {}, "top_contributors": [], "pac_contributions": []}
    if isinstance(efd_data, Exception):
        print(f"ERROR fetching eFD data: {efd_data}")
        efd_data = {"assets": [], "transactions": [], "votes": []}

    return congress_data, fec_data, efd_data


# ---------------------------------------------------------------------------
# Phase 2: Generate AI briefing
# ---------------------------------------------------------------------------
async def generate_briefing(congress_data: dict, fec_data: dict, efd_data: dict) -> str:
    """Generate AI briefing from collected data."""
    from app.services.ingestion.briefing_generator import BriefingGenerator

    print("\n" + "=" * 60)
    print("PHASE 2: Generating AI briefing")
    print("=" * 60)

    generator = BriefingGenerator()
    return await generator.generate(congress_data, fec_data, efd_data)


# ---------------------------------------------------------------------------
# Phase 3: Merge into database
# ---------------------------------------------------------------------------
async def upsert_entity(session: AsyncSession, slug: str, entity_type: str,
                        name: str, summary: str | None = None,
                        metadata: dict | None = None) -> Entity:
    """Insert or update an entity by slug."""
    # Sanitize all strings for SQL_ASCII database and enforce column limits
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
            entity.metadata_ = sanitize_dict({**entity.metadata_, **metadata})
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


async def clear_relationships(session: AsyncSession, entity_id, rel_type: str):
    """Delete all relationships of a given type for an entity."""
    await session.execute(
        delete(Relationship).where(
            Relationship.from_entity_id == entity_id,
            Relationship.relationship_type == rel_type,
        )
    )
    # Also clear incoming
    await session.execute(
        delete(Relationship).where(
            Relationship.to_entity_id == entity_id,
            Relationship.relationship_type == rel_type,
        )
    )


async def merge_into_database(congress_data: dict, fec_data: dict,
                               efd_data: dict, briefing: str):
    """Merge all fetched data into the database."""
    print("\n" + "=" * 60)
    print("PHASE 3: Merging data into database")
    print("=" * 60)

    async with async_session() as session:
        async with session.begin():
            # ----- 1. Update Fetterman entity -----
            member = congress_data.get("member", {})
            committees_raw = congress_data.get("committees", [])

            metadata_update = {
                "data_source": "live_api",
                "last_ingested": datetime.now(tz=None).isoformat(),
            }

            if member:
                # Extract party from partyHistory (API v3 uses this instead of partyName)
                party = member.get("partyName", "")
                party_history = member.get("partyHistory", [])
                if not party and party_history:
                    party = party_history[-1].get("partyName", "Democratic")

                metadata_update.update({
                    "bioguideId": member.get("bioguideId", BIOGUIDE_ID),
                    "party": party or "Democratic",
                    "state": member.get("state", "Pennsylvania"),
                    "depiction": member.get("depiction", {}),
                    "officialWebsiteUrl": member.get("officialWebsiteUrl", ""),
                    "currentMember": member.get("currentMember", True),
                })
                # Extract terms — API v3 returns list directly or {"item": [...]}
                terms = member.get("terms", [])
                if isinstance(terms, dict):
                    terms = terms.get("item", [])
                if terms and isinstance(terms, list):
                    latest = terms[-1]
                    if isinstance(latest, dict):
                        metadata_update["chamber"] = latest.get("chamber", "Senate")
                        metadata_update["termStart"] = latest.get("startYear", "")
                        metadata_update["termEnd"] = latest.get("endYear", "")

            # Add committees to metadata
            if committees_raw:
                metadata_update["committees"] = committees_raw

            # Add briefing
            metadata_update["mock_briefing"] = briefing

            # Add campaign finance summary
            totals = fec_data.get("totals", {})
            if totals:
                metadata_update["campaign_finance_2022"] = {
                    "receipts": totals.get("receipts"),
                    "disbursements": totals.get("disbursements"),
                    "cash_on_hand": totals.get("cash_on_hand_end_period"),
                    "debt": totals.get("debts_owed_by_committee"),
                    "individual_contributions": totals.get("individual_contributions"),
                    "cycle": 2022,
                }

            fetterman = await upsert_entity(
                session, SLUG, "person", "John Fetterman",
                summary="United States Senator from Pennsylvania (D). "
                        "Member of the Senate Banking, Housing, and Urban Affairs Committee; "
                        "Agriculture, Nutrition, and Forestry Committee; and Joint Economic Committee.",
                metadata=metadata_update,
            )
            print(f"  Updated entity: {fetterman.name} ({fetterman.slug})")

            # ----- 2. Upsert committees -----
            await clear_relationships(session, fetterman.id, "committee_member")
            committee_count = 0
            for comm in committees_raw:
                comm_name = comm.get("name", "")
                if not comm_name:
                    continue
                comm_slug = slugify(comm_name)
                comm_entity = await upsert_entity(
                    session, comm_slug, "committee", comm_name,
                    metadata={"code": comm.get("code", ""), "chamber": comm.get("chamber", "Senate")},
                )
                rel = make_relationship(
                    from_entity_id=fetterman.id,
                    to_entity_id=comm_entity.id,
                    relationship_type="committee_member",
                    source_label="Congress.gov",
                    source_url=f"https://api.congress.gov/v3/member/{BIOGUIDE_ID}",
                    metadata_={"role": comm.get("role", "Member")},
                )
                session.add(rel)
                committee_count += 1
            print(f"  Inserted {committee_count} committee memberships")

            # ----- 3. Upsert sponsored bills -----
            await clear_relationships(session, fetterman.id, "sponsored")
            bill_count = 0
            for bill in congress_data.get("sponsored_bills", []):
                title = bill.get("title", "")
                if not title:
                    continue
                bill_num = bill.get("number", "")
                bill_type = bill.get("type", "")
                congress_num = bill.get("congress", "")
                bill_slug = slugify(f"{bill_type}-{bill_num}-{congress_num}")

                bill_entity = await upsert_entity(
                    session, bill_slug, "bill", title,
                    summary=f"{bill_type} {bill_num} ({congress_num}th Congress)",
                    metadata={
                        "congress": congress_num,
                        "number": bill_num,
                        "type": bill_type,
                        "policyArea": bill.get("policyArea", {}),
                        "latestAction": bill.get("latestAction", {}),
                        "introducedDate": bill.get("introducedDate", ""),
                        "url": bill.get("url", ""),
                    },
                )
                rel = make_relationship(
                    from_entity_id=fetterman.id,
                    to_entity_id=bill_entity.id,
                    relationship_type="sponsored",
                    date_start=parse_date(bill.get("introducedDate")),
                    source_label="Congress.gov",
                    source_url=bill.get("url", ""),
                    metadata_={"latestAction": bill.get("latestAction", {})},
                )
                session.add(rel)
                bill_count += 1
            print(f"  Inserted {bill_count} sponsored bills")

            # ----- 4. Upsert cosponsored bills -----
            await clear_relationships(session, fetterman.id, "cosponsored")
            cosponsor_count = 0
            for bill in congress_data.get("cosponsored_bills", []):
                title = bill.get("title", "")
                if not title:
                    continue
                bill_num = bill.get("number", "")
                bill_type = bill.get("type", "")
                congress_num = bill.get("congress", "")
                bill_slug = slugify(f"{bill_type}-{bill_num}-{congress_num}")

                bill_entity = await upsert_entity(
                    session, bill_slug, "bill", title,
                    summary=f"{bill_type} {bill_num} ({congress_num}th Congress)",
                    metadata={
                        "congress": congress_num,
                        "number": bill_num,
                        "type": bill_type,
                        "policyArea": bill.get("policyArea", {}),
                        "introducedDate": bill.get("introducedDate", ""),
                    },
                )
                rel = make_relationship(
                    from_entity_id=fetterman.id,
                    to_entity_id=bill_entity.id,
                    relationship_type="cosponsored",
                    date_start=parse_date(bill.get("introducedDate")),
                    source_label="Congress.gov",
                    metadata_={},
                )
                session.add(rel)
                cosponsor_count += 1
            print(f"  Inserted {cosponsor_count} cosponsored bills")

            # ----- 5. Upsert donors from FEC -----
            await clear_relationships(session, fetterman.id, "donated_to")
            await clear_relationships(session, fetterman.id, "donated_by")
            donor_count = 0

            # Aggregate individual contributors by name
            contributor_agg = {}
            for contrib in fec_data.get("top_contributors", []):
                name = contrib.get("contributor_name", "UNKNOWN")
                if name in contributor_agg:
                    contributor_agg[name]["total"] += contrib.get("contribution_receipt_amount", 0)
                    contributor_agg[name]["count"] += 1
                else:
                    contributor_agg[name] = {
                        "total": contrib.get("contribution_receipt_amount", 0),
                        "count": 1,
                        "employer": contrib.get("contributor_employer", ""),
                        "occupation": contrib.get("contributor_occupation", ""),
                        "city": contrib.get("contributor_city", ""),
                        "state": contrib.get("contributor_state", ""),
                    }

            # Top 50 individual donors by aggregated amount
            sorted_donors = sorted(contributor_agg.items(), key=lambda x: x[1]["total"], reverse=True)[:50]
            for donor_name, info in sorted_donors:
                if not donor_name or donor_name == "UNKNOWN":
                    continue
                donor_slug = slugify(donor_name)
                donor_entity = await upsert_entity(
                    session, donor_slug, "person", donor_name,
                    metadata={
                        "employer": info["employer"],
                        "occupation": info["occupation"],
                        "city": info["city"],
                        "state": info["state"],
                        "donor_type": "individual",
                    },
                )
                amount_cents = int(info["total"] * 100)
                rel = make_relationship(
                    from_entity_id=donor_entity.id,
                    to_entity_id=fetterman.id,
                    relationship_type="donated_to",
                    amount_usd=amount_cents,
                    amount_label=f"${info['total']:,.0f}",
                    source_label="FEC Schedule A",
                    source_url=f"https://www.fec.gov/data/receipts/?committee_id={FEC_COMMITTEE_ID}",
                    metadata_={
                        "contribution_count": info["count"],
                        "cycle": 2022,
                    },
                )
                session.add(rel)
                donor_count += 1

            # PAC contributions
            pac_agg = {}
            for pac in fec_data.get("pac_contributions", []):
                name = pac.get("contributor_name", "") or pac.get("committee", {}).get("name", "UNKNOWN")
                if name in pac_agg:
                    pac_agg[name]["total"] += pac.get("contribution_receipt_amount", 0)
                    pac_agg[name]["count"] += 1
                else:
                    pac_agg[name] = {
                        "total": pac.get("contribution_receipt_amount", 0),
                        "count": 1,
                        "committee_id": (pac.get("contributor") or {}).get("committee_id", ""),
                    }

            sorted_pacs = sorted(pac_agg.items(), key=lambda x: x[1]["total"], reverse=True)[:30]
            for pac_name, info in sorted_pacs:
                if not pac_name or pac_name == "UNKNOWN":
                    continue
                pac_slug = slugify(pac_name)
                pac_entity = await upsert_entity(
                    session, pac_slug, "organization", pac_name,
                    metadata={
                        "donor_type": "pac",
                        "fec_committee_id": info.get("committee_id", ""),
                    },
                )
                amount_cents = int(info["total"] * 100)
                rel = make_relationship(
                    from_entity_id=pac_entity.id,
                    to_entity_id=fetterman.id,
                    relationship_type="donated_to",
                    amount_usd=amount_cents,
                    amount_label=f"${info['total']:,.0f}",
                    source_label="FEC Schedule A (PAC)",
                    source_url=f"https://www.fec.gov/data/receipts/?committee_id={FEC_COMMITTEE_ID}",
                    metadata_={
                        "contribution_count": info["count"],
                        "cycle": 2022,
                        "contributor_type": "committee",
                    },
                )
                session.add(rel)
                donor_count += 1
            print(f"  Inserted {donor_count} donor relationships")

            # ----- 6. Upsert votes -----
            await clear_relationships(session, fetterman.id, "voted_yes")
            await clear_relationships(session, fetterman.id, "voted_no")
            await clear_relationships(session, fetterman.id, "voted_present")
            vote_count = 0
            for vote in efd_data.get("votes", []):
                question = vote.get("question", "") or vote.get("description", "")
                if not question:
                    continue
                vote_slug = slugify(f"vote-{vote.get('rollNumber', '')}-{vote.get('congress', '')}-{vote.get('session', '')}")

                vote_entity = await upsert_entity(
                    session, vote_slug, "bill", question,
                    metadata={
                        "congress": vote.get("congress"),
                        "session": vote.get("session"),
                        "rollNumber": vote.get("rollNumber"),
                        "result": vote.get("result"),
                        "date": vote.get("date"),
                        "url": vote.get("url", ""),
                    },
                )

                member_vote = vote.get("memberVote", "Yes")
                if member_vote.lower() in ("yes", "yea", "aye"):
                    rel_type = "voted_yes"
                elif member_vote.lower() in ("no", "nay"):
                    rel_type = "voted_no"
                else:
                    rel_type = "voted_present"

                rel = make_relationship(
                    from_entity_id=fetterman.id,
                    to_entity_id=vote_entity.id,
                    relationship_type=rel_type,
                    date_start=parse_date(vote.get("date")),
                    source_label="Congress.gov Votes",
                    source_url=vote.get("url", ""),
                    metadata_={"result": vote.get("result", "")},
                )
                session.add(rel)
                vote_count += 1
            print(f"  Inserted {vote_count} vote records")

            # ----- 7. Add data source records -----
            # Clear old data sources
            await session.execute(
                delete(DataSource).where(DataSource.entity_id == fetterman.id)
            )

            sources = [
                DataSource(
                    entity_id=fetterman.id,
                    source_type="Congress.gov",
                    external_id=BIOGUIDE_ID,
                    raw_payload={"member": congress_data.get("member", {}),
                                 "bill_count": len(congress_data.get("sponsored_bills", [])),
                                 "cosponsor_count": len(congress_data.get("cosponsored_bills", []))},
                ),
                DataSource(
                    entity_id=fetterman.id,
                    source_type="FEC",
                    external_id=FEC_CANDIDATE_ID,
                    raw_payload={"totals": fec_data.get("totals", {}),
                                 "contributor_count": len(fec_data.get("top_contributors", [])),
                                 "pac_count": len(fec_data.get("pac_contributions", []))},
                ),
                DataSource(
                    entity_id=fetterman.id,
                    source_type="Senate.EFD",
                    external_id="fetterman",
                    raw_payload={"asset_count": len(efd_data.get("assets", [])),
                                 "vote_count": len(efd_data.get("votes", []))},
                ),
            ]
            for ds in sources:
                session.add(ds)

            print(f"  Added {len(sources)} data source records")

            # ----- 8. Update briefing/summary -----
            fetterman.summary = (
                "United States Senator from Pennsylvania (D). "
                "Member of the Senate Banking, Housing, and Urban Affairs Committee; "
                "Agriculture, Nutrition, and Forestry Committee; and Joint Economic Committee. "
                "Former Lt. Governor of Pennsylvania (2019-2023) and Mayor of Braddock, PA (2006-2019)."
            )
            if briefing:
                fetterman.metadata_ = sanitize_dict({**fetterman.metadata_, "mock_briefing": sanitize_str(briefing)})
            print(f"  Updated briefing ({len(briefing)} chars)")

    print("\nDatabase merge complete!")


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------
async def run_ingestion():
    """Full ingestion pipeline."""
    print("\n" + "#" * 60)
    print("# JERRY MAGUIRE — Real Data Ingestion Pipeline")
    print(f"# Target: John Fetterman ({BIOGUIDE_ID})")
    print(f"# Time: {datetime.now(tz=None).isoformat()}")
    print("#" * 60 + "\n")

    if not CONGRESS_API_KEY:
        print("WARNING: CONGRESS_GOV_API_KEY not set!")
    if not FEC_API_KEY:
        print("WARNING: FEC_API_KEY not set!")

    # Phase 1: Fetch
    congress_data, fec_data, efd_data = await fetch_all_data()

    # Phase 2: Generate briefing
    briefing = await generate_briefing(congress_data, fec_data, efd_data)

    # Phase 3: Merge
    await merge_into_database(congress_data, fec_data, efd_data, briefing)

    print("\n" + "#" * 60)
    print("# INGESTION COMPLETE")
    print("#" * 60)


if __name__ == "__main__":
    asyncio.run(run_ingestion())
