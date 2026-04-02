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

import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

EFD_BASE = "https://efdsearch.senate.gov"
EFD_HOME = f"{EFD_BASE}/search/home/"
EFD_SEARCH = f"{EFD_BASE}/search/"
EFD_DATA = f"{EFD_BASE}/search/report/data/"


class EFDClient:
    """Fetches Senate Electronic Financial Disclosure data and voting records."""

    def __init__(self):
        self.congress_base_url = "https://api.congress.gov/v3"
        self.timeout = 30.0

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

        Args:
            start_date: MM/DD/YYYY format
            end_date: MM/DD/YYYY format
            last_name: Senator last name filter
            first_name: Senator first name filter
            state: Two-letter state code filter
            length: Number of results to fetch (max per request)

        Returns:
            List of PTR records with fields: first_name, last_name, report_type,
            date_received, report_url
        """
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True
            ) as client:
                csrf = await self._get_efd_session(client)
                if not csrf:
                    return []

                resp = await client.post(
                    EFD_DATA,
                    data={
                        "draw": "1",
                        "start": "0",
                        "length": str(length),
                        "report_types": "[11]",  # PTR
                        "filer_types": "[]",
                        "submitted_start_date": start_date,
                        "submitted_end_date": end_date,
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
                    # DataTables returns rows as lists of HTML strings
                    if isinstance(row, list) and len(row) >= 5:
                        # Parse HTML fragments
                        name_parts = re.sub(r"<[^>]+>", "", row[0]).strip().split(", ")
                        records.append({
                            "last_name": name_parts[0] if name_parts else "",
                            "first_name": name_parts[1] if len(name_parts) > 1 else "",
                            "office": re.sub(r"<[^>]+>", "", row[1]).strip(),
                            "report_type": re.sub(r"<[^>]+>", "", row[2]).strip(),
                            "date_received": re.sub(r"<[^>]+>", "", row[3]).strip(),
                            "report_url": _extract_href(row[4]),
                        })
                    elif isinstance(row, dict):
                        records.append(row)

                logger.info("[EFDClient] Fetched %d PTR records", len(records))
                return records

        except httpx.HTTPStatusError as e:
            logger.warning("[EFDClient] HTTP error fetching PTRs: %s", e.response.status_code)
            return []
        except (httpx.ConnectError, httpx.ConnectTimeout, OSError) as e:
            logger.warning("[EFDClient] Connection error fetching PTRs: %s", e)
            return []
        except Exception as e:
            logger.warning("[EFDClient] Unexpected error fetching PTRs: %s", e)
            return []

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


def _extract_href(html: str) -> str:
    """Extract the first href from an HTML fragment."""
    match = re.search(r'href="([^"]+)"', html)
    if match:
        url = match.group(1)
        if url.startswith("/"):
            return EFD_BASE + url
        return url
    return ""
