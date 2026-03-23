"""
FBI Special Agent Briefing Generator.
Generates investigative briefings for every entity type using Claude CLI.
"""

import json
import os
import subprocess
from typing import Optional

try:
    import anthropic
except ImportError:
    anthropic = None

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entity, Relationship


def _sanitize(s: str) -> str:
    return s.encode("ascii", errors="ignore").decode("ascii") if s else ""


async def _gather_entity_context(session: AsyncSession, entity: Entity) -> dict:
    """Gather all relevant data for an entity to feed into the briefing prompt."""
    from sqlalchemy import and_

    # Get all outgoing connections
    from_rels = (
        await session.execute(
            select(Relationship, Entity)
            .join(Entity, Entity.id == Relationship.to_entity_id)
            .where(Relationship.from_entity_id == entity.id)
            .limit(50)
        )
    ).all()

    # Get all incoming connections
    to_rels = (
        await session.execute(
            select(Relationship, Entity)
            .join(Entity, Entity.id == Relationship.from_entity_id)
            .where(Relationship.to_entity_id == entity.id)
            .limit(50)
        )
    ).all()

    # Build evidence chains for persons — trace money → lobbying → vote → outcome
    evidence_chains = []
    if entity.entity_type == "person":
        # Get companies this official holds stock in
        stock_companies = {}
        for rel, connected in from_rels:
            if rel.relationship_type == "holds_stock":
                stock_companies[connected.id] = {
                    "name": _sanitize(connected.name),
                    "slug": connected.slug,
                    "amount": rel.amount_label or "undisclosed",
                }

        # Get donors
        donors = {}
        for rel, connected in to_rels:
            if rel.relationship_type == "donated_to":
                donors[connected.id] = {
                    "name": _sanitize(connected.name),
                    "amount_usd": rel.amount_usd,
                    "amount_label": rel.amount_label,
                }

        # For each stock holding, check if that company lobbied for any bill this official voted on
        for company_id, company_info in stock_companies.items():
            # Find bills this company lobbied for
            lobby_q = await session.execute(
                select(Relationship, Entity)
                .join(Entity, Entity.id == Relationship.to_entity_id)
                .where(and_(
                    Relationship.from_entity_id == company_id,
                    Relationship.relationship_type == "lobbies_on_behalf_of",
                ))
            )
            lobbied_bills = lobby_q.all()

            for lobby_rel, bill_entity in lobbied_bills:
                # Did this official vote on or sponsor this bill?
                vote_q = await session.execute(
                    select(Relationship).where(and_(
                        Relationship.from_entity_id == entity.id,
                        Relationship.to_entity_id == bill_entity.id,
                        Relationship.relationship_type.in_(["voted_yes", "voted_no", "sponsored", "cosponsored"]),
                    ))
                )
                votes = vote_q.scalars().all()
                for vote in votes:
                    evidence_chains.append({
                        "chain": (
                            f"Official holds {company_info['amount']} in {company_info['name']} stock -> "
                            f"{company_info['name']} lobbied for {_sanitize(bill_entity.name)} -> "
                            f"Official {vote.relationship_type.replace('_', ' ')} {_sanitize(bill_entity.name)}"
                        ),
                        "company": company_info["name"],
                        "bill": _sanitize(bill_entity.name),
                        "vote": vote.relationship_type,
                        "stock_amount": company_info["amount"],
                    })

    context = {
        "entity_type": entity.entity_type,
        "name": entity.name,
        "slug": entity.slug,
        "summary": entity.summary or "",
        "metadata": entity.metadata_ or {},
        "outgoing": [
            {
                "type": rel.relationship_type,
                "to": _sanitize(connected.name),
                "to_type": connected.entity_type,
                "amount_label": rel.amount_label,
                "amount_usd": rel.amount_usd,
                "date": str(rel.date_start) if rel.date_start else None,
                "source": rel.source_label,
            }
            for rel, connected in from_rels
        ],
        "incoming": [
            {
                "type": rel.relationship_type,
                "from": _sanitize(connected.name),
                "from_type": connected.entity_type,
                "amount_label": rel.amount_label,
                "amount_usd": rel.amount_usd,
                "date": str(rel.date_start) if rel.date_start else None,
                "source": rel.source_label,
            }
            for rel, connected in to_rels
        ],
        "evidence_chains": evidence_chains,
    }
    return context


