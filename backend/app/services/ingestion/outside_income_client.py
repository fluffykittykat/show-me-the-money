"""
Outside Income Client — Senate eFD Non-Investment Income
Real source: Senate eFD non-investment income section (speaking fees, book deals, honoraria)
Currently returns mock data matching real eFD response shapes.
"""
import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

_SPEAKING_PAYERS = [
    ("Financial Services Roundtable", "financial_services", True, "Annual Policy Summit keynote address"),
    ("American Bankers Association", "financial_services", True, "Banking Leadership Conference"),
    ("National Association of Manufacturers", "manufacturing", True, "Industry Future Forum"),
    ("Chamber of Commerce", "business", True, "Annual Business Summit"),
    ("Brookings Institution", "think_tank", False, "Policy Discussion Panel"),
    ("Heritage Foundation", "think_tank", True, "Conservative Policy Forum"),
    ("Center for American Progress", "think_tank", True, "Progressive Policy Summit"),
    ("Council on Foreign Relations", "foreign_policy", False, "Global Affairs Symposium"),
    ("Aspen Institute", "think_tank", False, "Ideas Festival"),
    ("World Economic Forum", "international", False, "Annual Meeting panel"),
    ("American Enterprise Institute", "think_tank", True, "Economic Policy Conference"),
    ("Cato Institute", "think_tank", False, "Freedom & Governance Forum"),
    ("RAND Corporation", "think_tank", False, "National Security Symposium"),
    ("Peterson Institute for International Economics", "think_tank", False, "Global Trade Summit"),
    ("Hoover Institution", "think_tank", False, "Policy Retreat keynote"),
    ("National Association of Realtors", "real_estate", True, "Legislative Conference"),
    ("American Medical Association", "healthcare", True, "Health Policy Forum"),
    ("PhRMA Annual Conference", "pharmaceutical", True, "Innovation Summit keynote"),
    ("American Bar Association", "legal", False, "Annual Convention address"),
    ("National Governors Association", "government", False, "Winter Meeting keynote"),
    ("AIPAC Policy Conference", "foreign_policy", True, "Policy Conference address"),
    ("Business Roundtable", "business", True, "CEO Summit keynote"),
    ("National League of Cities", "government", False, "Congressional Forum"),
    ("American Farm Bureau Federation", "agriculture", True, "Annual Convention address"),
    ("Securities Industry and Financial Markets Association", "financial_services", True, "Annual Meeting keynote"),
    ("Consumer Technology Association", "technology", True, "CES Policy Forum"),
    ("American Petroleum Institute", "energy", True, "Energy Summit address"),
    ("National Mining Association", "energy", True, "Annual Conference keynote"),
    ("Insurance Information Institute", "insurance", True, "Risk & Policy Forum"),
    ("National Retail Federation", "retail", True, "Retail Advocacy Summit"),
    ("U.S.-China Business Council", "international", True, "Trade Policy Forum"),
]

_BOOK_PUBLISHERS = [
    ("HarperCollins Publishers", "News Corp", "Book advance: memoir"),
    ("Simon & Schuster", "Paramount Global", "Book advance: policy vision"),
    ("Penguin Random House", "Bertelsmann", "Book advance: leadership reflections"),
    ("Hachette Book Group", "Lagardère", "Book royalties: political memoir"),
    ("Macmillan Publishers", "Holtzbrinck", "Book advance: public service journey"),
    ("W.W. Norton & Company", "Employee-owned", "Book advance: American governance"),
    ("Crown Publishing Group", "Penguin Random House", "Book royalties: personal narrative"),
    ("Little, Brown and Company", "Hachette Book Group", "Book advance: public policy essays"),
    ("St. Martin's Press", "Macmillan", "Book advance: political biography"),
    ("Knopf Doubleday", "Penguin Random House", "Book royalties: national security memoir"),
    ("Scribner", "Simon & Schuster", "Book advance: leadership principles"),
]

