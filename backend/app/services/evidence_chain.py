"""
Evidence Chain Builder — connects stock holdings, lobbying, votes, and outcomes
into narrative chains that surface structural conflicts of interest.

A complete evidence chain traces the path:
  Official holds stock in Company →
  Company lobbies for Bill →
  Official votes on that Bill →
  Bill outcome / financial impact

Minimum viable chain requires steps 1-3 (stock + lobbying + vote alignment).
Steps 4-5 (bill outcome, AI narrative) are enrichment.
"""

import json
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entity, Relationship


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ChainLink:
    step: int
    type: str          # "stock_holding", "lobbying", "vote", "bill_outcome", "financial_impact"
    description: str
    entity: str        # slug of the entity involved
    amount: str        # dollar amount or range
    source_url: str
    date: str          # when this link occurred (ISO date string)


@dataclass
class EvidenceChain:
    official_slug: str
    company_slug: str
    chain: list[ChainLink] = field(default_factory=list)
    severity: str = "connection_noted"
    narrative: str = ""
    chain_depth: int = 0


def _sanitize(text: str) -> str:
    """Strip non-ASCII characters."""
    if text is None:
        return ""
    return text.encode("ascii", errors="ignore").decode("ascii")


def _format_amount(amount_usd: Optional[int], amount_label: Optional[str]) -> str:
    """Format a dollar amount for display."""
    if amount_label:
        return amount_label
    if amount_usd:
        return f"${amount_usd / 100:,.0f}" if amount_usd > 100 else f"${amount_usd:,}"
    return "undisclosed"


def _severity_from_depth(depth: int) -> str:
    """Map chain depth to severity level."""
    if depth >= 5:
        return "high_concern"
    if depth >= 4:
        return "notable_pattern"
    if depth >= 3:
        return "structural_relationship"
    return "connection_noted"


# ---------------------------------------------------------------------------
# Core chain builder
# ---------------------------------------------------------------------------

