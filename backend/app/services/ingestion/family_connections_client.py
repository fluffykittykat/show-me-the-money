"""
Family Connections Client — Senate eFD Spouse/Dependent Income
Real source: Senate Electronic Financial Disclosures, spouse employment section
Currently returns mock data matching real eFD response shapes.
"""
import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

_FIRST_NAMES = [
    "Sarah", "Michael", "Jennifer", "David", "Maria", "James", "Patricia", "Robert",
    "Linda", "Thomas", "Elizabeth", "Christopher", "Angela", "William", "Susan",
    "Richard", "Karen", "Joseph", "Nancy", "Charles", "Margaret", "Daniel",
    "Barbara", "Matthew", "Dorothy", "Andrew", "Lisa", "Kenneth", "Sandra",
    "Steven", "Ashley", "Edward", "Kimberly", "Brian", "Donna", "Timothy",
    "Carol", "Jason", "Michelle", "Jeffrey", "Amanda", "Laura",
]

_LAST_NAMES = [
    "Williams", "Chen", "Martinez", "O'Brien", "Patel", "Thompson", "Rivera",
    "Nakamura", "Kowalski", "Hassan", "Bergström", "Okafor", "Fitzgerald",
    "Dubois", "Castillo", "Johansson", "Brennan", "Alvarez", "Whitaker",
    "Nguyen", "Hartwell", "Bianchi", "Prescott", "Delgado", "Eriksson",
    "Sullivan", "Kim", "Moreau", "Andersen", "Gupta", "Romano", "Weber",
    "Larsson", "Takahashi", "Müller", "Santos", "Park", "Ivanova", "Campbell",
    "Mitchell", "Reeves", "Foster",
]

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
    ("Citigroup Inc.", "Managing Director, Public Sector", 220000),
    ("Merck & Co.", "Director of Health Policy", 185000),
    ("Accenture Federal Services", "Senior Managing Director", 205000),
    ("EY (Ernst & Young)", "Partner, Government Advisory", 240000),
    ("KPMG LLP", "Director of Public Policy Practice", 195000),
    ("PricewaterhouseCoopers", "Partner, Federal Practice", 230000),
    ("Northrop Grumman", "VP of Government Relations", 210000),
    ("General Dynamics", "Director of Legislative Affairs", 190000),
    ("Anthem Blue Cross", "VP of Federal Programs", 200000),
    ("Humana Inc.", "Director of Government Markets", 175000),
    ("Intel Corporation", "Head of Policy & Government Affairs", 195000),
    ("Qualcomm Inc.", "VP of Government Affairs", 185000),
    ("Chevron Corporation", "Director of Public Affairs", 180000),
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
        seed = f"{senator_name}family"
        hash_hex = hashlib.md5(seed.encode()).hexdigest()
        hash_int = int(hash_hex, 16)

        # ~50% of officials have family connections
        if hash_int % 10 >= 5:
            return []

        # Pick a family member name from independent first/last pools
        first_idx = hash_int % len(_FIRST_NAMES)
        last_idx = (hash_int // 7919) % len(_LAST_NAMES)
        family_member_name = f"{_FIRST_NAMES[first_idx]} {_LAST_NAMES[last_idx]}"

        # Pick primary employer
        emp_idx = hash_int % len(_EMPLOYERS)
        employer, position, income = _EMPLOYERS[emp_idx]

        results = [
            {
                "filer": senator_name,
                "report_type": "Annual Report",
                "report_year": 2024,
                "family_member": family_member_name,
                "relationship": "family member",
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
                    "family_member": family_member_name,
                    "relationship": "family member",
                    "employer": sec_employer,
                    "position": sec_position,
                    "income_amount": sec_income,
                    "income_type": "salary",
                    "asset_category": "employment_income",
                    "source_url": f"https://efdsearch.senate.gov/search/view/annual/mock-{hash_hex[:6]}/",
                }
            )

        return results