_HONORARIA_PAYERS = [
    ("Harvard University", "education", "Commencement address"),
    ("University of Michigan", "education", "Distinguished lecture series"),
    ("Stanford University", "education", "Public policy lecture"),
    ("Georgetown University", "education", "Graduation keynote"),
    ("MIT", "education", "Technology and governance lecture"),
    ("Columbia University", "education", "Commencement address"),
    ("Duke University", "education", "Public leadership forum"),
    ("University of Virginia", "education", "Miller Center address"),
    ("Yale University", "education", "Political leadership lecture"),
    ("Princeton University", "education", "Woodrow Wilson School address"),
    ("Northwestern University", "education", "Public affairs lecture"),
    ("University of Chicago", "education", "Harris School policy forum"),
    ("Johns Hopkins University", "education", "SAIS Distinguished Lecture"),
    ("UC Berkeley", "education", "Goldman School policy address"),
    ("University of Pennsylvania", "education", "Fels Institute keynote"),
    ("Vanderbilt University", "education", "Chancellor's Lecture Series"),
    ("Emory University", "education", "Distinguished faculty lecture"),
    ("Carnegie Mellon University", "education", "Heinz College policy forum"),
    ("Brown University", "education", "Watson Institute address"),
    ("George Washington University", "education", "Elliott School keynote"),
    ("National Constitution Center", "civic", "Liberty Medal Forum"),
    ("Smithsonian Institution", "civic", "American History Lecture"),
]


class OutsideIncomeClient:
    """Parses Senate eFD data for speaking fees, book deals, and other non-investment income."""

    def __init__(self):
        self._use_mock = True

    async def fetch_outside_income(self, senator_name: str) -> list[dict[str, Any]]:
        """Fetch non-investment income from eFD filings."""
        if self._use_mock:
            return self._mock_outside_income(senator_name)
        raise NotImplementedError("Real eFD parsing not yet implemented")

    def _mock_outside_income(self, senator_name: str) -> list[dict[str, Any]]:
        """Mock data matching eFD non-investment income format."""
        seed = f"{senator_name}income"
        hash_hex = hashlib.md5(seed.encode()).hexdigest()
        hash_int = int(hash_hex, 16)

        # ~60% of officials have outside income
        if hash_int % 10 >= 6:
            return []

        mock_id = hash_hex[:6]
        results = []

        # Speaking fee (most common)
        sp_idx = hash_int % len(_SPEAKING_PAYERS)
        payer, industry, is_lobby, desc = _SPEAKING_PAYERS[sp_idx]
        amount = 50000 + (hash_int % 8) * 12500
        results.append(
            {
                "filer": senator_name,
                "report_year": 2025,
                "payer": payer,
                "income_type": "speaking_fee",
                "amount": amount,
                "date": "2025-03-15",
                "description": desc,
                "payer_industry": industry,
                "is_lobbying_org": is_lobby,
                "source_url": f"https://efdsearch.senate.gov/search/view/annual/mock-{mock_id}/",
            }
        )

        # Book deal (~40%)
        if (hash_int // 5) % 5 < 2:
            bk_idx = (hash_int // 13) % len(_BOOK_PUBLISHERS)
            publisher, parent, desc = _BOOK_PUBLISHERS[bk_idx]
            book_amount = 100000 + (hash_int % 6) * 50000
            results.append(
                {
                    "filer": senator_name,
                    "report_year": 2024,
                    "payer": publisher,
                    "income_type": "book_advance",
                    "amount": book_amount,
                    "date": "2024-11-01",
                    "description": desc,
                    "payer_industry": "media",
                    "is_lobbying_org": False,
                    "parent_company": parent,
                    "source_url": f"https://efdsearch.senate.gov/search/view/annual/mock-{mock_id}/",
                }
            )

        # Honorarium (~50%)
        if (hash_int // 3) % 2 == 0:
            hon_idx = (hash_int // 17) % len(_HONORARIA_PAYERS)
            hon_payer, hon_industry, hon_desc = _HONORARIA_PAYERS[hon_idx]
            hon_amount = 10000 + (hash_int % 5) * 5000
            results.append(
                {
                    "filer": senator_name,
                    "report_year": 2025,
                    "payer": hon_payer,
                    "income_type": "honorarium",
                    "amount": hon_amount,
                    "date": "2025-06-20",
                    "description": hon_desc,
                    "payer_industry": hon_industry,
                    "is_lobbying_org": False,
                    "source_url": f"https://efdsearch.senate.gov/search/view/annual/mock-{mock_id}/",
                }
            )

        return results
