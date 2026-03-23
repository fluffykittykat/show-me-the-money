"""
Trade investigation router — exposes trade data, alerts, and cross-references.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.trade_alerts import (
    get_cross_reference_trades,
    get_recent_trades,
    get_trade_alerts_for_official,
    get_trades_by_ticker,
)

router = APIRouter(prefix="/investigate", tags=["trades"])


@router.get("/trades/recent")
async def recent_trades(
    days: int = Query(7, ge=1, le=90, description="Number of days to look back"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get all trades filed in the last N days (paginated)."""
    return await get_recent_trades(db, days=days, limit=limit, offset=offset)


@router.get("/trades/ticker/{ticker}")
async def trades_by_ticker(
    ticker: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get all officials who have traded this stock (paginated)."""
    return await get_trades_by_ticker(db, ticker=ticker, limit=limit, offset=offset)


@router.get("/trades/alert/{slug}")
async def trade_alerts(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Get trade pattern alerts for an official."""
    return await get_trade_alerts_for_official(db, slug=slug)


@router.get("/trades/cross-reference")
async def cross_reference_trades(
    days: int = Query(14, ge=1, le=90, description="Window in days"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Find stocks traded by 2+ officials within the same period (paginated)."""
    return await get_cross_reference_trades(db, days=days, limit=limit, offset=offset)
