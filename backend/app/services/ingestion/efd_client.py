"""
Client for fetching Senate Electronic Financial Disclosure (eFD) data
and congressional voting records.

The Senate retired efts.senate.gov (NXDOMAIN as of ~March 2026) and
moved to efdsearch.senate.gov which uses:
  - A Django app with CSRF protection
  - A prohibition agreement that must be accepted per session
  - A DataTables server-side AJAX endpoint at /search/report/data/

Report type codes:
  11 = Periodic Transaction Report (PTR)
  7  = Annual Report
  13 = Amendment
"""

import asyncio
import json
import logging
import re

import httpx

from app.services.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

EFD_BASE = "https://efdsearch.senate.gov"
EFD_HOME = f"{EFD_BASE}/search/home/"
EFD_SEARCH = f"{EFD_BASE}/search/"
EFD_DATA = f"{EFD_BASE}/search/report/data/"

# Senate eFD is fragile and intermittently returns 503 during maintenance.
# We retry up-to 3 times with exponential backoff; if all attempts fail we
# raise so the caller can record a failed ingestion job instead of silently
# returning an empty list and pretending success.
EFD_MAX_RETRIES = 3
EFD_BACKOFF_BASE_SECONDS = 2.0


class EFDError(Exception):
    """Raised when Senate eFD is persistently unreachable after retries."""


# As of ~May 2026 the eFD DataTables endpoint rejects bare `MM/DD/YYYY` date
# filters with HTTP 503 — it now requires a `HH:MM:SS` time component. Bare
# dates and empty strings both 503; only `MM/DD/YYYY HH:MM:SS` returns data.
_DATE_ONLY_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def _normalize_efd_date(value: str, *, end: bool) -> str:
    """Append the time component eFD now requires to a `MM/DD/YYYY` date.

    `end=True` uses end-of-day so the range is inclusive of the final date.
    Values that already include a time, or that aren't bare dates, pass through
    unchanged so callers retain full control when they need it.
    """
    if value and _DATE_ONLY_RE.match(value):
        return f"{value} 23:59:59" if end else f"{value} 00:00:00"
    return value