def _build_system_prompt(entity_type: str) -> str:
    """Build the system prompt for the FBI analyst persona."""
    base = (
        "You are an FBI Special Agent assigned to the Financial Crimes & Public "
        "Corruption Unit. You write investigative intelligence briefings about "
        "political figures, organizations, and legislation.\n\n"
        "YOUR AUDIENCE: Regular citizens who want to understand where political "
        "money flows. They are NOT lawyers or policy experts. Write so a high "
        "school student could understand every sentence.\n\n"
        "VOICE & TONE:\n"
        "- First-person analyst voice: \"This unit has identified...\", "
        "\"Our analysis of financial records shows...\"\n"
        "- Be direct and concrete. Instead of \"potential conflict of interest\" "
        "say exactly what the conflict IS: \"He sits on the Banking Committee "
        "which regulates JPMorgan, and his wife works at JPMorgan.\"\n"
        "- CONNECT THE DOTS. Don't just list facts -- show HOW they connect. "
        "\"Company X donated $50K to this official. That same company lobbied "
        "for Bill Y. This official voted YES on Bill Y.\"\n"
        "- Use dollar amounts. People understand money.\n"
        "- Name names. Don't say \"several companies\" -- say which ones.\n\n"
        "RULES:\n"
        "- EVERY claim must cite its source (FEC filing, Senate eFD, Congress.gov, "
        "LDA filing, etc.)\n"
        "- Draw investigative conclusions -- what do the patterns SUGGEST?\n"
        "- Do NOT accuse anyone of crimes. Present findings as \"patterns worth "
        "investigating\" and \"questions the public should ask.\"\n"
        "- Be specific: dollar amounts, dates, company names, bill numbers.\n\n"
        "FORMAT (follow exactly):\n"
        "KEY FINDINGS:\n"
        "- [3-5 bullet points. Each one should connect dots, not just state a "
        "single fact. Bad: \"Holds stock in JPMorgan.\" Good: \"Holds $1K-$15K "
        "in JPMorgan stock while sitting on the Banking Committee that regulates "
        "JPMorgan -- and his wife earns $185K/year from JPMorgan.\"]\n\n"
        "[2 narrative paragraphs. First paragraph: follow the money -- trace the "
        "flow of dollars from donors through committees to legislation. Second "
        "paragraph: the hidden connections -- family income, revolving door "
        "lobbyists, suspicious timing.]\n\n"
        "INVESTIGATIVE ASSESSMENT:\n"
        "[1 paragraph: What questions should the public be asking? What warrants "
        "further investigation? What would you look at next if this were a real "
        "case? End with a clear, plain-English summary of the overall concern "
        "level.]"
    )

    type_specific = {
        "person": (
            "\n\nFOR THIS OFFICIAL, CONNECT THESE DOTS:\n"
            "1. MONEY IN: Who donates to them? What industries? How much?\n"
            "2. MONEY OUT: What stocks do they hold? Where does their family work?\n"
            "3. POWER: What committees do they sit on? What do those committees regulate?\n"
            "4. VOTES: Did they vote in ways that benefit their donors or their stock portfolio?\n"
            "5. THE QUESTION: Could their financial interests be influencing their votes?\n"
            "\nIf their spouse works at a bank, and they sit on the Banking Committee, "
            "and that bank donated to their campaign -- SAY THAT CLEARLY."
        ),
        "company": (
            "\n\nFOR THIS COMPANY, CONNECT THESE DOTS:\n"
            "1. Which officials hold stock in this company?\n"
            "2. Did this company donate to officials who sit on committees that regulate it?\n"
            "3. Did this company lobby for specific bills? Did those bills pass?\n"
            "4. Did officials who hold this stock vote YES on bills the company lobbied for?\n"
            "5. THE QUESTION: Is this company buying political influence?"
        ),
        "organization": (
            "\n\nFOR THIS ORGANIZATION, CONNECT THESE DOTS:\n"
            "1. Who do they fund? How much?\n"
            "2. What committees do their recipients sit on?\n"
            "3. What policy outcomes would benefit this organization?\n"
            "4. Did their recipients vote in ways that benefit this organization?\n"
            "5. THE QUESTION: What are they getting for their money?"
        ),
        "bill": (
            "\n\nFOR THIS BILL, FOLLOW THE MONEY:\n"
            "1. Who voted YES? Who voted NO?\n"
            "2. What industries benefit from this bill passing?\n"
            "3. Did those industries donate to the YES voters?\n"
            "4. Did companies lobby for this bill? Which ones?\n"
            "5. Do any YES voters hold stock in companies that benefit?\n"
            "6. THE QUESTION: Was this bill's passage influenced by money?"
        ),
        "committee": (
            "\n\nFOR THIS COMMITTEE, FIND THE CONFLICTS:\n"
            "1. What industries does this committee regulate?\n"
            "2. Do any members hold stock in companies they regulate?\n"
            "3. Do any members receive donations from industries they oversee?\n"
            "4. Are there revolving door lobbyists who used to work here?\n"
            "5. THE QUESTION: Can this committee be objective when its members "
            "have financial ties to the industries they oversee?"
        ),
        "industry": (
            "\n\nFOR THIS INDUSTRY, TRACE THE INFLUENCE:\n"
            "1. How much does this industry spend on political donations?\n"
            "2. Which officials receive the most from this industry?\n"
            "3. Do those officials sit on committees relevant to this industry?\n"
            "4. What legislation benefits this industry? Who voted for it?\n"
            "5. THE QUESTION: Is this industry getting favorable treatment for its money?"
        ),
    }

    return base + type_specific.get(entity_type, "")