async def build_evidence_chain(
    session: AsyncSession,
    official_slug: str,
    company_slug: str,
) -> Optional[EvidenceChain]:
    """Build a complete evidence chain between an official and a company.

    Steps:
    1. Get official's holds_stock relationships to the company -> ChainLink step 1
    2. Get company's lobbies_on_behalf_of relationships -> find bills lobbied for -> ChainLink step 2
    3. Cross-reference those bills with official's voted_yes/voted_no/sponsored -> ChainLink step 3
    4. Get bill status from entity metadata -> ChainLink step 4
    5. Generate AI narrative via Claude CLI explaining the financial impact -> ChainLink step 5

    Only returns a chain if at least steps 1-3 are present (stock + lobbying + vote alignment).
    Steps 4-5 are enrichment.
    """

    # Load official entity
    result = await session.execute(
        select(Entity).where(Entity.slug == official_slug)
    )
    official = result.scalar_one_or_none()
    if official is None:
        return None

    # Load company entity
    result = await session.execute(
        select(Entity).where(Entity.slug == company_slug)
    )
    company = result.scalar_one_or_none()
    if company is None:
        return None

    chain = EvidenceChain(
        official_slug=official_slug,
        company_slug=company_slug,
    )

    # --- Step 1: Stock holding ---
    stock_q = select(Relationship).where(
        and_(
            Relationship.from_entity_id == official.id,
            Relationship.to_entity_id == company.id,
            Relationship.relationship_type == "holds_stock",
        )
    )
    stock_result = await session.execute(stock_q)
    stock_rels = stock_result.scalars().all()

    if not stock_rels:
        return None  # No stock holding = no chain

    stock_rel = stock_rels[0]  # Use first/primary holding
    chain.chain.append(ChainLink(
        step=1,
        type="stock_holding",
        description=(
            f"{_sanitize(official.name)} holds stock in {_sanitize(company.name)}"
            f" ({_format_amount(stock_rel.amount_usd, stock_rel.amount_label)})"
        ),
        entity=company_slug,
        amount=_format_amount(stock_rel.amount_usd, stock_rel.amount_label),
        source_url=stock_rel.source_url or "",
        date=str(stock_rel.date_start) if stock_rel.date_start else "",
    ))

    # --- Step 2: Company lobbying -> find bills ---
    lobby_q = select(Relationship, Entity).join(
        Entity, Entity.id == Relationship.to_entity_id
    ).where(
        and_(
            Relationship.from_entity_id == company.id,
            Relationship.relationship_type == "lobbies_on_behalf_of",
        )
    )
    lobby_result = await session.execute(lobby_q)
    lobby_rows = lobby_result.all()

    if not lobby_rows:
        return None  # No lobbying = chain incomplete

    # Collect bills lobbied for
    lobbied_bills: dict[str, tuple[Relationship, Entity]] = {}
    for rel, bill_entity in lobby_rows:
        lobbied_bills[bill_entity.slug] = (rel, bill_entity)

    # --- Step 3: Cross-reference with official's votes/sponsorship ---
    vote_q = select(Relationship, Entity).join(
        Entity, Entity.id == Relationship.to_entity_id
    ).where(
        and_(
            Relationship.from_entity_id == official.id,
            Relationship.relationship_type.in_(["voted_yes", "voted_no", "sponsored", "cosponsored"]),
        )
    )
    vote_result = await session.execute(vote_q)
    vote_rows = vote_result.all()

    # Find votes that match lobbied bills
    matching_vote: Optional[tuple] = None
    matching_bill_slug: Optional[str] = None
    lobby_link: Optional[ChainLink] = None

    for v_rel, v_entity in vote_rows:
        if v_entity.slug in lobbied_bills:
            l_rel, l_entity = lobbied_bills[v_entity.slug]

            # Add lobbying link (step 2)
            lobby_link = ChainLink(
                step=2,
                type="lobbying",
                description=(
                    f"{_sanitize(company.name)} lobbied on behalf of "
                    f"{_sanitize(l_entity.name)}"
                    f" ({_format_amount(l_rel.amount_usd, l_rel.amount_label)})"
                ),
                entity=l_entity.slug,
                amount=_format_amount(l_rel.amount_usd, l_rel.amount_label),
                source_url=l_rel.source_url or "",
                date=str(l_rel.date_start) if l_rel.date_start else "",
            )

            # Add vote link (step 3)
            vote_action = {
                "voted_yes": "voted YES on",
                "voted_no": "voted NO on",
                "sponsored": "sponsored",
                "cosponsored": "cosponsored",
            }.get(v_rel.relationship_type, "voted on")

            matching_vote = (v_rel, v_entity)
            matching_bill_slug = v_entity.slug

            chain.chain.append(lobby_link)
            chain.chain.append(ChainLink(
                step=3,
                type="vote",
                description=(
                    f"{_sanitize(official.name)} {vote_action} "
                    f"{_sanitize(v_entity.name)}"
                ),
                entity=v_entity.slug,
                amount="",
                source_url=v_rel.source_url or "",
                date=str(v_rel.date_start) if v_rel.date_start else "",
            ))
            break  # Use first matching vote

    if matching_vote is None:
        return None  # No vote alignment = chain incomplete (need steps 1-3)

    # --- Step 4: Bill outcome (enrichment) ---
    v_rel, v_entity = matching_vote
    bill_meta = v_entity.metadata_ or {}
    bill_status = bill_meta.get("status", bill_meta.get("latest_action", ""))
    if bill_status:
        chain.chain.append(ChainLink(
            step=4,
            type="bill_outcome",
            description=(
                f"Bill status: {_sanitize(str(bill_status))}"
            ),
            entity=v_entity.slug,
            amount="",
            source_url="",
            date="",
        ))

    # --- Step 5: AI narrative (enrichment) ---
    chain.chain_depth = len(chain.chain)
    chain.severity = _severity_from_depth(chain.chain_depth)

    narrative = await _generate_chain_narrative(chain)
    chain.narrative = narrative

    if chain.chain_depth >= 5 or (chain.chain_depth >= 3 and narrative):
        # Add a financial impact link summarizing the narrative
        chain.chain.append(ChainLink(
            step=5,
            type="financial_impact",
            description=narrative[:300] if narrative else "Financial impact analysis unavailable.",
            entity=company_slug,
            amount=_format_amount(stock_rel.amount_usd, stock_rel.amount_label),
            source_url="",
            date="",
        ))
        chain.chain_depth = len(chain.chain)
        chain.severity = _severity_from_depth(chain.chain_depth)

    return chain


# ---------------------------------------------------------------------------
# Batch builders
# ---------------------------------------------------------------------------

async def build_all_chains(
    session: AsyncSession,
    official_slug: str,
) -> list[EvidenceChain]:
    """For each company the official holds stock in, attempt to build a chain.
    Return only chains with 3+ steps, sorted by chain_depth descending."""

    # Load official
    result = await session.execute(
        select(Entity).where(Entity.slug == official_slug)
    )
    official = result.scalar_one_or_none()
    if official is None:
        return []

    # Get all companies this official holds stock in
    stock_q = select(Relationship, Entity).join(
        Entity, Entity.id == Relationship.to_entity_id
    ).where(
        and_(
            Relationship.from_entity_id == official.id,
            Relationship.relationship_type == "holds_stock",
        )
    )
    stock_result = await session.execute(stock_q)
    stock_rows = stock_result.all()

    chains: list[EvidenceChain] = []
    seen_companies: set[str] = set()

    for _, company_entity in stock_rows:
        if company_entity.slug in seen_companies:
            continue
        seen_companies.add(company_entity.slug)

        chain = await build_evidence_chain(session, official_slug, company_entity.slug)
        if chain and chain.chain_depth >= 3:
            chains.append(chain)

    # Sort by chain_depth descending
    chains.sort(key=lambda c: c.chain_depth, reverse=True)
    return chains


