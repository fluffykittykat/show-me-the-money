"""
Government Contracts Client — USASpending.gov API
Real endpoint: https://api.usaspending.gov/api/v2/search/spending_by_award/
No API key required. Currently returns mock data matching real API response shapes.
"""
import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

_AGENCIES = [
    "Department of Transportation",
    "Department of Defense",
    "Department of Veterans Affairs",
    "Department of Health and Human Services",
    "Department of Energy",
    "Department of Homeland Security",
    "Department of Education",
    "Environmental Protection Agency",
    "General Services Administration",
    "National Aeronautics and Space Administration",
]

_CONTRACT_TEMPLATES = [
    ("Infrastructure Group", "Highway bridge replacement and road improvement", "Department of Transportation", 12000000),
    ("Tech Solutions", "Electronic health records modernization", "Department of Veterans Affairs", 8500000),
    ("Health Partners", "Rural healthcare expansion program", "Department of Health and Human Services", 22000000),
    ("Defense Systems", "Cybersecurity infrastructure upgrade", "Department of Defense", 15000000),
    ("Energy Innovations", "Renewable energy grid integration", "Department of Energy", 9800000),
    ("Security Services", "Border security technology deployment", "Department of Homeland Security", 11000000),
    ("Environmental Solutions", "Water treatment facility upgrade", "Environmental Protection Agency", 6500000),
    ("Education Services", "Digital learning platform deployment", "Department of Education", 4200000),
    ("Aerospace Corp", "Satellite communications system", "National Aeronautics and Space Administration", 18000000),
    ("Construction Co", "Federal building renovation", "General Services Administration", 7300000),
    ("Medical Devices Inc", "Hospital equipment procurement", "Department of Veterans Affairs", 5600000),
    ("Logistics Group", "Supply chain management system", "Department of Defense", 13500000),
]

_STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee",
    "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

_COUNTY_POOL = [
    "Central County", "Western District", "Eastern Region", "Northern County",
    "Metro Area", "Southern District", "Coastal Region", "Highland County",
]


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
        hash_hex = hashlib.md5(company_name.lower().encode()).hexdigest()
        hash_int = int(hash_hex, 16)

        # Pick a template based on company name hash
        tmpl_idx = hash_int % len(_CONTRACT_TEMPLATES)
        suffix, description, agency, base_amount = _CONTRACT_TEMPLATES[tmpl_idx]

        # Vary the amount somewhat
        amount = base_amount + (hash_int % 10) * 500000

        agency_prefix = agency.split()[-1][:3].upper()
        return [
            {
                "Award ID": f"{agency_prefix}-{hash_hex[:4].upper()}-2024-{hash_int % 9999:04d}",
                "Recipient Name": company_name,
                "Award Amount": amount,
                "Awarding Agency": agency,
                "Award Type": "Contract",
                "Description": description,
                "Start Date": "2024-02-20",
                "End Date": "2026-02-20",
                "Place of Performance": "United States",
                "Recipient State": "US",
            }
        ]

    def _mock_state_contracts(self, state: str) -> list[dict[str, Any]]:
        """Generate plausible contract data for any state."""
        state_upper = state.upper()
        state_name = _STATE_NAMES.get(state_upper, state_upper)
        hash_hex = hashlib.md5(state_upper.encode()).hexdigest()
        hash_int = int(hash_hex, 16)

        # Generate 3 contracts per state
        contracts = []
        for i in range(3):
            c_hash = hash_int + i * 7919
            tmpl_idx = c_hash % len(_CONTRACT_TEMPLATES)
            suffix, description, agency, base_amount = _CONTRACT_TEMPLATES[tmpl_idx]
            county_idx = c_hash % len(_COUNTY_POOL)

            amount = base_amount + (c_hash % 10) * 500000
            agency_prefix = agency.split()[-1][:3].upper()
            company_name = f"{state_name} {suffix}"
            location = f"{_COUNTY_POOL[county_idx]}, {state_upper}"

            contracts.append(
                {
                    "Award ID": f"{agency_prefix}-{state_upper}-2024-{c_hash % 9999:04d}",
                    "Recipient Name": company_name,
                    "Award Amount": amount,
                    "Awarding Agency": agency,
                    "Award Type": "Contract",
                    "Description": f"{description}, {state_name}",
                    "Start Date": "2024-02-20",
                    "End Date": f"202{6 + (c_hash % 3)}-02-20",
                    "Place of Performance": location,
                    "Recipient State": state_upper,
                }
            )

        return contracts
