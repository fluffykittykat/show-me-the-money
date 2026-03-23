"""
Cross-reference service for entity network queries.
Powers the "everything is a clickable node" feature.
"""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entity, Relationship


def _sanitize(s: str) -> str:
    return s.encode("ascii", errors="ignore").decode("ascii") if s else ""


async def get_entity_with_connections_summary(
    session: AsyncSession, slug: str
) -> dict | None:
    """Get an entity with a summary of its connections, grouped by type."""
    entity = (
        await session.execute(select(Entity).where(Entity.slug == slug))
    ).scalar_one_or_none()
    if not entity:
        return None

    # Count outgoing connections by type
    out_q = (
        select(
            Relationship.relationship_type,
            func.count().label("cnt"),
        )
        .where(Relationship.from_entity_id == entity.id)
        .group_by(Relationship.relationship_type)
    )
    out_result = await session.execute(out_q)
    out_counts = {row.relationship_type: row.cnt for row in out_result.all()}

    # Count incoming connections by type
    in_q = (
        select(
            Relationship.relationship_type,
            func.count().label("cnt"),
        )
        .where(Relationship.to_entity_id == entity.id)
        .group_by(Relationship.relationship_type)
    )
    in_result = await session.execute(in_q)
    in_counts = {row.relationship_type: row.cnt for row in in_result.all()}

    # Merge counts
    connection_counts: dict[str, int] = {}
    for k, v in out_counts.items():
        connection_counts[k] = connection_counts.get(k, 0) + v
    for k, v in in_counts.items():
        connection_counts[k] = connection_counts.get(k, 0) + v

    # Connected officials (people connected via any relationship)
    connected_people_q = (
        select(Entity.slug, Entity.name)
        .select_from(Relationship)
        .join(Entity, Entity.id == Relationship.to_entity_id)
        .where(
            Relationship.from_entity_id == entity.id,
            Entity.entity_type == "person",
        )
    )
    connected_people_q2 = (
        select(Entity.slug, Entity.name)
        .select_from(Relationship)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(
            Relationship.to_entity_id == entity.id,
            Entity.entity_type == "person",
        )
    )
    people_result = await session.execute(
        connected_people_q.union(connected_people_q2).limit(50)
    )
    connected_officials = [
        {"slug": row.slug, "name": row.name} for row in people_result.all()
    ]

    # Total money in (incoming donated_to)
    money_in_q = select(func.coalesce(func.sum(Relationship.amount_usd), 0)).where(
        Relationship.to_entity_id == entity.id,
        Relationship.relationship_type == "donated_to",
    )
    total_money_in = (await session.execute(money_in_q)).scalar() or 0

    # Total money out (outgoing donated_to)
    money_out_q = select(func.coalesce(func.sum(Relationship.amount_usd), 0)).where(
        Relationship.from_entity_id == entity.id,
        Relationship.relationship_type == "donated_to",
    )
    total_money_out = (await session.execute(money_out_q)).scalar() or 0

    return {
        "entity": entity,
        "connection_counts": connection_counts,
        "connected_officials": connected_officials,
        "total_money_in": total_money_in,
        "total_money_out": total_money_out,
    }


async def who_else_holds_stock(
    session: AsyncSession, company_slug: str
) -> list[dict]:
    """Find all officials who hold stock in a given company."""
    company = (
        await session.execute(select(Entity).where(Entity.slug == company_slug))
    ).scalar_one_or_none()
    if not company:
        return []

    query = (
        select(Entity, Relationship)
        .join(Relationship, Relationship.from_entity_id == Entity.id)
        .where(
            Relationship.to_entity_id == company.id,
            Relationship.relationship_type == "holds_stock",
            Entity.entity_type == "person",
        )
    )
    results = await session.execute(query)
    return [
        {
            "slug": person.slug,
            "name": _sanitize(person.name),
            "party": (person.metadata_ or {}).get("party", ""),
            "state": (person.metadata_ or {}).get("state", ""),
            "amount_label": rel.amount_label,
            "amount_usd": rel.amount_usd,
        }
        for person, rel in results.all()
    ]


