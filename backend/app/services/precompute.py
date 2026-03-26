"""
Pre-Compute Background Job — Verdict Engine + AI Briefings

Runs the verdict engine for ALL officials, stores results in money_trails,
and pre-generates AI briefings so the frontend loads instantly.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.database import async_session
from app.models import AppConfig, Entity, IngestionJob, MoneyTrail, Relationship
from app.services.verdict_engine import compute_overall_verdict, compute_verdicts

logger = logging.getLogger(__name__)


def _to_int(value) -> int:
    """Coerce Decimal/float/None to int for JSON serialization."""
    if value is None:
        return 0
    if isinstance(value, Decimal):
        return int(value)
    return int(value)


def _format_amount(cents: int) -> str:
    """Format cents as a human-readable dollar string."""
    dollars = cents / 100
    if dollars >= 1_000_000:
        return f"${dollars / 1_000_000:,.1f}M"
    if dollars >= 1_000:
        return f"${dollars / 1_000:,.0f}K"
    return f"${dollars:,.0f}"


def _json_default(obj):
    """Custom JSON serializer for types json module can't handle."""
    if isinstance(obj, Decimal):
        return int(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


async def _build_story_feed(session: AsyncSession) -> list[dict]:
    """Build the homepage story feed from pre-computed money trails.

    Selects the most interesting trails across all officials:
    1. All OWNED officials (multi-industry capture) — headline stories
    2. Top INFLUENCED trails by total amount — biggest money
    3. Biggest middleman chains (PACs funneling the most money)
    4. Revolving door highlights (former staffers now lobbying)

    Returns list of 10-15 stories, sorted by importance.
    """
    stories: list[dict] = []
    seen_official_ids: set[str] = set()

    # ── 1. OWNED stories ─────────────────────────────────────────────
    # One story per official who is OWNED, showing their top industries
    owned_q = (
        select(MoneyTrail, Entity)
        .join(Entity, MoneyTrail.official_id == Entity.id)
        .where(MoneyTrail.verdict == "OWNED")
        .order_by(MoneyTrail.dot_count.desc(), MoneyTrail.total_amount.desc())
    )
    result = await session.execute(owned_q)
    owned_rows = result.all()

    # Group by official
    owned_by_official: dict[str, dict] = {}
    for trail, official in owned_rows:
        oid = str(official.id)
        if oid not in owned_by_official:
            owned_by_official[oid] = {
                "official": official,
                "industries": [],
                "total_amount": 0,
                "max_dots": 0,
            }
        owned_by_official[oid]["industries"].append(trail.industry)
        owned_by_official[oid]["total_amount"] += _to_int(trail.total_amount)
        owned_by_official[oid]["max_dots"] = max(
            owned_by_official[oid]["max_dots"], trail.dot_count
        )

    # Sort by max dot count desc, then total amount desc
    sorted_owned = sorted(
        owned_by_official.values(),
        key=lambda x: (x["max_dots"], x["total_amount"]),
        reverse=True,
    )

    for entry in sorted_owned[:5]:
        off = entry["official"]
        meta = off.metadata_ or {}
        party = meta.get("party", "")
        industries_str = ", ".join(entry["industries"][:3])
        if len(entry["industries"]) > 3:
            industries_str += f" +{len(entry['industries']) - 3} more"

        stories.append({
            "story_type": "owned",
            "headline": f"{off.name} OWNED by {industries_str}",
            "narrative": (
                f"{off.name} ({party}) received "
                f"{_format_amount(entry['total_amount'])} across "
                f"{len(entry['industries'])} industries with verdict OWNED."
            ),
            "verdict": "OWNED",
            "officials": [{"name": off.name, "slug": off.slug, "party": party}],
            "total_amount": entry["total_amount"],
            "industry": entry["industries"][0] if entry["industries"] else "",
        })
        seen_official_ids.add(str(off.id))

    # ── 2. INFLUENCED stories ────────────────────────────────────────
    influenced_q = (
        select(MoneyTrail, Entity)
        .join(Entity, MoneyTrail.official_id == Entity.id)
        .where(MoneyTrail.verdict == "INFLUENCED")
        .order_by(MoneyTrail.total_amount.desc())
    )
    result = await session.execute(influenced_q)
    influenced_rows = result.all()

    influenced_count = 0
    for trail, official in influenced_rows:
        if influenced_count >= 5:
            break
        oid = str(official.id)
        if oid in seen_official_ids:
            continue

        meta = official.metadata_ or {}
        party = meta.get("party", "")

        stories.append({
            "story_type": "influenced",
            "headline": (
                f"{trail.industry} → {official.name}: "
                f"{_format_amount(trail.total_amount)}"
            ),
            "narrative": trail.narrative or (
                f"{official.name} ({party}) received "
                f"{_format_amount(trail.total_amount)} from "
                f"the {trail.industry} industry."
            ),
            "verdict": "INFLUENCED",
            "officials": [{"name": official.name, "slug": official.slug, "party": party}],
            "total_amount": _to_int(trail.total_amount),
            "industry": trail.industry,
        })
        seen_official_ids.add(oid)
        influenced_count += 1

    # ── 3. Middleman stories (PACs funneling money) ──────────────────
    # Find PAC entities that have both incoming and outgoing donated_to
    pac_from = aliased(Relationship)
    pac_to = aliased(Relationship)
    pac_entity = aliased(Entity)

    middleman_q = (
        select(
            pac_entity.name,
            pac_entity.slug,
            func.sum(pac_from.amount_usd).label("inflow"),
            func.count(func.distinct(pac_to.to_entity_id)).label("recipient_count"),
        )
        .select_from(pac_entity)
        .join(pac_from, pac_from.to_entity_id == pac_entity.id)
        .join(pac_to, pac_to.from_entity_id == pac_entity.id)
        .where(pac_entity.entity_type == "pac")
        .where(pac_from.relationship_type == "donated_to")
        .where(pac_to.relationship_type == "donated_to")
        .group_by(pac_entity.id, pac_entity.name, pac_entity.slug)
        .having(func.count(func.distinct(pac_to.to_entity_id)) > 1)
        .order_by(func.sum(pac_from.amount_usd).desc().nulls_last())
        .limit(3)
    )
    result = await session.execute(middleman_q)
    middleman_rows = result.all()

    for row in middleman_rows:
        pac_name, pac_slug, inflow, recipient_count = row
        inflow_val = _to_int(inflow)
        stories.append({
            "story_type": "middleman",
            "headline": f"{pac_name} funneled money to {recipient_count} officials",
            "narrative": (
                f"{pac_name} received {_format_amount(inflow_val)} in donations "
                f"and distributed funds to {recipient_count} officials."
            ),
            "verdict": "MIDDLEMAN",
            "officials": [],
            "total_amount": inflow_val,
            "industry": "",
        })

    # ── 4. Revolving door stories ────────────────────────────────────
    rd_rel_q = (
        select(Relationship)
        .where(Relationship.relationship_type == "revolving_door_lobbyist")
        .order_by(Relationship.amount_usd.desc().nulls_last())
        .limit(3)
    )
    result = await session.execute(rd_rel_q)
    rd_rels = result.scalars().all()

    for rel in rd_rels:
        # Load from/to entities
        from_ent = await session.get(Entity, rel.from_entity_id)
        to_ent = await session.get(Entity, rel.to_entity_id)
        if not from_ent or not to_ent:
            continue

        stories.append({
            "story_type": "revolving_door",
            "headline": f"{from_ent.name} → lobbyist for {to_ent.name}",
            "narrative": (
                f"{from_ent.name} is now lobbying for {to_ent.name}"
                + (f" ({_format_amount(rel.amount_usd)})" if rel.amount_usd else "")
                + "."
            ),
            "verdict": "REVOLVING_DOOR",
            "officials": [{"name": to_ent.name, "slug": to_ent.slug, "party": ""}],
            "total_amount": _to_int(rel.amount_usd),
            "industry": "",
        })

    # ── Sort: OWNED first, then INFLUENCED by amount, middleman, revolving door
    type_order = {"owned": 0, "influenced": 1, "middleman": 2, "revolving_door": 3}
    stories.sort(
        key=lambda s: (type_order.get(s["story_type"], 99), -s["total_amount"])
    )

    # Cap at 15 stories
    stories = stories[:15]

    # ── Store in app_config ──────────────────────────────────────────
    existing = await session.get(AppConfig, "v2_story_feed")
    if existing:
        existing.value = json.dumps(stories, default=_json_default)
        existing.is_secret = False
        existing.updated_at = datetime.now(timezone.utc)
    else:
        config = AppConfig(
            key="v2_story_feed",
            value=json.dumps(stories, default=_json_default),
            is_secret=False,
        )
        session.add(config)
    await session.commit()

    return stories


async def run_precompute(force: bool = False) -> str:
    """Pre-compute verdicts + briefings for all officials.

    Steps:
    1. Load all officials with bioguide_id
    2. For each: run verdict_engine.compute_verdicts()
    3. Store results in money_trails table (delete old, insert new per official)
    4. Compute overall verdict and store in entity metadata as 'v2_verdict' and 'v2_dot_count'
    5. Pre-generate AI briefing if not cached (or force=True)
    6. Track progress via IngestionJob (job_type="precompute")
    """
    async with async_session() as session:
        # ── Create tracking job ──────────────────────────────────────
        job = IngestionJob(
            id=uuid.uuid4(),
            job_type="precompute",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.commit()

        # ── Load all officials with bioguide_id ──────────────────────
        officials_q = (
            select(Entity)
            .where(Entity.entity_type == "person")
        )
        result = await session.execute(officials_q)
        officials = result.scalars().all()

        # Filter to those with bioguide_id in metadata
        officials = [
            o for o in officials
            if (o.metadata_ or {}).get("bioguide_id")
        ]

        total = len(officials)
        job.total = total
        await session.commit()

        logger.info("Precompute started: %d officials to process", total)

        errors: list[dict] = []
        processed = 0

        for i, official in enumerate(officials, 1):
            try:
                # ── Step 2: Compute verdicts ─────────────────────────
                trails = await compute_verdicts(session, official.id)

                # ── Step 3: Store in money_trails table ──────────────
                # Delete old trails for this official
                await session.execute(
                    delete(MoneyTrail).where(
                        MoneyTrail.official_id == official.id
                    )
                )

                # Insert new trails
                now = datetime.now(timezone.utc)
                for trail in trails:
                    mt = MoneyTrail(
                        id=uuid.uuid4(),
                        official_id=official.id,
                        industry=trail["industry"],
                        verdict=trail["verdict"],
                        dot_count=trail["dot_count"],
                        narrative=trail.get("narrative"),
                        chain={**trail.get("chain", {}), "donor_count": trail.get("donor_count", 0)},
                        total_amount=trail.get("total_amount", 0),
                        computed_at=now,
                    )
                    session.add(mt)

                # ── Step 4: Compute overall verdict ──────────────────
                overall_verdict, total_dots = compute_overall_verdict(trails)
                meta = dict(official.metadata_ or {})
                meta["v2_verdict"] = overall_verdict
                meta["v2_dot_count"] = total_dots
                meta["last_refreshed"] = datetime.now(timezone.utc).isoformat()
                official.metadata_ = meta

                await session.commit()

                # ── Step 5: Pre-generate AI briefing ─────────────────
                try:
                    cached_briefing = (official.metadata_ or {}).get("fbi_briefing")
                    if force or not cached_briefing:
                        from app.services.ai_service import ai_briefing_service

                        await ai_briefing_service.generate_briefing(
                            entity_slug=official.slug,
                            context_data={},
                            session=session,
                            force_refresh=force,
                        )
                except Exception as briefing_err:
                    logger.warning(
                        "Briefing generation failed for %s: %s",
                        official.slug,
                        briefing_err,
                    )

                processed += 1

            except Exception as exc:
                logger.error(
                    "Precompute failed for %s: %s", official.slug, exc
                )
                errors.append({
                    "slug": official.slug,
                    "error": str(exc),
                })
                # Rollback the failed transaction and continue
                await session.rollback()

            # ── Update progress ──────────────────────────────────────
            if i % 25 == 0 or i == total:
                logger.info(
                    "Precompute progress: %d/%d (%d errors)",
                    i,
                    total,
                    len(errors),
                )
                try:
                    job.progress = i
                    job.errors = errors
                    await session.commit()
                except Exception:
                    await session.rollback()

        # ── Mark job complete ────────────────────────────────────────
        try:
            job.status = "completed"
            job.progress = total
            job.completed_at = datetime.now(timezone.utc)
            job.errors = errors
            job.metadata_ = {
                "processed": processed,
                "errors_count": len(errors),
                "force": force,
            }
            await session.commit()
        except Exception:
            await session.rollback()

        # ── Build homepage story feed ──────────────────────────────────
        try:
            feed_stories = await _build_story_feed(session)
            logger.info("Story feed built: %d stories", len(feed_stories))
        except Exception as feed_err:
            logger.error("Story feed generation failed: %s", feed_err)

        summary = (
            f"Precompute complete: {processed}/{total} officials, "
            f"{len(errors)} errors"
        )
        logger.info(summary)
        return summary
