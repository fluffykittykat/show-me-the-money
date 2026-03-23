"""
Government Contracts Client — USASpending.gov API
Real endpoint: https://api.usaspending.gov/api/v2/search/spending_by_award/
No API key required. Currently returns mock data matching real API response shapes.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ContractsClient:
    """Fetches federal contract data from USASpending.gov and cross-references with donor data."""

    BASE_URL = "https://api.usaspending.gov/api/v2"

    def __init__(self):
        self._use_mock = True

    async def fetch_contracts_by_recipient(self, company_name: str) -> list[dict[str, Any]]:
        """Search for federal contracts awarded to a specific company."""
        if self._use_mock:
            return self._mock_contracts(company_name)
        # Real implementation:
        # POST {BASE_URL}/search/spending_by_award/
        # body: {"filters": {"recipient_search_text": [company_name], "award_type_codes": ["A","B","C","D"]}, ...}
        raise NotImplementedError("Real USASpending API integration not yet implemented")

    async def fetch_contracts_by_state(self, state: str, limit: int = 50) -> list[dict[str, Any]]:
        """Fetch top contracts in a state for cross-referencing with donations."""
        if self._use_mock:
            return self._mock_state_contracts(state)
        raise NotImplementedError("Real USASpending API integration not yet implemented")

    def _mock_contracts(self, company_name: str) -> list[dict[str, Any]]:
        """Mock data matching USASpending.gov API response shape."""
        contracts_db = {
            "keystone infrastructure": [
                {
                    "Award ID": "DOT-PA-2024-0847",
                    "Recipient Name": "Keystone Infrastructure Group",
                    "Award Amount": 12000000,
                    "Awarding Agency": "Department of Transportation",
                    "Award Type": "Contract",
                    "Description": "Highway bridge replacement, I-76 corridor, Montgomery County PA",
                    "Start Date": "2024-02-20",
                    "End Date": "2026-02-20",
                    "Place of Performance": "Montgomery County, PA",
                    "Recipient State": "PA",
                }
            ],
            "penntech": [
                {
                    "Award ID": "VA-PA-2024-1203",
                    "Recipient Name": "PennTech Solutions",
                    "Award Amount": 8500000,
                    "Awarding Agency": "Department of Veterans Affairs",
                    "Award Type": "Contract",
                    "Description": "Electronic health records modernization, Philadelphia VA Medical Center",
                    "Start Date": "2024-08-05",
                    "End Date": "2027-08-05",
                    "Place of Performance": "Philadelphia, PA",
                    "Recipient State": "PA",
                }
            ],
            "commonwealth health": [
                {
                    "Award ID": "HHS-PA-2024-0392",
                    "Recipient Name": "Commonwealth Health Partners",
                    "Award Amount": 22000000,
                    "Awarding Agency": "Department of Health and Human Services",
                    "Award Type": "Contract",
                    "Description": "Rural healthcare expansion program, Western Pennsylvania",
                    "Start Date": "2024-04-15",
                    "End Date": "2028-04-15",
                    "Place of Performance": "Western PA (multiple counties)",
                    "Recipient State": "PA",
                }
            ],
        }
        key = company_name.lower()
        for k, v in contracts_db.items():
            if k in key:
                return v
        return []

    def _mock_state_contracts(self, state: str) -> list[dict[str, Any]]:
        if state.upper() == "PA":
            return (
                self._mock_contracts("keystone infrastructure")
                + self._mock_contracts("penntech")
                + self._mock_contracts("commonwealth health")
            )
        return []