async def who_else_receives_from_donor(
    session: AsyncSession, donor_slug: str
) -> list[dict]:
    """Find all officials who receive money from a given donor/PAC."""
    donor = (
        await session.execute(select(Entity).where(Entity.slug == donor_slug))
    ).scalar_one_or_none()
    if not donor:
        return []

    query = (
        select(Entity, Relationship)
        .join(Relationship, Relationship.to_entity_id == Entity.id)
        .where(
            Relationship.from_entity_id == donor.id,
            Relationship.relationship_type == "donated_to",
            Entity.entity_type == "person",
        )
        .order_by(Relationship.amount_usd.desc().nullslast())
    )
    results = await session.execute(query)
    return [
        {
            "slug": person.slug,
            "name": _sanitize(person.name),
            "party": (person.metadata_ or {}).get("party", ""),
            "state": (person.metadata_ or {}).get("state", ""),
            "amount_usd": rel.amount_usd,
            "amount_label": rel.amount_label,
        }
        for person, rel in results.all()
    ]


# Committee jurisdiction mapping
_COMMITTEE_JURISDICTION: dict[str, dict[str, list[str]]] = {
    "banking": {
        "industries": [
            "Banking", "Finance", "Insurance", "Real Estate", "Securities",
        ],
        "topics": [
            "Financial regulation", "Housing policy",
            "Economic sanctions", "Federal Reserve oversight",
        ],
    },
    "agriculture": {
        "industries": [
            "Agriculture", "Food", "Farming", "Agribusiness", "Rural Development",
        ],
        "topics": [
            "Farm subsidies", "Food safety", "Nutrition programs",
            "Forestry", "Rural broadband",
        ],
    },
    "joint economic": {
        "industries": ["Finance", "Economics", "Trade"],
        "topics": [
            "Economic policy", "Monetary policy", "Trade agreements", "Employment",
        ],
    },
    "appropriations": {
        "industries": ["Defense", "Government", "Healthcare"],
        "topics": [
            "Federal spending", "Budget allocation", "Government funding",
        ],
    },
    "judiciary": {
        "industries": ["Legal", "Technology", "Immigration Services"],
        "topics": [
            "Constitutional law", "Immigration", "Antitrust", "Criminal justice",
        ],
    },
    "armed services": {
        "industries": ["Defense", "Aerospace", "Military"],
        "topics": [
            "National defense", "Military operations", "Defense contracts", "Veterans",
        ],
    },
    "commerce": {
        "industries": ["Technology", "Telecommunications", "Transportation", "Energy"],
        "topics": [
            "Consumer protection", "Internet regulation", "Trade", "Science",
        ],
    },
    "energy": {
        "industries": ["Energy", "Oil & Gas", "Mining", "Nuclear"],
        "topics": [
            "Energy policy", "Nuclear regulation", "Public lands", "Water resources",
        ],
    },
    "environment": {
        "industries": ["Environment", "Construction", "Chemical", "Waste Management"],
        "topics": [
            "Environmental protection", "Climate policy",
            "Infrastructure", "Clean water",
        ],
    },
    "finance": {
        "industries": ["Finance", "Insurance", "Healthcare", "Trade"],
        "topics": [
            "Tax policy", "Social Security", "Medicare", "International trade",
        ],
    },
    "foreign relations": {
        "industries": ["Defense", "International", "Foreign Aid"],
        "topics": [
            "Foreign policy", "Treaties", "International organizations", "Arms control",
        ],
    },
    "health": {
        "industries": ["Healthcare", "Pharmaceuticals", "Biotech"],
        "topics": [
            "Public health", "Medicare", "Drug pricing", "Health insurance",
        ],
    },
    "homeland security": {
        "industries": ["Defense", "Technology", "Security"],
        "topics": [
            "Border security", "Cybersecurity",
            "Emergency management", "Immigration enforcement",
        ],
    },
    "intelligence": {
        "industries": ["Defense", "Technology", "Intelligence"],
        "topics": [
            "Intelligence operations", "Surveillance",
            "Cybersecurity", "Counter-terrorism",
        ],
    },
    "rules": {
        "industries": [],
        "topics": ["Senate procedures", "Legislative process"],
    },
    "veterans": {
        "industries": ["Healthcare", "Defense"],
        "topics": [
            "Veterans benefits", "VA healthcare", "Military transition",
        ],
    },
}