def _build_briefing_prompt(context: dict) -> str:
    """Build the data prompt with all entity context."""
    entity_type = context["entity_type"]
    name = _sanitize(context["name"])

    prompt = (
        "Generate an FBI Financial Crimes & Public Corruption Unit intelligence "
        "briefing for the following subject.\n\n"
        "CRITICAL: Start DIRECTLY with 'KEY FINDINGS:' — do NOT include any "
        "preamble, introduction, 'here is the briefing', or meta-commentary. "
        "Do NOT include SUBJECT/CLASSIFICATION/PREPARED BY lines (the UI adds those). "
        "Do NOT use markdown links like [text](url) — just name the source in "
        "parentheses like (Source: OpenSecrets FEC filings). "
        "Do NOT use markdown headers like ## — just use the section names.\n\n"
        "FORMAT (follow exactly, start with KEY FINDINGS):\n\n"
        "KEY FINDINGS:\n"
        "* [3-5 bullet points. Each one CONNECTS DOTS, not just states a fact.]\n\n"
        "[2 narrative paragraphs. First: follow the money. Second: hidden connections.]\n\n"
        "INVESTIGATIVE ASSESSMENT:\n"
        "[1 paragraph with the agent's conclusion and recommended investigation]\n\n"
        "---\n"
        "ENTITY DATA:\n"
        f"Type: {entity_type}\n"
        f"Name: {name}\n"
        f"Summary: {_sanitize(context.get('summary', 'N/A'))}\n\n"
        f"Metadata: {json.dumps(context.get('metadata', {}), default=str)[:2000]}\n\n"
        f"Outgoing relationships ({len(context.get('outgoing', []))}):\n"
    )

    for rel in context.get("outgoing", [])[:30]:
        prompt += f"  - {rel['type']} -> {_sanitize(rel['to'])} ({rel['to_type']})"
        if rel.get("amount_label"):
            prompt += f" [{rel['amount_label']}]"
        if rel.get("source"):
            prompt += f" (Source: {rel['source']})"
        prompt += "\n"

    prompt += f"\nIncoming relationships ({len(context.get('incoming', []))}):\n"
    for rel in context.get("incoming", [])[:30]:
        prompt += (
            f"  - {_sanitize(rel['from'])} ({rel['from_type']}) -> {rel['type']}"
        )
        if rel.get("amount_label"):
            prompt += f" [{rel['amount_label']}]"
        if rel.get("source"):
            prompt += f" (Source: {rel['source']})"
        prompt += "\n"

    # Evidence chains — the connected dots
    chains = context.get("evidence_chains", [])
    if chains:
        prompt += (
            f"\n\n*** CRITICAL: EVIDENCE CHAINS ({len(chains)} found) ***\n"
            "These are PROVEN connections from our database. Each chain traces:\n"
            "Official holds stock -> Company lobbied for bill -> Official voted on bill\n"
            "You MUST reference these chains in your briefing. These are the dots connected.\n\n"
        )
        for i, chain in enumerate(chains, 1):
            prompt += f"  Chain {i}: {chain['chain']}\n"

    return prompt


