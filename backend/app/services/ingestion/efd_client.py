"""
Client for fetching Senate Electronic Financial Disclosure (eFD) data
and congressional voting records.
"""

import json
import httpx


class EFDClient:
    """Fetches Senate Electronic Financial Disclosure data and voting records."""

    def __init__(self):
        self.efd_base_url = "https://efts.senate.gov/LATEST/search-results"
        self.congress_base_url = "https://api.congress.gov/v3"
        self.timeout = 30.0

    async def fetch_financial_disclosures(self, senator_name: str = "Fetterman") -> dict:
        """Fetch financial disclosure filings from the Senate eFD system.

        The eFD system is notoriously difficult to scrape programmatically.
        If the request fails or returns empty data, this method returns an
        empty result with a note rather than raising an exception.
        """
        print(f"[EFDClient] Fetching financial disclosures for: {senator_name}")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self.efd_base_url,
                    params={
                        "q": f'"{senator_name}"',
                        "senator": "true",
                    },
                )
                response.raise_for_status()

                data = response.json()

                if not data:
                    print(f"[EFDClient] No disclosure data returned for {senator_name}")
                    return {
                        "assets": [],
                        "transactions": [],
                        "note": "eFD returned empty results. Manual parsing may be required.",
                    }

                assets = []
                transactions = []

                results = data if isinstance(data, list) else data.get("results", [])
                for record in results:
                    report_type = record.get("report_type", "")
                    entry = {
                        "senator": senator_name,
                        "date": record.get("date", ""),
                        "report_type": report_type,
                        "description": record.get("description", ""),
                        "raw": record,
                    }
                    if "transaction" in report_type.lower() or "ptr" in report_type.lower():
                        transactions.append(entry)
                    else:
                        assets.append(entry)

                print(
                    f"[EFDClient] Found {len(assets)} asset records and "
                    f"{len(transactions)} transaction records for {senator_name}"
                )
                return {
                    "assets": assets,
                    "transactions": transactions,
                }

        except httpx.HTTPStatusError as e:
            print(
                f"[EFDClient] HTTP error fetching disclosures for {senator_name}: "
                f"{e.response.status_code}"
            )
            return {
                "assets": [],
                "transactions": [],
                "note": f"eFD request failed with status {e.response.status_code}. "
                        "eFD requires manual parsing.",
            }
        except httpx.RequestError as e:
            print(f"[EFDClient] Request error fetching disclosures for {senator_name}: {e}")
            return {
                "assets": [],
                "transactions": [],
                "note": "eFD request failed due to connection error. "
                        "eFD requires manual parsing.",
            }
        except Exception as e:
            print(f"[EFDClient] Unexpected error fetching disclosures for {senator_name}: {e}")
            return {
                "assets": [],
                "transactions": [],
                "note": f"eFD parsing failed: {e}. eFD requires manual parsing.",
            }

    async def fetch_votes(self, bioguide_id: str, api_key: str) -> list:
        """Fetch recent voting records from the Congress.gov API.

        Returns a list of vote records, each containing: congress, session,
        rollNumber, question, result, date, description, and url.
        """
        print(f"[EFDClient] Fetching votes for bioguide_id: {bioguide_id}")
        url = f"{self.congress_base_url}/member/{bioguide_id}/votes"
        params = {
            "api_key": api_key,
            "format": "json",
            "limit": 20,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

            raw_votes = data.get("votes", [])
            votes = []
            for vote in raw_votes:
                votes.append({
                    "congress": vote.get("congress"),
                    "session": vote.get("session"),
                    "rollNumber": vote.get("rollNumber"),
                    "question": vote.get("question"),
                    "result": vote.get("result"),
                    "date": vote.get("date"),
                    "description": vote.get("description", ""),
                    "url": vote.get("url", ""),
                })

            print(f"[EFDClient] Found {len(votes)} vote records for {bioguide_id}")
            return votes

        except httpx.HTTPStatusError as e:
            print(
                f"[EFDClient] HTTP error fetching votes for {bioguide_id}: "
                f"{e.response.status_code}"
            )
            return []
        except httpx.RequestError as e:
            print(f"[EFDClient] Request error fetching votes for {bioguide_id}: {e}")
            return []
        except Exception as e:
            print(f"[EFDClient] Unexpected error fetching votes for {bioguide_id}: {e}")
            return []

    async def fetch_all(self, bioguide_id: str, congress_api_key: str) -> dict:
        """Fetch both financial disclosures and voting records.

        Writes combined results to /tmp/efd_data.json and returns the dict.
        """
        print("[EFDClient] Starting full data fetch...")

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
        print(f"[EFDClient] Data written to {output_path}")

        return result
