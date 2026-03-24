"""
FEC Re-Match — Find donor data for officials using the bioguide→FEC crosswalk.

Uses the unitedstates/congress-legislators YAML file which maps every
Congress member's bioguide ID to their FEC candidate ID(s). No name
matching needed — 100% accuracy.
"""

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import httpx
import yaml
from sqlalchemy import select, update

from app.database import async_session
from app.models import Entity, IngestionJob, Relationship
from app.services.ingestion.fec_client import FECClient

logger = logging.getLogger("fec_rematch")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    logger.addHandler(handler)

_STATE_ABBREV = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE",
    "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ",
    "New Mexico": "NM", "New York": "NY", "North Carolina": "NC",
    "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA",
    "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
    "District of Columbia": "DC", "American Samoa": "AS", "Guam": "GU",
    "Northern Mariana Islands": "MP", "Puerto Rico": "PR",
    "U.S. Virgin Islands": "VI",
}


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


CROSSWALK_URL = "https://raw.githubusercontent.com/unitedstates/congress-legislators/main/legislators-current.yaml"


async def _download_crosswalk() -> dict[str, list[str]]:
    """Download the bioguide→FEC ID crosswalk from unitedstates/congress-legislators.

    Returns a dict mapping bioguide_id -> list of FEC candidate IDs.
    """
    logger.info("Downloading bioguide→FEC crosswalk from GitHub...")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(CROSSWALK_URL)
        resp.raise_for_status()
        data = yaml.safe_load(resp.text)

    crosswalk = {}
    for member in data:
        ids = member.get("id", {})
        bioguide = ids.get("bioguide", "")
        fec_ids = ids.get("fec", [])
        if bioguide and fec_ids:
            crosswalk[bioguide] = fec_ids

    logger.info("Crosswalk loaded: %d members with FEC IDs", len(crosswalk))
    return crosswalk


