"""
Family Connections Client — Senate eFD Spouse/Dependent Income
Real source: Senate Electronic Financial Disclosures, spouse employment section
Currently returns mock data matching real eFD response shapes.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


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
        if "fetterman" not in senator_name.lower():
            return []
        return [
            {
                "filer": "John Fetterman",
                "report_type": "Annual Report",
                "report_year": 2024,
                "family_member": "Gisele Barreto Fetterman",
                "relationship": "spouse",
                "employer": "JPMorgan Chase & Co.",
                "position": "Senior Community Development Consultant",
                "income_amount": 185000,
                "income_type": "salary",
                "asset_category": "employment_income",
                "source_url": "https://efdsearch.senate.gov/search/view/annual/mock-001/",
            },
            {
                "filer": "John Fetterman",
                "report_type": "Annual Report",
                "report_year": 2024,
                "family_member": "Gisele Barreto Fetterman",
                "relationship": "spouse",
                "employer": "Fetterman Foundation",
                "position": "Executive Director",
                "income_amount": 95000,
                "income_type": "salary",
                "asset_category": "employment_income",
                "source_url": "https://efdsearch.senate.gov/search/view/annual/mock-001/",
            },
        ]
