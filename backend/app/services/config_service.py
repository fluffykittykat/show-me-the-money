"""
Config service: reads from DB first, falls back to env vars.
Never returns raw secret values through the API — masked only.
"""

import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppConfig

# TODO: Add encryption at rest for secret values (future enhancement)

KNOWN_KEYS: dict[str, dict] = {
    "ANTHROPIC_API_KEY": {
        "description": "Anthropic Claude API key for AI briefing generation",
        "is_secret": True,
        "env_fallback": "ANTHROPIC_API_KEY",
    },
    "CONGRESS_GOV_API_KEY": {
        "description": "Congress.gov API key (api.congress.gov/sign-up)",
        "is_secret": True,
        "env_fallback": "CONGRESS_GOV_API_KEY",
    },
    "FEC_API_KEY": {
        "description": "FEC Open Data API key (api.data.gov/signup)",
        "is_secret": True,
        "env_fallback": "FEC_API_KEY",
    },
    "OPENSECRETS_API_KEY": {
        "description": "OpenSecrets API key (opensecrets.org/api)",
        "is_secret": True,
        "env_fallback": "OPENSECRETS_API_KEY",
    },
    "CONGRESS_GOV_BASE_URL": {
        "description": "Congress.gov API base URL",
        "is_secret": False,
        "default": "https://api.congress.gov/v3",
        "env_fallback": "CONGRESS_GOV_BASE_URL",
    },
    "FEC_BASE_URL": {
        "description": "FEC API base URL",
        "is_secret": False,
        "default": "https://api.open.fec.gov/v1",
        "env_fallback": "FEC_BASE_URL",
    },
    "OPENSECRETS_BASE_URL": {
        "description": "OpenSecrets API base URL",
        "is_secret": False,
        "default": "https://www.opensecrets.org/api",
        "env_fallback": "OPENSECRETS_BASE_URL",
    },
}


def _mask_value(value: str) -> str:
    """Mask a secret value, showing only last 4 chars."""
    if len(value) <= 4:
        return "****"
    return f"****...{value[-4:]}"


async def get_config_value(session: AsyncSession, key: str) -> Optional[str]:
    """Get config value: DB first, then env var, then default."""
    # Check DB
    result = await session.execute(
        select(AppConfig.value).where(AppConfig.key == key)
    )
    db_value = result.scalar_one_or_none()
    if db_value is not None:
        return db_value

    # Check env var
    key_info = KNOWN_KEYS.get(key, {})
    env_key = key_info.get("env_fallback", key)
    env_value = os.getenv(env_key)
    if env_value:
        return env_value

    # Return default if available
    return key_info.get("default")


async def set_config_value(session: AsyncSession, key: str, value: str) -> None:
    """Set/update a config value in the DB."""
    key_info = KNOWN_KEYS.get(key)
    if key_info is None:
        raise ValueError(f"Unknown config key: {key}")

    result = await session.execute(
        select(AppConfig).where(AppConfig.key == key)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.value = value
    else:
        entry = AppConfig(
            key=key,
            value=value,
            description=key_info["description"],
            is_secret=key_info["is_secret"],
        )
        session.add(entry)

    await session.commit()


async def delete_config_value(session: AsyncSession, key: str) -> bool:
    """Delete a config value from DB (falls back to env var)."""
    result = await session.execute(
        select(AppConfig).where(AppConfig.key == key)
    )
    existing = result.scalar_one_or_none()
    if existing:
        await session.delete(existing)
        await session.commit()
        return True
    return False


async def get_all_config(session: AsyncSession) -> list[dict]:
    """Return all config entries with masked values and source info."""
    # Fetch all DB entries
    result = await session.execute(select(AppConfig))
    db_entries = {row.key: row for row in result.scalars().all()}

    configs = []
    for key, info in KNOWN_KEYS.items():
        db_entry = db_entries.get(key)
        env_key = info.get("env_fallback", key)
        env_value = os.getenv(env_key)
        default_value = info.get("default")

        # Determine source and value
        if db_entry and db_entry.value is not None:
            source = "database"
            raw_value = db_entry.value
            is_configured = True
        elif env_value:
            source = "env_var"
            raw_value = env_value
            is_configured = True
        elif default_value:
            source = "default"
            raw_value = default_value
            is_configured = True
        else:
            source = "not_set"
            raw_value = None
            is_configured = False

        # Mask secret values
        if raw_value and info["is_secret"]:
            masked_value = _mask_value(raw_value)
        elif raw_value and not info["is_secret"]:
            masked_value = raw_value
        else:
            masked_value = None

        configs.append({
            "key": key,
            "description": info["description"],
            "is_secret": info["is_secret"],
            "is_configured": is_configured,
            "masked_value": masked_value,
            "source": source,
        })

    return configs