async def get_committee_details(
    session: AsyncSession, committee_slug: str
) -> dict | None:
    """Get detailed committee info including jurisdiction, members."""
    committee = (
        await session.execute(
            select(Entity).where(Entity.slug == committee_slug)
        )
    ).scalar_one_or_none()
    if not committee:
        return None

    members_q = (
        select(Entity, Relationship)
        .join(Relationship, Relationship.from_entity_id == Entity.id)
        .where(
            Relationship.to_entity_id == committee.id,
            Relationship.relationship_type == "committee_member",
        )
    )
    members_result = await session.execute(members_q)
    members = [
        {
            "slug": person.slug,
            "name": _sanitize(person.name),
            "party": (person.metadata_ or {}).get("party", ""),
            "state": (person.metadata_ or {}).get("state", ""),
            "role": (rel.metadata_ or {}).get("role", "Member"),
        }
        for person, rel in members_result.all()
    ]

    committee_name_lower = committee.name.lower()
    jurisdiction: dict[str, list[str]] = {"industries": [], "topics": []}
    for key, value in _COMMITTEE_JURISDICTION.items():
        if key in committee_name_lower:
            jurisdiction = value
            break

    return {
        "entity": committee,
        "members": members,
        "jurisdiction": jurisdiction,
        "member_count": len(members),
    }


async def get_industry_connections(
    session: AsyncSession, industry_keyword: str
) -> dict:
    """Get all entities and officials connected to an industry."""
    keyword_lower = f"%{industry_keyword.lower()}%"

    entities_q = (
        select(Entity)
        .where(
            or_(
                func.lower(Entity.name).like(keyword_lower),
                Entity.metadata_["industry_label"].astext.ilike(keyword_lower),
                Entity.metadata_["policyArea"].astext.ilike(keyword_lower),
            )
        )
        .limit(100)
    )
    entities_result = await session.execute(entities_q)
    entities = entities_result.scalars().all()

    entity_ids = [e.id for e in entities]
    donations_to_officials: list[dict] = []
    if entity_ids:
        donations_q = (
            select(Entity, Relationship)
            .join(Relationship, Relationship.to_entity_id == Entity.id)
            .where(
                Relationship.from_entity_id.in_(entity_ids),
                Relationship.relationship_type == "donated_to",
                Entity.entity_type == "person",
            )
        )
        donations_result = await session.execute(donations_q)
        for person, rel in donations_result.all():
            donations_to_officials.append(
                {
                    "slug": person.slug,
                    "name": _sanitize(person.name),
                    "party": (person.metadata_ or {}).get("party", ""),
                    "state": (person.metadata_ or {}).get("state", ""),
                    "amount_usd": rel.amount_usd,
                    "amount_label": rel.amount_label,
                }
            )

    total_donated = sum(d["amount_usd"] or 0 for d in donations_to_officials)

    return {
        "industry": industry_keyword,
        "entity_count": len(entities),
        "official_count": len(
            set(d["slug"] for d in donations_to_officials)
        ),
        "total_donated": total_donated,
        "donations_to_officials": sorted(
            donations_to_officials,
            key=lambda x: x["amount_usd"] or 0,
            reverse=True,
        ),
        "related_entities": [
            {"slug": e.slug, "name": _sanitize(e.name), "entity_type": e.entity_type}
            for e in entities[:20]
        ],
    }


