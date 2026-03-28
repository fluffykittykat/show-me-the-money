"""
Bill Baselines — Per-policy-area baseline rates for influence signals.

Computes how common each signal pattern is across all bills in a policy area,
so we can say "this pattern occurs in X% of agriculture bills."
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict

from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entity, Relationship, AppConfig

log = logging.getLogger(__name__)

SAMPLE_LIMIT = 500  # Max bills per policy area to keep computation tractable


async def compute_baselines(session: AsyncSession) -> dict[str, dict]:
    """Compute baseline rates per policy area.

    Returns: {
        "Agriculture and Food": {
            "lobby_donate_rate": 0.02,
            "timing_90d_avg": 1.2,
            "timing_spike": 1.2,
            "total_bills": 842,
        },
        ...
    }

    Also stores the result in app_config with key "bill_baselines".
    """
    log.info("Computing bill baselines per policy area...")

    # Step 1: Get all bill entities grouped by policy_area
    q = (
        select(
            Entity.metadata_["policy_area"].astext.label("policy_area"),
            func.count(Entity.id).label("total"),
        )
        .where(Entity.entity_type == "bill")
        .where(Entity.metadata_["policy_area"].astext != "")
        .where(Entity.metadata_["policy_area"].astext.isnot(None))
        .group_by(Entity.metadata_["policy_area"].astext)
    )
    result = await session.execute(q)
    area_counts = {row.policy_area: row.total for row in result.all()}

    log.info("Found %d policy areas across bills", len(area_counts))

    baselines: dict[str, dict] = {}

    for policy_area, total_count in area_counts.items():
        if not policy_area:
            continue

        log.info("Processing policy area: %s (%d bills)", policy_area, total_count)

        # Get sample of bill IDs in this policy area
        bill_q = (
            select(Entity.id)
            .where(Entity.entity_type == "bill")
            .where(Entity.metadata_["policy_area"].astext == policy_area)
            .limit(SAMPLE_LIMIT)
        )
        bill_result = await session.execute(bill_q)
        bill_ids = [row[0] for row in bill_result.all()]

        if not bill_ids:
            continue

        # Step 2b: Count bills with lobby+donate overlap
        # A bill has lobby_donate if: entity lobbied_on bill AND same entity donated_to a sponsor
        lobby_donate_count = 0
        timing_total = 0

        for bill_id in bill_ids:
            # Get sponsors of this bill
            sponsor_q = (
                select(Relationship.from_entity_id)
                .where(Relationship.to_entity_id == bill_id)
                .where(Relationship.relationship_type.in_(["sponsored", "cosponsored"]))
            )
            sponsor_result = await session.execute(sponsor_q)
            sponsor_ids = [row[0] for row in sponsor_result.all()]

            if not sponsor_ids:
                continue

            # Get lobby clients for this bill
            lobby_q = (
                select(Relationship.from_entity_id)
                .where(Relationship.to_entity_id == bill_id)
                .where(Relationship.relationship_type == "lobbied_on")
            )
            lobby_result = await session.execute(lobby_q)
            lobby_client_ids = {row[0] for row in lobby_result.all()}

            if lobby_client_ids:
                # Check if any lobby client also donated to a sponsor
                donor_q = (
                    select(func.count())
                    .select_from(Relationship)
                    .where(Relationship.from_entity_id.in_(lobby_client_ids))
                    .where(Relationship.to_entity_id.in_(sponsor_ids))
                    .where(Relationship.relationship_type == "donated_to")
                )
                donor_result = await session.execute(donor_q)
                donor_count = donor_result.scalar() or 0
                if donor_count > 0:
                    lobby_donate_count += 1

            # Step 2c: Count donated_to relationships to sponsors within 90 days
            timing_q = (
                select(func.count())
                .select_from(Relationship)
                .where(Relationship.to_entity_id.in_(sponsor_ids))
                .where(Relationship.relationship_type == "donated_to")
                .where(Relationship.date_start.isnot(None))
            )
            timing_result = await session.execute(timing_q)
            timing_total += timing_result.scalar() or 0

        sampled = len(bill_ids)
        lobby_donate_rate = lobby_donate_count / sampled if sampled > 0 else 0.0
        timing_90d_avg = timing_total / sampled if sampled > 0 else 1.2

        # Ensure timing baseline is at least 0.1 to avoid division by zero
        timing_90d_avg = max(timing_90d_avg, 0.1)

        baselines[policy_area] = {
            "lobby_donate_rate": round(lobby_donate_rate, 6),
            "timing_90d_avg": round(timing_90d_avg, 2),
            "timing_spike": round(timing_90d_avg, 2),  # alias used by bill_signals
            "total_bills": total_count,
            "sampled_bills": sampled,
        }

        # Also store lowercase key for easy lookup
        baselines[policy_area.lower().strip()] = baselines[policy_area]

        log.info(
            "  %s: lobby_donate_rate=%.4f, timing_90d_avg=%.2f, sampled=%d/%d",
            policy_area, lobby_donate_rate, timing_90d_avg, sampled, total_count,
        )

    # Step 3: Store in app_config
    config_q = select(AppConfig).where(AppConfig.key == "bill_baselines")
    config_result = await session.execute(config_q)
    config_row = config_result.scalar_one_or_none()

    baselines_json = json.dumps(baselines)

    if config_row:
        config_row.value = baselines_json
        config_row.is_secret = False
    else:
        session.add(AppConfig(
            key="bill_baselines",
            value=baselines_json,
            description="Per-policy-area baseline rates for bill influence signals",
            is_secret=False,
        ))

    log.info("Bill baselines computed for %d policy areas, stored in app_config", len(area_counts))
    return baselines
