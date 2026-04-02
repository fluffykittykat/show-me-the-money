"""
Verdict Engine — The 4-Level "Gotcha" Algorithm

Counts connected dots between officials and industries to determine
how structurally "bought" an official appears to be.

For each official, donors are grouped by industry and dots are counted:

  Dot 1: DONOR_FROM_INDUSTRY    — A donor from this industry donated (FEC)
  Dot 2: REGULATING_COMMITTEE   — Official sits on a committee regulating this industry
  Dot 3: SPONSORED_ALIGNED_BILLS — Official sponsored/cosponsored bills in this policy area
  Dot 4: DONOR_LOBBIES          — Donor (or related entity) also lobbies Congress
  Dot 5: MIDDLEMAN_PAC          — Money flows through a middleman PAC
  Dot 6: SIGNIFICANT_MONEY      — Industry donations >= $50K
  Dot 7: MAJOR_MONEY            — Industry donations >= $500K
  Dot 8: SUSPICIOUS_TIMING      — Donation within 90 days before bill introduction
  Dot 9: INSIDER_TRADE          — Official traded stocks in companies they regulate
  Dot 10: VOTED_FOR_DONOR_INTEREST — Official voted YES on bill their donor lobbied for

Verdicts:
  1 dot   = NORMAL      (just got donations, everyone does)
  2 dots  = CONNECTED   (structural relationship exists)
  4+ dots = INFLUENCED  (money -> power -> legislation chain complete)
  OWNED   = 2+ industries each score INFLUENCED or higher
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entity, Relationship
from app.services.conflict_engine import (
    _extract_industry_keywords,
    _industries_for_committee,
    _keyword_overlap,
    _sanitize,
)

# ── Policy area to industry keyword mapping ──────────────────────────────
# Maps bill policy_area strings (from Congress.gov) to the same industry
# keywords used by COMMITTEE_INDUSTRY_MAP so we can compare them.
POLICY_AREA_INDUSTRY_MAP: dict[str, list[str]] = {
    "finance and financial sector": ["finance", "banking", "securities", "insurance"],
    "economics and public finance": ["finance", "economics", "budget", "tax"],
    "taxation": ["finance", "tax"],
    "health": ["health", "pharma", "pharmaceutical", "medical", "biotech"],
    "energy": ["energy", "oil", "gas", "mining", "nuclear", "utilities"],
    "agriculture and food": ["agriculture", "food", "farming", "agribusiness"],
    "environmental protection": ["environment", "conservation", "climate", "water"],
    "science, technology, communications": ["technology", "telecom", "communications"],
    "transportation and public works": ["transportation", "infrastructure", "airline", "railroad"],
    "armed forces and national security": ["defense", "military", "aerospace", "weapons"],
    "crime and law enforcement": ["legal", "law", "courts", "prison", "corrections"],
    "international affairs": ["foreign", "trade", "international", "diplomacy"],
    "education": ["education"],
    "labor and employment": ["labor", "employment"],
    "housing and community development": ["real estate", "housing"],
    "commerce": ["commerce", "consumer", "retail", "trade"],
    "public lands and natural resources": ["environment", "mining", "conservation"],
    "immigration": ["immigration", "border"],
    "native americans": ["tribal", "native", "casino", "gaming"],
    "government operations and politics": ["government", "administration"],
}


def _industry_keywords_for_policy_area(policy_area: str) -> list[str]:
    """Map a bill's policy_area to industry keywords."""
    if not policy_area:
        return []
    pa_lower = _sanitize(policy_area).lower().strip()
    # Exact match first
    if pa_lower in POLICY_AREA_INDUSTRY_MAP:
        return POLICY_AREA_INDUSTRY_MAP[pa_lower]
    # Fuzzy: check if any key is contained in the policy_area or vice-versa
    for key, kws in POLICY_AREA_INDUSTRY_MAP.items():
        if key in pa_lower or pa_lower in key:
            return kws
    # Last resort: split words
    return pa_lower.split()


def _verdict_for_dots(dot_count: int) -> str:
    """Map dot count to verdict string."""
    if dot_count >= 4:
        return "INFLUENCED"
    if dot_count >= 2:
        return "CONNECTED"
    return "NORMAL"


def _fmt_amount(cents: int) -> str:
    """Format cents as human-readable dollar string."""
    if cents is None or cents == 0:
        return "$0"
    dollars = cents / 100
    if dollars >= 1_000_000:
        return f"${dollars / 1_000_000:.1f}M"
    if dollars >= 1_000:
        return f"${dollars / 1_000:.0f}K"
    return f"${dollars:,.0f}"


