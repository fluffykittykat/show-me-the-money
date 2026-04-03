"""
Telegram notification service for trade alerts.

Sends formatted messages via the Telegram Bot API when new trades
match active subscriptions. Gracefully degrades if no bot token
is configured.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AlertSubscription, Entity, TradeAlert

logger = logging.getLogger(__name__)

_last_sent: float = 0.0
THROTTLE_SECONDS = 2.0


def format_alert_message(alert: TradeAlert, official_name: str, official_meta: dict) -> str:
    """Format a trade alert as a plain-text Telegram message."""
    party = official_meta.get("party", "?")
    state = official_meta.get("state", "?")
    chamber = official_meta.get("chamber", "")

    days_to_file = ""
    if alert.trade_date and alert.filed_date:
        delta = (alert.filed_date - alert.trade_date).days
        days_to_file = f" ({delta} days to file)"

    lines = [
        f"[NEW TRADE ALERT]",
        f"{official_name} ({party}-{state}) {chamber}",
        f"{alert.transaction_type} {alert.ticker} -- {alert.amount_label}",
        f"Trade date: {alert.trade_date}  Filed: {alert.filed_date}{days_to_file}",
        f"Alert level: {alert.alert_level}",
    ]

    if alert.narrative:
        lines.append(f"\n{alert.narrative}")

    if alert.signals:
        sig_strs = [str(s) for s in alert.signals[:5]]
        lines.append(f"\nSignals: {', '.join(sig_strs)}")

    source_url = alert.context.get("source_url", "")
    if source_url:
        lines.append(f"\n{source_url}")

    return "\n".join(lines)


async def get_matching_subscriptions(
    session: AsyncSession, ticker: str, official_slug: str
) -> list[AlertSubscription]:
    """Find active subscriptions that match this trade."""
    result = await session.execute(
        select(AlertSubscription).where(
            AlertSubscription.is_active == True,
            or_(
                AlertSubscription.sub_type == "global",
                (AlertSubscription.sub_type == "ticker") & (AlertSubscription.target_value == ticker.upper()),
                (AlertSubscription.sub_type == "politician") & (AlertSubscription.target_value == official_slug),
            ),
        )
    )
    return list(result.scalars().all())


async def send_telegram_message(bot_token: str, chat_id: str, text: str) -> bool:
    """Send a message via Telegram Bot API. Returns True on success."""
    global _last_sent

    # Throttle
    elapsed = time.monotonic() - _last_sent
    if elapsed < THROTTLE_SECONDS:
        await asyncio.sleep(THROTTLE_SECONDS - elapsed)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": chat_id, "text": text},
            )
            _last_sent = time.monotonic()

            if resp.status_code == 200:
                return True
            else:
                logger.warning(
                    "[TelegramNotifier] Send failed: HTTP %s — %s",
                    resp.status_code, resp.text[:200],
                )
                return False
    except Exception as exc:
        logger.warning("[TelegramNotifier] Send error: %s", exc)
        return False


async def notify_trade_alert(
    session: AsyncSession, alert: TradeAlert, is_backfill: bool = False
) -> bool:
    """Send Telegram notifications for a trade alert.

    Skips notification for ROUTINE alerts and during backfills.
    Returns True if at least one notification was sent.
    """
    # Don't notify for routine trades or during backfill
    if alert.alert_level == "ROUTINE" or is_backfill:
        return False

    from app.services.config_service import get_config_value

    bot_token = await get_config_value(session, "TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.debug("[TelegramNotifier] No TELEGRAM_BOT_TOKEN configured, skipping")
        return False

    # Get official info
    result = await session.execute(
        select(Entity).where(Entity.id == alert.official_id)
    )
    official = result.scalars().first()
    if not official:
        return False

    # Find matching subscriptions
    subs = await get_matching_subscriptions(
        session, alert.ticker, official.slug
    )

    if not subs:
        # Fall back to default chat ID
        default_chat = await get_config_value(session, "TELEGRAM_DEFAULT_CHAT_ID")
        if default_chat:
            message = format_alert_message(alert, official.name, official.metadata_ or {})
            sent = await send_telegram_message(bot_token, default_chat, message)
            if sent:
                alert.status = "notified"
                alert.notified_at = datetime.now(timezone.utc)
                await session.commit()
            return sent
        return False

    message = format_alert_message(alert, official.name, official.metadata_ or {})
    any_sent = False

    for sub in subs:
        chat_id = sub.channel_target
        if not chat_id or sub.channel != "telegram":
            continue

        sent = await send_telegram_message(bot_token, chat_id, message)
        if sent:
            any_sent = True

    if any_sent:
        alert.status = "notified"
        alert.notified_at = datetime.now(timezone.utc)
        await session.commit()

    return any_sent
