"""
FBI Special Agent Briefing Generator.
Generates investigative briefings for every entity type using Claude CLI.
"""

import json
import os
from typing import Optional

import anthropic

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entity, Relationship


def _sanitize(s: str) -> str:
    return s.encode("ascii", errors="ignore").decode("ascii") if s else ""


async def _gather_entity_context(session: AsyncSession, entity: Entity) -> dict:
    """Gather all relevant data for an entity to feed into the briefing prompt."""
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
    }
    return context


def _build_system_prompt(entity_type: str) -> str:
    """Build the system prompt for the FBI analyst persona."""
    base = (
        "You are an FBI Special Agent assigned to the Financial Crimes & Public "
        "Corruption Unit. You write investigative intelligence briefings about "
        "political figures, organizations, and legislation.\n\n"
        "RULES:\n"
        "- Write in first-person analyst voice: \"This unit has identified...\", "
        "\"Analysis of financial records indicates...\"\n"
        "- EVERY claim must cite a source (FEC filing, Senate eFD, Congress.gov "
        "vote record, etc.)\n"
        "- Include analytical conclusions -- interpret the facts, identify patterns, "
        "flag conflicts of interest\n"
        "- Be factual but draw investigative conclusions about what the patterns "
        "suggest\n"
        "- Do NOT be accusatory -- present findings as warranting further "
        "investigation\n"
        "- Keep it concise: KEY FINDINGS (3-5 bullets) + 2 narrative paragraphs + "
        "INVESTIGATIVE ASSESSMENT (1 paragraph)"
    )

    type_specific = {
        "person": (
            "\nFocus on: financial conflicts of interest, donation patterns, "
            "voting record alignment with donor interests, stock holdings vs "
            "committee assignments, suspicious timing of donations before votes."
        ),
        "company": (
            "\nFocus on: which officials hold stock in this company, how much "
            "political money flows from this company's industry, any legislation "
            "that benefits this company, lobbying connections."
        ),
        "organization": (
            "\nFocus on: political strategy -- who they fund and why, what policy "
            "outcomes they appear to be purchasing, which committees their "
            "recipients sit on, legislative influence."
        ),
        "bill": (
            "\nFocus on: who benefits from this legislation, money trail to YES "
            "voters, whether donor activity suggests the bill's passage was "
            "influenced, industry lobbying connections."
        ),
        "committee": (
            "\nFocus on: whether jurisdiction creates conflicts for any members, "
            "overlap between committee oversight industries and member financial "
            "interests/donors."
        ),
        "industry": (
            "\nFocus on: total political spending, which officials receive the "
            "most, committee assignments of recipients, legislative outcomes "
            "favorable to the industry."
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
        "FORMAT (follow exactly):\n"
        f"SUBJECT: {name}\n"
        "CLASSIFICATION: UNCLASSIFIED // FOR OFFICIAL USE ONLY\n"
        "PREPARED BY: Financial Crimes & Public Corruption Unit\n\n"
        "KEY FINDINGS:\n"
        "* [3-5 bullet points of the most important findings]\n\n"
        "[2 narrative paragraphs analyzing the data]\n\n"
        "INVESTIGATIVE ASSESSMENT:\n"
        "[1 paragraph with the agent's opinion, conclusion, key questions raised, "
        "and recommended further investigation]\n\n"
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

    return prompt


def _generate_via_claude(system_prompt: str, data_prompt: str) -> str:
    """Call Anthropic API to generate the briefing."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _generate_fallback_briefing(data_prompt)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            system=system_prompt,
            messages=[{"role": "user", "content": data_prompt}],
        )
        text = message.content[0].text
        return _sanitize(text)
    except Exception as e:
        print(f"[AIService] Anthropic SDK error: {e}")
        return _generate_fallback_briefing(data_prompt)


def _generate_fallback_briefing(data_prompt: str) -> str:
    """Fallback when Claude CLI is unavailable."""
    return (
        "BRIEFING GENERATION UNAVAILABLE\n\n"
        "The AI briefing service is currently offline. "
        "Raw entity data is available through the profile tabs."
    )


class AIBriefingService:
    async def generate_briefing(
        self,
        entity_slug: str,
        context_data: dict,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """Generate an FBI-style briefing for any entity."""
        if not session:
            return "Session required for briefing generation."

        # Get entity
        result = await session.execute(
            select(Entity).where(Entity.slug == entity_slug)
        )
        entity = result.scalar_one_or_none()
        if not entity:
            return "Entity not found."

        # Check if briefing is cached in metadata
        cached = (entity.metadata_ or {}).get("fbi_briefing")
        if cached:
            return cached

        # Check for old mock briefing as fallback
        mock = (entity.metadata_ or {}).get("mock_briefing")
        if mock and len(mock) > 200:
            return mock

        # Gather context and generate
        context = await _gather_entity_context(session, entity)
        system_prompt = _build_system_prompt(entity.entity_type)
        data_prompt = _build_briefing_prompt(context)

        briefing = _generate_via_claude(system_prompt, data_prompt)

        # Cache in metadata (non-blocking, best effort)
        try:
            entity.metadata_ = {**(entity.metadata_ or {}), "fbi_briefing": briefing}
            await session.commit()
        except Exception:
            pass  # Don't fail if caching fails

        return briefing


ai_briefing_service = AIBriefingService()
