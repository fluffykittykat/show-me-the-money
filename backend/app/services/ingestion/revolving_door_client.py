"""
Revolving Door Client — LDA Senate API
Real endpoint: https://lda.senate.gov/api/v1/registrations/?covered_official_position=true&format=json
Currently returns mock data matching real API response shapes.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


class RevolvingDoorClient:
    """Fetches LDA registrations where lobbyists disclosed former government positions."""

    BASE_URL = "https://lda.senate.gov/api/v1"

    def __init__(self):
        self._use_mock = True  # Flip to False when ready for real API

    async def fetch_revolving_door_registrations(self, official_name: str | None = None) -> list[dict[str, Any]]:
        """Fetch LDA registrations where covered_official_position is not null."""
        if self._use_mock:
            return self._mock_registrations(official_name)
        # Real implementation would be:
        # GET {BASE_URL}/registrations/?covered_official_position=true&format=json
        raise NotImplementedError("Real LDA API integration not yet implemented")

    async def fetch_lobbyist_details(self, registrant_id: str) -> dict[str, Any]:
        """Fetch details for a specific lobbyist registration."""
        if self._use_mock:
            return self._mock_lobbyist_details(registrant_id)
        raise NotImplementedError("Real LDA API integration not yet implemented")

    def _mock_registrations(self, official_name: str | None = None) -> list[dict[str, Any]]:
        """Mock data matching real LDA API response shape."""
        registrations = [
            {
                "registration_id": "mock-lda-001",
                "registrant": {"name": "Capitol Bridge Partners", "id": "R-001"},
                "lobbyists": [
                    {
                        "name": "Marcus Webb",
                        "covered_official_position": "Chief of Staff, Senate Banking Committee (2017-2021)",
                        "new_lobbyist": False,
                    }
                ],
                "client": {"name": "JPMorgan Chase", "id": "C-001"},
                "specific_lobbying_issues": "Financial regulation, banking oversight, capital requirements",
                "filing_year": 2024,
                "filing_period": "Q4",
                "income": 420000,
                "url": "https://lda.senate.gov/filings/mock-001",
            },
            {
                "registration_id": "mock-lda-002",
                "registrant": {"name": "Harvest Policy Group", "id": "R-002"},
                "lobbyists": [
                    {
                        "name": "Sarah Chen-Watkins",
                        "covered_official_position": "Legislative Director, Office of Sen. Fetterman (2023-2024)",
                        "new_lobbyist": True,
                    }
                ],
                "client": {"name": "Cargill", "id": "C-002"},
                "specific_lobbying_issues": "Agricultural subsidies, farm bill provisions, nutrition programs",
                "filing_year": 2024,
                "filing_period": "Q2",
                "income": 280000,
                "url": "https://lda.senate.gov/filings/mock-002",
            },
            {
                "registration_id": "mock-lda-003",
                "registrant": {"name": "PhRMA", "id": "R-003"},
                "lobbyists": [
                    {
                        "name": "David Thornton",
                        "covered_official_position": "General Counsel, Senate Banking Committee (2019-2022)",
                        "new_lobbyist": False,
                    }
                ],
                "client": {"name": "Pfizer", "id": "C-003"},
                "specific_lobbying_issues": "Drug pricing regulation, pharmaceutical patent reform, FDA approval process",
                "filing_year": 2025,
                "filing_period": "Q1",
                "income": 650000,
                "url": "https://lda.senate.gov/filings/mock-003",
            },
        ]
        return registrations

    def _mock_lobbyist_details(self, registrant_id: str) -> dict[str, Any]:
        return {"registrant_id": registrant_id, "status": "active"}
