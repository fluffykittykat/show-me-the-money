"""
House Clerk stock trade ingestion pipeline.

Downloads PTR (Periodic Transaction Report) filings from the House Clerk
financial disclosure XML index, parses the PDF attachments to extract
individual stock trades, and stores them as stock_trade relationships.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional
from xml.etree import ElementTree

import httpx
from pypdf import PdfReader
from io import BytesIO
from sqlalchemy import select

from app.database import async_session
from app.models import Entity, Relationship

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HOUSE_XML_INDEX_URL = (
    "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.xml"
)
HOUSE_PTR_PDF_URL = (
    "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"
)

# Regex to parse a single trade line from PDF text.
# Format: {owner} {asset_name} ({ticker}) [{asset_type}] {txn_type} {trade_date} {notification_date} {amount_range}
#
# Examples:
#   SP Albemarle Corporation (ALB) [ST] S 12/21/2023 01/08/2024 $1,001 - $15,000
#   JT Apple Inc. (AAPL) [ST] P 03/15/2024 04/01/2024 $15,001 - $50,000
#   DC Microsoft Corporation (MSFT) [OP] S (Partial) 01/10/2024 02/05/2024 $50,001 - $100,000
TRADE_LINE_RE = re.compile(
    r"(?P<owner>SP|JT|DC|self)?\s*"
    r"(?P<asset>.+?)\s+"
    r"\((?P<ticker>[A-Z]{1,5})\)\s+"
    r"\[(?P<asset_type>[A-Z]{2,4})\]\s+"
    r"(?P<txn_type>P|S|S\s*\(Partial\)|E)\s+"
    r"(?P<trade_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<notification_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<amount_range>\$[\d,]+\s*-\s*\$[\d,]+)",
    re.IGNORECASE,
)

# Cap-gains indicator that may appear at the end of the line
CAP_GAINS_RE = re.compile(r"\b(Yes|No)\s*$", re.IGNORECASE)


# ---------------------------------------------------------------------------
# 1. Fetch House PTR index
# ---------------------------------------------------------------------------

async def fetch_house_ptr_index(year: int) -> list[dict]:
    """Download and parse the House Clerk XML financial-disclosure index.

    Returns a list of PTR filing dicts with keys:
        first, last, state_dist, filing_date, doc_id
    """
    url = HOUSE_XML_INDEX_URL.format(year=year)
    logger.info("[house_trades] Fetching XML index: %s", url)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    root = ElementTree.fromstring(resp.text)

    filings: list[dict] = []
    for member in root.iter("Member"):
        filing_type = (member.findtext("FilingType") or "").strip()
        if filing_type != "P":
            continue

        doc_id = (member.findtext("DocID") or "").strip()
        if not doc_id:
            continue

        filings.append(
            {
                "first": (member.findtext("First") or "").strip(),
                "last": (member.findtext("Last") or "").strip(),
                "state_dist": (member.findtext("StateDst") or "").strip(),
                "filing_date": (member.findtext("FilingDate") or "").strip(),
                "doc_id": doc_id,
            }
        )

    logger.info("[house_trades] Found %d PTR filings for %d", len(filings), year)
    return filings


# ---------------------------------------------------------------------------
# 2. Parse a PTR PDF
# ---------------------------------------------------------------------------

def parse_ptr_pdf(pdf_bytes: bytes) -> list[dict]:
    """Extract stock trades from a PTR PDF.

    Returns a list of trade dicts with keys:
        owner, asset, ticker, transaction_type, trade_date,
        notification_date, amount_range, cap_gains
    """
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception as exc:
        logger.warning("[house_trades] Failed to open PDF: %s", exc)
        return []

    full_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n"

    trades: list[dict] = []

    for match in TRADE_LINE_RE.finditer(full_text):
        owner = (match.group("owner") or "").strip().upper()
        if not owner:
            owner = "self"

        txn_raw = match.group("txn_type").strip()
        if "partial" in txn_raw.lower():
            txn_type = "Sale (Partial)"
        elif txn_raw.upper() == "S":
            txn_type = "Sale"
        elif txn_raw.upper() == "P":
            txn_type = "Purchase"
        elif txn_raw.upper() == "E":
            txn_type = "Exchange"
        else:
            txn_type = txn_raw

        # Check for cap-gains indicator after the amount range
        remainder = full_text[match.end(): match.end() + 20]
        cap_match = CAP_GAINS_RE.search(remainder)
        cap_gains = cap_match.group(1).lower() == "yes" if cap_match else False

        trades.append(
            {
                "owner": owner,
                "asset": match.group("asset").strip(),
                "ticker": match.group("ticker").upper(),
                "transaction_type": txn_type,
                "trade_date": match.group("trade_date"),
                "notification_date": match.group("notification_date"),
                "amount_range": match.group("amount_range").strip(),
                "cap_gains": cap_gains,
            }
        )

    return trades


# ---------------------------------------------------------------------------
# 3. Main ingestion orchestrator
# ---------------------------------------------------------------------------

def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse MM/DD/YYYY to a date object, or None on failure."""
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _slugify(ticker: str) -> str:
    return f"stock-{ticker.lower()}"