async def get_shared_interests(session: AsyncSession, entity_slug: str) -> dict:
    """Get officials who share financial interests with this official."""
    person = (
        await session.execute(
            select(Entity).where(
                Entity.slug == entity_slug, Entity.entity_type == "person"
            )
        )
    ).scalar_one_or_none()
    if not person:
        return {
            "shared_stocks": [],
            "shared_donors": [],
            "legislative_allies": [],
            "industry_network": [],
        }

    # 1. Shared stocks
    my_holdings_q = select(Relationship.to_entity_id).where(
        Relationship.from_entity_id == person.id,
        Relationship.relationship_type == "holds_stock",
    )
    my_holdings = [r[0] for r in (await session.execute(my_holdings_q)).all()]

    shared_stocks: list[dict] = []
    if my_holdings:
        others_q = (
            select(
                Entity.slug,
                Entity.name,
                func.count().label("overlap_count"),
            )
            .select_from(Relationship)
            .join(Entity, Entity.id == Relationship.from_entity_id)
            .where(
                Relationship.to_entity_id.in_(my_holdings),
                Relationship.from_entity_id != person.id,
                Relationship.relationship_type == "holds_stock",
                Entity.entity_type == "person",
            )
            .group_by(Entity.slug, Entity.name)
            .order_by(func.count().desc())
        )
        results = await session.execute(others_q)
        shared_stocks = [
            {
                "slug": row.slug,
                "name": _sanitize(row.name),
                "overlap_count": row.overlap_count,
            }
            for row in results.all()
        ]

    # 2. Shared donors
    my_donors_q = select(Relationship.from_entity_id).where(
        Relationship.to_entity_id == person.id,
        Relationship.relationship_type == "donated_to",
    )
    my_donors = [r[0] for r in (await session.execute(my_donors_q)).all()]

    shared_donors: list[dict] = []
    if my_donors:
        donors_q = (
            select(
                Entity.slug,
                Entity.name,
                func.count().label("shared_count"),
                func.sum(Relationship.amount_usd).label("total_amount"),
            )
            .select_from(Relationship)
            .join(Entity, Entity.id == Relationship.to_entity_id)
            .where(
                Relationship.from_entity_id.in_(my_donors),
                Relationship.to_entity_id != person.id,
                Relationship.relationship_type == "donated_to",
                Entity.entity_type == "person",
            )
            .group_by(Entity.slug, Entity.name)
            .order_by(func.count().desc())
        )
        results = await session.execute(donors_q)
        shared_donors = [
            {
                "slug": row.slug,
                "name": _sanitize(row.name),
                "shared_count": row.shared_count,
                "total_amount": row.total_amount or 0,
            }
            for row in results.all()
        ]

    # 3. Legislative allies
    my_bills_q = select(Relationship.to_entity_id).where(
        Relationship.from_entity_id == person.id,
        Relationship.relationship_type.in_(["sponsored", "cosponsored"]),
    )
    my_bills = [r[0] for r in (await session.execute(my_bills_q)).all()]

    legislative_allies: list[dict] = []
    if my_bills:
        allies_q = (
            select(
                Entity.slug,
                Entity.name,
                func.count().label("shared_bills"),
            )
            .select_from(Relationship)
            .join(Entity, Entity.id == Relationship.from_entity_id)
            .where(
                Relationship.to_entity_id.in_(my_bills),
                Relationship.from_entity_id != person.id,
                Relationship.relationship_type.in_(
                    ["sponsored", "cosponsored"]
                ),
                Entity.entity_type == "person",
            )
            .group_by(Entity.slug, Entity.name)
            .order_by(func.count().desc())
        )
        results = await session.execute(allies_q)
        legislative_allies = [
            {
                "slug": row.slug,
                "name": _sanitize(row.name),
                "shared_bills": row.shared_bills,
            }
            for row in results.all()
        ]

    industry_network: list[dict] = []

    return {
        "shared_stocks": shared_stocks[:20],
        "shared_donors": shared_donors[:20],
        "legislative_allies": legislative_allies[:20],
        "industry_network": industry_network,
    }


