"""
Ingestion script for committee members: fetches data from Congress.gov, FEC,
and enriches bill entities with summaries and TLDRs.

This script identifies Fetterman's committee members and runs a full ingestion
for each one, including voting records, campaign finance data, and bill metadata.

Usage:
    cd /home/mansona/workspace/jerry-maguire/backend
    python -m app.services.ingestion.ingest_committee_members
"""

import asyncio
import os
import re
import subprocess
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../../.env"))

from app.database import async_session
from app.models import Entity
from app.services.ingestion.congress_client import CongressClient
from app.services.ingestion.fec_client import FECClient
from app.services.ingestion.ingest_fetterman import (
    clear_relationships,
    make_relationship,
    parse_date,
    sanitize_dict,
    sanitize_str,
    slugify,
    upsert_entity,
)

CONGRESS_API_KEY = os.getenv("CONGRESS_GOV_API_KEY", "")
FEC_API_KEY = os.getenv("FEC_API_KEY", "")

# Fetterman's committees and their codes
COMMITTEES = [
    {"name": "Banking, Housing, and Urban Affairs", "code": "SSBK", "chamber": "Senate"},
    {"name": "Agriculture, Nutrition, and Forestry", "code": "SSAF", "chamber": "Senate"},
    {"name": "Joint Economic Committee", "code": "JSEC", "chamber": "Joint"},
]

# Fetterman's bioguide ID -- skip him during committee member ingestion
FETTERMAN_BIOGUIDE = "F000479"

# Hardcoded fallback committee members (119th Congress, 2025)
# Used when the Congress.gov committee API does not return member lists
FALLBACK_COMMITTEE_MEMBERS = {
    "SSBK": [
        {"bioguideId": "B000944", "name": "Sherrod Brown", "party": "Democratic", "state": "OH"},
        {"bioguideId": "R000122", "name": "Jack Reed", "party": "Democratic", "state": "RI"},
        {"bioguideId": "M000639", "name": "Robert Menendez", "party": "Democratic", "state": "NJ"},
        {"bioguideId": "T000464", "name": "Jon Tester", "party": "Democratic", "state": "MT"},
        {"bioguideId": "W000805", "name": "Mark Warner", "party": "Democratic", "state": "VA"},
        {"bioguideId": "V000128", "name": "Chris Van Hollen", "party": "Democratic", "state": "MD"},
        {"bioguideId": "C001113", "name": "Catherine Cortez Masto", "party": "Democratic", "state": "NV"},
        {"bioguideId": "S001203", "name": "Tina Smith", "party": "Democratic", "state": "MN"},
        {"bioguideId": "W000790", "name": "Raphael Warnock", "party": "Democratic", "state": "GA"},
        {"bioguideId": "S000033", "name": "Bernie Sanders", "party": "Independent", "state": "VT"},
        {"bioguideId": "S001184", "name": "Tim Scott", "party": "Republican", "state": "SC"},
        {"bioguideId": "C000880", "name": "Mike Crapo", "party": "Republican", "state": "ID"},
        {"bioguideId": "R000605", "name": "Mike Rounds", "party": "Republican", "state": "SD"},
        {"bioguideId": "T000250", "name": "John Thune", "party": "Republican", "state": "SD"},
        {"bioguideId": "H000601", "name": "Bill Hagerty", "party": "Republican", "state": "TN"},
        {"bioguideId": "L000571", "name": "Cynthia Lummis", "party": "Republican", "state": "WY"},
        {"bioguideId": "D000618", "name": "Steve Daines", "party": "Republican", "state": "MT"},
        {"bioguideId": "K000393", "name": "John Kennedy", "party": "Republican", "state": "LA"},
        {"bioguideId": "C001098", "name": "Ted Cruz", "party": "Republican", "state": "TX"},
        {"bioguideId": "T000476", "name": "Thom Tillis", "party": "Republican", "state": "NC"},
    ],
    "SSAF": [
        {"bioguideId": "S000770", "name": "Debbie Stabenow", "party": "Democratic", "state": "MI"},
        {"bioguideId": "B001288", "name": "Cory Booker", "party": "Democratic", "state": "NJ"},
        {"bioguideId": "G000555", "name": "Kirsten Gillibrand", "party": "Democratic", "state": "NY"},
        {"bioguideId": "K000367", "name": "Amy Klobuchar", "party": "Democratic", "state": "MN"},
        {"bioguideId": "B001267", "name": "Michael Bennet", "party": "Democratic", "state": "CO"},
        {"bioguideId": "L000174", "name": "Patrick Leahy", "party": "Democratic", "state": "VT"},
        {"bioguideId": "W000437", "name": "Roger Wicker", "party": "Republican", "state": "MS"},
        {"bioguideId": "B001236", "name": "John Boozman", "party": "Republican", "state": "AR"},
        {"bioguideId": "G000386", "name": "Chuck Grassley", "party": "Republican", "state": "IA"},
        {"bioguideId": "H001079", "name": "Cindy Hyde-Smith", "party": "Republican", "state": "MS"},
        {"bioguideId": "M000355", "name": "Mitch McConnell", "party": "Republican", "state": "KY"},
        {"bioguideId": "T000250", "name": "John Thune", "party": "Republican", "state": "SD"},
        {"bioguideId": "F000463", "name": "Deb Fischer", "party": "Republican", "state": "NE"},
        {"bioguideId": "B001310", "name": "Mike Braun", "party": "Republican", "state": "IN"},
    ],
    "JSEC": [
        {"bioguideId": "C001070", "name": "Bob Casey", "party": "Democratic", "state": "PA"},
        {"bioguideId": "H001042", "name": "Mazie Hirono", "party": "Democratic", "state": "HI"},
        {"bioguideId": "K000384", "name": "Tim Kaine", "party": "Democratic", "state": "VA"},
        {"bioguideId": "P000595", "name": "Gary Peters", "party": "Democratic", "state": "MI"},
        {"bioguideId": "L000577", "name": "Mike Lee", "party": "Republican", "state": "UT"},
        {"bioguideId": "C001098", "name": "Ted Cruz", "party": "Republican", "state": "TX"},
        {"bioguideId": "C000880", "name": "Mike Crapo", "party": "Republican", "state": "ID"},
        {"bioguideId": "C001075", "name": "Bill Cassidy", "party": "Republican", "state": "LA"},
    ],
}


