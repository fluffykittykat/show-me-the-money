"""
Conflict Detection Engine — Structural Transparency Mode
Surfaces structural relationships for public awareness.

The tool's job is NOT to accuse anyone. It surfaces structural relationships
the user would never know to look for, presents the facts, and lets the user
draw their own conclusions.

A "structural relationship" is detected when signals align:
1. Official sits on committee with jurisdiction over an industry
2. Official received donations from that industry
3. Official voted on legislation affecting that industry
4. Official holds stock in companies in that industry
5. Company actively lobbying while connected to official

Severity scoring:
- 1 signal = connection_noted (display: "Connection Noted")
- 2 signals = structural_relationship (display: "Structural Relationship - User Should Know")
- 3+ signals = notable_pattern (display: "Notable Pattern - Worth Investigating")
- Full alignment / lobbying = high_concern (display: "High Concern - Review Recommended")

Timing window: 180 days

Structural alerts fire based purely on structural facts, even with zero
voting evidence.
"""

import json
import subprocess
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entity, Relationship


# ---------------------------------------------------------------------------
# Severity display labels
# ---------------------------------------------------------------------------
SEVERITY_DISPLAY = {
    "connection_noted": "Connection Noted",
    "structural_relationship": "Structural Relationship \u2014 User Should Know",
    "notable_pattern": "Notable Pattern \u2014 Worth Investigating",
    "high_concern": "High Concern \u2014 Review Recommended",
}


# ---------------------------------------------------------------------------
# Why This Matters explainers
# ---------------------------------------------------------------------------
WHY_THIS_MATTERS = {
    "structural_committee_donor_overlap": (
        "Officials who receive campaign donations from industries they regulate "
        "may face pressure \u2014 conscious or unconscious \u2014 when voting on "
        "legislation that affects those donors. This is not an accusation of "
        "wrongdoing. It is a structural relationship the public has a right to "
        "know about."
    ),
    "structural_stock_vote_alignment": (
        "When an official holds stock in companies affected by legislation they "
        "vote on, there is a structural financial incentive that the public "
        "should be aware of, even if the official votes against their financial "
        "interest."
    ),
    "structural_donor_vote_timing": (
        "The timing of campaign donations relative to legislative votes can "
        "suggest \u2014 but does not prove \u2014 that donations influenced "
        "voting decisions. This pattern is worth noting regardless of the "
        "official's actual vote."
    ),
    "full_structural_alignment": (
        "When multiple structural relationships align \u2014 committee "
        "jurisdiction, campaign donations, stock holdings, and voting patterns "
        "\u2014 the cumulative pattern warrants public awareness, even if each "
        "individual relationship is common in politics."
    ),
    "structural_committee_jurisdiction": (
        "Committee assignments give officials direct regulatory authority over "
        "specific industries. When those same industries contribute to the "
        "official's campaign or the official holds financial interests in those "
        "industries, the structural relationship is worth public scrutiny."
    ),
    "structural_lobbying_regulatory_overlap": (
        "When a company actively lobbies on issues before a committee AND "
        "contributes to officials on that committee, there is a structural "
        "pathway for influence that the public should understand."
    ),
    "donation_vote_timing_pattern": (
        "Donations received shortly before related legislative votes create a "
        "temporal pattern that, while not evidence of corruption, represents the "
        "kind of structural relationship investigative journalists and the "
        "public look for."
    ),
    "pre_vote_donation_pattern": (
        "Unusually large donations in the months before a key vote from "
        "industries that benefit from that vote represent a notable pattern "
        "worth public awareness."
    ),
    "revolving_door_access": (
        "This person used to work in government, and now they get paid to "
        "lobby the very same officials they used to work with. They know "
        "exactly who to call, what to say, and how the system works from "
        "the inside. The question is: should someone be allowed to cash in "
        "on government connections like this?"
    ),
    "family_employer_conflict": (
        "A close family member of this official gets a paycheck from a "
        "company that this official has power over through their committee "
        "work. Even if the official tries to be fair, the family income "
        "creates a built-in reason to go easy on that company. Would you "
        "trust a referee whose spouse worked for one of the teams?"
    ),
    "paid_speaking_regulated_industry": (
        "This official got paid thousands of dollars to give a speech to "
        "a company or industry group. Speaking fees are legal, but they "
        "create a personal financial relationship between the official and "
        "the people they are supposed to be regulating. Ask yourself: if "
        "someone paid you $50,000 for a speech, would you feel completely "
        "neutral about them?"
    ),
    "contractor_donor_pattern": (
        "A company donated money to this official's campaign, and then "
        "that same company got a government contract worth many times more "
        "than the donation. This does not prove the donation bought the "
        "contract, but the pattern is worth noticing. The question is: "
        "would that company have gotten the contract if they had not donated?"
    ),
    "suspicious_trade_timing": (
        "This official bought or sold stock right before their committee "
        "took action that moved the stock price. Members of Congress get "
        "briefings and inside information that regular people do not have. "
        "The timing of these trades raises a simple question: did they know "
        "something the rest of us did not?"
    ),
}


# ---------------------------------------------------------------------------
# Committee -> industry keyword mapping
# ---------------------------------------------------------------------------
COMMITTEE_INDUSTRY_MAP: dict[str, list[str]] = {
    "banking": ["finance", "banking", "insurance", "real estate", "securities"],
    "agriculture": ["agriculture", "food", "farming", "agribusiness"],
    "joint economic": ["finance", "economics", "trade"],
    "commerce": ["technology", "telecom", "communications", "media", "consumer"],
    "energy": ["energy", "oil", "gas", "mining", "nuclear", "utilities"],
    "environment": ["environment", "conservation", "climate", "water"],
    "finance": ["finance", "tax", "banking", "insurance", "securities"],
    "health": ["health", "pharma", "pharmaceutical", "medical", "biotech"],
    "armed services": ["defense", "military", "aerospace", "weapons"],
    "judiciary": ["legal", "law", "courts", "prison", "corrections"],
    "appropriations": ["finance", "government", "budget"],
    "foreign relations": ["foreign", "trade", "international", "diplomacy"],
    "intelligence": ["intelligence", "surveillance", "cybersecurity", "defense"],
    "veterans": ["veterans", "military", "health"],
    "transportation": ["transportation", "infrastructure", "airline", "railroad"],
    "small business": ["small business", "entrepreneurship"],
    "homeland security": ["security", "defense", "cybersecurity", "border"],
    "rules": ["government", "administration"],
    "budget": ["finance", "budget", "economics"],
    "indian affairs": ["tribal", "native", "casino", "gaming"],
}


CONFLICT_RELEVANT_TYPES = {"committee_member", "donated_to", "holds_stock",
                            "lobbies_on_behalf_of", "registered_lobbyist_for",
                            "voted_yes", "voted_no",
                            "revolving_door_lobbyist", "former_employer",
                            "spouse_income_from", "family_employed_by",
                            "speaking_fee_from", "outside_income_from",
                            "book_deal_with", "contractor_donor",
                            "received_gov_contract"}

