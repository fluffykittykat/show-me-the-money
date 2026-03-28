"""V2 API — single response per page.

Each endpoint serves ALL data the frontend needs for a given page,
eliminating waterfall fetches.
"""

import json
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AppConfig, BillInfluenceSignal, Entity, MoneyTrail, OfficialInfluenceSignal, Relationship
from app.services.ingestion.congress_client import CongressClient
from app.schemas import (
    EntityResponse,
    V2BillResponse,
    V2BillSponsor,
    V2EntityResponse,
    V2HomepageResponse,
    V2InfluenceSignal,
    V2MoneyTrail,
    V2OfficialResponse,
    V2SponsorContext,
    V2SponsorVerifiedConnection,
)

router = APIRouter(tags=["v2"])


# ---------------------------------------------------------------------------
# GET /v2/official/{slug}
# ---------------------------------------------------------------------------


@router.get("/official/{slug}", response_model=V2OfficialResponse)
async def v2_official(slug: str, db: AsyncSession = Depends(get_db)):
    """Return everything the Official page needs in one response."""

    entity = (
        await db.execute(select(Entity).where(Entity.slug == slug))
    ).scalar_one_or_none()

    if not entity or entity.entity_type != "person":
        raise HTTPException(status_code=404, detail="Official not found")

    meta = entity.metadata_ or {}

    # --- Money trails (pre-computed) ---
    trails_result = await db.execute(
        select(MoneyTrail)
        .where(MoneyTrail.official_id == entity.id)
        .order_by(MoneyTrail.dot_count.desc())
    )
    trails = trails_result.scalars().all()

    money_trails = []
    for t in trails:
        chain_data = t.chain or {}
        dots = chain_data.get("dots", [])
        # Ensure dots is a list of strings
        if not isinstance(dots, list):
            dots = []
        money_trails.append(
            V2MoneyTrail(
                industry=t.industry,
                verdict=t.verdict,
                dot_count=t.dot_count,
                dots=dots,
                narrative=t.narrative,
                total_amount=t.total_amount or 0,
                chain=chain_data,
            )
        )

    # --- Overall verdict from entity metadata ---
    overall_verdict = meta.get("v2_verdict", "NORMAL")
    total_dots = meta.get("v2_dot_count", 0)

    # --- Top donors: aggregate donated_to where to_entity = official ---
    donor_q = (
        select(
            Relationship.from_entity_id,
            func.sum(Relationship.amount_usd).label("total_donated"),
            func.max(Relationship.date_start).label("latest_date"),
        )
        .where(Relationship.to_entity_id == entity.id)
        .where(Relationship.relationship_type == "donated_to")
        .group_by(Relationship.from_entity_id)
        .order_by(func.sum(Relationship.amount_usd).desc())
        .limit(15)
    )
    donor_rows = (await db.execute(donor_q)).all()

    # Load donor entities
    donor_ids = [r[0] for r in donor_rows]
    donor_entities = {}
    if donor_ids:
        de_result = await db.execute(
            select(Entity).where(Entity.id.in_(donor_ids))
        )
        donor_entities = {e.id: e for e in de_result.scalars().all()}

    top_donors = []
    middlemen = []
    for donor_id, total_donated, latest_date in donor_rows:
        de = donor_entities.get(donor_id)
        if not de:
            continue
        entry = {
            "slug": de.slug,
            "name": de.name,
            "entity_type": de.entity_type,
            "total_donated": total_donated or 0,
            "latest_date": latest_date.isoformat() if latest_date else None,
        }
        top_donors.append(entry)
        if de.entity_type == "pac":
            middlemen.append(entry)

    # --- Committees from committee_member relationships ---
    committee_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.to_entity_id)
        .where(Relationship.from_entity_id == entity.id)
        .where(Relationship.relationship_type == "committee_member")
    )
    committee_rows = (await db.execute(committee_q)).all()

    committees = []
    for rel, committee_entity in committee_rows:
        rel_meta = rel.metadata_ or {}
        committees.append({
            "slug": committee_entity.slug,
            "name": committee_entity.name,
            "role": rel_meta.get("role", "Member"),
        })

    # --- Briefing ---
    briefing = meta.get("fbi_briefing")

    # --- Patch campaign_total fallback ---
    if not meta.get("campaign_total") and meta.get("total_receipts"):
        meta["campaign_total"] = meta["total_receipts"]
        entity.metadata_ = meta
        db.add(entity)
        await db.commit()

    # --- Stock trades ---
    stock_q = (
        select(Relationship)
        .where(Relationship.from_entity_id == entity.id)
        .where(Relationship.relationship_type.in_(["stock_trade", "holds_stock"]))
        .order_by(Relationship.date_start.desc().nulls_last())
        .limit(50)
    )
    stock_result = await db.execute(stock_q)
    stock_trades_raw = stock_result.scalars().all()

    stock_trade_list = []
    for st in stock_trades_raw:
        m = st.metadata_ or {}
        stock_trade_list.append({
            "ticker": m.get("ticker", ""),
            "transaction_type": m.get("transaction_type", ""),
            "amount_range": st.amount_label or m.get("amount_range", ""),
            "date": str(st.date_start) if st.date_start else None,
            "asset_name": m.get("asset_name", m.get("asset_description", "")),
        })

    # --- FEC cycle breakdown ---
    fec_cycles = meta.get("fec_all_cycles", [])
    total_all_cycles = int(sum(c.get("receipts", 0) for c in fec_cycles)) if fec_cycles else 0

    # --- Freshness ---
    has_donors = len(top_donors) > 0
    has_committees = len(committees) > 0
    freshness = {
        "fec_cycle": meta.get("best_fec_cycle"),
        "last_refreshed": meta.get("last_refreshed"),
        "has_donors": has_donors,
        "has_committees": has_committees,
    }

    # --- Influence signals ---
    signals_q = select(OfficialInfluenceSignal).where(
        OfficialInfluenceSignal.official_id == entity.id
    )
    signals_result = await db.execute(signals_q)
    signals = signals_result.scalars().all()

    influence_signals = [
        V2InfluenceSignal(
            type=s.signal_type,
            found=s.found,
            rarity_label=s.rarity_label,
            rarity_pct=s.rarity_pct,
            p_value=s.p_value,
            baseline_rate=s.baseline_rate,
            observed_rate=s.observed_rate,
            description=s.description,
            evidence=s.evidence or {},
        )
        for s in signals
    ]

    pct = meta.get("official_influence_percentile")
    percentile_rank = int(float(pct)) if pct else None
    chamber = meta.get("chamber", "")
    peer_group = "senators" if "Senate" in str(chamber) else "representatives"
    peer_count = 100 if peer_group == "senators" else 435

    return V2OfficialResponse(
        entity=EntityResponse.model_validate(entity),
        overall_verdict=overall_verdict,
        total_dots=total_dots,
        money_trails=money_trails,
        top_donors=top_donors,
        middlemen=middlemen,
        committees=committees,
        briefing=briefing,
        freshness=freshness,
        stock_trades=stock_trade_list,
        fec_cycles=fec_cycles,
        total_all_cycles=total_all_cycles,
        influence_signals=influence_signals,
        percentile_rank=percentile_rank,
        peer_count=peer_count,
        peer_group=peer_group,
    )


