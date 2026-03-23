"""Client for the Senate LDA (Lobbying Disclosure Act) API.

The LDA API (https://lda.senate.gov/api/v1/) is public and requires no API key.
It can be slow and occasionally returns HTML error pages, so all calls are
wrapped in try/except with generous timeouts.
"""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://lda.senate.gov/api/v1"
TIMEOUT = 30.0
MAX_RETRIES = 2


def _sanitize_str(s) -> str:
    """Strip non-ASCII characters (DB uses SQL_ASCII encoding)."""
    if not isinstance(s, str):
        return str(s) if s is not None else ""
    return s.encode("ascii", errors="ignore").decode("ascii")


class LDAClient:
    """Async client for the Senate Lobbying Disclosure Act API."""

    async def _get_json(self, url: str, params: dict) -> dict:
        """Make a GET request with retry logic and error handling."""
        for attempt in range(MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    return data
            except httpx.TimeoutException:
                logger.warning("LDA API timeout (attempt %d/%d): %s", attempt + 1, MAX_RETRIES + 1, url)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(2 * (attempt + 1))
                continue
            except httpx.HTTPStatusError as exc:
                logger.warning("LDA API HTTP %s: %s", exc.response.status_code, url)
                return {}
            except Exception as exc:
                logger.warning("LDA API error: %s — %s", type(exc).__name__, exc)
                return {}
        return {}

    async def fetch_filings(self, client_name: str, limit: int = 25) -> list:
        """GET /filings/?client_name={name}&format=json

        Returns a list of lobbying filing records for the given client.
        """
        url = f"{BASE_URL}/filings/"
        params = {
            "client_name": _sanitize_str(client_name),
            "format": "json",
            "page_size": limit,
        }
        data = await self._get_json(url, params)
        return data.get("results", [])

    async def fetch_registrations(self, client_name: str) -> list:
        """GET /registrations/?client_name={name}&format=json

        Returns lobbying registrations (firm-client relationships).
        """
        url = f"{BASE_URL}/registrations/"
        params = {
            "client_name": _sanitize_str(client_name),
            "format": "json",
            "page_size": 25,
        }
        data = await self._get_json(url, params)
        return data.get("results", [])

    async def fetch_client_lobbying_summary(self, client_name: str) -> dict:
        """Get complete lobbying profile for a company.

        Aggregates filings and registrations into a summary with total spend,
        lobbying firms, lobbyists, issues lobbied on, and bills referenced.
        All monetary amounts are returned in cents.
        """
        filings_task = self.fetch_filings(client_name)
        registrations_task = self.fetch_registrations(client_name)

        filings, registrations = await asyncio.gather(
            filings_task, registrations_task, return_exceptions=True
        )

        # Handle exceptions gracefully
        if isinstance(filings, Exception):
            logger.warning("Failed to fetch filings for %s: %s", client_name, filings)
            filings = []
        if isinstance(registrations, Exception):
            logger.warning("Failed to fetch registrations for %s: %s", client_name, registrations)
            registrations = []

        total_spend = 0
        firms: set[str] = set()
        issues: list[str] = []
        lobbyists: set[str] = set()
        bills_lobbied: list[dict] = []

        for filing in filings:
            # Parse income/expenses — LDA reports amounts as strings or numbers
            income = filing.get("income") or filing.get("expenses") or 0
            if isinstance(income, str):
                cleaned = income.replace(",", "").replace("$", "").strip()
                try:
                    income = float(cleaned) if cleaned else 0
                except ValueError:
                    income = 0
            total_spend += float(income)

            # Extract registrant (the lobbying firm)
            registrant = filing.get("registrant", {})
            if isinstance(registrant, dict) and registrant.get("name"):
                firms.add(_sanitize_str(registrant["name"]))

            # Extract lobbying activities and issues
            for activity in filing.get("lobbying_activities", []):
                desc = activity.get("description", "")
                if desc:
                    issues.append(_sanitize_str(desc))
                # Extract specific bill numbers if available
                for bill in activity.get("bills", []):
                    if isinstance(bill, dict):
                        bills_lobbied.append(bill)
                    elif isinstance(bill, str):
                        bills_lobbied.append({"bill_number": bill})

            # Extract lobbyists
            for lobbyist in filing.get("lobbyists", []):
                if isinstance(lobbyist, dict):
                    first = _sanitize_str(lobbyist.get("first_name", ""))
                    last = _sanitize_str(lobbyist.get("last_name", ""))
                    name = f"{first} {last}".strip()
                    if name:
                        lobbyists.add(name)

        return {
            "total_spend": int(total_spend * 100),  # convert to cents
            "filing_count": len(filings),
            "lobbying_firms": list(firms),
            "lobbyists": list(lobbyists),
            "issues": issues[:20],
            "bills_lobbied": bills_lobbied[:20],
            "registrations": len(registrations),
        }