KNOWN_INDUSTRY_ENTITIES = {
    # Banking/Finance — major banks
    "jpmorgan": ["finance", "banking", "securities"],
    "bank of america": ["finance", "banking"],
    "wells fargo": ["finance", "banking"],
    "goldman sachs": ["finance", "banking", "securities"],
    "blackrock": ["finance", "banking", "securities", "investment"],
    "vanguard": ["finance", "investment", "securities"],
    "charles schwab": ["finance", "banking", "securities"],
    "schwab": ["finance", "banking", "securities"],
    "visa": ["finance", "banking"],
    "mastercard": ["finance", "banking"],
    "morgan stanley": ["finance", "banking", "securities"],
    "citigroup": ["finance", "banking"],
    "citi": ["finance", "banking"],
    "capital one": ["finance", "banking"],
    "state street": ["finance", "banking", "securities"],
    "fidelity": ["finance", "investment", "securities"],
    "northern trust": ["finance", "banking", "investment"],
    "bank of new york": ["finance", "banking"],
    "mellon": ["finance", "banking"],
    "ubs": ["finance", "banking", "securities"],
    "credit suisse": ["finance", "banking"],
    "deutsche bank": ["finance", "banking"],
    "barclays": ["finance", "banking"],
    "hsbc": ["finance", "banking"],
    "td bank": ["finance", "banking"],
    "pnc": ["finance", "banking"],
    "usaa": ["finance", "banking", "insurance"],
    "ally financial": ["finance", "banking"],
    "discover": ["finance", "banking"],
    "american express": ["finance", "banking"],
    "amex": ["finance", "banking"],
    "synchrony": ["finance", "banking"],
    "navient": ["finance", "banking"],
    "sallie mae": ["finance", "banking"],
    "freddie mac": ["finance", "banking", "real estate"],
    "fannie mae": ["finance", "banking", "real estate"],
    # Insurance/Finance
    "aig": ["finance", "insurance"],
    "prudential": ["finance", "insurance"],
    "metlife": ["finance", "insurance"],
    "aflac": ["finance", "insurance"],
    "allstate": ["finance", "insurance"],
    "geico": ["finance", "insurance"],
    "berkshire": ["finance", "insurance", "investment"],
    "progressive insurance": ["finance", "insurance"],
    "travelers": ["finance", "insurance"],
    # Technology
    "apple": ["technology"],
    "microsoft": ["technology"],
    "amazon": ["technology", "retail"],
    "google": ["technology"],
    "alphabet": ["technology"],
    "meta": ["technology"],
    "facebook": ["technology"],
    "intel": ["technology"],
    "nvidia": ["technology"],
    "amd": ["technology"],
    "qualcomm": ["technology"],
    "broadcom": ["technology"],
    "cisco": ["technology", "telecommunications"],
    "oracle": ["technology"],
    "ibm": ["technology"],
    "salesforce": ["technology"],
    "adobe": ["technology"],
    "palantir": ["technology", "defense"],
    "dell": ["technology"],
    "hp": ["technology"],
    "hewlett": ["technology"],
    "samsung": ["technology"],
    "sony": ["technology"],
    "tiktok": ["technology"],
    "bytedance": ["technology"],
    "snap": ["technology"],
    "twitter": ["technology"],
    "uber": ["technology", "transportation"],
    "lyft": ["technology", "transportation"],
    "airbnb": ["technology"],
    "doordash": ["technology"],
    "spotify": ["technology", "entertainment"],
    "netflix": ["technology", "entertainment"],
    "roku": ["technology", "entertainment"],
    "zoom": ["technology"],
    "crowdstrike": ["technology", "cybersecurity"],
    "palo alto": ["technology", "cybersecurity"],
    # Energy
    "exxon": ["energy", "oil"],
    "chevron": ["energy", "oil"],
    "bp": ["energy", "oil"],
    "shell": ["energy", "oil"],
    "conocophillips": ["energy", "oil"],
    "marathon": ["energy", "oil"],
    "phillips 66": ["energy", "oil"],
    "valero": ["energy", "oil"],
    "halliburton": ["energy", "oil"],
    "schlumberger": ["energy", "oil"],
    "baker hughes": ["energy", "oil"],
    "devon": ["energy", "oil"],
    "pioneer": ["energy", "oil"],
    "diamondback": ["energy", "oil"],
    "williams": ["energy", "oil"],
    "kinder morgan": ["energy", "oil"],
    "sempra": ["energy"],
    "dominion": ["energy"],
    "duke energy": ["energy"],
    "southern company": ["energy"],
    "nextera": ["energy"],
    "firstenergy": ["energy"],
    "entergy": ["energy"],
    "xcel": ["energy"],
    "constellation": ["energy"],
    # Healthcare/Pharma
    "pfizer": ["health", "pharma"],
    "johnson & johnson": ["health", "pharma"],
    "unitedhealth": ["health", "insurance"],
    "abbvie": ["health", "pharma"],
    "merck": ["health", "pharma"],
    "eli lilly": ["health", "pharma"],
    "lilly": ["health", "pharma"],
    "bristol myers": ["health", "pharma"],
    "novartis": ["health", "pharma"],
    "roche": ["health", "pharma"],
    "astrazeneca": ["health", "pharma"],
    "sanofi": ["health", "pharma"],
    "gsk": ["health", "pharma"],
    "glaxo": ["health", "pharma"],
    "gilead": ["health", "pharma"],
    "regeneron": ["health", "pharma"],
    "moderna": ["health", "pharma"],
    "biogen": ["health", "pharma"],
    "amgen": ["health", "pharma"],
    "cigna": ["health", "insurance"],
    "humana": ["health", "insurance"],
    "centene": ["health", "insurance"],
    "molina": ["health", "insurance"],
    "anthem": ["health", "insurance"],
    "elevance": ["health", "insurance"],
    "cvs": ["health", "retail"],
    "walgreens": ["health", "retail"],
    "mckesson": ["health"],
    "cardinal health": ["health"],
    "medtronic": ["health"],
    "stryker": ["health"],
    "baxter": ["health"],
    "becton dickinson": ["health"],
    "hca": ["health"],
    "tenet": ["health"],
    "community health": ["health"],
    # Defense/Aerospace
    "lockheed": ["defense"],
    "boeing": ["defense"],
    "raytheon": ["defense"],
    "northrop grumman": ["defense"],
    "northrop": ["defense"],
    "general dynamics": ["defense"],
    "l3harris": ["defense"],
    "bae systems": ["defense"],
    "textron": ["defense"],
    "huntington ingalls": ["defense"],
    "leidos": ["defense"],
    "saic": ["defense"],
    "booz allen": ["defense"],
    "caci": ["defense"],
    "mantech": ["defense"],
    "parsons": ["defense"],
    "vectrus": ["defense"],
    # Telecom
    "at&t": ["telecommunications"],
    "verizon": ["telecommunications"],
    "t-mobile": ["telecommunications"],
    "comcast": ["telecommunications", "entertainment"],
    "charter": ["telecommunications"],
    "cox": ["telecommunications"],
    "lumen": ["telecommunications"],
    "centurylink": ["telecommunications"],
    # Agriculture/Food
    "cargill": ["agriculture"],
    "adm": ["agriculture"],
    "archer daniels": ["agriculture"],
    "bunge": ["agriculture"],
    "tyson": ["agriculture", "food"],
    "jbs": ["agriculture", "food"],
    "smithfield": ["agriculture", "food"],
    "hormel": ["agriculture", "food"],
    "conagra": ["agriculture", "food"],
    "general mills": ["agriculture", "food"],
    "kellogg": ["agriculture", "food"],
    "kraft": ["agriculture", "food"],
    "mondelez": ["agriculture", "food"],
    "pepsico": ["agriculture", "food", "beverage"],
    "coca-cola": ["agriculture", "food", "beverage"],
    "nestle": ["agriculture", "food"],
    "mars": ["agriculture", "food"],
    "hershey": ["agriculture", "food"],
    "mccormick": ["agriculture", "food"],
    "smucker": ["agriculture", "food"],
    "farm bureau": ["agriculture"],
    "cattlemen": ["agriculture"],
    "dairy": ["agriculture"],
    "growers": ["agriculture"],
    "sugar": ["agriculture"],
    # Transportation
    "fedex": ["transportation"],
    "ups": ["transportation"],
    "union pacific": ["transportation"],
    "bnsf": ["transportation"],
    "csx": ["transportation"],
    "norfolk southern": ["transportation"],
    "delta": ["transportation"],
    "united airlines": ["transportation"],
    "american airlines": ["transportation"],
    "southwest": ["transportation"],
    "jetblue": ["transportation"],
    "spirit": ["transportation"],
    "ford": ["transportation", "automotive"],
    "general motors": ["transportation", "automotive"],
    "gm": ["transportation", "automotive"],
    "toyota": ["transportation", "automotive"],
    "honda": ["transportation", "automotive"],
    "tesla": ["transportation", "automotive", "technology"],
    "stellantis": ["transportation", "automotive"],
    "chrysler": ["transportation", "automotive"],
    # Real Estate/Construction
    "realtors": ["real estate"],
    "homebuilders": ["real estate", "construction"],
    "lennar": ["real estate", "construction"],
    "d.r. horton": ["real estate", "construction"],
    "pulte": ["real estate", "construction"],
    "toll brothers": ["real estate", "construction"],
    "brookfield": ["real estate", "finance"],
    "simon property": ["real estate"],
    "prologis": ["real estate"],
    "caterpillar": ["construction", "manufacturing"],
    "deere": ["construction", "agriculture"],
    "john deere": ["construction", "agriculture"],
    # Retail
    "walmart": ["retail"],
    "target": ["retail"],
    "costco": ["retail"],
    "home depot": ["retail", "construction"],
    "lowe": ["retail", "construction"],
    "kroger": ["retail", "food"],
    "albertsons": ["retail", "food"],
    "publix": ["retail", "food"],
    "macy": ["retail"],
    "nordstrom": ["retail"],
    "gap": ["retail"],
    "nike": ["retail"],
    "best buy": ["retail", "technology"],
    # Labor Unions
    "teamsters": ["labor", "transportation"],
    "seiu": ["labor", "health"],
    "afscme": ["labor", "government"],
    "aft": ["labor", "education"],
    "nea": ["labor", "education"],
    "ufcw": ["labor", "retail"],
    "ibew": ["labor"],
    "painters": ["labor", "construction"],
    "plumbers": ["labor", "construction"],
    "pipefitters": ["labor", "construction"],
    "ironworkers": ["labor", "construction"],
    "carpenters": ["labor", "construction"],
    "laborers": ["labor", "construction"],
    "operating engineers": ["labor", "construction"],
    "steelworkers": ["labor", "manufacturing"],
    "machinists": ["labor", "manufacturing"],
    "autoworkers": ["labor", "automotive"],
    "uaw": ["labor", "automotive"],
    "aflcio": ["labor"],
    "afl-cio": ["labor"],
    # Lobbying/Legal/Political
    "akin gump": ["legal", "lobbying"],
    "squire patton": ["legal", "lobbying"],
    "holland knight": ["legal", "lobbying"],
    "brownstein": ["legal", "lobbying"],
    "bgr": ["lobbying"],
    "podesta": ["lobbying"],
    "invariant": ["lobbying"],
    "crossroads": ["lobbying"],
    "majority forward": ["lobbying"],
    "senate majority": ["lobbying"],
    "house majority": ["lobbying"],
    "emily's list": ["lobbying"],
    "club for growth": ["lobbying"],
    "americans for prosperity": ["lobbying"],
}

BANKING_COMMITTEE_STOCKS = ["jpmorgan", "bank of america", "wells fargo", "goldman",
                             "blackrock", "vanguard", "schwab", "visa", "mastercard",
                             "ishares", "s&p", "financial"]


def _sanitize(text: str) -> str:
    """Strip non-ASCII characters (database uses SQL_ASCII encoding)."""
    if text is None:
        return ""
    return text.encode("ascii", errors="ignore").decode("ascii")


_VALID_INDUSTRY_TERMS: set[str] = set()

def _build_valid_industry_terms() -> set[str]:
    """Build the set of recognised industry keywords from all maps."""
    if _VALID_INDUSTRY_TERMS:
        return _VALID_INDUSTRY_TERMS
    # From COMMITTEE_INDUSTRY_MAP values
    for kws in COMMITTEE_INDUSTRY_MAP.values():
        _VALID_INDUSTRY_TERMS.update(kw.lower() for kw in kws)
    # From KNOWN_INDUSTRY_ENTITIES values
    for kws in KNOWN_INDUSTRY_ENTITIES.values():
        _VALID_INDUSTRY_TERMS.update(kw.lower() for kw in kws)
    # Canonical industry names themselves
    _VALID_INDUSTRY_TERMS.update([
        "finance", "energy", "health", "defense", "technology", "agriculture",
        "environment", "legal", "transportation", "international", "government",
        "native affairs", "education", "labor", "veterans", "intelligence",
        "retail", "construction", "manufacturing", "telecommunications",
        "entertainment", "real estate", "insurance", "banking", "securities",
        "telecom", "media", "hospitality", "tourism", "mining", "chemicals",
        "automotive", "aerospace", "cybersecurity", "fintech", "biotech",
        "crypto", "cannabis", "gambling", "gaming", "firearms", "tobacco",
        "alcohol", "food", "beverage", "pharma", "investment", "lobbying",
        "oil", "utilities", "housing",
    ])
    return _VALID_INDUSTRY_TERMS


def _extract_industry_keywords(entity: Entity) -> list[str]:
    """Pull industry-related keywords — checks known entities first,
    then metadata fields, filtering to only recognised industry terms."""
    valid = _build_valid_industry_terms()
    name_lower = _sanitize(entity.name).lower()
    # Check known entities map first
    for known_name, keywords in KNOWN_INDUSTRY_ENTITIES.items():
        if known_name in name_lower:
            return keywords
    # Collect candidate words from name + metadata
    candidates: list[str] = []
    candidates.extend(name_lower.split())
    meta = entity.metadata_ or {}
    for key in ("industry", "sector", "category", "employer", "occupation"):
        val = meta.get(key, "")
        if val:
            candidates.extend(_sanitize(str(val)).lower().split())
    # Only return words that are recognised industry terms
    return [w for w in candidates if w in valid]


def _industries_for_committee(committee_name: str) -> list[str]:
    """Return industry keywords for a committee name (fuzzy match on key)."""
    name_lower = _sanitize(committee_name).lower()
    industries: list[str] = []
    for key, kws in COMMITTEE_INDUSTRY_MAP.items():
        if key in name_lower:
            industries.extend(kws)
    return industries


def _keyword_overlap(keywords_a: list[str], keywords_b: list[str]) -> bool:
    """Return True when any keyword from A appears in B."""
    set_a = set(keywords_a)
    set_b = set(keywords_b)
    return bool(set_a & set_b)


def _severity(signal_count: int) -> str:
    """Structural transparency severity scoring."""
    if signal_count >= 3:
        return "notable_pattern"
    if signal_count >= 2:
        return "structural_relationship"
    return "connection_noted"


