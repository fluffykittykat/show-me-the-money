"""Alerts API — trade alert feed, subscriptions, and status management."""

import uuid

from fastapi import APIRouter, Query

from app.database import async_session

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/feed")
async def alerts_feed(
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    ticker: str = None,
    official_slug: str = None,
    status: str = None,
    alert_level: str = None,
):
    """Paginated alert feed with optional filters."""
    from app.services.alert_engine import get_alerts_feed

    async with async_session() as session:
        return await get_alerts_feed(
            session,
            limit=limit,
            offset=offset,
            ticker=ticker,
            official_slug=official_slug,
            status=status,
            alert_level=alert_level,
        )


@router.get("/unread-count")
async def unread_count():
    """Fast count of unread alerts for badge display."""
    from app.services.alert_engine import get_unread_count

    async with async_session() as session:
        count = await get_unread_count(session)
    return {"count": count}


@router.post("/{alert_id}/seen")
async def mark_seen(alert_id: str):
    """Mark a single alert as seen."""
    from app.services.alert_engine import mark_alert_seen

    try:
        parsed_id = uuid.UUID(alert_id)
    except ValueError:
        return {"status": "error", "message": "Invalid alert ID"}

    async with async_session() as session:
        ok = await mark_alert_seen(session, parsed_id)
    return {"status": "ok" if ok else "not_found"}


@router.post("/seen-all")
async def mark_all_alerts_seen():
    """Mark all unread alerts as seen."""
    from app.services.alert_engine import mark_all_seen

    async with async_session() as session:
        count = await mark_all_seen(session)
    return {"status": "ok", "updated": count}


@router.get("/subscriptions")
async def list_subscriptions():
    """List all active alert subscriptions."""
    from sqlalchemy import select

    from app.models import AlertSubscription

    async with async_session() as session:
        result = await session.execute(
            select(AlertSubscription).where(AlertSubscription.is_active == True)
        )
        subs = result.scalars().all()

    return [
        {
            "id": str(s.id),
            "sub_type": s.sub_type,
            "target_value": s.target_value,
            "channel": s.channel,
            "channel_target": s.channel_target,
            "is_active": s.is_active,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in subs
    ]


@router.post("/subscriptions")
async def create_subscription(
    sub_type: str = Query(..., description="politician, ticker, or global"),
    target_value: str = Query(..., description="slug, ticker symbol, or ALL"),
    channel: str = Query("feed", description="telegram or feed"),
    channel_target: str = Query(None, description="telegram chat_id"),
):
    """Create a new alert subscription."""
    from app.models import AlertSubscription

    sub = AlertSubscription(
        sub_type=sub_type,
        target_value=target_value.upper() if sub_type == "ticker" else target_value,
        channel=channel,
        channel_target=channel_target,
    )

    async with async_session() as session:
        session.add(sub)
        await session.commit()
        await session.refresh(sub)

    return {
        "id": str(sub.id),
        "sub_type": sub.sub_type,
        "target_value": sub.target_value,
        "channel": sub.channel,
        "channel_target": sub.channel_target,
        "is_active": sub.is_active,
    }


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str):
    """Deactivate a subscription."""
    from sqlalchemy import update

    from app.models import AlertSubscription

    try:
        parsed_id = uuid.UUID(subscription_id)
    except ValueError:
        return {"status": "error", "message": "Invalid subscription ID"}

    async with async_session() as session:
        result = await session.execute(
            update(AlertSubscription)
            .where(AlertSubscription.id == parsed_id)
            .values(is_active=False)
        )
        await session.commit()

    return {"status": "ok" if result.rowcount > 0 else "not_found"}