def _generate_narrative(
    industry: str,
    donors: list[dict],
    committees: list[dict],
    bills: list[dict],
    lobbying: list[dict],
    middlemen: list[dict],
    total_amount: int,
    total_campaign: int = 0,
    timing_hits: list[dict] | None = None,
    trades: list[dict] | None = None,
    votes: list[dict] | None = None,
) -> str:
    """Build a human-readable narrative for an industry trail."""
    parts: list[str] = []

    if len(donors) == 1:
        parts.append(f"{donors[0]['name']} donated {_fmt_amount(total_amount)} to this official.")
    else:
        top_names = ", ".join(d["name"] for d in donors[:3])
        if len(donors) > 3:
            top_names += f" and {len(donors) - 3} others"
        parts.append(f"{len(donors)} {industry} donors gave {_fmt_amount(total_amount)} total (top: {top_names}).")

    if committees:
        committee_names = ", ".join(c["name"] for c in committees[:2])
        parts.append(f"This official sits on {committee_names} which regulates the {industry} industry.")

    if bills:
        parts.append(f"They sponsored {len(bills)} bill{'s' if len(bills) != 1 else ''} affecting this sector.")

    if total_campaign > 0 and total_campaign > total_amount:
        parts.append(
            f"Total campaign donations: {_fmt_amount(total_campaign)}"
            f" — {industry} industry represents {_fmt_amount(total_amount)} of that."
        )

    if lobbying:
        parts.append(f"{len(lobbying)} of these donors also lobby Congress on related issues.")

    if middlemen:
        mid_names = ", ".join(m["name"] for m in middlemen[:2])
        parts.append(f"Money flowed through {mid_names}.")

    if timing_hits:
        closest = min(timing_hits, key=lambda h: h["days_before"])
        if closest["days_before"] == 0:
            parts.append(
                f"⚠ TIMING: {closest['donor']} donated the SAME DAY "
                f"{closest['bill']} was introduced ({closest['bill_date']})."
            )
        elif closest["days_before"] <= 14:
            parts.append(
                f"⚠ TIMING: {closest['donor']} donated just "
                f"{closest['days_before']} days before "
                f"{closest['bill']} was introduced ({closest['bill_date']})."
            )
        else:
            parts.append(
                f"⚠ TIMING: {closest['donor']} donated "
                f"{closest['days_before']} days before "
                f"{closest['bill']} was introduced."
            )
        if len(timing_hits) > 1:
            parts.append(f"{len(timing_hits)} total suspicious timing correlations found.")

    if trades:
        trade_tickers = ", ".join(t.get("ticker", "?") for t in trades[:3])
        buys = sum(1 for t in trades if t.get("transaction_type", "").lower() in ("purchase", "p", "buy"))
        sells = sum(1 for t in trades if t.get("transaction_type", "").lower() in ("sale", "s", "sell", "sale (partial)", "sale (full)"))
        parts.append(
            f"🔴 STOCK TRADES: This official (or spouse) traded {trade_tickers} "
            f"({buys} buys, {sells} sells) — stocks in the same industry they regulate and legislate."
        )

    if votes:
        unique_bills = {v["bill"] for v in votes}
        unique_donors = {v["donor"] for v in votes}
        total_vote_money = sum(v.get("donation_amount", 0) for v in votes)
        parts.append(
            f"🔴 VOTED WITH DONORS: This official voted YES on {len(unique_bills)} bill(s) "
            f"that {len(unique_donors)} of their donors lobbied for "
            f"(donors gave {_fmt_amount(total_vote_money)} total)."
        )

    return " ".join(parts)


# ── Main engine ──────────────────────────────────────────────────────────


