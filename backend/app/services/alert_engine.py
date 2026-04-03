"""
Alert engine — creates trade alerts from new ingested trades,
queries the alert feed, and manages alert status.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlertSubscription, Entity, TradeAlert

logger = logging.getLogger(__name__)


async def create_trade_alert(
    session: AsyncSession,
    relationship_id: uuid.UUID,
    official_id: uuid.UUID,
    ticker: str,
    transaction_type: str = "",
    amount_label: str = "",
    trade_date: Optional[date] = None,
    filed_date: Optional[date] = None,
    source: str = "senate_efd",
    signals: list = None,
    narrative: str = "",
    context: dict = None,
) -> Optional[TradeAlert]:
    """Create a trade alert if one doesn't already exist for this relationship.

    Returns the alert if created, None if duplicate.
    """
    # Check for existing alert (idempotent)
    existing = await session.execute(
        select(TradeAlert).where(TradeAlert.relationship_id == relationship_id)
    )
    if existing.scalars().first():
        return None

    # Determine alert level from signals
    alert_level = "ROUTINE"
    if signals:
        signal_texts = " ".join(str(s) for s in signals).lower()
        if "high" in signal_texts or "conflict" in signal_texts:
            alert_level = "HIGH_CONCERN"
        elif "pattern" in signal_texts or "notable" in signal_texts or "cluster" in signal_texts:
            alert_level = "NOTABLE_PATTERN"

    alert = TradeAlert(
        relationship_id=relationship_id,
        official_id=official_id,
        ticker=ticker,
        transaction_type=transaction_type or "Unknown",
        amount_label=amount_label or "",
        trade_date=trade_date,
        filed_date=filed_date,
        alert_level=alert_level,
        narrative=narrative,
        signals=signals or [],
        context=context or {},
        source=source,
        status="new",
    )
    session.add(alert)
    await session.flush()

    logger.info(
        "[AlertEngine] Created %s alert for %s %s",
        alert_level, ticker, transaction_type,
    )
    return alert


async def get_alerts_feed(
    session: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    ticker: str = None,
    official_slug: str = None,
    status: str = None,
    alert_level: str = None,
) -> dict:
    """Paginated alert feed with optional filters."""
    query = select(TradeAlert, Entity.name, Entity.slug).join(
        Entity, TradeAlert.official_id == Entity.id
    )

    if ticker:
        query = query.where(TradeAlert.ticker == ticker.upper())
    if status:
        query = query.where(TradeAlert.status == status)
    if alert_level:
        query = query.where(TradeAlert.alert_level == alert_level)
    if official_slug:
        query = query.where(Entity.slug == official_slug)

    # Count total
    count_q = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_q)).scalar_one()

    # Fetch page
    query = query.order_by(TradeAlert.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(query)
    rows = result.all()

    alerts = []
    for alert, name, slug in rows:
        alerts.append({
            "id": str(alert.id),
            "official_name": name,
            "official_slug": slug,
            "ticker": alert.ticker,
            "transaction_type": alert.transaction_type,
            "amount_label": alert.amount_label,
            "trade_date": alert.trade_date.isoformat() if alert.trade_date else None,
            "filed_date": alert.filed_date.isoformat() if alert.filed_date else None,
            "alert_level": alert.alert_level,
            "narrative": alert.narrative or "",
            "signals": alert.signals or [],
            "context": alert.context or {},
            "source": alert.source,
            "status": alert.status,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        })

    unread = (await session.execute(
        select(func.count()).where(TradeAlert.status == "new")
    )).scalar_one()

    return {"alerts": alerts, "total": total, "unread_count": unread}


async def get_unread_count(session: AsyncSession) -> int:
    """Fast count of unread alerts."""
    result = await session.execute(
        select(func.count()).where(TradeAlert.status == "new")
    )
    return result.scalar_one()


async def mark_alert_seen(session: AsyncSession, alert_id: uuid.UUID) -> bool:
    """Mark a single alert as seen."""
    result = await session.execute(
        update(TradeAlert)
        .where(TradeAlert.id == alert_id)
        .values(status="seen")
    )
    await session.commit()
    return result.rowcount > 0


async def mark_all_seen(session: AsyncSession) -> int:
    """Mark all 'new' alerts as seen. Returns count updated."""
    result = await session.execute(
        update(TradeAlert)
        .where(TradeAlert.status == "new")
        .values(status="seen")
    )
    await session.commit()
    return result.rowcount
