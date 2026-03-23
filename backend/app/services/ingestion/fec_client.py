import asyncio
import json
import httpx

BASE_URL = "https://api.open.fec.gov/v1"
MAX_PAGES = 3
TIMEOUT = 30.0


class FECClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = BASE_URL

    async def fetch_candidate_totals(
        self, candidate_id: str, cycle: int = 2022
    ) -> dict:
        """Fetch financial totals for a candidate."""
        url = f"{BASE_URL}/candidate/{candidate_id}/totals/"
        params = {
            "api_key": self.api_key,
            "cycle": cycle,
        }
        print(f"[FEC] Fetching candidate totals for {candidate_id}, cycle={cycle}")
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            try:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])
                if results:
                    print(f"[FEC] Got totals for {candidate_id}")
                    return results[0]
                print(f"[FEC] No totals found for {candidate_id}")
                return {}
            except httpx.HTTPStatusError as e:
                print(f"[FEC] HTTP error fetching candidate totals: {e}")
                raise
            except httpx.RequestError as e:
                print(f"[FEC] Request error fetching candidate totals: {e}")
                raise

    async def fetch_top_contributors(
        self, committee_id: str, cycle: int = 2022, per_page: int = 100
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
        print(
            f"[FEC] Fetching top contributors for {committee_id}, cycle={cycle}"
        )
        return await self._paginate_schedule_a(url, params)

    async def fetch_pac_contributions(
        self, committee_id: str, cycle: int = 2022, per_page: int = 100
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
        print(
            f"[FEC] Fetching PAC contributions for {committee_id}, cycle={cycle}"
        )
        return await self._paginate_schedule_a(url, params)

    async def _paginate_schedule_a(self, url: str, params: dict) -> list:
        """Paginate through schedule_a results using keyset/cursor pagination.

        The FEC API uses cursor-based pagination via `last_index` and
        `last_contribution_receipt_amount` (provided in the `pagination.last_indexes`
        object of each response).
        """
        all_results = []
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            for page_num in range(1, MAX_PAGES + 1):
                try:
                    print(f"[FEC]   Fetching page {page_num}...")
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()

                    results = data.get("results", [])
                    all_results.extend(results)

                    if not results:
                        print(f"[FEC]   No more results at page {page_num}")
                        break

                    pagination = data.get("pagination", {})
                    last_indexes = pagination.get("last_indexes")

                    if not last_indexes:
                        print(f"[FEC]   No more pages (no last_indexes)")
                        break

                    # Apply cursor params for the next page
                    for key, value in last_indexes.items():
                        params[key] = value

                except httpx.HTTPStatusError as e:
                    print(f"[FEC] HTTP error on page {page_num}: {e}")
                    raise
                except httpx.RequestError as e:
                    print(f"[FEC] Request error on page {page_num}: {e}")
                    raise

        print(f"[FEC]   Total results fetched: {len(all_results)}")
        return all_results

    async def fetch_all(self, candidate_id: str, committee_id: str) -> dict:
        """Fetch all FEC data for a candidate/committee and write to /tmp/fec_data.json."""
        print(
            f"[FEC] Starting full fetch for candidate={candidate_id}, "
            f"committee={committee_id}"
        )

        totals = await self.fetch_candidate_totals(candidate_id)
        top_contributors = await self.fetch_top_contributors(committee_id)

        # Small delay to avoid FEC rate limiting after top_contributors fetch
        import asyncio
        await asyncio.sleep(2)

        try:
            pac_contributions = await self.fetch_pac_contributions(committee_id)
        except Exception as e:
            print(f"[FEC] PAC contributions fetch failed (non-fatal): {e}")
            pac_contributions = []

        result = {
            "totals": totals,
            "top_contributors": top_contributors,
            "pac_contributions": pac_contributions,
            "committee_id": committee_id,
            "candidate_id": candidate_id,
        }

        output_path = "/tmp/fec_data.json"
        with open(output_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"[FEC] Wrote FEC data to {output_path}")

        return result

    async def search_candidate(self, name: str, state: str = "") -> dict | None:
        """Search FEC for a candidate by name. Returns candidate info with FEC IDs.

        Searches for Senate candidates matching the given name and optionally
        filtered by state. Returns the first matching result or None.
        """
        url = f"{self.base_url}/candidates/search/"
        params = {
            "api_key": self.api_key,
            "q": name,
            "sort": "-election_year",
            "per_page": 5,
        }
        if state:
            params["state"] = state

        print(f"[FEC] Searching for candidate: {name}" + (f" ({state})" if state else ""))
        try:
            await asyncio.sleep(0.5)  # Rate limit
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                results = data.get("results", [])
                if not results:
                    print(f"[FEC] No candidates found for: {name}")
                    return None

                # Prefer Senate candidates
                for candidate in results:
                    office = (candidate.get("office_full") or "").lower()
                    if "senate" in office:
                        print(
                            f"[FEC] Found Senate candidate: {candidate.get('name')} "
                            f"(ID: {candidate.get('candidate_id')})"
                        )
                        return {
                            "candidate_id": candidate.get("candidate_id", ""),
                            "name": candidate.get("name", ""),
                            "party": candidate.get("party_full", ""),
                            "state": candidate.get("state", ""),
                            "office": candidate.get("office_full", ""),
                            "election_years": candidate.get("election_years", []),
                            "principal_committees": candidate.get(
                                "principal_committees", []
                            ),
                        }

                # Fall back to first result if no Senate match
                candidate = results[0]
                print(
                    f"[FEC] Found candidate (non-Senate): {candidate.get('name')} "
                    f"(ID: {candidate.get('candidate_id')})"
                )
                return {
                    "candidate_id": candidate.get("candidate_id", ""),
                    "name": candidate.get("name", ""),
                    "party": candidate.get("party_full", ""),
                    "state": candidate.get("state", ""),
                    "office": candidate.get("office_full", ""),
                    "election_years": candidate.get("election_years", []),
                    "principal_committees": candidate.get(
                        "principal_committees", []
                    ),
                }

        except httpx.HTTPStatusError as e:
            print(f"[FEC] HTTP error searching for candidate {name}: {e}")
            return None
        except httpx.RequestError as e:
            print(f"[FEC] Request error searching for candidate {name}: {e}")
            return None