def generate_bill_tldr(bill_title: str, official_summary: str) -> str:
    """Generate a plain-English TLDR of a bill using the claude CLI."""
    if not bill_title and not official_summary:
        return ""

    prompt = (
        f"Write a 1-2 sentence plain English summary of this bill. "
        f"Title: {bill_title}. Official summary: {official_summary}. "
        f"Write it so a non-expert can understand what this bill actually does. "
        f"Be specific about the concrete effects."
    )
    try:
        result = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception as e:
        print(f"[TLDR] Error generating TLDR: {e}")
        return ""


async def get_committee_members(congress_client: CongressClient) -> dict[str, list]:
    """Fetch committee members for all of Fetterman's committees.

    Returns a dict mapping committee code to list of member dicts.
    Falls back to hardcoded lists if the API doesn't return members.
    """
    result = {}
    for comm in COMMITTEES:
        code = comm["code"]
        print(f"\n[CommitteeMembers] Fetching members for {comm['name']} ({code})")

        members = await congress_client.fetch_committee_members(code)
        if members:
            # Normalize member data -- API may return different structures
            normalized = []
            for m in members:
                if isinstance(m, dict):
                    bio_id = (
                        m.get("bioguideId")
                        or m.get("bioguide_id")
                        or m.get("member", {}).get("bioguideId", "")
                    )
                    name = (
                        m.get("name")
                        or m.get("firstName", "") + " " + m.get("lastName", "")
                    ).strip()
                    if bio_id:
                        normalized.append({
                            "bioguideId": bio_id,
                            "name": name or bio_id,
                            "party": m.get("party", m.get("partyName", "")),
                            "state": m.get("state", ""),
                        })
            if normalized:
                result[code] = normalized
                print(
                    f"[CommitteeMembers] Got {len(normalized)} members from API "
                    f"for {code}"
                )
                continue

        # Fall back to hardcoded list
        fallback = FALLBACK_COMMITTEE_MEMBERS.get(code, [])
        result[code] = fallback
        print(
            f"[CommitteeMembers] Using fallback list with {len(fallback)} members "
            f"for {code}"
        )

    return result


