"""
Refresh endpoint — re-fetches ALL data for an entity from live APIs.

Goes one level deep: if the entity has connections, refreshes those too.
"""

import asyncio
import logging
import os
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.models import Entity, Relationship
from app.services.ingestion.fec_client import FECClient

logger = logging.getLogger("refresh")
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/refresh", tags=["refresh"])

FEC_API_KEY = os.getenv("FEC_API_KEY", "")
FEC_TIMEOUT = 30.0
DELAY = 1.5


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _ascii_safe(obj):
    if isinstance(obj, str):
        return obj.encode("ascii", "replace").decode("ascii")
    if isinstance(obj, dict):
        return {k: _ascii_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ascii_safe(i) for i in obj]
    return obj


@router.post("/{slug}")
async def refresh_entity(slug: str, db: AsyncSession = Depends(get_db)):
    """Re-fetch ALL data for an entity from live APIs. Goes one level deep."""

    result = await db.execute(select(Entity).where(Entity.slug == slug))
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    meta = entity.metadata_ or {}
    entity_type = entity.entity_type
    actions = []

    # --- PERSON (official) ---
    if entity_type == "person" and meta.get("bioguide_id"):
        candidate_id = meta.get("fec_candidate_id", "")
        committee_id = meta.get("fec_committee_id", "")

        if not FEC_API_KEY:
            actions.append("skipped FEC — no API key")
        else:
            fec_client = FECClient(FEC_API_KEY)

            # 1. Resolve committee ID if missing
            if not committee_id and candidate_id:
                await asyncio.sleep(DELAY)
                try:
                    async with httpx.AsyncClient(timeout=FEC_TIMEOUT) as client:
                        resp = await client.get(
                            f"https://api.open.fec.gov/v1/candidate/{candidate_id}/committees/",
                            params={"api_key": FEC_API_KEY},
                        )
                        resp.raise_for_status()
                        committees = resp.json().get("results", [])
                        for c in committees:
                            if c.get("designation") == "P":
                                committee_id = c["committee_id"]
                                break
                        if not committee_id and committees:
                            committee_id = committees[0]["committee_id"]
                        if committee_id:
                            meta["fec_committee_id"] = committee_id
                            actions.append(f"resolved committee: {committee_id}")
                except Exception as e:
                    actions.append(f"committee lookup failed: {e}")

            # 2. Fetch ALL cycle totals
            best_receipts = 0
            best_cycle = None
            all_cycles = []
            for cycle in [2026, 2024, 2022, 2020, 2018]:
                await asyncio.sleep(DELAY)
                try:
                    totals = await fec_client.fetch_candidate_totals(candidate_id, cycle=cycle)
                    if totals and (totals.get("receipts", 0) or 0) > 0:
                        receipts = totals.get("receipts", 0) or 0
                        disbursements = totals.get("disbursements", 0) or 0
                        all_cycles.append({
                            "cycle": cycle,
                            "receipts": receipts,
                            "disbursements": disbursements,
                        })
                        if receipts > best_receipts:
                            best_receipts = receipts
                            best_cycle = cycle
                            meta["total_receipts"] = best_receipts
                            meta["total_disbursements"] = disbursements
                            meta["individual_contributions"] = totals.get("individual_contributions", 0)
                            meta["best_fec_cycle"] = best_cycle
                            meta["campaign_total"] = best_receipts
                except Exception:
                    continue
            if all_cycles:
                meta["fec_all_cycles"] = all_cycles
                actions.append(f"fetched {len(all_cycles)} FEC cycles")
            if best_cycle:
                actions.append(f"totals: ${best_receipts:,.0f} (cycle {best_cycle})")

            # 3. Fetch donors (2024 + 2022) — top by amount AND all PAC/committee donors
            if committee_id:
                new_donors = 0
                # Fetch both: top donors by amount + ALL PAC/committee donors
                fetch_configs = [
                    {"cycle": 2024, "per_page": 50, "params": {}},
                    {"cycle": 2022, "per_page": 50, "params": {}},
                    {"cycle": 2024, "per_page": 100, "params": {"contributor_type": "committee"}},
                    {"cycle": 2022, "per_page": 100, "params": {"contributor_type": "committee"}},
                    {"cycle": 2020, "per_page": 100, "params": {"contributor_type": "committee"}},
                ]
                for fc in fetch_configs:
                    await asyncio.sleep(DELAY)
                    try:
                        # Build params for FEC API
                        fec_params = {
                            "api_key": FEC_API_KEY,
                            "committee_id": committee_id,
                            "per_page": fc["per_page"],
                            "sort": "-contribution_receipt_amount",
                            "two_year_transaction_period": fc["cycle"],
                            **fc["params"],
                        }
                        async with httpx.AsyncClient(timeout=FEC_TIMEOUT) as client:
                            resp = await client.get(
                                "https://api.open.fec.gov/v1/schedules/schedule_a/",
                                params=fec_params,
                            )
                            resp.raise_for_status()
                            contributors = resp.json().get("results", [])
                        for donor in contributors:
                            donor_name = _ascii_safe(donor.get("contributor_name", "") or "")
                            if not donor_name or len(donor_name) < 2:
                                continue
                            donor_slug = _slugify(donor_name)
                            if not donor_slug:
                                continue

                            amount = donor.get("total", 0) or donor.get("contribution_receipt_amount", 0) or 0
                            name_upper = donor_name.upper()
                            is_pac = any(kw in name_upper for kw in [
                                "PAC", "FUND", "VICTORY", "COMMITTEE",
                            ])

                            donor_ent = (await db.execute(
                                select(Entity).where(Entity.slug == donor_slug)
                            )).scalar_one_or_none()
                            if not donor_ent:
                                donor_ent = Entity(
                                    slug=donor_slug,
                                    entity_type="pac" if is_pac else "person",
                                    name=donor_name,
                                    metadata_=_ascii_safe({"donor_type": "pac" if is_pac else "individual"}),
                                )
                                db.add(donor_ent)
                                await db.flush()

                            existing = (await db.execute(
                                select(Relationship).where(
                                    Relationship.from_entity_id == donor_ent.id,
                                    Relationship.to_entity_id == entity.id,
                                    Relationship.relationship_type == "donated_to",
                                ).limit(1)
                            )).scalar_one_or_none()
                            if not existing:
                                amount_cents = int(float(amount) * 100) if amount else 0
                                date_str = donor.get("contribution_receipt_date")
                                receipt_date = None
                                if date_str:
                                    try:
                                        receipt_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
                                    except (ValueError, TypeError):
                                        pass
                                db.add(Relationship(
                                    from_entity_id=donor_ent.id,
                                    to_entity_id=entity.id,
                                    relationship_type="donated_to",
                                    amount_usd=amount_cents,
                                    date_start=receipt_date,
                                    source_label="FEC",
                                ))
                                new_donors += 1
                    except Exception as e:
                        actions.append(f"donor fetch failed (cycle {fc['cycle']} {fc['params']}): {e}")
                if new_donors > 0:
                    actions.append(f"fetched {new_donors} new donors (incl. PAC/committee donors)")

        # 4. Clear cached briefing so it regenerates
        meta.pop("fbi_briefing", None)
        meta.pop("fbi_briefing_fingerprint", None)
        actions.append("cleared briefing cache")

        # 5. Update entity metadata
        meta["last_refreshed"] = datetime.now(timezone.utc).isoformat()
        entity.metadata_ = _ascii_safe(meta)
        db.add(entity)

        # 6. Refresh one level deep — fetch PAC donors for top PAC donors
        pac_donors = (await db.execute(
            select(Relationship, Entity)
            .join(Entity, Entity.id == Relationship.from_entity_id)
            .where(
                Relationship.to_entity_id == entity.id,
                Relationship.relationship_type == "donated_to",
                Entity.entity_type == "pac",
            )
            .order_by(Relationship.amount_usd.desc().nulls_last())
            .limit(3)
        )).all()

        for rel, pac_entity in pac_donors:
            pac_meta = pac_entity.metadata_ or {}
            pac_committee_id = pac_meta.get("fec_committee_id", "")
            # Check if PAC already has donors cached
            existing_pac_donors = (await db.execute(
                select(Relationship).where(
                    Relationship.to_entity_id == pac_entity.id,
                    Relationship.relationship_type == "donated_to",
                ).limit(1)
            )).scalar_one_or_none()
            if not existing_pac_donors and not pac_committee_id:
                # Search FEC for this PAC's committee ID
                await asyncio.sleep(DELAY)
                try:
                    async with httpx.AsyncClient(timeout=FEC_TIMEOUT) as client:
                        resp = await client.get(
                            "https://api.open.fec.gov/v1/committees/",
                            params={"api_key": FEC_API_KEY, "q": pac_entity.name, "per_page": 3},
                        )
                        resp.raise_for_status()
                        results = resp.json().get("results", [])
                        if results:
                            pac_committee_id = results[0]["committee_id"]
                            pac_meta["fec_committee_id"] = pac_committee_id
                            pac_entity.metadata_ = _ascii_safe(pac_meta)
                            db.add(pac_entity)
                except Exception:
                    pass

            if not existing_pac_donors and pac_committee_id:
                await asyncio.sleep(DELAY)
                try:
                    async with httpx.AsyncClient(timeout=FEC_TIMEOUT) as client:
                        resp = await client.get(
                            "https://api.open.fec.gov/v1/schedules/schedule_a/",
                            params={
                                "api_key": FEC_API_KEY,
                                "committee_id": pac_committee_id,
                                "per_page": 15,
                                "sort": "-contribution_receipt_amount",
                            },
                        )
                        resp.raise_for_status()
                        pac_fec_donors = resp.json().get("results", [])
                        pac_new = 0
                        for d in pac_fec_donors:
                            dname = _ascii_safe(d.get("contributor_name", "") or "")
                            if not dname or len(dname) < 2:
                                continue
                            dslug = _slugify(dname)
                            dent = (await db.execute(select(Entity).where(Entity.slug == dslug))).scalar_one_or_none()
                            if not dent:
                                dent = Entity(slug=dslug, entity_type="person", name=dname)
                                db.add(dent)
                                await db.flush()
                            amt = d.get("contribution_receipt_amount", 0) or 0
                            db.add(Relationship(
                                from_entity_id=dent.id,
                                to_entity_id=pac_entity.id,
                                relationship_type="donated_to",
                                amount_usd=int(amt * 100) if amt else 0,
                                source_label="FEC Schedule A",
                            ))
                            pac_new += 1
                        if pac_new:
                            actions.append(f"fetched {pac_new} donors for PAC {pac_entity.name[:30]}")
                except Exception:
                    pass

        # 7. Commit all data changes before computing verdicts
        await db.commit()

        # 8. Compute money trail verdicts (connect the dots)
        try:
            from app.services.verdict_engine import compute_verdicts, compute_overall_verdict
            from app.models import MoneyTrail
            trails = await compute_verdicts(db, entity.id)
            # Delete old trails and insert new ones
            old_trails = await db.execute(
                select(MoneyTrail).where(MoneyTrail.official_id == entity.id)
            )
            for old in old_trails.scalars().all():
                await db.delete(old)
            for trail in trails:
                db.add(MoneyTrail(
                    official_id=entity.id,
                    industry=trail["industry"],
                    verdict=trail["verdict"],
                    dot_count=trail["dot_count"],
                    narrative=trail.get("narrative"),
                    chain=trail.get("chain", {}),
                    total_amount=trail.get("total_amount", 0),
                ))
            overall_verdict, total_dots = compute_overall_verdict(trails)
            # Reload entity after commit
            result2 = await db.execute(select(Entity).where(Entity.id == entity.id))
            entity2 = result2.scalar_one_or_none()
            if entity2:
                m2 = dict(entity2.metadata_ or {})
                m2["v2_verdict"] = overall_verdict
                m2["v2_dot_count"] = total_dots
                entity2.metadata_ = _ascii_safe(m2)
                db.add(entity2)
            await db.commit()
            actions.append(f"computed {len(trails)} money trails → verdict: {overall_verdict} ({total_dots} dots)")
        except Exception as e:
            actions.append(f"verdict computation failed: {e}")

        # 9. Generate fresh AI briefing
        try:
            from app.services.ai_service import ai_briefing_service
            briefing = await ai_briefing_service.generate_briefing(
                entity_slug=slug,
                context_data={"metadata": meta},
                session=db,
                force_refresh=True,
            )
            actions.append(f"generated AI briefing ({len(briefing)} chars)")
        except Exception as e:
            actions.append(f"briefing generation failed: {e}")

    # --- PAC / ORGANIZATION / COMPANY ---
    elif entity_type in ("pac", "organization", "company"):
        # Fetch donors for this entity from FEC
        pac_committee_id = meta.get("fec_committee_id", "")
        if not pac_committee_id and FEC_API_KEY:
            await asyncio.sleep(DELAY)
            try:
                async with httpx.AsyncClient(timeout=FEC_TIMEOUT) as client:
                    resp = await client.get(
                        "https://api.open.fec.gov/v1/committees/",
                        params={"api_key": FEC_API_KEY, "q": entity.name, "per_page": 3},
                    )
                    resp.raise_for_status()
                    results = resp.json().get("results", [])
                    if results:
                        pac_committee_id = results[0]["committee_id"]
                        meta["fec_committee_id"] = pac_committee_id
                        actions.append(f"resolved committee: {pac_committee_id}")
            except Exception as e:
                actions.append(f"committee search failed: {e}")

        if pac_committee_id and FEC_API_KEY:
            await asyncio.sleep(DELAY)
            try:
                async with httpx.AsyncClient(timeout=FEC_TIMEOUT) as client:
                    resp = await client.get(
                        "https://api.open.fec.gov/v1/schedules/schedule_a/",
                        params={
                            "api_key": FEC_API_KEY,
                            "committee_id": pac_committee_id,
                            "per_page": 20,
                            "sort": "-contribution_receipt_amount",
                        },
                    )
                    resp.raise_for_status()
                    fec_donors = resp.json().get("results", [])
                    new_count = 0
                    for d in fec_donors:
                        dname = _ascii_safe(d.get("contributor_name", "") or "")
                        if not dname or len(dname) < 2:
                            continue
                        dslug = _slugify(dname)
                        dent = (await db.execute(select(Entity).where(Entity.slug == dslug))).scalar_one_or_none()
                        if not dent:
                            dent = Entity(slug=dslug, entity_type="person", name=dname,
                                         metadata_=_ascii_safe({"employer": d.get("contributor_employer", "")}))
                            db.add(dent)
                            await db.flush()
                        existing = (await db.execute(
                            select(Relationship).where(
                                Relationship.from_entity_id == dent.id,
                                Relationship.to_entity_id == entity.id,
                                Relationship.relationship_type == "donated_to",
                            ).limit(1)
                        )).scalar_one_or_none()
                        if not existing:
                            amt = d.get("contribution_receipt_amount", 0) or 0
                            db.add(Relationship(
                                from_entity_id=dent.id, to_entity_id=entity.id,
                                relationship_type="donated_to",
                                amount_usd=int(amt * 100) if amt else 0,
                                source_label="FEC Schedule A",
                            ))
                            new_count += 1
                    actions.append(f"fetched {new_count} donors")
            except Exception as e:
                actions.append(f"donor fetch failed: {e}")

        # Clear briefing cache
        meta.pop("fbi_briefing", None)
        meta.pop("fbi_briefing_fingerprint", None)
        meta["last_refreshed"] = datetime.now(timezone.utc).isoformat()
        entity.metadata_ = _ascii_safe(meta)
        db.add(entity)
        actions.append("cleared briefing cache")

    # --- BILL ---
    elif entity_type == "bill":
        # Re-enrich from Congress.gov
        bill_url = meta.get("url", "")
        if not bill_url:
            congress = meta.get("congress", "")
            bill_type = (meta.get("type", "") or "").lower()
            bill_number = meta.get("number", "") or meta.get("bill_number", "")
            if congress and bill_type and bill_number:
                bill_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}"

        congress_key = os.getenv("CONGRESS_GOV_API_KEY", "")
        if bill_url and congress_key:
            base_url = bill_url.split("?")[0]
            # Fetch bill detail
            await asyncio.sleep(DELAY)
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(base_url, params={"api_key": congress_key, "format": "json"})
                    resp.raise_for_status()
                    detail = resp.json().get("bill", {})
                    if detail.get("title"):
                        meta["full_title"] = _ascii_safe(detail["title"])[:1000]
                    if detail.get("legislationUrl"):
                        meta["congress_url"] = detail["legislationUrl"]
                    if detail.get("policyArea", {}).get("name"):
                        meta["policy_area"] = detail["policyArea"]["name"]
                    sponsors = detail.get("sponsors", [])
                    if sponsors:
                        meta["sponsors"] = _ascii_safe([{
                            "name": s.get("fullName", ""),
                            "bioguideId": s.get("bioguideId", ""),
                            "party": s.get("party", ""),
                            "state": s.get("state", ""),
                        } for s in sponsors[:10]])
                    la = detail.get("latestAction", {})
                    if la:
                        meta["status"] = _ascii_safe(la.get("text", ""))[:500]
                    actions.append("refreshed bill detail")
            except Exception as e:
                actions.append(f"bill detail failed: {e}")

            # Fetch summary
            await asyncio.sleep(DELAY)
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(f"{base_url}/summaries", params={"api_key": congress_key, "format": "json"})
                    resp.raise_for_status()
                    summaries = resp.json().get("summaries", [])
                    if summaries:
                        import re as _re
                        text = _re.sub(r"<[^>]+>", "", summaries[-1].get("text", "")).strip()
                        if text:
                            meta["crs_summary"] = _ascii_safe(text)[:5000]
                            meta["official_summary"] = meta["crs_summary"]
                            sentences = _re.split(r'(?<=[.!?])\s+', text)
                            meta["tldr"] = _ascii_safe(" ".join(sentences[:3]))[:500]
                            entity.summary = _ascii_safe(text)[:2000]
                            actions.append("refreshed CRS summary")
            except Exception:
                pass

            # Fetch text URLs
            await asyncio.sleep(DELAY)
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(f"{base_url}/text", params={"api_key": congress_key, "format": "json"})
                    resp.raise_for_status()
                    versions = resp.json().get("textVersions", [])
                    if versions:
                        for fmt in versions[0].get("formats", []):
                            ft = (fmt.get("type") or "").lower()
                            if "html" in ft or "formatted text" in ft:
                                meta["full_text_url"] = fmt["url"]
                                break
                        actions.append("refreshed text URL")
            except Exception:
                pass

        meta.pop("fbi_briefing", None)
        meta.pop("fbi_briefing_fingerprint", None)
        meta["enriched_at"] = datetime.now(timezone.utc).isoformat()
        meta["last_refreshed"] = datetime.now(timezone.utc).isoformat()
        entity.metadata_ = _ascii_safe(meta)
        db.add(entity)
        actions.append("cleared briefing cache")

    else:
        meta.pop("fbi_briefing", None)
        meta.pop("fbi_briefing_fingerprint", None)
        meta["last_refreshed"] = datetime.now(timezone.utc).isoformat()
        entity.metadata_ = _ascii_safe(meta)
        db.add(entity)
        actions.append("cleared briefing cache")

    await db.commit()

    return {
        "slug": slug,
        "entity_type": entity_type,
        "actions": actions,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
    }
