from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import ConfigEntryResponse, ConfigSetRequest
from app.services import config_service

router = APIRouter(prefix="/config", tags=["config"])


@router.get("", response_model=list[ConfigEntryResponse])
async def list_config(db: AsyncSession = Depends(get_db)):
    return await config_service.get_all_config(db)


@router.post("/{key}")
async def set_config(
    key: str, body: ConfigSetRequest, db: AsyncSession = Depends(get_db)
):
    if key not in config_service.KNOWN_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown config key: {key}")
    await config_service.set_config_value(db, key, body.value)
    return {"status": "ok", "key": key}


@router.delete("/{key}")
async def clear_config(key: str, db: AsyncSession = Depends(get_db)):
    if key not in config_service.KNOWN_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown config key: {key}")
    deleted = await config_service.delete_config_value(db, key)
    return {
        "status": "ok",
        "key": key,
        "was_set": deleted,
    }


@router.get("/{key}/test")
async def test_config(key: str, db: AsyncSession = Depends(get_db)):
    if key not in config_service.KNOWN_KEYS:
        raise HTTPException(status_code=404, detail=f"Unknown config key: {key}")
    value = await config_service.get_config_value(db, key)
    return {
        "key": key,
        "is_set": value is not None,
    }
