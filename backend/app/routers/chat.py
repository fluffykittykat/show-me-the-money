import os
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
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
    slug: str  # current page entity (for context)
    message: str
    history: list[dict] = []
    session_id: str = "default"  # support multiple chat sessions


class ChatResponse(BaseModel):
    reply: str
    sources: list[str] = []
    action_taken: str | None = None  # "refreshed" | "regenerated_briefing" | None


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


SYSTEM_PROMPT_TEMPLATE = """You are an investigative analyst for Follow The Money, a political corruption research platform.

The user is currently viewing: **{entity_name}**
But you can answer questions about ANY official, bill, PAC, or company in the database — not just the current page.

Here is the data we have:

{context}

## Your Capabilities

You can do everything the UI can do and more:

1. **Analyze patterns** — Connect dots between donors, committees, bills, and lobbying activity. Look for correlations the user might miss.

2. **Explain the data** — Translate dollar amounts, relationship types, and political structures into plain English anyone can understand.

3. **Compare** — If the user asks about another official or entity, use what you know to compare. If you don't have data on the other entity, tell them to search for it on the site.

4. **Trace money chains** — Follow the money from donor → PAC → official → committee → bill. Explain each link.

5. **Assess influence signals** — Explain what each signal means, why it's statistically significant (or not), and what it implies.

6. **Suggest investigations** — Tell the user what to look at next. "You should check who funds [PAC name]" or "Click on [bill name] to see its lobbying connections."

7. **Calculate** — Add up totals, compute percentages, compare across cycles.

## Actions You Can Take

When the user asks you to:
- "Run a full investigation" / "refresh the data" / "get latest" → The system will automatically trigger a full refresh. Summarize what the fresh data shows.
- "Regenerate the briefing" / "new briefing" → The system will regenerate the AI briefing. Summarize the new briefing.

## Rich Output Format

Use rich markdown in ALL your responses:
- **Bold** for key names, dollar amounts, and important findings
- Bullet points and numbered lists for clarity
- `code style` for bill numbers (e.g., `S. 2963`, `HR 1107`)
- Tables when comparing data (use markdown table syntax)
- > Blockquotes for highlighting key findings or smoking guns
- [Link text](url) when you know the Congress.gov or FEC URL from the data
- Use headers (### ) to organize longer responses
- Use --- horizontal rules to separate sections

## Rules

- Be factual. Reference specific data from above — dollar amounts, names, dates.
- When you make a connection, show the chain: **X** donated **$Y** → Official sits on **Z committee** → sponsored `Bill W`
- When you don't have data, say so clearly and suggest: "Try asking me to **run a full investigation** to fetch the latest data."
- Never accuse anyone of crimes. Say "the pattern suggests" or "this is statistically unusual."
- Be thorough. This is an investigation — give the user everything they need.
- When referencing other entities, mention their name so the user can search for them on the site.
"""


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    # 1. Load entity
    result = await db.execute(select(Entity).where(Entity.slug == req.slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity '{req.slug}' not found")

    # 2. Search for ANY entities the user mentions — not just current page
    action_taken = None
    msg_lower = req.message.lower()

    # Try to find other entities the user is asking about
    additional_entities = []
    # Extract potential entity names (words after "about", "for", "on", between quotes, etc.)
    import re as _re
    name_candidates = _re.findall(r'"([^"]+)"', req.message)  # quoted names
    name_candidates += _re.findall(r'(?:about|for|compare|vs|versus|look up|search|find|investigate)\s+(.+?)(?:\?|$|\.|\band\b)', msg_lower)

    for candidate in name_candidates:
        candidate = candidate.strip()
        if len(candidate) < 3 or len(candidate) > 50:
            continue
        search_result = await db.execute(
            select(Entity).where(
                Entity.name.ilike(f"%{candidate}%")
            ).limit(3)
        )
        for found_entity in search_result.scalars().all():
            if found_entity.id != entity.id and found_entity.id not in [e.id for e in additional_entities]:
                additional_entities.append(found_entity)

    # Action: Run full investigation / refresh
    if any(kw in msg_lower for kw in ["run investigation", "refresh", "full investigation", "update data", "fetch latest", "get fresh data", "re-run", "rerun"]):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=180.0) as hc:
                resp = await hc.post(f"http://localhost:8000/refresh/{entity.slug}")
                if resp.status_code == 200:
                    refresh_data = resp.json()
                    action_taken = "refreshed"
                    # Reload entity after refresh
                    result = await db.execute(select(Entity).where(Entity.slug == req.slug))
                    entity = result.scalar_one_or_none()
        except Exception as e:
            action_taken = f"refresh_failed: {e}"

    # Action: Query specific data
    elif any(kw in msg_lower for kw in ["how many donors", "how many bills", "how many", "total donated", "total raised", "count", "list all"]):
        # Run live queries and add results to context
        query_results = []

        # Donor count + total
        donor_q = await db.execute(
            select(
                func.count(Relationship.id).label("cnt"),
                func.sum(Relationship.amount_usd).label("total"),
            )
            .where(Relationship.to_entity_id == entity.id)
            .where(Relationship.relationship_type == "donated_to")
        )
        donor_row = donor_q.one_or_none()
        if donor_row:
            cnt, total = donor_row
            query_results.append(f"Donor count: {cnt}, Total donated: {_fmt_money(total)}")

        # Bill count
        bill_q = await db.execute(
            select(func.count(Relationship.id))
            .where(Relationship.from_entity_id == entity.id)
            .where(Relationship.relationship_type.in_(["sponsored", "cosponsored"]))
        )
        bill_count = bill_q.scalar() or 0
        query_results.append(f"Bills sponsored/cosponsored: {bill_count}")

        # Committee count
        comm_q = await db.execute(
            select(func.count(Relationship.id))
            .where(Relationship.from_entity_id == entity.id)
            .where(Relationship.relationship_type == "committee_member")
        )
        comm_count = comm_q.scalar() or 0
        query_results.append(f"Committee assignments: {comm_count}")

        # Stock trades
        stock_q = await db.execute(
            select(func.count(Relationship.id))
            .where(Relationship.from_entity_id == entity.id)
            .where(Relationship.relationship_type == "stock_trade")
        )
        stock_count = stock_q.scalar() or 0
        query_results.append(f"Stock trades on file: {stock_count}")

        # Lobbied_on connections
        lobby_q = await db.execute(
            select(func.count(Relationship.id))
            .where(Relationship.to_entity_id == entity.id)
            .where(Relationship.relationship_type == "lobbied_on")
        )
        lobby_count = lobby_q.scalar() or 0
        query_results.append(f"Bills with lobbying connections: {lobby_count}")

        action_taken = "queried"
        req.message += f"\n\n[LIVE QUERY RESULTS: {'; '.join(query_results)}]"

    # Action: Regenerate briefing
    elif any(kw in msg_lower for kw in ["regenerate briefing", "new briefing", "rewrite briefing", "generate briefing", "fresh briefing", "redo briefing", "update briefing"]):
        try:
            from app.services.ai_service import ai_briefing_service
            briefing = await ai_briefing_service.generate_briefing(
                entity_slug=entity.slug,
                context_data={"metadata": entity.metadata_ or {}},
                session=db,
                force_refresh=True,
            )
            action_taken = "regenerated_briefing"
        except Exception as e:
            action_taken = f"briefing_failed: {e}"

    # 3. Build context for the primary entity (after any actions)
    context = await _build_context(entity, db)

    # 3. Build context for additional entities the user asked about
    extra_context = ""
    for ae in additional_entities[:3]:  # max 3 extra entities to stay within context limits
        ae_context = await _build_context(ae, db)
        extra_context += f"\n\n{'='*60}\n## DATA FOR: {ae.name} (slug: {ae.slug})\n{ae_context}"

    full_context = context + extra_context

    # Add action result to context if applicable
    if action_taken == "refreshed":
        full_context += "\n\n## ACTION JUST TAKEN\nA full investigation refresh was just completed. All data above is now fresh from FEC, Congress.gov, and Senate LDA. Summarize what changed or what the new data shows."
    elif action_taken == "regenerated_briefing":
        full_context += "\n\n## ACTION JUST TAKEN\nThe AI briefing was just regenerated with the latest data. The briefing above is brand new."
    elif action_taken and "failed" in action_taken:
        full_context += f"\n\n## ACTION ATTEMPTED BUT FAILED\n{action_taken}"

    # 5. Build system prompt
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        entity_name=entity.name,
        context=full_context,
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
            max_tokens=2000,
            system=system_prompt,
            messages=messages,
        )
        reply = response.content[0].text if response.content else "No response generated."
    except Exception as e:
        logger.error("Chat API error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")

    return ChatResponse(reply=reply, sources=[], action_taken=action_taken)
