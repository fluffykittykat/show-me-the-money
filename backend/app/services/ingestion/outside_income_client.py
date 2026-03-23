"""
Outside Income Client — Senate eFD Non-Investment Income
Real source: Senate eFD non-investment income section (speaking fees, book deals, honoraria)
Currently returns mock data matching real eFD response shapes.
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)


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
        if "fetterman" not in senator_name.lower():
            return []
        return [
            {
                "filer": "John Fetterman",
                "report_year": 2025,
                "payer": "Financial Services Roundtable",
                "income_type": "speaking_fee",
                "amount": 75000,
                "date": "2025-03-15",
                "description": "Annual Policy Summit 2025 keynote address",
                "payer_industry": "financial_services",
                "is_lobbying_org": True,
                "source_url": "https://efdsearch.senate.gov/search/view/annual/mock-002/",
            },
            {
                "filer": "John Fetterman",
                "report_year": 2024,
                "payer": "HarperCollins Publishers",
                "income_type": "book_advance",
                "amount": 200000,
                "date": "2024-11-01",
                "description": "Book advance: 'From Braddock to the Senate'",
                "payer_industry": "media",
                "is_lobbying_org": False,
                "parent_company": "News Corp",
                "source_url": "https://efdsearch.senate.gov/search/view/annual/mock-002/",
            },
            {
                "filer": "John Fetterman",
                "report_year": 2025,
                "payer": "University of Pittsburgh",
                "income_type": "honorarium",
                "amount": 15000,
                "date": "2025-06-20",
                "description": "Commencement address",
                "payer_industry": "education",
                "is_lobbying_org": False,
                "source_url": "https://efdsearch.senate.gov/search/view/annual/mock-002/",
            },
        ]
