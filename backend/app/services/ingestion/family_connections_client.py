"""
Family Connections Client — Senate eFD Spouse/Dependent Income
Real source: Senate Electronic Financial Disclosures, spouse employment section
Currently returns mock data matching real eFD response shapes.
"""
import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

_EMPLOYERS = [
    ("JPMorgan Chase & Co.", "Senior Community Development Consultant", 185000),
    ("Goldman Sachs Group", "Vice President, Public Affairs", 210000),
    ("Deloitte Consulting", "Managing Director", 195000),
    ("McKinsey & Company", "Senior Partner", 275000),
    ("Microsoft Corporation", "Director of Government Relations", 165000),
    ("Amazon Web Services", "Head of Public Policy", 190000),
    ("Pfizer Inc.", "Regional Affairs Director", 170000),
    ("Boeing Company", "Senior Policy Analyst", 155000),
    ("Lockheed Martin", "Director of Strategic Partnerships", 180000),
    ("UnitedHealth Group", "VP of Community Programs", 200000),
    ("General Electric", "Senior Government Liaison", 160000),
    ("Raytheon Technologies", "Director of Federal Programs", 175000),
]

_SECONDARY_EMPLOYERS = [
    ("Family Foundation", "Executive Director", 95000),
    ("State University Board", "Trustee (compensated)", 45000),
    ("Community Health Network", "Board Member", 60000),
    ("Regional Development Corp", "Advisory Board Chair", 55000),
    ("Children's Education Fund", "President", 85000),
    ("Local Hospital Foundation", "Board Director", 50000),
    ("Arts & Culture Council", "Executive Board Member", 40000),
    ("Veterans Support Alliance", "Program Director", 72000),
]

_SPOUSE_FIRST_NAMES = [
    "Sarah", "Michael", "Jennifer", "David", "Maria", "James",
    "Patricia", "Robert", "Linda", "Thomas", "Elizabeth", "Christopher",
]

_SPOUSE_LAST_SUFFIXES = [
    "Williams", "Chen", "Martinez", "O'Brien", "Patel", "Thompson",
    "Rivera", "Nakamura", "Kowalski", "Hassan", "Bergström", "Okafor",
]


class FamilyConnectionsClient:
    """Parses Senate eFD data for spouse/dependent employment and income."""

    def __init__(self):
        self._use_mock = True

    async def fetch_family_income(self, senator_name: str) -> list[dict[str, Any]]:
        """Fetch spouse and dependent income from eFD filings."""
        if self._use_mock:
            return self._mock_family_income(senator_name)
        raise NotImplementedError("Real eFD parsing not yet implemented")

    def _mock_family_income(self, senator_name: str) -> list[dict[str, Any]]:
        """Mock data matching eFD spouse/dependent income format."""
        hash_hex = hashlib.md5(senator_name.encode()).hexdigest()
        hash_int = int(hash_hex, 16)

        # ~60% of officials have family connections
        if hash_int % 10 >= 6:
            return []

        # Pick a spouse name
        first_idx = hash_int % len(_SPOUSE_FIRST_NAMES)
        last_idx = (hash_int // 7) % len(_SPOUSE_LAST_SUFFIXES)
        spouse_name = f"{_SPOUSE_FIRST_NAMES[first_idx]} {_SPOUSE_LAST_SUFFIXES[last_idx]}"

        # Pick primary employer
        emp_idx = hash_int % len(_EMPLOYERS)
        employer, position, income = _EMPLOYERS[emp_idx]

        results = [
            {
                "filer": senator_name,
                "report_type": "Annual Report",
                "report_year": 2024,
                "family_member": spouse_name,
                "relationship": "spouse",
                "employer": employer,
                "position": position,
                "income_amount": income,
                "income_type": "salary",
                "asset_category": "employment_income",
                "source_url": f"https://efdsearch.senate.gov/search/view/annual/mock-{hash_hex[:6]}/",
            },
        ]

        # ~50% also have a secondary position
        if (hash_int // 3) % 2 == 0:
            sec_idx = (hash_int // 11) % len(_SECONDARY_EMPLOYERS)
            sec_employer, sec_position, sec_income = _SECONDARY_EMPLOYERS[sec_idx]
            # Personalize foundation names
            last_name = senator_name.split()[-1] if " " in senator_name else senator_name
            sec_employer = sec_employer.replace("Family Foundation", f"{last_name} Family Foundation")
            results.append(
                {
                    "filer": senator_name,
                    "report_type": "Annual Report",
                    "report_year": 2024,
                    "family_member": spouse_name,
                    "relationship": "spouse",
                    "employer": sec_employer,
                    "position": sec_position,
                    "income_amount": sec_income,
                    "income_type": "salary",
                    "asset_category": "employment_income",
                    "source_url": f"https://efdsearch.senate.gov/search/view/annual/mock-{hash_hex[:6]}/",
                }
            )

        return results
