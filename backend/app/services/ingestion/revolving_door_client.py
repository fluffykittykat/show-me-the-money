"""
Revolving Door Client — LDA Senate API
Real endpoint: https://lda.senate.gov/api/v1/registrations/?covered_official_position=true&format=json
Currently returns mock data matching real API response shapes.
"""
import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

_FIRST_NAMES = [
    "Marcus", "Sarah", "David", "Rachel", "Anthony", "Laura", "James", "Priya",
    "Daniel", "Monica", "Kevin", "Yuki", "Brandon", "Natasha", "Gregory", "Mei",
    "Theodore", "Camille", "Victor", "Ingrid", "Wesley", "Fatima", "Russell",
    "Adrienne", "Malcolm", "Renata", "Oscar", "Simone", "Franklin", "Daphne",
    "Clayton", "Bianca",
]

_LAST_NAMES = [
    "Webb", "Chen", "Thornton", "Morrison", "Graves", "Petrov", "Whitfield",
    "Kapoor", "Reeves", "Sandoval", "O'Malley", "Tanaka", "Harrington", "Dubois",
    "Castillo", "Nakamura", "Brennan", "Okonkwo", "Lindqvist", "Patel",
    "Fitzgerald", "Romanov", "Alvarez", "Johansson", "Whitaker", "Nguyen",
    "Hartwell", "Bianchi", "Prescott", "Kowalski", "Delgado", "Eriksson",
]

_LOBBYING_FIRMS = [
    "Capitol Bridge Partners", "Harbour Policy Group", "Meridian Government Affairs",
    "Crossroads Strategy Group", "Potomac Advocacy Partners", "Summit Public Affairs",
    "Ironclad Policy Solutions", "Horizon Government Relations", "Cornerstone Policy Advisors",
    "Pinnacle Strategies LLC", "Atlas Federal Affairs", "Keystone Advocacy Group",
    "Constellation Policy Partners", "Ridgeline Government Solutions", "Liberty Hill Advisors",
    "Trident Public Strategies", "Vanguard Policy Group", "Sterling Government Relations",
    "Northstar Advocacy LLC", "Sentinel Public Affairs", "Blackstone Policy Partners",
    "Greystone Government Relations", "Pacific Rim Advisors", "Beltway Strategy Group",
    "Fulcrum Policy Consultants", "Redwood Government Affairs", "Granite State Advisors",
    "Ironbridge Public Policy", "Civic Square Partners", "Clearpath Government Solutions",
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
    ("Chevron", "Oil and gas leasing, environmental compliance, pipeline regulation"),
    ("Meta Platforms", "Social media regulation, content moderation, digital advertising"),
    ("Raytheon Technologies", "Missile defense, military procurement, export controls"),
    ("AT&T", "Spectrum allocation, rural broadband, telecom mergers"),
    ("General Motors", "EV tax credits, auto emissions standards, trade tariffs"),
    ("Walmart", "Minimum wage policy, supply chain regulation, trade agreements"),
    ("Cigna Group", "Pharmacy benefit management, health plan regulation, drug formularies"),
    ("Northrop Grumman", "Space systems, nuclear modernization, intelligence contracts"),
    ("Apple", "Digital markets regulation, app store policy, encryption standards"),
    ("Goldman Sachs", "Securities regulation, capital markets reform, fiduciary standards"),
    ("Caterpillar", "Infrastructure spending, trade policy, emissions standards"),
    ("FedEx", "Postal reform, logistics regulation, drone delivery policy"),
    ("Duke Energy", "Grid modernization, nuclear licensing, clean energy credits"),
    ("Anthem Blue Cross", "ACA marketplace rules, Medicaid expansion, telehealth policy"),
    ("Shell USA", "Carbon capture incentives, refinery permits, LNG exports"),
    ("Microsoft", "Cloud computing procurement, AI regulation, cybersecurity standards"),
    ("Dow Chemical", "Chemical safety rules, PFAS regulation, trade policy"),
    ("Delta Air Lines", "FAA reauthorization, airport slot allocation, fuel tax policy"),
    ("Humana", "Medicare Advantage, home health regulation, senior care policy"),
    ("Koch Industries", "Regulatory reform, energy deregulation, labor policy"),
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
            # Use official_name + index as seed for each registration
            reg_seed = f"{seed}{i}"
            reg_hex = hashlib.md5(reg_seed.encode()).hexdigest()
            reg_hash = int(reg_hex, 16)

            # Pick lobbyist name from independent first/last pools
            first_idx = reg_hash % len(_FIRST_NAMES)
            last_idx = (reg_hash // 7919) % len(_LAST_NAMES)
            lobbyist_name = f"{_FIRST_NAMES[first_idx]} {_LAST_NAMES[last_idx]}"

            firm_idx = reg_hash % len(_LOBBYING_FIRMS)
            client_idx = reg_hash % len(_CLIENTS)
            title_idx = (reg_hash // 7) % len(_STAFF_TITLES)
            committee_idx = (reg_hash // 11) % len(_COMMITTEE_NAMES)

            client_name, issues = _CLIENTS[client_idx]
            title = _STAFF_TITLES[title_idx]

            # Build position string — use official_name if available
            if official_name and (reg_hash % 3 != 0):
                last_name = official_name.split()[-1]
                position = f"{title}, Office of Sen. {last_name} ({2017 + (reg_hash % 6)}-{2022 + (reg_hash % 3)})"
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
                            "name": lobbyist_name,
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