async def count_other_holders(session: AsyncSession, company_entity_id) -> int:
    """Count how many officials hold stock in this company."""
    result = await session.execute(
        select(func.count(func.distinct(Relationship.from_entity_id))).where(
            Relationship.to_entity_id == company_entity_id,
            Relationship.relationship_type == "holds_stock",
        )
    )
    return result.scalar() or 0


async def count_other_recipients(session: AsyncSession, donor_entity_id) -> int:
    """Count how many officials receive money from this donor."""
    result = await session.execute(
        select(func.count(func.distinct(Relationship.to_entity_id))).where(
            Relationship.from_entity_id == donor_entity_id,
            Relationship.relationship_type == "donated_to",
        )
    )
    return result.scalar() or 0


async def count_cosponsors(session: AsyncSession, bill_entity_id) -> int:
    """Count how many officials co-sponsored this bill."""
    result = await session.execute(
        select(func.count(func.distinct(Relationship.from_entity_id))).where(
            Relationship.to_entity_id == bill_entity_id,
            Relationship.relationship_type.in_(["sponsored", "cosponsored"]),
        )
    )
    return result.scalar() or 0


async def get_bill_donor_industries(
    session: AsyncSession, bill_entity_id
) -> list[dict]:
    """Get industries that donated to YES voters on this bill."""
    voters_q = select(Relationship.from_entity_id).where(
        Relationship.to_entity_id == bill_entity_id,
        Relationship.relationship_type == "voted_yes",
    )
    voter_ids = [r[0] for r in (await session.execute(voters_q)).all()]
    if not voter_ids:
        return []

    donations_q = (
        select(
            func.sum(Relationship.amount_usd).label("total"),
            func.count().label("donor_count"),
        ).where(
            Relationship.to_entity_id.in_(voter_ids),
            Relationship.relationship_type == "donated_to",
        )
    )
    result = await session.execute(donations_q)
    row = result.one_or_none()
    total = row.total if row else 0

    return [
        {
            "industry": "All Donors",
            "total": total or 0,
            "count": row.donor_count if row else 0,
        }
    ]