async def ingest_member_votes(
    session, member_entity: Entity, bioguide_id: str, congress_client: CongressClient
):
    """Fetch and store voting records for a member."""
    print(f"[Votes] Fetching votes for {bioguide_id}")
    votes = await congress_client.fetch_member_votes(bioguide_id, limit=50)

    if not votes:
        print(f"[Votes] No votes found for {bioguide_id}")
        return 0

    # Clear existing vote relationships for this member
    await clear_relationships(session, member_entity.id, "voted_yes")
    await clear_relationships(session, member_entity.id, "voted_no")
    await clear_relationships(session, member_entity.id, "voted_present")

    vote_count = 0
    for vote in votes:
        # Extract vote metadata
        question = vote.get("question", "") or vote.get("description", "")
        if not question:
            continue

        congress_num = vote.get("congress", "")
        session_num = vote.get("session", "")
        roll_number = vote.get("rollNumber", vote.get("number", ""))

        vote_slug = slugify(
            f"vote-{roll_number}-{congress_num}-{session_num}"
        )

        vote_entity = await upsert_entity(
            session,
            vote_slug,
            "bill",
            sanitize_str(question),
            metadata=sanitize_dict({
                "congress": congress_num,
                "session": session_num,
                "rollNumber": roll_number,
                "result": vote.get("result", ""),
                "date": vote.get("date", ""),
                "url": vote.get("url", ""),
            }),
        )

        # Determine vote type
        member_vote = vote.get("memberVotes", {})
        # The API nests member votes differently; try multiple paths
        vote_position = ""
        if isinstance(member_vote, dict):
            # Might be nested under member bioguide
            for _key, val in member_vote.items():
                if isinstance(val, list):
                    for v in val:
                        if isinstance(v, dict) and v.get("bioguideId") == bioguide_id:
                            vote_position = v.get("vote", "")
                            break
                elif isinstance(val, str):
                    vote_position = val
                if vote_position:
                    break

        if not vote_position:
            vote_position = vote.get("memberVote", "Yes")

        if isinstance(vote_position, str):
            vp_lower = vote_position.lower()
        else:
            vp_lower = "present"

        if vp_lower in ("yes", "yea", "aye"):
            rel_type = "voted_yes"
        elif vp_lower in ("no", "nay"):
            rel_type = "voted_no"
        else:
            rel_type = "voted_present"

        rel = make_relationship(
            from_entity_id=member_entity.id,
            to_entity_id=vote_entity.id,
            relationship_type=rel_type,
            date_start=parse_date(vote.get("date")),
            source_label="Congress.gov Votes",
            source_url=sanitize_str(vote.get("url", "")),
            metadata_=sanitize_dict({"result": vote.get("result", "")}),
        )
        session.add(rel)
        vote_count += 1

    print(f"[Votes] Inserted {vote_count} vote records for {bioguide_id}")
    return vote_count


async def ingest_member_fec_data(
    session, member_entity: Entity, member_name: str, member_state: str,
    fec_client: FECClient
):
    """Fetch and store FEC campaign finance data for a member."""
    print(f"[FEC] Looking up FEC data for {member_name} ({member_state})")

    # Search for the candidate in FEC
    candidate_info = await fec_client.search_candidate(member_name, state=member_state)
    if not candidate_info:
        print(f"[FEC] No FEC candidate found for {member_name}")
        return 0

    candidate_id = candidate_info.get("candidate_id", "")
    if not candidate_id:
        print(f"[FEC] No candidate_id in FEC result for {member_name}")
        return 0

    # Find the principal committee ID
    committee_id = ""
    committees = candidate_info.get("principal_committees", [])
    if committees:
        committee_id = committees[0].get("committee_id", "")

    if not committee_id:
        print(f"[FEC] No principal committee found for {member_name}, skipping contributions")
        return 0

    # Fetch top contributors
    donor_count = 0
    try:
        await asyncio.sleep(1)  # Rate limit
        top_contributors = await fec_client.fetch_top_contributors(
            committee_id, cycle=2024, per_page=50
        )

        # Clear existing donation relationships
        await clear_relationships(session, member_entity.id, "donated_to")

        # Aggregate contributors by name
        contributor_agg = {}
        for contrib in top_contributors:
            name = contrib.get("contributor_name", "UNKNOWN")
            if name in contributor_agg:
                contributor_agg[name]["total"] += contrib.get(
                    "contribution_receipt_amount", 0
                )
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

        # Top 30 donors
        sorted_donors = sorted(
            contributor_agg.items(), key=lambda x: x[1]["total"], reverse=True
        )[:30]

        for donor_name, info in sorted_donors:
            if not donor_name or donor_name == "UNKNOWN":
                continue
            donor_slug = slugify(donor_name)
            donor_entity = await upsert_entity(
                session,
                donor_slug,
                "person",
                sanitize_str(donor_name),
                metadata=sanitize_dict({
                    "employer": info["employer"],
                    "occupation": info["occupation"],
                    "city": info["city"],
                    "state": info["state"],
                    "donor_type": "individual",
                }),
            )
            amount_cents = int(info["total"] * 100)
            rel = make_relationship(
                from_entity_id=donor_entity.id,
                to_entity_id=member_entity.id,
                relationship_type="donated_to",
                amount_usd=amount_cents,
                amount_label=f"${info['total']:,.0f}",
                source_label="FEC Schedule A",
                source_url=f"https://www.fec.gov/data/receipts/?committee_id={committee_id}",
                metadata_=sanitize_dict({
                    "contribution_count": info["count"],
                    "cycle": 2024,
                }),
            )
            session.add(rel)
            donor_count += 1

    except Exception as e:
        print(f"[FEC] Error fetching contributors for {member_name}: {e}")

    print(f"[FEC] Inserted {donor_count} donor relationships for {member_name}")
    return donor_count