# Timing window for donation-vote correlation (expanded from 90 to 180 days)
TIMING_WINDOW_DAYS = 180


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------
@dataclass
class ConflictSignal:
    entity_slug: str
    conflict_type: str  # 'structural_committee_donor_overlap', 'structural_stock_vote_alignment',
                        # 'structural_donor_vote_timing', 'full_structural_alignment',
                        # 'structural_committee_jurisdiction', 'structural_lobbying_regulatory_overlap',
                        # 'donation_vote_timing_pattern', 'pre_vote_donation_pattern'
    severity: str       # 'connection_noted', 'structural_relationship', 'notable_pattern', 'high_concern'
    description: str
    why_this_matters: str = ""  # plain English explainer
    evidence: list[dict] = field(default_factory=list)
    related_entities: list[str] = field(default_factory=list)
    evidence_chain: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Structural relationship detection (fires with ZERO voting evidence)
# ---------------------------------------------------------------------------
async def detect_structural_relationships(
    session: AsyncSession, entity_slug: str
) -> list[ConflictSignal]:
    """Detect ALL structural relationships, even with zero voting evidence.
    These fire based purely on structural facts: committee assignments,
    donations, stock holdings, and lobbying registrations."""

    # Load entity
    result = await session.execute(
        select(Entity).where(Entity.slug == entity_slug)
    )
    entity = result.scalar_one_or_none()
    if entity is None:
        return []

    # Load all outgoing + incoming relationships for this entity
    rels_q = select(Relationship).where(
        or_(
            Relationship.from_entity_id == entity.id,
            Relationship.to_entity_id == entity.id,
        )
    )
    rels_result = await session.execute(rels_q)
    all_rels = rels_result.scalars().all()

    # Collect connected entity IDs — only conflict-relevant types
    connected_ids = set()
    for r in all_rels:
        if r.relationship_type in CONFLICT_RELEVANT_TYPES:
            connected_ids.add(r.from_entity_id)
            connected_ids.add(r.to_entity_id)
    connected_ids.discard(entity.id)

    entities_map: dict = {}
    if connected_ids:
        ent_result = await session.execute(
            select(Entity).where(Entity.id.in_(connected_ids))
        )
        for e in ent_result.scalars().all():
            entities_map[e.id] = e

    # Categorize relationships
    committees: list[Relationship] = []
    donations: list[tuple[Relationship, Entity]] = []
    stocks: list[tuple[Relationship, Entity]] = []
    lobbying_rels: list[tuple[Relationship, Entity]] = []

    for r in all_rels:
        other_id = r.to_entity_id if r.from_entity_id == entity.id else r.from_entity_id
        other = entities_map.get(other_id)

        if r.relationship_type == "committee_member":
            committees.append(r)
        elif r.relationship_type == "donated_to" and r.to_entity_id == entity.id:
            if other:
                donations.append((r, other))
        elif r.relationship_type == "holds_stock" and r.from_entity_id == entity.id:
            if other:
                stocks.append((r, other))
        elif r.relationship_type in ("lobbies_on_behalf_of", "registered_lobbyist_for"):
            if other:
                lobbying_rels.append((r, other))

    signals: list[ConflictSignal] = []

    # Build keyword sets
    donor_keywords: dict[str, list[str]] = {}
    for rel, donor_ent in donations:
        donor_keywords[donor_ent.slug] = _extract_industry_keywords(donor_ent)

    stock_keywords: dict[str, list[str]] = {}
    for rel, stock_ent in stocks:
        stock_keywords[stock_ent.slug] = _extract_industry_keywords(stock_ent)

    # --- Structural Alert 0: Presence-Based (committee + donors + stocks) ---
    if committees and donations and stocks:
        committee_names = [_sanitize(entities_map.get(
            c.to_entity_id if c.from_entity_id == entity.id else c.from_entity_id
        ).name) for c in committees if entities_map.get(
            c.to_entity_id if c.from_entity_id == entity.id else c.from_entity_id
        )]
        stock_names = [_sanitize(s_ent.name) for _, s_ent in stocks[:3]]
        top_donors = [_sanitize(d_ent.name) for _, d_ent in donations[:3]]

        signals.append(ConflictSignal(
            entity_slug=entity_slug,
            conflict_type="structural_committee_donor_stock_overlap",
            severity="notable_pattern",
            description=(
                f"This official sits on {len(committees)} committee(s) "
                f"({', '.join(committee_names[:2])}), has received campaign contributions "
                f"from {len(donations)} donors, and holds stock in {len(stocks)} companies "
                f"({', '.join(stock_names[:2])}). These structural relationships create "
                f"potential conflicts of interest the public should be aware of."
            ),
            why_this_matters=WHY_THIS_MATTERS["structural_committee_donor_overlap"],
            evidence=[
                {"type": "committee", "name": name, "detail": "Regulatory oversight role"}
                for name in committee_names
            ] + [
                {"type": "stock", "name": _sanitize(s_ent.name), "amount_label": s_rel.amount_label}
                for s_rel, s_ent in stocks[:5]
            ] + [
                {"type": "donation", "name": _sanitize(d_ent.name), "amount": d_rel.amount_usd}
                for d_rel, d_ent in donations[:5]
            ],
            related_entities=[],
        ))

    # --- Structural Alert 0b: Committee-Stock jurisdiction (known entities) ---
    for c_rel in committees:
        c_other_id = c_rel.to_entity_id if c_rel.from_entity_id == entity.id else c_rel.from_entity_id
        c_ent = entities_map.get(c_other_id)
        if not c_ent:
            continue
        c_industries = _industries_for_committee(c_ent.name)

        for s_rel, s_ent in stocks:
            s_name_lower = _sanitize(s_ent.name).lower()
            s_kws = _extract_industry_keywords(s_ent)
            if _keyword_overlap(c_industries, s_kws):
                signals.append(ConflictSignal(
                    entity_slug=entity_slug,
                    conflict_type="structural_committee_stock",
                    severity="structural_relationship",
                    description=(
                        f"Potential Conflict: This official sits on the "
                        f"{_sanitize(c_ent.name)} committee, which has regulatory "
                        f"oversight over the financial industry. They hold stock in "
                        f"{_sanitize(s_ent.name)}, a company directly regulated by "
                        f"this committee."
                    ),
                    why_this_matters=WHY_THIS_MATTERS["structural_committee_jurisdiction"],
                    evidence=[
                        {"type": "committee", "name": _sanitize(c_ent.name)},
                        {"type": "stock", "name": _sanitize(s_ent.name),
                         "amount_label": s_rel.amount_label or "Amount disclosed"},
                    ],
                    related_entities=[c_ent.slug, s_ent.slug],
                ))

    # --- Structural Alert 1: Committee-Donor Structural ---
    # Official on committee + industry donated -> always flag
    for c_rel in committees:
        c_other_id = c_rel.to_entity_id if c_rel.from_entity_id == entity.id else c_rel.from_entity_id
        c_ent = entities_map.get(c_other_id)
        if not c_ent:
            continue
        c_industries = _industries_for_committee(c_ent.name)
        if not c_industries:
            continue
        for d_rel, d_ent in donations:
            d_kws = donor_keywords.get(d_ent.slug, [])
            if _keyword_overlap(c_industries, d_kws):
                signals.append(ConflictSignal(
                    entity_slug=entity_slug,
                    conflict_type="structural_committee_donor_overlap",
                    severity="structural_relationship",
                    description=(
                        f"Structural relationship: This official sits on {_sanitize(c_ent.name)}, "
                        f"which has regulatory jurisdiction over the industry that "
                        f"{_sanitize(d_ent.name)} operates in. {_sanitize(d_ent.name)} has "
                        f"contributed to this official's campaign. This is a structural "
                        f"relationship the public should be aware of."
                    ),
                    why_this_matters=WHY_THIS_MATTERS["structural_committee_donor_overlap"],
                    evidence=[
                        {"type": "committee", "entity": c_ent.slug, "name": _sanitize(c_ent.name)},
                        {"type": "donation", "entity": d_ent.slug, "name": _sanitize(d_ent.name),
                         "amount": d_rel.amount_usd},
                    ],
                    related_entities=[c_ent.slug, d_ent.slug],
                ))

    # --- Structural Alert 2: Committee-Stock Structural ---
    # Official on committee + holds stock in regulated company -> always flag
    for c_rel in committees:
        c_other_id = c_rel.to_entity_id if c_rel.from_entity_id == entity.id else c_rel.from_entity_id
        c_ent = entities_map.get(c_other_id)
        if not c_ent:
            continue
        c_industries = _industries_for_committee(c_ent.name)
        if not c_industries:
            continue
        for s_rel, s_ent in stocks:
            s_kws = stock_keywords.get(s_ent.slug, [])
            if _keyword_overlap(c_industries, s_kws):
                signals.append(ConflictSignal(
                    entity_slug=entity_slug,
                    conflict_type="structural_committee_jurisdiction",
                    severity="structural_relationship",
                    description=(
                        f"Structural relationship: This official sits on {_sanitize(c_ent.name)}, "
                        f"which has regulatory jurisdiction over the industry that "
                        f"{_sanitize(s_ent.name)} operates in. This official holds stock in "
                        f"{_sanitize(s_ent.name)}. This structural financial relationship is "
                        f"worth public scrutiny."
                    ),
                    why_this_matters=WHY_THIS_MATTERS["structural_committee_jurisdiction"],
                    evidence=[
                        {"type": "committee", "entity": c_ent.slug, "name": _sanitize(c_ent.name)},
                        {"type": "stock", "entity": s_ent.slug, "name": _sanitize(s_ent.name)},
                    ],
                    related_entities=[c_ent.slug, s_ent.slug],
                ))

    # --- Structural Alert 3: Committee-Lobbying Structural ---
    # Official on committee + companies lobbying on committee issues + those companies donated
    for c_rel in committees:
        c_other_id = c_rel.to_entity_id if c_rel.from_entity_id == entity.id else c_rel.from_entity_id
        c_ent = entities_map.get(c_other_id)
        if not c_ent:
            continue
        c_industries = _industries_for_committee(c_ent.name)
        if not c_industries:
            continue

        for d_rel, d_ent in donations:
            d_kws = donor_keywords.get(d_ent.slug, [])
            if not _keyword_overlap(c_industries, d_kws):
                continue
            # Check if the donor or associated company has lobbying activity
            d_meta = d_ent.metadata_ or {}
            lobbying_data = d_meta.get("lobbying", {})
            has_lobbying = lobbying_data.get("filing_count", 0) > 0

            employer = d_meta.get("employer", "")
            if not has_lobbying and employer:
                employer_lower = _sanitize(str(employer)).lower()
                for eid, ent in entities_map.items():
                    ent_meta = ent.metadata_ or {}
                    if ent_meta.get("lobbying", {}).get("filing_count", 0) > 0:
                        if employer_lower in _sanitize(ent.name).lower():
                            has_lobbying = True
                            break

            if has_lobbying:
                signals.append(ConflictSignal(
                    entity_slug=entity_slug,
                    conflict_type="structural_lobbying_regulatory_overlap",
                    severity="structural_relationship",
                    description=(
                        f"Structural relationship: {_sanitize(d_ent.name)} (or an associated "
                        f"company) actively lobbies on issues under {_sanitize(c_ent.name)}'s "
                        f"jurisdiction AND has contributed to this official's campaign. This "
                        f"creates a structural pathway for influence the public should "
                        f"understand."
                    ),
                    why_this_matters=WHY_THIS_MATTERS["structural_lobbying_regulatory_overlap"],
                    evidence=[
                        {"type": "committee", "entity": c_ent.slug, "name": _sanitize(c_ent.name)},
                        {"type": "donation", "entity": d_ent.slug, "name": _sanitize(d_ent.name),
                         "amount": d_rel.amount_usd},
                        {"type": "lobbying", "filing_count": lobbying_data.get("filing_count", 0),
                         "total_spend": lobbying_data.get("total_spend", 0)},
                    ],
                    related_entities=[c_ent.slug, d_ent.slug],
                ))

    # --- Structural Alert 4: Lobbying-Donor Structural ---
    # Lobbying firm's clients donated to official + firm lobbied on bills official voted on
    for l_rel, l_ent in lobbying_rels:
        l_kws = _extract_industry_keywords(l_ent)
        for d_rel, d_ent in donations:
            d_kws = donor_keywords.get(d_ent.slug, [])
            if _keyword_overlap(l_kws, d_kws):
                signals.append(ConflictSignal(
                    entity_slug=entity_slug,
                    conflict_type="structural_lobbying_regulatory_overlap",
                    severity="structural_relationship",
                    description=(
                        f"Structural relationship: {_sanitize(l_ent.name)} lobbies on issues "
                        f"related to this official's work, and {_sanitize(d_ent.name)} "
                        f"(associated with the lobbying firm's industry) has contributed to "
                        f"this official's campaign. This structural relationship is worth "
                        f"public awareness."
                    ),
                    why_this_matters=WHY_THIS_MATTERS["structural_lobbying_regulatory_overlap"],
                    evidence=[
                        {"type": "lobbying", "entity": l_ent.slug, "name": _sanitize(l_ent.name)},
                        {"type": "donation", "entity": d_ent.slug, "name": _sanitize(d_ent.name),
                         "amount": d_rel.amount_usd},
                    ],
                    related_entities=[l_ent.slug, d_ent.slug],
                ))

    # Deduplicate by description
    seen: set[str] = set()
    unique_signals: list[ConflictSignal] = []
    for s in signals:
        if s.description not in seen:
            seen.add(s.description)
            unique_signals.append(s)

    return unique_signals


