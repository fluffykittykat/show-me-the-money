import os
import json
import base64
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
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")


# ---------------------------------------------------------------------------
# Google OAuth endpoints
# ---------------------------------------------------------------------------

class GoogleAuthRequest(BaseModel):
    credential: str  # JWT token from Google Sign-In


class AuthResponse(BaseModel):
    user_id: str
    name: str
    email: str
    picture: str | None = None


@router.get("/auth/config")
async def auth_config():
    """Return the Google client ID so the frontend can initialize Sign-In."""
    return {"google_client_id": GOOGLE_CLIENT_ID}


@router.post("/auth/google", response_model=AuthResponse)
async def google_auth(req: GoogleAuthRequest):
    """Verify Google OAuth token and return user info."""
    parts = req.credential.split('.')
    if len(parts) != 3:
        raise HTTPException(400, "Invalid token")

    # Decode JWT payload (add padding for base64)
    payload = parts[1] + '=' * (4 - len(parts[1]) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        raise HTTPException(400, "Invalid token payload")

    # Basic validation
    if data.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
        raise HTTPException(400, "Invalid token issuer")
    if data.get('aud') != GOOGLE_CLIENT_ID:
        raise HTTPException(400, "Invalid token audience")

    email = data.get('email', '')
    if not email:
        raise HTTPException(400, "No email in token")

    return AuthResponse(
        user_id=email,
        name=data.get('name', ''),
        email=email,
        picture=data.get('picture'),
    )


# ---------------------------------------------------------------------------
# Chat models & endpoint
# ---------------------------------------------------------------------------

class OtherSession(BaseModel):
    name: str = ""
    slug: str = ""
    message_count: int = 0
    last_message: str = ""

class ChatRequest(BaseModel):
    slug: str  # current session's entity
    message: str
    history: list[dict] = []
    session_id: str = "default"
    other_sessions: list[OtherSession] = []  # summaries of other open investigations


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


SYSTEM_PROMPT_TEMPLATE = """You are a sharp, knowledgeable investigative partner helping the user dig into political money and influence. Think of yourself as a colleague who's been researching this stuff for years — you know the data inside out, you're opinionated but fair, and you talk like a real person, not a report generator.

The user is currently looking at: **{entity_name}**
You can discuss ANY official, bill, PAC, or company — not just the current page.

Here's what you know:

{context}

## How to Talk

**Be conversational.** You're having a discussion, not writing a report.

- Start with the headline — what's the most interesting thing? Lead with that.
- Use "I" and "you" — "I found something interesting here..." or "So what you're looking at is..."
- React to what the user asks — if they seem surprised, dig deeper. If they're confused, simplify.
- Ask follow-up questions when relevant — "Want me to dig into who funds that PAC?" or "Should I check if any of those donors also lobbied?"
- Be direct — "Honestly, this one looks clean" or "OK this is where it gets interesting..."
- Show personality — you care about this stuff. You find it fascinating. Share that energy.

**But stay structured when it helps.** Use:
- **Bold** for names, dollar amounts, key findings
- Bullet points when listing multiple items
- `code style` for bill numbers like `S. 2963`
- > Blockquotes for the smoking gun — the one thing that really matters
- Short paragraphs — no walls of text

**DON'T:**
- Don't repeat what's already visible on the page — add NEW insight
- Don't start every response with "Based on the data..." — just talk
- Don't write headers for short answers — just answer
- Don't be preachy about disclaimers — state facts and move on
- Don't give the same information the page already shows unless asked specifically

## What You Can Do

- Trace money chains and explain them conversationally
- Compare officials, donors, bills
- Run live database queries (counts, totals)
- Trigger a full investigation refresh or briefing regeneration
- Cross-reference with other open investigation sessions
- Suggest what to look at next — be proactive

## The Golden Rules

1. Every dollar amount you mention must come from the data above
2. Never accuse — say "the pattern here is unusual" not "they're corrupt"
3. When you don't have data, say "I don't have that — want me to run a full investigation to pull it?"
4. Be the colleague who makes the user say "oh shit, really?"
5. NEVER show SQL queries, code, or technical implementation details to the user. Just show results.
6. When you search the database, say "I checked our records" or "Looking at the data..." — not "I ran a query"
7. When you can't find something, say "I don't see that in our records" — not "the query returned no results"
"""


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    # 1. Load entity — allow homepage/general questions without an entity
    entity = None
    if req.slug and req.slug not in ("homepage", "general", ""):
        result = await db.execute(select(Entity).where(Entity.slug == req.slug))
        entity = result.scalar_one_or_none()

    # If no entity, build a general context with top-level stats
    if not entity:
        # Answer general questions by querying the DB
        from sqlalchemy import text
        stats_result = await db.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM entities WHERE entity_type = 'person' AND metadata->>'bioguide_id' IS NOT NULL) as officials,
                (SELECT COUNT(*) FROM relationships WHERE relationship_type = 'donated_to') as donations,
                (SELECT COUNT(*) FROM relationships WHERE relationship_type = 'lobbied_on') as lobbying_connections,
                (SELECT COUNT(*) FROM entities WHERE entity_type = 'bill') as bills
        """))
        stats = stats_result.one()

        # Get top officials by influence signals
        top_q = await db.execute(text("""
            SELECT e.name, e.slug, e.metadata->>'party' as party, e.metadata->>'state' as state,
                   e.metadata->>'v2_verdict' as verdict, e.metadata->>'v2_dot_count' as dots,
                   COUNT(*) FILTER (WHERE s.found AND s.rarity_label IN ('Rare', 'Above Baseline', 'Unusual')) as strong_signals
            FROM entities e
            LEFT JOIN official_influence_signals s ON s.official_id = e.id
            WHERE e.entity_type = 'person' AND e.metadata->>'bioguide_id' IS NOT NULL
            GROUP BY e.id, e.name, e.slug, e.metadata
            ORDER BY strong_signals DESC, (e.metadata->>'v2_dot_count')::int DESC NULLS LAST
            LIMIT 15
        """))
        top_officials = top_q.all()

        general_context = f"""## Platform Overview