# ---------------------------------------------------------------------------
# GET /v2/bill/{slug}
# ---------------------------------------------------------------------------


_STATUS_MAP = {
    "became_law": "BECAME LAW",
    "becamelaw": "BECAME LAW",
    "enacted": "BECAME LAW",
    "in_committee": "IN COMMITTEE",
    "committee": "IN COMMITTEE",
    "passed": "PASSED",
    "failed": "FAILED",
    "vetoed": "FAILED",
    "introduced": "INTRODUCED",
}


def _parse_bill_status(raw: str | None) -> str:
    if not raw:
        return "INTRODUCED"
    key = raw.lower().replace(" ", "_").replace("-", "_")
    # Direct match
    if key in _STATUS_MAP:
        return _STATUS_MAP[key]
    # Phrase matching for verbose clerk text
    raw_lower = raw.lower()
    if "became law" in raw_lower or "enacted" in raw_lower:
        return "BECAME LAW"
    if "passed" in raw_lower or "agreed to" in raw_lower:
        return "PASSED"
    if "failed" in raw_lower or "rejected" in raw_lower or "vetoed" in raw_lower:
        return "FAILED"
    if "committee" in raw_lower or "referred" in raw_lower:
        return "IN COMMITTEE"
    if "floor" in raw_lower or "calendar" in raw_lower:
        return "ON FLOOR"
    if "introduced" in raw_lower or "read twice" in raw_lower:
        return "INTRODUCED"
    # Fallback: if it mentions "motion" or other procedural text, it likely passed
    if "motion to reconsider" in raw_lower:
        return "PASSED"
    return "INTRODUCED"


