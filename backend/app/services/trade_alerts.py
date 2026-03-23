"""
Trade alerts detection and cross-referencing service.

Detects suspicious trading patterns among congressional officials by analyzing
stock trades (stored as relationships with relationship_type='holds_stock')
and cross-referencing with committee assignments, legislation, and timing.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Entity, Relationship

logger = logging.getLogger(__name__)

# Alert level thresholds
ALERT_LEVEL_ROUTINE = "ROUTINE"
ALERT_LEVEL_NOTABLE = "NOTABLE_PATTERN"
ALERT_LEVEL_HIGH = "HIGH_CONCERN"

# Amount thresholds for flagging
LARGE_TRADE_LABELS = {
    "$100,001 - $250,000",
    "$250,001 - $500,000",
    "$500,001 - $1,000,000",
    "$1,000,001 - $5,000,000",
    "$5,000,001 - $25,000,000",
    "$25,000,001 - $50,000,000",
    "Over $50,000,000",
}


def _determine_alert_level(signal_count: int) -> str:
    """Determine alert level based on number of pattern signals found."""
    if signal_count >= 3:
        return ALERT_LEVEL_HIGH
    elif signal_count >= 1:
        return ALERT_LEVEL_NOTABLE
    return ALERT_LEVEL_ROUTINE


def _parse_date_safe(value) -> Optional[date]:
    """Safely parse a date from various formats."""
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


async def detect_trade_pattern(
    session: AsyncSession, ticker: str, trade_date: date, official_slug: str
) -> dict:
    """After a new trade is filed, check for suspicious patterns:

    1. Multiple officials traded same stock within 14 days
    2. Trade within 30 days before/after committee vote on related legislation
    3. Unusually large trade (>$100k) by official who sits on regulating committee

    Returns a trade alert dict with ticker, officials, alert_level, narrative.
    """
    signals: list[str] = []
    officials_info: list[dict] = []
    related_legislation: list[dict] = []

    # --- Signal 1: Multiple officials traded same stock within 14 days ---
    window_start = trade_date - timedelta(days=14)
    window_end = trade_date + timedelta(days=14)

    # Find all holds_stock relationships for this ticker in the window
    stmt = (
        select(Relationship, Entity)
        .join(Entity, Relationship.from_entity_id == Entity.id)
        .where(
            and_(
                Relationship.relationship_type == "holds_stock",
                Relationship.metadata_["ticker"].astext == ticker,
                Relationship.date_start >= window_start,
                Relationship.date_start <= window_end,
            )
        )
        .order_by(Relationship.date_start.desc())
    )
    result = await session.execute(stmt)
    rows = result.all()

    unique_officials = set()
    for rel, entity in rows:
        meta = rel.metadata_ or {}
        filed_date = _parse_date_safe(meta.get("filed_date"))
        days_to_file = None
        if filed_date and rel.date_start:
            days_to_file = (filed_date - rel.date_start).days

        official_info = {
            "name": entity.name,
            "slug": entity.slug,
            "transaction_type": meta.get("transaction_type", "Unknown"),
            "amount_label": rel.amount_label or meta.get("amount_label", "Unknown"),
            "filed_date": str(filed_date) if filed_date else str(rel.date_start),
            "days_to_file": days_to_file,
            "committee_relevance": meta.get("committee_relevance", ""),
        }
        unique_officials.add(entity.slug)
        officials_info.append(official_info)

    if len(unique_officials) >= 2:
        signals.append(
            f"{len(unique_officials)} officials traded {ticker} within a 14-day window"
        )

    # --- Signal 2: Check for large trades ---
    for rel, entity in rows:
        if entity.slug == official_slug:
            meta = rel.metadata_ or {}
            amount_label = rel.amount_label or meta.get("amount_label", "")
            if amount_label in LARGE_TRADE_LABELS:
                signals.append(
                    f"Large trade ({amount_label}) by {entity.name}"
                )

    # --- Signal 3: Check committee relevance ---
    # Look up the official's committee assignments
    official_stmt = (
        select(Entity)
        .where(Entity.slug == official_slug)
    )
    official_result = await session.execute(official_stmt)
    official = official_result.scalar_one_or_none()

    if official:
        official_meta = official.metadata_ or {}
        committees = official_meta.get("committees", [])
        if committees:
            # Check if any committee has jurisdiction over relevant industries
            committee_names = []
            for c in committees:
                if isinstance(c, dict):
                    committee_names.append(c.get("name", ""))
                elif isinstance(c, str):
                    committee_names.append(c)

            # Simple keyword matching for committee relevance
            relevance_keywords = {
                "banking": ["bank", "finance", "financial"],
                "commerce": ["tech", "telecom", "consumer"],
                "energy": ["energy", "oil", "gas", "utility"],
                "agriculture": ["farm", "food", "agri"],
                "armed services": ["defense", "military", "weapon"],
                "health": ["pharma", "health", "biotech", "medical"],
            }

            for comm_name in committee_names:
                comm_lower = comm_name.lower()
                for keyword_group, _keywords in relevance_keywords.items():
                    if keyword_group in comm_lower:
                        signals.append(
                            f"{official.name} sits on {comm_name} committee"
                        )
                        # Update committee_relevance for this official
                        for info in officials_info:
                            if info["slug"] == official_slug and not info["committee_relevance"]:
                                info["committee_relevance"] = (
                                    f"Sits on {comm_name}"
                                )
                        break

    # --- Signal 3b: Check for related legislation votes ---
    # Look for bill votes within 30 days of the trade
    vote_window_start = trade_date - timedelta(days=30)
    vote_window_end = trade_date + timedelta(days=30)

    vote_stmt = (
        select(Relationship, Entity)
        .join(Entity, Relationship.to_entity_id == Entity.id)
        .where(
            and_(
                Relationship.from_entity_id == official.id if official else text("false"),
                Relationship.relationship_type == "voted_on",
                Relationship.date_start >= vote_window_start,
                Relationship.date_start <= vote_window_end,
            )
        )
    )
    vote_result = await session.execute(vote_stmt)
    vote_rows = vote_result.all()
    for vote_rel, bill_entity in vote_rows:
        related_legislation.append({
            "bill_slug": bill_entity.slug,
            "bill_name": bill_entity.name,
            "vote_date": str(vote_rel.date_start) if vote_rel.date_start else "",
            "vote": (vote_rel.metadata_ or {}).get("vote", ""),
        })
        signals.append(
            f"Vote on {bill_entity.name} within 30 days of trade"
        )

    # Build date range string
    dates = [rel.date_start for rel, _ in rows if rel.date_start]
    if dates:
        min_date = min(dates)
        max_date = max(dates)
        trade_date_range = f"{min_date} to {max_date}"
    else:
        trade_date_range = str(trade_date)

    alert_level = _determine_alert_level(len(signals))

    # Build narrative
    if signals:
        narrative = f"Pattern detected for {ticker}: " + "; ".join(signals) + "."
    else:
        narrative = f"Trade of {ticker} recorded. No unusual patterns detected."

    return {
        "ticker": ticker,
        "trade_date_range": trade_date_range,
        "officials": officials_info,
        "alert_level": alert_level,
        "narrative": narrative,
        "related_legislation": related_legislation,
    }


async def get_recent_trades(
    session: AsyncSession, days: int = 7, limit: int = 50, offset: int = 0
) -> dict:
    """Get all trades filed in last N days."""
    cutoff = date.today() - timedelta(days=days)

    # Count total
    count_stmt = (
        select(func.count())
        .select_from(Relationship)
        .where(
            and_(
                Relationship.relationship_type == "holds_stock",
                Relationship.date_start >= cutoff,
            )
        )
    )
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    # Fetch trades with entity info
    stmt = (
        select(Relationship, Entity)
        .join(Entity, Relationship.from_entity_id == Entity.id)
        .where(
            and_(
                Relationship.relationship_type == "holds_stock",
                Relationship.date_start >= cutoff,
            )
        )
        .order_by(Relationship.date_start.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.all()

    trades = []
    for rel, entity in rows:
        meta = rel.metadata_ or {}
        filed_date = _parse_date_safe(meta.get("filed_date"))
        days_to_file = None
        if filed_date and rel.date_start:
            days_to_file = (filed_date - rel.date_start).days

        trades.append({
            "official_name": entity.name,
            "official_slug": entity.slug,
            "ticker": meta.get("ticker", ""),
            "transaction_type": meta.get("transaction_type", "Unknown"),
            "amount_label": rel.amount_label or meta.get("amount_label", "Unknown"),
            "filed_date": str(filed_date) if filed_date else None,
            "days_to_file": days_to_file,
            "is_flagged": meta.get("is_new", False),
            "committee_relevance": meta.get("committee_relevance", ""),
        })

    return {"trades": trades, "total": total}


async def get_trades_by_ticker(
    session: AsyncSession, ticker: str, limit: int = 50, offset: int = 0
) -> dict:
    """Get all officials who've traded this stock."""
    ticker_upper = ticker.upper()

    count_stmt = (
        select(func.count())
        .select_from(Relationship)
        .where(
            and_(
                Relationship.relationship_type == "holds_stock",
                Relationship.metadata_["ticker"].astext == ticker_upper,
            )
        )
    )
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    stmt = (
        select(Relationship, Entity)
        .join(Entity, Relationship.from_entity_id == Entity.id)
        .where(
            and_(
                Relationship.relationship_type == "holds_stock",
                Relationship.metadata_["ticker"].astext == ticker_upper,
            )
        )
        .order_by(Relationship.date_start.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.all()

    trades = []
    for rel, entity in rows:
        meta = rel.metadata_ or {}
        filed_date = _parse_date_safe(meta.get("filed_date"))
        days_to_file = None
        if filed_date and rel.date_start:
            days_to_file = (filed_date - rel.date_start).days

        trades.append({
            "official_name": entity.name,
            "official_slug": entity.slug,
            "ticker": meta.get("ticker", ticker_upper),
            "transaction_type": meta.get("transaction_type", "Unknown"),
            "amount_label": rel.amount_label or meta.get("amount_label", "Unknown"),
            "filed_date": str(filed_date) if filed_date else None,
            "days_to_file": days_to_file,
            "is_flagged": meta.get("is_new", False),
            "committee_relevance": meta.get("committee_relevance", ""),
        })

    return {"trades": trades, "total": total}


async def get_trade_alerts_for_official(
    session: AsyncSession, slug: str
) -> list:
    """Get trade pattern alerts for an official."""
    # Get all trades for this official
    stmt = (
        select(Relationship, Entity)
        .join(Entity, Relationship.from_entity_id == Entity.id)
        .where(
            and_(
                Entity.slug == slug,
                Relationship.relationship_type == "holds_stock",
            )
        )
        .order_by(Relationship.date_start.desc())
        .limit(100)
    )
    result = await session.execute(stmt)
    rows = result.all()

    alerts = []
    seen_tickers = set()

    for rel, entity in rows:
        meta = rel.metadata_ or {}
        ticker = meta.get("ticker", "")
        if not ticker or ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)

        trade_date = rel.date_start or date.today()
        alert = await detect_trade_pattern(session, ticker, trade_date, slug)
        if alert["alert_level"] != ALERT_LEVEL_ROUTINE:
            alerts.append(alert)

    return alerts


async def get_cross_reference_trades(
    session: AsyncSession, days: int = 14, limit: int = 20, offset: int = 0
) -> list:
    """Find stocks traded by 2+ officials within the same period.

    Returns a list of cross-reference results grouped by ticker, each showing
    the officials who traded that stock within the window.
    """
    cutoff = date.today() - timedelta(days=days)

    # Find tickers traded by multiple officials in the period
    # Subquery: get ticker + official combos
    ticker_officials_stmt = (
        select(
            Relationship.metadata_["ticker"].astext.label("ticker"),
            Relationship.from_entity_id,
        )
        .where(
            and_(
                Relationship.relationship_type == "holds_stock",
                Relationship.date_start >= cutoff,
                Relationship.metadata_["ticker"].astext.isnot(None),
            )
        )
        .distinct()
    )

    # Get tickers with 2+ unique officials
    from sqlalchemy import literal_column
    grouped_stmt = (
        select(
            Relationship.metadata_["ticker"].astext.label("ticker"),
            func.count(func.distinct(Relationship.from_entity_id)).label("official_count"),
        )
        .where(
            and_(
                Relationship.relationship_type == "holds_stock",
                Relationship.date_start >= cutoff,
                Relationship.metadata_["ticker"].astext.isnot(None),
            )
        )
        .group_by(Relationship.metadata_["ticker"].astext)
        .having(func.count(func.distinct(Relationship.from_entity_id)) >= 2)
        .order_by(func.count(func.distinct(Relationship.from_entity_id)).desc())
        .offset(offset)
        .limit(limit)
    )

    result = await session.execute(grouped_stmt)
    ticker_rows = result.all()

    cross_refs = []
    for row in ticker_rows:
        ticker = row.ticker
        officials_count = row.official_count

        # Fetch the officials and their trade details for this ticker
        detail_stmt = (
            select(Relationship, Entity)
            .join(Entity, Relationship.from_entity_id == Entity.id)
            .where(
                and_(
                    Relationship.relationship_type == "holds_stock",
                    Relationship.metadata_["ticker"].astext == ticker,
                    Relationship.date_start >= cutoff,
                )
            )
            .order_by(Relationship.date_start.desc())
        )
        detail_result = await session.execute(detail_stmt)
        detail_rows = detail_result.all()

        officials = []
        dates = []
        seen_slugs = set()
        for rel, entity in detail_rows:
            if entity.slug in seen_slugs:
                continue
            seen_slugs.add(entity.slug)

            meta = rel.metadata_ or {}
            filed_date = _parse_date_safe(meta.get("filed_date"))
            days_to_file = None
            if filed_date and rel.date_start:
                days_to_file = (filed_date - rel.date_start).days
            if rel.date_start:
                dates.append(rel.date_start)

            officials.append({
                "name": entity.name,
                "slug": entity.slug,
                "transaction_type": meta.get("transaction_type", "Unknown"),
                "amount_label": rel.amount_label or meta.get("amount_label", "Unknown"),
                "filed_date": str(filed_date) if filed_date else None,
                "days_to_file": days_to_file,
                "committee_relevance": meta.get("committee_relevance", ""),
            })

        date_range = ""
        if dates:
            date_range = f"{min(dates)} to {max(dates)}"

        # Determine alert level based on count
        signal_count = max(0, officials_count - 1)  # 2 officials = 1 signal
        alert_level = _determine_alert_level(signal_count)

        cross_refs.append({
            "ticker": ticker,
            "officials_count": officials_count,
            "officials": officials,
            "date_range": date_range,
            "alert_level": alert_level,
        })

    return cross_refs


async def clear_stale_new_flags(session: AsyncSession, days: int = 7):
    """Clear is_new flags older than N days. Called by scheduler."""
    cutoff = date.today() - timedelta(days=days)

    stmt = (
        select(Relationship)
        .where(
            and_(
                Relationship.relationship_type == "holds_stock",
                Relationship.metadata_["is_new"].astext == "true",
                Relationship.date_start < cutoff,
            )
        )
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()

    updated = 0
    for rel in rows:
        meta = dict(rel.metadata_ or {})
        meta["is_new"] = False
        rel.metadata_ = meta
        updated += 1

    if updated:
        await session.commit()
        logger.info(f"Cleared is_new flag on {updated} stale trade records")

    return updated