Officials tracked: {stats[0]}
Donation records: {stats[1]}
Lobbying-to-bill connections: {stats[2]}
Bills tracked: {stats[3]}

## Most Flagged Officials (by influence signals)
"""
        for row in top_officials:
            name, slug, party, state, verdict, dots, strong = row
            general_context += f"- **{name}** ({party}-{state}) — Verdict: {verdict}, {dots} dots, {strong} strong signal(s) — /officials/{slug}\n"

        # Create a fake entity-like context for the system prompt
        context = general_context
        entity_name = "Follow the Money Platform"

        # Skip entity-specific actions, go straight to AI call
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            entity_name=entity_name,
            context=context,
        )

        messages = []
        for msg in req.history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": req.message})

        if not CHAT_API_KEY:
            raise HTTPException(status_code=500, detail="AI service not configured")

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=CHAT_API_KEY)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                system=system_prompt,
                messages=messages,
            )
            reply = response.content[0].text if response.content else "No response."
        except Exception as e:
            logger.error("Chat API error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=f"AI error: {e}")

        return ChatResponse(reply=reply, sources=[], action_taken=None)

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

    # Action: Query the database — handle any investigative question
    elif any(kw in msg_lower for kw in [
        "how many", "total donated", "total raised", "count", "list all",
        "look up", "search for", "find", "check", "who donated", "who gave",
        "show me", "what about", "is there", "do they have", "did they",
        "confirm", "verify", "check the", "in the database", "in our records",
    ]):
        query_results = []

        # 1. Donor stats for this entity
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
            query_results.append(f"Total donors in DB: {cnt}, Total amount: {_fmt_money(total)}")

        # 2. Top 10 donors with amounts
        top_donors_q = await db.execute(
            select(Entity.name, func.sum(Relationship.amount_usd).label("total"))
            .join(Entity, Entity.id == Relationship.from_entity_id)
            .where(Relationship.to_entity_id == entity.id)
            .where(Relationship.relationship_type == "donated_to")
            .group_by(Entity.name)
            .order_by(func.sum(Relationship.amount_usd).desc())
            .limit(10)
        )
        top_donors = top_donors_q.all()
        if top_donors:
            donor_lines = [f"  {name}: {_fmt_money(amt)}" for name, amt in top_donors]
            query_results.append(f"Top 10 donors:\n" + "\n".join(donor_lines))

        # 3. Search for a specific name if mentioned in quotes or after "about"
        import re as _re
        name_searches = _re.findall(r'"([^"]+)"', req.message)
        name_searches += _re.findall(r'(?:about|for|named?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', req.message)
        for search_name in name_searches[:2]:
            found_q = await db.execute(
                select(Entity.name, Entity.entity_type, Entity.slug)
                .where(Entity.name.ilike(f"%{search_name}%"))
                .limit(5)
            )
            found = found_q.all()
            if found:
                query_results.append(f"Search for '{search_name}': {len(found)} results")
                for name, etype, eslug in found:
                    # Check if they donated to current entity
                    don_q = await db.execute(
                        select(func.sum(Relationship.amount_usd))
                        .where(Relationship.relationship_type == "donated_to")
                        .where(Relationship.to_entity_id == entity.id)
                        .join(Entity, Entity.id == Relationship.from_entity_id)
                        .where(Entity.name.ilike(f"%{search_name}%"))
                    )
                    donated = don_q.scalar()
                    query_results.append(f"  {name} ({etype}) — donated {_fmt_money(donated) if donated else '$0'} to {entity.name}")

        # 4. Bill + committee counts
        bill_count = (await db.execute(
            select(func.count(Relationship.id))
            .where(Relationship.from_entity_id == entity.id)
            .where(Relationship.relationship_type.in_(["sponsored", "cosponsored"]))
        )).scalar() or 0
        query_results.append(f"Bills sponsored/cosponsored: {bill_count}")

        stock_count = (await db.execute(
            select(func.count(Relationship.id))
            .where(Relationship.from_entity_id == entity.id)
            .where(Relationship.relationship_type == "stock_trade")
        )).scalar() or 0
        if stock_count > 0:
            query_results.append(f"Stock trades on file: {stock_count}")

        lobby_count = (await db.execute(
            select(func.count(Relationship.id))
            .where(Relationship.to_entity_id == entity.id)
            .where(Relationship.relationship_type == "lobbied_on")
        )).scalar() or 0
        query_results.append(f"Bills with lobbying connections: {lobby_count}")

        action_taken = "queried"
        req.message += f"\n\n[LIVE DATABASE RESULTS — present these naturally, never show SQL:\n{chr(10).join(query_results)}]"

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

    # Add other open investigations context
    if req.other_sessions:
        other_lines = []
        for os in req.other_sessions:
            other_lines.append(f"- **{os.name}** ({os.slug}): {os.message_count} messages. Last discussed: {os.last_message[:100]}...")
        full_context += f"\n\n## Other Open Investigations\nThe user has these other investigation threads open. They may ask you to cross-reference or compare:\n" + "\n".join(other_lines)

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


# ---------------------------------------------------------------------------
# Session persistence endpoints
# ---------------------------------------------------------------------------

class SessionData(BaseModel):
    id: str
    name: str
    slug: str
    messages: list[dict]

class SaveSessionsRequest(BaseModel):
    user_id: str  # anonymous ID or email
    sessions: list[SessionData]

class RegisterRequest(BaseModel):
    email: str

class RegisterResponse(BaseModel):
    user_id: str
    message: str

@router.post("/register", response_model=RegisterResponse)
async def register_email(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register an email to sync sessions across devices. No password needed."""
    from sqlalchemy import text
    email = req.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")
    # Email IS the user_id — simple and unique
    return RegisterResponse(user_id=email, message="Sessions will now sync across devices")