async def compute_verdicts(
    session: AsyncSession, official_id: uuid.UUID
) -> list[dict]:
    """Compute money trail verdicts for an official, grouped by industry.

    Returns list of dicts, one per industry trail:
    {
        "industry": "Finance",
        "verdict": "INFLUENCED",
        "dot_count": 3,
        "dots": ["donor_from_industry", "regulating_committee", ...],
        "chain": {
            "donors": [...],
            "committees": [...],
            "bills": [...],
            "middlemen": [...],
            "lobbying": [...],
        },
        "narrative": "...",
        "total_amount": 500000,
    }
    """
    # ── Step 1: Load all relationships involving this official ────────
    # Outgoing: official -> committee, official -> bill (sponsored/cosponsored/voted)
    # Incoming: donor -> official (donated_to)
    outgoing_q = (
        select(Relationship)
        .where(Relationship.from_entity_id == official_id)
        .where(
            Relationship.relationship_type.in_(
                ["committee_member", "sponsored", "cosponsored",
                 "stock_trade", "holds_stock", "voted_yes", "voted_no"]
            )
        )
    )
    incoming_q = (
        select(Relationship)
        .where(Relationship.to_entity_id == official_id)
        .where(Relationship.relationship_type == "donated_to")
    )

    outgoing_result = await session.execute(outgoing_q)
    incoming_result = await session.execute(incoming_q)
    outgoing_rels = outgoing_result.scalars().all()
    incoming_rels = incoming_result.scalars().all()

    if not incoming_rels:
        return []  # No donors, no trails

    # ── Step 2: Collect entity IDs we need to load ────────────────────
    entity_ids: set[uuid.UUID] = {official_id}
    committee_rel_map: dict[uuid.UUID, list[Relationship]] = defaultdict(list)
    bill_rel_map: dict[uuid.UUID, list[Relationship]] = defaultdict(list)
    donor_rels: list[Relationship] = list(incoming_rels)

    trade_rels: list[Relationship] = []
    vote_rels: dict[uuid.UUID, str] = {}  # bill_id -> "voted_yes" or "voted_no"
    for rel in outgoing_rels:
        entity_ids.add(rel.to_entity_id)
        if rel.relationship_type == "committee_member":
            committee_rel_map[rel.to_entity_id].append(rel)
        elif rel.relationship_type in ("sponsored", "cosponsored"):
            bill_rel_map[rel.to_entity_id].append(rel)
        elif rel.relationship_type in ("stock_trade", "holds_stock"):
            trade_rels.append(rel)
        elif rel.relationship_type in ("voted_yes", "voted_no"):
            vote_rels[rel.to_entity_id] = rel.relationship_type

    donor_ids: set[uuid.UUID] = set()
    for rel in donor_rels:
        entity_ids.add(rel.from_entity_id)
        donor_ids.add(rel.from_entity_id)

    # ── Step 3: Load all referenced entities ──────────────────────────
    entities_q = select(Entity).where(Entity.id.in_(list(entity_ids)))
    entities_result = await session.execute(entities_q)
    entities_by_id: dict[uuid.UUID, Entity] = {
        e.id: e for e in entities_result.scalars().all()
    }

    # ── Step 4: Load lobbying relationships for donors ────────────────
    # Look for lobbies_on_behalf_of where from_entity or to_entity is a donor
    lobby_rels: list[Relationship] = []
    if donor_ids:
        lobby_q = (
            select(Relationship)
            .where(
                or_(
                    Relationship.from_entity_id.in_(list(donor_ids)),
                    Relationship.to_entity_id.in_(list(donor_ids)),
                )
            )
            .where(Relationship.relationship_type == "lobbies_on_behalf_of")
        )
        lobby_result = await session.execute(lobby_q)
        lobby_rels = list(lobby_result.scalars().all())

    # ── Step 4b: Identify true middleman PACs ─────────────────────────
    # A PAC is a middleman only if OTHER entities donated TO it.
    # Pre-load which donor PACs have incoming donations.
    pac_donor_ids = {
        did for did in donor_ids
        if entities_by_id.get(did) and entities_by_id[did].entity_type == "pac"
    }
    pacs_with_incoming: set[uuid.UUID] = set()
    if pac_donor_ids:
        pac_incoming_q = (
            select(Relationship.to_entity_id)
            .where(Relationship.to_entity_id.in_(list(pac_donor_ids)))
            .where(Relationship.relationship_type == "donated_to")
            .where(Relationship.from_entity_id != official_id)  # exclude self-referential
            .limit(1000)
        )
        pac_incoming_result = await session.execute(pac_incoming_q)
        pacs_with_incoming = {row[0] for row in pac_incoming_result.all()}

    # Load any additional entities referenced by lobbying rels
    lobby_entity_ids: set[uuid.UUID] = set()
    for rel in lobby_rels:
        lobby_entity_ids.add(rel.from_entity_id)
        lobby_entity_ids.add(rel.to_entity_id)
    missing_ids = lobby_entity_ids - set(entities_by_id.keys())
    if missing_ids:
        extra_q = select(Entity).where(Entity.id.in_(list(missing_ids)))
        extra_result = await session.execute(extra_q)
        for e in extra_result.scalars().all():
            entities_by_id[e.id] = e

    # ── Step 5: Build committee industry map ──────────────────────────
    # committee_id -> industry keywords
    committee_industries: dict[uuid.UUID, list[str]] = {}
    for cid in committee_rel_map:
        entity = entities_by_id.get(cid)
        if entity:
            committee_industries[cid] = _industries_for_committee(entity.name)

    # Leadership detection: Speaker, Majority/Minority Leader, Whips
    # have jurisdiction over ALL legislation, so they regulate every industry
    is_leadership = False
    official_entity = entities_by_id.get(official_id)
    if official_entity and not committee_industries:
        official_name_raw = (official_entity.name or "").lower()
        meta = official_entity.metadata_ or {}
        leadership_keywords = {"speaker", "majority leader", "minority leader",
                               "whip", "majority whip", "minority whip", "leader"}
        title = (meta.get("title") or meta.get("leadership_role") or "").lower()
        # Known leadership members by slug
        known_leaders = {
            "pelosi-nancy", "johnson-mike", "jeffries-hakeem-s",
            "scalise-steve", "clark-katherine-m", "schumer-charles-e",
            "mcconnell-mitch", "thune-john",
        }
        if (any(kw in title for kw in leadership_keywords)
                or official_entity.slug in known_leaders):
            is_leadership = True
            # Leadership has jurisdiction over all industries
            all_industry_keywords = list(set(
                kw for kws in POLICY_AREA_INDUSTRY_MAP.values() for kw in kws
            ))
            # Create a synthetic "leadership" committee entry
            committee_industries[official_id] = all_industry_keywords

    # All industry keywords from all committees the official sits on
    all_committee_keywords: list[str] = []
    for kws in committee_industries.values():
        all_committee_keywords.extend(kws)

    # ── Step 6: Build bill industry map ───────────────────────────────
    # bill_id -> industry keywords from policy_area
    bill_industries: dict[uuid.UUID, list[str]] = {}
    for bid in bill_rel_map:
        entity = entities_by_id.get(bid)
        if entity:
            meta = entity.metadata_ or {}
            policy_area = meta.get("policy_area", "")
            bill_industries[bid] = _industry_keywords_for_policy_area(policy_area)

    # ── Step 7: Group donors by industry ──────────────────────────────
    # industry_keyword -> list of (donor_entity, relationship)
    industry_donors: dict[str, list[tuple[Entity, Relationship]]] = defaultdict(list)

    # Get official's name for self-donation detection
    official_entity = entities_by_id.get(official_id) or (await session.get(Entity, official_id))
    official_name_lower = (official_entity.name if official_entity else "").lower().replace(",", "").strip()
    official_slug = (official_entity.slug if official_entity else "")
    official_last_name = official_name_lower.split()[0] if official_name_lower else ""

    def _is_self_donation(donor_entity: Entity) -> bool:
        """Detect if a donor is the official themselves or their personal PAC."""
        dn = donor_entity.name.lower().replace(",", "").strip()
        ds = donor_entity.slug
        # Same entity
        if donor_entity.id == official_id:
            return True
        # Name match: "MCCORMICK, DAVE" vs "McCormick, David"
        if official_last_name and len(official_last_name) > 2:
            donor_parts = dn.split()
            if donor_parts and donor_parts[0] == official_last_name:
                return True
        # Victory fund / campaign committee named after official
        slug_parts = official_slug.split("-")
        if len(slug_parts) >= 1 and slug_parts[0] in ds:
            name_keywords = {"victory", "for congress", "for senate", "committee", "fund", "team"}
            if any(kw in dn for kw in name_keywords):
                return True
        return False

    for rel in donor_rels:
        donor = entities_by_id.get(rel.from_entity_id)
        if not donor:
            continue
        # Skip self-donations — own money is not industry influence
        if _is_self_donation(donor):
            continue
        keywords = _extract_industry_keywords(donor)
        if not keywords:
            # Use "general" as fallback
            industry_donors["general"].append((donor, rel))
            continue
        # Assign donor to each matching industry keyword that is also
        # relevant (appears in committee or bill industries, or is a
        # well-known industry keyword).
        assigned = False
        for kw in keywords:
            kw_lower = kw.lower().strip()
            if kw_lower and len(kw_lower) > 2:
                industry_donors[kw_lower].append((donor, rel))
                assigned = True
        if not assigned:
            industry_donors["general"].append((donor, rel))

    # ── Step 7b: Filter out junk industry keys ──────────────────────────
    # Only keep keys that are recognised industry terms or canonical names
    _STOPWORDS = {
        "pac", "political", "action", "committee", "fund", "inc", "inc.",
        "llc", "corp", "corporation", "association", "national", "american",
        "united", "states", "federal", "employees", "international",
        "voluntary", "the", "for", "and", "fka", "formerly", "known",
    }
    cleaned_donors: dict[str, list[tuple[Entity, Relationship]]] = defaultdict(list)
    for kw, donor_list in industry_donors.items():
        if kw in _STOPWORDS or kw == "general":
            # Push stopword donors back to "general" (they'll be skipped)
            if kw != "general":
                cleaned_donors["general"].extend(donor_list)
            else:
                cleaned_donors["general"] = donor_list
        else:
            cleaned_donors[kw] = donor_list
    industry_donors = cleaned_donors

    # ── Step 8: Merge related industry keywords ───────────────────────
    # Consolidate synonymous industry keys into canonical industries
    CANONICAL_INDUSTRIES: dict[str, str] = {
        "banking": "finance",
        "securities": "finance",
        "insurance": "finance",
        "investment": "finance",
        "real estate": "finance",
        "oil": "energy",
        "gas": "energy",
        "nuclear": "energy",
        "utilities": "energy",
        "mining": "energy",
        "pharma": "health",
        "pharmaceutical": "health",
        "medical": "health",
        "biotech": "health",
        "military": "defense",
        "aerospace": "defense",
        "weapons": "defense",
        "telecom": "technology",
        "communications": "technology",
        "media": "technology",
        "food": "agriculture",
        "farming": "agriculture",
        "agribusiness": "agriculture",
        "conservation": "environment",
        "climate": "environment",
        "water": "environment",
        "law": "legal",
        "courts": "legal",
        "prison": "legal",
        "corrections": "legal",
        "infrastructure": "transportation",
        "airline": "transportation",
        "railroad": "transportation",
        "trade": "international",
        "diplomacy": "international",
        "foreign": "international",
        "tribal": "native affairs",
        "native": "native affairs",
        "casino": "native affairs",
        "gaming": "native affairs",
        "budget": "government",
        "administration": "government",
        "tax": "finance",
        "economics": "finance",
    }

    def _canonicalize_keywords(keywords: list[str]) -> set[str]:
        """Convert raw keywords to canonical industry names."""
        canonical = set()
        for kw in keywords:
            kw_lower = kw.lower().strip()
            if kw_lower in CANONICAL_INDUSTRIES:
                canonical.add(CANONICAL_INDUSTRIES[kw_lower])
            else:
                canonical.add(kw_lower)
        return canonical

    # Regroup by canonical industry
    canonical_donors: dict[str, list[tuple[Entity, Relationship]]] = defaultdict(list)
    for raw_kw, donor_list in industry_donors.items():
        canonical = CANONICAL_INDUSTRIES.get(raw_kw, raw_kw)
        # Deduplicate: same donor+rel shouldn't appear twice
        for item in donor_list:
            if item not in canonical_donors[canonical]:
                canonical_donors[canonical].append(item)

    # ── Step 9: Compute dots per canonical industry ───────────────────
    trails: list[dict] = []

    # Pre-compute total campaign money (all donors combined)
    total_campaign = sum(r.amount_usd or 0 for r in donor_rels)

    # Build a set of all donor rels for "other donors" display
    all_donor_entries: list[tuple[Entity, Relationship]] = []
    all_donor_ids_seen: set[uuid.UUID] = set()
    for rel in donor_rels:
        donor = entities_by_id.get(rel.from_entity_id)
        if donor and donor.id not in all_donor_ids_seen:
            all_donor_ids_seen.add(donor.id)
            all_donor_entries.append((donor, rel))
    # Sort by amount desc
    all_donor_entries.sort(key=lambda x: x[1].amount_usd or 0, reverse=True)

    for industry, donor_list in canonical_donors.items():
        if industry == "general":
            continue  # Skip unclassifiable donors

        # Deduplicate donors by entity ID
        seen_donor_ids: set[uuid.UUID] = set()
        unique_donors: list[tuple[Entity, Relationship]] = []
        total_amount = 0
        for donor_entity, rel in donor_list:
            if donor_entity.id not in seen_donor_ids:
                seen_donor_ids.add(donor_entity.id)
                unique_donors.append((donor_entity, rel))
            total_amount += rel.amount_usd or 0

        dots: list[str] = []
        chain_donors: list[dict] = []
        chain_committees: list[dict] = []
        chain_bills: list[dict] = []
        chain_middlemen: list[dict] = []
        chain_lobbying: list[dict] = []

        # ── Dot 1: DONOR_FROM_INDUSTRY ────────────────────────────────
        # Always true if we're processing this industry
        dots.append("donor_from_industry")
        for donor_entity, rel in unique_donors:
            chain_donors.append({
                "name": _sanitize(donor_entity.name),
                "slug": donor_entity.slug,
                "amount": rel.amount_usd or 0,
                "date": rel.date_start.isoformat() if rel.date_start else None,
            })

        # ── Dot 2: REGULATING_COMMITTEE ───────────────────────────────
        for cid, kws in committee_industries.items():
            canon_kws = _canonicalize_keywords(kws)
            if industry in canon_kws:
                entity = entities_by_id.get(cid)
                if entity and not any(
                    c["slug"] == entity.slug for c in chain_committees
                ):
                    chain_committees.append({
                        "name": _sanitize(entity.name),
                        "slug": entity.slug,
                    })
        if chain_committees:
            dots.append("regulating_committee")

        # ── Dot 3: SPONSORED_ALIGNED_BILLS ────────────────────────────
        for bid, kws in bill_industries.items():
            if _keyword_overlap(kws, [industry]):
                entity = entities_by_id.get(bid)
                if entity and not any(
                    b["slug"] == entity.slug for b in chain_bills
                ):
                    bill_meta = entity.metadata_ or {}
                    chain_bills.append({
                        "name": _sanitize(entity.name),
                        "slug": entity.slug,
                        "date": bill_meta.get("introduced_date"),
                    })
        if chain_bills:
            dots.append("sponsored_aligned_bills")

        # ── Dot 4: DONOR_LOBBIES ──────────────────────────────────────
        for rel in lobby_rels:
            firm = entities_by_id.get(rel.from_entity_id)
            client = entities_by_id.get(rel.to_entity_id)
            # Check if any donor is involved (as firm or client)
            connected = (
                rel.from_entity_id in seen_donor_ids
                or rel.to_entity_id in seen_donor_ids
            )
            if connected:
                meta = rel.metadata_ or {}
                issue = meta.get("issue", meta.get("general_issue_code", ""))
                description = meta.get("description", "")
                # Filter: only count if lobbying issue/description
                # overlaps with the current industry
                issue_text = f"{issue} {description}".lower()
                issue_words = [w.strip() for w in issue_text.split() if len(w.strip()) > 2]
                canon_issue_kws = _canonicalize_keywords(issue_words)
                if industry not in canon_issue_kws and not _keyword_overlap(issue_words, [industry]):
                    continue
                chain_lobbying.append({
                    "firm": _sanitize(firm.name) if firm else "Unknown",
                    "client": _sanitize(client.name) if client else "Unknown",
                    "issue": _sanitize(str(issue)) if issue else "",
                    "date": rel.date_start.isoformat() if rel.date_start else None,
                })
        if chain_lobbying:
            dots.append("donor_lobbies")

        # ── Dot 5: MIDDLEMAN_PAC ──────────────────────────────────────
        # Only count PACs that have incoming donations from others
        # (i.e., money flows THROUGH them, not just FROM them)
        for donor_entity, rel in unique_donors:
            if (
                donor_entity.entity_type == "pac"
                and donor_entity.id in pacs_with_incoming
            ):
                chain_middlemen.append({
                    "name": _sanitize(donor_entity.name),
                    "slug": donor_entity.slug,
                    "amount_in": rel.amount_usd or 0,
                    "amount_out": rel.amount_usd or 0,
                })
        if chain_middlemen:
            dots.append("middleman_pac")

        # ── Dot 6: SIGNIFICANT_MONEY ────────────────────────────────
        # Factor in the aggregate dollar amount from this industry
        # $50K+ = 1 additional dot, $500K+ = 2 additional dots
        if total_amount >= 50_000_00:  # $50K in cents
            dots.append("significant_money")
        if total_amount >= 500_000_00:  # $500K in cents
            dots.append("major_money")

        # ── Dot 8: SUSPICIOUS_TIMING ────────────────────────────────
        # If any donation came within 90 days BEFORE a related bill
        # was introduced, that's a timing signal.
        timing_window_days = 90
        timing_hits: list[dict] = []
        for donor_entry in chain_donors:
            d_date_str = donor_entry.get("date")
            if not d_date_str:
                continue
            try:
                from datetime import date as date_type
                d_date = date_type.fromisoformat(d_date_str[:10])
            except (ValueError, TypeError):
                continue
            for bill_entry in chain_bills:
                b_date_str = bill_entry.get("date")
                if not b_date_str:
                    continue
                try:
                    b_date = date_type.fromisoformat(b_date_str[:10])
                except (ValueError, TypeError):
                    continue
                # Donation came before the bill (or same day)
                delta = (b_date - d_date).days
                if 0 <= delta <= timing_window_days:
                    timing_hits.append({
                        "donor": donor_entry["name"],
                        "donor_slug": donor_entry.get("slug", ""),
                        "amount": donor_entry.get("amount", 0),
                        "donation_date": d_date_str[:10],
                        "bill": bill_entry["name"],
                        "bill_slug": bill_entry.get("slug", ""),
                        "bill_date": b_date_str[:10],
                        "days_before": delta,
                    })
        if timing_hits:
            dots.append("suspicious_timing")

        # ── Dot 9: INSIDER_TRADE ─────────────────────────────────────
        # Did the official (or spouse) trade stocks in companies from
        # this industry? Cross-reference trade tickers against industry.
        chain_trades: list[dict] = []
        for trel in trade_rels:
            stock_entity = entities_by_id.get(trel.to_entity_id)
            if not stock_entity:
                continue
            # Check if this stock relates to the current industry
            stock_name = (stock_entity.name or "").lower()
            stock_meta = stock_entity.metadata_ or {}
            stock_ticker = (stock_meta.get("ticker", "") or "").lower()
            # Match: stock name/ticker contains industry keyword, or
            # industry keyword appears in the stock entity's industry metadata
            stock_words = set(stock_name.split())
            stock_industry = (stock_meta.get("industry", "") or "").lower()
            match = (
                industry.lower() in stock_name
                or industry.lower() in stock_industry
                or _keyword_overlap([industry.lower()], list(stock_words))
                or _keyword_overlap(
                    _extract_industry_keywords(stock_entity),
                    [industry.lower()],
                )
            )
            if match:
                trel_meta = trel.metadata_ or {}
                chain_trades.append({
                    "ticker": stock_ticker.upper() or stock_entity.name,
                    "asset": _sanitize(stock_entity.name),
                    "transaction_type": trel_meta.get("transaction_type", "Unknown"),
                    "amount_range": trel.amount_label or trel_meta.get("amount_range", ""),
                    "date": trel.date_start.isoformat() if trel.date_start else None,
                    "owner": trel_meta.get("owner", ""),
                })
        if chain_trades:
            dots.append("insider_trade")

            # ── Dot 9b: MAJOR_INSIDER_TRADE ─────────────────────────
            # Scale by trade size — $100K+ trades get extra dots
            _AMOUNT_RANGES = {
                "$1,000,001": 3,   # $1M+ = 3 extra dots
                "$500,001": 2,     # $500K+ = 2 extra dots
                "$250,001": 1,     # $250K+ = 1 extra dot
                "$100,001": 1,     # $100K+ = 1 extra dot
            }
            max_trade_bonus = 0
            for trade in chain_trades:
                amt_range = trade.get("amount_range", "")
                for threshold, bonus in _AMOUNT_RANGES.items():
                    if threshold in amt_range:
                        max_trade_bonus = max(max_trade_bonus, bonus)
                        break
            for _ in range(max_trade_bonus):
                dots.append("major_insider_trade")

        # ── Dot 10: VOTED_FOR_DONOR_INTEREST ─────────────────────────
        # Did the official vote YES on a bill that was lobbied on by one of
        # their donors (or a donor's lobbying client)?
        chain_votes: list[dict] = []
        if vote_rels and chain_bills:
            # Get bill IDs from this industry that the official voted YES on
            voted_yes_bills = set()
            for bill_entry in chain_bills:
                bill_slug = bill_entry.get("slug", "")
                for bid, kws in bill_industries.items():
                    bill_ent = entities_by_id.get(bid)
                    if bill_ent and bill_ent.slug == bill_slug:
                        if vote_rels.get(bid) == "voted_yes":
                            voted_yes_bills.add(bid)
                        break

            if voted_yes_bills:
                # Check if any donor (or connected entity) lobbied on these bills
                for bill_id in voted_yes_bills:
                    bill_ent = entities_by_id.get(bill_id)
                    bill_name = _sanitize(bill_ent.name) if bill_ent else "Unknown"
                    # Check lobbied_on relationships for this bill
                    for donor_entity, donor_rel in unique_donors:
                        # Direct match: donor entity lobbied on the bill
                        for lrel in lobby_rels:
                            lobby_connected = (
                                lrel.from_entity_id == donor_entity.id
                                or lrel.to_entity_id == donor_entity.id
                            )
                            if lobby_connected:
                                chain_votes.append({
                                    "bill": bill_name,
                                    "bill_slug": bill_ent.slug if bill_ent else "",
                                    "donor": _sanitize(donor_entity.name),
                                    "donor_slug": donor_entity.slug,
                                    "vote": "YES",
                                    "donation_amount": donor_rel.amount_usd or 0,
                                })
                                break

        if chain_votes:
            dots.append("voted_for_donor_interest")

        # ── Build trail ───────────────────────────────────────────────
        dot_count = len(dots)
        verdict = _verdict_for_dots(dot_count)

        narrative = _generate_narrative(
            industry=industry,
            donors=chain_donors,
            committees=chain_committees,
            bills=chain_bills,
            lobbying=chain_lobbying,
            middlemen=chain_middlemen,
            total_amount=total_amount,
            total_campaign=total_campaign,
            timing_hits=timing_hits,
            trades=chain_trades,
            votes=chain_votes,
        )

        # Build "other top donors" — biggest donors NOT in this industry
        other_donors: list[dict] = []
        for od_entity, od_rel in all_donor_entries[:10]:
            if od_entity.id not in seen_donor_ids:
                other_donors.append({
                    "name": _sanitize(od_entity.name),
                    "slug": od_entity.slug,
                    "amount": od_rel.amount_usd or 0,
                })
            if len(other_donors) >= 5:
                break

        trails.append({
            "industry": industry.title(),
            "verdict": verdict,
            "dot_count": dot_count,
            "dots": dots,
            "chain": {
                "donors": chain_donors,
                "committees": chain_committees,
                "bills": chain_bills,
                "middlemen": chain_middlemen,
                "lobbying": chain_lobbying,
                "timing_hits": timing_hits,
                "trades": chain_trades,
                "votes": chain_votes,
            },
            "narrative": narrative,
            "total_amount": total_amount,
            "total_campaign": total_campaign,
            "other_top_donors": other_donors,
            "donor_count": len(unique_donors),
        })

    # Sort trails: highest dot count first, then by total amount
    trails.sort(key=lambda t: (-t["dot_count"], -t["total_amount"]))

    return trails