@router.get("/bill/{slug}", response_model=V2BillResponse)
async def v2_bill(slug: str, db: AsyncSession = Depends(get_db)):
    """Return everything the Bill page needs in one response."""
    import traceback as _tb

    entity = (
        await db.execute(select(Entity).where(Entity.slug == slug))
    ).scalar_one_or_none()

    if not entity or entity.entity_type != "bill":
        raise HTTPException(status_code=404, detail="Bill not found")

    try:
        return await _v2_bill_inner(entity, slug, db)
    except Exception as e:
        print(f"[v2] Bill endpoint error for {slug}: {e}")
        _tb.print_exc()
        raise


async def _v2_bill_inner(entity, slug: str, db):
    """Inner bill logic — separated for error tracing."""
    from datetime import timedelta

    meta = entity.metadata_ or {}
    status_label = _parse_bill_status(meta.get("status"))

    # --- Load pre-computed influence signals ---
    signals_q = select(BillInfluenceSignal).where(BillInfluenceSignal.bill_id == entity.id)
    signals_result = await db.execute(signals_q)
    signals = signals_result.scalars().all()
    influence_signals = [
        V2InfluenceSignal(
            type=s.signal_type,
            found=s.found,
            rarity_label=s.rarity_label,
            rarity_pct=s.rarity_pct,
            p_value=s.p_value,
            baseline_rate=s.baseline_rate,
            observed_rate=s.observed_rate,
            description=s.description,
            evidence=s.evidence or {},
        )
        for s in signals
    ]

    # --- Sponsors / cosponsors with layered data ---
    sponsor_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.to_entity_id == entity.id)
        .where(
            Relationship.relationship_type.in_(["sponsored", "cosponsored"])
        )
    )
    sponsor_rows = (await db.execute(sponsor_q)).all()

    # Find lobbying clients for THIS bill (lobbied_on relationships pointing to this bill)
    lobby_client_q = (
        select(Relationship.from_entity_id)
        .where(Relationship.to_entity_id == entity.id)
        .where(Relationship.relationship_type == "lobbied_on")
    )
    lobby_client_rows = (await db.execute(lobby_client_q)).all()
    lobby_client_ids = {r[0] for r in lobby_client_rows}

    sponsors: list[V2BillSponsor] = []
    total_money_behind = 0
    all_donor_names: dict[str, int] = {}

    for rel, sponsor_entity in sponsor_rows:
        s_meta = sponsor_entity.metadata_ or {}
        role = "Primary Sponsor" if rel.relationship_type == "sponsored" else "Cosponsor"

        # --- Verified connections: lobby clients that also donated to this sponsor ---
        verified_connections: list[V2SponsorVerifiedConnection] = []
        if lobby_client_ids:
            vc_q = (
                select(Relationship, Entity)
                .join(Entity, Entity.id == Relationship.from_entity_id)
                .where(Relationship.to_entity_id == sponsor_entity.id)
                .where(Relationship.relationship_type == "donated_to")
                .where(Relationship.from_entity_id.in_(lobby_client_ids))
            )
            vc_rows = (await db.execute(vc_q)).all()
            for vc_rel, vc_entity in vc_rows:
                verified_connections.append(
                    V2SponsorVerifiedConnection(
                        entity=vc_entity.name,
                        type="lobby_donor",
                        amount=int(vc_rel.amount_usd or 0),
                    )
                )

        # --- Context: career PAC total ---
        career_pac_q = (
            select(func.sum(Relationship.amount_usd))
            .where(Relationship.to_entity_id == sponsor_entity.id)
            .where(Relationship.relationship_type == "donated_to")
        )
        career_pac_total = (await db.execute(career_pac_q)).scalar() or 0

        # --- Context: industry donations within 90 days ---
        industry_90d = 0
        if rel.date_start:
            window_start = rel.date_start - timedelta(days=90)
            ind_q = (
                select(func.sum(Relationship.amount_usd))
                .where(Relationship.to_entity_id == sponsor_entity.id)
                .where(Relationship.relationship_type == "donated_to")
                .where(Relationship.date_start >= window_start)
                .where(Relationship.date_start <= rel.date_start)
            )
            industry_90d = (await db.execute(ind_q)).scalar() or 0

        # --- Context: committee ---
        committee_name = None
        comm_q = (
            select(Entity.name)
            .join(Relationship, Relationship.to_entity_id == Entity.id)
            .where(Relationship.from_entity_id == sponsor_entity.id)
            .where(Relationship.relationship_type == "committee_member")
            .limit(1)
        )
        comm_result = (await db.execute(comm_q)).scalar()
        if comm_result:
            committee_name = comm_result

        context = V2SponsorContext(
            industry_donations_90d=int(industry_90d),
            career_pac_total=int(career_pac_total),
            committee=committee_name,
        )

        total_money_behind += int(career_pac_total)

        # Track top donors across all sponsors
        donor_q = (
            select(
                Relationship.from_entity_id,
                func.sum(Relationship.amount_usd).label("total"),
            )
            .where(Relationship.to_entity_id == sponsor_entity.id)
            .where(Relationship.relationship_type == "donated_to")
            .group_by(Relationship.from_entity_id)
            .order_by(func.sum(Relationship.amount_usd).desc())
            .limit(5)
        )
        donor_rows = (await db.execute(donor_q)).all()
        donor_ids = [r[0] for r in donor_rows]
        donor_entities = {}
        if donor_ids:
            de_result = await db.execute(
                select(Entity).where(Entity.id.in_(donor_ids))
            )
            donor_entities = {e.id: e for e in de_result.scalars().all()}

        for did, amount in donor_rows:
            de = donor_entities.get(did)
            if de:
                amt = int(amount or 0)
                all_donor_names[de.name] = all_donor_names.get(de.name, 0) + amt

        sponsors.append(V2BillSponsor(
            slug=sponsor_entity.slug,
            name=sponsor_entity.name,
            party=s_meta.get("party", ""),
            state=s_meta.get("state", ""),
            role=role,
            verified_connections=verified_connections,
            context=context,
        ))

    # Sort: primary sponsors first, then by career_pac_total desc
    sponsors.sort(key=lambda s: (0 if s.role == "Primary Sponsor" else 1, -s.context.career_pac_total))

    # Top donors across all sponsors
    top_donors_across = [[name, int(amt)] for name, amt in sorted(all_donor_names.items(), key=lambda x: -x[1])[:10]]

    briefing = meta.get("fbi_briefing")
    policy_area = meta.get("policy_area") or ""

    # --- Percentile rank ---
    percentile_rank = meta.get("influence_percentile")
    if percentile_rank is not None:
        percentile_rank = int(percentile_rank)

    # --- Similar bill count ---
    similar_bill_count = 0
    if policy_area:
        similar_q = (
            select(func.count())
            .select_from(Entity)
            .where(Entity.entity_type == "bill")
            .where(Entity.metadata_["policy_area"].astext == policy_area)
        )
        similar_bill_count = (await db.execute(similar_q)).scalar() or 0

    # --- Data limitations ---
    data_limitations = {
        "fec_threshold": "$200",
        "senate_stocks": False,
        "industry_matching": "keyword",
        "lda_coverage": "quarterly",
    }

    # --- Vote data (cached in metadata, fetched from Congress.gov if missing) ---
    votes = meta.get("votes") or []
    if not votes and isinstance(votes, list):
        congress_api_key = os.getenv("CONGRESS_API_KEY", "")
        congress_num = meta.get("congress")
        bill_number = meta.get("bill_number")
        if congress_api_key and congress_num and bill_number:
            slug_str = slug or ""
            bill_type = "hres"
            origin = (meta.get("origin_chamber") or "").lower()
            name_lower = (entity.name or "").lower()
            if "joint resolution" in name_lower:
                bill_type = "hjres" if origin == "house" else "sjres"
            elif "concurrent resolution" in name_lower:
                bill_type = "hconres" if origin == "house" else "sconres"
            elif "resolution" in name_lower:
                bill_type = "hres" if origin == "house" else "sres"
            elif origin == "senate":
                bill_type = "s"
            else:
                bill_type = "hr"

            try:
                client = CongressClient(congress_api_key)
                votes = await client.fetch_bill_votes(
                    int(congress_num), bill_type, int(bill_number)
                )
                if votes:
                    meta["votes"] = votes
                    entity.metadata_ = meta
                    db.add(entity)
                    await db.commit()
            except Exception as e:
                print(f"[v2] Vote fetch error for {slug}: {e}")

    return V2BillResponse(
        entity=EntityResponse.model_validate(entity),
        status_label=status_label,
        sponsors=sponsors,
        briefing=briefing,
        summary=entity.summary,
        policy_area=policy_area,
        total_money_behind=total_money_behind,
        top_donors_across=top_donors_across,
        votes=votes,
        percentile_rank=percentile_rank,
        similar_bill_count=similar_bill_count,
        influence_signals=influence_signals,
        data_limitations=data_limitations,
    )