# ---------------------------------------------------------------------------
# Hidden Connections detection — 5 new signal types
# ---------------------------------------------------------------------------
async def detect_hidden_connections(
    session: AsyncSession, entity_slug: str
) -> list[ConflictSignal]:
    """Detect hidden connection signals for an entity.

    Covers 5 categories:
    1. Revolving door lobbyists — people who left government to lobby their old colleagues
    2. Family employer conflicts — spouse/family income from regulated industries
    3. Paid speaking from regulated industries — speaking fees creating personal ties
    4. Contractor-donor patterns — donate then receive government contracts
    5. Suspicious trade timing — stock trades before committee action
    """

    # Load entity
    result = await session.execute(
        select(Entity).where(Entity.slug == entity_slug)
    )
    entity = result.scalar_one_or_none()
    if entity is None:
        return []

    # Load all relationships for this entity
    rels_q = select(Relationship).where(
        or_(
            Relationship.from_entity_id == entity.id,
            Relationship.to_entity_id == entity.id,
        )
    )
    rels_result = await session.execute(rels_q)
    all_rels = rels_result.scalars().all()

    # Collect connected entity IDs
    connected_ids = set()
    for r in all_rels:
        connected_ids.add(r.from_entity_id)
        connected_ids.add(r.to_entity_id)
    connected_ids.discard(entity.id)

    entities_map: dict = {}
    if connected_ids:
        ent_result = await session.execute(
            select(Entity).where(Entity.id.in_(connected_ids))
        )
        for e in ent_result.scalars().all():
            entities_map[e.id] = e

    # Gather committee names for this official
    committee_names: list[str] = []
    for r in all_rels:
        if r.relationship_type == "committee_member":
            other_id = r.to_entity_id if r.from_entity_id == entity.id else r.from_entity_id
            c_ent = entities_map.get(other_id)
            if c_ent:
                committee_names.append(_sanitize(c_ent.name))

    signals: list[ConflictSignal] = []

    # --- 1. Revolving Door Access ---
    for r in all_rels:
        if r.relationship_type != "revolving_door_lobbyist":
            continue
        # The lobbyist entity points TO the official
        lobbyist_id = r.from_entity_id if r.to_entity_id == entity.id else r.to_entity_id
        lobbyist = entities_map.get(lobbyist_id)
        if not lobbyist:
            continue
        meta = r.metadata_ or {}
        l_meta = lobbyist.metadata_ or {}
        former_position = meta.get("former_position", l_meta.get("former_position", "government official"))
        current_employer = meta.get("current_employer", l_meta.get("employer", "a lobbying firm"))
        lobbies_committee = meta.get("lobbies_committee", "")

        # Check if this lobbyist lobbies the official's committee
        targets_committee = False
        if lobbies_committee:
            for cn in committee_names:
                if lobbies_committee.lower() in cn.lower() or cn.lower() in lobbies_committee.lower():
                    targets_committee = True
                    break

        if targets_committee or lobbies_committee:
            clients = meta.get("clients", l_meta.get("clients", []))
            if isinstance(clients, str):
                clients = [clients]
            signals.append(ConflictSignal(
                entity_slug=entity_slug,
                conflict_type="revolving_door_access",
                severity="high_concern" if targets_committee else "notable_pattern",
                description=(
                    f"{_sanitize(lobbyist.name)} used to be a {_sanitize(former_position)} "
                    f"and now works for {_sanitize(current_employer)} as a lobbyist. "
                    f"They lobby {_sanitize(lobbies_committee) if lobbies_committee else 'Congress'}, "
                    f"which is {'the same committee this official sits on' if targets_committee else 'related to this official'}. "
                    f"They know the system from the inside and now get paid to work it."
                ),
                why_this_matters=WHY_THIS_MATTERS["revolving_door_access"],
                evidence=[
                    {"type": "revolving_door", "lobbyist": _sanitize(lobbyist.name),
                     "former_position": _sanitize(former_position),
                     "current_employer": _sanitize(current_employer),
                     "lobbies_committee": _sanitize(lobbies_committee)},
                ],
                related_entities=[lobbyist.slug],
            ))

    # --- 2. Family Employer Conflict ---
    family_rel_types = {"spouse_income_from", "family_employed_by"}
    for r in all_rels:
        if r.relationship_type not in family_rel_types:
            continue
        employer_id = r.to_entity_id if r.from_entity_id == entity.id else r.from_entity_id
        employer = entities_map.get(employer_id)
        if not employer:
            continue
        meta = r.metadata_ or {}
        family_member = meta.get("family_member", "A family member")
        relationship_label = meta.get("relationship", "family member")
        role = meta.get("role", "employee")
        annual_income = meta.get("annual_income") or r.amount_usd

        # Check if employer operates in an industry regulated by official's committee
        employer_kws = _extract_industry_keywords(employer)
        overlap_committee = None
        for cn in committee_names:
            c_industries = _industries_for_committee(cn)
            if _keyword_overlap(c_industries, employer_kws):
                overlap_committee = cn
                break

        income_str = f"${annual_income / 100:,.0f}/year" if annual_income else "an undisclosed salary"
        signals.append(ConflictSignal(
            entity_slug=entity_slug,
            conflict_type="family_employer_conflict",
            severity="high_concern" if overlap_committee else "structural_relationship",
            description=(
                f"{_sanitize(family_member)} ({_sanitize(relationship_label)}) works as a "
                f"{_sanitize(role)} at {_sanitize(employer.name)}, earning {income_str}. "
                + (f"This official sits on {_sanitize(overlap_committee)}, which regulates "
                   f"the industry {_sanitize(employer.name)} operates in. "
                   f"The family paycheck and the committee power create a built-in conflict."
                   if overlap_committee else
                   f"While there is no direct committee overlap, the financial relationship "
                   f"between the family and this company is worth knowing about.")
            ),
            why_this_matters=WHY_THIS_MATTERS["family_employer_conflict"],
            evidence=[
                {"type": "family_income", "family_member": _sanitize(family_member),
                 "relationship": _sanitize(relationship_label),
                 "employer": _sanitize(employer.name), "role": _sanitize(role),
                 "annual_income": annual_income,
                 "committee_overlap": _sanitize(overlap_committee) if overlap_committee else None},
            ],
            related_entities=[employer.slug],
        ))

    # --- 3. Paid Speaking from Regulated Industry ---
    speaking_types = {"speaking_fee_from", "outside_income_from", "book_deal_with"}
    for r in all_rels:
        if r.relationship_type not in speaking_types:
            continue
        payer_id = r.to_entity_id if r.from_entity_id == entity.id else r.from_entity_id
        payer = entities_map.get(payer_id)
        if not payer:
            continue
        meta = r.metadata_ or {}
        amount = r.amount_usd or meta.get("amount_usd", 0)
        income_type = meta.get("income_type", r.relationship_type.replace("_from", "").replace("_with", ""))
        event_desc = meta.get("event_description", "")

        # Check if payer is in a regulated industry or has lobbying activity
        payer_kws = _extract_industry_keywords(payer)
        payer_meta = payer.metadata_ or {}
        has_lobbying = payer_meta.get("lobbying", {}).get("filing_count", 0) > 0
        is_regulated = False
        overlap_committee = None
        for cn in committee_names:
            c_industries = _industries_for_committee(cn)
            if _keyword_overlap(c_industries, payer_kws):
                is_regulated = True
                overlap_committee = cn
                break

        if is_regulated or has_lobbying or amount >= 500000:  # $5,000+ in cents
            amount_str = f"${amount / 100:,.0f}" if amount else "an undisclosed amount"
            signals.append(ConflictSignal(
                entity_slug=entity_slug,
                conflict_type="paid_speaking_regulated_industry",
                severity="notable_pattern" if is_regulated else "connection_noted",
                description=(
                    f"This official received {amount_str} from {_sanitize(payer.name)} "
                    f"for {_sanitize(income_type).replace('_', ' ')}. "
                    + (f"{_sanitize(payer.name)} operates in an industry regulated by "
                       f"{_sanitize(overlap_committee)}, where this official sits. "
                       f"Getting paid by the people you regulate creates a personal "
                       f"financial tie that the public should know about."
                       if is_regulated else
                       f"{_sanitize(payer.name)} {'actively lobbies Congress' if has_lobbying else 'paid a notable amount'}. "
                       f"Speaking fees create personal relationships between officials "
                       f"and the organizations paying them.")
                ),
                why_this_matters=WHY_THIS_MATTERS["paid_speaking_regulated_industry"],
                evidence=[
                    {"type": "speaking_fee", "payer": _sanitize(payer.name),
                     "amount": amount, "income_type": income_type,
                     "is_regulated": is_regulated, "has_lobbying": has_lobbying,
                     "committee_overlap": _sanitize(overlap_committee) if overlap_committee else None},
                ],
                related_entities=[payer.slug],
            ))

    # --- 4. Contractor-Donor Pattern ---
    for r in all_rels:
        if r.relationship_type != "contractor_donor":
            continue
        contractor_id = r.from_entity_id if r.to_entity_id == entity.id else r.to_entity_id
        contractor = entities_map.get(contractor_id)
        if not contractor:
            continue
        meta = r.metadata_ or {}
        donation_amount = meta.get("donation_amount", r.amount_usd or 0)
        contract_amount = meta.get("contract_amount", 0)
        contract_agency = meta.get("contract_agency", "a government agency")
        contract_desc = meta.get("contract_description", "government services")
        donation_date = meta.get("donation_date", str(r.date_start) if r.date_start else None)
        contract_date = meta.get("contract_date", str(r.date_end) if r.date_end else None)

        ratio = round(contract_amount / donation_amount, 1) if donation_amount and donation_amount > 0 else None

        donation_str = f"${donation_amount / 100:,.0f}" if donation_amount else "an unknown amount"
        contract_str = f"${contract_amount / 100:,.0f}" if contract_amount else "an unknown amount"
        ratio_str = f"That is ${ratio:.0f} in government contracts for every $1 donated." if ratio else ""

        signals.append(ConflictSignal(
            entity_slug=entity_slug,
            conflict_type="contractor_donor_pattern",
            severity="high_concern" if ratio and ratio >= 100 else "notable_pattern",
            description=(
                f"{_sanitize(contractor.name)} donated {donation_str} to this official's campaign"
                + (f" on {donation_date}" if donation_date else "")
                + f". Then {_sanitize(contractor.name)} received a {contract_str} contract from "
                f"{_sanitize(contract_agency)} for {_sanitize(contract_desc)}"
                + (f" on {contract_date}" if contract_date else "")
                + f". {ratio_str} "
                f"This does not prove anything illegal, but the pattern is the kind of thing "
                f"investigative reporters look for."
            ),
            why_this_matters=WHY_THIS_MATTERS["contractor_donor_pattern"],
            evidence=[
                {"type": "contractor_donor", "contractor": _sanitize(contractor.name),
                 "donation_amount": donation_amount, "contract_amount": contract_amount,
                 "contract_agency": _sanitize(contract_agency),
                 "dollars_per_donation_dollar": ratio},
            ],
            related_entities=[contractor.slug],
        ))

    # --- 5. Suspicious Trade Timing ---
    for r in all_rels:
        if r.relationship_type != "holds_stock":
            continue
        if r.from_entity_id != entity.id:
            continue
        stock_id = r.to_entity_id
        stock_ent = entities_map.get(stock_id)
        if not stock_ent:
            continue
        meta = r.metadata_ or {}
        info_score = meta.get("information_access_score", 0)
        if not isinstance(info_score, (int, float)):
            try:
                info_score = int(info_score)
            except (ValueError, TypeError):
                info_score = 0
        if info_score < 7:
            continue

        transaction_type = meta.get("transaction_type", "trade")
        transaction_date = meta.get("transaction_date", str(r.date_start) if r.date_start else "unknown date")
        amount_range = meta.get("amount_range", r.amount_label or "undisclosed")
        days_before_hearing = meta.get("days_before_committee_hearing")
        hearing_topic = meta.get("hearing_topic", "")
        hearing_date = meta.get("hearing_date", "")
        days_before_vote = meta.get("days_before_related_vote")
        vote_topic = meta.get("vote_topic", "")
        stock_movement = meta.get("stock_movement_after", "")
        pattern_desc = meta.get("pattern_description", "Trade timed near committee activity")

        timing_detail = ""
        if days_before_hearing:
            timing_detail = f" just {days_before_hearing} days before a committee hearing on {_sanitize(hearing_topic)}"
        elif days_before_vote:
            timing_detail = f" just {days_before_vote} days before a vote on {_sanitize(vote_topic)}"

        movement_detail = ""
        if stock_movement:
            movement_detail = f" The stock {_sanitize(stock_movement)} after the official action."

        signals.append(ConflictSignal(
            entity_slug=entity_slug,
            conflict_type="suspicious_trade_timing",
            severity="high_concern" if info_score >= 9 else "notable_pattern",
            description=(
                f"This official {'bought' if transaction_type == 'buy' else 'sold'} "
                f"{amount_range} worth of {_sanitize(stock_ent.name)} stock on "
                f"{_sanitize(transaction_date)}{timing_detail}.{movement_detail} "
                f"With an information access score of {info_score}/10, this trade "
                f"happened when the official likely had non-public knowledge about "
                f"upcoming government actions affecting this company."
            ),
            why_this_matters=WHY_THIS_MATTERS["suspicious_trade_timing"],
            evidence=[
                {"type": "trade_timing", "stock": _sanitize(stock_ent.name),
                 "transaction_type": transaction_type,
                 "transaction_date": _sanitize(transaction_date),
                 "amount_range": amount_range,
                 "information_access_score": info_score,
                 "days_before_hearing": days_before_hearing,
                 "days_before_vote": days_before_vote,
                 "stock_movement_after": stock_movement},
            ],
            related_entities=[stock_ent.slug],
        ))

    # Deduplicate by description
    seen: set[str] = set()
    unique_signals: list[ConflictSignal] = []
    for s in signals:
        if s.description not in seen:
            seen.add(s.description)
            unique_signals.append(s)

    return unique_signals