def compute_overall_verdict(trails: list[dict]) -> tuple[str, int]:
    """Given all industry trails, compute the official's overall verdict.

    OWNED       = Deep structural capture across multiple industries
    COMPROMISED = Strong trade-based conflicts even without donation chains
    INFLUENCED  = Clear money → power → legislation chain in at least 1 industry
    CONNECTED   = Structural relationships exist
    NORMAL      = No concerning patterns detected

    Returns (verdict, total_dots_across_all_industries)
    """
    if not trails:
        return ("NORMAL", 0)

    total_dots = sum(t["dot_count"] for t in trails)
    total_money = sum(t["total_amount"] for t in trails)
    influenced_count = sum(1 for t in trails if t["verdict"] == "INFLUENCED")
    connected_count = sum(1 for t in trails if t["verdict"] == "CONNECTED")

    # Count industries with insider trades and trade-size bonus dots
    has_insider_trade = sum(
        1 for t in trails
        if "insider_trade" in t.get("dots", [])
    )
    has_major_trade = sum(
        1 for t in trails
        if "major_insider_trade" in t.get("dots", [])
    )
    has_voted_for_donors = sum(
        1 for t in trails
        if "voted_for_donor_interest" in t.get("dots", [])
    )

    # OWNED: deep structural capture
    if influenced_count >= 2:
        return ("OWNED", total_dots)
    if influenced_count >= 1 and total_money >= 1_000_000_00:  # $1M in cents
        return ("OWNED", total_dots)
    # OWNED via trades: major insider trades in 2+ industries
    if has_major_trade >= 2:
        return ("OWNED", total_dots)
    # OWNED via combined signals: influenced + insider trades
    if influenced_count >= 1 and has_insider_trade >= 1:
        return ("OWNED", total_dots)

    # COMPROMISED: trade-based conflicts without full donation chain
    if has_major_trade >= 1 and connected_count >= 2:
        return ("COMPROMISED", total_dots)
    if has_insider_trade >= 2 and connected_count >= 1:
        return ("COMPROMISED", total_dots)
    # Voted with donor interest + trades = COMPROMISED
    if has_voted_for_donors >= 1 and has_insider_trade >= 1:
        return ("COMPROMISED", total_dots)

    if influenced_count >= 1:
        return ("INFLUENCED", total_dots)
    if any(t["dot_count"] >= 2 for t in trails):
        return ("CONNECTED", total_dots)
    return ("NORMAL", total_dots)