async def _find_official(session, first: str, last: str) -> Optional[Entity]:
    """Find an official entity by first + last name (case-insensitive)."""
    stmt = (
        select(Entity)
        .where(Entity.entity_type == "person")
        .where(Entity.name.ilike(f"%{last}%"))
        .where(Entity.name.ilike(f"%{first}%"))
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def _get_or_create_stock(session, ticker: str, asset_name: str) -> Entity:
    """Find or create a stock/company entity for a given ticker."""
    slug = _slugify(ticker)
    stmt = select(Entity).where(Entity.slug == slug)
    result = await session.execute(stmt)
    entity = result.scalars().first()

    if entity is None:
        entity = Entity(
            slug=slug,
            entity_type="company",
            name=asset_name,
            metadata_={"ticker": ticker},
        )
        session.add(entity)
        await session.flush()

    return entity


async def ingest_house_trades(
    year: int = 2024,
    limit: Optional[int] = None,
) -> dict:
    """End-to-end House Clerk stock trade ingestion.

    1. Fetch the XML PTR index for *year*.
    2. Download each PTR PDF, parse trades, and store relationships.
    3. Return summary stats.
    """
    logger.info("[house_trades] Starting ingestion for year=%d limit=%s", year, limit)

    filings = await fetch_house_ptr_index(year)
    if limit:
        filings = filings[:limit]

    stats = {
        "filings_total": len(filings),
        "filings_matched": 0,
        "filings_unmatched": 0,
        "filings_failed": 0,
        "trades_created": 0,
        "trades_skipped_dup": 0,
    }

    for idx, filing in enumerate(filings, 1):
        first = filing["first"]
        last = filing["last"]
        doc_id = filing["doc_id"]
        filing_date = filing["filing_date"]

        logger.info(
            "[house_trades] [%d/%d] Processing %s %s (doc %s)",
            idx, len(filings), first, last, doc_id,
        )

        # Download the PDF ---------------------------------------------------
        pdf_url = HOUSE_PTR_PDF_URL.format(year=year, doc_id=doc_id)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(pdf_url)
                resp.raise_for_status()
                pdf_bytes = resp.content
        except Exception as exc:
            logger.warning("[house_trades] Failed to download %s: %s", pdf_url, exc)
            stats["filings_failed"] += 1
            await asyncio.sleep(1)
            continue

        # Parse trades --------------------------------------------------------
        try:
            trades = parse_ptr_pdf(pdf_bytes)
        except Exception as exc:
            logger.warning("[house_trades] PDF parse error for doc %s: %s", doc_id, exc)
            stats["filings_failed"] += 1
            await asyncio.sleep(1)
            continue

        if not trades:
            logger.info("[house_trades] No trades parsed from doc %s", doc_id)
            await asyncio.sleep(1)
            continue

        # Match official + store trades ---------------------------------------
        async with async_session() as session:
            official = await _find_official(session, first, last)
            if official is None:
                logger.info(
                    "[house_trades] No DB match for %s %s — skipping", first, last
                )
                stats["filings_unmatched"] += 1
                await asyncio.sleep(1)
                continue

            stats["filings_matched"] += 1

            for trade in trades:
                ticker = trade["ticker"]
                stock_entity = await _get_or_create_stock(
                    session, ticker, trade["asset"]
                )

                trade_date = _parse_date(trade["trade_date"])
                source_url = HOUSE_PTR_PDF_URL.format(year=year, doc_id=doc_id)

                # Duplicate check: same official -> stock, same doc_id, same trade_date, same txn type
                dup_stmt = (
                    select(Relationship)
                    .where(Relationship.from_entity_id == official.id)
                    .where(Relationship.to_entity_id == stock_entity.id)
                    .where(Relationship.relationship_type == "stock_trade")
                    .where(Relationship.source_url == source_url)
                    .where(Relationship.date_start == trade_date)
                )
                dup_result = await session.execute(dup_stmt)
                if dup_result.scalars().first() is not None:
                    stats["trades_skipped_dup"] += 1
                    continue

                metadata_ = {
                    "ticker": ticker,
                    "transaction_type": trade["transaction_type"],
                    "amount_range": trade["amount_range"],
                    "owner": trade["owner"],
                    "notification_date": trade["notification_date"],
                    "filed_date": filing_date,
                    "doc_id": doc_id,
                    "source": "House Clerk PTR",
                }

                rel = Relationship(
                    from_entity_id=official.id,
                    to_entity_id=stock_entity.id,
                    relationship_type="stock_trade",
                    amount_label=trade["amount_range"],
                    date_start=trade_date,
                    source_url=source_url,
                    source_label="House Clerk PTR",
                    metadata_=metadata_,
                )
                session.add(rel)
                stats["trades_created"] += 1

            await session.commit()

        # Rate-limit between PDF downloads
        await asyncio.sleep(1)

    logger.info("[house_trades] Ingestion complete: %s", stats)
    return stats