def _generate_via_sdk(system_prompt: str, data_prompt: str) -> Optional[str]:
    """Try Anthropic SDK if API key is available."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key or not anthropic:
        return None
    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": data_prompt}],
        )
        return _sanitize(message.content[0].text)
    except Exception as e:
        print(f"[AIService] SDK error: {e}")
        return None


def _generate_via_cli(system_prompt: str, data_prompt: str) -> Optional[str]:
    """Fall back to claude CLI (uses existing auth token)."""
    full_prompt = f"{system_prompt}\n\n{data_prompt}"
    try:
        result = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions", full_prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return _sanitize(result.stdout.strip())
        print(f"[AIService] CLI returned code {result.returncode}: {result.stderr[:200]}")
        return None
    except Exception as e:
        print(f"[AIService] CLI error: {e}")
        return None


def _clean_briefing(text: str) -> str:
    """Strip AI preamble and meta-commentary from briefing output."""
    import re
    # Find where the actual briefing starts (KEY FINDINGS or first bullet)
    markers = ["KEY FINDINGS", "* **", "- **"]
    for marker in markers:
        idx = text.find(marker)
        if idx > 0:
            # Check if there's preamble before the marker
            preamble = text[:idx].strip()
            if preamble and not preamble.upper().startswith("KEY"):
                text = text[idx:]
            break

    # Strip markdown-style headers (## ) — the UI handles section styling
    text = re.sub(r'^##\s+', '', text, flags=re.MULTILINE)

    # Strip SUBJECT/CLASSIFICATION/PREPARED BY/DATE lines (UI adds these)
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        upper = line.strip().upper()
        if upper.startswith('**SUBJECT:') or upper.startswith('SUBJECT:'):
            continue
        if upper.startswith('**CLASSIFICATION') or upper.startswith('CLASSIFICATION:'):
            continue
        if upper.startswith('**PREPARED BY') or upper.startswith('PREPARED BY:'):
            continue
        if upper.startswith('**DATE:') or upper.startswith('DATE:'):
            continue
        if line.strip() == '---':
            continue
        cleaned.append(line)

    return '\n'.join(cleaned).strip()


def _generate_via_claude(system_prompt: str, data_prompt: str) -> str:
    """Generate briefing via SDK (preferred) or CLI (fallback)."""
    # Try SDK first
    result = _generate_via_sdk(system_prompt, data_prompt)
    if result:
        return _clean_briefing(result)

    # Fall back to CLI
    result = _generate_via_cli(system_prompt, data_prompt)
    if result:
        return _clean_briefing(result)

    return _generate_fallback_briefing(data_prompt)


def _generate_fallback_briefing(data_prompt: str) -> str:
    """Fallback when Claude CLI is unavailable."""
    return (
        "BRIEFING GENERATION UNAVAILABLE\n\n"
        "The AI briefing service is currently offline. "
        "Raw entity data is available through the profile tabs."
    )


def _compute_data_fingerprint(context: dict) -> str:
    """Create a hash of entity relationships so we know when data changes."""
    import hashlib
    # Build a stable string from the relationship data
    parts = []
    for rel in sorted(context.get("outgoing", []), key=lambda r: (r["type"], r["to"])):
        parts.append(f'{rel["type"]}:{rel["to"]}:{rel.get("amount_usd","")}')
    for rel in sorted(context.get("incoming", []), key=lambda r: (r["type"], r["from"])):
        parts.append(f'{rel["type"]}:{rel["from"]}:{rel.get("amount_usd","")}')
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:12]


class AIBriefingService:
    async def generate_briefing(
        self,
        entity_slug: str,
        context_data: dict,
        session: Optional[AsyncSession] = None,
        force_refresh: bool = False,
    ) -> str:
        """Generate an FBI-style briefing for any entity.

        Caching strategy:
        1. Generate briefing on first request, cache in entity metadata
        2. On subsequent requests, serve cached version instantly
        3. If entity's relationships have changed (new donors, votes, etc),
           auto-regenerate because the data fingerprint won't match
        4. ?refresh=true forces regeneration regardless
        """
        if not session:
            return "Session required for briefing generation."

        # Get entity
        result = await session.execute(
            select(Entity).where(Entity.slug == entity_slug)
        )
        entity = result.scalar_one_or_none()
        if not entity:
            return "Entity not found."

        # Fast path: return cached briefing immediately (no DB queries beyond entity lookup)
        if not force_refresh:
            cached = (entity.metadata_ or {}).get("fbi_briefing")
            if cached:
                return cached

        # Slow path: gather context and generate (only on first visit or force refresh)
        context = await _gather_entity_context(session, entity)
        current_fingerprint = _compute_data_fingerprint(context)

        # On force_refresh, check if data actually changed — skip regen if not
        if force_refresh:
            cached = (entity.metadata_ or {}).get("fbi_briefing")
            cached_fingerprint = (entity.metadata_ or {}).get("fbi_briefing_fingerprint")
            if cached and cached_fingerprint == current_fingerprint:
                return cached

        # Generate via AI
        system_prompt = _build_system_prompt(entity.entity_type)
        data_prompt = _build_briefing_prompt(context)

        briefing = _generate_via_claude(system_prompt, data_prompt)

        # If AI failed, fall back to cached or mock briefing
        if briefing.startswith("BRIEFING GENERATION UNAVAILABLE"):
            cached = (entity.metadata_ or {}).get("fbi_briefing")
            if cached:
                return cached
            mock = (entity.metadata_ or {}).get("mock_briefing")
            if mock and len(mock) > 200:
                return mock
            return briefing

        # Cache briefing + fingerprint in metadata
        try:
            entity.metadata_ = {
                **(entity.metadata_ or {}),
                "fbi_briefing": briefing,
                "fbi_briefing_fingerprint": current_fingerprint,
            }
            await session.commit()
        except Exception:
            pass

        return briefing


ai_briefing_service = AIBriefingService()