# ---------------------------------------------------------------------------
# GET /v2/entity/{slug}
# ---------------------------------------------------------------------------


@router.get("/entity/{slug}", response_model=V2EntityResponse)
async def v2_entity(slug: str, db: AsyncSession = Depends(get_db)):
    """Return everything an Entity page needs in one response."""

    entity = (
        await db.execute(select(Entity).where(Entity.slug == slug))
    ).scalar_one_or_none()

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    meta = entity.metadata_ or {}

    # --- Money in: donated_to where this entity is to_entity ---
    money_in_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.to_entity_id == entity.id)
        .where(Relationship.relationship_type == "donated_to")
        .order_by(Relationship.amount_usd.desc().nulls_last())
        .limit(50)
    )
    money_in_rows = (await db.execute(money_in_q)).all()

    money_in = []
    for rel, from_entity in money_in_rows:
        money_in.append({
            "slug": from_entity.slug,
            "name": from_entity.name,
            "entity_type": from_entity.entity_type,
            "amount_usd": rel.amount_usd or 0,
            "amount_label": rel.amount_label,
            "date": rel.date_start.isoformat() if rel.date_start else None,
        })

    # --- Money out: donated_to where this entity is from_entity ---
    money_out_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.to_entity_id)
        .where(Relationship.from_entity_id == entity.id)
        .where(Relationship.relationship_type == "donated_to")
        .order_by(Relationship.amount_usd.desc().nulls_last())
        .limit(50)
    )
    money_out_rows = (await db.execute(money_out_q)).all()

    money_out = []
    for rel, to_entity in money_out_rows:
        money_out.append({
            "slug": to_entity.slug,
            "name": to_entity.name,
            "entity_type": to_entity.entity_type,
            "amount_usd": rel.amount_usd or 0,
            "amount_label": rel.amount_label,
            "date": rel.date_start.isoformat() if rel.date_start else None,
        })

    briefing = meta.get("fbi_briefing")

    # --- Money trails: trace money forward to officials + their legislation ---
    # For each money_out recipient:
    #   If recipient is an official (person with bioguide_id): show their bills
    #   If recipient is a PAC/fund: trace where that PAC sent money to officials
    money_trails: list[dict] = []
    seen_officials: set[str] = set()

    async def _trace_official(off_entity: Entity, amount: int, via: str | None = None):
        """Build a trail entry for an official showing their legislation."""
        if off_entity.slug in seen_officials:
            return
        seen_officials.add(off_entity.slug)
        off_meta = off_entity.metadata_ or {}
        # Get bills this official sponsored
        bill_q = (
            select(Relationship, Entity)
            .join(Entity, Entity.id == Relationship.to_entity_id)
            .where(Relationship.from_entity_id == off_entity.id)
            .where(Relationship.relationship_type.in_(["sponsored", "cosponsored"]))
            .limit(10)
        )
        bill_rows = (await db.execute(bill_q)).all()
        bills = [
            {"name": be.name, "slug": be.slug, "role": br.relationship_type}
            for br, be in bill_rows
        ]
        # Get their verdict
        verdict = off_meta.get("v2_verdict", "NORMAL")
        trail: dict = {
            "official_name": off_entity.name,
            "official_slug": off_entity.slug,
            "official_party": off_meta.get("party", ""),
            "official_state": off_meta.get("state", ""),
            "amount_received": amount,
            "verdict": verdict,
            "bills": bills,
        }
        if via:
            trail["via"] = via
        money_trails.append(trail)

    for out_entry in money_out:
        out_slug = out_entry["slug"]
        out_entity_type = out_entry["entity_type"]
        out_amount = out_entry["amount_usd"]

        if out_entity_type == "person":
            # Direct to official
            off = (await db.execute(
                select(Entity).where(Entity.slug == out_slug)
            )).scalar_one_or_none()
            if off and ((off.metadata_ or {}).get("bioguide_id") or (off.metadata_ or {}).get("bioguideId")):
                await _trace_official(off, out_amount)
        elif out_entity_type in ("pac", "donor"):
            # Trace through PAC: where did this PAC send money?
            pac = (await db.execute(
                select(Entity).where(Entity.slug == out_slug)
            )).scalar_one_or_none()
            if not pac:
                continue
            pac_out_q = (
                select(Relationship, Entity)
                .join(Entity, Entity.id == Relationship.to_entity_id)
                .where(Relationship.from_entity_id == pac.id)
                .where(Relationship.relationship_type == "donated_to")
                .where(Entity.entity_type == "person")
                .order_by(Relationship.amount_usd.desc().nulls_last())
                .limit(20)
            )
            pac_out_rows = (await db.execute(pac_out_q)).all()
            for pac_rel, off_entity in pac_out_rows:
                if ((off_entity.metadata_ or {}).get("bioguide_id") or (off_entity.metadata_ or {}).get("bioguideId")):
                    await _trace_official(
                        off_entity,
                        pac_rel.amount_usd or 0,
                        via=pac.name,
                    )

    # Sort trails by amount descending
    money_trails.sort(key=lambda t: -t["amount_received"])

    # --- ALL other relationships (lobbying, revolving door, committees, etc.) ---
    all_outgoing_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.to_entity_id)
        .where(Relationship.from_entity_id == entity.id)
        .where(Relationship.relationship_type != "donated_to")
        .order_by(Relationship.amount_usd.desc().nulls_last())
        .limit(50)
    )
    all_incoming_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.to_entity_id == entity.id)
        .where(Relationship.relationship_type != "donated_to")
        .order_by(Relationship.amount_usd.desc().nulls_last())
        .limit(50)
    )
    outgoing_rows = (await db.execute(all_outgoing_q)).all()
    incoming_rows = (await db.execute(all_incoming_q)).all()

    connections: list[dict] = []
    for rel, other_entity in outgoing_rows:
        r_meta = rel.metadata_ or {}
        connections.append({
            "direction": "outgoing",
            "relationship_type": rel.relationship_type,
            "entity_name": other_entity.name,
            "entity_slug": other_entity.slug,
            "entity_type": other_entity.entity_type,
            "amount_usd": rel.amount_usd or 0,
            "amount_label": rel.amount_label,
            "date": rel.date_start.isoformat() if rel.date_start else None,
            "detail": r_meta.get("covered_position")
                or r_meta.get("general_issue_code")
                or r_meta.get("description", "")
                or r_meta.get("client", ""),
        })
    for rel, other_entity in incoming_rows:
        r_meta = rel.metadata_ or {}
        connections.append({
            "direction": "incoming",
            "relationship_type": rel.relationship_type,
            "entity_name": other_entity.name,
            "entity_slug": other_entity.slug,
            "entity_type": other_entity.entity_type,
            "amount_usd": rel.amount_usd or 0,
            "amount_label": rel.amount_label,
            "date": rel.date_start.isoformat() if rel.date_start else None,
            "detail": r_meta.get("covered_position")
                or r_meta.get("general_issue_code")
                or r_meta.get("description", "")
                or r_meta.get("client", ""),
        })

    # Extract key dossier fields from metadata
    dossier = {
        "covered_position": meta.get("covered_position", ""),
        "current_firm": meta.get("current_firm", ""),
        "is_revolving_door": meta.get("is_revolving_door", False),
        "lda_lobbyist_id": meta.get("lda_lobbyist_id"),
    }

    return V2EntityResponse(
        entity=EntityResponse.model_validate(entity),
        money_in=money_in,
        money_out=money_out,
        money_trails=money_trails,
        briefing=briefing,
        connections=connections,
        dossier=dossier,
    )