class EFDClient:
    """Fetches Senate Electronic Financial Disclosure data and voting records."""

    def __init__(self):
        self.congress_base_url = "https://api.congress.gov/v3"
        self.timeout = 30.0
        self._limiter = get_rate_limiter()

    async def _get_efd_session(self, client: httpx.AsyncClient) -> str | None:
        """Establish an eFD session by accepting the prohibition agreement.

        Returns the CSRF token for subsequent requests, or None on failure.
        """
        # Step 1: Load home page to get CSRF token and session cookie
        resp = await client.get(EFD_HOME)
        resp.raise_for_status()

        match = re.search(r'csrfmiddlewaretoken" value="([^"]+)"', resp.text)
        if not match:
            logger.warning("[EFDClient] Could not find CSRF token on eFD home page")
            return None

        csrf_token = match.group(1)

        # Step 2: Accept the prohibition agreement
        resp2 = await client.post(
            EFD_HOME,
            data={
                "csrfmiddlewaretoken": csrf_token,
                "prohibition_agreement": "1",
            },
            headers={"Referer": EFD_HOME},
            follow_redirects=True,
        )

        # Should redirect to /search/ on success
        if resp2.status_code not in (200, 302):
            logger.warning(
                "[EFDClient] Agreement acceptance failed: HTTP %s", resp2.status_code
            )
            return None

        # Extract CSRF cookie for AJAX requests
        for cookie in client.cookies.jar:
            if cookie.name == "csrftoken":
                return cookie.value

        return csrf_token

    async def fetch_ptr_reports(
        self,
        start_date: str = "",
        end_date: str = "",
        last_name: str = "",
        first_name: str = "",
        state: str = "",
        length: int = 100,
    ) -> list[dict]:
        """Fetch Periodic Transaction Reports from Senate eFD.

        Retries up to EFD_MAX_RETRIES with exponential backoff on transient
        failures (5xx, connection errors). Raises EFDError if all attempts fail
        so the scheduler records the run as failed instead of silently treating
        an empty result as success.
        """
        last_error: Exception | None = None
        for attempt in range(1, EFD_MAX_RETRIES + 1):
            try:
                return await self._fetch_ptr_reports_once(
                    start_date=start_date,
                    end_date=end_date,
                    last_name=last_name,
                    first_name=first_name,
                    state=state,
                    length=length,
                )
            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}"
                status = e.response.status_code
                # 4xx (except 429) are not retryable — bail immediately.
                if 400 <= status < 500 and status != 429:
                    logger.warning(
                        "[EFDClient] non-retryable HTTP %s; aborting", status,
                    )
                    raise EFDError(f"HTTP {status}") from e
                wait = EFD_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "[EFDClient] HTTP %s (attempt %d/%d); retrying in %.1fs",
                    status, attempt, EFD_MAX_RETRIES, wait,
                )
                await asyncio.sleep(wait)
            except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as e:
                last_error = type(e).__name__
                wait = EFD_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                logger.warning(
                    "[EFDClient] connection error (attempt %d/%d): %s; retrying in %.1fs",
                    attempt, EFD_MAX_RETRIES, e, wait,
                )
                await asyncio.sleep(wait)

        raise EFDError(str(last_error))

    async def _fetch_ptr_reports_once(
        self,
        start_date: str,
        end_date: str,
        last_name: str,
        first_name: str,
        state: str,
        length: int,
    ) -> list[dict]:
        """Single attempt — caller (`fetch_ptr_reports`) handles retries."""
        async with self._limiter.acquire("senate_efd"):
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True
            ) as client:
                csrf = await self._get_efd_session(client)
                if not csrf:
                    # Session establishment failed — treat as retryable.
                    raise httpx.ConnectError("could not establish eFD session")

                resp = await client.post(
                    EFD_DATA,
                    data={
                        "draw": "1",
                        "start": "0",
                        "length": str(length),
                        "report_types": "[11]",  # PTR
                        "filer_types": "[]",
                        "submitted_start_date": _normalize_efd_date(
                            start_date, end=False
                        ),
                        "submitted_end_date": _normalize_efd_date(
                            end_date, end=True
                        ),
                        "candidate_state": "",
                        "senator_state": state,
                        "first_name": first_name,
                        "last_name": last_name,
                    },
                    headers={
                        "Referer": EFD_SEARCH,
                        "X-CSRFToken": csrf,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

        records = []
        for row in data.get("data", []):
            if isinstance(row, list) and len(row) >= 5:
                # eFD DataTables column layout (as of ~May 2026):
                #   [0] first name          e.g. "Sheldon"
                #   [1] last name           e.g. "Whitehouse"
                #   [2] "Last, First (Office)" e.g. "Whitehouse, Sheldon (Senator)"
                #   [3] <a href="/search/view/ptr/{uuid}/">Periodic Transaction
                #        Report for {date}</a>
                #   [4] date received       e.g. "06/02/2026"
                first_name = _strip_tags(row[0])
                last_name = _strip_tags(row[1])
                office_match = re.search(r"\(([^)]+)\)", _strip_tags(row[2]))
                records.append({
                    "first_name": first_name,
                    "last_name": last_name,
                    "office": office_match.group(1) if office_match else "",
                    "report_type": _strip_tags(row[3]),
                    "date_received": _strip_tags(row[4]),
                    "report_url": _extract_href(row[3]),
                })
            elif isinstance(row, dict):
                records.append(row)

        logger.info("[EFDClient] Fetched %d PTR records", len(records))
        return records

    async def fetch_financial_disclosures(self, senator_name: str = "Fetterman") -> dict:
        """Fetch financial disclosure filings from the Senate eFD system.

        Uses the new efdsearch.senate.gov DataTables API.
        """
        logger.info("[EFDClient] Fetching financial disclosures for: %s", senator_name)

        # Parse name
        parts = senator_name.strip().split()
        first = parts[0] if parts else ""
        last = parts[-1] if len(parts) > 1 else parts[0] if parts else ""

        records = await self.fetch_ptr_reports(last_name=last, first_name=first)

        assets = []
        transactions = []
        for record in records:
            report_type = record.get("report_type", "")
            entry = {
                "senator": senator_name,
                "date": record.get("date_received", ""),
                "report_type": report_type,
                "description": f"{record.get('first_name', '')} {record.get('last_name', '')}",
                "report_url": record.get("report_url", ""),
                "raw": record,
            }
            if "transaction" in report_type.lower() or "ptr" in report_type.lower():
                transactions.append(entry)
            else:
                assets.append(entry)

        logger.info(
            "[EFDClient] Found %d asset records and %d transaction records for %s",
            len(assets), len(transactions), senator_name,
        )
        return {"assets": assets, "transactions": transactions}

    async def fetch_votes(self, bioguide_id: str, api_key: str) -> list:
        """Fetch recent House voting records from the Congress.gov API.

        Note: Senate votes are not available via Congress.gov v3 API.
        House votes use /house-vote/{congress}/{session}.
        """
        logger.info("[EFDClient] Fetching votes for bioguide_id: %s", bioguide_id)

        # Fetch recent house votes (chamber-level, not per-member)
        url = f"{self.congress_base_url}/house-vote/119/1"
        params = {"api_key": api_key, "format": "json", "limit": 20}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            raw_votes = data.get("houseRollCallVotes", [])
            votes = []
            for vote in raw_votes:
                votes.append({
                    "congress": vote.get("congress"),
                    "session": vote.get("sessionNumber"),
                    "rollNumber": vote.get("rollCallNumber"),
                    "question": vote.get("voteType"),
                    "result": vote.get("result"),
                    "date": vote.get("startDate", "")[:10],
                    "description": vote.get("legislationType", ""),
                    "url": vote.get("url", ""),
                })

            logger.info("[EFDClient] Found %d vote records", len(votes))
            return votes

        except httpx.HTTPStatusError as e:
            logger.warning(
                "[EFDClient] HTTP error fetching votes: %s", e.response.status_code
            )
            return []
        except httpx.RequestError as e:
            logger.warning("[EFDClient] Request error fetching votes: %s", e)
            return []
        except Exception as e:
            logger.warning("[EFDClient] Unexpected error fetching votes: %s", e)
            return []

    async def fetch_all(self, bioguide_id: str, congress_api_key: str) -> dict:
        """Fetch both financial disclosures and voting records.

        Writes combined results to /tmp/efd_data.json and returns the dict.
        """
        logger.info("[EFDClient] Starting full data fetch...")

        disclosures = await self.fetch_financial_disclosures()
        votes = await self.fetch_votes(bioguide_id, congress_api_key)

        result = {
            "assets": disclosures.get("assets", []),
            "transactions": disclosures.get("transactions", []),
            "votes": votes,
        }

        output_path = "/tmp/efd_data.json"
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2)
        logger.info("[EFDClient] Data written to %s", output_path)

        return result


def _strip_tags(html: str) -> str:
    """Strip HTML tags and surrounding whitespace from a cell value."""
    return re.sub(r"<[^>]+>", "", str(html)).strip()


def _extract_href(html: str) -> str:
    """Extract the first href from an HTML fragment."""
    match = re.search(r'href="([^"]+)"', html)
    if match:
        url = match.group(1)
        if url.startswith("/"):
            return EFD_BASE + url
        return url
    return ""