async def ingest_member_legislation(
    session, member_entity: Entity, bioguide_id: str, congress_client: CongressClient
):
    """Fetch and store sponsored legislation for a member."""
    print(f"[Legislation] Fetching sponsored legislation for {bioguide_id}")

    try:
        sponsored = await congress_client.fetch_sponsored_legislation(bioguide_id, limit=50)
    except Exception as e:
        print(f"[Legislation] Error fetching sponsored legislation: {e}")
        sponsored = []

    await clear_relationships(session, member_entity.id, "sponsored")

    bill_count = 0
    for bill in sponsored:
        title = bill.get("title", "")
        if not title:
            continue
        bill_num = bill.get("number", "")
        bill_type = bill.get("type", "")
        congress_num = bill.get("congress", "")
        bill_slug = slugify(f"{bill_type}-{bill_num}-{congress_num}")

        bill_entity = await upsert_entity(
            session,
            bill_slug,
            "bill",
            sanitize_str(title),
            summary=sanitize_str(f"{bill_type} {bill_num} ({congress_num}th Congress)"),
            metadata=sanitize_dict({
                "congress": congress_num,
                "number": bill_num,
                "type": bill_type,
                "policyArea": bill.get("policyArea", {}),
                "latestAction": bill.get("latestAction", {}),
                "introducedDate": bill.get("introducedDate", ""),
                "url": bill.get("url", ""),
            }),
        )
        rel = make_relationship(
            from_entity_id=member_entity.id,
            to_entity_id=bill_entity.id,
            relationship_type="sponsored",
            date_start=parse_date(bill.get("introducedDate")),
            source_label="Congress.gov",
            source_url=sanitize_str(bill.get("url", "")),
            metadata_=sanitize_dict({"latestAction": bill.get("latestAction", {})}),
        )
        session.add(rel)
        bill_count += 1

    print(f"[Legislation] Inserted {bill_count} sponsored bills for {bioguide_id}")
    return bill_count


async def enrich_bill_entity(
    session, bill_entity: Entity, congress_client: CongressClient
):
    """Enrich a bill entity with full text URL, official summary, and TLDR."""
    meta = bill_entity.metadata_ or {}
    congress_num = meta.get("congress")
    bill_type = meta.get("type", "")
    bill_number = meta.get("number")

    if not congress_num or not bill_type or not bill_number:
        return

    # Skip if already enriched
    if meta.get("tldr") or meta.get("full_text_url") or meta.get("official_summary"):
        return

    try:
        bill_number_int = int(bill_number)
        congress_int = int(congress_num)
    except (ValueError, TypeError):
        return

    # Fetch text info
    text_info = await congress_client.fetch_bill_text_info(
        congress_int, bill_type, bill_number_int
    )
    full_text_url = text_info.get("url", "")

    # Fetch official summary
    official_summary = await congress_client.fetch_bill_summaries(
        congress_int, bill_type, bill_number_int
    )

    # Generate TLDR
    tldr = ""
    if official_summary or bill_entity.name:
        tldr = generate_bill_tldr(
            sanitize_str(bill_entity.name),
            sanitize_str(official_summary[:2000]) if official_summary else "",
        )

    # Update metadata
    updates = {}
    if full_text_url:
        updates["full_text_url"] = sanitize_str(full_text_url)
    if official_summary:
        updates["official_summary"] = sanitize_str(official_summary[:5000])
    if tldr:
        updates["tldr"] = sanitize_str(tldr)

    if updates:
        bill_entity.metadata_ = sanitize_dict({**meta, **updates})
        bill_entity.updated_at = datetime.now(tz=None)
        print(
            f"[Enrich] Enriched bill {bill_entity.slug}: "
            f"text={'yes' if full_text_url else 'no'}, "
            f"summary={'yes' if official_summary else 'no'}, "
            f"tldr={'yes' if tldr else 'no'}"
        )


