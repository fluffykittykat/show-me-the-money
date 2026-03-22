from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.config_service import get_config_value


class AIBriefingService:
    async def generate_briefing(
        self,
        entity_slug: str,
        context_data: dict,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """
        Generate an AI briefing for an entity.

        Config plumbing is in place — when ready to wire to Anthropic Claude API,
        use: api_key = await get_config_value(session, "ANTHROPIC_API_KEY")

        For now: return pre-written mock briefing from DB metadata.
        """
        if session:
            _api_key = await get_config_value(session, "ANTHROPIC_API_KEY")
            # TODO: Use api_key to call Anthropic Claude API when ready

        return context_data.get("metadata", {}).get(
            "mock_briefing", "Briefing not available."
        )


ai_briefing_service = AIBriefingService()