async def get_donor_profile(session: AsyncSession, donor_slug: str) -> dict | None:
    """Complete donor reverse-lookup profile.

    Returns:
    - entity info
    - total_political_spend (sum of all donated_to amounts, in cents)
    - recipients: list of officials receiving money, with amounts
    - recipient_committees: what committees do their recipients sit on
    - influenced_legislation: bills where their recipients voted yes
    - industry: derived from entity metadata or name
    """
    # 1. Get the donor entity
    donor = (
        await session.execute(select(Entity).where(Entity.slug == donor_slug))
    ).scalar_one_or_none()
    if not donor:
        return None

    # 2. Find ALL donated_to relationships (outgoing) -- these are the recipients
    donations_q = (
        select(Entity, Relationship)
        .join(Relationship, Relationship.to_entity_id == Entity.id)
        .where(
            Relationship.from_entity_id == donor.id,
            Relationship.relationship_type == "donated_to",
            Entity.entity_type == "person",
        )
        .order_by(Relationship.amount_usd.desc().nullslast())
    )
    donations_result = await session.execute(donations_q)
    donation_rows = donations_result.all()

    # Build recipient details
    recipient_ids = [person.id for person, _rel in donation_rows]
    total_political_spend = sum(rel.amount_usd or 0 for _person, rel in donation_rows)

    # 3. For each recipient, find their committee_member relationships
    committees_by_person: dict[str, list[str]] = {}
    all_committees: set[str] = set()
    if recipient_ids:
        committee_q = (
            select(Relationship.from_entity_id, Entity.name)
            .join(Entity, Entity.id == Relationship.to_entity_id)
            .where(
                Relationship.from_entity_id.in_(recipient_ids),
                Relationship.relationship_type == "committee_member",
            )
        )
        committee_result = await session.execute(committee_q)
        for row in committee_result.all():
            person_id_str = str(row[0])
            committee_name = _sanitize(row[1])
            if person_id_str not in committees_by_person:
                committees_by_person[person_id_str] = []
            committees_by_person[person_id_str].append(committee_name)
            all_committees.add(committee_name)

    # 4. For each recipient, find their voted_yes / voted_no relationships
    votes_by_person: dict[str, list[str]] = {}
    bill_vote_tracker: dict[str, dict] = {}  # bill_slug -> {name, yes_voters, total}
    if recipient_ids:
        votes_q = (
            select(Relationship.from_entity_id, Relationship.relationship_type, Entity)
            .join(Entity, Entity.id == Relationship.to_entity_id)
            .where(
                Relationship.from_entity_id.in_(recipient_ids),
                Relationship.relationship_type.in_(["voted_yes", "voted_no"]),
            )
        )
        votes_result = await session.execute(votes_q)
        for row in votes_result.all():
            person_id_str = str(row[0])
            vote_type = row[1]
            bill_entity = row[2]
            vote_label = (
                f"Voted {'YES' if vote_type == 'voted_yes' else 'NO'} on "
                f"{_sanitize(bill_entity.name)}"
            )
            if person_id_str not in votes_by_person:
                votes_by_person[person_id_str] = []
            votes_by_person[person_id_str].append(vote_label)

            # Track legislation influenced (only YES votes from funded recipients)
            if vote_type == "voted_yes":
                b_slug = bill_entity.slug
                if b_slug not in bill_vote_tracker:
                    bill_vote_tracker[b_slug] = {
                        "bill_name": _sanitize(bill_entity.name),
                        "yes_voter_ids": set(),
                        "total_to_yes_voters": 0,
                    }
                bill_vote_tracker[b_slug]["yes_voter_ids"].add(person_id_str)

    # Calculate total donated to yes voters per bill
    amount_by_person: dict[str, int] = {}
    for person, rel in donation_rows:
        amount_by_person[str(person.id)] = rel.amount_usd or 0

    for b_slug, info in bill_vote_tracker.items():
        info["total_to_yes_voters"] = sum(
            amount_by_person.get(pid, 0) for pid in info["yes_voter_ids"]
        )

    # 5. Assemble recipients list
    recipients = []
    for person, rel in donation_rows:
        pid = str(person.id)
        recipients.append(
            {
                "slug": person.slug,
                "name": _sanitize(person.name),
                "party": (person.metadata_ or {}).get("party", ""),
                "state": (person.metadata_ or {}).get("state", ""),
                "amount_usd": rel.amount_usd,
                "amount_label": rel.amount_label,
                "committees": committees_by_person.get(pid, []),
                "relevant_votes": votes_by_person.get(pid, []),
            }
        )

    # 6. Legislation influenced
    legislation_influenced = sorted(
        [
            {
                "bill_slug": b_slug,
                "bill_name": info["bill_name"],
                "yes_voters_funded": len(info["yes_voter_ids"]),
                "total_to_yes_voters": info["total_to_yes_voters"],
            }
            for b_slug, info in bill_vote_tracker.items()
        ],
        key=lambda x: x["total_to_yes_voters"],
        reverse=True,
    )

    # 7. Derive industry from metadata or name
    industry = (
        (donor.metadata_ or {}).get("industry_label", "")
        or (donor.metadata_ or {}).get("industry", "")
        or (donor.metadata_ or {}).get("sector", "")
        or "Unknown"
    )

    return {
        "entity": donor,
        "total_political_spend": total_political_spend,
        "recipient_count": len(recipients),
        "recipients": recipients,
        "committees_covered": sorted(all_committees),
        "legislation_influenced": legislation_influenced,
        "industry": _sanitize(industry),
    }