async def ingest_single_member(
    bioguide_id: str,
    member_info: dict,
    congress_client: CongressClient,
    fec_client: FECClient,
):
    """Run full ingestion for a single committee member."""
    name = member_info.get("name", bioguide_id)
    state = member_info.get("state", "")
    party = member_info.get("party", "")

    print(f"\n{'=' * 50}")
    print(f"Ingesting member: {name} ({party}, {state}) [{bioguide_id}]")
    print(f"{'=' * 50}")

    # Fetch member details from Congress.gov
    try:
        member_data = await congress_client.fetch_member(bioguide_id)
    except Exception as e:
        print(f"[Member] Error fetching member data for {bioguide_id}: {e}")
        member_data = {}

    # Extract additional info from API response
    if member_data and isinstance(member_data, dict):
        if not name or name == bioguide_id:
            first = member_data.get("firstName", "")
            last = member_data.get("lastName", "")
            name = f"{first} {last}".strip() or name
            name = member_data.get("directOrderName", name)

        if not party:
            party_history = member_data.get("partyHistory", [])
            if party_history:
                party = party_history[-1].get("partyName", "")
            else:
                party = member_data.get("partyName", "")

        if not state:
            state = member_data.get("state", "")

    slug = slugify(name)
    if not slug:
        slug = slugify(bioguide_id)

    async with async_session() as session:
        async with session.begin():
            # Create/update the member entity
            metadata = sanitize_dict({
                "bioguideId": bioguide_id,
                "party": party,
                "state": state,
                "data_source": "live_api",
                "last_ingested": datetime.now(tz=None).isoformat(),
            })

            # Add depiction/photo if available
            if member_data and isinstance(member_data, dict):
                depiction = member_data.get("depiction", {})
                if depiction:
                    metadata["depiction"] = depiction
                website = member_data.get("officialWebsiteUrl", "")
                if website:
                    metadata["officialWebsiteUrl"] = website
                current = member_data.get("currentMember")
                if current is not None:
                    metadata["currentMember"] = current

                # Extract terms
                terms = member_data.get("terms", [])
                if isinstance(terms, dict):
                    terms = terms.get("item", [])
                if terms and isinstance(terms, list):
                    latest = terms[-1]
                    if isinstance(latest, dict):
                        metadata["chamber"] = latest.get("chamber", "Senate")
                        metadata["termStart"] = latest.get("startYear", "")
                        metadata["termEnd"] = latest.get("endYear", "")

            member_entity = await upsert_entity(
                session,
                slug,
                "person",
                sanitize_str(name),
                summary=sanitize_str(
                    f"United States Senator from {state} ({party[0] if party else '?'}). "
                    f"Bioguide ID: {bioguide_id}."
                ),
                metadata=metadata,
            )
            print(f"  Created/updated entity: {member_entity.name} ({member_entity.slug})")

            # Ingest committee memberships -- link to existing committee entities
            await clear_relationships(session, member_entity.id, "committee_member")
            for comm in COMMITTEES:
                comm_slug = slugify(comm["name"])
                comm_entity = await upsert_entity(
                    session,
                    comm_slug,
                    "committee",
                    sanitize_str(comm["name"]),
                    metadata=sanitize_dict({
                        "code": comm["code"],
                        "chamber": comm["chamber"],
                    }),
                )
                # Check if this member is in this committee's fallback list
                comm_members = FALLBACK_COMMITTEE_MEMBERS.get(comm["code"], [])
                is_member = any(
                    m.get("bioguideId") == bioguide_id for m in comm_members
                )
                if is_member:
                    rel = make_relationship(
                        from_entity_id=member_entity.id,
                        to_entity_id=comm_entity.id,
                        relationship_type="committee_member",
                        source_label="Congress.gov",
                        source_url=f"https://api.congress.gov/v3/member/{bioguide_id}",
                        metadata_={"role": "Member"},
                    )
                    session.add(rel)

            # Ingest voting records
            try:
                await ingest_member_votes(
                    session, member_entity, bioguide_id, congress_client
                )
            except Exception as e:
                print(f"[Votes] Error ingesting votes for {name}: {e}")

            # Ingest sponsored legislation
            try:
                await ingest_member_legislation(
                    session, member_entity, bioguide_id, congress_client
                )
            except Exception as e:
                print(f"[Legislation] Error ingesting legislation for {name}: {e}")

            # Ingest FEC data
            try:
                await ingest_member_fec_data(
                    session, member_entity, name, state, fec_client
                )
            except Exception as e:
                print(f"[FEC] Error ingesting FEC data for {name}: {e}")

    print(f"  Completed ingestion for {name}")


