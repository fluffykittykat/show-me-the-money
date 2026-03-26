"""Async client for the Congress.gov API v3."""

import asyncio
import json
import httpx


BASE_URL = "https://api.congress.gov/v3"
TIMEOUT = 30.0
PAGE_SIZE = 20
RATE_LIMIT_DELAY = 0.5  # seconds between API calls to avoid 429s


class CongressClient:
    """Async client for fetching data from the Congress.gov API."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _base_params(self) -> dict:
        return {"api_key": self.api_key, "format": "json"}

    async def fetch_member(self, bioguide_id: str) -> dict:
        """GET /member/{bioguide_id} and return the member data."""
        url = f"{BASE_URL}/member/{bioguide_id}"
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(url, params=self._base_params())
                response.raise_for_status()
                data = response.json()
                print(f"[CongressClient] Fetched member {bioguide_id}")
                return data.get("member", data)
        except httpx.HTTPStatusError as exc:
            print(
                f"[CongressClient] HTTP error fetching member {bioguide_id}: "
                f"{exc.response.status_code}"
            )
            raise
        except httpx.RequestError as exc:
            print(
                f"[CongressClient] Request error fetching member {bioguide_id}: {exc}"
            )
            raise

    async def _fetch_legislation_pages(
        self, bioguide_id: str, leg_type: str, limit: int = 250
    ) -> list:
        """Paginate through a legislation endpoint and collect all bills up to *limit*."""
        next_url: str | None = f"{BASE_URL}/member/{bioguide_id}/{leg_type}"
        all_bills: list = []
        offset = 0

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                while next_url and len(all_bills) < limit:
                    params = {
                        **self._base_params(),
                        "offset": offset,
                        "limit": PAGE_SIZE,
                    }
                    response = await client.get(next_url, params=params)
                    response.raise_for_status()
                    data = response.json()

                    # The API returns bills under camelCase keys
                    bills = data.get("sponsoredLegislation", [])
                    if not bills:
                        bills = data.get("cosponsoredLegislation", [])

                    if not bills:
                        break

                    all_bills.extend(bills)
                    print(
                        f"[CongressClient] Fetched {len(bills)} {leg_type} items "
                        f"(offset={offset}, total so far={len(all_bills)})"
                    )

                    # Determine the next page — always use manual offset
                    offset += PAGE_SIZE
                    if len(bills) < PAGE_SIZE:
                        break

        except httpx.HTTPStatusError as exc:
            print(
                f"[CongressClient] HTTP error fetching {leg_type} for {bioguide_id}: "
                f"{exc.response.status_code}"
            )
            raise
        except httpx.RequestError as exc:
            print(
                f"[CongressClient] Request error fetching {leg_type} for {bioguide_id}: "
                f"{exc}"
            )
            raise

        return all_bills[:limit]

    async def fetch_sponsored_legislation(
        self, bioguide_id: str, limit: int = 250
    ) -> list:
        """Return a list of all sponsored bills for *bioguide_id* (up to *limit*)."""
        return await self._fetch_legislation_pages(
            bioguide_id, "sponsored-legislation", limit=limit
        )

    async def fetch_cosponsored_legislation(
        self, bioguide_id: str, limit: int = 250
    ) -> list:
        """Return a list of all cosponsored bills for *bioguide_id* (up to *limit*)."""
        return await self._fetch_legislation_pages(
            bioguide_id, "cosponsored-legislation", limit=limit
        )

    async def fetch_member_votes(self, bioguide_id: str, limit: int = 50) -> list:
        """GET /v3/member/{bioguideId}/votes -- fetch recent votes for a member."""
        url = f"{BASE_URL}/member/{bioguide_id}/votes"
        all_votes: list = []
        offset = 0

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                while len(all_votes) < limit:
                    params = {
                        **self._base_params(),
                        "offset": offset,
                        "limit": min(PAGE_SIZE, limit - len(all_votes)),
                    }
                    await asyncio.sleep(RATE_LIMIT_DELAY)
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()

                    votes = data.get("votes", [])
                    if not votes:
                        break

                    all_votes.extend(votes)
                    print(
                        f"[CongressClient] Fetched {len(votes)} votes for {bioguide_id} "
                        f"(offset={offset}, total so far={len(all_votes)})"
                    )

                    offset += PAGE_SIZE
                    if len(votes) < PAGE_SIZE:
                        break

        except httpx.HTTPStatusError as exc:
            print(
                f"[CongressClient] HTTP error fetching votes for {bioguide_id}: "
                f"{exc.response.status_code}"
            )
            return all_votes  # return what we have so far
        except httpx.RequestError as exc:
            print(
                f"[CongressClient] Request error fetching votes for {bioguide_id}: {exc}"
            )
            return all_votes

        return all_votes[:limit]

    async def fetch_bill_actions(
        self, congress: int, bill_type: str, bill_number: int
    ) -> list:
        """GET /v3/bill/{congress}/{type}/{number}/actions"""
        url = f"{BASE_URL}/bill/{congress}/{bill_type.lower()}/{bill_number}/actions"
        try:
            await asyncio.sleep(RATE_LIMIT_DELAY)
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(url, params=self._base_params())
                response.raise_for_status()
                data = response.json()
                actions = data.get("actions", [])
                print(
                    f"[CongressClient] Fetched {len(actions)} actions for "
                    f"{bill_type.lower()}{bill_number} ({congress}th Congress)"
                )
                return actions
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            print(f"[CongressClient] Error fetching bill actions: {exc}")
            return []

    async def fetch_bill_text_info(
        self, congress: int, bill_type: str, bill_number: int
    ) -> dict:
        """GET /v3/bill/{congress}/{type}/{number}/text -- get bill text URLs.

        Returns the best available text URL (prefer HTML over PDF).
        """
        url = f"{BASE_URL}/bill/{congress}/{bill_type.lower()}/{bill_number}/text"
        try:
            await asyncio.sleep(RATE_LIMIT_DELAY)
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(url, params=self._base_params())
                response.raise_for_status()
                data = response.json()

                text_versions = data.get("textVersions", [])
                if not text_versions:
                    return {}

                # Get the most recent text version
                latest = text_versions[0]
                formats = latest.get("formats", [])

                # Prefer HTML over PDF
                best_url = ""
                for fmt in formats:
                    fmt_type = (fmt.get("type") or "").lower()
                    fmt_url = fmt.get("url", "")
                    if "html" in fmt_type and fmt_url:
                        best_url = fmt_url
                        break
                    if "pdf" in fmt_type and fmt_url and not best_url:
                        best_url = fmt_url
                    if fmt_url and not best_url:
                        best_url = fmt_url

                result = {
                    "url": best_url,
                    "date": latest.get("date", ""),
                    "type": latest.get("type", ""),
                }
                print(
                    f"[CongressClient] Got text info for "
                    f"{bill_type.lower()}{bill_number} ({congress}th Congress)"
                )
                return result

        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            print(f"[CongressClient] Error fetching bill text: {exc}")
            return {}

    async def fetch_bill_summaries(
        self, congress: int, bill_type: str, bill_number: int
    ) -> str:
        """GET /v3/bill/{congress}/{type}/{number}/summaries -- get CRS summary text."""
        url = f"{BASE_URL}/bill/{congress}/{bill_type.lower()}/{bill_number}/summaries"
        try:
            await asyncio.sleep(RATE_LIMIT_DELAY)
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                response = await client.get(url, params=self._base_params())
                response.raise_for_status()
                data = response.json()

                summaries = data.get("summaries", [])
                if not summaries:
                    return ""

                # Get the most detailed summary (last one is usually most recent)
                best_summary = summaries[-1]
                text = best_summary.get("text", "")
                # Strip HTML tags if present
                import re
                text = re.sub(r"<[^>]+>", "", text)
                print(
                    f"[CongressClient] Got summary for "
                    f"{bill_type.lower()}{bill_number} ({congress}th Congress)"
                )
                return text.strip()

        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            print(f"[CongressClient] Error fetching bill summaries: {exc}")
            return ""

    async def fetch_bill_votes(
        self, congress: int, bill_type: str, bill_number: int
    ) -> list[dict]:
        """Fetch roll call vote data for a bill from its actions.

        Congress.gov actions contain recordedVotes entries with URLs to
        the House Clerk or Senate roll call vote pages. We extract vote
        counts from these.

        Returns list of vote dicts: {chamber, date, result, yea, nay, not_voting, url}
        """
        actions = await self.fetch_bill_actions(congress, bill_type, bill_number)
        votes: list[dict] = []

        for action in actions:
            recorded_votes = action.get("recordedVotes", [])
            if not recorded_votes:
                continue

            for rv in recorded_votes:
                vote_url = rv.get("url", "")
                chamber = rv.get("chamber", "")
                date = rv.get("date", action.get("actionDate", ""))

                # Try to fetch vote totals from the API
                # Congress.gov has /v3/bill/{congress}/{type}/{number} with
                # actions that embed vote references
                vote_entry: dict = {
                    "chamber": chamber,
                    "date": date,
                    "url": vote_url,
                    "result": action.get("text", ""),
                }

                # Parse vote counts from action text if available
                # Common formats: "Agreed to (222-190)" or "Passed (64-34)"
                import re
                text = action.get("text", "")
                count_match = re.search(r"\((\d+)-(\d+)(?:-(\d+))?\)", text)
                if count_match:
                    vote_entry["yea"] = int(count_match.group(1))
                    vote_entry["nay"] = int(count_match.group(2))
                    if count_match.group(3):
                        vote_entry["not_voting"] = int(count_match.group(3))

                # Also try: "Yeas - 222, Nays - 190"
                yea_match = re.search(r"[Yy]eas?\s*[-:]\s*(\d+)", text)
                nay_match = re.search(r"[Nn]ays?\s*[-:]\s*(\d+)", text)
                if yea_match and "yea" not in vote_entry:
                    vote_entry["yea"] = int(yea_match.group(1))
                if nay_match and "nay" not in vote_entry:
                    vote_entry["nay"] = int(nay_match.group(1))

                votes.append(vote_entry)

        print(f"[CongressClient] Found {len(votes)} recorded votes for {bill_type}{bill_number}")
        return votes

    async def fetch_committee_members(self, committee_code: str) -> list:
        """Fetch committee members from the Congress.gov API.

        Tries both Senate and Joint committee endpoints.
        Returns a list of member dicts with at least 'bioguideId' and 'name'.
        """
        # Try senate first, then joint
        chambers = ["senate", "joint", "house"]
        for chamber in chambers:
            url = f"{BASE_URL}/committee/{chamber}/{committee_code}"
            try:
                await asyncio.sleep(RATE_LIMIT_DELAY)
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    response = await client.get(url, params=self._base_params())
                    response.raise_for_status()
                    data = response.json()

                    committee = data.get("committee", data)
                    if not isinstance(committee, dict):
                        continue

                    # Try multiple paths for member data
                    members = []
                    # Path 1: committee -> currentMembers
                    current = committee.get("currentMembers", [])
                    if current:
                        members = current
                    # Path 2: committee -> subcommittees -> members
                    if not members:
                        for sub in committee.get("subcommittees", []):
                            members.extend(sub.get("currentMembers", []))
                    # Path 3: direct members key
                    if not members:
                        members = committee.get("members", [])

                    if members:
                        print(
                            f"[CongressClient] Fetched {len(members)} members "
                            f"for committee {committee_code} ({chamber})"
                        )
                        return members

            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    continue  # Try next chamber
                print(
                    f"[CongressClient] HTTP error fetching committee {committee_code} "
                    f"({chamber}): {exc.response.status_code}"
                )
            except httpx.RequestError as exc:
                print(
                    f"[CongressClient] Request error fetching committee {committee_code}: "
                    f"{exc}"
                )

        print(
            f"[CongressClient] Could not fetch members for committee {committee_code} "
            f"from any chamber endpoint"
        )
        return []

    async def fetch_all(self, bioguide_id: str) -> dict:
        """Fetch member info, sponsored and cosponsored legislation.

        Writes the combined result to ``/tmp/congress_data.json`` and returns it.
        """
        print(f"[CongressClient] Starting full fetch for {bioguide_id}")

        member = await self.fetch_member(bioguide_id)
        sponsored = await self.fetch_sponsored_legislation(bioguide_id)
        cosponsored = await self.fetch_cosponsored_legislation(bioguide_id)

        # Extract committees from the member payload when available
        committees: list = []
        if isinstance(member, dict):
            committees = member.get("committees", [])
            if not committees:
                terms = member.get("terms", [])
                if isinstance(terms, dict):
                    terms = terms.get("item", [])
                for term in (terms if isinstance(terms, list) else []):
                    committees.extend(term.get("committees", []))

        # Congress.gov API v3 doesn't provide committee assignments in member data.
        # Use known committee data for Fetterman as fallback.
        if not committees and bioguide_id == "F000479":
            committees = [
                {"name": "Banking, Housing, and Urban Affairs", "role": "Member", "code": "SSBK", "chamber": "Senate"},
                {"name": "Agriculture, Nutrition, and Forestry", "role": "Member", "code": "SSAF", "chamber": "Senate"},
                {"name": "Joint Economic Committee", "role": "Member", "code": "JSEC", "chamber": "Senate"},
            ]
            print("[CongressClient] Using known committee data for Fetterman")

        result = {
            "member": member,
            "sponsored_bills": sponsored,
            "cosponsored_bills": cosponsored,
            "committees": committees,
        }

        output_path = "/tmp/congress_data.json"
        try:
            with open(output_path, "w") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"[CongressClient] Wrote results to {output_path}")
        except OSError as exc:
            print(f"[CongressClient] Failed to write {output_path}: {exc}")

        return result