# ---------------------------------------------------------------------------
# Main detection
# ---------------------------------------------------------------------------
async def detect_conflicts(
    session: AsyncSession, entity_slug: str
) -> list[ConflictSignal]:
    """Detect conflicts-of-interest signals for an entity.

    Returns both vote-based conflict signals AND structural relationships
    (which fire regardless of voting evidence)."""

    # Load entity
    result = await session.execute(
        select(Entity).where(Entity.slug == entity_slug)
    )
    entity = result.scalar_one_or_none()
    if entity is None:
        return []

    # Load all outgoing + incoming relationships for this entity
    rels_q = select(Relationship).where(
        or_(
            Relationship.from_entity_id == entity.id,
            Relationship.to_entity_id == entity.id,
        )
    )
    rels_result = await session.execute(rels_q)
    all_rels = rels_result.scalars().all()

    # Collect connected entity IDs — only conflict-relevant types
    connected_ids = set()
    for r in all_rels:
        if r.relationship_type in CONFLICT_RELEVANT_TYPES:
            connected_ids.add(r.from_entity_id)
            connected_ids.add(r.to_entity_id)
    connected_ids.discard(entity.id)

    entities_map: dict = {}
    if connected_ids:
        ent_result = await session.execute(
            select(Entity).where(Entity.id.in_(connected_ids))
        )
        for e in ent_result.scalars().all():
            entities_map[e.id] = e

    # Categorize relationships
    committees: list[Relationship] = []
    donations: list[tuple[Relationship, Entity]] = []  # (rel, donor_entity)
    stocks: list[tuple[Relationship, Entity]] = []      # (rel, company_entity)
    yes_votes: list[tuple[Relationship, Entity]] = []    # (rel, bill_entity)
    no_votes: list[tuple[Relationship, Entity]] = []

    for r in all_rels:
        other_id = r.to_entity_id if r.from_entity_id == entity.id else r.from_entity_id
        other = entities_map.get(other_id)

        if r.relationship_type == "committee_member":
            committees.append(r)
        elif r.relationship_type == "donated_to" and r.to_entity_id == entity.id:
            # Donor -> entity
            if other:
                donations.append((r, other))
        elif r.relationship_type == "holds_stock" and r.from_entity_id == entity.id:
            if other:
                stocks.append((r, other))
        elif r.relationship_type == "voted_yes" and r.from_entity_id == entity.id:
            if other:
                yes_votes.append((r, other))
        elif r.relationship_type == "voted_no" and r.from_entity_id == entity.id:
            if other:
                no_votes.append((r, other))

    signals: list[ConflictSignal] = []

    # Build industry keyword sets per category
    donor_keywords: dict[str, list[str]] = {}
    for rel, donor_ent in donations:
        donor_keywords[donor_ent.slug] = _extract_industry_keywords(donor_ent)

    stock_keywords: dict[str, list[str]] = {}
    for rel, stock_ent in stocks:
        stock_keywords[stock_ent.slug] = _extract_industry_keywords(stock_ent)

    bill_keywords: dict[str, list[str]] = {}
    for rel, bill_ent in yes_votes:
        bill_keywords[bill_ent.slug] = _extract_industry_keywords(bill_ent)

    # 1) Committee-Donor overlap — aggregate per committee, not per donor
    for c_rel in committees:
        c_other_id = c_rel.to_entity_id if c_rel.from_entity_id == entity.id else c_rel.from_entity_id
        c_ent = entities_map.get(c_other_id)
        if not c_ent:
            continue
        c_industries = _industries_for_committee(c_ent.name)
        if not c_industries:
            continue

        # Collect ALL donors that overlap with this committee's industries
        overlapping_donors = []
        total_amount = 0
        for d_rel, d_ent in donations:
            d_kws = donor_keywords.get(d_ent.slug, [])
            if _keyword_overlap(c_industries, d_kws):
                amount = d_rel.amount_usd or 0
                overlapping_donors.append((_sanitize(d_ent.name), amount, d_ent.slug))
                total_amount += amount

        if not overlapping_donors:
            continue

        # Sort by amount descending, take top 3 for the description
        overlapping_donors.sort(key=lambda x: x[1], reverse=True)
        top_names = ", ".join(d[0] for d in overlapping_donors[:3])
        total_dollars = total_amount / 100 if total_amount else 0

        # Severity based on number of donors and amounts
        if len(overlapping_donors) >= 5 or total_dollars >= 100000:
            severity = "notable_pattern"
        elif len(overlapping_donors) >= 2:
            severity = "structural_relationship"
        else:
            severity = "connection_noted"

        signals.append(ConflictSignal(
            entity_slug=entity_slug,
            conflict_type="structural_committee_donor_overlap",
            severity=severity,
            description=(
                f"Sits on {_sanitize(c_ent.name)} which regulates industries that "
                f"{len(overlapping_donors)} of their donors operate in. "
                f"Top donors: {top_names}. "
                f"Total from these donors: ${total_dollars:,.0f}."
            ),
            why_this_matters=WHY_THIS_MATTERS["structural_committee_donor_overlap"],
            evidence=[
                {"type": "committee", "entity": c_ent.slug, "name": _sanitize(c_ent.name)},
            ] + [
                {"type": "donation", "entity": d[2], "name": d[0], "amount": d[1]}
                for d in overlapping_donors[:5]
            ],
            related_entities=[c_ent.slug] + [d[2] for d in overlapping_donors[:5]],
        ))

    # 2) Stock-Vote overlap
    for s_rel, s_ent in stocks:
        s_kws = stock_keywords.get(s_ent.slug, [])
        for v_rel, v_ent in yes_votes:
            v_kws = bill_keywords.get(v_ent.slug, [])
            if _keyword_overlap(s_kws, v_kws):
                signals.append(ConflictSignal(
                    entity_slug=entity_slug,
                    conflict_type="structural_stock_vote_alignment",
                    severity="notable_pattern",
                    description=(
                        f"Structural relationship: This official holds stock in "
                        f"{_sanitize(s_ent.name)} and voted on {_sanitize(v_ent.name)}, which "
                        f"may affect that company's industry. There is a structural financial "
                        f"incentive the public should be aware of, regardless of how the "
                        f"official voted."
                    ),
                    why_this_matters=WHY_THIS_MATTERS["structural_stock_vote_alignment"],
                    evidence=[
                        {"type": "stock", "entity": s_ent.slug, "name": _sanitize(s_ent.name)},
                        {"type": "vote_yes", "entity": v_ent.slug, "name": _sanitize(v_ent.name)},
                    ],
                    related_entities=[s_ent.slug, v_ent.slug],
                ))

    # 3) Timing correlation: donation within 180 days before YES vote
    for d_rel, d_ent in donations:
        if not d_rel.date_start:
            continue
        d_kws = donor_keywords.get(d_ent.slug, [])
        for v_rel, v_ent in yes_votes:
            if not v_rel.date_start:
                continue
            v_kws = bill_keywords.get(v_ent.slug, [])
            if not _keyword_overlap(d_kws, v_kws):
                continue
            days_diff = (v_rel.date_start - d_rel.date_start).days
            if 0 <= days_diff <= TIMING_WINDOW_DAYS:
                signals.append(ConflictSignal(
                    entity_slug=entity_slug,
                    conflict_type="donation_vote_timing_pattern",
                    severity="notable_pattern",
                    description=(
                        f"Temporal pattern: This official received a donation from "
                        f"{_sanitize(d_ent.name)} {days_diff} days before voting on "
                        f"{_sanitize(v_ent.name)}. The timing of campaign donations relative "
                        f"to legislative votes is a structural pattern worth noting, "
                        f"regardless of the official's actual vote."
                    ),
                    why_this_matters=WHY_THIS_MATTERS["donation_vote_timing_pattern"],
                    evidence=[
                        {"type": "donation", "entity": d_ent.slug, "name": _sanitize(d_ent.name),
                         "amount": d_rel.amount_usd, "date": str(d_rel.date_start)},
                        {"type": "vote_yes", "entity": v_ent.slug, "name": _sanitize(v_ent.name),
                         "date": str(v_rel.date_start), "days_after_donation": days_diff},
                    ],
                    related_entities=[d_ent.slug, v_ent.slug],
                ))

    # 4) Full alignment: committee + stock + donor + vote on same industry
    for c_rel in committees:
        c_other_id = c_rel.to_entity_id if c_rel.from_entity_id == entity.id else c_rel.from_entity_id
        c_ent = entities_map.get(c_other_id)
        if not c_ent:
            continue
        c_industries = _industries_for_committee(c_ent.name)
        if not c_industries:
            continue
        c_set = set(c_industries)

        for s_rel, s_ent in stocks:
            s_kws = set(stock_keywords.get(s_ent.slug, []))
            if not (c_set & s_kws):
                continue
            for d_rel, d_ent in donations:
                d_kws = set(donor_keywords.get(d_ent.slug, []))
                if not (c_set & d_kws):
                    continue
                for v_rel, v_ent in yes_votes:
                    v_kws = set(bill_keywords.get(v_ent.slug, []))
                    if not (c_set & v_kws):
                        continue
                    overlap_industry = c_set & s_kws & d_kws & v_kws
                    if not overlap_industry:
                        # At least the committee industry must match each individually
                        if (c_set & s_kws) and (c_set & d_kws) and (c_set & v_kws):
                            overlap_industry = c_set & (s_kws | d_kws | v_kws)
                        else:
                            continue
                    signals.append(ConflictSignal(
                        entity_slug=entity_slug,
                        conflict_type="full_structural_alignment",
                        severity="high_concern",
                        description=(
                            f"Full structural alignment: This official sits on "
                            f"{_sanitize(c_ent.name)}, holds stock in {_sanitize(s_ent.name)}, "
                            f"received a donation from {_sanitize(d_ent.name)}, and voted on "
                            f"{_sanitize(v_ent.name)}. When multiple structural relationships "
                            f"align, the cumulative pattern warrants public awareness."
                        ),
                        why_this_matters=WHY_THIS_MATTERS["full_structural_alignment"],
                        evidence=[
                            {"type": "committee", "entity": c_ent.slug},
                            {"type": "stock", "entity": s_ent.slug},
                            {"type": "donation", "entity": d_ent.slug, "amount": d_rel.amount_usd},
                            {"type": "vote_yes", "entity": v_ent.slug},
                        ],
                        related_entities=[c_ent.slug, s_ent.slug, d_ent.slug, v_ent.slug],
                    ))

    # 5) Committee jurisdiction: official on committee that regulates a company
    #    they hold stock in OR received donations from
    for c_rel in committees:
        c_other_id = c_rel.to_entity_id if c_rel.from_entity_id == entity.id else c_rel.from_entity_id
        c_ent = entities_map.get(c_other_id)
        if not c_ent:
            continue
        c_industries = _industries_for_committee(c_ent.name)
        if not c_industries:
            continue

        # Check stocks under jurisdiction
        for s_rel, s_ent in stocks:
            s_kws = stock_keywords.get(s_ent.slug, [])
            if _keyword_overlap(c_industries, s_kws):
                signals.append(ConflictSignal(
                    entity_slug=entity_slug,
                    conflict_type="structural_committee_jurisdiction",
                    severity="structural_relationship",
                    description=(
                        f"Structural relationship: This official sits on "
                        f"{_sanitize(c_ent.name)}, which has jurisdiction over the industry "
                        f"that {_sanitize(s_ent.name)} operates in. This official holds stock "
                        f"in {_sanitize(s_ent.name)}. Committee assignments give officials "
                        f"direct regulatory authority over specific industries."
                    ),
                    why_this_matters=WHY_THIS_MATTERS["structural_committee_jurisdiction"],
                    evidence=[
                        {"type": "committee", "entity": c_ent.slug, "name": _sanitize(c_ent.name)},
                        {"type": "stock", "entity": s_ent.slug, "name": _sanitize(s_ent.name)},
                    ],
                    related_entities=[c_ent.slug, s_ent.slug],
                ))

        # Check donations from entities under jurisdiction
        for d_rel, d_ent in donations:
            d_kws = donor_keywords.get(d_ent.slug, [])
            if _keyword_overlap(c_industries, d_kws):
                signals.append(ConflictSignal(
                    entity_slug=entity_slug,
                    conflict_type="structural_committee_jurisdiction",
                    severity="structural_relationship",
                    description=(
                        f"Structural relationship: This official sits on "
                        f"{_sanitize(c_ent.name)}, which regulates the industry that donor "
                        f"{_sanitize(d_ent.name)} operates in. When industries contribute to "
                        f"officials who regulate them, the structural relationship is worth "
                        f"public scrutiny."
                    ),
                    why_this_matters=WHY_THIS_MATTERS["structural_committee_jurisdiction"],
                    evidence=[
                        {"type": "committee", "entity": c_ent.slug, "name": _sanitize(c_ent.name)},
                        {"type": "donation", "entity": d_ent.slug, "name": _sanitize(d_ent.name),
                         "amount": d_rel.amount_usd},
                    ],
                    related_entities=[c_ent.slug, d_ent.slug],
                ))

    # 6) Active lobbying: company actively lobbying + official on relevant committee
    #    + received donations
    for c_rel in committees:
        c_other_id = c_rel.to_entity_id if c_rel.from_entity_id == entity.id else c_rel.from_entity_id
        c_ent = entities_map.get(c_other_id)
        if not c_ent:
            continue
        c_industries = _industries_for_committee(c_ent.name)
        if not c_industries:
            continue

        for d_rel, d_ent in donations:
            d_kws = donor_keywords.get(d_ent.slug, [])
            if not _keyword_overlap(c_industries, d_kws):
                continue
            # Check if the donor's employer/associated company has active lobbying
            d_meta = d_ent.metadata_ or {}
            lobbying_data = d_meta.get("lobbying", {})
            has_lobbying = lobbying_data.get("filing_count", 0) > 0

            # Also check if any connected entity (via employer) has lobbying
            employer = d_meta.get("employer", "")
            if not has_lobbying and employer:
                employer_lower = _sanitize(str(employer)).lower()
                for eid, ent in entities_map.items():
                    ent_meta = ent.metadata_ or {}
                    if ent_meta.get("lobbying", {}).get("filing_count", 0) > 0:
                        if employer_lower in _sanitize(ent.name).lower():
                            has_lobbying = True
                            break

            if has_lobbying:
                signals.append(ConflictSignal(
                    entity_slug=entity_slug,
                    conflict_type="structural_lobbying_regulatory_overlap",
                    severity="high_concern",
                    description=(
                        f"Structural relationship: {_sanitize(d_ent.name)} (or an associated "
                        f"company) actively lobbies on issues under {_sanitize(c_ent.name)}'s "
                        f"jurisdiction AND has contributed to this official's campaign. This "
                        f"creates a structural pathway for influence the public should "
                        f"understand."
                    ),
                    why_this_matters=WHY_THIS_MATTERS["structural_lobbying_regulatory_overlap"],
                    evidence=[
                        {"type": "committee", "entity": c_ent.slug, "name": _sanitize(c_ent.name)},
                        {"type": "donation", "entity": d_ent.slug, "name": _sanitize(d_ent.name),
                         "amount": d_rel.amount_usd},
                        {"type": "lobbying", "filing_count": lobbying_data.get("filing_count", 0),
                         "total_spend": lobbying_data.get("total_spend", 0)},
                    ],
                    related_entities=[c_ent.slug, d_ent.slug],
                ))

    # 7) Pre-vote spike: unusually large donations in 6 months (180 days) before a key vote
    #    "Large" = above median donation amount for this entity
    if donations:
        amounts = [d_rel.amount_usd for d_rel, _ in donations if d_rel.amount_usd and d_rel.amount_usd > 0]
        if amounts:
            amounts.sort()
            median_amount = amounts[len(amounts) // 2]
            large_threshold = max(median_amount * 2, 100000)  # 2x median or $1000, whichever higher (in cents)

            for d_rel, d_ent in donations:
                if not d_rel.date_start or not d_rel.amount_usd:
                    continue
                if d_rel.amount_usd < large_threshold:
                    continue
                d_kws = donor_keywords.get(d_ent.slug, [])

                for v_rel, v_ent in yes_votes:
                    if not v_rel.date_start:
                        continue
                    v_kws = bill_keywords.get(v_ent.slug, [])
                    if not _keyword_overlap(d_kws, v_kws):
                        continue
                    days_diff = (v_rel.date_start - d_rel.date_start).days
                    if 0 <= days_diff <= TIMING_WINDOW_DAYS:
                        signals.append(ConflictSignal(
                            entity_slug=entity_slug,
                            conflict_type="pre_vote_donation_pattern",
                            severity="high_concern",
                            description=(
                                f"Notable pattern: An unusually large donation "
                                f"(${d_rel.amount_usd / 100:,.0f}) from {_sanitize(d_ent.name)} "
                                f"was received {days_diff} days before a vote on "
                                f"{_sanitize(v_ent.name)}. Unusually large donations in the "
                                f"months before a key vote from industries that benefit from "
                                f"that vote represent a pattern worth public awareness."
                            ),
                            why_this_matters=WHY_THIS_MATTERS["pre_vote_donation_pattern"],
                            evidence=[
                                {"type": "donation", "entity": d_ent.slug, "name": _sanitize(d_ent.name),
                                 "amount": d_rel.amount_usd, "date": str(d_rel.date_start),
                                 "threshold": large_threshold},
                                {"type": "vote_yes", "entity": v_ent.slug, "name": _sanitize(v_ent.name),
                                 "date": str(v_rel.date_start), "days_after_donation": days_diff},
                            ],
                            related_entities=[d_ent.slug, v_ent.slug],
                        ))

    # --- Merge structural relationships (zero-vote-evidence alerts) ---
    structural_signals = await detect_structural_relationships(session, entity_slug)
    signals.extend(structural_signals)

    # --- Merge hidden connections (revolving door, family, speaking fees, etc.) ---
    hidden_signals = await detect_hidden_connections(session, entity_slug)
    signals.extend(hidden_signals)

    # --- Enrich with evidence chains for stock-related signals ---
    if stocks:
        from app.services.evidence_chain import build_evidence_chain, chain_to_dict
        enriched_companies: set[str] = set()
        for s_rel, s_ent in stocks:
            if s_ent.slug in enriched_companies:
                continue
            enriched_companies.add(s_ent.slug)
            try:
                ec = await build_evidence_chain(session, entity_slug, s_ent.slug)
                if ec and ec.chain_depth >= 3:
                    ec_dict = chain_to_dict(ec)
                    # Attach chain to matching signals
                    for sig in signals:
                        if s_ent.slug in sig.related_entities:
                            sig.evidence_chain = [ec_dict]
            except Exception:
                pass  # Don't break conflict detection if chain building fails

    # Deduplicate by description
    seen: set[str] = set()
    unique_signals: list[ConflictSignal] = []
    for s in signals:
        if s.description not in seen:
            seen.add(s.description)
            unique_signals.append(s)

    return unique_signals


# ---------------------------------------------------------------------------
# Bill money trail
# ---------------------------------------------------------------------------
def _generate_narrative(bill_name: str, money_data: dict) -> str:
    """Generate an investigative narrative via the claude CLI."""
    prompt = (
        f"Write a 2-sentence investigative summary about money flowing to senators "
        f"who voted YES on '{_sanitize(bill_name)}'. Data: {json.dumps(money_data)}. "
        f"Write from an FBI analyst perspective - factual, documented. Do not be accusatory."
    )
    try:
        result = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions", prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.stdout.strip() if result.returncode == 0 else "Narrative generation unavailable."
    except Exception:
        return "Narrative generation unavailable."


async def get_bill_money_trail(
    session: AsyncSession, bill_slug: str
) -> dict:
    """Trace money flowing to YES/NO voters on a bill."""

    # Load the bill entity
    result = await session.execute(
        select(Entity).where(Entity.slug == bill_slug)
    )
    bill = result.scalar_one_or_none()
    if bill is None:
        return {}

    # Get vote relationships pointing to this bill
    vote_q = select(Relationship).where(
        and_(
            Relationship.to_entity_id == bill.id,
            Relationship.relationship_type.in_(["voted_yes", "voted_no"]),
        )
    )
    vote_result = await session.execute(vote_q)
    vote_rels = vote_result.scalars().all()

    voter_ids = {r.from_entity_id for r in vote_rels}
    if not voter_ids:
        return {
            "bill": {"slug": bill.slug, "name": bill.name, "summary": bill.summary, "metadata": bill.metadata_},
            "yes_voters": [],
            "no_voters": [],
            "money_trail": {
                "total_to_yes_voters": 0,
                "by_industry": [],
                "conflict_score": "LOW",
                "narrative": "No vote data available.",
            },
        }

    # Load voter entities
    voters_result = await session.execute(
        select(Entity).where(Entity.id.in_(voter_ids))
    )
    voters_map = {e.id: e for e in voters_result.scalars().all()}

    # Separate yes/no voters
    yes_voter_ids: set = set()
    no_voter_ids: set = set()
    for r in vote_rels:
        if r.relationship_type == "voted_yes":
            yes_voter_ids.add(r.from_entity_id)
        else:
            no_voter_ids.add(r.from_entity_id)

    # Get donations TO yes voters
    donation_rels: list[Relationship] = []
    if yes_voter_ids:
        don_q = select(Relationship).where(
            and_(
                Relationship.to_entity_id.in_(yes_voter_ids),
                Relationship.relationship_type == "donated_to",
            )
        )
        don_result = await session.execute(don_q)
        donation_rels = don_result.scalars().all()

    # Load donor entities
    donor_ids = {r.from_entity_id for r in donation_rels}
    donors_map: dict = {}
    if donor_ids:
        d_result = await session.execute(
            select(Entity).where(Entity.id.in_(donor_ids))
        )
        donors_map = {e.id: e for e in d_result.scalars().all()}

    # Aggregate donations by industry
    industry_totals: dict[str, dict] = {}  # industry -> {amount, senators set}
    voter_top_industries: dict[str, dict[str, int]] = {}  # voter_slug -> {industry: amount}

    for d_rel in donation_rels:
        donor = donors_map.get(d_rel.from_entity_id)
        if not donor:
            continue
        meta = donor.metadata_ or {}
        industry = _sanitize(str(meta.get("industry", meta.get("sector", "Unknown"))))
        if not industry:
            industry = "Unknown"
        amount = d_rel.amount_usd or 0

        voter_ent = voters_map.get(d_rel.to_entity_id)
        voter_slug = voter_ent.slug if voter_ent else "unknown"

        if industry not in industry_totals:
            industry_totals[industry] = {"amount": 0, "senators": set()}
        industry_totals[industry]["amount"] += amount
        industry_totals[industry]["senators"].add(voter_slug)

        if voter_slug not in voter_top_industries:
            voter_top_industries[voter_slug] = {}
        voter_top_industries[voter_slug][industry] = (
            voter_top_industries[voter_slug].get(industry, 0) + amount
        )

    total_to_yes = sum(info["amount"] for info in industry_totals.values())

    by_industry = sorted(
        [
            {
                "industry": ind,
                "amount": info["amount"],
                "pct_of_total": round(info["amount"] * 100 / total_to_yes) if total_to_yes > 0 else 0,
                "senators": list(info["senators"]),
            }
            for ind, info in industry_totals.items()
        ],
        key=lambda x: x["amount"],
        reverse=True,
    )

    # Conflict score based on concentration
    if len(by_industry) > 0 and by_industry[0]["pct_of_total"] >= 40:
        conflict_score = "CRITICAL"
    elif len(by_industry) > 0 and by_industry[0]["pct_of_total"] >= 25:
        conflict_score = "HIGH"
    elif total_to_yes > 0:
        conflict_score = "MEDIUM"
    else:
        conflict_score = "LOW"

    # Build voter lists
    def _voter_info(vid: object) -> dict:
        v = voters_map.get(vid)
        if not v:
            return {"slug": "unknown", "name": "Unknown", "party": "", "top_donor_industries": []}
        meta = v.metadata_ or {}
        top_ind = voter_top_industries.get(v.slug, {})
        sorted_ind = sorted(top_ind.items(), key=lambda x: x[1], reverse=True)
        return {
            "slug": v.slug,
            "name": _sanitize(v.name),
            "party": _sanitize(str(meta.get("party", ""))),
            "top_donor_industries": [i[0] for i in sorted_ind[:5]],
        }

    yes_voters = [_voter_info(vid) for vid in yes_voter_ids]
    no_voters = [_voter_info(vid) for vid in no_voter_ids]

    money_data = {
        "total_to_yes_voters": total_to_yes,
        "by_industry": by_industry[:5],
        "conflict_score": conflict_score,
    }
    narrative = _generate_narrative(bill.name, money_data)

    return {
        "bill": {"slug": bill.slug, "name": _sanitize(bill.name), "summary": bill.summary, "metadata": bill.metadata_},
        "yes_voters": yes_voters,
        "no_voters": no_voters,
        "money_trail": {
            "total_to_yes_voters": total_to_yes,
            "by_industry": by_industry,
            "conflict_score": conflict_score,
            "narrative": narrative,
        },
    }


# ---------------------------------------------------------------------------
# Industry legislation
# ---------------------------------------------------------------------------
async def get_industry_legislation(
    session: AsyncSession, industry: str
) -> dict:
    """Find bills where donors from a given industry contributed heavily to YES voters."""
    industry_lower = _sanitize(industry).lower()

    # Find all bills
    bills_result = await session.execute(
        select(Entity).where(Entity.entity_type == "bill")
    )
    bills = bills_result.scalars().all()

    results = []
    for bill in bills:
        # Find YES voters
        vote_q = select(Relationship).where(
            and_(
                Relationship.to_entity_id == bill.id,
                Relationship.relationship_type == "voted_yes",
            )
        )
        vote_result = await session.execute(vote_q)
        yes_rels = vote_result.scalars().all()
        yes_ids = {r.from_entity_id for r in yes_rels}
        if not yes_ids:
            continue

        # Find donations to those YES voters
        don_q = select(Relationship).where(
            and_(
                Relationship.to_entity_id.in_(yes_ids),
                Relationship.relationship_type == "donated_to",
            )
        )
        don_result = await session.execute(don_q)
        don_rels = don_result.scalars().all()

        donor_ids = {r.from_entity_id for r in don_rels}
        if not donor_ids:
            continue

        donors_result = await session.execute(
            select(Entity).where(Entity.id.in_(donor_ids))
        )
        donors = {e.id: e for e in donors_result.scalars().all()}

        # Sum donations from matching industry
        industry_amount = 0
        matched_donors: list[str] = []
        for dr in don_rels:
            donor = donors.get(dr.from_entity_id)
            if not donor:
                continue
            kws = _extract_industry_keywords(donor)
            if industry_lower in kws:
                industry_amount += dr.amount_usd or 0
                if donor.slug not in matched_donors:
                    matched_donors.append(donor.slug)

        if industry_amount > 0:
            results.append({
                "bill_slug": bill.slug,
                "bill_name": _sanitize(bill.name),
                "industry_donation_total": industry_amount,
                "yes_voter_count": len(yes_ids),
                "matched_donors": matched_donors,
            })

    results.sort(key=lambda x: x["industry_donation_total"], reverse=True)
    return {
        "industry": industry,
        "bills": results,
        "total_bills": len(results),
    }


# ---------------------------------------------------------------------------
# Donation timeline
# ---------------------------------------------------------------------------
async def get_donation_timeline(
    session: AsyncSession, entity_slug: str
) -> list[dict]:
    """Return chronological donations and votes with days_between for related pairs."""

    result = await session.execute(
        select(Entity).where(Entity.slug == entity_slug)
    )
    entity = result.scalar_one_or_none()
    if entity is None:
        return []

    # Incoming donations (others donated to this entity)
    don_q = select(Relationship).where(
        and_(
            Relationship.to_entity_id == entity.id,
            Relationship.relationship_type == "donated_to",
        )
    )
    don_result = await session.execute(don_q)
    donation_rels = don_result.scalars().all()

    # Outgoing votes
    vote_q = select(Relationship).where(
        and_(
            Relationship.from_entity_id == entity.id,
            Relationship.relationship_type.in_(["voted_yes", "voted_no", "voted_present"]),
        )
    )
    vote_result = await session.execute(vote_q)
    vote_rels = vote_result.scalars().all()

    # Load related entities
    related_ids = set()
    for r in donation_rels:
        related_ids.add(r.from_entity_id)
    for r in vote_rels:
        related_ids.add(r.to_entity_id)

    related_map: dict = {}
    if related_ids:
        ent_result = await session.execute(
            select(Entity).where(Entity.id.in_(related_ids))
        )
        related_map = {e.id: e for e in ent_result.scalars().all()}

    events: list[dict] = []

    for dr in donation_rels:
        donor = related_map.get(dr.from_entity_id)
        events.append({
            "date": str(dr.date_start) if dr.date_start else None,
            "event_type": "donation",
            "description": f"Donation from {_sanitize(donor.name) if donor else 'Unknown'}",
            "amount_usd": dr.amount_usd,
            "related_entity_slug": donor.slug if donor else None,
            "days_before_vote": None,
        })

    for vr in vote_rels:
        bill = related_map.get(vr.to_entity_id)
        events.append({
            "date": str(vr.date_start) if vr.date_start else None,
            "event_type": "vote",
            "description": f"{vr.relationship_type.replace('_', ' ').title()} on {_sanitize(bill.name) if bill else 'Unknown'}",
            "amount_usd": None,
            "related_entity_slug": bill.slug if bill else None,
            "days_before_vote": None,
        })

    # Sort chronologically
    events.sort(key=lambda e: e["date"] or "9999-99-99")

    # Calculate days_before_vote for donation->vote pairs in related industries
    suspicious_count = 0
    for i, ev in enumerate(events):
        if ev["event_type"] != "donation" or ev["date"] is None:
            continue
        donor_ent = None
        for dr in donation_rels:
            d = related_map.get(dr.from_entity_id)
            if d and d.slug == ev["related_entity_slug"]:
                donor_ent = d
                break
        if not donor_ent:
            continue
        d_kws = _extract_industry_keywords(donor_ent)

        for j in range(i + 1, len(events)):
            vev = events[j]
            if vev["event_type"] != "vote" or vev["date"] is None:
                continue
            bill_ent = None
            for vr in vote_rels:
                b = related_map.get(vr.to_entity_id)
                if b and b.slug == vev["related_entity_slug"]:
                    bill_ent = b
                    break
            if not bill_ent:
                continue
            b_kws = _extract_industry_keywords(bill_ent)
            if _keyword_overlap(d_kws, b_kws):
                from datetime import date as date_type
                d_date = date_type.fromisoformat(ev["date"])
                v_date = date_type.fromisoformat(vev["date"])
                days = (v_date - d_date).days
                if 0 <= days <= TIMING_WINDOW_DAYS:
                    ev["days_before_vote"] = days
                    suspicious_count += 1
                    break  # Only link to closest related vote

    return events


# ---------------------------------------------------------------------------
# Shared donor network
# ---------------------------------------------------------------------------
async def get_shared_donor_network(
    session: AsyncSession, entity_slug: str
) -> dict:
    """Find other entities that share donors with this entity."""

    result = await session.execute(
        select(Entity).where(Entity.slug == entity_slug)
    )
    entity = result.scalar_one_or_none()
    if entity is None:
        return {"entity": None, "network": [], "total_shared_donors": 0}

    # Get donors to this entity
    don_q = select(Relationship).where(
        and_(
            Relationship.to_entity_id == entity.id,
            Relationship.relationship_type == "donated_to",
        )
    )
    don_result = await session.execute(don_q)
    my_donations = don_result.scalars().all()
    my_donor_ids = {r.from_entity_id for r in my_donations}

    if not my_donor_ids:
        return {
            "entity": {"slug": entity.slug, "name": _sanitize(entity.name), "entity_type": entity.entity_type},
            "network": [],
            "total_shared_donors": 0,
        }

    # Find other entities that received donations from the same donors
    shared_q = select(Relationship).where(
        and_(
            Relationship.from_entity_id.in_(my_donor_ids),
            Relationship.relationship_type == "donated_to",
            Relationship.to_entity_id != entity.id,
        )
    )
    shared_result = await session.execute(shared_q)
    shared_rels = shared_result.scalars().all()

    # Load related entities
    other_ids = {r.to_entity_id for r in shared_rels}
    all_needed = my_donor_ids | other_ids
    ent_result = await session.execute(
        select(Entity).where(Entity.id.in_(all_needed))
    )
    ent_map = {e.id: e for e in ent_result.scalars().all()}

    # Build network grouped by recipient
    network: dict[str, dict] = {}  # recipient_slug -> info
    all_shared_donor_slugs: set[str] = set()

    for r in shared_rels:
        recipient = ent_map.get(r.to_entity_id)
        donor = ent_map.get(r.from_entity_id)
        if not recipient or not donor:
            continue
        slug = recipient.slug
        if slug not in network:
            network[slug] = {
                "senator_slug": slug,
                "senator_name": _sanitize(recipient.name),
                "shared_donors": [],
                "total_shared_amount": 0,
            }
        d_name = _sanitize(donor.name)
        if d_name not in network[slug]["shared_donors"]:
            network[slug]["shared_donors"].append(d_name)
        network[slug]["total_shared_amount"] += r.amount_usd or 0
        all_shared_donor_slugs.add(donor.slug)

    network_list = sorted(network.values(), key=lambda x: x["total_shared_amount"], reverse=True)

    return {
        "entity": {"slug": entity.slug, "name": _sanitize(entity.name), "entity_type": entity.entity_type},
        "network": network_list,
        "total_shared_donors": len(all_shared_donor_slugs),
    }


# ---------------------------------------------------------------------------
# Relationship spotlight detection
# ---------------------------------------------------------------------------
async def detect_relationship_spotlight(
    session: AsyncSession, entity_slug: str
) -> list[dict]:
    """Find entities with 3+ connection signals to this person.

    For each connected entity (company, org), count signal types:
    - donated_to
    - holds_stock
    - committee jurisdiction overlap
    - lobbying relationship (lobbies_on_behalf_of, registered_lobbyist_for)
    - voted on their legislation

    If 3+ signals exist, create a spotlight entry for display.

    Returns list of spotlight dicts sorted by signal_count descending.
    """

    # Load entity
    result = await session.execute(
        select(Entity).where(Entity.slug == entity_slug)
    )
    entity = result.scalar_one_or_none()
    if entity is None:
        return []

    # Load all relationships
    rels_q = select(Relationship).where(
        or_(
            Relationship.from_entity_id == entity.id,
            Relationship.to_entity_id == entity.id,
        )
    )
    rels_result = await session.execute(rels_q)
    all_rels = rels_result.scalars().all()

    # Collect connected entity IDs
    connected_ids = set()
    for r in all_rels:
        connected_ids.add(r.from_entity_id)
        connected_ids.add(r.to_entity_id)
    connected_ids.discard(entity.id)

    if not connected_ids:
        return []

    # Load connected entities
    ent_result = await session.execute(
        select(Entity).where(Entity.id.in_(connected_ids))
    )
    entities_map = {e.id: e for e in ent_result.scalars().all()}

    # Build signal map: entity_id -> set of signal types
    signal_map: dict[object, dict] = {}  # entity_id -> {"signals": set, "evidence": list}

    # Get committee industries for this person
    person_committee_industries: dict[str, list[str]] = {}  # committee_slug -> industries
    for r in all_rels:
        if r.relationship_type == "committee_member" and r.from_entity_id == entity.id:
            c_ent = entities_map.get(r.to_entity_id)
            if c_ent:
                industries = _industries_for_committee(c_ent.name)
                if industries:
                    person_committee_industries[c_ent.slug] = industries

    for r in all_rels:
        other_id = r.to_entity_id if r.from_entity_id == entity.id else r.from_entity_id
        other = entities_map.get(other_id)
        if not other:
            continue

        if other_id not in signal_map:
            signal_map[other_id] = {"signals": set(), "evidence": []}

        rel_type = r.relationship_type

        if rel_type == "donated_to" and r.to_entity_id == entity.id:
            signal_map[other_id]["signals"].add("donated_to")
            signal_map[other_id]["evidence"].append({
                "type": "donation",
                "amount": r.amount_usd,
            })

        elif rel_type == "holds_stock" and r.from_entity_id == entity.id:
            signal_map[other_id]["signals"].add("holds_stock")
            signal_map[other_id]["evidence"].append({
                "type": "stock_holding",
            })

        elif rel_type in ("lobbies_on_behalf_of", "registered_lobbyist_for"):
            signal_map[other_id]["signals"].add("lobbying_relationship")
            signal_map[other_id]["evidence"].append({
                "type": "lobbying",
                "relationship": rel_type,
            })

        elif rel_type in ("voted_yes", "voted_no", "voted_present"):
            signal_map[other_id]["signals"].add("voted_on_legislation")
            signal_map[other_id]["evidence"].append({
                "type": "vote",
                "vote_type": rel_type,
            })

    # Check committee jurisdiction overlap for connected entities
    all_committee_industries = set()
    for industries in person_committee_industries.values():
        all_committee_industries.update(industries)

    if all_committee_industries:
        for eid, info in signal_map.items():
            ent = entities_map.get(eid)
            if not ent:
                continue
            ent_kws = _extract_industry_keywords(ent)
            if _keyword_overlap(list(all_committee_industries), ent_kws):
                info["signals"].add("committee_jurisdiction_overlap")
                info["evidence"].append({
                    "type": "jurisdiction_overlap",
                })

    # Build spotlights for entities with 3+ signals
    spotlights: list[dict] = []
    for eid, info in signal_map.items():
        signal_count = len(info["signals"])
        if signal_count >= 3:
            ent = entities_map.get(eid)
            if not ent:
                continue
            spotlights.append({
                "entity_slug": ent.slug,
                "entity_name": _sanitize(ent.name),
                "entity_type": ent.entity_type,
                "signal_count": signal_count,
                "signals": [{"type": s} for s in sorted(info["signals"])],
                "severity": _severity(signal_count),
            })

    # Sort by signal_count descending
    spotlights.sort(key=lambda x: x["signal_count"], reverse=True)
    return spotlights
