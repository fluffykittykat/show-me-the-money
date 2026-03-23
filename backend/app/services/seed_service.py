"""
Seed service: loads realistic mock data into the database.

Can be run as a module:
    python -m app.services.seed_service
"""

import asyncio
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, engine
from app.models import Base, DataSource, Entity, Relationship
from app.seed.fetterman import get_all_seed_data


def _parse_date(d):
    if d is None:
        return None
    if isinstance(d, date):
        return d
    return date.fromisoformat(d)


async def clear_database(session: AsyncSession):
    """Delete all data from the database."""
    await session.execute(delete(Relationship))
    await session.execute(delete(DataSource))
    await session.execute(delete(Entity))
    await session.commit()


async def seed_database(session: AsyncSession):
    """Seed the database with Fetterman data."""
    data = get_all_seed_data()

    # Create the main Fetterman entity
    fetterman_data = data["fetterman"]
    fetterman = Entity(
        slug=fetterman_data["slug"],
        entity_type=fetterman_data["entity_type"],
        name=fetterman_data["name"],
        summary=fetterman_data["summary"],
        metadata_=fetterman_data["metadata"],
    )
    session.add(fetterman)
    await session.flush()

    # Helper to create related entities and relationships
    async def create_related(items, direction="from_fetterman"):
        for item in items:
            ent_data = item["entity"]
            rel_data = item["relationship"]

            # Check if entity already exists (e.g. Microsoft appears in both holdings and donors)
            result = await session.execute(
                select(Entity).where(Entity.slug == ent_data["slug"])
            )
            entity = result.scalar_one_or_none()
            if not entity:
                entity = Entity(
                    slug=ent_data["slug"],
                    entity_type=ent_data["entity_type"],
                    name=ent_data["name"],
                    summary=ent_data.get("summary"),
                    metadata_=ent_data.get("metadata", {}),
                )
                session.add(entity)
                await session.flush()

            # Create relationship
            if direction == "from_fetterman":
                from_id = fetterman.id
                to_id = entity.id
            else:
                from_id = entity.id
                to_id = fetterman.id

            rel = Relationship(
                from_entity_id=from_id,
                to_entity_id=to_id,
                relationship_type=rel_data["relationship_type"],
                amount_usd=rel_data.get("amount_usd"),
                amount_label=rel_data.get("amount_label"),
                date_start=_parse_date(rel_data.get("date_start")),
                date_end=_parse_date(rel_data.get("date_end")),
                source_url=rel_data.get("source_url"),
                source_label=rel_data.get("source_label"),
                metadata_=rel_data.get("metadata", {}),
            )
            session.add(rel)

    # Holdings: Fetterman -> Company
    await create_related(data["holdings"], direction="from_fetterman")

    # Donors: Donor -> Fetterman
    await create_related(data["donors"], direction="to_fetterman")

    # Bills: Fetterman -> Bill (sponsored)
    await create_related(data["bills"], direction="from_fetterman")

    # Votes: Fetterman -> Bill (voted)
    await create_related(data["votes"], direction="from_fetterman")

    # Committees: Fetterman -> Committee
    await create_related(data["committees"], direction="from_fetterman")

    # Hidden connections — revolving door, family, outside income, contractor donors
    def _ascii_safe(obj):
        """Recursively replace non-ASCII characters to avoid SQL_ASCII DB errors."""
        if isinstance(obj, str):
            return obj.encode("ascii", "replace").decode("ascii")
        if isinstance(obj, dict):
            return {k: _ascii_safe(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_ascii_safe(i) for i in obj]
        return obj

    async def seed_hidden(items, direction="to_fetterman"):
        for item in items:
            ent_data = (item.get("lobbyist") or item.get("entity") or
                        item.get("employer") or item.get("payer") or
                        item.get("contractor") or item.get("company"))
            if not ent_data:
                continue
            result = await session.execute(select(Entity).where(Entity.slug == ent_data["slug"]))
            entity = result.scalar_one_or_none()
            if not entity:
                entity = Entity(
                    slug=ent_data["slug"],
                    entity_type=ent_data.get("entity_type", "person"),
                    name=_ascii_safe(ent_data["name"]),
                    summary=_ascii_safe(ent_data.get("summary")),
                    metadata_=_ascii_safe(ent_data.get("metadata", {})),
                )
                session.add(entity)
                await session.flush()
            # Build metadata from all top-level item fields (skip nested entity keys)
            skip = {"lobbyist", "entity", "employer", "payer", "contractor", "company", "relationship_type"}
            meta = _ascii_safe({k: v for k, v in item.items() if k not in skip})
            if direction == "to_fetterman":
                from_id, to_id = entity.id, fetterman.id
            else:
                from_id, to_id = fetterman.id, entity.id
            rel = Relationship(
                from_entity_id=from_id,
                to_entity_id=to_id,
                relationship_type=item.get("relationship_type", "connection"),
                amount_usd=item.get("amount_usd") or item.get("amount") or item.get("donation_amount") or item.get("annual_income"),
                source_url=item.get("source_url") or item.get("registration_url"),
                metadata_=meta,
            )
            session.add(rel)

    # Flush to ensure all entities are persisted before lobbying lookups
    await session.flush()

    # Lobbying: Company -> Bill (lobbies_on_behalf_of)
    lobbying_data = data.get("lobbying", [])
    for lobby in lobbying_data:
        company_result = await session.execute(
            select(Entity).where(Entity.slug == lobby["company_slug"])
        )
        company = company_result.scalar_one_or_none()
        bill_result = await session.execute(
            select(Entity).where(Entity.slug == lobby["bill_slug"])
        )
        bill = bill_result.scalar_one_or_none()
        if company and bill:
            rel = Relationship(
                from_entity_id=company.id,
                to_entity_id=bill.id,
                relationship_type="lobbies_on_behalf_of",
                source_label="LDA Filing",
                metadata_=_ascii_safe(lobby.get("metadata", {})),
            )
            session.add(rel)

    await seed_hidden(data.get("revolving_door", []), direction="to_fetterman")
    await seed_hidden(data.get("family_connections", []), direction="from_fetterman")
    await seed_hidden(data.get("outside_income", []), direction="to_fetterman")
    await seed_hidden(data.get("contractor_donors", []), direction="to_fetterman")

    await session.commit()


async def is_database_empty(session: AsyncSession) -> bool:
    result = await session.execute(select(Entity).limit(1))
    return result.scalar_one_or_none() is None


async def run_seed():
    """Run a full clear + seed."""
    async with async_session() as session:
        print("Clearing database...")
        await clear_database(session)
        print("Seeding database...")
        await seed_database(session)
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(run_seed())