# ---------------------------------------------------------------------------
# GET /v2/trades
# ---------------------------------------------------------------------------


@router.get("/trades")
async def v2_trades(db: AsyncSession = Depends(get_db), limit: int = 50, offset: int = 0):
    """Return recent stock trades with official info."""
    trade_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.relationship_type.in_(["stock_trade", "holds_stock"]))
        .order_by(Relationship.date_start.desc().nulls_last())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(trade_q)).all()

    # Load stock entities
    stock_ids = [r[0].to_entity_id for r in rows]
    stock_entities = {}
    if stock_ids:
        se_result = await db.execute(select(Entity).where(Entity.id.in_(stock_ids)))
        stock_entities = {e.id: e for e in se_result.scalars().all()}

    trades = []
    for rel, official in rows:
        stock = stock_entities.get(rel.to_entity_id)
        r_meta = rel.metadata_ or {}
        o_meta = official.metadata_ or {}
        trades.append({
            "official_name": official.name,
            "official_slug": official.slug,
            "official_party": o_meta.get("party", ""),
            "official_state": o_meta.get("state", ""),
            "ticker": r_meta.get("ticker", stock.name if stock else "?"),
            "asset_name": stock.name if stock else r_meta.get("description", "Unknown"),
            "transaction_type": r_meta.get("transaction_type", "Unknown"),
            "amount_range": rel.amount_label or r_meta.get("amount_range", ""),
            "trade_date": rel.date_start.isoformat() if rel.date_start else None,
            "notification_date": r_meta.get("notification_date"),
            "owner": r_meta.get("owner", ""),
            "source_url": rel.source_url,
        })

    # Count total
    count_q = (
        select(func.count())
        .select_from(Relationship)
        .where(Relationship.relationship_type.in_(["stock_trade", "holds_stock"]))
    )
    total = (await db.execute(count_q)).scalar() or 0

    return {"trades": trades, "total": total}