async def enrich_all_bills(congress_client: CongressClient, limit: int = 100):
    """Enrich bill entities that are missing tldr/text/summary metadata."""
    from sqlalchemy import select

    print(f"\n{'=' * 60}")
    print("ENRICHING BILL ENTITIES")
    print(f"{'=' * 60}")

    async with async_session() as session:
        # Fetch bill entities that haven't been enriched yet
        result = await session.execute(
            select(Entity).where(Entity.entity_type == "bill").limit(limit)
        )
        bills = result.scalars().all()

    enriched = 0
    for bill in bills:
        meta = bill.metadata_ or {}
        # Skip already enriched
        if meta.get("tldr") and meta.get("full_text_url"):
            continue
        # Need congress, type, number to fetch
        if not meta.get("congress") or not meta.get("type") or not meta.get("number"):
            continue

        try:
            async with async_session() as session:
                async with session.begin():
                    # Re-fetch within transaction
                    from sqlalchemy import select as sel
                    r = await session.execute(
                        sel(Entity).where(Entity.id == bill.id)
                    )
                    fresh_bill = r.scalar_one_or_none()
                    if fresh_bill:
                        await enrich_bill_entity(session, fresh_bill, congress_client)
                        enriched += 1
        except Exception as e:
            print(f"[Enrich] Error enriching bill {bill.slug}: {e}")

        # Don't overwhelm the API
        if enriched >= limit:
            break

    print(f"[Enrich] Enriched {enriched} bill entities")


async def run_committee_member_ingestion():
    """Main entry point: ingest all committee members."""
    print("\n" + "#" * 60)
    print("# JERRY MAGUIRE -- Committee Member Ingestion")
    print(f"# Time: {datetime.now(tz=None).isoformat()}")
    print("#" * 60 + "\n")

    if not CONGRESS_API_KEY:
        print("WARNING: CONGRESS_GOV_API_KEY not set!")
    if not FEC_API_KEY:
        print("WARNING: FEC_API_KEY not set!")

    congress_client = CongressClient(CONGRESS_API_KEY)
    fec_client = FECClient(FEC_API_KEY)

    # Step 1: Get committee members
    committee_members = await get_committee_members(congress_client)

    # Step 2: Deduplicate members across committees
    seen_bioguides = set()
    seen_bioguides.add(FETTERMAN_BIOGUIDE)  # Skip Fetterman
    all_members = []

    for code, members in committee_members.items():
        for member in members:
            bio_id = member.get("bioguideId", "")
            if bio_id and bio_id not in seen_bioguides:
                seen_bioguides.add(bio_id)
                all_members.append(member)

    print(f"\n[CommitteeMembers] {len(all_members)} unique members to ingest")

    # Step 3: Ingest each member sequentially (to respect rate limits)
    success_count = 0
    error_count = 0
    for i, member in enumerate(all_members, 1):
        bio_id = member.get("bioguideId", "")
        print(f"\n--- Member {i}/{len(all_members)} ---")
        try:
            await ingest_single_member(bio_id, member, congress_client, fec_client)
            success_count += 1
        except Exception as e:
            print(f"ERROR ingesting member {member.get('name', bio_id)}: {e}")
            error_count += 1
        # Rate limit between members
        await asyncio.sleep(1)

    # Step 4: Enrich bill entities
    try:
        await enrich_all_bills(congress_client, limit=50)
    except Exception as e:
        print(f"ERROR enriching bills: {e}")

    print(f"\n{'#' * 60}")
    print(f"# COMMITTEE MEMBER INGESTION COMPLETE")
    print(f"# Success: {success_count}, Errors: {error_count}")
    print(f"{'#' * 60}")


if __name__ == "__main__":
    asyncio.run(run_committee_member_ingestion())
