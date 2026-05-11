"""FEC OpenAPI client.

All calls go through `SmartRateLimiter` (api_name="fec") so the process-wide
token bucket enforces the 1000/hr API quota and we never trigger the 429-storm
that hung the scheduler in April–May 2026.

On 429, callers get a `FECRateLimitError` so they can abort the run rather than
hammering the next candidate. On other HTTPStatusError, `FECHTTPError` is raised.
"""

import json
import logging

import httpx

from app.services.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

BASE_URL = "https://api.open.fec.gov/v1"
MAX_PAGES = 5
TIMEOUT = 30.0


class FECError(Exception):
    """Base class for FEC client errors."""


class FECRateLimitError(FECError):
    """Raised on 429. Callers should abort their batch run."""


class FECHTTPError(FECError):
    """Raised on non-429 HTTP errors."""


class FECClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = BASE_URL
        self._limiter = get_rate_limiter()

    async def _get(self, url: str, params: dict) -> dict:
        """Single GET through the rate limiter. Raises FECRateLimitError on 429."""
        async with self._limiter.acquire("fec"):
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(url, params=params)
                if response.status_code == 429:
                    raise FECRateLimitError(
                        f"FEC returned 429 for {url} — quota exhausted"
                    )
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as e:
                    raise FECHTTPError(str(e)) from e
                return response.json()

    async def fetch_candidate_totals(
        self, candidate_id: str, cycle: int = 2024
    ) -> dict:
        """Fetch financial totals for a candidate."""
        url = f"{BASE_URL}/candidate/{candidate_id}/totals/"
        params = {"api_key": self.api_key, "cycle": cycle}
        logger.debug("[FEC] candidate_totals %s cycle=%s", candidate_id, cycle)
        data = await self._get(url, params)
        results = data.get("results", [])
        return results[0] if results else {}

    async def fetch_top_contributors(
        self, committee_id: str, cycle: int = 2024, per_page: int = 100
    ) -> list:
        """Fetch top individual contributors for a committee, up to 3 pages."""
        url = f"{BASE_URL}/schedules/schedule_a/"
        params = {
            "api_key": self.api_key,
            "committee_id": committee_id,
            "per_page": per_page,
            "sort": "-contribution_receipt_amount",
            "two_year_transaction_period": cycle,
        }
        logger.debug("[FEC] top_contributors %s cycle=%s", committee_id, cycle)
        return await self._paginate_schedule_a(url, params)

    async def fetch_pac_contributions(
        self, committee_id: str, cycle: int = 2024, per_page: int = 100
    ) -> list:
        """Fetch PAC/committee contributions for a committee, up to 3 pages."""
        url = f"{BASE_URL}/schedules/schedule_a/"
        params = {
            "api_key": self.api_key,
            "committee_id": committee_id,
            "per_page": per_page,
            "sort": "-contribution_receipt_amount",
            "two_year_transaction_period": cycle,
            "contributor_type": "committee",
        }
        logger.debug("[FEC] pac_contributions %s cycle=%s", committee_id, cycle)
        return await self._paginate_schedule_a(url, params)

    async def _paginate_schedule_a(self, url: str, params: dict) -> list:
        """Paginate through schedule_a results using cursor pagination."""
        all_results: list = []
        for page_num in range(1, MAX_PAGES + 1):
            data = await self._get(url, params)
            results = data.get("results", [])
            all_results.extend(results)

            if not results:
                break

            last_indexes = (data.get("pagination") or {}).get("last_indexes")
            if not last_indexes:
                break
            for key, value in last_indexes.items():
                params[key] = value

        logger.debug("[FEC] paginated total=%d", len(all_results))
        return all_results

    async def fetch_all(self, candidate_id: str, committee_id: str) -> dict:
        """Fetch all FEC data for a candidate/committee and write to
        /tmp/fec_data.json (debug helper, used by ad-hoc scripts)."""
        logger.info(
            "[FEC] fetch_all candidate=%s committee=%s",
            candidate_id, committee_id,
        )

        totals = await self.fetch_candidate_totals(candidate_id)
        top_contributors = await self.fetch_top_contributors(committee_id)

        try:
            pac_contributions = await self.fetch_pac_contributions(committee_id)
        except FECError as e:
            logger.warning("[FEC] PAC contributions fetch failed (non-fatal): %s", e)
            pac_contributions = []

        result = {
            "totals": totals,
            "top_contributors": top_contributors,
            "pac_contributions": pac_contributions,
            "committee_id": committee_id,
            "candidate_id": candidate_id,
        }

        with open("/tmp/fec_data.json", "w") as f:
            json.dump(result, f, indent=2, default=str)

        return result

    def _extract_candidate(self, candidate: dict) -> dict:
        return {
            "candidate_id": candidate.get("candidate_id", ""),
            "name": candidate.get("name", ""),
            "party": candidate.get("party_full", ""),
            "state": candidate.get("state", ""),
            "office": candidate.get("office_full", ""),
            "election_years": candidate.get("election_years", []),
            "principal_committees": candidate.get("principal_committees", []),
        }

    async def _fec_search(self, query: str, state: str = "") -> list:
        url = f"{self.base_url}/candidates/search/"
        params = {
            "api_key": self.api_key,
            "q": query,
            "sort": "-first_file_date",
            "per_page": 5,
        }
        if state:
            params["state"] = state
        data = await self._get(url, params)
        return data.get("results", [])

    def _normalize_name_variants(self, name: str) -> list[str]:
        """Generate multiple search variants from a name to handle the
        FEC ↔ Congress.gov naming differences (nicknames, suffixes, etc.)."""
        variants = []
        clean = name.strip()
        variants.append(clean)

        parts = clean.split()
        if len(parts) >= 2:
            last_name = parts[-1]
            if last_name.rstrip(".").lower() in ("jr", "sr", "ii", "iii", "iv"):
                last_name = parts[-2] if len(parts) > 2 else parts[0]
            variants.append(last_name)

            first_name = parts[0]
            if first_name != last_name:
                variants.append(f"{first_name} {last_name}")

        seen = set()
        unique = []
        for v in variants:
            if v.lower() not in seen:
                seen.add(v.lower())
                unique.append(v)
        return unique

    async def search_candidate(
        self, name: str, state: str = "", chamber: str = ""
    ) -> dict | None:
        """Search FEC for a candidate by name using multi-strategy matching."""
        variants = self._normalize_name_variants(name)
        logger.debug("[FEC] search %s variants=%s", name, variants)

        try:
            results: list = []
            for variant in variants:
                results = await self._fec_search(variant, state)
                if results:
                    break

            if not results:
                return None

            for candidate in results:
                office = (candidate.get("office_full") or "").lower()
                if "senate" in office:
                    return self._extract_candidate(candidate)

            for candidate in results:
                office = (candidate.get("office_full") or "").lower()
                if "house" in office:
                    return self._extract_candidate(candidate)

            return self._extract_candidate(results[0])

        except FECError as e:
            logger.warning("[FEC] search %s failed: %s", name, e)
            return None
