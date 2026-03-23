"""
Revolving Door Client — LDA Senate API
Real endpoint: https://lda.senate.gov/api/v1/registrations/?covered_official_position=true&format=json
Currently returns mock data matching real API response shapes.
"""
import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

_LOBBYING_FIRMS = [
    "Capitol Bridge Partners",
    "Harbour Policy Group",
    "Meridian Government Affairs",
    "Crossroads Strategy Group",
    "Potomac Advocacy Partners",
    "Summit Public Affairs",
    "Ironclad Policy Solutions",
    "Horizon Government Relations",
    "Cornerstone Policy Advisors",
    "Pinnacle Strategies LLC",
]

_LOBBYIST_NAMES = [
    "Marcus Webb", "Sarah Chen-Watkins", "David Thornton", "Rachel Morrison",
    "Anthony Graves", "Laura Petrov", "James Whitfield", "Priya Kapoor",
    "Daniel Reeves", "Monica Sandoval", "Kevin O'Malley", "Yuki Tanaka",
]

_CLIENTS = [
    ("JPMorgan Chase", "Financial regulation, banking oversight, capital requirements"),
    ("Cargill", "Agricultural subsidies, farm bill provisions, nutrition programs"),
    ("Pfizer", "Drug pricing regulation, pharmaceutical patent reform, FDA approval process"),
    ("Boeing", "Defense procurement, aerospace regulation, trade policy"),
    ("Google", "Data privacy, antitrust regulation, Section 230 reform"),
    ("ExxonMobil", "Energy policy, carbon regulation, offshore drilling permits"),
    ("Lockheed Martin", "Defense contracts, cybersecurity policy, space program funding"),
    ("Amazon", "E-commerce regulation, labor policy, antitrust enforcement"),
    ("UnitedHealth Group", "Healthcare regulation, Medicare policy, insurance reform"),
    ("Comcast", "Telecommunications policy, broadband access, net neutrality"),
]

_STAFF_TITLES = [
    "Chief of Staff", "Legislative Director", "Senior Policy Advisor",
    "General Counsel", "Communications Director", "Deputy Chief of Staff",
    "Senior Legislative Aide", "Policy Director",
]

_COMMITTEE_NAMES = [
    "Senate Banking Committee", "Senate Finance Committee",
    "Senate Commerce Committee", "Senate Judiciary Committee",
    "Senate Armed Services Committee", "Senate Appropriations Committee",
    "Senate Health Committee", "Senate Energy Committee",
]


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
        seed = official_name or "generic-official"
        hash_hex = hashlib.md5(seed.encode()).hexdigest()
        hash_int = int(hash_hex, 16)

        # Generate 1-4 registrations
        num_registrations = 1 + (hash_int % 4)
        registrations = []

        for i in range(num_registrations):
            reg_hash = hash_int + i * 9973  # offset per registration

            firm_idx = reg_hash % len(_LOBBYING_FIRMS)
            lobbyist_idx = reg_hash % len(_LOBBYIST_NAMES)
            client_idx = reg_hash % len(_CLIENTS)
            title_idx = (reg_hash // 7) % len(_STAFF_TITLES)
            committee_idx = (reg_hash // 11) % len(_COMMITTEE_NAMES)

            client_name, issues = _CLIENTS[client_idx]
            title = _STAFF_TITLES[title_idx]

            # Build position string — use official_name if available
            if official_name and (reg_hash % 3 != 0):
                position = f"{title}, Office of Sen. {official_name.split()[-1]} ({2017 + (reg_hash % 6)}-{2022 + (reg_hash % 3)})"
            else:
                committee = _COMMITTEE_NAMES[committee_idx]
                position = f"{title}, {committee} ({2017 + (reg_hash % 6)}-{2022 + (reg_hash % 3)})"

            year = 2024 + (reg_hash % 2)
            quarters = ["Q1", "Q2", "Q3", "Q4"]
            quarter = quarters[reg_hash % 4]
            income = 150000 + (reg_hash % 20) * 50000

            registrations.append(
                {
                    "registration_id": f"mock-lda-{hash_hex[:4]}-{i:03d}",
                    "registrant": {"name": _LOBBYING_FIRMS[firm_idx], "id": f"R-{firm_idx:03d}"},
                    "lobbyists": [
                        {
                            "name": _LOBBYIST_NAMES[lobbyist_idx],
                            "covered_official_position": position,
                            "new_lobbyist": reg_hash % 3 == 0,
                        }
                    ],
                    "client": {"name": client_name, "id": f"C-{client_idx:03d}"},
                    "specific_lobbying_issues": issues,
                    "filing_year": year,
                    "filing_period": quarter,
                    "income": income,
                    "url": f"https://lda.senate.gov/filings/mock-{hash_hex[:4]}-{i:03d}",
                }
            )

        return registrations

    def _mock_lobbyist_details(self, registrant_id: str) -> dict[str, Any]:
        return {"registrant_id": registrant_id, "status": "active"}
