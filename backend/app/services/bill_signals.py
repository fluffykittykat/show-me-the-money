"""
Bill Signals Engine — 5 Statistical Influence Detectors

Computes five correlation signals for any bill:

1. lobby_donate   (STRONGEST) — Entity lobbied on bill AND donated to sponsor
2. timing_spike   — Same-industry donations spiked before bill introduction
3. committee_overlap — Sponsor sits on committee with jurisdiction
4. stock_trade    — Sponsor traded stocks in affected companies near intro date
5. revolving_door — Former staffer now lobbies on bill's policy area
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entity, Relationship
from app.services.conflict_engine import (
    _extract_industry_keywords,
    _industries_for_committee,
    _keyword_overlap,
    _sanitize,
)
from app.services.verdict_engine import _industry_keywords_for_policy_area

try:
    from scipy.stats import poisson  # type: ignore
except ImportError:
    poisson = None

log = logging.getLogger(__name__)

PLATFORM_PACS = {"winred", "actblue", "anedot"}


# ── Helpers ───────────────────────────────────────────────────────────────


def _slug_words(name: str) -> list[str]:
    """Extract significant words from an entity name for fuzzy matching."""
    stopwords = {
        "the", "of", "for", "and", "inc", "llc", "corp", "corporation",
        "pac", "political", "action", "committee", "fund", "association",
    }
    words = re.sub(r"[^a-z0-9\s]", "", name.lower()).split()
    return [w for w in words if w not in stopwords and len(w) > 2]


def _names_match(client_name: str, donor_slug: str) -> bool:
    """Fuzzy check: does the donor slug contain significant words from client?"""
    words = _slug_words(client_name)
    if not words:
        return False
    slug_lower = donor_slug.lower()
    # Require at least the first significant word to appear in the slug
    return words[0] in slug_lower


def _is_platform_pac(slug: str) -> bool:
    """Check if entity is a platform PAC (WinRed, ActBlue, etc)."""
    slug_lower = slug.lower()
    return any(p in slug_lower for p in PLATFORM_PACS)


def _fmt_amount(cents: int | None) -> str:
    """Format cents as human-readable dollar string."""
    if not cents:
        return "$0"
    dollars = cents / 100
    if dollars >= 1_000_000:
        return f"${dollars / 1_000_000:.1f}M"
    if dollars >= 1_000:
        return f"${dollars / 1_000:.0f}K"
    return f"${dollars:,.0f}"


# ── Data loading helpers ──────────────────────────────────────────────────


async def _get_bill_entity(session: AsyncSession, bill_id: uuid.UUID) -> Entity | None:
    result = await session.execute(select(Entity).where(Entity.id == bill_id))
    return result.scalar_one_or_none()


async def _get_sponsors(
    session: AsyncSession, bill_id: uuid.UUID
) -> list[tuple[Relationship, Entity]]:
    """Get sponsors/cosponsors: relationship from official TO bill."""
    q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.to_entity_id == bill_id)
        .where(Relationship.relationship_type.in_(["sponsored", "cosponsored"]))
    )
    result = await session.execute(q)
    return list(result.all())


async def _get_lobby_clients(
    session: AsyncSession, bill_id: uuid.UUID
) -> list[tuple[Relationship, Entity]]:
    """Get lobbying relationships: client lobbied_on bill."""
    q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.to_entity_id == bill_id)
        .where(Relationship.relationship_type == "lobbied_on")
    )
    result = await session.execute(q)
    return list(result.all())


async def _get_donations_to(
    session: AsyncSession, official_id: uuid.UUID
) -> list[tuple[Relationship, Entity]]:
    """Get all donated_to relationships targeting an official."""
    q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.to_entity_id == official_id)
        .where(Relationship.relationship_type == "donated_to")
    )
    result = await session.execute(q)
    return list(result.all())


# ── Signal 1: lobby_donate ───────────────────────────────────────────────


async def _signal_lobby_donate(
    session: AsyncSession,
    bill_id: uuid.UUID,
    bill_entity: Entity,
    sponsors: list[tuple[Relationship, Entity]],
) -> dict:
    """Did any entity BOTH lobby for this bill AND donate to its sponsors?"""
    signal = {
        "signal_type": "lobby_donate",
        "found": False,
        "confidence": None,
        "rarity_pct": None,
        "rarity_label": None,
        "p_value": None,
        "baseline_rate": None,
        "observed_rate": None,
        "description": "",
        "evidence": {},
    }

    # Get lobby clients for this bill
    lobby_data = await _get_lobby_clients(session, bill_id)
    if not lobby_data:
        signal["description"] = "No lobbying relationships found for this bill."
        return signal

    sponsor_ids = {ent.id for _, ent in sponsors}
    sponsor_names = {ent.id: _sanitize(ent.name) for _, ent in sponsors}

    matches: list[dict] = []

    for lobby_rel, client_entity in lobby_data:
        client_name = _sanitize(client_entity.name)
        lobby_meta = lobby_rel.metadata_ or {}
        filing_url = lobby_rel.source_url or lobby_meta.get("filing_url", "")

        # For each sponsor, check if this client (or related PAC) donated
        for sponsor_id in sponsor_ids:
            donations = await _get_donations_to(session, sponsor_id)
            for don_rel, donor_entity in donations:
                # Direct match (same entity) or name/slug fuzzy match
                is_match = (
                    donor_entity.id == client_entity.id
                    or _names_match(client_name, donor_entity.slug)
                )
                if is_match:
                    matches.append({
                        "lobby_client": client_name,
                        "donor": _sanitize(donor_entity.name),
                        "donor_slug": donor_entity.slug,
                        "sponsor": sponsor_names.get(sponsor_id, "Unknown"),
                        "donation_amount": don_rel.amount_usd or 0,
                        "donation_amount_fmt": _fmt_amount(don_rel.amount_usd),
                        "filing_url": filing_url,
                        "donation_date": (
                            don_rel.date_start.isoformat()
                            if don_rel.date_start
                            else None
                        ),
                    })

    if matches:
        signal["found"] = True
        signal["confidence"] = "high"
        signal["rarity_label"] = "Rare"
        total = sum(m["donation_amount"] for m in matches)
        unique_clients = {m["lobby_client"] for m in matches}
        signal["description"] = (
            f"{len(unique_clients)} entit{'y' if len(unique_clients) == 1 else 'ies'} "
            f"lobbied on this bill AND donated {_fmt_amount(total)} to its sponsors."
        )
        signal["evidence"] = {"matches": matches}
    else:
        signal["description"] = (
            f"{len(lobby_data)} entities lobbied on this bill but none "
            f"appear to have donated to its sponsors."
        )

    return signal


# ── Signal 2: timing_spike ───────────────────────────────────────────────


async def _signal_timing_spike(
    session: AsyncSession,
    bill_id: uuid.UUID,
    bill_entity: Entity,
    sponsors: list[tuple[Relationship, Entity]],
    baseline_rate: float = 1.2,
) -> dict:
    """Did same-industry donations spike in the 90 days before introduction?"""
    signal = {
        "signal_type": "timing_spike",
        "found": False,
        "confidence": None,
        "rarity_pct": None,
        "rarity_label": None,
        "p_value": None,
        "baseline_rate": baseline_rate,
        "observed_rate": None,
        "description": "",
        "evidence": {},
    }

    meta = bill_entity.metadata_ or {}
    introduced_str = meta.get("introduced_date")
    if not introduced_str:
        signal["description"] = "No introduced_date on bill — cannot compute timing."
        return signal

    try:
        introduced_date = date.fromisoformat(str(introduced_str)[:10])
    except (ValueError, TypeError):
        signal["description"] = "Invalid introduced_date format."
        return signal

    policy_area = meta.get("policy_area", "")
    bill_keywords = _industry_keywords_for_policy_area(policy_area)
    if not bill_keywords:
        signal["description"] = "No policy_area mapped — cannot match industries."
        return signal

    window_start = introduced_date - timedelta(days=90)
    sponsor_ids = [ent.id for _, ent in sponsors]

    # Get donations to all sponsors within the 90-day window
    donation_evidence: list[dict] = []

    for sponsor_id in sponsor_ids:
        sponsor_name = None
        for _, ent in sponsors:
            if ent.id == sponsor_id:
                sponsor_name = _sanitize(ent.name)
                break

        q = (
            select(Relationship, Entity)
            .join(Entity, Entity.id == Relationship.from_entity_id)
            .where(Relationship.to_entity_id == sponsor_id)
            .where(Relationship.relationship_type == "donated_to")
            .where(Relationship.date_start >= window_start)
            .where(Relationship.date_start <= introduced_date)
        )
        result = await session.execute(q)
        rows = list(result.all())

        for don_rel, donor_entity in rows:
            # Skip platform PACs
            if _is_platform_pac(donor_entity.slug):
                continue

            donor_keywords = _extract_industry_keywords(donor_entity)
            if _keyword_overlap(donor_keywords, bill_keywords):
                days_before = (introduced_date - don_rel.date_start).days
                donation_evidence.append({
                    "donor": _sanitize(donor_entity.name),
                    "donor_slug": donor_entity.slug,
                    "sponsor": sponsor_name or "Unknown",
                    "amount": don_rel.amount_usd or 0,
                    "amount_fmt": _fmt_amount(don_rel.amount_usd),
                    "date": don_rel.date_start.isoformat(),
                    "days_before": days_before,
                })

    observed = len(donation_evidence)
    signal["observed_rate"] = float(observed)

    if observed == 0:
        signal["description"] = (
            f"No same-industry donations in 90 days before introduction "
            f"({window_start.isoformat()} to {introduced_date.isoformat()})."
        )
        return signal

    multiplier = observed / max(baseline_rate, 0.01)

    # Compute p-value
    if poisson is not None:
        p_value = 1 - poisson.cdf(observed - 1, baseline_rate)
    else:
        p_value = min(1.0, baseline_rate / max(observed, 1))

    signal["p_value"] = round(p_value, 6)

    if multiplier >= 2.0:
        signal["found"] = True
        signal["confidence"] = "medium"
        signal["rarity_label"] = f"{multiplier:.1f}x"
        total = sum(d["amount"] for d in donation_evidence)
        signal["description"] = (
            f"{observed} same-industry donations ({_fmt_amount(total)}) in 90 days "
            f"before introduction — {multiplier:.1f}x the baseline rate."
        )
    else:
        signal["description"] = (
            f"{observed} same-industry donations found but only {multiplier:.1f}x "
            f"baseline (threshold: 2.0x)."
        )

    signal["evidence"] = {
        "donations": sorted(donation_evidence, key=lambda d: d["days_before"]),
        "window_start": window_start.isoformat(),
        "window_end": introduced_date.isoformat(),
        "multiplier": round(multiplier, 2),
        "policy_area": policy_area,
        "bill_keywords": bill_keywords,
    }

    return signal


# ── Signal 3: committee_overlap ──────────────────────────────────────────


async def _signal_committee_overlap(
    session: AsyncSession,
    bill_id: uuid.UUID,
    bill_entity: Entity,
    sponsors: list[tuple[Relationship, Entity]],
) -> dict:
    """Does any sponsor sit on a committee with jurisdiction over this bill?"""
    signal = {
        "signal_type": "committee_overlap",
        "found": False,
        "confidence": None,
        "rarity_pct": None,
        "rarity_label": "Expected",
        "p_value": None,
        "baseline_rate": None,
        "observed_rate": None,
        "description": "",
        "evidence": {},
    }

    meta = bill_entity.metadata_ or {}
    policy_area = meta.get("policy_area", "")
    bill_keywords = _industry_keywords_for_policy_area(policy_area)

    if not bill_keywords:
        signal["description"] = "No policy_area mapped — cannot check committee overlap."
        return signal

    overlaps: list[dict] = []

    for _, sponsor_entity in sponsors:
        # Get committee memberships for this sponsor
        q = (
            select(Relationship, Entity)
            .join(Entity, Entity.id == Relationship.to_entity_id)
            .where(Relationship.from_entity_id == sponsor_entity.id)
            .where(Relationship.relationship_type == "committee_member")
        )
        result = await session.execute(q)
        committee_rows = list(result.all())

        for comm_rel, comm_entity in committee_rows:
            comm_keywords = _industries_for_committee(comm_entity.name)
            if _keyword_overlap(comm_keywords, bill_keywords):
                overlaps.append({
                    "sponsor": _sanitize(sponsor_entity.name),
                    "sponsor_slug": sponsor_entity.slug,
                    "committee": _sanitize(comm_entity.name),
                    "committee_slug": comm_entity.slug,
                    "committee_keywords": comm_keywords,
                    "bill_keywords": bill_keywords,
                })

    if overlaps:
        signal["found"] = True
        signal["confidence"] = "context"
        unique_sponsors = {o["sponsor"] for o in overlaps}
        unique_committees = {o["committee"] for o in overlaps}
        signal["description"] = (
            f"{len(unique_sponsors)} sponsor(s) sit on "
            f"{len(unique_committees)} committee(s) with jurisdiction over "
            f"this bill's policy area ({policy_area})."
        )
        signal["evidence"] = {"overlaps": overlaps}
    else:
        signal["description"] = (
            f"No sponsor sits on a committee with jurisdiction matching "
            f"policy area '{policy_area}'."
        )

    return signal


# ── Signal 4: stock_trade ────────────────────────────────────────────────


async def _signal_stock_trade(
    session: AsyncSession,
    bill_id: uuid.UUID,
    bill_entity: Entity,
    sponsors: list[tuple[Relationship, Entity]],
) -> dict:
    """Did any sponsor trade stocks in bill-affected companies within 60 days?"""
    signal = {
        "signal_type": "stock_trade",
        "found": False,
        "confidence": None,
        "rarity_pct": None,
        "rarity_label": None,
        "p_value": None,
        "baseline_rate": None,
        "observed_rate": None,
        "description": "",
        "evidence": {},
    }

    meta = bill_entity.metadata_ or {}
    introduced_str = meta.get("introduced_date")
    if not introduced_str:
        signal["description"] = "No introduced_date — cannot compute stock trade timing."
        return signal

    try:
        introduced_date = date.fromisoformat(str(introduced_str)[:10])
    except (ValueError, TypeError):
        signal["description"] = "Invalid introduced_date format."
        return signal

    policy_area = meta.get("policy_area", "")
    bill_keywords = _industry_keywords_for_policy_area(policy_area)
    if not bill_keywords:
        signal["description"] = "No policy_area mapped — cannot match stock trades."
        return signal

    window_start = introduced_date - timedelta(days=60)
    window_end = introduced_date + timedelta(days=60)

    trade_evidence: list[dict] = []

    for _, sponsor_entity in sponsors:
        q = (
            select(Relationship)
            .where(Relationship.from_entity_id == sponsor_entity.id)
            .where(Relationship.relationship_type == "stock_trade")
            .where(Relationship.date_start >= window_start)
            .where(Relationship.date_start <= window_end)
        )
        result = await session.execute(q)
        trade_rels = list(result.scalars().all())

        for trel in trade_rels:
            # Load the stock entity to check industry match
            stock_entity = await session.get(Entity, trel.to_entity_id)
            if not stock_entity:
                continue

            stock_keywords = _extract_industry_keywords(stock_entity)
            stock_meta = stock_entity.metadata_ or {}
            stock_industry = (stock_meta.get("industry", "") or "").lower()

            # Also check entity name against bill keywords
            name_words = re.sub(r"[^a-z0-9\s]", "", stock_entity.name.lower()).split()
            all_stock_kws = stock_keywords + name_words
            if stock_industry:
                all_stock_kws.extend(stock_industry.split())

            if _keyword_overlap(all_stock_kws, bill_keywords):
                trel_meta = trel.metadata_ or {}
                days_relative = (trel.date_start - introduced_date).days
                trade_evidence.append({
                    "sponsor": _sanitize(sponsor_entity.name),
                    "sponsor_slug": sponsor_entity.slug,
                    "ticker": (stock_meta.get("ticker", "") or stock_entity.name).upper(),
                    "asset": _sanitize(stock_entity.name),
                    "transaction_type": trel_meta.get("transaction_type", "Unknown"),
                    "amount_range": trel.amount_label or trel_meta.get("amount_range", ""),
                    "date": trel.date_start.isoformat() if trel.date_start else None,
                    "days_relative": days_relative,
                })

    if trade_evidence:
        signal["found"] = True
        signal["confidence"] = "medium"
        signal["rarity_label"] = "Suspicious"
        unique_sponsors = {t["sponsor"] for t in trade_evidence}
        signal["description"] = (
            f"{len(trade_evidence)} stock trade(s) by {len(unique_sponsors)} "
            f"sponsor(s) in {policy_area}-related companies within 60 days "
            f"of bill introduction."
        )
        signal["evidence"] = {
            "trades": sorted(trade_evidence, key=lambda t: abs(t["days_relative"])),
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "policy_area": policy_area,
        }
    else:
        signal["description"] = (
            f"No sponsor stock trades in {policy_area}-related companies "
            f"within 60 days of introduction."
        )

    return signal


# ── Signal 5: revolving_door ─────────────────────────────────────────────


async def _signal_revolving_door(
    session: AsyncSession,
    bill_id: uuid.UUID,
    bill_entity: Entity,
    sponsors: list[tuple[Relationship, Entity]],
) -> dict:
    """Are former staffers of sponsors currently lobbying on this policy area?"""
    signal = {
        "signal_type": "revolving_door",
        "found": False,
        "confidence": None,
        "rarity_pct": None,
        "rarity_label": None,
        "p_value": None,
        "baseline_rate": None,
        "observed_rate": None,
        "description": "",
        "evidence": {},
    }

    meta = bill_entity.metadata_ or {}
    policy_area = meta.get("policy_area", "")
    bill_keywords = _industry_keywords_for_policy_area(policy_area)

    matches: list[dict] = []

    for _, sponsor_entity in sponsors:
        # Get revolving_door_lobbyist relationships TO this sponsor
        q = (
            select(Relationship, Entity)
            .join(Entity, Entity.id == Relationship.from_entity_id)
            .where(Relationship.to_entity_id == sponsor_entity.id)
            .where(Relationship.relationship_type == "revolving_door_lobbyist")
        )
        result = await session.execute(q)
        rd_rows = list(result.all())

        for rd_rel, lobbyist_entity in rd_rows:
            rd_meta = rd_rel.metadata_ or {}
            former_position = rd_meta.get("position", rd_meta.get("title", ""))

            # Check if this lobbyist lobbies_on_behalf_of anyone
            lobby_q = (
                select(Relationship, Entity)
                .join(Entity, Entity.id == Relationship.to_entity_id)
                .where(Relationship.from_entity_id == lobbyist_entity.id)
                .where(Relationship.relationship_type == "lobbies_on_behalf_of")
            )
            lobby_result = await session.execute(lobby_q)
            lobby_rows = list(lobby_result.all())

            for lobby_rel, client_entity in lobby_rows:
                lobby_meta = lobby_rel.metadata_ or {}
                issue = lobby_meta.get("issue", lobby_meta.get("general_issue_code", ""))
                description = lobby_meta.get("description", "")

                # Check if lobbying area matches bill policy area
                issue_text = f"{issue} {description}".lower()
                issue_words = [w.strip() for w in issue_text.split() if len(w.strip()) > 2]

                area_match = (
                    _keyword_overlap(issue_words, bill_keywords)
                    if bill_keywords
                    else False
                )

                if area_match or not bill_keywords:
                    matches.append({
                        "lobbyist": _sanitize(lobbyist_entity.name),
                        "lobbyist_slug": lobbyist_entity.slug,
                        "sponsor": _sanitize(sponsor_entity.name),
                        "sponsor_slug": sponsor_entity.slug,
                        "former_position": former_position,
                        "current_client": _sanitize(client_entity.name),
                        "lobbying_issue": str(issue)[:200] if issue else "",
                    })

    if matches:
        signal["found"] = True
        signal["confidence"] = "medium"
        signal["rarity_label"] = "Notable"
        unique_lobbyists = {m["lobbyist"] for m in matches}
        signal["description"] = (
            f"{len(unique_lobbyists)} former staffer(s) of bill sponsors "
            f"now lobby on related policy areas."
        )
        signal["evidence"] = {"matches": matches}
    else:
        signal["description"] = "No revolving-door connections found for this bill."

    return signal


# ── Main entry point ─────────────────────────────────────────────────────


async def compute_bill_signals(
    session: AsyncSession,
    bill_id: uuid.UUID,
    baselines: dict | None = None,
) -> list[dict]:
    """Compute all 5 influence signals for a bill.

    baselines: optional dict from bill_baselines.py with per-policy-area rates.
    If not provided, uses defaults.

    Returns list of 5 signal dicts, one per signal type.
    Each dict has keys matching BillInfluenceSignal model columns:
    signal_type, found, confidence, rarity_pct, rarity_label, p_value,
    baseline_rate, observed_rate, description, evidence (dict)
    """
    bill_entity = await _get_bill_entity(session, bill_id)
    if not bill_entity:
        log.warning("Bill entity %s not found", bill_id)
        return []

    sponsors = await _get_sponsors(session, bill_id)

    # Extract baseline for timing_spike
    baselines = baselines or {}
    meta = bill_entity.metadata_ or {}
    policy_area = (meta.get("policy_area") or "").lower().strip()
    timing_baseline = baselines.get(policy_area, {}).get("timing_spike", 1.2)

    # Run all 5 signals
    signals = [
        await _signal_lobby_donate(session, bill_id, bill_entity, sponsors),
        await _signal_timing_spike(
            session, bill_id, bill_entity, sponsors, baseline_rate=timing_baseline
        ),
        await _signal_committee_overlap(session, bill_id, bill_entity, sponsors),
        await _signal_stock_trade(session, bill_id, bill_entity, sponsors),
        await _signal_revolving_door(session, bill_id, bill_entity, sponsors),
    ]

    return signals


# ── Batch pre-compute ────────────────────────────────────────────────────


async def run_precompute_bill_signals() -> str:
    """Pre-compute influence signals for all bills with sponsors.

    1. Loads baselines from app_config
    2. Queries all bills with at least 1 sponsor (119th congress first)
    3. For each bill: compute signals, delete old rows, insert new
    4. Compute percentile ranks within each policy area
    5. Tracks via IngestionJob
    """
    import json
    from datetime import datetime, timezone
    from sqlalchemy import delete

    from app.database import async_session
    from app.models import BillInfluenceSignal, IngestionJob, AppConfig

    log.info("Starting pre-compute of bill signals...")

    async with async_session() as session:
        # Create ingestion job
        job = IngestionJob(
            job_type="precompute_bill_signals",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.commit()

        try:
            # Step 1: Load baselines
            config_q = select(AppConfig).where(AppConfig.key == "bill_baselines")
            config_result = await session.execute(config_q)
            config_row = config_result.scalar_one_or_none()
            baselines = {}
            if config_row and config_row.value:
                baselines = json.loads(config_row.value)
                log.info("Loaded baselines for %d policy areas", len(baselines))
            else:
                log.warning("No bill_baselines found in app_config — using defaults")

            # Step 2: Get all bills with at least 1 sponsor, 119th congress first
            bills_q = (
                select(Entity.id, Entity.metadata_)
                .where(Entity.entity_type == "bill")
                .where(
                    Entity.id.in_(
                        select(Relationship.to_entity_id)
                        .where(Relationship.relationship_type.in_(["sponsored", "cosponsored"]))
                        .distinct()
                    )
                )
                .order_by(
                    # Prioritize 119th congress
                    func.case(
                        (Entity.metadata_["congress"].astext == "119", 0),
                        else_=1,
                    ),
                    Entity.created_at.desc(),
                )
            )
            bills_result = await session.execute(bills_q)
            bills = list(bills_result.all())

            log.info("Found %d bills with sponsors to process", len(bills))
            job.total = len(bills)
            await session.commit()

            # Step 3: Process each bill
            errors = []
            policy_area_signals: dict[str, list[tuple[uuid.UUID, int]]] = defaultdict(list)

            for idx, (bill_id, bill_meta) in enumerate(bills):
                try:
                    # Compute signals
                    signals = await compute_bill_signals(session, bill_id, baselines)
                    if not signals:
                        continue

                    # Delete old signal rows for this bill
                    del_q = delete(BillInfluenceSignal).where(
                        BillInfluenceSignal.bill_id == bill_id
                    )
                    await session.execute(del_q)

                    # Insert new signal rows
                    found_count = 0
                    for sig in signals:
                        row = BillInfluenceSignal(
                            bill_id=bill_id,
                            signal_type=sig["signal_type"],
                            found=sig.get("found", False),
                            confidence=0.0,  # numeric default
                            rarity_pct=sig.get("rarity_pct"),
                            rarity_label=sig.get("rarity_label"),
                            p_value=sig.get("p_value"),
                            baseline_rate=sig.get("baseline_rate"),
                            observed_rate=sig.get("observed_rate"),
                            description=sig.get("description", ""),
                            evidence=sig.get("evidence", {}),
                        )
                        # Map confidence string to numeric
                        conf = sig.get("confidence")
                        if conf == "high":
                            row.confidence = 0.9
                        elif conf == "medium":
                            row.confidence = 0.6
                        elif conf == "context":
                            row.confidence = 0.3
                        session.add(row)
                        if sig.get("found"):
                            found_count += 1

                    # Track for percentile calculation
                    meta = bill_meta or {}
                    pa = (meta.get("policy_area") or "").lower().strip()
                    if pa:
                        policy_area_signals[pa].append((bill_id, found_count))

                    await session.commit()

                except Exception as exc:
                    log.error("Error computing signals for bill %s: %s", bill_id, exc)
                    errors.append({"bill_id": str(bill_id), "error": str(exc)})
                    await session.rollback()

                # Log progress
                job.progress = idx + 1
                if (idx + 1) % 100 == 0:
                    log.info("Progress: %d/%d bills processed", idx + 1, len(bills))
                    await session.commit()

            # Step 6: Compute percentile ranks within each policy area
            log.info("Computing percentile ranks for %d policy areas...", len(policy_area_signals))
            for pa, bill_found_list in policy_area_signals.items():
                # Sort by found_count
                sorted_bills = sorted(bill_found_list, key=lambda x: x[1])
                n = len(sorted_bills)
                for rank, (bill_id, found_count) in enumerate(sorted_bills):
                    percentile = round((rank / max(n - 1, 1)) * 100, 1)
                    # Update bill entity metadata with influence_percentile
                    bill_entity = await session.get(Entity, bill_id)
                    if bill_entity:
                        meta = dict(bill_entity.metadata_ or {})
                        meta["influence_percentile"] = percentile
                        meta["influence_signals_found"] = found_count
                        bill_entity.metadata_ = meta

                await session.commit()

            # Complete job
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.errors = errors
            job.metadata_ = {
                "total_bills": len(bills),
                "total_errors": len(errors),
                "policy_areas": len(policy_area_signals),
            }
            await session.commit()

            summary = (
                f"Pre-computed signals for {len(bills)} bills, "
                f"{len(errors)} errors, "
                f"{len(policy_area_signals)} policy areas ranked."
            )
            log.info(summary)
            return summary

        except Exception as exc:
            log.exception("Fatal error in run_precompute_bill_signals: %s", exc)
            job.status = "failed"
            job.errors = [{"error": str(exc)}]
            job.completed_at = datetime.now(timezone.utc)
            await session.commit()
            raise
