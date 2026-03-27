import asyncio
import os
import re
from datetime import date, datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Entity, Relationship
from app.schemas import (
    ConnectionsResponse,
    EntityBrief,
    EntityResponse,
    FlatConnectionItem,
)

FEC_API_KEY = os.getenv("FEC_API_KEY", "Fs8xrx9MhdRYufNFFUmoi1NBg2Xa5xIfrgezy8sb")
FEC_BASE_URL = "https://api.open.fec.gov/v1"
FEC_TIMEOUT = 30.0


def _slugify(name: str) -> str:
    """Convert a name to a URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _ascii_safe(obj):
    """Recursively strip non-ASCII characters for SQL_ASCII database."""
    if isinstance(obj, str):
        return obj.encode("ascii", "replace").decode("ascii")
    if isinstance(obj, dict):
        return {k: _ascii_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ascii_safe(v) for v in obj]
    return obj

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("/{slug}", response_model=EntityResponse)
async def get_entity(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


@router.get("/{slug}/connections", response_model=ConnectionsResponse)
async def get_entity_connections(
    slug: str,
    type: Optional[str] = Query(None, description="Filter by relationship type"),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Build query for relationships where this entity is either from or to
    base_q = select(Relationship).where(
        or_(
            Relationship.from_entity_id == entity.id,
            Relationship.to_entity_id == entity.id,
        )
    )
    if type:
        base_q = base_q.where(Relationship.relationship_type == type)

    # Count
    count_q = select(func.count()).select_from(base_q.subquery())
    total = (await db.execute(count_q)).scalar()

    # Fetch page
    rels_q = base_q.offset(offset).limit(limit)
    rels_result = await db.execute(rels_q)
    rels = rels_result.scalars().all()

    # Gather connected entity IDs
    connected_ids = set()
    for r in rels:
        if r.from_entity_id == entity.id:
            connected_ids.add(r.to_entity_id)
        else:
            connected_ids.add(r.from_entity_id)

    # Fetch connected entities
    entities_map = {}
    if connected_ids:
        ent_result = await db.execute(
            select(Entity).where(Entity.id.in_(connected_ids))
        )
        for e in ent_result.scalars().all():
            entities_map[e.id] = e

    # Build flat connection items
    connections = []
    for r in rels:
        connected_id = (
            r.to_entity_id if r.from_entity_id == entity.id else r.from_entity_id
        )
        connected = entities_map.get(connected_id)
        connections.append(
            FlatConnectionItem(
                id=r.id,
                from_entity_id=r.from_entity_id,
                to_entity_id=r.to_entity_id,
                relationship_type=r.relationship_type,
                amount_usd=r.amount_usd,
                amount_label=r.amount_label,
                date_start=r.date_start,
                date_end=r.date_end,
                source_url=r.source_url,
                source_label=r.source_label,
                metadata=r.metadata_,
                connected_entity=EntityBrief.model_validate(connected)
                if connected
                else None,
            )
        )

    return ConnectionsResponse(
        entity=EntityResponse.model_validate(entity),
        connections=connections,
        total=total,
    )


@router.get("/{slug}/money-to-bills")
async def get_money_to_bills(slug: str, db: AsyncSession = Depends(get_db)):
    """Trace the chain: Donor → gave money → Official → sponsored Bill.

    Groups by policy area to show where donor industries align with
    the official's legislative activity.
    """
    result = await db.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Find donor→official→bill chains
    from sqlalchemy import text as sql_text
    chains_query = sql_text("""
        SELECT
            donor.name as donor_name,
            donor.slug as donor_slug,
            donor_rel.amount_usd as donation_amount,
            bill.name as bill_name,
            bill.slug as bill_slug,
            bill.metadata->>'policy_area' as policy_area,
            bill.metadata->>'status' as bill_status,
            bill_rel.relationship_type as bill_rel_type
        FROM relationships donor_rel
        JOIN entities donor ON donor.id = donor_rel.from_entity_id
        JOIN relationships bill_rel ON bill_rel.from_entity_id = :entity_id
        JOIN entities bill ON bill.id = bill_rel.to_entity_id
        WHERE donor_rel.to_entity_id = :entity_id
        AND donor_rel.relationship_type = 'donated_to'
        AND bill_rel.relationship_type IN ('sponsored', 'cosponsored')
        AND bill.metadata->>'policy_area' IS NOT NULL
        AND bill.metadata->>'policy_area' != ''
        AND donor_rel.amount_usd > 10000
        ORDER BY donor_rel.amount_usd DESC
        LIMIT 200
    """)

    rows = (await db.execute(chains_query, {"entity_id": entity.id})).fetchall()

    # Group by policy area to find patterns
    from collections import defaultdict
    by_area: dict[str, dict] = defaultdict(lambda: {"donors": {}, "bills": set(), "total_donated": 0})

    for row in rows:
        area = row.policy_area or "Other"
        donor_key = row.donor_name
        if donor_key not in by_area[area]["donors"]:
            by_area[area]["donors"][donor_key] = {
                "name": row.donor_name,
                "slug": row.donor_slug,
                "amount": row.donation_amount or 0,
            }
        by_area[area]["bills"].add((row.bill_name, row.bill_slug, row.bill_rel_type))
        by_area[area]["total_donated"] = max(by_area[area]["total_donated"],
            sum(d["amount"] for d in by_area[area]["donors"].values()))

    # Format results
    results = []
    for area, data in sorted(by_area.items(), key=lambda x: -x[1]["total_donated"]):
        donors = sorted(data["donors"].values(), key=lambda d: -d["amount"])[:5]
        bills = [{"name": b[0], "slug": b[1], "type": b[2]} for b in list(data["bills"])[:5]]
        if donors and bills:
            results.append({
                "policy_area": area,
                "total_donated": data["total_donated"],
                "donor_count": len(data["donors"]),
                "bill_count": len(data["bills"]),
                "top_donors": donors,
                "related_bills": bills,
                "narrative": (
                    f"{len(data['donors'])} donor{'s' if len(data['donors']) > 1 else ''} "
                    f"from the {area} sector gave money to this official, who then "
                    f"{'sponsored' if bills[0]['type'] == 'sponsored' else 'cosponsored'} "
                    f"{len(data['bills'])} bill{'s' if len(data['bills']) > 1 else ''} "
                    f"in {area}."
                ),
            })

    return {
        "entity": slug,
        "entity_name": entity.name,
        "chains": results[:10],
        "total_chains": len(results),
    }


@router.get("/{slug}/influence-map")
async def get_influence_map(slug: str, db: AsyncSession = Depends(get_db)):
    """Find entities that both donate to AND lobby related to this official.

    These are the strongest influence signals: an entity gives money to
    your campaign AND pays lobbyists to influence legislation.
    """
    result = await db.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Find all donors to this official
    donor_rels = (await db.execute(
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(
            Relationship.to_entity_id == entity.id,
            Relationship.relationship_type == "donated_to",
        )
    )).all()

    if not donor_rels:
        return {"entity": slug, "dual_influence": [], "total": 0}

    # Get all lobbying clients
    lobby_clients = (await db.execute(
        select(Entity.name, Entity.slug, Entity.id)
        .join(Relationship, Relationship.to_entity_id == Entity.id)
        .where(Relationship.relationship_type == "lobbies_on_behalf_of")
    )).all()

    # Build a lookup of lobby client names (lowercased) -> slug
    lobby_lookup: dict[str, str] = {}
    for name, client_slug, client_id in lobby_clients:
        lobby_lookup[name.lower()] = client_slug

    # Match donors to lobby clients
    dual_influence = []
    for rel, donor_entity in donor_rels:
        donor_name = donor_entity.name.lower()
        # Check if this donor (or part of their name) matches a lobbying client
        matched_client = None
        for lobby_name, lobby_slug in lobby_lookup.items():
            # Match if donor name contains the lobby client name or vice versa
            donor_key = donor_name.split(",")[0].strip() if "," in donor_name else donor_name
            if len(donor_key) > 5 and (donor_key in lobby_name or lobby_name in donor_key):
                matched_client = lobby_name
                break

        if matched_client:
            dual_influence.append({
                "donor_name": donor_entity.name,
                "donor_slug": donor_entity.slug,
                "donor_type": donor_entity.entity_type,
                "donation_amount": rel.amount_usd or 0,
                "also_lobbies": True,
                "lobby_client_name": matched_client.title(),
            })

    dual_influence.sort(key=lambda x: x["donation_amount"], reverse=True)

    return {
        "entity": slug,
        "entity_name": entity.name,
        "dual_influence": dual_influence,
        "total": len(dual_influence),
        "total_donors": len(donor_rels),
    }


@router.get("/{slug}/pac-donors")
async def get_pac_donors(slug: str, cycle: int | None = None, db: AsyncSession = Depends(get_db)):
    """Fetch PAC/committee donors on-the-fly from the FEC API.

    1. Loads the entity by slug
    2. Checks for existing cached donated_to relationships
    3. If none, looks up FEC committee ID (from metadata or FEC search)
    4. Fetches top donors from FEC Schedule A
    5. Caches results as entities + relationships in the DB
    """
    # 1. Load entity
    result = await db.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    # 2. Check for cached donor relationships (donated_to pointing TO this entity)
    cached_rels = await db.execute(
        select(Relationship)
        .where(
            Relationship.to_entity_id == entity.id,
            Relationship.relationship_type == "donated_to",
        )
        .order_by(Relationship.amount_usd.desc().nulls_last())
        .limit(50)
    )
    cached = cached_rels.scalars().all()

    if cached and not cycle:
        # Fetch the donor entities (skip cache if specific cycle requested)
        donor_ids = [r.from_entity_id for r in cached]
        donor_result = await db.execute(
            select(Entity).where(Entity.id.in_(donor_ids))
        )
        donors_map = {e.id: e for e in donor_result.scalars().all()}

        donors_list = []
        for r in cached:
            donor = donors_map.get(r.from_entity_id)
            if donor:
                donors_list.append({
                    "name": donor.name,
                    "slug": donor.slug,
                    "amount": r.amount_usd or 0,
                    "date": str(r.date_start) if r.date_start else None,
                    "employer": (donor.metadata_ or {}).get("employer", ""),
                })

        fec_committee_id = (entity.metadata_ or {}).get("fec_committee_id", "")
        return {
            "entity_slug": entity.slug,
            "entity_name": entity.name,
            "fec_committee_id": fec_committee_id,
            "donors": donors_list,
            "total_donors": len(donors_list),
            "source": "cached",
        }

    # 3. Find FEC committee ID
    metadata = entity.metadata_ or {}
    fec_committee_id = metadata.get("fec_committee_id", "")

    if not fec_committee_id:
        # Search FEC API by committee name
        await asyncio.sleep(1)  # Rate limit delay
        try:
            async with httpx.AsyncClient(timeout=FEC_TIMEOUT) as client:
                search_resp = await client.get(
                    f"{FEC_BASE_URL}/committees/",
                    params={
                        "api_key": FEC_API_KEY,
                        "q": entity.name,
                        "per_page": 5,
                    },
                )
                search_resp.raise_for_status()
                search_data = search_resp.json()
                committees = search_data.get("results", [])
                if committees:
                    fec_committee_id = committees[0].get("committee_id", "")
                    print(f"[PAC-DONORS] Found committee ID {fec_committee_id} for '{entity.name}'")
                else:
                    print(f"[PAC-DONORS] No FEC committee found for '{entity.name}'")
                    return {
                        "entity_slug": entity.slug,
                        "entity_name": entity.name,
                        "fec_committee_id": None,
                        "donors": [],
                        "total_donors": 0,
                        "source": "fec_live",
                        "error": "No matching FEC committee found",
                    }
        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"[PAC-DONORS] FEC committee search failed: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"FEC API error searching for committee: {str(e)}",
            )

        # Save committee ID to entity metadata for future lookups
        updated_metadata = dict(metadata)
        updated_metadata["fec_committee_id"] = fec_committee_id
        entity.metadata_ = _ascii_safe(updated_metadata)
        db.add(entity)

    # 4. Fetch Schedule A donors from FEC
    await asyncio.sleep(1)  # Rate limit delay
    try:
        async with httpx.AsyncClient(timeout=FEC_TIMEOUT) as client:
            donors_resp = await client.get(
                f"{FEC_BASE_URL}/schedules/schedule_a/",
                params={
                    "api_key": FEC_API_KEY,
                    "committee_id": fec_committee_id,
                    "per_page": 20,
                    "sort": "-contribution_receipt_amount",
                    **({"two_year_transaction_period": cycle} if cycle else {}),
                },
            )
            donors_resp.raise_for_status()
            donors_data = donors_resp.json()
            fec_donors = donors_data.get("results", [])
            print(f"[PAC-DONORS] Fetched {len(fec_donors)} donors for {fec_committee_id}")
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        print(f"[PAC-DONORS] FEC Schedule A fetch failed: {e}")
        raise HTTPException(
            status_code=502,
            detail=f"FEC API error fetching donors: {str(e)}",
        )

    # 5. Create donor entities + relationships in DB (cache)
    donors_list = []
    for donor_record in fec_donors:
        donor_name = _ascii_safe(
            donor_record.get("contributor_name", "UNKNOWN DONOR")
        )
        donor_slug = _slugify(donor_name)
        amount = donor_record.get("contribution_receipt_amount")
        amount_int = int(amount * 100) if amount else None  # Store as cents
        contribution_date_str = donor_record.get("contribution_receipt_date")
        contribution_date = None
        if contribution_date_str:
            try:
                contribution_date = datetime.strptime(
                    contribution_date_str, "%Y-%m-%dT%H:%M:%S"
                ).date()
            except (ValueError, TypeError):
                try:
                    contribution_date = datetime.strptime(
                        contribution_date_str[:10], "%Y-%m-%d"
                    ).date()
                except (ValueError, TypeError):
                    pass

        employer = _ascii_safe(
            donor_record.get("contributor_employer", "") or ""
        )
        occupation = _ascii_safe(
            donor_record.get("contributor_occupation", "") or ""
        )
        contributor_city = _ascii_safe(
            donor_record.get("contributor_city", "") or ""
        )
        contributor_state = donor_record.get("contributor_state", "") or ""

        # Check if donor entity already exists
        existing = await db.execute(
            select(Entity).where(Entity.slug == donor_slug)
        )
        donor_entity = existing.scalar_one_or_none()

        if not donor_entity:
            donor_entity = Entity(
                slug=donor_slug,
                entity_type="donor",
                name=donor_name,
                metadata_=_ascii_safe({
                    "employer": employer,
                    "occupation": occupation,
                    "city": contributor_city,
                    "state": contributor_state,
                    "source": "fec_schedule_a",
                }),
            )
            db.add(donor_entity)
            await db.flush()  # Get the ID assigned

        # Create donated_to relationship
        rel = Relationship(
            from_entity_id=donor_entity.id,
            to_entity_id=entity.id,
            relationship_type="donated_to",
            amount_usd=amount_int,
            date_start=contribution_date,
            source_url=f"https://api.open.fec.gov/v1/schedules/schedule_a/?committee_id={fec_committee_id}",
            source_label="FEC Schedule A",
            metadata_=_ascii_safe({
                "fec_committee_id": fec_committee_id,
                "memo_text": donor_record.get("memo_text", ""),
                "receipt_type": donor_record.get("receipt_type", ""),
            }),
        )
        db.add(rel)

        donors_list.append({
            "name": donor_name,
            "slug": donor_slug,
            "amount": amount_int or 0,
            "date": str(contribution_date) if contribution_date else None,
            "employer": employer,
        })

    await db.commit()
    print(f"[PAC-DONORS] Cached {len(donors_list)} donors for '{entity.name}'")

    return {
        "entity_slug": entity.slug,
        "entity_name": entity.name,
        "fec_committee_id": fec_committee_id,
        "donors": donors_list,
        "total_donors": len(donors_list),
        "source": "fec_live",
    }
