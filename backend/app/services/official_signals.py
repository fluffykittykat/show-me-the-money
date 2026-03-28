"""
Official Signals Engine — 5 Statistical Influence Detectors

Computes five correlation signals for any official (member of Congress):

1. donors_lobby_bills — Donor entities also lobbied on bills this official sponsored
2. timing_spike      — Same-industry donations spiked before bill introductions
3. stock_committee   — Stock trades in sectors matching committee jurisdiction
4. committee_donors  — Donors operate in industries regulated by official's committees
5. revolving_door    — Former staffers now lobby on behalf of industry clients
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select, and_, func, delete
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


async def _get_official_bills(
    session: AsyncSession, official_id: uuid.UUID
) -> list[tuple[Relationship, Entity]]:
    """Get all bills this official sponsored or cosponsored."""
    q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.to_entity_id)
        .where(Relationship.from_entity_id == official_id)
        .where(Relationship.relationship_type.in_(["sponsored", "cosponsored"]))
    )
    result = await session.execute(q)
    return list(result.all())


async def _get_donor_relationships(
    session: AsyncSession, official_id: uuid.UUID
) -> list[tuple[Relationship, Entity]]:
    """Get all donated_to relationships targeting this official."""
    q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.to_entity_id == official_id)
        .where(Relationship.relationship_type == "donated_to")
    )
    result = await session.execute(q)
    return list(result.all())


async def _get_committees(
    session: AsyncSession, official_id: uuid.UUID
) -> list[tuple[Relationship, Entity]]:
    """Get committee memberships for this official."""
    q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.to_entity_id)
        .where(Relationship.from_entity_id == official_id)
        .where(Relationship.relationship_type == "committee_member")
    )
    result = await session.execute(q)
    return list(result.all())


async def _get_stock_trades(
    session: AsyncSession, official_id: uuid.UUID
) -> list[tuple[Relationship, Entity]]:
    """Get stock trades by this official."""
    q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.to_entity_id)
        .where(Relationship.from_entity_id == official_id)
        .where(Relationship.relationship_type == "stock_trade")
    )
    result = await session.execute(q)
    return list(result.all())


# ── Signal 1: donors_lobby_bills ──────────────────────────────────────────


async def _signal_donors_lobby_bills(
    session: AsyncSession,
    official_id: uuid.UUID,
    official_bills: list[tuple[Relationship, Entity]],
    donor_entities: list[tuple[Relationship, Entity]],
) -> dict:
    """Did any donor entity also lobby on a bill this official sponsored/cosponsored?"""
    signal = {
        "signal_type": "donors_lobby_bills",
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

    if not official_bills or not donor_entities:
        signal["description"] = "No bills or no donors found for this official."
        return signal

    bill_ids = [ent.id for _, ent in official_bills]
    bill_names = {ent.id: _sanitize(ent.name) for _, ent in official_bills}

    # Get all lobbying relationships for this official's bills
    lobby_q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.to_entity_id.in_(bill_ids))
        .where(Relationship.relationship_type == "lobbied_on")
    )
    lobby_result = await session.execute(lobby_q)
    lobby_rows = list(lobby_result.all())

    if not lobby_rows:
        signal["description"] = "No lobbying relationships found on this official's bills."
        return signal

    matches: list[dict] = []

    for lobby_rel, lobby_entity in lobby_rows:
        lobby_name = _sanitize(lobby_entity.name)
        lobby_meta = lobby_rel.metadata_ or {}
        filing_url = lobby_rel.source_url or lobby_meta.get("filing_url", "")

        for don_rel, donor_entity in donor_entities:
            is_match = (
                donor_entity.id == lobby_entity.id
                or _names_match(lobby_name, donor_entity.slug)
            )
            if is_match:
                matches.append({
                    "donor": _sanitize(donor_entity.name),
                    "donor_slug": donor_entity.slug,
                    "donation_amount": don_rel.amount_usd or 0,
                    "donation_amount_fmt": _fmt_amount(don_rel.amount_usd),
                    "bill": bill_names.get(lobby_rel.to_entity_id, "Unknown"),
                    "bill_id": str(lobby_rel.to_entity_id),
                    "filing_url": filing_url,
                })

    if matches:
        signal["found"] = True
        signal["confidence"] = "high"
        signal["rarity_label"] = "Rare"
        unique_donors = {m["donor"] for m in matches}
        total = sum(m["donation_amount"] for m in matches)
        signal["description"] = (
            f"{len(unique_donors)} donor(s) donated {_fmt_amount(total)} AND "
            f"lobbied on bills this official sponsored."
        )
        signal["evidence"] = {"matches": matches}

        # Compute rarity vs same chamber
        official_entity = await session.get(Entity, official_id)
        if official_entity:
            meta = official_entity.metadata_ or {}
            chamber = meta.get("chamber", "senate")
            chamber_count = await _count_officials_with_signal_in_chamber(
                session, chamber, "donors_lobby_bills"
            )
            if chamber_count > 0:
                signal["rarity_pct"] = round(
                    (1 - chamber_count / _chamber_size(chamber)) * 100, 1
                )
    else:
        signal["description"] = (
            f"{len(lobby_rows)} entities lobbied on this official's bills "
            f"but none appear to match their donors."
        )

    return signal


def _chamber_size(chamber: str) -> int:
    """Approximate chamber size."""
    if chamber and "house" in chamber.lower():
        return 435
    return 100


async def _count_officials_with_signal_in_chamber(
    session: AsyncSession, chamber: str, signal_type: str
) -> int:
    """Count how many officials in the same chamber have a given signal found=True."""
    from app.models import OfficialInfluenceSignal
    q = (
        select(func.count(func.distinct(OfficialInfluenceSignal.official_id)))
        .join(Entity, Entity.id == OfficialInfluenceSignal.official_id)
        .where(OfficialInfluenceSignal.signal_type == signal_type)
        .where(OfficialInfluenceSignal.found.is_(True))
    )
    # Filter by chamber in metadata
    if chamber and "house" in chamber.lower():
        q = q.where(Entity.metadata_["chamber"].astext == "house")
    else:
        q = q.where(Entity.metadata_["chamber"].astext == "senate")
    result = await session.execute(q)
    return result.scalar() or 0


# ── Signal 2: timing_spike ───────────────────────────────────────────────


async def _signal_timing_spike(
    session: AsyncSession,
    official_id: uuid.UUID,
    official_bills: list[tuple[Relationship, Entity]],
    donor_rels: list[tuple[Relationship, Entity]],
    baseline_rate: float = 3.8,
) -> dict:
    """Did same-industry donations spike in the 90 days before any bill introduction?"""
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

    if not official_bills:
        signal["description"] = "No bills found for this official."
        return signal

    donation_evidence: list[dict] = []

    for bill_rel, bill_entity in official_bills:
        # Only count sponsored bills (not cosponsored) for timing
        if bill_rel.relationship_type != "sponsored":
            continue

        meta = bill_entity.metadata_ or {}
        introduced_str = meta.get("introduced_date")
        if not introduced_str:
            continue

        try:
            introduced_date = date.fromisoformat(str(introduced_str)[:10])
        except (ValueError, TypeError):
            continue

        policy_area = meta.get("policy_area", "")
        bill_keywords = _industry_keywords_for_policy_area(policy_area)
        if not bill_keywords:
            continue

        window_start = introduced_date - timedelta(days=90)

        for don_rel, donor_entity in donor_rels:
            # Skip platform PACs
            if _is_platform_pac(donor_entity.slug):
                continue

            # Check date in window
            if not don_rel.date_start:
                continue
            if don_rel.date_start < window_start or don_rel.date_start > introduced_date:
                continue

            # Check industry match
            donor_keywords = _extract_industry_keywords(donor_entity)
            if _keyword_overlap(donor_keywords, bill_keywords):
                days_before = (introduced_date - don_rel.date_start).days
                donation_evidence.append({
                    "donor": _sanitize(donor_entity.name),
                    "donor_slug": donor_entity.slug,
                    "amount": don_rel.amount_usd or 0,
                    "amount_fmt": _fmt_amount(don_rel.amount_usd),
                    "date": don_rel.date_start.isoformat(),
                    "days_before": days_before,
                    "bill": _sanitize(bill_entity.name),
                    "introduced_date": str(introduced_str)[:10],
                })

    observed = len(donation_evidence)
    signal["observed_rate"] = float(observed)

    if observed == 0:
        signal["description"] = (
            "No same-industry donations in 90 days before any bill introduction."
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
            f"{observed} same-industry donations ({_fmt_amount(total)}) within "
            f"90 days before bill introductions — {multiplier:.1f}x the baseline."
        )
    else:
        signal["description"] = (
            f"{observed} same-industry donations found but only {multiplier:.1f}x "
            f"baseline (threshold: 2.0x)."
        )

    signal["evidence"] = {
        "donations": sorted(donation_evidence, key=lambda d: d["days_before"]),
        "multiplier": round(multiplier, 2),
    }

    return signal


# ── Signal 3: stock_committee ────────────────────────────────────────────


async def _signal_stock_committee(
    session: AsyncSession,
    official_id: uuid.UUID,
    committees: list[tuple[Relationship, Entity]],
    stock_trades: list[tuple[Relationship, Entity]],
) -> dict:
    """Do stock trades match the official's committee jurisdictions?"""
    signal = {
        "signal_type": "stock_committee",
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

    if not committees or not stock_trades:
        signal["description"] = "No committee memberships or no stock trades found."
        return signal

    # Build committee keyword sets
    committee_keywords: dict[str, list[str]] = {}
    for _, comm_entity in committees:
        comm_name = _sanitize(comm_entity.name)
        kws = _industries_for_committee(comm_entity.name)
        if kws:
            committee_keywords[comm_name] = kws

    if not committee_keywords:
        signal["description"] = "No committee jurisdiction keywords could be mapped."
        return signal

    # Also check bill timing — get official's sponsored bills for 60-day window
    official_bills = await _get_official_bills(session, official_id)
    bill_dates: list[date] = []
    for bill_rel, bill_entity in official_bills:
        if bill_rel.relationship_type != "sponsored":
            continue
        meta = bill_entity.metadata_ or {}
        intro_str = meta.get("introduced_date")
        if intro_str:
            try:
                bill_dates.append(date.fromisoformat(str(intro_str)[:10]))
            except (ValueError, TypeError):
                pass

    trade_evidence: list[dict] = []

    for trade_rel, stock_entity in stock_trades:
        stock_meta = stock_entity.metadata_ or {}
        trade_meta = trade_rel.metadata_ or {}
        ticker = (stock_meta.get("ticker", "") or stock_entity.name).upper()

        # Build stock keywords from entity
        stock_keywords = _extract_industry_keywords(stock_entity)
        stock_industry = (stock_meta.get("industry", "") or "").lower()
        name_words = re.sub(r"[^a-z0-9\s]", "", stock_entity.name.lower()).split()
        all_stock_kws = stock_keywords + name_words
        if stock_industry:
            all_stock_kws.extend(stock_industry.split())

        # Check against each committee's keywords
        matching_committees: list[str] = []
        for comm_name, comm_kws in committee_keywords.items():
            if _keyword_overlap(all_stock_kws, comm_kws):
                matching_committees.append(comm_name)

        if matching_committees:
            # Check if trade is within 60 days of a bill introduction
            near_bill = False
            if trade_rel.date_start and bill_dates:
                for bd in bill_dates:
                    if abs((trade_rel.date_start - bd).days) <= 60:
                        near_bill = True
                        break

            trade_evidence.append({
                "ticker": ticker,
                "asset": _sanitize(stock_entity.name),
                "transaction_type": trade_meta.get("transaction_type", "Unknown"),
                "amount_range": trade_rel.amount_label or trade_meta.get("amount_range", ""),
                "date": trade_rel.date_start.isoformat() if trade_rel.date_start else None,
                "matching_committees": matching_committees,
                "near_bill_introduction": near_bill,
            })

    if trade_evidence:
        signal["found"] = True
        signal["confidence"] = "medium"
        near_bill_count = sum(1 for t in trade_evidence if t["near_bill_introduction"])
        if near_bill_count > 0:
            signal["rarity_label"] = "Suspicious"
        else:
            signal["rarity_label"] = "Notable"
        signal["description"] = (
            f"{len(trade_evidence)} stock trade(s) match committee jurisdiction. "
            f"{near_bill_count} within 60 days of a bill introduction."
        )
        signal["evidence"] = {"trades": trade_evidence}
    else:
        signal["description"] = (
            "No stock trades match the official's committee jurisdictions."
        )

    return signal


# ── Signal 4: committee_donors ───────────────────────────────────────────


async def _signal_committee_donors(
    session: AsyncSession,
    official_id: uuid.UUID,
    committees: list[tuple[Relationship, Entity]],
    donor_rels: list[tuple[Relationship, Entity]],
) -> dict:
    """Do donors operate in industries regulated by the official's committees?"""
    signal = {
        "signal_type": "committee_donors",
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

    if not committees or not donor_rels:
        signal["description"] = "No committee memberships or no donors found."
        return signal

    # Build committee keyword sets
    committee_matches: dict[str, list[dict]] = defaultdict(list)

    for _, comm_entity in committees:
        comm_name = _sanitize(comm_entity.name)
        comm_kws = _industries_for_committee(comm_entity.name)
        if not comm_kws:
            continue

        for don_rel, donor_entity in donor_rels:
            if _is_platform_pac(donor_entity.slug):
                continue
            donor_kws = _extract_industry_keywords(donor_entity)
            if _keyword_overlap(donor_kws, comm_kws):
                committee_matches[comm_name].append({
                    "donor": _sanitize(donor_entity.name),
                    "donor_slug": donor_entity.slug,
                    "amount": don_rel.amount_usd or 0,
                    "amount_fmt": _fmt_amount(don_rel.amount_usd),
                })

    if committee_matches:
        signal["found"] = True
        signal["confidence"] = "context"
        total_donors = sum(len(v) for v in committee_matches.values())
        committees_list = []
        for comm_name, donors in committee_matches.items():
            committees_list.append({
                "committee": comm_name,
                "donor_count": len(donors),
                "total_amount_fmt": _fmt_amount(sum(d["amount"] for d in donors)),
                "donors": donors[:10],  # cap at 10 per committee
            })
        signal["description"] = (
            f"{total_donors} donor(s) operate in industries regulated by "
            f"{len(committee_matches)} committee(s) this official sits on."
        )
        signal["evidence"] = {"committees": committees_list}
    else:
        signal["description"] = (
            "No donors appear to operate in industries regulated by "
            "this official's committees."
        )

    return signal


# ── Signal 5: revolving_door ─────────────────────────────────────────────


async def _signal_revolving_door(
    session: AsyncSession,
    official_id: uuid.UUID,
) -> dict:
    """Are there revolving-door lobbyists connected to this official?"""
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

    # Get revolving_door_lobbyist relationships pointing TO this official
    q = (
        select(Relationship, Entity)
        .join(Entity, Entity.id == Relationship.from_entity_id)
        .where(Relationship.to_entity_id == official_id)
        .where(Relationship.relationship_type == "revolving_door_lobbyist")
    )
    result = await session.execute(q)
    rd_rows = list(result.all())

    if not rd_rows:
        signal["description"] = "No revolving-door connections found for this official."
        return signal

    matches: list[dict] = []

    for rd_rel, lobbyist_entity in rd_rows:
        rd_meta = rd_rel.metadata_ or {}
        former_position = rd_meta.get("position", rd_meta.get("title", ""))

        # Find who this lobbyist currently represents
        lobby_q = (
            select(Relationship, Entity)
            .join(Entity, Entity.id == Relationship.to_entity_id)
            .where(Relationship.from_entity_id == lobbyist_entity.id)
            .where(Relationship.relationship_type == "lobbies_on_behalf_of")
        )
        lobby_result = await session.execute(lobby_q)
        lobby_rows = list(lobby_result.all())

        current_clients = [_sanitize(client.name) for _, client in lobby_rows]

        matches.append({
            "lobbyist": _sanitize(lobbyist_entity.name),
            "lobbyist_slug": lobbyist_entity.slug,
            "former_position": former_position,
            "current_clients": current_clients,
        })

    if matches:
        signal["found"] = True
        signal["confidence"] = "medium"
        signal["rarity_label"] = "Notable"
        signal["description"] = (
            f"{len(matches)} former staffer(s) of this official now work as lobbyists."
        )
        signal["evidence"] = {"matches": matches}

    return signal


# ── Main entry point ─────────────────────────────────────────────────────


async def compute_official_signals(
    session: AsyncSession,
    official_id: uuid.UUID,
    baselines: dict | None = None,
) -> list[dict]:
    """Compute all 5 influence signals for an official.

    Returns list of 5 signal dicts, one per signal type.
    Each dict has keys matching OfficialInfluenceSignal model columns.
    """
    official_entity = await session.get(Entity, official_id)
    if not official_entity:
        log.warning("Official entity %s not found", official_id)
        return []

    # Load data
    official_bills = await _get_official_bills(session, official_id)
    donor_rels = await _get_donor_relationships(session, official_id)
    committees = await _get_committees(session, official_id)
    stock_trades = await _get_stock_trades(session, official_id)

    # Extract baseline for timing_spike
    baselines = baselines or {}
    meta = official_entity.metadata_ or {}
    chamber = (meta.get("chamber") or "senate").lower()
    timing_baseline = baselines.get(chamber, {}).get("timing_spike", 3.8)

    # Run all 5 signals
    signals = [
        await _signal_donors_lobby_bills(session, official_id, official_bills, donor_rels),
        await _signal_timing_spike(
            session, official_id, official_bills, donor_rels,
            baseline_rate=timing_baseline,
        ),
        await _signal_stock_committee(session, official_id, committees, stock_trades),
        await _signal_committee_donors(session, official_id, committees, donor_rels),
        await _signal_revolving_door(session, official_id),
    ]

    return signals


# ── Batch pre-compute ────────────────────────────────────────────────────


async def run_precompute_official_signals() -> str:
    """Pre-compute influence signals for all officials.

    1. Queries all person entities (officials)
    2. For each: compute signals, delete old rows, insert new
    3. Compute percentile ranks within each chamber
    4. Tracks via IngestionJob
    """
    import json
    from datetime import datetime, timezone

    from app.database import async_session
    from app.models import OfficialInfluenceSignal, IngestionJob, AppConfig

    log.info("Starting pre-compute of official signals...")

    async with async_session() as session:
        # Create ingestion job
        job = IngestionJob(
            job_type="precompute_official_signals",
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.add(job)
        await session.commit()

        try:
            # Step 1: Load baselines from app_config if available
            config_q = select(AppConfig).where(AppConfig.key == "official_baselines")
            config_result = await session.execute(config_q)
            config_row = config_result.scalar_one_or_none()
            baselines = {}
            if config_row and config_row.value:
                baselines = json.loads(config_row.value)
                log.info("Loaded official baselines: %s", list(baselines.keys()))
            else:
                log.info("No official_baselines in app_config — using defaults")

            # Step 2: Get all officials (person entities)
            officials_q = (
                select(Entity.id, Entity.name, Entity.metadata_)
                .where(Entity.entity_type == "person")
                .order_by(Entity.name)
            )
            officials_result = await session.execute(officials_q)
            officials = list(officials_result.all())

            log.info("Found %d officials to process", len(officials))
            job.total = len(officials)
            await session.commit()

            # Step 3: Process each official
            errors = []
            chamber_signals: dict[str, list[tuple[uuid.UUID, int]]] = defaultdict(list)

            for idx, (official_id, official_name, official_meta) in enumerate(officials):
                try:
                    signals = await compute_official_signals(
                        session, official_id, baselines
                    )
                    if not signals:
                        continue

                    # Delete old signal rows for this official
                    del_q = delete(OfficialInfluenceSignal).where(
                        OfficialInfluenceSignal.official_id == official_id
                    )
                    await session.execute(del_q)

                    # Insert new signal rows
                    found_count = 0
                    for sig in signals:
                        row = OfficialInfluenceSignal(
                            official_id=official_id,
                            signal_type=sig["signal_type"],
                            found=sig.get("found", False),
                            confidence=0.0,
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

                    # Track for percentile
                    meta = official_meta or {}
                    chamber = (meta.get("chamber") or "senate").lower()
                    chamber_signals[chamber].append((official_id, found_count))

                    await session.commit()

                except Exception as exc:
                    log.error(
                        "Error computing signals for official %s (%s): %s",
                        official_name, official_id, exc,
                    )
                    errors.append({
                        "official_id": str(official_id),
                        "name": official_name,
                        "error": str(exc),
                    })
                    await session.rollback()

                # Log progress
                job.progress = idx + 1
                if (idx + 1) % 50 == 0:
                    log.info(
                        "Progress: %d/%d officials processed",
                        idx + 1, len(officials),
                    )
                    await session.commit()

            # Step 4: Compute percentile ranks within each chamber
            log.info(
                "Computing percentile ranks for %d chambers...",
                len(chamber_signals),
            )
            for chamber, official_found_list in chamber_signals.items():
                sorted_officials = sorted(official_found_list, key=lambda x: x[1])
                n = len(sorted_officials)
                for rank, (official_id, found_count) in enumerate(sorted_officials):
                    percentile = round((rank / max(n - 1, 1)) * 100, 1)
                    # Update percentile on each signal row for this official
                    update_q = (
                        select(OfficialInfluenceSignal)
                        .where(OfficialInfluenceSignal.official_id == official_id)
                    )
                    result = await session.execute(update_q)
                    for row in result.scalars().all():
                        if row.found:
                            row.rarity_pct = percentile

                    # Also update official entity metadata
                    official_entity = await session.get(Entity, official_id)
                    if official_entity:
                        meta = dict(official_entity.metadata_ or {})
                        meta["influence_percentile"] = percentile
                        meta["influence_signals_found"] = found_count
                        official_entity.metadata_ = meta

                await session.commit()

            # Complete job
            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.errors = errors
            job.metadata_ = {
                "total_officials": len(officials),
                "total_errors": len(errors),
                "chambers": {k: len(v) for k, v in chamber_signals.items()},
            }
            await session.commit()

            summary = (
                f"Pre-computed signals for {len(officials)} officials, "
                f"{len(errors)} errors, "
                f"{len(chamber_signals)} chambers ranked."
            )
            log.info(summary)
            return summary

        except Exception as exc:
            log.exception("Fatal error in run_precompute_official_signals: %s", exc)
            job.status = "failed"
            job.errors = [{"error": str(exc)}]
            job.completed_at = datetime.now(timezone.utc)
            await session.commit()
            raise