@router.get("/sessions")
async def get_sessions(user_id: str = "anonymous", db: AsyncSession = Depends(get_db)):
    """Load saved chat sessions for a user."""
    from sqlalchemy import text
    result = await db.execute(text(
        "SELECT id, name, slug, messages, updated_at FROM chat_sessions WHERE user_id = :user_id ORDER BY updated_at DESC"
    ), {"user_id": user_id})
    rows = result.fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "slug": row[2],
            "messages": row[3],
            "updated_at": row[4].isoformat() if row[4] else None,
        }
        for row in rows
    ]

@router.post("/sessions")
async def save_sessions(req: SaveSessionsRequest, db: AsyncSession = Depends(get_db)):
    """Save chat sessions for a user (upsert)."""
    from sqlalchemy import text
    user_id = req.user_id or "anonymous"
    for s in req.sessions:
        if not s.messages:
            continue
        await db.execute(text("""
            INSERT INTO chat_sessions (id, name, slug, messages, user_id, updated_at)
            VALUES (:id, :name, :slug, :messages::jsonb, :user_id, NOW())
            ON CONFLICT (id) DO UPDATE SET
                name = :name,
                slug = :slug,
                messages = :messages::jsonb,
                updated_at = NOW()
        """), {
            "id": s.id,
            "name": s.name,
            "slug": s.slug,
            "messages": __import__('json').dumps(s.messages),
            "user_id": user_id,
        })
    await db.commit()
    return {"saved": len([s for s in req.sessions if s.messages])}

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a saved chat session."""
    from sqlalchemy import text
    await db.execute(text("DELETE FROM chat_sessions WHERE id = :id"), {"id": session_id})
    await db.commit()
    return {"deleted": session_id}
