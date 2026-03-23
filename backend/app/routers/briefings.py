from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Entity
from app.schemas import BriefingResponse
from app.services.ai_service import ai_briefing_service

router = APIRouter(tags=["briefings"])


@router.get("/entities/{slug}/briefing", response_model=BriefingResponse)
async def get_entity_briefing(
    slug: str,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    briefing_text = await ai_briefing_service.generate_briefing(
        entity_slug=slug,
        context_data={"metadata": entity.metadata_},
        session=db,
        force_refresh=refresh,
    )

    return BriefingResponse(
        entity_slug=entity.slug,
        entity_name=entity.name,
        briefing_text=briefing_text,
        generated_at=None,
    )