async def get_company_chains(
    session: AsyncSession,
    company_slug: str,
) -> list[EvidenceChain]:
    """Find all officials with evidence chains connecting them to this company.
    Return chains sorted by chain_depth descending."""

    # Load company
    result = await session.execute(
        select(Entity).where(Entity.slug == company_slug)
    )
    company = result.scalar_one_or_none()
    if company is None:
        return []

    # Find all officials who hold stock in this company
    stock_q = select(Relationship, Entity).join(
        Entity, Entity.id == Relationship.from_entity_id
    ).where(
        and_(
            Relationship.to_entity_id == company.id,
            Relationship.relationship_type == "holds_stock",
        )
    )
    stock_result = await session.execute(stock_q)
    stock_rows = stock_result.all()

    chains: list[EvidenceChain] = []
    seen_officials: set[str] = set()

    for _, official_entity in stock_rows:
        if official_entity.slug in seen_officials:
            continue
        seen_officials.add(official_entity.slug)

        chain = await build_evidence_chain(session, official_entity.slug, company_slug)
        if chain and chain.chain_depth >= 3:
            chains.append(chain)

    # Sort by chain_depth descending
    chains.sort(key=lambda c: c.chain_depth, reverse=True)
    return chains


# ---------------------------------------------------------------------------
# AI narrative generation
# ---------------------------------------------------------------------------

async def _generate_chain_narrative(chain: EvidenceChain) -> str:
    """Generate AI narrative for the chain via Claude CLI.

    The narrative should sound like:
    'Senator Fetterman holds between $15,000 and $50,000 in Bank of America stock.
    Bank of America spent $1.2 million lobbying for the Community Reinvestment
    Modernization Act, which Fetterman voted for in January 2024. The bill passed
    and reduced CFPB oversight requirements that had previously resulted in
    enforcement actions against Bank of America. This sequence of events represents
    a textbook structural conflict of interest that the public has a right to scrutinize.'

    Falls back to a template-based narrative if Claude CLI is unavailable.
    """
    # Build chain data for the prompt
    chain_data = []
    for link in chain.chain:
        chain_data.append({
            "step": link.step,
            "type": link.type,
            "description": link.description,
            "entity": link.entity,
            "amount": link.amount,
            "date": link.date,
        })

    system_prompt = (
        "You are an investigative journalist writing a concise, factual narrative "
        "about a structural conflict of interest. Write 2-3 sentences that connect "
        "the chain of evidence in plain English. Be factual, not accusatory. "
        "End with a sentence about why this pattern matters for public transparency. "
        "Do NOT use bullet points. Write a flowing paragraph."
    )

    data_prompt = (
        f"Write a narrative connecting this evidence chain:\n"
        f"{json.dumps(chain_data, indent=2)}\n\n"
        f"Official: {chain.official_slug}\n"
        f"Company: {chain.company_slug}\n"
        f"Severity: {chain.severity}"
    )

    full_prompt = f"{system_prompt}\n\n{data_prompt}"

    try:
        result = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions", full_prompt],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if result.returncode == 0 and result.stdout.strip():
            return _sanitize(result.stdout.strip())
    except Exception as e:
        print(f"[EvidenceChain] Claude CLI failed: {e}")

    # Fallback: template-based narrative
    return _generate_fallback_narrative(chain)


def _generate_fallback_narrative(chain: EvidenceChain) -> str:
    """Generate a template-based narrative when Claude CLI is unavailable."""
    parts = []
    for link in chain.chain:
        if link.type == "stock_holding":
            parts.append(link.description)
        elif link.type == "lobbying":
            parts.append(link.description)
        elif link.type == "vote":
            parts.append(link.description)
        elif link.type == "bill_outcome":
            parts.append(link.description)

    if not parts:
        return "Evidence chain data unavailable."

    narrative = ". ".join(parts) + "."
    narrative += (
        " This sequence of events represents a structural relationship "
        "that the public has a right to scrutinize."
    )
    return narrative


def chain_to_dict(chain: EvidenceChain) -> dict:
    """Convert an EvidenceChain to a JSON-serializable dict."""
    return {
        "official_slug": chain.official_slug,
        "company_slug": chain.company_slug,
        "chain": [asdict(link) for link in chain.chain],
        "severity": chain.severity,
        "narrative": chain.narrative,
        "chain_depth": chain.chain_depth,
    }