# ---------------------------------------------------------------------------
# GET /v2/homepage
# ---------------------------------------------------------------------------


@router.get("/homepage", response_model=V2HomepageResponse)
async def v2_homepage(db: AsyncSession = Depends(get_db)):
    """Return everything the homepage needs in one response."""

    # --- Top stories from app_config (pre-computed) ---
    top_stories: list[dict] = []
    story_row = (
        await db.execute(
            select(AppConfig).where(AppConfig.key == "v2_story_feed")
        )
    ).scalar_one_or_none()
    if story_row and story_row.value:
        try:
            top_stories = json.loads(story_row.value)
        except (json.JSONDecodeError, TypeError):
            pass

    # --- Stats ---
    officials_count = (
        await db.execute(
            select(func.count())
            .select_from(Entity)
            .where(Entity.entity_type == "person")
        )
    ).scalar() or 0

    bills_count = (
        await db.execute(
            select(func.count())
            .select_from(Entity)
            .where(Entity.entity_type == "bill")
        )
    ).scalar() or 0

    donations_total = (
        await db.execute(
            select(func.sum(Relationship.amount_usd)).where(
                Relationship.relationship_type == "donated_to"
            )
        )
    ).scalar() or 0

    relationship_count = (
        await db.execute(
            select(func.count()).select_from(Relationship)
        )
    ).scalar() or 0

    stats = {
        "officials_count": officials_count,
        "bills_count": bills_count,
        "donations_total": donations_total,
        "relationship_count": relationship_count,
    }

    # --- Top officials by v2_dot_count ---
    # Filter entities that have v2_verdict in metadata
    officials_q = (
        select(Entity)
        .where(Entity.entity_type == "person")
        .where(Entity.metadata_.has_key("v2_verdict"))
        .limit(100)
    )
    officials_result = (await db.execute(officials_q)).scalars().all()

    # Sort by v2_dot_count descending in Python (JSONB sort is tricky)
    officials_sorted = sorted(
        officials_result,
        key=lambda e: (e.metadata_ or {}).get("v2_dot_count", 0),
        reverse=True,
    )[:10]

    top_officials = []
    for o in officials_sorted:
        m = o.metadata_ or {}
        top_officials.append({
            "slug": o.slug,
            "name": o.name,
            "party": m.get("party", ""),
            "state": m.get("state", ""),
            "verdict": m.get("v2_verdict", "NORMAL"),
            "dot_count": m.get("v2_dot_count", 0),
        })

    # --- Top influencers (same logic as dashboard) ---
    influencer_q = (
        select(
            Relationship.from_entity_id,
            func.sum(Relationship.amount_usd).label("total_donated"),
            func.count(func.distinct(Relationship.to_entity_id)).label(
                "officials_funded"
            ),
        )
        .where(Relationship.relationship_type == "donated_to")
        .group_by(Relationship.from_entity_id)
        .having(func.count(func.distinct(Relationship.to_entity_id)) >= 2)
        .order_by(func.sum(Relationship.amount_usd).desc())
        .limit(20)
    )
    inf_rows = (await db.execute(influencer_q)).all()

    inf_ids = [r[0] for r in inf_rows]
    inf_entities = {}
    if inf_ids:
        ie_result = await db.execute(
            select(Entity).where(Entity.id.in_(inf_ids))
        )
        inf_entities = {e.id: e for e in ie_result.scalars().all()}

    top_influencers = []
    for entity_id, total_donated, officials_funded in inf_rows:
        ie = inf_entities.get(entity_id)
        if not ie:
            continue
        if ie.entity_type == "person" and not (ie.metadata_ or {}).get(
            "donor_type"
        ) == "pac":
            continue
        top_influencers.append({
            "slug": ie.slug,
            "name": ie.name,
            "entity_type": ie.entity_type,
            "total_donated": total_donated or 0,
            "officials_funded": officials_funded,
        })
        if len(top_influencers) >= 10:
            break

    # --- Revolving door (same logic as dashboard) ---
    rd_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.to_entity_id)
        .where(Relationship.relationship_type == "revolving_door_lobbyist")
        .where(Entity.entity_type == "person")
        .where(Entity.metadata_.has_key("bioguide_id"))
        .limit(15)
    )
    rd_rows = (await db.execute(rd_q)).all()

    lobbyist_ids = [r[0].from_entity_id for r in rd_rows]
    lobbyist_map = {}
    if lobbyist_ids:
        lb_result = await db.execute(
            select(Entity).where(Entity.id.in_(lobbyist_ids))
        )
        lobbyist_map = {e.id: e for e in lb_result.scalars().all()}

    revolving_door = []
    seen_lobbyists: set[str] = set()
    for rel, official in rd_rows:
        lobbyist = lobbyist_map.get(rel.from_entity_id)
        if not lobbyist or lobbyist.slug in seen_lobbyists:
            continue
        seen_lobbyists.add(lobbyist.slug)
        r_meta = rel.metadata_ or {}
        o_meta = official.metadata_ or {}
        l_meta = lobbyist.metadata_ or {}
        revolving_door.append({
            "lobbyist_name": lobbyist.name,
            "lobbyist_slug": lobbyist.slug,
            "former_position": (
                r_meta.get("former_position", l_meta.get("covered_position", ""))
                or ""
            )[:200],
            "current_employer": r_meta.get(
                "current_employer", l_meta.get("current_employer", "")
            ),
            "official_name": official.name,
            "official_slug": official.slug,
            "official_party": o_meta.get("party", ""),
            "official_state": o_meta.get("state", ""),
        })

    # Last precompute timestamp
    last_computed = None
    story_config = (await db.execute(
        select(AppConfig).where(AppConfig.key == "v2_story_feed")
    )).scalar_one_or_none()
    if story_config and story_config.updated_at:
        last_computed = story_config.updated_at.isoformat()

    return V2HomepageResponse(
        top_stories=top_stories,
        stats=stats,
        top_officials=top_officials,
        top_influencers=top_influencers,
        revolving_door=revolving_door,
        last_computed=last_computed,
    )