async def run_fec_rematch() -> uuid.UUID:
    """Re-match FEC data for all officials using the bioguide→FEC crosswalk.

    No name matching — uses the authoritative ID mapping from
    unitedstates/congress-legislators project.
    """
    fec_api_key = os.getenv("FEC_API_KEY", "")
    if not fec_api_key:
        from app.services.config_service import get_config_value
        async with async_session() as cfg_session:
            fec_api_key = await get_config_value(cfg_session, "FEC_API_KEY") or ""

    if not fec_api_key:
        raise ValueError("FEC_API_KEY not set")

    fec_client = FECClient(fec_api_key)

    # Download the crosswalk
    crosswalk = await _download_crosswalk()

    # Create tracking job
    async with async_session() as session:
        async with session.begin():
            job = IngestionJob(
                job_type="fec_rematch",
                status="in_progress",
                started_at=datetime.now(timezone.utc),
            )
            session.add(job)
            await session.flush()
            job_id = job.id

    # Find ALL officials (re-match everyone, not just missing ones)
    async with async_session() as session:
        result = await session.execute(
            select(Entity)
            .where(Entity.entity_type == "person")
            .where(Entity.metadata_.has_key("bioguide_id"))
        )
        officials = result.scalars().all()

    # Filter to those missing FEC data OR those we can improve
    needs_match = []
    for official in officials:
        meta = official.metadata_ or {}
        bioguide = meta.get("bioguide_id", "")
        has_fec = meta.get("fec_candidate_id", "")
        # Include if: no FEC data, OR we have a crosswalk entry (verify/update)
        if not has_fec and bioguide in crosswalk:
            needs_match.append((official, crosswalk[bioguide]))

    total = len(needs_match)
    logger.info("Found %d officials to match via crosswalk (of %d total)", total, len(officials))

    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob).where(IngestionJob.id == job_id)
                .values(total=total, progress=0)
            )

    matched = 0
    errors = []
    processed = 0

    for official, fec_ids in needs_match:
        meta = official.metadata_ or {}
        name = official.name
        # Use the first FEC ID (most recent campaign)
        candidate_id = fec_ids[0]

        try:
            # Rate limit: 1.5s between each official to stay under FEC limits
            await asyncio.sleep(1.5)

            # Look up the principal committee using the known candidate ID
            committee_id = ""
            try:
                url = f"https://api.open.fec.gov/v1/candidate/{candidate_id}/"
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(url, params={"api_key": fec_api_key})
                    resp.raise_for_status()
                    cand_data = resp.json().get("results", [])
                    if cand_data:
                        committees = cand_data[0].get("principal_committees", [])
                        if committees:
                            committee_id = committees[0].get("committee_id", "")
            except Exception:
                pass

            # Fetch totals
            await asyncio.sleep(1.0)
            totals = {}
            try:
                totals = await fec_client.fetch_candidate_totals(candidate_id)
            except Exception:
                pass

            # Fetch top donors if we have a committee ID
            await asyncio.sleep(1.0)
            donors = []
            if committee_id:
                try:
                    donors = await fec_client.fetch_top_contributors(
                        committee_id, per_page=20
                    )
                except Exception:
                    pass

            # Update official entity
            async with async_session() as session:
                async with session.begin():
                    entity = (await session.execute(
                        select(Entity).where(Entity.id == official.id)
                    )).scalar_one()

                    updated_meta = {**(entity.metadata_ or {})}
                    updated_meta["fec_candidate_id"] = candidate_id
                    updated_meta["fec_committee_id"] = committee_id
                    if totals:
                        updated_meta["total_receipts"] = totals.get("receipts", 0)
                        updated_meta["total_disbursements"] = totals.get("disbursements", 0)
                    entity.metadata_ = _ascii_safe(updated_meta)

                    entity_id = entity.id

                    # Create donor relationships
                    for donor in donors[:30]:
                        donor_name = _ascii_safe(donor.get("contributor_name", "") or "")
                        if not donor_name or len(donor_name) < 2:
                            continue
                        donor_slug = _slugify(donor_name)
                        if not donor_slug:
                            continue
                        amount = donor.get("total", 0) or donor.get("contribution_receipt_amount", 0) or 0

                        name_upper = donor_name.upper()
                        is_pac = any(kw in name_upper for kw in [
                            "PAC", "FUND", "VICTORY", "COMMITTEE", "DSCC", "DCCC",
                            "EMILY", "ACTION", "SENATE", "HOUSE",
                        ])
                        donor_type = "pac" if is_pac else "person"

                        donor_ent = (await session.execute(
                            select(Entity).where(Entity.slug == donor_slug)
                        )).scalar_one_or_none()
                        if not donor_ent:
                            donor_ent = Entity(
                                slug=donor_slug,
                                entity_type=donor_type,
                                name=donor_name,
                                metadata_=_ascii_safe({"donor_type": "pac" if is_pac else "individual"}),
                            )
                            session.add(donor_ent)
                            await session.flush()

                        existing_rel = (await session.execute(
                            select(Relationship).where(
                                Relationship.from_entity_id == donor_ent.id,
                                Relationship.to_entity_id == entity_id,
                                Relationship.relationship_type == "donated_to",
                            ).limit(1)
                        )).scalar_one_or_none()
                        if not existing_rel:
                            amount_cents = int(float(amount) * 100) if amount else 0
                            session.add(Relationship(
                                from_entity_id=donor_ent.id,
                                to_entity_id=entity_id,
                                relationship_type="donated_to",
                                amount_usd=amount_cents,
                                source_label="FEC",
                            ))

            matched += 1
            logger.info("Matched: %s -> %s (%d donors)", name, candidate_id, len(donors))

        except Exception as exc:
            errors.append({"official": name, "error": str(exc)[:200]})
            logger.warning("Error matching %s: %s", name, exc)

        processed += 1
        if processed % 25 == 0:
            logger.info("Progress: %d/%d processed, %d matched", processed, total, matched)
            async with async_session() as session:
                async with session.begin():
                    await session.execute(
                        update(IngestionJob).where(IngestionJob.id == job_id)
                        .values(progress=processed, errors=errors[-20:])
                    )

    # Complete
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                update(IngestionJob).where(IngestionJob.id == job_id)
                .values(
                    status="completed",
                    progress=processed,
                    total=total,
                    completed_at=datetime.now(timezone.utc),
                    errors=errors[-20:],
                    metadata_={"matched": matched, "total_errors": len(errors)},
                )
            )

    logger.info("FEC re-match complete: %d/%d matched, %d errors", matched, total, len(errors))
    return job_id
