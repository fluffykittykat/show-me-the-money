import os
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import (
    BillInfluenceSignal,
    Entity,
    MoneyTrail,
    OfficialInfluenceSignal,
    Relationship,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

CHAT_API_KEY = os.getenv("ANTHROPIC_CHAT_API_KEY", os.getenv("ANTHROPIC_API_KEY", ""))


class ChatRequest(BaseModel):
    slug: str
    message: str
    history: list[dict] = []


class ChatResponse(BaseModel):
    reply: str
    sources: list[str] = []


def _json_safe(val):
    """Convert Decimal and other non-serializable types to strings."""
    if isinstance(val, Decimal):
        return float(val)
    return val


def _fmt_money(cents: int | None) -> str:
    if not cents:
        return "$0"
    dollars = abs(cents) / 100
    if dollars >= 1_000_000:
        return f"${dollars / 1_000_000:,.1f}M"
    if dollars >= 1_000:
        return f"${dollars / 1_000:,.0f}K"
    return f"${dollars:,.0f}"


async def _build_context(entity: Entity, db: AsyncSession) -> str:
    """Build rich context string from all available data for an entity."""
    meta = entity.metadata_ or {}
    entity_type = entity.entity_type
    sections = []

    # --- Entity basics ---
    basics = [f"Name: {entity.name}", f"Type: {entity_type}", f"Slug: {entity.slug}"]
    if entity.summary:
        basics.append(f"Summary: {entity.summary}")
    for key in ("party", "state", "chamber", "bioguide_id", "fec_candidate_id",
                "best_fec_cycle", "campaign_total", "total_receipts", "total_disbursements",
                "policy_area", "congress_url", "introduced_date", "status_label",
                "crs_summary", "bill_type", "bill_number", "congress"):
        val = meta.get(key)
        if val is not None:
            basics.append(f"{key}: {val}")
    sections.append("## Entity Profile\n" + "\n".join(basics))

    # --- Committees ---
    committees = meta.get("committees") or meta.get("committee_assignments")
    if committees and isinstance(committees, list):
        lines = [f"- {c}" if isinstance(c, str) else f"- {c.get('name', c)}" for c in committees[:20]]
        sections.append("## Committee Assignments\n" + "\n".join(lines))

    # --- Money trails (for officials) ---
    trails_result = await db.execute(
        select(MoneyTrail).where(MoneyTrail.official_id == entity.id)
    )
    trails = trails_result.scalars().all()
    if trails:
        lines = []
        for t in sorted(trails, key=lambda x: x.total_amount or 0, reverse=True)[:15]:
            lines.append(
                f"- {t.industry}: {_fmt_money(t.total_amount)} | Verdict: {t.verdict} "
                f"({t.dot_count} dots) | {t.narrative or ''}"
            )
        sections.append("## Money Trails (Industry Influence)\n" + "\n".join(lines))

    # --- Top donors (relationships) ---
    donors_result = await db.execute(
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.to_entity_id == entity.id)
        .where(Relationship.relationship_type.in_(["donated_to", "donor"]))
        .order_by(Relationship.amount_usd.desc().nullslast())
        .limit(20)
    )
    donors = donors_result.all()
    if donors:
        lines = []
        for rel, donor_entity in donors:
            amt = _fmt_money(rel.amount_usd) if rel.amount_usd else "unknown"
            lines.append(f"- {donor_entity.name}: {amt}")
        sections.append("## Top Donors\n" + "\n".join(lines))

    # --- Outgoing relationships (for officials — who they connect to) ---
    out_result = await db.execute(
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.to_entity_id)
        .where(Relationship.from_entity_id == entity.id)
        .order_by(Relationship.amount_usd.desc().nullslast())
        .limit(15)
    )
    outgoing = out_result.all()
    if outgoing:
        lines = []
        for rel, target in outgoing:
            amt = _fmt_money(rel.amount_usd) if rel.amount_usd else ""
            lines.append(f"- [{rel.relationship_type}] {target.name} {amt}")
        sections.append("## Key Relationships\n" + "\n".join(lines))

    # --- Influence signals (official or bill) ---
    if entity_type == "person":
        sig_result = await db.execute(
            select(OfficialInfluenceSignal).where(
                OfficialInfluenceSignal.official_id == entity.id
            )
        )
    else:
        sig_result = await db.execute(
            select(BillInfluenceSignal).where(
                BillInfluenceSignal.bill_id == entity.id
            )
        )
    signals = sig_result.scalars().all()
    if signals:
        lines = []
        for s in signals:
            status = "FOUND" if s.found else "CLEAR"
            rarity = f" ({s.rarity_label})" if s.rarity_label else ""
            desc = f" — {s.description}" if s.description else ""
            lines.append(f"- {s.signal_type}: {status}{rarity}{desc}")
        sections.append("## Influence Signals\n" + "\n".join(lines))

    # --- AI Briefing (cached) ---
    briefing = meta.get("fbi_briefing") or meta.get("ai_briefing")
    if briefing:
        sections.append(f"## AI Briefing (cached)\n{briefing}")

    # --- Stock trades ---
    trades = meta.get("stock_trades")
    if trades and isinstance(trades, list):
        lines = []
        for t in trades[:10]:
            if isinstance(t, dict):
                ticker = t.get("ticker", "?")
                tx_type = t.get("type", "?")
                amount = t.get("amount", "?")
                date = t.get("date", "?")
                lines.append(f"- {date}: {tx_type} {ticker} ({amount})")
        if lines:
            sections.append("## Stock Trades\n" + "\n".join(lines))

    # --- Bill sponsors (for bill entities) ---
    if entity_type == "bill":
        sponsors_result = await db.execute(
            select(Relationship, Entity)
            .join(Entity, Entity.id == Relationship.from_entity_id)
            .where(Relationship.to_entity_id == entity.id)
            .where(Relationship.relationship_type.in_(["sponsored", "cosponsored", "sponsor", "cosponsor"]))
            .limit(20)
        )
        sponsors = sponsors_result.all()
        if sponsors:
            lines = []
            for rel, sponsor_entity in sponsors:
                sp_meta = sponsor_entity.metadata_ or {}
                party = sp_meta.get("party", "")
                state = sp_meta.get("state", "")
                lines.append(f"- {sponsor_entity.name} ({party}-{state}) [{rel.relationship_type}]")
            sections.append("## Sponsors & Cosponsors\n" + "\n".join(lines))

    return "\n\n".join(sections)


SYSTEM_PROMPT_TEMPLATE = """You are an investigative analyst for Follow The Money, a political corruption research platform. You have access to the following data about {entity_name}:

{context}

Rules:
- Be factual. Only reference data you can see above.
- Use specific dollar amounts, names, dates.
- When you don't have data to answer, say so honestly.
- Never accuse anyone of crimes. Present patterns and let the user draw conclusions.
- Keep responses concise — 2-3 paragraphs max.
- If the user asks about something not in the data, suggest they click Refresh Investigation to fetch more.
"""


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    # 1. Load entity
    result = await db.execute(select(Entity).where(Entity.slug == req.slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity '{req.slug}' not found")

    # 2. Build context
    context = await _build_context(entity, db)

    # 3. Build system prompt
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        entity_name=entity.name,
        context=context,
    )

    # 4. Build message history
    messages = []
    for msg in req.history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": req.message})

    # 5. Call Anthropic
    if not CHAT_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_CHAT_API_KEY not configured",
        )

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=CHAT_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=system_prompt,
            messages=messages,
        )
        reply = response.content[0].text if response.content else "No response generated."
    except Exception as e:
        logger.error("Chat API error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")

    return ChatResponse(reply=reply, sources=[])
